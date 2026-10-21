from __future__ import annotations

import re
from contextlib import closing
from pathlib import Path
from typing import Any

from audioextender.library.recording_identity import (
    audio_fingerprint,
)
from audioextender.persistence.base import RepositoryMixinBase
from audioextender.persistence.catalog.identity_assignment import assignment_for_upsert
from audioextender.persistence.catalog.shared import catalog_now as _now


class TrackCoreRepositoryMixin(RepositoryMixinBase):
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
            assignment = assignment_for_upsert(
                connection,
                title=title,
                artist=artist,
                resolved_path=resolved,
                genre_category=genre_category,
                spotify_uri=spotify_uri,
                youtube_id=youtube_id,
                next_recording_number=self._next_recording_number(connection),
            )
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
                        spotify_uri=CASE WHEN excluded.spotify_uri != ''
                            THEN excluded.spotify_uri ELSE downloaded_tracks.spotify_uri END,
                        youtube_id=CASE WHEN excluded.youtube_id != ''
                            THEN excluded.youtube_id ELSE downloaded_tracks.youtube_id END,
                        youtube_url=CASE WHEN excluded.youtube_url != ''
                            THEN excluded.youtube_url ELSE downloaded_tracks.youtube_url END,
                        artwork_url=CASE WHEN excluded.artwork_url != ''
                            THEN excluded.artwork_url ELSE downloaded_tracks.artwork_url END,
                        artwork_path=CASE WHEN excluded.artwork_path != ''
                            THEN excluded.artwork_path ELSE downloaded_tracks.artwork_path END,
                        audio_fingerprint=CASE WHEN excluded.audio_fingerprint != ''
                            THEN excluded.audio_fingerprint ELSE downloaded_tracks.audio_fingerprint END,
                        duration_seconds=COALESCE(excluded.duration_seconds, downloaded_tracks.duration_seconds),
                        recording_code=excluded.recording_code,
                        version_code=excluded.version_code,
                        identity_key=excluded.identity_key,
                        identity_confidence=excluded.identity_confidence,
                        identity_reason=excluded.identity_reason,
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
                    assignment.recording_code,
                    assignment.version_code,
                    assignment.key,
                    assignment.confidence,
                    assignment.reason,
                    fingerprint,
                ),
            )
            row = connection.execute("SELECT id FROM downloaded_tracks WHERE file_path = ?", (resolved,)).fetchone()
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
            item["playlists"] = [value for value in str(item.get("playlists") or "").split("||") if value]
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
                    same_spotify = bool(first.get("spotify_uri")) and first["spotify_uri"] == second.get("spotify_uri")
                    same_youtube = bool(first.get("youtube_id")) and first["youtube_id"] == second.get("youtube_id")
                    durations = (first.get("duration_seconds"), second.get("duration_seconds"))
                    close_duration = (
                        durations[0] is not None
                        and durations[1] is not None
                        and abs(float(durations[0]) - float(durations[1])) <= 2
                    )
                    if not (same_spotify or same_youtube or close_duration):
                        continue
                    pair = (
                        min(int(first["id"]), int(second["id"])),
                        max(int(first["id"]), int(second["id"])),
                    )
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
                    pair = (
                        min(int(first["id"]), int(second["id"])),
                        max(int(first["id"]), int(second["id"])),
                    )
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
