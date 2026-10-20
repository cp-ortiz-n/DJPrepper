"""Ordered, idempotent SQLite schema initialization for the repository facade."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from audioextender.persistence.migrations.musical_verification import initialize_musical_verifications

SchemaAction = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class SchemaStep:
    name: str
    apply: SchemaAction


class RepositorySchemaInitializer:
    """Run explicit schema capabilities in dependency order in one transaction."""

    def __init__(self, identity_migration: SchemaAction) -> None:
        self.steps: Sequence[SchemaStep] = (
            SchemaStep("jobs", _initialize_jobs),
            SchemaStep("settings-and-feedback", _initialize_settings_and_feedback),
            SchemaStep("catalog-core", _initialize_catalog_core),
            SchemaStep("recording-identities", identity_migration),
            SchemaStep("catalog-relations", _initialize_catalog_relations),
            SchemaStep("library-search", _initialize_library_search),
            SchemaStep("system-state", _initialize_system_state),
        )

    def initialize(self, connection: sqlite3.Connection) -> None:
        with connection:
            for step in self.steps:
                step.apply(connection)
            connection.execute("PRAGMA optimize")


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_columns(connection: sqlite3.Connection, table: str, additions: dict[str, str]) -> set[str]:
    existing = _columns(connection, table)
    for column, definition in additions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    return existing


def _initialize_jobs(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY, source_name TEXT NOT NULL, source_path TEXT NOT NULL,
        status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
        stage TEXT NOT NULL DEFAULT 'Queued', preset TEXT NOT NULL DEFAULT 'auto',
        intro_bars INTEGER NOT NULL, outro_bars INTEGER NOT NULL,
        use_stems INTEGER NOT NULL DEFAULT 0, config_json TEXT NOT NULL DEFAULT '{}',
        error TEXT, extended_path TEXT, wav_path TEXT, intro_preview_path TEXT,
        outro_preview_path TEXT, cue_sheet_path TEXT, rekordbox_path TEXT,
        candidates_json TEXT NOT NULL DEFAULT '{}', cues_json TEXT NOT NULL DEFAULT '[]',
        parent_job_id INTEGER, bpm REAL, intro_quality REAL, outro_quality REAL,
        review_status TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source_id ON jobs(source_path, id DESC)")
    _add_columns(
        connection,
        "jobs",
        {
            "intro_preview_path": "TEXT",
            "outro_preview_path": "TEXT",
            "config_json": "TEXT NOT NULL DEFAULT '{}'",
            "cue_sheet_path": "TEXT",
            "rekordbox_path": "TEXT",
            "candidates_json": "TEXT NOT NULL DEFAULT '{}'",
            "cues_json": "TEXT NOT NULL DEFAULT '[]'",
            "parent_job_id": "INTEGER",
            "review_status": "TEXT",
        },
    )
    rows = connection.execute("SELECT id, parent_job_id, config_json, review_status FROM jobs").fetchall()
    for row in rows:
        try:
            config = json.loads(row["config_json"] or "{}")
        except (TypeError, ValueError):
            config = {}
        if row["review_status"] is None and config.get("review_candidates"):
            state = "resolved" if config.get("manual_candidate_selection") else "pending"
            connection.execute("UPDATE jobs SET review_status=? WHERE id=?", (state, row["id"]))
        if row["parent_job_id"] and config.get("manual_candidate_selection"):
            connection.execute("UPDATE jobs SET review_status='resolved' WHERE id=?", (row["parent_job_id"],))


def _initialize_settings_and_feedback(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS web_settings (
        key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidate_feedback (
        id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, position TEXT NOT NULL,
        candidate_rank INTEGER, accepted INTEGER NOT NULL, tags TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES jobs(id));
        CREATE TABLE IF NOT EXISTS track_feedback (
        id INTEGER PRIMARY KEY, source_name TEXT NOT NULL, position TEXT NOT NULL,
        accepted INTEGER NOT NULL, tags TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_track_feedback_source
        ON track_feedback(source_name COLLATE NOCASE, created_at DESC);"""
    )
    initialize_musical_verifications(connection)


def _initialize_catalog_core(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS downloaded_tracks (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL DEFAULT '',
        file_path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL, genre TEXT NOT NULL DEFAULT '',
        genre_category TEXT NOT NULL DEFAULT 'Other', spotify_uri TEXT NOT NULL DEFAULT '',
        youtube_id TEXT NOT NULL DEFAULT '', youtube_url TEXT NOT NULL DEFAULT '',
        artwork_url TEXT NOT NULL DEFAULT '', artwork_path TEXT NOT NULL DEFAULT '',
        duration_seconds REAL, imported_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    existing = _add_columns(
        connection,
        "downloaded_tracks",
        {
            "artwork_url": "TEXT NOT NULL DEFAULT ''",
            "artwork_path": "TEXT NOT NULL DEFAULT ''",
            "recording_code": "TEXT NOT NULL DEFAULT ''",
            "version_code": "TEXT NOT NULL DEFAULT ''",
            "identity_key": "TEXT NOT NULL DEFAULT ''",
            "identity_confidence": "TEXT NOT NULL DEFAULT 'migrated'",
            "identity_reason": "TEXT NOT NULL DEFAULT ''",
            "audio_fingerprint": "TEXT NOT NULL DEFAULT ''",
            "identity_inference_locked": "INTEGER NOT NULL DEFAULT 0",
            "audio_quality_score": "REAL",
            "audio_quality_label": "TEXT NOT NULL DEFAULT ''",
            "audio_quality_json": "TEXT NOT NULL DEFAULT '{}'",
            "audio_quality_analyzed_at": "TEXT NOT NULL DEFAULT ''",
            "detected_key": "TEXT NOT NULL DEFAULT ''",
            "key_confidence": "REAL",
            "key_candidates_json": "TEXT NOT NULL DEFAULT '[]'",
            "key_analyzed_at": "TEXT NOT NULL DEFAULT ''",
        },
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS downloaded_track_descriptors (
        track_id INTEGER NOT NULL, category TEXT NOT NULL, value TEXT NOT NULL,
        provenance TEXT NOT NULL DEFAULT 'manual', confidence REAL NOT NULL DEFAULT 1.0,
        updated_at TEXT NOT NULL, PRIMARY KEY(track_id, category, value),
        FOREIGN KEY(track_id) REFERENCES downloaded_tracks(id) ON DELETE CASCADE)"""
    )
    if "identity_inference_locked" not in existing:
        connection.execute(
            """UPDATE downloaded_tracks SET identity_inference_locked=1
            WHERE identity_inference_locked=0 AND EXISTS (
            SELECT 1 FROM downloaded_track_descriptors descriptors
            WHERE descriptors.track_id=downloaded_tracks.id AND descriptors.provenance='manual')"""
        )


def _initialize_catalog_relations(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS downloaded_track_playlists (
        track_id INTEGER NOT NULL, playlist_name TEXT NOT NULL, added_at TEXT NOT NULL,
        PRIMARY KEY(track_id, playlist_name),
        FOREIGN KEY(track_id) REFERENCES downloaded_tracks(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS import_failures (
        id INTEGER PRIMARY KEY, playlist_name TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '', spotify_uri TEXT NOT NULL DEFAULT '',
        youtube_url TEXT NOT NULL DEFAULT '', error TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
        resolved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(playlist_name, title, artist));
        CREATE TABLE IF NOT EXISTS identity_vocabulary_rules (
        signal TEXT PRIMARY KEY, category TEXT NOT NULL DEFAULT '', value TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'approved', source TEXT NOT NULL DEFAULT 'manual',
        confidence REAL NOT NULL DEFAULT 1.0, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS downloaded_track_exclusions (
        file_path TEXT PRIMARY KEY, excluded_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_genre
        ON downloaded_tracks(genre_category, artist, title);
        CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_imported
        ON downloaded_tracks(imported_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_title
        ON downloaded_tracks(title COLLATE NOCASE, id);
        CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_artist
        ON downloaded_tracks(artist COLLATE NOCASE, title COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_recording
        ON downloaded_tracks(recording_code, version_code);
        CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_identity_key
        ON downloaded_tracks(identity_key, recording_code);
        CREATE INDEX IF NOT EXISTS idx_import_failures_open
        ON import_failures(resolved, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_downloaded_playlists_name
        ON downloaded_track_playlists(playlist_name, track_id);
        CREATE INDEX IF NOT EXISTS idx_track_descriptors_value
        ON downloaded_track_descriptors(category, value, track_id);"""
    )


def _initialize_library_search(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS library_search_index (
        job_id INTEGER PRIMARY KEY, source_name TEXT NOT NULL, title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '', downloaded_id INTEGER,
        category TEXT NOT NULL DEFAULT 'Unclassified', detail_genre TEXT NOT NULL DEFAULT '',
        roles TEXT NOT NULL DEFAULT '', preset TEXT NOT NULL DEFAULT 'default',
        requested_preset TEXT NOT NULL DEFAULT 'default', result TEXT NOT NULL,
        bpm REAL NOT NULL DEFAULT 0, musical_key TEXT NOT NULL DEFAULT '',
        camelot TEXT NOT NULL DEFAULT '', energy REAL NOT NULL DEFAULT 0.5,
        energy_band TEXT NOT NULL DEFAULT 'medium', vocals TEXT NOT NULL DEFAULT 'mixed',
        timing TEXT NOT NULL DEFAULT 'steady', updated_at TEXT NOT NULL,
        analysis_json TEXT NOT NULL DEFAULT '{}', set_analysis_json TEXT NOT NULL DEFAULT '{}')"""
    )
    _add_columns(
        connection,
        "library_search_index",
        {
            "set_analysis_json": "TEXT NOT NULL DEFAULT '{}'",
            "detail_genre": "TEXT NOT NULL DEFAULT ''",
        },
    )
    connection.executescript(
        """CREATE INDEX IF NOT EXISTS idx_library_search_updated
        ON library_search_index(updated_at DESC, job_id DESC);
        CREATE INDEX IF NOT EXISTS idx_library_search_category
        ON library_search_index(category, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_library_search_bpm ON library_search_index(bpm, job_id);
        CREATE INDEX IF NOT EXISTS idx_library_search_key ON library_search_index(musical_key, job_id);"""
    )


def _initialize_system_state(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS system_state (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS catalog_source_index (
        source_path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL,
        size INTEGER NOT NULL, scanned_at TEXT NOT NULL);"""
    )
