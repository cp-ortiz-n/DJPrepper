"""Conservative repair of legacy recording-family assignments."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from audioextender.library.recording_identity import (
    artists_share_credit,
    canonical_title_key,
    identity_key,
    next_version_code,
    normalize_identity_text,
    version_kind,
)
from audioextender.persistence.base import RepositoryMixinBase
from audioextender.persistence.catalog.shared import catalog_now as _now


class RecordingFamilyReassessmentRepositoryMixin(RepositoryMixinBase):
    def reassess_recording_family(self, track_id: int) -> dict[str, Any]:
        """Repair one unlocked recording identity from conservative metadata evidence.

        Reanalysis uses this boundary to converge legacy original/remix rows that
        received separate family codes. Manual identities always remain
        authoritative, and an established multi-track family is never split.
        """
        with self._lock, closing(self._connect()) as connection, connection:
            source = connection.execute("SELECT * FROM downloaded_tracks WHERE id=?", (track_id,)).fetchone()
            if source is None:
                raise KeyError(track_id)
            if bool(source["identity_inference_locked"]):
                return dict(source)
            family_size = int(
                connection.execute(
                    "SELECT COUNT(*) FROM downloaded_tracks WHERE recording_code=?",
                    (str(source["recording_code"] or ""),),
                ).fetchone()[0]
            )
            if family_size > 1:
                return dict(source)

            title_key = canonical_title_key(str(source["title"] or ""), str(source["artist"] or ""))
            if not title_key:
                return dict(source)
            candidates = connection.execute(
                """SELECT * FROM downloaded_tracks
                WHERE id!=? AND recording_code!=?
                ORDER BY id""",
                (track_id, str(source["recording_code"] or "")),
            ).fetchall()
            matches: list[tuple[int, sqlite3.Row]] = []
            for candidate in candidates:
                if str(candidate["identity_reason"] or "") == "Kept separate by user":
                    continue
                candidate_title_key = canonical_title_key(str(candidate["title"] or ""), str(candidate["artist"] or ""))
                shared_source = any(
                    str(source[field] or "") and str(source[field] or "") == str(candidate[field] or "")
                    for field in ("spotify_uri", "youtube_id", "audio_fingerprint")
                )
                shared_metadata = title_key == candidate_title_key and artists_share_credit(
                    str(source["artist"] or ""), str(candidate["artist"] or "")
                )
                if not shared_source and not shared_metadata:
                    continue
                exact_artist = normalize_identity_text(str(source["artist"] or "")) == normalize_identity_text(
                    str(candidate["artist"] or "")
                )
                matches.append((2 if shared_source else 1 + int(exact_artist), candidate))
            if not matches:
                return dict(source)

            _, target = max(matches, key=lambda item: (item[0], -int(item[1]["id"])))
            recording_code = str(target["recording_code"] or "")
            existing = {
                str(row[0])
                for row in connection.execute(
                    "SELECT version_code FROM downloaded_tracks WHERE recording_code=? AND id!=?",
                    (recording_code, track_id),
                )
            }
            version_code = next_version_code(version_kind(str(source["title"] or "")), existing)
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?,version_code=?,identity_key=?,
                identity_confidence='review',identity_reason=?,updated_at=? WHERE id=?""",
                (
                    recording_code,
                    version_code,
                    identity_key(str(source["artist"] or ""), str(source["title"] or "")),
                    f"Reanalysis matched canonical title and artist credit to {recording_code}",
                    _now(),
                    track_id,
                ),
            )
        return self.get_downloaded_track(track_id) or {}
