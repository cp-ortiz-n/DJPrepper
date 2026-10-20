"""Shared structural contract for repository domain mixins."""

from __future__ import annotations

import sqlite3
from typing import Any


class RepositoryMixinBase:
    """Methods supplied by the concrete facade and shared across mixins."""

    _lock: Any

    def _connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    @staticmethod
    def _next_recording_number(connection: sqlite3.Connection) -> int:
        raise NotImplementedError

    def get_downloaded_track(self, track_id: int) -> dict[str, Any] | None:
        """Return one catalog row through the composed catalog facade."""
        raise NotImplementedError

    def list_downloaded_tracks(self) -> list[dict[str, Any]]:
        """Return catalog rows through the composed catalog facade."""
        raise NotImplementedError
