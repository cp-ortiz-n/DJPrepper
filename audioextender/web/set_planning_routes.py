"""HTTP boundary for Set Builder candidate retrieval and plan validation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from audioextender.set_builder.candidate_retriever import SET_BUILDER_CATALOG_VERSION, SetCandidateRetriever
from audioextender.set_builder.plan_validator import SetPlanValidator


class SetCandidatePoolRequest(BaseModel):
    journey: dict[str, Any]
    required_track_ids: list[str] = Field(default_factory=list, max_length=500)
    excluded_track_ids: list[str] = Field(default_factory=list, max_length=5000)
    locked_track_ids: list[str] = Field(default_factory=list, max_length=500)
    per_section_limit: int = Field(default=16, ge=1, le=30)
    total_limit: int = Field(default=100, ge=1, le=100)


class SetPlanValidationRequest(BaseModel):
    journey: dict[str, Any]
    candidate_pool: list[dict[str, Any]] = Field(max_length=100)
    selections: list[dict[str, Any]] = Field(max_length=500)
    required_track_ids: list[str] = Field(default_factory=list, max_length=500)
    excluded_track_ids: list[str] = Field(default_factory=list, max_length=5000)
    locked_track_ids: list[str] = Field(default_factory=list, max_length=500)
    target_duration_minutes: int | None = Field(default=None, ge=1, le=480)
    target_track_count: int | None = Field(default=None, ge=1, le=500)


@dataclass(frozen=True)
class SetPlanningRouteDependencies:
    catalog_cache_path: Path
    ensure_catalog_current: Callable[[], Any]
    write_catalog_cache: Callable[[], Any]
    candidate_retriever: SetCandidateRetriever
    plan_validator: SetPlanValidator


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

    @router.post("/candidate-pool")
    def candidate_pool(request: SetCandidatePoolRequest) -> dict:
        return deps.candidate_retriever.retrieve(
            _read_catalog(deps),
            request.journey,
            required_ids=set(request.required_track_ids),
            excluded_ids=set(request.excluded_track_ids),
            locked_ids=set(request.locked_track_ids),
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
            target_duration_minutes=request.target_duration_minutes,
            target_track_count=request.target_track_count,
        )

    return router
