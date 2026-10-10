"""Repeatable real-catalog evaluation runs for Set Builder planning changes."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.plan_evaluator import SetPlanEvaluator
from audioextender.set_builder.track_planner import AITrackPlanner


@dataclass(frozen=True)
class SetPlanningEvaluationHarness:
    retriever: SetCandidateRetriever
    planner: AITrackPlanner
    evaluator: SetPlanEvaluator

    def run(self, catalog: list[dict[str, Any]], scenarios: list[dict[str, Any]]) -> dict[str, Any]:
        results = [self._run_scenario(catalog, scenario) for scenario in scenarios]
        completed = [result for result in results if result["status"] == "complete"]
        return {
            "version": 1,
            "scenarioCount": len(results),
            "completedCount": len(completed),
            "failedCount": len(results) - len(completed),
            "averageQualityScore": round(
                sum(result["evaluation"]["qualityScore"] for result in completed) / max(1, len(completed)), 1
            ),
            "results": results,
        }

    def _run_scenario(self, catalog: list[dict[str, Any]], scenario: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        pool: dict[str, Any] | None = None
        try:
            journey = scenario["journey"]
            pool = self.retriever.retrieve(
                catalog,
                journey,
                required_ids=set(scenario.get("requiredTrackIds", [])),
                excluded_ids=set(scenario.get("excludedTrackIds", [])),
                constraints=scenario.get("brief", {}),
                section_limit=int(scenario.get("perSectionLimit", 30)),
                total_limit=int(scenario.get("totalLimit", 100)),
            )
            result = self.planner.plan(
                brief=scenario.get("brief", {}),
                journey=journey,
                candidate_pool=pool,
                target_track_count=int(scenario["targetTrackCount"]),
                target_duration_minutes=int(scenario["targetDurationMinutes"]),
                required_ids=set(scenario.get("requiredTrackIds", [])),
                excluded_ids=set(scenario.get("excludedTrackIds", [])),
                locked_ids=set(),
            )
            evaluation = self.evaluator.evaluate(
                result["plan"],
                journey,
                result["warnings"],
                target_duration_minutes=int(scenario["targetDurationMinutes"]),
            )
            acceptance_failures = _acceptance_failures(evaluation, scenario.get("expectations", {}))
            return {
                "id": str(scenario.get("id") or "unnamed"),
                "status": "failed" if acceptance_failures else "complete",
                "mode": result["mode"],
                "provider": result["provider"],
                "model": result["model"],
                "attempts": result.get("attempts"),
                "planValid": bool(result.get("valid")),
                "fallbackReason": result.get("fallbackReason"),
                "modelRepairs": result.get("modelRepairs", []),
                "observability": result.get("observability", {}),
                "durationMs": round((perf_counter() - started) * 1000),
                "candidateCount": pool["candidateCount"],
                "trackIds": [track["id"] for track in result["plan"]],
                "warnings": result["warnings"],
                "evaluation": evaluation,
                "planComparison": result.get("comparison"),
                "acceptanceFailures": acceptance_failures,
            }
        except Exception as error:
            return {
                "id": str(scenario.get("id") or "unnamed"),
                "status": "failed",
                "durationMs": round((perf_counter() - started) * 1000),
                "candidateCount": int(pool.get("candidateCount") or 0) if pool else 0,
                "availableCandidateCount": _available_candidate_count(pool),
                "error": str(error),
            }


def _available_candidate_count(pool: dict[str, Any] | None) -> int:
    if not pool:
        return 0
    candidate_ids = {
        candidate["id"]
        for section in pool.get("sections", [])
        for candidate in section.get("candidates", [])
        if candidate.get("available") and candidate.get("id")
    }
    return len(candidate_ids)


def _acceptance_failures(evaluation: dict[str, Any], expectations: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    minimum_quality = float(expectations.get("minimumQualityScore") or 0)
    if minimum_quality and float(evaluation.get("qualityScore") or 0) < minimum_quality:
        failures.append(
            {
                "code": "quality-below-floor",
                "expected": minimum_quality,
                "actual": evaluation.get("qualityScore"),
            }
        )
    minimum_genre_coverage = float(expectations.get("minimumGenreCoverage") or 0)
    actual_coverage = float((evaluation.get("requestedGenreCoverage") or {}).get("ratio") or 0)
    if minimum_genre_coverage and actual_coverage < minimum_genre_coverage:
        failures.append(
            {
                "code": "genre-coverage-below-floor",
                "expected": minimum_genre_coverage,
                "actual": actual_coverage,
            }
        )
    warning_counts = evaluation.get("warningCounts") or {}
    for code, maximum in (expectations.get("maximumWarnings") or {}).items():
        actual = int(warning_counts.get(code) or 0)
        if actual > int(maximum):
            failures.append({"code": "warning-limit-exceeded", "warning": code, "expected": maximum, "actual": actual})
    return failures


def compare_evaluation_reports(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {"baselineAvailable": False, "qualityScoreDelta": None, "newFailures": []}
    previous_failures = {result["id"] for result in previous.get("results", []) if result.get("status") == "failed"}
    current_failures = {result["id"] for result in current.get("results", []) if result.get("status") == "failed"}
    return {
        "baselineAvailable": True,
        "qualityScoreDelta": round(
            float(current.get("averageQualityScore") or 0) - float(previous.get("averageQualityScore") or 0), 1
        ),
        "newFailures": sorted(current_failures - previous_failures),
    }


def compare_planning_variants(personalized: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare two same-scenario runs without treating either as ground truth."""
    baseline_by_id = {str(result.get("id")): result for result in baseline.get("results", [])}
    scenarios = []
    for result in personalized.get("results", []):
        reference = baseline_by_id.get(str(result.get("id")), {})
        chosen = list(result.get("trackIds", []))
        original = list(reference.get("trackIds", []))
        scenarios.append(
            {
                "id": result.get("id"),
                "personalizedQualityScore": (result.get("evaluation") or {}).get("qualityScore"),
                "baselineQualityScore": (reference.get("evaluation") or {}).get("qualityScore"),
                "changedTrackIds": sorted(set(chosen).symmetric_difference(original)),
                "orderChanged": chosen != original,
            }
        )
    return {
        "qualityScoreDelta": round(
            float(personalized.get("averageQualityScore") or 0) - float(baseline.get("averageQualityScore") or 0),
            1,
        ),
        "changedScenarioCount": sum(item["orderChanged"] for item in scenarios),
        "scenarios": scenarios,
    }
