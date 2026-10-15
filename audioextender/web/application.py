"""Local DJ Library Studio web interface; the AudioExtender CLI remains independent."""

# Runtime compatibility names are installed atomically by ``_bind_runtime``.
# They intentionally do not exist while this module is only being imported.
# ruff: noqa: F821
# mypy: disable-error-code="name-defined"

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlencode, urlparse

import httpx
import uvicorn
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.middleware.gzip import GZipMiddleware

from audioextender.audio.loading import SUPPORTED_EXTENSIONS
from audioextender.audio.quality import analyze_audio_quality
from audioextender.audio.wav_metadata import (
    embed_wav_artwork,
    read_wav_artwork,
    read_wav_metadata,
    sync_wav_metadata,
    write_wav_metadata,
)
from audioextender.core.operation_feedback import operation_receipt
from audioextender.core.presets import PRESETS, EditPreset
from audioextender.imports.creative_commons import CreativeCommonsImportService
from audioextender.imports.local import LocalAudioImportService
from audioextender.imports.playlist_match import PlaylistMatchService
from audioextender.imports.routes import AuthorizedImportRequest, create_import_router
from audioextender.imports.service import (
    ImportService,
    authorized_source_provider,
    scdl_download_command,
)
from audioextender.library.catalog_query_service import (
    DownloadedCatalogQuery,
    DownloadedCatalogQueryService,
)
from audioextender.library.metadata_mutations import (
    TrackMetadataMutationDependencies,
    TrackMetadataMutationService,
)
from audioextender.library.musical_corrections import MusicalCorrectionIndex
from audioextender.library.musical_profile import CAMELOT_KEYS, musical_profile
from audioextender.library.track_overrides import load_track_overrides
from audioextender.processing.job_workflows import (
    JobCreationCommand,
    JobWorkflowError,
    JobWorkflowService,
    UploadedAudio,
)
from audioextender.reporting.feedback import append_web_feedback
from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.journey_planner import JourneyPlanner
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.preference_learning import (
    DJPreferenceService,
    JsonPreferenceStore,
    PersonalizedCandidateRanker,
)
from audioextender.set_builder.review_service import SetReviewService
from audioextender.set_builder.track_planner import AITrackPlanner, SetPlanningModelClient
from audioextender.web.composition import (
    ApplicationPaths,
    ApplicationRuntime,
    LazyApplication,
    runtime_bindings,
)
from audioextender.web.descriptor_routes import (
    DescriptorRouteDependencies,
    create_descriptor_router,
)
from audioextender.web.error_contracts import install_error_handlers
from audioextender.web.job_media_routes import (
    BatchDownloadRequest,  # noqa: F401 - compatibility re-export
    JobMediaRouteDependencies,
    create_job_media_router,
)
from audioextender.web.job_routes import (
    JobQueueService,
    create_job_router,
)
from audioextender.web.library_maintenance_routes import (
    LibraryMaintenanceDependencies,
    LibraryMaintenanceService,
    create_library_maintenance_router,
)
from audioextender.web.library_routes import (
    LibraryRouteDependencies,
    create_library_router,
)
from audioextender.web.metadata_batch_routes import (
    MetadataBatchDependencies,
    MetadataBatchService,
    create_metadata_batch_router,
)
from audioextender.web.reporting_routes import (
    ReportingRouteDependencies,
    create_reporting_router,
)
from audioextender.web.set_builder_routes import (
    SetBuilderRouteDependencies,
    SetExportPreflightRequest,  # noqa: F401 - compatibility re-export
    SetPlaylistSaveRequest,  # noqa: F401 - compatibility re-export
    SetPlaylistTrack,  # noqa: F401 - compatibility re-export
    create_set_builder_router,
    preflight_paths,
    save_playlist_file,
)
from audioextender.web.set_planning_routes import SetPlanningRouteDependencies, create_set_planning_router
from audioextender.web.set_preference_routes import create_set_preference_router
from audioextender.web.set_review_routes import create_set_review_router
from audioextender.web.settings_routes import (
    SettingsRouteDependencies,
    create_settings_router,
)
from settings import (
    CACHE_FOLDER_NAME,
    DEFAULT_AUTO_BAR_SELECTION,
    DEFAULT_CANDIDATE_COUNT,
    DEFAULT_EXPORT_CUES,
    DEFAULT_INTRO_BARS,
    DEFAULT_MINIMUM_INTRO_LOOP_QUALITY,
    DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY,
    DEFAULT_OUTRO_BARS,
    DEFAULT_PCM_BITS,
    DEFAULT_PRESET,
    DEFAULT_PREVIEW_SECONDS,
    DEFAULT_USE_STEMS,
    INTRO_SEARCH_SECONDS,
    MAXIMUM_BASS_RESET_RISK,
    MAXIMUM_BUILDUP_RISK,
    MAXIMUM_VOCAL_BOUNDARY_RISK,
    MAXIMUM_VOCAL_COVERAGE,
    MINIMUM_CROSSFADE_MS,
    MINIMUM_STEM_CONSTRUCTION_RELIABILITY,
    OUTRO_SEARCH_SECONDS,
    SUPPORTED_BAR_COUNTS,
)

DEFAULT_PATHS = ApplicationPaths.from_project(Path(__file__).resolve().parents[2])
PROJECT = DEFAULT_PATHS.project
INPUT = DEFAULT_PATHS.input
OUTPUT = DEFAULT_PATHS.output
WEB = DEFAULT_PATHS.web
DATABASE = DEFAULT_PATHS.database
OVERRIDES = DEFAULT_PATHS.overrides
WEB_PRESETS = DEFAULT_PATHS.presets
SET_BUILDER_CATALOG_CACHE = DEFAULT_PATHS.set_builder_catalog_cache
DEFAULT_MUSIC_LIBRARY = DEFAULT_PATHS.default_music_library
BACKUP_ROOT = DEFAULT_PATHS.backup_root
STORAGE_INVENTORY_SNAPSHOT = DEFAULT_PATHS.storage_inventory_snapshot

legacy_router = APIRouter()
logger = logging.getLogger("uvicorn.error")
wav_tag_audit_refresh_active = False
downloaded_catalog_migrated = False
DOWNLOADED_CATALOG_MIGRATION_VERSION = "3"
artwork_thumbnail_worker_started = False
library_index_refresh_active = False
jobs_watchdog_last = 0.0


def _record_cache_result(cache_name: str, hit: bool) -> None:
    with performance_diagnostics_lock:
        counters = performance_cache_stats.setdefault(cache_name, {"hits": 0, "misses": 0})
        counters["hits" if hit else "misses"] += 1


async def record_api_performance(request: Request, call_next):
    """Keep a small, process-local timing window for actionable UI diagnostics."""
    if not request.url.path.startswith("/api/") or request.url.path == "/api/diagnostics/performance":
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


@legacy_router.get("/api/diagnostics/performance")
def performance_diagnostics_report() -> dict:
    with performance_diagnostics_lock:
        samples = list(performance_diagnostics)
        cache_snapshot = {name: dict(values) for name, values in performance_cache_stats.items()}

    grouped: dict[str, list[dict[str, object]]] = {}
    for sample in samples:
        key = f"{sample['method']} {sample['path']}"
        grouped.setdefault(key, []).append(sample)

    operations = []
    for operation, entries in grouped.items():
        durations = sorted(float(cast(Any, entry["duration_ms"])) for entry in entries)
        percentile_index = round((len(durations) - 1) * 0.95)
        operations.append(
            {
                "operation": operation,
                "count": len(entries),
                "average_ms": round(sum(durations) / len(durations), 1),
                "p95_ms": durations[percentile_index],
                "maximum_ms": durations[-1],
                "failures": sum(int(cast(Any, entry["status"])) >= 400 for entry in entries),
                "average_response_bytes": round(
                    sum(int(cast(Any, entry.get("response_bytes") or 0)) for entry in entries) / len(entries)
                ),
            }
        )
    operations.sort(key=lambda item: (-float(cast(Any, item["p95_ms"])), -int(cast(Any, item["count"]))))

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
    slow = [sample for sample in reversed(samples) if float(cast(Any, sample["duration_ms"])) >= 250][:20]
    durations = [float(cast(Any, sample["duration_ms"])) for sample in samples]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_size": len(samples),
        "window_limit": performance_diagnostics.maxlen,
        "overall_average_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "operations": operations,
        "recent_slow_operations": slow,
        "cache": cache,
    }


@legacy_router.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


WEB_DEFAULTS = {
    "music_library_path": DEFAULT_MUSIC_LIBRARY,
    "preset": DEFAULT_PRESET or "auto",
    "intro_bars": DEFAULT_INTRO_BARS,
    "outro_bars": DEFAULT_OUTRO_BARS,
    "use_stems": DEFAULT_USE_STEMS,
    "auto_bars": DEFAULT_AUTO_BAR_SELECTION,
    "minimum_intro_loop_quality": DEFAULT_MINIMUM_INTRO_LOOP_QUALITY,
    "minimum_outro_loop_quality": DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY,
    "pcm_bits": DEFAULT_PCM_BITS,
    "preview_seconds": DEFAULT_PREVIEW_SECONDS,
    "export_cues": DEFAULT_EXPORT_CUES,
    "maximum_repetitions": 8,
    "crossfade_ms": MINIMUM_CROSSFADE_MS,
    "candidate_count": DEFAULT_CANDIDATE_COUNT,
    "intro_search_seconds": INTRO_SEARCH_SECONDS,
    "outro_search_seconds": OUTRO_SEARCH_SECONDS,
    "maximum_vocal_coverage_percent": round(MAXIMUM_VOCAL_COVERAGE * 100, 6),
    "maximum_vocal_boundary_risk_percent": round(MAXIMUM_VOCAL_BOUNDARY_RISK * 100, 6),
    "maximum_buildup_risk_percent": round(MAXIMUM_BUILDUP_RISK * 100, 6),
    "maximum_bass_reset_risk_percent": round(MAXIMUM_BASS_RESET_RISK * 100, 6),
    "minimum_stem_reliability_percent": round(MINIMUM_STEM_CONSTRUCTION_RELIABILITY * 100, 6),
}


class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")
    intro_bars: int
    outro_bars: int
    use_stems: bool = False
    minimum_loop_quality: float = Field(ge=0, le=100)
    maximum_repetitions: int = Field(ge=1, le=8)


def _preset_state() -> dict:
    try:
        state = json.loads(WEB_PRESETS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = {}
    return {
        "definitions": dict(state.get("definitions") or {}),
        "hidden": list(state.get("hidden") or []),
    }


def _save_preset_state(state: dict) -> None:
    WEB_PRESETS.parent.mkdir(parents=True, exist_ok=True)
    temporary = WEB_PRESETS.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(WEB_PRESETS)


def _available_presets() -> dict[str, EditPreset]:
    state = _preset_state()
    available = dict(PRESETS)
    for name, values in state["definitions"].items():
        try:
            available[name] = EditPreset(**values)
        except (TypeError, ValueError):
            continue
    for name in state["hidden"]:
        available.pop(name, None)
    return available


def _preset_payload() -> list[dict]:
    state = _preset_state()
    return [
        {
            "name": name,
            **preset.__dict__,
            "built_in": name in PRESETS,
            "modified": name in state["definitions"],
        }
        for name, preset in _available_presets().items()
    ]


def _preset_snapshot(name: str) -> dict:
    preset = _available_presets().get(name)
    return {"preset_definition": preset.__dict__} if preset is not None else {}


class FeedbackRequest(BaseModel):
    position: str
    candidate_rank: int | None = None
    accepted: bool
    tags: str = ""
    notes: str = ""


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


class OverrideRequest(BaseModel):
    intro_before: float | None = Field(None, gt=0)
    outro_after: float | None = Field(None, gt=0)
    outro_before: float | None = Field(None, gt=0)


def _effective_settings() -> dict:
    overrides = repository.get_settings()
    durable_library_path = repository.get_system_state("music_library_path")
    return {
        **WEB_DEFAULTS,
        **({"music_library_path": durable_library_path} if durable_library_path else {}),
        **overrides,
    }


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
    for track in repository.list_downloaded_tracks():
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


@legacy_router.get("/api/presets")
def list_presets() -> dict:
    return {"presets": _preset_payload()}


@legacy_router.put("/api/presets/{current_name}")
def save_preset(current_name: str, request: PresetRequest) -> dict:
    if request.intro_bars not in SUPPORTED_BAR_COUNTS or request.outro_bars not in SUPPORTED_BAR_COUNTS:
        raise HTTPException(400, "Unsupported bar count")
    state = _preset_state()
    if current_name != request.name and request.name in _available_presets():
        raise HTTPException(409, "A preset with that name already exists")
    if current_name != request.name:
        state["definitions"].pop(current_name, None)
        if current_name in PRESETS and current_name not in state["hidden"]:
            state["hidden"].append(current_name)
    state["hidden"] = [name for name in state["hidden"] if name != request.name]
    state["definitions"][request.name] = {key: value for key, value in request.model_dump().items() if key != "name"}
    _save_preset_state(state)
    return {"presets": _preset_payload()}


@legacy_router.delete("/api/presets/{name}")
def delete_preset(name: str) -> dict:
    if name not in _available_presets():
        raise HTTPException(404, "Preset not found")
    state = _preset_state()
    state["definitions"].pop(name, None)
    if name in PRESETS and name not in state["hidden"]:
        state["hidden"].append(name)
    _save_preset_state(state)
    return {"presets": _preset_payload()}


@legacy_router.post("/api/presets/restore")
def restore_presets() -> dict:
    _save_preset_state({"definitions": {}, "hidden": []})
    return {"presets": _preset_payload()}


def _match_tracks_to_youtube(tracks: list[dict], progress: Callable[..., None]) -> list[dict]:
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
                    "youtube_url": (f"https://www.youtube.com/watch?v={video_id}" if video_id else None),
                    "youtube_duration": match.get("duration"),
                    "match_score": match_score,
                    "match_warnings": warnings,
                }
            )
            progress(
                stage=f"Matching {index} of {len(tracks)}",
                progress=round(index * 100 / len(tracks), 1),
                matched=index,
                total=len(tracks),
            )
    return results


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
        candidate_context = candidate_title | _match_tokens(entry.get("channel")) | _match_tokens(entry.get("uploader"))
        title_coverage = len(expected_title & candidate_title) / max(1, len(expected_title))
        artist_coverage = len(expected_artist & candidate_context) / len(expected_artist) if expected_artist else 1.0
        extra_bad = (unwanted & candidate_title) - expected_all
        expected_versions = expected_title & version_tokens
        candidate_versions = candidate_title & version_tokens
        version_mismatch = bool(candidate_versions - expected_versions)
        duration = float(entry.get("duration") or 0)
        duration_difference = abs(duration - expected_duration) if duration and expected_duration else 0
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
    """Compatibility wrapper for callers that import this legacy helper."""
    return authorized_source_provider(url)


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


@legacy_router.post("/api/imports/source-match")
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
        {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True, "playlistend": 8}
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
        (fields[name] for name in ("artist name(s)", "artist name", "artists", "artist") if name in fields),
        None,
    )
    if title_field is None or artist_field is None:
        raise ValueError("CSV needs track and artist columns, such as Track Name and Artist Name(s)")
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


def _safe_audio_name(value: str) -> str:
    cleaned = "".join(character for character in value if character not in '<>:"/\\|?*')
    return cleaned.strip()[:180] or "Imported Audio"


def _generalized_genre(value: str) -> str:
    """Map detailed Spotify-style genres to practical, broad DJ library folders."""
    genre = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
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
            ("regional mexican", "musica mexicana", "banda", "norteno", "sierreno", "ranchera", "mariachi"),
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
    latin_matches = [(genre.find(term), family) for family, terms in latin_families for term in terms if term in genre]
    if latin_matches:
        return f"Latin / {min(latin_matches, key=lambda match: match[0])[1]}"
    electronic_matches = [
        (genre.find(term), family)
        for family, terms in electronic_families
        for term in terms
        if term in genre and (term != "electro" or re.search(r"(?<![a-z0-9])electro(?![a-z0-9])", genre))
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
    matched = next((family for family, terms in families if any(term in genre for term in terms)), "")
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
            for track in repository.list_downloaded_tracks()
            if track.get("youtube_id") == video_id and Path(str(track.get("file_path") or "")).is_file()
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
        playlist_name = str(metadata.get("playlist_name") or "Legacy Imports")
        stored_category = str(metadata.get("genre_category") or "")
        detailed_genre = str(metadata.get("genre") or "")
        category = _catalog_genre_category(wav_path, stored_category, detailed_genre)
        repository.upsert_downloaded_track(
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
    repository.upsert_catalog_source_signatures(signatures)
    return results


def _ensure_downloaded_catalog_migrated() -> None:
    """Run legacy migration once per schema version, not once per restart."""
    global downloaded_catalog_migrated
    if downloaded_catalog_migrated:
        return
    with downloaded_catalog_migration_lock:
        if downloaded_catalog_migrated:
            return
        if repository.get_system_state("downloaded_catalog_migration") != DOWNLOADED_CATALOG_MIGRATION_VERSION:
            _migrate_downloaded_catalog()
            repository.set_system_state("downloaded_catalog_migration", DOWNLOADED_CATALOG_MIGRATION_VERSION)
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
        artwork_dir = _require_music_library_online() / ".artwork"
        artwork_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if content_type == "image/png" else ".jpg"
        artwork_file = artwork_dir / f"{hashlib.sha256(artwork_url.encode()).hexdigest()[:24]}{suffix}"
        artwork_file.write_bytes(response.content)
        embed_wav_artwork(destination, artwork_file, content_type)
        return str(artwork_file)
    except Exception:
        return ""


def _creative_commons_worker(batch_id: str, tracks: list[CreativeCommonsMatch], playlist_name: str) -> None:
    report: dict[str, list[dict]] = {
        "downloaded": [],
        "already_downloaded": [],
        "skipped_not_creative_commons": [],
        "failed": [],
    }
    safe_playlist = _safe_folder_name(playlist_name)
    try:
        destination_dir = _require_music_library_online()
    except Exception as error:
        with creative_commons_batch_lock:
            creative_commons_batches[batch_id].update(
                status="failed", stage="Music library disconnected", error=str(error)
            )
        return
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
                    _generalized_genre(track.genre) if track.genre else _normalize_genre_category(track.genre_category)
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
                                json.loads(source_record.read_text(encoding="utf-8")).get("youtube_id", "")
                            )
                        except (OSError, json.JSONDecodeError):
                            recorded_video_id = ""
                    if destination.exists() and recorded_video_id == video_id:
                        base["filename"] = output_name
                        report["already_downloaded"].append(base)
                        repository.upsert_downloaded_track(
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
                        repository.resolve_import_failure(
                            playlist_name=track_playlist, title=track.title, artist=track.artist
                        )
                        continue
                    if destination.exists():
                        original_stem = destination.stem
                        copy_number = 2
                        while destination.exists():
                            destination = destination.with_name(f"{original_stem} ({copy_number}){destination.suffix}")
                            copy_number += 1
                        output_name = destination.name
                        source_record = _source_metadata_path(destination)
                    with tempfile.TemporaryDirectory(prefix="audioextender-cc-import-") as temporary:
                        options = {
                            "format": "bestaudio/best",
                            "outtmpl": str(Path(temporary) / "source.%(ext)s"),
                            "noplaylist": True,
                            "quiet": True,
                            "no_warnings": True,
                            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
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
                repository.upsert_downloaded_track(
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
                repository.resolve_import_failure(playlist_name=track_playlist, title=track.title, artist=track.artist)
            except Exception as error:
                report["failed"].append({**base, "error": str(error)})
                repository.record_import_failure(
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
            creative_commons_batches[batch_id].update(status="failed", stage="Batch import failed", error=str(error))


@legacy_router.post("/api/imports/creative-commons", status_code=202)
def create_creative_commons_batch(request: CreativeCommonsBatchRequest) -> dict:
    try:
        return creative_commons_service.start(request.tracks, request.playlist_name)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@legacy_router.get("/api/imports/creative-commons/{batch_id}")
def creative_commons_batch_status(batch_id: str) -> dict:
    try:
        return creative_commons_service.status(batch_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@legacy_router.get("/api/imports/creative-commons/{batch_id}/download")
def download_creative_commons_batch(batch_id: str) -> FileResponse:
    with creative_commons_batch_lock:
        state = creative_commons_batches.get(batch_id)
        playlist_name = str(state.get("playlist_name") or "Imported Playlist") if state else "Imported Playlist"
        report_data = dict(state.get("report") or {}) if state else {}
    included = list(report_data.get("downloaded") or []) + list(report_data.get("already_downloaded") or [])
    if not included:
        raise HTTPException(404, "No verified Creative Commons WAV files are available")
    safe_playlist = _safe_folder_name(playlist_name)
    temporary = tempfile.NamedTemporaryFile(prefix=f"{safe_playlist}-", suffix="-WAVs.zip", delete=False)
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
                    else _music_library_root().joinpath(*_genre_path_parts(category), str(item.get("filename") or ""))
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


@legacy_router.get("/api/imports/creative-commons/{batch_id}/report")
def download_creative_commons_report(batch_id: str) -> FileResponse:
    with creative_commons_batch_lock:
        state = creative_commons_batches.get(batch_id)
        path = Path(state["report_path"]) if state and state.get("report_path") else None
    if path is None or not path.exists():
        raise HTTPException(404, "Creative Commons import report is not available")
    with creative_commons_batch_lock:
        playlist_name = str(creative_commons_batches.get(batch_id, {}).get("playlist_name") or "Imported Playlist")
    return FileResponse(path, filename=f"{_safe_folder_name(playlist_name)} - Import Report.json")


@legacy_router.get("/api/imports/failures")
def list_import_failures() -> dict:
    if not repository.list_import_failures(include_resolved=True):
        for report_path in (OUTPUT / "reports" / "imports").glob("**/*Import Report.json"):
            try:
                document = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            playlist_name = str(document.get("playlist_name") or report_path.parent.name)
            for item in (document.get("results") or {}).get("failed", []):
                repository.record_import_failure(
                    playlist_name=playlist_name,
                    title=str(item.get("title") or item.get("filename") or "Unknown track"),
                    artist=str(item.get("artist") or ""),
                    spotify_uri=str(item.get("spotify_uri") or ""),
                    youtube_url=str(item.get("url") or item.get("youtube_url") or ""),
                    error=str(item.get("error") or "Download failed"),
                )
    failures = repository.list_import_failures()
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
                            _generalized_genre(genre) if genre else _normalize_genre_category(category or "Other")
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
                    part for part in (str(failure.get("artist") or ""), str(failure.get("title") or "")) if part
                )
                old_url = str(failure.get("youtube_url") or "")
                old_id_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]+)", old_url)
                old_id = old_id_match.group(1) if old_id_match else ""
                info = searcher.extract_info(f"ytsearch8:{query}", download=False) or {}
                entries = [entry for entry in (info.get("entries") or []) if str(entry.get("id") or "") != old_id]
                match, _, _ = _best_youtube_match(failure, entries)
                video_id = str(match.get("id") or "")
                source_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else old_url
                if not source_url:
                    repository.record_import_failure(
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


@legacy_router.post("/api/imports/failures/retry", status_code=202)
def retry_import_failures(request: ImportFailureRetryRequest) -> dict:
    wanted = set(request.failure_ids)
    failures = [item for item in repository.list_import_failures() if int(item["id"]) in wanted]
    if len(failures) != len(wanted):
        raise HTTPException(404, "One or more import issues are no longer available")
    return creative_commons_service.start_retry(failures)


@legacy_router.delete("/api/imports/failures/{failure_id}")
def dismiss_import_failure(failure_id: int) -> dict:
    failures = repository.list_import_failures(include_resolved=True)
    failure = next((item for item in failures if int(item["id"]) == failure_id), None)
    if failure is None:
        raise HTTPException(404, "Import failure not found")
    repository.resolve_import_failure(
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
    tags = {str(key).casefold(): str(value).strip() for key, value in (format_data.get("tags") or {}).items()}
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


def _scdl_download_command(url: str, destination: Path) -> list[str]:
    """Compatibility wrapper for callers that import this legacy helper."""
    return scdl_download_command(url, destination)


def _authorized_import_worker(import_id: str, request: AuthorizedImportRequest) -> None:
    """Compatibility entry point for deterministic worker tests."""
    import_service.run(import_id, request)


def _downloaded_track_payload(track: dict) -> dict:
    suggested_genre = _generalized_genre(str(track.get("genre") or ""))
    current_genre = _normalize_genre_category(str(track.get("genre_category") or "Other"))
    try:
        descriptors = json.loads(str(track.get("descriptors_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        descriptors = []
    payload = {
        key: value for key, value in track.items() if key not in {"file_path", "artwork_path", "descriptors_json"}
    } | {
        "absolute_path": str(Path(str(track.get("file_path") or "")).expanduser().resolve()),
        "available": Path(track["file_path"]).is_file(),
        "artwork_available": bool(track.get("artwork_path")) and Path(str(track["artwork_path"])).is_file(),
        "genre_category": current_genre,
        "suggested_genre": suggested_genre,
        "needs_genre": current_genre in {"Other", "Latin / Other"},
        "descriptors": descriptors,
    }
    return payload


def _run_audio_quality_batch(batch_id: str) -> None:
    tracks = repository.list_downloaded_tracks()

    def inspect(track: dict) -> tuple[dict, Path, dict | None, str]:
        path = Path(str(track.get("file_path") or ""))
        try:
            if not path.is_file():
                raise FileNotFoundError("Audio file is unavailable")
            result = analyze_audio_quality(
                path,
                window_seconds=0.5,
                source_is_transcoded_lossy=bool(track.get("youtube_id") or track.get("youtube_url")),
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
                repository.update_audio_quality(int(track["id"]), result)
            with audio_quality_batch_lock:
                batch = audio_quality_batches[batch_id]
                batch["processed"] = index
                batch["failed"] += int(bool(error))
                batch["current"] = str(track.get("filename") or track.get("title") or "")
                if error and len(batch["errors"]) < 30:
                    batch["errors"].append({"id": track.get("id"), "filename": path.name, "error": error})
    summary = repository.audio_quality_summary()
    with audio_quality_batch_lock:
        audio_quality_batches[batch_id].update(status="complete", stage="Quality scan complete", summary=summary)
    with library_status_cache_lock:
        library_status_cache.update(payload=None, expires_at=0.0)


@legacy_router.post("/api/downloaded-library/audio-quality")
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
        total = len(repository.list_downloaded_tracks())
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
        target=_run_audio_quality_batch, args=(batch_id,), daemon=True, name=f"audio-quality-{batch_id[:8]}"
    ).start()
    return {"batch_id": batch_id, **audio_quality_batches[batch_id]}


@legacy_router.get("/api/downloaded-library/audio-quality-latest")
def latest_audio_quality_scan() -> dict:
    with audio_quality_batch_lock:
        if not audio_quality_batches:
            return {"status": "none", "summary": repository.audio_quality_summary()}
        batch_id = next(reversed(audio_quality_batches))
        return {"batch_id": batch_id, **audio_quality_batches[batch_id]}


@legacy_router.get("/api/downloaded-library/audio-quality/{batch_id}")
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


@legacy_router.get("/api/downloaded-library")
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
    quality: str = Query(default="all", pattern="^(all|excellent|good|review|poor|below-target|unanalyzed)$"),
    sort: str = Query(default="newest", max_length=30),
) -> dict:
    return downloaded_catalog_query_service.execute(
        DownloadedCatalogQuery(
            paged=paged,
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
    )


@legacy_router.get("/api/downloaded-library/tracks/{track_id}/audio")
def downloaded_track_audio(track_id: int) -> FileResponse:
    track = repository.get_downloaded_track(track_id)
    path = Path(track["file_path"]) if track else None
    if path is None or not path.is_file():
        raise HTTPException(404, "Downloaded WAV is unavailable")
    return FileResponse(path, filename=path.name, media_type="audio/wav")


@legacy_router.get("/api/downloaded-library/tracks/{track_id}/artwork")
def downloaded_track_artwork(track_id: int, thumbnail: bool = False) -> FileResponse:
    track = repository.get_downloaded_track(track_id)
    path = Path(str(track.get("artwork_path") or "")) if track else None
    if path is None or not path.is_file():
        raise HTTPException(404, "Track artwork is unavailable")
    if thumbnail:
        path = _cached_artwork_thumbnail(path)
    media_type = "image/png" if path.suffix.casefold() == ".png" else "image/jpeg"
    headers = {"Cache-Control": "public, max-age=31536000, immutable"} if thumbnail else None
    return FileResponse(path, media_type=media_type, headers=headers)


@legacy_router.get("/api/downloaded-library/tracks/{track_id}/download")
def downloaded_track_download(track_id: int) -> FileResponse:
    return downloaded_track_audio(track_id)


@legacy_router.post("/api/downloaded-library/tracks/{track_id}/reveal")
def reveal_downloaded_track(track_id: int) -> dict:
    """Reveal a cataloged audio file using the host operating system's file browser."""
    track = repository.get_downloaded_track(track_id)
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


@legacy_router.delete("/api/downloaded-library/tracks/{track_id}")
def remove_downloaded_track(track_id: int) -> dict:
    if not repository.delete_downloaded_track(track_id):
        raise HTTPException(404, "Downloaded track was not found")
    return {"removed": True, "track_id": track_id}


@legacy_router.delete("/api/downloaded-library/tracks")
def remove_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    requested = set(request.track_ids)
    removed = sum(1 for track_id in requested if repository.delete_downloaded_track(track_id))
    return {"removed": removed, "requested": len(requested)}


@legacy_router.get("/api/downloaded-library/duplicate-candidates")
def downloaded_duplicate_candidates() -> dict:
    candidates = repository.duplicate_candidates()
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


@legacy_router.post("/api/downloaded-library/merge-duplicate")
def merge_downloaded_duplicate(request: DuplicateMergeRequest) -> dict:
    try:
        track = repository.merge_downloaded_tracks(request.survivor_id, request.duplicate_id)
    except KeyError as error:
        raise HTTPException(404, "One or more tracks were not found") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"merged": True, "track": _downloaded_track_payload(track)}


@legacy_router.post("/api/downloaded-library/tracks/{track_id}/keep-separate")
def keep_downloaded_track_separate(track_id: int) -> dict:
    try:
        track = repository.separate_recording(track_id)
    except KeyError as error:
        raise HTTPException(404, "Track was not found") from error
    return {"updated": True, "track": _downloaded_track_payload(track)}


@legacy_router.get("/api/downloaded-library/tracks/{track_id}/family")
def downloaded_track_family(track_id: int) -> dict:
    try:
        family = repository.recording_family(track_id)
        suggestions = repository.recording_family_suggestions(track_id)
    except KeyError as error:
        raise HTTPException(404, "Track was not found") from error
    return {
        "family": [_downloaded_track_payload(track) for track in family],
        "suggestions": [{**item, "track": _downloaded_track_payload(item["track"])} for item in suggestions],
    }


@legacy_router.post("/api/downloaded-library/tracks/{track_id}/link-version")
def link_downloaded_track_version(track_id: int, request: TrackFamilyLinkRequest) -> dict:
    target_track_id = request.target_track_id or repository.track_id_for_identity(request.target_identity)
    if target_track_id is None:
        raise HTTPException(404, "Target track ID was not found")
    try:
        track = repository.link_recording_version(track_id, target_track_id, request.relationship)
    except KeyError as error:
        raise HTTPException(404, "One or more tracks were not found") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"updated": True, "track": _downloaded_track_payload(track)}


@legacy_router.post("/api/downloaded-library/tracks/{track_id}/unlink-version")
def unlink_downloaded_track_version(track_id: int) -> dict:
    """Create a new family for a track; this is the safe inverse of linking."""
    return keep_downloaded_track_separate(track_id)


def _downloaded_archive(tracks: list[dict], name: str) -> FileResponse:
    available = [track for track in tracks if Path(track["file_path"]).is_file()]
    if not available:
        raise HTTPException(404, "No downloaded WAV files are available for this selection")
    handle = tempfile.NamedTemporaryFile(prefix="audioextender-downloads-", suffix=".zip", delete=False)
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


@legacy_router.post("/api/downloaded-library/download")
def download_selected_tracks(request: DownloadedTracksRequest) -> FileResponse:
    wanted = set(request.track_ids)
    tracks = [track for track in repository.list_downloaded_tracks() if track["id"] in wanted]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    return _downloaded_archive(tracks, "Selected Downloaded Tracks")


@legacy_router.post("/api/downloaded-library/analyze", status_code=202)
def analyze_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    wanted = set(request.track_ids)
    tracks = [track for track in repository.list_downloaded_tracks() if track["id"] in wanted]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    return _queue_downloaded_analysis(tracks)


@legacy_router.post("/api/downloaded-library/reanalyze", status_code=202)
def reanalyze_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    wanted = set(request.track_ids)
    tracks = [track for track in repository.list_downloaded_tracks_with_jobs() if track["id"] in wanted]
    if len(tracks) != len(wanted):
        raise HTTPException(404, "One or more downloaded tracks were not found")
    return _queue_downloaded_analysis(tracks, force=True)


def _queue_downloaded_analysis(tracks: list[dict], *, force: bool = False) -> dict:
    existing_paths = {
        str(Path(job["source_path"]).resolve())
        for job in repository.list_jobs(limit=10_000)
        if job["status"]
        in ({"queued", "processing", "paused"} if force else {"queued", "processing", "paused", "complete"})
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
        job_id = repository.create(
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
                int(track["completed_library_job_id"]) if force and track.get("completed_library_job_id") else None
            ),
        )
        created.append(job_id)
        existing_paths.add(str(source.resolve()))
    service.enqueue_many(created)
    return {"job_ids": created, "skipped": skipped, "unavailable": unavailable}


@legacy_router.post("/api/downloaded-library/analyze-matching", status_code=202)
def analyze_matching_downloaded_tracks(request: DownloadedAnalysisFilterRequest) -> dict:
    if request.analysis in {"complete", "active"}:
        return {"job_ids": [], "skipped": [], "unavailable": [], "matched": 0}
    tracks, _ = repository.page_downloaded_tracks(
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


@legacy_router.post("/api/downloaded-library/reanalyze-matching", status_code=202)
def reanalyze_matching_downloaded_tracks(request: DownloadedAnalysisFilterRequest) -> dict:
    tracks, _ = repository.page_downloaded_tracks(
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


@legacy_router.patch("/api/downloaded-library/genre")
def change_downloaded_genre(request: DownloadedGenreRequest) -> dict:
    try:
        result = track_metadata_mutations.change_genre(request.track_ids, request.genre_category)
        return {
            **result,
            "receipt": operation_receipt(
                operation="change-track-genre",
                requested=f"Move {len(set(request.track_ids))} tracks to {request.genre_category}",
                requested_count=len(set(request.track_ids)),
                changed=f"Moved and retagged {result['updated']} tracks",
                changed_count=int(result["updated"]),
                written_to=[str(_genre_directory(result["genre_category"]))],
                survives_restart=True,
                durability="WAV locations, embedded tags, sidecars, and catalog paths were persisted.",
            ),
        }
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except (FileNotFoundError, FileExistsError) as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(500, f"Could not change genre: {error}") from error


@legacy_router.patch("/api/downloaded-library/tracks/{track_id}/metadata")
def update_downloaded_track_metadata(track_id: int, request: DownloadedMetadataRequest) -> dict:
    """Synchronize editable identity fields across disk, WAV tags, and Library records."""
    track = repository.get_downloaded_track(track_id)
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
        if artwork_url and (artwork_url != str(track.get("artwork_url") or "") or not Path(artwork_path).is_file()):
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
            repository.update_downloaded_track_artwork(track_id, artwork_url=artwork_url, artwork_path=artwork_path)
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
        "receipt": operation_receipt(
            operation="save-track-metadata",
            requested=f"Save metadata for track {track_id}",
            requested_count=1,
            changed="Updated the WAV tags, source record, and catalog entry",
            changed_count=1,
            written_to=[
                str(destination.resolve()),
                str(_source_metadata_path(destination)),
                str(getattr(repository, "path", DATABASE)),
            ],
            survives_restart=True,
            durability="The WAV, source sidecar, and catalog database were updated on disk.",
        ),
    }


@legacy_router.post("/api/downloaded-library/repair-playlist-derived-genres")
def repair_playlist_derived_genres() -> dict:
    """Replace playlist labels accidentally stored as detailed track genres."""
    repaired: list[int] = []
    restored: list[int] = []
    cleared: list[int] = []
    failed: list[dict[str, object]] = []
    for track in repository.list_downloaded_tracks():
        playlists = [str(value).strip() for value in (track.get("playlists") or []) if str(value).strip()]
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


@legacy_router.post("/api/downloaded-library/retag")
def retag_downloaded_tracks(request: DownloadedTracksRequest) -> dict:
    """Synchronize embedded WAV tags from the authoritative music catalog."""
    _require_music_library_online()
    wanted = set(request.track_ids)
    tracks = [track for track in repository.list_downloaded_tracks() if int(track["id"]) in wanted]
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
    return {
        "tagged": tagged,
        "skipped": skipped,
        "failed": failed,
        "receipt": operation_receipt(
            operation="retag-selected-tracks",
            requested=f"Synchronize WAV tags for {len(wanted)} selected tracks",
            requested_count=len(wanted),
            changed=f"Updated {len(tagged)} WAV files; {len(skipped)} were already correct",
            changed_count=len(tagged),
            written_to=[str(Path(str(track["file_path"])).resolve()) for track in tracks if int(track["id"]) in tagged],
            failures=failed,
            survives_restart=True,
            durability="Embedded WAV tags are stored in the audio files and survive restart.",
        ),
    }


def _refresh_wav_tag_audit() -> dict:
    tracks = repository.list_downloaded_tracks()
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
    repository.set_system_state(
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


@legacy_router.get("/api/downloaded-library/genres/{genre}/download")
def download_genre(genre: str) -> FileResponse:
    tracks = [
        track
        for track in repository.list_downloaded_tracks()
        if str(track.get("genre_category") or "Other").casefold() == genre.casefold()
    ]
    return _downloaded_archive(tracks, genre)


@legacy_router.get("/api/downloaded-library/playlists/{playlist}/download")
def download_playlist(playlist: str) -> FileResponse:
    tracks = [
        track
        for track in repository.list_downloaded_tracks()
        if any(item.casefold() == playlist.casefold() for item in track.get("playlists", []))
    ]
    return _downloaded_archive(tracks, playlist)


@legacy_router.delete("/api/library/{source_name}")
def remove_library_track(source_name: str) -> dict:
    """Remove every inactive generation from the Library without deleting exports."""
    matching = [
        job for job in repository.list_jobs(10_000) if str(job["source_name"]).casefold() == source_name.casefold()
    ]
    if not matching:
        raise HTTPException(404, "Library track not found")
    if any(job["status"] in {"queued", "processing"} for job in matching):
        raise HTTPException(409, "Cancel or finish this track before removing it")
    removed = sum(int(repository.delete(int(job["id"]))) for job in matching)
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


@legacy_router.post("/api/jobs/{job_id}/reprocess", status_code=202)
def reprocess_job(job_id: int, request: ReprocessRequest | None = None) -> dict:
    try:
        return job_workflow_service.reprocess(job_id, request.model_dump() if request is not None else None)
    except JobWorkflowError as error:
        raise HTTPException(error.status_code, error.detail) from error


def _legacy_reprocess_job(job_id: int, request: ReprocessRequest | None = None) -> dict:
    job = repository.get(job_id)
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
                raise HTTPException(400, "Insertion requires source start, source end, and destination")
            assert request.insert_source_start is not None
            assert request.insert_source_end is not None
            assert request.insert_destination is not None
            if request.insert_source_end <= request.insert_source_start:
                raise HTTPException(400, "Inserted source end must follow start")
            config_overrides["insert_source_start"] = request.insert_source_start
            config_overrides["insert_source_end"] = request.insert_source_end
            config_overrides["insert_destination"] = request.insert_destination
            config_overrides["insert_copies"] = request.insert_copies or 1
    new_id = repository.create(
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
        repository.update(job_id, review_status="resolved")
    service.enqueue(new_id)
    return {"job_id": new_id}


@legacy_router.post("/api/jobs/{job_id}/review/reject")
def reject_review(job_id: int) -> dict:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.get("review_status") != "pending":
        raise HTTPException(409, "Review is no longer pending")
    repository.update(job_id, review_status="rejected")
    return {"ok": True}


@legacy_router.get("/api/jobs/{job_id}/candidates")
def candidates(job_id: int) -> dict:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return json.loads(job.get("candidates_json") or "{}")


@legacy_router.get("/api/jobs/{job_id}/candidate/{position}/{rank}")
def candidate_audio(job_id: int, position: str, rank: int) -> FileResponse:
    job = repository.get(job_id)
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
                (item for item in previews.iterdir() if item.is_dir() and item.name.casefold() == wanted),
                folder,
            )
            if previews.is_dir()
            else folder
        )
    path = folder / f"{position.title()} Candidate {rank}.wav"
    if not path.is_file():
        raise HTTPException(404, "Candidate preview was not generated")
    return FileResponse(path, media_type="audio/wav")


@legacy_router.post("/api/jobs/{job_id}/feedback")
def save_feedback(job_id: int, request: FeedbackRequest) -> dict:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if request.position not in {"intro", "outro"}:
        raise HTTPException(400, "Position must be intro or outro")
    feedback_id = repository.add_feedback(
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


@legacy_router.get("/api/jobs/{job_id}/feedback")
def job_feedback(job_id: int) -> list[dict]:
    return repository.feedback(job_id)


@legacy_router.post("/api/jobs", status_code=202)
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
    overrides = {
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
    }
    try:
        return job_workflow_service.create(
            [UploadedAudio(Path(upload.filename or "").name, upload.file) for upload in files],
            JobCreationCommand(
                preset=preset,
                intro_bars=intro_bars,
                outro_bars=outro_bars,
                use_stems=use_stems,
                review_candidates=review_candidates,
                analysis_only=analysis_only,
                overrides=overrides,
            ),
        )
    except JobWorkflowError as error:
        raise HTTPException(error.status_code, error.detail) from error


async def _legacy_create_jobs(
    files: Annotated[list[UploadFile], File()],
    preset: str = "auto",
    intro_bars: str = "auto",
    outro_bars: str = "auto",
    use_stems: bool = False,
    review_candidates: bool = False,
    auto_bars: bool | None = None,
    minimum_intro_loop_quality: float | None = None,
    minimum_outro_loop_quality: float | None = None,
    maximum_repetitions: int | None = None,
    crossfade_ms: float | None = None,
    pcm_bits: int | None = None,
    preview_seconds: float | None = None,
    export_cues: bool | None = None,
    candidate_count: int | None = None,
    intro_search_seconds: float | None = None,
    outro_search_seconds: float | None = None,
    maximum_vocal_coverage_percent: float | None = None,
    maximum_vocal_boundary_risk_percent: float | None = None,
    maximum_buildup_risk_percent: float | None = None,
    maximum_bass_reset_risk_percent: float | None = None,
    minimum_stem_reliability_percent: float | None = None,
    analysis_only: bool = False,
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
        job_id = repository.create(
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


@legacy_router.get("/api/overrides/{source_name}")
def get_override(source_name: str) -> dict:
    override = load_track_overrides(OVERRIDES).get(source_name.casefold())
    return {
        "intro_before": override.intro_before if override else None,
        "outro_after": override.outro_after if override else None,
        "outro_before": override.outro_before if override else None,
    }


@legacy_router.put("/api/overrides/{source_name}")
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


@legacy_router.get("/api/analytics")
def analytics() -> dict:
    now = perf_counter()
    with analytics_cache_lock:
        if analytics_cache["payload"] is not None and now < float(cast(Any, analytics_cache["expires_at"])):
            return cast(dict, analytics_cache["payload"])
    summary = repository.analytics_summary()
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
            return cast(dict, report_cache["payload"])
    except (OSError, ValueError) as error:
        raise HTTPException(500, "The report could not be read") from error


@legacy_router.get("/api/report", response_model=None)
def report(recent: int = Query(0, ge=0, le=20)) -> dict | FileResponse:
    path = OUTPUT / "reports" / "processing_report.json"
    if not path.exists():
        return {"songs": {}}
    if not recent:
        return FileResponse(path, media_type="application/json")
    try:
        payload = _load_processing_report()
        songs = [song for song in payload.get("songs", {}).values() if song.get("status") == "updated"]
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


@legacy_router.get("/api/report-audio-index")
def report_audio_index() -> list[dict]:
    """Expose preview availability without loading the full job queue/history."""
    result = []
    for job in repository.list_report_audio_jobs():
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
    return musical_profile(song)["roles"]


def _library_energy(song: dict) -> float:
    return float(musical_profile(song)["energy"])


def _set_builder_analysis(song: dict, *, roles: list[str], energy: float, vocals: str, timing: str) -> dict:
    profile = musical_profile(song | {"_roles": roles, "_energy": energy, "_vocals": vocals, "_timing": timing})
    base_fields = {
        "source_name",
        "bpm",
        "detected_bpm",
        "bpm_verified",
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
            "musical_profile": profile,
            "intro": {
                key: value for key, value in (song.get("intro") or {}).items() if key in {"instrumentalness", "section"}
            },
            "outro": {
                key: value for key, value in (song.get("outro") or {}).items() if key in {"instrumentalness", "section"}
            },
            "dj_readiness": {
                key: value
                for key, value in (song.get("dj_readiness") or {}).items()
                if key in {"intro_mixable_bars", "outro_mixable_bars"}
            },
            "arrangement_sections": [
                {key: value for key, value in section.items() if key in {"label", "name", "start", "end", "confidence"}}
                for section in (song.get("arrangement_sections") or [])
            ],
        }
    )
    return compact


def _build_set_builder_catalog_payload() -> dict:
    tracks = []
    for row in repository.list_set_builder_tracks():
        try:
            descriptors = json.loads(str(row.get("descriptors_json") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            descriptors = []
        analysis = json.loads(row.get("set_analysis_json") or "{}")
        analysis.update(
            title=row.get("title") or "",
            artist=row.get("artist") or "",
            _camelot=row.get("camelot") or "",
        )
        tracks.append(
            {
                "analysis": analysis,
                "genre": row.get("category") or "Other",
                "detailed_genre": row.get("detail_genre") or "",
                "downloaded_id": row.get("downloaded_id"),
                "descriptors": descriptors,
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
    return {"version": 5, "tracks": tracks, "total": len(tracks)}


def _write_set_builder_catalog_cache() -> None:
    payload = _build_set_builder_catalog_payload()
    SET_BUILDER_CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SET_BUILDER_CATALOG_CACHE.with_suffix(".pending.json")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(SET_BUILDER_CATALOG_CACHE)


_CAMELOT_KEYS = CAMELOT_KEYS


def _refresh_library_search_index() -> None:
    analysis_by_name = {
        str(song.get("source_name") or "").casefold(): song
        for song in _load_processing_report().get("songs", {}).values()
    }
    downloaded_tracks = repository.list_downloaded_tracks_with_jobs()
    downloaded_by_path = {str(track.get("file_path") or ""): track for track in downloaded_tracks}
    downloaded_by_job = {
        int(track["completed_library_job_id"]): track
        for track in downloaded_tracks
        if track.get("completed_library_job_id")
    }
    corrections = MusicalCorrectionIndex.from_records(repository.key_verifications(), repository.bpm_verifications())
    entries = []
    for job in repository.list_latest_completed_jobs():
        song = dict(analysis_by_name.get(str(job.get("source_name") or "").casefold(), {}))
        song = corrections.apply(song, str(job.get("source_name") or ""), detected_bpm_fallback=job.get("bpm"))
        downloaded = downloaded_by_job.get(int(job["id"])) or downloaded_by_path.get(str(job.get("source_path") or ""))
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
        preset = (analyzed_preset.split("→")[-1].strip() if "→" in analyzed_preset else analyzed_preset.strip()) or str(
            job.get("preset") or "default"
        )
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
            if "live" in timing_text or "variable" in timing_text or float(song.get("tempo_drift") or 0) >= 0.08
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
                        song, roles=roles, energy=energy, vocals=vocal_profile, timing=timing_profile
                    ),
                    separators=(",", ":"),
                ),
            }
        )
    repository.replace_library_search_index(entries)
    _write_set_builder_catalog_cache()


def _ensure_library_search_index_current() -> tuple[tuple[int, int], ...]:
    """Refresh the compact Library index only when its inputs have changed."""
    _ensure_downloaded_catalog_migrated()
    report_path = OUTPUT / "reports" / "processing_report.json"
    report_signature = (report_path.stat().st_mtime_ns, report_path.stat().st_size) if report_path.exists() else (0, 0)
    source_signature = repository.library_index_source_signature()
    signature_text = json.dumps(
        {"version": 5, "report": report_signature, "sources": source_signature}, separators=(",", ":")
    )
    signature = (report_signature, (hash(source_signature), len(source_signature)))
    with library_catalog_cache_lock:
        memory_current = library_catalog_cache.get("signature") == signature
    persisted_current = repository.get_system_state("library_search_index_signature") == signature_text
    needs_refresh = not memory_current and not persisted_current
    if needs_refresh and repository.library_index_count() > 0:
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
        source_signature = repository.library_index_source_signature()
        signature_text = json.dumps(
            {"version": 5, "report": report_signature, "sources": source_signature}, separators=(",", ":")
        )
        signature = (report_signature, (hash(source_signature), len(source_signature)))
        repository.set_system_state("library_search_index_signature", signature_text)
    with library_catalog_cache_lock:
        library_catalog_cache["signature"] = signature
    return signature


def _refresh_library_index_background() -> None:
    global library_index_refresh_active
    try:
        _refresh_library_search_index()
        report_path = OUTPUT / "reports" / "processing_report.json"
        report_signature = (
            (report_path.stat().st_mtime_ns, report_path.stat().st_size) if report_path.exists() else (0, 0)
        )
        source_signature = repository.library_index_source_signature()
        signature_text = json.dumps(
            {"version": 5, "report": report_signature, "sources": source_signature},
            separators=(",", ":"),
        )
        repository.set_system_state("library_search_index_signature", signature_text)
        with library_catalog_cache_lock:
            library_catalog_cache["signature"] = (report_signature, (hash(source_signature), len(source_signature)))
    finally:
        with library_index_refresh_lock:
            library_index_refresh_active = False


# Compatibility entry points retained for scripts and tests that used these
# application helpers before Set Builder received its own router module.
def set_builder_export_preflight(request: SetExportPreflightRequest) -> dict:
    return preflight_paths(request)


def set_builder_save_playlist(request: SetPlaylistSaveRequest) -> dict:
    return save_playlist_file(request, _music_library_root(), _safe_folder_name)


@legacy_router.get("/api/library/jobs/{job_id}/details")
def library_job_details(job_id: int) -> dict:
    job = repository.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(404, "Library track not found")
    return {
        "job": job,
        "versions": repository.list_completed_versions(str(job["source_path"])),
    }


def _bind_runtime(runtime: ApplicationRuntime) -> None:
    """Expose one runtime through the legacy module-level compatibility facade."""
    globals().update(runtime_bindings(runtime))
    WEB_DEFAULTS["music_library_path"] = runtime.paths.default_music_library


def _log_intention_provider_status() -> None:
    status = intention_planner.status()
    if status["available"]:
        logger.info(
            "Set Builder AI ready: provider=%s model=%s local_runtime=%s",
            status["provider"],
            status["model"],
            status["local_runtime"],
        )
    else:
        logger.warning("Set Builder AI unavailable: deterministic offline rules will be used")


def create_app(
    runtime: ApplicationRuntime | None = None,
    *,
    paths: ApplicationPaths | None = None,
) -> FastAPI:
    """Compose an isolated FastAPI application from explicit runtime dependencies."""
    if runtime is not None and paths is not None:
        raise ValueError("Pass either runtime or paths, not both")
    runtime = runtime or ApplicationRuntime.create(paths or DEFAULT_PATHS)
    _bind_runtime(runtime)

    global import_service, local_import_service, playlist_match_service, creative_commons_service
    global library_maintenance_service, track_metadata_mutations, metadata_batch_service
    global _run_integrity_scan, intention_planner, journey_planner, set_preference_service
    global set_review_service, candidate_retriever, set_plan_validator, track_planner
    global downloaded_catalog_query_service, job_workflow_service

    import_service = ImportService(
        repository=repository,
        processing_service=service,
        library_root=_music_library_root,
        effective_settings=_effective_settings,
        preset_snapshot=_preset_snapshot,
        duplicate_lookup=_cataloged_download_by_youtube_id,
        probe_audio=_probe_local_audio,
        cache_artwork=_cache_track_artwork,
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )
    local_import_service = LocalAudioImportService(
        repository=repository,
        staging_root=INPUT / "local-imports",
        require_library_online=_require_music_library_online,
        probe_audio=_probe_local_audio,
        generalized_genre=_generalized_genre,
        genre_directory=_genre_directory,
        write_metadata=write_wav_metadata,
        write_source_metadata=_write_source_metadata,
        safe_name=_safe_audio_name,
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )
    playlist_match_service = PlaylistMatchService(
        _match_tracks_to_youtube,
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )
    creative_commons_service = CreativeCommonsImportService(
        creative_commons_registry,
        require_library_online=_require_music_library_online,
        worker=_creative_commons_worker,
        retry_worker=_retry_import_failures_worker,
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )
    library_maintenance_service = LibraryMaintenanceService(
        LibraryMaintenanceDependencies(
            repository=lambda: repository,
            music_library_root=lambda: _music_library_root(),
            require_library_online=lambda: _require_music_library_online(),
            migrate_catalog=lambda **kwargs: _migrate_downloaded_catalog(**kwargs),
            read_wav_metadata=read_wav_metadata,
            sync_wav_metadata=sync_wav_metadata,
            probe_local_audio=lambda path: _probe_local_audio(path),
            catalog_genre_category=lambda path, genre, detailed: _catalog_genre_category(path, genre, detailed),
            metadata_batches=metadata_batch_registry,
            catalog_migration_lock=downloaded_catalog_migration_lock,
            integrity_batches=integrity_scan_batches,
            integrity_lock=integrity_scan_batch_lock,
        )
    )
    track_metadata_mutations = TrackMetadataMutationService(
        TrackMetadataMutationDependencies(
            repository=repository,
            normalize_genre=_normalize_genre_category,
            genre_directory=_genre_directory,
            music_library_root=_music_library_root,
            source_metadata_path=_source_metadata_path,
            write_wav_metadata=write_wav_metadata,
            write_source_metadata=_write_source_metadata,
        )
    )
    metadata_batch_service = MetadataBatchService(
        MetadataBatchDependencies(
            repository=lambda: repository,
            require_library_online=_require_music_library_online,
            sync_wav_metadata=sync_wav_metadata,
            read_wav_artwork=read_wav_artwork,
            embed_wav_artwork=embed_wav_artwork,
            cache_track_artwork=_cache_track_artwork,
            spotify_source_metadata=_spotify_source_metadata,
            generalized_genre=_generalized_genre,
            normalize_genre=_normalize_genre_category,
            genre_directory=_genre_directory,
            change_genre=lambda track_ids, category: change_downloaded_genre(
                DownloadedGenreRequest(track_ids=track_ids, genre_category=category)
            ),
            refresh_wav_tag_audit=_refresh_wav_tag_audit,
            schedule_wav_tag_audit_refresh=_schedule_wav_tag_audit_refresh,
            music_library_root=_music_library_root,
            registry=metadata_batch_registry,
        )
    )
    downloaded_catalog_query_service = DownloadedCatalogQueryService(
        repository=lambda: repository,
        ensure_catalog_migrated=_ensure_downloaded_catalog_migrated,
        normalize_genre_category=_normalize_genre_category,
        track_payload=_downloaded_track_payload,
    )
    job_workflow_service = JobWorkflowService(
        repository=repository,
        processor=service,
        input_root=INPUT,
        supported_extensions=frozenset(SUPPORTED_EXTENSIONS),
        supported_bar_counts=SUPPORTED_BAR_COUNTS,
        available_presets=_available_presets,
        effective_settings=_effective_settings,
        preset_snapshot=_preset_snapshot,
    )
    _run_integrity_scan = library_maintenance_service.run_integrity_scan
    intention_planner = IntentionPlanner.from_environment()
    journey_planner = JourneyPlanner(intention_planner)
    set_preference_service = DJPreferenceService(
        JsonPreferenceStore(SET_BUILDER_CATALOG_CACHE.with_name("set_builder_preferences.json"))
    )
    set_review_service = SetReviewService(
        JsonPreferenceStore(SET_BUILDER_CATALOG_CACHE.with_name("set_builder_reviews.json")),
        set_preference_service.profile,
    )
    candidate_retriever = SetCandidateRetriever(
        preference_ranker=PersonalizedCandidateRanker(set_preference_service.profile)
    )
    set_plan_validator = SetPlanValidator()
    track_planner = AITrackPlanner(SetPlanningModelClient(intention_planner), set_plan_validator)
    runtime.services.update(
        import_service=import_service,
        local_import_service=local_import_service,
        playlist_match_service=playlist_match_service,
        creative_commons_service=creative_commons_service,
        library_maintenance_service=library_maintenance_service,
        track_metadata_mutations=track_metadata_mutations,
        metadata_batch_service=metadata_batch_service,
        downloaded_catalog_query_service=downloaded_catalog_query_service,
        job_workflow_service=job_workflow_service,
        _run_integrity_scan=_run_integrity_scan,
        intention_planner=intention_planner,
        journey_planner=journey_planner,
        set_preference_service=set_preference_service,
        set_review_service=set_review_service,
        candidate_retriever=candidate_retriever,
        set_plan_validator=set_plan_validator,
        track_planner=track_planner,
    )

    application = install_error_handlers(FastAPI(title="DJ Library Studio", docs_url="/api/docs", redoc_url=None))
    application.state.runtime = runtime
    application.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    application.middleware("http")(record_api_performance)
    application.mount(
        "/vendor/wavesurfer",
        StaticFiles(directory=PROJECT / "node_modules" / "wavesurfer.js" / "dist", check_dir=False),
        name="wavesurfer",
    )
    application.mount("/assets", StaticFiles(directory=WEB, check_dir=False), name="assets")
    application.include_router(legacy_router)
    application.include_router(
        create_settings_router(
            SettingsRouteDependencies(
                repository=lambda: repository,
                job_service=service,
                relocation=library_relocation,
                import_services=(
                    import_service,
                    local_import_service,
                    playlist_match_service,
                    creative_commons_service,
                ),
                project=PROJECT,
                input_root=INPUT,
                output_root=OUTPUT,
                database=DATABASE,
                overrides_path=OVERRIDES,
                presets_path=WEB_PRESETS,
                backup_root=BACKUP_ROOT,
                storage_snapshot=STORAGE_INVENTORY_SNAPSHOT,
                cache_folder_name=CACHE_FOLDER_NAME,
                supported_bar_counts=SUPPORTED_BAR_COUNTS,
                defaults=WEB_DEFAULTS,
                available_presets=_available_presets,
                effective_settings=_effective_settings,
                music_library_root=lambda: _music_library_root(),
                library_location_summary=_library_location_summary,
                source_metadata_path=_source_metadata_path,
                refresh_wav_tag_audit=_refresh_wav_tag_audit,
                metadata_batches=metadata_batch_registry,
                library_status_cache=library_status_cache,
                library_status_lock=library_status_cache_lock,
                storage_inventory_cache=storage_inventory_cache,
                storage_inventory_lock=storage_inventory_lock,
                report_cache=report_cache,
                catalog_cache=library_catalog_cache,
                pending_restores=pending_backup_restores,
            )
        )
    )
    application.include_router(
        create_set_builder_router(
            SetBuilderRouteDependencies(
                catalog_cache_path=SET_BUILDER_CATALOG_CACHE,
                ensure_catalog_current=_ensure_library_search_index_current,
                write_catalog_cache=_write_set_builder_catalog_cache,
                music_library_root=lambda: _music_library_root(),
                safe_folder_name=_safe_folder_name,
                intention_planner=intention_planner,
                journey_planner=journey_planner,
            )
        )
    )
    application.include_router(
        create_set_planning_router(
            SetPlanningRouteDependencies(
                catalog_cache_path=SET_BUILDER_CATALOG_CACHE,
                ensure_catalog_current=_ensure_library_search_index_current,
                write_catalog_cache=_write_set_builder_catalog_cache,
                candidate_retriever=candidate_retriever,
                plan_validator=set_plan_validator,
                track_planner=track_planner,
                planning_job_store_path=SET_BUILDER_CATALOG_CACHE.with_name("set_planning_jobs.json"),
            )
        )
    )
    application.include_router(create_set_preference_router(set_preference_service))
    application.include_router(create_set_review_router(set_review_service, set_preference_service))
    application.include_router(
        create_library_router(
            LibraryRouteDependencies(
                repository=lambda: repository,
                ensure_search_index_current=_ensure_library_search_index_current,
                generalized_genre=_generalized_genre,
                catalog_cache=library_catalog_cache,
                catalog_cache_lock=library_catalog_cache_lock,
            )
        )
    )
    application.include_router(
        create_descriptor_router(
            DescriptorRouteDependencies(
                repository=lambda: repository,
                invalidate_set_catalog=lambda: SET_BUILDER_CATALOG_CACHE.unlink(missing_ok=True),
            )
        )
    )
    application.include_router(create_library_maintenance_router(library_maintenance_service))
    application.include_router(create_metadata_batch_router(metadata_batch_service))
    application.include_router(
        create_job_router(JobQueueService(repository=lambda: repository, processor=lambda: service))
    )
    application.include_router(
        create_job_media_router(
            JobMediaRouteDependencies(
                repository=lambda: repository,
                job_service=service,
                record_cache_result=_record_cache_result,
                waveform_locks_guard=waveform_generation_locks_guard,
                waveform_locks=waveform_generation_locks,
            )
        )
    )
    application.include_router(
        create_reporting_router(
            ReportingRouteDependencies(
                repository=lambda: repository,
                output_root=OUTPUT,
                append_feedback=append_web_feedback,
                refresh_library_index=_refresh_library_search_index,
                valid_keys=frozenset(_CAMELOT_KEYS),
            )
        )
    )
    application.include_router(
        create_import_router(
            import_service,
            local_import_service,
            playlist_match_service,
            _playlist_csv_tracks,
            _safe_folder_name,
        )
    )

    def startup() -> None:
        runtime.repository.recover_interrupted()
        _log_intention_provider_status()

    application.router.add_event_handler("startup", startup)
    return application


app: Any = LazyApplication(create_app)


if __name__ == "__main__":
    uvicorn.run("audioextender.web.application:create_app", host="127.0.0.1", port=8765, reload=False, factory=True)
