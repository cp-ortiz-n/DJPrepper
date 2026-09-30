"""HTTP routes for authorized source imports."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from helpers.import_service import (
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


def create_import_router(service: ImportService) -> APIRouter:
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

    return router
