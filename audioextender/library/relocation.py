"""Safe, recoverable relocation of the managed music library."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RelocationRepository(Protocol):
    path: Path
    def list_downloaded_tracks(self) -> list[dict]: ...
    def relocate_library_paths(self, old_root: Path, new_root: Path) -> dict[str, int]: ...


class LibraryRelocationPlanner:
    def __init__(self, repository: RelocationRepository) -> None:
        self.repository = repository

    def plan(self, source: Path, destination: Path, mode: str, verification: str) -> dict:
        source, destination = source.resolve(), destination.expanduser().resolve()
        if mode not in {"copy", "move", "relink"}:
            raise ValueError("Mode must be copy, move, or relink")
        if verification not in {"fast", "full"}:
            raise ValueError("Verification must be fast or full")
        if source == destination:
            raise ValueError("Choose a different destination")
        if source in destination.parents or destination in source.parents:
            raise ValueError("The destination cannot be inside the current library")
        if mode != "relink" and not source.is_dir():
            raise ValueError("The current music library is unavailable")
        if mode == "relink" and not destination.is_dir():
            raise ValueError("The relocated library folder was not found")
        if mode != "relink" and destination.exists() and any(destination.iterdir()):
            raise ValueError("The destination folder must be empty or not yet exist")
        files = [path for path in source.rglob("*") if path.is_file()] if source.is_dir() else []
        total_bytes = sum(path.stat().st_size for path in files)
        tracks = self.repository.list_downloaded_tracks()
        managed = [track for track in tracks if self._relative(Path(track["file_path"]), source) is not None]
        missing = [track for track in managed if not Path(track["file_path"]).is_file()]
        if mode != "relink":
            probe = destination.parent if destination.parent.exists() else source.parent
            free = shutil.disk_usage(probe).free
            if free < total_bytes:
                raise ValueError("The destination does not have enough free space")
        else:
            absent = [track for track in managed if not (destination / self._relative(Path(track["file_path"]), source)).is_file()]
            if absent:
                raise ValueError(f"The relocated folder is missing {len(absent)} cataloged track(s)")
        return {
            "source": str(source), "destination": str(destination), "mode": mode,
            "verification": verification, "file_count": len(files), "track_count": len(managed),
            "missing_source_tracks": len(missing), "total_bytes": total_bytes,
        }

    @staticmethod
    def _relative(path: Path, root: Path) -> Path | None:
        try:
            return path.resolve().relative_to(root)
        except (OSError, ValueError):
            return None


class LibraryFileTransferService:
    def copy(self, source: Path, staging: Path, update: Callable[[int, int, str], None], canceled: Callable[[], bool]) -> None:
        files = [path for path in source.rglob("*") if path.is_file()]
        staging.mkdir(parents=True, exist_ok=True)
        for index, path in enumerate(files, 1):
            if canceled():
                raise InterruptedError("Relocation canceled")
            relative = path.relative_to(source)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.stat().st_size != path.stat().st_size:
                shutil.copy2(path, target)
            update(index, len(files), f"Copying {relative}")


class LibraryRelocationVerifier:
    def verify(self, source: Path, destination: Path, level: str, update: Callable[[int, int, str], None], canceled: Callable[[], bool]) -> None:
        files = [path for path in source.rglob("*") if path.is_file()]
        for index, source_file in enumerate(files, 1):
            if canceled():
                raise InterruptedError("Relocation canceled")
            relative = source_file.relative_to(source)
            target = destination / relative
            if not target.is_file() or target.stat().st_size != source_file.stat().st_size:
                raise ValueError(f"Verification failed for {relative}")
            if level == "full" and self._hash(source_file) != self._hash(target):
                raise ValueError(f"Content verification failed for {relative}")
            update(index, len(files), f"Verifying {relative}")

    def verify_relink(self, tracks: list[dict], source: Path, destination: Path, update: Callable[[int, int, str], None], canceled: Callable[[], bool]) -> None:
        managed = []
        for track in tracks:
            try:
                relative = Path(str(track["file_path"])).resolve().relative_to(source)
            except (OSError, ValueError):
                continue
            managed.append((track, relative))
        for index, (_track, relative) in enumerate(managed, 1):
            if canceled():
                raise InterruptedError("Relocation canceled")
            if not (destination / relative).is_file():
                raise ValueError(f"Relocated track was not found: {relative}")
            update(index, len(managed), f"Verifying {relative}")

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class LibraryMetadataRelinker:
    def __init__(self, repository: RelocationRepository) -> None:
        self.repository = repository

    def rebuild(self, destination: Path) -> None:
        source_root = destination / ".audioextender" / "sources"
        source_root.mkdir(parents=True, exist_ok=True)
        for existing in source_root.glob("*.json"):
            try:
                existing.unlink()
            except FileNotFoundError:
                # FAT/exFAT AppleDouble sidecars can vanish alongside their
                # companion file while the directory is being enumerated.
                continue
        playlists: dict[str, list[str]] = {}
        for track in self.repository.list_downloaded_tracks():
            path = Path(str(track["file_path"]))
            try:
                path.relative_to(destination)
            except ValueError:
                continue
            payload = {
                "title": track.get("title", ""), "artist": track.get("artist", ""),
                "genre": track.get("genre", ""), "genre_category": track.get("genre_category", "Other"),
                "youtube_id": track.get("youtube_id", ""), "youtube_url": track.get("youtube_url", ""),
                "artwork_url": track.get("artwork_url", ""), "file_path": str(path),
                "playlist_name": (track.get("playlists") or ["Imported Singles"])[0],
            }
            key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
            (source_root / f"{key}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            for playlist in track.get("playlists") or []:
                playlists.setdefault(str(playlist), []).append(str(path))
        playlist_root = destination / "_Playlist"
        playlist_root.mkdir(exist_ok=True)
        for playlist, paths in playlists.items():
            safe = "".join(char if char.isalnum() or char in " -_" else "_" for char in playlist).strip() or "Playlist"
            (playlist_root / f"{safe}.m3u8").write_text("#EXTM3U\n" + "\n".join(paths) + "\n", encoding="utf-8")
        identity = destination / ".audioextender" / "library.json"
        if not identity.exists():
            identity.write_text(json.dumps({"library_id": uuid.uuid4().hex, "created_at": _now()}, indent=2), encoding="utf-8")


class LibraryRelocationCoordinator:
    def __init__(self, repository: RelocationRepository, manifest_path: Path) -> None:
        self.repository = repository
        self.manifest_path = manifest_path
        self.planner = LibraryRelocationPlanner(repository)
        self.transfer = LibraryFileTransferService()
        self.verifier = LibraryRelocationVerifier()
        self.metadata = LibraryMetadataRelinker(repository)
        self._lock = threading.Lock()
        self._state: dict = self._load()
        if self._state.get("status") == "processing":
            self._state.update(status="failed", stage="Interrupted safely", error="The app stopped during relocation. Start again to resume the copy.")
            self._save()
        self._cancel = threading.Event()

    def _load(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def prepare(self, source: Path, destination: Path, mode: str, verification: str) -> dict:
        plan = self.planner.plan(source, destination, mode, verification)
        with self._lock:
            self._state = {"id": uuid.uuid4().hex, "status": "planned", "stage": "Ready", "progress": 0, "created_at": _now(), **plan}
            self._save()
            return dict(self._state)

    def start(self) -> dict:
        with self._lock:
            if self._state.get("status") not in {"planned", "failed", "canceled"}:
                raise ValueError("No relocation plan is ready")
            self._state.update(status="processing", stage="Starting", progress=0, error="")
            self._cancel.clear()
            self._save()
            snapshot = dict(self._state)
        threading.Thread(target=self._run, daemon=True, name="library-relocation").start()
        return snapshot

    def cancel(self) -> dict:
        self._cancel.set()
        return self.status()

    def reset(self) -> dict:
        """Discard a terminal plan so Settings returns to a clean form."""
        with self._lock:
            if self._state.get("status") == "processing":
                raise ValueError("Cancel the active relocation before resetting it")
            self._state = {}
            try:
                self.manifest_path.unlink()
            except FileNotFoundError:
                pass
            return {}

    def rollback(self) -> dict:
        state = self.status()
        backup = Path(str(state.get("database_backup") or ""))
        if state.get("status") != "complete" or not backup.is_file():
            raise ValueError("No completed relocation backup is available")
        with self._lock:
            with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(self.repository.path)) as target:
                source.backup(target)
                target.commit()
            self._state.update(status="rolled_back", stage="Catalog restored to the original library", progress=100, rolled_back_at=_now())
            self._save()
            return dict(self._state)

    def _update(self, stage: str, processed: int = 0, total: int = 0) -> None:
        with self._lock:
            self._state.update(stage=stage, processed=processed, total=total, progress=round(processed / max(1, total) * 100) if total else self._state.get("progress", 0))
            self._save()

    def _backup_database(self) -> Path:
        backup = self.repository.path.with_name(f"{self.repository.path.stem}.before-relocation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3")
        with closing(sqlite3.connect(self.repository.path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            target.commit()
        return backup

    def _run(self) -> None:
        state = self.status()
        source = Path(state["source"])
        destination = Path(state["destination"])
        staging = destination.with_name(destination.name + ".relocating")
        try:
            active = destination
            if state["mode"] != "relink":
                self._update("Copying library")
                self.transfer.copy(source, staging, lambda i,n,s:self._update(s,i,n), self._cancel.is_set)
                self._update("Verifying copy")
                self.verifier.verify(source, staging, state["verification"], lambda i,n,s:self._update(s,i,n), self._cancel.is_set)
                if destination.exists():
                    destination.rmdir()
                staging.rename(destination)
                active = destination
            else:
                self._update("Verifying relocated library")
                self.verifier.verify_relink(self.repository.list_downloaded_tracks(), source, destination, lambda i,n,s:self._update(s,i,n), self._cancel.is_set)
            if state["mode"] in {"move", "relink"}:
                backup = self._backup_database()
                self._update("Relinking catalog and analysis")
                counts = self.repository.relocate_library_paths(source, active)
                self._update("Rebuilding metadata and playlists")
                self.metadata.rebuild(active)
            else:
                backup = None
                counts = {}
            with self._lock:
                self._state.update(status="complete", stage="Relocation complete", progress=100, completed_at=_now(), database_backup=str(backup or ""), updated=counts, original_retained=True)
                self._save()
        except InterruptedError as error:
            with self._lock:
                self._state.update(status="canceled", stage="Canceled safely", error=str(error))
                self._save()
        except Exception as error:
            with self._lock:
                self._state.update(status="failed", stage="Relocation failed", error=str(error))
                self._save()
