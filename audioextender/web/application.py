"""Local DJ Library Studio web interface; the AudioExtender CLI remains independent."""

# Runtime compatibility names are installed atomically by ``_bind_runtime``.
# Their explicit declarations below keep that legacy facade visible to static
# analysis without eagerly constructing application services during import.

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
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
from audioextender.core.defaults import (
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
from audioextender.core.presets import PRESETS
from audioextender.imports.creative_commons import CreativeCommonsImportService
from audioextender.imports.creative_commons_worker import CreativeCommonsBatchWorker
from audioextender.imports.local import LocalAudioImportService
from audioextender.imports.playlist_csv import parse_playlist_csv
from audioextender.imports.playlist_match import PlaylistMatchService
from audioextender.imports.service import (
    ImportService,
    authorized_source_provider,
    scdl_download_command,
)
from audioextender.imports.source_matching import SourceMatchError, SourceMatchingService, best_youtube_match
from audioextender.infrastructure.performance_diagnostics import PerformanceDiagnostics
from audioextender.library.analysis_queue import DownloadedTrackAnalysisQueue
from audioextender.library.artwork_thumbnails import ArtworkThumbnailService
from audioextender.library.catalog_migration import DownloadedCatalogMigrator
from audioextender.library.catalog_presenter import downloaded_track_payload
from audioextender.library.catalog_projection import CatalogProjectionPublisher
from audioextender.library.catalog_projection_builder import CatalogProjectionBuilder
from audioextender.library.catalog_query_service import DownloadedCatalogQueryService
from audioextender.library.genre_taxonomy import (
    catalog_genre_category,
    generalized_genre,
    genre_path_parts,
    normalize_genre_category,
    safe_audio_name,
    safe_folder_name,
)
from audioextender.library.job_catalog import LibraryJobCatalogService
from audioextender.library.local_media import LocalMediaService
from audioextender.library.metadata_mutations import (
    TrackMetadataMutationDependencies,
    TrackMetadataMutationService,
)
from audioextender.library.musical_profile import CAMELOT_KEYS
from audioextender.processing.job_workflows import JobWorkflowService
from audioextender.reporting.feedback import append_web_feedback
from audioextender.set_builder.brief_preparation import BriefPreparationService
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
from audioextender.web.assets.frontend import FrontendAssetService
from audioextender.web.assets.static import UncachedStaticFiles
from audioextender.web.composition import (
    ApplicationPaths,
    ApplicationRuntime,
    LazyApplication,
    runtime_bindings,
)
from audioextender.web.contracts.downloaded_library import (
    DownloadedGenreRequest,  # noqa: F401 - compatibility re-export
    DownloadedMetadataRequest,  # noqa: F401 - compatibility re-export
    DownloadedTracksRequest,  # noqa: F401 - compatibility re-export
)
from audioextender.web.contracts.errors import install_error_handlers
from audioextender.web.routes.audio_quality_routes import (
    AudioQualityRouteDependencies,
    AudioQualityScanService,
    create_audio_quality_router,
)
from audioextender.web.routes.creative_commons import (
    CreativeCommonsArchiveDependencies,
    CreativeCommonsArchiveService,
    CreativeCommonsBatchRequest,  # noqa: F401 - compatibility re-export
    CreativeCommonsMatch,
    ImportFailureRetryRequest,  # noqa: F401 - compatibility re-export
    ImportIssueDependencies,
    ImportIssueService,
    create_creative_commons_router,
)
from audioextender.web.routes.descriptor_routes import (
    DescriptorRouteDependencies,
    create_descriptor_router,
)
from audioextender.web.routes.diagnostic_routes import create_diagnostic_router
from audioextender.web.routes.downloaded_analysis_routes import (
    DownloadedAnalysisFilterRequest,  # noqa: F401 - compatibility re-export
    DownloadedAnalysisRouteService,
    create_downloaded_analysis_router,
)
from audioextender.web.routes.downloaded_library_routes import (
    DownloadedLibraryDeliveryService,
    DownloadedLibraryRouteDependencies,
    create_downloaded_library_router,
)
from audioextender.web.routes.downloaded_track_mutation_routes import (
    DownloadedTrackMutationDependencies,
    DownloadedTrackMutationService,
    create_downloaded_track_mutation_router,
)
from audioextender.web.routes.frontend_routes import create_frontend_router
from audioextender.web.routes.imports import (
    AuthorizedImportRequest,  # noqa: F401 - compatibility re-export
    SourceMatchRequest,  # noqa: F401 - compatibility re-export
    create_import_router,
)
from audioextender.web.routes.job_media_routes import (
    BatchDownloadRequest,  # noqa: F401 - compatibility re-export
    JobMediaRouteDependencies,
    create_job_media_router,
)
from audioextender.web.routes.job_review_routes import (
    FeedbackRequest,  # noqa: F401 - compatibility re-export
    JobReviewRouteDependencies,
    JobReviewService,
    ReprocessRequest,  # noqa: F401 - compatibility re-export
    create_job_review_router,
)
from audioextender.web.routes.job_routes import (
    JobQueueService,
    create_job_router,
)
from audioextender.web.routes.library_maintenance_routes import (
    LibraryMaintenanceDependencies,
    LibraryMaintenanceService,
    create_library_maintenance_router,
)
from audioextender.web.routes.library_routes import (
    LibraryRouteDependencies,
    create_library_router,
)
from audioextender.web.routes.metadata_batch_routes import (
    MetadataBatchDependencies,
    MetadataBatchService,
    create_metadata_batch_router,
)
from audioextender.web.routes.preset_routes import (
    PresetRequest,  # noqa: F401 - compatibility re-export
    PresetRouteDependencies,
    PresetService,
    create_preset_router,
)
from audioextender.web.routes.recording_family_routes import (
    DuplicateMergeRequest,  # noqa: F401 - compatibility re-export
    RecordingFamilyRouteDependencies,
    RecordingFamilyService,
    TrackFamilyLinkRequest,  # noqa: F401 - compatibility re-export
    create_recording_family_router,
)
from audioextender.web.routes.reporting_routes import (
    OverrideRequest,  # noqa: F401 - compatibility re-export
    ReportingRouteDependencies,
    ReportingService,
    create_reporting_router,
)
from audioextender.web.routes.set_builder_routes import (
    SetBuilderRouteDependencies,
    SetExportPreflightRequest,  # noqa: F401 - compatibility re-export
    SetPlaylistSaveRequest,  # noqa: F401 - compatibility re-export
    SetPlaylistTrack,  # noqa: F401 - compatibility re-export
    create_set_builder_router,
    preflight_paths,
    save_playlist_file,
)
from audioextender.web.routes.set_planning_routes import SetPlanningRouteDependencies, create_set_planning_router
from audioextender.web.routes.set_preference_routes import create_set_preference_router
from audioextender.web.routes.set_review_routes import create_set_review_router
from audioextender.web.routes.settings_routes import (
    SettingsRouteDependencies,
    create_settings_router,
)

DEFAULT_PATHS = ApplicationPaths.from_project(Path(__file__).resolve().parents[2])
PROJECT = DEFAULT_PATHS.project
INPUT = DEFAULT_PATHS.input
OUTPUT = DEFAULT_PATHS.output
FRONTEND = DEFAULT_PATHS.frontend
DATABASE = DEFAULT_PATHS.database
OVERRIDES = DEFAULT_PATHS.overrides
WEB_PRESETS = DEFAULT_PATHS.presets
SET_BUILDER_CATALOG_CACHE = DEFAULT_PATHS.set_builder_catalog_cache
DEFAULT_MUSIC_LIBRARY = DEFAULT_PATHS.default_music_library
BACKUP_ROOT = DEFAULT_PATHS.backup_root
STORAGE_INVENTORY_SNAPSHOT = DEFAULT_PATHS.storage_inventory_snapshot

logger = logging.getLogger("uvicorn.error")
wav_tag_audit_refresh_active = False
library_index_refresh_active = False

# ``_bind_runtime`` and the construction helpers replace these sentinels before
# the application handles a request. Real assignments (rather than annotation-
# only declarations) are intentional: Pyflakes-based tools require a lexical
# binding, while eager construction here would open the database during import.
_UNBOUND: Any = object()

# State installed by ``composition.runtime_bindings``.
repository: Any = _UNBOUND
service: Any = _UNBOUND
library_relocation: Any = _UNBOUND
pending_backup_restores: Any = _UNBOUND
creative_commons_registry: Any = _UNBOUND
creative_commons_batches: Any = _UNBOUND
creative_commons_batch_lock: Any = _UNBOUND
wav_tag_audit_refresh_lock: Any = _UNBOUND
metadata_batch_registry: Any = _UNBOUND
integrity_scan_batches: Any = _UNBOUND
integrity_scan_batch_lock: Any = _UNBOUND
audio_quality_batches: Any = _UNBOUND
audio_quality_batch_lock: Any = _UNBOUND
key_analysis_batches: Any = _UNBOUND
key_analysis_batch_lock: Any = _UNBOUND
library_consolidation_batches: Any = _UNBOUND
library_consolidation_batch_lock: Any = _UNBOUND
downloaded_catalog_migration_lock: Any = _UNBOUND
report_cache_lock: Any = _UNBOUND
report_cache: Any = _UNBOUND
analytics_cache_lock: Any = _UNBOUND
analytics_cache: Any = _UNBOUND
library_catalog_cache_lock: Any = _UNBOUND
library_catalog_cache: Any = _UNBOUND
library_status_cache_lock: Any = _UNBOUND
library_status_cache: Any = _UNBOUND
storage_inventory_lock: Any = _UNBOUND
storage_inventory_cache: Any = _UNBOUND
library_index_refresh_lock: Any = _UNBOUND
performance_diagnostics_lock: Any = _UNBOUND
waveform_generation_locks_guard: Any = _UNBOUND
waveform_generation_locks: Any = _UNBOUND
performance_diagnostics: Any = _UNBOUND
performance_cache_stats: Any = _UNBOUND

# Services installed by the focused construction helpers in ``create_app``.
performance_diagnostics_service: Any = _UNBOUND
source_matching_service: Any = _UNBOUND
local_media_service: Any = _UNBOUND
downloaded_catalog_migrator: Any = _UNBOUND
intention_planner: Any = _UNBOUND
journey_planner: Any = _UNBOUND
brief_preparation: Any = _UNBOUND
set_preference_service: Any = _UNBOUND
set_review_service: Any = _UNBOUND
candidate_retriever: Any = _UNBOUND
set_plan_validator: Any = _UNBOUND
track_planner: Any = _UNBOUND
preset_service: Any = _UNBOUND
downloaded_library_delivery_service: Any = _UNBOUND
recording_family_service: Any = _UNBOUND
downloaded_track_mutation_service: Any = _UNBOUND
audio_quality_scan_service: Any = _UNBOUND
creative_commons_service: Any = _UNBOUND
creative_commons_archive_service: Any = _UNBOUND
import_issue_service: Any = _UNBOUND
import_service: Any = _UNBOUND
local_import_service: Any = _UNBOUND
playlist_match_service: Any = _UNBOUND
library_job_catalog_service: Any = _UNBOUND
library_maintenance_service: Any = _UNBOUND
metadata_batch_service: Any = _UNBOUND
job_workflow_service: Any = _UNBOUND
job_review_service: Any = _UNBOUND
track_metadata_mutations: Any = _UNBOUND
downloaded_catalog_query_service: Any = _UNBOUND
artwork_thumbnail_service: Any = _UNBOUND
downloaded_analysis_queue: Any = _UNBOUND
reporting_service: Any = _UNBOUND
creative_commons_worker: Any = _UNBOUND
_run_integrity_scan: Any = _UNBOUND


def _record_cache_result(cache_name: str, hit: bool) -> None:
    """Compatibility callback used by cache-aware services."""
    performance_diagnostics_service.record_cache_result(cache_name, hit)


async def record_api_performance(request, call_next):
    """Compatibility middleware entry point for historical callers."""
    return await performance_diagnostics_service.middleware(request, call_next)


def performance_diagnostics_report() -> dict:
    """Compatibility report entry point for historical callers."""
    return performance_diagnostics_service.report()


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


def _match_tracks_to_youtube(tracks: list[dict], progress) -> list[dict]:
    """Compatibility wrapper for playlist matching callers."""
    return source_matching_service.match_tracks(tracks, progress)


_best_youtube_match = best_youtube_match
_generalized_genre = generalized_genre
_normalize_genre_category = normalize_genre_category
_genre_path_parts = genre_path_parts
_safe_audio_name = safe_audio_name
_safe_folder_name = safe_folder_name


def _spotify_source_metadata(url: str) -> dict:
    """Compatibility wrapper preserving the historical HTTP error contract."""
    try:
        return source_matching_service.spotify_metadata(url)
    except SourceMatchError as error:
        raise HTTPException(error.status_code, error.detail) from error


def _soundcloud_source_metadata(url: str) -> dict:
    """Compatibility wrapper preserving the historical HTTP error contract."""
    try:
        return source_matching_service.soundcloud_metadata(url)
    except SourceMatchError as error:
        raise HTTPException(error.status_code, error.detail) from error


def _authorized_source_provider(url: str) -> str | None:
    """Compatibility wrapper for callers that import this legacy helper."""
    return authorized_source_provider(url)


def _playlist_csv_tracks(contents: bytes) -> list[dict]:
    """Compatibility wrapper around the import-owned CSV parser."""
    return parse_playlist_csv(contents, generalized_genre)


def _genre_directory(category: str) -> Path:
    return _music_library_root().joinpath(*genre_path_parts(category))


def _catalog_genre_category(wav_path: Path, stored_category: str, detailed_genre: str) -> str:
    return catalog_genre_category(
        wav_path,
        stored_category,
        detailed_genre,
        library_root=_music_library_root(),
    )


def _source_metadata_path(audio_path: Path) -> Path:
    return local_media_service.source_metadata_path(audio_path)


def _write_source_metadata(audio_path: Path, metadata: dict) -> Path:
    return local_media_service.write_source_metadata(audio_path, metadata)


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


def _migrate_downloaded_catalog(*, incremental: bool = False, progress=None) -> dict[str, int]:
    return downloaded_catalog_migrator.migrate(incremental=incremental, progress=progress)


def _ensure_downloaded_catalog_migrated() -> None:
    downloaded_catalog_migrator.ensure_current()


def _cache_track_artwork(artwork_url: str, destination: Path) -> str:
    return local_media_service.cache_artwork(artwork_url, destination)


def _probe_local_audio(path: Path) -> dict:
    return LocalMediaService.probe(path)


def _scdl_download_command(url: str, destination: Path) -> list[str]:
    """Compatibility wrapper for callers that import this legacy helper."""
    return scdl_download_command(url, destination)


def _downloaded_track_payload(track: dict) -> dict:
    return downloaded_track_payload(
        track,
        generalized_genre=generalized_genre,
        normalize_genre_category=normalize_genre_category,
    )


def _queue_downloaded_analysis(tracks: list[dict], *, force: bool = False) -> dict:
    """Compatibility wrapper around the catalog analysis queue service."""
    return DownloadedTrackAnalysisQueue(
        repository=repository,
        processor=service,
        effective_settings=_effective_settings,
    ).queue(tracks, force=force)


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


def _reporting_dependencies() -> ReportingRouteDependencies:
    return ReportingRouteDependencies(
        repository=lambda: repository,
        output_root=OUTPUT,
        append_feedback=append_web_feedback,
        refresh_library_index=catalog_projection_publisher.publish,
        valid_keys=frozenset(_CAMELOT_KEYS),
        overrides_path=OVERRIDES,
        analytics_cache=analytics_cache,
        analytics_cache_lock=analytics_cache_lock,
        report_cache=report_cache,
        report_cache_lock=report_cache_lock,
    )


def _load_processing_report() -> dict:
    """Compatibility export for catalog projection and historical callers."""
    return ReportingService(_reporting_dependencies()).load_report()


def _build_set_builder_services() -> dict[str, Any]:
    """Construct the Set Builder service family and publish compatibility names."""
    global intention_planner, journey_planner, brief_preparation, set_preference_service, set_review_service
    global candidate_retriever, set_plan_validator, track_planner

    intention_planner = IntentionPlanner.from_environment()
    journey_planner = JourneyPlanner(intention_planner)
    brief_preparation = BriefPreparationService(intention_planner)
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
    return {
        "intention_planner": intention_planner,
        "journey_planner": journey_planner,
        "brief_preparation": brief_preparation,
        "set_preference_service": set_preference_service,
        "set_review_service": set_review_service,
        "candidate_retriever": candidate_retriever,
        "set_plan_validator": set_plan_validator,
        "track_planner": track_planner,
    }


def _register_routers(application: FastAPI) -> None:
    """Register feature routers after every dependency family is composed."""
    routers = [
        create_frontend_router(),
        create_diagnostic_router(performance_diagnostics_service),
        create_preset_router(preset_service),
        create_downloaded_library_router(downloaded_library_delivery_service),
        create_downloaded_analysis_router(
            DownloadedAnalysisRouteService(
                repository=lambda: repository,
                queue=lambda: DownloadedTrackAnalysisQueue(
                    repository=repository, processor=service, effective_settings=_effective_settings
                ),
            )
        ),
        create_recording_family_router(recording_family_service),
        create_downloaded_track_mutation_router(downloaded_track_mutation_service),
        create_audio_quality_router(audio_quality_scan_service),
        create_creative_commons_router(
            creative_commons_service, creative_commons_archive_service, import_issue_service
        ),
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
        ),
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
                brief_preparation=brief_preparation,
            )
        ),
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
        ),
        create_set_preference_router(set_preference_service),
        create_set_review_router(set_review_service, set_preference_service),
        create_library_router(
            LibraryRouteDependencies(
                repository=lambda: repository,
                ensure_search_index_current=_ensure_library_search_index_current,
                generalized_genre=_generalized_genre,
                catalog_cache=library_catalog_cache,
                catalog_cache_lock=library_catalog_cache_lock,
                job_catalog=library_job_catalog_service,
            )
        ),
        create_descriptor_router(
            DescriptorRouteDependencies(
                repository=lambda: repository,
                invalidate_set_catalog=catalog_projection_publisher.publish,
            )
        ),
        create_library_maintenance_router(library_maintenance_service),
        create_metadata_batch_router(metadata_batch_service),
        create_job_router(
            JobQueueService(repository=lambda: repository, processor=lambda: service),
            job_workflow_service,
        ),
        create_job_review_router(job_review_service),
        create_job_media_router(
            JobMediaRouteDependencies(
                repository=lambda: repository,
                job_service=service,
                record_cache_result=_record_cache_result,
                waveform_locks_guard=waveform_generation_locks_guard,
                waveform_locks=waveform_generation_locks,
            )
        ),
        create_reporting_router(_reporting_dependencies()),
        create_import_router(
            import_service,
            local_import_service,
            playlist_match_service,
            _playlist_csv_tracks,
            _safe_folder_name,
            source_matching_service,
        ),
    ]

    for router in routers:
        application.include_router(router)


def _build_library_services() -> dict[str, Any]:
    """Construct catalog, mutation, analysis, job-review, and reporting services."""
    global library_maintenance_service, track_metadata_mutations, metadata_batch_service
    global downloaded_track_mutation_service, recording_family_service
    global downloaded_catalog_query_service, downloaded_library_delivery_service, downloaded_analysis_queue
    global job_workflow_service, job_review_service, reporting_service, library_job_catalog_service, _run_integrity_scan

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
            cache_track_artwork=_cache_track_artwork,
            safe_audio_name=_safe_audio_name,
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
    downloaded_track_mutation_service = DownloadedTrackMutationService(
        DownloadedTrackMutationDependencies(
            repository=lambda: repository,
            metadata=track_metadata_mutations,
            metadata_batches=metadata_batch_service,
            genre_directory=_genre_directory,
            original_import_metadata=import_issue_service.original_metadata,
            database_path=lambda: Path(str(getattr(repository, "path", DATABASE))),
        )
    )
    recording_family_service = RecordingFamilyService(
        RecordingFamilyRouteDependencies(
            repository=lambda: repository,
            track_payload=_downloaded_track_payload,
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
    library_job_catalog_service = LibraryJobCatalogService(
        repository=lambda: repository,
        processing_report=OUTPUT / "reports" / "processing_report.json",
    )
    job_review_service = JobReviewService(
        JobReviewRouteDependencies(
            repository=lambda: repository,
            workflow=job_workflow_service,
            output_root=OUTPUT,
            append_feedback=append_web_feedback,
        )
    )
    reporting_service = ReportingService(_reporting_dependencies())
    _run_integrity_scan = library_maintenance_service.run_integrity_scan
    return {
        "library_maintenance_service": library_maintenance_service,
        "track_metadata_mutations": track_metadata_mutations,
        "metadata_batch_service": metadata_batch_service,
        "downloaded_track_mutation_service": downloaded_track_mutation_service,
        "recording_family_service": recording_family_service,
        "downloaded_catalog_query_service": downloaded_catalog_query_service,
        "downloaded_library_delivery_service": downloaded_library_delivery_service,
        "downloaded_analysis_queue": downloaded_analysis_queue,
        "job_workflow_service": job_workflow_service,
        "library_job_catalog_service": library_job_catalog_service,
        "job_review_service": job_review_service,
        "reporting_service": reporting_service,
        "_run_integrity_scan": _run_integrity_scan,
    }


def _build_import_services() -> None:
    """Construct import workflows after shared preset and catalog services."""
    global import_service, local_import_service, playlist_match_service, creative_commons_service
    global creative_commons_archive_service, creative_commons_worker, import_issue_service, source_matching_service

    source_matching_service = SourceMatchingService()

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
        source_matching_service.match_tracks,
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
        best_youtube_match=best_youtube_match,
        spotify_source_metadata=source_matching_service.spotify_metadata,
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
    global creative_commons_archive_service, creative_commons_worker, import_issue_service, source_matching_service
    global audio_quality_scan_service, artwork_thumbnail_service, library_maintenance_service
    global local_media_service, downloaded_catalog_migrator, library_job_catalog_service
    global track_metadata_mutations, metadata_batch_service, downloaded_track_mutation_service
    global recording_family_service
    global _run_integrity_scan, intention_planner, journey_planner, brief_preparation, set_preference_service
    global set_review_service, candidate_retriever, set_plan_validator, track_planner
    global downloaded_analysis_queue, downloaded_catalog_query_service, downloaded_library_delivery_service
    global preset_service, job_workflow_service, job_review_service, reporting_service
    global catalog_projection_builder, catalog_projection_publisher
    global performance_diagnostics_service

    performance_diagnostics_service = PerformanceDiagnostics(
        samples=performance_diagnostics,
        cache_stats=performance_cache_stats,
        lock=performance_diagnostics_lock,
    )

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
    local_media_service = LocalMediaService(
        music_library_root=_music_library_root,
        require_library_online=_require_music_library_online,
        embed_artwork=embed_wav_artwork,
    )
    downloaded_catalog_migrator = DownloadedCatalogMigrator(
        repository=lambda: repository,
        output_root=OUTPUT,
        music_library_root=_music_library_root,
        catalog_genre_category=_catalog_genre_category,
        write_source_metadata=local_media_service.write_source_metadata,
        lock=downloaded_catalog_migration_lock,
    )

    _build_import_services()
    library_services = _build_library_services()
    set_builder_services = _build_set_builder_services()
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
        local_media_service=local_media_service,
        downloaded_catalog_migrator=downloaded_catalog_migrator,
        source_matching_service=source_matching_service,
        preset_service=preset_service,
        catalog_projection_builder=catalog_projection_builder,
        performance_diagnostics_service=performance_diagnostics_service,
        **library_services,
        **set_builder_services,
    )

    application = install_error_handlers(FastAPI(title="DJ Library Studio", docs_url="/api/docs", redoc_url=None))
    application.state.runtime = runtime
    application.state.frontend_assets = FrontendAssetService(runtime.paths.frontend)
    application.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    application.middleware("http")(performance_diagnostics_service.middleware)
    application.mount(
        "/vendor/wavesurfer",
        StaticFiles(directory=PROJECT / "node_modules" / "wavesurfer.js" / "dist", check_dir=False),
        name="wavesurfer",
    )
    application.mount(
        "/assets",
        UncachedStaticFiles(directory=runtime.paths.frontend, check_dir=False),
        name="assets",
    )
    _register_routers(application)

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
