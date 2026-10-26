from __future__ import annotations

import unittest
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.planning_jobs import PlanningCanceled, SetPlanningJobService
from audioextender.set_builder.planning_store import JsonPlanningJobStore
from audioextender.set_builder.track_planner import (
    TRACK_PLAN_SCHEMA,
    AITrackPlanner,
    SetPlanningModelClient,
    bounded_model_candidates,
    deterministic_track_plan,
    flatten_candidates,
)
from audioextender.web.routes.set_planning_routes import SetPlanningRouteDependencies, create_set_planning_router
from tests.unit.set_builder.test_set_candidate_planning import catalog_track, journey


class FakeModel:
    def __init__(self, responses: Sequence[dict | Exception], *, available: bool = True) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.available = available

    def status(self) -> dict:
        return {
            "available": self.available,
            "provider": "ollama" if self.available else "offline",
            "model": "test-model" if self.available else None,
        }

    def complete(self, payload: dict, *, timeout_seconds: float) -> dict:
        self.calls.append({"payload": payload, "timeout": timeout_seconds})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def planning_candidates(root: Path) -> tuple[dict, dict]:
    first, second = root / "one.wav", root / "two.wav"
    first.touch()
    second.touch()
    set_journey = journey("Reggaeton", "Salsa")
    pool = SetCandidateRetriever().retrieve(
        [catalog_track(1, first), catalog_track(2, second, genre="Latin / Salsa", detail="Salsa")],
        set_journey,
        section_limit=1,
    )
    return set_journey, pool


class AITrackPlannerTests(unittest.TestCase):
    def test_model_shortlist_is_available_compact_section_balanced_and_bounded(self) -> None:
        candidates = [
            {
                "id": f"downloaded:{index}",
                "available": index != 1,
                "eligibleSectionIds": ["opening" if index < 50 else "peak"],
                "relevanceScore": 100 - index,
                "descriptors": [{"value": "melodic", "provenance": "inferred", "confidence": 0.9}],
                "path": f"/private/{index}.wav",
                "reasons": [{"text": "verbose"}],
            }
            for index in range(80)
        ]
        result = bounded_model_candidates(candidates, {"opening": 8, "peak": 8})
        self.assertLessEqual(len(result), 60)
        self.assertNotIn("downloaded:1", {item["id"] for item in result})
        self.assertTrue(
            {"opening", "peak"}.issubset({section for item in result for section in item["eligibleSectionIds"]})
        )
        self.assertTrue(
            all("path" not in item and "reasons" not in item and "descriptors" not in item for item in result)
        )
        self.assertTrue(any(item["identity"] == ["melodic"] for item in result))

    def test_valid_ai_plan_is_compared_before_acceptance(self) -> None:
        with TemporaryDirectory() as temporary:
            set_journey, pool = planning_candidates(Path(temporary))
            model = FakeModel(
                [
                    {
                        "summary": "A validated rise",
                        "selections": [
                            {
                                "trackId": "downloaded:1",
                                "sectionId": "section-1",
                                "reason": "Direct opening",
                                "evidence": "ai-suggested",
                            },
                            {
                                "trackId": "downloaded:2",
                                "sectionId": "section-2",
                                "reason": "Direct finish",
                                "evidence": "ai-suggested",
                            },
                        ],
                    }
                ]
            )
            result = AITrackPlanner(model, SetPlanValidator(duration_tolerance=0.5)).plan(
                brief={"vibe": "balanced"},
                journey=set_journey,
                candidate_pool=pool,
                target_track_count=2,
                target_duration_minutes=8,
                required_ids=set(),
                excluded_ids=set(),
                locked_ids=set(),
            )
        self.assertEqual(result["mode"], "deterministic-fallback")
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["comparison"]["winner"], "deterministic")
        self.assertEqual(result["fallbackReason"]["code"], "ai-quality-below-baseline")
        self.assertEqual(result["observability"]["attempts"][0]["outcome"], "deterministic-selected")
        self.assertIn("plannerTotalMs", result["observability"])
        self.assertEqual([track["id"] for track in result["plan"]], ["downloaded:1", "downloaded:2"])
        self.assertTrue(all("path" not in track for track in model.calls[0]["payload"]["candidates"]))
        self.assertTrue(all("path" not in track for track in result["plan"]))

    def test_repairs_hallucinated_id_without_a_second_model_call(self) -> None:
        invalid = {
            "summary": "Invalid",
            "selections": [
                {"trackId": "invented:99", "sectionId": "section-1", "reason": "Invented", "evidence": "ai-suggested"}
            ],
        }
        with TemporaryDirectory() as temporary:
            set_journey, pool = planning_candidates(Path(temporary))
            model = FakeModel([invalid])
            result = AITrackPlanner(model, SetPlanValidator(duration_tolerance=0.5)).plan(
                brief={},
                journey=set_journey,
                candidate_pool=pool,
                target_track_count=2,
                target_duration_minutes=8,
                required_ids=set(),
                excluded_ids=set(),
                locked_ids=set(),
            )
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual({track["id"] for track in result["plan"]}, {"downloaded:1", "downloaded:2"})
        self.assertTrue(result["modelRepairs"])

    def test_provider_failures_fall_back_to_deterministic_valid_plan(self) -> None:
        failures = [httpx.TimeoutException("slow") for _ in range(3)]
        with TemporaryDirectory() as temporary:
            set_journey, pool = planning_candidates(Path(temporary))
            result = AITrackPlanner(
                FakeModel(failures), SetPlanValidator(duration_tolerance=0.5), maximum_attempts=3
            ).plan(
                brief={},
                journey=set_journey,
                candidate_pool=pool,
                target_track_count=2,
                target_duration_minutes=8,
                required_ids=set(),
                excluded_ids=set(),
                locked_ids=set(),
            )
        self.assertEqual(result["mode"], "deterministic-fallback")
        self.assertTrue(result["valid"])
        self.assertEqual(result["attempts"], 3)

    def test_offline_mode_never_calls_model(self) -> None:
        with TemporaryDirectory() as temporary:
            set_journey, pool = planning_candidates(Path(temporary))
            model = FakeModel([], available=False)
            result = AITrackPlanner(model, SetPlanValidator(duration_tolerance=0.5)).plan(
                brief={},
                journey=set_journey,
                candidate_pool=pool,
                target_track_count=2,
                target_duration_minutes=8,
                required_ids=set(),
                excluded_ids=set(),
                locked_ids=set(),
            )
        self.assertEqual(result["mode"], "deterministic-fallback")
        self.assertEqual(model.calls, [])

    def test_cancellation_after_provider_response_is_not_swallowed_as_provider_failure(self) -> None:
        with TemporaryDirectory() as temporary:
            set_journey, pool = planning_candidates(Path(temporary))
            model = FakeModel([{"summary": "ignored", "selections": []}])
            checks = 0

            def cancel() -> None:
                nonlocal checks
                checks += 1
                if checks == 2:
                    raise PlanningCanceled("canceled checkpoint")

            with self.assertRaises(PlanningCanceled):
                AITrackPlanner(model, SetPlanValidator()).plan(
                    brief={},
                    journey=set_journey,
                    candidate_pool=pool,
                    target_track_count=2,
                    target_duration_minutes=8,
                    required_ids=set(),
                    excluded_ids=set(),
                    locked_ids=set(),
                    cancel_check=cancel,
                )

    def test_deterministic_plan_preserves_section_order(self) -> None:
        with TemporaryDirectory() as temporary:
            set_journey, pool = planning_candidates(Path(temporary))
            result = deterministic_track_plan(pool, set_journey, 2)
        self.assertEqual(
            [selection["sectionId"] for selection in result["selections"]],
            ["section-1", "section-2"],
        )

    def test_deterministic_regeneration_preserves_locked_track_section(self) -> None:
        pool = {
            "sections": [
                {
                    "sectionId": "opening",
                    "candidates": [{"id": "downloaded:2", "available": True, "relevanceScore": 100}],
                },
                {
                    "sectionId": "peak",
                    "candidates": [
                        {"id": "downloaded:1", "available": True, "locked": True, "relevanceScore": 1000},
                        {"id": "downloaded:3", "available": True, "relevanceScore": 90},
                    ],
                },
            ]
        }
        set_journey = {
            "sections": [
                {"id": "opening", "durationPercent": 50},
                {"id": "peak", "durationPercent": 50},
            ]
        }
        result = deterministic_track_plan(
            pool,
            set_journey,
            2,
            locked_sections={"downloaded:1": "peak"},
        )
        locked = next(item for item in result["selections"] if item["trackId"] == "downloaded:1")
        self.assertEqual(locked["sectionId"], "peak")

    def test_deterministic_plan_balances_relevance_with_section_runtime(self) -> None:
        candidates = [
            {
                "id": f"downloaded:{index}",
                "available": True,
                "durationSeconds": duration,
                "relevanceScore": relevance,
            }
            for index, duration, relevance in (
                (1, 600, 100),
                (2, 600, 99),
                (3, 240, 90),
                (4, 240, 89),
            )
        ]
        pool = {"sections": [{"sectionId": "opening", "candidates": candidates}]}
        set_journey = {"sections": [{"id": "opening", "durationPercent": 100}]}
        result = deterministic_track_plan(pool, set_journey, 2, target_duration_minutes=8)
        self.assertEqual(
            [selection["trackId"] for selection in result["selections"]],
            ["downloaded:3", "downloaded:4"],
        )

    def test_deterministic_plan_never_uses_two_versions_of_one_recording(self) -> None:
        pool = {
            "sections": [
                {
                    "sectionId": "opening",
                    "candidates": [
                        {
                            "id": "downloaded:1",
                            "recordingKey": "recording:DSC-1",
                            "available": True,
                            "relevanceScore": 99,
                        },
                    ],
                },
                {
                    "sectionId": "peak",
                    "candidates": [
                        {
                            "id": "downloaded:2",
                            "recordingKey": "recording:DSC-1",
                            "available": True,
                            "relevanceScore": 100,
                        },
                        {
                            "id": "downloaded:3",
                            "recordingKey": "recording:DSC-3",
                            "available": True,
                            "relevanceScore": 90,
                        },
                    ],
                },
            ]
        }
        set_journey = {
            "sections": [
                {"id": "opening", "durationPercent": 50},
                {"id": "peak", "durationPercent": 50},
            ]
        }
        result = deterministic_track_plan(pool, set_journey, 2)
        self.assertEqual([item["trackId"] for item in result["selections"]], ["downloaded:1", "downloaded:3"])

    def test_flattened_candidates_merge_multi_section_eligibility(self) -> None:
        candidates = flatten_candidates(
            {
                "sections": [
                    {"candidates": [{"id": "downloaded:1", "eligibleSectionIds": ["opening"]}]},
                    {"candidates": [{"id": "downloaded:1", "eligibleSectionIds": ["peak"]}]},
                ]
            }
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["eligibleSectionIds"], ["opening", "peak"])


class SetPlanningModelClientTests(unittest.TestCase):
    def test_ollama_request_uses_strict_schema_and_timeout(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"content": '{"summary":"ok","selections":[]}'}}
        configuration = IntentionPlanner(provider="ollama", ollama_model="test")
        client = SetPlanningModelClient(configuration)
        with (
            patch.object(IntentionPlanner, "status", return_value={"provider": "ollama", "model": "test"}),
            patch("audioextender.set_builder.track_planner.httpx.post", return_value=response) as post,
        ):
            result = client.complete(
                {
                    "candidates": [{"id": "downloaded:1"}, {"id": "downloaded:2"}],
                    "journey": {"sections": [{"id": "opening"}, {"id": "peak"}]},
                    "targetTrackCount": 12,
                },
                timeout_seconds=12,
            )
        self.assertEqual(result["summary"], "ok")
        response_schema = post.call_args.kwargs["json"]["format"]
        self.assertEqual(response_schema["properties"]["selections"]["minItems"], 12)
        self.assertEqual(response_schema["properties"]["selections"]["maxItems"], 12)
        item_properties = response_schema["properties"]["selections"]["items"]["properties"]
        self.assertEqual(item_properties["trackId"]["enum"], ["downloaded:1", "downloaded:2"])
        self.assertEqual(item_properties["sectionId"]["enum"], ["opening", "peak"])
        self.assertEqual(TRACK_PLAN_SCHEMA["properties"]["selections"]["minItems"], 1)
        self.assertEqual(post.call_args.kwargs["timeout"], 12)
        options = post.call_args.kwargs["json"]["options"]
        self.assertEqual(options["num_ctx"], 16384)
        self.assertEqual(options["num_predict"], 540)

    def test_openai_request_disables_storage(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"output_text": '{"summary":"ok","selections":[]}'}
        configuration = IntentionPlanner(provider="openai", api_key="secret", model="test")
        client = SetPlanningModelClient(configuration)
        with (
            patch.object(IntentionPlanner, "status", return_value={"provider": "openai", "model": "test"}),
            patch("audioextender.set_builder.track_planner.httpx.post", return_value=response) as post,
        ):
            client.complete({"candidates": []}, timeout_seconds=10)
        self.assertFalse(post.call_args.kwargs["json"]["store"])


class ImmediateThread:
    def __init__(self, *, target: Callable[..., None], args: tuple, **_: object) -> None:
        self.target = target
        self.args = args

    def start(self) -> None:
        self.target(*self.args)


class DeferredThread(ImmediateThread):
    started: list[DeferredThread] = []

    def start(self) -> None:
        self.started.append(self)


class SetPlanningJobServiceTests(unittest.TestCase):
    def request(self) -> dict:
        return {
            "brief": {},
            "journey": journey("Reggaeton", "Salsa"),
            "required_track_ids": [],
            "excluded_track_ids": [],
            "locked_track_ids": [],
            "locked_track_sections": {},
            "base_plan_revision": {"id": "revision-1", "number": 1},
            "target_duration_minutes": 8,
            "target_track_count": 2,
            "per_section_limit": 1,
            "total_limit": 2,
        }

    def test_job_runs_to_completion_without_blocking_route_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracks = [catalog_track(1, root / "one.wav"), catalog_track(2, root / "two.wav", genre="Salsa")]
            for track in tracks:
                Path(track["job"]["library_path"]).touch()
            planner = AITrackPlanner(FakeModel([], available=False), SetPlanValidator(duration_tolerance=0.5))
            service = SetPlanningJobService(
                lambda: tracks, SetCandidateRetriever(), planner, thread_factory=ImmediateThread
            )
            state = service.start(self.request())
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["result"]["mode"], "deterministic-fallback")

    def test_job_rejects_two_locked_versions_of_one_recording_with_actionable_error(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracks = [
                catalog_track(1, root / "original.wav", recording_code="DSC-000001"),
                catalog_track(2, root / "remix.wav", recording_code="DSC-000001"),
            ]
            for track in tracks:
                Path(track["job"]["library_path"]).touch()
            planner = AITrackPlanner(FakeModel([], available=False), SetPlanValidator())
            service = SetPlanningJobService(
                lambda: tracks, SetCandidateRetriever(), planner, thread_factory=ImmediateThread
            )
            request = self.request()
            request["locked_track_ids"] = ["downloaded:1", "downloaded:2"]

            state = service.start(request)

        self.assertEqual(state["status"], "failed")
        self.assertIn("multiple versions of the same song", state["error"])
        self.assertIn("Keep one version", state["error"])

    def test_new_job_cancels_stale_inflight_job_and_retry_is_guarded(self) -> None:
        DeferredThread.started = []
        planner = AITrackPlanner(FakeModel([], available=False), SetPlanValidator())
        service = SetPlanningJobService(lambda: [], SetCandidateRetriever(), planner, thread_factory=DeferredThread)
        first = service.start(self.request())
        second = service.start(self.request())
        self.assertEqual(service.status(first["jobId"])["status"], "canceling")
        self.assertEqual(second["status"], "pending")
        with self.assertRaises(ValueError):
            service.retry(second["jobId"])

    def test_cancel_unknown_job_is_reported(self) -> None:
        service = SetPlanningJobService(
            lambda: [], SetCandidateRetriever(), AITrackPlanner(FakeModel([], available=False), SetPlanValidator())
        )
        with self.assertRaises(KeyError):
            service.cancel("missing")

    def test_http_job_contract_returns_a_validated_completed_plan(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracks = [catalog_track(1, root / "one.wav"), catalog_track(2, root / "two.wav", genre="Salsa")]
            for track in tracks:
                Path(track["job"]["library_path"]).touch()
            planner = AITrackPlanner(FakeModel([], available=False), SetPlanValidator(duration_tolerance=0.5))
            jobs = SetPlanningJobService(
                lambda: tracks, SetCandidateRetriever(), planner, thread_factory=ImmediateThread
            )
            app = FastAPI()
            app.include_router(
                create_set_planning_router(
                    SetPlanningRouteDependencies(
                        catalog_cache_path=root / "unused.json",
                        ensure_catalog_current=lambda: None,
                        write_catalog_cache=lambda: None,
                        candidate_retriever=SetCandidateRetriever(),
                        plan_validator=SetPlanValidator(duration_tolerance=0.5),
                        track_planner=planner,
                        planning_jobs=jobs,
                    )
                )
            )
            client = TestClient(app)
            request = self.request()
            request["target_duration_minutes"] = 15
            request["per_section_limit"] = 2
            response = client.post("/api/set-builder/plan-tracks", json=request)
            status = client.get(f"/api/set-builder/plan-tracks/{response.json()['jobId']}")
            telemetry = client.get("/api/set-builder/ai-observability")
            invalid = client.post(
                "/api/set-builder/plan-tracks",
                json={**request, "locked_track_sections": {"downloaded:1": "missing-section"}},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "complete", status.json())
        self.assertTrue(status.json()["result"]["valid"])
        self.assertIn("evaluation", status.json()["result"])
        self.assertIn("planningDurationMs", status.json()["result"])
        self.assertEqual(status.json()["result"]["basePlanRevision"]["id"], "revision-1")
        self.assertIn("candidateRetrievalMs", status.json()["result"]["observability"])
        self.assertEqual(telemetry.status_code, 200)
        self.assertEqual(telemetry.json()["completedCount"], 1)
        self.assertEqual(invalid.status_code, 422)

    def test_persisted_inflight_job_becomes_retryable_after_restart(self) -> None:
        with TemporaryDirectory() as temporary:
            store = JsonPlanningJobStore(Path(temporary) / "planning.json")
            request = self.request()
            store.save(
                {
                    "interrupted": {
                        "jobId": "interrupted",
                        "status": "processing",
                        "stage": "Planning",
                        "progress": 35,
                        "result": None,
                        "error": None,
                        "retryable": False,
                        "retryOf": None,
                        "createdAt": "2026-01-01T00:00:00+00:00",
                        "updatedAt": "2026-01-01T00:00:00+00:00",
                    }
                },
                {"interrupted": request},
            )
            service = SetPlanningJobService(
                lambda: [],
                SetCandidateRetriever(),
                AITrackPlanner(FakeModel([], available=False), SetPlanValidator()),
                store=store,
            )
            state = service.status("interrupted")
            reloaded_states, _ = store.load()
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["retryable"])
        self.assertIn("restarted", state["error"])
        self.assertEqual(reloaded_states["interrupted"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
