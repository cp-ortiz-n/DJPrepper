"""Conservative musical-identity inference from catalog and analysis metadata."""

from __future__ import annotations

import re
from typing import Any

GENERIC_PLAYLISTS = {
    "imported singles",
    "soundcloud imports",
    "youtube imports",
    "spotify imports",
    "downloads",
    "downloaded",
    "music",
    "tracks",
    "favorites",
    "favourites",
}

PLAYLIST_NOISE_WORDS = {
    "a",
    "and",
    "best",
    "by",
    "for",
    "from",
    "in",
    "las",
    "latest",
    "lo",
    "mejores",
    "mix",
    "mixes",
    "of",
    "on",
    "playlist",
    "popular",
    "songs",
    "spotify",
    "the",
    "tiktok",
    "track",
    "tracks",
    "transitions",
    "viral",
    "with",
}

KNOWN_PLAYLIST_WORDS = {
    "afro",
    "afrobeats",
    "after",
    "afterhours",
    "amapiano",
    "anthem",
    "bachata",
    "bhangra",
    "bollywood",
    "boiler",
    "brazil",
    "brazilian",
    "caribbean",
    "classic",
    "club",
    "colombia",
    "colombian",
    "cumbia",
    "dance",
    "dancefloor",
    "dembow",
    "desi",
    "disco",
    "ecuador",
    "ecuadorian",
    "electronic",
    "festival",
    "funk",
    "guaracha",
    "gym",
    "hard",
    "hindi",
    "hit",
    "hits",
    "house",
    "indian",
    "latin",
    "live",
    "lounge",
    "merengue",
    "party",
    "rave",
    "reggae",
    "reggaeton",
    "remix",
    "remixes",
    "room",
    "running",
    "salsa",
    "scratch",
    "set",
    "singalong",
    "skratch",
    "soca",
    "techno",
    "throwback",
    "tribal",
    "turntablism",
    "uk",
    "workout",
}

RULES: tuple[tuple[str, str, tuple[str, ...], float], ...] = (
    ("cultural", "latin", ("latin", "latino", "reggaeton", "dembow", "salsa", "bachata", "cumbia", "guaracha"), 0.82),
    ("cultural", "ecuadorian", ("ecuador", "ecuadorian", "ecuatoriano"), 0.92),
    ("cultural", "colombian", ("colombia", "colombian", "colombiano"), 0.9),
    ("cultural", "caribbean", ("caribbean", "caribe", "dancehall", "reggae", "soca"), 0.82),
    ("cultural", "brazilian", ("brazil", "brazilian", "brasil", "funk carioca", "baile funk"), 0.9),
    ("cultural", "afro-influenced", ("afro", "afrobeats", "amapiano", "afro house"), 0.82),
    ("cultural", "indian / south asian", ("indian", "india", "bollywood", "hindi", "desi", "bhangra"), 0.9),
    ("rhythm", "dembow", ("dembow", "reggaeton", "perreo"), 0.9),
    ("rhythm", "cumbia rhythm", ("cumbia",), 0.92),
    ("rhythm", "salsa rhythm", ("salsa",), 0.92),
    ("rhythm", "latin percussion", ("latin house", "guaracha", "tribal house", "latin techno"), 0.78),
    ("rhythm", "four-on-the-floor", ("house", "techno", "trance", "disco"), 0.72),
    ("sound", "melodic", ("melodic", "progressive", "organic house"), 0.78),
    ("sound", "dark", ("dark", "industrial", "hard techno"), 0.8),
    ("sound", "tribal", ("tribal", "guaracha"), 0.82),
    ("sound", "bollywood pop", ("bollywood", "indian pop", "hindi pop"), 0.9),
    ("vocal", "spanish-language cues", ("spanish", "español", "latino vocal", "reggaeton", "salsa", "bachata"), 0.66),
    ("vocal", "hindi-language cues", ("hindi", "bollywood", "indian pop"), 0.68),
    ("role", "peak-time", ("peak time", "peak-time", "mainstage", "festival", "banger"), 0.83),
    ("role", "warm-up", ("warm up", "warm-up", "opening", "lounge"), 0.84),
    ("role", "closing", ("closing", "afterhours", "after hours", "sunrise"), 0.82),
)

ARTIST_CUES: tuple[tuple[tuple[str, ...], tuple[tuple[str, str, float], ...]], ...] = (
    (("skrillex",), (("sound", "bass-forward", 0.74), ("sound", "high-impact electronic", 0.68))),
    (("fred again",), (("sound", "emotive electronic", 0.74), ("sound", "vocal-sample driven", 0.7))),
    (
        ("skrillex", "fred again"),
        (("context", "contemporary electronic crossover", 0.76), ("role", "festival-ready", 0.66)),
    ),
)


def _clean(value: Any) -> str:
    value = re.sub(r"[_]+", " ", str(value or "").strip())
    return re.sub(r"\s+", " ", value).casefold()


def _playlist_contexts(value: str) -> list[str]:
    normalized = _clean(value)
    contexts: list[str] = []
    if "party" in normalized:
        if any(word in normalized for word in ("indian", "bollywood", "hindi", "desi")):
            contexts.append("indian party")
        elif any(word in normalized for word in ("ecuador", "ecuadorian", "ecuatoriano")):
            contexts.append("ecuadorian party")
        elif "latin" in normalized:
            contexts.append("latin party")
        else:
            contexts.append("party")
    controlled = (
        ("workout / gym", ("workout", "gym")),
        ("rave", ("rave",)),
        ("dancefloor", ("dancefloor", "dance floor")),
        ("scratch practice", ("scratch", "skratch")),
        ("turntablism", ("turntablism",)),
        ("running", ("running",)),
        ("boiler room / live set", ("boiler room", "live set")),
        ("after-hours", ("afterhours", "after hours")),
    )
    for context, needles in controlled:
        if any(needle in normalized for needle in needles) and context not in contexts:
            contexts.append(context)
    return contexts


def unknown_playlist_signals(playlists: list[str]) -> list[str]:
    """Return reviewable playlist words that are neither known cues nor formatting noise."""
    unknown: set[str] = set()
    for playlist in playlists:
        normalized = _clean(playlist)
        for token in re.findall(r"[a-zà-ÿ][a-z0-9à-ÿ'-]{2,}", normalized):
            if token in PLAYLIST_NOISE_WORDS or token in KNOWN_PLAYLIST_WORDS:
                continue
            if token.isdigit() or re.fullmatch(r"20\d{2}", token):
                continue
            unknown.add(token.strip("-_'"))
    return sorted(value for value in unknown if value)


def infer_identity_descriptors(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explainable suggestions without asserting unsupported audio facts."""
    playlists = [str(value).strip() for value in context.get("playlists", []) if str(value).strip()]
    metadata_parts = [
        context.get("title"),
        context.get("artist"),
        context.get("filename"),
        context.get("genre"),
        context.get("genre_category"),
        context.get("library_category"),
        context.get("library_detail_genre"),
        context.get("library_roles"),
        context.get("energy_band"),
    ]
    metadata_text = _clean(" ".join(str(value or "") for value in metadata_parts))
    playlist_text = _clean(" ".join(playlists))
    combined = f"{metadata_text} {playlist_text}".strip()
    suggestions: dict[tuple[str, str], dict[str, Any]] = {}

    for category, value, needles, confidence in RULES:
        matches = [needle for needle in needles if needle in combined]
        if not matches:
            continue
        from_playlist = any(needle in playlist_text for needle in matches)
        source = "playlist" if from_playlist else "catalog metadata"
        suggestions[(category, value)] = {
            "category": category,
            "value": value,
            "provenance": "inferred",
            "confidence": min(0.98, confidence + (0.04 if from_playlist else 0)),
            "reason": f"Matched {', '.join(matches[:2])} in {source}",
        }

    if any(needle in combined for needle in ("party", "dancefloor", "club", "banger")):
        suggestions.setdefault(
            ("role", "party-ready"),
            {
                "category": "role",
                "value": "party-ready",
                "provenance": "inferred",
                "confidence": 0.78,
                "reason": "Party or dancefloor context in metadata/playlist",
            },
        )
    if any(
        needle in combined
        for needle in ("hit", "classic", "throwback", "anthem", "singalong", "popular", "viral", "tiktok")
    ):
        suggestions.setdefault(
            ("familiarity", "crowd-recognizable"),
            {
                "category": "familiarity",
                "value": "crowd-recognizable",
                "provenance": "inferred",
                "confidence": 0.72,
                "reason": "Popularity/recognition cue in metadata or playlist; not verified chart data",
            },
        )

    for required, cues in ARTIST_CUES:
        if all(artist in combined for artist in required):
            for category, value, confidence in cues:
                suggestions.setdefault(
                    (category, value),
                    {
                        "category": category,
                        "value": value,
                        "provenance": "inferred",
                        "confidence": confidence,
                        "reason": f"Artist-crate cue: {' + '.join(required)}",
                    },
                )

    unknown_signals = set(unknown_playlist_signals(playlists))
    for rule in context.get("vocabulary_rules", []) or []:
        signal = _clean(rule.get("signal"))
        if signal not in unknown_signals:
            continue
        category, value = _clean(rule.get("category")), _clean(rule.get("value"))
        if category and value:
            suggestions[(category, value)] = {
                "category": category,
                "value": value,
                "provenance": "inferred",
                "confidence": float(rule.get("confidence") or 0.8),
                "reason": f'Approved identity vocabulary: "{signal}"',
            }

    for playlist in playlists:
        normalized = _clean(playlist)
        if not normalized or normalized in GENERIC_PLAYLISTS or len(normalized) < 4:
            continue
        if normalized.endswith(" imports") or normalized.startswith("imported "):
            continue
        for context_value in _playlist_contexts(playlist):
            suggestions.setdefault(
                ("context", context_value),
                {
                    "category": "context",
                    "value": context_value,
                    "provenance": "crate",
                    "confidence": 0.78,
                    "reason": f'Normalized playlist/crate cue: "{playlist}"',
                },
            )

    roles = [value for value in str(context.get("library_roles") or "").strip("|").split("|") if value]
    for role in roles:
        clean_role = _clean(role).replace("_", "-")
        if clean_role and clean_role not in {"live timing", "steady timing", "variable timing"}:
            suggestions.setdefault(
                ("role", clean_role),
                {
                    "category": "role",
                    "value": clean_role,
                    "provenance": "inferred",
                    "confidence": 0.86,
                    "reason": "Derived from DJ analysis role",
                },
            )
    vocals = _clean(context.get("vocals"))
    if vocals and vocals not in {"all", "unknown"}:
        suggestions.setdefault(
            ("vocal", vocals),
            {
                "category": "vocal",
                "value": vocals,
                "provenance": "inferred",
                "confidence": 0.8,
                "reason": "Derived from vocal-density analysis",
            },
        )
    timing = _clean(context.get("timing"))
    if timing in {"steady", "variable", "live", "variable/live"}:
        value = "steady / griddable" if timing == "steady" else "live timing"
        suggestions.setdefault(
            ("sound", value),
            {
                "category": "sound",
                "value": value,
                "provenance": "inferred",
                "confidence": 0.84,
                "reason": "Derived from timing analysis",
            },
        )
    return sorted(suggestions.values(), key=lambda item: (item["category"], -item["confidence"], item["value"]))
