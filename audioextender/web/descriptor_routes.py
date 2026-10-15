"""Durable musical-identity descriptor delivery for the local track catalog."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from audioextender.library.descriptor_service import (
    DescriptorService,
    DescriptorTrackNotFound,
    InvalidVocabularyRule,
)

DESCRIPTOR_CATEGORIES = {"cultural", "rhythm", "sound", "vocal", "role", "context", "familiarity"}


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
    protect_from_inference: bool | None = None


class BulkDescriptorUpdateRequest(DescriptorUpdateRequest):
    track_ids: list[int] = Field(min_length=1, max_length=5000)


class DescriptorInferenceRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=5000)
    apply: bool = False


class InferenceProtectionRequest(BaseModel):
    protected: bool


class VocabularyRuleRequest(BaseModel):
    signal: str = Field(min_length=1, max_length=80)
    category: str = Field(default="", max_length=40)
    value: str = Field(default="", max_length=120)
    status: Literal["approved", "ignored"] = "approved"

    @field_validator("category")
    @classmethod
    def valid_optional_category(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized and normalized not in DESCRIPTOR_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(DESCRIPTOR_CATEGORIES))}")
        return normalized


@dataclass(frozen=True)
class DescriptorRouteDependencies:
    repository: Callable[[], Any]
    invalidate_set_catalog: Callable[[], Any]


def create_descriptor_router(deps: DescriptorRouteDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/downloaded-library", tags=["track-descriptors"])
    service = DescriptorService(deps.repository, deps.invalidate_set_catalog)

    @router.get("/tracks/{track_id}/descriptors")
    def descriptors(track_id: int) -> dict[str, Any]:
        try:
            return service.get(track_id)
        except DescriptorTrackNotFound as error:
            raise HTTPException(404, "Track not found") from error

    @router.put("/tracks/{track_id}/descriptors")
    def update_descriptors(track_id: int, request: DescriptorUpdateRequest) -> dict[str, Any]:
        try:
            return service.update(
                track_id,
                [item.model_dump() for item in request.descriptors],
                mode=request.mode,
                protect_from_inference=request.protect_from_inference,
            )
        except DescriptorTrackNotFound as error:
            raise HTTPException(404, "Track not found") from error

    @router.put("/tracks/{track_id}/inference-protection")
    def update_inference_protection(track_id: int, request: InferenceProtectionRequest) -> dict[str, Any]:
        try:
            return service.set_protection(track_id, request.protected)
        except DescriptorTrackNotFound as error:
            raise HTTPException(404, "Track not found") from error

    @router.post("/descriptors/bulk")
    def bulk_update_descriptors(request: BulkDescriptorUpdateRequest) -> dict[str, Any]:
        return service.bulk_update(
            request.track_ids,
            [item.model_dump() for item in request.descriptors],
            mode=request.mode,
        )

    @router.get("/tracks/{track_id}/descriptor-suggestions")
    def descriptor_suggestions(track_id: int) -> dict[str, Any]:
        try:
            return service.suggestions(track_id)
        except DescriptorTrackNotFound as error:
            raise HTTPException(404, "Track not found") from error

    @router.post("/descriptors/infer")
    def infer_descriptors(request: DescriptorInferenceRequest) -> dict[str, Any]:
        return service.infer(request.track_ids, apply=request.apply)

    @router.post("/descriptors/infer-missing")
    def infer_missing_descriptors() -> dict[str, Any]:
        return service.infer_missing()

    @router.post("/descriptors/reinfer-unprotected")
    def reinfer_unprotected_descriptors() -> dict[str, Any]:
        return service.reinfer_unprotected()

    @router.get("/descriptors/vocabulary")
    def vocabulary_review() -> dict[str, Any]:
        return service.vocabulary_review()

    @router.post("/descriptors/vocabulary")
    def save_vocabulary_rule(request: VocabularyRuleRequest) -> dict[str, Any]:
        try:
            return service.save_vocabulary_rule(
                signal=request.signal,
                category=request.category,
                value=request.value,
                status=request.status,
            )
        except InvalidVocabularyRule as error:
            raise HTTPException(422, str(error)) from error

    return router
