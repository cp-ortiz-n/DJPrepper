"""HTTP delivery for previewable Rekordbox collection-rating synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from audioextender.imports.rekordbox_ratings import (
    MAX_REKORDBOX_EXPORT_BYTES,
    RekordboxRatingImportError,
    RekordboxRatingSyncService,
)


class RekordboxRatingApplyRequest(BaseModel):
    token: str = Field(min_length=1)


def create_rekordbox_rating_router(service: RekordboxRatingSyncService) -> APIRouter:
    router = APIRouter(prefix="/api/settings/rekordbox-ratings", tags=["settings", "rekordbox"])

    @router.get("")
    def status() -> dict:
        return service.status()

    @router.post("/preview")
    async def preview(file: Annotated[UploadFile, File()]) -> dict:
        if Path(str(file.filename or "")).suffix.casefold() not in {".xml", ".txt"}:
            raise HTTPException(status_code=400, detail="Choose a Rekordbox collection XML or TXT export.")
        content = await file.read(MAX_REKORDBOX_EXPORT_BYTES + 1)
        try:
            return service.preview(content, file.filename or "collection.xml")
        except RekordboxRatingImportError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.post("/apply")
    def apply(request: RekordboxRatingApplyRequest) -> dict:
        try:
            return service.apply(request.token)
        except RekordboxRatingImportError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.delete("")
    def clear() -> dict:
        return service.clear()

    return router
