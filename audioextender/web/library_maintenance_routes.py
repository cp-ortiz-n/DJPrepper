"""Downloaded-library reconciliation and integrity workflows."""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from audioextender.core.operation_feedback import operation_receipt
from audioextender.infrastructure.batch_operations import BatchContext, BatchOperationRegistry


class IntegrityRepairRequest(BaseModel):
    action: Literal["remove-missing", "catalog-uncataloged", "delete-stale-sidecars", "retag-mismatches"]
    item_ids: list[str] = Field(default_factory=list, max_length=5000)


@dataclass
class LibraryMaintenanceDependencies:
    repository: Callable[[], Any]
    music_library_root: Callable[[], Path]
    require_library_online: Callable[[], Any]
    migrate_catalog: Callable[..., dict]
    read_wav_metadata: Callable[[Path], dict]
    sync_wav_metadata: Callable[..., bool]
    probe_local_audio: Callable[[Path], dict]
    catalog_genre_category: Callable[[Path, str, str], str]
    metadata_batches: BatchOperationRegistry
    catalog_migration_lock: threading.Lock
    integrity_batches: dict[str, dict]
    integrity_lock: threading.Lock


class LibraryMaintenanceService:
    def __init__(self, dependencies: LibraryMaintenanceDependencies) -> None:
        self.dependencies = dependencies

    @property
    def repository(self) -> Any:
        return self.dependencies.repository()

    def run_catalog_reconcile(self, context: BatchContext, _items: list[object]) -> dict:
        def publish(result: dict[str, int]) -> None:
            context.check_canceled()
            context.progress(
                processed=result["processed"],
                total=result["total"],
                stage=f"Checking source records {result['processed']} of {result['total']}",
                counters={**result, "succeeded": int(result.get("updated") or 0)},
            )

        with self.dependencies.catalog_migration_lock:
            result = self.dependencies.migrate_catalog(incremental=True, progress=publish)
        return {**result, "stage": "File reconciliation complete"}

    def start_catalog_reconcile(self) -> dict:
        self.dependencies.require_library_online()
        return self.dependencies.metadata_batches.start(
            "catalog-propagation",
            [None],
            self.run_catalog_reconcile,
            stage="Indexing source records",
            counters={"updated": 0},
            requested="Reconcile source records with the downloaded-track catalog",
            written_to=[str(self.dependencies.music_library_root())],
            durability="Catalog and sidecar updates are persisted and survive restart.",
        )

    def run_integrity_scan(self, batch_id: str) -> None:
        root = self.dependencies.music_library_root()
        repository = self.repository
        repository.refresh_missing_audio_fingerprints()
        tracks = repository.list_downloaded_tracks_with_jobs()
        findings: dict[str, list[dict]] = {
            key: []
            for key in (
                "missing_files",
                "uncataloged_files",
                "duplicate_records",
                "stale_sidecars",
                "broken_analysis_links",
                "tag_mismatches",
                "unreadable_tags",
            )
        }
        catalog_paths = {str(Path(str(track["file_path"])).resolve()) for track in tracks}
        for track in tracks:
            path = Path(str(track["file_path"]))
            if not path.is_file():
                findings["missing_files"].append(
                    {
                        "id": str(track["id"]),
                        "title": track.get("title") or track.get("filename"),
                        "path": str(path),
                    }
                )
        for candidate in repository.duplicate_candidates():
            group = candidate["tracks"]
            findings["duplicate_records"].append(
                {
                    "id": str(group[0]["id"]),
                    "title": group[0].get("title"),
                    "artist": group[0].get("artist"),
                    "track_ids": [item["id"] for item in group],
                    "paths": [item["file_path"] for item in group],
                    "identities": [f"{item['recording_code']}-{item['version_code']}" for item in group],
                    "reason": candidate["reason"],
                    "confidence": candidate["confidence"],
                }
            )
        for path in root.rglob("*.wav"):
            resolved = str(path.resolve())
            if (
                ".audioextender" not in path.parts
                and resolved not in catalog_paths
                and not repository.downloaded_track_is_excluded(path)
            ):
                findings["uncataloged_files"].append({"id": resolved, "title": path.stem, "path": resolved})
        sidecar_root = root / ".audioextender" / "sources"
        if sidecar_root.exists():
            for sidecar in sidecar_root.glob("*.json"):
                try:
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                    audio_path = Path(str(data.get("file_path") or ""))
                except (OSError, ValueError):
                    audio_path = Path("")
                if not audio_path.is_file():
                    findings["stale_sidecars"].append(
                        {
                            "id": str(sidecar.resolve()),
                            "title": sidecar.name,
                            "path": str(sidecar.resolve()),
                            "audio_path": str(audio_path),
                        }
                    )
        for job in repository.list_jobs(limit=10_000):
            source = Path(str(job.get("source_path") or ""))
            try:
                managed = source.resolve().is_relative_to(root)
            except (OSError, ValueError):
                managed = False
            if managed and not source.is_file():
                findings["broken_analysis_links"].append(
                    {
                        "id": str(job["id"]),
                        "title": job.get("source_name"),
                        "path": str(source),
                        "status": job.get("status"),
                    }
                )
        total = len(tracks)
        for index, track in enumerate(tracks, start=1):
            path = Path(str(track["file_path"]))
            if path.is_file():
                try:
                    tags = self.dependencies.read_wav_metadata(path)
                    expected = {
                        "title": str(track.get("title") or "").strip(),
                        "artist": str(track.get("artist") or "").strip(),
                        "genre": str(track.get("genre_category") or "Other").strip(),
                        "album": str((track.get("playlists") or ["Imported Singles"])[0]).strip(),
                    }
                    differences = [key for key, value in expected.items() if tags.get(key, "") != value]
                    if differences:
                        findings["tag_mismatches"].append(
                            {
                                "id": str(track["id"]),
                                "title": track.get("title") or path.name,
                                "path": str(path),
                                "fields": differences,
                            }
                        )
                except Exception as error:
                    findings["unreadable_tags"].append(
                        {
                            "id": str(track["id"]),
                            "title": track.get("title") or path.name,
                            "path": str(path),
                            "error": str(error),
                        }
                    )
            with self.dependencies.integrity_lock:
                self.dependencies.integrity_batches[batch_id].update(
                    processed=index,
                    total=total,
                    progress=round(index / max(1, total) * 100),
                    stage=f"Checking WAV metadata {index} of {total}",
                )
        with self.dependencies.integrity_lock:
            finding_count = sum(len(value) for value in findings.values())
            self.dependencies.integrity_batches[batch_id].update(
                status="complete",
                stage="Integrity scan complete",
                progress=100,
                findings=findings,
                counts={key: len(value) for key, value in findings.items()},
                receipt=operation_receipt(
                    operation="library-integrity-scan",
                    requested=f"Verify {total} catalog tracks and the configured library folder",
                    requested_count=total,
                    changed="Read-only verification; no files or catalog records changed",
                    changed_count=0,
                    failures=[],
                    survives_restart=False,
                    durability=(
                        f"Found {finding_count} issues. Scan results are read-only and are recomputed after restart."
                    ),
                ),
            )

    def repair(self, request: IntegrityRepairRequest) -> dict:
        root = self.dependencies.music_library_root()
        repository = self.repository
        if request.action == "remove-missing":
            updated = sum(repository.delete_downloaded_track(int(item)) for item in request.item_ids)
            return self._repair_result(request, updated, [str(getattr(repository, "path", "catalog database"))])
        if request.action == "retag-mismatches":
            wanted = {int(item) for item in request.item_ids}
            updated = 0
            for track in repository.list_downloaded_tracks():
                if int(track["id"]) not in wanted:
                    continue
                path = Path(str(track["file_path"]))
                updated += int(
                    self.dependencies.sync_wav_metadata(
                        path,
                        title=str(track.get("title") or path.stem),
                        artist=str(track.get("artist") or ""),
                        genre=str(track.get("genre_category") or "Other"),
                        album=str((track.get("playlists") or ["Imported Singles"])[0]),
                    )
                )
            return self._repair_result(request, updated, [str(root)])
        paths = [Path(item).resolve() for item in request.item_ids]
        if any(not path.is_relative_to(root) for path in paths):
            raise HTTPException(400, "Repair target is outside the Music Library")
        if request.action == "delete-stale-sidecars":
            sidecar_root = (root / ".audioextender" / "sources").resolve()
            if any(not path.is_relative_to(sidecar_root) for path in paths):
                raise HTTPException(400, "Invalid sidecar target")
            for path in paths:
                path.unlink(missing_ok=True)
            return self._repair_result(request, len(paths), [str(sidecar_root)])
        added = 0
        for path in paths:
            if not path.is_file() or path.suffix.casefold() != ".wav":
                continue
            metadata = self.dependencies.probe_local_audio(path)
            category = self.dependencies.catalog_genre_category(path, "", str(metadata.get("genre") or ""))
            repository.upsert_downloaded_track(
                title=str(metadata.get("title") or path.stem),
                artist=str(metadata.get("artist") or ""),
                file_path=path,
                genre=str(metadata.get("genre") or ""),
                genre_category=category,
                duration_seconds=metadata.get("duration"),
                playlist_name="Recovered files",
            )
            added += 1
        return self._repair_result(request, added, [str(getattr(repository, "path", "catalog database"))])

    @staticmethod
    def _repair_result(request: IntegrityRepairRequest, updated: int, written_to: list[str]) -> dict:
        return {
            "updated": updated,
            "receipt": operation_receipt(
                operation=f"library-integrity-{request.action}",
                requested=f"Apply {request.action} to {len(request.item_ids)} findings",
                requested_count=len(request.item_ids),
                changed=f"Updated {updated} items",
                changed_count=updated,
                written_to=written_to,
                survives_restart=True,
                durability="Completed file or catalog repairs are persisted and survive restart.",
            ),
        }


def create_library_maintenance_router(
    service: LibraryMaintenanceService,
) -> APIRouter:
    router = APIRouter(prefix="/api/downloaded-library", tags=["library maintenance"])
    dependencies = service.dependencies

    @router.post("/reconcile-files", status_code=202)
    def start_catalog_reconcile() -> dict:
        return service.start_catalog_reconcile()

    @router.get("/reconcile-files/{batch_id}")
    def catalog_reconcile_status(batch_id: str) -> dict:
        try:
            return dependencies.metadata_batches.status(batch_id)
        except KeyError as error:
            raise HTTPException(404, "File reconciliation was not found") from error

    @router.post("/integrity-scan", status_code=202)
    def start_integrity_scan() -> dict:
        dependencies.require_library_online()
        batch_id = uuid.uuid4().hex
        total = len(service.repository.list_downloaded_tracks())
        with dependencies.integrity_lock:
            dependencies.integrity_batches[batch_id] = {
                "batch_id": batch_id,
                "status": "processing",
                "stage": "Indexing catalog and files",
                "progress": 0,
                "processed": 0,
                "total": total,
                "findings": {},
                "counts": {},
                "receipt": operation_receipt(
                    operation="library-integrity-scan",
                    requested=f"Verify {total} catalog tracks and the configured library folder",
                    requested_count=total,
                    changed="No changes; verification is running",
                    changed_count=0,
                    survives_restart=False,
                    durability="The read-only scan must be run again after an application restart.",
                    status="processing",
                ),
            }
        threading.Thread(
            target=service.run_integrity_scan,
            args=(batch_id,),
            daemon=True,
            name=f"integrity-scan-{batch_id[:8]}",
        ).start()
        return dict(dependencies.integrity_batches[batch_id])

    @router.get("/integrity-scan/{batch_id}")
    def integrity_scan_status(batch_id: str) -> dict:
        with dependencies.integrity_lock:
            batch = dependencies.integrity_batches.get(batch_id)
            if not batch:
                raise HTTPException(404, "Integrity scan was not found")
            return dict(batch)

    @router.post("/integrity-repair")
    def integrity_repair(request: IntegrityRepairRequest) -> dict:
        return service.repair(request)

    return router
