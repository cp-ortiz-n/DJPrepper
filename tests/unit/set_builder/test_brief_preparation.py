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
            "Melodic Latin House",
            [{"canonical": "latin house", "aliases": ["latin house"], "count": 0}],
            schema=BRIEF_SCHEMA,
            instructions=BRIEF_INSTRUCTIONS,
        )
        self.assertEqual(result["journey"]["evidence"], "ai-interpreted")
        self.assertEqual(result["journey"]["sections"][0]["genres"], ["latin house"])
        self.assertFalse(result["cache"]["hit"])

    def test_explicit_disco_repairs_empty_model_genres_before_journey_review(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.return_value = {
            "required": [],
            "preferred": ["disco"],
            "avoided": [],
            "requestedGenres": [],
            "optionalGenres": [],
            "genreSequence": [],
            "drift": "none",
            "vibe": "dance-party",
            "curve": "steady",
            "opening": None,
            "ending": None,
            "explanation": "Keep a steady disco groove.",
            "provider": "ollama",
            "model": "test-local",
            "journey": {
                "summary": "A continuous disco set.",
                "sections": [
                    {
                        "name": "Main Body",
                        "purpose": "Core dance performance",
                        "durationPercent": 100,
                        "genres": [],
                        "characteristics": ["groovy"],
                        "energyStart": 7,
                        "energyEnd": 8,
                    }
                ],
            },
        }
        result = BriefPreparationService(planner).prepare(
            "Create a disco set",
            [{"canonical": "Disco & Funk", "aliases": ["Disco"], "count": 12}],
            60,
        )
        self.assertEqual(result["interpretation"]["requestedGenres"], ["disco & funk"])
        self.assertEqual(result["interpretation"]["genreSequence"], ["disco & funk"])
        self.assertEqual(result["journey"]["sections"][0]["genres"], ["disco & funk"])
        self.assertEqual(result["journey"]["genrePolicy"]["mode"], "strict")

    def test_genre_matrix_repairs_empty_model_output_into_complete_journeys(self) -> None:
        vocabulary = [
            {"canonical": "House", "aliases": ["House"], "count": 40},
            {"canonical": "Disco & Funk", "aliases": ["Disco", "Funk"], "count": 20},
            {"canonical": "Techno", "aliases": ["Techno"], "count": 35},
            {"canonical": "Hard Techno", "aliases": ["Hard Techno"], "count": 15},
            {"canonical": "Latin Techno", "aliases": ["Latin Techno"], "count": 8},
            {"canonical": "Rock & Alternative", "aliases": ["Rock", "Alternative"], "count": 12},
            {"canonical": "R&B & Soul", "aliases": ["R&B", "Soul"], "count": 10},
            {
                "canonical": "Hip-Hop & Rap",
                "aliases": ["Hip Hop", "Rap", "Afropop"],
                "count": 50,
                "aliasCounts": {"Afropop": 1},
            },
            {"canonical": "Afro House", "aliases": ["Afropop"], "count": 18, "aliasCounts": {"Afropop": 3}},
        ]
        cases = {
            "House set": "house",
            "Disco set": "disco & funk",
            "Funk set": "disco & funk",
            "Hard Techno set": "hard techno",
            "Latin Techno set": "latin techno",
            "Rock set": "rock & alternative",
            "R&B set": "r&b & soul",
            "Hip Hop set": "hip hop & rap",
            "Afropop set": "afro house",
        }
        for brief, expected in cases.items():
            with self.subTest(brief=brief):
                planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
                planner.interpret.return_value = {
                    "required": [],
                    "preferred": [],
                    "avoided": [],
                    "requestedGenres": [],
                    "optionalGenres": [],
                    "genreSequence": [],
                    "drift": "none",
                    "vibe": "balanced",
                    "curve": "rise",
                    "opening": None,
                    "ending": None,
                    "explanation": "Catalog-derived fallback.",
                    "provider": "ollama",
                    "model": "test-local",
                }
                result = BriefPreparationService(planner).prepare(brief, vocabulary, 60)
                self.assertEqual(result["interpretation"]["requestedGenres"], [expected])
                self.assertTrue(result["journey"]["sections"])
                self.assertTrue(all(section["genres"] == [expected] for section in result["journey"]["sections"]))

    def test_reuses_versioned_result_for_identical_request(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.return_value = self.interpretation()
        service = BriefPreparationService(planner)

        service.prepare("Same brief", ["Latin House"], 60)
        cached = service.prepare("Same brief", ["Latin House"], 60)

        planner.interpret.assert_called_once()
        self.assertTrue(cached["cache"]["hit"])

    def test_latin_house_warmup_is_ordered_before_latin_techno(self) -> None:
        planner = Mock(provider="ollama", ollama_model="test-local", model="cloud-test")
        planner.interpret.return_value = {
            "required": [],
            "preferred": [],
            "avoided": [],
            "requestedGenres": [],
            "optionalGenres": [],
            "genreSequence": [],
            "drift": "none",
            "vibe": "dance-party",
            "curve": "rise",
            "opening": None,
            "ending": None,
            "explanation": "Start with Latin House and move into Latin Techno.",
            "provider": "ollama",
            "model": "test-local",
        }
        result = BriefPreparationService(planner).prepare(
            "Create a latin techno set, latin house to warmup",
            ["latin techno", "latin house"],
            60,
        )

        self.assertEqual(result["interpretation"]["requestedGenres"], ["latin techno", "latin house"])
        self.assertEqual(result["interpretation"]["genreSequence"], ["latin house", "latin techno"])
        self.assertEqual(result["journey"]["sections"][0]["genres"], ["latin house"])
        self.assertEqual(result["journey"]["sections"][-1]["genres"], ["latin techno"])

    def test_combined_ollama_response_preserves_ai_journey_in_one_call(self) -> None:
        import json

        interpretation = self.interpretation()
        interpretation["journey"] = {
            "summary": "Keep the dance floor energetic.",
            "sections": [
                {
                    "name": "Peak",
                    "purpose": "High energy with an unrelated detour",
                    "durationPercent": 100,
                    "genres": ["Amapiano"],
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
            result = service.prepare("High energy Latin House", ["Latin House", "Amapiano"], 60)
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"]["format"], BRIEF_SCHEMA)
        self.assertEqual(result["journey"]["evidence"], "ai-planned")
        self.assertEqual(result["journey"]["sections"][0]["energyStart"], 8)
        self.assertEqual(result["journey"]["sections"][0]["genres"], ["latin house"])
        self.assertEqual(result["journey"]["sections"][0]["suggestedGenres"], ["amapiano"])
        self.assertEqual(result["journey"]["genrePolicy"]["mode"], "strict")
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
                    "catalog_vocabulary": [{"canonical": "Latin House", "aliases": ["Guaracha"], "count": 9}],
                    "duration_minutes": 45,
                },
            )
            self.assertEqual(response.status_code, 200)
            preparation.prepare.assert_called_once_with(
                "Latin House",
                [{"canonical": "latin house", "aliases": ["latin house", "guaracha"], "count": 9}],
                45,
            )
            invalid = client.post("/api/set-builder/prepare-brief", json={"brief": "", "duration_minutes": 1})
            self.assertEqual(invalid.status_code, 422)

    def test_route_replaces_stale_browser_vocabulary_with_server_catalog(self) -> None:
        with TemporaryDirectory() as temporary:
            catalog_path = Path(temporary) / "catalog.json"
            catalog_path.write_text(
                '{"version":11,"tracks":[],"genre_vocabulary":['
                '{"canonical":"latin techno","aliases":["latin techno"],"count":12},'
                '{"canonical":"latin house","aliases":["latin house"],"count":9}]}'
            )
            preparation = Mock()
            preparation.prepare.return_value = {"interpretation": {}, "journey": {"sections": []}}
            app = FastAPI()
            app.include_router(
                create_set_builder_router(
                    SetBuilderRouteDependencies(
                        catalog_cache_path=catalog_path,
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

            response = TestClient(app).post(
                "/api/set-builder/prepare-brief",
                json={
                    "brief": "Create a latin techno set, latin house to warmup",
                    "catalog_vocabulary": ["house"],
                    "duration_minutes": 60,
                },
            )

            self.assertEqual(response.status_code, 200)
            vocabulary = preparation.prepare.call_args.args[1]
            self.assertEqual([item["canonical"] for item in vocabulary], ["latin techno", "latin house"])

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
