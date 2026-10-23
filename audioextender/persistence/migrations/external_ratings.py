"""Schema capability for source-scoped external track-rating evidence."""

from __future__ import annotations

import sqlite3


def initialize_external_track_ratings(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS external_track_ratings (
        track_id INTEGER NOT NULL, source TEXT NOT NULL, source_track_id TEXT NOT NULL DEFAULT '',
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        match_method TEXT NOT NULL, confidence REAL NOT NULL,
        source_location TEXT NOT NULL DEFAULT '', synced_at TEXT NOT NULL,
        PRIMARY KEY(track_id, source),
        FOREIGN KEY(track_id) REFERENCES downloaded_tracks(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_external_track_ratings_source
        ON external_track_ratings(source, rating DESC, track_id);"""
    )
