"""HTTP routes for queuing downloaded-library analysis jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from audioextender.library.analysis_queue import DownloadedTrackAnalysisQueue
from audioextender.web.downloaded_library_models import DownloadedTracksRequest


class DownloadedAnalysisFilterRequest(BaseModel):
    search: str = Field(default="", max_length=300)
    genre: str = Field(default="all", max_length=100)
    detailed_genre: str = Field(default="all", max_length=120)
    playlist: str = Field(default="all", max_length=200)
    analysis: str = Field(default="all", max_length=30)
    quality: str = Field(default="all", max_length=30)
    sort: str = Field(default="newest", max_length=30)


@dataclass(frozen=True)
class DownloadedAnalysisRouteService:
    """Resolve catalog selections and delegate job creation to the queue."""

    repository: Callable[[], Any]
    queue: Callable[[], DownloadedTrackAnalysisQueue]

    def selected(self, track_ids: list[int], *, force: bool) -> dict[str, list[int]]:
        wanted = set(track_ids)
        repository = self.repository()
        source = repository.list_downloaded_tracks_with_jobs() if force else repository.list_downloaded_tracks()
        tracks = [track for track in source if int(track["id"]) in wanted]
        if len(tracks) != len(wanted):
            raise HTTPException(404, "One or more downloaded tracks were not found")
        return self.queue().queue(tracks, force=force)

    def matching(self, request: DownloadedAnalysisFilterRequest, *, force: bool) -> dict[str, Any]:
        if not force and request.analysis in {"complete", "active"}:
            return {"job_ids": [], "skipped": [], "unavailable": [], "matched": 0}
        tracks, _ = self.repository().page_downloaded_tracks(
            page=1,
            page_size=10_000_000,
            search=request.search,
            genre=request.genre,
            detailed_genre=request.detailed_genre,
            playlist=request.playlist,
            analysis=request.analysis if force else ("failed" if request.analysis == "failed" else "needs"),
            quality=request.quality,
            sort=request.sort,
        )
        return {**self.queue().queue(tracks, force=force), "matched": len(tracks)}


def create_downloaded_analysis_router(service: DownloadedAnalysisRouteService) -> APIRouter:
    router = APIRouter(prefix="/api/downloaded-library", tags=["downloaded-library-analysis"])

    @router.post("/analyze", status_code=202)
    def analyze(request: DownloadedTracksRequest) -> dict:
        return service.selected(request.track_ids, force=False)

    @router.post("/reanalyze", status_code=202)
    def reanalyze(request: DownloadedTracksRequest) -> dict:
        return service.selected(request.track_ids, force=True)

    @router.post("/analyze-matching", status_code=202)
    def analyze_matching(request: DownloadedAnalysisFilterRequest) -> dict:
        return service.matching(request, force=False)

    @router.post("/reanalyze-matching", status_code=202)
    def reanalyze_matching(request: DownloadedAnalysisFilterRequest) -> dict:
        return service.matching(request, force=True)

    return router
