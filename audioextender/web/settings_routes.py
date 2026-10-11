"""Settings, storage, relocation, backup, and application-cleanup routes."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audioextender.core.operation_feedback import operation_receipt
from audioextender.infrastructure.cache import AnalysisCache
from audioextender.library.backup import LibraryBackupService
from settings import (
    DEFAULT_CANDIDATE_COUNT,
    INTRO_SEARCH_SECONDS,
    MAXIMUM_BASS_RESET_RISK,
    MAXIMUM_BUILDUP_RISK,
    MAXIMUM_VOCAL_BOUNDARY_RISK,
    MAXIMUM_VOCAL_COVERAGE,
    MINIMUM_CROSSFADE_MS,
    MINIMUM_STEM_CONSTRUCTION_RELIABILITY,
    OUTRO_SEARCH_SECONDS,
)


class WebSettings(BaseModel):
    music_library_path: str = str(Path.home() / "Music" / "AudioExtender Library")
    preset: str = "auto"
    intro_bars: int = 8
    outro_bars: int = 8
    use_stems: bool = False
    auto_bars: bool = True
    minimum_intro_loop_quality: float = Field(65.0, ge=0, le=100)
    minimum_outro_loop_quality: float = Field(65.0, ge=0, le=100)
    pcm_bits: int = 24
    preview_seconds: float = Field(8.0, gt=0, le=60)
    export_cues: bool = True
    maximum_repetitions: int = Field(8, ge=1, le=8)
    crossfade_ms: float = Field(MINIMUM_CROSSFADE_MS, ge=1, le=100)
    candidate_count: int = Field(DEFAULT_CANDIDATE_COUNT, ge=1, le=8)
    intro_search_seconds: float = Field(INTRO_SEARCH_SECONDS, ge=15, le=600)
    outro_search_seconds: float = Field(OUTRO_SEARCH_SECONDS, ge=15, le=600)
    maximum_vocal_coverage_percent: float = Field(MAXIMUM_VOCAL_COVERAGE * 100, ge=0, le=100)
    maximum_vocal_boundary_risk_percent: float = Field(MAXIMUM_VOCAL_BOUNDARY_RISK * 100, ge=0, le=100)
    maximum_buildup_risk_percent: float = Field(MAXIMUM_BUILDUP_RISK * 100, ge=0, le=100)
    maximum_bass_reset_risk_percent: float = Field(MAXIMUM_BASS_RESET_RISK * 100, ge=0, le=100)
    minimum_stem_reliability_percent: float = Field(MINIMUM_STEM_CONSTRUCTION_RELIABILITY * 100, ge=0, le=100)


class LibraryRelocationRequest(BaseModel):
    destination: str = Field(min_length=1)
    mode: str = Field(pattern=r"^(copy|move|relink)$")
    verification: str = Field(default="fast", pattern=r"^(fast|full)$")


class BackupCreateRequest(BaseModel):
    include_analysis_cache: bool = False
    retention: int = Field(default=5, ge=1, le=25)


class BackupRestoreRequest(BaseModel):
    token: str = Field(min_length=1)
    confirmation: str


class StorageCleanupRequest(BaseModel):
    target: Literal["stale-cache", "orphaned-output"]


class ApplicationCleanupRequest(BaseModel):
    confirmation: str


@dataclass(slots=True)
class SettingsRouteDependencies:
    repository: Callable[[], Any]
    job_service: Any
    relocation: Any
    import_services: Sequence[Any]
    project: Path
    input_root: Path
    output_root: Path
    database: Path
    overrides_path: Path
    presets_path: Path
    backup_root: Path
    storage_snapshot: Path
    cache_folder_name: str
    supported_bar_counts: Sequence[int]
    defaults: dict[str, Any]
    available_presets: Callable[[], dict[str, Any]]
    effective_settings: Callable[[], dict[str, Any]]
    music_library_root: Callable[[], Path]
    library_location_summary: Callable[[], dict[str, Any]]
    source_metadata_path: Callable[[Path], Path]
    refresh_wav_tag_audit: Callable[[], Any]
    metadata_batches: Any
    library_status_cache: dict[str, Any]
    library_status_lock: Any
    storage_inventory_cache: dict[str, Any]
    storage_inventory_lock: Any
    report_cache: dict[str, Any]
    catalog_cache: dict[str, Any]
    pending_restores: dict[str, Path]


class SettingsRouteService:
    """Keep settings-related filesystem and persistence policy out of FastAPI composition."""

    def __init__(self, dependencies: SettingsRouteDependencies) -> None:
        self.dependencies = dependencies

    @staticmethod
    def _path_size(path: Path) -> int:
        try:
            return path.stat().st_size if path.is_file() else 0
        except OSError:
            return 0

    def library_status(self, refresh: bool = False) -> dict[str, Any]:
        deps = self.dependencies
        now = perf_counter()
        with deps.library_status_lock:
            root = deps.music_library_root()
            cached = deps.library_status_cache.get("payload")
            mount_changed = cached is not None and bool(cached.get("online")) != root.is_dir()
            if (
                not refresh
                and cached is not None
                and not mount_changed
                and now < float(deps.library_status_cache["expires_at"])
            ):
                return dict(cached)
            identity = root / ".audioextender" / "library.json"
            try:
                library_id = str(json.loads(identity.read_text(encoding="utf-8")).get("library_id") or "")
            except (OSError, ValueError):
                library_id = ""
            scan_started = perf_counter()
            tracks = deps.repository().list_downloaded_tracks()
            available_paths: set[Path] = set()
            song_bytes = 0
            for track in tracks:
                path = Path(str(track.get("file_path") or ""))
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if path.is_file():
                    available_paths.add(path)
                    song_bytes += stat.st_size
            total_bytes = 0
            file_count = 0
            pending = [root]
            while pending:
                directory = pending.pop()
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    pending.append(Path(entry.path))
                                elif entry.is_file(follow_symlinks=False):
                                    total_bytes += entry.stat(follow_symlinks=False).st_size
                                    file_count += 1
                            except OSError:
                                continue
                except OSError:
                    continue
            try:
                disk = shutil.disk_usage(root if root.exists() else root.parent)
                free_bytes, capacity_bytes = disk.free, disk.total
            except OSError:
                free_bytes = capacity_bytes = 0
            payload = {
                "path": str(root),
                "online": root.is_dir(),
                "library_id": library_id,
                "cataloged_tracks": len(tracks),
                "available_tracks": len(available_paths),
                "offline_tracks": len(tracks) - len(available_paths),
                "song_bytes": song_bytes,
                "supporting_bytes": max(0, total_bytes - song_bytes),
                "total_bytes": total_bytes,
                "file_count": file_count,
                "free_bytes": free_bytes,
                "capacity_bytes": capacity_bytes,
                "audio_quality": deps.repository().audio_quality_summary(),
                "location_integrity": deps.library_location_summary(),
                "storage_scan_ms": round((perf_counter() - scan_started) * 1000, 1),
            }
            deps.library_status_cache.update(payload=payload, expires_at=now + 60.0)
            return payload

    def library_health(self, *, refresh: bool = False) -> dict[str, Any]:
        deps = self.dependencies
        status = self.library_status(refresh=refresh)
        storage = self.public_inventory(self.storage_inventory(refresh=refresh))
        active = []
        failed_operations: list[dict[str, Any]] = []
        for kind in ("wav-tags", "artwork", "genre-rescan", "catalog-propagation"):
            batch = deps.metadata_batches.latest(kind)
            if not batch:
                continue
            if batch.get("status") in {"pending", "processing", "canceling"}:
                active.append(
                    {
                        "kind": kind,
                        "batch_id": batch.get("batch_id"),
                        "status": batch.get("status"),
                        "remaining": max(
                            0,
                            int(batch.get("total") or 0) - int(batch.get("processed") or 0),
                        ),
                    }
                )
            if kind not in {"wav-tags", "artwork"}:
                continue
            errors = list(batch.get("errors") or [])
            if kind == "wav-tags":
                errors = [item for item in errors if not item.get("path") or not Path(str(item["path"])).is_file()]
            if errors:
                failed_operations.append(
                    {
                        "kind": kind,
                        "batch_id": batch.get("batch_id"),
                        "count": len(errors),
                        "errors": errors[:10],
                    }
                )
        location = status.get("location_integrity") or {}
        missing = int(status.get("offline_tracks") or 0)
        outside = int(location.get("outside_count") or 0)
        pending = sum(int(item["remaining"]) for item in active)
        failed = sum(int(item["count"]) for item in failed_operations)
        return {
            "configured_folder": status.get("path"),
            "online": bool(status.get("online")),
            "connection": "connected" if status.get("online") else "disconnected",
            "cataloged_tracks": int(status.get("cataloged_tracks") or 0),
            "available_tracks": int(status.get("available_tracks") or 0),
            "outside_folder": outside,
            "missing_files": missing,
            "pending_metadata_writes": pending,
            "active_operations": active,
            "failed_metadata_operations": failed,
            "failed_operations": failed_operations,
            "storage": {
                "song_bytes": int(status.get("song_bytes") or 0),
                "supporting_bytes": int(status.get("supporting_bytes") or 0),
                "total_bytes": int(status.get("total_bytes") or 0),
                "free_bytes": int(status.get("free_bytes") or 0),
                "capacity_bytes": int(status.get("capacity_bytes") or 0),
                "reclaimable_bytes": int(storage.get("reclaimable_bytes") or 0),
            },
            "audio_quality": status.get("audio_quality") or {},
            "verified": bool(status.get("online")) and not missing,
        }

    def verify_library(self) -> dict[str, Any]:
        deps = self.dependencies
        root = deps.music_library_root()
        if not root.is_dir():
            raise HTTPException(409, f"Connect the configured library drive first: {root}")
        deps.repository().refresh_missing_audio_fingerprints()
        deps.refresh_wav_tag_audit()
        with deps.library_status_lock:
            deps.library_status_cache.update(payload=None, expires_at=0.0)
        with deps.storage_inventory_lock:
            deps.storage_inventory_cache.update(payload=None, expires_at=0.0)
        deps.catalog_cache.clear()
        health = self.library_health(refresh=True)
        return {**health, "verified_at": datetime.now(timezone.utc).isoformat()}

    def _inventory_signature(self) -> list[list[object]]:
        deps = self.dependencies
        paths = [
            deps.database,
            deps.project / deps.cache_folder_name,
            deps.output_root / "extended",
            deps.output_root / "previews",
            deps.output_root / "versions",
        ]
        signature: list[list[object]] = []
        for path in paths:
            try:
                stat = path.stat()
                signature.append([str(path.resolve()), stat.st_mtime_ns, stat.st_size])
            except OSError:
                signature.append([str(path.resolve()), 0, 0])
        return signature

    def _saved_inventory(self, signature: list[list[object]]) -> dict[str, Any] | None:
        try:
            saved = json.loads(self.dependencies.storage_snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        payload = saved.get("payload")
        return dict(payload) if saved.get("signature") == signature and isinstance(payload, dict) else None

    def storage_inventory(self, refresh: bool = False) -> dict[str, Any]:
        deps = self.dependencies
        now = perf_counter()
        with deps.storage_inventory_lock:
            cached = deps.storage_inventory_cache.get("payload")
            if not refresh and cached is not None and now < float(deps.storage_inventory_cache["expires_at"]):
                return dict(cached)
        signature = self._inventory_signature()
        if not refresh and (saved := self._saved_inventory(signature)) is not None:
            with deps.storage_inventory_lock:
                deps.storage_inventory_cache.update(payload=saved, expires_at=now + 120.0)
            return saved
        cache_root = (deps.project / deps.cache_folder_name).resolve()
        cache = AnalysisCache(cache_root, enabled=False)
        retained_cache: set[Path] = set()
        referenced_outputs: set[Path] = set()
        for job in deps.repository().list_storage_job_references():
            for field in (
                "source_path",
                "wav_path",
                "extended_path",
                "intro_preview_path",
                "outro_preview_path",
                "cue_sheet_path",
                "rekordbox_path",
            ):
                if value := str(job.get(field) or "").strip():
                    referenced_outputs.add(Path(value).expanduser().resolve())
            source = Path(str(job.get("source_path") or ""))
            if source.is_file():
                try:
                    retained_cache.update(cache.processing_paths(source, deps.job_service.config_for(job)))
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            for field in ("wav_path", "extended_path"):
                audio = Path(str(job.get(field) or ""))
                if audio.is_file():
                    try:
                        retained_cache.add(cache.waveform_path(audio))
                    except OSError:
                        pass
        for track in deps.repository().list_downloaded_tracks():
            for field in ("file_path", "artwork_path"):
                if value := str(track.get(field) or "").strip():
                    referenced_outputs.add(Path(value).expanduser().resolve())
        cache_files = {
            path.resolve()
            for path in cache_root.glob("*")
            if path.is_file() and (path.suffix == ".npz" or path.name.endswith((".instrumental.wav", ".drums.wav")))
        }
        stale_cache = sorted(cache_files - retained_cache)
        generated: set[Path] = set()
        for directory in (
            deps.output_root / "extended",
            deps.output_root / "previews",
            deps.output_root / "versions",
        ):
            if directory.is_dir():
                generated.update(path.resolve() for path in directory.rglob("*") if path.is_file())
        generated.update(path.resolve() for path in deps.output_root.glob("*.wav") if path.is_file())
        orphaned = sorted(generated - referenced_outputs)
        stale_bytes = sum(self._path_size(path) for path in stale_cache)
        orphaned_bytes = sum(self._path_size(path) for path in orphaned)
        payload = {
            "analysis_cache_bytes": sum(self._path_size(path) for path in cache_files),
            "analysis_cache_files": len(cache_files),
            "stale_cache_bytes": stale_bytes,
            "stale_cache_files": len(stale_cache),
            "generated_output_bytes": sum(self._path_size(path) for path in generated),
            "generated_output_files": len(generated),
            "orphaned_output_bytes": orphaned_bytes,
            "orphaned_output_files": len(orphaned),
            "reclaimable_bytes": stale_bytes + orphaned_bytes,
            "_stale_cache": [str(path) for path in stale_cache],
            "_orphaned_outputs": [str(path) for path in orphaned],
        }
        with deps.storage_inventory_lock:
            deps.storage_inventory_cache.update(payload=payload, expires_at=now + 120.0)
        try:
            deps.storage_snapshot.parent.mkdir(parents=True, exist_ok=True)
            temporary = deps.storage_snapshot.with_suffix(".tmp")
            temporary.write_text(json.dumps({"signature": signature, "payload": payload}), encoding="utf-8")
            temporary.replace(deps.storage_snapshot)
        except OSError:
            pass
        return dict(payload)

    @staticmethod
    def public_inventory(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if not key.startswith("_")}

    def backup_service(self) -> LibraryBackupService:
        deps = self.dependencies
        return LibraryBackupService(deps.database, deps.project, deps.music_library_root())

    @staticmethod
    def public_backup(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key not in {"files", "path"}}

    @staticmethod
    def remove_managed_path(path: Path, project: Path) -> int:
        path.resolve().relative_to(project.resolve())
        if not path.exists() and not path.is_symlink():
            return 0
        count = (
            1
            if path.is_file() or path.is_symlink()
            else sum(1 for child in path.rglob("*") if child.is_file() or child.is_symlink())
        )
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        return count


def create_settings_router(deps: SettingsRouteDependencies) -> APIRouter:
    router = APIRouter()
    service = SettingsRouteService(deps)

    @router.get("/api/config")
    def config() -> dict:
        presets = deps.available_presets()
        return {
            "presets": ["auto", *presets.keys()],
            "preset_details": {name: preset.__dict__ for name, preset in presets.items()},
            "bar_counts": list(deps.supported_bar_counts),
            "defaults": deps.defaults,
            "effective": deps.effective_settings(),
            "overrides": deps.repository().get_settings(),
        }

    @router.put("/api/settings")
    def save_settings(settings: WebSettings) -> dict:
        before = deps.effective_settings()
        values = settings.model_dump()
        try:
            root = Path(values["music_library_path"].strip()).expanduser()
            if not root.is_absolute():
                raise ValueError
            values["music_library_path"] = str(root.resolve())
        except (OSError, ValueError):
            raise HTTPException(400, "Music Library Location must be an absolute path") from None
        if values["preset"] != "auto" and values["preset"] not in deps.available_presets():
            raise HTTPException(400, "Unknown preset")
        if (
            values["intro_bars"] not in deps.supported_bar_counts
            or values["outro_bars"] not in deps.supported_bar_counts
        ):
            raise HTTPException(400, "Unsupported bar count")
        if values["pcm_bits"] not in (16, 24):
            raise HTTPException(400, "PCM depth must be 16 or 24")
        overrides = {key: value for key, value in values.items() if value != deps.defaults[key]}
        deps.repository().replace_settings(overrides)
        deps.repository().set_system_state("music_library_path", values["music_library_path"])
        with deps.library_status_lock:
            deps.library_status_cache.update(payload=None, expires_at=0.0)
        if Path(values["music_library_path"]).is_dir():
            deps.refresh_wav_tag_audit()
        effective = deps.effective_settings()
        changed_keys = [key for key, value in effective.items() if before.get(key) != value]
        return {
            "defaults": deps.defaults,
            "effective": effective,
            "overrides": overrides,
            "receipt": operation_receipt(
                operation="save-settings",
                requested=f"Save {len(values)} application settings",
                requested_count=len(values),
                changed=(
                    f"Changed {len(changed_keys)} setting{'s' if len(changed_keys) != 1 else ''}: "
                    + (", ".join(changed_keys) if changed_keys else "none")
                ),
                changed_count=len(changed_keys),
                written_to=[str(getattr(deps.repository(), "path", deps.database))],
                survives_restart=True,
                durability="Saved in the application database and loaded again after restart.",
            ),
        }

    @router.delete("/api/settings")
    def reset_settings() -> dict:
        before = deps.effective_settings()
        deps.repository().replace_settings({})
        with deps.library_status_lock:
            deps.library_status_cache.update(payload=None, expires_at=0.0)
        effective = deps.effective_settings()
        changed = sum(before.get(key) != value for key, value in effective.items())
        return {
            "defaults": deps.defaults,
            "effective": effective,
            "overrides": {},
            "receipt": operation_receipt(
                operation="reset-settings",
                requested="Restore application defaults",
                requested_count=len(deps.defaults),
                changed=f"Restored {changed} setting{'s' if changed != 1 else ''}",
                changed_count=changed,
                written_to=[str(getattr(deps.repository(), "path", deps.database))],
                survives_restart=True,
                durability="Default settings are persisted and remain active after restart.",
            ),
        }

    router.add_api_route("/api/settings/library-status", service.library_status, methods=["GET"])

    @router.get("/api/settings/library-health")
    def library_health() -> dict:
        return service.library_health()

    @router.post("/api/settings/library-health/verify")
    def verify_library() -> dict:
        return service.verify_library()

    @router.get("/api/settings/storage")
    def settings_storage() -> dict:
        return service.public_inventory(service.storage_inventory())

    @router.post("/api/settings/storage/cleanup")
    def cleanup_storage(request: StorageCleanupRequest) -> dict:
        active = [
            job
            for job in deps.repository().list_jobs(limit=10_000)
            if job.get("status") in {"queued", "processing", "paused"}
        ]
        if active:
            raise HTTPException(409, "Finish or cancel active analysis jobs before cleaning storage")
        inventory = service.storage_inventory(refresh=True)
        key = "_stale_cache" if request.target == "stale-cache" else "_orphaned_outputs"
        removed_files = removed_bytes = 0
        for value in inventory[key]:
            path = Path(value)
            try:
                removed_bytes += path.stat().st_size
                path.unlink()
                removed_files += 1
            except FileNotFoundError:
                continue
            except OSError as error:
                raise HTTPException(500, f"Could not remove {path.name}: {error}") from error
        with deps.storage_inventory_lock:
            deps.storage_inventory_cache.update(payload=None, expires_at=0.0)
        return {
            "removed_files": removed_files,
            "removed_bytes": removed_bytes,
            "storage": service.public_inventory(service.storage_inventory(refresh=True)),
        }

    @router.post("/api/settings/library-relocation/plan")
    def plan_relocation(request: LibraryRelocationRequest) -> dict:
        try:
            destination = Path(request.destination).expanduser()
            if not destination.is_absolute():
                raise ValueError("The destination must be an absolute path")
            return deps.relocation.prepare(deps.music_library_root(), destination, request.mode, request.verification)
        except (OSError, ValueError) as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/api/settings/library-relocation/start", status_code=202)
    def start_relocation() -> dict:
        try:
            return deps.relocation.start()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    router.add_api_route("/api/settings/library-relocation", deps.relocation.status, methods=["GET"])

    @router.delete("/api/settings/library-relocation")
    def reset_relocation() -> dict:
        try:
            return deps.relocation.reset()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    router.add_api_route("/api/settings/library-relocation/cancel", deps.relocation.cancel, methods=["POST"])

    @router.post("/api/settings/library-relocation/rollback")
    def rollback_relocation() -> dict:
        try:
            return deps.relocation.rollback()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/api/settings/backups")
    def list_backups() -> dict:
        deps.backup_root.mkdir(parents=True, exist_ok=True)
        backups = []
        for path in sorted(
            deps.backup_root.glob("*.aexbackup"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            try:
                backups.append(service.public_backup(service.backup_service().describe(path)))
            except ValueError:
                backups.append({"filename": path.name, "size": service._path_size(path), "valid": False})
        return {"backups": backups, "directory": str(deps.backup_root)}

    @router.post("/api/settings/backups", status_code=201)
    def create_backup(request: BackupCreateRequest) -> dict:
        try:
            result = service.backup_service().create(
                deps.backup_root,
                include_cache=request.include_analysis_cache,
                retention=request.retention,
            )
            return {
                **service.public_backup(result),
                "download_url": f"/api/settings/backups/{result['filename']}/download",
            }
        except (OSError, sqlite3.Error, ValueError) as error:
            raise HTTPException(500, f"Backup could not be created: {error}") from error

    @router.get("/api/settings/backups/{filename}/download")
    def download_backup(filename: str) -> FileResponse:
        if Path(filename).name != filename or not filename.endswith(".aexbackup"):
            raise HTTPException(400, "Invalid backup name")
        path = deps.backup_root / filename
        if not path.is_file():
            raise HTTPException(404, "Backup not found")
        return FileResponse(path, filename=path.name, media_type="application/zip")

    @router.post("/api/settings/backups/preview")
    async def preview_backup(file: Annotated[UploadFile, File()]) -> dict:
        if not str(file.filename or "").endswith(".aexbackup"):
            raise HTTPException(400, "Choose an .aexbackup file")
        pending = deps.backup_root / ".pending"
        pending.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        target = pending / f"{token}.aexbackup"
        try:
            with target.open("wb") as handle:
                shutil.copyfileobj(file.file, handle)
            if target.stat().st_size > 4 * 1024 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413, "Backup files larger than 4 GB are not supported")
            preview = service.backup_service().inspect(target)
        except ValueError as error:
            target.unlink(missing_ok=True)
            raise HTTPException(400, str(error)) from error
        deps.pending_restores[token] = target
        current_tracks = len(deps.repository().list_downloaded_tracks())
        return {
            **service.public_backup(preview),
            "token": token,
            "current_track_count": current_tracks,
            "track_difference": int(preview.get("track_count") or 0) - current_tracks,
        }

    @router.post("/api/settings/backups/restore")
    def restore_backup(request: BackupRestoreRequest) -> dict:
        if request.confirmation != "RESTORE BACKUP":
            raise HTTPException(400, "Type RESTORE BACKUP exactly to confirm")
        active = deps.repository().list_jobs_page(page=1, page_size=1, statuses=("queued", "processing", "paused"))[1]
        if active:
            raise HTTPException(409, "Finish or cancel active analysis jobs before restoring a backup")
        archive = deps.pending_restores.pop(request.token, None)
        if archive is None or not archive.is_file():
            raise HTTPException(404, "The restore preview expired; select the backup again")
        try:
            result = service.backup_service().restore(archive, deps.backup_root)
            deps.report_cache.update(mtime_ns=None, payload={"songs": {}})
            deps.catalog_cache.update(signature=None, facets_signature=None, facets=None)
            return {
                "restored": True,
                "manifest": service.public_backup(result["manifest"]),
                "pre_restore_backup": service.public_backup(result["pre_restore_backup"]),
            }
        except (OSError, sqlite3.Error, ValueError) as error:
            raise HTTPException(500, f"Backup restore failed: {error}") from error
        finally:
            archive.unlink(missing_ok=True)

    @router.post("/api/settings/cleanup")
    def cleanup_application(request: ApplicationCleanupRequest) -> dict:
        if request.confirmation != "DELETE EVERYTHING":
            raise HTTPException(400, "Type DELETE EVERYTHING exactly to confirm the reset")
        active_jobs = [
            job
            for job in deps.repository().list_jobs(limit=10_000)
            if job["status"] in {"queued", "processing", "paused"}
        ]
        if active_jobs or any(item.has_active_imports() for item in deps.import_services):
            raise HTTPException(409, "Cancel or finish all processing and imports before cleaning up the app")
        downloaded = [
            Path(track["file_path"]) for track in deps.repository().list_downloaded_tracks() if track.get("file_path")
        ]
        deps.repository().reset_track_data()
        removed = 0
        for path in downloaded:
            if path.is_file():
                path.unlink()
                removed += 1
            source_record = deps.source_metadata_path(path)
            if source_record.is_file():
                source_record.unlink()
                removed += 1
        for path in (
            deps.input_root,
            deps.project / deps.cache_folder_name,
            deps.output_root / "cue_sheets",
            deps.output_root / "extended",
            deps.output_root / "previews",
            deps.output_root / "rekordbox",
            deps.output_root / "versions",
            deps.output_root / "wav",
        ):
            removed += service.remove_managed_path(path, deps.project)
        if deps.output_root.exists():
            for child in deps.output_root.iterdir():
                if child.name != "reports":
                    removed += service.remove_managed_path(child, deps.project)
        reports = deps.output_root / "reports"
        if reports.exists():
            retained = {
                deps.database.name,
                f"{deps.database.name}-wal",
                f"{deps.database.name}-shm",
                deps.presets_path.name,
            }
            for child in reports.iterdir():
                if child.name not in retained:
                    removed += service.remove_managed_path(child, deps.project)
        removed += service.remove_managed_path(deps.overrides_path, deps.project)
        deps.input_root.mkdir(parents=True, exist_ok=True)
        deps.output_root.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        for item in deps.import_services:
            item.clear()
        return {"reset": True, "removed_files": removed}

    return router
