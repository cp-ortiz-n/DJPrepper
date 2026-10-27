"""Derive explainable musical-identity tags from durable playlist membership."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from itertools import combinations
from typing import Any

_IGNORED_GENRE_TERMS = {"all", "general", "other", "unknown", "unclassified"}


def _normalize(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", str(value or "").casefold()).split())


def _identity_tokens(value: str) -> list[str]:
    """Return comparable words while ignoring punctuation-only joiners."""
    return re.findall(r"[a-z0-9]+", value)


def _tokens_match(left: str, right: str) -> bool:
    """Match exact words plus conservative one-letter inflections.

    This keeps playlist interpretation catalog-driven while allowing common
    variants such as ``latin``/``latino`` and ``funk``/``funky``. Broader
    stemming would make short or unrelated playlist words unsafe evidence.
    """
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 4 and len(longer) == len(shorter) + 1 and longer.startswith(shorter)


def _contains_vocabulary_term(playlist: str, term: str) -> bool:
    """Return whether all words of a catalog term occur in any order."""
    playlist_tokens = _identity_tokens(playlist)
    term_tokens = _identity_tokens(term)
    if not playlist_tokens or not term_tokens:
        return False
    unused = set(range(len(playlist_tokens)))
    for term_token in term_tokens:
        match = next(
            (index for index in unused if _tokens_match(term_token, playlist_tokens[index])),
            None,
        )
        if match is None:
            return False
        unused.remove(match)
    return True


def catalog_genre_terms(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return the genre vocabulary already evidenced by catalog records."""
    terms: set[str] = set()
    for record in records:
        category_parts = str(record.get("category") or record.get("genre") or "").split("/")
        detail_parts = str(record.get("detail_genre") or record.get("detailed_genre") or "").split(",")
        for raw_term in [*category_parts, *detail_parts]:
            normalized = _normalize(raw_term)
            if not normalized or normalized in _IGNORED_GENRE_TERMS:
                continue
            terms.add(normalized)
            terms.update(
                component
                for component in (_normalize(value) for value in re.split(r"\s+(?:&|and)\s+", normalized))
                if component and component not in _IGNORED_GENRE_TERMS
            )
    return sorted(terms, key=lambda value: (-len(value), value))


def playlist_genre_identity_tags(playlists: Iterable[str], genre_terms: Iterable[str]) -> list[dict[str, Any]]:
    """Build lower-confidence genre identity tags from meaningful playlist words.

    Tags are derived from the current catalog vocabulary, not a fixed alias map.
    Compound combinations let a crate such as ``Latin Bounce Techno`` support a
    ``Latin Techno`` request while leaving the track's canonical genre intact.
    """
    vocabulary = {
        normalized
        for normalized in (_normalize(value) for value in genre_terms)
        if normalized and normalized not in _IGNORED_GENRE_TERMS
    }
    tags: dict[tuple[str, str], dict[str, Any]] = {}
    for playlist in playlists:
        source = str(playlist or "").strip()
        normalized_playlist = _normalize(source)
        if not source or not normalized_playlist:
            continue
        matches: list[tuple[int, int, str]] = []
        for term in vocabulary:
            pattern = rf"(?<![a-z0-9&]){re.escape(term)}(?![a-z0-9&])"
            matches.extend((match.start(), match.end(), term) for match in re.finditer(pattern, normalized_playlist))
        ordered = sorted(set(matches), key=lambda item: (item[0], item[1], item[2]))
        candidates: set[str] = {term for term in vocabulary if _contains_vocabulary_term(normalized_playlist, term)}
        candidates.update(term for _, _, term in ordered)
        for size in range(2, min(3, len(ordered)) + 1):
            for selected in combinations(ordered, size):
                if any(left[1] > right[0] for left, right in zip(selected, selected[1:], strict=False)):
                    continue
                candidates.add(" ".join(item[2] for item in selected))
        for value in candidates:
            key = (value, source.casefold())
            tags[key] = {
                "value": value,
                "source": source,
                "provenance": "playlist",
                "confidence": 0.78 if " " in value else 0.68,
            }
    return sorted(tags.values(), key=lambda item: (str(item["value"]), str(item["source"]).casefold()))


def playlist_identity_projection(raw_playlists: Any, genre_terms: Iterable[str]) -> dict[str, Any]:
    """Translate a persisted playlist JSON value into the Set Builder projection."""
    try:
        values = raw_playlists if isinstance(raw_playlists, list) else json.loads(str(raw_playlists or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        values = []
    if not isinstance(values, list):
        values = []
    playlists = [str(value).strip() for value in values if str(value).strip()]
    return {
        "playlists": playlists,
        "playlist_identity": playlist_genre_identity_tags(playlists, genre_terms),
    }
