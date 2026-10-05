"""Durable musical-identity descriptor delivery for the local track catalog."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from audioextender.library.identity_inference import infer_identity_descriptors


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


class DescriptorInferenceRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=5000)
    apply: bool = False


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

    @router.get("/tracks/{track_id}/descriptor-suggestions")
    def descriptor_suggestions(track_id: int) -> dict[str, Any]:
        context = deps.repository().track_identity_inference_context(track_id)
        if context is None:
            raise HTTPException(404, "Track not found")
        suggestions = infer_identity_descriptors(context)
        return {
            "track_id": track_id, "suggestions": suggestions,
            "playlists_considered": context.get("playlists", []),
            "applied": False,
        }

    @router.post("/descriptors/infer")
    def infer_descriptors(request: DescriptorInferenceRequest) -> dict[str, Any]:
        repository = deps.repository()
        tracks: list[dict[str, Any]] = []
        missing: list[int] = []
        applied = 0
        for track_id in dict.fromkeys(request.track_ids):
            context = repository.track_identity_inference_context(track_id)
            if context is None:
                missing.append(track_id)
                continue
            suggestions = infer_identity_descriptors(context)
            if request.apply and suggestions:
                repository.replace_inferred_track_descriptors(track_id, suggestions)
                applied += 1
            tracks.append({
                "track_id": track_id, "suggestions": suggestions,
                "playlists_considered": context.get("playlists", []),
            })
        if request.apply:
            deps.invalidate_set_catalog()
        return {
            "requested": len(set(request.track_ids)), "processed": len(tracks),
            "applied": applied, "missing": missing, "tracks": tracks,
            "survives_restart": request.apply,
            "written_to": "AudioExtender track catalog" if request.apply else "Preview only",
        }

    @router.post("/descriptors/infer-missing")
    def infer_missing_descriptors() -> dict[str, Any]:
        repository = deps.repository()
        track_ids = repository.track_ids_missing_inferred_identity()
        applied = 0
        suggestions_added = 0
        no_suggestions: list[int] = []
        for track_id in track_ids:
            context = repository.track_identity_inference_context(track_id)
            suggestions = infer_identity_descriptors(context or {})
            if not suggestions:
                no_suggestions.append(track_id)
                continue
            repository.replace_inferred_track_descriptors(track_id, suggestions)
            applied += 1
            suggestions_added += len(suggestions)
        if applied:
            deps.invalidate_set_catalog()
        return {
            "requested": len(track_ids), "processed": len(track_ids), "applied": applied,
            "suggestions_added": suggestions_added, "no_suggestions": no_suggestions,
            "failed": 0, "survives_restart": True,
            "written_to": "AudioExtender track catalog",
            "requested_action": "Infer identity for every track without inferred descriptors",
        }

    return router
