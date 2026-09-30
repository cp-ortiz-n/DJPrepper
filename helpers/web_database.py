"""Small SQLite repository for local web processing jobs."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from helpers.recording_identity import (
    audio_fingerprint,
    base_title,
    format_family_code,
    identity_key,
    next_version_code,
    normalize_identity_text,
    version_kind,
)
from helpers.repository_views import RepositoryBundle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteApplicationStore:
    """Internal SQLite implementation shared by the focused repositories.

    Application code should depend on one of the domain repositories exposed on
    :class:`JobRepository`, rather than on this storage engine directly.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()
        repositories = RepositoryBundle(self)
        self.track_catalog = repositories.track_catalog
        self.jobs_and_queues = repositories.jobs_and_queues
        self.settings_system = repositories.settings_system
        self.recording_families = repositories.recording_families
        self.feedback_key_verification = repositories.feedback_key_verification
        self.backups_relocation = repositories.backups_relocation

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
                    "CREATE INDEX IF NOT EXISTS idx_jobs_status_created "
                    "ON jobs(status, created_at DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_source_id ON jobs(source_path, id DESC)"
                )
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
                }
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
                rows = connection.execute(
                    "SELECT id, parent_job_id, config_json, review_status FROM jobs"
                ).fetchall()
                for row in rows:
                    if row["review_status"] is not None:
                        continue
                    try:
                        job_config = json.loads(row["config_json"] or "{}")
                    except (TypeError, ValueError):
                        job_config = {}
                    if job_config.get("review_candidates"):
                        state = (
                            "resolved"
                            if job_config.get("manual_candidate_selection")
                            else "pending"
                        )
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
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(downloaded_tracks)").fetchall()
                }
                for column in ("artwork_url", "artwork_path"):
                    if column not in downloaded_columns:
                        connection.execute(
                            f"ALTER TABLE downloaded_tracks ADD COLUMN {column} "
                            "TEXT NOT NULL DEFAULT ''"
                        )
                identity_columns = {
                    "recording_code": "TEXT NOT NULL DEFAULT ''",
                    "version_code": "TEXT NOT NULL DEFAULT ''",
                    "identity_key": "TEXT NOT NULL DEFAULT ''",
                    "identity_confidence": "TEXT NOT NULL DEFAULT 'migrated'",
                    "identity_reason": "TEXT NOT NULL DEFAULT ''",
                    "audio_fingerprint": "TEXT NOT NULL DEFAULT ''",
                }
                for column, definition in identity_columns.items():
                    if column not in downloaded_columns:
                        connection.execute(
                            f"ALTER TABLE downloaded_tracks ADD COLUMN {column} {definition}"
                        )
                quality_columns = {
                    "audio_quality_score": "REAL",
                    "audio_quality_label": "TEXT NOT NULL DEFAULT ''",
                    "audio_quality_json": "TEXT NOT NULL DEFAULT '{}'",
                    "audio_quality_analyzed_at": "TEXT NOT NULL DEFAULT ''",
                }
                for column, definition in quality_columns.items():
                    if column not in downloaded_columns:
                        connection.execute(
                            f"ALTER TABLE downloaded_tracks ADD COLUMN {column} {definition}"
                        )
                key_analysis_columns = {
                    "detected_key": "TEXT NOT NULL DEFAULT ''",
                    "key_confidence": "REAL",
                    "key_candidates_json": "TEXT NOT NULL DEFAULT '[]'",
                    "key_analyzed_at": "TEXT NOT NULL DEFAULT ''",
                }
                for column, definition in key_analysis_columns.items():
                    if column not in downloaded_columns:
                        connection.execute(
                            f"ALTER TABLE downloaded_tracks ADD COLUMN {column} {definition}"
                        )
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
                    "CREATE INDEX IF NOT EXISTS idx_import_failures_open "
                    "ON import_failures(resolved, updated_at DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_downloaded_playlists_name "
                    "ON downloaded_track_playlists(playlist_name, track_id)"
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
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(library_search_index)"
                    ).fetchall()
                }
                if "set_analysis_json" not in library_columns:
                    connection.execute(
                        "ALTER TABLE library_search_index ADD COLUMN "
                        "set_analysis_json TEXT NOT NULL DEFAULT '{}'"
                    )
                if "detail_genre" not in library_columns:
                    connection.execute(
                        "ALTER TABLE library_search_index ADD COLUMN "
                        "detail_genre TEXT NOT NULL DEFAULT ''"
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
                    "CREATE INDEX IF NOT EXISTS idx_library_search_bpm "
                    "ON library_search_index(bpm, job_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_library_search_key "
                    "ON library_search_index(musical_key, job_id)"
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
        migration = connection.execute(
            "SELECT value FROM system_state WHERE key='recording_genre_codes'"
        ).fetchone()
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
        missing = connection.execute(
            "SELECT 1 FROM downloaded_tracks WHERE recording_code='' LIMIT 1"
        ).fetchone()
        if missing is None:
            return
        rows = connection.execute("SELECT * FROM downloaded_tracks ORDER BY id").fetchall()
        next_number = self._next_recording_number(connection)
        families: dict[str, str] = {}
        versions: dict[str, set[str]] = {}
        for row in rows:
            current_code = str(row["recording_code"] or "")
            key = str(row["identity_key"] or "") or identity_key(
                str(row["artist"] or ""), str(row["title"] or "")
            )
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

    def get_system_state(self, key: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT value FROM system_state WHERE key=?", (key,)
            ).fetchone()
        return str(row["value"]) if row else None

    def set_system_state(self, key: str, value: str) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                updated_at=excluded.updated_at""",
                (key, value, _now()),
            )

    def library_index_source_signature(self) -> str:
        """Return a stable logical signature unaffected by unrelated SQLite writes."""
        with closing(self._connect()) as connection:
            jobs = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(MAX(updated_at),'') "
                "FROM jobs WHERE status='complete'"
            ).fetchone()
            tracks = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(MAX(updated_at),'') "
                "FROM downloaded_tracks"
            ).fetchone()
            indexed = int(
                connection.execute("SELECT COUNT(*) FROM library_search_index").fetchone()[0]
            )
        return json.dumps(
            {"jobs": list(jobs), "tracks": list(tracks), "indexed": indexed}, separators=(",", ":")
        )

    def catalog_source_signatures(self) -> dict[str, tuple[int, int]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT source_path,mtime_ns,size FROM catalog_source_index"
            ).fetchall()
        return {str(row["source_path"]): (int(row["mtime_ns"]), int(row["size"])) for row in rows}

    def upsert_catalog_source_signatures(self, signatures: list[tuple[str, int, int]]) -> None:
        if not signatures:
            return
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO catalog_source_index
                (source_path,mtime_ns,size,scanned_at) VALUES (?,?,?,?)
                ON CONFLICT(source_path) DO UPDATE SET
                mtime_ns=excluded.mtime_ns,size=excluded.size,
                scanned_at=excluded.scanned_at""",
                [(path, mtime, size, now) for path, mtime, size in signatures],
            )

    def create(
        self,
        source_name: str,
        source_path: Path,
        preset: str,
        intro_bars: int,
        outro_bars: int,
        use_stems: bool,
        config_overrides: dict[str, Any] | None = None,
        parent_job_id: int | None = None,
    ) -> int:
        now = _now()
        config_values = config_overrides or {}
        review_status = (
            "resolved"
            if config_values.get("manual_candidate_selection")
            else "pending"
            if config_values.get("review_candidates")
            else None
        )
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (
                    source_name, source_path, status, preset, intro_bars,
                    outro_bars, use_stems, config_json, parent_job_id,
                    review_status, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_name,
                    str(source_path.resolve()),
                    preset,
                    intro_bars,
                    outro_bars,
                    int(use_stems),
                    json.dumps(config_values, sort_keys=True),
                    parent_job_id,
                    review_status,
                    now,
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a job id")
            return cursor.lastrowid

    def update(self, job_id: int, **values: Any) -> None:
        allowed = {
            "status",
            "progress",
            "stage",
            "error",
            "extended_path",
            "wav_path",
            "intro_preview_path",
            "outro_preview_path",
            "bpm",
            "intro_quality",
            "outro_quality",
            "cue_sheet_path",
            "rekordbox_path",
            "candidates_json",
            "cues_json",
            "review_status",
        }
        selected = {key: value for key, value in values.items() if key in allowed}
        if not selected:
            return
        selected["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in selected)
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",  # noqa: S608
                (*selected.values(), job_id),
            )

    def get(self, job_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_storage_job_references(self) -> list[dict[str, Any]]:
        """Return only fields needed to classify managed cache and output files."""
        columns = (
            "source_path, wav_path, extended_path, intro_preview_path, "
            "outro_preview_path, cue_sheet_path, rekordbox_path, preset, "
            "intro_bars, outro_bars, use_stems, config_json"
        )
        with closing(self._connect()) as connection:
            rows = connection.execute(f"SELECT {columns} FROM jobs").fetchall()
        return [dict(row) for row in rows]

    def analytics_summary(self) -> dict[str, Any]:
        """Return dashboard aggregates without loading full job rows into Python."""
        with closing(self._connect()) as connection:
            job_counts = connection.execute(
                """SELECT COUNT(*) AS completed,
                COALESCE(SUM(CASE WHEN use_stems = 1 THEN 1 ELSE 0 END), 0) AS stemmed
                FROM jobs WHERE status = 'complete'"""
            ).fetchone()
            feedback_rows = connection.execute(
                """SELECT accepted, tags FROM candidate_feedback
                UNION ALL SELECT accepted, tags FROM track_feedback"""
            ).fetchall()
        return {
            "completed": int(job_counts["completed"]),
            "stemmed": int(job_counts["stemmed"]),
            "feedback": [dict(row) for row in feedback_rows],
        }

    def list_job_summaries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return queue-card fields without the potentially large candidate and cue payloads."""
        columns = (
            "id, source_name, source_path, status, progress, stage, preset, intro_bars, "
            "outro_bars, use_stems, error, extended_path, wav_path, bpm, intro_quality, "
            "outro_quality, created_at, updated_at, intro_preview_path, outro_preview_path, "
            "config_json, cue_sheet_path, rekordbox_path, parent_job_id, review_status"
        )
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT {columns} FROM jobs ORDER BY id DESC LIMIT ?",  # noqa: S608
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_jobs_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        statuses: tuple[str, ...] = (),
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a bounded jobs page without materializing the full history."""
        where = ""
        parameters: tuple[Any, ...] = ()
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            where = f"WHERE status IN ({placeholders})"
            parameters = statuses
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM jobs {where}",  # noqa: S608
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?",  # noqa: S608
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(row) for row in rows], total

    def list_latest_completed_jobs(self) -> list[dict[str, Any]]:
        """Return one latest completed generation per source using SQLite grouping."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """WITH latest AS (
                    SELECT source_path, MAX(id) AS job_id, COUNT(*) AS generation_count
                    FROM jobs WHERE status = 'complete' GROUP BY source_path
                )
                SELECT jobs.*, latest.generation_count
                FROM latest JOIN jobs ON jobs.id = latest.job_id
                ORDER BY jobs.updated_at DESC, jobs.id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def list_report_audio_jobs(self) -> list[dict[str, Any]]:
        """Return the newest completed audio references for every report track name.

        Report history outlives the bounded queue listing, so diagnostics must not
        depend on ``list_job_summaries`` to locate previews for older tracks.
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """WITH latest AS (
                    SELECT LOWER(source_name) AS source_key, MAX(id) AS job_id
                    FROM jobs WHERE status = 'complete' GROUP BY LOWER(source_name)
                )
                SELECT jobs.id, jobs.source_name, jobs.wav_path, jobs.extended_path,
                (SELECT id FROM downloaded_tracks
                 WHERE file_path=jobs.source_path
                 ORDER BY id LIMIT 1) AS downloaded_track_id,
                (SELECT detected_key FROM downloaded_tracks
                 WHERE file_path=jobs.source_path
                 ORDER BY id LIMIT 1) AS latest_detected_key,
                (SELECT key_confidence FROM downloaded_tracks
                 WHERE file_path=jobs.source_path
                 ORDER BY id LIMIT 1) AS latest_key_confidence,
                (SELECT key_analyzed_at FROM downloaded_tracks
                 WHERE file_path=jobs.source_path
                 ORDER BY id LIMIT 1) AS key_analyzed_at
                FROM latest JOIN jobs ON jobs.id = latest.job_id
                ORDER BY jobs.id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def list_completed_versions(self, source_path: str) -> list[dict[str, Any]]:
        """Load version history only when a Library card asks for it."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM jobs WHERE status = 'complete' AND source_path = ?
                ORDER BY id DESC""",
                (source_path,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_library_search_index(self, entries: list[dict[str, Any]]) -> None:
        """Atomically refresh the compact, queryable latest-generation Library index."""
        columns = (
            "job_id",
            "source_name",
            "title",
            "artist",
            "downloaded_id",
            "category",
            "detail_genre",
            "roles",
            "preset",
            "requested_preset",
            "result",
            "bpm",
            "musical_key",
            "camelot",
            "energy",
            "energy_band",
            "vocals",
            "timing",
            "updated_at",
            "analysis_json",
            "set_analysis_json",
        )
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM library_search_index")
            if entries:
                connection.executemany(
                    f"INSERT INTO library_search_index ({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})",
                    [
                        tuple(
                            entry.get(column, "{}")
                            if column == "set_analysis_json"
                            else entry.get(column, "")
                            if column == "detail_genre"
                            else entry.get(column)
                            for column in columns
                        )
                        for entry in entries
                    ],
                )

    def page_library_tracks(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        role: str = "all",
        category: str = "all",
        detail_genre: str = "all",
        preset: str = "all",
        result: str = "all",
        quality: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        musical_key: str = "all",
        energy: str = "all",
        vocals: str = "all",
        timing: str = "all",
        sort: str = "newest",
    ) -> tuple[list[dict[str, Any]], int]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if search.strip():
            value = f"%{search.strip().casefold()}%"
            conditions.append(
                "(LOWER(idx.source_name) LIKE ? OR LOWER(idx.title) LIKE ? OR "
                "LOWER(idx.artist) LIKE ? OR LOWER(idx.category) LIKE ? OR LOWER(idx.detail_genre) LIKE ? OR "
                "LOWER(idx.roles) LIKE ? OR LOWER(idx.preset) LIKE ? OR "
                "LOWER(idx.musical_key) LIKE ? OR LOWER(idx.camelot) LIKE ? OR "
                "LOWER(COALESCE(tracks.recording_code, '')) LIKE ? OR "
                "LOWER(COALESCE(tracks.recording_code, '') || '-' || "
                "COALESCE(tracks.version_code, '')) LIKE ?)"
            )
            parameters.extend([value] * 11)
        if role != "all":
            conditions.append("idx.roles LIKE ?")
            parameters.append(f"%|{role}|%")
        if category != "all":
            conditions.append("(LOWER(idx.category) = ? OR LOWER(idx.category) LIKE ?)")
            normalized = category.casefold()
            parameters.extend((normalized, f"{normalized} / %"))
        if detail_genre != "all":
            conditions.append(
                "(',' || REPLACE(REPLACE(LOWER(COALESCE(idx.detail_genre, '')), ', ', ','), ' ,', ',') || ',') LIKE ?"
            )
            parameters.append(f"%,{detail_genre.strip().casefold()},%")
        for column, value in (
            ("preset", preset),
            ("result", result),
            ("musical_key", musical_key),
            ("energy_band", energy),
            ("vocals", vocals),
            ("timing", timing),
        ):
            if value != "all":
                conditions.append(f"idx.{column} = ?")
                parameters.append(value)
        if bpm_min is not None:
            conditions.append("idx.bpm >= ?")
            parameters.append(bpm_min)
        if bpm_max is not None:
            conditions.append("idx.bpm <= ?")
            parameters.append(bpm_max)
        quality_conditions = {
            "excellent": "tracks.audio_quality_label = 'excellent'",
            "good": "tracks.audio_quality_label = 'good'",
            "review": "tracks.audio_quality_label = 'review'",
            "poor": "tracks.audio_quality_label = 'poor'",
            "below-target": "tracks.audio_quality_label IN ('review','poor')",
            "unanalyzed": "tracks.audio_quality_score IS NULL",
        }
        if quality in quality_conditions:
            conditions.append(quality_conditions[quality])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order = {
            "title": "idx.title COLLATE NOCASE, idx.job_id",
            "bpm-up": "idx.bpm, idx.job_id",
            "bpm-down": "idx.bpm DESC, idx.job_id DESC",
            "energy-down": "idx.energy DESC, idx.job_id DESC",
            "newest": "idx.updated_at DESC, idx.job_id DESC",
        }.get(sort, "idx.updated_at DESC, idx.job_id DESC")
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"""SELECT COUNT(*) FROM library_search_index idx
                LEFT JOIN downloaded_tracks tracks ON tracks.id = idx.downloaded_id
                {where}""",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT jobs.id, jobs.source_name, jobs.source_path, jobs.status,
                jobs.progress, jobs.stage, jobs.preset, jobs.intro_bars, jobs.outro_bars,
                jobs.use_stems, jobs.config_json, jobs.error, jobs.extended_path, jobs.wav_path,
                jobs.intro_preview_path, jobs.outro_preview_path, jobs.cue_sheet_path,
                jobs.rekordbox_path, jobs.parent_job_id, jobs.bpm, jobs.intro_quality,
                jobs.outro_quality, jobs.review_status, jobs.created_at, jobs.updated_at,
                idx.job_id, idx.downloaded_id,
                idx.title AS library_title, idx.artist AS library_artist,
                idx.category AS library_category, idx.detail_genre AS library_detail_genre,
                idx.roles AS library_roles,
                idx.preset AS library_preset, idx.requested_preset, idx.result AS library_result,
                idx.bpm AS library_bpm, idx.musical_key, idx.camelot,
                idx.energy AS library_energy, idx.energy_band, idx.vocals, idx.timing,
                (SELECT COUNT(*) FROM jobs version
                 WHERE version.status = 'complete' AND version.source_path = jobs.source_path)
                 AS generation_count,
                tracks.genre, tracks.genre_category, tracks.recording_code,
                tracks.version_code, tracks.identity_confidence, tracks.identity_reason,
                tracks.audio_quality_score, tracks.audio_quality_label,
                tracks.audio_quality_json, tracks.audio_quality_analyzed_at,
                tracks.artwork_path, tracks.file_path AS downloaded_file_path
                FROM library_search_index idx JOIN jobs ON jobs.id = idx.job_id
                LEFT JOIN downloaded_tracks tracks ON tracks.id = idx.downloaded_id
                {where} ORDER BY {order} LIMIT ? OFFSET ?""",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(row) for row in rows], total

    def library_search_facets(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = int(
                connection.execute("SELECT COUNT(*) FROM library_search_index").fetchone()[0]
            )
            categories = dict(
                connection.execute(
                    "SELECT category, COUNT(*) FROM library_search_index GROUP BY category"
                ).fetchall()
            )
            detail_rows = connection.execute(
                "SELECT category, detail_genre, COUNT(*) FROM library_search_index "
                "WHERE detail_genre != '' GROUP BY category, detail_genre"
            ).fetchall()
            presets = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT preset FROM library_search_index ORDER BY preset"
                ).fetchall()
            ]
            keys = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT musical_key FROM library_search_index "
                    "WHERE musical_key != '' ORDER BY musical_key"
                ).fetchall()
            ]
            role_rows = connection.execute("SELECT roles FROM library_search_index").fetchall()
            intelligence = connection.execute(
                """SELECT job_id, source_name, bpm, musical_key, roles, energy,
                energy_band, vocals, timing FROM library_search_index"""
            ).fetchall()
        roles: dict[str, int] = {}
        for row in role_rows:
            for name in str(row[0] or "").strip("|").split("|"):
                if name:
                    roles[name] = roles.get(name, 0) + 1
        detailed_genres: dict[str, int] = {}
        detailed_by_category: dict[str, dict[str, int]] = {}
        canonical: dict[str, str] = {}
        for category, raw_genres, count in detail_rows:
            category_counts = detailed_by_category.setdefault(str(category), {})
            for raw_genre in str(raw_genres or "").split(","):
                genre = raw_genre.strip()
                if not genre:
                    continue
                display = canonical.setdefault(genre.casefold(), genre)
                detailed_genres[display] = detailed_genres.get(display, 0) + int(count)
                category_counts[display] = category_counts.get(display, 0) + int(count)
        return {
            "total": total,
            "categories": categories,
            "detailed_genres": detailed_genres,
            "detailed_genres_by_category": detailed_by_category,
            "presets": presets,
            "keys": keys,
            "roles": roles,
            "intelligence": [dict(row) for row in intelligence],
        }

    def get_library_analysis(self, job_id: int) -> dict[str, Any]:
        """Load one indexed analysis record for waveform timeline rendering."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT analysis_json FROM library_search_index WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            return {}
        try:
            return json.loads(str(row["analysis_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def list_set_builder_tracks(self) -> list[dict[str, Any]]:
        """Return every latest analyzed track using the compact Library index."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT idx.job_id, idx.source_name, idx.category, idx.detail_genre, idx.roles,
                idx.energy, idx.vocals, idx.timing, idx.set_analysis_json,
                jobs.source_path, jobs.wav_path,
                jobs.extended_path, jobs.config_json,
                downloaded.file_path AS library_path
                FROM library_search_index idx
                JOIN jobs ON jobs.id = idx.job_id
                LEFT JOIN downloaded_tracks downloaded ON downloaded.id = idx.downloaded_id
                ORDER BY idx.source_name COLLATE NOCASE, idx.job_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, job_id: int) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM candidate_feedback WHERE job_id = ?", (job_id,))
            cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0

    def add_feedback(
        self,
        job_id: int,
        position: str,
        candidate_rank: int | None,
        accepted: bool,
        tags: str,
        notes: str,
    ) -> int:
        with self._lock, closing(self._connect()) as connection, connection:
            if accepted:
                connection.execute(
                    "DELETE FROM candidate_feedback WHERE job_id = ? AND position = ?",
                    (job_id, position),
                )
            else:
                connection.execute(
                    """DELETE FROM candidate_feedback
                    WHERE job_id = ? AND position = ? AND candidate_rank IS ?""",
                    (job_id, position, candidate_rank),
                )
            cursor = connection.execute(
                """INSERT INTO candidate_feedback
                (job_id, position, candidate_rank, accepted, tags, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (job_id, position, candidate_rank, int(accepted), tags, notes, _now()),
            )
            return int(cursor.lastrowid or 0)

    def feedback(self, job_id: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM candidate_feedback"
        parameters: tuple[Any, ...] = ()
        if job_id is not None:
            query += " WHERE job_id = ?"
            parameters = (job_id,)
        query += " ORDER BY id DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def add_track_feedback(
        self,
        source_name: str,
        position: str,
        accepted: bool,
        tags: str,
        notes: str,
    ) -> int:
        """Store feedback against a processed track, including CLI-only tracks."""
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """INSERT INTO track_feedback
                (source_name, position, accepted, tags, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (source_name, position, int(accepted), tags, notes, _now()),
            )
            return int(cursor.lastrowid or 0)

    def track_feedback(self, source_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM track_feedback"
        parameters: tuple[Any, ...] = ()
        if source_name is not None:
            query += " WHERE source_name = ? COLLATE NOCASE"
            parameters = (source_name,)
        query += " ORDER BY id DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def set_key_verification(
        self,
        source_name: str,
        verified_key: str,
        detected_key: str,
        candidates: list[dict[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        """Persist a user-confirmed key independently from generated analysis."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO key_verifications
                (source_name, verified_key, detected_key, candidates_json, notes,
                 created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                verified_key=excluded.verified_key,
                detected_key=excluded.detected_key,
                candidates_json=excluded.candidates_json,
                notes=excluded.notes,
                updated_at=excluded.updated_at""",
                (
                    source_name,
                    verified_key,
                    detected_key,
                    json.dumps(candidates, separators=(",", ":")),
                    notes,
                    now,
                    now,
                ),
            )
        return self.key_verification(source_name) or {}

    def key_verification(self, source_name: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM key_verifications WHERE source_name=? COLLATE NOCASE",
                (source_name,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["candidates"] = json.loads(item.pop("candidates_json") or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            item["candidates"] = []
        return item

    def key_verifications(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM key_verifications ORDER BY updated_at DESC"
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            try:
                item["candidates"] = json.loads(item.pop("candidates_json") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                item["candidates"] = []
            results.append(item)
        return results

    def delete_key_verification(self, source_name: str) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM key_verifications WHERE source_name=? COLLATE NOCASE",
                (source_name,),
            )
        return cursor.rowcount > 0

    def recover_interrupted(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE jobs SET status = 'failed', stage = 'Server stopped', "
                "error = 'Processing was interrupted when the web app stopped', "
                "updated_at = ? WHERE status = 'processing'",
                (_now(),),
            )

    def fail_stalled_jobs(self, minutes: int = 30) -> int:
        """Close processing records that have stopped reporting progress."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(
            timespec="seconds"
        )
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE jobs SET status='failed', stage='Processing stalled',
                error='No processing progress was reported for 30 minutes', updated_at=?
                WHERE status='processing' AND updated_at < ?""",
                (_now(), cutoff),
            )
        return cursor.rowcount

    def library_index_count(self) -> int:
        with closing(self._connect()) as connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM library_search_index").fetchone()[0]
            )

    def get_settings(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT key, value_json FROM web_settings").fetchall()
        settings: dict[str, Any] = {}
        for row in rows:
            try:
                settings[str(row["key"])] = json.loads(row["value_json"])
            except (TypeError, ValueError):
                continue
        return settings

    def replace_settings(self, values: dict[str, Any]) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM web_settings")
            connection.executemany(
                "INSERT INTO web_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                [(key, json.dumps(value), _now()) for key, value in values.items()],
            )

    def relocate_library_paths(self, old_root: Path, new_root: Path) -> dict[str, int]:
        """Atomically rewrite managed library paths while preserving record IDs."""
        old_root = old_root.expanduser().resolve()
        new_root = new_root.expanduser().resolve()
        old_prefix = str(old_root) + "/"
        new_prefix = str(new_root) + "/"
        counts = {"tracks": 0, "artwork": 0, "jobs": 0, "job_paths": 0, "sources": 0}
        with self._lock, closing(self._connect()) as connection, connection:
            duplicate = connection.execute(
                """SELECT COUNT(*) FROM downloaded_tracks target
                WHERE target.file_path LIKE ? AND EXISTS (
                    SELECT 1 FROM downloaded_tracks source
                    WHERE source.file_path LIKE ?
                    AND target.file_path = ? || SUBSTR(source.file_path, ?)
                    AND target.id != source.id)""",
                (new_prefix + "%", old_prefix + "%", new_prefix, len(old_prefix) + 1),
            ).fetchone()[0]
            if duplicate:
                raise ValueError(
                    "The destination is already represented by conflicting catalog records"
                )
            cursor = connection.execute(
                "UPDATE downloaded_tracks SET file_path=? || SUBSTR(file_path, ?), updated_at=? WHERE file_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
            )
            counts["tracks"] = cursor.rowcount
            cursor = connection.execute(
                "UPDATE downloaded_tracks SET artwork_path=? || SUBSTR(artwork_path, ?), updated_at=? WHERE artwork_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
            )
            counts["artwork"] = cursor.rowcount
            cursor = connection.execute(
                "UPDATE jobs SET source_path=? || SUBSTR(source_path, ?), updated_at=? WHERE source_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
            )
            counts["jobs"] = cursor.rowcount
            for field in (
                "wav_path",
                "extended_path",
                "intro_preview_path",
                "outro_preview_path",
                "cue_sheet_path",
                "rekordbox_path",
            ):
                cursor = connection.execute(
                    f"UPDATE jobs SET {field}=? || SUBSTR({field}, ?), updated_at=? WHERE {field} LIKE ?",  # noqa: S608
                    (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
                )
                counts["job_paths"] += cursor.rowcount
            cursor = connection.execute(
                "UPDATE catalog_source_index SET source_path=? || SUBSTR(source_path, ?) WHERE source_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, old_prefix + "%"),
            )
            counts["sources"] = cursor.rowcount
            settings = {
                str(row["key"]): json.loads(row["value_json"])
                for row in connection.execute("SELECT key, value_json FROM web_settings")
            }
            settings["music_library_path"] = str(new_root)
            connection.execute(
                """INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                updated_at=excluded.updated_at""",
                ("music_library_path", str(new_root), _now()),
            )
            connection.execute("DELETE FROM web_settings")
            connection.executemany(
                "INSERT INTO web_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                [(key, json.dumps(value), _now()) for key, value in settings.items()],
            )
            connection.execute(
                """INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                updated_at=excluded.updated_at""",
                ("music_library_path", str(new_root), _now()),
            )
        return counts

    def upsert_downloaded_track(
        self,
        *,
        title: str,
        artist: str,
        file_path: Path,
        genre: str = "",
        genre_category: str = "Other",
        spotify_uri: str = "",
        youtube_id: str = "",
        youtube_url: str = "",
        artwork_url: str = "",
        artwork_path: str = "",
        duration_seconds: float | None = None,
        playlist_name: str = "Imported Singles",
    ) -> int:
        """Catalog a downloaded WAV without involving extended-edit jobs."""
        now = _now()
        resolved = str(file_path.resolve())
        resolved_artwork = str(Path(artwork_path).expanduser().resolve()) if artwork_path else ""
        fingerprint = audio_fingerprint(file_path) if file_path.is_file() else ""
        with self._lock, closing(self._connect()) as connection, connection:
            key = identity_key(artist, title)
            family_row = None
            identity_confidence = "new"
            identity_reason = "New recording family"
            if spotify_uri:
                family_row = connection.execute(
                    """SELECT recording_code FROM downloaded_tracks
                    WHERE spotify_uri=? AND recording_code!='' ORDER BY id LIMIT 1""",
                    (spotify_uri,),
                ).fetchone()
                if family_row:
                    identity_confidence = "high"
                    identity_reason = "Matched the same Spotify recording"
            if family_row is None and youtube_id:
                family_row = connection.execute(
                    """SELECT recording_code FROM downloaded_tracks
                    WHERE youtube_id=? AND recording_code!='' ORDER BY id LIMIT 1""",
                    (youtube_id,),
                ).fetchone()
                if family_row:
                    identity_confidence = "high"
                    identity_reason = "Matched the same source recording"
            if family_row is None and key != "|":
                family_row = connection.execute(
                    """SELECT recording_code FROM downloaded_tracks
                    WHERE identity_key=? AND recording_code!='' ORDER BY id LIMIT 1""",
                    (key,),
                ).fetchone()
                if family_row:
                    identity_confidence = "review"
                    identity_reason = "Matched normalized artist and title"
            if family_row:
                recording_code = str(family_row["recording_code"])
            else:
                recording_code = format_family_code(
                    self._next_recording_number(connection), genre_category
                )
            existing_versions = {
                str(row[0])
                for row in connection.execute(
                    "SELECT version_code FROM downloaded_tracks WHERE recording_code=?",
                    (recording_code,),
                )
            }
            version_code = next_version_code(version_kind(title), existing_versions)
            connection.execute(
                "DELETE FROM downloaded_track_exclusions WHERE file_path = ?",
                (resolved,),
            )
            connection.execute(
                """
                INSERT INTO downloaded_tracks (
                    title, artist, file_path, filename, genre, genre_category,
                    spotify_uri, youtube_id, youtube_url, artwork_url, artwork_path, duration_seconds,
                    imported_at, updated_at, recording_code, version_code, identity_key,
                    identity_confidence, identity_reason, audio_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    title=excluded.title, artist=excluded.artist,
                    genre=excluded.genre, genre_category=excluded.genre_category,
                    spotify_uri=CASE WHEN excluded.spotify_uri != '' THEN excluded.spotify_uri ELSE downloaded_tracks.spotify_uri END,
                    youtube_id=CASE WHEN excluded.youtube_id != '' THEN excluded.youtube_id ELSE downloaded_tracks.youtube_id END,
                    youtube_url=CASE WHEN excluded.youtube_url != '' THEN excluded.youtube_url ELSE downloaded_tracks.youtube_url END,
                    artwork_url=CASE WHEN excluded.artwork_url != '' THEN excluded.artwork_url ELSE downloaded_tracks.artwork_url END,
                    artwork_path=CASE WHEN excluded.artwork_path != '' THEN excluded.artwork_path ELSE downloaded_tracks.artwork_path END,
                    audio_fingerprint=CASE WHEN excluded.audio_fingerprint != '' THEN excluded.audio_fingerprint ELSE downloaded_tracks.audio_fingerprint END,
                    duration_seconds=COALESCE(excluded.duration_seconds, downloaded_tracks.duration_seconds),
                    updated_at=excluded.updated_at
                """,
                (
                    title,
                    artist,
                    resolved,
                    file_path.name,
                    genre,
                    genre_category or "Other",
                    spotify_uri,
                    youtube_id,
                    youtube_url,
                    artwork_url,
                    resolved_artwork,
                    duration_seconds,
                    now,
                    now,
                    recording_code,
                    version_code,
                    key,
                    identity_confidence,
                    identity_reason,
                    fingerprint,
                ),
            )
            row = connection.execute(
                "SELECT id FROM downloaded_tracks WHERE file_path = ?", (resolved,)
            ).fetchone()
            if row is None:
                raise RuntimeError("Downloaded track could not be cataloged")
            track_id = int(row["id"])
            connection.execute(
                """INSERT OR IGNORE INTO downloaded_track_playlists
                (track_id, playlist_name, added_at) VALUES (?, ?, ?)""",
                (track_id, playlist_name or "Imported Singles", now),
            )
            return track_id

    def list_downloaded_tracks(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT tracks.*,
                    GROUP_CONCAT(playlists.playlist_name, '||') AS playlists
                FROM downloaded_tracks AS tracks
                LEFT JOIN downloaded_track_playlists AS playlists
                    ON playlists.track_id = tracks.id
                GROUP BY tracks.id
                ORDER BY tracks.imported_at DESC, tracks.id DESC
                """
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [
                value for value in str(item.get("playlists") or "").split("||") if value
            ]
            results.append(item)
        return results

    def duplicate_candidates(self) -> list[dict[str, Any]]:
        """Return conservative same-version matches for explicit user review."""
        tracks = self.list_downloaded_tracks()
        groups: dict[str, list[dict[str, Any]]] = {}
        for track in tracks:
            groups.setdefault(str(track.get("recording_code") or ""), []).append(track)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for recording_code, family in groups.items():
            if not recording_code or len(family) < 2:
                continue
            for index, first in enumerate(family):
                for second in family[index + 1 :]:
                    first_kind = re.sub(r"\d+$", "", str(first.get("version_code") or "ORG"))
                    second_kind = re.sub(r"\d+$", "", str(second.get("version_code") or "ORG"))
                    if first_kind != second_kind:
                        continue
                    same_spotify = bool(first.get("spotify_uri")) and first[
                        "spotify_uri"
                    ] == second.get("spotify_uri")
                    same_youtube = bool(first.get("youtube_id")) and first[
                        "youtube_id"
                    ] == second.get("youtube_id")
                    first_duration = first.get("duration_seconds")
                    second_duration = second.get("duration_seconds")
                    close_duration = (
                        first_duration is not None
                        and second_duration is not None
                        and abs(float(first_duration) - float(second_duration)) <= 2
                    )
                    if not (same_spotify or same_youtube or close_duration):
                        continue
                    first_id, second_id = int(first["id"]), int(second["id"])
                    pair = (min(first_id, second_id), max(first_id, second_id))
                    seen.add(pair)
                    reason = (
                        "Same Spotify recording"
                        if same_spotify
                        else "Same source recording"
                        if same_youtube
                        else "Same artist/title version and duration"
                    )
                    candidates.append(
                        {
                            "recording_code": recording_code,
                            "reason": reason,
                            "confidence": "high" if same_spotify or same_youtube else "review",
                            "tracks": [first, second],
                        }
                    )
        fingerprints: dict[str, list[dict[str, Any]]] = {}
        for track in tracks:
            fingerprint = str(track.get("audio_fingerprint") or "")
            if fingerprint:
                fingerprints.setdefault(fingerprint, []).append(track)
        for matches in fingerprints.values():
            for index, first in enumerate(matches):
                for second in matches[index + 1 :]:
                    first_id, second_id = int(first["id"]), int(second["id"])
                    pair = (min(first_id, second_id), max(first_id, second_id))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    candidates.append(
                        {
                            "recording_code": str(first.get("recording_code") or ""),
                            "reason": "Exact audio fingerprint",
                            "confidence": "high",
                            "tracks": [first, second],
                        }
                    )
        return candidates

    def refresh_missing_audio_fingerprints(self) -> int:
        """Lazily fingerprint legacy files during an explicit integrity scan."""
        tracks = self.list_downloaded_tracks()
        updates = []
        for track in tracks:
            if track.get("audio_fingerprint"):
                continue
            path = Path(str(track.get("file_path") or ""))
            if not path.is_file():
                continue
            try:
                updates.append((audio_fingerprint(path), _now(), int(track["id"])))
            except OSError:
                continue
        if updates:
            with self._lock, closing(self._connect()) as connection, connection:
                connection.executemany(
                    "UPDATE downloaded_tracks SET audio_fingerprint=?, updated_at=? WHERE id=?",
                    updates,
                )
        return len(updates)

    def separate_recording(self, track_id: int) -> dict[str, Any]:
        """Move a false-positive match into its own permanent recording family."""
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)
            ).fetchone()
            if row is None:
                raise KeyError(track_id)
            recording_code = format_family_code(
                self._next_recording_number(connection), str(row["genre_category"] or "Other")
            )
            version_code = next_version_code(version_kind(str(row["title"])), set())
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?, version_code=?,
                identity_confidence='manual', identity_reason='Kept separate by user',
                updated_at=? WHERE id=?""",
                (recording_code, version_code, _now(), track_id),
            )
        return self.get_downloaded_track(track_id) or {}

    def recording_family(self, track_id: int) -> list[dict[str, Any]]:
        """Return every catalog entry intentionally linked to this recording."""
        track = self.get_downloaded_track(track_id)
        if not track:
            raise KeyError(track_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM downloaded_tracks WHERE recording_code=?
                ORDER BY CASE WHEN version_code='ORG' THEN 0 ELSE 1 END,
                version_code, title""",
                (track["recording_code"],),
            ).fetchall()
        return [dict(row) for row in rows]

    def track_id_for_identity(self, identity: str) -> int | None:
        """Resolve a visible AE recording/version ID to its catalog row."""
        match = re.fullmatch(r"([A-Z]{3}-\d+)(?:-([A-Z0-9]+))?", identity.strip().upper())
        if not match:
            return None
        recording_code, version_code = match.groups()
        with closing(self._connect()) as connection:
            if version_code:
                row = connection.execute(
                    "SELECT id FROM downloaded_tracks WHERE recording_code=? AND version_code=?",
                    (recording_code, version_code),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT id FROM downloaded_tracks WHERE recording_code=?
                    ORDER BY CASE WHEN version_code='ORG' THEN 0 ELSE 1 END, id LIMIT 1""",
                    (recording_code,),
                ).fetchone()
        return int(row[0]) if row else None

    def link_recording_version(
        self, track_id: int, target_track_id: int, kind: str
    ) -> dict[str, Any]:
        """Link a track to another track's family without merging files or history."""
        if track_id == target_track_id:
            raise ValueError("Choose a different track as the recording family")
        allowed = {"ORG", "RMX", "EXT", "RADIO", "LIVE", "INST", "ACAP", "REM"}
        kind = str(kind).upper()
        if kind not in allowed:
            raise ValueError("Unsupported recording relationship")
        with self._lock, closing(self._connect()) as connection, connection:
            track = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)
            ).fetchone()
            target = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (target_track_id,)
            ).fetchone()
            if track is None or target is None:
                raise KeyError("One or more tracks were not found")
            recording_code = str(target["recording_code"] or "")
            if not recording_code:
                raise ValueError("The target track does not have a recording identity")
            existing = {
                str(row[0])
                for row in connection.execute(
                    "SELECT version_code FROM downloaded_tracks WHERE recording_code=? AND id<>?",
                    (recording_code, track_id),
                ).fetchall()
            }
            version_code = next_version_code(kind, existing)
            target_id = f"{recording_code}-{target['version_code'] or 'ORG'}"
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?, version_code=?,
                identity_confidence='manual', identity_reason=?, updated_at=? WHERE id=?""",
                (
                    recording_code,
                    version_code,
                    f"Linked as {kind} version of {target_id} by user",
                    _now(),
                    track_id,
                ),
            )
        return self.get_downloaded_track(track_id) or {}

    def recording_family_suggestions(self, track_id: int, limit: int = 8) -> list[dict[str, Any]]:
        """Rank plausible recording families using metadata and duration evidence."""
        source = self.get_downloaded_track(track_id)
        if not source:
            raise KeyError(track_id)
        source_title = base_title(str(source.get("title") or source.get("filename") or ""))
        source_artist = normalize_identity_text(str(source.get("artist") or ""))
        source_duration = float(source.get("duration_seconds") or 0)
        candidates: list[dict[str, Any]] = []
        for candidate in self.list_downloaded_tracks():
            if candidate["id"] == track_id or candidate.get("recording_code") == source.get(
                "recording_code"
            ):
                continue
            candidate_title = base_title(
                str(candidate.get("title") or candidate.get("filename") or "")
            )
            title_score = (
                SequenceMatcher(None, source_title, candidate_title).ratio()
                if source_title and candidate_title
                else 0
            )
            candidate_artist = normalize_identity_text(str(candidate.get("artist") or ""))
            artist_score = (
                SequenceMatcher(None, source_artist, candidate_artist).ratio()
                if source_artist and candidate_artist
                else 0
            )
            duration = float(candidate.get("duration_seconds") or 0)
            duration_score = (
                max(0.0, 1.0 - abs(source_duration - duration) / 120.0)
                if source_duration and duration
                else 0.35
            )
            score = round(100 * (title_score * 0.62 + artist_score * 0.23 + duration_score * 0.15))
            exact_audio = bool(source.get("audio_fingerprint")) and source.get(
                "audio_fingerprint"
            ) == candidate.get("audio_fingerprint")
            if exact_audio:
                score = max(score, 98)
            if score < 38:
                continue
            reasons = []
            if exact_audio:
                reasons.append("matching audio fingerprint")
            if title_score >= 0.72:
                reasons.append("similar base title")
            if artist_score >= 0.72:
                reasons.append("matching artist")
            if source_duration and duration and abs(source_duration - duration) <= 45:
                reasons.append("similar duration")
            candidates.append(
                {"score": score, "reasons": reasons or ["metadata similarity"], "track": candidate}
            )
        candidates.sort(key=lambda item: (-item["score"], str(item["track"].get("title") or "")))
        return candidates[: max(1, min(limit, 20))]

    def merge_downloaded_tracks(self, survivor_id: int, duplicate_id: int) -> dict[str, Any]:
        """Merge catalog references while retaining both physical files."""
        if survivor_id == duplicate_id:
            raise ValueError("Choose two different tracks")
        with self._lock, closing(self._connect()) as connection, connection:
            survivor = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (survivor_id,)
            ).fetchone()
            duplicate = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (duplicate_id,)
            ).fetchone()
            if survivor is None or duplicate is None:
                raise KeyError("One or more tracks were not found")
            now = _now()
            connection.execute(
                """INSERT OR IGNORE INTO downloaded_track_playlists
                (track_id,playlist_name,added_at)
                SELECT ?,playlist_name,? FROM downloaded_track_playlists WHERE track_id=?""",
                (survivor_id, now, duplicate_id),
            )
            survivor_path = str(survivor["file_path"])
            duplicate_path = str(duplicate["file_path"])
            connection.execute(
                """UPDATE jobs SET source_path=?, source_name=?,
                wav_path=CASE WHEN wav_path=? THEN ? ELSE wav_path END, updated_at=?
                WHERE source_path=?""",
                (
                    survivor_path,
                    survivor["filename"],
                    duplicate_path,
                    survivor_path,
                    now,
                    duplicate_path,
                ),
            )
            connection.execute(
                "UPDATE library_search_index SET downloaded_id=? WHERE downloaded_id=?",
                (survivor_id, duplicate_id),
            )
            existing_key = connection.execute(
                "SELECT 1 FROM key_verifications WHERE source_name=? COLLATE NOCASE",
                (survivor["filename"],),
            ).fetchone()
            if existing_key:
                connection.execute(
                    "DELETE FROM key_verifications WHERE source_name=? COLLATE NOCASE",
                    (duplicate["filename"],),
                )
            else:
                connection.execute(
                    "UPDATE key_verifications SET source_name=? WHERE source_name=? COLLATE NOCASE",
                    (survivor["filename"], duplicate["filename"]),
                )
            connection.execute(
                "UPDATE track_feedback SET source_name=? WHERE source_name=? COLLATE NOCASE",
                (survivor["filename"], duplicate["filename"]),
            )
            connection.execute(
                """UPDATE downloaded_tracks SET
                spotify_uri=CASE WHEN spotify_uri='' THEN ? ELSE spotify_uri END,
                youtube_id=CASE WHEN youtube_id='' THEN ? ELSE youtube_id END,
                youtube_url=CASE WHEN youtube_url='' THEN ? ELSE youtube_url END,
                artwork_url=CASE WHEN artwork_url='' THEN ? ELSE artwork_url END,
                artwork_path=CASE WHEN artwork_path='' THEN ? ELSE artwork_path END,
                duration_seconds=COALESCE(duration_seconds,?),
                identity_confidence='manual', identity_reason='Confirmed duplicate merge',
                updated_at=? WHERE id=?""",
                (
                    duplicate["spotify_uri"],
                    duplicate["youtube_id"],
                    duplicate["youtube_url"],
                    duplicate["artwork_url"],
                    duplicate["artwork_path"],
                    duplicate["duration_seconds"],
                    now,
                    survivor_id,
                ),
            )
            connection.execute(
                "DELETE FROM downloaded_track_playlists WHERE track_id=?", (duplicate_id,)
            )
            connection.execute(
                """INSERT OR REPLACE INTO downloaded_track_exclusions
                (file_path,excluded_at) VALUES (?,?)""",
                (duplicate_path, now),
            )
            connection.execute("DELETE FROM downloaded_tracks WHERE id=?", (duplicate_id,))
        merged = self.get_downloaded_track(survivor_id) or {}
        merged["retained_file"] = duplicate_path
        return merged

    def list_downloaded_tracks_with_jobs(self) -> list[dict[str, Any]]:
        """Return the catalog with latest job state resolved inside SQLite."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                WITH latest_any AS (
                    SELECT source_path, MAX(id) AS job_id
                    FROM jobs GROUP BY source_path
                ), latest_complete AS (
                    SELECT source_path, MAX(id) AS job_id
                    FROM jobs WHERE status = 'complete' GROUP BY source_path
                )
                SELECT tracks.*,
                    GROUP_CONCAT(playlists.playlist_name, '||') AS playlists,
                    latest_job.status AS analysis_status,
                    latest_job.id AS library_job_id,
                    completed_job.id AS completed_library_job_id
                FROM downloaded_tracks AS tracks
                LEFT JOIN downloaded_track_playlists AS playlists
                    ON playlists.track_id = tracks.id
                LEFT JOIN latest_any
                    ON latest_any.source_path = tracks.file_path
                LEFT JOIN jobs AS latest_job
                    ON latest_job.id = latest_any.job_id
                LEFT JOIN latest_complete
                    ON latest_complete.source_path = tracks.file_path
                LEFT JOIN jobs AS completed_job
                    ON completed_job.id = latest_complete.job_id
                GROUP BY tracks.id
                ORDER BY tracks.imported_at DESC, tracks.id DESC
                """
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [
                value for value in str(item.get("playlists") or "").split("||") if value
            ]
            results.append(item)
        return results

    def page_downloaded_tracks(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        genre: str = "all",
        playlist: str = "all",
        detailed_genre: str = "all",
        analysis: str = "all",
        artwork: str = "all",
        quality: str = "all",
        sort: str = "newest",
    ) -> tuple[list[dict[str, Any]], int]:
        """Filter, sort, and page the downloaded catalog entirely in SQLite."""
        conditions: list[str] = []
        parameters: list[Any] = []
        if search.strip():
            value = f"%{search.strip().casefold()}%"
            conditions.append(
                "(LOWER(tracks.title) LIKE ? OR LOWER(tracks.artist) LIKE ? "
                "OR LOWER(tracks.genre) LIKE ? OR LOWER(tracks.genre_category) LIKE ? "
                "OR LOWER(tracks.recording_code || '-' || tracks.version_code) LIKE ? "
                "OR EXISTS (SELECT 1 FROM downloaded_track_playlists search_playlist "
                "WHERE search_playlist.track_id = tracks.id "
                "AND LOWER(search_playlist.playlist_name) LIKE ?))"
            )
            parameters.extend([value] * 6)
        missing_title = "TRIM(COALESCE(tracks.title, '')) = '' OR LOWER(TRIM(tracks.title)) IN ('unknown title','untitled')"
        missing_artist = "TRIM(COALESCE(tracks.artist, '')) = '' OR LOWER(TRIM(tracks.artist)) IN ('unknown artist','unknown','unavailable')"
        missing_genre = "TRIM(COALESCE(tracks.genre, '')) = ''"
        missing_artwork = "TRIM(COALESCE(tracks.artwork_path, '')) = ''"
        unmapped_genre = (
            "TRIM(COALESCE(tracks.genre, '')) != '' AND tracks.genre_category = 'Other'"
        )
        broad_genre = (
            "(tracks.genre_category LIKE '% / General' OR tracks.genre_category LIKE '% / Other')"
        )
        if genre != "all":
            aliases = {
                "Electronic / General": "Electronic / Electronic / Electronic",
                "Latin / General": "Latin / Other",
            }
            stored_genre = aliases.get(genre, genre)
            conditions.append(
                "(tracks.genre_category = ? OR tracks.genre_category LIKE ? ESCAPE '\\')"
            )
            escaped = stored_genre.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend((stored_genre, f"{escaped} / %"))
        if detailed_genre != "all":
            # Source genres are stored as comma-separated tags. Pad both sides
            # with commas so selecting "house" cannot also match "deep house".
            normalized_tag = detailed_genre.strip().casefold()
            conditions.append(
                "(',' || REPLACE(REPLACE(LOWER(COALESCE(tracks.genre, '')), ', ', ','), ' ,', ',') || ',') LIKE ?"
            )
            parameters.append(f"%,{normalized_tag},%")
        if playlist != "all":
            conditions.append(
                "EXISTS (SELECT 1 FROM downloaded_track_playlists selected_playlist "
                "WHERE selected_playlist.track_id = tracks.id "
                "AND selected_playlist.playlist_name = ?)"
            )
            parameters.append(playlist)
        status = "COALESCE(latest_job.status, 'not_analyzed')"
        analysis_conditions = {
            "needs": f"{status} IN ('not_analyzed','failed','canceled')",
            "complete": f"{status} = 'complete'",
            "active": f"{status} IN ('queued','processing')",
            "failed": f"{status} IN ('failed','canceled')",
            "attention": f"({missing_title} OR {missing_artist} OR {missing_genre} OR {missing_artwork} OR {unmapped_genre} OR {broad_genre})",
            "missing_title": f"({missing_title})",
            "missing_artist": f"({missing_artist})",
            "missing_genre": f"({missing_genre})",
            "missing_artwork": f"({missing_artwork})",
            "unmapped_genre": f"({unmapped_genre})",
            "broad_genre": f"({broad_genre})",
        }
        if analysis in analysis_conditions:
            conditions.append(analysis_conditions[analysis])
        if artwork == "missing":
            conditions.append("TRIM(COALESCE(tracks.artwork_path, '')) = ''")
        elif artwork == "available":
            conditions.append("TRIM(COALESCE(tracks.artwork_path, '')) != ''")
        quality_conditions = {
            "excellent": "tracks.audio_quality_label = 'excellent'",
            "good": "tracks.audio_quality_label = 'good'",
            "review": "tracks.audio_quality_label = 'review'",
            "poor": "tracks.audio_quality_label = 'poor'",
            "below-target": "tracks.audio_quality_label IN ('review','poor')",
            "unanalyzed": "tracks.audio_quality_score IS NULL",
        }
        if quality in quality_conditions:
            conditions.append(quality_conditions[quality])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order = {
            "newest": "tracks.imported_at DESC, tracks.id DESC",
            "title": "tracks.title COLLATE NOCASE, tracks.id",
            "artist": "tracks.artist COLLATE NOCASE, tracks.title COLLATE NOCASE",
            "genre": "tracks.genre_category COLLATE NOCASE, tracks.artist COLLATE NOCASE",
        }.get(sort, "tracks.imported_at DESC, tracks.id DESC")
        ctes = """WITH latest_any AS (
            SELECT source_path, MAX(id) AS job_id FROM jobs GROUP BY source_path
        ), latest_complete AS (
            SELECT source_path, MAX(id) AS job_id FROM jobs
            WHERE status = 'complete' GROUP BY source_path
        )"""
        joins = """FROM downloaded_tracks AS tracks
            LEFT JOIN latest_any ON latest_any.source_path = tracks.file_path
            LEFT JOIN jobs AS latest_job ON latest_job.id = latest_any.job_id
            LEFT JOIN latest_complete ON latest_complete.source_path = tracks.file_path
            LEFT JOIN jobs AS completed_job ON completed_job.id = latest_complete.job_id"""
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"{ctes} SELECT COUNT(*) {joins} {where}", parameters
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""{ctes} SELECT tracks.id, tracks.title, tracks.artist,
                tracks.filename, tracks.genre, tracks.genre_category,
                tracks.recording_code, tracks.version_code,
                tracks.identity_confidence, tracks.identity_reason,
                tracks.audio_quality_score, tracks.audio_quality_label,
                tracks.audio_quality_json, tracks.audio_quality_analyzed_at,
                tracks.artwork_url, tracks.artwork_path, tracks.file_path,
                tracks.duration_seconds, tracks.imported_at,
                (SELECT GROUP_CONCAT(p.playlist_name, '||')
                 FROM downloaded_track_playlists p WHERE p.track_id = tracks.id) AS playlists,
                latest_job.status AS analysis_status,
                latest_job.id AS library_job_id,
                completed_job.id AS completed_library_job_id
                {joins} {where} ORDER BY {order} LIMIT ? OFFSET ?""",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [
                value for value in str(item.get("playlists") or "").split("||") if value
            ]
            results.append(item)
        return results, total

    def update_audio_quality(self, track_id: int, result: dict[str, Any]) -> None:
        """Persist one quality assessment without changing music metadata."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE downloaded_tracks SET audio_quality_score=?,
                audio_quality_label=?,audio_quality_json=?,audio_quality_analyzed_at=?,
                updated_at=? WHERE id=?""",
                (
                    float(result["score"]),
                    str(result["label"]),
                    json.dumps(result, sort_keys=True),
                    now,
                    now,
                    track_id,
                ),
            )

    def audio_quality_summary(self) -> dict[str, Any]:
        """Return lightweight library-wide quality statistics for Settings."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS total,
                COUNT(audio_quality_score) AS analyzed,
                AVG(audio_quality_score) AS average_score,
                SUM(CASE WHEN audio_quality_label='excellent' THEN 1 ELSE 0 END) AS excellent,
                SUM(CASE WHEN audio_quality_label='good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN audio_quality_label='review' THEN 1 ELSE 0 END) AS review,
                SUM(CASE WHEN audio_quality_label='poor' THEN 1 ELSE 0 END) AS poor
                FROM downloaded_tracks"""
            ).fetchone()
        return {key: (0 if value is None else value) for key, value in dict(row).items()}

    def downloaded_catalog_facets(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM downloaded_tracks").fetchone()[0])
            genres = dict(
                connection.execute(
                    "SELECT genre_category, COUNT(*) FROM downloaded_tracks GROUP BY genre_category"
                ).fetchall()
            )
            playlists = dict(
                connection.execute(
                    "SELECT playlist_name, COUNT(*) FROM downloaded_track_playlists GROUP BY playlist_name"
                ).fetchall()
            )
            detailed_genres: dict[str, int] = {}
            detailed_genres_by_category: dict[str, dict[str, int]] = {}
            canonical_tags: dict[str, str] = {}
            for category, raw_genres in connection.execute(
                "SELECT genre_category, genre FROM downloaded_tracks WHERE TRIM(COALESCE(genre, '')) != ''"
            ).fetchall():
                category_genres = detailed_genres_by_category.setdefault(
                    str(category or "Other"), {}
                )
                seen: set[str] = set()
                for raw_tag in str(raw_genres or "").split(","):
                    tag = raw_tag.strip()
                    key = tag.casefold()
                    if not tag or key in seen:
                        continue
                    seen.add(key)
                    display = canonical_tags.setdefault(key, tag)
                    detailed_genres[display] = detailed_genres.get(display, 0) + 1
                    category_genres[display] = category_genres.get(display, 0) + 1
            issue_conditions = {
                "missing_title": "TRIM(COALESCE(title, '')) = '' OR LOWER(TRIM(title)) IN ('unknown title','untitled')",
                "missing_artist": "TRIM(COALESCE(artist, '')) = '' OR LOWER(TRIM(artist)) IN ('unknown artist','unknown','unavailable')",
                "missing_genre": "TRIM(COALESCE(genre, '')) = ''",
                "missing_artwork": "TRIM(COALESCE(artwork_path, '')) = ''",
                "unmapped_genre": "TRIM(COALESCE(genre, '')) != '' AND genre_category = 'Other'",
                "broad_genre": "genre_category LIKE '% / General' OR genre_category LIKE '% / Other'",
            }
            review_states = {
                name: int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM downloaded_tracks WHERE {condition}"
                    ).fetchone()[0]
                )
                for name, condition in issue_conditions.items()
            }
            review_states["needs_attention"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM downloaded_tracks WHERE "
                    + " OR ".join(f"({condition})" for condition in issue_conditions.values())
                ).fetchone()[0]
            )
        return {
            "total": total,
            "genres": genres,
            "detailed_genres": detailed_genres,
            "detailed_genres_by_category": detailed_genres_by_category,
            "playlists": playlists,
            "review_states": review_states,
        }

    def get_downloaded_track(self, track_id: int) -> dict[str, Any] | None:
        """Fetch one catalog entry without materializing the entire library."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT tracks.*,
                (SELECT GROUP_CONCAT(p.playlist_name, '||')
                 FROM downloaded_track_playlists p WHERE p.track_id = tracks.id)
                 AS playlists
                FROM downloaded_tracks tracks WHERE tracks.id = ?""",
                (track_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["playlists"] = [
            value for value in str(item.get("playlists") or "").split("||") if value
        ]
        return item

    def update_downloaded_track_artwork(
        self, track_id: int, *, artwork_url: str, artwork_path: str
    ) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE downloaded_tracks SET artwork_url=?, artwork_path=?, updated_at=? "
                "WHERE id=?",
                (artwork_url, artwork_path, _now(), track_id),
            )

    def update_downloaded_track_key_analysis(
        self,
        track_id: int,
        *,
        detected_key: str,
        confidence: float,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Save a key-only result without replacing the track's other analysis."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE downloaded_tracks SET detected_key=?, key_confidence=?,
                key_candidates_json=?, key_analyzed_at=?, updated_at=? WHERE id=?""",
                (
                    detected_key,
                    confidence,
                    json.dumps(candidates, separators=(",", ":")),
                    now,
                    now,
                    track_id,
                ),
            )
        return self.get_downloaded_track(track_id) or {}

    def record_import_failure(
        self,
        *,
        playlist_name: str,
        title: str,
        artist: str = "",
        spotify_uri: str = "",
        youtube_url: str = "",
        error: str,
    ) -> None:
        """Persist the latest failure for a track without duplicating retries."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO import_failures (
                    playlist_name, title, artist, spotify_uri, youtube_url,
                    error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(playlist_name, title, artist) DO UPDATE SET
                    spotify_uri=excluded.spotify_uri,
                    youtube_url=excluded.youtube_url,
                    error=excluded.error,
                    attempts=import_failures.attempts + 1,
                    resolved=0,
                    updated_at=excluded.updated_at""",
                (playlist_name, title, artist, spotify_uri, youtube_url, error, now, now),
            )

    def resolve_import_failure(self, *, playlist_name: str, title: str, artist: str = "") -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE import_failures SET resolved=1, updated_at=?
                WHERE playlist_name=? AND title=? AND artist=?""",
                (_now(), playlist_name, title, artist),
            )

    def list_import_failures(self, *, include_resolved: bool = False) -> list[dict[str, Any]]:
        where = "" if include_resolved else "WHERE resolved=0"
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT * FROM import_failures {where} ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_downloaded_track_by_path(self, file_path: Path) -> dict[str, Any] | None:
        resolved = str(file_path.resolve())
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT tracks.*,
                GROUP_CONCAT(playlists.playlist_name, '||') AS playlists
                FROM downloaded_tracks AS tracks
                LEFT JOIN downloaded_track_playlists AS playlists
                    ON playlists.track_id = tracks.id
                WHERE tracks.file_path = ? GROUP BY tracks.id""",
                (resolved,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["playlists"] = [
            value for value in str(item.get("playlists") or "").split("||") if value
        ]
        return item

    def relocate_downloaded_tracks(self, moves: list[tuple[int, Path, Path, str]]) -> None:
        """Update catalog and job paths after WAVs move between genre folders."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            for track_id, old_path, new_path, genre_category in moves:
                old_value = str(old_path)
                old_resolved = str(old_path.resolve())
                new_value = str(new_path.resolve())
                connection.execute(
                    """UPDATE downloaded_tracks
                    SET file_path = ?, filename = ?, genre_category = ?, updated_at = ?
                    WHERE id = ?""",
                    (new_value, new_path.name, genre_category, now, track_id),
                )
                connection.execute(
                    """UPDATE jobs SET source_path = ?,
                    wav_path = CASE WHEN wav_path IN (?, ?) THEN ? ELSE wav_path END,
                    updated_at = ? WHERE source_path IN (?, ?)""",
                    (
                        new_value,
                        old_value,
                        old_resolved,
                        new_value,
                        now,
                        old_value,
                        old_resolved,
                    ),
                )

    def update_downloaded_track_metadata(
        self,
        *,
        track_id: int,
        old_path: Path,
        new_path: Path,
        title: str,
        artist: str,
        genre: str,
        genre_category: str,
        playlist_name: str,
    ) -> None:
        """Keep catalog identity, playlist membership, and linked jobs synchronized."""
        now = _now()
        old_value = str(old_path)
        old_resolved = str(old_path.resolve())
        new_value = str(new_path.resolve())
        with self._lock, closing(self._connect()) as connection, connection:
            current = connection.execute(
                "SELECT recording_code,version_code FROM downloaded_tracks WHERE id=?",
                (track_id,),
            ).fetchone()
            if current is None:
                raise KeyError(track_id)
            wanted_kind = version_kind(title)
            current_kind = re.sub(r"\d+$", "", str(current["version_code"] or "ORG"))
            version_code = str(current["version_code"] or "ORG")
            if wanted_kind != current_kind:
                existing_versions = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT version_code FROM downloaded_tracks "
                        "WHERE recording_code=? AND id!=?",
                        (current["recording_code"], track_id),
                    )
                }
                version_code = next_version_code(wanted_kind, existing_versions)
            cursor = connection.execute(
                """UPDATE downloaded_tracks SET title=?, artist=?, file_path=?, filename=?,
                genre=?, genre_category=?, identity_key=?, version_code=?,
                identity_confidence='manual', identity_reason='Metadata confirmed by user',
                updated_at=? WHERE id=?""",
                (
                    title,
                    artist,
                    new_value,
                    new_path.name,
                    genre,
                    genre_category,
                    identity_key(artist, title),
                    version_code,
                    now,
                    track_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(track_id)
            connection.execute(
                "DELETE FROM downloaded_track_playlists WHERE track_id=?", (track_id,)
            )
            connection.execute(
                """INSERT INTO downloaded_track_playlists
                (track_id, playlist_name, added_at) VALUES (?, ?, ?)""",
                (track_id, playlist_name, now),
            )
            connection.execute(
                """UPDATE jobs SET source_name=?, source_path=?,
                wav_path=CASE WHEN wav_path IN (?,?) THEN ? ELSE wav_path END,
                updated_at=? WHERE source_path IN (?,?)""",
                (
                    new_path.name,
                    new_value,
                    old_value,
                    old_resolved,
                    new_value,
                    now,
                    old_value,
                    old_resolved,
                ),
            )

    def delete_downloaded_track(self, track_id: int) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT file_path FROM downloaded_tracks WHERE id = ?", (track_id,)
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "INSERT OR REPLACE INTO downloaded_track_exclusions "
                "(file_path, excluded_at) VALUES (?, ?)",
                (row["file_path"], _now()),
            )
            connection.execute(
                "DELETE FROM downloaded_track_playlists WHERE track_id = ?", (track_id,)
            )
            cursor = connection.execute("DELETE FROM downloaded_tracks WHERE id = ?", (track_id,))
        return cursor.rowcount > 0

    def downloaded_track_is_excluded(self, file_path: Path) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM downloaded_track_exclusions WHERE file_path = ?",
                (str(file_path.resolve()),),
            ).fetchone()
        return row is not None

    def reset_track_data(self) -> None:
        """Remove track-owned records while retaining preferences and schema."""
        with self._lock, closing(self._connect()) as connection, connection:
            for table in (
                "candidate_feedback",
                "track_feedback",
                "key_verifications",
                "downloaded_track_playlists",
                "downloaded_tracks",
                "downloaded_track_exclusions",
                "jobs",
            ):
                connection.execute(f"DELETE FROM {table}")  # noqa: S608


class JobRepository(SQLiteApplicationStore):
    """Compatibility aggregate for the six focused repository interfaces.

    Existing integrations can continue calling historical methods while new
    code selects ``track_catalog``, ``jobs_and_queues``, ``settings_system``,
    ``recording_families``, ``feedback_key_verification``, or
    ``backups_relocation`` explicitly.
    """
