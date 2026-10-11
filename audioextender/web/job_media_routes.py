"""Audio delivery, waveform, transition, cue, and batch-export routes."""

from __future__ import annotations

import json
import mimetypes
import tempfile
import threading
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from audioextender.analysis.transition_scorer import assess_custom_insertion
from audioextender.infrastructure.cache import AnalysisCache

BatchFileType = Literal[
    "extended",
    "source",
    "cue-sheet",
    "rekordbox",
    "intro-preview",
    "outro-preview",
    "analysis",
]


class BatchDownloadRequest(BaseModel):
    job_ids: list[int] = Field(min_length=1)
    file_types: list[BatchFileType] = Field(default_factory=lambda: ["extended"], min_length=1)  # type: ignore[arg-type]


class TransitionScoreRequest(BaseModel):
    source_start: float = Field(ge=0)
    source_end: float = Field(gt=0)
    destination: float = Field(ge=0)
    copies: int = Field(ge=1, le=8)


class CueEdit(BaseModel):
    name: str
    start: float = Field(ge=0)
    end: float | None = Field(None, ge=0)
    kind: str = "memory"
    purpose: str = ""
    confidence: float | None = None


class CueEditRequest(BaseModel):
    cues: list[CueEdit]


@dataclass
class JobMediaRouteDependencies:
    repository: Callable[[], Any]
    job_service: Any
    record_cache_result: Callable[[str, bool], None]
    waveform_locks_guard: threading.Lock = field(default_factory=threading.Lock)
    waveform_locks: dict[str, threading.Lock] = field(default_factory=dict)


def _job_or_404(dependencies: JobMediaRouteDependencies, job_id: int) -> dict:
    job = dependencies.repository().get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def _audio_response(dependencies: JobMediaRouteDependencies, job_id: int, kind: str) -> FileResponse:
    job = _job_or_404(dependencies, job_id)
    field_name = {
        "extended": "extended_path",
        "wav": "wav_path",
        "intro-preview": "intro_preview_path",
        "outro-preview": "outro_preview_path",
        "cue-sheet": "cue_sheet_path",
        "rekordbox": "rekordbox_path",
    }.get(kind)
    if field_name is None:
        raise HTTPException(404, "Unknown download type")
    value = job.get(field_name)
    if not value or not Path(value).is_file():
        raise HTTPException(404, "Output is not ready")
    return FileResponse(
        value,
        filename=Path(value).name,
        media_type=mimetypes.guess_type(value)[0] or "application/octet-stream",
    )


def _batch_archive(dependencies: JobMediaRouteDependencies, request: BatchDownloadRequest) -> FileResponse:
    jobs: list[dict] = []
    for job_id in dict.fromkeys(request.job_ids):
        job = dependencies.repository().get(job_id)
        if job is None or job["status"] != "complete":
            raise HTTPException(404, f"Completed job {job_id} is unavailable")
        jobs.append(job)
    handle = tempfile.NamedTemporaryFile(prefix="audioextender-", suffix=".zip", delete=False)
    archive = Path(handle.name)
    handle.close()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        included: list[str] = []
        skipped: list[str] = []
        used_names: set[str] = set()
        file_options = {
            "extended": ("extended_path", "Extended WAV"),
            "source": ("wav_path", "Source WAV"),
            "cue-sheet": ("cue_sheet_path", "Cue Sheets"),
            "rekordbox": ("rekordbox_path", "Rekordbox XML"),
            "intro-preview": ("intro_preview_path", "Previews/Intro"),
            "outro-preview": ("outro_preview_path", "Previews/Outro"),
        }
        for job in jobs:
            stem = Path(job["source_name"]).stem
            for file_type in request.file_types:
                if file_type == "analysis":
                    name = f"Analysis Reports/{stem} Analysis.json"
                    if name.casefold() in used_names:
                        name = f"Analysis Reports/{stem} Analysis (job {job['id']}).json"
                    report = {
                        "job_id": job["id"],
                        "source_name": job["source_name"],
                        "processed_at": job["updated_at"],
                        "preset": job["preset"],
                        "bpm": job.get("bpm"),
                        "intro_quality": job.get("intro_quality"),
                        "outro_quality": job.get("outro_quality"),
                        "configuration": json.loads(job.get("config_json") or "{}"),
                        "candidates": json.loads(job.get("candidates_json") or "{}"),
                        "cues": json.loads(job.get("cues_json") or "[]"),
                    }
                    bundle.writestr(name, json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    field_name, folder = file_options[file_type]
                    value = job.get(field_name)
                    path = Path(value) if value else None
                    if path is None or not path.is_file():
                        skipped.append(f"{job['source_name']}: {folder} unavailable")
                        continue
                    name = f"{folder}/{path.name}"
                    if name.casefold() in used_names:
                        name = f"{folder}/{path.stem} (job {job['id']}){path.suffix}"
                    bundle.write(path, arcname=name)
                used_names.add(name.casefold())
                included.append(name)
        bundle.writestr(
            "Export Summary.txt",
            "\n".join(
                [
                    "DJ Library Studio batch export",
                    f"Tracks selected: {len(jobs)}",
                    f"Files included: {len(included)}",
                    f"Files skipped: {len(skipped)}",
                    "",
                    "Included:",
                    *(included or ["None"]),
                    "",
                    "Skipped:",
                    *(skipped or ["None"]),
                ]
            )
            + "\n",
        )
    return FileResponse(
        archive,
        filename="DJ Library Studio Selected Tracks.zip",
        media_type="application/zip",
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


def _waveform(dependencies: JobMediaRouteDependencies, job_id: int, kind: str) -> dict:
    job = _job_or_404(dependencies, job_id)
    field_name = {"wav": "wav_path", "extended": "extended_path"}.get(kind)
    path = Path(job.get(field_name) or "") if field_name else Path()
    if field_name is None or not path.is_file():
        raise HTTPException(404, "Audio is not ready")
    target_points = 1100
    config = dependencies.job_service.config_for(job)
    cache = AnalysisCache(Path(config.cache_directory), config.cache_enabled, False)
    waveform_key = f"{path.resolve()}:{target_points}"
    with dependencies.waveform_locks_guard:
        generation_lock = dependencies.waveform_locks.setdefault(waveform_key, threading.Lock())
    with generation_lock:
        cached = cache.load_waveform(path, target_points)
        cache_hit = cached is not None
        dependencies.record_cache_result("waveform", cache_hit)
        if cached is None:
            info = sf.info(path)
            sample_window = min(2048, max(256, int(info.samplerate * 0.025)))
            envelope = []
            with sf.SoundFile(path) as audio_file:
                positions = np.linspace(0, max(0, info.frames - sample_window), target_points, dtype=np.int64)
                for position in positions:
                    audio_file.seek(int(position))
                    block = audio_file.read(sample_window, dtype="float32", always_2d=True)
                    envelope.append(float(np.sqrt(np.mean(np.square(block, dtype=np.float64)))) if block.size else 0.0)
            scale = max(float(np.percentile(envelope, 98)), 1e-8) if envelope else 1.0
            peaks = np.power(np.clip(np.asarray(envelope) / scale, 0.0, 1.0), 1.35).astype(np.float32)
            duration = float(info.duration)
            cache.save_waveform(path, duration, peaks, target_points)
        else:
            duration, peaks = cached
    timeline: dict[str, list[dict]] = {"behavior": [], "arrangement": [], "edits": []}
    record = dependencies.repository().get_library_analysis(job_id)
    if record:
        try:
            intro, outro = record.get("intro"), record.get("outro")
            intro_boundary = float(intro["source_start"]) if intro else None
            intro_shift = (
                max(0.0, float(intro["output_end"]) - float(intro["source_start"]))
                if intro and intro.get("output_end") is not None
                else 0.0
            )
            outro_boundary = float(outro["source_end"]) if outro else None
            outro_shift = (
                max(0.0, float(outro["output_end"]) - float(outro["output_start"]))
                if outro and outro.get("output_end") is not None
                else 0.0
            )

            def output_time(source_time: float) -> float:
                if kind == "wav":
                    return min(duration, source_time)
                value = source_time
                if intro_boundary is not None and source_time >= intro_boundary:
                    value += intro_shift
                if outro_boundary is not None and source_time >= outro_boundary:
                    value += outro_shift
                return min(duration, value)

            for profile in record.get("section_profiles", []):
                timeline["behavior"].append(
                    {
                        **profile,
                        "start": output_time(float(profile["start"])),
                        "end": output_time(float(profile["end"])),
                    }
                )
            for section in record.get("arrangement_sections", []):
                timeline["arrangement"].append(
                    {
                        **section,
                        "start": output_time(float(section["start"])),
                        "end": output_time(float(section["end"])),
                    }
                )
            if kind == "extended":
                for name, candidate in (("Extended intro", intro), ("Extended outro", outro)):
                    if candidate and candidate.get("output_start") is not None:
                        timeline["edits"].append(
                            {
                                "label": name,
                                "start": float(candidate["output_start"]),
                                "end": float(candidate["output_end"]),
                            }
                        )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return {
        "duration": duration,
        "peaks": peaks.tolist(),
        "timeline": timeline,
        "cache": "hit" if cache_hit else "generated",
    }


def create_job_media_router(dependencies: JobMediaRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["job media"])

    @router.get("/api/jobs/{job_id}/audio/{kind}")
    def audio(job_id: int, kind: str) -> FileResponse:
        return _audio_response(dependencies, job_id, kind)

    @router.get("/api/jobs/{job_id}/download/{kind}")
    def download(job_id: int, kind: str) -> FileResponse:
        return _audio_response(dependencies, job_id, kind)

    @router.post("/api/library/download")
    def batch_download(request: BatchDownloadRequest) -> FileResponse:
        return _batch_archive(dependencies, request)

    @router.get("/api/jobs/{job_id}/waveform/{kind}")
    def waveform(job_id: int, kind: str) -> dict:
        return _waveform(dependencies, job_id, kind)

    @router.post("/api/jobs/{job_id}/transition-score")
    def transition_score(job_id: int, request: TransitionScoreRequest) -> dict:
        job = _job_or_404(dependencies, job_id)
        source = Path(job["source_path"])
        if not source.is_file():
            raise HTTPException(404, "Source audio is unavailable")
        config = dependencies.job_service.config_for(job)
        cache = AnalysisCache(Path(config.cache_directory), config.cache_enabled, False)
        analysis = cache.load_analysis(source, config)
        if analysis is None:
            raise HTTPException(409, "Cached analysis is unavailable; reprocess this track")
        try:
            assessment = assess_custom_insertion(
                analysis,
                request.source_start,
                request.source_end,
                request.destination,
                request.copies,
                cache.load_vocals(source, config),
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return assessment.to_dict()

    @router.get("/api/jobs/{job_id}/cues")
    def cues(job_id: int) -> dict:
        return {"cues": json.loads(_job_or_404(dependencies, job_id).get("cues_json") or "[]")}

    @router.put("/api/jobs/{job_id}/cues")
    def update_cues(job_id: int, request: CueEditRequest) -> dict:
        job = _job_or_404(dependencies, job_id)
        values = [cue.model_dump() for cue in request.cues]
        dependencies.repository().update(job_id, cues_json=json.dumps(values))
        cue_path = Path(job.get("cue_sheet_path") or "")
        if cue_path.is_file():
            document = json.loads(cue_path.read_text(encoding="utf-8"))
            document["cues"] = values
            cue_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        xml_path = Path(job.get("rekordbox_path") or "")
        if xml_path.is_file():
            tree = ET.parse(xml_path)
            track = tree.getroot().find("./COLLECTION/TRACK")
            if track is not None:
                for marker in list(track.findall("POSITION_MARK")):
                    track.remove(marker)
                for cue in values:
                    attributes = {
                        "Name": str(cue["name"]),
                        "Type": "4" if cue["kind"] == "loop" else "0",
                        "Start": f"{float(cue['start']):.6f}",
                        "Num": "-1",
                    }
                    if cue["end"] is not None:
                        attributes["End"] = f"{float(cue['end']):.6f}"
                    ET.SubElement(track, "POSITION_MARK", attrib=attributes)
            ET.indent(tree.getroot(), space="  ")
            tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
        return {"cues": values}

    return router
