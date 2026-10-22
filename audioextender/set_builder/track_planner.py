"""Provider-isolated AI track planning with deterministic validation and fallback."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol

import httpx

from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.plan_comparator import PlanQualityComparator
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.proposal_repairer import PlanProposalRepairer
from audioextender.set_builder.transition_optimizer import DeterministicTransitionOptimizer

logger = logging.getLogger("uvicorn.error")

TRACK_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "selections": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "trackId": {"type": "string"},
                    "sectionId": {"type": "string"},
                },
                "required": ["trackId", "sectionId"],
            },
        },
    },
    "required": ["summary", "selections"],
}

TRACK_PLAN_INSTRUCTIONS = (
    "Create a DJ running order only from the supplied candidates. Return only the requested JSON. "
    "Use every trackId exactly as supplied; never invent, shorten, or rewrite an ID. Select targetTrackCount tracks. "
    "Assign tracks only to eligibleSectionIds, cover every journey section, preserve required and locked tracks, "
    "assign every lockedTrackSections entry to its exact section, and "
    "never repeat a track. Use exactly the per-section counts in sectionTrackTargets. Follow section order, energy "
    "direction, requested genres, and musical identity. Prefer "
    "workable BPM, Camelot-key, vocal, and timing transitions. Bridge or fallback tracks are allowed only when direct "
    "matches are scarce. Return only trackId and sectionId for each selection; verified explanations are generated "
    "locally from catalog evidence. Do not claim to have heard audio."
)

MODEL_CANDIDATE_LIMIT = 60


def _model_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep selection evidence compact while validation retains full local data."""
    return {
        "id": candidate.get("id"),
        "title": candidate.get("title"),
        "artist": candidate.get("artist"),
        "genre": candidate.get("genre"),
        "detailedGenres": candidate.get("detailedGenres", []),
        "identity": [
            str(descriptor.get("value"))
            for descriptor in candidate.get("descriptors", [])
            if isinstance(descriptor, dict) and descriptor.get("value")
        ],
        "bpm": candidate.get("bpm"),
        "camelot": candidate.get("camelot") or candidate.get("key"),
        "energy": candidate.get("energy"),
        "durationSeconds": candidate.get("durationSeconds"),
        "vocals": candidate.get("vocals"),
        "timing": candidate.get("timing"),
        "roles": candidate.get("roles", []),
        "matchTier": candidate.get("matchTier"),
        "relevanceScore": candidate.get("relevanceScore"),
        "eligibleSectionIds": candidate.get("eligibleSectionIds", []),
        "required": bool(candidate.get("required")),
        "locked": bool(candidate.get("locked")),
    }


def bounded_model_candidates(candidates: list[dict[str, Any]], section_targets: dict[str, int]) -> list[dict[str, Any]]:
    """Build a diverse shortlist sized to the plan instead of the catalog cap."""
    chosen: dict[str, dict[str, Any]] = {}
    available = [candidate for candidate in candidates if candidate.get("available")]
    for candidate in available:
        if candidate.get("required") or candidate.get("locked"):
            chosen[str(candidate["id"])] = candidate
    for section_id, target in section_targets.items():
        section = [candidate for candidate in available if section_id in candidate.get("eligibleSectionIds", [])]
        section.sort(key=lambda item: (-float(item.get("relevanceScore") or 0), str(item.get("id") or "")))
        for candidate in section[: max(target + 4, target * 2)]:
            chosen.setdefault(str(candidate["id"]), candidate)
    ranked = sorted(
        chosen.values(),
        key=lambda item: (
            not bool(item.get("required") or item.get("locked")),
            -float(item.get("relevanceScore") or 0),
            str(item.get("id") or ""),
        ),
    )
    protected = [item for item in ranked if item.get("required") or item.get("locked")]
    optional = [item for item in ranked if not (item.get("required") or item.get("locked"))]
    bounded = [*protected, *optional[: max(0, MODEL_CANDIDATE_LIMIT - len(protected))]]
    return [_model_candidate(item) for item in bounded]


def _schema_for_request(payload: dict[str, Any]) -> dict[str, Any]:
    schema = json.loads(json.dumps(TRACK_PLAN_SCHEMA))
    requested = max(1, min(100, int(payload.get("targetTrackCount") or 1)))
    selections = schema["properties"]["selections"]
    selections["minItems"] = requested
    selections["maxItems"] = requested
    selections["uniqueItems"] = True
    candidate_ids = sorted(
        {str(candidate.get("id") or "") for candidate in payload.get("candidates", []) if candidate.get("id")}
    )
    section_ids = sorted(
        {
            str(section.get("id") or "")
            for section in (payload.get("journey") or {}).get("sections", [])
            if section.get("id")
        }
    )
    properties = selections["items"]["properties"]
    if candidate_ids:
        properties["trackId"]["enum"] = candidate_ids
    if section_ids:
        properties["sectionId"]["enum"] = section_ids
    return schema


def _public_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        **validation,
        "plan": [{key: value for key, value in track.items() if key != "path"} for track in validation.get("plan", [])],
    }


class TrackPlanningModel(Protocol):
    def status(self) -> dict[str, Any]: ...

    def complete(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SetPlanningModelClient:
    """Structured-output adapter for the configured local or cloud provider."""

    configuration: IntentionPlanner

    def status(self) -> dict[str, Any]:
        return self.configuration.status()

    def complete(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        status = self.status()
        provider = status["provider"]
        response_schema = _schema_for_request(payload)
        if provider == "ollama":
            prediction_limit = min(1200, max(400, int(payload.get("targetTrackCount") or 1) * 45))
            response = httpx.post(
                f"{self.configuration.ollama_endpoint}/api/chat",
                json={
                    "model": self.configuration.ollama_model,
                    "stream": False,
                    "think": False,
                    "format": response_schema,
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0.12,
                        "num_ctx": 16384,
                        "num_predict": prediction_limit,
                    },
                    "messages": [
                        {"role": "system", "content": TRACK_PLAN_INSTRUCTIONS},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
                    ],
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
        elif provider == "openai":
            response = httpx.post(
                self.configuration.endpoint,
                headers={
                    "Authorization": f"Bearer {self.configuration.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.configuration.model,
                    "store": False,
                    "instructions": TRACK_PLAN_INSTRUCTIONS,
                    "input": json.dumps(payload, ensure_ascii=False),
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "dj_track_plan",
                            "strict": True,
                            "schema": response_schema,
                        }
                    },
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("output_text", "") or next(
                (
                    part.get("text", "")
                    for item in body.get("output", [])
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                ),
                "",
            )
        else:
            raise RuntimeError("No AI track-planning provider is available")
        if not content:
            raise RuntimeError("The AI provider returned no track plan")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("The AI provider returned an invalid track plan")
        if provider == "ollama":
            body = response.json()
            result["_providerMetrics"] = {
                "promptTokens": int(body.get("prompt_eval_count") or 0),
                "outputTokens": int(body.get("eval_count") or 0),
                "promptEvalMs": round(float(body.get("prompt_eval_duration") or 0) / 1_000_000),
                "generationMs": round(float(body.get("eval_duration") or 0) / 1_000_000),
            }
        return result


def flatten_candidates(candidate_pool: dict[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for section in candidate_pool.get("sections", []):
        for candidate in section.get("candidates", []):
            if not isinstance(candidate, dict) or not candidate.get("id"):
                continue
            track_id = str(candidate["id"])
            if track_id not in merged:
                merged[track_id] = dict(candidate)
                continue
            current = merged[track_id]
            current["eligibleSectionIds"] = list(
                dict.fromkeys(
                    [
                        *current.get("eligibleSectionIds", []),
                        *candidate.get("eligibleSectionIds", []),
                    ]
                )
            )
            if float(candidate.get("relevanceScore") or 0) > float(current.get("relevanceScore") or 0):
                current["relevanceScore"] = candidate.get("relevanceScore")
                current["matchTier"] = candidate.get("matchTier")
            current["reasons"] = list(
                dict.fromkeys(
                    json.dumps(reason, sort_keys=True)
                    for reason in [*current.get("reasons", []), *candidate.get("reasons", [])]
                )
            )
            current["reasons"] = [json.loads(reason) for reason in current["reasons"]]
    return list(merged.values())


def _section_targets(journey: dict[str, Any], count: int) -> dict[str, int]:
    sections = journey.get("sections", [])
    if not sections:
        return {}
    exact = [max(0.0, float(section.get("durationPercent") or 0)) / 100 * count for section in sections]
    targets = [max(1, int(value)) for value in exact]
    while sum(targets) > count:
        reducible = [index for index, value in enumerate(targets) if value > 1]
        if not reducible:
            break
        targets[max(reducible, key=lambda index: targets[index] - exact[index])] -= 1
    while sum(targets) < count:
        index = max(range(len(targets)), key=lambda value: exact[value] - targets[value])
        targets[index] += 1
    return {str(section.get("id") or f"section-{index + 1}"): targets[index] for index, section in enumerate(sections)}


def _section_targets_with_locks(journey: dict[str, Any], count: int, locked_sections: dict[str, str]) -> dict[str, int]:
    targets = _section_targets(journey, count)
    minimums = {
        section_id: sum(locked_section == section_id for locked_section in locked_sections.values())
        for section_id in targets
    }
    for section_id, minimum in minimums.items():
        while targets[section_id] < minimum:
            donors = [
                candidate
                for candidate in targets
                if candidate != section_id and targets[candidate] > max(1, minimums[candidate])
            ]
            if not donors:
                break
            donor = max(donors, key=lambda candidate: targets[candidate] - minimums[candidate])
            targets[donor] -= 1
            targets[section_id] += 1
    return targets


def deterministic_track_plan(
    candidate_pool: dict[str, Any],
    journey: dict[str, Any],
    target_track_count: int,
    target_duration_minutes: int | None = None,
    locked_sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Select a stable, section-aware plan when a model cannot return a valid one."""
    targets = _section_targets_with_locks(journey, target_track_count, locked_sections or {})
    used: set[str] = set()
    used_recordings: set[str] = set()
    journey_sections = {
        str(section.get("id") or f"section-{index + 1}"): section
        for index, section in enumerate(journey.get("sections", []))
    }
    chosen_sections: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for section in candidate_pool.get("sections", []):
        section_id = str(section.get("sectionId") or "")
        candidates = [
            candidate
            for candidate in section.get("candidates", [])
            if candidate.get("available")
            and str(candidate.get("id") or "") not in used
            and str(candidate.get("recordingKey") or candidate.get("id") or "") not in used_recordings
        ]
        candidates.sort(
            key=lambda candidate: (
                not bool(candidate.get("required") or candidate.get("locked")),
                -float(candidate.get("relevanceScore") or 0),
                float(candidate.get("energy") or 0.5),
                str(candidate.get("id") or ""),
            )
        )
        target = targets.get(section_id, 0)
        section_definition = journey_sections.get(section_id, {})
        duration_target = (
            target_duration_minutes * 60 * float(section_definition.get("durationPercent") or 0) / 100
            if target_duration_minutes
            else None
        )
        selected = _select_section_candidates(candidates, target, duration_target)
        used.update(str(candidate.get("id") or "") for candidate in selected)
        used_recordings.update(
            str(candidate.get("recordingKey") or candidate.get("id") or "") for candidate in selected
        )
        chosen_sections.append((section_definition, selected))
    optimized = DeterministicTransitionOptimizer().optimize(chosen_sections)
    selections = [
        {
            "trackId": str(candidate.get("id") or ""),
            "sectionId": section_id,
            "reason": "Deterministic balance of section relevance, runtime, energy, BPM, key, and vocals.",
            "evidence": "estimated",
        }
        for section_id, candidate in optimized
    ]
    return {"summary": "Deterministic catalog-backed fallback plan.", "selections": selections}


def _select_section_candidates(
    candidates: list[dict[str, Any]], target_count: int, target_duration_seconds: float | None
) -> list[dict[str, Any]]:
    if target_count <= 0 or not candidates:
        return []
    if target_duration_seconds is None:
        return candidates[:target_count]
    forced = [candidate for candidate in candidates if candidate.get("required") or candidate.get("locked")]
    forced = forced[:target_count]
    remaining_count = target_count - len(forced)
    if remaining_count <= 0:
        return forced
    forced_ids = {str(candidate.get("id") or "") for candidate in forced}
    optional = [candidate for candidate in candidates if str(candidate.get("id") or "") not in forced_ids]
    # Dynamic programming keeps the strongest relevance combination for each
    # track-count/runtime pair. Ten-second buckets make the bound small and
    # stable even for the maximum 100-candidate server contract.
    states: dict[tuple[int, int], tuple[float, tuple[dict[str, Any], ...]]] = {(0, 0): (0.0, ())}
    for candidate in optional:
        duration_bucket = max(1, round(float(candidate.get("durationSeconds") or 0) / 10))
        relevance = float(candidate.get("relevanceScore") or 0)
        additions: dict[tuple[int, int], tuple[float, tuple[dict[str, Any], ...]]] = {}
        for (count, duration), (score, chosen) in states.items():
            if count >= remaining_count:
                continue
            key = (count + 1, duration + duration_bucket)
            proposal = (score + relevance, (*chosen, candidate))
            current = states.get(key) or additions.get(key)
            if current is None or proposal[0] > current[0]:
                additions[key] = proposal
        states.update(additions)
    forced_duration = sum(float(candidate.get("durationSeconds") or 0) for candidate in forced)
    complete = [
        (duration * 10 + forced_duration, score, chosen)
        for (count, duration), (score, chosen) in states.items()
        if count == remaining_count
    ]
    if not complete:
        return [*forced, *optional[:remaining_count]]
    tolerance = target_duration_seconds * 0.15
    within_tolerance = [state for state in complete if abs(state[0] - target_duration_seconds) <= tolerance]
    if within_tolerance:
        _, _, chosen = max(within_tolerance, key=lambda state: (state[1], -abs(state[0] - target_duration_seconds)))
    else:
        _, _, chosen = min(complete, key=lambda state: (abs(state[0] - target_duration_seconds), -state[1]))
    return [*forced, *chosen]


@dataclass(frozen=True)
class AITrackPlanner:
    model: TrackPlanningModel
    validator: SetPlanValidator
    comparator: PlanQualityComparator = field(default_factory=PlanQualityComparator)
    repairer: PlanProposalRepairer = field(default_factory=PlanProposalRepairer)
    maximum_attempts: int = 1
    timeout_seconds: float = 90

    def plan(
        self,
        *,
        brief: dict[str, Any],
        journey: dict[str, Any],
        candidate_pool: dict[str, Any],
        target_track_count: int,
        target_duration_minutes: int,
        required_ids: set[str],
        excluded_ids: set[str],
        locked_ids: set[str],
        locked_sections: dict[str, str] | None = None,
        cancel_check: Callable[[], None] = lambda: None,
    ) -> dict[str, Any]:
        planning_started = perf_counter()
        provider_status_started = perf_counter()
        candidates = flatten_candidates(candidate_pool)
        locked_by_section = locked_sections or {}
        section_targets = _section_targets_with_locks(journey, target_track_count, locked_by_section)
        model_candidates = bounded_model_candidates(candidates, section_targets)
        base_payload = {
            "brief": brief,
            "journey": journey,
            "targetTrackCount": target_track_count,
            "targetDurationMinutes": target_duration_minutes,
            "sectionTrackTargets": section_targets,
            "requiredTrackIds": sorted(required_ids),
            "lockedTrackIds": sorted(locked_ids),
            "lockedTrackSections": locked_by_section,
            "candidates": model_candidates,
        }
        failures: list[list[dict[str, Any]]] = []
        try:
            status = self.model.status()
        except (httpx.HTTPError, RuntimeError, ValueError) as error:
            status = {"available": False, "provider": "offline", "model": None}
            failures.append([{"code": "provider-status-error", "message": str(error)}])
        provider_status_ms = round((perf_counter() - provider_status_started) * 1000)
        attempt_telemetry: list[dict[str, Any]] = []
        if status.get("available"):
            previous: dict[str, Any] | None = None
            for attempt in range(1, self.maximum_attempts + 1):
                cancel_check()
                payload = dict(base_payload)
                if previous is not None:
                    payload["repair"] = {"previousPlan": previous, "validationErrors": failures[-1]}
                try:
                    model_started = perf_counter()
                    proposal = self.model.complete(payload, timeout_seconds=self.timeout_seconds)
                    model_ms = round((perf_counter() - model_started) * 1000)
                    if not isinstance(proposal, dict):
                        raise ValueError("The AI provider returned a non-object track plan")
                    provider_metrics = proposal.pop("_providerMetrics", {})
                except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, RuntimeError) as error:
                    model_ms = round((perf_counter() - model_started) * 1000)
                    attempt_telemetry.append({"attempt": attempt, "modelMs": model_ms, "outcome": "provider-error"})
                    failures.append([{"code": "provider-error", "message": str(error)}])
                    previous = None
                    if attempt >= self.maximum_attempts:
                        logger.warning("AI track planning failed after %d attempts: %s", attempt, error)
                    continue
                cancel_check()
                try:
                    validation_started = perf_counter()
                    proposal, model_repairs = self.repairer.repair(proposal, candidates, section_targets)
                    validation = self.validator.validate(
                        proposal.get("selections", []),
                        candidates,
                        journey,
                        required_ids=required_ids,
                        excluded_ids=excluded_ids,
                        locked_ids=locked_ids,
                        locked_sections=locked_by_section,
                        target_duration_minutes=target_duration_minutes,
                        target_track_count=target_track_count,
                    )
                    if validation["valid"]:
                        fallback = deterministic_track_plan(
                            candidate_pool,
                            journey,
                            target_track_count,
                            target_duration_minutes,
                            locked_by_section,
                        )
                        baseline_validation = self.validator.validate(
                            fallback["selections"],
                            candidates,
                            journey,
                            required_ids=required_ids,
                            excluded_ids=excluded_ids,
                            locked_ids=locked_ids,
                            locked_sections=locked_by_section,
                            target_duration_minutes=target_duration_minutes,
                            target_track_count=target_track_count,
                        )
                        comparison = self.comparator.compare(
                            validation,
                            baseline_validation,
                            journey,
                            target_duration_minutes=target_duration_minutes,
                        )
                        attempt_telemetry.append(
                            {
                                "attempt": attempt,
                                "modelMs": model_ms,
                                **provider_metrics,
                                "repairValidationComparisonMs": round((perf_counter() - validation_started) * 1000),
                                "repairCount": len(model_repairs),
                                "outcome": "ai-selected" if comparison["winner"] == "ai" else "deterministic-selected",
                            }
                        )
                        observability = {
                            "providerStatusMs": provider_status_ms,
                            "attempts": attempt_telemetry,
                            "plannerTotalMs": round((perf_counter() - planning_started) * 1000),
                        }
                        if comparison["winner"] == "ai":
                            return {
                                **_public_validation(validation),
                                "summary": str(proposal.get("summary") or "AI-planned running order."),
                                "mode": "ai-planned",
                                "provider": status.get("provider"),
                                "model": status.get("model"),
                                "attempts": attempt,
                                "fallbackReason": None,
                                "comparison": comparison,
                                "modelRepairs": model_repairs,
                                "observability": observability,
                            }
                        return {
                            **_public_validation(baseline_validation),
                            "summary": fallback["summary"],
                            "mode": "deterministic-fallback",
                            "provider": status.get("provider"),
                            "model": status.get("model"),
                            "attempts": attempt,
                            "fallbackReason": {
                                "code": "ai-quality-below-baseline",
                                "message": comparison["reason"],
                            },
                            "comparison": comparison,
                            "modelRepairs": model_repairs,
                            "observability": observability,
                        }
                    failures.append(validation["errors"])
                    attempt_telemetry.append(
                        {
                            "attempt": attempt,
                            "modelMs": model_ms,
                            **provider_metrics,
                            "repairValidationComparisonMs": round((perf_counter() - validation_started) * 1000),
                            "repairCount": len(model_repairs),
                            "outcome": "validation-failed",
                        }
                    )
                    previous = proposal
                except (TypeError, ValueError) as error:
                    attempt_telemetry.append(
                        {
                            "attempt": attempt,
                            "modelMs": model_ms,
                            **provider_metrics,
                            "repairValidationComparisonMs": round((perf_counter() - validation_started) * 1000),
                            "outcome": "validation-error",
                        }
                    )
                    failures.append([{"code": "provider-error", "message": str(error)}])
                    previous = None
        cancel_check()
        fallback = deterministic_track_plan(
            candidate_pool, journey, target_track_count, target_duration_minutes, locked_by_section
        )
        validation = self.validator.validate(
            fallback["selections"],
            candidates,
            journey,
            required_ids=required_ids,
            excluded_ids=excluded_ids,
            locked_ids=locked_ids,
            locked_sections=locked_by_section,
            target_duration_minutes=target_duration_minutes,
            target_track_count=target_track_count,
        )
        if not validation["valid"]:
            raise RuntimeError(f"No valid track plan could be built: {validation['errors']}")
        return {
            **_public_validation(validation),
            "summary": fallback["summary"],
            "mode": "deterministic-fallback",
            "provider": status.get("provider") if status.get("available") else "offline",
            "model": status.get("model") if status.get("available") else None,
            "attempts": len(failures),
            "fallbackReason": failures[-1] if failures else "AI provider unavailable",
            "comparison": None,
            "modelRepairs": [],
            "observability": {
                "providerStatusMs": provider_status_ms,
                "attempts": attempt_telemetry,
                "plannerTotalMs": round((perf_counter() - planning_started) * 1000),
            },
        }
