"""Metadata batch services and backward-compatible downloaded-library routes."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from audioextender.imports.source_artwork import SourceArtworkService
from audioextender.infrastructure.batch_operations import BatchContext, BatchOperationRegistry


class TrackIdsRequest(BaseModel):
    track_ids: list[int] = Field(default_factory=list, max_length=5000)


@dataclass
class MetadataBatchDependencies:
    repository: Callable[[], Any]
    require_library_online: Callable[[], Any]
    sync_wav_metadata: Callable[..., bool]
    read_wav_artwork: Callable[[Path], Any]
    embed_wav_artwork: Callable[[Path, Path], Any]
    source_artwork: SourceArtworkService
    generalized_genre: Callable[[str], str]
    normalize_genre: Callable[[str], str]
    genre_directory: Callable[[str], Path]
    change_genre: Callable[[list[int], str], dict]
    publish_catalog: Callable[[], Any]
    refresh_wav_tag_audit: Callable[[], dict]
    schedule_wav_tag_audit_refresh: Callable[[], None]
    music_library_root: Callable[[], Path]
    registry: BatchOperationRegistry
    thread_factory: Callable[..., threading.Thread] = threading.Thread


class MetadataBatchService:
    def __init__(self, dependencies: MetadataBatchDependencies) -> None:
        self.dependencies = dependencies

    @property
    def repository(self) -> Any:
        return self.dependencies.repository()

    def start_wav_tags(self) -> dict:
        self.dependencies.require_library_online()
        tracks = self.repository.list_downloaded_tracks()
        return self.dependencies.registry.start(
            "wav-tags",
            tracks,
            self._sync_wav_tags,
            stage="Synchronizing WAV metadata",
            counters={"tagged": 0},
            requested="Synchronize WAV tags with the catalog",
            written_to=[str(self.dependencies.music_library_root())],
            durability="WAV tags are written to the audio files and survive restart.",
            thread_factory=self.dependencies.thread_factory,
        )

    def _sync_wav_tags(self, context: BatchContext, tracks: list[dict]) -> dict:
        tagged = skipped = failed = 0
        for index, track in enumerate(tracks, start=1):
            context.check_canceled()
            path = Path(str(track["file_path"]))
            error = ""
            try:
                updated = self.sync_track_wav_metadata(track)
                tagged += int(updated)
                skipped += int(not updated)
            except (FileNotFoundError, OSError, ValueError, subprocess.SubprocessError) as exception:
                failed += 1
                error = str(exception)
            context.progress(
                processed=index,
                stage=f"Synchronizing WAV metadata {index} of {len(tracks)}",
                counters={"tagged": tagged, "skipped": skipped, "failed": failed, "succeeded": tagged},
                error=(
                    {"id": int(track["id"]), "filename": track["filename"], "path": str(path), "error": error}
                    if error
                    else None
                ),
            )
        return {
            "tagged": tagged,
            "skipped": skipped,
            "failed": failed,
            "stage": "WAV metadata synchronization complete",
        }

    def sync_selected_wav_tags(self, track_ids: list[int]) -> dict:
        """Synchronize selected catalog records using the same rules as the batch."""
        self.dependencies.require_library_online()
        wanted = set(track_ids)
        tracks = [track for track in self.repository.list_downloaded_tracks() if int(track["id"]) in wanted]
        if len(tracks) != len(wanted):
            raise HTTPException(404, "One or more downloaded tracks were not found")
        tagged: list[int] = []
        skipped: list[int] = []
        failed: list[dict[str, object]] = []
        for track in tracks:
            try:
                destination = tagged if self.sync_track_wav_metadata(track) else skipped
                destination.append(int(track["id"]))
            except (FileNotFoundError, OSError, ValueError, subprocess.SubprocessError) as error:
                failed.append({"id": int(track["id"]), "error": str(error)})
        return {"tracks": tracks, "tagged": tagged, "skipped": skipped, "failed": failed}

    def sync_track_wav_metadata(self, track: dict) -> bool:
        """Apply the authoritative catalog-to-WAV tag projection to one track."""
        path = Path(str(track["file_path"]))
        return self.dependencies.sync_wav_metadata(
            path,
            title=str(track.get("title") or path.stem),
            artist=str(track.get("artist") or ""),
            genre=str(track.get("genre_category") or "Other"),
            album=str((track.get("playlists") or ["Imported Singles"])[0]),
        )

    def start_artwork(self, track_ids: list[int]) -> dict:
        self.dependencies.require_library_online()
        tracks = self.repository.list_downloaded_tracks()
        if track_ids:
            wanted = set(dict.fromkeys(track_ids))
            tracks = [track for track in tracks if int(track["id"]) in wanted]
            if not tracks:
                raise HTTPException(404, "None of the selected tracks remain in the catalog")
        else:
            tracks = [track for track in tracks if not Path(str(track.get("artwork_path") or "")).is_file()]
        return self.dependencies.registry.start(
            "artwork",
            tracks,
            self._sync_artwork,
            stage="Synchronizing artwork",
            counters={"updated": 0, "resolved": 0},
            requested="Find, cache, and embed missing artwork",
            written_to=[str(self.dependencies.music_library_root())],
            durability="Artwork is stored in WAV files and the catalog and survives restart.",
            thread_factory=self.dependencies.thread_factory,
        )

    def _sync_artwork(self, context: BatchContext, tracks: list[dict]) -> dict:
        updated = skipped = failed = 0
        for index, track in enumerate(tracks, start=1):
            context.check_canceled()
            outcome = "skipped"
            error = ""
            path = Path(str(track.get("file_path") or ""))
            try:
                if not path.is_file():
                    raise FileNotFoundError(path)
                cached_path = Path(str(track.get("artwork_path") or ""))
                if cached_path.is_file():
                    if self.dependencies.read_wav_artwork(path) is None:
                        self.dependencies.embed_wav_artwork(path, cached_path)
                        outcome = "updated"
                else:
                    artwork = self.dependencies.source_artwork.sync_track(track, path)
                    if artwork is None:
                        raise ValueError("No supported artwork source could be resolved and embedded")
                    self.repository.update_downloaded_track_artwork(
                        int(track["id"]), artwork_url=artwork.url, artwork_path=artwork.path
                    )
                    outcome = "updated"
            except Exception as exception:
                outcome, error = "failed", str(exception)
            updated += int(outcome == "updated")
            skipped += int(outcome == "skipped")
            failed += int(outcome == "failed")
            context.progress(
                processed=index,
                stage=f"Synchronizing artwork {index} of {len(tracks)}",
                counters={"updated": updated, "skipped": skipped, "failed": failed, "succeeded": updated},
                error=({"id": int(track["id"]), "filename": track["filename"], "error": error} if error else None),
            )
        if updated:
            self.dependencies.publish_catalog()
        return {"updated": updated, "skipped": skipped, "failed": failed, "stage": "Artwork synchronization complete"}

    def start_genre_rescan(self) -> dict:
        self.dependencies.require_library_online()
        return self.dependencies.registry.start(
            "genre-rescan",
            self.repository.list_downloaded_tracks(),
            self._rescan_genres,
            stage="Rescanning genres",
            counters={"updated": 0, "unchanged": 0, "unresolved": 0},
            requested="Rescan detailed genres and organize tracks into genre folders",
            written_to=[str(self.dependencies.music_library_root())],
            durability="File moves and catalog paths are permanent and survive restart.",
            thread_factory=self.dependencies.thread_factory,
        )

    def _rescan_genres(self, context: BatchContext, tracks: list[dict]) -> dict:
        counters = {"updated": 0, "unchanged": 0, "unresolved": 0, "failed": 0}
        conflicts: list[dict] = []
        for index, track in enumerate(tracks, start=1):
            context.check_canceled()
            outcome = "unchanged"
            detailed = str(track.get("genre") or "").strip()
            inferred = self.dependencies.generalized_genre(detailed)
            current = self.dependencies.normalize_genre(track.get("genre_category") or "Other")
            destination = self.dependencies.genre_directory(inferred) / Path(str(track["file_path"])).name
            needs_move = inferred != "Other" and (
                current != inferred or Path(str(track["file_path"])).resolve() != destination.resolve()
            )
            target = "Other" if inferred == "Other" and current == "Latin / Other" else inferred
            if inferred == "Other" and current != "Latin / Other":
                outcome = "unresolved"
            elif needs_move or target == "Other":
                try:
                    self.dependencies.change_genre([int(track["id"])], target)
                    outcome = "updated"
                except HTTPException as error:
                    outcome = "failed"
                    conflict = {
                        "id": int(track["id"]),
                        "track_id": int(track["id"]),
                        "title": track.get("title") or track.get("filename"),
                        "reason": str(error.detail),
                        "error": str(error.detail),
                    }
                    conflicts.append(conflict)
            counters[outcome] += 1
            context.progress(
                processed=index,
                stage=f"Rescanning genres {index} of {len(tracks)}",
                counters={**counters, "succeeded": counters["updated"]},
                error=conflicts[-1] if outcome == "failed" else None,
            )
        if counters["updated"]:
            self.dependencies.publish_catalog()
        return {**counters, "conflicts": conflicts, "stage": "Genre rescan complete"}

    def status(self, batch_id: str) -> dict:
        """Return the current state of a metadata batch by identifier."""
        try:
            return self.dependencies.registry.status(batch_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    def latest(self, kind: str) -> dict:
        """Return the latest metadata batch of a given kind."""
        return self.dependencies.registry.latest(kind) or {"status": "none"}


def create_metadata_batch_router(service: MetadataBatchService) -> APIRouter:
    """Create and return an APIRouter for metadata batch operations."""

    router = APIRouter(tags=["metadata batches"])

    @router.post("/api/downloaded-library/retag-all", status_code=202)
    def start_wav_tags() -> dict:
        return service.start_wav_tags()

    @router.get("/api/downloaded-library/retag-all-latest")
    def latest_wav_tags() -> dict:
        latest = service.latest("wav-tags")
        if latest["status"] == "none":
            return service.dependencies.refresh_wav_tag_audit()
        return latest

    @router.get("/api/downloaded-library/retag-all/{batch_id}")
    def wav_tags_status(batch_id: str) -> dict:
        return service.status(batch_id)

    @router.post("/api/downloaded-library/artwork-sync", status_code=202)
    def start_artwork(request: TrackIdsRequest | None = None) -> dict:
        return service.start_artwork(request.track_ids if request else [])

    @router.get("/api/downloaded-library/artwork-sync-latest")
    def latest_artwork() -> dict:
        return service.latest("artwork")

    @router.get("/api/downloaded-library/artwork-sync/{batch_id}")
    def artwork_status(batch_id: str) -> dict:
        return service.status(batch_id)

    @router.post("/api/downloaded-library/rescan-genres", status_code=202)
    def start_genres() -> dict:
        return service.start_genre_rescan()

    @router.get("/api/downloaded-library/rescan-genres-latest")
    def latest_genres() -> dict:
        return service.latest("genre-rescan")

    @router.get("/api/downloaded-library/rescan-genres/{batch_id}")
    def genre_status(batch_id: str) -> dict:
        return service.status(batch_id)

    @router.get("/api/downloaded-library/metadata-batches/{batch_id}")
    def metadata_batch_status(batch_id: str) -> dict:
        return service.status(batch_id)

    @router.post("/api/downloaded-library/metadata-batches/{batch_id}/cancel")
    def cancel_metadata_batch(batch_id: str) -> dict:
        try:
            return service.dependencies.registry.cancel(batch_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    @router.post("/api/downloaded-library/metadata-batches/{batch_id}/retry", status_code=202)
    def retry_metadata_batch(batch_id: str) -> dict:
        try:
            return service.dependencies.registry.retry(batch_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    return router
