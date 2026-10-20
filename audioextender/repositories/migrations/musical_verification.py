"""Schema ownership for durable, user-verified musical corrections."""

from __future__ import annotations

import sqlite3


def initialize_musical_verifications(connection: sqlite3.Connection) -> None:
    """Create the verification stores without coupling them to feedback tables."""
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS key_verifications (
        source_name TEXT PRIMARY KEY COLLATE NOCASE, verified_key TEXT NOT NULL,
        detected_key TEXT NOT NULL DEFAULT '', candidates_json TEXT NOT NULL DEFAULT '[]',
        notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bpm_verifications (
        source_name TEXT PRIMARY KEY COLLATE NOCASE, verified_bpm REAL NOT NULL,
        detected_bpm REAL NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"""
    )
