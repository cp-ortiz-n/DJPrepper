"""Atomic file, tag, sidecar, and catalog propagation for track metadata changes."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TrackMetadataMutationDependencies:
    repository: Any
    normalize_genre: Callable[[str], str]
    genre_directory: Callable[[str], Path]
    music_library_root: Callable[[], Path]
    source_metadata_path: Callable[[Path], Path]
    write_wav_metadata: Callable[..., None]
    write_source_metadata: Callable[[Path, dict], Any]


class TrackMetadataMutationService:
    """Keep disk layout, WAV tags, sidecars, and catalog paths in one transaction."""

    def __init__(self, dependencies: TrackMetadataMutationDependencies) -> None:
        self.dependencies = dependencies

    def change_genre(self, track_ids: list[int], genre_category: str) -> dict:
        tracks = self.dependencies.repository.list_downloaded_tracks()
        requested = self.dependencies.normalize_genre(genre_category.strip())
        category = next(
            (
                str(track.get("genre_category") or "Other")
                for track in tracks
                if str(track.get("genre_category") or "Other").casefold() == requested.casefold()
            ),
            requested,
        )
        if not category or category == ".":
            raise ValueError("Choose a valid genre")
        wanted = set(track_ids)
        selected = [track for track in tracks if int(track["id"]) in wanted]
        if len(selected) != len(wanted):
            raise LookupError("One or more downloaded tracks were not found")
        destination_dir = self.dependencies.genre_directory(category)
        destination_dir.mkdir(parents=True, exist_ok=True)
        moves: list[tuple[int, Path, Path, str]] = []
        for track in selected:
            source = Path(str(track["file_path"]))
            if not source.is_file():
                raise FileNotFoundError(f"{track['filename']} is unavailable and cannot be moved")
            destination = destination_dir / source.name
            if destination.resolve() != source.resolve() and destination.exists():
                raise FileExistsError(f"{destination.name} already exists in {category}")
            moves.append((int(track["id"]), source, destination, category))
        completed: list[tuple[int, Path, Path, str]] = []
        try:
            indexed = {int(track["id"]): track for track in selected}
            for move in moves:
                track_id, source, destination, _ = move
                old_metadata = self.dependencies.source_metadata_path(source)
                if destination.resolve() != source.resolve():
                    shutil.move(str(source), str(destination))
                completed.append(move)
                metadata = indexed[track_id]
                self.dependencies.write_wav_metadata(
                    destination,
                    title=str(metadata.get("title") or destination.stem),
                    artist=str(metadata.get("artist") or ""),
                    genre=category,
                    album=str((metadata.get("playlists") or ["Imported Singles"])[0]),
                )
                self.dependencies.write_source_metadata(destination, {**metadata, "genre_category": category})
                if destination.resolve() != source.resolve():
                    old_metadata.unlink(missing_ok=True)
            self.dependencies.repository.relocate_downloaded_tracks(completed)
            for _, source, destination, _ in completed:
                if (
                    destination.resolve() != source.resolve()
                    and source.parent != self.dependencies.music_library_root()
                ):
                    try:
                        source.parent.rmdir()
                    except OSError:
                        pass
        except Exception:
            for _, source, destination, _ in reversed(completed):
                if destination.is_file() and destination.resolve() != source.resolve():
                    shutil.move(str(destination), str(source))
            raise
        return {"updated": len(completed), "genre_category": category}
