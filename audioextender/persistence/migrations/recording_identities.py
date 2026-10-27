"""Idempotent migrations for recording-family identities."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from audioextender.library.recording_identity import (
    canonical_title_key,
    format_family_code,
    identity_key,
    infer_recording_family,
    next_version_code,
    version_kind,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def migrate_recording_identities(
    connection: sqlite3.Connection,
    next_recording_number: Callable[[sqlite3.Connection], int],
) -> None:
    """Backfill stable identities and converge safe legacy title variants."""
    connection.execute(
        """CREATE TABLE IF NOT EXISTS system_state (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    _migrate_genre_codes(connection)
    _backfill_missing_identities(connection, next_recording_number)
    _migrate_canonical_keys(connection)
    _migrate_inferred_song_families(connection)


def _migrate_genre_codes(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT 1 FROM system_state WHERE key='recording_genre_codes'").fetchone():
        return
    families = connection.execute(
        """SELECT recording_code,
        COALESCE(MAX(CASE WHEN version_code='ORG' THEN genre_category END),
                 MAX(genre_category), 'Other') AS genre_category
        FROM downloaded_tracks GROUP BY recording_code"""
    ).fetchall()
    for family in families:
        try:
            number = int(str(family["recording_code"]).split("-", 1)[1])
        except (IndexError, ValueError):
            continue
        new_code = format_family_code(number, str(family["genre_category"] or "Other"))
        connection.execute(
            "UPDATE downloaded_tracks SET recording_code=? WHERE recording_code=?",
            (new_code, family["recording_code"]),
        )
    connection.execute(
        "INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)",
        ("recording_genre_codes", "v1", _now()),
    )


def _backfill_missing_identities(
    connection: sqlite3.Connection,
    next_recording_number: Callable[[sqlite3.Connection], int],
) -> None:
    if connection.execute("SELECT 1 FROM downloaded_tracks WHERE recording_code='' LIMIT 1").fetchone() is None:
        return
    rows = connection.execute("SELECT * FROM downloaded_tracks ORDER BY id").fetchall()
    next_number = next_recording_number(connection)
    families: dict[str, str] = {}
    versions: dict[str, set[str]] = {}
    for row in rows:
        current_code = str(row["recording_code"] or "")
        key = str(row["identity_key"] or "") or identity_key(str(row["artist"] or ""), str(row["title"] or ""))
        if current_code:
            families.setdefault(key, current_code)
            versions.setdefault(current_code, set()).add(str(row["version_code"] or "ORG"))
            if not row["identity_key"]:
                connection.execute("UPDATE downloaded_tracks SET identity_key=? WHERE id=?", (key, row["id"]))
            continue
        family = families.get(key)
        if not family:
            family = format_family_code(next_number, str(row["genre_category"] or "Other"))
            next_number += 1
            families[key] = family
        existing = versions.setdefault(family, set())
        version = next_version_code(version_kind(str(row["title"] or "")), existing)
        existing.add(version)
        connection.execute(
            """UPDATE downloaded_tracks SET recording_code=?, version_code=?, identity_key=?,
            identity_confidence='migrated', identity_reason='Assigned from existing artist and title' WHERE id=?""",
            (family, version, key, row["id"]),
        )


def _migrate_canonical_keys(connection: sqlite3.Connection) -> None:
    migration_key = "canonical_recording_identity_keys"
    if connection.execute("SELECT 1 FROM system_state WHERE key=?", (migration_key,)).fetchone():
        return
    rows = connection.execute("SELECT * FROM downloaded_tracks ORDER BY id").fetchall()
    eligible = [
        row
        for row in rows
        if not bool(row["identity_inference_locked"]) and str(row["identity_confidence"] or "").casefold() != "manual"
    ]
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in eligible:
        key = identity_key(str(row["artist"] or ""), str(row["title"] or ""))
        connection.execute("UPDATE downloaded_tracks SET identity_key=? WHERE id=?", (key, row["id"]))
        if key != "|":
            groups.setdefault(key, []).append(row)
    manual_codes = {
        str(row["recording_code"] or "")
        for row in rows
        if bool(row["identity_inference_locked"]) or str(row["identity_confidence"] or "").casefold() == "manual"
    }
    for key_rows in groups.values():
        codes = {str(row["recording_code"] or "") for row in key_rows if row["recording_code"]}
        if len(codes) <= 1 or codes & manual_codes:
            continue
        canonical = str(key_rows[0]["recording_code"])
        placeholders = ",".join("?" for _ in key_rows)
        existing = {
            str(row[0])
            for row in connection.execute(
                f"SELECT version_code FROM downloaded_tracks WHERE recording_code=? AND id NOT IN ({placeholders})",
                (canonical, *(int(row["id"]) for row in key_rows)),
            )
        }
        for row in key_rows:
            version = next_version_code(version_kind(str(row["title"] or "")), existing)
            existing.add(version)
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?, version_code=?,
                identity_confidence='review', identity_reason=? WHERE id=?""",
                (canonical, version, "Matched canonical artist and title", row["id"]),
            )
    connection.execute(
        "INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)",
        (migration_key, "v1", _now()),
    )


def _migrate_inferred_song_families(connection: sqlite3.Connection) -> None:
    """Converge safe legacy version rows using the current inference policy."""
    migration_key = "inferred_recording_song_families"
    if connection.execute("SELECT 1 FROM system_state WHERE key=?", (migration_key,)).fetchone():
        return
    rows = connection.execute("SELECT * FROM downloaded_tracks ORDER BY id").fetchall()
    for row in rows:
        key = identity_key(str(row["artist"] or ""), str(row["title"] or ""))
        connection.execute("UPDATE downloaded_tracks SET identity_key=? WHERE id=?", (key, row["id"]))
    eligible = [
        row
        for row in rows
        if not bool(row["identity_inference_locked"]) and str(row["identity_confidence"] or "").casefold() != "manual"
    ]

    components = _inference_components(eligible)

    protected_codes = {
        str(row["recording_code"] or "")
        for row in rows
        if bool(row["identity_inference_locked"]) or str(row["identity_confidence"] or "").casefold() == "manual"
    }
    now = _now()
    for component in components:
        codes = {str(row["recording_code"] or "") for row in component if row["recording_code"]}
        if len(codes) <= 1 or codes & protected_codes:
            continue
        code_sizes = {code: sum(str(row["recording_code"] or "") == code for row in component) for code in codes}
        canonical_code = min(
            codes,
            key=lambda code: (
                -code_sizes[code],
                min(int(row["id"]) for row in component if str(row["recording_code"] or "") == code),
            ),
        )
        component_ids = {int(row["id"]) for row in component}
        existing_versions = {
            str(row[1])
            for row in connection.execute(
                "SELECT id,version_code FROM downloaded_tracks WHERE recording_code=?",
                (canonical_code,),
            )
            if int(row[0]) not in component_ids
        }
        ordered_rows = sorted(
            component,
            key=lambda item: (
                version_kind(str(item["title"] or "")) != "ORG",
                int(item["id"]),
            ),
        )
        for row in ordered_rows:
            version = next_version_code(version_kind(str(row["title"] or "")), existing_versions)
            existing_versions.add(version)
            connection.execute(
                """UPDATE downloaded_tracks SET recording_code=?,version_code=?,
                identity_confidence='review',identity_reason=?,updated_at=? WHERE id=?""",
                (
                    canonical_code,
                    version,
                    "Inferred same song family from catalog identity evidence",
                    now,
                    row["id"],
                ),
            )
    connection.execute(
        "INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)",
        (migration_key, "v2", now),
    )


def _rows_share_family(left: sqlite3.Row, right: sqlite3.Row) -> bool:
    shared_source = any(
        str(left[field] or "") and str(left[field] or "") == str(right[field] or "")
        for field in ("spotify_uri", "youtube_id", "audio_fingerprint")
    )
    return (
        shared_source
        or infer_recording_family(
            str(left["artist"] or ""),
            str(left["title"] or ""),
            str(right["artist"] or ""),
            str(right["title"] or ""),
        )
        is not None
    )


def _inference_components(rows: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    """Build connected family groups from indexed source and title evidence."""
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    source_owners: dict[tuple[str, str], int] = {}
    title_groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        for field in ("spotify_uri", "youtube_id", "audio_fingerprint"):
            value = str(row[field] or "")
            if not value:
                continue
            owner = source_owners.setdefault((field, value), index)
            union(index, owner)
        title_key = canonical_title_key(str(row["title"] or ""), str(row["artist"] or ""))
        if title_key:
            title_groups.setdefault(title_key, []).append(index)
    for indexes in title_groups.values():
        for position, left_index in enumerate(indexes):
            for right_index in indexes[position + 1 :]:
                if _rows_share_family(rows[left_index], rows[right_index]):
                    union(left_index, right_index)
    grouped: dict[int, list[sqlite3.Row]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(find(index), []).append(row)
    return list(grouped.values())
