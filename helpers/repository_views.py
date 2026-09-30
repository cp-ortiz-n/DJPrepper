"""Focused database capabilities over the shared application store."""

from __future__ import annotations

from typing import Any, ClassVar


class _RepositoryView:
    """Restrict a shared store to one domain-specific public interface."""

    methods: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, store: Any) -> None:
        self._store = store

    @property
    def path(self):
        return self._store.path

    def __getattr__(self, name: str):
        if name not in self.methods:
            raise AttributeError(
                f"{type(self).__name__} does not expose repository operation {name!r}"
            )
        return getattr(self._store, name)

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(self.methods))


class TrackCatalogRepository(_RepositoryView):
    methods = frozenset({
        "library_index_source_signature", "catalog_source_signatures",
        "upsert_catalog_source_signatures", "library_index_count",
        "replace_library_search_index", "page_library_tracks",
        "library_search_facets", "get_library_analysis",
        "list_set_builder_tracks", "upsert_downloaded_track",
        "list_downloaded_tracks", "list_downloaded_tracks_with_jobs",
        "page_downloaded_tracks", "update_audio_quality",
        "audio_quality_summary", "downloaded_catalog_facets",
        "get_downloaded_track", "get_downloaded_track_by_path",
        "update_downloaded_track_artwork", "update_downloaded_track_key_analysis",
        "update_downloaded_track_metadata", "delete_downloaded_track",
        "downloaded_track_is_excluded", "reset_track_data",
    })


class JobsAndQueuesRepository(_RepositoryView):
    methods = frozenset({
        "create", "update", "get", "list_jobs", "analytics_summary",
        "list_job_summaries", "list_jobs_page", "list_latest_completed_jobs",
        "list_report_audio_jobs", "list_completed_versions", "delete",
        "recover_interrupted", "fail_stalled_jobs", "record_import_failure",
        "resolve_import_failure", "list_import_failures",
        "get_downloaded_track_by_path",
    })


class SettingsSystemRepository(_RepositoryView):
    methods = frozenset({
        "get_system_state", "set_system_state", "get_settings", "replace_settings",
    })


class RecordingFamilyRepository(_RepositoryView):
    methods = frozenset({
        "duplicate_candidates", "refresh_missing_audio_fingerprints",
        "separate_recording", "recording_family", "track_id_for_identity",
        "link_recording_version", "recording_family_suggestions",
        "merge_downloaded_tracks",
    })


class FeedbackKeyVerificationRepository(_RepositoryView):
    methods = frozenset({
        "add_feedback", "feedback", "add_track_feedback", "track_feedback",
        "set_key_verification", "key_verification", "key_verifications",
        "delete_key_verification",
    })


class BackupsRelocationRepository(_RepositoryView):
    methods = frozenset({
        "list_storage_job_references", "list_downloaded_tracks",
        "relocate_library_paths", "relocate_downloaded_tracks",
    })


class RepositoryBundle:
    """Named domain entry points sharing one SQLite owner and lock."""

    def __init__(self, store: Any) -> None:
        self.track_catalog = TrackCatalogRepository(store)
        self.jobs_and_queues = JobsAndQueuesRepository(store)
        self.settings_system = SettingsSystemRepository(store)
        self.recording_families = RecordingFamilyRepository(store)
        self.feedback_key_verification = FeedbackKeyVerificationRepository(store)
        self.backups_relocation = BackupsRelocationRepository(store)
