"""Local DJ Library Studio web interface; the AudioExtender CLI remains independent."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import mimetypes
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, Literal
from urllib.parse import urlencode, urlparse

import httpx
import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.middleware.gzip import GZipMiddleware

from helpers.audio_loader import SUPPORTED_EXTENSIONS
from helpers.audio_quality import analyze_audio_quality
from helpers.cache import AnalysisCache
from helpers.feedback_report import append_web_feedback
from helpers.library_backup import LibraryBackupService
from helpers.library_relocation import LibraryRelocationCoordinator
from helpers.presets import PRESETS, EditPreset
from helpers.track_overrides import load_track_overrides
from helpers.transition_scorer import assess_custom_insertion
from helpers.wav_metadata import (
    embed_wav_artwork,
    read_wav_artwork,
    read_wav_metadata,
    sync_wav_metadata,
    write_wav_metadata,
)
from helpers.web_configuration import (
    PresetStore,
    WebConfigurationService,
    WebSettings,
    web_defaults,
)
from helpers.web_database import JobRepository
from helpers.web_jobs import WebJobService
from settings import (
    CACHE_FOLDER_NAME,
    INPUT_FOLDER_NAME,
    OUTPUT_FOLDER_NAME,
    SUPPORTED_BAR_COUNTS,
)

PROJECT = Path(__file__).resolve().parent
INPUT = PROJECT / INPUT_FOLDER_NAME
OUTPUT = PROJECT / OUTPUT_FOLDER_NAME
WEB = PROJECT / "web"
DATABASE = OUTPUT / "reports" / "audioextender.sqlite3"
OVERRIDES = PROJECT / "track_overrides.json"
WEB_PRESETS = OUTPUT / "reports" / "web_presets.json"
SET_BUILDER_CATALOG_CACHE = OUTPUT / "reports" / "set_builder_catalog.json"
DEFAULT_MUSIC_LIBRARY = str(Path.home() / "Music" / "AudioExtender Library")
BACKUP_ROOT = OUTPUT / "backups"
STORAGE_INVENTORY_SNAPSHOT = OUTPUT / "reports" / "storage_inventory.json"

app = FastAPI(title="DJ Library Studio", docs_url="/api/docs", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
repository = JobRepository(DATABASE)


class _ActiveRepositoryView:
    """Resolve a focused repository from the currently active aggregate.

    Keeping this lookup dynamic also lets backup restore and isolated workflow
    tests swap the aggregate atomically without leaving stale domain handles.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, operation: str):
        return getattr(getattr(repository, self.name), operation)


track_catalog_repository = _ActiveRepositoryView("track_catalog")
jobs_repository = _ActiveRepositoryView("jobs_and_queues")
settings_repository = _ActiveRepositoryView("settings_system")
recording_family_repository = _ActiveRepositoryView("recording_families")
feedback_repository = _ActiveRepositoryView("feedback_key_verification")
relocation_repository = _ActiveRepositoryView("backups_relocation")
library_relocation = LibraryRelocationCoordinator(
    relocation_repository, OUTPUT / "reports" / "library_relocation.json"
)
pending_backup_restores: dict[str, Path] = {}
jobs_repository.recover_interrupted()
service = WebJobService(PROJECT, jobs_repository)
authorized_imports: dict[str, dict] = {}
authorized_import_lock = threading.Lock()
authorized_import_cancel_events: dict[str, threading.Event] = {}
playlist_matches: dict[str, dict] = {}
playlist_match_lock = threading.Lock()
creative_commons_batches: dict[str, dict] = {}
creative_commons_batch_lock = threading.Lock()
wav_tag_batches: dict[str, dict] = {}
wav_tag_batch_lock = threading.Lock()
wav_tag_audit_refresh_lock = threading.Lock()
wav_tag_audit_refresh_active = False
artwork_sync_batches: dict[str, dict] = {}
artwork_sync_batch_lock = threading.Lock()
genre_rescan_batches: dict[str, dict] = {}
genre_rescan_batch_lock = threading.Lock()
integrity_scan_batches: dict[str, dict] = {}
integrity_scan_batch_lock = threading.Lock()
catalog_reconcile_batches: dict[str, dict] = {}
catalog_reconcile_batch_lock = threading.Lock()
audio_quality_batches: dict[str, dict] = {}
audio_quality_batch_lock = threading.Lock()
key_analysis_batches: dict[str, dict] = {}
key_analysis_batch_lock = threading.Lock()
library_consolidation_batches: dict[str, dict] = {}
library_consolidation_batch_lock = threading.Lock()
local_import_batches: dict[str, dict] = {}
local_import_batch_lock = threading.Lock()
downloaded_catalog_migration_lock = threading.Lock()
downloaded_catalog_migrated = False
DOWNLOADED_CATALOG_MIGRATION_VERSION = "3"
artwork_thumbnail_lock = threading.Lock()
artwork_thumbnail_queue: queue.Queue[tuple[Path, Path, int]] = queue.Queue()
artwork_thumbnail_pending: set[Path] = set()
artwork_thumbnail_worker_started = False
report_cache_lock = threading.Lock()
report_cache: dict[str, Any] = {"mtime_ns": None, "payload": {"songs": {}}}
analytics_cache_lock = threading.Lock()
analytics_cache: dict[str, Any] = {"expires_at": 0.0, "payload": None}
library_catalog_cache_lock = threading.Lock()
library_catalog_cache: dict[str, Any] = {
    "signature": None,
    "facets_signature": None,
    "facets": None,
}
library_status_cache_lock = threading.Lock()
library_status_cache: dict[str, Any] = {"expires_at": 0.0, "payload": None}
storage_inventory_lock = threading.Lock()
storage_inventory_cache: dict[str, Any] = {"expires_at": 0.0, "payload": None}
library_index_refresh_lock = threading.Lock()
library_index_refresh_active = False
jobs_watchdog_last = 0.0
performance_diagnostics_lock = threading.Lock()
waveform_generation_locks_guard = threading.Lock()
waveform_generation_locks: dict[str, threading.Lock] = {}
performance_diagnostics: deque[dict[str, Any]] = deque(maxlen=500)
performance_cache_stats: dict[str, dict[str, int]] = {
    "waveform": {"hits": 0, "misses": 0},
    "artwork_thumbnail": {"hits": 0, "misses": 0},
}
app.mount(
    "/vendor/wavesurfer",
    StaticFiles(
        directory=PROJECT / "node_modules" / "wavesurfer.js" / "dist",
        check_dir=False,
    ),
    name="wavesurfer",
)
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


def _record_cache_result(cache_name: str, hit: bool) -> None:
    with performance_diagnostics_lock:
        counters = performance_cache_stats.setdefault(cache_name, {"hits": 0, "misses": 0})
        counters["hits" if hit else "misses"] += 1


@app.middleware("http")
async def record_api_performance(request: Request, call_next):
    """Keep a small, process-local timing window for actionable UI diagnostics."""
    if (
        not request.url.path.startswith("/api/")
        or request.url.path == "/api/diagnostics/performance"
    ):
        return await call_next(request)
    started = perf_counter()
    status = 500
    response_bytes = 0
    try:
        response = await call_next(request)
        status = response.status_code
        try:
            response_bytes = int(response.headers.get("content-length") or 0)
        except ValueError:
            response_bytes = 0
        return response
    finally:
        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        with performance_diagnostics_lock:
            performance_diagnostics.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "method": request.method,
                    "path": route_path,
                    "status": status,
                    "duration_ms": elapsed_ms,
                    "response_bytes": response_bytes,
                }
            )


@app.get("/api/diagnostics/performance")
def performance_diagnostics_report() -> dict:
    with performance_diagnostics_lock:
        samples = list(performance_diagnostics)
        cache_snapshot = {name: dict(values) for name, values in performance_cache_stats.items()}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        key = f"{sample['method']} {sample['path']}"
        grouped.setdefault(key, []).append(sample)

    operations: list[dict[str, Any]] = []
    for operation, entries in grouped.items():
        durations = sorted(float(entry["duration_ms"]) for entry in entries)
        percentile_index = round((len(durations) - 1) * 0.95)
        operations.append(
            {
                "operation": operation,
                "count": len(entries),
                "average_ms": round(sum(durations) / len(durations), 1),
                "p95_ms": durations[percentile_index],
                "maximum_ms": durations[-1],
                "failures": sum(int(entry["status"]) >= 400 for entry in entries),
                "average_response_bytes": round(
                    sum(int(entry.get("response_bytes") or 0) for entry in entries) / len(entries)
                ),
            }
        )
    operations.sort(key=lambda item: (-float(item["p95_ms"]), -int(item["count"])))

    cache = []
    for name, counters in cache_snapshot.items():
        total = counters["hits"] + counters["misses"]
        cache.append(
            {
                "name": name,
                **counters,
                "hit_rate": round(counters["hits"] * 100 / total, 1) if total else None,
            }
        )
    slow = [sample for sample in reversed(samples) if float(sample["duration_ms"]) >= 250][:20]
    durations = [float(sample["duration_ms"]) for sample in samples]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_size": len(samples),
        "window_limit": performance_diagnostics.maxlen,
        "overall_average_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "operations": operations,
        "recent_slow_operations": slow,
        "cache": cache,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


WEB_DEFAULTS = web_defaults(DEFAULT_MUSIC_LIBRARY)
preset_store = PresetStore(WEB_PRESETS)
configuration_service = WebConfigurationService(settings_repository, WEB_DEFAULTS, preset_store)


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


class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")
    intro_bars: int
    outro_bars: int
    use_stems: bool = False
    minimum_loop_quality: float = Field(ge=0, le=100)
    maximum_repetitions: int = Field(ge=1, le=8)


def _preset_state() -> dict:
    return preset_store.state()


def _save_preset_state(state: dict) -> None:
    preset_store.save(state)


def _available_presets() -> dict[str, EditPreset]:
    return preset_store.available()


def _preset_payload() -> list[dict]:
    return preset_store.payload()


def _preset_snapshot(name: str) -> dict:
    return preset_store.snapshot(name)


class FeedbackRequest(BaseModel):
    position: str
    candidate_rank: int | None = None
    accepted: bool
    tags: str = ""
    notes: str = ""


class TrackFeedbackRequest(BaseModel):
    source_name: str = Field(min_length=1)
    position: str
    accepted: bool
    tags: str = ""
    notes: str = ""


class KeyVerificationRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=500)
    verified_key: str = Field(min_length=1, max_length=20)
    detected_key: str = Field(default="", max_length=20)
    candidates: list[dict] = Field(default_factory=list, max_length=3)
    notes: str = Field(default="", max_length=1000)


class AuthorizedImportRequest(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    rights_basis: Literal["own-upload", "creative-commons", "public-domain", "permission"]
    confirmation: bool
    process_with_extender: bool = False
    title: str = Field(default="", max_length=300)
    artist: str = Field(default="", max_length=300)
    spotify_uri: str = Field(default="", max_length=200)
    artwork_url: str = Field(default="", max_length=1000)


class SourceMatchRequest(BaseModel):
    url: str = Field(min_length=10, max_length=500)


class CreativeCommonsMatch(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    spotify_uri: str = Field(default="", max_length=200)
    genre: str = Field(default="", max_length=500)
    genre_category: str = Field(default="Other", max_length=80)
    artwork_url: str = Field(default="", max_length=1000)
    playlist_name: str = Field(default="", max_length=180)


class CreativeCommonsBatchRequest(BaseModel):
    tracks: list[CreativeCommonsMatch] = Field(min_length=1, max_length=500)
    playlist_name: str = Field(default="Imported Playlist", min_length=1, max_length=180)


class DownloadedTracksRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=1000)


class DuplicateMergeRequest(BaseModel):
    survivor_id: int = Field(gt=0)
    duplicate_id: int = Field(gt=0)


class TrackFamilyLinkRequest(BaseModel):
    target_track_id: int | None = Field(default=None, gt=0)
    target_identity: str = Field(default="", max_length=40)
    relationship: Literal["ORG", "RMX", "EXT", "RADIO", "LIVE", "INST", "ACAP", "REM"]


class ImportFailureRetryRequest(BaseModel):
    failure_ids: list[int] = Field(min_length=1, max_length=500)


class ArtworkSyncRequest(BaseModel):
    track_ids: list[int] = Field(default_factory=list, max_length=5000)


class DownloadedAnalysisFilterRequest(BaseModel):
    search: str = Field(default="", max_length=300)
    genre: str = Field(default="all", max_length=100)
    detailed_genre: str = Field(default="all", max_length=120)
    playlist: str = Field(default="all", max_length=200)
    analysis: str = Field(default="all", max_length=30)
    quality: str = Field(default="all", max_length=30)
    sort: str = Field(default="newest", max_length=30)


class DownloadedGenreRequest(DownloadedTracksRequest):
    genre_category: str = Field(min_length=1, max_length=80)


class DownloadedMetadataRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="", max_length=300)
    genre: str = Field(default="", max_length=500)
    genre_category: str = Field(min_length=1, max_length=80)
    playlist_name: str = Field(default="Imported Singles", min_length=1, max_length=180)
    artwork_url: str = Field(default="", max_length=1000)
    rename_file: bool = False


class IntegrityRepairRequest(BaseModel):
    action: Literal[
        "remove-missing", "catalog-uncataloged", "delete-stale-sidecars", "retag-mismatches"
    ]
    item_ids: list[str] = Field(default_factory=list, max_length=5000)


class ApplicationCleanupRequest(BaseModel):
    confirmation: str


class ReorderRequest(BaseModel):
    job_ids: list[int]


class SetExportPreflightRequest(BaseModel):
    paths: list[str] = Field(default_factory=list, max_length=5000)


class SetPlaylistTrack(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    duration_seconds: float = Field(default=0, ge=0)


class SetPlaylistSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    tracks: list[SetPlaylistTrack] = Field(min_length=1, max_length=5000)


BatchFileType = Literal[
    "extended",
    "source",
    "cue-sheet",
    "rekordbox",
    "intro-preview",
    "outro-preview",
    "analysis",
]


def _default_batch_file_types() -> list[BatchFileType]:
    return ["extended"]


class BatchDownloadRequest(BaseModel):
    job_ids: list[int] = Field(min_length=1)
    file_types: list[BatchFileType] = Field(default_factory=_default_batch_file_types, min_length=1)


class ReprocessRequest(BaseModel):
    preset: str | None = None
    intro_bars: int | None = None
    outro_bars: int | None = None
    intro_bars_auto: bool | None = None
    outro_bars_auto: bool | None = None
    use_stems: bool | None = None
    auto_bars: bool | None = None
    minimum_intro_loop_quality: float | None = Field(None, ge=0, le=100)
    minimum_outro_loop_quality: float | None = Field(None, ge=0, le=100)
    maximum_repetitions: int | None = Field(None, ge=1, le=8)
    crossfade_ms: float | None = Field(None, ge=1, le=100)
    candidate_count: int | None = Field(None, ge=1, le=8)
    intro_search_seconds: float | None = Field(None, ge=15, le=600)
    outro_search_seconds: float | None = Field(None, ge=15, le=600)
    maximum_vocal_coverage_percent: float | None = Field(None, ge=0, le=100)
    maximum_vocal_boundary_risk_percent: float | None = Field(None, ge=0, le=100)
    maximum_buildup_risk_percent: float | None = Field(None, ge=0, le=100)
    maximum_bass_reset_risk_percent: float | None = Field(None, ge=0, le=100)
    minimum_stem_reliability_percent: float | None = Field(None, ge=0, le=100)
    pcm_bits: int | None = None
    preview_seconds: float | None = Field(None, gt=0, le=60)
    export_cues: bool | None = None
    intro_candidate: int | None = Field(None, ge=0, le=3)
    outro_candidate: int | None = Field(None, ge=0, le=3)
    review_candidates: bool | None = None
    custom_intro_start: float | None = Field(None, ge=0)
    custom_intro_end: float | None = Field(None, gt=0)
    custom_intro_copies: int | None = Field(None, ge=1, le=8)
    custom_outro_start: float | None = Field(None, ge=0)
    custom_outro_end: float | None = Field(None, gt=0)
    custom_outro_copies: int | None = Field(None, ge=1, le=8)
    insert_source_start: float | None = Field(None, ge=0)
    insert_source_end: float | None = Field(None, gt=0)
    insert_destination: float | None = Field(None, ge=0)
    insert_copies: int | None = Field(None, ge=1, le=8)
    clear_insertion: bool = False


class TransitionScoreRequest(BaseModel):
    source_start: float = Field(ge=0)
    source_end: float = Field(gt=0)
    destination: float = Field(ge=0)
    copies: int = Field(ge=1, le=8)


class OverrideRequest(BaseModel):
    intro_before: float | None = Field(None, gt=0)
    outro_after: float | None = Field(None, gt=0)
    outro_before: float | None = Field(None, gt=0)


class CueEdit(BaseModel):
    name: str
    start: float = Field(ge=0)
    end: float | None = Field(None, ge=0)
    kind: str = "memory"
    purpose: str = ""
    confidence: float | None = None


class CueEditRequest(BaseModel):
    cues: list[CueEdit]


def _effective_settings() -> dict:
    return configuration_service.effective()


def _music_library_root() -> Path:
    """Return the configured absolute download root without creating it."""
    raw = str(_effective_settings().get("music_library_path") or "").strip()
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError("Music Library Location must be an absolute path")
    return root.resolve()


def _require_music_library_online() -> Path:
    root = _music_library_root()
    if not root.is_dir():
        raise HTTPException(
            409,
            "Music library is offline. Connect the configured drive before running file operations.",
        )
    return root


def _library_location_summary() -> dict:
    root = _music_library_root()
    locations: dict[str, int] = {}
    outside: list[dict] = []
    for track in track_catalog_repository.list_downloaded_tracks():
        path = Path(str(track.get("file_path") or "")).expanduser()
        try:
            path.resolve().relative_to(root)
            label = str(root)
        except (OSError, ValueError):
            local_root = Path(DEFAULT_MUSIC_LIBRARY)
            try:
                path.resolve().relative_to(local_root)
                label = str(local_root)
            except (OSError, ValueError):
                label = str(path.parent)
            outside.append({"id": int(track["id"]), "title": track.get("title"), "path": str(path)})
        locations[label] = locations.get(label, 0) + 1
    return {
        "configured_root": str(root),
        "online": root.is_dir(),
        "locations": [
            {"path": path, "tracks": count, "configured": path == str(root)}
            for path, count in sorted(locations.items(), key=lambda item: (-item[1], item[0]))
        ],
        "outside_count": len(outside),
        "outside_tracks": outside,
    }


def _source_metadata_path(audio_path: Path) -> Path:
    """Store importer metadata away from the user-facing genre folders."""
    key = hashlib.sha256(str(audio_path.resolve()).encode("utf-8")).hexdigest()
    return _music_library_root() / ".audioextender" / "sources" / f"{key}.json"


def _write_source_metadata(audio_path: Path, metadata: dict) -> Path:
    destination = _source_metadata_path(audio_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({**metadata, "file_path": str(audio_path.resolve())}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


@app.get("/api/config")
def config() -> dict:
    available_presets = _available_presets()
    return {
        "presets": ["auto", *available_presets.keys()],
        "preset_details": {
            name: {
                "intro_bars": preset.intro_bars,
                "outro_bars": preset.outro_bars,
                "use_stems": preset.use_stems,
                "minimum_loop_quality": preset.minimum_loop_quality,
                "maximum_repetitions": preset.maximum_repetitions,
            }
            for name, preset in available_presets.items()
        },
        "bar_counts": list(SUPPORTED_BAR_COUNTS),
        "defaults": WEB_DEFAULTS,
        "effective": _effective_settings(),
        "overrides": settings_repository.get_settings(),
    }


@app.put("/api/settings")
def save_settings(settings: WebSettings) -> dict:
    values = settings.model_dump()
    try:
        overrides = configuration_service.persist(values)
    except (OSError, ValueError) as error:
        raise HTTPException(400, str(error)) from error
    with library_status_cache_lock:
        library_status_cache.update(payload=None, expires_at=0.0)
    if Path(values["music_library_path"]).is_dir():
        _refresh_wav_tag_audit()
    return {"defaults": WEB_DEFAULTS, "effective": _effective_settings(), "overrides": overrides}


@app.delete("/api/settings")
def reset_settings() -> dict:
    configuration_service.reset()
    with library_status_cache_lock:
        library_status_cache.update(payload=None, expires_at=0.0)
    return {"defaults": WEB_DEFAULTS, "effective": _effective_settings(), "overrides": {}}


@app.get("/api/settings/library-status")
def music_library_status() -> dict:
    now = perf_counter()
    with library_status_cache_lock:
        root = _music_library_root()
        cached = library_status_cache.get("payload")
        # Mount state can change without an application event. Never retain an
        # online/offline result after the external folder's existence flips.
        mount_state_changed = cached is not None and bool(cached.get("online")) != root.is_dir()
        if (
            cached is not None
            and not mount_state_changed
            and now < float(library_status_cache["expires_at"])
        ):
            return dict(cached)
        identity = root / ".audioextender" / "library.json"
        library_id = ""
        try:
            library_id = str(
                json.loads(identity.read_text(encoding="utf-8")).get("library_id") or ""
            )
        except (OSError, ValueError):
            pass
        storage_scan_started = perf_counter()
        tracks = track_catalog_repository.list_downloaded_tracks()
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
            free_bytes = disk.free
            capacity_bytes = disk.total
        except OSError:
            free_bytes = capacity_bytes = 0
        available = len(available_paths)
        payload = {
            "path": str(root),
            "online": root.is_dir(),
            "library_id": library_id,
            "cataloged_tracks": len(tracks),
            "available_tracks": available,
            "offline_tracks": len(tracks) - available,
            "song_bytes": song_bytes,
            "supporting_bytes": max(0, total_bytes - song_bytes),
            "total_bytes": total_bytes,
            "file_count": file_count,
            "free_bytes": free_bytes,
            "capacity_bytes": capacity_bytes,
            "audio_quality": track_catalog_repository.audio_quality_summary(),
            "location_integrity": _library_location_summary(),
            "storage_scan_ms": round((perf_counter() - storage_scan_started) * 1000, 1),
        }
        library_status_cache.update(payload=payload, expires_at=now + 60.0)
        return payload


def _path_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _storage_inventory_signature() -> list[list[object]]:
    paths = [
        DATABASE,
        PROJECT / CACHE_FOLDER_NAME,
        OUTPUT / "extended",
        OUTPUT / "previews",
        OUTPUT / "versions",
    ]
    signature: list[list[object]] = []
    for path in paths:
        try:
            stat = path.stat()
            signature.append([str(path.resolve()), stat.st_mtime_ns, stat.st_size])
        except OSError:
            signature.append([str(path.resolve()), 0, 0])
    return signature


def _saved_storage_inventory(signature: list[list[object]]) -> dict | None:
    try:
        saved = json.loads(STORAGE_INVENTORY_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    payload = saved.get("payload")
    return (
        dict(payload) if saved.get("signature") == signature and isinstance(payload, dict) else None
    )


def _storage_inventory(refresh: bool = False) -> dict:
    now = perf_counter()
    with storage_inventory_lock:
        cached = storage_inventory_cache.get("payload")
        if (
            not refresh
            and cached is not None
            and now < float(storage_inventory_cache["expires_at"])
        ):
            return dict(cached)
    signature = _storage_inventory_signature()
    if not refresh:
        saved = _saved_storage_inventory(signature)
        if saved is not None:
            with storage_inventory_lock:
                storage_inventory_cache.update(payload=saved, expires_at=now + 120.0)
            return saved
    cache_root = (PROJECT / CACHE_FOLDER_NAME).resolve()
    jobs = relocation_repository.list_storage_job_references()
    cache = AnalysisCache(cache_root, enabled=False)
    retained_cache: set[Path] = set()
    referenced_outputs: set[Path] = set()
    for job in jobs:
        for field in (
            "source_path",
            "wav_path",
            "extended_path",
            "intro_preview_path",
            "outro_preview_path",
            "cue_sheet_path",
            "rekordbox_path",
        ):
            value = str(job.get(field) or "").strip()
            if value:
                referenced_outputs.add(Path(value).expanduser().resolve())
        source = Path(str(job.get("source_path") or ""))
        if source.is_file():
            try:
                retained_cache.update(cache.processing_paths(source, service.config_for(job)))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        for field in ("wav_path", "extended_path"):
            audio = Path(str(job.get(field) or ""))
            if audio.is_file():
                try:
                    retained_cache.add(cache.waveform_path(audio))
                except OSError:
                    pass
    for track in track_catalog_repository.list_downloaded_tracks():
        for field in ("file_path", "artwork_path"):
            value = str(track.get(field) or "").strip()
            if value:
                referenced_outputs.add(Path(value).expanduser().resolve())
    cache_files = {
        path.resolve()
        for path in cache_root.glob("*")
        if path.is_file()
        and (path.suffix == ".npz" or path.name.endswith((".instrumental.wav", ".drums.wav")))
    }
    stale_cache = sorted(cache_files - retained_cache)
    generated_candidates: set[Path] = set()
    for directory in (OUTPUT / "extended", OUTPUT / "previews", OUTPUT / "versions"):
        if directory.is_dir():
            generated_candidates.update(
                path.resolve() for path in directory.rglob("*") if path.is_file()
            )
    generated_candidates.update(path.resolve() for path in OUTPUT.glob("*.wav") if path.is_file())
    orphaned_outputs = sorted(generated_candidates - referenced_outputs)
    stale_bytes = sum(_path_size(path) for path in stale_cache)
    orphaned_bytes = sum(_path_size(path) for path in orphaned_outputs)
    payload = {
        "analysis_cache_bytes": sum(_path_size(path) for path in cache_files),
        "analysis_cache_files": len(cache_files),
        "stale_cache_bytes": stale_bytes,
        "stale_cache_files": len(stale_cache),
        "generated_output_bytes": sum(_path_size(path) for path in generated_candidates),
        "generated_output_files": len(generated_candidates),
        "orphaned_output_bytes": orphaned_bytes,
        "orphaned_output_files": len(orphaned_outputs),
        "reclaimable_bytes": stale_bytes + orphaned_bytes,
        "_stale_cache": [str(path) for path in stale_cache],
        "_orphaned_outputs": [str(path) for path in orphaned_outputs],
    }
    with storage_inventory_lock:
        storage_inventory_cache.update(payload=payload, expires_at=now + 120.0)
    try:
        STORAGE_INVENTORY_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        temporary = STORAGE_INVENTORY_SNAPSHOT.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"signature": signature, "payload": payload}), encoding="utf-8"
        )
        temporary.replace(STORAGE_INVENTORY_SNAPSHOT)
    except OSError:
        pass
    return dict(payload)


def _public_storage_inventory(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if not key.startswith("_")}


@app.get("/api/settings/storage")
def settings_storage() -> dict:
    return _public_storage_inventory(_storage_inventory())


class StorageCleanupRequest(BaseModel):
    target: Literal["stale-cache", "orphaned-output"]


@app.post("/api/settings/storage/cleanup")
def cleanup_settings_storage(request: StorageCleanupRequest) -> dict:
    active = [
        job
        for job in jobs_repository.list_jobs(limit=10_000)
        if job.get("status") in {"queued", "processing", "paused"}
    ]
    if active:
        raise HTTPException(409, "Finish or cancel active analysis jobs before cleaning storage")
    inventory = _storage_inventory(refresh=True)
    key = "_stale_cache" if request.target == "stale-cache" else "_orphaned_outputs"
    removed_files = 0
    removed_bytes = 0
    for value in inventory[key]:
        path = Path(value)
        try:
            size = path.stat().st_size
            path.unlink()
            removed_files += 1
            removed_bytes += size
        except FileNotFoundError:
            continue
        except OSError as error:
            raise HTTPException(500, f"Could not remove {path.name}: {error}") from error
    with storage_inventory_lock:
        storage_inventory_cache.update(payload=None, expires_at=0.0)
    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "storage": _public_storage_inventory(_storage_inventory(refresh=True)),
    }


@app.post("/api/settings/library-relocation/plan")
def plan_library_relocation(request: LibraryRelocationRequest) -> dict:
    try:
        destination = Path(request.destination).expanduser()
        if not destination.is_absolute():
            raise ValueError("The destination must be an absolute path")
        return library_relocation.prepare(
            _music_library_root(), destination, request.mode, request.verification
        )
    except (OSError, ValueError) as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/settings/library-relocation/start", status_code=202)
def start_library_relocation() -> dict:
    try:
        return library_relocation.start()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/settings/library-relocation")
def library_relocation_status() -> dict:
    return library_relocation.status()


@app.delete("/api/settings/library-relocation")
def reset_library_relocation() -> dict:
    try:
        return library_relocation.reset()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/api/settings/library-relocation/cancel")
def cancel_library_relocation() -> dict:
    return library_relocation.cancel()


@app.post("/api/settings/library-relocation/rollback")
def rollback_library_relocation() -> dict:
    try:
        return library_relocation.rollback()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


def _backup_service() -> LibraryBackupService:
    return LibraryBackupService(DATABASE, PROJECT, _music_library_root())


def _public_backup_summary(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in {"files", "path"}}


def _require_idle_for_restore() -> None:
    active = jobs_repository.list_jobs_page(
        page=1, page_size=1, statuses=("queued", "processing", "paused")
    )[1]
    if active:
        raise HTTPException(409, "Finish or cancel active analysis jobs before restoring a backup")


@app.get("/api/settings/backups")
def list_backups() -> dict:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    backups = []
    for path in sorted(
        BACKUP_ROOT.glob("*.aexbackup"), key=lambda item: item.stat().st_mtime, reverse=True
    ):
        try:
            info = _backup_service().describe(path)
            backups.append(_public_backup_summary(info))
        except ValueError:
            backups.append({"filename": path.name, "size": _path_size(path), "valid": False})
    return {"backups": backups, "directory": str(BACKUP_ROOT)}


@app.post("/api/settings/backups", status_code=201)
def create_backup(request: BackupCreateRequest) -> dict:
    try:
        result = _backup_service().create(
            BACKUP_ROOT,
            include_cache=request.include_analysis_cache,
            retention=request.retention,
        )
        return {
            **_public_backup_summary(result),
            "download_url": f"/api/settings/backups/{result['filename']}/download",
        }
    except (OSError, sqlite3.Error, ValueError) as error:
        raise HTTPException(500, f"Backup could not be created: {error}") from error


@app.get("/api/settings/backups/{filename}/download")
def download_backup(filename: str) -> FileResponse:
    if Path(filename).name != filename or not filename.endswith(".aexbackup"):
        raise HTTPException(400, "Invalid backup name")
    path = BACKUP_ROOT / filename
    if not path.is_file():
        raise HTTPException(404, "Backup not found")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@app.post("/api/settings/backups/preview")
async def preview_backup(file: UploadFile = File(...)) -> dict:  # noqa: B008
    if not str(file.filename or "").endswith(".aexbackup"):
        raise HTTPException(400, "Choose an .aexbackup file")
    pending = BACKUP_ROOT / ".pending"
    pending.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    target = pending / f"{token}.aexbackup"
    try:
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        if target.stat().st_size > 4 * 1024 * 1024 * 1024:
            target.unlink(missing_ok=True)
            raise HTTPException(413, "Backup files larger than 4 GB are not supported")
        preview = _backup_service().inspect(target)
    except ValueError as error:
        target.unlink(missing_ok=True)
        raise HTTPException(400, str(error)) from error
    pending_backup_restores[token] = target
    current_tracks = len(track_catalog_repository.list_downloaded_tracks())
    return {
        **_public_backup_summary(preview),
        "token": token,
        "current_track_count": current_tracks,
        "track_difference": int(preview.get("track_count") or 0) - current_tracks,
    }


@app.post("/api/settings/backups/restore")
def restore_backup(request: BackupRestoreRequest) -> dict:
    if request.confirmation != "RESTORE BACKUP":
        raise HTTPException(400, "Type RESTORE BACKUP exactly to confirm")
    _require_idle_for_restore()
    archive = pending_backup_restores.pop(request.token, None)
    if archive is None or not archive.is_file():
        raise HTTPException(404, "The restore preview expired; select the backup again")
    try:
        result = _backup_service().restore(archive, BACKUP_ROOT)
        report_cache.update(mtime_ns=None, payload={"songs": {}})
        library_catalog_cache.update(signature=None, facets_signature=None, facets=None)
        return {
            "restored": True,
            "manifest": _public_backup_summary(result["manifest"]),
            "pre_restore_backup": _public_backup_summary(result["pre_restore_backup"]),
        }
    except (OSError, sqlite3.Error, ValueError) as error:
        raise HTTPException(500, f"Backup restore failed: {error}") from error
    finally:
        archive.unlink(missing_ok=True)


def _remove_managed_path(path: Path) -> int:
    """Remove one path only when it is contained by the AudioExtender project."""
    resolved = path.resolve()
    resolved.relative_to(PROJECT.resolve())
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


@app.post("/api/settings/cleanup")
def cleanup_application(request: ApplicationCleanupRequest) -> dict:
    if request.confirmation != "DELETE EVERYTHING":
        raise HTTPException(400, "Type DELETE EVERYTHING exactly to confirm the reset")
    active_jobs = [
        job
        for job in jobs_repository.list_jobs(limit=10_000)
        if job["status"] in {"queued", "processing", "paused"}
    ]
    active_imports = any(
        state.get("status") == "processing"
        for state in [
            *authorized_imports.values(),
            *playlist_matches.values(),
            *creative_commons_batches.values(),
        ]
    )
    if active_jobs or active_imports:
        raise HTTPException(
            409,
            "Cancel or finish all processing and imports before cleaning up the app",
        )

    downloaded_files = [
        Path(track["file_path"])
        for track in track_catalog_repository.list_downloaded_tracks()
        if track.get("file_path")
    ]
    track_catalog_repository.reset_track_data()
    removed = 0
    for downloaded_file in downloaded_files:
        if downloaded_file.is_file():
            downloaded_file.unlink()
            removed += 1
        source_record = _source_metadata_path(downloaded_file)
        if source_record.is_file():
            source_record.unlink()
            removed += 1
    for path in (
        INPUT,
        PROJECT / CACHE_FOLDER_NAME,
        OUTPUT / "cue_sheets",
        OUTPUT / "extended",
        OUTPUT / "previews",
        OUTPUT / "rekordbox",
        OUTPUT / "versions",
        OUTPUT / "wav",
    ):
        removed += _remove_managed_path(path)
    if OUTPUT.exists():
        for child in OUTPUT.iterdir():
            if child.name == "reports":
                continue
            removed += _remove_managed_path(child)
    reports = OUTPUT / "reports"
    if reports.exists():
        for child in reports.iterdir():
            if child.name in {
                DATABASE.name,
                f"{DATABASE.name}-wal",
                f"{DATABASE.name}-shm",
                WEB_PRESETS.name,
            }:
                continue
            removed += _remove_managed_path(child)
    removed += _remove_managed_path(OVERRIDES)
    INPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    with authorized_import_lock:
        authorized_imports.clear()
        authorized_import_cancel_events.clear()
    with playlist_match_lock:
        playlist_matches.clear()
    with creative_commons_batch_lock:
        creative_commons_batches.clear()
    return {"reset": True, "removed_files": removed}


@app.get("/api/presets")
def list_presets() -> dict:
    return {"presets": _preset_payload()}


@app.put("/api/presets/{current_name}")
def save_preset(current_name: str, request: PresetRequest) -> dict:
    if (
        request.intro_bars not in SUPPORTED_BAR_COUNTS
        or request.outro_bars not in SUPPORTED_BAR_COUNTS
    ):
        raise HTTPException(400, "Unsupported bar count")
    state = _preset_state()
    if current_name != request.name and request.name in _available_presets():
        raise HTTPException(409, "A preset with that name already exists")
    if current_name != request.name:
        state["definitions"].pop(current_name, None)
        if current_name in PRESETS and current_name not in state["hidden"]:
            state["hidden"].append(current_name)
    state["hidden"] = [name for name in state["hidden"] if name != request.name]
    state["definitions"][request.name] = {
        key: value for key, value in request.model_dump().items() if key != "name"
    }
    _save_preset_state(state)
    return {"presets": _preset_payload()}


@app.delete("/api/presets/{name}")
def delete_preset(name: str) -> dict:
    if name not in _available_presets():
        raise HTTPException(404, "Preset not found")
    state = _preset_state()
    state["definitions"].pop(name, None)
    if name in PRESETS and name not in state["hidden"]:
        state["hidden"].append(name)
    _save_preset_state(state)
    return {"presets": _preset_payload()}


@app.post("/api/presets/restore")
def restore_presets() -> dict:
    _save_preset_state({"definitions": {}, "hidden": []})
    return {"presets": _preset_payload()}


def _match_tracks_to_youtube(match_id: str, tracks: list[dict]) -> None:
    import yt_dlp

    results: list[dict] = []
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": 8,
    }
    with yt_dlp.YoutubeDL(options) as searcher:
        for index, track in enumerate(tracks, start=1):
            spotify_uri = str(track.get("spotify_uri") or "")
            if spotify_uri.startswith("spotify:track:"):
                try:
                    spotify_metadata = _spotify_source_metadata(
                        "https://open.spotify.com/track/" + spotify_uri.rsplit(":", 1)[-1]
                    )
                    track["artwork_url"] = spotify_metadata.get("thumbnail_url", "")
                except HTTPException:
                    track["artwork_url"] = ""
            query = f"{track['artist']} - {track['title']}"
            info = searcher.extract_info(f"ytsearch8:{query}", download=False) or {}
            entries = info.get("entries") or []
            match, match_score, warnings = _best_youtube_match(track, entries)
            video_id = str(match.get("id") or "")
            results.append(
                {
                    **track,
                    "youtube_title": match.get("title"),
                    "youtube_url": (
                        f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                    ),
                    "youtube_duration": match.get("duration"),
                    "match_score": match_score,
                    "match_warnings": warnings,
                }
            )
            with playlist_match_lock:
                playlist_matches[match_id].update(
                    stage=f"Matching {index} of {len(tracks)}",
                    progress=round(index * 100 / len(tracks), 1),
                    matched=index,
                    total=len(tracks),
                )
    with playlist_match_lock:
        playlist_matches[match_id].update(
            status="complete",
            stage="Playlist matching complete",
            progress=100,
            results=results,
        )


def _match_tokens(value: object) -> set[str]:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode().casefold()
    return set(re.findall(r"[a-z0-9]+", ascii_text))


def _best_youtube_match(track: dict, entries: list[dict]) -> tuple[dict, int, list[str]]:
    expected_title = _match_tokens(track.get("title"))
    expected_artist = _match_tokens(track.get("artist"))
    expected_duration = float(track.get("duration_ms") or 0) / 1000
    expected_all = expected_title | expected_artist
    version_tokens = {"remix", "edit", "rework", "mix", "version", "extended", "original"}
    unwanted = {
        "tutorial",
        "reaction",
        "karaoke",
        "cover",
        "compilation",
        "playlist",
        "slowed",
        "sped",
        "hour",
        "hours",
    }
    best: tuple[float, dict, list[str]] | None = None
    for entry in entries:
        candidate_title = _match_tokens(entry.get("title"))
        candidate_context = (
            candidate_title
            | _match_tokens(entry.get("channel"))
            | _match_tokens(entry.get("uploader"))
        )
        title_coverage = len(expected_title & candidate_title) / max(1, len(expected_title))
        artist_coverage = (
            len(expected_artist & candidate_context) / len(expected_artist)
            if expected_artist
            else 1.0
        )
        extra_bad = (unwanted & candidate_title) - expected_all
        expected_versions = expected_title & version_tokens
        candidate_versions = candidate_title & version_tokens
        version_mismatch = bool(candidate_versions - expected_versions)
        duration = float(entry.get("duration") or 0)
        duration_difference = (
            abs(duration - expected_duration) if duration and expected_duration else 0
        )
        duration_tolerance = max(15.0, expected_duration * 0.12)
        duration_score = (
            max(0.0, 1.0 - duration_difference / max(duration_tolerance, 1.0))
            if duration and expected_duration
            else 0.35
        )
        warnings: list[str] = []
        if title_coverage < 0.7:
            warnings.append("title mismatch")
        if expected_artist and artist_coverage < 0.5:
            warnings.append("artist mismatch")
        if extra_bad:
            warnings.append("non-track upload: " + ", ".join(sorted(extra_bad)))
        if version_mismatch:
            warnings.append("version or remix mismatch")
        if duration and expected_duration and duration_difference > duration_tolerance:
            warnings.append(f"duration differs by {round(duration_difference)}s")
        score = 100 * (0.48 * title_coverage + 0.27 * artist_coverage + 0.25 * duration_score)
        score -= 30 * bool(extra_bad)
        score -= 22 * version_mismatch
        if warnings:
            score -= 8 * len(warnings)
        if best is None or score > best[0]:
            best = (score, entry, warnings)
    if best is None:
        return {}, 0, ["no YouTube results"]
    score, entry, warnings = best
    if score < 48 or "title mismatch" in warnings or "artist mismatch" in warnings:
        return {}, max(0, round(score)), warnings + ["no reliable match selected"]
    if any(warning.startswith("duration differs") for warning in warnings):
        return {}, max(0, round(score)), warnings + ["no reliable match selected"]
    return entry, min(100, max(0, round(score))), warnings


def _spotify_source_metadata(url: str) -> dict:
    track_id_match = re.search(r"open\.spotify\.com/track/([A-Za-z0-9]+)", url)
    if not track_id_match:
        raise HTTPException(400, "Paste a Spotify track link, not an album or playlist link")
    endpoint = "https://open.spotify.com/oembed?" + urlencode({"url": url})
    try:
        response = httpx.get(
            endpoint,
            headers={"User-Agent": "DJ-Library-Studio/1.0"},
            timeout=12,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        raise HTTPException(502, "Spotify metadata could not be loaded") from error
    raw_title = str(payload.get("title") or "").strip()
    title = raw_title
    artist = str(payload.get("author_name") or "").strip()
    for pattern in (r"^(.+?)\s+[–-]\s+song and lyrics by\s+(.+)$", r"^(.+?)\s+by\s+(.+)$"):
        matched = re.match(pattern, raw_title, flags=re.IGNORECASE)
        if matched:
            title, artist = matched.group(1).strip(), matched.group(2).strip()
            break
    return {
        "title": title or "Spotify track",
        "artist": artist,
        "spotify_uri": f"spotify:track:{track_id_match.group(1)}",
        "spotify_url": url,
        "thumbnail_url": str(payload.get("thumbnail_url") or ""),
    }


def _authorized_source_provider(url: str) -> str | None:
    """Return a supported downloadable provider for an explicitly authorized URL."""
    host = (urlparse(url).hostname or "").casefold()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return "youtube"
    if host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}:
        return "soundcloud"
    return None


def _soundcloud_source_metadata(url: str) -> dict:
    """Read public SoundCloud oEmbed metadata without downloading audio."""
    try:
        response = httpx.get(
            "https://soundcloud.com/oembed",
            params={"format": "json", "url": url},
            headers={"User-Agent": "DJ-Library-Studio/1.0"},
            timeout=12,
            follow_redirects=True,
        )
        response.raise_for_status()
        info = response.json()
    except Exception as error:
        raise HTTPException(502, "SoundCloud metadata could not be loaded") from error
    return {
        "source_type": "soundcloud",
        "title": str(info.get("title") or "SoundCloud track").strip(),
        "artist": str(info.get("author_name") or "").strip(),
        "thumbnail_url": str(info.get("thumbnail_url") or ""),
        "duration": None,
        "soundcloud_url": url,
    }


@app.post("/api/imports/source-match")
def match_single_source(request: SourceMatchRequest) -> dict:
    host = (urlparse(request.url).hostname or "").casefold()
    if host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}:
        return _soundcloud_source_metadata(request.url)
    if host not in {"open.spotify.com", "www.open.spotify.com"}:
        raise HTTPException(400, "Source matching accepts Spotify or SoundCloud track links")
    metadata = _spotify_source_metadata(request.url)
    try:
        import yt_dlp
    except ImportError as error:
        raise HTTPException(500, "yt-dlp is not installed") from error
    query = " - ".join(part for part in (metadata["artist"], metadata["title"]) if part)
    with yt_dlp.YoutubeDL(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": 8,
        }
    ) as searcher:
        info = searcher.extract_info(f"ytsearch8:{query}", download=False) or {}
    match, score, warnings = _best_youtube_match(metadata, info.get("entries") or [])
    video_id = str(match.get("id") or "")
    if not metadata["artist"] and match:
        metadata["artist"] = str(match.get("channel") or match.get("uploader") or "").strip()
    return {
        **metadata,
        "youtube_title": match.get("title"),
        "youtube_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "youtube_duration": match.get("duration"),
        "match_score": score,
        "match_warnings": warnings,
    }


def _playlist_csv_tracks(contents: bytes) -> list[dict]:
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Playlist CSV must use UTF-8 text encoding") from error
    reader = csv.DictReader(io.StringIO(text))
    fields = {field.casefold().strip(): field for field in (reader.fieldnames or [])}
    title_field = next(
        (fields[name] for name in ("track name", "title", "name") if name in fields),
        None,
    )
    artist_field = next(
        (
            fields[name]
            for name in ("artist name(s)", "artist name", "artists", "artist")
            if name in fields
        ),
        None,
    )
    if title_field is None or artist_field is None:
        raise ValueError(
            "CSV needs track and artist columns, such as Track Name and Artist Name(s)"
        )
    duration_field = fields.get("duration (ms)") or fields.get("duration_ms")
    tracks: list[dict] = []
    for row in reader:
        title = str(row.get(title_field) or "").strip()
        artist = str(row.get(artist_field) or "").strip().replace(";", ", ")
        if not title or not artist:
            continue
        duration = str(row.get(duration_field) or "").strip() if duration_field else ""
        genre = str(row.get(fields.get("genres", "")) or "").strip()
        tracks.append(
            {
                "title": title,
                "artist": artist,
                "duration_ms": int(duration) if duration.isdigit() else None,
                "genre": genre,
                "genre_category": _generalized_genre(genre),
                "tempo": str(row.get(fields.get("tempo", "")) or "").strip(),
                "spotify_uri": str(row.get(fields.get("track uri", "")) or "").strip(),
            }
        )
    if not tracks:
        raise ValueError("The playlist CSV does not contain any usable tracks")
    return tracks


def _csv_match_worker(match_id: str, tracks: list[dict]) -> None:
    try:
        _match_tracks_to_youtube(match_id, tracks)
    except Exception as error:
        with playlist_match_lock:
            playlist_matches[match_id].update(
                status="failed", stage="Playlist matching failed", error=str(error)
            )


@app.get("/api/imports/playlist-matches/{match_id}")
def playlist_match_status(match_id: str) -> dict:
    with playlist_match_lock:
        state = playlist_matches.get(match_id)
        if state is None:
            raise HTTPException(404, "Playlist match job not found")
        return dict(state)


def _safe_audio_name(value: str) -> str:
    cleaned = "".join(character for character in value if character not in '<>:"/\\|?*')
    return cleaned.strip()[:180] or "Imported Audio"


def _generalized_genre(value: str) -> str:
    """Map detailed Spotify-style genres to practical, broad DJ library folders."""
    genre = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode()
        .casefold()
    )
    electronic_families = (
        ("Techno / Schranz", ("schranz",)),
        ("Techno / Hard Techno", ("hard techno",)),
        ("Techno / Acid Techno", ("acid techno",)),
        ("Techno / Melodic Techno", ("melodic techno",)),
        ("Techno / Minimal Techno", ("minimal techno", "minimal tech")),
        ("Techno / Industrial Techno", ("industrial techno",)),
        ("Techno / Hypnotic Techno", ("hypnotic techno", "dub techno")),
        ("Techno / Peak-Time Techno", ("peak time techno", "peak-time techno")),
        ("Techno / Techno", ("techno", "tekno", "rave")),
        ("House / Afro House", ("afro house",)),
        ("House / Latin House", ("latin house", "tribal house", "guaracha")),
        ("House / Deep House", ("deep house",)),
        ("House / Tech House", ("tech house",)),
        ("House / Progressive House", ("progressive house",)),
        ("House / Melodic House", ("melodic house",)),
        ("House / Organic House", ("organic house",)),
        ("House / Bass House", ("bass house",)),
        ("House / Soulful House", ("soulful house",)),
        ("House / Funky House", ("funky house", "disco house")),
        ("House / Amapiano", ("amapiano",)),
        ("House / House", ("house",)),
        ("Bass / Future Bass", ("future bass",)),
        ("Bass / Dubstep", ("dubstep",)),
        ("Bass / Moombahton", ("moombahton",)),
        (
            "Bass / Phonk",
            (
                "drift phonk",
                "phonk",
            ),
        ),
        ("Bass / Deep Bass", ("deep bass", "bass music")),
        ("Drum & Bass / Liquid", ("liquid drum and bass", "liquid dnb")),
        ("Drum & Bass / Jungle", ("jungle",)),
        ("Drum & Bass / Drum & Bass", ("drum and bass", "drum & bass", "dnb")),
        ("Trance / Psytrance", ("psytrance", "psy trance")),
        ("Trance / Hard Trance", ("hard trance",)),
        ("Trance / Trance", ("trance",)),
        ("Garage / UK Garage", ("uk garage", "ukg", "2-step", "2 step")),
        ("Garage / Garage", ("garage",)),
        ("Breaks / Big Beat", ("big beat",)),
        ("Breaks / Breakbeat", ("breakbeat", "breaks", "broken beat")),
        ("Downtempo / Trip Hop", ("trip hop",)),
        ("Hardcore / Gabber", ("gabber",)),
        ("Hardcore / Hardstyle", ("hardstyle",)),
        ("Hardcore / Hardcore", ("hardcore",)),
        ("Electronic / Electro", ("electro",)),
    )
    latin_families = (
        ("Reggaeton", ("reggaeton", "reggaetón", "urbano latino", "latin urban")),
        ("Reggaeton", ("neoperreo",)),
        ("Salsa", ("salsa", "timba", "son cubano", "mambo")),
        ("Cumbia", ("cumbia", "chicha", "tecnocumbia")),
        ("Merengue", ("merengue", "perico ripiao", "merengue urbano")),
        ("Zapateado", ("zapateado", "duranguense", "huapango", "quebradita")),
        ("Corridos", ("corrido", "corridos", "corridos tumbados")),
        (
            "Regional Mexican",
            (
                "regional mexican",
                "musica mexicana",
                "banda",
                "norteno",
                "sierreno",
                "ranchera",
                "mariachi",
            ),
        ),
        ("Bachata", ("bachata",)),
        ("Dembow", ("dembow",)),
        ("Latin Pop", ("latin pop", "pop latino")),
        ("Latin Jazz", ("latin jazz", "afro-cuban jazz", "afro cuban jazz")),
        ("Bolero", ("bolero",)),
        ("Vallenato", ("vallenato",)),
        ("Brazilian", ("brazilian", "funk carioca", "baile funk", "samba", "pagode")),
        ("Flamenco", ("flamenco",)),
        ("Latin Rock", ("rock en espanol", "rock en español", "latin rock", "mexican rock")),
        ("Latin Indie", ("latin indie", "mexican indie", "latin alternative")),
        ("Latin Ska", ("mexican ska", "latin ska")),
        ("Latin Hip-Hop", ("latin hip hop", "mexican hip hop")),
        ("Latin R&B", ("latin r&b",)),
    )
    latin_matches = [
        (genre.find(term), family)
        for family, terms in latin_families
        for term in terms
        if term in genre
    ]
    if latin_matches:
        return f"Latin / {min(latin_matches, key=lambda match: match[0])[1]}"
    electronic_matches = [
        (genre.find(term), family)
        for family, terms in electronic_families
        for term in terms
        if term in genre
        and (term != "electro" or re.search(r"(?<![a-z0-9])electro(?![a-z0-9])", genre))
    ]
    if electronic_matches:
        return f"Electronic / {electronic_matches[0][1]}"
    families = (
        ("Hip-Hop & Rap / Crunk", ("crunk",)),
        ("Hip-Hop & Rap / Hyphy", ("hyphy",)),
        ("Hip-Hop & Rap", ("hip hop", "hip-hop", "rap", "trap")),
        ("R&B & Soul", ("r&b", "rnb", "soul")),
        ("Disco & Funk", ("disco", "funk")),
        ("Rock & Alternative", ("rock", "indie", "alternative", "punk", "metal")),
        ("Pop / Chanson", ("chanson", "variete francaise", "variété française")),
        ("Pop", ("pop",)),
        ("Ambient & Chill", ("ambient", "downtempo", "chill", "lo-fi", "lofi")),
        ("Afro & Amapiano", ("afro", "afrobeats")),
    )
    matched = next(
        (family for family, terms in families if any(term in genre for term in terms)), ""
    )
    if matched:
        return matched
    if any(term in genre for term in ("latin", "latino", "musica mexicana")):
        return "Latin / Other"
    if any(term in genre for term in ("electronic", "edm", "dance", "big room")):
        return "Electronic / General"
    return "Other"


LATIN_SUBGENRES = {
    "reggaeton",
    "salsa",
    "cumbia",
    "merengue",
    "zapateado",
    "corridos",
    "regional mexican",
    "bachata",
    "dembow",
    "latin house",
    "latin pop",
    "latin jazz",
    "bolero",
    "vallenato",
    "brazilian",
    "flamenco",
    "latin rock",
    "latin indie",
    "latin ska",
    "latin hip-hop",
    "latin r&b",
}

LEGACY_ELECTRONIC_CATEGORIES = {
    "techno": "Electronic / Techno / Techno",
    "house": "Electronic / House / House",
    "trance": "Electronic / Trance / Trance",
    "drum & bass": "Electronic / Drum & Bass / Drum & Bass",
    "garage": "Electronic / Garage / Garage",
    "breaks": "Electronic / Breaks / Breakbeat",
    "electronic": "Electronic / Electronic / Electronic",
}


def _normalize_genre_category(value: str) -> str:
    """Normalize user and importer categories into the on-disk folder taxonomy."""
    cleaned = str(value or "Other").strip()
    legacy_electronic = LEGACY_ELECTRONIC_CATEGORIES.get(cleaned.casefold())
    if legacy_electronic:
        return legacy_electronic
    if cleaned.casefold() in {"electronic / electronic / electronic", "electronic / general"}:
        return "Electronic / General"
    if cleaned.casefold() == "latin & reggaeton":
        return "Latin / Other"
    is_latin_path = cleaned.casefold().startswith("latin / ")
    lowered = cleaned.casefold().removeprefix("latin / ").strip()
    if is_latin_path and lowered == "other":
        return "Latin / Other"
    if lowered in LATIN_SUBGENRES:
        label = lowered.title()
        label = {"Reggaeton": "Reggaeton", "Dembow": "Dembow"}.get(label, label)
        return f"Latin / {label}"
    parts = [part.strip() for part in cleaned.split(" / ") if part.strip()]
    return " / ".join(_safe_folder_name(part) for part in parts) or "Other"


def _genre_path_parts(category: str) -> tuple[str, ...]:
    normalized = _normalize_genre_category(category)
    return tuple(_safe_folder_name(part) for part in normalized.split(" / "))


def _genre_directory(category: str) -> Path:
    return _music_library_root().joinpath(*_genre_path_parts(category))


def _catalog_genre_category(wav_path: Path, stored_category: str, detailed_genre: str) -> str:
    """Resolve catalog genre without overwriting a user's folder choice."""
    stored = _normalize_genre_category(stored_category or "Other")
    if not detailed_genre.strip() and stored in {"Other", "Latin / Other"}:
        return "Other"
    inferred = _generalized_genre(detailed_genre)
    if stored == "Latin / Other" and inferred == "Other":
        stored = "Other"
    try:
        relative = wav_path.resolve().relative_to(_music_library_root())
        folder_parts = relative.parts[:-1]
        if folder_parts and folder_parts[0] != ".audioextender":
            path_category = _normalize_genre_category(" / ".join(folder_parts))
            if path_category == "Latin / Other" and inferred != "Latin / Other":
                return inferred
            return path_category
    except (ValueError, OSError):
        pass
    if stored not in {"Other", "Latin / Other"}:
        return stored
    return inferred if inferred != "Other" else stored


def _safe_folder_name(value: str) -> str:
    return _safe_audio_name(value).strip(". ") or "Imported Playlist"


def _cataloged_download_by_youtube_id(video_id: str) -> dict | None:
    """Find an available master file for a recording already in the catalog."""
    if not video_id:
        return None
    return next(
        (
            track
            for track in track_catalog_repository.list_downloaded_tracks()
            if track.get("youtube_id") == video_id
            and Path(str(track.get("file_path") or "")).is_file()
        ),
        None,
    )


def _migrate_downloaded_catalog(
    *,
    incremental: bool = False,
    progress: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, int]:
    """Catalog source records, skipping unchanged files during reconciliation."""
    roots = [OUTPUT / "wav" / "imports", OUTPUT / "wav" / "creative-commons"]
    try:
        configured_root = _music_library_root()
        roots.append(configured_root)
    except ValueError:
        pass
    records: list[tuple[Path, bool]] = []
    for root in roots:
        if not root.exists():
            continue
        records.extend((record, True) for record in root.rglob("*.source.json"))
    metadata_root = _music_library_root() / ".audioextender" / "sources"
    if metadata_root.exists():
        records.extend((record, False) for record in metadata_root.glob("*.json"))
    known = track_catalog_repository.catalog_source_signatures() if incremental else {}
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
        if track_catalog_repository.downloaded_track_is_excluded(wav_path):
            results["skipped"] += 1
            results["processed"] = index
            signatures.append((source_key, *signature))
            if progress:
                progress(dict(results))
            continue
        playlist_name = str(metadata.get("playlist_name") or "Legacy Imports")
        stored_category = str(metadata.get("genre_category") or "")
        detailed_genre = str(metadata.get("genre") or "")
        category = _catalog_genre_category(wav_path, stored_category, detailed_genre)
        track_catalog_repository.upsert_downloaded_track(
            title=str(metadata.get("title") or wav_path.stem),
            artist=str(metadata.get("artist") or ""),
            file_path=wav_path,
            genre=detailed_genre,
            genre_category=category,
            youtube_id=str(metadata.get("youtube_id") or ""),
            youtube_url=str(metadata.get("youtube_url") or ""),
            playlist_name=playlist_name,
        )
        results["updated"] += 1
        results["processed"] = index
        signatures.append((source_key, *signature))
        if legacy_record and wav_path.is_relative_to(_music_library_root()):
            _write_source_metadata(wav_path, metadata)
            source_record.unlink(missing_ok=True)
        if progress:
            progress(dict(results))
    track_catalog_repository.upsert_catalog_source_signatures(signatures)
    return results


def _ensure_downloaded_catalog_migrated() -> None:
    """Run legacy migration once per schema version, not once per restart."""
    global downloaded_catalog_migrated
    if downloaded_catalog_migrated:
        return
    with downloaded_catalog_migration_lock:
        if downloaded_catalog_migrated:
            return
        if (
            settings_repository.get_system_state("downloaded_catalog_migration")
            != DOWNLOADED_CATALOG_MIGRATION_VERSION
        ):
            _migrate_downloaded_catalog()
            settings_repository.set_system_state(
                "downloaded_catalog_migration", DOWNLOADED_CATALOG_MIGRATION_VERSION
            )
        downloaded_catalog_migrated = True


def _cache_track_artwork(artwork_url: str, destination: Path) -> str:
    """Cache trusted provider artwork and embed it in a WAV when possible."""
    if not artwork_url:
        return ""
    artwork_host = (urlparse(artwork_url).hostname or "").casefold()
    trusted_artwork = artwork_host in {
        "image-cdn-ak.spotifycdn.com",
        "i.scdn.co",
        "i.ytimg.com",
    } or artwork_host.endswith(".sndcdn.com")
    if not trusted_artwork:
        return ""
    try:
        response = httpx.get(artwork_url, timeout=15, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        if content_type not in {"image/jpeg", "image/png"} or len(response.content) > 8_000_000:
            return ""
        artwork_dir = _music_library_root() / ".artwork"
        artwork_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if content_type == "image/png" else ".jpg"
        artwork_file = (
            artwork_dir / f"{hashlib.sha256(artwork_url.encode()).hexdigest()[:24]}{suffix}"
        )
        artwork_file.write_bytes(response.content)
        embed_wav_artwork(destination, artwork_file, content_type)
        return str(artwork_file)
    except Exception:
        return ""


def _creative_commons_worker(
    batch_id: str, tracks: list[CreativeCommonsMatch], playlist_name: str
) -> None:
    report: dict[str, list[dict]] = {
        "downloaded": [],
        "already_downloaded": [],
        "skipped_not_creative_commons": [],
        "failed": [],
    }
    safe_playlist = _safe_folder_name(playlist_name)
    destination_dir = _music_library_root()
    report_dir = OUTPUT / "reports" / "imports" / safe_playlist
    destination_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yt_dlp

        for index, track in enumerate(tracks, start=1):
            base = track.model_dump()
            track_playlist = track.playlist_name or playlist_name
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as inspector:
                    info = inspector.extract_info(track.url, download=False) or {}
                license_name = str(info.get("license") or "").strip()
                video_id = str(info.get("id") or "").strip()
                artwork_url = track.artwork_url or (
                    f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""
                )
                base.update(license=license_name, youtube_id=video_id, artwork_url=artwork_url)
                # if "creative commons" not in license_name.casefold():
                #    report["skipped_not_creative_commons"].append(base)
                # else:
                category = (
                    _generalized_genre(track.genre)
                    if track.genre
                    else _normalize_genre_category(track.genre_category)
                )
                base.update(genre=track.genre, genre_category=category)
                output_name = _safe_audio_name(f"{track.artist} - {track.title}") + ".wav"
                existing_download = _cataloged_download_by_youtube_id(video_id)
                if existing_download:
                    destination = Path(existing_download["file_path"])
                    category = str(existing_download.get("genre_category") or category)
                    base.update(
                        filename=destination.name,
                        genre_category=category,
                    )
                    report["already_downloaded"].append(base)
                else:
                    category_dir = destination_dir.joinpath(*_genre_path_parts(category))
                    category_dir.mkdir(parents=True, exist_ok=True)
                    destination = category_dir / output_name
                    source_record = _source_metadata_path(destination)
                    recorded_video_id = ""
                    if source_record.exists():
                        try:
                            recorded_video_id = str(
                                json.loads(source_record.read_text(encoding="utf-8")).get(
                                    "youtube_id", ""
                                )
                            )
                        except (OSError, json.JSONDecodeError):
                            recorded_video_id = ""
                    if destination.exists() and recorded_video_id == video_id:
                        base["filename"] = output_name
                        report["already_downloaded"].append(base)
                        track_catalog_repository.upsert_downloaded_track(
                            title=track.title,
                            artist=track.artist,
                            file_path=destination,
                            genre=track.genre,
                            genre_category=category,
                            spotify_uri=track.spotify_uri,
                            youtube_id=video_id,
                            youtube_url=track.url,
                            duration_seconds=float(info.get("duration") or 0) or None,
                            artwork_url=artwork_url,
                            artwork_path=_cache_track_artwork(artwork_url, destination),
                            playlist_name=track_playlist,
                        )
                        jobs_repository.resolve_import_failure(
                            playlist_name=track_playlist, title=track.title, artist=track.artist
                        )
                        continue
                    if destination.exists():
                        original_stem = destination.stem
                        copy_number = 2
                        while destination.exists():
                            destination = destination.with_name(
                                f"{original_stem} ({copy_number}){destination.suffix}"
                            )
                            copy_number += 1
                        output_name = destination.name
                        source_record = _source_metadata_path(destination)
                    with tempfile.TemporaryDirectory(
                        prefix="audioextender-cc-import-"
                    ) as temporary:
                        options = {
                            "format": "bestaudio/best",
                            "outtmpl": str(Path(temporary) / "source.%(ext)s"),
                            "noplaylist": True,
                            "quiet": True,
                            "no_warnings": True,
                            "postprocessors": [
                                {"key": "FFmpegExtractAudio", "preferredcodec": "wav"}
                            ],
                        }
                        with yt_dlp.YoutubeDL(options) as downloader:
                            downloader.extract_info(track.url, download=True)
                        wavs = list(Path(temporary).glob("*.wav"))
                        if not wavs:
                            raise RuntimeError("YouTube audio could not be converted to WAV")
                        shutil.move(str(wavs[0]), destination)
                    write_wav_metadata(
                        destination,
                        title=track.title,
                        artist=track.artist,
                        genre=category,
                        album=track_playlist,
                    )
                    _write_source_metadata(
                        destination,
                        {
                            "youtube_id": video_id,
                            "youtube_url": track.url,
                            "title": track.title,
                            "artist": track.artist,
                            "playlist_name": track_playlist,
                            "genre": track.genre,
                            "genre_category": category,
                            "artwork_url": artwork_url,
                        },
                    )
                    base["filename"] = output_name
                    report["downloaded"].append(base)
                track_catalog_repository.upsert_downloaded_track(
                    title=track.title,
                    artist=track.artist,
                    file_path=destination,
                    genre=track.genre,
                    genre_category=category,
                    spotify_uri=track.spotify_uri,
                    youtube_id=video_id,
                    youtube_url=track.url,
                    duration_seconds=float(info.get("duration") or 0) or None,
                    artwork_url=artwork_url,
                    artwork_path=_cache_track_artwork(artwork_url, destination),
                    playlist_name=track_playlist,
                )
                jobs_repository.resolve_import_failure(
                    playlist_name=track_playlist, title=track.title, artist=track.artist
                )
            except Exception as error:
                report["failed"].append({**base, "error": str(error)})
                jobs_repository.record_import_failure(
                    playlist_name=track_playlist,
                    title=track.title,
                    artist=track.artist,
                    spotify_uri=track.spotify_uri,
                    youtube_url=track.url,
                    error=str(error),
                )
            with creative_commons_batch_lock:
                creative_commons_batches[batch_id].update(
                    stage=f"Verified {index} of {len(tracks)}",
                    progress=round(index * 100 / len(tracks), 1),
                    counts={key: len(value) for key, value in report.items()},
                )
        included = report["downloaded"] + report["already_downloaded"]
        report_path = report_dir / f"{safe_playlist} - Import Report.json"
        genre_summary: dict[str, int] = {}
        for item in included:
            category = item.get("genre_category", "Other")
            genre_summary[category] = genre_summary.get(category, 0) + 1
        report_document = {
            "playlist_name": playlist_name,
            "export_folder": str(destination_dir),
            "genre_summary": dict(sorted(genre_summary.items())),
            "results": report,
        }
        report_path.write_text(json.dumps(report_document, indent=2), encoding="utf-8")
        with creative_commons_batch_lock:
            creative_commons_batches[batch_id].update(
                status="complete",
                stage="Download complete",
                progress=100,
                counts={key: len(value) for key, value in report.items()},
                report=report,
                genre_summary=dict(sorted(genre_summary.items())),
                report_path=str(report_path),
            )
    except Exception as error:
        with creative_commons_batch_lock:
            creative_commons_batches[batch_id].update(
                status="failed", stage="Batch import failed", error=str(error)
            )


@app.post("/api/imports/creative-commons", status_code=202)
def create_creative_commons_batch(request: CreativeCommonsBatchRequest) -> dict:
    allowed_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
    if any(
        (urlparse(track.url).hostname or "").casefold() not in allowed_hosts
        for track in request.tracks
    ):
        raise HTTPException(400, "Every batch item must use a YouTube URL")
    batch_id = uuid.uuid4().hex
    with creative_commons_batch_lock:
        creative_commons_batches[batch_id] = {
            "id": batch_id,
            "status": "processing",
            "stage": "Preparing Creative Commons verification",
            "progress": 0,
            "counts": {},
            "playlist_name": request.playlist_name,
        }
    threading.Thread(
        target=_creative_commons_worker,
        args=(batch_id, request.tracks, request.playlist_name),
        daemon=True,
    ).start()
    return {"batch_id": batch_id}


@app.get("/api/imports/creative-commons/{batch_id}")
def creative_commons_batch_status(batch_id: str) -> dict:
    with creative_commons_batch_lock:
        state = creative_commons_batches.get(batch_id)
        if state is None:
            raise HTTPException(404, "Creative Commons import not found")
        return {key: value for key, value in state.items() if not key.endswith("_path")}


@app.get("/api/imports/creative-commons/{batch_id}/download")
def download_creative_commons_batch(batch_id: str) -> FileResponse:
    with creative_commons_batch_lock:
        state = creative_commons_batches.get(batch_id)
        playlist_name = (
            str(state.get("playlist_name") or "Imported Playlist") if state else "Imported Playlist"
        )
        report_data = dict(state.get("report") or {}) if state else {}
    included = list(report_data.get("downloaded") or []) + list(
        report_data.get("already_downloaded") or []
    )
    if not included:
        raise HTTPException(404, "No verified Creative Commons WAV files are available")
    safe_playlist = _safe_folder_name(playlist_name)
    temporary = tempfile.NamedTemporaryFile(
        prefix=f"{safe_playlist}-", suffix="-WAVs.zip", delete=False
    )
    temporary.close()
    path = Path(temporary.name)
    added = 0
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in included:
                category = str(item.get("genre_category") or "Other")
                catalog_track = _cataloged_download_by_youtube_id(str(item.get("youtube_id") or ""))
                source = (
                    Path(str(catalog_track.get("file_path")))
                    if catalog_track
                    else _music_library_root().joinpath(
                        *_genre_path_parts(category), str(item.get("filename") or "")
                    )
                )
                if catalog_track:
                    category = str(catalog_track.get("genre_category") or category)
                if not source.is_file():
                    continue
                category_path = "/".join(_genre_path_parts(category))
                archive.write(source, arcname=f"{safe_playlist}/{category_path}/{source.name}")
                added += 1
        if not added:
            path.unlink(missing_ok=True)
            raise HTTPException(404, "The imported WAV files are no longer available")
        return FileResponse(
            path,
            filename=f"{safe_playlist} - WAVs.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.get("/api/imports/creative-commons/{batch_id}/report")
def download_creative_commons_report(batch_id: str) -> FileResponse:
    with creative_commons_batch_lock:
        state = creative_commons_batches.get(batch_id)
        path = Path(state["report_path"]) if state and state.get("report_path") else None
    if path is None or not path.exists():
        raise HTTPException(404, "Creative Commons import report is not available")
    with creative_commons_batch_lock:
        playlist_name = str(
            creative_commons_batches.get(batch_id, {}).get("playlist_name") or "Imported Playlist"
        )
    return FileResponse(path, filename=f"{_safe_folder_name(playlist_name)} - Import Report.json")


@app.get("/api/imports/failures")
def list_import_failures() -> dict:
    if not jobs_repository.list_import_failures(include_resolved=True):
        for report_path in (OUTPUT / "reports" / "imports").glob("**/*Import Report.json"):
            try:
                document = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            playlist_name = str(document.get("playlist_name") or report_path.parent.name)
            for item in (document.get("results") or {}).get("failed", []):
                jobs_repository.record_import_failure(
                    playlist_name=playlist_name,
                    title=str(item.get("title") or item.get("filename") or "Unknown track"),
                    artist=str(item.get("artist") or ""),
                    spotify_uri=str(item.get("spotify_uri") or ""),
                    youtube_url=str(item.get("url") or item.get("youtube_url") or ""),
                    error=str(item.get("error") or "Download failed"),
                )
    failures = jobs_repository.list_import_failures()
    return {"failures": failures, "total": len(failures)}


def _original_import_metadata(playlist_name: str, title: str, artist: str) -> dict[str, str]:
    """Recover source metadata from the first playlist report for a failed track."""
    report_root = OUTPUT / "reports" / "imports"
    wanted_title = title.strip().casefold()
    wanted_artist = artist.strip().casefold()
    preferred = report_root / _safe_folder_name(playlist_name)
    candidates = [*preferred.glob("*Import Report.json")]
    candidates.extend(
        path
        for path in report_root.glob("**/*Import Report.json")
        if path.parent != preferred and path.parent.name != "Retry imports"
    )
    for report_path in candidates:
        try:
            document = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for section in ("failed", "downloaded", "already_downloaded"):
            for item in (document.get("results") or {}).get(section, []):
                if (
                    str(item.get("title") or "").strip().casefold() == wanted_title
                    and str(item.get("artist") or "").strip().casefold() == wanted_artist
                ):
                    genre = str(item.get("genre") or "").strip()
                    category = str(item.get("genre_category") or "").strip()
                    return {
                        "genre": genre,
                        "genre_category": (
                            _generalized_genre(genre)
                            if genre
                            else _normalize_genre_category(category or "Other")
                        ),
                    }
    return {"genre": "", "genre_category": "Other"}


def _retry_import_failures_worker(batch_id: str, failures: list[dict]) -> None:
    """Refresh failed source matches, then reuse the normal batch downloader."""
    try:
        import yt_dlp

        tracks: list[CreativeCommonsMatch] = []
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": 8,
            "socket_timeout": 15,
            "retries": 1,
            "extractor_retries": 1,
        }
        with yt_dlp.YoutubeDL(options) as searcher:
            for index, failure in enumerate(failures, start=1):
                query = " - ".join(
                    part
                    for part in (str(failure.get("artist") or ""), str(failure.get("title") or ""))
                    if part
                )
                old_url = str(failure.get("youtube_url") or "")
                old_id_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]+)", old_url)
                old_id = old_id_match.group(1) if old_id_match else ""
                info = searcher.extract_info(f"ytsearch8:{query}", download=False) or {}
                entries = [
                    entry
                    for entry in (info.get("entries") or [])
                    if str(entry.get("id") or "") != old_id
                ]
                match, _, _ = _best_youtube_match(failure, entries)
                video_id = str(match.get("id") or "")
                source_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else old_url
                if not source_url:
                    jobs_repository.record_import_failure(
                        playlist_name=str(failure.get("playlist_name") or "Imported Playlist"),
                        title=str(failure.get("title") or "Unknown track"),
                        artist=str(failure.get("artist") or ""),
                        spotify_uri=str(failure.get("spotify_uri") or ""),
                        youtube_url="",
                        error="No reliable replacement source was found",
                    )
                    continue
                artwork_url = ""
                spotify_uri = str(failure.get("spotify_uri") or "")
                if spotify_uri.startswith("spotify:track:"):
                    try:
                        artwork_url = str(
                            _spotify_source_metadata(
                                "https://open.spotify.com/track/" + spotify_uri.rsplit(":", 1)[-1]
                            ).get("thumbnail_url")
                            or ""
                        )
                    except HTTPException:
                        pass
                original_metadata = _original_import_metadata(
                    str(failure.get("playlist_name") or "Imported Playlist"),
                    str(failure.get("title") or "Unknown track"),
                    str(failure.get("artist") or "Unknown artist"),
                )
                tracks.append(
                    CreativeCommonsMatch(
                        url=source_url,
                        title=str(failure.get("title") or "Unknown track"),
                        artist=str(failure.get("artist") or "Unknown artist"),
                        spotify_uri=spotify_uri,
                        genre=original_metadata["genre"],
                        genre_category=original_metadata["genre_category"],
                        artwork_url=artwork_url,
                        playlist_name=str(failure.get("playlist_name") or "Imported Playlist"),
                    )
                )
                with creative_commons_batch_lock:
                    creative_commons_batches[batch_id].update(
                        stage=f"Refreshing sources {index} of {len(failures)}",
                        progress=round(index * 25 / max(1, len(failures)), 1),
                    )
        if not tracks:
            with creative_commons_batch_lock:
                creative_commons_batches[batch_id].update(
                    status="complete",
                    stage="No retryable sources were found",
                    progress=100,
                    counts={"downloaded": 0, "already_downloaded": 0, "failed": len(failures)},
                )
            return
        _creative_commons_worker(batch_id, tracks, "Retry imports")
    except Exception as error:
        with creative_commons_batch_lock:
            creative_commons_batches[batch_id].update(
                status="failed", stage="Retry preparation failed", error=str(error)
            )


@app.post("/api/imports/failures/retry", status_code=202)
def retry_import_failures(request: ImportFailureRetryRequest) -> dict:
    _require_music_library_online()
    wanted = set(request.failure_ids)
    failures = [
        item for item in jobs_repository.list_import_failures() if int(item["id"]) in wanted
    ]
    if len(failures) != len(wanted):
        raise HTTPException(404, "One or more import issues are no longer available")
    batch_id = uuid.uuid4().hex
    with creative_commons_batch_lock:
        creative_commons_batches[batch_id] = {
            "id": batch_id,
            "status": "processing",
            "stage": "Preparing retries",
            "progress": 0,
            "counts": {},
            "playlist_name": "Retry imports",
        }
    threading.Thread(
        target=_retry_import_failures_worker,
        args=(batch_id, failures),
        daemon=True,
        name=f"import-retry-{batch_id[:8]}",
    ).start()
    return {"batch_id": batch_id, "retry_count": len(failures)}


@app.delete("/api/imports/failures/{failure_id}")
def dismiss_import_failure(failure_id: int) -> dict:
    failures = jobs_repository.list_import_failures(include_resolved=True)
    failure = next((item for item in failures if int(item["id"]) == failure_id), None)
    if failure is None:
        raise HTTPException(404, "Import failure not found")
    jobs_repository.resolve_import_failure(
        playlist_name=str(failure["playlist_name"]),
        title=str(failure["title"]),
        artist=str(failure["artist"]),
    )
    return {"resolved": True, "id": failure_id}


def _probe_local_audio(path: Path) -> dict:
    """Read common file tags without decoding the complete recording."""
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout or "{}")
    format_data = payload.get("format") or {}
    tags = {
        str(key).casefold(): str(value).strip()
        for key, value in (format_data.get("tags") or {}).items()
    }
    stem = path.stem
    pieces = [piece.strip() for piece in stem.split(" - ", 1)]
    artist = tags.get("artist", "") or (pieces[0] if len(pieces) == 2 else "")
    title = tags.get("title", "") or (pieces[1] if len(pieces) == 2 else stem)
    genre = tags.get("genre", "")
    try:
        duration = float(format_data.get("duration") or 0) or None
    except (TypeError, ValueError):
        duration = None
    return {"title": title, "artist": artist, "genre": genre, "duration": duration}


def _local_audio_import_worker(batch_id: str, staged_dir: Path, playlist_name: str) -> None:
    files = [path for path in staged_dir.rglob("*") if path.is_file()]
    results: list[dict] = []
    imported = skipped = failed = 0
    try:
        existing = track_catalog_repository.list_downloaded_tracks()
        known = {
            (str(track.get("artist") or "").casefold(), str(track.get("title") or "").casefold())
            for track in existing
            if Path(str(track.get("file_path") or "")).is_file()
        }
        for index, source in enumerate(files, start=1):
            with local_import_batch_lock:
                local_import_batches[batch_id].update(
                    stage=f"Converting {source.name}",
                    progress=round(100 * (index - 1) / max(1, len(files)), 1),
                )
            try:
                metadata = _probe_local_audio(source)
                identity = (metadata["artist"].casefold(), metadata["title"].casefold())
                if identity in known:
                    skipped += 1
                    results.append({"filename": source.name, "status": "duplicate", **metadata})
                    continue
                category = _generalized_genre(metadata["genre"])
                destination_dir = _genre_directory(category)
                destination_dir.mkdir(parents=True, exist_ok=True)
                display_name = " - ".join(
                    value for value in (metadata["artist"], metadata["title"]) if value
                )
                destination = (
                    destination_dir / f"{_safe_audio_name(display_name or source.stem)}.wav"
                )
                counter = 2
                while destination.exists():
                    destination = (
                        destination_dir
                        / f"{_safe_audio_name(display_name or source.stem)} ({counter}).wav"
                    )
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
                write_wav_metadata(
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
                _write_source_metadata(destination, source_metadata)
                track_catalog_repository.upsert_downloaded_track(
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
        with local_import_batch_lock:
            local_import_batches[batch_id].update(
                status="complete",
                stage="Local playlist import complete",
                progress=100,
                counts={"imported": imported, "duplicates": skipped, "failed": failed},
                results=results,
            )
    except Exception as error:
        with local_import_batch_lock:
            local_import_batches[batch_id].update(
                status="failed", stage="Local import failed", error=str(error)
            )
    finally:
        shutil.rmtree(staged_dir, ignore_errors=True)


@app.post("/api/imports/local-audio", status_code=202)
async def create_local_audio_import(
    files: Annotated[list[UploadFile], File()],
    playlist_name: Annotated[str, Form()] = "Local Playlist",
) -> dict:
    if not files or len(files) > 1000:
        raise HTTPException(400, "Choose between 1 and 1000 audio files")
    supported = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav", ".aiff", ".aif"}
    invalid = [
        file.filename or "unnamed"
        for file in files
        if Path(file.filename or "").suffix.casefold() not in supported
    ]
    if invalid:
        raise HTTPException(400, f"Unsupported audio file: {invalid[0]}")
    batch_id = uuid.uuid4().hex
    safe_playlist = _safe_folder_name(playlist_name or "Local Playlist")
    staged_dir = INPUT / "local-imports" / batch_id
    staged_dir.mkdir(parents=True, exist_ok=True)
    for index, upload in enumerate(files):
        name = _safe_audio_name(Path(upload.filename or f"Track {index + 1}").name)
        destination = staged_dir / f"{index:04d}-{name}"
        with destination.open("wb") as target:
            shutil.copyfileobj(upload.file, target)
        await upload.close()
    with local_import_batch_lock:
        local_import_batches[batch_id] = {
            "id": batch_id,
            "status": "processing",
            "stage": f"Staged {len(files)} audio files",
            "progress": 0,
            "playlist_name": safe_playlist,
            "total": len(files),
            "counts": {},
        }
    threading.Thread(
        target=_local_audio_import_worker,
        args=(batch_id, staged_dir, safe_playlist),
        daemon=True,
    ).start()
    return {"batch_id": batch_id, "track_count": len(files), "playlist_name": safe_playlist}


@app.get("/api/imports/local-audio/{batch_id}")
def local_audio_import_status(batch_id: str) -> dict:
    with local_import_batch_lock:
        state = local_import_batches.get(batch_id)
        if state is None:
            raise HTTPException(404, "Local audio import not found")
        return dict(state)


@app.post("/api/imports/playlist-file/matches", status_code=202)
async def create_playlist_file_matches(
    file: Annotated[UploadFile, File()],
) -> dict:
    if not (file.filename or "").casefold().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV playlist export")
    contents = await file.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(400, "Playlist CSV must be 5 MB or smaller")
    try:
        tracks = _playlist_csv_tracks(contents)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    playlist_name = _safe_folder_name(Path(file.filename or "Imported Playlist").stem)
    match_id = uuid.uuid4().hex
    with playlist_match_lock:
        playlist_matches[match_id] = {
            "id": match_id,
            "status": "processing",
            "stage": f"Loaded {len(tracks)} tracks from CSV",
            "progress": 0,
            "matched": 0,
            "total": len(tracks),
            "playlist_name": playlist_name,
        }
    threading.Thread(target=_csv_match_worker, args=(match_id, tracks), daemon=True).start()
    return {"match_id": match_id, "track_count": len(tracks), "playlist_name": playlist_name}


def _scdl_executable() -> str:
    """Locate scdl beside the running Python interpreter or on PATH."""
    adjacent = Path(sys.executable).with_name("scdl")
    executable = str(adjacent) if adjacent.is_file() else shutil.which("scdl")
    if not executable:
        raise RuntimeError("scdl is not installed. Run pip install -r requirements.txt.")
    return executable


def _scdl_download_command(url: str, destination: Path) -> list[str]:
    """Build the constrained single-track/mix scdl invocation used by imports."""
    return [
        _scdl_executable(),
        "-l",
        url,
        "--path",
        str(destination),
        "--no-playlist",
        "--original-art",
        "--hide-progress",
        "--overwrite",
    ]


def _authorized_import_worker(import_id: str, request: AuthorizedImportRequest) -> None:
    try:
        cancel_event = authorized_import_cancel_events[import_id]
        provider = _authorized_source_provider(request.url)
        if provider is None:
            raise RuntimeError("Unsupported authorized audio source")
        if provider == "youtube":
            try:
                import yt_dlp
            except ImportError as error:
                raise RuntimeError(
                    "yt-dlp is not installed. Run pip install -r requirements.txt."
                ) from error
        INPUT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="audioextender-import-") as temporary:
            temporary_path = Path(temporary)
            template = str(temporary_path / "%(title).180B.%(ext)s")

            def progress(update: dict) -> None:
                if cancel_event.is_set():
                    raise RuntimeError("Import canceled")
                if update.get("status") != "downloading":
                    return
                total = update.get("total_bytes") or update.get("total_bytes_estimate")
                downloaded = update.get("downloaded_bytes") or 0
                percent = round(100 * downloaded / total, 1) if total else 0
                with authorized_import_lock:
                    authorized_imports[import_id].update(
                        stage="Downloading authorized audio", progress=percent
                    )

            if provider == "soundcloud":
                with authorized_import_lock:
                    authorized_imports[import_id].update(
                        stage="Downloading from SoundCloud with scdl", progress=15
                    )
                process = subprocess.Popen(
                    _scdl_download_command(request.url, temporary_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                while process.poll() is None:
                    if cancel_event.wait(0.2):
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        raise RuntimeError("Import canceled")
                stdout, stderr = process.communicate()
                completed = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
                )
                if process.returncode:
                    raise subprocess.CalledProcessError(
                        process.returncode, process.args, stdout, stderr
                    )
                audio_extensions = {
                    ".mp3",
                    ".m4a",
                    ".aac",
                    ".opus",
                    ".ogg",
                    ".flac",
                    ".wav",
                    ".aif",
                    ".aiff",
                }
                downloaded = next(
                    (
                        path
                        for path in temporary_path.rglob("*")
                        if path.is_file() and path.suffix.casefold() in audio_extensions
                    ),
                    None,
                )
                if downloaded is None:
                    detail = (completed.stderr or completed.stdout or "").strip()
                    raise RuntimeError(detail[-1000:] or "scdl did not produce an audio file")
                source_metadata = _probe_local_audio(downloaded)
                converted = temporary_path / "soundcloud-import.wav"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        str(downloaded),
                        "-vn",
                        "-c:a",
                        "pcm_s24le",
                        str(converted),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                info = {
                    "id": hashlib.sha256(request.url.encode()).hexdigest()[:24],
                    "title": source_metadata["title"],
                    "artist": source_metadata["artist"],
                    "uploader": source_metadata["artist"],
                    "duration": source_metadata["duration"],
                    "thumbnail": request.artwork_url,
                }
                wavs = [converted]
                with authorized_import_lock:
                    authorized_imports[import_id].update(
                        stage="SoundCloud audio converted to WAV", progress=75
                    )
            else:
                options = {
                    "format": "bestaudio/best",
                    "outtmpl": template,
                    "noplaylist": True,
                    "restrictfilenames": True,
                    "progress_hooks": [progress],
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info(request.url, download=True)
                wavs = list(temporary_path.glob("*.wav"))
            if not wavs:
                raise RuntimeError("The authorized source could not be converted to WAV")
            if cancel_event.is_set():
                raise RuntimeError("Import canceled")
            title = (
                str(request.title or info.get("title") or wavs[0].stem).strip() or "Imported Audio"
            )
            safe_name = (
                "".join(character for character in title if character not in '<>:"/\\|?*').strip()[
                    :180
                ]
                or "Imported Audio"
            )
            raw_source_id = str(info.get("id") or "").strip()
            catalog_source_id = (
                raw_source_id if provider == "youtube" else f"{provider}:{raw_source_id}"
            )
            existing_download = _cataloged_download_by_youtube_id(catalog_source_id)
            destination_dir = _music_library_root() / "Other"
            destination_dir.mkdir(parents=True, exist_ok=True)
            if existing_download:
                destination = Path(existing_download["file_path"])
            else:
                destination = destination_dir / f"{safe_name}.wav"
                counter = 2
                while destination.exists():
                    destination = destination_dir / f"{safe_name} ({counter}).wav"
                    counter += 1
                shutil.move(str(wavs[0]), destination)
        artist = str(request.artist or info.get("artist") or info.get("uploader") or "").strip()
        artwork_url = str(request.artwork_url or info.get("thumbnail") or "")
        artwork_path = _cache_track_artwork(artwork_url, destination)
        track_catalog_repository.upsert_downloaded_track(
            title=title,
            artist=artist,
            file_path=destination,
            # These legacy columns represent the downloadable source identity;
            # prefix non-YouTube IDs to prevent cross-provider collisions.
            youtube_id=catalog_source_id,
            youtube_url=request.url,
            spotify_uri=request.spotify_uri,
            artwork_url=artwork_url,
            artwork_path=artwork_path,
            duration_seconds=float(info.get("duration") or 0) or None,
            playlist_name="SoundCloud Imports" if provider == "soundcloud" else "Imported Singles",
        )
        if not request.process_with_extender:
            with authorized_import_lock:
                authorized_imports[import_id].update(
                    status="complete",
                    stage="WAV import complete",
                    progress=100,
                    filename=destination.name,
                    file_path=str(destination),
                    processed_with_extender=False,
                )
            return
        effective = _effective_settings()
        preset = str(effective["preset"])
        job_id = jobs_repository.create(
            destination.name,
            destination,
            preset,
            int(effective["intro_bars"]),
            int(effective["outro_bars"]),
            bool(effective["use_stems"]),
            {
                **effective,
                **_preset_snapshot(preset),
                "authorized_source_url": request.url,
                "rights_basis": request.rights_basis,
                "intro_bars_auto": True,
                "outro_bars_auto": True,
            },
        )
        service.enqueue(job_id)
        with authorized_import_lock:
            authorized_imports[import_id].update(
                status="complete",
                stage="Imported and added to processing queue",
                progress=100,
                job_id=job_id,
                filename=destination.name,
                file_path=str(destination),
                processed_with_extender=True,
            )
    except Exception as error:
        message = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            detail = str(error.stderr or error.stdout or "").strip()
            if detail:
                message = detail[-1500:]
        with authorized_import_lock:
            canceled = authorized_import_cancel_events.get(import_id, threading.Event()).is_set()
            authorized_imports[import_id].update(
                status="canceled" if canceled else "failed",
                stage="Import canceled" if canceled else "Import failed",
                error="Canceled by user" if canceled else message,
            )


@app.post("/api/imports/authorized", status_code=202)
def create_authorized_import(request: AuthorizedImportRequest) -> dict:
    provider = _authorized_source_provider(request.url)
    if provider is None:
        raise HTTPException(400, "Only YouTube and SoundCloud URLs are supported in this importer")
    if not request.confirmation:
        raise HTTPException(400, "Confirm that you have permission to download this audio")
    import_id = uuid.uuid4().hex
    with authorized_import_lock:
        authorized_import_cancel_events[import_id] = threading.Event()
        authorized_imports[import_id] = {
            "id": import_id,
            "status": "processing",
            "stage": "Preparing authorized import",
            "progress": 0,
            "rights_basis": request.rights_basis,
            "source_provider": provider,
        }
    threading.Thread(
        target=_authorized_import_worker,
        args=(import_id, request),
        daemon=True,
    ).start()
    return {"import_id": import_id}


@app.post("/api/imports/{import_id}/cancel")
def cancel_authorized_import(import_id: str) -> dict:
    with authorized_import_lock:
        state = authorized_imports.get(import_id)
        cancel_event = authorized_import_cancel_events.get(import_id)
        if state is None or cancel_event is None:
            raise HTTPException(404, "Import not found")
        if state.get("status") != "processing":
            return {"canceled": False, "status": state.get("status")}
        cancel_event.set()
        state.update(stage="Canceling import")
    return {"canceled": True, "status": "canceling"}


@app.get("/api/imports/{import_id}")
def authorized_import_status(import_id: str) -> dict:
    with authorized_import_lock:
        state = authorized_imports.get(import_id)
        if state is None:
            raise HTTPException(404, "Import not found")
        return {key: value for key, value in state.items() if key != "file_path"}


@app.get("/api/imports/{import_id}/download")
def download_authorized_import(import_id: str) -> FileResponse:
    with authorized_import_lock:
        state = authorized_imports.get(import_id)
        path = Path(state["file_path"]) if state and state.get("file_path") else None
    if path is None or not path.exists():
        raise HTTPException(404, "Imported WAV is not available")
    return FileResponse(path, filename=path.name)


def _downloaded_track_payload(track: dict) -> dict:
    suggested_genre = _generalized_genre(str(track.get("genre") or ""))
    current_genre = _normalize_genre_category(str(track.get("genre_category") or "Other"))
    payload = {
        key: value for key, value in track.items() if key not in {"file_path", "artwork_path"}
    } | {
        "absolute_path": str(Path(str(track.get("file_path") or "")).expanduser().resolve()),
        "available": Path(track["file_path"]).is_file(),
        "artwork_available": bool(track.get("artwork_path"))
        and Path(str(track["artwork_path"])).is_file(),
        "genre_category": current_genre,
        "suggested_genre": suggested_genre,
        "needs_genre": current_genre in {"Other", "Latin / Other"},
    }
    return payload


def _run_audio_quality_batch(batch_id: str) -> None:
    tracks = track_catalog_repository.list_downloaded_tracks()

    def inspect(track: dict) -> tuple[dict, Path, dict | None, str]:
        path = Path(str(track.get("file_path") or ""))
        try:
            if not path.is_file():
                raise FileNotFoundError("Audio file is unavailable")
            result = analyze_audio_quality(
                path,
                window_seconds=0.5,
                source_is_transcoded_lossy=bool(
                    track.get("youtube_id") or track.get("youtube_url")
                ),
            ).to_dict()
            return track, path, result, ""
        except (OSError, RuntimeError, ValueError) as exc:
            return track, path, None, str(exc)

    # Audio decoding and FFT work release the GIL. A small worker pool makes a
    # full external-drive scan practical without saturating the disk.
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="audio-quality") as executor:
        futures = [executor.submit(inspect, track) for track in tracks]
        for index, future in enumerate(as_completed(futures), start=1):
            track, path, result, error = future.result()
            if result is not None:
                track_catalog_repository.update_audio_quality(int(track["id"]), result)
            with audio_quality_batch_lock:
                batch = audio_quality_batches[batch_id]
                batch["processed"] = index
                batch["failed"] += int(bool(error))
                batch["current"] = str(track.get("filename") or track.get("title") or "")
                if error and len(batch["errors"]) < 30:
                    batch["errors"].append(
                        {"id": track.get("id"), "filename": path.name, "error": error}
                    )
    summary = track_catalog_repository.audio_quality_summary()
    with audio_quality_batch_lock:
        audio_quality_batches[batch_id].update(
            status="complete", stage="Quality scan complete", summary=summary
        )
    with library_status_cache_lock:
        library_status_cache.update(payload=None, expires_at=0.0)


@app.post("/api/downloaded-library/audio-quality")
def start_audio_quality_scan() -> dict:
    with audio_quality_batch_lock:
        active = next(
            (
                {"batch_id": key, **value}
                for key, value in audio_quality_batches.items()
                if value["status"] == "processing"
            ),
            None,
        )
        if active:
            return active
        total = len(track_catalog_repository.list_downloaded_tracks())
        batch_id = uuid.uuid4().hex
        audio_quality_batches[batch_id] = {
            "status": "processing",
            "stage": "Analyzing audio quality",
            "total": total,
            "processed": 0,
            "failed": 0,
            "current": "",
            "errors": [],
        }
    threading.Thread(
        target=_run_audio_quality_batch,
        args=(batch_id,),
        daemon=True,
        name=f"audio-quality-{batch_id[:8]}",
    ).start()
    return {"batch_id": batch_id, **audio_quality_batches[batch_id]}


@app.get("/api/downloaded-library/audio-quality-latest")
def latest_audio_quality_scan() -> dict:
    with audio_quality_batch_lock:
        if not audio_quality_batches:
            return {"status": "none", "summary": track_catalog_repository.audio_quality_summary()}
        batch_id = next(reversed(audio_quality_batches))
        return {"batch_id": batch_id, **audio_quality_batches[batch_id]}


@app.get("/api/downloaded-library/audio-quality/{batch_id}")
def audio_quality_scan_status(batch_id: str) -> dict:
    with audio_quality_batch_lock:
        batch = audio_quality_batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "Audio-quality scan not found")
        return {"batch_id": batch_id, **batch}


def _cached_artwork_thumbnail(source: Path, size: int = 96) -> Path:
    """Return a thumbnail when ready; otherwise queue it and serve the small source immediately."""
    global artwork_thumbnail_worker_started
    stat = source.stat()
    identity = f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{size}"
    thumbnail_root = _music_library_root() / ".artwork" / "thumbnails"
    thumbnail = thumbnail_root / f"{hashlib.sha256(identity.encode()).hexdigest()[:24]}.jpg"
    if thumbnail.is_file():
        _record_cache_result("artwork_thumbnail", True)
        return thumbnail
    with artwork_thumbnail_lock:
        if thumbnail.is_file():
            _record_cache_result("artwork_thumbnail", True)
            return thumbnail
        _record_cache_result("artwork_thumbnail", False)
        if thumbnail not in artwork_thumbnail_pending:
            artwork_thumbnail_pending.add(thumbnail)
            artwork_thumbnail_queue.put((source, thumbnail, size))
        if not artwork_thumbnail_worker_started:
            artwork_thumbnail_worker_started = True
            threading.Thread(
                target=_artwork_thumbnail_worker,
                name="artwork-thumbnail-worker",
                daemon=True,
            ).start()
    return source


def _artwork_thumbnail_worker() -> None:
    """Generate queued thumbnails serially so large pages cannot launch an FFmpeg stampede."""
    while True:
        source, thumbnail, size = artwork_thumbnail_queue.get()
        temporary = thumbnail.with_suffix(".pending.jpg")
        try:
            thumbnail.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vf",
                    f"scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size}",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "4",
                    str(temporary),
                ],
                check=True,
                timeout=15,
            )
            temporary.replace(thumbnail)
        except (OSError, subprocess.SubprocessError):
            temporary.unlink(missing_ok=True)
        finally:
            with artwork_thumbnail_lock:
                artwork_thumbnail_pending.discard(thumbnail)
            artwork_thumbnail_queue.task_done()


@app.get("/api/downloaded-library")
def downloaded_library(
    paged: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str = Query(default="", max_length=300),
    genre: str = Query(default="all", max_length=100),
    detailed_genre: str = Query(default="all", max_length=120),
    playlist: str = Query(default="all", max_length=200),
    analysis: str = Query(default="all", max_length=30),
    artwork: str = Query(default="all", pattern="^(all|missing|available)$"),
    quality: str = Query(
        default="all", pattern="^(all|excellent|good|review|poor|below-target|unanalyzed)$"
    ),
    sort: str = Query(default="newest", max_length=30),
) -> dict:
    _ensure_downloaded_catalog_migrated()
    if paged:
        facets = track_catalog_repository.downloaded_catalog_facets()
        tracks, filtered_total = track_catalog_repository.page_downloaded_tracks(
            page=page,
            page_size=page_size,
            search=search,
            genre=genre,
            detailed_genre=detailed_genre,
            playlist=playlist,
            analysis=analysis,
            artwork=artwork,
            quality=quality,
            sort=sort,
        )
        if analysis in {
            "complete",
            "active",
            "attention",
            "missing_title",
            "missing_artist",
            "missing_genre",
            "missing_artwork",
            "unmapped_genre",
            "broad_genre",
        }:
            analyzable_total = 0
        else:
            _, analyzable_total = track_catalog_repository.page_downloaded_tracks(
                page=1,
                page_size=1,
                search=search,
                genre=genre,
                detailed_genre=detailed_genre,
                playlist=playlist,
                artwork=artwork,
                quality=quality,
                analysis=("failed" if analysis == "failed" else "needs"),
                sort=sort,
            )
        total_pages = max(1, (filtered_total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages
            tracks, filtered_total = track_catalog_repository.page_downloaded_tracks(
                page=page,
                page_size=page_size,
                search=search,
                genre=genre,
                detailed_genre=detailed_genre,
                playlist=playlist,
                analysis=analysis,
                artwork=artwork,
                quality=quality,
                sort=sort,
            )
        genres: dict[str, int] = {}
        for raw_genre, count in facets["genres"].items():
            normalized = _normalize_genre_category(raw_genre)
            genres[normalized] = genres.get(normalized, 0) + int(count)
        playlists = facets["playlists"]
    else:
        tracks = track_catalog_repository.list_downloaded_tracks_with_jobs()
        genres = {}
        playlists = {}
        for track in tracks:
            track_genre = _normalize_genre_category(str(track.get("genre_category") or "Other"))
            genres[track_genre] = genres.get(track_genre, 0) + 1
            for track_playlist in track.get("playlists", []):
                playlists[track_playlist] = playlists.get(track_playlist, 0) + 1
        filtered_total = len(tracks)

        def review_flags(track: dict) -> dict[str, bool]:
            title = str(track.get("title") or "").strip().casefold()
            artist = str(track.get("artist") or "").strip().casefold()
            detailed_genre = str(track.get("genre") or "").strip()
            category = str(track.get("genre_category") or "Other")
            return {
                "missing_title": title in {"", "unknown title", "untitled"},
                "missing_artist": artist in {"", "unknown artist", "unknown", "unavailable"},
                "missing_genre": not detailed_genre,
                "missing_artwork": not str(track.get("artwork_path") or "").strip(),
                "unmapped_genre": bool(detailed_genre) and category == "Other",
                "broad_genre": category.endswith(" / General") or category.endswith(" / Other"),
            }

        track_review_flags = [review_flags(track) for track in tracks]
        facets = {
            "total": len(tracks),
            "review_states": {
                **{
                    issue: sum(flags[issue] for flags in track_review_flags)
                    for issue in (track_review_flags[0] if track_review_flags else review_flags({}))
                },
                "needs_attention": sum(any(flags.values()) for flags in track_review_flags),
            },
        }
        total_pages = 1
        analyzable_total = sum(
            (track.get("analysis_status") or "not_analyzed")
            not in {"queued", "processing", "complete"}
            for track in tracks
        )
    return {
        "tracks": [
            _downloaded_track_payload(track)
            | {
                "analysis_status": track.get("analysis_status") or "not_analyzed",
            }
            for track in tracks
        ],
        "genres": dict(sorted(genres.items())),
        "detailed_genres": dict(sorted(facets.get("detailed_genres", {}).items())),
        "detailed_genres_by_category": facets.get("detailed_genres_by_category", {}),
        "playlists": dict(sorted(playlists.items())),
        "review_states": facets.get("review_states", {}),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "filtered_total": filtered_total,
            "analyzable_total": analyzable_total,
            "catalog_total": facets["total"],
            "total_pages": total_pages,
        },
    }


@app.get("/api/downloaded-library/tracks/{track_id}/audio")
def downloaded_track_audio(track_id: int) -> FileResponse:
    track = track_catalog_repository.get_downloaded_track(track_id)
    path = Path(track["file_path"]) if track else None
    if path is None or not path.is_file():
        raise HTTPException(404, "Downloaded WAV is unavailable")
    return FileResponse(path, filename=path.name, media_type="audio/wav")


@app.get("/api/downloaded-library/tracks/{track_id}/artwork")
def downloaded_track_artwork(track_id: int, thumbnail: bool = False) -> FileResponse:
    track = track_catalog_repository.get_downloaded_track(track_id)
    path = Path(str(track.get("artwork_path") or "")) if track else None
    if path is None or not path.is_file():
        raise HTTPException(404, "Track artwork is unavailable")
    if thumbnail:
        path = _cached_artwork_thumbnail(path)
    media_type = "image/png" if path.suffix.casefold() == ".png" else "image/jpeg"
    headers = {"Cache-Control": "public, max-age=31536000, immutable"} if thumbnail else None
    return FileResponse(path, media_type=media_type, headers=headers)


@app.get("/api/downloaded-library/tracks/{track_id}/download")
def downloaded_track_download(track_id: int) -> FileResponse:
    return downloaded_track_audio(track_id)


@app.post("/api/downloaded-library/tracks/{track_id}/reveal")
def reveal_downloaded_track(track_id: int) -> dict:
    """Reveal a cataloged audio file using the host operating system's file browser."""
    track = track_catalog_repository.get_downloaded_track(track_id)
    path = Path(str(track.get("file_path") or "")).expanduser() if track else None
    if path is None or not path.is_file():
        raise HTTPException(404, "Downloaded WAV is unavailable")
    if sys.platform == "darwin":
        command = ["open", "-R", str(path)]
    elif sys.platform.startswith("win"):
        command = ["explorer", f"/select,{path}"]
    else:
        command = ["xdg-open", str(path.parent)]
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        raise HTTPException(500, "The system file browser could not be opened") from error
    return {"revealed": True, "absolute_path": str(path.resolve())}


@app.delete("/api/downloaded-library/tracks/{track_id}")
def remove_downloaded_track(track_id: int) -> dict:
    if not track_catalog_repository.delete_downloaded_track(track_id):
        raise HTTPException(404, "Downloaded track was not found")
    return {"removed": True, "track_id": track_id}


@app.delete("/api/downloaded-library/tracks")
def remove_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    requested = set(request.track_ids)
    removed = sum(
        1 for track_id in requested if track_catalog_repository.delete_downloaded_track(track_id)
    )
    return {"removed": removed, "requested": len(requested)}


@app.get("/api/downloaded-library/duplicate-candidates")
def downloaded_duplicate_candidates() -> dict:
    candidates = recording_family_repository.duplicate_candidates()
    return {
        "candidates": [
            {
                **candidate,
                "tracks": [_downloaded_track_payload(track) for track in candidate["tracks"]],
            }
            for candidate in candidates
        ],
        "total": len(candidates),
    }


@app.post("/api/downloaded-library/merge-duplicate")
def merge_downloaded_duplicate(request: DuplicateMergeRequest) -> dict:
    try:
        track = recording_family_repository.merge_downloaded_tracks(
            request.survivor_id, request.duplicate_id
        )
    except KeyError as error:
        raise HTTPException(404, "One or more tracks were not found") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"merged": True, "track": _downloaded_track_payload(track)}


@app.post("/api/downloaded-library/tracks/{track_id}/keep-separate")
def keep_downloaded_track_separate(track_id: int) -> dict:
    try:
        track = recording_family_repository.separate_recording(track_id)
    except KeyError as error:
        raise HTTPException(404, "Track was not found") from error
    return {"updated": True, "track": _downloaded_track_payload(track)}


@app.get("/api/downloaded-library/tracks/{track_id}/family")
def downloaded_track_family(track_id: int) -> dict:
    try:
        family = recording_family_repository.recording_family(track_id)
        suggestions = recording_family_repository.recording_family_suggestions(track_id)
    except KeyError as error:
        raise HTTPException(404, "Track was not found") from error
    return {
        "family": [_downloaded_track_payload(track) for track in family],
        "suggestions": [
            {**item, "track": _downloaded_track_payload(item["track"])} for item in suggestions
        ],
    }


@app.post("/api/downloaded-library/tracks/{track_id}/link-version")
def link_downloaded_track_version(track_id: int, request: TrackFamilyLinkRequest) -> dict:
    target_track_id = request.target_track_id or recording_family_repository.track_id_for_identity(
        request.target_identity
    )
    if target_track_id is None:
        raise HTTPException(404, "Target track ID was not found")
    try:
        track = recording_family_repository.link_recording_version(
            track_id, target_track_id, request.relationship
        )
    except KeyError as error:
        raise HTTPException(404, "One or more tracks were not found") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"updated": True, "track": _downloaded_track_payload(track)}


@app.post("/api/downloaded-library/tracks/{track_id}/unlink-version")
def unlink_downloaded_track_version(track_id: int) -> dict:
    """Create a new family for a track; this is the safe inverse of linking."""
    return keep_downloaded_track_separate(track_id)


def _downloaded_archive(tracks: list[dict], name: str) -> FileResponse:
    available = [track for track in tracks if Path(track["file_path"]).is_file()]
    if not available:
        raise HTTPException(404, "No downloaded WAV files are available for this selection")
    handle = tempfile.NamedTemporaryFile(
        prefix="audioextender-downloads-", suffix=".zip", delete=False
    )
    archive = Path(handle.name)
    handle.close()
    root_name = _safe_folder_name(name)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        used: set[str] = set()
        for track in available:
            path = Path(track["file_path"])
            category = "/".join(_genre_path_parts(track.get("genre_category") or "Other"))
            relative = f"{root_name}/{category}/{path.name}"
            counter = 2
            while relative.casefold() in used:
                relative = f"{root_name}/{category}/{path.stem} ({counter}){path.suffix}"
                counter += 1
            used.add(relative.casefold())
            bundle.write(path, arcname=relative)
    return FileResponse(
        archive,
        filename=f"{root_name} - WAVs.zip",
        media_type="application/zip",
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


@app.post("/api/downloaded-library/download")
def download_selected_tracks(request: DownloadedTracksRequest) -> FileResponse:
    wanted = set(request.track_ids)
    tracks = [
        track
        for track in track_catalog_repository.list_downloaded_tracks()
        if track["id"] in wanted
    ]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    return _downloaded_archive(tracks, "Selected Downloaded Tracks")


@app.post("/api/downloaded-library/analyze", status_code=202)
def analyze_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    wanted = set(request.track_ids)
    tracks = [
        track
        for track in track_catalog_repository.list_downloaded_tracks()
        if track["id"] in wanted
    ]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    return _queue_downloaded_analysis(tracks)


@app.post("/api/downloaded-library/reanalyze", status_code=202)
def reanalyze_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    wanted = set(request.track_ids)
    tracks = [
        track
        for track in track_catalog_repository.list_downloaded_tracks_with_jobs()
        if track["id"] in wanted
    ]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    return _queue_downloaded_analysis(tracks, force=True)


def _queue_downloaded_analysis(tracks: list[dict], *, force: bool = False) -> dict:
    existing_paths = {
        str(Path(job["source_path"]).resolve())
        for job in jobs_repository.list_jobs(limit=10_000)
        if job["status"]
        in (
            {"queued", "processing", "paused"}
            if force
            else {"queued", "processing", "paused", "complete"}
        )
    }
    effective = _effective_settings()
    created: list[int] = []
    skipped: list[int] = []
    unavailable: list[int] = []
    for track in tracks:
        source = Path(track["file_path"])
        if not source.is_file():
            unavailable.append(int(track["id"]))
            continue
        if str(source.resolve()) in existing_paths:
            skipped.append(int(track["id"]))
            continue
        job_id = jobs_repository.create(
            source.name,
            source,
            "auto",
            0,
            0,
            False,
            {
                **effective,
                "use_stems": False,
                "analysis_only": True,
                "refresh_cache": force,
                "reanalyze": force,
                "intro_bars_auto": False,
                "outro_bars_auto": False,
                "review_candidates": False,
            },
            parent_job_id=(
                int(track["completed_library_job_id"])
                if force and track.get("completed_library_job_id")
                else None
            ),
        )
        created.append(job_id)
        existing_paths.add(str(source.resolve()))
    service.enqueue_many(created)
    return {"job_ids": created, "skipped": skipped, "unavailable": unavailable}


@app.post("/api/downloaded-library/analyze-matching", status_code=202)
def analyze_matching_downloaded_tracks(request: DownloadedAnalysisFilterRequest) -> dict:
    if request.analysis in {"complete", "active"}:
        return {"job_ids": [], "skipped": [], "unavailable": [], "matched": 0}
    tracks, _ = track_catalog_repository.page_downloaded_tracks(
        page=1,
        page_size=10_000_000,
        search=request.search,
        genre=request.genre,
        detailed_genre=request.detailed_genre,
        playlist=request.playlist,
        analysis=("failed" if request.analysis == "failed" else "needs"),
        quality=request.quality,
        sort=request.sort,
    )
    result = _queue_downloaded_analysis(tracks)
    return {**result, "matched": len(tracks)}


@app.post("/api/downloaded-library/reanalyze-matching", status_code=202)
def reanalyze_matching_downloaded_tracks(request: DownloadedAnalysisFilterRequest) -> dict:
    tracks, _ = track_catalog_repository.page_downloaded_tracks(
        page=1,
        page_size=10_000_000,
        search=request.search,
        genre=request.genre,
        detailed_genre=request.detailed_genre,
        playlist=request.playlist,
        analysis=request.analysis,
        quality=request.quality,
        sort=request.sort,
    )
    result = _queue_downloaded_analysis(tracks, force=True)
    return {**result, "matched": len(tracks)}


@app.patch("/api/downloaded-library/genre")
def change_downloaded_genre(request: DownloadedGenreRequest) -> dict:
    """Move imported WAVs to a genre folder without losing analysis history."""
    all_tracks = track_catalog_repository.list_downloaded_tracks()
    requested_category = _normalize_genre_category(request.genre_category.strip())
    category = next(
        (
            str(track.get("genre_category") or "Other")
            for track in all_tracks
            if str(track.get("genre_category") or "Other").casefold()
            == requested_category.casefold()
        ),
        requested_category,
    )
    if not category or category == ".":
        raise HTTPException(400, "Choose a valid genre")
    wanted = set(request.track_ids)
    tracks = [track for track in all_tracks if track["id"] in wanted]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    destination_dir = _genre_directory(category)
    destination_dir.mkdir(parents=True, exist_ok=True)
    moves: list[tuple[int, Path, Path, str]] = []
    for track in tracks:
        source = Path(track["file_path"])
        if not source.is_file():
            raise HTTPException(409, f"{track['filename']} is unavailable and cannot be moved")
        destination = destination_dir / source.name
        if destination.resolve() != source.resolve() and destination.exists():
            raise HTTPException(409, f"{destination.name} already exists in {category}")
        moves.append((int(track["id"]), source, destination, category))
    completed: list[tuple[int, Path, Path, str]] = []
    try:
        for move in moves:
            track_id, source, destination, _ = move
            old_metadata = _source_metadata_path(source)
            if destination.resolve() != source.resolve():
                shutil.move(str(source), str(destination))
            completed.append(move)
            metadata = next(track for track in tracks if int(track["id"]) == track_id)
            write_wav_metadata(
                destination,
                title=str(metadata.get("title") or destination.stem),
                artist=str(metadata.get("artist") or ""),
                genre=category,
                album=str((metadata.get("playlists") or ["Imported Singles"])[0]),
            )
            _write_source_metadata(destination, {**metadata, "genre_category": category})
            if destination.resolve() != source.resolve():
                old_metadata.unlink(missing_ok=True)
        relocation_repository.relocate_downloaded_tracks(completed)
        for _, source, destination, _ in completed:
            old_parent = source.parent
            if destination.resolve() != source.resolve() and old_parent != _music_library_root():
                try:
                    old_parent.rmdir()
                except OSError:
                    pass
    except Exception as error:
        for _, source, destination, _ in reversed(completed):
            if destination.is_file() and destination.resolve() != source.resolve():
                shutil.move(str(destination), str(source))
        raise HTTPException(500, f"Could not change genre: {error}") from error
    return {"updated": len(completed), "genre_category": category}


@app.patch("/api/downloaded-library/tracks/{track_id}/metadata")
def update_downloaded_track_metadata(track_id: int, request: DownloadedMetadataRequest) -> dict:
    """Synchronize editable identity fields across disk, WAV tags, and Library records."""
    track = track_catalog_repository.get_downloaded_track(track_id)
    if not track:
        raise HTTPException(404, "Downloaded track was not found")
    source = Path(str(track["file_path"]))
    if not source.is_file():
        raise HTTPException(409, "The WAV file is missing and cannot be updated")
    category = _normalize_genre_category(request.genre_category.strip())
    if not category or category == ".":
        raise HTTPException(400, "Choose a valid genre category")
    title = request.title.strip()
    artist = request.artist.strip()
    detailed_genre = request.genre.strip()
    playlist_name = request.playlist_name.strip() or "Imported Singles"
    artwork_url = request.artwork_url.strip()
    filename = source.name
    if request.rename_file:
        display_name = " - ".join(value for value in (artist, title) if value) or title
        filename = f"{_safe_audio_name(display_name)}{source.suffix.lower()}"
    destination_dir = _genre_directory(category)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    if destination.resolve() != source.resolve() and destination.exists():
        raise HTTPException(409, f"{destination.name} already exists in {category}")
    old_metadata = _source_metadata_path(source)
    moved = destination.resolve() != source.resolve()
    try:
        if moved:
            shutil.move(str(source), str(destination))
        write_wav_metadata(
            destination,
            title=title,
            artist=artist,
            genre=category,
            album=playlist_name,
        )
        artwork_path = str(track.get("artwork_path") or "")
        if artwork_url and (
            artwork_url != str(track.get("artwork_url") or "") or not Path(artwork_path).is_file()
        ):
            artwork_path = _cache_track_artwork(artwork_url, destination)
            if not artwork_path:
                raise HTTPException(
                    400,
                    "Artwork could not be downloaded. Use a direct Spotify or YouTube image URL.",
                )
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
            "artwork_url": artwork_url or str(track.get("artwork_url") or ""),
            "artwork_path": artwork_path,
        }
        _write_source_metadata(destination, metadata)
        track_catalog_repository.update_downloaded_track_metadata(
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
            track_catalog_repository.update_downloaded_track_artwork(
                track_id, artwork_url=artwork_url, artwork_path=artwork_path
            )
        if moved:
            old_metadata.unlink(missing_ok=True)
            try:
                source.parent.rmdir()
            except OSError:
                pass
    except HTTPException:
        if moved and destination.is_file() and not source.exists():
            shutil.move(str(destination), str(source))
        raise
    except Exception as error:
        if moved and destination.is_file() and not source.exists():
            shutil.move(str(destination), str(source))
        raise HTTPException(500, f"Could not update track metadata: {error}") from error
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
    }


@app.post("/api/downloaded-library/repair-playlist-derived-genres")
def repair_playlist_derived_genres() -> dict:
    """Replace playlist labels accidentally stored as detailed track genres."""
    repaired: list[int] = []
    restored: list[int] = []
    cleared: list[int] = []
    failed: list[dict[str, object]] = []
    for track in track_catalog_repository.list_downloaded_tracks():
        playlists = [
            str(value).strip() for value in (track.get("playlists") or []) if str(value).strip()
        ]
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
        original = _original_import_metadata(
            matching_playlist,
            str(track.get("title") or ""),
            str(track.get("artist") or ""),
        )
        try:
            result = update_downloaded_track_metadata(
                int(track["id"]),
                DownloadedMetadataRequest(
                    title=str(track.get("title") or Path(str(track["file_path"])).stem),
                    artist=str(track.get("artist") or ""),
                    genre=original["genre"],
                    genre_category=original["genre_category"],
                    playlist_name=matching_playlist,
                    # Genre repair must not depend on a remote artwork host being
                    # available. A blank request preserves the cataloged URL/path.
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


@app.post("/api/downloaded-library/retag")
def retag_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    """Synchronize embedded WAV tags from the authoritative music catalog."""
    _require_music_library_online()
    wanted = set(request.track_ids)
    tracks = [
        track
        for track in track_catalog_repository.list_downloaded_tracks()
        if int(track["id"]) in wanted
    ]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    tagged: list[int] = []
    skipped: list[int] = []
    failed: list[dict[str, object]] = []
    for track in tracks:
        path = Path(str(track["file_path"]))
        try:
            updated = sync_wav_metadata(
                path,
                title=str(track.get("title") or path.stem),
                artist=str(track.get("artist") or ""),
                genre=str(track.get("genre_category") or "Other"),
                album=str((track.get("playlists") or ["Imported Singles"])[0]),
            )
            if updated:
                tagged.append(int(track["id"]))
            else:
                skipped.append(int(track["id"]))
        except (FileNotFoundError, OSError, ValueError, subprocess.SubprocessError) as error:
            failed.append({"id": int(track["id"]), "error": str(error)})
    return {"tagged": tagged, "skipped": skipped, "failed": failed}


def _run_wav_tag_batch(batch_id: str) -> None:
    tracks = track_catalog_repository.list_downloaded_tracks()
    for index, track in enumerate(tracks, start=1):
        path = Path(str(track["file_path"]))
        error = ""
        updated = False
        try:
            updated = sync_wav_metadata(
                path,
                title=str(track.get("title") or path.stem),
                artist=str(track.get("artist") or ""),
                genre=str(track.get("genre_category") or "Other"),
                album=str((track.get("playlists") or ["Imported Singles"])[0]),
            )
        except (FileNotFoundError, OSError, ValueError, subprocess.SubprocessError) as exception:
            error = str(exception)
        with wav_tag_batch_lock:
            batch = wav_tag_batches[batch_id]
            batch["processed"] = index
            if error:
                batch["failed"] += 1
                batch["errors"].append(
                    {
                        "id": int(track["id"]),
                        "filename": track["filename"],
                        "path": str(path),
                        "error": error,
                    }
                )
            else:
                batch["tagged" if updated else "skipped"] += 1
    with wav_tag_batch_lock:
        wav_tag_batches[batch_id]["status"] = "complete"


@app.post("/api/downloaded-library/retag-all")
def start_retag_all_downloaded_tracks() -> dict:
    """Start a sequential, disk-safe metadata synchronization for the catalog."""
    _require_music_library_online()
    with wav_tag_batch_lock:
        active = next(
            (
                {"batch_id": key, **value}
                for key, value in wav_tag_batches.items()
                if value["status"] == "processing"
            ),
            None,
        )
        if active:
            return active
        batch_id = uuid.uuid4().hex
        total = len(track_catalog_repository.list_downloaded_tracks())
        wav_tag_batches[batch_id] = {
            "status": "processing",
            "total": total,
            "processed": 0,
            "tagged": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }
    threading.Thread(
        target=_run_wav_tag_batch,
        args=(batch_id,),
        daemon=True,
        name=f"wav-tags-{batch_id[:8]}",
    ).start()
    return {"batch_id": batch_id, **wav_tag_batches[batch_id]}


@app.get("/api/downloaded-library/retag-all/{batch_id}")
def wav_tag_batch_status(batch_id: str) -> dict:
    with wav_tag_batch_lock:
        batch = wav_tag_batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "WAV metadata synchronization was not found")
        return {"batch_id": batch_id, **batch}


@app.get("/api/downloaded-library/retag-all-latest")
def latest_wav_tag_batch_status() -> dict:
    with wav_tag_batch_lock:
        if not wav_tag_batches:
            cached_audit = settings_repository.get_system_state("wav_tag_latest_audit")
            if cached_audit:
                try:
                    cached = json.loads(cached_audit)
                    generated = datetime.fromisoformat(str(cached.pop("generated_at")))
                    if cached.get("failed") and _music_library_root().is_dir():
                        return _refresh_wav_tag_audit()
                    if (datetime.now(timezone.utc) - generated).total_seconds() >= 300:
                        _schedule_wav_tag_audit_refresh()
                    return cached
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    pass
            return _refresh_wav_tag_audit()
        batch_id = next(reversed(wav_tag_batches))
        batch = dict(wav_tag_batches[batch_id])
        if batch.get("status") == "complete" and batch.get("errors"):
            current = {
                int(track["id"]): track
                for track in track_catalog_repository.list_downloaded_tracks()
            }
            active_errors = []
            for item in batch["errors"]:
                track = current.get(int(item.get("id") or 0))
                current_path = Path(str((track or {}).get("file_path") or item.get("path") or ""))
                missing_error = (
                    "missing" in str(item.get("error") or "").casefold()
                    or "no such file" in str(item.get("error") or "").casefold()
                )
                if missing_error and current_path.is_file():
                    continue
                active_errors.append({**item, "path": str(current_path)})
            resolved = len(batch["errors"]) - len(active_errors)
            batch["errors"] = active_errors
            batch["failed"] = len(active_errors)
            batch["skipped"] = int(batch.get("skipped") or 0) + resolved
        return {"batch_id": batch_id, **batch}


def _refresh_wav_tag_audit() -> dict:
    tracks = track_catalog_repository.list_downloaded_tracks()
    errors = [
        {
            "id": int(track["id"]),
            "filename": track["filename"],
            "path": str(track["file_path"]),
            "error": "File is missing from disk",
        }
        for track in tracks
        if not Path(str(track["file_path"])).is_file()
    ]
    payload = {
        "status": "audit",
        "total": len(tracks),
        "processed": len(tracks),
        "tagged": 0,
        "skipped": len(tracks) - len(errors),
        "failed": len(errors),
        "errors": errors,
    }
    settings_repository.set_system_state(
        "wav_tag_latest_audit",
        json.dumps({**payload, "generated_at": datetime.now(timezone.utc).isoformat()}),
    )
    return payload


def _schedule_wav_tag_audit_refresh() -> None:
    global wav_tag_audit_refresh_active
    with wav_tag_audit_refresh_lock:
        if wav_tag_audit_refresh_active:
            return
        wav_tag_audit_refresh_active = True

    def refresh() -> None:
        global wav_tag_audit_refresh_active
        try:
            _refresh_wav_tag_audit()
        finally:
            with wav_tag_audit_refresh_lock:
                wav_tag_audit_refresh_active = False

    threading.Thread(target=refresh, daemon=True, name="wav-tag-audit").start()


def _run_artwork_sync_batch(batch_id: str, track_ids: list[int] | None = None) -> None:
    tracks = track_catalog_repository.list_downloaded_tracks()
    if track_ids is not None:
        requested = set(track_ids)
        tracks = [track for track in tracks if int(track["id"]) in requested]
    for index, track in enumerate(tracks, start=1):
        outcome = "skipped"
        error = ""
        path = Path(str(track.get("file_path") or ""))
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            artwork_url = str(track.get("artwork_url") or "")
            cached_path = Path(str(track.get("artwork_path") or ""))
            if cached_path.is_file():
                if read_wav_artwork(path) is None:
                    embed_wav_artwork(path, cached_path)
                    outcome = "updated"
            else:
                spotify_uri = str(track.get("spotify_uri") or "")
                if spotify_uri.startswith("spotify:track:"):
                    metadata = _spotify_source_metadata(
                        "https://open.spotify.com/track/" + spotify_uri.rsplit(":", 1)[-1]
                    )
                    artwork_url = str(metadata.get("thumbnail_url") or "")
                if not artwork_url and track.get("youtube_id"):
                    artwork_url = f"https://i.ytimg.com/vi/{track['youtube_id']}/hqdefault.jpg"
                if not artwork_url:
                    raise ValueError("No Spotify or YouTube artwork source is stored")
                artwork_path = _cache_track_artwork(artwork_url, path)
                if not artwork_path:
                    raise ValueError("Artwork could not be downloaded or embedded")
                track_catalog_repository.update_downloaded_track_artwork(
                    int(track["id"]), artwork_url=artwork_url, artwork_path=artwork_path
                )
                outcome = "updated"
        except Exception as exception:
            outcome = "failed"
            error = str(exception)
        with artwork_sync_batch_lock:
            batch = artwork_sync_batches[batch_id]
            batch["processed"] = index
            batch[outcome] += 1
            if error:
                batch["errors"].append(
                    {
                        "id": int(track["id"]),
                        "filename": track["filename"],
                        "error": error,
                    }
                )
    with artwork_sync_batch_lock:
        artwork_sync_batches[batch_id]["status"] = "complete"


@app.post("/api/downloaded-library/artwork-sync")
def start_downloaded_artwork_sync(request: ArtworkSyncRequest | None = None) -> dict:
    _require_music_library_online()
    track_ids = list(dict.fromkeys(request.track_ids)) if request else []
    tracks = track_catalog_repository.list_downloaded_tracks()
    if track_ids:
        known = {int(track["id"]) for track in tracks}
        track_ids = [track_id for track_id in track_ids if track_id in known]
        if not track_ids:
            raise HTTPException(404, "None of the selected tracks remain in the catalog")
    else:
        # A library-wide artwork sync should only touch tracks that still need it.
        track_ids = [
            int(track["id"])
            for track in tracks
            if not Path(str(track.get("artwork_path") or "")).is_file()
        ]
    with artwork_sync_batch_lock:
        active = next(
            (
                {"batch_id": key, **value}
                for key, value in artwork_sync_batches.items()
                if value["status"] == "processing"
            ),
            None,
        )
        if active:
            return active
        batch_id = uuid.uuid4().hex
        artwork_sync_batches[batch_id] = {
            "status": "processing",
            "total": len(track_ids),
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "resolved": 0,
            "errors": [],
        }
    threading.Thread(
        target=_run_artwork_sync_batch,
        args=(batch_id, track_ids),
        daemon=True,
        name=f"artwork-{batch_id[:8]}",
    ).start()
    return {"batch_id": batch_id, **artwork_sync_batches[batch_id]}


def _reconcile_artwork_sync_errors(batch_id: str) -> dict:
    """Drop stale failures after a track is repaired manually or removed."""
    with artwork_sync_batch_lock:
        stored = artwork_sync_batches.get(batch_id)
        if stored is None:
            raise HTTPException(404, "Artwork synchronization was not found")
        snapshot = dict(stored)
        errors = list(stored.get("errors") or [])
    if snapshot.get("status") != "complete" or not errors:
        return {"batch_id": batch_id, **snapshot}

    current = {
        int(track["id"]): track for track in track_catalog_repository.list_downloaded_tracks()
    }
    active_errors = []
    for item in errors:
        track = current.get(int(item.get("id") or 0))
        if track is None:
            continue
        wav_path = Path(str(track.get("file_path") or ""))
        artwork_path = Path(str(track.get("artwork_path") or ""))
        try:
            repaired = (
                wav_path.is_file()
                and artwork_path.is_file()
                and read_wav_artwork(wav_path) is not None
            )
        except (OSError, ValueError):
            repaired = False
        if not repaired:
            active_errors.append(item)

    with artwork_sync_batch_lock:
        batch = artwork_sync_batches[batch_id]
        resolved_now = len(batch.get("errors") or []) - len(active_errors)
        batch["errors"] = active_errors
        batch["failed"] = len(active_errors)
        batch["resolved"] = int(batch.get("resolved") or 0) + max(0, resolved_now)
        return {"batch_id": batch_id, **batch}


@app.get("/api/downloaded-library/artwork-sync/{batch_id}")
def downloaded_artwork_sync_status(batch_id: str) -> dict:
    return _reconcile_artwork_sync_errors(batch_id)


@app.get("/api/downloaded-library/artwork-sync-latest")
def latest_downloaded_artwork_sync() -> dict:
    with artwork_sync_batch_lock:
        if not artwork_sync_batches:
            return {"status": "none"}
        batch_id = next(reversed(artwork_sync_batches))
    return _reconcile_artwork_sync_errors(batch_id)


def _run_genre_rescan_batch(batch_id: str) -> None:
    """Reclassify downloads sequentially while publishing per-track progress."""
    tracks = track_catalog_repository.list_downloaded_tracks()
    for index, track in enumerate(tracks, start=1):
        outcome = "unchanged"
        conflict: dict | None = None
        detailed = str(track.get("genre") or "").strip()
        inferred = _generalized_genre(detailed)
        if inferred == "Other":
            current = _normalize_genre_category(track.get("genre_category") or "Other")
            if current == "Latin / Other":
                try:
                    change_downloaded_genre(
                        DownloadedGenreRequest(track_ids=[int(track["id"])], genre_category="Other")
                    )
                    outcome = "updated"
                except HTTPException as error:
                    outcome = "failed"
                    conflict = {"id": int(track["id"]), "detail": str(error.detail)}
            else:
                outcome = "unresolved"
        else:
            source = Path(track["file_path"])
            destination = _genre_directory(inferred) / source.name
            current = _normalize_genre_category(track.get("genre_category") or "Other")
            if current != inferred or source.resolve() != destination.resolve():
                try:
                    change_downloaded_genre(
                        DownloadedGenreRequest(
                            track_ids=[int(track["id"])], genre_category=inferred
                        )
                    )
                    outcome = "updated"
                except HTTPException as error:
                    outcome = "failed"
                    conflict = {
                        "track_id": int(track["id"]),
                        "title": track.get("title") or track.get("filename"),
                        "reason": str(error.detail),
                    }
        with genre_rescan_batch_lock:
            batch = genre_rescan_batches[batch_id]
            batch["processed"] = index
            batch[outcome] += 1
            if conflict:
                batch["conflicts"].append(conflict)
    with genre_rescan_batch_lock:
        genre_rescan_batches[batch_id]["status"] = "complete"
    with wav_tag_batch_lock:
        for wav_batch_id in [
            key for key, value in wav_tag_batches.items() if value.get("status") != "processing"
        ]:
            wav_tag_batches.pop(wav_batch_id, None)


@app.post("/api/downloaded-library/rescan-genres", status_code=202)
def start_downloaded_genre_rescan() -> dict:
    """Start a sequential genre rescan and return its observable batch state."""
    _require_music_library_online()
    with genre_rescan_batch_lock:
        active = next(
            (
                {"batch_id": key, **value}
                for key, value in genre_rescan_batches.items()
                if value["status"] == "processing"
            ),
            None,
        )
        if active:
            return active
        batch_id = uuid.uuid4().hex
        genre_rescan_batches[batch_id] = {
            "status": "processing",
            "total": len(track_catalog_repository.list_downloaded_tracks()),
            "processed": 0,
            "updated": 0,
            "unchanged": 0,
            "unresolved": 0,
            "failed": 0,
            "conflicts": [],
        }
    threading.Thread(
        target=_run_genre_rescan_batch,
        args=(batch_id,),
        daemon=True,
        name=f"genre-rescan-{batch_id[:8]}",
    ).start()
    return {"batch_id": batch_id, **genre_rescan_batches[batch_id]}


@app.get("/api/downloaded-library/rescan-genres/{batch_id}")
def downloaded_genre_rescan_status(batch_id: str) -> dict:
    with genre_rescan_batch_lock:
        batch = genre_rescan_batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "Genre rescan was not found")
        return {"batch_id": batch_id, **batch}


@app.get("/api/downloaded-library/rescan-genres-latest")
def latest_downloaded_genre_rescan_status() -> dict:
    with genre_rescan_batch_lock:
        if not genre_rescan_batches:
            return {"status": "none"}
        batch_id = next(reversed(genre_rescan_batches))
        return {"batch_id": batch_id, **genre_rescan_batches[batch_id]}


def _run_catalog_reconcile(batch_id: str) -> None:
    def publish(result: dict[str, int]) -> None:
        with catalog_reconcile_batch_lock:
            catalog_reconcile_batches[batch_id].update(
                result, stage=f"Checking source records {result['processed']} of {result['total']}"
            )

    try:
        with downloaded_catalog_migration_lock:
            result = _migrate_downloaded_catalog(incremental=True, progress=publish)
        with catalog_reconcile_batch_lock:
            catalog_reconcile_batches[batch_id].update(
                result, status="complete", stage="File reconciliation complete"
            )
    except Exception as error:
        with catalog_reconcile_batch_lock:
            catalog_reconcile_batches[batch_id].update(
                status="failed", stage="File reconciliation failed", error=str(error)
            )


@app.post("/api/downloaded-library/reconcile-files", status_code=202)
def start_catalog_reconcile() -> dict:
    _require_music_library_online()
    with catalog_reconcile_batch_lock:
        active = next(
            (
                dict(value)
                for value in catalog_reconcile_batches.values()
                if value.get("status") == "processing"
            ),
            None,
        )
        if active:
            return active
        batch_id = uuid.uuid4().hex
        catalog_reconcile_batches[batch_id] = {
            "batch_id": batch_id,
            "status": "processing",
            "stage": "Indexing source records",
            "total": 0,
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
        }
    threading.Thread(
        target=_run_catalog_reconcile,
        args=(batch_id,),
        daemon=True,
        name=f"catalog-reconcile-{batch_id[:8]}",
    ).start()
    return dict(catalog_reconcile_batches[batch_id])


@app.get("/api/downloaded-library/reconcile-files/{batch_id}")
def catalog_reconcile_status(batch_id: str) -> dict:
    with catalog_reconcile_batch_lock:
        batch = catalog_reconcile_batches.get(batch_id)
        if not batch:
            raise HTTPException(404, "File reconciliation was not found")
        return dict(batch)


def _run_integrity_scan(batch_id: str) -> None:
    root = _music_library_root()
    recording_family_repository.refresh_missing_audio_fingerprints()
    tracks = track_catalog_repository.list_downloaded_tracks_with_jobs()
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
    for candidate in recording_family_repository.duplicate_candidates():
        group = candidate["tracks"]
        findings["duplicate_records"].append(
            {
                "id": str(group[0]["id"]),
                "title": group[0].get("title"),
                "artist": group[0].get("artist"),
                "track_ids": [item["id"] for item in group],
                "paths": [item["file_path"] for item in group],
                "identities": [
                    f"{item['recording_code']}-{item['version_code']}" for item in group
                ],
                "reason": candidate["reason"],
                "confidence": candidate["confidence"],
            }
        )
    for path in root.rglob("*.wav"):
        if (
            ".audioextender" not in path.parts
            and str(path.resolve()) not in catalog_paths
            and not track_catalog_repository.downloaded_track_is_excluded(path)
        ):
            findings["uncataloged_files"].append(
                {"id": str(path.resolve()), "title": path.stem, "path": str(path.resolve())}
            )
    sidecar_root = root / ".audioextender" / "sources"
    if sidecar_root.exists():
        for sidecar in sidecar_root.glob("*.json"):
            try:
                audio_path = Path(
                    str(json.loads(sidecar.read_text(encoding="utf-8")).get("file_path") or "")
                )
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
    for job in jobs_repository.list_jobs(limit=10_000):
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
                tags = read_wav_metadata(path)
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
        with integrity_scan_batch_lock:
            integrity_scan_batches[batch_id].update(
                processed=index,
                total=total,
                progress=round(index / max(1, total) * 100),
                stage=f"Checking WAV metadata {index} of {total}",
            )
    with integrity_scan_batch_lock:
        integrity_scan_batches[batch_id].update(
            status="complete",
            stage="Integrity scan complete",
            progress=100,
            findings=findings,
            counts={key: len(value) for key, value in findings.items()},
        )


@app.post("/api/downloaded-library/integrity-scan", status_code=202)
def start_integrity_scan() -> dict:
    _require_music_library_online()
    batch_id = uuid.uuid4().hex
    total = len(track_catalog_repository.list_downloaded_tracks())
    with integrity_scan_batch_lock:
        integrity_scan_batches[batch_id] = {
            "batch_id": batch_id,
            "status": "processing",
            "stage": "Indexing catalog and files",
            "progress": 0,
            "processed": 0,
            "total": total,
            "findings": {},
            "counts": {},
        }
    threading.Thread(
        target=_run_integrity_scan,
        args=(batch_id,),
        daemon=True,
        name=f"integrity-scan-{batch_id[:8]}",
    ).start()
    return dict(integrity_scan_batches[batch_id])


@app.get("/api/downloaded-library/integrity-scan/{batch_id}")
def integrity_scan_status(batch_id: str) -> dict:
    with integrity_scan_batch_lock:
        batch = integrity_scan_batches.get(batch_id)
        if not batch:
            raise HTTPException(404, "Integrity scan was not found")
        return dict(batch)


@app.post("/api/downloaded-library/integrity-repair")
def integrity_repair(request: IntegrityRepairRequest) -> dict:
    root = _music_library_root()
    if request.action == "remove-missing":
        return {
            "updated": sum(
                track_catalog_repository.delete_downloaded_track(int(item))
                for item in request.item_ids
            )
        }
    if request.action == "retag-mismatches":
        wanted = {int(item) for item in request.item_ids}
        updated = 0
        for track in track_catalog_repository.list_downloaded_tracks():
            if int(track["id"]) not in wanted:
                continue
            path = Path(str(track["file_path"]))
            updated += int(
                sync_wav_metadata(
                    path,
                    title=str(track.get("title") or path.stem),
                    artist=str(track.get("artist") or ""),
                    genre=str(track.get("genre_category") or "Other"),
                    album=str((track.get("playlists") or ["Imported Singles"])[0]),
                )
            )
        return {"updated": updated}
    paths = [Path(item).resolve() for item in request.item_ids]
    if any(not path.is_relative_to(root) for path in paths):
        raise HTTPException(400, "Repair target is outside the Music Library")
    if request.action == "delete-stale-sidecars":
        sidecar_root = (root / ".audioextender" / "sources").resolve()
        if any(not path.is_relative_to(sidecar_root) for path in paths):
            raise HTTPException(400, "Invalid sidecar target")
        for path in paths:
            path.unlink(missing_ok=True)
        return {"updated": len(paths)}
    added = 0
    for path in paths:
        if not path.is_file() or path.suffix.casefold() != ".wav":
            continue
        metadata = _probe_local_audio(path)
        category = _catalog_genre_category(path, "", str(metadata.get("genre") or ""))
        track_catalog_repository.upsert_downloaded_track(
            title=str(metadata.get("title") or path.stem),
            artist=str(metadata.get("artist") or ""),
            file_path=path,
            genre=str(metadata.get("genre") or ""),
            genre_category=category,
            duration_seconds=metadata.get("duration"),
            playlist_name="Recovered files",
        )
        added += 1
    return {"updated": added}


@app.get("/api/downloaded-library/genres/{genre}/download")
def download_genre(genre: str) -> FileResponse:
    tracks = [
        track
        for track in track_catalog_repository.list_downloaded_tracks()
        if str(track.get("genre_category") or "Other").casefold() == genre.casefold()
    ]
    return _downloaded_archive(tracks, genre)


@app.get("/api/downloaded-library/playlists/{playlist}/download")
def download_playlist(playlist: str) -> FileResponse:
    tracks = [
        track
        for track in track_catalog_repository.list_downloaded_tracks()
        if any(item.casefold() == playlist.casefold() for item in track.get("playlists", []))
    ]
    return _downloaded_archive(tracks, playlist)


@app.get("/api/jobs")
def jobs(
    paged: bool = False,
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(50, ge=1, le=200),
    status: list[str] = Query(default=[]),  # noqa: B008
) -> list[dict] | dict:
    global jobs_watchdog_last
    if perf_counter() - jobs_watchdog_last >= 60:
        jobs_repository.fail_stalled_jobs()
        jobs_watchdog_last = perf_counter()
    if paged:
        rows, total = jobs_repository.list_jobs_page(
            page=page, page_size=page_size, statuses=tuple(status)
        )
    else:
        rows = jobs_repository.list_job_summaries()
        active_rows, _ = jobs_repository.list_jobs_page(
            page=1, page_size=10_000, statuses=("queued", "processing")
        )
        rows_by_id = {int(row["id"]): row for row in rows}
        rows_by_id.update({int(row["id"]): row for row in active_rows})
        rows = sorted(rows_by_id.values(), key=lambda row: int(row["id"]), reverse=True)
    queue = service.snapshot()
    pending = {job_id: index for index, job_id in enumerate(queue["pending"])}
    active_ids = set(
        queue.get("active_ids") or ([] if queue["active"] is None else [queue["active"]])
    )
    paused_ids = set(queue.get("paused_ids") or [])
    for row in rows:
        row["queue_index"] = pending.get(int(row["id"]))
        row["is_active"] = int(row["id"]) in active_ids
        row["pause_requested"] = int(row["id"]) in paused_ids
    if not paged:
        return rows
    return {
        "jobs": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@app.post("/api/jobs/reorder")
def reorder_jobs(request: ReorderRequest) -> dict:
    service.reorder(request.job_ids)
    return {"ok": True}


@app.post("/api/jobs/clear")
def clear_jobs() -> dict:
    """Clear workspace queue entries without removing completed library audio."""
    active_ids = set(service.snapshot().get("active_ids") or [])
    cleared = 0
    for job in jobs_repository.list_jobs(1000):
        job_id = int(job["id"])
        if job_id in active_ids:
            continue
        if job["status"] == "queued":
            service.cancel(job_id)
            cleared += int(jobs_repository.delete(job_id))
        elif job["status"] in {"failed", "canceled"}:
            cleared += int(jobs_repository.delete(job_id))
        elif job.get("review_status") in {"pending", "rejected"}:
            jobs_repository.update(job_id, review_status="resolved")
            cleared += 1
    return {"cleared": cleared, "active_preserved": bool(active_ids)}


@app.delete("/api/library/{source_name}")
def remove_library_track(source_name: str) -> dict:
    """Remove every inactive generation from the Library without deleting exports."""
    matching = [
        job
        for job in jobs_repository.list_jobs(10_000)
        if str(job["source_name"]).casefold() == source_name.casefold()
    ]
    if not matching:
        raise HTTPException(404, "Library track not found")
    if any(job["status"] in {"queued", "processing"} for job in matching):
        raise HTTPException(409, "Cancel or finish this track before removing it")
    removed = sum(int(jobs_repository.delete(int(job["id"]))) for job in matching)
    report_path = OUTPUT / "reports" / "processing_report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        record = report.get("songs", {}).get(source_name.casefold())
        if isinstance(record, dict):
            record["status"] = "removed"
            temporary = report_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            temporary.replace(report_path)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"removed_generations": removed, "files_preserved": True}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int) -> dict:
    if not service.cancel(job_id):
        raise HTTPException(409, "Only queued jobs can be canceled")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: int) -> dict:
    if not service.pause(job_id):
        raise HTTPException(409, "Only the actively processing job can be paused")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: int) -> dict:
    if not service.resume(job_id):
        raise HTTPException(409, "Only the actively processing job can be resumed")
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def remove_job(job_id: int) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job["status"] in {"queued", "processing"}:
        raise HTTPException(409, "Cancel or finish the job before removing it")
    return {"removed": jobs_repository.delete(job_id)}


@app.post("/api/jobs/{job_id}/reprocess", status_code=202)
def reprocess_job(job_id: int, request: ReprocessRequest | None = None) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    config_overrides = json.loads(job.get("config_json") or "{}")
    config_overrides.pop("analysis_only", None)
    preset = job["preset"]
    intro_bars = int(job["intro_bars"])
    outro_bars = int(job["outro_bars"])
    use_stems = bool(job["use_stems"])
    if request is not None:
        if request.pcm_bits not in {None, 16, 24}:
            raise HTTPException(400, "PCM depth must be 16 or 24")
        if request.preset is not None:
            if request.preset != "auto" and request.preset not in _available_presets():
                raise HTTPException(400, "Unknown preset")
            preset = request.preset
        for position in ("intro", "outro"):
            requested_bars = getattr(request, f"{position}_bars")
            if requested_bars is not None:
                if requested_bars not in SUPPORTED_BAR_COUNTS:
                    raise HTTPException(400, "Unsupported bar count")
                if position == "intro":
                    intro_bars = requested_bars
                else:
                    outro_bars = requested_bars
            automatic = getattr(request, f"{position}_bars_auto")
            if automatic is not None:
                config_overrides[f"{position}_bars_auto"] = automatic
        if request.use_stems is not None:
            use_stems = request.use_stems
        for key in (
            "auto_bars",
            "minimum_intro_loop_quality",
            "minimum_outro_loop_quality",
            "maximum_repetitions",
            "crossfade_ms",
            "candidate_count",
            "intro_search_seconds",
            "outro_search_seconds",
            "maximum_vocal_coverage_percent",
            "maximum_vocal_boundary_risk_percent",
            "maximum_buildup_risk_percent",
            "maximum_bass_reset_risk_percent",
            "minimum_stem_reliability_percent",
            "pcm_bits",
            "preview_seconds",
            "export_cues",
        ):
            value = getattr(request, key)
            if value is not None:
                config_overrides[key] = value
        if request.preset is not None:
            config_overrides.pop("preset_definition", None)
            config_overrides.update(_preset_snapshot(preset))
        if request.clear_insertion:
            for key in (
                "insert_source_start",
                "insert_source_end",
                "insert_destination",
                "insert_copies",
            ):
                config_overrides.pop(key, None)
        if request.intro_candidate is not None:
            config_overrides["intro_candidate"] = request.intro_candidate
            config_overrides.pop("custom_intro_start", None)
            config_overrides.pop("custom_intro_end", None)
            config_overrides.pop("custom_intro_copies", None)
        if request.outro_candidate is not None:
            config_overrides["outro_candidate"] = request.outro_candidate
            config_overrides.pop("custom_outro_start", None)
            config_overrides.pop("custom_outro_end", None)
            config_overrides.pop("custom_outro_copies", None)
        if request.intro_candidate is not None or request.outro_candidate is not None:
            config_overrides["manual_candidate_selection"] = True
        if request.review_candidates is not None:
            config_overrides["review_candidates"] = request.review_candidates
        for position in ("intro", "outro"):
            start = getattr(request, f"custom_{position}_start")
            end = getattr(request, f"custom_{position}_end")
            copies = getattr(request, f"custom_{position}_copies")
            if (start is None) != (end is None):
                raise HTTPException(400, f"Custom {position} requires start and end")
            if start is not None:
                if end <= start:
                    raise HTTPException(400, f"Custom {position} end must follow start")
                config_overrides[f"custom_{position}_start"] = start
                config_overrides[f"custom_{position}_end"] = end
                config_overrides[f"custom_{position}_copies"] = copies or 1
                config_overrides["manual_candidate_selection"] = True
        insert_values = (
            request.insert_source_start,
            request.insert_source_end,
            request.insert_destination,
        )
        if any(value is not None for value in insert_values):
            if any(value is None for value in insert_values):
                raise HTTPException(
                    400, "Insertion requires source start, source end, and destination"
                )
            assert request.insert_source_start is not None
            assert request.insert_source_end is not None
            assert request.insert_destination is not None
            if request.insert_source_end <= request.insert_source_start:
                raise HTTPException(400, "Inserted source end must follow start")
            config_overrides["insert_source_start"] = request.insert_source_start
            config_overrides["insert_source_end"] = request.insert_source_end
            config_overrides["insert_destination"] = request.insert_destination
            config_overrides["insert_copies"] = request.insert_copies or 1
    new_id = jobs_repository.create(
        job["source_name"],
        Path(job["source_path"]),
        preset,
        intro_bars,
        outro_bars,
        use_stems,
        config_overrides,
        parent_job_id=job_id,
    )
    if request is not None and (
        request.review_candidates is not None
        or request.intro_candidate is not None
        or request.outro_candidate is not None
        or request.custom_intro_start is not None
        or request.custom_outro_start is not None
        or request.insert_source_start is not None
    ):
        jobs_repository.update(job_id, review_status="resolved")
    service.enqueue(new_id)
    return {"job_id": new_id}


@app.post("/api/jobs/{job_id}/review/reject")
def reject_review(job_id: int) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.get("review_status") != "pending":
        raise HTTPException(409, "Review is no longer pending")
    jobs_repository.update(job_id, review_status="rejected")
    return {"ok": True}


@app.get("/api/jobs/{job_id}/candidates")
def candidates(job_id: int) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return json.loads(job.get("candidates_json") or "{}")


@app.get("/api/jobs/{job_id}/candidate/{position}/{rank}")
def candidate_audio(job_id: int, position: str, rank: int) -> FileResponse:
    job = jobs_repository.get(job_id)
    if job is None or position not in {"intro", "outro"} or rank not in {1, 2, 3}:
        raise HTTPException(404, "Candidate not found")
    stem = Path(job["source_name"]).stem
    archived = OUTPUT / "versions" / stem / f"job-{job_id}" / "previews"
    folder = archived if archived.is_dir() else OUTPUT / "previews" / stem
    if not folder.is_dir():
        wanted = Path(job["source_name"]).stem.casefold()
        previews = OUTPUT / "previews"
        folder = (
            next(
                (
                    item
                    for item in previews.iterdir()
                    if item.is_dir() and item.name.casefold() == wanted
                ),
                folder,
            )
            if previews.is_dir()
            else folder
        )
    path = folder / f"{position.title()} Candidate {rank}.wav"
    if not path.is_file():
        raise HTTPException(404, "Candidate preview was not generated")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/jobs/{job_id}/feedback")
def save_feedback(job_id: int, request: FeedbackRequest) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if request.position not in {"intro", "outro"}:
        raise HTTPException(400, "Position must be intro or outro")
    feedback_id = feedback_repository.add_feedback(
        job_id,
        request.position,
        request.candidate_rank,
        request.accepted,
        request.tags.strip(),
        request.notes.strip(),
    )
    append_web_feedback(
        OUTPUT,
        job["source_name"],
        request.position,
        request.candidate_rank,
        request.accepted,
        request.tags.strip(),
        request.notes.strip(),
    )
    return {"id": feedback_id}


@app.get("/api/jobs/{job_id}/feedback")
def job_feedback(job_id: int) -> list[dict]:
    return feedback_repository.feedback(job_id)


@app.post("/api/jobs", status_code=202)
async def create_jobs(
    files: Annotated[list[UploadFile], File()],
    preset: Annotated[str, Form()] = "auto",
    intro_bars: Annotated[str, Form()] = "auto",
    outro_bars: Annotated[str, Form()] = "auto",
    use_stems: Annotated[bool, Form()] = False,
    review_candidates: Annotated[bool, Form()] = False,
    auto_bars: Annotated[bool | None, Form()] = None,
    minimum_intro_loop_quality: Annotated[float | None, Form()] = None,
    minimum_outro_loop_quality: Annotated[float | None, Form()] = None,
    maximum_repetitions: Annotated[int | None, Form()] = None,
    crossfade_ms: Annotated[float | None, Form()] = None,
    pcm_bits: Annotated[int | None, Form()] = None,
    preview_seconds: Annotated[float | None, Form()] = None,
    export_cues: Annotated[bool | None, Form()] = None,
    candidate_count: Annotated[int | None, Form()] = None,
    intro_search_seconds: Annotated[float | None, Form()] = None,
    outro_search_seconds: Annotated[float | None, Form()] = None,
    maximum_vocal_coverage_percent: Annotated[float | None, Form()] = None,
    maximum_vocal_boundary_risk_percent: Annotated[float | None, Form()] = None,
    maximum_buildup_risk_percent: Annotated[float | None, Form()] = None,
    maximum_bass_reset_risk_percent: Annotated[float | None, Form()] = None,
    minimum_stem_reliability_percent: Annotated[float | None, Form()] = None,
    analysis_only: Annotated[bool, Form()] = False,
) -> dict:
    if preset != "auto" and preset not in _available_presets():
        raise HTTPException(400, "Unknown preset")
    effective = _effective_settings()
    requested_overrides = {
        key: value
        for key, value in {
            "auto_bars": auto_bars,
            "minimum_intro_loop_quality": minimum_intro_loop_quality,
            "minimum_outro_loop_quality": minimum_outro_loop_quality,
            "maximum_repetitions": maximum_repetitions,
            "crossfade_ms": crossfade_ms,
            "pcm_bits": pcm_bits,
            "preview_seconds": preview_seconds,
            "export_cues": export_cues,
            "candidate_count": candidate_count,
            "intro_search_seconds": intro_search_seconds,
            "outro_search_seconds": outro_search_seconds,
            "maximum_vocal_coverage_percent": maximum_vocal_coverage_percent,
            "maximum_vocal_boundary_risk_percent": maximum_vocal_boundary_risk_percent,
            "maximum_buildup_risk_percent": maximum_buildup_risk_percent,
            "maximum_bass_reset_risk_percent": maximum_bass_reset_risk_percent,
            "minimum_stem_reliability_percent": minimum_stem_reliability_percent,
        }.items()
        if value is not None
    }
    for key in ("minimum_intro_loop_quality", "minimum_outro_loop_quality"):
        value = requested_overrides.get(key)
        if value is not None and not 0 <= float(value) <= 100:
            raise HTTPException(400, "Quality thresholds must be between 0 and 100")
    repetitions = requested_overrides.get("maximum_repetitions")
    if repetitions is not None and not 1 <= int(repetitions) <= 8:
        raise HTTPException(400, "Maximum repetitions must be between 1 and 8")
    fade = requested_overrides.get("crossfade_ms")
    if fade is not None and not 1 <= float(fade) <= 100:
        raise HTTPException(400, "Crossfade must be between 1 and 100 ms")
    if requested_overrides.get("pcm_bits") not in {None, 16, 24}:
        raise HTTPException(400, "PCM depth must be 16 or 24")
    preview = requested_overrides.get("preview_seconds")
    if preview is not None and not 0 < float(preview) <= 60:
        raise HTTPException(400, "Preview context must be between 1 and 60 seconds")
    candidate_depth = requested_overrides.get("candidate_count")
    if candidate_depth is not None and not 1 <= int(candidate_depth) <= 8:
        raise HTTPException(400, "Candidate depth must be between 1 and 8")
    for key in ("intro_search_seconds", "outro_search_seconds"):
        value = requested_overrides.get(key)
        if value is not None and not 15 <= float(value) <= 600:
            raise HTTPException(400, "Search windows must be between 15 and 600 seconds")
    for key in (
        "maximum_vocal_coverage_percent",
        "maximum_vocal_boundary_risk_percent",
        "maximum_buildup_risk_percent",
        "maximum_bass_reset_risk_percent",
        "minimum_stem_reliability_percent",
    ):
        value = requested_overrides.get(key)
        if value is not None and not 0 <= float(value) <= 100:
            raise HTTPException(400, "Analysis percentages must be between 0 and 100")

    def bars(value: str, default_key: str) -> tuple[int, bool]:
        if value == "auto":
            return int(effective[default_key]), True
        try:
            parsed = int(value)
        except ValueError as error:
            raise HTTPException(400, "Unsupported bar count") from error
        if parsed not in SUPPORTED_BAR_COUNTS:
            raise HTTPException(400, "Unsupported bar count")
        return parsed, False

    if analysis_only:
        resolved_intro = resolved_outro = 0
        intro_auto = outro_auto = False
        review_candidates = False
    else:
        resolved_intro, intro_auto = bars(intro_bars, "intro_bars")
        resolved_outro, outro_auto = bars(outro_bars, "outro_bars")
    INPUT.mkdir(parents=True, exist_ok=True)
    created: list[int] = []
    for upload in files:
        filename = Path(upload.filename or "").name
        if not filename or Path(filename).suffix.casefold() not in SUPPORTED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported audio file: {filename or 'unnamed'}")
        destination = INPUT / filename
        with destination.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        job_id = jobs_repository.create(
            filename,
            destination,
            preset,
            resolved_intro,
            resolved_outro,
            use_stems,
            {
                **effective,
                **requested_overrides,
                **_preset_snapshot(preset),
                "review_candidates": review_candidates,
                "analysis_only": analysis_only,
                "intro_bars_auto": intro_auto,
                "outro_bars_auto": outro_auto,
            },
        )
        service.enqueue(job_id)
        created.append(job_id)
    return {"job_ids": created}


@app.get("/api/jobs/{job_id}/audio/{kind}")
def audio(job_id: int, kind: str) -> FileResponse:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    field = {
        "extended": "extended_path",
        "wav": "wav_path",
        "intro-preview": "intro_preview_path",
        "outro-preview": "outro_preview_path",
        "cue-sheet": "cue_sheet_path",
        "rekordbox": "rekordbox_path",
    }.get(kind)
    if field is None:
        raise HTTPException(404, "Unknown download type")
    value = job.get(field)
    if not value or not Path(value).is_file():
        raise HTTPException(404, "Output is not ready")
    media_type = mimetypes.guess_type(value)[0] or "application/octet-stream"
    return FileResponse(value, filename=Path(value).name, media_type=media_type)


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: int, kind: str) -> FileResponse:
    """Retain download URLs while the players use the streaming endpoint."""
    return audio(job_id, kind)


@app.post("/api/library/download")
def batch_download(request: BatchDownloadRequest) -> FileResponse:
    jobs: list[dict] = []
    for job_id in dict.fromkeys(request.job_ids):
        job = jobs_repository.get(job_id)
        if job is None or job["status"] != "complete":
            raise HTTPException(404, f"Completed job {job_id} is unavailable")
        jobs.append(job)

    handle = tempfile.NamedTemporaryFile(prefix="audioextender-", suffix=".zip", delete=False)
    archive = Path(handle.name)
    handle.close()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        included: list[str] = []
        skipped: list[str] = []
        used_names: set[str] = set()
        file_options = {
            "extended": ("extended_path", "Extended WAV"),
            "source": ("wav_path", "Source WAV"),
            "cue-sheet": ("cue_sheet_path", "Cue Sheets"),
            "rekordbox": ("rekordbox_path", "Rekordbox XML"),
            "intro-preview": ("intro_preview_path", "Previews/Intro"),
            "outro-preview": ("outro_preview_path", "Previews/Outro"),
        }
        for job in jobs:
            stem = Path(job["source_name"]).stem
            for file_type in request.file_types:
                if file_type == "analysis":
                    name = f"Analysis Reports/{stem} Analysis.json"
                    if name.casefold() in used_names:
                        name = f"Analysis Reports/{stem} Analysis (job {job['id']}).json"
                    report = {
                        "job_id": job["id"],
                        "source_name": job["source_name"],
                        "processed_at": job["updated_at"],
                        "preset": job["preset"],
                        "bpm": job.get("bpm"),
                        "intro_quality": job.get("intro_quality"),
                        "outro_quality": job.get("outro_quality"),
                        "configuration": json.loads(job.get("config_json") or "{}"),
                        "candidates": json.loads(job.get("candidates_json") or "{}"),
                        "cues": json.loads(job.get("cues_json") or "[]"),
                    }
                    bundle.writestr(name, json.dumps(report, indent=2, ensure_ascii=False))
                    used_names.add(name.casefold())
                    included.append(name)
                    continue
                field, folder = file_options[file_type]
                value = job.get(field)
                path = Path(value) if value else None
                if path is None or not path.is_file():
                    skipped.append(f"{job['source_name']}: {folder} unavailable")
                    continue
                name = f"{folder}/{path.name}"
                if name.casefold() in used_names:
                    name = f"{folder}/{path.stem} (job {job['id']}){path.suffix}"
                bundle.write(path, arcname=name)
                used_names.add(name.casefold())
                included.append(name)
        summary = [
            "DJ Library Studio batch export",
            f"Tracks selected: {len(jobs)}",
            f"Files included: {len(included)}",
            f"Files skipped: {len(skipped)}",
            "",
            "Included:",
            *(included or ["None"]),
            "",
            "Skipped:",
            *(skipped or ["None"]),
        ]
        bundle.writestr("Export Summary.txt", "\n".join(summary) + "\n")
    return FileResponse(
        archive,
        filename="DJ Library Studio Selected Tracks.zip",
        media_type="application/zip",
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


@app.get("/api/jobs/{job_id}/waveform/{kind}")
def waveform(job_id: int, kind: str) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    field = {"wav": "wav_path", "extended": "extended_path"}.get(kind)
    path = Path(job.get(field) or "") if field else Path()
    if field is None or not path.is_file():
        raise HTTPException(404, "Audio is not ready")
    target_points = 1100
    config = service.config_for(job)
    cache = AnalysisCache(Path(config.cache_directory), config.cache_enabled, False)
    waveform_key = f"{path.resolve()}:{target_points}"
    with waveform_generation_locks_guard:
        generation_lock = waveform_generation_locks.setdefault(waveform_key, threading.Lock())
    with generation_lock:
        cached_waveform = cache.load_waveform(path, target_points)
        cache_hit = cached_waveform is not None
        _record_cache_result("waveform", cache_hit)
        if cached_waveform is None:
            info = sf.info(path)
            sample_window = min(2048, max(256, int(info.samplerate * 0.025)))
            envelope = []
            with sf.SoundFile(path) as audio:
                positions = np.linspace(
                    0, max(0, info.frames - sample_window), target_points, dtype=np.int64
                )
                for position in positions:
                    audio.seek(int(position))
                    block = audio.read(sample_window, dtype="float32", always_2d=True)
                    envelope.append(
                        float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))
                        if block.size
                        else 0.0
                    )
            scale = max(float(np.percentile(envelope, 98)), 1e-8) if envelope else 1.0
            peak_values = np.power(np.clip(np.asarray(envelope) / scale, 0.0, 1.0), 1.35).astype(
                np.float32
            )
            duration = float(info.duration)
            cache.save_waveform(path, duration, peak_values, target_points)
        else:
            duration, peak_values = cached_waveform
    timeline: dict[str, list[dict]] = {"behavior": [], "arrangement": [], "edits": []}
    record = track_catalog_repository.get_library_analysis(job_id)
    if record:
        try:
            intro = record.get("intro")
            outro = record.get("outro")
            intro_boundary = float(intro["source_start"]) if intro else None
            intro_shift = (
                max(0.0, float(intro["output_end"]) - float(intro["source_start"]))
                if intro and intro.get("output_end") is not None
                else 0.0
            )
            outro_boundary = float(outro["source_end"]) if outro else None
            outro_shift = (
                max(0.0, float(outro["output_end"]) - float(outro["output_start"]))
                if outro and outro.get("output_end") is not None
                else 0.0
            )

            def output_time(source_time: float) -> float:
                if kind == "wav":
                    return min(duration, source_time)
                value = source_time
                if intro_boundary is not None and source_time >= intro_boundary:
                    value += intro_shift
                if outro_boundary is not None and source_time >= outro_boundary:
                    value += outro_shift
                return min(duration, value)

            for profile in record.get("section_profiles", []):
                timeline["behavior"].append(
                    {
                        **profile,
                        "start": output_time(float(profile["start"])),
                        "end": output_time(float(profile["end"])),
                    }
                )
            for section in record.get("arrangement_sections", []):
                timeline["arrangement"].append(
                    {
                        **section,
                        "start": output_time(float(section["start"])),
                        "end": output_time(float(section["end"])),
                    }
                )
            if kind == "extended":
                for name, candidate in (("Extended intro", intro), ("Extended outro", outro)):
                    if candidate and candidate.get("output_start") is not None:
                        timeline["edits"].append(
                            {
                                "label": name,
                                "start": float(candidate["output_start"]),
                                "end": float(candidate["output_end"]),
                            }
                        )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return {
        "duration": duration,
        "peaks": peak_values.tolist(),
        "timeline": timeline,
        "cache": "hit" if cache_hit else "generated",
    }


@app.post("/api/jobs/{job_id}/transition-score")
def transition_score(job_id: int, request: TransitionScoreRequest) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    source = Path(job["source_path"])
    if not source.is_file():
        raise HTTPException(404, "Source audio is unavailable")
    config = service.config_for(job)
    cache = AnalysisCache(Path(config.cache_directory), config.cache_enabled, False)
    analysis = cache.load_analysis(source, config)
    if analysis is None:
        raise HTTPException(409, "Cached analysis is unavailable; reprocess this track")
    try:
        assessment = assess_custom_insertion(
            analysis,
            request.source_start,
            request.source_end,
            request.destination,
            request.copies,
            cache.load_vocals(source, config),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return assessment.to_dict()


@app.get("/api/jobs/{job_id}/cues")
def cues(job_id: int) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {"cues": json.loads(job.get("cues_json") or "[]")}


@app.put("/api/jobs/{job_id}/cues")
def update_cues(job_id: int, request: CueEditRequest) -> dict:
    job = jobs_repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    values = [cue.model_dump() for cue in request.cues]
    jobs_repository.update(job_id, cues_json=json.dumps(values))
    cue_path = Path(job.get("cue_sheet_path") or "")
    if cue_path.is_file():
        document = json.loads(cue_path.read_text(encoding="utf-8"))
        document["cues"] = values
        cue_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    xml_path = Path(job.get("rekordbox_path") or "")
    if xml_path.is_file():
        tree = ET.parse(xml_path)
        track = tree.getroot().find("./COLLECTION/TRACK")
        if track is not None:
            for marker in list(track.findall("POSITION_MARK")):
                track.remove(marker)
            for cue in values:
                attributes: dict[str, str] = {
                    "Name": str(cue["name"]),
                    "Type": "4" if cue["kind"] == "loop" else "0",
                    "Start": f"{float(cue['start']):.6f}",
                    "Num": "-1",
                }
                if cue["end"] is not None:
                    attributes["End"] = f"{float(cue['end']):.6f}"
                ET.SubElement(track, "POSITION_MARK", attrib=attributes)
        ET.indent(tree.getroot(), space="  ")
        tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
    return {"cues": values}


@app.get("/api/overrides/{source_name}")
def get_override(source_name: str) -> dict:
    override = load_track_overrides(OVERRIDES).get(source_name.casefold())
    return {
        "intro_before": override.intro_before if override else None,
        "outro_after": override.outro_after if override else None,
        "outro_before": override.outro_before if override else None,
    }


@app.put("/api/overrides/{source_name}")
def save_override(source_name: str, request: OverrideRequest) -> dict:
    if request.outro_after and request.outro_before and request.outro_after >= request.outro_before:
        raise HTTPException(400, "Outro start must be earlier than outro end")
    try:
        document = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    except (OSError, ValueError) as error:
        raise HTTPException(500, "Could not read track overrides") from error
    values = request.model_dump()
    if any(value is not None for value in values.values()):
        document[source_name] = values
    else:
        for key in list(document):
            if key.casefold() == source_name.casefold():
                del document[key]
    OVERRIDES.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return values


@app.get("/api/analytics")
def analytics() -> dict:
    now = perf_counter()
    with analytics_cache_lock:
        if analytics_cache["payload"] is not None and now < float(analytics_cache["expires_at"]):
            return analytics_cache["payload"]
    summary = jobs_repository.analytics_summary()
    feedback = summary["feedback"]
    accepted = [item for item in feedback if item["accepted"]]
    tags: dict[str, int] = {}
    for item in feedback:
        for tag in str(item["tags"]).split(","):
            tag = tag.strip().lower()
            if tag:
                tags[tag] = tags.get(tag, 0) + 1
    payload = {
        "completed": summary["completed"],
        "feedback_count": len(feedback),
        "acceptance_rate": len(accepted) / len(feedback) if feedback else None,
        "stemmed_tracks": summary["stemmed"],
        "common_tags": sorted(tags.items(), key=lambda item: item[1], reverse=True),
    }
    with analytics_cache_lock:
        analytics_cache.update(payload=payload, expires_at=now + 15.0)
    return payload


def _load_processing_report() -> dict:
    path = OUTPUT / "reports" / "processing_report.json"
    if not path.exists():
        return {"songs": {}}
    try:
        mtime_ns = path.stat().st_mtime_ns
        with report_cache_lock:
            if report_cache["mtime_ns"] != mtime_ns:
                report_cache["payload"] = json.loads(path.read_text(encoding="utf-8"))
                report_cache["mtime_ns"] = mtime_ns
            return report_cache["payload"]
    except (OSError, ValueError) as error:
        raise HTTPException(500, "The report could not be read") from error


@app.get("/api/report", response_model=None)
def report(recent: int = Query(0, ge=0, le=20)) -> dict | FileResponse:
    path = OUTPUT / "reports" / "processing_report.json"
    if not path.exists():
        return {"songs": {}}
    if not recent:
        return FileResponse(path, media_type="application/json")
    try:
        payload = _load_processing_report()
        songs = [
            song for song in payload.get("songs", {}).values() if song.get("status") == "updated"
        ]
        songs.sort(key=lambda song: str(song.get("updated_at") or ""), reverse=True)
        fields = {"source_name", "status", "updated_at", "bpm", "key", "intro", "outro"}
        return {
            "songs": {
                str(index): {key: value for key, value in song.items() if key in fields}
                for index, song in enumerate(songs[:recent])
            }
        }
    except (OSError, ValueError) as error:
        raise HTTPException(500, "The report could not be read") from error


@app.get("/api/report-audio-index")
def report_audio_index() -> list[dict]:
    """Expose preview availability without loading the full job queue/history."""
    result = []
    for job in jobs_repository.list_report_audio_jobs():
        wav_available = Path(str(job.get("wav_path") or "")).is_file()
        extended_available = Path(str(job.get("extended_path") or "")).is_file()
        result.append(
            {
                "id": int(job["id"]),
                "source_name": str(job["source_name"]),
                "status": "complete",
                "wav_available": wav_available,
                "extended_available": extended_available,
                "downloaded_track_id": job.get("downloaded_track_id"),
                "detected_key": job.get("latest_detected_key") or "",
                "key_confidence": job.get("latest_key_confidence"),
                "key_analyzed_at": job.get("key_analyzed_at") or "",
            }
        )
    return result


def _library_roles(song: dict) -> list[str]:
    style = str(song.get("detected_style") or "").casefold()
    timing = str(song.get("timing") or "").casefold()
    bpm = float(song.get("bpm") or 0)
    intro = song.get("intro") or {}
    outro = song.get("outro") or {}
    roles: set[str] = set()
    if "ambient" in style or "sparse" in style:
        roles.add("ambient")
    if "melodic" in style or "harmonic" in style or float(song.get("key_confidence") or 0) >= 0.65:
        roles.add("melodic")
    if (
        "vocal-safe" in style
        or max(float(intro.get("instrumentalness") or 0), float(outro.get("instrumentalness") or 0))
        >= 0.72
    ):
        roles.add("vocal-safe")
    if "live" in timing or "variable" in timing or float(song.get("tempo_drift") or 0) >= 0.08:
        roles.add("live timing")
    if "peak" in style or "high-energy" in style or (bpm >= 122 and "ambient" not in roles):
        roles.add("peak-time")
    if "slow" in style or "subtle" in style or (bpm and bpm < 120) or "ambient" in roles:
        roles.add("warm-up")
    readiness = song.get("dj_readiness") or {}
    if (
        "closing" in style
        or float(readiness.get("outro_mixable_bars") or 0) >= 8
        or outro.get("section") == "closing"
    ):
        roles.add("closing")
    if not roles:
        roles.add("peak-time" if bpm >= 122 else "warm-up")
    return sorted(roles)


def _library_energy(song: dict) -> float:
    values: list[float] = []
    for section in song.get("section_profiles") or []:
        match = re.search(r"energy\s+([\d.]+)", str(section.get("reason") or ""), re.I)
        if match:
            try:
                values.append(float(match.group(1)))
            except ValueError:
                pass
    if values:
        return sum(values) / len(values)
    style = str(song.get("detected_style") or "").casefold()
    return (
        0.8
        if "high-energy" in style or "peak" in style
        else 0.25
        if "ambient" in style or "sparse" in style
        else 0.5
    )


def _set_builder_analysis(
    song: dict, *, roles: list[str], energy: float, vocals: str, timing: str
) -> dict:
    base_fields = {
        "source_name",
        "bpm",
        "key",
        "key_confidence",
        "beat_grid_confidence",
        "duration_seconds",
        "mix_in",
        "mix_out",
    }
    compact = {key: value for key, value in song.items() if key in base_fields}
    compact.update(
        {
            "_roles": roles,
            "_energy": energy,
            "_vocals": vocals,
            "_timing": timing,
            "intro": {
                key: value
                for key, value in (song.get("intro") or {}).items()
                if key in {"instrumentalness", "section"}
            },
            "outro": {
                key: value
                for key, value in (song.get("outro") or {}).items()
                if key in {"instrumentalness", "section"}
            },
            "dj_readiness": {
                key: value
                for key, value in (song.get("dj_readiness") or {}).items()
                if key in {"intro_mixable_bars", "outro_mixable_bars"}
            },
            "arrangement_sections": [
                {
                    key: value
                    for key, value in section.items()
                    if key in {"label", "name", "start", "end", "confidence"}
                }
                for section in (song.get("arrangement_sections") or [])
            ],
        }
    )
    return compact


def _build_set_builder_catalog_payload() -> dict:
    tracks = []
    for row in track_catalog_repository.list_set_builder_tracks():
        tracks.append(
            {
                "analysis": json.loads(row.get("set_analysis_json") or "{}"),
                "genre": row.get("category") or "Other",
                "detailed_genre": row.get("detail_genre") or "",
                "job": {
                    "id": row["job_id"],
                    "source_name": row["source_name"],
                    "source_path": row.get("source_path"),
                    "wav_path": row.get("wav_path"),
                    "library_path": row.get("library_path"),
                    "extended_path": row.get("extended_path"),
                    "config_json": row.get("config_json") or "{}",
                },
            }
        )
    return {"version": 2, "tracks": tracks, "total": len(tracks)}


def _write_set_builder_catalog_cache() -> None:
    payload = _build_set_builder_catalog_payload()
    SET_BUILDER_CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SET_BUILDER_CATALOG_CACHE.with_suffix(".pending.json")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(SET_BUILDER_CATALOG_CACHE)


_CAMELOT_KEYS = {
    "A minor": "8A",
    "E minor": "9A",
    "B minor": "10A",
    "F# minor": "11A",
    "C# minor": "12A",
    "G# minor": "1A",
    "D# minor": "2A",
    "A# minor": "3A",
    "F minor": "4A",
    "C minor": "5A",
    "G minor": "6A",
    "D minor": "7A",
    "C major": "8B",
    "G major": "9B",
    "D major": "10B",
    "A major": "11B",
    "E major": "12B",
    "B major": "1B",
    "F# major": "2B",
    "C# major": "3B",
    "G# major": "4B",
    "D# major": "5B",
    "A# major": "6B",
    "F major": "7B",
}


def _refresh_library_search_index() -> None:
    analysis_by_name = {
        str(song.get("source_name") or "").casefold(): song
        for song in _load_processing_report().get("songs", {}).values()
    }
    downloaded_tracks = track_catalog_repository.list_downloaded_tracks_with_jobs()
    downloaded_by_path = {str(track.get("file_path") or ""): track for track in downloaded_tracks}
    downloaded_by_job = {
        int(track["completed_library_job_id"]): track
        for track in downloaded_tracks
        if track.get("completed_library_job_id")
    }
    key_verifications = {
        str(item["source_name"]).casefold(): item
        for item in feedback_repository.key_verifications()
    }
    entries = []
    for job in jobs_repository.list_latest_completed_jobs():
        song = dict(analysis_by_name.get(str(job.get("source_name") or "").casefold(), {}))
        verification = key_verifications.get(str(job.get("source_name") or "").casefold())
        if verification:
            song["detected_key"] = song.get("key")
            song["key"] = verification["verified_key"]
            song["key_confidence"] = 1.0
            song["key_verified"] = True
        downloaded = downloaded_by_job.get(int(job["id"])) or downloaded_by_path.get(
            str(job.get("source_path") or "")
        )
        if downloaded and downloaded.get("key_analyzed_at"):
            song["key"] = downloaded.get("detected_key") or song.get("key")
            song["key_confidence"] = float(downloaded.get("key_confidence") or 0) / 100.0
        source_stem = re.sub(r"\.[^.]+$", "", str(job.get("source_name") or ""))
        source_parts = source_stem.split(" - ")
        title = str(downloaded.get("title") or "") if downloaded else ""
        artist = str(downloaded.get("artist") or "") if downloaded else ""
        title = title or (" - ".join(source_parts[1:]) if len(source_parts) > 1 else source_stem)
        artist = artist or (source_parts[0] if len(source_parts) > 1 else "Unknown artist")
        category = (
            _normalize_genre_category(str(downloaded.get("genre_category") or "Other"))
            if downloaded
            else str(song.get("detected_style") or "Unclassified")
        )
        roles = _library_roles(song)
        energy = _library_energy(song)
        analyzed_preset = str(song.get("preset") or "")
        preset = (
            analyzed_preset.split("→")[-1].strip()
            if "→" in analyzed_preset
            else analyzed_preset.strip()
        ) or str(job.get("preset") or "default")
        result = (
            "review"
            if job.get("review_status") == "pending"
            else "extended"
            if job.get("intro_quality") is not None or job.get("outro_quality") is not None
            else "preserved"
        )
        musical_key = (
            str(song.get("key") or "")
            .replace("Db ", "C# ")
            .replace("Eb ", "D# ")
            .replace("Gb ", "F# ")
            .replace("Ab ", "G# ")
            .replace("Bb ", "A# ")
        )
        instrumental_values = [
            float(value)
            for value in (
                (song.get("intro") or {}).get("instrumentalness"),
                (song.get("outro") or {}).get("instrumentalness"),
            )
            if value is not None
        ]
        instrumental = max(instrumental_values) if instrumental_values else None
        timing_text = str(song.get("timing") or "").casefold()
        vocal_profile = (
            "mixed"
            if instrumental is None
            else "vocal-safe"
            if instrumental >= 0.72
            else "vocal-forward"
            if instrumental < 0.45
            else "mixed"
        )
        timing_profile = (
            "variable"
            if "live" in timing_text
            or "variable" in timing_text
            or float(song.get("tempo_drift") or 0) >= 0.08
            else "steady"
        )
        entries.append(
            {
                "job_id": int(job["id"]),
                "source_name": job["source_name"],
                "title": title,
                "artist": artist,
                "downloaded_id": int(downloaded["id"]) if downloaded else None,
                "category": category,
                "detail_genre": str(downloaded.get("genre") or "").strip() if downloaded else "",
                "roles": f"|{'|'.join(roles)}|",
                "preset": preset.casefold(),
                "requested_preset": str(job.get("preset") or "default").casefold(),
                "result": result,
                "bpm": float(song.get("bpm") or job.get("bpm") or 0),
                "musical_key": musical_key,
                "camelot": _CAMELOT_KEYS.get(musical_key, ""),
                "energy": energy,
                "energy_band": "high" if energy >= 0.67 else "low" if energy < 0.4 else "medium",
                "vocals": vocal_profile,
                "timing": timing_profile,
                "updated_at": job["updated_at"],
                "analysis_json": json.dumps(song, separators=(",", ":")),
                "set_analysis_json": json.dumps(
                    _set_builder_analysis(
                        song,
                        roles=roles,
                        energy=energy,
                        vocals=vocal_profile,
                        timing=timing_profile,
                    ),
                    separators=(",", ":"),
                ),
            }
        )
    track_catalog_repository.replace_library_search_index(entries)
    _write_set_builder_catalog_cache()


def _ensure_library_search_index_current() -> tuple[tuple[int, int], ...]:
    """Refresh the compact Library index only when its inputs have changed."""
    _ensure_downloaded_catalog_migrated()
    report_path = OUTPUT / "reports" / "processing_report.json"
    report_signature = (
        (report_path.stat().st_mtime_ns, report_path.stat().st_size)
        if report_path.exists()
        else (0, 0)
    )
    source_signature = track_catalog_repository.library_index_source_signature()
    signature_text = json.dumps(
        {"version": 4, "report": report_signature, "sources": source_signature},
        separators=(",", ":"),
    )
    signature = (report_signature, (hash(source_signature), len(source_signature)))
    with library_catalog_cache_lock:
        memory_current = library_catalog_cache.get("signature") == signature
    persisted_current = (
        settings_repository.get_system_state("library_search_index_signature") == signature_text
    )
    needs_refresh = not memory_current and not persisted_current
    if needs_refresh and track_catalog_repository.library_index_count() > 0:
        global library_index_refresh_active
        with library_index_refresh_lock:
            if not library_index_refresh_active:
                library_index_refresh_active = True
                threading.Thread(
                    target=_refresh_library_index_background,
                    name="library-index-refresh",
                    daemon=True,
                ).start()
        return signature
    if needs_refresh:
        _refresh_library_search_index()
        source_signature = track_catalog_repository.library_index_source_signature()
        signature_text = json.dumps(
            {"version": 4, "report": report_signature, "sources": source_signature},
            separators=(",", ":"),
        )
        signature = (report_signature, (hash(source_signature), len(source_signature)))
        settings_repository.set_system_state("library_search_index_signature", signature_text)
    with library_catalog_cache_lock:
        library_catalog_cache["signature"] = signature
    return signature


def _refresh_library_index_background() -> None:
    global library_index_refresh_active
    try:
        _refresh_library_search_index()
        report_path = OUTPUT / "reports" / "processing_report.json"
        report_signature = (
            (report_path.stat().st_mtime_ns, report_path.stat().st_size)
            if report_path.exists()
            else (0, 0)
        )
        source_signature = track_catalog_repository.library_index_source_signature()
        signature_text = json.dumps(
            {"version": 4, "report": report_signature, "sources": source_signature},
            separators=(",", ":"),
        )
        settings_repository.set_system_state("library_search_index_signature", signature_text)
        with library_catalog_cache_lock:
            library_catalog_cache["signature"] = (
                report_signature,
                (hash(source_signature), len(source_signature)),
            )
    finally:
        with library_index_refresh_lock:
            library_index_refresh_active = False


@app.get("/api/set-builder/catalog", response_model=None)
def set_builder_catalog() -> FileResponse | dict:
    """All latest analyzed tracks, without loading the full job history."""
    _ensure_library_search_index_current()
    cache_current = False
    try:
        cache_current = (
            json.loads(SET_BUILDER_CATALOG_CACHE.read_text(encoding="utf-8")).get("version") == 2
        )
    except (OSError, ValueError):
        pass
    if not cache_current:
        _write_set_builder_catalog_cache()
    return FileResponse(
        SET_BUILDER_CATALOG_CACHE,
        media_type="application/json",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/api/set-builder/export-preflight")
def set_builder_export_preflight(request: SetExportPreflightRequest) -> dict:
    """Verify every local audio path before a Rekordbox playlist is exported."""
    items = []
    for raw_path in request.paths:
        value = str(raw_path or "").strip()
        path = Path(value).expanduser() if value else None
        exists = bool(path and path.is_file())
        items.append(
            {
                "path": str(path) if path else value,
                "exists": exists,
                "reason": ""
                if exists
                else ("No file path is available" if not value else "File is missing from disk"),
            }
        )
    valid = sum(1 for item in items if item["exists"])
    return {
        "ready": valid == len(items) and bool(items),
        "valid": valid,
        "missing": len(items) - valid,
        "total": len(items),
        "items": items,
    }


@app.post("/api/set-builder/save-playlist")
def set_builder_save_playlist(request: SetPlaylistSaveRequest) -> dict:
    """Persist a created set beside the organized music library."""
    missing = [
        track.path for track in request.tracks if not Path(track.path).expanduser().is_file()
    ]
    if missing:
        raise HTTPException(
            409,
            detail={
                "message": "Playlist contains files that are missing from disk.",
                "missing": missing,
            },
        )
    playlist_directory = _music_library_root() / "_Playlist"
    playlist_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_folder_name(request.name)}.m3u8"
    playlist_path = playlist_directory / filename
    lines = ["#EXTM3U"]
    for track in request.tracks:
        lines.extend(
            [
                f"#EXTINF:{round(track.duration_seconds)},{track.title or Path(track.path).stem}",
                str(Path(track.path).expanduser().resolve()),
            ]
        )
    playlist_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return {"saved": True, "path": str(playlist_path), "tracks": len(request.tracks)}


@app.get("/api/library/catalog")
def library_catalog(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str = "",
    role: str = "all",
    category: str = "all",
    detailed_genre: str = "all",
    preset: str = "all",
    result: str = "all",
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    key: str = "all",
    energy: str = "all",
    vocals: str = "all",
    timing: str = "all",
    quality: str = Query(
        default="all", pattern="^(all|excellent|good|review|poor|below-target|unanalyzed)$"
    ),
    sort: str = "newest",
) -> dict:
    """Compact Library index; expensive generation history stays lazy."""
    signature = _ensure_library_search_index_current()
    rows, filtered_total = track_catalog_repository.page_library_tracks(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        category=category,
        detail_genre=detailed_genre,
        preset=preset,
        result=result,
        quality=quality,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        musical_key=key,
        energy=energy,
        vocals=vocals,
        timing=timing,
        sort=sort,
    )
    with library_catalog_cache_lock:
        cached_facets = (
            library_catalog_cache.get("facets")
            if library_catalog_cache.get("facets_signature") == signature
            else None
        )
    if cached_facets is None:
        facets = track_catalog_repository.library_search_facets()
        with library_catalog_cache_lock:
            library_catalog_cache["facets_signature"] = signature
            library_catalog_cache["facets"] = facets
        facets = dict(facets)
    else:
        # The endpoint removes the intelligence payload below, so copy the
        # shallow containers while retaining immutable row dictionaries.
        facets = dict(cached_facets)
    total_pages = max(1, math.ceil(filtered_total / page_size))
    if page > total_pages:
        page = total_pages
        rows, filtered_total = track_catalog_repository.page_library_tracks(
            page=page,
            page_size=page_size,
            search=search,
            role=role,
            category=category,
            detail_genre=detailed_genre,
            preset=preset,
            result=result,
            quality=quality,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            musical_key=key,
            energy=energy,
            vocals=vocals,
            timing=timing,
            sort=sort,
        )
    tracks = []
    for row in rows:
        row.pop("analysis_json", None)
        analysis = {
            "source_name": row.get("source_name") or "",
            "bpm": row.get("library_bpm") or row.get("bpm") or 0,
            "key": row.get("musical_key") or "",
            "_roles": str(row.get("library_roles") or "").strip("|").split("|"),
            "_energy": row.get("library_energy"),
            "_vocals": row.get("vocals") or "mixed",
            "_timing": row.get("timing") or "steady",
        }
        downloaded = None
        if row.get("downloaded_id"):
            try:
                quality_details = json.loads(str(row.get("audio_quality_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                quality_details = {}
            downloaded = {
                "id": row["downloaded_id"],
                "title": row["library_title"],
                "artist": row["library_artist"],
                "genre": row.get("genre") or "",
                "genre_category": row["library_category"],
                "recording_code": row.get("recording_code") or "",
                "version_code": row.get("version_code") or "",
                "identity_confidence": row.get("identity_confidence") or "",
                "identity_reason": row.get("identity_reason") or "",
                "audio_quality_score": row.get("audio_quality_score"),
                "audio_quality_label": row.get("audio_quality_label") or "",
                "audio_quality": quality_details,
                "suggested_genre": _generalized_genre(str(row.get("genre") or "")),
                "completed_library_job_id": row["job_id"],
                "artwork_available": bool(row.get("artwork_path"))
                and Path(str(row["artwork_path"])).is_file(),
            }
        job = {
            key: row.get(key)
            for key in (
                "id",
                "source_name",
                "source_path",
                "status",
                "progress",
                "stage",
                "preset",
                "intro_bars",
                "outro_bars",
                "use_stems",
                "config_json",
                "error",
                "extended_path",
                "wav_path",
                "intro_preview_path",
                "outro_preview_path",
                "cue_sheet_path",
                "rekordbox_path",
                "parent_job_id",
                "bpm",
                "intro_quality",
                "outro_quality",
                "review_status",
                "created_at",
                "updated_at",
                "generation_count",
            )
        }
        tracks.append({"job": job, "analysis": analysis, "downloaded": downloaded})
    intelligence = [
        {
            "job_id": item["job_id"],
            "source_name": item["source_name"],
            "analysis": {
                "source_name": item["source_name"],
                "bpm": item["bpm"],
                "key": item["musical_key"],
                "_roles": str(item.get("roles") or "").strip("|").split("|"),
                "_energy": item["energy"],
                "_vocals": item["vocals"],
                "_timing": item["timing"],
            },
        }
        for item in facets.pop("intelligence")
    ]
    payload = {
        "tracks": tracks,
        "total": facets["total"],
        "filtered_total": filtered_total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "facets": facets,
        "intelligence": intelligence,
    }
    return payload


@app.get("/api/library/jobs/{job_id}/details")
def library_job_details(job_id: int) -> dict:
    job = jobs_repository.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(404, "Library track not found")
    return {
        "job": job,
        "versions": jobs_repository.list_completed_versions(str(job["source_path"])),
    }


@app.get("/api/report-feedback")
def report_feedback() -> list[dict]:
    return feedback_repository.track_feedback()


@app.post("/api/report-feedback")
def save_report_feedback(request: TrackFeedbackRequest) -> dict:
    if request.position not in {"intro", "outro", "overall"}:
        raise HTTPException(400, "Position must be intro, outro, or overall")
    source_name = Path(request.source_name).name
    feedback_id = feedback_repository.add_track_feedback(
        source_name,
        request.position,
        request.accepted,
        request.tags.strip(),
        request.notes.strip(),
    )
    append_web_feedback(
        OUTPUT,
        source_name,
        request.position,
        None,
        request.accepted,
        request.tags.strip(),
        request.notes.strip(),
    )
    return {"id": feedback_id}


@app.get("/api/key-verifications")
def key_verifications() -> dict:
    items = feedback_repository.key_verifications()
    detector_totals: dict[str, int] = {}
    detector_correct: dict[str, int] = {}
    for item in items:
        verified = str(item.get("verified_key") or "")
        seen: set[str] = set()
        for candidate in item.get("candidates") or []:
            for detector in str(candidate.get("detectors") or "").split(","):
                detector = detector.strip()
                if not detector or detector in seen:
                    continue
                seen.add(detector)
                detector_totals[detector] = detector_totals.get(detector, 0) + 1
                if str(candidate.get("key") or "") == verified:
                    detector_correct[detector] = detector_correct.get(detector, 0) + 1
    accuracy = {
        detector: {
            "correct": detector_correct.get(detector, 0),
            "total": total,
            "accuracy": detector_correct.get(detector, 0) / total if total else None,
        }
        for detector, total in detector_totals.items()
    }
    return {"items": items, "total": len(items), "detector_accuracy": accuracy}


@app.put("/api/key-verifications/{source_name:path}")
def save_key_verification(source_name: str, request: KeyVerificationRequest) -> dict:
    normalized_source = Path(source_name).name
    if Path(request.source_name).name.casefold() != normalized_source.casefold():
        raise HTTPException(400, "Track identity does not match")
    normalized_key = request.verified_key.strip().replace("♭", "b").replace("♯", "#")
    aliases = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    parts = normalized_key.split()
    if len(parts) == 2 and parts[0] in aliases:
        normalized_key = f"{aliases[parts[0]]} {parts[1].casefold()}"
    if normalized_key not in _CAMELOT_KEYS:
        raise HTTPException(400, "Choose a valid major or minor key")
    saved = feedback_repository.set_key_verification(
        normalized_source,
        normalized_key,
        request.detected_key.strip(),
        request.candidates,
        request.notes.strip(),
    )
    _refresh_library_search_index()
    return saved


@app.delete("/api/key-verifications/{source_name:path}")
def remove_key_verification(source_name: str) -> dict:
    removed = feedback_repository.delete_key_verification(Path(source_name).name)
    if removed:
        _refresh_library_search_index()
    return {"removed": removed}


@app.get("/api/feedback")
def feedback() -> dict:
    path = OUTPUT / "reports" / "Candidate Feedback.md"
    return {"markdown": path.read_text(encoding="utf-8") if path.exists() else ""}


if __name__ == "__main__":
    uvicorn.run("web_app:app", host="127.0.0.1", port=8765, reload=False)
