"""Portable, integrity-checked backups for DJ Library Studio state."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

BACKUP_FORMAT_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LibraryBackupService:
    """Create, inspect, retain, and restore application-state archives."""

    def __init__(self, database: Path, project: Path, library_root: Path) -> None:
        self.database = database
        self.project = project
        self.library_root = library_root

    def sources(self, include_cache: bool = False) -> list[tuple[Path, str]]:
        items = [
            (self.project / "track_overrides.json", "state/track_overrides.json"),
            (
                self.project / "output/reports/processing_report.json",
                "state/processing_report.json",
            ),
            (self.project / "output/reports/web_presets.json", "state/web_presets.json"),
            (
                self.project / "output/reports/set_builder_catalog.json",
                "state/set_builder_catalog.json",
            ),
        ]
        for root, prefix in (
            (self.library_root / ".audioextender", "library/.audioextender"),
            (self.library_root / "_Playlist", "library/_Playlist"),
        ):
            if root.is_dir():
                items.extend(
                    (path, f"{prefix}/{path.relative_to(root).as_posix()}")
                    for path in root.rglob("*")
                    if path.is_file() and path.name != ".DS_Store" and "backups" not in path.parts
                )
        if include_cache:
            cache = self.project / "cache"
            if cache.is_dir():
                items.extend(
                    (path, f"cache/{path.relative_to(cache).as_posix()}")
                    for path in cache.rglob("*")
                    if path.is_file()
                )
        return [(path, name) for path, name in items if path.is_file()]

    def create(self, destination: Path, *, include_cache: bool, retention: int) -> dict:
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        archive = destination / f"AudioExtender-Backup-{stamp}.aexbackup"
        with tempfile.TemporaryDirectory(prefix="audioextender-backup-") as temporary:
            snapshot = Path(temporary) / "audioextender.sqlite3"
            with (
                closing(sqlite3.connect(self.database)) as source,
                closing(sqlite3.connect(snapshot)) as target,
            ):
                source.backup(target)
                target.commit()
            files = [(snapshot, "state/audioextender.sqlite3"), *self.sources(include_cache)]
            manifest_files = []
            with zipfile.ZipFile(
                archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as bundle:
                for path, name in files:
                    manifest_files.append(
                        {"path": name, "size": path.stat().st_size, "sha256": _sha256(path)}
                    )
                    bundle.write(path, name)
                track_count = 0
                with closing(sqlite3.connect(snapshot)) as connection:
                    track_count = int(
                        connection.execute("SELECT COUNT(*) FROM downloaded_tracks").fetchone()[0]
                    )
                manifest = {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "created_at": _now(),
                    "library_path": str(self.library_root),
                    "track_count": track_count,
                    "includes_analysis_cache": include_cache,
                    "files": manifest_files,
                }
                bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
        self._apply_retention(destination, retention)
        return {
            **manifest,
            "filename": archive.name,
            "path": str(archive),
            "size": archive.stat().st_size,
        }

    def inspect(self, archive: Path) -> dict:
        try:
            with zipfile.ZipFile(archive) as bundle:
                manifest = json.loads(bundle.read("manifest.json"))
                if int(manifest.get("format_version", 0)) != BACKUP_FORMAT_VERSION:
                    raise ValueError("This backup format is not supported")
                declared = {str(item["path"]): item for item in manifest.get("files", [])}
                if "state/audioextender.sqlite3" not in declared:
                    raise ValueError("The backup does not contain its catalog database")
                for name, item in declared.items():
                    info = bundle.getinfo(name)
                    if info.file_size != int(item["size"]):
                        raise ValueError(f"Size validation failed for {name}")
                    digest = hashlib.sha256(bundle.read(name)).hexdigest()
                    if digest != item["sha256"]:
                        raise ValueError(f"Integrity validation failed for {name}")
        except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
            raise ValueError("The selected file is not a valid AudioExtender backup") from error
        return {
            **manifest,
            "filename": archive.name,
            "size": archive.stat().st_size,
            "file_count": len(manifest.get("files", [])),
            "valid": True,
        }

    def describe(self, archive: Path) -> dict:
        """Read display metadata without rehashing every archived sidecar."""
        try:
            with zipfile.ZipFile(archive) as bundle:
                manifest = json.loads(bundle.read("manifest.json"))
            if int(manifest.get("format_version", 0)) != BACKUP_FORMAT_VERSION:
                raise ValueError("Unsupported backup format")
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
            raise ValueError("Invalid backup") from error
        return {
            **manifest,
            "filename": archive.name,
            "size": archive.stat().st_size,
            "file_count": len(manifest.get("files", [])),
            "valid": True,
        }

    def restore(self, archive: Path, pre_restore_destination: Path) -> dict:
        manifest = self.inspect(archive)
        pre_restore = self.create(pre_restore_destination, include_cache=False, retention=10)
        with tempfile.TemporaryDirectory(prefix="audioextender-restore-") as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(archive) as bundle:
                for item in manifest["files"]:
                    name = str(item["path"])
                    target = (staging / name).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise ValueError("The backup contains an unsafe path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(bundle.read(name))
            restored_database = staging / "state/audioextender.sqlite3"
            with (
                closing(sqlite3.connect(restored_database)) as source_connection,
                closing(sqlite3.connect(self.database)) as target_connection,
            ):
                source_connection.backup(target_connection)
                target_connection.commit()
            mapping = {
                "state/track_overrides.json": self.project / "track_overrides.json",
                "state/processing_report.json": self.project
                / "output/reports/processing_report.json",
                "state/web_presets.json": self.project / "output/reports/web_presets.json",
                "state/set_builder_catalog.json": self.project
                / "output/reports/set_builder_catalog.json",
            }
            for source_name, destination in mapping.items():
                source_path = staging / source_name
                if source_path.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source_path, destination)
            self._restore_tree(
                staging / "library/.audioextender", self.library_root / ".audioextender"
            )
            self._restore_tree(staging / "library/_Playlist", self.library_root / "_Playlist")
            self._restore_tree(staging / "cache", self.project / "cache")
        return {"restored": True, "manifest": manifest, "pre_restore_backup": pre_restore}

    @staticmethod
    def _restore_tree(source: Path, destination: Path) -> None:
        if not source.is_dir():
            return
        destination.mkdir(parents=True, exist_ok=True)
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    @staticmethod
    def _apply_retention(destination: Path, retention: int) -> None:
        backups = sorted(
            destination.glob("AudioExtender-Backup-*.aexbackup"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for expired in backups[max(1, retention) :]:
            expired.unlink(missing_ok=True)
