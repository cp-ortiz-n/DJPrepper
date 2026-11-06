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
    cache_track_artwork: Callable[[str, Path], str]
    safe_audio_name: Callable[[str], str]
    publish_catalog: Callable[[], Any]


@dataclass(frozen=True)
class TrackMetadataUpdate:
    title: str
    artist: str = ""
    genre: str = ""
    genre_category: str = "Other"
    playlist_name: str = "Imported Singles"
    artwork_url: str = ""
    rename_file: bool = False


class TrackMetadataMutationService:
    """Keep disk layout, WAV tags, sidecars, and catalog paths in one transaction."""

    def __init__(self, dependencies: TrackMetadataMutationDependencies) -> None:
        self.dependencies = dependencies

    def change_genre(self, track_ids: list[int], genre_category: str, *, publish: bool = True) -> dict:
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
        if publish and completed:
            self.dependencies.publish_catalog()
        return {"updated": len(completed), "genre_category": category}

    def update_metadata(self, track_id: int, update: TrackMetadataUpdate, *, publish: bool = True) -> dict:
        """Synchronize editable metadata across the WAV, sidecar, and catalog."""
        repository = self.dependencies.repository
        track = repository.get_downloaded_track(track_id)
        if not track:
            raise LookupError("Downloaded track was not found")
        source = Path(str(track["file_path"]))
        if not source.is_file():
            raise FileNotFoundError("The WAV file is missing and cannot be updated")
        category = self.dependencies.normalize_genre(update.genre_category.strip())
        if not category or category == ".":
            raise ValueError("Choose a valid genre category")
        title = update.title.strip()
        artist = update.artist.strip()
        detailed_genre = update.genre.strip()
        playlist_name = update.playlist_name.strip() or "Imported Singles"
        artwork_url = update.artwork_url.strip()
        filename = source.name
        if update.rename_file:
            display_name = " - ".join(value for value in (artist, title) if value) or title
            filename = f"{self.dependencies.safe_audio_name(display_name)}{source.suffix.lower()}"
        destination_dir = self.dependencies.genre_directory(category)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / filename
        if destination.resolve() != source.resolve() and destination.exists():
            raise FileExistsError(f"{destination.name} already exists in {category}")
        old_metadata = self.dependencies.source_metadata_path(source)
        moved = destination.resolve() != source.resolve()
        try:
            if moved:
                shutil.move(str(source), str(destination))
            self.dependencies.write_wav_metadata(
                destination,
                title=title,
                artist=artist,
                genre=category,
                album=playlist_name,
            )
            stored_artwork_url = str(track.get("artwork_url") or "")
            artwork_path = str(track.get("artwork_path") or "")
            artwork_changed = artwork_url != stored_artwork_url
            if artwork_url and (artwork_changed or not Path(artwork_path).is_file()):
                cached_artwork_path = self.dependencies.cache_track_artwork(artwork_url, destination)
                if cached_artwork_path:
                    artwork_path = cached_artwork_path
                elif artwork_changed:
                    raise ValueError("Artwork could not be downloaded. Use a direct Spotify or YouTube image URL.")
            metadata = {
                **track,
                "title": title,
                "artist": artist,
                "genre": detailed_genre,
                "genre_category": category,
                "playlist_name": playlist_name,
                "playlists": [playlist_name],
                "file_path": str(destination.resolve()),
                "filename": destination.name,
                "artwork_url": artwork_url or stored_artwork_url,
                "artwork_path": artwork_path,
            }
            self.dependencies.write_source_metadata(destination, metadata)
            repository.update_downloaded_track_metadata(
                track_id=track_id,
                old_path=source,
                new_path=destination,
                title=title,
                artist=artist,
                genre=detailed_genre,
                genre_category=category,
                playlist_name=playlist_name,
            )
            if artwork_url and artwork_path:
                repository.update_downloaded_track_artwork(
                    track_id,
                    artwork_url=artwork_url,
                    artwork_path=artwork_path,
                )
            if moved:
                old_metadata.unlink(missing_ok=True)
                try:
                    source.parent.rmdir()
                except OSError:
                    pass
        except Exception:
            if moved and destination.is_file() and not source.exists():
                shutil.move(str(destination), str(source))
            raise
        if publish:
            self.dependencies.publish_catalog()
        return {
            "updated": True,
            "track_id": track_id,
            "title": title,
            "artist": artist,
            "genre": detailed_genre,
            "genre_category": category,
            "playlist_name": playlist_name,
            "filename": destination.name,
            "artwork_url": metadata["artwork_url"],
            "artwork_available": bool(artwork_path),
            "file_path": str(destination.resolve()),
            "sidecar_path": str(self.dependencies.source_metadata_path(destination)),
        }
