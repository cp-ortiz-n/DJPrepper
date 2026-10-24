"""Validated, local-first musical journey planning for Set Builder."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from audioextender.set_builder.genre_vocabulary import canonical_genres
from audioextender.set_builder.intention_planner import IntentionPlanner, _clean_term

logger = logging.getLogger("uvicorn.error")

JOURNEY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "purpose": {"type": "string"},
                    "durationPercent": {"type": "number", "minimum": 1, "maximum": 100},
                    "genres": {"type": "array", "items": {"type": "string"}},
                    "characteristics": {"type": "array", "items": {"type": "string"}},
                    "energyStart": {"type": "number", "minimum": 1, "maximum": 10},
                    "energyEnd": {"type": "number", "minimum": 1, "maximum": 10},
                },
                "required": ["name", "purpose", "durationPercent", "genres", "characteristics",
                             "energyStart", "energyEnd"],
            },
        },
    },
    "required": ["summary", "sections"],
}

JOURNEY_INSTRUCTIONS = (
    "You are planning the high-level sections of a DJ set, not selecting tracks. Return only the requested JSON. "
    "Use the supplied interpreted intention as authoritative. Preserve explicitly requested genre order and keep "
    "optional genres optional. When drift is none, use only requestedGenres, optionalGenres, and genreSequence; vary "
    "energy, character, and purpose instead of introducing adjacent genres. Never invent a genre outside "
    "catalog_vocabulary. Treat melodic, warm-up, peak-time, "
    "closing, and similar words as characteristics or purposes, not genres. Section durationPercent values must total "
    "100. Use 1-10 energy values and allow deliberate waves or resets when requested. Keep the plan practical and "
    "concise, normally 3-6 sections. Do not claim knowledge of tracks or audio that was not supplied."
)


def _canonical_genre(value: Any, vocabulary: list[str]) -> str:
    raw = _clean_term(value)
    catalog = sorted({_clean_term(item) for item in vocabulary if _clean_term(item)}, key=len, reverse=True)
    return next((genre for genre in catalog if genre == raw or genre in raw), "")


def _rebalance_percentages(values: list[float]) -> list[int]:
    if not values:
        return []
    positive = [max(1.0, float(value or 0)) for value in values]
    total = sum(positive)
    exact = [value / total * 100 for value in positive]
    rounded = [max(1, int(value)) for value in exact]
    difference = 100 - sum(rounded)
    order = sorted(range(len(exact)), key=lambda index: exact[index] - int(exact[index]), reverse=difference > 0)
    cursor = 0
    while difference and order:
        index = order[cursor % len(order)]
        if difference > 0:
            rounded[index] += 1
            difference -= 1
        elif rounded[index] > 1:
            rounded[index] -= 1
            difference += 1
        cursor += 1
    return rounded


def sanitize_journey(result: dict[str, Any], vocabulary: list[str], duration_minutes: int) -> dict[str, Any]:
    """Normalize a model proposal into a safe, contiguous, catalog-backed journey."""
    raw_value = result.get("sections")
    raw_sections: list[Any] = raw_value if isinstance(raw_value, list) else []
    sections: list[dict[str, Any]] = []
    for index, raw_section in enumerate(raw_sections[:10]):
        if not isinstance(raw_section, dict):
            continue
        genres = []
        for value in raw_section.get("genres", []):
            genre = _canonical_genre(value, vocabulary)
            if genre and genre not in genres:
                genres.append(genre)
        characteristics = [
            term for term in dict.fromkeys(_clean_term(value) for value in raw_section.get("characteristics", []))
            if term
        ][:8]
        sections.append({
            "id": f"section-{index + 1}",
            "name": str(raw_section.get("name") or f"Section {index + 1}").strip()[:80],
            "purpose": str(raw_section.get("purpose") or "Continue the musical journey.").strip()[:240],
            "durationPercent": float(raw_section.get("durationPercent") or 1),
            "genres": genres,
            "characteristics": characteristics,
            "energyStart": max(1, min(10, round(float(raw_section.get("energyStart") or 5), 1))),
            "energyEnd": max(1, min(10, round(float(raw_section.get("energyEnd") or 5), 1))),
        })
    if not sections:
        raise ValueError("Journey planner returned no usable sections")
    percentages = _rebalance_percentages([section["durationPercent"] for section in sections])
    elapsed = 0
    for section, percentage in zip(sections, percentages, strict=True):
        section["durationPercent"] = percentage
        section["startMinute"] = round(duration_minutes * elapsed / 100, 1)
        elapsed += percentage
        section["endMinute"] = round(duration_minutes * elapsed / 100, 1)
    return {
        "version": 1,
        "summary": str(result.get("summary") or "A structured musical journey.").strip()[:400],
        "durationMinutes": duration_minutes,
        "sections": sections,
    }


def offline_journey(interpreted: dict[str, Any], vocabulary: list[str], duration_minutes: int) -> dict[str, Any]:
    """Produce a useful journey without an AI provider."""
    sequence = list(dict.fromkeys([
        *interpreted.get("genreSequence", []),
        *interpreted.get("requestedGenres", []),
        *interpreted.get("optionalGenres", []),
    ]))
    canonical = [genre for value in sequence if (genre := _canonical_genre(value, vocabulary))]
    groups = [[genre] for genre in canonical] or [[]]
    curve = interpreted.get("curve") or "rise"
    opening = _clean_term(interpreted.get("opening"))
    ending = _clean_term(interpreted.get("ending"))
    raw_sections = []
    for index, genres in enumerate(groups):
        progress = index / max(1, len(groups) - 1)
        if curve == "waves":
            energy_start = 4 + (index % 2) * 2
            energy_end = 6 if index % 2 == 0 else 5
        elif curve == "steady":
            energy_start = energy_end = 6
        elif curve == "peak-release":
            energy_start = 4 + round(progress * 5)
            energy_end = 7 if index == len(groups) - 1 else min(9, energy_start + 1)
        else:
            energy_start = 3 + round(progress * 4)
            energy_end = min(9, energy_start + 1)
        characteristics: list[str] = []
        if index == 0 and opening:
            characteristics.extend(term.strip() for term in opening.split(",") if term.strip())
        if index == len(groups) - 1 and ending:
            characteristics.extend(term.strip() for term in ending.split(",") if term.strip())
        raw_sections.append({
            "name": "Opening" if index == 0 else "Closing" if index == len(groups) - 1 else f"Movement {index + 1}",
            "purpose": (
                "Establish the atmosphere."
                if index == 0
                else "Deliver a deliberate finish."
                if index == len(groups) - 1
                else "Advance the requested genre and energy journey."
            ),
            "durationPercent": 100 / len(groups),
            "genres": genres,
            "characteristics": characteristics,
            "energyStart": energy_start,
            "energyEnd": energy_end,
        })
    return sanitize_journey({"summary": interpreted.get("explanation") or "Offline structured journey.",
                             "sections": raw_sections}, vocabulary, duration_minutes)


def _preserves_requested_sequence(journey: dict[str, Any], interpreted: dict[str, Any],
                                  vocabulary: list[str]) -> bool:
    optional = {_canonical_genre(value, vocabulary) for value in interpreted.get("optionalGenres", [])}
    expected = [_canonical_genre(value, vocabulary) for value in interpreted.get("genreSequence", [])]
    expected = [value for value in expected if value and value not in optional]
    planned = [genre for section in journey.get("sections", []) for genre in section.get("genres", [])]
    cursor = 0
    for genre in planned:
        if cursor < len(expected) and genre == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def enforce_journey_genre_policy(
    journey: dict[str, Any], interpreted: dict[str, Any], vocabulary: list[str]
) -> dict[str, Any]:
    """Prevent an exact genre brief from silently expanding into catalog neighbors."""
    drift = str(interpreted.get("drift") or "none").strip().lower()
    core = list(dict.fromkeys(
        genre
        for value in [*interpreted.get("genreSequence", []), *interpreted.get("requestedGenres", [])]
        if (genre := _canonical_genre(value, vocabulary))
    ))
    optional = list(dict.fromkeys(
        genre
        for value in interpreted.get("optionalGenres", [])
        if (genre := _canonical_genre(value, vocabulary)) and genre not in core
    ))
    allowed = [*core, *optional]
    strict = drift == "none" and bool(allowed)
    policy: dict[str, Any] = {
        "mode": "strict" if strict else "related",
        "coreGenres": core,
        "optionalGenres": optional,
        "repairedSections": [],
    }
    journey["genrePolicy"] = policy
    if not strict:
        return journey
    sections = journey.get("sections", [])
    for index, section in enumerate(sections):
        proposed = list(dict.fromkeys(section.get("genres", [])))
        kept = [genre for genre in proposed if genre in allowed]
        removed = [genre for genre in proposed if genre not in allowed]
        if not kept:
            source = core or optional
            position = min(len(source) - 1, int(index * len(source) / max(1, len(sections))))
            kept = [source[position]]
        if removed:
            section["suggestedGenres"] = removed
        section["genres"] = kept
        if kept != proposed:
            policy["repairedSections"].append(str(section.get("id") or f"section-{index + 1}"))
            section["purpose"] = f"Develop the requested {', '.join(kept)} direction at this energy level."
    return journey


@dataclass(frozen=True)
class JourneyPlanner:
    intention_planner: IntentionPlanner

    def plan(self, brief: str, interpreted: dict[str, Any], catalog_vocabulary: list[Any],
             duration_minutes: int) -> dict[str, Any]:
        vocabulary = canonical_genres(catalog_vocabulary)[:800]
        started = perf_counter()
        try:
            result = self._plan_with_provider(brief, interpreted, vocabulary)
            journey = sanitize_journey(result, vocabulary, duration_minutes)
            journey = enforce_journey_genre_policy(journey, interpreted, vocabulary)
            if not _preserves_requested_sequence(journey, interpreted, vocabulary):
                raise ValueError("AI journey omitted or reordered an explicitly requested genre")
            status = self.intention_planner.status()
            journey.update(provider=status["provider"], model=status["model"], evidence="ai-planned")
            logger.info("Set Builder journey planned: provider=%s model=%s sections=%d elapsed_ms=%d",
                        journey["provider"], journey["model"], len(journey["sections"]),
                        round((perf_counter() - started) * 1000))
            return journey
        except (httpx.HTTPError, ValueError, RuntimeError, TypeError) as error:
            logger.warning("Set Builder journey fallback: error=%s", error)
            journey = offline_journey(interpreted, vocabulary, duration_minutes)
            journey.update(provider="offline", model=None, evidence="deterministic-fallback", warning=str(error))
            return journey

    def _plan_with_provider(self, brief: str, interpreted: dict[str, Any], vocabulary: list[str]) -> dict[str, Any]:
        planner = self.intention_planner
        payload = json.dumps({"brief": brief, "interpreted_intention": interpreted,
                              "catalog_vocabulary": vocabulary}, ensure_ascii=False)
        status = planner.status()
        if status["provider"] == "ollama":
            response = httpx.post(
                f"{planner.ollama_endpoint}/api/chat",
                json={"model": planner.ollama_model, "stream": False, "think": False, "format": JOURNEY_SCHEMA,
                      "keep_alive": "10m", "options": {"temperature": 0.15, "num_predict": 1400},
                      "messages": [{"role": "system", "content": JOURNEY_INSTRUCTIONS},
                                   {"role": "user", "content": payload}]},
                timeout=90,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
        elif status["provider"] == "openai":
            response = httpx.post(
                planner.endpoint,
                headers={"Authorization": f"Bearer {planner.api_key}", "Content-Type": "application/json"},
                json={"model": planner.model, "store": False, "instructions": JOURNEY_INSTRUCTIONS,
                      "input": payload, "text": {"format": {"type": "json_schema", "name": "dj_set_journey",
                                                               "strict": True, "schema": JOURNEY_SCHEMA}}},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("output_text", "")
            if not content:
                content = next((part.get("text", "") for item in body.get("output", [])
                                for part in item.get("content", []) if part.get("type") == "output_text"), "")
        else:
            raise RuntimeError("No AI journey provider is available")
        if not content:
            raise RuntimeError("The AI provider returned no journey")
        return json.loads(content)
