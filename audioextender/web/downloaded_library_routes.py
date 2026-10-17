"""Read, media-delivery, reveal, and archive routes for downloaded tracks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from audioextender.library.artwork_thumbnails import ArtworkThumbnailService
from audioextender.library.catalog_query_service import DownloadedCatalogQuery, DownloadedCatalogQueryService
from audioextender.web.downloaded_library_models import DownloadedTracksRequest


@dataclass(frozen=True)
class DownloadedLibraryRouteDependencies:
    repository: Callable[[], Any]
    catalog_query: DownloadedCatalogQueryService
    artwork_thumbnails: ArtworkThumbnailService
    safe_folder_name: Callable[[str], str]
    genre_path_parts: Callable[[str], tuple[str, ...]]
    reveal: Callable[[Path], None] | None = None


class DownloadedLibraryDeliveryService:
    """Resolve catalog media and build transient user-facing downloads."""

    def __init__(self, dependencies: DownloadedLibraryRouteDependencies) -> None:
        self._dependencies = dependencies

    def catalog(self, query: DownloadedCatalogQuery) -> dict:
        return self._dependencies.catalog_query.execute(query)

    def audio(self, track_id: int) -> FileResponse:
        path = self._audio_path(track_id)
        return FileResponse(path, filename=path.name, media_type="audio/wav")

    def artwork(self, track_id: int, *, thumbnail: bool) -> FileResponse:
        track = self._dependencies.repository().get_downloaded_track(track_id)
        path = Path(str(track.get("artwork_path") or "")) if track else None
        if path is None or not path.is_file():
            raise HTTPException(404, "Track artwork is unavailable")
        if thumbnail:
            path = self._dependencies.artwork_thumbnails.get_or_queue(path)
        media_type = "image/png" if path.suffix.casefold() == ".png" else "image/jpeg"
        headers = {"Cache-Control": "public, max-age=31536000, immutable"} if thumbnail else None
        return FileResponse(path, media_type=media_type, headers=headers)

    def reveal(self, track_id: int) -> dict:
        path = self._audio_path(track_id)
        try:
            (self._dependencies.reveal or self._reveal_on_host)(path)
        except OSError as error:
            raise HTTPException(500, "The system file browser could not be opened") from error
        return {"revealed": True, "absolute_path": str(path.resolve())}

    def selected_archive(self, track_ids: list[int]) -> FileResponse:
        wanted = set(track_ids)
        tracks = [track for track in self._dependencies.repository().list_downloaded_tracks() if track["id"] in wanted]
        if len(tracks) != len(wanted):
            raise HTTPException(404, "One or more downloaded tracks were not found")
        return self.archive(tracks, "Selected Downloaded Tracks")

    def genre_archive(self, genre: str) -> FileResponse:
        tracks = [
            track
            for track in self._dependencies.repository().list_downloaded_tracks()
            if str(track.get("genre_category") or "Other").casefold() == genre.casefold()
        ]
        return self.archive(tracks, genre)

    def playlist_archive(self, playlist: str) -> FileResponse:
        tracks = [
            track
            for track in self._dependencies.repository().list_downloaded_tracks()
            if any(item.casefold() == playlist.casefold() for item in track.get("playlists", []))
        ]
        return self.archive(tracks, playlist)

    def archive(self, tracks: list[dict], name: str) -> FileResponse:
        available = [track for track in tracks if Path(track["file_path"]).is_file()]
        if not available:
            raise HTTPException(404, "No downloaded WAV files are available for this selection")
        handle = tempfile.NamedTemporaryFile(prefix="audioextender-downloads-", suffix=".zip", delete=False)
        archive = Path(handle.name)
        handle.close()
        root_name = self._dependencies.safe_folder_name(name)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
            used: set[str] = set()
            for track in available:
                path = Path(track["file_path"])
                category = "/".join(self._dependencies.genre_path_parts(track.get("genre_category") or "Other"))
                relative = f"{root_name}/{category}/{path.name}"
                counter = 2
                while relative.casefold() in used:
                    relative = f"{root_name}/{category}/{path.stem} ({counter}){path.suffix}"
                    counter += 1
                used.add(relative.casefold())
                bundle.write(path, arcname=relative)
        return FileResponse(
            archive,
            filename=f"{root_name} - WAVs.zip",
            media_type="application/zip",
            background=BackgroundTask(archive.unlink, missing_ok=True),
        )

    def _audio_path(self, track_id: int) -> Path:
        track = self._dependencies.repository().get_downloaded_track(track_id)
        path = Path(str(track.get("file_path") or "")) if track else None
        if path is None or not path.is_file():
            raise HTTPException(404, "Downloaded WAV is unavailable")
        return path

    @staticmethod
    def _reveal_on_host(path: Path) -> None:
        if sys.platform == "darwin":
            command = ["open", "-R", str(path)]
        elif sys.platform.startswith("win"):
            command = ["explorer", f"/select,{path}"]
        else:
            command = ["xdg-open", str(path.parent)]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def create_downloaded_library_router(service: DownloadedLibraryDeliveryService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/downloaded-library")
    def downloaded_library(
        paged: bool = False,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        search: str = Query(default="", max_length=300),
        genre: str = Query(default="all", max_length=100),
        detailed_genre: str = Query(default="all", max_length=120),
        playlist: str = Query(default="all", max_length=200),
        analysis: str = Query(default="all", max_length=30),
        artwork: str = Query(default="all", pattern="^(all|missing|available)$"),
        quality: str = Query(default="all", pattern="^(all|excellent|good|review|poor|below-target|unanalyzed)$"),
        sort: str = Query(default="newest", max_length=30),
    ) -> dict:
        return service.catalog(
            DownloadedCatalogQuery(
                paged=paged,
                page=page,
                page_size=page_size,
                search=search,
                genre=genre,
                detailed_genre=detailed_genre,
                playlist=playlist,
                analysis=analysis,
                artwork=artwork,
                quality=quality,
                sort=sort,
            )
        )

    @router.get("/api/downloaded-library/tracks/{track_id}/audio")
    def downloaded_track_audio(track_id: int) -> FileResponse:
        return service.audio(track_id)

    @router.get("/api/downloaded-library/tracks/{track_id}/artwork")
    def downloaded_track_artwork(track_id: int, thumbnail: bool = False) -> FileResponse:
        return service.artwork(track_id, thumbnail=thumbnail)

    @router.get("/api/downloaded-library/tracks/{track_id}/download")
    def downloaded_track_download(track_id: int) -> FileResponse:
        return service.audio(track_id)

    @router.post("/api/downloaded-library/tracks/{track_id}/reveal")
    def reveal_downloaded_track(track_id: int) -> dict:
        return service.reveal(track_id)

    @router.post("/api/downloaded-library/download")
    def download_selected_tracks(request: DownloadedTracksRequest) -> FileResponse:
        return service.selected_archive(request.track_ids)

    @router.get("/api/downloaded-library/genres/{genre}/download")
    def download_genre(genre: str) -> FileResponse:
        return service.genre_archive(genre)

    @router.get("/api/downloaded-library/playlists/{playlist}/download")
    def download_playlist(playlist: str) -> FileResponse:
        return service.playlist_archive(playlist)

    return router
