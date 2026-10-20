"""Downloaded-track mutation workflows and HTTP routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from audioextender.core.operation_feedback import operation_receipt
from audioextender.library.metadata_mutations import TrackMetadataMutationService
from audioextender.web.contracts.downloaded_library import (
    DownloadedGenreRequest,
    DownloadedMetadataRequest,
    DownloadedTracksRequest,
)
from audioextender.web.routes.metadata_batch_routes import MetadataBatchService


@dataclass(frozen=True)
class DownloadedTrackMutationDependencies:
    repository: Callable[[], Any]
    metadata: TrackMetadataMutationService
    metadata_batches: MetadataBatchService
    genre_directory: Callable[[str], Path]
    original_import_metadata: Callable[[str, str, str], dict[str, str]]
    database_path: Callable[[], Path]


class DownloadedTrackMutationService:
    """Coordinate catalog mutations without duplicating metadata transaction rules."""

    def __init__(self, dependencies: DownloadedTrackMutationDependencies) -> None:
        self._dependencies = dependencies

    @property
    def repository(self) -> Any:
        return self._dependencies.repository()

    def delete(self, track_id: int) -> dict:
        if not self.repository.delete_downloaded_track(track_id):
            raise HTTPException(404, "Downloaded track was not found")
        return {"removed": True, "track_id": track_id}

    def delete_many(self, track_ids: list[int]) -> dict:
        requested = set(track_ids)
        removed = sum(1 for track_id in requested if self.repository.delete_downloaded_track(track_id))
        return {"removed": removed, "requested": len(requested)}

    def change_genre(self, request: DownloadedGenreRequest) -> dict:
        try:
            result = self._dependencies.metadata.change_genre(request.track_ids, request.genre_category)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (FileNotFoundError, FileExistsError) as error:
            raise HTTPException(409, str(error)) from error
        except Exception as error:
            raise HTTPException(500, f"Could not change genre: {error}") from error
        requested_count = len(set(request.track_ids))
        return {
            **result,
            "receipt": operation_receipt(
                operation="change-track-genre",
                requested=f"Move {requested_count} tracks to {request.genre_category}",
                requested_count=requested_count,
                changed=f"Moved and retagged {result['updated']} tracks",
                changed_count=int(result["updated"]),
                written_to=[str(self._dependencies.genre_directory(result["genre_category"]))],
                survives_restart=True,
                durability="WAV locations, embedded tags, sidecars, and catalog paths were persisted.",
            ),
        }

    def update_metadata(self, track_id: int, request: DownloadedMetadataRequest) -> dict:
        try:
            result = self._dependencies.metadata.update_metadata(track_id, request.mutation())
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (FileNotFoundError, FileExistsError) as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except Exception as error:
            raise HTTPException(500, f"Could not update track metadata: {error}") from error
        file_path = result.pop("file_path")
        sidecar_path = result.pop("sidecar_path")
        return {
            **result,
            "receipt": operation_receipt(
                operation="save-track-metadata",
                requested=f"Save metadata for track {track_id}",
                requested_count=1,
                changed="Updated the WAV tags, source record, and catalog entry",
                changed_count=1,
                written_to=[file_path, sidecar_path, str(self._dependencies.database_path())],
                survives_restart=True,
                durability="The WAV, source sidecar, and catalog database were updated on disk.",
            ),
        }

    def repair_playlist_derived_genres(self) -> dict:
        repaired: list[int] = []
        restored: list[int] = []
        cleared: list[int] = []
        failed: list[dict[str, object]] = []
        for track in self.repository.list_downloaded_tracks():
            playlists = [str(value).strip() for value in (track.get("playlists") or []) if str(value).strip()]
            detailed_genre = str(track.get("genre") or "").strip()
            matching_playlist = next(
                (
                    playlist
                    for playlist in playlists
                    if playlist.replace("_", " ").strip().casefold() == detailed_genre.casefold()
                ),
                "",
            )
            if not detailed_genre or not matching_playlist:
                continue
            original = self._dependencies.original_import_metadata(
                matching_playlist,
                str(track.get("title") or ""),
                str(track.get("artist") or ""),
            )
            try:
                result = self.update_metadata(
                    int(track["id"]),
                    DownloadedMetadataRequest(
                        title=str(track.get("title") or Path(str(track["file_path"])).stem),
                        artist=str(track.get("artist") or ""),
                        genre=original["genre"],
                        genre_category=original["genre_category"],
                        playlist_name=matching_playlist,
                        artwork_url="",
                        rename_file=False,
                    ),
                )
                track_id = int(result["track_id"])
                repaired.append(track_id)
                (restored if original["genre"] else cleared).append(track_id)
            except HTTPException as error:
                failed.append({"id": int(track["id"]), "error": str(error.detail)})
            except Exception as error:
                failed.append({"id": int(track["id"]), "error": str(error)})
        return {
            "repaired": len(repaired),
            "restored_from_source": len(restored),
            "cleared_without_source_genre": len(cleared),
            "failed": failed,
        }

    def retag(self, track_ids: list[int]) -> dict:
        result = self._dependencies.metadata_batches.sync_selected_wav_tags(track_ids)
        tracks = result.pop("tracks")
        tagged = result["tagged"]
        skipped = result["skipped"]
        failed = result["failed"]
        return {
            **result,
            "receipt": operation_receipt(
                operation="retag-selected-tracks",
                requested=f"Synchronize WAV tags for {len(set(track_ids))} selected tracks",
                requested_count=len(set(track_ids)),
                changed=f"Updated {len(tagged)} WAV files; {len(skipped)} were already correct",
                changed_count=len(tagged),
                written_to=[
                    str(Path(str(track["file_path"])).resolve()) for track in tracks if int(track["id"]) in tagged
                ],
                failures=failed,
                survives_restart=True,
                durability="Embedded WAV tags are stored in the audio files and survive restart.",
            ),
        }


def create_downloaded_track_mutation_router(service: DownloadedTrackMutationService) -> APIRouter:
    router = APIRouter(tags=["downloaded track mutations"])

    @router.delete("/api/downloaded-library/tracks/{track_id}")
    def remove_track(track_id: int) -> dict:
        return service.delete(track_id)

    @router.delete("/api/downloaded-library/tracks")
    def remove_tracks(request: DownloadedTracksRequest) -> dict:
        return service.delete_many(request.track_ids)

    @router.patch("/api/downloaded-library/genre")
    def change_genre(request: DownloadedGenreRequest) -> dict:
        return service.change_genre(request)

    @router.patch("/api/downloaded-library/tracks/{track_id}/metadata")
    def update_metadata(track_id: int, request: DownloadedMetadataRequest) -> dict:
        return service.update_metadata(track_id, request)

    @router.post("/api/downloaded-library/repair-playlist-derived-genres")
    def repair_playlist_derived_genres() -> dict:
        return service.repair_playlist_derived_genres()

    @router.post("/api/downloaded-library/retag")
    def retag(request: DownloadedTracksRequest) -> dict:
        return service.retag(request.track_ids)

    return router
