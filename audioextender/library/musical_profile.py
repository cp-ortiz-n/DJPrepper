"""Authoritative, versioned musical facts shared by backend and browser."""

from __future__ import annotations

import re
from typing import Any

MUSICAL_PROFILE_VERSION = 1

CAMELOT_KEYS = {
    "A minor": "8A",
    "E minor": "9A",
    "B minor": "10A",
    "F# minor": "11A",
    "C# minor": "12A",
    "G# minor": "1A",
    "D# minor": "2A",
    "A# minor": "3A",
    "F minor": "4A",
    "C minor": "5A",
    "G minor": "6A",
    "D minor": "7A",
    "C major": "8B",
    "G major": "9B",
    "D major": "10B",
    "A major": "11B",
    "E major": "12B",
    "B major": "1B",
    "F# major": "2B",
    "C# major": "3B",
    "G# major": "4B",
    "D# major": "5B",
    "A# major": "6B",
    "F major": "7B",
}


def normalize_key(value: object) -> str:
    return (
        str(value or "")
        .replace("Db ", "C# ", 1)
        .replace("Eb ", "D# ", 1)
        .replace("Gb ", "F# ", 1)
        .replace("Ab ", "G# ", 1)
        .replace("Bb ", "A# ", 1)
    )


def energy_band(value: float) -> str:
    return "high" if value >= 0.67 else "low" if value < 0.4 else "medium"


def musical_profile(song: dict[str, Any]) -> dict[str, Any]:
    key = normalize_key(song.get("key") or song.get("musical_key"))
    roles = _roles(song)
    energy, energy_source = _energy(song)
    vocals, vocals_source = _vocals(song)
    timing, timing_source = _timing(song)
    key_confidence = _bounded(song.get("key_confidence"), 0.0)
    return {
        "version": MUSICAL_PROFILE_VERSION,
        "key": key,
        "camelot": CAMELOT_KEYS.get(key, ""),
        "energy": energy,
        "energy_band": energy_band(energy),
        "roles": roles,
        "vocals": vocals,
        "timing": timing,
        "confidence": {
            "key": key_confidence,
            "energy": 1.0 if energy_source == "serialized" else 0.8 if energy_source == "analysis" else 0.55,
            "roles": 1.0 if song.get("_roles") else 0.75,
            "vocals": 1.0 if vocals_source == "serialized" else 0.7,
            "timing": 1.0 if timing_source == "serialized" else 0.8,
        },
        "provenance": {
            "key": "analysis" if key else "unknown",
            "energy": energy_source,
            "roles": "serialized" if song.get("_roles") else "derived",
            "vocals": vocals_source,
            "timing": timing_source,
        },
    }


def _roles(song: dict[str, Any]) -> list[str]:
    if isinstance(song.get("_roles"), list) and song["_roles"]:
        return list(dict.fromkeys(str(value) for value in song["_roles"]))
    style = str(song.get("detected_style") or "").casefold()
    timing = str(song.get("timing") or "").casefold()
    bpm = float(song.get("bpm") or 0)
    intro, outro = song.get("intro") or {}, song.get("outro") or {}
    roles: set[str] = set()
    if "ambient" in style or "sparse" in style:
        roles.add("ambient")
    if "melodic" in style or "harmonic" in style or float(song.get("key_confidence") or 0) >= 0.65:
        roles.add("melodic")
    if (
        "vocal-safe" in style
        or max(float(intro.get("instrumentalness") or 0), float(outro.get("instrumentalness") or 0)) >= 0.72
    ):
        roles.add("vocal-safe")
    if "live" in timing or "variable" in timing or float(song.get("tempo_drift") or 0) >= 0.08:
        roles.add("live timing")
    if "peak" in style or "high-energy" in style or (bpm >= 122 and "ambient" not in roles):
        roles.add("peak-time")
    if "slow" in style or "subtle" in style or (bpm and bpm < 120) or "ambient" in roles:
        roles.add("warm-up")
    readiness = song.get("dj_readiness") or {}
    if "closing" in style or float(readiness.get("outro_mixable_bars") or 0) >= 8 or outro.get("section") == "closing":
        roles.add("closing")
    if not roles:
        roles.add("peak-time" if bpm >= 122 else "warm-up")
    return sorted(roles)


def _energy(song: dict[str, Any]) -> tuple[float, str]:
    if _finite(song.get("_energy")):
        return float(song["_energy"]), "serialized"
    values = []
    for section in song.get("section_profiles") or []:
        match = re.search(r"energy\s+([\d.]+)", str(section.get("reason") or ""), re.I)
        if match:
            try:
                values.append(float(match.group(1)))
            except ValueError:
                pass
    if values:
        return sum(values) / len(values), "analysis"
    style = str(song.get("detected_style") or "").casefold()
    return (
        0.8 if "high-energy" in style or "peak" in style else 0.25 if "ambient" in style or "sparse" in style else 0.5
    ), "derived"


def _vocals(song: dict[str, Any]) -> tuple[str, str]:
    if song.get("_vocals"):
        return str(song["_vocals"]), "serialized"
    intro, outro = song.get("intro") or {}, song.get("outro") or {}
    instrumental = max(float(intro.get("instrumentalness") or 0), float(outro.get("instrumentalness") or 0))
    return ("vocal-safe" if instrumental >= 0.72 else "vocal-forward" if instrumental < 0.45 else "mixed"), "derived"


def _timing(song: dict[str, Any]) -> tuple[str, str]:
    if song.get("_timing"):
        return str(song["_timing"]), "serialized"
    timing = str(song.get("timing") or "").casefold()
    value = (
        "variable"
        if "live" in timing or "variable" in timing or float(song.get("tempo_drift") or 0) >= 0.08
        else "steady"
    )
    return value, "analysis" if timing or song.get("tempo_drift") is not None else "derived"


def _finite(value: Any) -> bool:
    try:
        return value is not None and float(value) == float(value)
    except (TypeError, ValueError):
        return False


def _bounded(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
