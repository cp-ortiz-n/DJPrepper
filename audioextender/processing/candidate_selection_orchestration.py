"""Candidate selection, customization, validation, and rescue orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from audioextender.analysis.candidate_reranker import assess_candidate
from audioextender.analysis.candidate_selection import Position
from audioextender.analysis.candidate_validator import CandidateValidator
from audioextender.analysis.section_selector import SectionCandidate
from audioextender.analysis.selection_coordinator import SelectionCoordinator, SideSelectionRequest
from audioextender.audio.redrum import select_redrum_candidate
from audioextender.audio.stem_provider import StemProvider
from audioextender.core.defaults import DEFAULT_CANDIDATE_COUNT, DJ_READY_MINIMUM_BARS, MINIMUM_REDRUM_STEM_RELIABILITY
from audioextender.core.exceptions import StemSeparationError
from audioextender.core.interfaces import ProgressReporter
from audioextender.library.export_service import ExportService
from audioextender.processing.extended_edit import optimize_candidate_boundaries
from audioextender.processing.track_processing_stages import AnalysisStageResult, SelectionStageResult


def format_time(seconds: float) -> str:
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def parse_timestamp(value: str) -> float:
    """Parse seconds or M:SS entered at an interactive prompt."""
    value = value.strip()
    try:
        if ":" not in value:
            result = float(value)
        else:
            minutes, seconds = value.split(":", 1)
            result = 60.0 * float(minutes) + float(seconds)
    except ValueError as error:
        raise ValueError("Enter a timestamp such as 75, 75.5, or 1:15.") from error
    if result < 0:
        raise ValueError("Timestamp cannot be negative.")
    return result


def pick_ranked_candidate(
    candidates: list[SectionCandidate],
    position: Position,
    requested_rank: int,
    interactive: bool,
    progress: ProgressReporter,
    audition: Callable[[list[SectionCandidate]], None] | None = None,
) -> tuple[SectionCandidate | None, int | None]:
    """Display ranked alternatives when requested and return the chosen one."""
    if not candidates:
        raise RuntimeError(f"No {position} candidates are available")
    if requested_rank > len(candidates):
        raise RuntimeError(
            f"Requested {position} candidate {requested_rank}, but only {len(candidates)} distinct option(s) exist"
        )
    if not interactive:
        if requested_rank == 0:
            progress.log(f"No {position} candidate selected")
            return None, None
        return candidates[requested_rank - 1], requested_rank

    pause = getattr(progress, "pause_for_input", lambda: None)
    resume = getattr(progress, "resume_after_input", lambda: None)
    page_start = 0
    while True:
        page = candidates[page_start : page_start + DEFAULT_CANDIDATE_COUNT]
        if audition is not None:
            audition(page)
        pause()
        print(f"{position.title()} candidates:")
        for local_rank, candidate in enumerate(page, start=1):
            assessment = assess_candidate(candidate, position, None)
            print(
                f"  {local_rank}. {format_time(candidate.start)}–{format_time(candidate.end)}  "
                f"phrase {assessment.phrase:.0f}%  ·  loop {assessment.loop:.0f}%  ·  "
                f"transition {assessment.transition:.0f}%  ·  "
                f"section {candidate.section_label}  ·  "
                f"buildup {candidate.buildup_risk:.0%}  ·  bass reset "
                f"{candidate.bass_reset_risk:.0%}  ·  unique {candidate.unit_bars} bars"
            )
        print("  0. None — do not create this extension")
        if page_start + len(page) < len(candidates):
            print("  R. Reject these and show the next options")
        print("  C. Choose the candidate nearest a custom source-time range")
        page_default_rank = requested_rank if page_start == 0 else page_start + 1
        default_label = "none" if page_default_rank == 0 else "1"
        response = (
            input(f"Choose {position} candidate [0-{len(page)}, R, C] (Enter for {default_label}): ").strip().upper()
        )
        if not response:
            resume()
            if page_default_rank == 0:
                return None, None
            return candidates[page_default_rank - 1], page_default_rank
        if response == "0":
            resume()
            return None, None
        if response == "R" and page_start + len(page) < len(candidates):
            page_start += len(page)
            resume()
            continue
        if response == "C":
            try:
                custom_start = parse_timestamp(input("Custom source start (seconds or M:SS): "))
                custom_end = parse_timestamp(input("Custom source end (seconds or M:SS): "))
            except ValueError as error:
                print(error)
                continue
            if custom_end <= custom_start:
                print("Custom end must be later than custom start.")
                continue
            chosen = min(
                candidates,
                key=lambda candidate: abs(candidate.start - custom_start) + abs(candidate.end - custom_end),
            )
            rank = candidates.index(chosen) + 1
            print(f"Snapped to ranked candidate {rank}: {format_time(chosen.start)}–{format_time(chosen.end)}")
            resume()
            return chosen, rank
        if response.isdigit() and 1 <= int(response) <= len(page):
            local_rank = int(response)
            rank = page_start + local_rank
            resume()
            return candidates[rank - 1], rank
        print(f"Please enter 0–{len(page)}, R, or C.")


class CandidateSelectionOrchestrator:
    """Turn prepared analysis facts into validated construction choices."""

    def __init__(
        self,
        stem_provider: StemProvider,
        selection_coordinator: SelectionCoordinator,
        export_service: ExportService,
        candidate_validator: CandidateValidator,
    ) -> None:
        self._stem_provider = stem_provider
        self._selection_coordinator = selection_coordinator
        self._export_service = export_service
        self._candidate_validator = candidate_validator

    def select(
        self,
        source: Path,
        output: Path,
        stage: AnalysisStageResult,
        progress: ProgressReporter,
        outro_before: float | None,
    ) -> SelectionStageResult:
        audio = stage.audio
        analysis = stage.analysis
        config = stage.config
        instrumental_audio = stage.instrumental_audio
        drums_audio = stage.drums_audio
        stem_reliability = stage.stem_reliability
        vocal_cache_hit = stage.vocal_cache_hit
        intro_before = stage.intro_before
        outro_after = stage.outro_after
        automatic_intro_boundary = stage.automatic_intro_boundary
        automatic_outro_boundary = stage.automatic_outro_boundary
        readiness = stage.readiness

        intro_already_ready = (
            not config.intro_bars_locked
            and config.intro_bars > 0
            and readiness.intro.mixable_bars >= max(DJ_READY_MINIMUM_BARS, config.intro_bars)
        )
        outro_already_ready = (
            not config.outro_bars_locked
            and config.outro_bars > 0
            and readiness.outro.mixable_bars >= max(DJ_READY_MINIMUM_BARS, config.outro_bars)
        )
        intro_preservation_reason = None
        outro_preservation_reason = None
        if intro_already_ready:
            intro_preservation_reason = (
                f"already DJ-ready with {readiness.intro.mixable_bars} consecutive mixable opening bars"
            )
            progress.log(f"Intro preserved: {intro_preservation_reason}")
            config = replace(config, intro_bars=0)
        if outro_already_ready:
            outro_preservation_reason = (
                f"already DJ-ready with {readiness.outro.mixable_bars} consecutive mixable closing bars"
            )
            progress.log(f"Outro preserved: {outro_preservation_reason}")
            config = replace(config, outro_bars=0)

        progress.update(80, "Scoring intro phrases")
        reviews: dict[str, tuple[str | None, str | None]] = {}

        def choose_side(
            options: list[SectionCandidate], position: Position, requested_rank: int
        ) -> tuple[SectionCandidate | None, int | None]:
            chosen, rank = pick_ranked_candidate(
                options,
                position,
                requested_rank,
                config.choose_candidates,
                progress,
                lambda page: self._export_service.export_candidate_auditions(
                    audio,
                    page,
                    position,
                    source,
                    output,
                    config,
                    progress,
                    instrumental_audio,
                    stem_reliability,
                ),
            )
            if config.review_mode:
                pause = getattr(progress, "pause_for_input", lambda: None)
                resume = getattr(progress, "resume_after_input", lambda: None)
                pause()
                print("Feedback tags: good, chopped, wrong phrase, vocals, buildup, bass reset, too repetitive, other")
                reason = input(f"Why did you choose this {position} option? (comma-separated, optional): ").strip()
                notes = input("Notes (optional): ").strip()
                reviews[position] = (reason or None, notes or None)
                resume()
            return chosen, rank

        if config.intro_bars == 0:
            progress.log("Extended intro disabled")
        elif intro_before is not None:
            source_label = "automatic vocal detection" if automatic_intro_boundary else "manual rule"
            progress.log(
                f"Protected vocal entrance: intro source must end before {format_time(intro_before)} ({source_label})"
            )
        prefer_instrumental = (
            instrumental_audio is not None and stem_reliability >= config.minimum_stem_construction_reliability
        )
        intro_selection = self._selection_coordinator.select(
            analysis,
            audio.duration,
            stage.vocal_energy,
            config,
            SideSelectionRequest(
                position="intro",
                bars=config.intro_bars,
                bars_locked=config.intro_bars_locked,
                search_seconds=config.intro_search_seconds,
                requested_rank=config.intro_candidate,
                count=config.candidate_count,
                maximum_end=intro_before,
                automatic_boundary=automatic_intro_boundary,
            ),
            choose_side,
            progress,
            prefer_instrumental,
        )
        intro = intro_selection.candidate
        intro_candidate_rank = intro_selection.rank
        intro_before = intro_selection.maximum_end
        automatic_intro_boundary = intro_selection.automatic_boundary
        intro_fallback = intro_selection.fallback

        progress.update(85, "Scoring outro phrases")
        if config.outro_bars == 0:
            progress.log("Extended outro disabled; preserving original ending")
        else:
            if outro_after is not None and outro_before is not None and outro_after >= outro_before:
                raise ValueError("outro_after must be earlier than outro_before")
            if outro_after is not None:
                source_label = "automatic vocal detection" if automatic_outro_boundary else "manual rule"
                progress.log(
                    "Protected vocal release: outro source must begin after "
                    f"{format_time(outro_after)} ({source_label})"
                )
            if outro_before is not None:
                progress.log(
                    f"Protected closing section: outro source must end before {format_time(outro_before)} (manual rule)"
                )
        outro_selection = self._selection_coordinator.select(
            analysis,
            audio.duration,
            stage.vocal_energy,
            config,
            SideSelectionRequest(
                position="outro",
                bars=config.outro_bars,
                bars_locked=config.outro_bars_locked,
                search_seconds=config.outro_search_seconds,
                requested_rank=config.outro_candidate,
                count=config.candidate_count,
                maximum_end=outro_before,
                minimum_start=outro_after,
                automatic_boundary=automatic_outro_boundary,
            ),
            choose_side,
            progress,
            prefer_instrumental,
        )
        outro = outro_selection.candidate
        outro_candidate_rank = outro_selection.rank
        outro_before = outro_selection.maximum_end
        outro_after = outro_selection.minimum_start
        automatic_outro_boundary = outro_selection.automatic_boundary
        outro_fallback = outro_selection.fallback

        def custom_candidate(
            position: Position,
            start: float | None,
            end: float | None,
            copies: int,
            options: tuple[SectionCandidate, ...],
        ) -> SectionCandidate | None:
            if start is None or end is None:
                return None
            if end > audio.duration:
                raise ValueError(f"Custom {position} ends after the source track")
            base = (
                min(options, key=lambda item: abs(item.start - start) + abs(item.end - end))
                if options
                else SectionCandidate(start, end, 0.0, 0.5, 0.5, 0.5)
            )
            beat_seconds = 60.0 / max(analysis.bpm, 1.0)
            bars = max(1, round((end - start) / (beat_seconds * config.beats_per_bar)))
            progress.log(
                f"Custom {position}: {format_time(start)} - {format_time(end)} ({bars}-bar estimate ×{copies})"
            )
            return replace(
                base,
                start=start,
                end=end,
                unit_bars=bars,
                repetitions=copies,
                section_label="custom selection",
            )

        intro_rejection_reason = intro_preservation_reason
        outro_rejection_reason = outro_preservation_reason
        if config.custom_intro_start is not None:
            intro = custom_candidate(
                "intro",
                config.custom_intro_start,
                config.custom_intro_end,
                config.custom_intro_copies,
                intro_selection.options,
            )
            intro_candidate_rank = None
            intro_rejection_reason = None
        if config.custom_outro_start is not None:
            outro = custom_candidate(
                "outro",
                config.custom_outro_start,
                config.custom_outro_end,
                config.custom_outro_copies,
                outro_selection.options,
            )
            outro_candidate_rank = None
            outro_rejection_reason = None

        if config.create_candidate_auditions:
            for position, options in (("intro", intro_selection.options), ("outro", outro_selection.options)):
                if options:
                    self._export_service.export_candidate_auditions(
                        audio,
                        list(options[: config.candidate_count]),
                        position,
                        source,
                        output,
                        config,
                        progress,
                        instrumental_audio,
                        stem_reliability,
                    )

        progress.update(88, "Optimizing loop boundaries")
        if intro is not None:
            intro = optimize_candidate_boundaries(audio, intro)
            progress.log(
                f"Intro candidate: {format_time(intro.start)} - {format_time(intro.end)} "
                f"({intro.unit_bars}-bar unit ×{intro.repetitions}, score={intro.score:.2f}, "
                f"instrumental={intro.instrumentalness:.2f})"
            )
        if outro is not None:
            outro = optimize_candidate_boundaries(audio, outro)
            progress.log(
                f"Outro candidate: {format_time(outro.start)} - {format_time(outro.end)} "
                f"({outro.unit_bars}-bar unit ×{outro.repetitions}, score={outro.score:.2f}, "
                f"instrumental={outro.instrumentalness:.2f})"
            )
        intro_validation = self._candidate_validator.validate(
            intro,
            config,
            instrumental_audio,
            stem_reliability,
            stage.vocal_energy is not None,
            position="intro",
        )
        outro_validation = self._candidate_validator.validate(
            outro,
            config,
            instrumental_audio,
            stem_reliability,
            stage.vocal_energy is not None,
            position="outro",
        )
        intro = intro_validation.candidate
        outro = outro_validation.candidate
        intro_rejection_reason = intro_validation.rejection_reason or intro_preservation_reason
        outro_rejection_reason = outro_validation.rejection_reason or outro_preservation_reason
        redrum_intro = False
        high_quality_drums = None
        if (
            intro is None
            and config.intro_bars > 0
            and (
                (intro_rejection_reason is not None and "exposed melodic phrase" in intro_rejection_reason)
                or not intro_selection.options
            )
        ):
            redrum_candidate = select_redrum_candidate(analysis, config.intro_bars, audio.duration)
            if redrum_candidate is not None:
                intro = redrum_candidate
                reason = intro_rejection_reason or intro_selection.fallback or "no safe full-mix phrase"
                intro_fallback = f"rejected {reason}; automatic percussion redrum"
                intro_rejection_reason = None
                redrum_intro = True
                progress.log(
                    "Intro fallback: exposed melody protected; creating a "
                    f"{config.intro_bars}-bar percussion redrum from "
                    f"{format_time(intro.start)}–{format_time(intro.end)}"
                )
        if redrum_intro:
            if drums_audio is None or stem_reliability < MINIMUM_REDRUM_STEM_RELIABILITY:
                cached_drums = stage.cache.load_drums(source, config)
                cached_instrumental = stage.cache.load_instrumental(source, config)
                if cached_drums is not None and cached_instrumental is not None:
                    drums_audio = cached_drums
                    stem_reliability = cached_instrumental[1]
                    progress.log("Loaded cached Demucs drums for melodic intro rescue")
            if drums_audio is None or stem_reliability < MINIMUM_REDRUM_STEM_RELIABILITY:
                progress.log("Melodic intro rescue requires clean drums; running Demucs only for this track")
                try:
                    rescue = self._stem_provider.analyze(
                        source,
                        audio,
                        analysis,
                        replace(config, use_stems=True, refresh_cache=False),
                        stage.cache,
                        progress,
                    )
                except StemSeparationError as error:
                    intro = None
                    redrum_intro = False
                    intro_rejection_reason = f"melodic intro needs a clean drum stem; Demucs unavailable: {error}"
                else:
                    drums_audio = rescue.drums_audio
                    instrumental_audio = rescue.instrumental_audio
                    stem_reliability = rescue.reliability
                    vocal_cache_hit = rescue.cache_hit
            if redrum_intro and drums_audio is not None and stem_reliability >= MINIMUM_REDRUM_STEM_RELIABILITY:
                high_quality_drums = drums_audio
            elif redrum_intro:
                intro = None
                redrum_intro = False
                intro_rejection_reason = (
                    "melodic intro needs a reliable Demucs drum stem "
                    f"({stem_reliability:.0%} below {MINIMUM_REDRUM_STEM_RELIABILITY:.0%})"
                )
        if intro_rejection_reason:
            progress.log(f"Intro disabled: {intro_rejection_reason}")
        elif intro_validation.shortened:
            progress.log(f"Intro shortened to {config.maximum_repetitions} repeats by preset")
        if outro_rejection_reason:
            progress.log(f"Outro disabled: {outro_rejection_reason}")
        elif outro_validation.shortened:
            progress.log(f"Outro shortened to {config.maximum_repetitions} repeats by preset")

        return SelectionStageResult(
            config=config,
            intro=intro,
            outro=outro,
            intro_selection=intro_selection,
            outro_selection=outro_selection,
            reviews=reviews,
            intro_before=intro_before,
            outro_after=outro_after,
            outro_before=outro_before,
            automatic_intro_boundary=automatic_intro_boundary,
            automatic_outro_boundary=automatic_outro_boundary,
            intro_candidate_rank=intro_candidate_rank,
            outro_candidate_rank=outro_candidate_rank,
            intro_rejection_reason=intro_rejection_reason,
            outro_rejection_reason=outro_rejection_reason,
            intro_fallback=intro_fallback,
            outro_fallback=outro_fallback,
            intro_already_ready=intro_already_ready,
            outro_already_ready=outro_already_ready,
            redrum_intro=redrum_intro,
            high_quality_drums=high_quality_drums,
            instrumental_audio=instrumental_audio,
            stem_reliability=stem_reliability,
            vocal_cache_hit=vocal_cache_hit,
        )
