from __future__ import annotations

import json
import re
from contextlib import closing
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from audioextender.library.recording_identity import (
    audio_fingerprint,
    base_title,
    format_family_code,
    identity_key,
    next_version_code,
    normalize_identity_text,
    version_kind,
)
from audioextender.repositories.base import RepositoryMixinBase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TrackCatalogRepositoryMixin(RepositoryMixinBase):
    def track_ids_missing_inferred_identity(self) -> list[int]:
        """Return catalog tracks that have never received inferred/crate descriptors."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT tracks.id FROM downloaded_tracks tracks
                WHERE NOT EXISTS (
                    SELECT 1 FROM downloaded_track_descriptors descriptors
                    WHERE descriptors.track_id=tracks.id
                    AND descriptors.provenance IN ('inferred','crate'))
                OR EXISTS (
                    SELECT 1 FROM downloaded_track_descriptors stale
                    WHERE stale.track_id=tracks.id AND stale.provenance='crate'
                    AND (INSTR(stale.value, '_')>0 OR stale.value LIKE '% playlist'))
                ORDER BY tracks.id"""
            ).fetchall()
        return [int(row[0]) for row in rows]

    def replace_inferred_track_descriptors(
        self, track_id: int, descriptors: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Refresh machine/crate descriptors while retaining all manual decisions."""
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM downloaded_track_descriptors WHERE track_id=? AND provenance!='manual'",
                (track_id,),
            )
        return self.update_track_descriptors([track_id], descriptors, mode="add")

    def track_identity_inference_context(self, track_id: int) -> dict[str, Any] | None:
        """Collect catalog, playlist, and latest analysis evidence for inference."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT tracks.id,tracks.title,tracks.artist,tracks.filename,tracks.genre,
                    tracks.genre_category,
                    (SELECT GROUP_CONCAT(p.playlist_name,'||') FROM downloaded_track_playlists p
                     WHERE p.track_id=tracks.id) AS playlists,
                    idx.category AS library_category,idx.detail_genre AS library_detail_genre,
                    idx.roles AS library_roles,idx.energy_band,idx.vocals,idx.timing
                    FROM downloaded_tracks tracks
                    LEFT JOIN library_search_index idx ON idx.job_id=(
                        SELECT MAX(latest.job_id) FROM library_search_index latest
                        WHERE latest.downloaded_id=tracks.id)
                    WHERE tracks.id=?""",
                (track_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["playlists"] = [value for value in str(result.get("playlists") or "").split("||") if value]
        return result

    def track_descriptors(self, track_id: int) -> list[dict[str, Any]]:
        """Return durable musical-identity descriptors and their provenance."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT category,value,provenance,confidence,updated_at
                FROM downloaded_track_descriptors WHERE track_id=?
                ORDER BY category,value COLLATE NOCASE""",
                (track_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_track_descriptors(
        self,
        track_ids: list[int],
        descriptors: list[dict[str, Any]],
        *,
        mode: str = "replace",
    ) -> dict[str, Any]:
        """Add, remove, or replace descriptors atomically across selected tracks."""
        wanted = list(dict.fromkeys(int(track_id) for track_id in track_ids))
        normalized: list[tuple[str, str, str, float]] = []
        for descriptor in descriptors:
            category = str(descriptor.get("category") or "context").strip().casefold()
            value = str(descriptor.get("value") or "").strip().casefold()
            provenance = str(descriptor.get("provenance") or "manual").strip().casefold()
            confidence = max(0.0, min(1.0, float(descriptor.get("confidence", 1.0))))
            if value:
                normalized.append((category, value, provenance, confidence))
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            existing = {
                int(row[0])
                for row in connection.execute(
                    f"SELECT id FROM downloaded_tracks WHERE id IN ({','.join('?' for _ in wanted)})",
                    wanted,
                ).fetchall()
            } if wanted else set()
            if mode == "replace":
                connection.executemany(
                    "DELETE FROM downloaded_track_descriptors WHERE track_id=?",
                    [(track_id,) for track_id in existing],
                )
            elif mode == "remove" and normalized:
                connection.executemany(
                    "DELETE FROM downloaded_track_descriptors WHERE track_id=? AND category=? AND value=?",
                    [
                        (track_id, category, value)
                        for track_id in existing
                        for category, value, _, _ in normalized
                    ],
                )
            if mode in {"replace", "add"} and normalized:
                connection.executemany(
                    """INSERT INTO downloaded_track_descriptors
                    (track_id,category,value,provenance,confidence,updated_at)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(track_id,category,value) DO UPDATE SET
                    provenance=CASE WHEN downloaded_track_descriptors.provenance='manual'
                        AND excluded.provenance!='manual' THEN downloaded_track_descriptors.provenance
                        ELSE excluded.provenance END,
                    confidence=CASE WHEN downloaded_track_descriptors.provenance='manual'
                        AND excluded.provenance!='manual' THEN downloaded_track_descriptors.confidence
                        ELSE excluded.confidence END,
                    updated_at=excluded.updated_at""",
                    [
                        (track_id, category, value, provenance, confidence, now)
                        for track_id in existing
                        for category, value, provenance, confidence in normalized
                    ],
                )
        return {
            "requested": len(wanted),
            "updated": len(existing),
            "missing": sorted(set(wanted) - existing),
            "mode": mode,
            "descriptors": len(normalized),
            "survives_restart": True,
        }
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
            key = identity_key(artist, title)
            family_row = None
            identity_confidence = "new"
            identity_reason = "New recording family"
            if spotify_uri:
                family_row = connection.execute(
                    """SELECT recording_code FROM downloaded_tracks
                        WHERE spotify_uri=? AND recording_code!='' ORDER BY id LIMIT 1""",
                    (spotify_uri,),
                ).fetchone()
                if family_row:
                    identity_confidence = "high"
                    identity_reason = "Matched the same Spotify recording"
            if family_row is None and youtube_id:
                family_row = connection.execute(
                    """SELECT recording_code FROM downloaded_tracks
                        WHERE youtube_id=? AND recording_code!='' ORDER BY id LIMIT 1""",
                    (youtube_id,),
                ).fetchone()
                if family_row:
                    identity_confidence = "high"
                    identity_reason = "Matched the same source recording"
            if family_row is None and key != "|":
                family_row = connection.execute(
                    """SELECT recording_code FROM downloaded_tracks
                        WHERE identity_key=? AND recording_code!='' ORDER BY id LIMIT 1""",
                    (key,),
                ).fetchone()
                if family_row:
                    identity_confidence = "review"
                    identity_reason = "Matched normalized artist and title"
            if family_row:
                recording_code = str(family_row["recording_code"])
            else:
                recording_code = format_family_code(
                    self._next_recording_number(connection), genre_category
                )
            existing_versions = {
                str(row[0])
                for row in connection.execute(
                    "SELECT version_code FROM downloaded_tracks WHERE recording_code=?",
                    (recording_code,),
                )
            }
            version_code = next_version_code(version_kind(title), existing_versions)
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
                        spotify_uri=CASE WHEN excluded.spotify_uri != '' THEN excluded.spotify_uri ELSE downloaded_tracks.spotify_uri END,
                        youtube_id=CASE WHEN excluded.youtube_id != '' THEN excluded.youtube_id ELSE downloaded_tracks.youtube_id END,
                        youtube_url=CASE WHEN excluded.youtube_url != '' THEN excluded.youtube_url ELSE downloaded_tracks.youtube_url END,
                        artwork_url=CASE WHEN excluded.artwork_url != '' THEN excluded.artwork_url ELSE downloaded_tracks.artwork_url END,
                        artwork_path=CASE WHEN excluded.artwork_path != '' THEN excluded.artwork_path ELSE downloaded_tracks.artwork_path END,
                        audio_fingerprint=CASE WHEN excluded.audio_fingerprint != '' THEN excluded.audio_fingerprint ELSE downloaded_tracks.audio_fingerprint END,
                        duration_seconds=COALESCE(excluded.duration_seconds, downloaded_tracks.duration_seconds),
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
                    recording_code,
                    version_code,
                    key,
                    identity_confidence,
                    identity_reason,
                    fingerprint,
                ),
            )
            row = connection.execute(
                "SELECT id FROM downloaded_tracks WHERE file_path = ?", (resolved,)
            ).fetchone()
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
            item["playlists"] = [
                value for value in str(item.get("playlists") or "").split("||") if value
            ]
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
                    same_spotify = bool(first.get("spotify_uri")) and first[
                        "spotify_uri"
                    ] == second.get("spotify_uri")
                    same_youtube = bool(first.get("youtube_id")) and first[
                        "youtube_id"
                    ] == second.get("youtube_id")
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

    def separate_recording(self, track_id: int) -> dict[str, Any]:
        """Move a false-positive match into its own permanent recording family."""
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)
            ).fetchone()
            if row is None:
                raise KeyError(track_id)
            recording_code = format_family_code(
                self._next_recording_number(connection), str(row["genre_category"] or "Other")
            )
            version_code = next_version_code(version_kind(str(row["title"])), set())
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?, version_code=?,
                    identity_confidence='manual', identity_reason='Kept separate by user',
                    updated_at=? WHERE id=?""",
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

    def link_recording_version(
        self, track_id: int, target_track_id: int, kind: str
    ) -> dict[str, Any]:
        """Link a track to another track's family without merging files or history."""
        if track_id == target_track_id:
            raise ValueError("Choose a different track as the recording family")
        allowed = {"ORG", "RMX", "EXT", "RADIO", "LIVE", "INST", "ACAP", "REM"}
        kind = str(kind).upper()
        if kind not in allowed:
            raise ValueError("Unsupported recording relationship")
        with self._lock, closing(self._connect()) as connection, connection:
            track = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)
            ).fetchone()
            target = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (target_track_id,)
            ).fetchone()
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
                    identity_confidence='manual', identity_reason=?, updated_at=? WHERE id=?""",
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
            if candidate["id"] == track_id or candidate.get("recording_code") == source.get(
                "recording_code"
            ):
                continue
            candidate_title = base_title(
                str(candidate.get("title") or candidate.get("filename") or "")
            )
            title_score = (
                SequenceMatcher(None, source_title, candidate_title).ratio()
                if source_title and candidate_title
                else 0
            )
            candidate_artist = normalize_identity_text(str(candidate.get("artist") or ""))
            artist_score = (
                SequenceMatcher(None, source_artist, candidate_artist).ratio()
                if source_artist and candidate_artist
                else 0
            )
            duration = float(candidate.get("duration_seconds") or 0)
            duration_score = (
                max(0.0, 1.0 - abs(source_duration - duration) / 120.0)
                if source_duration and duration
                else 0.35
            )
            score = round(100 * (title_score * 0.62 + artist_score * 0.23 + duration_score * 0.15))
            exact_audio = bool(source.get("audio_fingerprint")) and source.get(
                "audio_fingerprint"
            ) == candidate.get("audio_fingerprint")
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
            candidates.append(
                {"score": score, "reasons": reasons or ["metadata similarity"], "track": candidate}
            )
        candidates.sort(key=lambda item: (-item["score"], str(item["track"].get("title") or "")))
        return candidates[: max(1, min(limit, 20))]

    def merge_downloaded_tracks(self, survivor_id: int, duplicate_id: int) -> dict[str, Any]:
        """Merge catalog references while retaining both physical files."""
        if survivor_id == duplicate_id:
            raise ValueError("Choose two different tracks")
        with self._lock, closing(self._connect()) as connection, connection:
            survivor = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (survivor_id,)
            ).fetchone()
            duplicate = connection.execute(
                "SELECT * FROM downloaded_tracks WHERE id=?", (duplicate_id,)
            ).fetchone()
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
            connection.execute(
                "DELETE FROM downloaded_track_playlists WHERE track_id=?", (duplicate_id,)
            )
            connection.execute(
                """INSERT OR IGNORE INTO downloaded_track_descriptors
                (track_id,category,value,provenance,confidence,updated_at)
                SELECT ?,category,value,provenance,confidence,updated_at
                FROM downloaded_track_descriptors WHERE track_id=?""",
                (survivor_id, duplicate_id),
            )
            connection.execute(
                "DELETE FROM downloaded_track_descriptors WHERE track_id=?", (duplicate_id,)
            )
            connection.execute(
                """INSERT OR REPLACE INTO downloaded_track_exclusions
                    (file_path,excluded_at) VALUES (?,?)""",
                (duplicate_path, now),
            )
            connection.execute("DELETE FROM downloaded_tracks WHERE id=?", (duplicate_id,))
        merged = self.get_downloaded_track(survivor_id) or {}
        merged["retained_file"] = duplicate_path
        return merged

    def list_downloaded_tracks_with_jobs(self) -> list[dict[str, Any]]:
        """Return the catalog with latest job state resolved inside SQLite."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                    WITH latest_any AS (
                        SELECT source_path, MAX(id) AS job_id
                        FROM jobs GROUP BY source_path
                    ), latest_complete AS (
                        SELECT source_path, MAX(id) AS job_id
                        FROM jobs WHERE status = 'complete' GROUP BY source_path
                    )
                    SELECT tracks.*,
                        GROUP_CONCAT(playlists.playlist_name, '||') AS playlists,
                        (SELECT json_group_array(json_object(
                            'category', descriptors.category, 'value', descriptors.value,
                            'provenance', descriptors.provenance,
                            'confidence', descriptors.confidence,
                            'updated_at', descriptors.updated_at))
                         FROM downloaded_track_descriptors descriptors
                         WHERE descriptors.track_id=tracks.id) AS descriptors_json,
                        latest_job.status AS analysis_status,
                        latest_job.id AS library_job_id,
                        completed_job.id AS completed_library_job_id
                    FROM downloaded_tracks AS tracks
                    LEFT JOIN downloaded_track_playlists AS playlists
                        ON playlists.track_id = tracks.id
                    LEFT JOIN latest_any
                        ON latest_any.source_path = tracks.file_path
                    LEFT JOIN jobs AS latest_job
                        ON latest_job.id = latest_any.job_id
                    LEFT JOIN latest_complete
                        ON latest_complete.source_path = tracks.file_path
                    LEFT JOIN jobs AS completed_job
                        ON completed_job.id = latest_complete.job_id
                    GROUP BY tracks.id
                    ORDER BY tracks.imported_at DESC, tracks.id DESC
                    """
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [
                value for value in str(item.get("playlists") or "").split("||") if value
            ]
            results.append(item)
        return results

    def page_downloaded_tracks(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        genre: str = "all",
        playlist: str = "all",
        detailed_genre: str = "all",
        analysis: str = "all",
        artwork: str = "all",
        quality: str = "all",
        sort: str = "newest",
    ) -> tuple[list[dict[str, Any]], int]:
        """Filter, sort, and page the downloaded catalog entirely in SQLite."""
        conditions: list[str] = []
        parameters: list[Any] = []
        if search.strip():
            value = f"%{search.strip().casefold()}%"
            conditions.append(
                "(LOWER(tracks.title) LIKE ? OR LOWER(tracks.artist) LIKE ? "
                "OR LOWER(tracks.genre) LIKE ? OR LOWER(tracks.genre_category) LIKE ? "
                "OR LOWER(tracks.recording_code || '-' || tracks.version_code) LIKE ? "
                "OR EXISTS (SELECT 1 FROM downloaded_track_playlists search_playlist "
                "WHERE search_playlist.track_id = tracks.id "
                "AND LOWER(search_playlist.playlist_name) LIKE ?) "
                "OR EXISTS (SELECT 1 FROM downloaded_track_descriptors search_descriptor "
                "WHERE search_descriptor.track_id = tracks.id AND LOWER(search_descriptor.value) LIKE ?))"
            )
            parameters.extend([value] * 7)
        missing_title = "TRIM(COALESCE(tracks.title, '')) = '' OR LOWER(TRIM(tracks.title)) IN ('unknown title','untitled')"
        missing_artist = "TRIM(COALESCE(tracks.artist, '')) = '' OR LOWER(TRIM(tracks.artist)) IN ('unknown artist','unknown','unavailable')"
        missing_genre = "TRIM(COALESCE(tracks.genre, '')) = ''"
        missing_artwork = "TRIM(COALESCE(tracks.artwork_path, '')) = ''"
        unmapped_genre = (
            "TRIM(COALESCE(tracks.genre, '')) != '' AND tracks.genre_category = 'Other'"
        )
        broad_genre = (
            "(tracks.genre_category LIKE '% / General' OR tracks.genre_category LIKE '% / Other')"
        )
        if genre != "all":
            aliases = {
                "Electronic / General": "Electronic / Electronic / Electronic",
                "Latin / General": "Latin / Other",
            }
            stored_genre = aliases.get(genre, genre)
            conditions.append(
                "(tracks.genre_category = ? OR tracks.genre_category LIKE ? ESCAPE '\\')"
            )
            escaped = stored_genre.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend((stored_genre, f"{escaped} / %"))
        if detailed_genre != "all":
            # Source genres are stored as comma-separated tags. Pad both sides
            # with commas so selecting "house" cannot also match "deep house".
            normalized_tag = detailed_genre.strip().casefold()
            conditions.append(
                "(',' || REPLACE(REPLACE(LOWER(COALESCE(tracks.genre, '')), ', ', ','), ' ,', ',') || ',') LIKE ?"
            )
            parameters.append(f"%,{normalized_tag},%")
        if playlist != "all":
            conditions.append(
                "EXISTS (SELECT 1 FROM downloaded_track_playlists selected_playlist "
                "WHERE selected_playlist.track_id = tracks.id "
                "AND selected_playlist.playlist_name = ?)"
            )
            parameters.append(playlist)
        status = "COALESCE(latest_job.status, 'not_analyzed')"
        analysis_conditions = {
            "needs": f"{status} IN ('not_analyzed','failed','canceled')",
            "complete": f"{status} = 'complete'",
            "active": f"{status} IN ('queued','processing')",
            "failed": f"{status} IN ('failed','canceled')",
            "attention": f"({missing_title} OR {missing_artist} OR {missing_genre} OR {missing_artwork} OR {unmapped_genre} OR {broad_genre})",
            "missing_title": f"({missing_title})",
            "missing_artist": f"({missing_artist})",
            "missing_genre": f"({missing_genre})",
            "missing_artwork": f"({missing_artwork})",
            "unmapped_genre": f"({unmapped_genre})",
            "broad_genre": f"({broad_genre})",
        }
        if analysis in analysis_conditions:
            conditions.append(analysis_conditions[analysis])
        if artwork == "missing":
            conditions.append("TRIM(COALESCE(tracks.artwork_path, '')) = ''")
        elif artwork == "available":
            conditions.append("TRIM(COALESCE(tracks.artwork_path, '')) != ''")
        quality_conditions = {
            "excellent": "tracks.audio_quality_label = 'excellent'",
            "good": "tracks.audio_quality_label = 'good'",
            "review": "tracks.audio_quality_label = 'review'",
            "poor": "tracks.audio_quality_label = 'poor'",
            "below-target": "tracks.audio_quality_label IN ('review','poor')",
            "unanalyzed": "tracks.audio_quality_score IS NULL",
        }
        if quality in quality_conditions:
            conditions.append(quality_conditions[quality])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order = {
            "newest": "tracks.imported_at DESC, tracks.id DESC",
            "title": "tracks.title COLLATE NOCASE, tracks.id",
            "artist": "tracks.artist COLLATE NOCASE, tracks.title COLLATE NOCASE",
            "genre": "tracks.genre_category COLLATE NOCASE, tracks.artist COLLATE NOCASE",
        }.get(sort, "tracks.imported_at DESC, tracks.id DESC")
        ctes = """WITH latest_any AS (
                SELECT source_path, MAX(id) AS job_id FROM jobs GROUP BY source_path
            ), latest_complete AS (
                SELECT source_path, MAX(id) AS job_id FROM jobs
                WHERE status = 'complete' GROUP BY source_path
            )"""
        joins = """FROM downloaded_tracks AS tracks
                LEFT JOIN latest_any ON latest_any.source_path = tracks.file_path
                LEFT JOIN jobs AS latest_job ON latest_job.id = latest_any.job_id
                LEFT JOIN latest_complete ON latest_complete.source_path = tracks.file_path
                LEFT JOIN jobs AS completed_job ON completed_job.id = latest_complete.job_id"""
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"{ctes} SELECT COUNT(*) {joins} {where}", parameters
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""{ctes} SELECT tracks.id, tracks.title, tracks.artist,
                    tracks.filename, tracks.genre, tracks.genre_category,
                    tracks.recording_code, tracks.version_code,
                    tracks.identity_confidence, tracks.identity_reason,
                    tracks.audio_quality_score, tracks.audio_quality_label,
                    tracks.audio_quality_json, tracks.audio_quality_analyzed_at,
                    tracks.artwork_url, tracks.artwork_path, tracks.file_path,
                    tracks.duration_seconds, tracks.imported_at,
                    (SELECT json_group_array(json_object(
                        'category', descriptors.category, 'value', descriptors.value,
                        'provenance', descriptors.provenance,
                        'confidence', descriptors.confidence,
                        'updated_at', descriptors.updated_at))
                     FROM downloaded_track_descriptors descriptors
                     WHERE descriptors.track_id=tracks.id) AS descriptors_json,
                    (SELECT GROUP_CONCAT(p.playlist_name, '||')
                     FROM downloaded_track_playlists p WHERE p.track_id = tracks.id) AS playlists,
                    latest_job.status AS analysis_status,
                    latest_job.id AS library_job_id,
                    completed_job.id AS completed_library_job_id
                    {joins} {where} ORDER BY {order} LIMIT ? OFFSET ?""",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [
                value for value in str(item.get("playlists") or "").split("||") if value
            ]
            results.append(item)
        return results, total

    def update_audio_quality(self, track_id: int, result: dict[str, Any]) -> None:
        """Persist one quality assessment without changing music metadata."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE downloaded_tracks SET audio_quality_score=?,
                    audio_quality_label=?,audio_quality_json=?,audio_quality_analyzed_at=?,
                    updated_at=? WHERE id=?""",
                (
                    float(result["score"]),
                    str(result["label"]),
                    json.dumps(result, sort_keys=True),
                    now,
                    now,
                    track_id,
                ),
            )

    def audio_quality_summary(self) -> dict[str, Any]:
        """Return lightweight library-wide quality statistics for Settings."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS total,
                    COUNT(audio_quality_score) AS analyzed,
                    AVG(audio_quality_score) AS average_score,
                    SUM(CASE WHEN audio_quality_label='excellent' THEN 1 ELSE 0 END) AS excellent,
                    SUM(CASE WHEN audio_quality_label='good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN audio_quality_label='review' THEN 1 ELSE 0 END) AS review,
                    SUM(CASE WHEN audio_quality_label='poor' THEN 1 ELSE 0 END) AS poor
                    FROM downloaded_tracks"""
            ).fetchone()
        return {key: (0 if value is None else value) for key, value in dict(row).items()}

    def downloaded_catalog_facets(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM downloaded_tracks").fetchone()[0])
            genres = dict(
                connection.execute(
                    "SELECT genre_category, COUNT(*) FROM downloaded_tracks GROUP BY genre_category"
                ).fetchall()
            )
            playlists = dict(
                connection.execute(
                    "SELECT playlist_name, COUNT(*) FROM downloaded_track_playlists GROUP BY playlist_name"
                ).fetchall()
            )
            detailed_genres: dict[str, int] = {}
            detailed_genres_by_category: dict[str, dict[str, int]] = {}
            canonical_tags: dict[str, str] = {}
            for category, raw_genres in connection.execute(
                "SELECT genre_category, genre FROM downloaded_tracks WHERE TRIM(COALESCE(genre, '')) != ''"
            ).fetchall():
                category_genres = detailed_genres_by_category.setdefault(
                    str(category or "Other"), {}
                )
                seen: set[str] = set()
                for raw_tag in str(raw_genres or "").split(","):
                    tag = raw_tag.strip()
                    key = tag.casefold()
                    if not tag or key in seen:
                        continue
                    seen.add(key)
                    display = canonical_tags.setdefault(key, tag)
                    detailed_genres[display] = detailed_genres.get(display, 0) + 1
                    category_genres[display] = category_genres.get(display, 0) + 1
            issue_conditions = {
                "missing_title": "TRIM(COALESCE(title, '')) = '' OR LOWER(TRIM(title)) IN ('unknown title','untitled')",
                "missing_artist": "TRIM(COALESCE(artist, '')) = '' OR LOWER(TRIM(artist)) IN ('unknown artist','unknown','unavailable')",
                "missing_genre": "TRIM(COALESCE(genre, '')) = ''",
                "missing_artwork": "TRIM(COALESCE(artwork_path, '')) = ''",
                "unmapped_genre": "TRIM(COALESCE(genre, '')) != '' AND genre_category = 'Other'",
                "broad_genre": "genre_category LIKE '% / General' OR genre_category LIKE '% / Other'",
            }
            review_states = {
                name: int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM downloaded_tracks WHERE {condition}"
                    ).fetchone()[0]
                )
                for name, condition in issue_conditions.items()
            }
            review_states["needs_attention"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM downloaded_tracks WHERE "
                    + " OR ".join(f"({condition})" for condition in issue_conditions.values())
                ).fetchone()[0]
            )
        return {
            "total": total,
            "genres": genres,
            "detailed_genres": detailed_genres,
            "detailed_genres_by_category": detailed_genres_by_category,
            "playlists": playlists,
            "review_states": review_states,
        }

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
        item["playlists"] = [
            value for value in str(item.get("playlists") or "").split("||") if value
        ]
        return item

    def update_downloaded_track_artwork(
        self, track_id: int, *, artwork_url: str, artwork_path: str
    ) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE downloaded_tracks SET artwork_url=?, artwork_path=?, updated_at=? "
                "WHERE id=?",
                (artwork_url, artwork_path, _now(), track_id),
            )

    def update_downloaded_track_key_analysis(
        self,
        track_id: int,
        *,
        detected_key: str,
        confidence: float,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Save a key-only result without replacing the track's other analysis."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE downloaded_tracks SET detected_key=?, key_confidence=?,
                    key_candidates_json=?, key_analyzed_at=?, updated_at=? WHERE id=?""",
                (
                    detected_key,
                    confidence,
                    json.dumps(candidates, separators=(",", ":")),
                    now,
                    now,
                    track_id,
                ),
            )
        return self.get_downloaded_track(track_id) or {}

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
        item["playlists"] = [
            value for value in str(item.get("playlists") or "").split("||") if value
        ]
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
                        "SELECT version_code FROM downloaded_tracks "
                        "WHERE recording_code=? AND id!=?",
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
            connection.execute(
                "DELETE FROM downloaded_track_playlists WHERE track_id=?", (track_id,)
            )
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
            row = connection.execute(
                "SELECT file_path FROM downloaded_tracks WHERE id = ?", (track_id,)
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "INSERT OR REPLACE INTO downloaded_track_exclusions "
                "(file_path, excluded_at) VALUES (?, ?)",
                (row["file_path"], _now()),
            )
            connection.execute(
                "DELETE FROM downloaded_track_playlists WHERE track_id = ?", (track_id,)
            )
            connection.execute(
                "DELETE FROM downloaded_track_descriptors WHERE track_id = ?", (track_id,)
            )
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
