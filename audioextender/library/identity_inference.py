"""Conservative musical-identity inference from catalog and analysis metadata."""

from __future__ import annotations

import re
from typing import Any


GENERIC_PLAYLISTS = {
    "imported singles", "soundcloud imports", "youtube imports", "spotify imports",
    "downloads", "downloaded", "music", "tracks", "favorites", "favourites",
}

RULES: tuple[tuple[str, str, tuple[str, ...], float], ...] = (
    ("cultural", "latin", ("latin", "latino", "reggaeton", "dembow", "salsa", "bachata", "cumbia", "guaracha"), .82),
    ("cultural", "ecuadorian", ("ecuador", "ecuadorian", "ecuatoriano"), .92),
    ("cultural", "colombian", ("colombia", "colombian", "colombiano"), .9),
    ("cultural", "caribbean", ("caribbean", "caribe", "dancehall", "reggae", "soca"), .82),
    ("cultural", "brazilian", ("brazil", "brazilian", "brasil", "funk carioca", "baile funk"), .9),
    ("cultural", "afro-influenced", ("afro", "afrobeats", "amapiano", "afro house"), .82),
    ("cultural", "indian / south asian", ("indian", "india", "bollywood", "hindi", "desi", "bhangra"), .9),
    ("rhythm", "dembow", ("dembow", "reggaeton", "perreo"), .9),
    ("rhythm", "cumbia rhythm", ("cumbia",), .92),
    ("rhythm", "salsa rhythm", ("salsa",), .92),
    ("rhythm", "latin percussion", ("latin house", "guaracha", "tribal house", "latin techno"), .78),
    ("rhythm", "four-on-the-floor", ("house", "techno", "trance", "disco"), .72),
    ("sound", "melodic", ("melodic", "progressive", "organic house"), .78),
    ("sound", "dark", ("dark", "industrial", "hard techno"), .8),
    ("sound", "tribal", ("tribal", "guaracha"), .82),
    ("sound", "bollywood pop", ("bollywood", "indian pop", "hindi pop"), .9),
    ("vocal", "spanish-language cues", ("spanish", "español", "latino vocal", "reggaeton", "salsa", "bachata"), .66),
    ("vocal", "hindi-language cues", ("hindi", "bollywood", "indian pop"), .68),
    ("role", "peak-time", ("peak time", "peak-time", "mainstage", "festival", "banger"), .83),
    ("role", "warm-up", ("warm up", "warm-up", "opening", "lounge"), .84),
    ("role", "closing", ("closing", "afterhours", "after hours", "sunrise"), .82),
)

ARTIST_CUES: tuple[tuple[tuple[str, ...], tuple[tuple[str, str, float], ...]], ...] = (
    (("skrillex",), (("sound", "bass-forward", .74), ("sound", "high-impact electronic", .68))),
    (("fred again",), (("sound", "emotive electronic", .74), ("sound", "vocal-sample driven", .7))),
    (("skrillex", "fred again"), (("context", "contemporary electronic crossover", .76), ("role", "festival-ready", .66))),
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


def infer_identity_descriptors(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explainable suggestions without asserting unsupported audio facts."""
    playlists = [str(value).strip() for value in context.get("playlists", []) if str(value).strip()]
    metadata_parts = [
        context.get("title"), context.get("artist"), context.get("filename"),
        context.get("genre"), context.get("genre_category"),
        context.get("library_category"), context.get("library_detail_genre"),
        context.get("library_roles"), context.get("energy_band"),
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
            "category": category, "value": value, "provenance": "inferred",
            "confidence": min(.98, confidence + (.04 if from_playlist else 0)),
            "reason": f"Matched {', '.join(matches[:2])} in {source}",
        }

    if any(needle in combined for needle in ("party", "dancefloor", "club", "banger")):
        suggestions.setdefault(("role", "party-ready"), {"category":"role","value":"party-ready","provenance":"inferred","confidence":.78,"reason":"Party or dancefloor context in metadata/playlist"})
    if any(needle in combined for needle in ("hit", "classic", "throwback", "anthem", "singalong", "popular", "viral", "tiktok")):
        suggestions.setdefault(("familiarity", "crowd-recognizable"), {"category":"familiarity","value":"crowd-recognizable","provenance":"inferred","confidence":.72,"reason":"Popularity/recognition cue in metadata or playlist; not verified chart data"})

    for required, cues in ARTIST_CUES:
        if all(artist in combined for artist in required):
            for category, value, confidence in cues:
                suggestions.setdefault((category, value), {"category":category,"value":value,"provenance":"inferred","confidence":confidence,"reason":f"Artist-crate cue: {' + '.join(required)}"})

    for playlist in playlists:
        normalized = _clean(playlist)
        if not normalized or normalized in GENERIC_PLAYLISTS or len(normalized) < 4:
            continue
        if normalized.endswith(" imports") or normalized.startswith("imported "):
            continue
        for context_value in _playlist_contexts(playlist):
            suggestions.setdefault(("context", context_value), {
                "category": "context", "value": context_value, "provenance": "crate",
                "confidence": .78, "reason": f'Normalized playlist/crate cue: "{playlist}"',
            })

    roles = [value for value in str(context.get("library_roles") or "").strip("|").split("|") if value]
    for role in roles:
        clean_role = _clean(role).replace("_", "-")
        if clean_role and clean_role not in {"live timing", "steady timing", "variable timing"}:
            suggestions.setdefault(("role", clean_role), {
                "category": "role", "value": clean_role, "provenance": "inferred",
                "confidence": .86, "reason": "Derived from DJ analysis role",
            })
    vocals = _clean(context.get("vocals"))
    if vocals and vocals not in {"all", "unknown"}:
        suggestions.setdefault(("vocal", vocals), {
            "category": "vocal", "value": vocals, "provenance": "inferred",
            "confidence": .8, "reason": "Derived from vocal-density analysis",
        })
    timing = _clean(context.get("timing"))
    if timing in {"steady", "variable", "live", "variable/live"}:
        value = "steady / griddable" if timing == "steady" else "live timing"
        suggestions.setdefault(("sound", value), {
            "category": "sound", "value": value, "provenance": "inferred",
            "confidence": .84, "reason": "Derived from timing analysis",
        })
    return sorted(suggestions.values(), key=lambda item: (item["category"], -item["confidence"], item["value"]))
