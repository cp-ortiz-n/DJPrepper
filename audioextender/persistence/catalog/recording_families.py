from __future__ import annotations

import re
from contextlib import closing
from difflib import SequenceMatcher
from typing import Any

from audioextender.library.recording_identity import (
    base_title,
    format_family_code,
    next_version_code,
    normalize_identity_text,
    version_kind,
)
from audioextender.persistence.base import RepositoryMixinBase
from audioextender.persistence.catalog.shared import catalog_now as _now


class RecordingFamilyRepositoryMixin(RepositoryMixinBase):
    def separate_recording(self, track_id: int) -> dict[str, Any]:
        """Move a false-positive match into its own permanent recording family."""
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)).fetchone()
            if row is None:
                raise KeyError(track_id)
            recording_code = format_family_code(
                self._next_recording_number(connection), str(row["genre_category"] or "Other")
            )
            version_code = next_version_code(version_kind(str(row["title"])), set())
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?, version_code=?,
                    identity_confidence='manual', identity_reason='Kept separate by user',
                    identity_inference_locked=1, updated_at=? WHERE id=?""",
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

    def link_recording_version(self, track_id: int, target_track_id: int, kind: str) -> dict[str, Any]:
        """Link a track to another track's family without merging files or history."""
        if track_id == target_track_id:
            raise ValueError("Choose a different track as the recording family")
        allowed = {"ORG", "RMX", "EXT", "RADIO", "LIVE", "INST", "ACAP", "REM"}
        kind = str(kind).upper()
        if kind not in allowed:
            raise ValueError("Unsupported recording relationship")
        with self._lock, closing(self._connect()) as connection, connection:
            track = connection.execute("SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)).fetchone()
            target = connection.execute("SELECT * FROM downloaded_tracks WHERE id=?", (target_track_id,)).fetchone()
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
                    identity_confidence='manual', identity_reason=?,
                    identity_inference_locked=1, updated_at=? WHERE id=?""",
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
            if candidate["id"] == track_id or candidate.get("recording_code") == source.get("recording_code"):
                continue
            candidate_title = base_title(str(candidate.get("title") or candidate.get("filename") or ""))
            title_score = (
                SequenceMatcher(None, source_title, candidate_title).ratio() if source_title and candidate_title else 0
            )
            candidate_artist = normalize_identity_text(str(candidate.get("artist") or ""))
            artist_score = (
                SequenceMatcher(None, source_artist, candidate_artist).ratio()
                if source_artist and candidate_artist
                else 0
            )
            duration = float(candidate.get("duration_seconds") or 0)
            duration_score = (
                max(0.0, 1.0 - abs(source_duration - duration) / 120.0) if source_duration and duration else 0.35
            )
            score = round(100 * (title_score * 0.62 + artist_score * 0.23 + duration_score * 0.15))
            exact_audio = bool(source.get("audio_fingerprint")) and source.get("audio_fingerprint") == candidate.get(
                "audio_fingerprint"
            )
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
            candidates.append({"score": score, "reasons": reasons or ["metadata similarity"], "track": candidate})
        candidates.sort(key=lambda item: (-item["score"], str(item["track"].get("title") or "")))
        return candidates[: max(1, min(limit, 20))]

    def merge_downloaded_tracks(self, survivor_id: int, duplicate_id: int) -> dict[str, Any]:
        """Merge catalog references while retaining both physical files."""
        if survivor_id == duplicate_id:
            raise ValueError("Choose two different tracks")
        with self._lock, closing(self._connect()) as connection, connection:
            survivor = connection.execute("SELECT * FROM downloaded_tracks WHERE id=?", (survivor_id,)).fetchone()
            duplicate = connection.execute("SELECT * FROM downloaded_tracks WHERE id=?", (duplicate_id,)).fetchone()
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
            connection.execute("DELETE FROM downloaded_track_playlists WHERE track_id=?", (duplicate_id,))
            connection.execute(
                """INSERT OR IGNORE INTO downloaded_track_descriptors
                (track_id,category,value,provenance,confidence,updated_at)
                SELECT ?,category,value,provenance,confidence,updated_at
                FROM downloaded_track_descriptors WHERE track_id=?""",
                (survivor_id, duplicate_id),
            )
            connection.execute("DELETE FROM downloaded_track_descriptors WHERE track_id=?", (duplicate_id,))
            connection.execute(
                """INSERT OR REPLACE INTO downloaded_track_exclusions
                    (file_path,excluded_at) VALUES (?,?)""",
                (duplicate_path, now),
            )
            connection.execute("DELETE FROM downloaded_tracks WHERE id=?", (duplicate_id,))
        merged = self.get_downloaded_track(survivor_id) or {}
        merged["retained_file"] = duplicate_path
        return merged
