"""Local-first LLM planning for natural-language Set Builder briefs."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

logger = logging.getLogger("uvicorn.error")

INTENTION_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "required": {"type": "array", "description": "Concrete must-have musical traits; empty unless explicit.",
                     "items": {"type": "string"}},
        "preferred": {"type": "array", "description": "Concrete musical, crowd, venue, or identity preferences.",
                      "items": {"type": "string"}},
        "avoided": {"type": "array", "description": "Concrete traits the DJ explicitly limits or rejects.",
                    "items": {"type": "string"}},
        "requestedGenres": {"type": "array", "description": "Catalog genres directly requested.",
                            "items": {"type": "string"}},
        "optionalGenres": {"type": "array", "description": "Genres qualified by if available, some, or a little.",
                           "items": {"type": "string"}},
        "genreSequence": {"type": "array",
                          "description": "Directly requested catalog genres in the order their sections should appear.",
                          "items": {"type": "string"}},
        "drift": {"type": "string", "enum": ["none", "low", "moderate", "wide"]},
        "vibe": {"type": ["string", "null"],
                 "enum": ["balanced", "dance-party", "warm-up", "peak-time", "melodic", "vocal-safe",
                          "ambient", "closing", None]},
        "curve": {"type": ["string", "null"], "enum": ["rise", "peak-release", "waves", "steady", None]},
        "opening": {"type": ["string", "null"],
                    "description": "All explicitly requested opening traits, comma-separated when there are several."},
        "ending": {"type": ["string", "null"],
                   "description": "All explicitly requested ending traits, comma-separated when there are several."},
        "explanation": {"type": "string"},
    },
    "required": ["required", "preferred", "avoided", "requestedGenres", "optionalGenres", "genreSequence",
                 "drift", "vibe", "curve", "opening", "ending", "explanation"],
}

PLANNER_INSTRUCTIONS = (
    "You translate a DJ's natural-language set brief into constraints for a deterministic local set planner. "
    "Understand composition and position: beginning/start/opening describe early tracks, ending/close describe late "
    "tracks, and phrases such as 'melodic beginning' mean an opening style—not a genre applied to every track. "
    "Distinguish required requests from preferences and phrases such as 'if available', which belong in "
    "optionalGenres. "
    "Required, preferred, and avoided must contain concrete requested traits, never schema field names or generic "
    "placeholders. Do not infer an ending, venue, or crowd when none was stated. 'Varying waves' always means the "
    "waves curve, not rise. Example: 'Latin House with a little Schranz if available; start melodic with varying "
    "waves' produces requestedGenres=['Latin House'], optionalGenres=['Schranz'], opening='melodic', curve='waves', "
    "required=[], and ending=null. "
    "When the DJ requests multiple opening or ending traits, preserve every trait in that positional field, separated "
    "by commas; for example, 'begin organic and melodic' means opening='organic, melodic'. "
    "When the brief uses ordering language such as 'start with', 'from there', 'then', or 'end with', put every "
    "directly requested catalog genre in genreSequence in performance order. Genres joined by 'and' belong to the "
    "same neighboring section but still appear individually and in stated order. Do not put non-genre traits there. "
    "Never invent catalog genres. Preserve cultural, rhythmic, vocal, energy, venue, and crowd intent as concise "
    "preferred descriptors. Return only the requested JSON schema."
)

RESERVED_PLACEHOLDERS = {
    "genre", "requestedgenres", "optionalgenres", "opening", "opening style", "closing style", "ending", "curve",
    "energy level", "rhythm", "vocal type", "venue", "venue intent", "crowd", "crowd intent", "optional genres",
    "cultural context", "rhythmic variation", "vocal delivery", "energy transition", "venue specifics",
    "invented genres", "genre misinterpretation", "overly specific cultural references",
}
NON_GENRE_JOURNEY_TERMS = {
    "ambient", "balanced", "closing", "dance party", "dark", "driving", "euphoric", "hypnotic",
    "industrial", "melodic", "peak time", "party ready", "warm up", "vocal safe",
}


def _clean_term(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", str(value or "").strip().lower()).split())


def sanitize_interpretation(result: dict[str, Any], vocabulary: list[str], brief: str = "") -> dict[str, Any]:
    """Reject schema-label hallucinations and canonicalize genres against the local catalog."""
    cleaned = dict(result)
    for field in ("required", "preferred", "avoided"):
        cleaned[field] = [
            term for term in dict.fromkeys(_clean_term(value) for value in result.get(field, []))
            if term and term not in RESERVED_PLACEHOLDERS
        ]
    catalog = sorted({_clean_term(value) for value in vocabulary if _clean_term(value)}, key=len, reverse=True)
    for field in ("requestedGenres", "optionalGenres", "genreSequence"):
        genres: list[str] = []
        for value in result.get(field, []):
            raw = _clean_term(value)
            match = next((term for term in catalog if term == raw or term in raw), "")
            if match and match not in genres:
                genres.append(match)
        cleaned[field] = genres
    if brief:
        normalized_brief = f" {_clean_term(brief)} "
        explicit_genres = {
            genre for genre in [*cleaned["requestedGenres"], *cleaned["optionalGenres"], *cleaned["genreSequence"]]
            if f" {genre} " in normalized_brief and genre not in NON_GENRE_JOURNEY_TERMS
        }
        cleaned["genreSequence"] = sorted(
            explicit_genres, key=lambda genre: normalized_brief.index(f" {genre} ")
        )
    return cleaned


@dataclass(frozen=True)
class IntentionPlanner:
    provider: str = "auto"
    ollama_model: str = "qwen3.5:4b"
    ollama_endpoint: str = "http://127.0.0.1:11434"
    api_key: str = ""
    model: str = "gpt-5-mini"
    endpoint: str = "https://api.openai.com/v1/responses"

    @classmethod
    def from_environment(cls) -> IntentionPlanner:
        return cls(
            provider=os.getenv("AUDIOEXTENDER_LLM_PROVIDER", "auto").strip().lower() or "auto",
            ollama_model=os.getenv("OLLAMA_SET_BUILDER_MODEL", "qwen3.5:4b").strip() or "qwen3.5:4b",
            ollama_endpoint=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=os.getenv("OPENAI_SET_BUILDER_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
        )

    @property
    def available(self) -> bool:
        return self.provider != "offline" and (self.provider in {"auto", "ollama"} or bool(self.api_key))

    def status(self) -> dict[str, Any]:
        local_available = False
        local_models: list[str] = []
        if self.provider in {"auto", "ollama"}:
            try:
                response = httpx.get(f"{self.ollama_endpoint}/api/tags", timeout=0.75)
                response.raise_for_status()
                local_models = [item.get("name", "") for item in response.json().get("models", [])]
                local_available = any(
                    name == self.ollama_model or name.split(":")[0] == self.ollama_model.split(":")[0]
                    for name in local_models
                )
            except (httpx.HTTPError, ValueError):
                pass
        return {"available": local_available or bool(self.api_key),
                "provider": "ollama" if local_available else "openai" if self.api_key else "offline",
                "model": self.ollama_model if local_available else self.model if self.api_key else None,
                "local_runtime": local_available, "installed_local_models": local_models}

    def interpret(self, brief: str, catalog_vocabulary: list[str]) -> dict[str, Any]:
        vocabulary = sorted({str(value).strip() for value in catalog_vocabulary if str(value).strip()})[:800]
        errors: list[str] = []
        started = perf_counter()
        if self.provider in {"auto", "ollama"}:
            try:
                result = self._interpret_ollama(brief, vocabulary)
                logger.info(
                    "Set Builder AI response: provider=ollama model=%s elapsed_ms=%d vocabulary_terms=%d",
                    self.ollama_model,
                    round((perf_counter() - started) * 1000),
                    len(vocabulary),
                )
                return result
            except (httpx.HTTPError, ValueError, RuntimeError) as error:
                errors.append(f"Ollama: {error}")
                logger.warning(
                    "Set Builder AI provider failed: provider=ollama model=%s error=%s",
                    self.ollama_model,
                    error,
                )
                if self.provider == "ollama":
                    raise RuntimeError(errors[-1]) from error
        if self.provider in {"auto", "openai"} and self.api_key:
            try:
                result = self._interpret_openai(brief, vocabulary)
                logger.info(
                    "Set Builder AI response: provider=openai model=%s elapsed_ms=%d vocabulary_terms=%d",
                    self.model,
                    round((perf_counter() - started) * 1000),
                    len(vocabulary),
                )
                return result
            except (httpx.HTTPError, ValueError, RuntimeError) as error:
                errors.append(f"OpenAI: {error}")
                logger.warning("Set Builder AI provider failed: provider=openai model=%s error=%s", self.model, error)
        raise RuntimeError("; ".join(errors) or "No local or cloud AI provider is configured")

    def _interpret_ollama(self, brief: str, vocabulary: list[str]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.ollama_endpoint}/api/chat",
            json={"model": self.ollama_model, "stream": False, "think": False, "format": INTENTION_SCHEMA,
                  "keep_alive": "10m", "options": {"temperature": 0, "num_predict": 800},
                  "messages": [{"role": "system", "content": PLANNER_INSTRUCTIONS},
                               {"role": "user", "content": json.dumps({"brief": brief,
                                                                         "catalog_vocabulary": vocabulary})}]},
            timeout=90,
        )
        response.raise_for_status()
        output_text = response.json().get("message", {}).get("content", "")
        if not output_text:
            raise RuntimeError("The local model returned no structured interpretation")
        result = sanitize_interpretation(json.loads(output_text), vocabulary, brief)
        result.update(provider="ollama", model=self.ollama_model)
        return result

    def _interpret_openai(self, brief: str, vocabulary: list[str]) -> dict[str, Any]:
        response = httpx.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "store": False, "instructions": PLANNER_INSTRUCTIONS,
                  "input": json.dumps({"brief": brief, "catalog_vocabulary": vocabulary}, ensure_ascii=False),
                  "text": {"format": {"type": "json_schema", "name": "dj_set_intention", "strict": True,
                                      "schema": INTENTION_SCHEMA}}},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text")
        if not output_text:
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        output_text = content.get("text")
                        break
        if not output_text:
            raise RuntimeError("The cloud model returned no structured interpretation")
        result = sanitize_interpretation(json.loads(output_text), vocabulary, brief)
        result.update(provider="openai", model=self.model)
        return result
