"""Recording-family query and mutation routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class DuplicateMergeRequest(BaseModel):
    survivor_id: int = Field(gt=0)
    duplicate_id: int = Field(gt=0)


class TrackFamilyLinkRequest(BaseModel):
    target_track_id: int | None = Field(default=None, gt=0)
    target_identity: str = Field(default="", max_length=40)
    relationship: Literal["ORG", "RMX", "EXT", "RADIO", "LIVE", "INST", "ACAP", "REM"]


@dataclass(frozen=True)
class RecordingFamilyRouteDependencies:
    repository: Callable[[], Any]
    track_payload: Callable[[dict], dict]


class RecordingFamilyService:
    """Expose the recording-family repository capability with stable API errors."""

    def __init__(self, dependencies: RecordingFamilyRouteDependencies) -> None:
        self._dependencies = dependencies

    @property
    def repository(self) -> Any:
        return self._dependencies.repository()

    def duplicate_candidates(self) -> dict:
        candidates = self.repository.duplicate_candidates()
        return {
            "candidates": [
                {
                    **candidate,
                    "tracks": [self._dependencies.track_payload(track) for track in candidate["tracks"]],
                }
                for candidate in candidates
            ],
            "total": len(candidates),
        }

    def merge(self, request: DuplicateMergeRequest) -> dict:
        try:
            track = self.repository.merge_downloaded_tracks(request.survivor_id, request.duplicate_id)
        except KeyError as error:
            raise HTTPException(404, "One or more tracks were not found") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"merged": True, "track": self._dependencies.track_payload(track)}

    def keep_separate(self, track_id: int) -> dict:
        try:
            track = self.repository.separate_recording(track_id)
        except KeyError as error:
            raise HTTPException(404, "Track was not found") from error
        return {"updated": True, "track": self._dependencies.track_payload(track)}

    def family(self, track_id: int) -> dict:
        try:
            family = self.repository.recording_family(track_id)
            suggestions = self.repository.recording_family_suggestions(track_id)
        except KeyError as error:
            raise HTTPException(404, "Track was not found") from error
        return {
            "family": [self._dependencies.track_payload(track) for track in family],
            "suggestions": [{**item, "track": self._dependencies.track_payload(item["track"])} for item in suggestions],
        }

    def link(self, track_id: int, request: TrackFamilyLinkRequest) -> dict:
        target_track_id = request.target_track_id or self.repository.track_id_for_identity(request.target_identity)
        if target_track_id is None:
            raise HTTPException(404, "Target track ID was not found")
        try:
            track = self.repository.link_recording_version(track_id, target_track_id, request.relationship)
        except KeyError as error:
            raise HTTPException(404, "One or more tracks were not found") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"updated": True, "track": self._dependencies.track_payload(track)}


def create_recording_family_router(service: RecordingFamilyService) -> APIRouter:
    router = APIRouter(tags=["recording families"])

    @router.get("/api/downloaded-library/duplicate-candidates")
    def duplicate_candidates() -> dict:
        return service.duplicate_candidates()

    @router.post("/api/downloaded-library/merge-duplicate")
    def merge_duplicate(request: DuplicateMergeRequest) -> dict:
        return service.merge(request)

    @router.post("/api/downloaded-library/tracks/{track_id}/keep-separate")
    def keep_separate(track_id: int) -> dict:
        return service.keep_separate(track_id)

    @router.get("/api/downloaded-library/tracks/{track_id}/family")
    def family(track_id: int) -> dict:
        return service.family(track_id)

    @router.post("/api/downloaded-library/tracks/{track_id}/link-version")
    def link_version(track_id: int, request: TrackFamilyLinkRequest) -> dict:
        return service.link(track_id, request)

    @router.post("/api/downloaded-library/tracks/{track_id}/unlink-version")
    def unlink_version(track_id: int) -> dict:
        return service.keep_separate(track_id)

    return router
