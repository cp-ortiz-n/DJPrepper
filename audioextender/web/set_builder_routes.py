"""FastAPI routes for Set Builder catalog access and playlist export."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audioextender.set_builder.intention_planner import IntentionPlanner


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
    catalog_vocabulary: list[str] = Field(default_factory=list, max_length=2000)


@dataclass(frozen=True)
class SetBuilderRouteDependencies:
    catalog_cache_path: Path
    ensure_catalog_current: Callable[[], Any]
    write_catalog_cache: Callable[[], Any]
    music_library_root: Callable[[], Path]
    safe_folder_name: Callable[[str], str]
    intention_planner: IntentionPlanner


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

    @router.get("/catalog", response_model=None)
    def catalog() -> FileResponse | dict:
        """Return all latest analyzed tracks without loading full job history."""
        deps.ensure_catalog_current()
        cache_current = False
        try:
            cache_current = json.loads(deps.catalog_cache_path.read_text(encoding="utf-8")).get("version") == 3
        except (OSError, ValueError):
            pass
        if not cache_current:
            deps.write_catalog_cache()
        return FileResponse(
            deps.catalog_cache_path,
            media_type="application/json",
            headers={"Cache-Control": "no-cache"},
        )

    @router.post("/export-preflight")
    def export_preflight(request: SetExportPreflightRequest) -> dict:
        return preflight_paths(request)

    @router.post("/save-playlist")
    def save_playlist(request: SetPlaylistSaveRequest) -> dict:
        return save_playlist_file(request, deps.music_library_root(), deps.safe_folder_name)

    @router.get("/intention-provider")
    def intention_provider() -> dict:
        return deps.intention_planner.status()

    @router.post("/interpret-intention")
    def interpret_intention(request: SetIntentionRequest) -> dict:
        try:
            return deps.intention_planner.interpret(request.brief, request.catalog_vocabulary)
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            raise HTTPException(502, f"AI interpretation failed: {error}") from error

    return router
