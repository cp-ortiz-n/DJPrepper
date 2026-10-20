"""Explicit runtime paths and process-local state for the web application."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from audioextender.core.defaults import INPUT_FOLDER_NAME, OUTPUT_FOLDER_NAME
from audioextender.infrastructure.background_tasks import BackgroundTaskRegistry
from audioextender.infrastructure.batch_operations import BatchOperationRegistry
from audioextender.library.relocation import LibraryRelocationCoordinator
from audioextender.persistence.facade import JobRepository
from audioextender.processing.web_jobs import WebJobService


@dataclass(frozen=True)
class ApplicationPaths:
    """Every filesystem root used while composing one application instance."""

    project: Path
    input: Path
    output: Path
    frontend: Path
    database: Path
    overrides: Path
    presets: Path
    set_builder_catalog_cache: Path
    default_music_library: str
    backup_root: Path
    storage_inventory_snapshot: Path

    @classmethod
    def from_project(
        cls,
        project: Path,
        *,
        frontend_root: Path | None = None,
        default_music_library: Path | None = None,
    ) -> ApplicationPaths:
        """Build a complete path set under ``project`` for production or tests."""
        project = project.expanduser().resolve()
        output = project / OUTPUT_FOLDER_NAME
        reports = output / "reports"
        return cls(
            project=project,
            input=project / INPUT_FOLDER_NAME,
            output=output,
            frontend=(frontend_root or project / "frontend").expanduser().resolve(),
            database=reports / "audioextender.sqlite3",
            overrides=project / "track_overrides.json",
            presets=reports / "web_presets.json",
            set_builder_catalog_cache=reports / "set_builder_catalog.json",
            default_music_library=str(default_music_library or Path.home() / "Music" / "AudioExtender Library"),
            backup_root=output / "backups",
            storage_inventory_snapshot=reports / "storage_inventory.json",
        )


@dataclass
class ApplicationRuntime:
    """Owned dependencies and mutable process state for one FastAPI app."""

    paths: ApplicationPaths
    repository: JobRepository
    job_service: WebJobService
    relocation: LibraryRelocationCoordinator
    creative_commons_registry: BackgroundTaskRegistry
    metadata_batch_registry: BatchOperationRegistry = field(default_factory=BatchOperationRegistry)
    pending_backup_restores: dict[str, Path] = field(default_factory=dict)
    wav_tag_audit_refresh_lock: threading.Lock = field(default_factory=threading.Lock)
    integrity_scan_batches: dict[str, dict[str, Any]] = field(default_factory=dict)
    integrity_scan_batch_lock: threading.Lock = field(default_factory=threading.Lock)
    audio_quality_batches: dict[str, dict[str, Any]] = field(default_factory=dict)
    audio_quality_batch_lock: threading.Lock = field(default_factory=threading.Lock)
    key_analysis_batches: dict[str, dict[str, Any]] = field(default_factory=dict)
    key_analysis_batch_lock: threading.Lock = field(default_factory=threading.Lock)
    library_consolidation_batches: dict[str, dict[str, Any]] = field(default_factory=dict)
    library_consolidation_batch_lock: threading.Lock = field(default_factory=threading.Lock)
    downloaded_catalog_migration_lock: threading.Lock = field(default_factory=threading.Lock)
    report_cache_lock: threading.Lock = field(default_factory=threading.Lock)
    report_cache: dict[str, object] = field(default_factory=lambda: {"mtime_ns": None, "payload": {"songs": {}}})
    analytics_cache_lock: threading.Lock = field(default_factory=threading.Lock)
    analytics_cache: dict[str, object] = field(default_factory=lambda: {"expires_at": 0.0, "payload": None})
    library_catalog_cache_lock: threading.Lock = field(default_factory=threading.Lock)
    library_catalog_cache: dict[str, object] = field(
        default_factory=lambda: {"signature": None, "facets_signature": None, "facets": None}
    )
    library_status_cache_lock: threading.Lock = field(default_factory=threading.Lock)
    library_status_cache: dict[str, object] = field(default_factory=lambda: {"expires_at": 0.0, "payload": None})
    storage_inventory_lock: threading.Lock = field(default_factory=threading.Lock)
    storage_inventory_cache: dict[str, object] = field(default_factory=lambda: {"expires_at": 0.0, "payload": None})
    library_index_refresh_lock: threading.Lock = field(default_factory=threading.Lock)
    performance_diagnostics_lock: threading.Lock = field(default_factory=threading.Lock)
    waveform_generation_locks_guard: threading.Lock = field(default_factory=threading.Lock)
    waveform_generation_locks: dict[str, threading.Lock] = field(default_factory=dict)
    performance_diagnostics: deque[dict[str, object]] = field(default_factory=lambda: deque(maxlen=500))
    performance_cache_stats: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "waveform": {"hits": 0, "misses": 0},
            "artwork_thumbnail": {"hits": 0, "misses": 0},
        }
    )
    services: dict[str, object] = field(default_factory=dict)

    @classmethod
    def create(cls, paths: ApplicationPaths) -> ApplicationRuntime:
        """Construct dependencies without running startup recovery or workers."""
        paths.database.parent.mkdir(parents=True, exist_ok=True)
        repository = JobRepository(paths.database)
        return cls(
            paths=paths,
            repository=repository,
            job_service=WebJobService(paths.project, repository),
            relocation=LibraryRelocationCoordinator(
                repository,
                paths.output / "reports" / "library_relocation.json",
            ),
            creative_commons_registry=BackgroundTaskRegistry(
                paths.output / "reports" / "tasks" / "creative-commons.json"
            ),
        )


def runtime_bindings(runtime: ApplicationRuntime) -> dict[str, object]:
    """Return the legacy names backed by an explicit runtime instance."""
    paths = runtime.paths
    return {
        "PROJECT": paths.project,
        "INPUT": paths.input,
        "OUTPUT": paths.output,
        "FRONTEND": paths.frontend,
        "DATABASE": paths.database,
        "OVERRIDES": paths.overrides,
        "WEB_PRESETS": paths.presets,
        "SET_BUILDER_CATALOG_CACHE": paths.set_builder_catalog_cache,
        "DEFAULT_MUSIC_LIBRARY": paths.default_music_library,
        "BACKUP_ROOT": paths.backup_root,
        "STORAGE_INVENTORY_SNAPSHOT": paths.storage_inventory_snapshot,
        "repository": runtime.repository,
        "library_relocation": runtime.relocation,
        "service": runtime.job_service,
        "pending_backup_restores": runtime.pending_backup_restores,
        "creative_commons_registry": runtime.creative_commons_registry,
        "creative_commons_batches": runtime.creative_commons_registry,
        "creative_commons_batch_lock": runtime.creative_commons_registry.lock,
        "wav_tag_audit_refresh_lock": runtime.wav_tag_audit_refresh_lock,
        "metadata_batch_registry": runtime.metadata_batch_registry,
        "integrity_scan_batches": runtime.integrity_scan_batches,
        "integrity_scan_batch_lock": runtime.integrity_scan_batch_lock,
        "audio_quality_batches": runtime.audio_quality_batches,
        "audio_quality_batch_lock": runtime.audio_quality_batch_lock,
        "key_analysis_batches": runtime.key_analysis_batches,
        "key_analysis_batch_lock": runtime.key_analysis_batch_lock,
        "library_consolidation_batches": runtime.library_consolidation_batches,
        "library_consolidation_batch_lock": runtime.library_consolidation_batch_lock,
        "downloaded_catalog_migration_lock": runtime.downloaded_catalog_migration_lock,
        "report_cache_lock": runtime.report_cache_lock,
        "report_cache": runtime.report_cache,
        "analytics_cache_lock": runtime.analytics_cache_lock,
        "analytics_cache": runtime.analytics_cache,
        "library_catalog_cache_lock": runtime.library_catalog_cache_lock,
        "library_catalog_cache": runtime.library_catalog_cache,
        "library_status_cache_lock": runtime.library_status_cache_lock,
        "library_status_cache": runtime.library_status_cache,
        "storage_inventory_lock": runtime.storage_inventory_lock,
        "storage_inventory_cache": runtime.storage_inventory_cache,
        "library_index_refresh_lock": runtime.library_index_refresh_lock,
        "performance_diagnostics_lock": runtime.performance_diagnostics_lock,
        "waveform_generation_locks_guard": runtime.waveform_generation_locks_guard,
        "waveform_generation_locks": runtime.waveform_generation_locks,
        "performance_diagnostics": runtime.performance_diagnostics,
        "performance_cache_stats": runtime.performance_cache_stats,
        **runtime.services,
    }


class LazyApplication:
    """ASGI proxy that defers application-factory work until first use."""

    def __init__(self, factory: Callable[[], FastAPI]) -> None:
        self._factory = factory
        self._resolved: FastAPI | None = None
        self._lock = threading.Lock()

    def resolve(self) -> FastAPI:
        if self._resolved is None:
            with self._lock:
                if self._resolved is None:
                    self._resolved = self._factory()
        return self._resolved

    def __getattr__(self, name: str) -> Any:
        return getattr(self.resolve(), name)

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        await self.resolve()(scope, receive, send)
