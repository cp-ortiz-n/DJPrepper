"""Previewable, conservative synchronization of public Rekordbox rating exports."""

from __future__ import annotations

import csv
import io
import json
import re
import threading
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from audioextender.library.recording_identity import normalize_identity_text

REKORDBOX_SOURCE = "rekordbox"
MAX_REKORDBOX_EXPORT_BYTES = 32 * 1024 * 1024
_DJLS_TRACK_ID = re.compile(r"(?:^|\s)DJLS:downloaded:(\d+)(?:\s|$)", re.I)
_DJLS_VERSION_ID = re.compile(r"(?:^|\s)DJLS:recording:([^:\s]+):([^\s]+)(?:\s|$)", re.I)


class RekordboxRatingImportError(ValueError):
    """The selected file is not a safe, supported Rekordbox collection XML."""


@dataclass(frozen=True)
class RekordboxRatingTrack:
    source_track_id: str
    title: str
    artist: str
    duration_seconds: float | None
    location: str
    rating: int
    comments: str


def _rating(value: str) -> int | None:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    if raw == 0:
        return 0
    if 1 <= raw <= 5:
        return raw
    if raw in {51, 102, 153, 204, 255}:
        return raw // 51
    return None


def _decode_export(content: bytes) -> str:
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        return content.decode(encoding)
    except UnicodeDecodeError as error:
        raise RekordboxRatingImportError("The Rekordbox export must use UTF-8 or UTF-16 text encoding.") from error


def _duration_seconds(value: str) -> float | None:
    try:
        parts = [int(part) for part in value.strip().split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    if len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return None


def _text_rating(value: str) -> int | None:
    if not value.strip():
        return 0
    numeric = _rating(value.strip())
    if numeric is not None:
        return numeric
    stars = value.count("*") + value.count("★")
    return stars if 1 <= stars <= 5 else None


def _parse_text_ratings(text: str) -> tuple[list[RekordboxRatingTrack], dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    fields = {str(name or "").strip().casefold(): name for name in (reader.fieldnames or [])}
    required = {"track title", "artist", "rating", "time"}
    if not required.issubset(fields):
        raise RekordboxRatingImportError("The text export must include Track Title, Artist, Rating, and Time columns.")
    tracks: list[RekordboxRatingTrack] = []
    invalid = 0
    unknown = 0
    total = 0
    for row in reader:
        if not any(str(value or "").strip() for value in row.values()):
            continue
        total += 1
        parsed_rating = _text_rating(str(row.get(fields["rating"]) or ""))
        if parsed_rating is None:
            invalid += 1
            continue
        if parsed_rating == 0:
            unknown += 1
            continue
        title = str(row.get(fields["track title"]) or "").strip()
        artist = str(row.get(fields["artist"]) or "").strip()
        duration = _duration_seconds(str(row.get(fields["time"]) or ""))
        if not title or not artist or duration is None:
            invalid += 1
            continue
        tracks.append(
            RekordboxRatingTrack(
                source_track_id=str(row.get(fields.get("#", "")) or "").strip(),
                title=title,
                artist=artist,
                duration_seconds=duration,
                location="",
                rating=parsed_rating,
                comments="",
            )
        )
    return tracks, {
        "format": "txt",
        "total_export_tracks": total,
        "unrated_tracks": unknown,
        "invalid_rows": invalid,
    }


def _parse_xml_ratings(content: bytes, decoded: str) -> tuple[list[RekordboxRatingTrack], dict[str, Any]]:
    head = decoded[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise RekordboxRatingImportError("DTD and entity declarations are not supported.")
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as error:
        raise RekordboxRatingImportError("The selected file is not valid Rekordbox XML.") from error
    if root.tag != "DJ_PLAYLISTS":
        raise RekordboxRatingImportError("The selected XML is not a Rekordbox DJ_PLAYLISTS export.")
    nodes = root.findall("./COLLECTION/TRACK")
    tracks: list[RekordboxRatingTrack] = []
    invalid = 0
    unknown = 0
    for node in nodes:
        raw_rating = str(node.attrib.get("Rating") or "0").strip()
        parsed_rating = _rating(raw_rating)
        if parsed_rating is None:
            invalid += 1
            continue
        if parsed_rating == 0:
            unknown += 1
            continue
        try:
            duration = float(node.attrib["TotalTime"]) if node.attrib.get("TotalTime") else None
        except ValueError:
            duration = None
        tracks.append(
            RekordboxRatingTrack(
                source_track_id=str(node.attrib.get("TrackID") or ""),
                title=str(node.attrib.get("Name") or "").strip(),
                artist=str(node.attrib.get("Artist") or "").strip(),
                duration_seconds=duration,
                location=str(node.attrib.get("Location") or "").strip(),
                rating=parsed_rating,
                comments=str(node.attrib.get("Comments") or "").strip(),
            )
        )
    return tracks, {
        "format": "xml",
        "total_export_tracks": len(nodes),
        "unrated_tracks": unknown,
        "invalid_rows": invalid,
    }


def parse_rekordbox_ratings(content: bytes) -> tuple[list[RekordboxRatingTrack], dict[str, Any]]:
    """Parse a public Rekordbox XML or UTF-16 tab-separated text export."""
    if not content:
        raise RekordboxRatingImportError("The selected Rekordbox export is empty.")
    if len(content) > MAX_REKORDBOX_EXPORT_BYTES:
        raise RekordboxRatingImportError("The Rekordbox export exceeds the 32 MB import limit.")
    decoded = _decode_export(content)
    if decoded.lstrip().startswith("<"):
        return _parse_xml_ratings(content, decoded)
    return _parse_text_ratings(decoded)


def _location_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme.casefold() == "file":
        path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.casefold() not in {"", "localhost"}:
            path = f"//{parsed.netloc}{path}"
        return str(Path(path).expanduser().resolve(strict=False))
    if parsed.scheme:
        return ""
    return str(Path(unquote(value)).expanduser().resolve(strict=False))


def _metadata_key(title: str, artist: str, duration: float | None) -> tuple[str, str, int | None]:
    rounded = round(duration) if duration is not None and duration > 0 else None
    return normalize_identity_text(artist), normalize_identity_text(title), rounded


@dataclass
class RekordboxRatingSyncService:
    repository: Any
    invalidate_catalog: Any

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._previews: dict[str, dict[str, Any]] = {}

    def preview(self, content: bytes, filename: str = "collection.xml") -> dict[str, Any]:
        rows, parsing = parse_rekordbox_ratings(content)
        catalog = self.repository.list_downloaded_tracks()
        existing = {int(item["track_id"]): item for item in self.repository.external_track_ratings(REKORDBOX_SOURCE)}
        by_id = {int(item["id"]): item for item in catalog}
        by_path: dict[str, list[dict[str, Any]]] = {}
        by_version: dict[tuple[str, str], list[dict[str, Any]]] = {}
        by_metadata: dict[tuple[str, str, int | None], list[dict[str, Any]]] = {}
        for item in catalog:
            path = str(Path(str(item.get("file_path") or "")).expanduser().resolve(strict=False))
            by_path.setdefault(path, []).append(item)
            version_key = (
                str(item.get("recording_code") or "").upper(),
                str(item.get("version_code") or "").upper(),
            )
            if all(version_key):
                by_version.setdefault(version_key, []).append(item)
            by_metadata.setdefault(
                _metadata_key(
                    str(item.get("title") or ""),
                    str(item.get("artist") or ""),
                    item.get("duration_seconds"),
                ),
                [],
            ).append(item)

        proposed: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []
        match_counts: dict[str, int] = {}
        unchanged = 0
        for row in rows:
            matches: list[dict[str, Any]] = []
            method = ""
            confidence = 0.0
            direct = _DJLS_TRACK_ID.search(row.comments)
            version = _DJLS_VERSION_ID.search(row.comments)
            if direct and int(direct.group(1)) in by_id:
                matches, method, confidence = [by_id[int(direct.group(1))]], "catalog-identity", 1.0
            elif _location_path(row.location) in by_path:
                matches, method, confidence = by_path[_location_path(row.location)], "file-location", 1.0
            elif version:
                version_key = (version.group(1).upper(), version.group(2).upper())
                matches, method, confidence = by_version.get(version_key, []), "recording-version", 0.99
            else:
                metadata_key = _metadata_key(row.title, row.artist, row.duration_seconds)
                matches, method, confidence = by_metadata.get(metadata_key, []), "artist-title-duration", 0.95
            review = {
                "source_track_id": row.source_track_id,
                "title": row.title,
                "artist": row.artist,
                "rating": row.rating,
                "location": row.location,
            }
            if len(matches) != 1:
                if matches:
                    ambiguous.append({**review, "candidate_track_ids": [int(item["id"]) for item in matches]})
                else:
                    unmatched.append(review)
                continue
            match = matches[0]
            current = existing.get(int(match["id"]))
            is_unchanged = current is not None and int(current["rating"]) == row.rating
            unchanged += int(is_unchanged)
            match_counts[method] = match_counts.get(method, 0) + 1
            proposed.append(
                {
                    "track_id": int(match["id"]),
                    "catalog_title": str(match.get("title") or ""),
                    "catalog_artist": str(match.get("artist") or ""),
                    "source": REKORDBOX_SOURCE,
                    "source_track_id": row.source_track_id,
                    "rating": row.rating,
                    "match_method": method,
                    "confidence": confidence,
                    "source_location": row.location,
                    "unchanged": is_unchanged,
                }
            )
        token = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._previews = {
                token: {
                    "created_at": now,
                    "filename": Path(filename).name,
                    "ratings": proposed,
                }
            }
        return {
            "token": token,
            "filename": Path(filename).name,
            **parsing,
            "rated_tracks": len(rows),
            "matched_tracks": len(proposed),
            "proposed_changes": len(proposed) - unchanged,
            "unchanged_values": unchanged,
            "ambiguous_rows": len(ambiguous),
            "unmatched_rows": len(unmatched),
            "match_methods": match_counts,
            "matches": proposed[:100],
            "ambiguous": ambiguous[:100],
            "unmatched": unmatched[:100],
            "review_truncated": any(len(items) > 100 for items in (proposed, ambiguous, unmatched)),
        }

    def apply(self, token: str) -> dict[str, Any]:
        with self._lock:
            preview = self._previews.pop(token, None)
        if preview is None:
            raise RekordboxRatingImportError("This rating preview expired. Choose the XML file again.")
        synced_at = datetime.now(UTC).isoformat(timespec="seconds")
        ratings = [{**item, "synced_at": synced_at} for item in preview["ratings"] if not item.get("unchanged")]
        changed = self.repository.apply_external_track_ratings(ratings)
        self.repository.set_system_state(
            "rekordbox_rating_sync",
            json.dumps(
                {
                    "filename": preview["filename"],
                    "synced_at": synced_at,
                    "matched": len(preview["ratings"]),
                    "changed": changed,
                },
                separators=(",", ":"),
            ),
        )
        if changed:
            self.invalidate_catalog()
        return {"changed": changed, "matched": len(preview["ratings"]), "synced_at": synced_at, "status": self.status()}

    def status(self) -> dict[str, Any]:
        ratings = self.repository.external_track_ratings(REKORDBOX_SOURCE)
        counts = {str(stars): 0 for stars in range(1, 6)}
        for item in ratings:
            counts[str(int(item["rating"]))] += 1
        return {
            "source": REKORDBOX_SOURCE,
            "rated_tracks": len(ratings),
            "ratings": counts,
            "last_synced_at": max((str(item["synced_at"]) for item in ratings), default=None),
            "tracks": [
                {
                    key: item.get(key)
                    for key in (
                        "track_id",
                        "title",
                        "artist",
                        "recording_code",
                        "version_code",
                        "rating",
                        "match_method",
                        "confidence",
                        "synced_at",
                    )
                }
                for item in ratings[:100]
            ],
        }

    def clear(self) -> dict[str, Any]:
        removed = self.repository.clear_external_track_ratings(REKORDBOX_SOURCE)
        if removed:
            self.invalidate_catalog()
        return {"removed": removed, "status": self.status()}
