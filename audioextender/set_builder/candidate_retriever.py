"""Build bounded, explainable candidate pools for each set journey section."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SET_BUILDER_CATALOG_VERSION = 4


def _terms(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [
        term
        for item in values
        for raw in re.split(r"[,/|]", str(item or ""))
        if (term := raw.strip().casefold())
    ]


def _track_id(item: dict[str, Any]) -> str:
    downloaded_id = item.get("downloaded_id") or (item.get("downloaded") or {}).get("id")
    if downloaded_id is not None:
        return f"downloaded:{downloaded_id}"
    job_id = (item.get("job") or {}).get("id")
    return f"job:{job_id}" if job_id is not None else ""


def _selected_path(item: dict[str, Any]) -> str:
    job = item.get("job") or {}
    return str(job.get("library_path") or job.get("wav_path") or job.get("source_path") or "")


def _descriptors(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw = item.get("descriptors") or []
    return [descriptor for descriptor in raw if isinstance(descriptor, dict)]


def _compact_track(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("analysis") or {}
    job = item.get("job") or {}
    descriptors = _descriptors(item)
    path = _selected_path(item)
    return {
        "id": _track_id(item),
        "title": str(
            analysis.get("title") or Path(str(analysis.get("source_name") or job.get("source_name") or "")).stem
        ),
        "artist": str(analysis.get("artist") or ""),
        "genre": str(item.get("genre") or "Other"),
        "detailedGenres": _terms(item.get("detailed_genre")),
        "descriptors": [
            {
                "category": str(value.get("category") or ""),
                "value": str(value.get("value") or ""),
                "provenance": str(value.get("provenance") or "inferred"),
                "confidence": float(value.get("confidence") or 0),
            }
            for value in descriptors
            if value.get("value")
        ],
        "bpm": round(float(analysis.get("bpm") or 0), 2),
        "key": str(analysis.get("key") or ""),
        "camelot": str(analysis.get("_camelot") or ""),
        "energy": round(float(analysis.get("_energy") or 0.5), 3),
        "durationSeconds": round(float(analysis.get("duration_seconds") or 0), 2),
        "vocals": str(analysis.get("_vocals") or "mixed"),
        "timing": str(analysis.get("_timing") or "steady"),
        "roles": [str(role) for role in analysis.get("_roles", []) if role],
        "path": path,
        "available": bool(path and Path(path).is_file()),
    }


def _match_score(track: dict[str, Any], section: dict[str, Any]) -> tuple[float, str, list[dict[str, str]]]:
    genres = set(_terms(track["genre"]) + track["detailedGenres"])
    descriptor_values = {str(item["value"]).casefold() for item in track["descriptors"]}
    requested_genres = set(_terms(section.get("genres", [])))
    characteristics = set(_terms(section.get("characteristics", [])))
    direct = requested_genres & genres
    identity = (requested_genres | characteristics) & descriptor_values
    target_energy = (float(section.get("energyStart") or 5) + float(section.get("energyEnd") or 5)) / 20
    energy_fit = max(0.0, 1 - abs(float(track["energy"]) - target_energy))
    reasons: list[dict[str, str]] = []
    if direct:
        reasons.append({"evidence": "verified", "text": f"Catalog genre matches: {', '.join(sorted(direct))}."})
    if identity:
        reasons.append({"evidence": "verified", "text": f"Identity descriptors match: {', '.join(sorted(identity))}."})
    reasons.append({"evidence": "estimated", "text": f"Energy fit is {round(energy_fit * 100)}%."})
    tier = "direct" if direct else "identity" if identity else "bridge" if energy_fit >= 0.72 else "fallback"
    score = len(direct) * 45 + len(identity) * 24 + energy_fit * 20
    if track["timing"] == "steady":
        score += 3
    return score, tier, reasons


def _matches_constraints(track: dict[str, Any], constraints: dict[str, Any]) -> bool:
    bpm = float(track.get("bpm") or 0)
    minimum_bpm = float(constraints.get("bpmMin") or 0)
    maximum_bpm = float(constraints.get("bpmMax") or 0)
    if minimum_bpm and bpm < minimum_bpm:
        return False
    if maximum_bpm and bpm > maximum_bpm:
        return False
    if constraints.get("vocals") not in {None, "", "all", track.get("vocals")}:
        return False
    if constraints.get("timing") not in {None, "", "all", track.get("timing")}:
        return False
    detailed = set(_terms(track.get("detailedGenres", [])))
    required_details = set(_terms(constraints.get("detailedGenres", [])))
    if required_details and not detailed.intersection(required_details):
        return False
    genre = str(track.get("genre") or "").strip().casefold()
    excluded_genres = {
        str(value).strip().casefold() for value in constraints.get("excludedGenres", []) if str(value).strip()
    }
    return not any(genre == excluded or genre.startswith(f"{excluded} /") for excluded in excluded_genres)


@dataclass(frozen=True)
class SetCandidateRetriever:
    """Retrieve small real-catalog pools without asking an AI to inspect the whole library."""

    default_section_limit: int = 16
    maximum_section_limit: int = 100
    maximum_total: int = 100

    def retrieve(
        self,
        catalog: list[dict[str, Any]],
        journey: dict[str, Any],
        *,
        required_ids: set[str] | None = None,
        excluded_ids: set[str] | None = None,
        locked_ids: set[str] | None = None,
        constraints: dict[str, Any] | None = None,
        section_limit: int | None = None,
        total_limit: int | None = None,
    ) -> dict[str, Any]:
        required = required_ids or set()
        excluded = excluded_ids or set()
        locked = locked_ids or set()
        limit = max(1, min(section_limit or self.default_section_limit, self.maximum_section_limit))
        total_cap = max(1, min(total_limit or self.maximum_total, self.maximum_total))
        compact = [_compact_track(item) for item in catalog]
        compact = [
            track for track in compact
            if track["id"]
            and track["id"] not in excluded
            and (track["id"] in required | locked or _matches_constraints(track, constraints or {}))
        ]
        known_ids = {track["id"] for track in compact}
        sections: list[dict[str, Any]] = []
        emitted: set[str] = set()
        for section in journey.get("sections", []):
            section_id = str(section.get("id") or f"section-{len(sections) + 1}")
            ranked = []
            for track in compact:
                score, tier, reasons = _match_score(track, section)
                if track["id"] in required | locked:
                    score += 1000
                    reasons.insert(0, {"evidence": "verified", "text": "Required or locked by the DJ."})
                ranked.append((score, tier, track, reasons))
            ranked.sort(key=lambda value: (-value[0], value[2]["artist"].casefold(), value[2]["title"].casefold()))
            selected: list[dict[str, Any]] = []
            artist_counts: dict[str, int] = {}
            for score, tier, track, reasons in ranked:
                if len(selected) >= limit:
                    break
                if track["id"] not in emitted and len(emitted) >= total_cap:
                    continue
                artist = track["artist"].strip().casefold()
                if artist and artist_counts.get(artist, 0) >= 2 and track["id"] not in required | locked:
                    continue
                selected.append({
                    **track,
                    "matchTier": tier,
                    "relevanceScore": round(score, 2),
                    "required": track["id"] in required,
                    "locked": track["id"] in locked,
                    "eligibleSectionIds": [section_id],
                    "reasons": reasons,
                })
                emitted.add(track["id"])
                if artist:
                    artist_counts[artist] = artist_counts.get(artist, 0) + 1
            sections.append({
                "sectionId": section_id,
                "requestedGenres": _terms(section.get("genres", [])),
                "candidates": selected,
                "scarcity": {
                    "direct": sum(candidate["matchTier"] == "direct" for candidate in selected),
                    "identity": sum(candidate["matchTier"] == "identity" for candidate in selected),
                    "bridge": sum(candidate["matchTier"] == "bridge" for candidate in selected),
                    "fallback": sum(candidate["matchTier"] == "fallback" for candidate in selected),
                },
            })
        available_ids = {track["id"] for track in compact if track["available"]}
        return {
            "version": 1,
            "sections": sections,
            "candidateCount": len(emitted),
            "missingRequiredIds": sorted(required - known_ids),
            "unavailableRequiredIds": sorted((required & known_ids) - available_ids),
            "limits": {"perSection": limit, "total": total_cap},
        }
