"""Reporting, feedback, and key-verification HTTP delivery."""

from __future__ import annotations

import json
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audioextender.library.track_overrides import load_track_overrides


class TrackFeedbackRequest(BaseModel):
    source_name: str = Field(min_length=1)
    position: str
    accepted: bool
    tags: str = ""
    notes: str = ""


class KeyVerificationRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=500)
    verified_key: str = Field(min_length=1, max_length=20)
    detected_key: str = Field(default="", max_length=20)
    candidates: list[dict] = Field(default_factory=list, max_length=3)
    notes: str = Field(default="", max_length=1000)


class BpmVerificationRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=500)
    verified_bpm: float = Field(ge=20, le=300)
    detected_bpm: float = Field(default=0, ge=0, le=300)
    notes: str = Field(default="", max_length=1000)


class OverrideRequest(BaseModel):
    intro_before: float | None = Field(None, gt=0)
    outro_after: float | None = Field(None, gt=0)
    outro_before: float | None = Field(None, gt=0)


@dataclass(frozen=True)
class ReportingRouteDependencies:
    repository: Callable[[], Any]
    output_root: Path
    append_feedback: Callable[..., Any]
    refresh_library_index: Callable[[], Any]
    valid_keys: frozenset[str]
    overrides_path: Path
    analytics_cache: MutableMapping[str, Any]
    analytics_cache_lock: Lock
    report_cache: MutableMapping[str, Any]
    report_cache_lock: Lock


class ReportingService:
    def __init__(self, dependencies: ReportingRouteDependencies) -> None:
        self._deps = dependencies

    def override(self, source_name: str) -> dict:
        override = load_track_overrides(self._deps.overrides_path).get(source_name.casefold())
        return {
            "intro_before": override.intro_before if override else None,
            "outro_after": override.outro_after if override else None,
            "outro_before": override.outro_before if override else None,
        }

    def save_override(self, source_name: str, request: OverrideRequest) -> dict:
        if request.outro_after and request.outro_before and request.outro_after >= request.outro_before:
            raise HTTPException(400, "Outro start must be earlier than outro end")
        path = self._deps.overrides_path
        try:
            document = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, ValueError) as error:
            raise HTTPException(500, "Could not read track overrides") from error
        values = request.model_dump()
        if any(value is not None for value in values.values()):
            document[source_name] = values
        else:
            for key in list(document):
                if key.casefold() == source_name.casefold():
                    del document[key]
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return values

    def analytics(self) -> dict:
        now = perf_counter()
        cache = self._deps.analytics_cache
        with self._deps.analytics_cache_lock:
            if cache["payload"] is not None and now < float(cache["expires_at"]):
                return dict(cache["payload"])
        summary = self._deps.repository().analytics_summary()
        feedback = summary["feedback"]
        accepted = [item for item in feedback if item["accepted"]]
        tags: dict[str, int] = {}
        for item in feedback:
            for tag in str(item["tags"]).split(","):
                normalized = tag.strip().lower()
                if normalized:
                    tags[normalized] = tags.get(normalized, 0) + 1
        payload = {
            "completed": summary["completed"],
            "feedback_count": len(feedback),
            "acceptance_rate": len(accepted) / len(feedback) if feedback else None,
            "stemmed_tracks": summary["stemmed"],
            "common_tags": sorted(tags.items(), key=lambda item: item[1], reverse=True),
        }
        with self._deps.analytics_cache_lock:
            cache.update(payload=payload, expires_at=now + 15.0)
        return payload

    def report(self, recent: int) -> dict | FileResponse:
        path = self._report_path()
        if not path.exists():
            return {"songs": {}}
        if not recent:
            return FileResponse(path, media_type="application/json")
        payload = self.load_report()
        songs = [song for song in payload.get("songs", {}).values() if song.get("status") == "updated"]
        songs.sort(key=lambda song: str(song.get("updated_at") or ""), reverse=True)
        fields = {"source_name", "status", "updated_at", "bpm", "key", "intro", "outro"}
        return {
            "songs": {
                str(index): {key: value for key, value in song.items() if key in fields}
                for index, song in enumerate(songs[:recent])
            }
        }

    def audio_index(self) -> list[dict]:
        result = []
        for job in self._deps.repository().list_report_audio_jobs():
            result.append(
                {
                    "id": int(job["id"]),
                    "source_name": str(job["source_name"]),
                    "status": "complete",
                    "wav_available": Path(str(job.get("wav_path") or "")).is_file(),
                    "extended_available": Path(str(job.get("extended_path") or "")).is_file(),
                    "downloaded_track_id": job.get("downloaded_track_id"),
                    "detected_key": job.get("latest_detected_key") or "",
                    "key_confidence": job.get("latest_key_confidence"),
                    "key_analyzed_at": job.get("key_analyzed_at") or "",
                }
            )
        return result

    def library_job(self, job_id: int) -> dict:
        repository = self._deps.repository()
        job = repository.get(job_id)
        if not job or job.get("status") != "complete":
            raise HTTPException(404, "Library track not found")
        return {"job": job, "versions": repository.list_completed_versions(str(job["source_path"]))}

    def _report_path(self) -> Path:
        return self._deps.output_root / "reports" / "processing_report.json"

    def load_report(self) -> dict:
        path = self._report_path()
        try:
            mtime_ns = path.stat().st_mtime_ns
            with self._deps.report_cache_lock:
                if self._deps.report_cache["mtime_ns"] != mtime_ns:
                    self._deps.report_cache["payload"] = json.loads(path.read_text(encoding="utf-8"))
                    self._deps.report_cache["mtime_ns"] = mtime_ns
                return dict(self._deps.report_cache["payload"])
        except (OSError, ValueError) as error:
            raise HTTPException(500, "The report could not be read") from error


def create_reporting_router(deps: ReportingRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["reporting"])
    service = ReportingService(deps)

    @router.get("/api/overrides/{source_name}")
    def get_override(source_name: str) -> dict:
        return service.override(source_name)

    @router.put("/api/overrides/{source_name}")
    def save_override(source_name: str, request: OverrideRequest) -> dict:
        return service.save_override(source_name, request)

    @router.get("/api/analytics")
    def analytics() -> dict:
        return service.analytics()

    @router.get("/api/report", response_model=None)
    def report(recent: int = Query(0, ge=0, le=20)) -> dict | FileResponse:
        return service.report(recent)

    @router.get("/api/report-audio-index")
    def report_audio_index() -> list[dict]:
        return service.audio_index()

    @router.get("/api/library/jobs/{job_id}/details")
    def library_job_details(job_id: int) -> dict:
        return service.library_job(job_id)

    @router.get("/api/report-feedback")
    def report_feedback() -> list[dict]:
        return deps.repository().track_feedback()

    @router.post("/api/report-feedback")
    def save_report_feedback(request: TrackFeedbackRequest) -> dict:
        if request.position not in {"intro", "outro", "overall"}:
            raise HTTPException(400, "Position must be intro, outro, or overall")
        source_name = Path(request.source_name).name
        feedback_id = deps.repository().add_track_feedback(
            source_name,
            request.position,
            request.accepted,
            request.tags.strip(),
            request.notes.strip(),
        )
        deps.append_feedback(
            deps.output_root,
            source_name,
            request.position,
            None,
            request.accepted,
            request.tags.strip(),
            request.notes.strip(),
        )
        return {"id": feedback_id}

    @router.get("/api/key-verifications")
    def key_verifications() -> dict:
        items = deps.repository().key_verifications()
        detector_totals: dict[str, int] = {}
        detector_correct: dict[str, int] = {}
        for item in items:
            verified = str(item.get("verified_key") or "")
            seen: set[str] = set()
            for candidate in item.get("candidates") or []:
                for detector in str(candidate.get("detectors") or "").split(","):
                    detector = detector.strip()
                    if not detector or detector in seen:
                        continue
                    seen.add(detector)
                    detector_totals[detector] = detector_totals.get(detector, 0) + 1
                    if str(candidate.get("key") or "") == verified:
                        detector_correct[detector] = detector_correct.get(detector, 0) + 1
        accuracy = {
            detector: {
                "correct": detector_correct.get(detector, 0),
                "total": total,
                "accuracy": detector_correct.get(detector, 0) / total if total else None,
            }
            for detector, total in detector_totals.items()
        }
        return {"items": items, "total": len(items), "detector_accuracy": accuracy}

    @router.put("/api/key-verifications/{source_name:path}")
    def save_key_verification(source_name: str, request: KeyVerificationRequest) -> dict:
        normalized_source = Path(source_name).name
        if Path(request.source_name).name.casefold() != normalized_source.casefold():
            raise HTTPException(400, "Track identity does not match")
        normalized_key = request.verified_key.strip().replace("♭", "b").replace("♯", "#")
        aliases = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
        parts = normalized_key.split()
        if len(parts) == 2 and parts[0] in aliases:
            normalized_key = f"{aliases[parts[0]]} {parts[1].casefold()}"
        if normalized_key not in deps.valid_keys:
            raise HTTPException(400, "Choose a valid major or minor key")
        saved = deps.repository().set_key_verification(
            normalized_source,
            normalized_key,
            request.detected_key.strip(),
            request.candidates,
            request.notes.strip(),
        )
        deps.refresh_library_index()
        return saved

    @router.delete("/api/key-verifications/{source_name:path}")
    def remove_key_verification(source_name: str) -> dict:
        removed = deps.repository().delete_key_verification(Path(source_name).name)
        if removed:
            deps.refresh_library_index()
        return {"removed": removed}

    @router.get("/api/bpm-verifications")
    def bpm_verifications() -> dict:
        items = deps.repository().bpm_verifications()
        return {"items": items, "total": len(items)}

    @router.put("/api/bpm-verifications/{source_name:path}")
    def save_bpm_verification(source_name: str, request: BpmVerificationRequest) -> dict:
        normalized_source = Path(source_name).name
        if Path(request.source_name).name.casefold() != normalized_source.casefold():
            raise HTTPException(400, "Track identity does not match")
        saved = deps.repository().set_bpm_verification(
            normalized_source,
            request.verified_bpm,
            request.detected_bpm,
            request.notes.strip(),
        )
        deps.refresh_library_index()
        return saved

    @router.delete("/api/bpm-verifications/{source_name:path}")
    def remove_bpm_verification(source_name: str) -> dict:
        removed = deps.repository().delete_bpm_verification(Path(source_name).name)
        if removed:
            deps.refresh_library_index()
        return {"removed": removed}

    @router.get("/api/feedback")
    def feedback() -> dict:
        path = deps.output_root / "reports" / "Candidate Feedback.md"
        return {"markdown": path.read_text(encoding="utf-8") if path.exists() else ""}

    return router
