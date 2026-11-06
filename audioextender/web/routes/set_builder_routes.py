"""FastAPI routes for Set Builder catalog access and playlist export."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audioextender.set_builder import catalog_cache as cache
from audioextender.set_builder.brief_preparation import BriefPreparationService
from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.journey_planner import JourneyPlanner
from audioextender.set_builder.saved_sets import SavedSetService


class SetExportPreflightRequest(BaseModel):
    paths: list[str] = Field(default_factory=list, max_length=5000)


class SetPlaylistTrack(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    duration_seconds: float = Field(default=0, ge=0)


class SetPlaylistSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    tracks: list[SetPlaylistTrack] = Field(min_length=1, max_length=5000)


class SetIntentionRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    catalog_vocabulary: list[str | dict[str, Any]] = Field(default_factory=list, max_length=2000)


class SetJourneyRequest(SetIntentionRequest):
    interpreted_intention: dict[str, Any] = Field(default_factory=dict)
    duration_minutes: int = Field(default=60, ge=15, le=480)


class SetBriefPreparationRequest(SetIntentionRequest):
    duration_minutes: int = Field(default=60, ge=15, le=480)


class SavedSetRequest(BaseModel):
    record: dict[str, Any]


class SavedSetMigrationRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)


@dataclass(frozen=True)
class SetBuilderRouteDependencies:
    catalog_cache_path: Path
    ensure_catalog_current: Callable[[], Any]
    write_catalog_cache: Callable[[], Any]
    music_library_root: Callable[[], Path]
    safe_folder_name: Callable[[str], str]
    intention_planner: IntentionPlanner
    journey_planner: JourneyPlanner
    saved_sets: SavedSetService
    brief_preparation: BriefPreparationService | None = None


def preflight_paths(request: SetExportPreflightRequest) -> dict:
    """Verify every local audio path before a playlist is exported."""
    items = []
    for raw_path in request.paths:
        value = str(raw_path or "").strip()
        path = Path(value).expanduser() if value else None
        exists = bool(path and path.is_file())
        items.append(
            {
                "path": str(path) if path else value,
                "exists": exists,
                "reason": "" if exists else ("No file path is available" if not value else "File is missing from disk"),
            }
        )
    valid = sum(1 for item in items if item["exists"])
    return {
        "ready": valid == len(items) and bool(items),
        "valid": valid,
        "missing": len(items) - valid,
        "total": len(items),
        "items": items,
    }


def save_playlist_file(
    request: SetPlaylistSaveRequest,
    library_root: Path,
    safe_folder_name: Callable[[str], str],
) -> dict:
    """Persist a created set beside the organized music library."""
    missing = [track.path for track in request.tracks if not Path(track.path).expanduser().is_file()]
    if missing:
        raise HTTPException(
            409,
            detail={
                "message": "Playlist contains files that are missing from disk.",
                "missing": missing,
            },
        )
    playlist_directory = library_root / "_Playlist"
    playlist_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_folder_name(request.name)}.m3u8"
    playlist_path = playlist_directory / filename
    lines = ["#EXTM3U"]
    for track in request.tracks:
        lines.extend(
            [
                f"#EXTINF:{round(track.duration_seconds)},{track.title or Path(track.path).stem}",
                str(Path(track.path).expanduser().resolve()),
            ]
        )
    playlist_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return {"saved": True, "path": str(playlist_path), "tracks": len(request.tracks)}


def create_set_builder_router(deps: SetBuilderRouteDependencies) -> APIRouter:
    """Create the Set Builder router with explicit application dependencies."""
    router = APIRouter(prefix="/api/set-builder", tags=["set-builder"])

    def catalog_vocabulary(requested: list[Any]) -> list[dict[str, Any]]:
        return cache.authoritative_catalog_vocabulary(
            deps.catalog_cache_path,
            deps.ensure_catalog_current,
            deps.write_catalog_cache,
            requested,
        )

    @router.get("/catalog", response_model=None)
    def catalog() -> FileResponse | dict:
        """Return all latest analyzed tracks without loading full job history."""
        cache.current_catalog_payload(deps.catalog_cache_path, deps.ensure_catalog_current, deps.write_catalog_cache)
        return FileResponse(
            deps.catalog_cache_path,
            media_type="application/json",
            headers={"Cache-Control": "no-cache"},
        )

    @router.get("/catalog-version")
    def catalog_version() -> dict[str, int]:
        return {"version": cache.catalog_schema_version()}

    @router.post("/export-preflight")
    def export_preflight(request: SetExportPreflightRequest) -> dict:
        return preflight_paths(request)

    @router.post("/save-playlist")
    def save_playlist(request: SetPlaylistSaveRequest) -> dict:
        return save_playlist_file(request, deps.music_library_root(), deps.safe_folder_name)

    @router.get("/sets")
    def saved_sets() -> dict[str, Any]:
        return deps.saved_sets.list_sets()

    @router.put("/sets/{set_id}")
    def save_set(set_id: str, request: SavedSetRequest) -> dict[str, Any]:
        record = {**request.record, "id": set_id}
        try:
            return deps.saved_sets.upsert(record)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.delete("/sets/{set_id}")
    def delete_set(set_id: str) -> dict[str, Any]:
        return deps.saved_sets.delete(set_id)

    @router.post("/sets/migrate-v1")
    def migrate_saved_sets(request: SavedSetMigrationRequest) -> dict[str, Any]:
        try:
            return deps.saved_sets.migrate_v1(request.records)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/intention-provider")
    def intention_provider() -> dict:
        return deps.intention_planner.status()

    @router.post("/interpret-intention")
    def interpret_intention(request: SetIntentionRequest) -> dict:
        try:
            return deps.intention_planner.interpret(
                request.brief,
                catalog_vocabulary(request.catalog_vocabulary),
            )
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            raise HTTPException(502, f"AI interpretation failed: {error}") from error

    @router.post("/prepare-brief")
    def prepare_brief(request: SetBriefPreparationRequest) -> dict:
        if deps.brief_preparation is None:
            raise HTTPException(503, "Combined brief preparation is unavailable")
        try:
            return deps.brief_preparation.prepare(
                request.brief,
                catalog_vocabulary(request.catalog_vocabulary),
                request.duration_minutes,
            )
        except (httpx.HTTPError, ValueError, RuntimeError, TimeoutError) as error:
            raise HTTPException(502, f"AI brief preparation failed: {error}") from error

    @router.post("/plan-journey")
    def plan_journey(request: SetJourneyRequest) -> dict:
        return deps.journey_planner.plan(
            request.brief,
            request.interpreted_intention,
            catalog_vocabulary(request.catalog_vocabulary),
            request.duration_minutes,
        )

    return router
