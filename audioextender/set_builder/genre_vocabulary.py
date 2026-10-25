"""Catalog-derived genre vocabulary for Set Builder interpretation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def normalize_genre_term(value: Any) -> str:
    """Normalize a genre or alias for deterministic comparison."""
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", str(value or "").strip().lower()).split())


def _contains_phrase(value: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9&]){re.escape(phrase)}(?![a-z0-9&])", value))


def _canonical_alias_affinity(canonical: str, alias: str) -> int:
    if _contains_phrase(canonical, alias):
        return 2
    canonical_tokens = [token for token in canonical.split() if len(token) >= 4]
    alias_tokens = [token for token in alias.split() if len(token) >= 4]
    return int(
        any(left.startswith(right) or right.startswith(left) for left in canonical_tokens for right in alias_tokens)
    )


@dataclass(frozen=True)
class GenreVocabularyEntry:
    """One catalog genre and the names actually associated with it."""

    canonical: str
    aliases: tuple[str, ...]
    count: int = 0
    alias_counts: tuple[tuple[str, int], ...] = ()


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
        current = merged.setdefault(
            canonical,
            {"canonical": canonical, "aliases": set(), "alias_counts": {}, "count": 0},
        )
        current["aliases"].update(normalized_aliases)
        for alias, count in (item.get("aliasCounts", {}) if item else {}).items():
            normalized = normalize_genre_term(alias)
            if not normalized:
                continue
            try:
                current["alias_counts"][normalized] = current["alias_counts"].get(normalized, 0) + max(0, int(count))
            except (TypeError, ValueError):
                continue
        try:
            current["count"] += max(0, int(item.get("count", 0))) if item else 0
        except (TypeError, ValueError):
            pass
    return [
        {
            "canonical": item["canonical"],
            "aliases": sorted(item["aliases"], key=lambda alias: (-len(alias), alias)),
            "count": item["count"],
            **({"aliasCounts": item["alias_counts"]} if item["alias_counts"] else {}),
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
            alias_counts=tuple(item.get("aliasCounts", {}).items()),
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
    candidates: list[tuple[int, int, int, int, int, str]] = []
    for entry in vocabulary_entries(vocabulary):
        alias_counts = dict(entry.alias_counts)
        for alias in entry.aliases:
            if raw == alias or alias in raw:
                canonical_affinity = _canonical_alias_affinity(entry.canonical, alias)
                candidates.append(
                    (
                        int(raw == entry.canonical),
                        canonical_affinity,
                        len(alias),
                        alias_counts.get(alias, entry.count),
                        entry.count,
                        entry.canonical,
                    )
                )
    return max(candidates, default=(0, 0, 0, 0, 0, ""))[-1]


def explicit_genre_mentions(
    brief: str,
    vocabulary: Sequence[Any],
    *,
    excluded: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """Resolve explicit brief phrases through the current catalog taxonomy."""
    normalized = normalize_genre_term(brief)
    mentions: list[tuple[int, int, str, bool, int, int, int]] = []
    for entry in vocabulary_entries(vocabulary):
        if entry.canonical in excluded:
            continue
        alias_counts = dict(entry.alias_counts)
        for alias in entry.aliases:
            pattern = rf"(?<![a-z0-9&]){re.escape(alias)}(?![a-z0-9&])"
            mentions.extend(
                (
                    match.start(),
                    match.end(),
                    entry.canonical,
                    alias == entry.canonical,
                    _canonical_alias_affinity(entry.canonical, alias),
                    alias_counts.get(alias, entry.count),
                    entry.count,
                )
                for match in re.finditer(pattern, normalized)
            )
    by_span: dict[tuple[int, int], tuple[int, int, str, bool, int, int, int]] = {}
    for mention in mentions:
        span = mention[:2]
        current = by_span.get(span)
        if current is None or (mention[3], mention[4], mention[5], mention[6], len(mention[2])) > (
            current[3],
            current[4],
            current[5],
            current[6],
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
    for _, _, genre, _, _, _, _ in sorted(unnested, key=lambda item: (item[0], -(item[1] - item[0]))):
        if genre not in ordered:
            ordered.append(genre)
    return ordered


_NEGATIVE_GENRE_CUE = re.compile(
    r"\b(?:no|not|without|avoid(?:ing)?|exclude(?:d|s|ing)?|free of|do not play|don t play)\b"
)
_NEGATIVE_GENRE_STOP = re.compile(r"\b(?:but|however|instead|except|only)\b")
_OPENING_CUE = re.compile(r"\b(?:warm ?up|opening|start|begin|first)\b")


def excluded_genre_mentions(brief: str, vocabulary: Sequence[Any]) -> list[str]:
    """Return catalog identities rejected by generic negative language."""
    rejected: list[str] = []
    for clause in re.split(r"[.!?;,]", brief):
        normalized = normalize_genre_term(clause)
        cue = _NEGATIVE_GENRE_CUE.search(normalized)
        if cue is None:
            continue
        tail = _NEGATIVE_GENRE_STOP.split(normalized[cue.end() :], maxsplit=1)[0]
        for genre in explicit_genre_mentions(tail, vocabulary):
            if genre not in rejected:
                rejected.append(genre)
    return rejected


def opening_genre_mentions(brief: str, vocabulary: Sequence[Any]) -> list[str]:
    """Return catalog identities explicitly assigned to the opening or warm-up."""
    opening: list[str] = []
    for clause in re.split(r"[.!?;,]|\bthen\b|\bfrom there\b", brief, flags=re.IGNORECASE):
        normalized = normalize_genre_term(clause)
        if not _OPENING_CUE.search(normalized):
            continue
        for genre in explicit_genre_mentions(clause, vocabulary):
            if genre not in opening:
                opening.append(genre)
    return opening
