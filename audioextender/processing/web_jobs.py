"""Background job service reusing the production audio engine."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from typing import TypedDict

from audioextender.analysis.candidate_reranker import assess_candidate
from audioextender.analysis.candidate_selection import Position
from audioextender.analysis.resource_planner import choose_worker_count
from audioextender.audio.wav_metadata import split_artist_title, write_wav_metadata
from audioextender.core.config import EditConfig
from audioextender.core.defaults import (
    CACHE_FOLDER_NAME,
    EXTENDED_OUTPUT_FOLDER_NAME,
    MINIMUM_CROSSFADE_MS,
    OUTPUT_FOLDER_NAME,
    WAV_OUTPUT_FOLDER_NAME,
)
from audioextender.core.interfaces import ProgressReporter
from audioextender.core.presets import EditPreset, get_preset
from audioextender.infrastructure.operation_lifecycle import AUDIO_JOBS, LifecycleProjection
from audioextender.library.cue_export import write_rekordbox_xml
from audioextender.library.track_overrides import load_track_overrides
from audioextender.persistence.capabilities import JobQueueRepository
from audioextender.processing.track_processor import process_file
from audioextender.reporting.feedback import append_candidate_feedback
from audioextender.reporting.processing import update_processing_report


class QueueSnapshot(TypedDict):
    active: int | None
    active_ids: list[int]
    paused_ids: list[int]
    pending: list[int]
    pause_requested: bool


_stage_history_lock = threading.Lock()
_stage_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=24))


def _stage_duration(seconds: float) -> str:
    seconds = max(1, round(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"


class DatabaseProgress(ProgressReporter):
    def __init__(
        self,
        repository: JobQueueRepository,
        job_id: int,
        run_gate: threading.Event | None = None,
    ) -> None:
        self.repository = repository
        self.job_id = job_id
        self.run_gate = run_gate
        self._stage: str | None = None
        self._stage_started = time.monotonic()

    def update(self, percent: float, label: str) -> None:
        if self.run_gate is not None and not self.run_gate.is_set():
            self.repository.update(self.job_id, stage="Paused")
            self.run_gate.wait()
        now = time.monotonic()
        with _stage_history_lock:
            if self._stage is not None and self._stage != label:
                _stage_history[self._stage].append(now - self._stage_started)
            estimates = tuple(_stage_history[label])
        if self._stage != label:
            self._stage = label
            self._stage_started = now
        display = label
        if estimates and label not in {"Analysis complete", "Ready"}:
            estimate = sorted(estimates)[len(estimates) // 2]
            display = f"{label} · typically {_stage_duration(estimate)}"
        self.repository.update(self.job_id, progress=max(0.0, min(100.0, percent)), stage=display)

    def log(self, message: str) -> None:
        return

    def complete(self, label: str = "Complete") -> None:
        self.update(100.0, label)

    def stop(self) -> None:
        return

    def pause_for_input(self) -> None:
        return

    def resume_after_input(self) -> None:
        return


class WebJobService:
    """Run lightweight analysis in parallel while keeping heavy edits exclusive."""

    def __init__(self, project: Path, repository: JobQueueRepository) -> None:
        self.project = project
        self.repository = repository
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="audioextender")
        self._lock = threading.RLock()
        self._pending: list[int] = []
        self._active: set[int] = set()
        self._parallel_active: set[int] = set()
        self._run_gates: dict[int, threading.Event] = {}
        for job in reversed(repository.list_jobs(1000)):
            if job["status"] == "queued":
                self._pending.append(int(job["id"]))
        self._start_next_locked()

    def enqueue(self, job_id: int) -> None:
        with self._lock:
            self._pending.append(job_id)
            self._start_next_locked()

    def enqueue_many(self, job_ids: list[int]) -> None:
        """Queue a batch with one scheduling pass instead of rescanning per track."""
        with self._lock:
            self._pending.extend(job_ids)
            self._start_next_locked()

    def _start_next_locked(self) -> None:
        while self._pending:
            job_id = self._pending[0]
            parallel = self._parallel_eligible(job_id)
            if self._active and (not parallel or self._active != self._parallel_active):
                return
            limit = self._analysis_worker_limit() if parallel else 1
            if len(self._active) >= limit:
                return
            self._pending.pop(0)
            gate = threading.Event()
            gate.set()
            self._active.add(job_id)
            if parallel:
                self._parallel_active.add(job_id)
            self._run_gates[job_id] = gate
            self.executor.submit(self._run_and_continue, job_id)
            if not parallel:
                return

    def _parallel_eligible(self, job_id: int) -> bool:
        job = self.repository.get(job_id)
        if not job or bool(job.get("use_stems")):
            return False
        try:
            options = json.loads(job.get("config_json") or "{}")
        except (TypeError, ValueError):
            return False
        return bool(options.get("analysis_only"))

    def _analysis_worker_limit(self) -> int:
        job_ids = [*self._active, *self._pending[:3]]
        paths = []
        for job_id in job_ids:
            if not self._parallel_eligible(job_id):
                continue
            job = self.repository.get(job_id)
            if job:
                path = Path(job["source_path"])
                if path.is_file():
                    paths.append(path)
        workers, _, _ = choose_worker_count(paths, "auto", False)
        return max(1, min(3, workers))

    def _run_and_continue(self, job_id: int) -> None:
        try:
            self._run(job_id)
        finally:
            with self._lock:
                self._active.discard(job_id)
                self._parallel_active.discard(job_id)
                self._run_gates.pop(job_id, None)
                self._start_next_locked()

    def snapshot(self) -> QueueSnapshot:
        """Return UI-only scheduler state without persisting implementation details."""
        with self._lock:
            return {
                "active": min(self._active) if self._active else None,
                "active_ids": sorted(self._active),
                "paused_ids": sorted(job_id for job_id, gate in self._run_gates.items() if not gate.is_set()),
                "pending": list(self._pending),
                "pause_requested": bool(any(not gate.is_set() for gate in self._run_gates.values())),
            }

    def lifecycle_status(self, job_id: int) -> LifecycleProjection:
        """Project a persisted audio job into the shared lifecycle contract."""
        job = self.repository.get(job_id)
        if job is None:
            raise KeyError("Audio job was not found")
        return AUDIO_JOBS.project(job)

    def pause(self, job_id: int) -> bool:
        with self._lock:
            gate = self._run_gates.get(job_id)
            if gate is None:
                return False
            gate.clear()
            self.repository.update(job_id, stage="Pause requested — finishing current step")
            return True

    def resume(self, job_id: int) -> bool:
        with self._lock:
            gate = self._run_gates.get(job_id)
            if gate is None:
                return False
            gate.set()
            self.repository.update(job_id, stage="Resuming")
            return True

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            if job_id not in self._pending:
                return False
            self._pending.remove(job_id)
            self.repository.update(job_id, status="canceled", stage="Canceled")
            return True

    def reorder(self, job_ids: list[int]) -> None:
        with self._lock:
            present = set(self._pending)
            requested = [job_id for job_id in job_ids if job_id in present]
            self._pending = requested + [job_id for job_id in self._pending if job_id not in requested]

    def _config(self, job: dict) -> EditConfig:
        preset = get_preset(job["preset"])
        try:
            overrides = json.loads(job.get("config_json") or "{}")
        except (TypeError, ValueError):
            overrides = {}
        preset_values = overrides.get("preset_definition")
        if isinstance(preset_values, dict):
            try:
                preset = EditPreset(**preset_values)
            except (TypeError, ValueError):
                pass
        config = EditConfig(
            intro_bars=int(job["intro_bars"]),
            outro_bars=int(job["outro_bars"]),
            use_stems=bool(job["use_stems"]),
            preset_name=job["preset"],
            intro_bars_locked=not bool(overrides.get("intro_bars_auto", False)),
            outro_bars_locked=not bool(overrides.get("outro_bars_auto", False)),
            stems_locked=True,
            cache_directory=str(self.project / CACHE_FOLDER_NAME),
            create_previews=bool(overrides.get("review_candidates", False)),
            create_candidate_auditions=bool(overrides.get("review_candidates", False)),
            auto_select_bar_lengths=bool(overrides.get("auto_bars", True)),
            minimum_intro_loop_quality=float(overrides.get("minimum_intro_loop_quality", 65.0)),
            minimum_outro_loop_quality=float(overrides.get("minimum_outro_loop_quality", 65.0)),
            pcm_bits=int(overrides.get("pcm_bits", 24)),
            preview_seconds=float(overrides.get("preview_seconds", 8.0)),
            export_cues=bool(overrides.get("export_cues", True)),
            analysis_only=bool(overrides.get("analysis_only", False)),
            maximum_repetitions=int(overrides.get("maximum_repetitions", 8)),
            crossfade_ms=float(overrides.get("crossfade_ms", MINIMUM_CROSSFADE_MS)),
            candidate_count=int(overrides.get("candidate_count", 3)),
            intro_search_seconds=float(overrides.get("intro_search_seconds", 120.0)),
            outro_search_seconds=float(overrides.get("outro_search_seconds", 150.0)),
            maximum_vocal_coverage=float(overrides.get("maximum_vocal_coverage_percent", 45.0)) / 100.0,
            maximum_vocal_boundary_risk=float(overrides.get("maximum_vocal_boundary_risk_percent", 65.0)) / 100.0,
            maximum_buildup_risk=float(overrides.get("maximum_buildup_risk_percent", 60.0)) / 100.0,
            maximum_bass_reset_risk=float(overrides.get("maximum_bass_reset_risk_percent", 65.0)) / 100.0,
            minimum_stem_construction_reliability=float(overrides.get("minimum_stem_reliability_percent", 65.0))
            / 100.0,
            intro_candidate=int(overrides.get("intro_candidate", 1)),
            outro_candidate=int(overrides.get("outro_candidate", 1)),
            manual_candidate_selection=bool(overrides.get("manual_candidate_selection", False)),
            custom_intro_start=overrides.get("custom_intro_start"),
            custom_intro_end=overrides.get("custom_intro_end"),
            custom_intro_copies=int(overrides.get("custom_intro_copies", 1)),
            custom_outro_start=overrides.get("custom_outro_start"),
            custom_outro_end=overrides.get("custom_outro_end"),
            custom_outro_copies=int(overrides.get("custom_outro_copies", 1)),
            insert_source_start=overrides.get("insert_source_start"),
            insert_source_end=overrides.get("insert_source_end"),
            insert_destination=overrides.get("insert_destination"),
            insert_copies=int(overrides.get("insert_copies", 1)),
        )
        if preset is not None:
            config = replace(
                config,
                minimum_loop_quality=preset.minimum_loop_quality,
                maximum_repetitions=(
                    int(overrides["maximum_repetitions"])
                    if "maximum_repetitions" in overrides
                    else preset.maximum_repetitions
                ),
            )
        config.validate()
        return config

    def config_for(self, job: dict) -> EditConfig:
        """Return the effective configuration for read-only web analysis tools."""
        return self._config(job)

    def _run(self, job_id: int) -> None:
        job = self.repository.get(job_id)
        if job is None:
            return
        source = Path(job["source_path"])
        try:
            job_options = json.loads(job.get("config_json") or "{}")
        except (TypeError, ValueError):
            job_options = {}
        analysis_only = bool(job_options.get("analysis_only", False))
        output_root = self.project / OUTPUT_FOLDER_NAME
        extended = (
            output_root
            / EXTENDED_OUTPUT_FOLDER_NAME
            / (f"{source.stem} (Analysis job {job_id}).wav" if analysis_only else f"{source.stem} (Extended Edit).wav")
        )
        (output_root / EXTENDED_OUTPUT_FOLDER_NAME).mkdir(parents=True, exist_ok=True)
        (output_root / WAV_OUTPUT_FOLDER_NAME).mkdir(parents=True, exist_ok=True)
        self.repository.update(job_id, status="processing", stage="Loading audio")
        try:
            result = process_file(
                source,
                extended,
                self._config(job),
                DatabaseProgress(self.repository, job_id, self._run_gates.get(job_id)),
                *self._boundaries(source),
            )
            catalog_track = self.repository.get_downloaded_track_by_path(source)
            inferred_artist, inferred_title = split_artist_title(source.stem)
            result = replace(
                result,
                title=str((catalog_track or {}).get("title") or inferred_title),
                artist=str((catalog_track or {}).get("artist") or inferred_artist),
                genre=str((catalog_track or {}).get("genre_category") or ""),
                album=str(((catalog_track or {}).get("playlists") or [""])[0]),
            )
            if not analysis_only:
                metadata = {
                    "title": result.title,
                    "artist": result.artist,
                    "genre": result.genre,
                    "album": result.album,
                }
                if result.wav_output:
                    write_wav_metadata(result.wav_output, **metadata)
                write_wav_metadata(result.output, **metadata)
            update_processing_report(output_root, [result], [])
            append_candidate_feedback(output_root, [result])
            rekordbox_path = output_root / "rekordbox" / f"job-{job_id}.xml"
            write_rekordbox_xml([result], rekordbox_path)
            archived = {} if analysis_only else self._archive_artifacts(job_id, source, result)

            def options(position: Position, candidates) -> list[dict]:
                return [
                    {
                        "rank": rank,
                        "start": candidate.start,
                        "end": candidate.end,
                        "bars": candidate.unit_bars,
                        "copies": candidate.repetitions,
                        "section": candidate.section_label,
                        "phrase": candidate.phrase_suitability,
                        "loop": candidate.loop_quality,
                        "transition": candidate.transition_quality,
                        "warnings": list(assess_candidate(candidate, position, result.preset_name).warnings),
                    }
                    for rank, candidate in enumerate(candidates, start=1)
                ]

            candidates = {
                "intro": options("intro", result.intro_candidates),
                "outro": options("outro", result.outro_candidates),
                "selected_intro": result.intro_candidate_rank,
                "selected_outro": result.outro_candidate_rank,
            }
            self.repository.update(
                job_id,
                status="complete",
                progress=100.0,
                stage=("Analyzed · Added to Library" if analysis_only else "Ready"),
                extended_path=(None if analysis_only else str(archived["extended"])),
                wav_path=(str(source) if analysis_only else str(result.wav_output) if result.wav_output else None),
                intro_preview_path=(str(archived["intro_preview"]) if archived.get("intro_preview") else None),
                outro_preview_path=(str(archived["outro_preview"]) if archived.get("outro_preview") else None),
                cue_sheet_path=(str(archived["cue_sheet"]) if archived.get("cue_sheet") else None),
                rekordbox_path=str(rekordbox_path),
                candidates_json=json.dumps(candidates),
                cues_json=json.dumps([asdict(cue) for cue in result.cue_points]),
                bpm=result.bpm,
                intro_quality=result.intro.loop_quality if result.intro else None,
                outro_quality=result.outro.loop_quality if result.outro else None,
            )
        except Exception as error:  # Job boundaries must retain unexpected failures.
            self.repository.update(job_id, status="failed", stage="Failed", error=str(error))

    def _archive_artifacts(self, job_id: int, source: Path, result) -> dict[str, Path]:
        """Give each web generation immutable files while retaining latest aliases."""
        directory = self.project / OUTPUT_FOLDER_NAME / "versions" / source.stem / f"job-{job_id}"
        directory.mkdir(parents=True, exist_ok=True)
        archived: dict[str, Path] = {}

        def copy(name: str, path: Path | None) -> None:
            if path is None or not path.is_file():
                return
            destination = directory / path.name
            shutil.copy2(path, destination)
            archived[name] = destination

        copy("extended", result.output)
        copy("intro_preview", result.intro_preview)
        copy("outro_preview", result.outro_preview)
        copy("cue_sheet", result.cue_sheet)
        preview_source = self.project / OUTPUT_FOLDER_NAME / "previews" / source.stem
        preview_target = directory / "previews"
        if preview_source.is_dir():
            preview_target.mkdir(exist_ok=True)
            for audition in preview_source.glob("* Candidate *.wav"):
                shutil.copy2(audition, preview_target / audition.name)
        return archived

    def _boundaries(self, source: Path) -> tuple[float | None, float | None, float | None]:
        override = load_track_overrides(self.project / "track_overrides.json").get(source.name.casefold())
        if override is None:
            return None, None, None
        return override.intro_before, override.outro_after, override.outro_before
