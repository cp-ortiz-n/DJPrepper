"""Audio loading, analysis, stem preparation, and style inference."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from audioextender.analysis.dj_readiness import detect_dj_readiness
from audioextender.analysis.key_detection import analyze_track
from audioextender.analysis.style_detector import classify_track_sections, detect_editing_style
from audioextender.audio.loading import load_audio
from audioextender.audio.stem_provider import StemProvider
from audioextender.core.config import EditConfig
from audioextender.core.interfaces import ProgressReporter
from audioextender.core.presets import PRESETS
from audioextender.infrastructure.cache import AnalysisCache
from audioextender.processing.track_processing_stages import AnalysisStageResult


class AnalysisPreparationService:
    """Prepare immutable analysis facts for the rest of the transaction."""

    def __init__(self, stem_provider: StemProvider) -> None:
        self._stem_provider = stem_provider

    def prepare(
        self,
        source: Path,
        config: EditConfig,
        progress: ProgressReporter,
        intro_before: float | None,
        outro_after: float | None,
    ) -> AnalysisStageResult:
        stage_timings: list[tuple[str, float]] = []
        progress.update(0, "Loading audio")
        stage_started = time.monotonic()
        audio = load_audio(source)
        stage_timings.append(("Loading audio", time.monotonic() - stage_started))
        progress.update(8, "Starting audio analysis")
        cache = AnalysisCache(Path(config.cache_directory), config.cache_enabled, config.refresh_cache)
        analysis = cache.load_analysis(source, config)
        analysis_cache_hit = analysis is not None
        if analysis is None:
            analysis_stage_started = time.monotonic()
            analysis_stage_label = "Starting audio analysis"

            def report_analysis(fraction: float, label: str) -> None:
                nonlocal analysis_stage_started, analysis_stage_label
                now = time.monotonic()
                if label != analysis_stage_label:
                    stage_timings.append((analysis_stage_label, now - analysis_stage_started))
                    analysis_stage_started = now
                    analysis_stage_label = label
                progress.update(8 + 62 * fraction, label)

            analysis = analyze_track(audio, config, report_analysis)
            stage_timings.append((analysis_stage_label, time.monotonic() - analysis_stage_started))
            cache.save_analysis(source, config, analysis)
            if config.cache_enabled:
                progress.log("Saved track analysis to cache")
        else:
            progress.update(70, "Loaded cached track analysis")
            progress.log("Loaded track analysis from cache")

        progress.log(f"Audio: {audio.sample_rate} Hz, stereo, {audio.duration:.1f} seconds")
        progress.log(f"Detected BPM: {analysis.bpm:.1f}")
        progress.log(f"Estimated key: {analysis.key_label} ({analysis.key_confidence:.0f}% confidence)")
        progress.log(
            f"Groove: {analysis.groove_label}; timing: {analysis.timing_label}; "
            f"downbeat continuity: {analysis.downbeat_continuity:.0f}%"
        )
        progress.log(f"Detected {len(analysis.beat_times)} beats ({len(analysis.downbeat_indices)} inferred bars)")

        stem_started = time.monotonic()
        stem_analysis = self._stem_provider.analyze(source, audio, analysis, config, cache, progress)
        stage_timings.append(("Vocal and stem analysis", time.monotonic() - stem_started))
        automatic_intro_boundary = intro_before is None and stem_analysis.intro_boundary is not None
        automatic_outro_boundary = outro_after is None and stem_analysis.outro_boundary is not None
        if automatic_intro_boundary:
            intro_before = stem_analysis.intro_boundary
        if automatic_outro_boundary:
            outro_after = stem_analysis.outro_boundary

        detected_style = None
        preset_reason = None
        section_profiles = classify_track_sections(analysis, stem_analysis.vocal_energy)
        progress.log(
            "Section styles: "
            + "; ".join(
                f"{profile.name.lower()} {profile.style} ({profile.confidence:.0%})" for profile in section_profiles
            )
        )
        if config.preset_name == "auto":
            decision = detect_editing_style(analysis, stem_analysis.vocal_energy)
            selected = PRESETS[decision.preset]
            config = replace(
                config,
                intro_bars=(config.intro_bars if config.intro_bars_locked else selected.intro_bars),
                outro_bars=(config.outro_bars if config.outro_bars_locked else selected.outro_bars),
                use_stems=(config.use_stems if config.stems_locked else selected.use_stems),
                minimum_loop_quality=selected.minimum_loop_quality,
                maximum_repetitions=selected.maximum_repetitions,
                preset_name=f"auto → {decision.preset}",
            )
            detected_style = decision.style
            preset_reason = decision.reason
            progress.log(f"Automatic style: {decision.style}; selected {decision.preset} ({decision.reason})")

        return AnalysisStageResult(
            audio=audio,
            analysis=analysis,
            cache=cache,
            config=config,
            analysis_cache_hit=analysis_cache_hit,
            vocal_energy=stem_analysis.vocal_energy,
            instrumental_audio=stem_analysis.instrumental_audio,
            drums_audio=stem_analysis.drums_audio,
            stem_reliability=stem_analysis.reliability,
            vocal_cache_hit=stem_analysis.cache_hit,
            intro_before=intro_before,
            outro_after=outro_after,
            automatic_intro_boundary=automatic_intro_boundary,
            automatic_outro_boundary=automatic_outro_boundary,
            detected_style=detected_style,
            preset_reason=preset_reason,
            section_profiles=section_profiles,
            readiness=detect_dj_readiness(analysis),
            stage_timings=tuple(stage_timings),
        )
