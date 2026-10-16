"""Reporting, feedback, and key-verification HTTP delivery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


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


@dataclass(frozen=True)
class ReportingRouteDependencies:
    repository: Callable[[], Any]
    output_root: Path
    append_feedback: Callable[..., Any]
    refresh_library_index: Callable[[], Any]
    valid_keys: frozenset[str]


def create_reporting_router(deps: ReportingRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["reporting"])

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
