"""Small SQLite repository for local web processing jobs."""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from audioextender.persistence.catalog import TrackCatalogRepositoryMixin
from audioextender.persistence.jobs.feedback import FeedbackRepositoryMixin
from audioextender.persistence.jobs.library_analysis import LibraryAnalysisRepositoryMixin
from audioextender.persistence.jobs.queue import JobQueueRepositoryMixin
from audioextender.persistence.migrations.recording_identities import migrate_recording_identities
from audioextender.persistence.migrations.schema import RepositorySchemaInitializer
from audioextender.persistence.system.state import SystemStateRepositoryMixin


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
        migrate_recording_identities(connection, self._next_recording_number)
