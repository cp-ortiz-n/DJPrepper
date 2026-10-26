"""HTTP boundary for Set Builder human review and calibration."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from audioextender.set_builder.preference_learning import DJPreferenceService
from audioextender.set_builder.review_service import SetReviewService


class TrackReviewRequest(BaseModel):
    track_id: str = Field(min_length=1, max_length=200, alias="trackId")
    title: str = Field(default="", max_length=300)
    decision: Literal["accept", "reject", "unreviewed"] = "unreviewed"
    reason: str = Field(default="", max_length=200)
    features: dict[str, list[str] | str] = Field(default_factory=dict)
    technical_score: float = Field(default=0, alias="technicalScore")
    preference_adjustment: float = Field(default=0, alias="preferenceAdjustment")
    rank_delta: int = Field(default=0, alias="rankDelta")
    match_tier: str = Field(default="unknown", alias="matchTier", max_length=50)


class TransitionReviewRequest(BaseModel):
    pair_id: str = Field(min_length=1, max_length=500, alias="pairId")
    rating: int = Field(ge=1, le=5)
    features: dict[str, str | float | int | bool] = Field(default_factory=dict)


class SetReviewRequest(BaseModel):
    id: str | None = Field(default=None, max_length=200)
    set_id: str = Field(default="", alias="setId", max_length=200)
    set_name: str = Field(default="Untitled set", alias="setName", max_length=200)
    context: str = Field(default="balanced", max_length=100)
    overall_decision: Literal["accept", "reject", "unreviewed"] = Field(default="unreviewed", alias="overallDecision")
    notes: str = Field(default="", max_length=2000)
    tracks: list[TrackReviewRequest] = Field(default_factory=list, max_length=200)
    transitions: list[TransitionReviewRequest] = Field(default_factory=list, max_length=200)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = Field(default=None, alias="createdAt", max_length=100)


def create_set_review_router(
    reviews: SetReviewService,
    preferences: DJPreferenceService,
) -> APIRouter:
    router = APIRouter(prefix="/api/set-builder/reviews", tags=["set-builder-reviews"])

    @router.get("")
    def report(context: str | None = None) -> dict[str, Any]:
        return reviews.report(context)

    @router.post("")
    def record(request: SetReviewRequest) -> dict[str, Any]:
        payload = request.model_dump(by_alias=True)
        result = reviews.record(payload)
        feedback = [
            {
                "action": "keep" if track.decision == "accept" else "reject",
                "trackId": track.track_id,
                "context": request.context,
                "features": track.features,
            }
            for track in request.tracks
            if track.decision in {"accept", "reject"}
        ]
        if feedback:
            preferences.record(feedback)
        result["preferenceProfile"] = preferences.profile(request.context)
        return result

    @router.delete("")
    def reset() -> dict[str, Any]:
        return reviews.reset()

    return router
