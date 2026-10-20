from __future__ import annotations

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.set_builder.brief_preparation import BRIEF_INSTRUCTIONS, BRIEF_SCHEMA, BriefPreparationService
from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.web.routes.set_builder_routes import SetBuilderRouteDependencies, create_set_builder_router


class BriefPreparationServiceTests(unittest.TestCase):
    def interpretation(self) -> dict:
        return {
            "required": [],
            "preferred": ["melodic"],
            "avoided": [],
            "requestedGenres": ["latin house"],
            "optionalGenres": [],
            "genreSequence": ["latin house"],
            "drift": "moderate",
            "vibe": "dance-party",
            "curve": "rise",
            "opening": "melodic",
            "ending": None,
            "explanation": "Build gradually.",
            "provider": "ollama",
            "model": "test-local",
        }

    def test_prepares_interpretation_and_journey_with_one_model_call(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.return_value = self.interpretation()
        service = BriefPreparationService(planner)

        result = service.prepare("Melodic Latin House", ["Latin House"], 60)

        planner.interpret.assert_called_once_with(
            "Melodic Latin House", ["Latin House"], schema=BRIEF_SCHEMA, instructions=BRIEF_INSTRUCTIONS
        )
        self.assertEqual(result["journey"]["evidence"], "ai-interpreted")
        self.assertEqual(result["journey"]["sections"][0]["genres"], ["latin house"])
        self.assertFalse(result["cache"]["hit"])

    def test_reuses_versioned_result_for_identical_request(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.return_value = self.interpretation()
        service = BriefPreparationService(planner)

        service.prepare("Same brief", ["Latin House"], 60)
        cached = service.prepare("Same brief", ["Latin House"], 60)

        planner.interpret.assert_called_once()
        self.assertTrue(cached["cache"]["hit"])

    def test_combined_ollama_response_preserves_ai_journey_in_one_call(self) -> None:
        import json

        interpretation = self.interpretation()
        interpretation["journey"] = {
            "summary": "Keep the dance floor energetic.",
            "sections": [
                {
                    "name": "Peak",
                    "purpose": "High energy",
                    "durationPercent": 100,
                    "genres": ["Latin House"],
                    "characteristics": ["bouncy"],
                    "energyStart": 8,
                    "energyEnd": 9,
                }
            ],
        }
        response = Mock()
        response.json.return_value = {"message": {"content": json.dumps(interpretation)}}
        service = BriefPreparationService(IntentionPlanner(provider="ollama"))
        with patch("audioextender.set_builder.intention_planner.httpx.post", return_value=response) as post:
            result = service.prepare("High energy Latin House", ["Latin House"], 60)
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"]["format"], BRIEF_SCHEMA)
        self.assertEqual(result["journey"]["evidence"], "ai-planned")
        self.assertEqual(result["journey"]["sections"][0]["energyStart"], 8)
        self.assertNotIn("journey", result["interpretation"])

    def test_cache_isolated_from_client_mutation_and_changed_duration(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.side_effect = lambda *_args, **_kwargs: self.interpretation()
        service = BriefPreparationService(planner)
        first = service.prepare("Same", ["Latin House"], 60)
        first["journey"]["sections"].clear()
        self.assertTrue(service.prepare("Same", ["Latin House"], 60)["journey"]["sections"])
        self.assertFalse(service.prepare("Same", ["Latin House"], 90)["cache"]["hit"])
        self.assertEqual(planner.interpret.call_count, 2)

    def test_failure_does_not_poison_cache_or_prevent_retry(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.side_effect = [RuntimeError("unavailable"), self.interpretation()]
        service = BriefPreparationService(planner)
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            service.prepare("Same", ["Latin House"], 60)
        result = service.prepare("Same", ["Latin House"], 60)
        self.assertEqual(planner.interpret.call_count, 2)
        self.assertFalse(result["cache"]["hit"])

    def test_route_validates_and_forwards_combined_request(self) -> None:
        with TemporaryDirectory() as temporary:
            preparation = Mock()
            preparation.prepare.return_value = {"interpretation": {}, "journey": {"sections": []}}
            app = FastAPI()
            app.include_router(
                create_set_builder_router(
                    SetBuilderRouteDependencies(
                        catalog_cache_path=Path(temporary) / "catalog.json",
                        ensure_catalog_current=lambda: None,
                        write_catalog_cache=lambda: None,
                        music_library_root=lambda: Path(temporary),
                        safe_folder_name=lambda value: value,
                        intention_planner=Mock(),
                        journey_planner=Mock(),
                        saved_sets=Mock(),
                        brief_preparation=preparation,
                    )
                )
            )
            client = TestClient(app)
            response = client.post(
                "/api/set-builder/prepare-brief",
                json={
                    "brief": "Latin House",
                    "catalog_vocabulary": ["Latin House"],
                    "duration_minutes": 45,
                },
            )
            self.assertEqual(response.status_code, 200)
            preparation.prepare.assert_called_once_with("Latin House", ["Latin House"], 45)
            invalid = client.post("/api/set-builder/prepare-brief", json={"brief": "", "duration_minutes": 1})
            self.assertEqual(invalid.status_code, 422)

    def test_deduplicates_concurrent_identical_requests(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        entered = threading.Event()
        release = threading.Event()

        def interpret(*_args: object, **_kwargs: object) -> dict:
            entered.set()
            release.wait(2)
            return self.interpretation()

        planner.interpret.side_effect = interpret
        service = BriefPreparationService(planner)
        results: list[dict] = []
        first = threading.Thread(target=lambda: results.append(service.prepare("Same", ["Latin House"], 60)))
        second = threading.Thread(target=lambda: results.append(service.prepare("Same", ["Latin House"], 60)))
        first.start()
        entered.wait(1)
        second.start()
        release.set()
        first.join(2)
        second.join(2)

        planner.interpret.assert_called_once()
        self.assertEqual(len(results), 2)
        self.assertTrue(any(result["cache"]["shared_request"] for result in results))


if __name__ == "__main__":
    unittest.main()
