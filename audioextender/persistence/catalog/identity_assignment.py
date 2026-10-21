"""Recording-family assignment policy for catalog writes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from audioextender.library.recording_identity import (
    format_family_code,
    identity_key,
    next_version_code,
    version_kind,
)


@dataclass(frozen=True)
class RecordingAssignment:
    key: str
    recording_code: str
    version_code: str
    confidence: str
    reason: str


def assignment_for_upsert(
    connection: sqlite3.Connection,
    *,
    title: str,
    artist: str,
    resolved_path: str,
    genre_category: str,
    spotify_uri: str,
    youtube_id: str,
    next_recording_number: int,
) -> RecordingAssignment:
    key = identity_key(artist, title)
    current = connection.execute(
        "SELECT id,recording_code,identity_inference_locked FROM downloaded_tracks WHERE file_path=?",
        (resolved_path,),
    ).fetchone()
    locked = bool(current and current["identity_inference_locked"])
    family = None
    confidence, reason = "new", "New recording family"
    lookups = (
        (spotify_uri, "spotify_uri", "high", "Matched the same Spotify recording"),
        (youtube_id, "youtube_id", "high", "Matched the same source recording"),
        (key if key != "|" else "", "identity_key", "review", "Matched normalized artist and title"),
    )
    if not locked:
        for value, column, match_confidence, match_reason in lookups:
            if not value:
                continue
            family = connection.execute(
                f"""SELECT recording_code FROM downloaded_tracks
                WHERE {column}=? AND recording_code!='' AND file_path!=? ORDER BY id LIMIT 1""",
                (value, resolved_path),
            ).fetchone()
            if family:
                confidence, reason = match_confidence, match_reason
                break
    if family:
        recording_code = str(family["recording_code"])
    elif current and current["recording_code"]:
        recording_code = str(current["recording_code"])
        confidence = "manual" if locked else "review"
        reason = "Preserved existing recording family"
    else:
        recording_code = format_family_code(next_recording_number, genre_category)
    existing = {
        str(row[1])
        for row in connection.execute(
            "SELECT id,version_code FROM downloaded_tracks WHERE recording_code=?", (recording_code,)
        )
        if current is None or int(row[0]) != int(current["id"])
    }
    return RecordingAssignment(
        key=key,
        recording_code=recording_code,
        version_code=next_version_code(version_kind(title), existing),
        confidence=confidence,
        reason=reason,
    )


def assignment_for_metadata_update(
    connection: sqlite3.Connection,
    *,
    current: sqlite3.Row,
    track_id: int,
    title: str,
    artist: str,
) -> RecordingAssignment:
    key = identity_key(artist, title)
    original_code = str(current["recording_code"] or "")
    recording_code = original_code
    if not bool(current["identity_inference_locked"]):
        matched = connection.execute(
            """SELECT recording_code FROM downloaded_tracks
            WHERE id!=? AND identity_key=? AND recording_code!='' ORDER BY id LIMIT 1""",
            (track_id, key),
        ).fetchone()
        if matched:
            recording_code = str(matched["recording_code"])
    wanted_kind = version_kind(title)
    current_kind = str(current["version_code"] or "ORG").rstrip("0123456789")
    version_code = str(current["version_code"] or "ORG")
    if wanted_kind != current_kind or recording_code != original_code:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT version_code FROM downloaded_tracks WHERE recording_code=? AND id!=?",
                (recording_code, track_id),
            )
        }
        version_code = next_version_code(wanted_kind, existing)
    return RecordingAssignment(
        key=key,
        recording_code=recording_code,
        version_code=version_code,
        confidence="manual",
        reason=(
            "Metadata matched canonical artist and title"
            if recording_code != original_code
            else "Metadata confirmed by user"
        ),
    )
