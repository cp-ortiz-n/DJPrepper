from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

import httpx

from audioextender.set_builder.intention_planner import (
    INTENTION_SCHEMA,
    IntentionPlanner,
    sanitize_interpretation,
)


class IntentionPlannerTests(unittest.TestCase):
    def test_default_local_model_matches_the_mac_launcher(self) -> None:
        self.assertEqual(IntentionPlanner().ollama_model, "qwen3.5:4b")

    def test_planner_requires_server_side_key(self) -> None:
        planner = IntentionPlanner(provider="offline")
        self.assertFalse(planner.available)
        with self.assertRaisesRegex(RuntimeError, "No local or cloud"):
            planner.interpret("melodic beginning", [])

    def test_planner_returns_strict_positional_interpretation(self) -> None:
        interpretation = {
            "required": [],
            "preferred": ["melodic", "warm-up"],
            "avoided": [],
            "requestedGenres": ["latin house"],
            "optionalGenres": ["schranz"],
            "genreSequence": ["latin house", "schranz"],
            "drift": "moderate",
            "vibe": "warm-up",
            "curve": "waves",
            "opening": "melodic",
            "ending": None,
            "explanation": "Open melodically, then move through energy waves.",
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"output_text": json.dumps(interpretation)}
        planner = IntentionPlanner(provider="openai", api_key="test-key", model="test-model")
        with (
            patch("audioextender.set_builder.intention_planner.httpx.post", return_value=response) as post,
            self.assertLogs("uvicorn.error", level="INFO") as logs,
        ):
            result = planner.interpret(
                "Start melodic and use varying waves; add schranz if available", ["Latin House", "Schranz"]
            )
        self.assertEqual(result["opening"], "melodic")
        self.assertEqual(result["optionalGenres"], ["schranz"])
        self.assertEqual(result["genreSequence"], ["schranz"])
        self.assertEqual(result["provider"], "openai")
        request = post.call_args.kwargs["json"]
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertIn("provider=openai model=test-model", " ".join(logs.output))

    def test_local_ollama_is_primary_and_uses_the_same_schema(self) -> None:
        interpretation = {
            "required": [],
            "preferred": ["melodic"],
            "avoided": [],
            "requestedGenres": ["latin techno"],
            "optionalGenres": [],
            "genreSequence": ["latin techno"],
            "drift": "low",
            "vibe": "warm-up",
            "curve": "rise",
            "opening": "melodic",
            "ending": None,
            "explanation": "Begin melodically.",
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"content": json.dumps(interpretation)}}
        planner = IntentionPlanner(provider="auto", ollama_model="test-local")
        with patch("audioextender.set_builder.intention_planner.httpx.post", return_value=response) as post:
            result = planner.interpret("melodic beginning", ["Latin Techno"])
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["model"], "test-local")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(post.call_args.kwargs["json"]["format"], INTENTION_SCHEMA)

    def test_schema_label_hallucinations_are_removed(self) -> None:
        result = sanitize_interpretation(
            {
                "required": ["requestedGenres", "Spanish vocals"],
                "preferred": ["opening", "melodic"],
                "avoided": ["venue", "generic instrumental techno"],
                "requestedGenres": ["Latin House", "Invented Club Music"],
                "optionalGenres": ["some SCHRAN: Schranz"],
                "genreSequence": ["Latin House", "some SCHRAN: Schranz"],
            },
            ["Latin House", "Schranz", "Bachata"],
        )
        self.assertEqual(result["required"], ["spanish vocals"])
        self.assertEqual(result["preferred"], ["melodic"])
        self.assertEqual(result["avoided"], ["generic instrumental techno"])
        self.assertEqual(result["requestedGenres"], ["latin house"])
        self.assertEqual(result["optionalGenres"], ["schranz"])
        self.assertEqual(result["genreSequence"], ["latin house", "schranz"])

    def test_inferred_genre_is_removed_from_explicit_journey(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": ["melodic"],
                "avoided": [],
                "requestedGenres": ["Latin House", "Cumbia", "Latin Techno"],
                "optionalGenres": [],
                "genreSequence": ["Latin House", "Cumbia", "Latin Techno"],
            },
            ["Latin House", "Cumbia", "Latin Techno"],
            "Start melodic, then Cumbia, and end with Latin Techno.",
        )
        self.assertEqual(result["genreSequence"], ["cumbia", "latin techno"])

    def test_exact_genre_request_disables_unrequested_genre_drift(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": [],
                "avoided": [],
                "requestedGenres": ["Latin Techno"],
                "optionalGenres": [],
                "genreSequence": ["Latin Techno"],
                "drift": "moderate",
            },
            ["Latin Techno", "Latin House", "Amapiano"],
            "Create a Latin Techno set",
        )
        self.assertEqual(result["drift"], "none")

    def test_exact_genre_request_removes_nested_parent_and_invented_neighbors(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": [],
                "avoided": [],
                "requestedGenres": ["Latin Techno", "Techno"],
                "optionalGenres": ["Latin House", "Latin Pop", "Latin R&B"],
                "genreSequence": ["Latin Techno", "Techno", "Latin House"],
                "drift": "moderate",
            },
            ["Latin Techno", "Techno", "Latin House", "Latin Pop", "Latin R&B"],
            "Create a Latin Techno set",
        )
        self.assertEqual(result["requestedGenres"], ["latin techno"])
        self.assertEqual(result["optionalGenres"], [])
        self.assertEqual(result["genreSequence"], ["latin techno"])
        self.assertEqual(result["drift"], "none")

    def test_separately_named_parent_and_specific_genres_are_both_preserved(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": [],
                "avoided": [],
                "requestedGenres": ["Techno", "Latin Techno"],
                "optionalGenres": [],
                "genreSequence": ["Techno", "Latin Techno"],
                "drift": "none",
            },
            ["Latin Techno", "Techno"],
            "Start with Techno, then move into Latin Techno",
        )
        self.assertEqual(result["requestedGenres"], ["techno", "latin techno"])
        self.assertEqual(result["genreSequence"], ["techno", "latin techno"])

    def test_warmup_only_genre_is_preserved_for_unrelated_catalog_pairs(self) -> None:
        cases = [
            ("Bachata", "Salsa"),
            ("Amapiano", "Afro House"),
            ("Disco & Funk", "Drum & Bass"),
        ]
        for opening, core in cases:
            with self.subTest(opening=opening, core=core):
                result = sanitize_interpretation(
                    {
                        "required": [],
                        "preferred": [],
                        "avoided": [],
                        "requestedGenres": [opening, core],
                        "optionalGenres": [],
                        "genreSequence": [opening, core],
                        "drift": "none",
                    },
                    [opening, core],
                    f"Create a {core} set, with {opening} just for the warmup, but more than half will be {core}",
                )

                self.assertEqual(result["genreSequence"], [opening.casefold(), core.casefold()])
                self.assertEqual(result["openingGenres"], [opening.casefold()])

    def test_high_energy_disco_techno_and_latin_techno_keeps_every_explicit_genre(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": ["high energy"],
                "avoided": [],
                "requestedGenres": [],
                "optionalGenres": [],
                "genreSequence": [],
                "drift": "none",
            },
            [
                {"canonical": "Disco & Funk", "aliases": ["Disco", "Funk"]},
                "Techno",
                "Latin Techno",
            ],
            "Implement a high energy disco techno, latin techno set",
        )

        self.assertEqual(result["requestedGenres"], ["disco & funk", "techno", "latin techno"])
        self.assertEqual(result["genreSequence"], ["disco & funk", "techno", "latin techno"])

    def test_common_short_name_maps_to_catalog_genre(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": [],
                "avoided": [],
                "requestedGenres": ["Disco & Funk"],
                "optionalGenres": [],
                "genreSequence": ["Disco & Funk"],
                "drift": "none",
            },
            [
                {"canonical": "Disco & Funk", "aliases": ["Disco"], "count": 24},
                {"canonical": "Techno", "aliases": ["Techno"], "count": 50},
            ],
            "Build a disco set",
        )
        self.assertEqual(result["requestedGenres"], ["disco & funk"])
        self.assertEqual(result["genreSequence"], ["disco & funk"])

    def test_common_short_name_prefers_canonical_parent_over_same_named_detail(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": ["disco"],
                "avoided": [],
                "requestedGenres": ["disco"],
                "optionalGenres": [],
                "genreSequence": ["disco"],
                "drift": "none",
            },
            [{"canonical": "Disco & Funk", "aliases": ["disco"], "count": 24}],
            "Create a disco set",
        )
        self.assertEqual(result["requestedGenres"], ["disco & funk"])
        self.assertEqual(result["genreSequence"], ["disco & funk"])

    def test_related_genre_drift_requires_explicit_authorization(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": [],
                "avoided": [],
                "requestedGenres": ["Latin Techno"],
                "optionalGenres": [],
                "genreSequence": ["Latin Techno"],
                "drift": "none",
            },
            ["Latin Techno", "Latin House"],
            "Create a Latin Techno set and allow related genres",
        )
        self.assertEqual(result["drift"], "moderate")

    def test_negated_catalog_genre_is_excluded_instead_of_requested(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": ["high energy", "rap"],
                "avoided": [],
                "requestedGenres": ["Indian / South Asian", "Hip-Hop & Rap"],
                "optionalGenres": [],
                "genreSequence": ["Indian / South Asian", "Hip-Hop & Rap"],
                "drift": "none",
            },
            [
                {"canonical": "Indian / South Asian", "aliases": ["Indian", "South Asian"]},
                {"canonical": "Hip-Hop & Rap", "aliases": ["Hip Hop", "Rap"]},
            ],
            "Create an Indian party song set, high energy all around. No rap",
        )
        self.assertEqual(result["requestedGenres"], ["indian south asian"])
        self.assertEqual(result["genreSequence"], ["indian south asian"])
        self.assertEqual(result["excludedGenres"], ["hip hop & rap"])
        self.assertIn("hip hop & rap", result["avoided"])
        self.assertNotIn("rap", result["preferred"])

    def test_warmup_assignment_controls_sequence_instead_of_text_order(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": [],
                "avoided": [],
                "requestedGenres": ["Latin Techno", "Latin House"],
                "optionalGenres": [],
                "genreSequence": ["Latin Techno", "Latin House"],
                "drift": "none",
            },
            ["Latin Techno", "Latin House"],
            "Create a Latin Techno set, Latin House to warmup",
        )
        self.assertEqual(result["requestedGenres"], ["latin techno", "latin house"])
        self.assertEqual(result["genreSequence"], ["latin house", "latin techno"])

    def test_prompt_policy_matrix_handles_unseen_genres_generically(self) -> None:
        vocabulary = [
            {"canonical": "Disco & Funk", "aliases": ["Disco", "Funk"]},
            "Techno",
            "House",
            "Afro House",
            "Schranz",
            "Latin House",
        ]
        cases = [
            ("Create a disco set without techno", ["disco & funk"], ["techno"]),
            ("Start with Afro House, then Techno", ["afro house", "techno"], []),
            ("Build a Latin House set, no Schranz", ["latin house"], ["schranz"]),
        ]
        for brief, sequence, excluded in cases:
            with self.subTest(brief=brief):
                result = sanitize_interpretation(
                    {
                        "required": [],
                        "preferred": [],
                        "avoided": [],
                        "requestedGenres": vocabulary,
                        "optionalGenres": [],
                        "genreSequence": vocabulary,
                        "drift": "none",
                    },
                    vocabulary,
                    brief,
                )
                self.assertEqual(result["genreSequence"], sequence)
                self.assertEqual(result["excludedGenres"], excluded)

    def test_positional_descriptor_is_not_treated_as_a_genre(self) -> None:
        result = sanitize_interpretation(
            {
                "required": [],
                "preferred": ["melodic"],
                "avoided": [],
                "requestedGenres": ["Melodic", "Cumbia"],
                "optionalGenres": [],
                "genreSequence": ["Melodic", "Cumbia"],
            },
            ["Melodic", "Cumbia"],
            "Start melodic, then Cumbia.",
        )
        self.assertEqual(result["genreSequence"], ["cumbia"])

    def test_auto_provider_falls_back_from_local_to_cloud(self) -> None:
        cloud_result = {
            "required": [],
            "preferred": ["smooth"],
            "avoided": [],
            "requestedGenres": ["latin house"],
            "optionalGenres": [],
            "genreSequence": ["latin house"],
            "drift": "low",
            "vibe": "warm-up",
            "curve": "rise",
            "opening": "melodic",
            "ending": "smooth",
            "explanation": "A gentle warm-up and smooth close.",
        }
        cloud_response = Mock()
        cloud_response.raise_for_status.return_value = None
        cloud_response.json.return_value = {"output_text": json.dumps(cloud_result)}
        planner = IntentionPlanner(provider="auto", api_key="test-key")
        with patch(
            "audioextender.set_builder.intention_planner.httpx.post",
            side_effect=[httpx.ConnectError("local runtime unavailable"), cloud_response],
        ):
            result = planner.interpret("Begin melodic and close smoothly", ["Latin House"])
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["ending"], "smooth")
