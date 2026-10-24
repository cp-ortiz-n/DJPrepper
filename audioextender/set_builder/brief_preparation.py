"""Cached one-pass preparation of an editable Set Builder brief."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from audioextender.set_builder.intention_planner import INTENTION_SCHEMA, PLANNER_INSTRUCTIONS, IntentionPlanner
from audioextender.set_builder.journey_planner import (
    JOURNEY_INSTRUCTIONS,
    JOURNEY_SCHEMA,
    _preserves_requested_sequence,
    enforce_journey_genre_policy,
    offline_journey,
    sanitize_journey,
)

BRIEF_PREPARATION_VERSION = 3
BRIEF_SCHEMA = {
    **INTENTION_SCHEMA,
    "properties": {**INTENTION_SCHEMA["properties"], "journey": JOURNEY_SCHEMA},
    "required": [*INTENTION_SCHEMA["required"], "journey"],
}
BRIEF_INSTRUCTIONS = (
    PLANNER_INSTRUCTIONS + " Also return a journey object for this same interpretation. " + JOURNEY_INSTRUCTIONS
)


@dataclass
class BriefPreparationService:
    """Interpret and plan in one model request, then reuse identical work."""

    intention_planner: IntentionPlanner
    ttl_seconds: float = 30 * 60
    maximum_entries: int = 64
    _cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)
    _inflight: dict[str, Future[dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def prepare(
        self,
        brief: str,
        catalog_vocabulary: list[str],
        duration_minutes: int,
    ) -> dict[str, Any]:
        vocabulary = sorted({str(value).strip() for value in catalog_vocabulary if str(value).strip()})[:800]
        key = self._key(brief, vocabulary, duration_minutes)
        now = monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now < cached[0]:
                return self._result(cached[1], cache_hit=True, shared_request=False)
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        assert future is not None
        if not owner:
            return self._result(future.result(timeout=95), cache_hit=False, shared_request=True)
        try:
            interpretation = self.intention_planner.interpret(
                brief, vocabulary, schema=BRIEF_SCHEMA, instructions=BRIEF_INSTRUCTIONS
            )
            proposed_journey = interpretation.pop("journey", None)
            try:
                if not isinstance(proposed_journey, dict):
                    raise ValueError("Missing journey")
                journey = sanitize_journey(proposed_journey, vocabulary, duration_minutes)
                journey = enforce_journey_genre_policy(journey, interpretation, vocabulary)
                if not _preserves_requested_sequence(journey, interpretation, vocabulary):
                    raise ValueError("Journey changed requested genre order")
                evidence = "ai-planned"
            except (ValueError, TypeError, KeyError):
                journey = offline_journey(interpretation, vocabulary, duration_minutes)
                evidence = "ai-interpreted"
            journey.update(
                provider=interpretation.get("provider", "offline"),
                model=interpretation.get("model"),
                evidence=evidence if interpretation.get("provider") != "offline" else "deterministic-fallback",
            )
            payload = {
                "version": BRIEF_PREPARATION_VERSION,
                "interpretation": interpretation,
                "journey": journey,
            }
            with self._lock:
                self._cache[key] = (monotonic() + self.ttl_seconds, copy.deepcopy(payload))
                self._trim_cache()
            future.set_result(payload)
            return self._result(payload, cache_hit=False, shared_request=False)
        except Exception as error:
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def _key(self, brief: str, vocabulary: list[str], duration_minutes: int) -> str:
        payload = {
            "version": BRIEF_PREPARATION_VERSION,
            "brief": brief.strip(),
            "vocabulary": vocabulary,
            "duration_minutes": duration_minutes,
            "provider": self.intention_planner.provider,
            "ollama_model": self.intention_planner.ollama_model,
            "cloud_model": self.intention_planner.model,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _trim_cache(self) -> None:
        while len(self._cache) > self.maximum_entries:
            oldest = min(self._cache, key=lambda key: self._cache[key][0])
            self._cache.pop(oldest, None)

    @staticmethod
    def _result(payload: dict[str, Any], *, cache_hit: bool, shared_request: bool) -> dict[str, Any]:
        result = copy.deepcopy(payload)
        result["cache"] = {"hit": cache_hit, "shared_request": shared_request}
        return result
