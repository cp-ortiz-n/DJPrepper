from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.evaluation_harness import (
    SetPlanningEvaluationHarness,
    compare_evaluation_reports,
)
from audioextender.set_builder.plan_evaluator import SetPlanEvaluator
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.track_planner import AITrackPlanner


class OfflineModel:
    def status(self) -> dict:
        return {"available": False, "provider": "offline", "model": None}

    def complete(self, payload: dict, *, timeout_seconds: float) -> dict:
        raise AssertionError("offline evaluation must not call a model")


class SetPlanEvaluatorTests(unittest.TestCase):
    def test_reports_scarcity_coverage_duration_repetition_and_warnings(self) -> None:
        plan = [
            {
                "id": "downloaded:1", "artist": "DJ One", "genre": "Latin / Reggaeton",
                "detailedGenres": ["Dembow"], "durationSeconds": 240, "sectionId": "opening",
                "matchTier": "direct", "descriptors": [],
            },
            {
                "id": "downloaded:2", "artist": "DJ One", "genre": "Electronic / House",
                "detailedGenres": [], "durationSeconds": 240, "sectionId": "peak",
                "matchTier": "bridge", "descriptors": [{"value": "Latin Techno"}],
            },
        ]
        journey = {"sections": [
            {"id": "opening", "genres": ["Reggaeton"]},
            {"id": "peak", "genres": ["Latin Techno"]},
        ]}
        result = SetPlanEvaluator().evaluate(
            plan, journey, [{"code": "large-bpm-jump"}], target_duration_minutes=8
        )
        self.assertEqual(result["tierCounts"], {"direct": 1, "bridge": 1})
        self.assertEqual(result["requestedGenreCoverage"]["ratio"], 1)
        self.assertEqual(result["journeyCoverage"], {"covered": 2, "total": 2})
        self.assertEqual(result["repeatedArtistPlacements"], 1)
        self.assertEqual(result["duration"]["errorPercent"], 0)
        self.assertLess(result["qualityScore"], 100)
        self.assertTrue(any("expanded" in line for line in result["disclosures"]))

    def test_empty_plan_produces_truthful_zero_coverage(self) -> None:
        result = SetPlanEvaluator().evaluate(
            [], {"sections": [{"id": "one", "genres": ["Salsa"]}]}, [], target_duration_minutes=30
        )
        self.assertEqual(result["requestedGenreCoverage"]["ratio"], 0)
        self.assertEqual(result["journeyCoverage"], {"covered": 0, "total": 1})
        self.assertEqual(result["duration"]["actualMinutes"], 0)


class SetPlanningEvaluationHarnessTests(unittest.TestCase):
    def _harness(self) -> SetPlanningEvaluationHarness:
        return SetPlanningEvaluationHarness(
            SetCandidateRetriever(),
            AITrackPlanner(OfflineModel(), SetPlanValidator(duration_tolerance=0.5)),
            SetPlanEvaluator(),
        )

    def test_runs_repeatable_catalog_scenario_and_compares_baseline(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = []
            for identifier, genre in ((1, "Reggaeton"), (2, "Salsa")):
                path = root / f"{identifier}.wav"
                path.touch()
                catalog.append({
                    "downloaded_id": identifier,
                    "genre": genre,
                    "detailed_genre": genre,
                    "analysis": {
                        "source_name": path.name, "artist": f"Artist {identifier}", "duration_seconds": 240,
                        "bpm": 120 + identifier, "key": "8A", "_energy": 0.5,
                    },
                    "job": {"id": identifier, "library_path": str(path)},
                    "descriptors": [],
                })
            scenario = {
                "id": "latin-test", "brief": {}, "targetDurationMinutes": 8, "targetTrackCount": 2,
                "journey": {"sections": [
                    {"id": "one", "durationPercent": 50, "genres": ["Reggaeton"]},
                    {"id": "two", "durationPercent": 50, "genres": ["Salsa"]},
                ]},
            }
            report = self._harness().run(catalog, [scenario])
        self.assertEqual(report["completedCount"], 1)
        self.assertEqual(report["results"][0]["trackIds"], ["downloaded:1", "downloaded:2"])
        comparison = compare_evaluation_reports(report, {**report, "averageQualityScore": 90})
        self.assertTrue(comparison["baselineAvailable"])
        self.assertEqual(comparison["newFailures"], [])

    def test_failed_scenario_discloses_unavailable_candidate_count(self) -> None:
        catalog = [{
            "downloaded_id": 1,
            "genre": "Techno",
            "analysis": {"source_name": "missing.wav", "duration_seconds": 240},
            "job": {"id": 1, "library_path": "/missing/audioextender-track.wav"},
        }]
        scenario = {
            "id": "missing-drive", "brief": {}, "targetDurationMinutes": 4, "targetTrackCount": 1,
            "journey": {"sections": [{"id": "one", "durationPercent": 100, "genres": ["Techno"]}]},
        }
        result = self._harness().run(catalog, [scenario])["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["availableCandidateCount"], 0)

    def test_scenario_expectations_turn_quality_regressions_into_failures(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "track.wav"
            path.touch()
            catalog = [{
                "downloaded_id": 1, "genre": "Techno", "detailed_genre": "Techno",
                "analysis": {"source_name": path.name, "duration_seconds": 240, "bpm": 125},
                "job": {"id": 1, "library_path": str(path)},
            }]
            scenario = {
                "id": "quality-gate", "brief": {}, "targetDurationMinutes": 4, "targetTrackCount": 1,
                "expectations": {"minimumQualityScore": 101},
                "journey": {"sections": [{"id": "one", "durationPercent": 100, "genres": ["Techno"]}]},
            }
            result = self._harness().run(catalog, [scenario])["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["acceptanceFailures"][0]["code"], "quality-below-floor")


if __name__ == "__main__":
    unittest.main()
