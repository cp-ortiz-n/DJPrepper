"""HTTP boundary for Set Builder candidate retrieval and plan validation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from audioextender.set_builder.candidate_retriever import SET_BUILDER_CATALOG_VERSION, SetCandidateRetriever
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.planning_jobs import SetPlanningJobService
from audioextender.set_builder.planning_store import JsonPlanningJobStore
from audioextender.set_builder.track_planner import AITrackPlanner


class SetCandidatePoolRequest(BaseModel):
    journey: dict[str, Any]
    required_track_ids: list[str] = Field(default_factory=list, max_length=500)
    excluded_track_ids: list[str] = Field(default_factory=list, max_length=5000)
    locked_track_ids: list[str] = Field(default_factory=list, max_length=500)
    locked_track_sections: dict[str, str] = Field(default_factory=dict, max_length=500)
    per_section_limit: int = Field(default=16, ge=1, le=100)
    total_limit: int = Field(default=100, ge=1, le=100)


class SetPlanValidationRequest(BaseModel):
    journey: dict[str, Any]
    candidate_pool: list[dict[str, Any]] = Field(max_length=100)
    selections: list[dict[str, Any]] = Field(max_length=500)
    required_track_ids: list[str] = Field(default_factory=list, max_length=500)
    excluded_track_ids: list[str] = Field(default_factory=list, max_length=5000)
    locked_track_ids: list[str] = Field(default_factory=list, max_length=500)
    locked_track_sections: dict[str, str] = Field(default_factory=dict, max_length=500)
    target_duration_minutes: int | None = Field(default=None, ge=1, le=480)
    target_track_count: int | None = Field(default=None, ge=1, le=500)


class SetTrackPlanningRequest(BaseModel):
    brief: dict[str, Any] = Field(default_factory=dict)
    journey: dict[str, Any]
    required_track_ids: list[str] = Field(default_factory=list, max_length=500)
    excluded_track_ids: list[str] = Field(default_factory=list, max_length=5000)
    locked_track_ids: list[str] = Field(default_factory=list, max_length=500)
    locked_track_sections: dict[str, str] = Field(default_factory=dict, max_length=500)
    base_plan_revision: dict[str, Any] | None = None
    target_duration_minutes: int = Field(ge=15, le=480)
    target_track_count: int = Field(ge=2, le=100)
    per_section_limit: int = Field(default=20, ge=2, le=100)
    total_limit: int = Field(default=100, ge=2, le=100)

    @model_validator(mode="after")
    def validate_bounded_context(self) -> SetTrackPlanningRequest:
        sections = self.journey.get("sections", [])
        if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
            raise ValueError("journey must contain between 1 and 12 sections")
        section_ids = {str(section.get("id") or "") for section in sections if isinstance(section, dict)}
        if not set(self.locked_track_sections).issubset(self.locked_track_ids):
            raise ValueError("locked_track_sections may only reference locked_track_ids")
        if not set(self.locked_track_sections.values()).issubset(section_ids):
            raise ValueError("locked_track_sections must reference journey sections")
        if len(json.dumps(self.brief, ensure_ascii=False)) > 50_000:
            raise ValueError("brief exceeds the 50 KB planning limit")
        if self.base_plan_revision and len(json.dumps(self.base_plan_revision, ensure_ascii=False)) > 2_000:
            raise ValueError("base_plan_revision exceeds the 2 KB planning limit")
        return self


@dataclass(frozen=True)
class SetPlanningRouteDependencies:
    catalog_cache_path: Path
    ensure_catalog_current: Callable[[], Any]
    write_catalog_cache: Callable[[], Any]
    candidate_retriever: SetCandidateRetriever
    plan_validator: SetPlanValidator
    track_planner: AITrackPlanner
    planning_jobs: SetPlanningJobService | None = None
    planning_job_store_path: Path | None = None


def _read_catalog(deps: SetPlanningRouteDependencies) -> list[dict[str, Any]]:
    deps.ensure_catalog_current()
    try:
        payload = json.loads(deps.catalog_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        deps.write_catalog_cache()
        payload = json.loads(deps.catalog_cache_path.read_text(encoding="utf-8"))
    if payload.get("version") != SET_BUILDER_CATALOG_VERSION:
        deps.write_catalog_cache()
        payload = json.loads(deps.catalog_cache_path.read_text(encoding="utf-8"))
    tracks = payload.get("tracks", [])
    return tracks if isinstance(tracks, list) else []


def create_set_planning_router(deps: SetPlanningRouteDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/set-builder", tags=["set-builder"])
    jobs = deps.planning_jobs or SetPlanningJobService(
        catalog_loader=lambda: _read_catalog(deps),
        candidate_retriever=deps.candidate_retriever,
        track_planner=deps.track_planner,
        store=JsonPlanningJobStore(deps.planning_job_store_path) if deps.planning_job_store_path else None,
    )

    @router.post("/candidate-pool")
    def candidate_pool(request: SetCandidatePoolRequest) -> dict:
        return deps.candidate_retriever.retrieve(
            _read_catalog(deps),
            request.journey,
            required_ids=set(request.required_track_ids),
            excluded_ids=set(request.excluded_track_ids),
            locked_ids=set(request.locked_track_ids),
            locked_sections=request.locked_track_sections,
            section_limit=request.per_section_limit,
            total_limit=request.total_limit,
        )

    @router.post("/validate-plan")
    def validate_plan(request: SetPlanValidationRequest) -> dict:
        return deps.plan_validator.validate(
            request.selections,
            request.candidate_pool,
            request.journey,
            required_ids=set(request.required_track_ids),
            excluded_ids=set(request.excluded_track_ids),
            locked_ids=set(request.locked_track_ids),
            locked_sections=request.locked_track_sections,
            target_duration_minutes=request.target_duration_minutes,
            target_track_count=request.target_track_count,
        )

    @router.post("/plan-tracks", status_code=202)
    def start_track_plan(request: SetTrackPlanningRequest) -> dict:
        return jobs.start(request.model_dump())

    @router.get("/plan-tracks/{job_id}")
    def track_plan_status(job_id: str) -> dict:
        try:
            return jobs.status(job_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    @router.post("/plan-tracks/{job_id}/cancel")
    def cancel_track_plan(job_id: str) -> dict:
        try:
            return jobs.cancel(job_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    @router.post("/plan-tracks/{job_id}/retry", status_code=202)
    def retry_track_plan(job_id: str) -> dict:
        try:
            return jobs.retry(job_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/ai-observability")
    def ai_observability() -> dict:
        return jobs.observability()

    return router
