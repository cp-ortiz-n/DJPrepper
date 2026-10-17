"""Shared request contracts for downloaded-library routes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from audioextender.library.metadata_mutations import TrackMetadataUpdate


class DownloadedTracksRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=1000)


class DownloadedGenreRequest(DownloadedTracksRequest):
    genre_category: str = Field(min_length=1, max_length=80)


class DownloadedMetadataRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="", max_length=300)
    genre: str = Field(default="", max_length=500)
    genre_category: str = Field(min_length=1, max_length=80)
    playlist_name: str = Field(default="Imported Singles", min_length=1, max_length=180)
    artwork_url: str = Field(default="", max_length=1000)
    rename_file: bool = False

    def mutation(self) -> TrackMetadataUpdate:
        return TrackMetadataUpdate(**self.model_dump())
