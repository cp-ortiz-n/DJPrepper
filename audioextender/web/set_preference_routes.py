"""HTTP boundary for local Set Builder preference learning."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from audioextender.set_builder.preference_learning import DJPreferenceService


class PreferenceEventRequest(BaseModel):
    id: str | None = Field(default=None, max_length=200)
    action: Literal["keep", "lock", "save", "export", "replace-in", "remove", "replace-out"]
    track_id: str = Field(min_length=1, max_length=200, alias="trackId")
    context: str = Field(default="balanced", max_length=100)
    features: dict[str, list[str] | str] = Field(default_factory=dict)
    created_at: str | None = Field(default=None, max_length=100, alias="createdAt")


class PreferenceEventsRequest(BaseModel):
    events: list[PreferenceEventRequest] = Field(min_length=1, max_length=500)


class PreferenceEnabledRequest(BaseModel):
    enabled: bool


class PreferenceSignalRequest(BaseModel):
    dimension: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=300)


def create_set_preference_router(service: DJPreferenceService) -> APIRouter:
    router = APIRouter(prefix="/api/set-builder/preferences", tags=["set-builder-preferences"])

    @router.get("")
    def profile(context: str | None = None) -> dict[str, Any]:
        return service.profile(context)

    @router.post("/events")
    def record_events(request: PreferenceEventsRequest) -> dict[str, Any]:
        return service.record([event.model_dump(by_alias=True) for event in request.events])

    @router.put("/enabled")
    def set_enabled(request: PreferenceEnabledRequest) -> dict[str, Any]:
        return service.set_enabled(request.enabled)

    @router.delete("")
    def reset() -> dict[str, Any]:
        return service.reset()

    @router.delete("/signals")
    def dismiss_signal(request: PreferenceSignalRequest) -> dict[str, Any]:
        return service.dismiss_signal(request.dimension, request.value)

    return router
