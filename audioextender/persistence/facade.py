"""Small SQLite repository for local web processing jobs."""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from audioextender.library.recording_identity import (
    format_family_code,
    identity_key,
    next_version_code,
    version_kind,
)
from audioextender.persistence.catalog import TrackCatalogRepositoryMixin
from audioextender.persistence.jobs.feedback import FeedbackRepositoryMixin
from audioextender.persistence.jobs.library_analysis import LibraryAnalysisRepositoryMixin
from audioextender.persistence.jobs.queue import JobQueueRepositoryMixin
from audioextender.persistence.migrations.schema import RepositorySchemaInitializer
from audioextender.persistence.system.state import SystemStateRepositoryMixin


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
            RepositorySchemaInitializer(self._ensure_recording_identities).initialize(connection)

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
