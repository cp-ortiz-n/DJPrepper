"""Provider-independent policy for choosing AI or deterministic Set Builder plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audioextender.set_builder.plan_evaluator import SetPlanEvaluator


@dataclass(frozen=True)
class PlanQualityComparator:
    """Choose an AI plan only when it beats a safe deterministic baseline."""

    evaluator: SetPlanEvaluator = field(default_factory=SetPlanEvaluator)
    minimum_score_advantage: int = 1

    def compare(
        self,
        ai_validation: dict[str, Any],
        baseline_validation: dict[str, Any],
        journey: dict[str, Any],
        *,
        target_duration_minutes: int,
    ) -> dict[str, Any]:
        ai_evaluation = self.evaluator.evaluate(
            ai_validation.get("plan", []), journey, ai_validation.get("warnings", []),
            target_duration_minutes=target_duration_minutes,
        )
        baseline_evaluation = self.evaluator.evaluate(
            baseline_validation.get("plan", []), journey, baseline_validation.get("warnings", []),
            target_duration_minutes=target_duration_minutes,
        )
        score_delta = int(ai_evaluation["qualityScore"]) - int(baseline_evaluation["qualityScore"])
        coverage_preserved = (
            ai_evaluation["requestedGenreCoverage"]["ratio"]
            >= baseline_evaluation["requestedGenreCoverage"]["ratio"]
        )
        ai_selected = bool(
            ai_validation.get("valid")
            and (
                not baseline_validation.get("valid")
                or (coverage_preserved and score_delta >= self.minimum_score_advantage)
            )
        )
        if not baseline_validation.get("valid"):
            reason = "AI selected because the deterministic baseline was invalid."
        elif not coverage_preserved:
            reason = "Deterministic baseline retained because AI reduced requested-genre coverage."
        elif ai_selected:
            reason = f"AI selected after improving the deterministic quality score by {score_delta} point(s)."
        else:
            reason = (
                "Deterministic baseline retained because AI did not improve its quality score "
                f"by at least {self.minimum_score_advantage} point(s)."
            )
        return {
            "version": 1,
            "winner": "ai" if ai_selected else "deterministic",
            "reason": reason,
            "scoreDelta": score_delta,
            "coveragePreserved": coverage_preserved,
            "ai": ai_evaluation,
            "deterministic": baseline_evaluation,
        }
