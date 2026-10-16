from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.journey_planner import JOURNEY_SCHEMA, JourneyPlanner, offline_journey, sanitize_journey
from audioextender.set_builder.saved_sets import SavedSetService
from audioextender.web.set_builder_routes import SetBuilderRouteDependencies, create_set_builder_router


class JourneyPlannerTests(unittest.TestCase):
    def test_sanitizer_rebalances_sections_and_rejects_unknown_genres(self) -> None:
        result = sanitize_journey(
            {
                "summary": "Warm up, dance, then peak.",
                "sections": [
                    {"name": "Open", "purpose": "Warm up", "durationPercent": 20,
                     "genres": ["Cumbia", "Invented Genre"], "characteristics": ["Melodic"],
                     "energyStart": 3, "energyEnd": 5},
                    {"name": "Peak", "purpose": "Finish", "durationPercent": 60,
                     "genres": ["Latin Techno"], "characteristics": ["Peak Time"],
                     "energyStart": 7, "energyEnd": 9},
                ],
            },
            ["Cumbia", "Latin Techno"],
            90,
        )
        self.assertEqual(sum(section["durationPercent"] for section in result["sections"]), 100)
        self.assertEqual(result["sections"][0]["genres"], ["cumbia"])
        self.assertEqual(result["sections"][-1]["endMinute"], 90)

    def test_offline_journey_preserves_order_and_optional_genre(self) -> None:
        journey = offline_journey(
            {"genreSequence": ["Cumbia", "Salsa", "Schranz"], "requestedGenres": [],
             "optionalGenres": ["Schranz"], "opening": "melodic", "ending": "hard",
             "curve": "waves"},
            ["Cumbia", "Salsa", "Schranz"],
            60,
        )
        self.assertEqual([section["genres"][0] for section in journey["sections"]],
                         ["cumbia", "salsa", "schranz"])
        self.assertIn("melodic", journey["sections"][0]["characteristics"])
        self.assertEqual(sum(section["durationPercent"] for section in journey["sections"]), 100)

    def test_invalid_ai_sequence_falls_back_without_losing_requested_genres(self) -> None:
        planner = JourneyPlanner(IntentionPlanner(provider="offline"))
        interpreted = {"genreSequence": ["Cumbia", "Salsa", "Latin Techno"],
                       "requestedGenres": ["Cumbia", "Salsa", "Latin Techno"], "optionalGenres": [],
                       "opening": "melodic", "ending": None, "curve": "rise"}
        invalid = {"summary": "Wrong order", "sections": [
            {"name": "Peak", "purpose": "Peak", "durationPercent": 100,
             "genres": ["Latin Techno"], "characteristics": [], "energyStart": 7, "energyEnd": 9},
        ]}
        with patch.object(JourneyPlanner, "_plan_with_provider", return_value=invalid):
            journey = planner.plan("brief", interpreted, ["Cumbia", "Salsa", "Latin Techno"], 60)
        self.assertEqual(journey["evidence"], "deterministic-fallback")
        self.assertEqual([section["genres"][0] for section in journey["sections"]],
                         ["cumbia", "salsa", "latin techno"])

    def test_ollama_journey_uses_strict_schema_and_reports_evidence(self) -> None:
        intention_planner = IntentionPlanner(provider="ollama", ollama_model="local-test")
        planner = JourneyPlanner(intention_planner)
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"content": """{
            "summary": "Rise from Cumbia into Salsa",
            "sections": [
                {"name":"Open","purpose":"Warm up","durationPercent":40,"genres":["Cumbia"],
                 "characteristics":["melodic"],"energyStart":3,"energyEnd":5},
                {"name":"Dance","purpose":"Lift the room","durationPercent":60,"genres":["Salsa"],
                 "characteristics":["danceable"],"energyStart":5,"energyEnd":8}
            ]
        }"""}}
        interpreted = {"genreSequence": ["Cumbia", "Salsa"], "requestedGenres": ["Cumbia", "Salsa"],
                       "optionalGenres": []}
        with (
            patch.object(IntentionPlanner, "status", return_value={"provider": "ollama", "model": "local-test"}),
            patch("audioextender.set_builder.journey_planner.httpx.post", return_value=response) as post,
        ):
            journey = planner.plan("Cumbia then Salsa", interpreted, ["Cumbia", "Salsa"], 60)
        self.assertEqual(journey["evidence"], "ai-planned")
        self.assertEqual(journey["provider"], "ollama")
        self.assertEqual(post.call_args.kwargs["json"]["format"], JOURNEY_SCHEMA)
        self.assertEqual(sum(section["durationPercent"] for section in journey["sections"]), 100)

    def test_plan_journey_route_passes_validated_request_to_service(self) -> None:
        with TemporaryDirectory() as temporary:
            planner = Mock()
            planner.plan.return_value = {
                "version": 1, "summary": "A journey", "durationMinutes": 45,
                "sections": [], "provider": "offline", "model": None,
                "evidence": "deterministic-fallback",
            }
            intention = Mock()
            state = Mock()
            state.get_system_state.return_value = None
            app = FastAPI()
            app.include_router(create_set_builder_router(SetBuilderRouteDependencies(
                catalog_cache_path=Path(temporary) / "catalog.json",
                ensure_catalog_current=lambda: None,
                write_catalog_cache=lambda: None,
                music_library_root=lambda: Path(temporary),
                safe_folder_name=lambda value: value,
                intention_planner=intention,
                journey_planner=planner,
                saved_sets=SavedSetService(state),
            )))
            response = TestClient(app).post("/api/set-builder/plan-journey", json={
                "brief": "Cumbia then Salsa",
                "catalog_vocabulary": ["Cumbia", "Salsa"],
                "interpreted_intention": {"genreSequence": ["Cumbia", "Salsa"]},
                "duration_minutes": 45,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["durationMinutes"], 45)
        planner.plan.assert_called_once_with(
            "Cumbia then Salsa", {"genreSequence": ["Cumbia", "Salsa"]}, ["Cumbia", "Salsa"], 45
        )


if __name__ == "__main__":
    unittest.main()
