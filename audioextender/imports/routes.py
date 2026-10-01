"""HTTP routes for authorized source imports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audioextender.imports.local import LocalAudioImportService, LocalImportNotFoundError
from audioextender.imports.playlist_match import PlaylistMatchNotFoundError, PlaylistMatchService
from audioextender.imports.service import (
    ImportNotFoundError,
    ImportService,
    LibraryOfflineError,
)


class AuthorizedImportRequest(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    rights_basis: Literal["own-upload", "creative-commons", "public-domain", "permission"]
    confirmation: bool
    process_with_extender: bool = False
    title: str = Field(default="", max_length=300)
    artist: str = Field(default="", max_length=300)
    spotify_uri: str = Field(default="", max_length=200)
    artwork_url: str = Field(default="", max_length=1000)


def create_import_router(
    service: ImportService,
    local_service: LocalAudioImportService | None = None,
    playlist_service: PlaylistMatchService | None = None,
    parse_playlist: Callable[[bytes], list[dict]] | None = None,
    safe_playlist_name: Callable[[str], str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/imports", tags=["imports"])

    @router.post("/authorized", status_code=202)
    def create_authorized_import(request: AuthorizedImportRequest) -> dict:
        try:
            return {"import_id": service.start(request)}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except LibraryOfflineError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/{import_id}/cancel")
    def cancel_authorized_import(import_id: str) -> dict:
        try:
            return service.cancel(import_id)
        except ImportNotFoundError as error:
            raise HTTPException(404, str(error)) from error

    @router.get("/{import_id}")
    def authorized_import_status(import_id: str) -> dict:
        try:
            return service.status(import_id)
        except ImportNotFoundError as error:
            raise HTTPException(404, str(error)) from error

    @router.get("/{import_id}/download")
    def download_authorized_import(import_id: str) -> FileResponse:
        try:
            path = service.download_path(import_id)
        except ImportNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        return FileResponse(path, filename=path.name)

    if local_service is not None:

        @router.post("/local-audio", status_code=202)
        async def create_local_audio_import(
            files: Annotated[list[UploadFile], File()],
            playlist_name: Annotated[str, Form()] = "Local Playlist",
        ) -> dict:
            try:
                return await local_service.start(files, playlist_name)
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            except LibraryOfflineError as error:
                raise HTTPException(409, str(error)) from error

        @router.get("/local-audio/{batch_id}")
        def local_audio_import_status(batch_id: str) -> dict:
            try:
                return local_service.status(batch_id)
            except LocalImportNotFoundError as error:
                raise HTTPException(404, str(error)) from error

    if playlist_service is not None and parse_playlist is not None and safe_playlist_name is not None:

        @router.post("/playlist-file/matches", status_code=202)
        async def create_playlist_file_matches(file: Annotated[UploadFile, File()]) -> dict:
            if not (file.filename or "").casefold().endswith(".csv"):
                raise HTTPException(400, "Upload a CSV playlist export")
            contents = await file.read(5 * 1024 * 1024 + 1)
            if len(contents) > 5 * 1024 * 1024:
                raise HTTPException(400, "Playlist CSV must be 5 MB or smaller")
            try:
                tracks = parse_playlist(contents)
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            playlist_name = safe_playlist_name(Path(file.filename or "Imported Playlist").stem)
            return playlist_service.start(tracks, playlist_name)

        @router.get("/playlist-matches/{match_id}")
        def playlist_match_status(match_id: str) -> dict:
            try:
                return playlist_service.status(match_id)
            except PlaylistMatchNotFoundError as error:
                raise HTTPException(404, str(error)) from error

    return router
