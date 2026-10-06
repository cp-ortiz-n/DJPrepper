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
    def test_planner_requires_server_side_key(self) -> None:
        planner = IntentionPlanner(provider="offline")
        self.assertFalse(planner.available)
        with self.assertRaisesRegex(RuntimeError, "No local or cloud"):
            planner.interpret("melodic beginning", [])

    def test_planner_returns_strict_positional_interpretation(self) -> None:
        interpretation = {
            "required": [], "preferred": ["melodic", "warm-up"], "avoided": [],
            "requestedGenres": ["latin house"], "optionalGenres": ["schranz"],
            "drift": "moderate", "vibe": "warm-up", "curve": "waves",
            "opening": "melodic", "ending": None,
            "explanation": "Open melodically, then move through energy waves.",
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"output_text": json.dumps(interpretation)}
        planner = IntentionPlanner(provider="openai", api_key="test-key", model="test-model")
        with patch("audioextender.set_builder.intention_planner.httpx.post", return_value=response) as post:
            result = planner.interpret(
                "Start melodic and use varying waves; add schranz if available", ["Latin House", "Schranz"]
            )
        self.assertEqual(result["opening"], "melodic")
        self.assertEqual(result["optionalGenres"], ["schranz"])
        self.assertEqual(result["provider"], "openai")
        request = post.call_args.kwargs["json"]
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])

    def test_local_ollama_is_primary_and_uses_the_same_schema(self) -> None:
        interpretation = {
            "required": [], "preferred": ["melodic"], "avoided": [], "requestedGenres": ["latin techno"],
            "optionalGenres": [], "drift": "low", "vibe": "warm-up", "curve": "rise",
            "opening": "melodic", "ending": None, "explanation": "Begin melodically.",
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
            },
            ["Latin House", "Schranz", "Bachata"],
        )
        self.assertEqual(result["required"], ["spanish vocals"])
        self.assertEqual(result["preferred"], ["melodic"])
        self.assertEqual(result["avoided"], ["generic instrumental techno"])
        self.assertEqual(result["requestedGenres"], ["latin house"])
        self.assertEqual(result["optionalGenres"], ["schranz"])

    def test_auto_provider_falls_back_from_local_to_cloud(self) -> None:
        cloud_result = {
            "required": [], "preferred": ["smooth"], "avoided": [], "requestedGenres": ["latin house"],
            "optionalGenres": [], "drift": "low", "vibe": "warm-up", "curve": "rise",
            "opening": "melodic", "ending": "smooth", "explanation": "A gentle warm-up and smooth close.",
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
