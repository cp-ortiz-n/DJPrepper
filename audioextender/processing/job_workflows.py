"""Application workflows for creating and reprocessing analysis jobs."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO


class JobWorkflowError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class UploadedAudio:
    filename: str
    file: BinaryIO


@dataclass(frozen=True)
class JobCreationCommand:
    preset: str
    intro_bars: str
    outro_bars: str
    use_stems: bool
    review_candidates: bool
    analysis_only: bool
    overrides: Mapping[str, Any]


@dataclass(frozen=True)
class JobWorkflowService:
    repository: Any
    processor: Any
    input_root: Path
    supported_extensions: frozenset[str]
    supported_bar_counts: Sequence[int]
    available_presets: Callable[[], Mapping[str, Any]]
    effective_settings: Callable[[], dict[str, Any]]
    preset_snapshot: Callable[[str], dict[str, Any]]

    def create(self, uploads: Iterable[UploadedAudio], command: JobCreationCommand) -> dict[str, list[int]]:
        self._validate_preset(command.preset)
        overrides = {key: value for key, value in command.overrides.items() if value is not None}
        self._validate_overrides(overrides)
        effective = self.effective_settings()
        if command.analysis_only:
            resolved_intro = resolved_outro = 0
            intro_auto = outro_auto = False
            review_candidates = False
        else:
            resolved_intro, intro_auto = self._bars(command.intro_bars, "intro_bars", effective)
            resolved_outro, outro_auto = self._bars(command.outro_bars, "outro_bars", effective)
            review_candidates = command.review_candidates
        self.input_root.mkdir(parents=True, exist_ok=True)
        created: list[int] = []
        for upload in uploads:
            filename = Path(upload.filename).name
            if not filename or Path(filename).suffix.casefold() not in self.supported_extensions:
                raise JobWorkflowError(400, f"Unsupported audio file: {filename or 'unnamed'}")
            destination = self.input_root / filename
            with destination.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            job_id = self.repository.create(
                filename,
                destination,
                command.preset,
                resolved_intro,
                resolved_outro,
                command.use_stems,
                {
                    **effective,
                    **overrides,
                    **self.preset_snapshot(command.preset),
                    "review_candidates": review_candidates,
                    "analysis_only": command.analysis_only,
                    "intro_bars_auto": intro_auto,
                    "outro_bars_auto": outro_auto,
                },
            )
            self.processor.enqueue(job_id)
            created.append(job_id)
        return {"job_ids": created}

    def reprocess(self, job_id: int, values: Mapping[str, Any] | None = None) -> dict[str, int]:
        job = self.repository.get(job_id)
        if job is None:
            raise JobWorkflowError(404, "Job not found")
        config = json.loads(job.get("config_json") or "{}")
        config.pop("analysis_only", None)
        preset = job["preset"]
        intro_bars = int(job["intro_bars"])
        outro_bars = int(job["outro_bars"])
        use_stems = bool(job["use_stems"])
        request = dict(values or {})
        if values is not None:
            pcm_bits = request.get("pcm_bits")
            if pcm_bits not in {None, 16, 24}:
                raise JobWorkflowError(400, "PCM depth must be 16 or 24")
            if request.get("preset") is not None:
                preset = str(request["preset"])
                self._validate_preset(preset)
            for position in ("intro", "outro"):
                requested_bars = request.get(f"{position}_bars")
                if requested_bars is not None:
                    if requested_bars not in self.supported_bar_counts:
                        raise JobWorkflowError(400, "Unsupported bar count")
                    if position == "intro":
                        intro_bars = int(requested_bars)
                    else:
                        outro_bars = int(requested_bars)
                automatic = request.get(f"{position}_bars_auto")
                if automatic is not None:
                    config[f"{position}_bars_auto"] = automatic
            if request.get("use_stems") is not None:
                use_stems = bool(request["use_stems"])
            configurable = (
                "auto_bars",
                "minimum_intro_loop_quality",
                "minimum_outro_loop_quality",
                "maximum_repetitions",
                "crossfade_ms",
                "candidate_count",
                "intro_search_seconds",
                "outro_search_seconds",
                "maximum_vocal_coverage_percent",
                "maximum_vocal_boundary_risk_percent",
                "maximum_buildup_risk_percent",
                "maximum_bass_reset_risk_percent",
                "minimum_stem_reliability_percent",
                "pcm_bits",
                "preview_seconds",
                "export_cues",
            )
            config.update({key: request[key] for key in configurable if request.get(key) is not None})
            if request.get("preset") is not None:
                config.pop("preset_definition", None)
                config.update(self.preset_snapshot(preset))
            if request.get("clear_insertion"):
                for key in ("insert_source_start", "insert_source_end", "insert_destination", "insert_copies"):
                    config.pop(key, None)
            for position in ("intro", "outro"):
                candidate = request.get(f"{position}_candidate")
                if candidate is not None:
                    config[f"{position}_candidate"] = candidate
                    for key in ("start", "end", "copies"):
                        config.pop(f"custom_{position}_{key}", None)
            if request.get("intro_candidate") is not None or request.get("outro_candidate") is not None:
                config["manual_candidate_selection"] = True
            if request.get("review_candidates") is not None:
                config["review_candidates"] = request["review_candidates"]
            self._apply_custom_ranges(config, request)
            self._apply_insertion(config, request)
        new_id = self.repository.create(
            job["source_name"],
            Path(job["source_path"]),
            preset,
            intro_bars,
            outro_bars,
            use_stems,
            config,
            parent_job_id=job_id,
        )
        review_keys = {
            "review_candidates",
            "intro_candidate",
            "outro_candidate",
            "custom_intro_start",
            "custom_outro_start",
            "insert_source_start",
        }
        if values is not None and any(request.get(key) is not None for key in review_keys):
            self.repository.update(job_id, review_status="resolved")
        self.processor.enqueue(new_id)
        return {"job_id": new_id}

    def _validate_preset(self, preset: str) -> None:
        if preset != "auto" and preset not in self.available_presets():
            raise JobWorkflowError(400, "Unknown preset")

    def _bars(self, value: str, default_key: str, effective: Mapping[str, Any]) -> tuple[int, bool]:
        if value == "auto":
            return int(effective[default_key]), True
        try:
            parsed = int(value)
        except ValueError as error:
            raise JobWorkflowError(400, "Unsupported bar count") from error
        if parsed not in self.supported_bar_counts:
            raise JobWorkflowError(400, "Unsupported bar count")
        return parsed, False

    @staticmethod
    def _validate_overrides(values: Mapping[str, Any]) -> None:
        for key in ("minimum_intro_loop_quality", "minimum_outro_loop_quality"):
            value = values.get(key)
            if value is not None and not 0 <= float(value) <= 100:
                raise JobWorkflowError(400, "Quality thresholds must be between 0 and 100")
        repetitions = values.get("maximum_repetitions")
        if repetitions is not None and not 1 <= int(repetitions) <= 8:
            raise JobWorkflowError(400, "Maximum repetitions must be between 1 and 8")
        fade = values.get("crossfade_ms")
        if fade is not None and not 1 <= float(fade) <= 100:
            raise JobWorkflowError(400, "Crossfade must be between 1 and 100 ms")
        if values.get("pcm_bits") not in {None, 16, 24}:
            raise JobWorkflowError(400, "PCM depth must be 16 or 24")
        preview = values.get("preview_seconds")
        if preview is not None and not 0 < float(preview) <= 60:
            raise JobWorkflowError(400, "Preview context must be between 1 and 60 seconds")
        candidate_count = values.get("candidate_count")
        if candidate_count is not None and not 1 <= int(candidate_count) <= 8:
            raise JobWorkflowError(400, "Candidate depth must be between 1 and 8")
        for key in ("intro_search_seconds", "outro_search_seconds"):
            value = values.get(key)
            if value is not None and not 15 <= float(value) <= 600:
                raise JobWorkflowError(400, "Search windows must be between 15 and 600 seconds")
        for key in (
            "maximum_vocal_coverage_percent",
            "maximum_vocal_boundary_risk_percent",
            "maximum_buildup_risk_percent",
            "maximum_bass_reset_risk_percent",
            "minimum_stem_reliability_percent",
        ):
            value = values.get(key)
            if value is not None and not 0 <= float(value) <= 100:
                raise JobWorkflowError(400, "Analysis percentages must be between 0 and 100")

    @staticmethod
    def _apply_custom_ranges(config: dict[str, Any], request: Mapping[str, Any]) -> None:
        for position in ("intro", "outro"):
            start = request.get(f"custom_{position}_start")
            end = request.get(f"custom_{position}_end")
            if (start is None) != (end is None):
                raise JobWorkflowError(400, f"Custom {position} requires start and end")
            if start is not None:
                assert end is not None
                if float(end) <= float(start):
                    raise JobWorkflowError(400, f"Custom {position} end must follow start")
                config[f"custom_{position}_start"] = start
                config[f"custom_{position}_end"] = end
                config[f"custom_{position}_copies"] = request.get(f"custom_{position}_copies") or 1
                config["manual_candidate_selection"] = True

    @staticmethod
    def _apply_insertion(config: dict[str, Any], request: Mapping[str, Any]) -> None:
        values = tuple(request.get(key) for key in ("insert_source_start", "insert_source_end", "insert_destination"))
        if any(value is not None for value in values):
            if any(value is None for value in values):
                raise JobWorkflowError(400, "Insertion requires source start, source end, and destination")
            start, end, destination = values
            assert start is not None and end is not None and destination is not None
            if float(end) <= float(start):
                raise JobWorkflowError(400, "Inserted source end must follow start")
            config.update(
                insert_source_start=start,
                insert_source_end=end,
                insert_destination=destination,
                insert_copies=request.get("insert_copies") or 1,
            )
