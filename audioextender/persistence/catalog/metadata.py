from __future__ import annotations

import re
from contextlib import closing
from pathlib import Path
from typing import Any

from audioextender.library.recording_identity import (
    identity_key,
    next_version_code,
    version_kind,
)
from audioextender.persistence.base import RepositoryMixinBase
from audioextender.persistence.catalog.shared import catalog_now as _now


class TrackMetadataStateRepositoryMixin(RepositoryMixinBase):
    def get_downloaded_track(self, track_id: int) -> dict[str, Any] | None:
        """Fetch one catalog entry without materializing the entire library."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT tracks.*,
                    (SELECT GROUP_CONCAT(p.playlist_name, '||')
                     FROM downloaded_track_playlists p WHERE p.track_id = tracks.id)
                     AS playlists,
                    (SELECT json_group_array(json_object(
                        'category', descriptors.category, 'value', descriptors.value,
                        'provenance', descriptors.provenance,
                        'confidence', descriptors.confidence,
                        'updated_at', descriptors.updated_at))
                     FROM downloaded_track_descriptors descriptors
                     WHERE descriptors.track_id=tracks.id) AS descriptors_json
                    FROM downloaded_tracks tracks WHERE tracks.id = ?""",
                (track_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["playlists"] = [value for value in str(item.get("playlists") or "").split("||") if value]
        return item

    def update_downloaded_track_artwork(self, track_id: int, *, artwork_url: str, artwork_path: str) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE downloaded_tracks SET artwork_url=?, artwork_path=?, updated_at=? WHERE id=?",
                (artwork_url, artwork_path, _now(), track_id),
            )

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
        item["playlists"] = [value for value in str(item.get("playlists") or "").split("||") if value]
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
                        "SELECT version_code FROM downloaded_tracks WHERE recording_code=? AND id!=?",
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
            connection.execute("DELETE FROM downloaded_track_playlists WHERE track_id=?", (track_id,))
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
            row = connection.execute("SELECT file_path FROM downloaded_tracks WHERE id = ?", (track_id,)).fetchone()
            if row is None:
                return False
            connection.execute(
                "INSERT OR REPLACE INTO downloaded_track_exclusions (file_path, excluded_at) VALUES (?, ?)",
                (row["file_path"], _now()),
            )
            connection.execute("DELETE FROM downloaded_track_playlists WHERE track_id = ?", (track_id,))
            connection.execute("DELETE FROM downloaded_track_descriptors WHERE track_id = ?", (track_id,))
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
