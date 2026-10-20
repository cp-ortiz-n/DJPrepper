"""Presentation mapping for downloaded catalog records."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


def downloaded_track_payload(
    track: dict,
    *,
    generalized_genre: Callable[[str], str],
    normalize_genre_category: Callable[[str], str],
) -> dict:
    """Hide storage internals and add availability/review fields for HTTP clients."""
    suggested_genre = generalized_genre(str(track.get("genre") or ""))
    current_genre = normalize_genre_category(str(track.get("genre_category") or "Other"))
    try:
        descriptors = json.loads(str(track.get("descriptors_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        descriptors = []
    return {
        key: value for key, value in track.items() if key not in {"file_path", "artwork_path", "descriptors_json"}
    } | {
        "absolute_path": str(Path(str(track.get("file_path") or "")).expanduser().resolve()),
        "available": Path(str(track.get("file_path") or "")).is_file(),
        "artwork_available": bool(track.get("artwork_path")) and Path(str(track["artwork_path"])).is_file(),
        "genre_category": current_genre,
        "suggested_genre": suggested_genre,
        "needs_genre": current_genre in {"Other", "Latin / Other"},
        "descriptors": descriptors,
    }
