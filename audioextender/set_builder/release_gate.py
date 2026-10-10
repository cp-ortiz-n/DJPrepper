"""Deterministic Phase 2G release assessment for AI Set Builder."""

from __future__ import annotations

from typing import Any


def assess_ai_release(
    report: dict[str, Any],
    *,
    required_scenarios: int = 5,
    manual_listening_approved: bool = False,
) -> dict[str, Any]:
    """Return an explicit, non-negotiable release decision.

    Automated evidence can make a release ready for listening, but only the DJ
    can satisfy the final listening gate.
    """
    results = list(report.get("results") or [])
    failures: list[dict[str, Any]] = []
    if len(results) < required_scenarios:
        failures.append({"code": "scenario-count", "expected": required_scenarios, "actual": len(results)})
    failed = [str(item.get("id") or "unnamed") for item in results if item.get("status") != "complete"]
    if failed:
        failures.append({"code": "scenario-failures", "scenarios": failed})
    invalid = [str(item.get("id") or "unnamed") for item in results if not item.get("planValid", False)]
    if invalid:
        failures.append({"code": "invalid-plans", "scenarios": invalid})
    coverage = [
        str(item.get("id") or "unnamed")
        for item in results
        if float(((item.get("evaluation") or {}).get("requestedGenreCoverage") or {}).get("ratio") or 0) < 1
    ]
    if coverage:
        failures.append({"code": "incomplete-genre-coverage", "scenarios": coverage})
    provider_failures = [
        str(item.get("id") or "unnamed") for item in results if _provider_failed(item.get("fallbackReason"))
    ]
    if provider_failures:
        failures.append({"code": "ai-provider-failures", "scenarios": provider_failures})
    automated_ready = not failures
    if not manual_listening_approved:
        failures.append({"code": "manual-listening-pending", "message": "DJ approval is required for all scenarios."})
    return {
        "version": 1,
        "automatedReady": automated_ready,
        "manualListeningApproved": manual_listening_approved,
        "released": not failures,
        "failures": failures,
    }


def _provider_failed(reason: Any) -> bool:
    reasons = reason if isinstance(reason, list) else [reason]
    return any(isinstance(item, dict) and str(item.get("code") or "").startswith("provider-") for item in reasons)


def summarize_planning_jobs(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate persisted jobs without exposing requests or catalog data."""
    terminal = [state for state in states if state.get("status") in {"complete", "failed", "canceled"}]
    completed = [state for state in terminal if state.get("status") == "complete"]
    results = [state.get("result") or {} for state in completed]
    durations = [float(result.get("planningDurationMs") or 0) for result in results]
    fallback = [result for result in results if result.get("mode") != "ai-planned"]
    repaired = [result for result in results if result.get("modelRepairs")]
    return {
        "version": 1,
        "jobCount": len(states),
        "completedCount": len(completed),
        "failedCount": sum(state.get("status") == "failed" for state in terminal),
        "canceledCount": sum(state.get("status") == "canceled" for state in terminal),
        "aiSelectedCount": sum(result.get("mode") == "ai-planned" for result in results),
        "fallbackCount": len(fallback),
        "fallbackRate": round(len(fallback) / len(results), 3) if results else 0,
        "repairedCount": len(repaired),
        "averageDurationMs": round(sum(durations) / len(durations)) if durations else 0,
        "latest": [
            {
                "jobId": state.get("jobId"),
                "status": state.get("status"),
                "updatedAt": state.get("updatedAt"),
                "mode": (state.get("result") or {}).get("mode"),
                "provider": (state.get("result") or {}).get("provider"),
                "model": (state.get("result") or {}).get("model"),
                "durationMs": (state.get("result") or {}).get("planningDurationMs"),
                "fallbackReason": (state.get("result") or {}).get("fallbackReason"),
            }
            for state in states[-10:][::-1]
        ],
    }
