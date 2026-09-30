"""Shared structural contract for repository domain mixins."""

from __future__ import annotations

import sqlite3
from typing import Any


class RepositoryMixinBase:
    _lock: Any

    def _connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    @staticmethod
    def _next_recording_number(connection: sqlite3.Connection) -> int:
        raise NotImplementedError
