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
import threading
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
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
from audioextender.core.presets import PRESETS
from audioextender.imports.creative_commons import CreativeCommonsImportService
from audioextender.imports.creative_commons_routes import (
    CreativeCommonsArchiveDependencies,
    CreativeCommonsArchiveService,
    CreativeCommonsBatchRequest,  # noqa: F401 - compatibility re-export
    CreativeCommonsMatch,
    ImportFailureRetryRequest,  # noqa: F401 - compatibility re-export
    ImportIssueDependencies,
    ImportIssueService,
    create_creative_commons_router,
)
from audioextender.imports.creative_commons_worker import CreativeCommonsBatchWorker
from audioextender.imports.local import LocalAudioImportService
from audioextender.imports.playlist_match import PlaylistMatchService
from audioextender.imports.routes import AuthorizedImportRequest, create_import_router  # noqa: F401
from audioextender.imports.service import (
    ImportService,
    authorized_source_provider,
    scdl_download_command,
)
from audioextender.library.analysis_queue import DownloadedTrackAnalysisQueue
from audioextender.library.artwork_thumbnails import ArtworkThumbnailService
from audioextender.library.catalog_projection import CatalogProjectionPublisher
from audioextender.library.catalog_projection_builder import CatalogProjectionBuilder
from audioextender.library.catalog_query_service import DownloadedCatalogQueryService
from audioextender.library.metadata_mutations import (
    TrackMetadataMutationDependencies,
    TrackMetadataMutationService,
)
from audioextender.library.musical_profile import CAMELOT_KEYS
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
from audioextender.set_builder.saved_sets import SavedSetService
from audioextender.set_builder.track_planner import AITrackPlanner, SetPlanningModelClient
from audioextender.web.audio_quality_routes import (
    AudioQualityRouteDependencies,
    AudioQualityScanService,
    create_audio_quality_router,
)
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
from audioextender.web.downloaded_library_routes import (
    DownloadedLibraryDeliveryService,
    DownloadedLibraryRouteDependencies,
    DownloadedTracksRequest,  # noqa: F401 - compatibility re-export
    create_downloaded_library_router,
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
from audioextender.web.preset_routes import (
    PresetRequest,  # noqa: F401 - compatibility re-export
    PresetRouteDependencies,
    PresetService,
    create_preset_router,
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
library_index_refresh_active = False


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
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
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
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
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


class FeedbackRequest(BaseModel):
    position: str
    candidate_rank: int | None = None
    accepted: bool
    tags: str = ""
    notes: str = ""


class SourceMatchRequest(BaseModel):
    url: str = Field(min_length=10, max_length=500)


class DownloadedTracksRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=1000)


class DuplicateMergeRequest(BaseModel):
    survivor_id: int = Field(gt=0)
    duplicate_id: int = Field(gt=0)


class TrackFamilyLinkRequest(BaseModel):
    target_track_id: int | None = Field(default=None, gt=0)
    target_identity: str = Field(default="", max_length=40)
    relationship: Literal["ORG", "RMX", "EXT", "RADIO", "LIVE", "INST", "ACAP", "REM"]


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
    """Compatibility wrapper around the catalog analysis queue service."""
    return DownloadedTrackAnalysisQueue(
        repository=repository,
        processor=service,
        effective_settings=_effective_settings,
    ).queue(tracks, force=force)


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
    catalog_projection_publisher.publish()
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
        json.dumps({**payload, "generated_at": datetime.now(UTC).isoformat()}),
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


_CAMELOT_KEYS = CAMELOT_KEYS


def _ensure_library_search_index_current() -> tuple[tuple[int, int], ...]:
    """Refresh the compact Library index only when its inputs have changed."""
    _ensure_downloaded_catalog_migrated()
    signature, signature_text = catalog_projection_publisher.signature()
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
        signature = catalog_projection_publisher.publish()
    with library_catalog_cache_lock:
        library_catalog_cache["signature"] = signature
    return signature


def _refresh_library_index_background() -> None:
    global library_index_refresh_active
    try:
        catalog_projection_publisher.publish()
    finally:
        with library_index_refresh_lock:
            library_index_refresh_active = False


catalog_projection_builder: CatalogProjectionBuilder
catalog_projection_publisher: CatalogProjectionPublisher


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
    global creative_commons_archive_service, creative_commons_worker, import_issue_service
    global audio_quality_scan_service, artwork_thumbnail_service, library_maintenance_service
    global track_metadata_mutations, metadata_batch_service
    global _run_integrity_scan, intention_planner, journey_planner, set_preference_service
    global set_review_service, candidate_retriever, set_plan_validator, track_planner
    global downloaded_analysis_queue, downloaded_catalog_query_service, downloaded_library_delivery_service
    global preset_service, job_workflow_service
    global catalog_projection_builder, catalog_projection_publisher

    catalog_projection_builder = _current_catalog_projection_builder()
    catalog_projection_publisher = CatalogProjectionPublisher(
        repository=lambda: repository,
        rebuild=catalog_projection_builder.rebuild,
        report_path=lambda: OUTPUT / "reports" / "processing_report.json",
        catalog_path=lambda: SET_BUILDER_CATALOG_CACHE,
        memory_cache=library_catalog_cache,
        memory_cache_lock=library_catalog_cache_lock,
    )
    artwork_thumbnail_service = ArtworkThumbnailService(
        thumbnail_root=lambda: _music_library_root() / ".artwork" / "thumbnails",
        record_cache_result=_record_cache_result,
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )
    preset_service = PresetService(
        PresetRouteDependencies(
            state_path=lambda: WEB_PRESETS,
            built_in_presets=PRESETS,
            supported_bar_counts=frozenset(SUPPORTED_BAR_COUNTS),
        )
    )
    audio_quality_scan_service = AudioQualityScanService(
        AudioQualityRouteDependencies(
            repository=lambda: repository,
            analyze=analyze_audio_quality,
            batches=audio_quality_batches,
            batch_lock=audio_quality_batch_lock,
            library_status_cache=library_status_cache,
            library_status_lock=library_status_cache_lock,
            thread_factory=lambda **kwargs: threading.Thread(**kwargs),
        )
    )

    import_service = ImportService(
        repository=repository,
        processing_service=service,
        library_root=_music_library_root,
        effective_settings=_effective_settings,
        preset_snapshot=preset_service.snapshot,
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
    import_issue_service = ImportIssueService(
        ImportIssueDependencies(
            repository=lambda: repository,
            lifecycle=lambda: creative_commons_service,
            report_root=OUTPUT / "reports" / "imports",
            safe_folder_name=_safe_folder_name,
            generalized_genre=_generalized_genre,
            normalize_genre=_normalize_genre_category,
        )
    )
    creative_commons_worker = CreativeCommonsBatchWorker(
        registry=creative_commons_registry,
        repository=repository,
        output=OUTPUT,
        require_library_online=_require_music_library_online,
        safe_folder_name=_safe_folder_name,
        generalized_genre=_generalized_genre,
        normalize_genre_category=_normalize_genre_category,
        safe_audio_name=_safe_audio_name,
        duplicate_lookup=_cataloged_download_by_youtube_id,
        genre_path_parts=_genre_path_parts,
        source_metadata_path=_source_metadata_path,
        cache_track_artwork=_cache_track_artwork,
        write_wav_metadata=write_wav_metadata,
        write_source_metadata=_write_source_metadata,
        best_youtube_match=_best_youtube_match,
        spotify_source_metadata=_spotify_source_metadata,
        original_import_metadata=import_issue_service.original_metadata,
        match_factory=CreativeCommonsMatch,
    )
    creative_commons_service = CreativeCommonsImportService(
        creative_commons_registry,
        require_library_online=_require_music_library_online,
        worker=creative_commons_worker.run,
        retry_worker=creative_commons_worker.retry,
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )
    creative_commons_archive_service = CreativeCommonsArchiveService(
        CreativeCommonsArchiveDependencies(
            lifecycle=creative_commons_service,
            music_library_root=lambda: _music_library_root(),
            safe_folder_name=_safe_folder_name,
            genre_path_parts=_genre_path_parts,
            cataloged_download=lambda video_id: _cataloged_download_by_youtube_id(video_id),
        )
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
            publish_catalog=catalog_projection_publisher.publish,
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
            change_genre=lambda track_ids, category: track_metadata_mutations.change_genre(
                track_ids, category, publish=False
            ),
            publish_catalog=catalog_projection_publisher.publish,
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
    downloaded_library_delivery_service = DownloadedLibraryDeliveryService(
        DownloadedLibraryRouteDependencies(
            repository=lambda: repository,
            catalog_query=downloaded_catalog_query_service,
            artwork_thumbnails=artwork_thumbnail_service,
            safe_folder_name=_safe_folder_name,
            genre_path_parts=_genre_path_parts,
        )
    )
    downloaded_analysis_queue = DownloadedTrackAnalysisQueue(
        repository=repository,
        processor=service,
        effective_settings=_effective_settings,
    )
    job_workflow_service = JobWorkflowService(
        repository=repository,
        processor=service,
        input_root=INPUT,
        supported_extensions=frozenset(SUPPORTED_EXTENSIONS),
        supported_bar_counts=SUPPORTED_BAR_COUNTS,
        available_presets=preset_service.available,
        effective_settings=_effective_settings,
        preset_snapshot=preset_service.snapshot,
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
        creative_commons_archive_service=creative_commons_archive_service,
        creative_commons_worker=creative_commons_worker,
        import_issue_service=import_issue_service,
        audio_quality_scan_service=audio_quality_scan_service,
        artwork_thumbnail_service=artwork_thumbnail_service,
        preset_service=preset_service,
        library_maintenance_service=library_maintenance_service,
        track_metadata_mutations=track_metadata_mutations,
        metadata_batch_service=metadata_batch_service,
        downloaded_catalog_query_service=downloaded_catalog_query_service,
        downloaded_library_delivery_service=downloaded_library_delivery_service,
        downloaded_analysis_queue=downloaded_analysis_queue,
        catalog_projection_builder=catalog_projection_builder,
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
    application.include_router(create_preset_router(preset_service))
    application.include_router(create_downloaded_library_router(downloaded_library_delivery_service))
    application.include_router(create_audio_quality_router(audio_quality_scan_service))
    application.include_router(
        create_creative_commons_router(
            creative_commons_service,
            creative_commons_archive_service,
            import_issue_service,
        )
    )
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
                available_presets=preset_service.available,
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
                saved_sets=SavedSetService(repository),
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
                invalidate_set_catalog=catalog_projection_publisher.publish,
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
                refresh_library_index=catalog_projection_publisher.publish,
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


def _write_set_builder_catalog_cache() -> None:
    """Compatibility wrapper for callers that publish the Set Builder cache."""
    _current_catalog_projection_builder().write_catalog_cache()


def _refresh_library_search_index() -> None:
    """Compatibility wrapper for scripts and propagation integration tests."""
    _current_catalog_projection_builder().rebuild()


def _current_catalog_projection_builder() -> CatalogProjectionBuilder:
    """Build against current compatibility bindings for isolated scripts/tests."""
    return CatalogProjectionBuilder(
        repository=lambda: repository,
        load_processing_report=_load_processing_report,
        normalize_genre_category=_normalize_genre_category,
        catalog_path=lambda: SET_BUILDER_CATALOG_CACHE,
        camelot_keys=CAMELOT_KEYS,
    )
