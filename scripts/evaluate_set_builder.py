"""Run repeatable Set Builder scenarios against the current local catalog."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.evaluation_harness import (
    SetPlanningEvaluationHarness,
    compare_evaluation_reports,
    compare_planning_variants,
)
from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.plan_evaluator import SetPlanEvaluator
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.preference_learning import (
    DJPreferenceService,
    JsonPreferenceStore,
    PersonalizedCandidateRanker,
)
from audioextender.set_builder.track_planner import AITrackPlanner, SetPlanningModelClient


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("output/reports/set_builder_catalog.json"))
    parser.add_argument("--scenarios", type=Path, default=Path("tests/fixtures/set_builder_eval_scenarios.json"))
    parser.add_argument("--output", type=Path, default=Path("output/reports/set_builder_evaluation.json"))
    parser.add_argument("--preferences", type=Path, default=Path("output/reports/set_builder_preferences.json"))
    parser.add_argument("--scenario", action="append", default=[], help="Run only the named scenario; repeatable")
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    options = arguments()
    catalog = read_json(options.catalog).get("tracks", [])
    scenarios = read_json(options.scenarios).get("scenarios", [])
    if options.scenario:
        requested = set(options.scenario)
        scenarios = [scenario for scenario in scenarios if scenario.get("id") in requested]
        missing = requested - {str(scenario.get("id")) for scenario in scenarios}
        if missing:
            raise SystemExit(f"Unknown scenario(s): {', '.join(sorted(missing))}")
    configuration = IntentionPlanner.from_environment()
    baseline_harness = SetPlanningEvaluationHarness(
        SetCandidateRetriever(),
        AITrackPlanner(SetPlanningModelClient(configuration), SetPlanValidator()),
        SetPlanEvaluator(),
    )
    preferences = DJPreferenceService(JsonPreferenceStore(options.preferences))
    harness = SetPlanningEvaluationHarness(
        SetCandidateRetriever(preference_ranker=PersonalizedCandidateRanker(preferences.profile)),
        AITrackPlanner(SetPlanningModelClient(configuration), SetPlanValidator()),
        SetPlanEvaluator(),
    )
    previous = read_json(options.output) if options.output.is_file() else None
    report = harness.run(catalog, scenarios)
    baseline = baseline_harness.run(catalog, scenarios)
    report["personalizationComparison"] = compare_planning_variants(report, baseline)
    report["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["comparison"] = compare_evaluation_reports(report, previous)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = options.output.with_suffix(".pending.json")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(options.output)
    print(
        f"Set Builder evaluation: {report['completedCount']}/{report['scenarioCount']} completed · "
        f"average quality {report['averageQualityScore']} · report {options.output}"
    )
    return 0 if report["failedCount"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
