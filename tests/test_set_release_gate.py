from __future__ import annotations

import unittest
from typing import Any

from audioextender.set_builder.release_gate import assess_ai_release, summarize_planning_jobs


def scenario(identifier: str, *, status: str = "complete", valid: bool = True, coverage: float = 1) -> dict:
    return {
        "id": identifier,
        "status": status,
        "planValid": valid,
        "evaluation": {"requestedGenreCoverage": {"ratio": coverage}},
    }


class AIReleaseGateTests(unittest.TestCase):
    def test_automated_success_still_requires_manual_listening(self) -> None:
        report = {"results": [scenario(str(index)) for index in range(5)]}
        pending = assess_ai_release(report)
        self.assertTrue(pending["automatedReady"])
        self.assertFalse(pending["released"])
        self.assertEqual(pending["failures"][0]["code"], "manual-listening-pending")
        self.assertTrue(assess_ai_release(report, manual_listening_approved=True)["released"])

    def test_invalid_or_incomplete_scenario_cannot_be_manually_overridden(self) -> None:
        report = {"results": [scenario("bad", valid=False, coverage=0.5)]}
        result = assess_ai_release(report, required_scenarios=1, manual_listening_approved=True)
        self.assertFalse(result["released"])
        self.assertEqual(
            {failure["code"] for failure in result["failures"]},
            {"invalid-plans", "incomplete-genre-coverage"},
        )

    def test_provider_timeout_blocks_release_even_when_fallback_is_valid(self) -> None:
        item = scenario("timeout")
        item["fallbackReason"] = [{"code": "provider-error", "message": "timed out"}]
        result = assess_ai_release({"results": [item]}, required_scenarios=1, manual_listening_approved=True)
        self.assertFalse(result["released"])
        self.assertEqual(result["failures"], [{"code": "ai-provider-failures", "scenarios": ["timeout"]}])

    def test_job_summary_reports_fallback_repairs_failures_and_cancellations(self) -> None:
        states: list[dict[str, Any]] = [
            {"jobId": "ai", "status": "complete", "result": {"mode": "ai-planned", "planningDurationMs": 100}},
            {
                "jobId": "fallback",
                "status": "complete",
                "result": {"mode": "deterministic-fallback", "planningDurationMs": 300, "modelRepairs": [{}]},
            },
            {"jobId": "failed", "status": "failed"},
            {"jobId": "canceled", "status": "canceled"},
        ]
        result = summarize_planning_jobs(states)
        self.assertEqual(result["aiSelectedCount"], 1)
        self.assertEqual(result["fallbackRate"], 0.5)
        self.assertEqual(result["repairedCount"], 1)
        self.assertEqual(result["averageDurationMs"], 200)
        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(result["canceledCount"], 1)


if __name__ == "__main__":
    unittest.main()
