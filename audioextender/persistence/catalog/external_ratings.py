"""Durable external preference evidence attached to catalog tracks."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from audioextender.persistence.base import RepositoryMixinBase


class ExternalTrackRatingRepositoryMixin(RepositoryMixinBase):
    def external_track_ratings(self, source: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT ratings.*, tracks.title, tracks.artist, tracks.recording_code,
            tracks.version_code FROM external_track_ratings ratings
            JOIN downloaded_tracks tracks ON tracks.id=ratings.track_id"""
        parameters: tuple[Any, ...] = ()
        if source:
            query += " WHERE ratings.source=?"
            parameters = (source,)
        query += " ORDER BY ratings.synced_at DESC, tracks.artist COLLATE NOCASE, tracks.title COLLATE NOCASE"
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(query, parameters).fetchall()]

    def apply_external_track_ratings(self, ratings: list[dict[str, Any]]) -> int:
        if not ratings:
            return 0
        with self._lock, closing(self._connect()) as connection, connection:
            changed = 0
            for rating in ratings:
                current = connection.execute(
                    "SELECT rating,source_track_id,match_method,confidence,source_location "
                    "FROM external_track_ratings WHERE track_id=? AND source=?",
                    (int(rating["track_id"]), str(rating["source"])),
                ).fetchone()
                values = (
                    int(rating["rating"]),
                    str(rating.get("source_track_id") or ""),
                    str(rating["match_method"]),
                    float(rating["confidence"]),
                    str(rating.get("source_location") or ""),
                )
                if current is not None and tuple(current) == values:
                    continue
                connection.execute(
                    """INSERT INTO external_track_ratings
                    (track_id,source,source_track_id,rating,match_method,confidence,source_location,synced_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(track_id,source) DO UPDATE SET
                    source_track_id=excluded.source_track_id,rating=excluded.rating,
                    match_method=excluded.match_method,confidence=excluded.confidence,
                    source_location=excluded.source_location,synced_at=excluded.synced_at""",
                    (
                        int(rating["track_id"]),
                        str(rating["source"]),
                        *values[1:2],
                        values[0],
                        *values[2:],
                        str(rating["synced_at"]),
                    ),
                )
                changed += 1
        return changed

    def clear_external_track_ratings(self, source: str) -> int:
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM external_track_ratings WHERE source=?", (source,))
            return int(cursor.rowcount)
