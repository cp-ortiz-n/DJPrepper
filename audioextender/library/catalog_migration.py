"""Reconcile downloaded source sidecars into the durable catalog."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DownloadedCatalogMigrator:
    """Own idempotent catalog discovery and its process-local checkpoint."""

    repository: Callable[[], Any]
    output_root: Path
    music_library_root: Callable[[], Path]
    catalog_genre_category: Callable[[Path, str, str], str]
    write_source_metadata: Callable[[Path, dict], Path]
    version: str = "3"
    lock: threading.Lock = field(default_factory=threading.Lock)
    _completed: bool = False

    def ensure_current(self) -> None:
        if self._completed:
            return
        with self.lock:
            if self._completed:
                return
            repository = self.repository()
            if repository.get_system_state("downloaded_catalog_migration") != self.version:
                self.migrate()
                repository.set_system_state("downloaded_catalog_migration", self.version)
            self._completed = True

    def migrate(
        self,
        *,
        incremental: bool = False,
        progress: Callable[[dict[str, int]], None] | None = None,
    ) -> dict[str, int]:
        """Catalog source records, skipping unchanged files during reconciliation."""
        repository = self.repository()
        roots = [self.output_root / "wav" / "imports", self.output_root / "wav" / "creative-commons"]
        try:
            library_root = self.music_library_root()
            roots.append(library_root)
        except ValueError:
            library_root = None
        records: list[tuple[Path, bool]] = []
        for root in roots:
            if root.exists():
                records.extend((record, True) for record in root.rglob("*.source.json"))
        if library_root is not None:
            metadata_root = library_root / ".audioextender" / "sources"
            if metadata_root.exists():
                records.extend((record, False) for record in metadata_root.glob("*.json"))
        known = repository.catalog_source_signatures() if incremental else {}
        results = {"total": len(records), "processed": 0, "updated": 0, "skipped": 0, "failed": 0}
        signatures: list[tuple[str, int, int]] = []
        for index, (source_record, legacy_record) in enumerate(records, start=1):
            try:
                stat = source_record.stat()
            except OSError:
                results["failed"] += 1
                continue
            source_key = str(source_record.resolve())
            signature = (stat.st_mtime_ns, stat.st_size)
            if incremental and known.get(source_key) == signature:
                results["skipped"] += 1
                results["processed"] = index
                if progress:
                    progress(dict(results))
                continue
            try:
                metadata = json.loads(source_record.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                results["failed"] += 1
                results["processed"] = index
                signatures.append((source_key, *signature))
                if progress:
                    progress(dict(results))
                continue
            wav_path = (
                source_record.with_name(source_record.name.removesuffix(".source.json") + ".wav")
                if legacy_record
                else Path(str(metadata.get("file_path") or ""))
            )
            if not wav_path.is_file():
                results["failed"] += 1
                results["processed"] = index
                signatures.append((source_key, *signature))
                if progress:
                    progress(dict(results))
                continue
            if repository.downloaded_track_is_excluded(wav_path):
                results["skipped"] += 1
                results["processed"] = index
                signatures.append((source_key, *signature))
                if progress:
                    progress(dict(results))
                continue
            detailed_genre = str(metadata.get("genre") or "")
            category = self.catalog_genre_category(
                wav_path,
                str(metadata.get("genre_category") or ""),
                detailed_genre,
            )
            repository.upsert_downloaded_track(
                title=str(metadata.get("title") or wav_path.stem),
                artist=str(metadata.get("artist") or ""),
                file_path=wav_path,
                genre=detailed_genre,
                genre_category=category,
                youtube_id=str(metadata.get("youtube_id") or ""),
                youtube_url=str(metadata.get("youtube_url") or ""),
                playlist_name=str(metadata.get("playlist_name") or "Legacy Imports"),
            )
            results["updated"] += 1
            results["processed"] = index
            signatures.append((source_key, *signature))
            if legacy_record and library_root is not None and wav_path.is_relative_to(library_root):
                self.write_source_metadata(wav_path, metadata)
                source_record.unlink(missing_ok=True)
            if progress:
                progress(dict(results))
        repository.upsert_catalog_source_signatures(signatures)
        return results
