"""Set Builder catalog cache and authoritative vocabulary coordination."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from audioextender.set_builder.candidate_retriever import SET_BUILDER_CATALOG_VERSION
from audioextender.set_builder.genre_vocabulary import catalog_projection_vocabulary, normalize_genre_vocabulary


def catalog_schema_version() -> int:
    """Return the schema revision required by the running Set Builder."""
    return SET_BUILDER_CATALOG_VERSION


def build_catalog_payload(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    """Add schema identity and server-owned genre vocabulary to projections."""
    return {
        "version": SET_BUILDER_CATALOG_VERSION,
        "tracks": tracks,
        "total": len(tracks),
        "genre_vocabulary": catalog_projection_vocabulary(tracks),
    }


def current_catalog_payload(
    cache_path: Path,
    ensure_current: Callable[[], Any],
    write_cache: Callable[[], Any],
) -> dict[str, Any]:
    """Return a current catalog payload, rebuilding obsolete cache revisions."""
    ensure_current()
    payload = _read_payload(cache_path)
    if payload.get("version") != SET_BUILDER_CATALOG_VERSION:
        write_cache()
        payload = _read_payload(cache_path)
    return payload


def authoritative_catalog_vocabulary(
    cache_path: Path,
    ensure_current: Callable[[], Any],
    write_cache: Callable[[], Any],
    requested: Sequence[Any],
) -> list[dict[str, Any]]:
    """Prefer the server catalog vocabulary over a possibly stale browser copy."""
    payload = current_catalog_payload(cache_path, ensure_current, write_cache)
    server = payload.get("genre_vocabulary") or catalog_projection_vocabulary(payload.get("tracks") or [])
    return normalize_genre_vocabulary(server or requested)[:800]


def _read_payload(cache_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}
