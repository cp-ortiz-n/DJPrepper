"""Durable musical-identity descriptor delivery for the local track catalog."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator


DESCRIPTOR_CATEGORIES = {
    "cultural", "rhythm", "sound", "vocal", "role", "context", "familiarity"
}


class TrackDescriptor(BaseModel):
    category: str = Field(default="context", max_length=40)
    value: str = Field(min_length=1, max_length=120)
    provenance: Literal["manual", "imported", "inferred", "crate"] = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in DESCRIPTOR_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(DESCRIPTOR_CATEGORIES))}")
        return normalized

    @field_validator("value")
    @classmethod
    def normalized_value(cls, value: str) -> str:
        return value.strip().casefold()


class DescriptorUpdateRequest(BaseModel):
    descriptors: list[TrackDescriptor] = Field(default_factory=list, max_length=100)
    mode: Literal["replace", "add", "remove"] = "replace"


class BulkDescriptorUpdateRequest(DescriptorUpdateRequest):
    track_ids: list[int] = Field(min_length=1, max_length=5000)


@dataclass(frozen=True)
class DescriptorRouteDependencies:
    repository: Callable[[], Any]
    invalidate_set_catalog: Callable[[], None]


def create_descriptor_router(deps: DescriptorRouteDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/downloaded-library", tags=["track-descriptors"])

    @router.get("/tracks/{track_id}/descriptors")
    def descriptors(track_id: int) -> dict[str, Any]:
        repository = deps.repository()
        if not repository.get_downloaded_track(track_id):
            raise HTTPException(404, "Track not found")
        return {"track_id": track_id, "descriptors": repository.track_descriptors(track_id)}

    @router.put("/tracks/{track_id}/descriptors")
    def update_descriptors(track_id: int, request: DescriptorUpdateRequest) -> dict[str, Any]:
        repository = deps.repository()
        result = repository.update_track_descriptors(
            [track_id], [item.model_dump() for item in request.descriptors], mode=request.mode
        )
        if result["missing"]:
            raise HTTPException(404, "Track not found")
        deps.invalidate_set_catalog()
        return {
            **result,
            "track_id": track_id,
            "values": repository.track_descriptors(track_id),
            "requested_action": f"{request.mode.title()} musical identity descriptors",
            "written_to": "AudioExtender track catalog",
        }

    @router.post("/descriptors/bulk")
    def bulk_update_descriptors(request: BulkDescriptorUpdateRequest) -> dict[str, Any]:
        result = deps.repository().update_track_descriptors(
            request.track_ids,
            [item.model_dump() for item in request.descriptors],
            mode=request.mode,
        )
        deps.invalidate_set_catalog()
        return {
            **result,
            "requested_action": f"{request.mode.title()} descriptors on {len(set(request.track_ids))} tracks",
            "written_to": "AudioExtender track catalog",
            "failed": len(result["missing"]),
        }

    return router
