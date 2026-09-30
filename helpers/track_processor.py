"""Single-track application service connecting the processing pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from helpers.analysis import TrackAnalysis, analyze_track
from helpers.audio_loader import load_audio
from helpers.cache import AnalysisCache
from helpers.candidate_reranker import assess_candidate
from helpers.candidate_selection import Position
from helpers.candidate_validator import CandidateValidator
from helpers.config import EditConfig
from helpers.dj_readiness import detect_dj_readiness
from helpers.exceptions import StemSeparationError
from helpers.export_service import ExportRequest, ExportService
from helpers.extended_edit import (
    adaptive_crossfade_ms,
    create_extended_edit,
    insert_audio_region,
    optimize_candidate_boundaries,
    should_use_instrumental,
)
from helpers.interfaces import ProgressReporter
from helpers.models import FileResult, TrackArrangementSection
from helpers.presets import PRESETS
from helpers.progress import ProgressBar
from helpers.redrum import (
    create_redrum_intro,
    redrum_added_seconds,
    select_redrum_candidate,
)
from helpers.section_selector import SectionCandidate
from helpers.selection_coordinator import (
    SelectionCoordinator,
    SideSelectionRequest,
)
from helpers.stem_provider import StemProvider
from helpers.style_detector import classify_track_sections, detect_editing_style
from settings import (
    DEFAULT_CANDIDATE_COUNT,
    DJ_READY_MINIMUM_BARS,
    MINIMUM_REDRUM_STEM_RELIABILITY,
    WAV_OUTPUT_FOLDER_NAME,
)


def _format_time(seconds: float) -> str:
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _format_duration(seconds: float) -> str:
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes:02d}:{remainder:02d}"


def _arrangement_sections(analysis: TrackAnalysis) -> tuple[TrackArrangementSection, ...]:
    """Merge adjacent bar labels into readable timeline regions."""
    labels = analysis.bar_section_labels
    confidence = analysis.bar_section_confidence
    boundaries = analysis.bar_boundaries
    usable = min(len(labels), len(confidence), max(0, len(boundaries) - 1))
    if usable == 0:
        return ()
    sections: list[TrackArrangementSection] = []
    first = 0
    for index in range(1, usable + 1):
        if index < usable and labels[index] == labels[first]:
            continue
        sections.append(TrackArrangementSection(
            float(boundaries[first]),
            float(boundaries[index]),
            str(labels[first]),
            sum(float(value) for value in confidence[first:index]) / (index - first),
        ))
        first = index
    return tuple(sections)


def _print_candidate(label: str, candidate: SectionCandidate) -> None:
    extra = f", vocal={candidate.vocal_energy:.2f}" if candidate.vocal_energy is not None else ""
    print(
        f"{label} candidate: {_format_time(candidate.start)} - {_format_time(candidate.end)} "
        f"(score={candidate.score:.2f}, instrumental={candidate.instrumentalness:.2f}{extra})"
    )


def _pick_ranked_candidate(
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
            f"Requested {position} candidate {requested_rank}, but only "
            f"{len(candidates)} distinct option(s) exist"
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
        page = candidates[page_start:page_start + DEFAULT_CANDIDATE_COUNT]
        if audition is not None:
            audition(page)
        pause()
        print(f"{position.title()} candidates:")
        for local_rank, candidate in enumerate(page, start=1):
            assessment = assess_candidate(candidate, position, None)
            print(
                f"  {local_rank}. {_format_time(candidate.start)}–{_format_time(candidate.end)}  "
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
        response = input(
            f"Choose {position} candidate [0-{len(page)}, R, C] "
            f"(Enter for {default_label}): "
        ).strip().upper()
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
                custom_start = _parse_timestamp(input("Custom source start (seconds or M:SS): "))
                custom_end = _parse_timestamp(input("Custom source end (seconds or M:SS): "))
            except ValueError as error:
                print(error)
                continue
            if custom_end <= custom_start:
                print("Custom end must be later than custom start.")
                continue
            chosen = min(
                candidates,
                key=lambda candidate: abs(candidate.start - custom_start)
                + abs(candidate.end - custom_end),
            )
            rank = candidates.index(chosen) + 1
            print(
                f"Snapped to ranked candidate {rank}: "
                f"{_format_time(chosen.start)}–{_format_time(chosen.end)}"
            )
            resume()
            return chosen, rank
        if response.isdigit() and 1 <= int(response) <= len(page):
            local_rank = int(response)
            rank = page_start + local_rank
            resume()
            return candidates[rank - 1], rank
        print(f"Please enter 0–{len(page)}, R, or C.")


def _parse_timestamp(value: str) -> float:
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



class TrackProcessor:
    """Orchestrate one track through analysis, stems, selection, and export."""

    def __init__(
        self,
        stem_provider: StemProvider | None = None,
        selection_coordinator: SelectionCoordinator | None = None,
        export_service: ExportService | None = None,
        candidate_validator: CandidateValidator | None = None,
    ) -> None:
        self.stem_provider = stem_provider or StemProvider()
        self.selection_coordinator = (
            selection_coordinator or SelectionCoordinator(validator=candidate_validator)
        )
        self.export_service = export_service or ExportService()

    def process(
        self,
        source: Path,
        output: Path,
        config: EditConfig,
        progress: ProgressReporter | None = None,
        intro_before: float | None = None,
        outro_after: float | None = None,
        outro_before: float | None = None,
    ) -> FileResult:
        """Analyze and render one input file."""
        if not source.is_file():
            raise FileNotFoundError(source)
        if output == source:
            raise ValueError("Output path must differ from input path")
    
        started = time.monotonic()
        stage_timings: list[tuple[str, float]] = []
        progress = progress or ProgressBar(show_logs=config.choose_candidates)
        progress.update(0, "Loading audio")
        try:
            stage_started = time.monotonic()
            audio = load_audio(source)
            stage_timings.append(("Loading audio", time.monotonic() - stage_started))
            progress.update(8, "Starting audio analysis")
            cache = AnalysisCache(
                Path(config.cache_directory), config.cache_enabled, config.refresh_cache
            )
            analysis = cache.load_analysis(source, config)
            analysis_cache_hit = analysis is not None
            if analysis is None:
                analysis_stage_started = time.monotonic()
                analysis_stage_label = "Starting audio analysis"
                def report_analysis(fraction: float, label: str) -> None:
                    nonlocal analysis_stage_started, analysis_stage_label
                    now = time.monotonic()
                    if label != analysis_stage_label:
                        stage_timings.append(
                            (analysis_stage_label, now - analysis_stage_started)
                        )
                        analysis_stage_started = now
                        analysis_stage_label = label
                    progress.update(8 + 62 * fraction, label)
                analysis = analyze_track(
                    audio,
                    config,
                    report_analysis,
                )
                stage_timings.append(
                    (analysis_stage_label, time.monotonic() - analysis_stage_started)
                )
                cache.save_analysis(source, config, analysis)
                if config.cache_enabled:
                    progress.log("Saved track analysis to cache")
            else:
                progress.update(70, "Loaded cached track analysis")
                progress.log("Loaded track analysis from cache")
            progress.log(f"Audio: {audio.sample_rate} Hz, stereo, {audio.duration:.1f} seconds")
            progress.log(f"Detected BPM: {analysis.bpm:.1f}")
            progress.log(
                f"Estimated key: {analysis.key_label} "
                f"({analysis.key_confidence:.0f}% confidence)"
            )
            progress.log(
                f"Groove: {analysis.groove_label}; timing: {analysis.timing_label}; "
                f"downbeat continuity: {analysis.downbeat_continuity:.0f}%"
            )
            progress.log(
                f"Detected {len(analysis.beat_times)} beats "
                f"({len(analysis.downbeat_indices)} inferred bars)"
            )
    
            stem_started = time.monotonic()
            stem_analysis = self.stem_provider.analyze(
                source, audio, analysis, config, cache, progress
            )
            stage_timings.append(("Vocal and stem analysis", time.monotonic() - stem_started))
            vocal_energy = stem_analysis.vocal_energy
            instrumental_audio = stem_analysis.instrumental_audio
            drums_audio = stem_analysis.drums_audio
            stem_reliability = stem_analysis.reliability
            vocal_cache_hit = stem_analysis.cache_hit
            automatic_intro_boundary = False
            automatic_outro_boundary = False
            if intro_before is None and stem_analysis.intro_boundary is not None:
                intro_before = stem_analysis.intro_boundary
                automatic_intro_boundary = True
            if outro_after is None and stem_analysis.outro_boundary is not None:
                outro_after = stem_analysis.outro_boundary
                automatic_outro_boundary = True
    
            detected_style = None
            preset_reason = None
            section_profiles = classify_track_sections(analysis, vocal_energy)
            progress.log(
                "Section styles: "
                + "; ".join(
                    f"{profile.name.lower()} {profile.style} ({profile.confidence:.0%})"
                    for profile in section_profiles
                )
            )
            if config.preset_name == "auto":
                decision = detect_editing_style(analysis, vocal_energy)
                selected = PRESETS[decision.preset]
                config = replace(
                    config,
                    intro_bars=(
                        config.intro_bars if config.intro_bars_locked else selected.intro_bars
                    ),
                    outro_bars=(
                        config.outro_bars if config.outro_bars_locked else selected.outro_bars
                    ),
                    use_stems=(
                        config.use_stems if config.stems_locked else selected.use_stems
                    ),
                    minimum_loop_quality=selected.minimum_loop_quality,
                    maximum_repetitions=selected.maximum_repetitions,
                    preset_name=f"auto → {decision.preset}",
                )
                detected_style = decision.style
                preset_reason = decision.reason
                progress.log(
                    f"Automatic style: {decision.style}; selected {decision.preset} "
                    f"({decision.reason})"
                )

            readiness = detect_dj_readiness(analysis)
            if config.analysis_only:
                progress.update(100, "Analysis complete")
                elapsed = time.monotonic() - started
                stage_timings.append(("Total", elapsed))
                return FileResult(
                    source_name=source.name,
                    output=source,
                    wav_output=source,
                    elapsed=elapsed,
                    bpm=analysis.bpm,
                    tempo_drift_percent=analysis.tempo_drift_percent,
                    beat_grid_confidence=analysis.beat_grid_confidence,
                    key_label=analysis.key_label,
                    key_confidence=analysis.key_confidence,
                    key_candidates=analysis.key_candidates,
                    groove_label=analysis.groove_label,
                    swing_ratio=analysis.swing_ratio,
                    timing_label=analysis.timing_label,
                    downbeat_continuity=analysis.downbeat_continuity,
                    beats=len(analysis.beat_times),
                    bars=len(analysis.downbeat_indices),
                    intro=None,
                    outro=None,
                    mix_in=None,
                    mix_out=None,
                    intro_existing_mix_bars=readiness.intro.mixable_bars,
                    outro_existing_mix_bars=readiness.outro.mixable_bars,
                    intro_already_dj_ready=(
                        readiness.intro.mixable_bars >= DJ_READY_MINIMUM_BARS
                    ),
                    outro_already_dj_ready=(
                        readiness.outro.mixable_bars >= DJ_READY_MINIMUM_BARS
                    ),
                    analysis_cache_hit=analysis_cache_hit,
                    vocal_cache_hit=vocal_cache_hit,
                    preset_name=config.preset_name,
                    detected_style=detected_style,
                    preset_reason=preset_reason,
                    stem_reliability=(stem_reliability if config.use_stems else None),
                    output_duration=audio.duration,
                    section_profiles=section_profiles,
                    arrangement_sections=_arrangement_sections(analysis),
                    stage_timings=tuple(stage_timings),
                )
            intro_already_ready = (
                not config.intro_bars_locked
                and config.intro_bars > 0
                and readiness.intro.mixable_bars
                >= max(DJ_READY_MINIMUM_BARS, config.intro_bars)
            )
            outro_already_ready = (
                not config.outro_bars_locked
                and config.outro_bars > 0
                and readiness.outro.mixable_bars
                >= max(DJ_READY_MINIMUM_BARS, config.outro_bars)
            )
            intro_preservation_reason = None
            outro_preservation_reason = None
            if intro_already_ready:
                intro_preservation_reason = (
                    f"already DJ-ready with {readiness.intro.mixable_bars} "
                    "consecutive mixable opening bars"
                )
                progress.log(f"Intro preserved: {intro_preservation_reason}")
                config = replace(config, intro_bars=0)
            if outro_already_ready:
                outro_preservation_reason = (
                    f"already DJ-ready with {readiness.outro.mixable_bars} "
                    "consecutive mixable closing bars"
                )
                progress.log(f"Outro preserved: {outro_preservation_reason}")
                config = replace(config, outro_bars=0)
    
            progress.update(80, "Scoring intro phrases")
            intro_rejection_reason = intro_preservation_reason
            outro_rejection_reason = outro_preservation_reason
    
            coordinator = self.selection_coordinator
            exporter = self.export_service
            reviews: dict[str, tuple[str | None, str | None]] = {}
    
            def choose_side(
                options: list[SectionCandidate], position: Position, requested_rank: int
            ) -> tuple[SectionCandidate | None, int | None]:
                chosen, rank = _pick_ranked_candidate(
                    options,
                    position,
                    requested_rank,
                    config.choose_candidates,
                    progress,
                    lambda page: exporter.export_candidate_auditions(
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
                    print(
                        "Feedback tags: good, chopped, wrong phrase, vocals, "
                        "buildup, bass reset, too repetitive, other"
                    )
                    reason = input(
                        f"Why did you choose this {position} option? "
                        "(comma-separated, optional): "
                    ).strip() or None
                    notes = input("Notes (optional): ").strip() or None
                    reviews[position] = (reason, notes)
                    resume()
                return chosen, rank
    
            if config.intro_bars == 0:
                progress.log("Extended intro disabled")
            elif intro_before is not None:
                source_label = (
                    "automatic vocal detection"
                    if automatic_intro_boundary else "manual rule"
                )
                progress.log(
                    f"Protected vocal entrance: intro source must end before "
                    f"{_format_time(intro_before)} ({source_label})"
                )
    
            prefer_instrumental = (
                instrumental_audio is not None
                and stem_reliability
                >= config.minimum_stem_construction_reliability
            )
            intro_selection = coordinator.select(
                analysis,
                audio.duration,
                vocal_energy,
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
                if (
                    outro_after is not None
                    and outro_before is not None
                    and outro_after >= outro_before
                ):
                    raise ValueError("outro_after must be earlier than outro_before")
                if outro_after is not None:
                    source_label = (
                        "automatic vocal detection"
                        if automatic_outro_boundary else "manual rule"
                    )
                    progress.log(
                        f"Protected vocal release: outro source must begin after "
                        f"{_format_time(outro_after)} ({source_label})"
                    )
                if outro_before is not None:
                    progress.log(
                        f"Protected closing section: outro source must end before "
                        f"{_format_time(outro_before)} (manual rule)"
                    )
    
            outro_selection = coordinator.select(
                analysis,
                audio.duration,
                vocal_energy,
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
                    raise ValueError(
                        f"Custom {position} ends after the source track"
                    )
                if options:
                    base = min(
                        options,
                        key=lambda item: abs(item.start - start) + abs(item.end - end),
                    )
                else:
                    base = SectionCandidate(start, end, 0.0, 0.5, 0.5, 0.5)
                beat_seconds = 60.0 / max(analysis.bpm, 1.0)
                bars = max(
                    1,
                    round((end - start) / (beat_seconds * config.beats_per_bar)),
                )
                progress.log(
                    f"Custom {position}: {_format_time(start)} - {_format_time(end)} "
                    f"({bars}-bar estimate ×{copies})"
                )
                return replace(
                    base,
                    start=start,
                    end=end,
                    unit_bars=bars,
                    repetitions=copies,
                    section_label="custom selection",
                )

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
                for position, options in (
                    ("intro", intro_selection.options),
                    ("outro", outro_selection.options),
                ):
                    if options:
                        exporter.export_candidate_auditions(
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
                    f"Intro candidate: {_format_time(intro.start)} - {_format_time(intro.end)} "
                    f"({intro.unit_bars}-bar unit ×{intro.repetitions}, "
                    f"score={intro.score:.2f}, instrumental={intro.instrumentalness:.2f})"
                )
            if outro is not None:
                outro = optimize_candidate_boundaries(audio, outro)
                progress.log(
                    f"Outro candidate: {_format_time(outro.start)} - {_format_time(outro.end)} "
                    f"({outro.unit_bars}-bar unit ×{outro.repetitions}, "
                    f"score={outro.score:.2f}, instrumental={outro.instrumentalness:.2f})"
                )
            intro_validation = coordinator.finalize(
                intro,
                config,
                instrumental_audio,
                stem_reliability,
                vocal_energy is not None,
                "intro",
            )
            outro_validation = coordinator.finalize(
                outro,
                config,
                instrumental_audio,
                stem_reliability,
                vocal_energy is not None,
                "outro",
            )
            intro = intro_validation.candidate
            outro = outro_validation.candidate
            intro_rejection_reason = (
                intro_validation.rejection_reason or intro_preservation_reason
            )
            outro_rejection_reason = (
                outro_validation.rejection_reason or outro_preservation_reason
            )
            redrum_intro = False
            high_quality_drums = None
            if (
                intro is None
                and config.intro_bars > 0
                and (
                    (
                        intro_rejection_reason is not None
                        and "exposed melodic phrase" in intro_rejection_reason
                    )
                    or not intro_selection.options
                )
            ):
                redrum_candidate = select_redrum_candidate(
                    analysis, config.intro_bars, audio.duration
                )
                if redrum_candidate is not None:
                    intro = redrum_candidate
                    reason = intro_rejection_reason or intro_selection.fallback or "no safe full-mix phrase"
                    intro_fallback = f"rejected {reason}; automatic percussion redrum"
                    intro_rejection_reason = None
                    redrum_intro = True
                    progress.log(
                        "Intro fallback: exposed melody protected; creating a "
                        f"{config.intro_bars}-bar percussion redrum from "
                        f"{_format_time(intro.start)}–{_format_time(intro.end)}"
                    )
            if redrum_intro:
                # Stem separation is a targeted rescue, not a blanket treatment.
                # Reuse a prior drum cache even during an ordinary `main.py`
                # batch; otherwise run Demucs only for this melodic fallback.
                if drums_audio is None or stem_reliability < MINIMUM_REDRUM_STEM_RELIABILITY:
                    cached_drums = cache.load_drums(source, config)
                    cached_instrumental = cache.load_instrumental(source, config)
                    if cached_drums is not None and cached_instrumental is not None:
                        drums_audio = cached_drums
                        stem_reliability = cached_instrumental[1]
                        progress.log("Loaded cached Demucs drums for melodic intro rescue")
                if drums_audio is None or stem_reliability < MINIMUM_REDRUM_STEM_RELIABILITY:
                    progress.log(
                        "Melodic intro rescue requires clean drums; running Demucs only "
                        "for this track"
                    )
                    try:
                        rescue = self.stem_provider.analyze(
                            source,
                            audio,
                            analysis,
                            replace(config, use_stems=True, refresh_cache=False),
                            cache,
                            progress,
                        )
                    except StemSeparationError as error:
                        intro = None
                        redrum_intro = False
                        intro_rejection_reason = (
                            f"melodic intro needs a clean drum stem; Demucs unavailable: {error}"
                        )
                    else:
                        drums_audio = rescue.drums_audio
                        instrumental_audio = rescue.instrumental_audio
                        stem_reliability = rescue.reliability
                        vocal_cache_hit = rescue.cache_hit
                if (
                    redrum_intro
                    and drums_audio is not None
                    and stem_reliability >= MINIMUM_REDRUM_STEM_RELIABILITY
                ):
                    high_quality_drums = drums_audio
                elif redrum_intro:
                    intro = None
                    redrum_intro = False
                    intro_rejection_reason = (
                        "melodic intro needs a reliable Demucs drum stem "
                        f"({stem_reliability:.0%} below "
                        f"{MINIMUM_REDRUM_STEM_RELIABILITY:.0%})"
                    )
            if intro_rejection_reason:
                progress.log(f"Intro disabled: {intro_rejection_reason}")
            elif intro_validation.shortened:
                progress.log(
                    f"Intro shortened to {config.maximum_repetitions} repeats by preset"
                )
            if outro_rejection_reason:
                progress.log(f"Outro disabled: {outro_rejection_reason}")
            elif outro_validation.shortened:
                progress.log(
                    f"Outro shortened to {config.maximum_repetitions} repeats by preset"
                )
            progress.update(90, "Assembling extended edit")
            intro_uses_stems = not redrum_intro and should_use_instrumental(
                intro, instrumental_audio, stem_reliability,
                config.minimum_stem_construction_reliability,
                config.minimum_vocal_coverage_for_instrumental_edit,
            )
            outro_uses_stems = should_use_instrumental(
                outro, instrumental_audio, stem_reliability,
                config.minimum_stem_construction_reliability,
                config.minimum_vocal_coverage_for_instrumental_edit,
            )
            if config.use_stems and instrumental_audio is not None:
                progress.log(
                    f"Construction: intro {'instrumental stems' if intro_uses_stems else 'full mix'}, "
                    f"outro {'instrumental stems' if outro_uses_stems else 'full mix'}"
                )
            edited = create_extended_edit(
                audio, None if redrum_intro else intro, outro, config.crossfade_ms, instrumental_audio,
                stem_reliability, config.minimum_stem_construction_reliability,
                config.minimum_vocal_coverage_for_instrumental_edit,
                None if redrum_intro else intro_validation.splice_plan,
                outro_validation.splice_plan,
            )
            if config.insert_source_start is not None:
                assert config.insert_source_end is not None
                assert config.insert_destination is not None
                edited = insert_audio_region(
                    edited,
                    audio,
                    config.insert_source_start,
                    config.insert_source_end,
                    config.insert_destination,
                    config.insert_copies,
                    max(config.crossfade_ms, 10.0),
                )
                progress.log(
                    "Inserted custom source "
                    f"{_format_time(config.insert_source_start)}–"
                    f"{_format_time(config.insert_source_end)} at "
                    f"{_format_time(config.insert_destination)} "
                    f"×{config.insert_copies}"
                )
            if redrum_intro and intro is not None:
                assert high_quality_drums is not None
                edited = create_redrum_intro(
                    edited,
                    audio,
                    intro,
                    high_quality_drums,
                    instrumental_audio,
                )
                progress.log(
                    "Redrum source: "
                    + "Demucs drums stem"
                )
            export_result = exporter.export(
                ExportRequest(
                    source=source,
                    output=output,
                    edited_audio=edited,
                    original_audio=audio,
                    wav_output=(
                        output.parent.parent / WAV_OUTPUT_FOLDER_NAME /
                        f"{source.stem}.wav"
                    ),
                    analysis=analysis,
                    intro=intro,
                    outro=outro,
                    config=config,
                ),
                progress,
            )
            intro_preview_path = export_result.intro_preview
            outro_preview_path = export_result.outro_preview
            cue_points = export_result.cue_points
            cue_sheet_path = export_result.cue_sheet
        except Exception:
            progress.stop()
            raise
        intro_added = 0.0
        intro_output_start = None
        intro_output_end = None
        if intro is not None:
            unit = intro.end - intro.start
            if redrum_intro:
                intro_added = redrum_added_seconds(intro)
                intro_output_start = 0.0
                intro_output_end = intro_added
            else:
                fade = adaptive_crossfade_ms(intro, config.crossfade_ms) / 1000.0
                intro_added = intro.repetitions * max(0.0, unit - fade)
                intro_output_start = intro.start
                intro_output_end = intro.start + intro_added
        outro_output_start = None
        outro_output_end = None
        if outro is not None:
            fade = adaptive_crossfade_ms(outro, config.crossfade_ms) / 1000.0
            unit = max(0.0, outro.end - outro.start - fade)
            outro_output_start = outro.end + intro_added - fade
            outro_output_end = outro_output_start + outro.repetitions * unit
        return FileResult(
            source_name=source.name,
            output=output,
            wav_output=(
                output.parent.parent / WAV_OUTPUT_FOLDER_NAME / f"{source.stem}.wav"
            ),
            intro_candidates=intro_selection.options,
            outro_candidates=outro_selection.options,
            intro_review_reason=reviews.get("intro", (None, None))[0],
            intro_review_notes=reviews.get("intro", (None, None))[1],
            outro_review_reason=reviews.get("outro", (None, None))[0],
            outro_review_notes=reviews.get("outro", (None, None))[1],
            elapsed=time.monotonic() - started,
            bpm=analysis.bpm,
            tempo_drift_percent=analysis.tempo_drift_percent,
            beat_grid_confidence=analysis.beat_grid_confidence,
            key_label=analysis.key_label,
            key_confidence=analysis.key_confidence,
            key_candidates=analysis.key_candidates,
            groove_label=analysis.groove_label,
            swing_ratio=analysis.swing_ratio,
            timing_label=analysis.timing_label,
            downbeat_continuity=analysis.downbeat_continuity,
            beats=len(analysis.beat_times),
            bars=len(analysis.downbeat_indices),
            intro=intro,
            outro=outro,
            # The extra intro is inserted at intro.start. The original outro shifts
            # later by the duration added at the intro loop seam.
            mix_in=0.0 if redrum_intro else (intro.start if intro is not None else None),
            mix_out=(
                outro.start
                + (
                    redrum_added_seconds(intro)
                    if redrum_intro
                    else intro.repetitions
                    * (
                        (intro.end - intro.start)
                        - adaptive_crossfade_ms(intro, config.crossfade_ms) / 1000.0
                    )
                )
            ) if intro is not None and outro is not None else (
                outro.start if outro is not None else None
            ),
            intro_output_start=intro_output_start,
            intro_output_end=intro_output_end,
            outro_output_start=outro_output_start,
            outro_output_end=outro_output_end,
            intro_before=intro_before,
            outro_after=outro_after,
            outro_before=outro_before,
            automatic_intro_boundary=automatic_intro_boundary,
            automatic_outro_boundary=automatic_outro_boundary,
            preset_name=config.preset_name,
            detected_style=detected_style,
            preset_reason=preset_reason,
            intro_existing_mix_bars=readiness.intro.mixable_bars,
            outro_existing_mix_bars=readiness.outro.mixable_bars,
            intro_already_dj_ready=intro_already_ready,
            outro_already_dj_ready=outro_already_ready,
            analysis_cache_hit=analysis_cache_hit,
            vocal_cache_hit=vocal_cache_hit,
            intro_preview=intro_preview_path,
            outro_preview=outro_preview_path,
            full_exported=export_result.full_exported,
            intro_candidate_rank=intro_candidate_rank,
            outro_candidate_rank=outro_candidate_rank,
            automatic_intro_length=(
                config.auto_select_bar_lengths and not config.intro_bars_locked
            ),
            automatic_outro_length=(
                config.auto_select_bar_lengths and not config.outro_bars_locked
            ),
            intro_rejection_reason=intro_rejection_reason,
            outro_rejection_reason=outro_rejection_reason,
            intro_fallback=intro_fallback,
            outro_fallback=outro_fallback,
            stem_reliability=(stem_reliability if config.use_stems or redrum_intro else None),
            intro_construction=(
                "progressive Demucs redrum" if redrum_intro
                else "instrumental stems" if intro_uses_stems else "full mix"
            ),
            outro_construction=("instrumental stems" if outro_uses_stems else "full mix"),
            output_duration=edited.duration,
            cue_points=cue_points,
            cue_sheet=cue_sheet_path,
            section_profiles=section_profiles,
            arrangement_sections=_arrangement_sections(analysis),
            stage_timings=tuple(stage_timings + [("Total", time.monotonic() - started)]),
        )
    
    

def process_file(
    source: Path,
    output: Path,
    config: EditConfig,
    progress: ProgressReporter | None = None,
    intro_before: float | None = None,
    outro_after: float | None = None,
    outro_before: float | None = None,
) -> FileResult:
    """Backward-compatible functional entry point for existing callers."""
    return TrackProcessor().process(
        source,
        output,
        config,
        progress,
        intro_before,
        outro_after,
        outro_before,
    )
