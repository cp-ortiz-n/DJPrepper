"""Local audio import staging, conversion, and catalog persistence."""

from __future__ import annotations

import shutil
import subprocess
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any


class LocalImportNotFoundError(LookupError):
    pass


class LocalAudioImportService:
    SUPPORTED = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav", ".aiff", ".aif"}

    def __init__(
        self,
        *,
        repository: Any,
        staging_root: Path,
        require_library_online: Callable[[], Path],
        probe_audio: Callable[[Path], dict[str, Any]],
        generalized_genre: Callable[[str], str],
        genre_directory: Callable[[str], Path],
        write_metadata: Callable[..., None],
        write_source_metadata: Callable[[Path, dict[str, Any]], Any],
        safe_name: Callable[[str], str],
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._repository = repository
        self._staging_root = staging_root
        self._require_library_online = require_library_online
        self._probe_audio = probe_audio
        self._generalized_genre = generalized_genre
        self._genre_directory = genre_directory
        self._write_metadata = write_metadata
        self._write_source_metadata = write_source_metadata
        self._safe_name = safe_name
        self._thread_factory = thread_factory
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    async def start(self, files: list[Any], playlist_name: str) -> dict[str, Any]:
        if not files or len(files) > 1000:
            raise ValueError("Choose between 1 and 1000 audio files")
        invalid = [
            upload.filename or "unnamed"
            for upload in files
            if Path(upload.filename or "").suffix.casefold() not in self.SUPPORTED
        ]
        if invalid:
            raise ValueError(f"Unsupported audio file: {invalid[0]}")
        self._require_library_online()
        batch_id = uuid.uuid4().hex
        safe_playlist = self._safe_name(playlist_name or "Local Playlist")
        staged_dir = self._staging_root / batch_id
        staged_dir.mkdir(parents=True, exist_ok=True)
        try:
            for index, upload in enumerate(files):
                name = self._safe_name(Path(upload.filename or f"Track {index + 1}").name)
                destination = staged_dir / f"{index:04d}-{name}"
                with destination.open("wb") as target:
                    shutil.copyfileobj(upload.file, target)
                await upload.close()
        except Exception:
            shutil.rmtree(staged_dir, ignore_errors=True)
            raise
        with self._lock:
            self._states[batch_id] = {
                "id": batch_id,
                "status": "processing",
                "stage": f"Staged {len(files)} audio files",
                "progress": 0,
                "playlist_name": safe_playlist,
                "total": len(files),
                "counts": {},
            }
        self._thread_factory(
            target=self.run,
            args=(batch_id, staged_dir, safe_playlist),
            daemon=True,
            name=f"local-import-{batch_id[:8]}",
        ).start()
        return {"batch_id": batch_id, "track_count": len(files), "playlist_name": safe_playlist}

    def status(self, batch_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._states.get(batch_id)
            if state is None:
                raise LocalImportNotFoundError("Local audio import not found")
            return dict(state)

    def has_active_imports(self) -> bool:
        with self._lock:
            return any(state.get("status") == "processing" for state in self._states.values())

    def clear(self) -> None:
        with self._lock:
            self._states.clear()

    def _update(self, batch_id: str, **values: Any) -> None:
        with self._lock:
            self._states[batch_id].update(values)

    def run(self, batch_id: str, staged_dir: Path, playlist_name: str) -> None:
        files = [path for path in staged_dir.rglob("*") if path.is_file()]
        results: list[dict[str, Any]] = []
        imported = skipped = failed = 0
        try:
            existing = self._repository.list_downloaded_tracks()
            known = {
                (str(track.get("artist") or "").casefold(), str(track.get("title") or "").casefold())
                for track in existing
                if Path(str(track.get("file_path") or "")).is_file()
            }
            for index, source in enumerate(files, start=1):
                self._update(
                    batch_id,
                    stage=f"Converting {source.name}",
                    progress=round(100 * (index - 1) / max(1, len(files)), 1),
                )
                try:
                    metadata = self._probe_audio(source)
                    identity = (metadata["artist"].casefold(), metadata["title"].casefold())
                    if identity in known:
                        skipped += 1
                        results.append({"filename": source.name, "status": "duplicate", **metadata})
                        continue
                    category = self._generalized_genre(metadata["genre"])
                    self._require_library_online()
                    destination_dir = self._genre_directory(category)
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    display_name = " - ".join(value for value in (metadata["artist"], metadata["title"]) if value)
                    stem = self._safe_name(display_name or source.stem)
                    destination = destination_dir / f"{stem}.wav"
                    counter = 2
                    while destination.exists():
                        destination = destination_dir / f"{stem} ({counter}).wav"
                        counter += 1
                    temporary_wav = destination.with_suffix(".importing.wav")
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-v",
                            "error",
                            "-i",
                            str(source),
                            "-vn",
                            "-c:a",
                            "pcm_s24le",
                            str(temporary_wav),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    temporary_wav.replace(destination)
                    self._write_metadata(
                        destination,
                        title=metadata["title"],
                        artist=metadata["artist"],
                        genre=category,
                        album=playlist_name,
                    )
                    source_metadata = {
                        "title": metadata["title"],
                        "artist": metadata["artist"],
                        "genre": metadata["genre"],
                        "genre_category": category,
                        "playlist_name": playlist_name,
                        "file_path": str(destination),
                        "import_source": "local-audio",
                    }
                    self._write_source_metadata(destination, source_metadata)
                    self._repository.upsert_downloaded_track(
                        title=metadata["title"],
                        artist=metadata["artist"],
                        file_path=destination,
                        genre=metadata["genre"],
                        genre_category=category,
                        duration_seconds=metadata["duration"],
                        playlist_name=playlist_name,
                    )
                    known.add(identity)
                    imported += 1
                    results.append(
                        {
                            "filename": destination.name,
                            "status": "imported",
                            "genre_category": category,
                            **metadata,
                        }
                    )
                except Exception as error:
                    failed += 1
                    results.append({"filename": source.name, "status": "failed", "error": str(error)})
            self._update(
                batch_id,
                status="complete",
                stage="Local playlist import complete",
                progress=100,
                counts={"imported": imported, "duplicates": skipped, "failed": failed},
                results=results,
            )
        except Exception as error:
            self._update(batch_id, status="failed", stage="Local import failed", error=str(error))
        finally:
            shutil.rmtree(staged_dir, ignore_errors=True)
