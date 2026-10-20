"""Job review, candidate audition, and feedback HTTP routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audioextender.processing.job_workflows import JobWorkflowError, JobWorkflowService


class FeedbackRequest(BaseModel):
    position: str
    candidate_rank: int | None = None
    accepted: bool
    tags: str = ""
    notes: str = ""


class ReprocessRequest(BaseModel):
    preset: str | None = None
    intro_bars: int | None = None
    outro_bars: int | None = None
    intro_bars_auto: bool | None = None
    outro_bars_auto: bool | None = None
    use_stems: bool | None = None
    auto_bars: bool | None = None
    minimum_intro_loop_quality: float | None = Field(None, ge=0, le=100)
    minimum_outro_loop_quality: float | None = Field(None, ge=0, le=100)
    maximum_repetitions: int | None = Field(None, ge=1, le=8)
    crossfade_ms: float | None = Field(None, ge=1, le=100)
    candidate_count: int | None = Field(None, ge=1, le=8)
    intro_search_seconds: float | None = Field(None, ge=15, le=600)
    outro_search_seconds: float | None = Field(None, ge=15, le=600)
    maximum_vocal_coverage_percent: float | None = Field(None, ge=0, le=100)
    maximum_vocal_boundary_risk_percent: float | None = Field(None, ge=0, le=100)
    maximum_buildup_risk_percent: float | None = Field(None, ge=0, le=100)
    maximum_bass_reset_risk_percent: float | None = Field(None, ge=0, le=100)
    minimum_stem_reliability_percent: float | None = Field(None, ge=0, le=100)
    pcm_bits: int | None = None
    preview_seconds: float | None = Field(None, gt=0, le=60)
    export_cues: bool | None = None
    intro_candidate: int | None = Field(None, ge=0, le=3)
    outro_candidate: int | None = Field(None, ge=0, le=3)
    review_candidates: bool | None = None
    custom_intro_start: float | None = Field(None, ge=0)
    custom_intro_end: float | None = Field(None, gt=0)
    custom_intro_copies: int | None = Field(None, ge=1, le=8)
    custom_outro_start: float | None = Field(None, ge=0)
    custom_outro_end: float | None = Field(None, gt=0)
    custom_outro_copies: int | None = Field(None, ge=1, le=8)
    insert_source_start: float | None = Field(None, ge=0)
    insert_source_end: float | None = Field(None, gt=0)
    insert_destination: float | None = Field(None, ge=0)
    insert_copies: int | None = Field(None, ge=1, le=8)
    clear_insertion: bool = False


@dataclass(frozen=True)
class JobReviewRouteDependencies:
    repository: Callable[[], Any]
    workflow: JobWorkflowService
    output_root: Path
    append_feedback: Callable[..., object]


class JobReviewService:
    def __init__(self, dependencies: JobReviewRouteDependencies) -> None:
        self._dependencies = dependencies

    def reprocess(self, job_id: int, values: dict[str, Any] | None) -> dict[str, int]:
        return self._dependencies.workflow.reprocess(job_id, values)

    def reject(self, job_id: int) -> dict[str, bool]:
        repository = self._dependencies.repository()
        job = repository.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job.get("review_status") != "pending":
            raise HTTPException(409, "Review is no longer pending")
        repository.update(job_id, review_status="rejected")
        return {"ok": True}

    def candidates(self, job_id: int) -> dict:
        job = self._job(job_id)
        return json.loads(job.get("candidates_json") or "{}")

    def candidate_audio(self, job_id: int, position: str, rank: int) -> Path:
        job = self._dependencies.repository().get(job_id)
        if job is None or position not in {"intro", "outro"} or rank not in {1, 2, 3}:
            raise HTTPException(404, "Candidate not found")
        stem = Path(job["source_name"]).stem
        output = self._dependencies.output_root
        archived = output / "versions" / stem / f"job-{job_id}" / "previews"
        folder = archived if archived.is_dir() else output / "previews" / stem
        if not folder.is_dir():
            previews = output / "previews"
            wanted = stem.casefold()
            if previews.is_dir():
                folder = next(
                    (item for item in previews.iterdir() if item.is_dir() and item.name.casefold() == wanted),
                    folder,
                )
        path = folder / f"{position.title()} Candidate {rank}.wav"
        if not path.is_file():
            raise HTTPException(404, "Candidate preview was not generated")
        return path

    def save_feedback(self, job_id: int, request: FeedbackRequest) -> dict[str, int]:
        job = self._job(job_id)
        if request.position not in {"intro", "outro"}:
            raise HTTPException(400, "Position must be intro or outro")
        tags = request.tags.strip()
        notes = request.notes.strip()
        repository = self._dependencies.repository()
        feedback_id = repository.add_feedback(
            job_id, request.position, request.candidate_rank, request.accepted, tags, notes
        )
        self._dependencies.append_feedback(
            self._dependencies.output_root,
            job["source_name"],
            request.position,
            request.candidate_rank,
            request.accepted,
            tags,
            notes,
        )
        return {"id": feedback_id}

    def feedback(self, job_id: int) -> list[dict]:
        return self._dependencies.repository().feedback(job_id)

    def _job(self, job_id: int) -> dict:
        job = self._dependencies.repository().get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return job


def create_job_review_router(service: JobReviewService) -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["job-review"])

    @router.post("/{job_id}/reprocess", status_code=202)
    def reprocess(job_id: int, request: ReprocessRequest | None = None) -> dict:
        try:
            return service.reprocess(job_id, request.model_dump() if request is not None else None)
        except JobWorkflowError as error:
            raise HTTPException(error.status_code, error.detail) from error

    @router.post("/{job_id}/review/reject")
    def reject(job_id: int) -> dict:
        return service.reject(job_id)

    @router.get("/{job_id}/candidates")
    def candidates(job_id: int) -> dict:
        return service.candidates(job_id)

    @router.get("/{job_id}/candidate/{position}/{rank}")
    def candidate_audio(job_id: int, position: str, rank: int) -> FileResponse:
        return FileResponse(service.candidate_audio(job_id, position, rank), media_type="audio/wav")

    @router.post("/{job_id}/feedback")
    def save_feedback(job_id: int, request: FeedbackRequest) -> dict:
        return service.save_feedback(job_id, request)

    @router.get("/{job_id}/feedback")
    def feedback(job_id: int) -> list[dict]:
        return service.feedback(job_id)

    return router
