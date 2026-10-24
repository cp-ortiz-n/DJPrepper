"""Catalog-derived genre vocabulary for Set Builder interpretation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def normalize_genre_term(value: Any) -> str:
    """Normalize a genre or alias for deterministic comparison."""
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", str(value or "").strip().lower()).split())


@dataclass(frozen=True)
class GenreVocabularyEntry:
    """One catalog genre and the names actually associated with it."""

    canonical: str
    aliases: tuple[str, ...]
    count: int = 0


def _mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        result = model_dump()
        return result if isinstance(result, Mapping) else None
    return None


def normalize_genre_vocabulary(values: Sequence[Any]) -> list[dict[str, Any]]:
    """Return a stable JSON-ready vocabulary while retaining legacy strings."""
    merged: dict[str, dict[str, Any]] = {}
    for value in values:
        item = _mapping(value)
        canonical = normalize_genre_term(item.get("canonical")) if item else normalize_genre_term(value)
        if not canonical:
            continue
        aliases = item.get("aliases", []) if item else []
        normalized_aliases = {alias for alias in (normalize_genre_term(alias) for alias in aliases) if alias}
        normalized_aliases.add(canonical)
        current = merged.setdefault(canonical, {"canonical": canonical, "aliases": set(), "count": 0})
        current["aliases"].update(normalized_aliases)
        try:
            current["count"] += max(0, int(item.get("count", 0))) if item else 0
        except (TypeError, ValueError):
            pass
    return [
        {
            "canonical": item["canonical"],
            "aliases": sorted(item["aliases"], key=lambda alias: (-len(alias), alias)),
            "count": item["count"],
        }
        for item in sorted(merged.values(), key=lambda item: (-item["count"], item["canonical"]))
    ]


def vocabulary_entries(values: Sequence[Any]) -> list[GenreVocabularyEntry]:
    """Return typed entries for matching and canonicalization."""
    return [
        GenreVocabularyEntry(
            canonical=item["canonical"],
            aliases=tuple(item["aliases"]),
            count=item["count"],
        )
        for item in normalize_genre_vocabulary(values)
    ]


def canonical_genres(values: Sequence[Any]) -> list[str]:
    """Return only canonical catalog genre names."""
    return [entry.canonical for entry in vocabulary_entries(values)]


def resolve_catalog_genre(value: Any, vocabulary: Sequence[Any]) -> str:
    """Resolve a provider value through catalog-derived aliases."""
    raw = normalize_genre_term(value)
    if not raw:
        return ""
    candidates: list[tuple[int, int, int, str]] = []
    for entry in vocabulary_entries(vocabulary):
        for alias in entry.aliases:
            if raw == alias or alias in raw:
                candidates.append((int(raw == entry.canonical), len(alias), entry.count, entry.canonical))
    return max(candidates, default=(0, 0, 0, ""))[-1]


def explicit_genre_mentions(
    brief: str,
    vocabulary: Sequence[Any],
    *,
    excluded: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """Resolve explicit brief phrases through the current catalog taxonomy."""
    normalized = normalize_genre_term(brief)
    mentions: list[tuple[int, int, str, bool, int]] = []
    for entry in vocabulary_entries(vocabulary):
        if entry.canonical in excluded:
            continue
        for alias in entry.aliases:
            pattern = rf"(?<![a-z0-9&]){re.escape(alias)}(?![a-z0-9&])"
            mentions.extend(
                (match.start(), match.end(), entry.canonical, alias == entry.canonical, entry.count)
                for match in re.finditer(pattern, normalized)
            )
    by_span: dict[tuple[int, int], tuple[int, int, str, bool, int]] = {}
    for mention in mentions:
        span = mention[:2]
        current = by_span.get(span)
        if current is None or (mention[3], mention[4], len(mention[2])) > (
            current[3],
            current[4],
            len(current[2]),
        ):
            by_span[span] = mention
    unambiguous = list(by_span.values())
    unnested = [
        mention
        for mention in unambiguous
        if not any(
            other[2] != mention[2]
            and other[0] <= mention[0]
            and other[1] >= mention[1]
            and other[1] - other[0] > mention[1] - mention[0]
            for other in unambiguous
        )
    ]
    ordered: list[str] = []
    for _, _, genre, _, _ in sorted(unnested, key=lambda item: (item[0], -(item[1] - item[0]))):
        if genre not in ordered:
            ordered.append(genre)
    return ordered
