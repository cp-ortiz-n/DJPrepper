"""Small SQLite repository for local web processing jobs."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from audioextender.library.recording_identity import (
    format_family_code,
    identity_key,
    next_version_code,
    version_kind,
)
from audioextender.repositories.feedback import FeedbackRepositoryMixin
from audioextender.repositories.jobs import JobQueueRepositoryMixin
from audioextender.repositories.library_analysis import LibraryAnalysisRepositoryMixin
from audioextender.repositories.system_state import SystemStateRepositoryMixin
from audioextender.repositories.track_catalog import TrackCatalogRepositoryMixin


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRepository(
    SystemStateRepositoryMixin,
    JobQueueRepositoryMixin,
    LibraryAnalysisRepositoryMixin,
    FeedbackRepositoryMixin,
    TrackCatalogRepositoryMixin,
):
    """Persist job state so the dashboard survives browser and server restarts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id INTEGER PRIMARY KEY,
                        source_name TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress REAL NOT NULL DEFAULT 0,
                        stage TEXT NOT NULL DEFAULT 'Queued',
                        preset TEXT NOT NULL DEFAULT 'auto',
                        intro_bars INTEGER NOT NULL,
                        outro_bars INTEGER NOT NULL,
                        use_stems INTEGER NOT NULL DEFAULT 0,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        error TEXT,
                        extended_path TEXT,
                        wav_path TEXT,
                        intro_preview_path TEXT,
                        outro_preview_path TEXT,
                        cue_sheet_path TEXT,
                        rekordbox_path TEXT,
                        candidates_json TEXT NOT NULL DEFAULT '{}',
                        cues_json TEXT NOT NULL DEFAULT '[]',
                        parent_job_id INTEGER,
                        bpm REAL,
                        intro_quality REAL,
                        outro_quality REAL,
                        review_status TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC)"
                )
                connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source_id ON jobs(source_path, id DESC)")
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
                additions = {
                    "intro_preview_path": "TEXT",
                    "outro_preview_path": "TEXT",
                    "config_json": "TEXT NOT NULL DEFAULT '{}'",
                    "cue_sheet_path": "TEXT",
                    "rekordbox_path": "TEXT",
                    "candidates_json": "TEXT NOT NULL DEFAULT '{}'",
                    "cues_json": "TEXT NOT NULL DEFAULT '[]'",
                    "parent_job_id": "INTEGER",
                    "review_status": "TEXT",
                }
                for column, definition in additions.items():
                    if column not in columns:
                        connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
                rows = connection.execute("SELECT id, parent_job_id, config_json, review_status FROM jobs").fetchall()
                for row in rows:
                    if row["review_status"] is not None:
                        continue
                    try:
                        job_config = json.loads(row["config_json"] or "{}")
                    except (TypeError, ValueError):
                        job_config = {}
                    if job_config.get("review_candidates"):
                        state = "resolved" if job_config.get("manual_candidate_selection") else "pending"
                        connection.execute(
                            "UPDATE jobs SET review_status = ? WHERE id = ?",
                            (state, row["id"]),
                        )
                for row in rows:
                    try:
                        child_config = json.loads(row["config_json"] or "{}")
                    except (TypeError, ValueError):
                        child_config = {}
                    if row["parent_job_id"] and child_config.get("manual_candidate_selection"):
                        connection.execute(
                            "UPDATE jobs SET review_status = 'resolved' WHERE id = ?",
                            (row["parent_job_id"],),
                        )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS web_settings (
                        key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS candidate_feedback (
                        id INTEGER PRIMARY KEY,
                        job_id INTEGER NOT NULL,
                        position TEXT NOT NULL,
                        candidate_rank INTEGER,
                        accepted INTEGER NOT NULL,
                        tags TEXT NOT NULL DEFAULT '',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(job_id) REFERENCES jobs(id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS track_feedback (
                        id INTEGER PRIMARY KEY,
                        source_name TEXT NOT NULL,
                        position TEXT NOT NULL,
                        accepted INTEGER NOT NULL,
                        tags TEXT NOT NULL DEFAULT '',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_track_feedback_source "
                    "ON track_feedback(source_name COLLATE NOCASE, created_at DESC)"
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS key_verifications (
                        source_name TEXT PRIMARY KEY COLLATE NOCASE,
                        verified_key TEXT NOT NULL,
                        detected_key TEXT NOT NULL DEFAULT '',
                        candidates_json TEXT NOT NULL DEFAULT '[]',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS downloaded_tracks (
                        id INTEGER PRIMARY KEY,
                        title TEXT NOT NULL,
                        artist TEXT NOT NULL DEFAULT '',
                        file_path TEXT NOT NULL UNIQUE,
                        filename TEXT NOT NULL,
                        genre TEXT NOT NULL DEFAULT '',
                        genre_category TEXT NOT NULL DEFAULT 'Other',
                        spotify_uri TEXT NOT NULL DEFAULT '',
                        youtube_id TEXT NOT NULL DEFAULT '',
                        youtube_url TEXT NOT NULL DEFAULT '',
                        artwork_url TEXT NOT NULL DEFAULT '',
                        artwork_path TEXT NOT NULL DEFAULT '',
                        duration_seconds REAL,
                        imported_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                downloaded_columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(downloaded_tracks)").fetchall()
                }
                for column in ("artwork_url", "artwork_path"):
                    if column not in downloaded_columns:
                        connection.execute(
                            f"ALTER TABLE downloaded_tracks ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                        )
                identity_columns = {
                    "recording_code": "TEXT NOT NULL DEFAULT ''",
                    "version_code": "TEXT NOT NULL DEFAULT ''",
                    "identity_key": "TEXT NOT NULL DEFAULT ''",
                    "identity_confidence": "TEXT NOT NULL DEFAULT 'migrated'",
                    "identity_reason": "TEXT NOT NULL DEFAULT ''",
                    "audio_fingerprint": "TEXT NOT NULL DEFAULT ''",
                    "identity_inference_locked": "INTEGER NOT NULL DEFAULT 0",
                }
                identity_lock_added = "identity_inference_locked" not in downloaded_columns
                for column, definition in identity_columns.items():
                    if column not in downloaded_columns:
                        connection.execute(f"ALTER TABLE downloaded_tracks ADD COLUMN {column} {definition}")
                quality_columns = {
                    "audio_quality_score": "REAL",
                    "audio_quality_label": "TEXT NOT NULL DEFAULT ''",
                    "audio_quality_json": "TEXT NOT NULL DEFAULT '{}'",
                    "audio_quality_analyzed_at": "TEXT NOT NULL DEFAULT ''",
                }
                for column, definition in quality_columns.items():
                    if column not in downloaded_columns:
                        connection.execute(f"ALTER TABLE downloaded_tracks ADD COLUMN {column} {definition}")
                key_analysis_columns = {
                    "detected_key": "TEXT NOT NULL DEFAULT ''",
                    "key_confidence": "REAL",
                    "key_candidates_json": "TEXT NOT NULL DEFAULT '[]'",
                    "key_analyzed_at": "TEXT NOT NULL DEFAULT ''",
                }
                for column, definition in key_analysis_columns.items():
                    if column not in downloaded_columns:
                        connection.execute(f"ALTER TABLE downloaded_tracks ADD COLUMN {column} {definition}")
                self._ensure_recording_identities(connection)
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS downloaded_track_playlists (
                        track_id INTEGER NOT NULL,
                        playlist_name TEXT NOT NULL,
                        added_at TEXT NOT NULL,
                        PRIMARY KEY(track_id, playlist_name),
                        FOREIGN KEY(track_id) REFERENCES downloaded_tracks(id) ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_genre "
                    "ON downloaded_tracks(genre_category, artist, title)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_imported "
                    "ON downloaded_tracks(imported_at DESC, id DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_title "
                    "ON downloaded_tracks(title COLLATE NOCASE, id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_artist "
                    "ON downloaded_tracks(artist COLLATE NOCASE, title COLLATE NOCASE)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_recording "
                    "ON downloaded_tracks(recording_code, version_code)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_tracks_identity_key "
                    "ON downloaded_tracks(identity_key, recording_code)"
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS import_failures (
                        id INTEGER PRIMARY KEY,
                        playlist_name TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL,
                        artist TEXT NOT NULL DEFAULT '',
                        spotify_uri TEXT NOT NULL DEFAULT '',
                        youtube_url TEXT NOT NULL DEFAULT '',
                        error TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 1,
                        resolved INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(playlist_name, title, artist)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_import_failures_open ON import_failures(resolved, updated_at DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_playlists_name "
                    "ON downloaded_track_playlists(playlist_name, track_id)"
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS downloaded_track_descriptors (
                    track_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    value TEXT NOT NULL,
                    provenance TEXT NOT NULL DEFAULT 'manual',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(track_id, category, value),
                    FOREIGN KEY(track_id) REFERENCES downloaded_tracks(id) ON DELETE CASCADE
                    )"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_track_descriptors_value "
                    "ON downloaded_track_descriptors(category, value, track_id)"
                )
                if identity_lock_added:
                    connection.execute(
                        """UPDATE downloaded_tracks SET identity_inference_locked=1
                    WHERE identity_inference_locked=0 AND EXISTS (
                        SELECT 1 FROM downloaded_track_descriptors descriptors
                        WHERE descriptors.track_id=downloaded_tracks.id
                        AND descriptors.provenance='manual'
                    )"""
                    )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS identity_vocabulary_rules (
                    signal TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT '',
                    value TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'approved',
                    source TEXT NOT NULL DEFAULT 'manual',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS library_search_index (
                    job_id INTEGER PRIMARY KEY, source_name TEXT NOT NULL,
                    title TEXT NOT NULL, artist TEXT NOT NULL DEFAULT '',
                    downloaded_id INTEGER, category TEXT NOT NULL DEFAULT 'Unclassified',
                    detail_genre TEXT NOT NULL DEFAULT '',
                    roles TEXT NOT NULL DEFAULT '', preset TEXT NOT NULL DEFAULT 'default',
                    requested_preset TEXT NOT NULL DEFAULT 'default', result TEXT NOT NULL,
                    bpm REAL NOT NULL DEFAULT 0, musical_key TEXT NOT NULL DEFAULT '',
                    camelot TEXT NOT NULL DEFAULT '', energy REAL NOT NULL DEFAULT 0.5,
                    energy_band TEXT NOT NULL DEFAULT 'medium', vocals TEXT NOT NULL DEFAULT 'mixed',
                    timing TEXT NOT NULL DEFAULT 'steady', updated_at TEXT NOT NULL,
                    analysis_json TEXT NOT NULL DEFAULT '{}',
                    set_analysis_json TEXT NOT NULL DEFAULT '{}')"""
                )
                library_columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(library_search_index)").fetchall()
                }
                if "set_analysis_json" not in library_columns:
                    connection.execute(
                        "ALTER TABLE library_search_index ADD COLUMN set_analysis_json TEXT NOT NULL DEFAULT '{}'"
                    )
                if "detail_genre" not in library_columns:
                    connection.execute(
                        "ALTER TABLE library_search_index ADD COLUMN detail_genre TEXT NOT NULL DEFAULT ''"
                    )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_library_search_updated "
                    "ON library_search_index(updated_at DESC, job_id DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_library_search_category "
                    "ON library_search_index(category, updated_at DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_library_search_bpm ON library_search_index(bpm, job_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_library_search_key ON library_search_index(musical_key, job_id)"
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS downloaded_track_exclusions (
                    file_path TEXT PRIMARY KEY, excluded_at TEXT NOT NULL)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS catalog_source_index (
                    source_path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL, scanned_at TEXT NOT NULL)"""
                )
                connection.execute("PRAGMA optimize")

    @staticmethod
    def _next_recording_number(connection: sqlite3.Connection) -> int:
        numbers = []
        for row in connection.execute("SELECT DISTINCT recording_code FROM downloaded_tracks"):
            try:
                match = re.fullmatch(r"[A-Z]{2,4}-(\d+)", str(row[0]))
                if match:
                    numbers.append(int(match.group(1)))
            except (IndexError, ValueError):
                continue
        return max(numbers, default=0) + 1

    def _ensure_recording_identities(self, connection: sqlite3.Connection) -> None:
        """Backfill stable identities without moving or renaming existing files."""
        connection.execute(
            """CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        migration = connection.execute("SELECT value FROM system_state WHERE key='recording_genre_codes'").fetchone()
        legacy_families = connection.execute(
            """SELECT recording_code,
            COALESCE(MAX(CASE WHEN version_code='ORG' THEN genre_category END),
                     MAX(genre_category), 'Other') AS genre_category
            FROM downloaded_tracks
            GROUP BY recording_code"""
        ).fetchall()
        if migration is None:
            for family in legacy_families:
                try:
                    number = int(str(family["recording_code"]).split("-", 1)[1])
                except (IndexError, ValueError):
                    continue
                new_code = format_family_code(number, str(family["genre_category"] or "Other"))
                connection.execute(
                    "UPDATE downloaded_tracks SET recording_code=? WHERE recording_code=?",
                    (new_code, family["recording_code"]),
                )
            connection.execute(
                "INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)",
                ("recording_genre_codes", "v1", _now()),
            )
        missing = connection.execute("SELECT 1 FROM downloaded_tracks WHERE recording_code='' LIMIT 1").fetchone()
        if missing is None:
            return
        rows = connection.execute("SELECT * FROM downloaded_tracks ORDER BY id").fetchall()
        next_number = self._next_recording_number(connection)
        families: dict[str, str] = {}
        versions: dict[str, set[str]] = {}
        for row in rows:
            current_code = str(row["recording_code"] or "")
            key = str(row["identity_key"] or "") or identity_key(str(row["artist"] or ""), str(row["title"] or ""))
            if current_code:
                families.setdefault(key, current_code)
                versions.setdefault(current_code, set()).add(str(row["version_code"] or "ORG"))
                if not row["identity_key"]:
                    connection.execute(
                        "UPDATE downloaded_tracks SET identity_key=? WHERE id=?",
                        (key, row["id"]),
                    )
                continue
            family = families.get(key)
            if not family:
                family = format_family_code(next_number, str(row["genre_category"] or "Other"))
                next_number += 1
                families[key] = family
            existing = versions.setdefault(family, set())
            version = next_version_code(version_kind(str(row["title"] or "")), existing)
            existing.add(version)
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?, version_code=?,
                identity_key=?, identity_confidence='migrated',
                identity_reason='Assigned from existing artist and title' WHERE id=?""",
                (family, version, key, row["id"]),
            )
