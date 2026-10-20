from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.track_planner import AITrackPlanner
from audioextender.web.routes.set_planning_routes import SetPlanningRouteDependencies, create_set_planning_router


def catalog_track(
    track_id: int,
    path: Path,
    *,
    genre: str = "Latin / Reggaeton",
    detail: str = "Reggaeton",
    artist: str = "",
    energy: float = 0.6,
    bpm: float = 100,
    key: str = "8A",
    vocals: str = "mixed",
    descriptors: list[dict] | None = None,
) -> dict:
    return {
        "downloaded_id": track_id,
        "genre": genre,
        "detailed_genre": detail,
        "descriptors": descriptors or [],
        "analysis": {
            "source_name": f"Track {track_id}.wav",
            "title": f"Track {track_id}",
            "artist": artist,
            "bpm": bpm,
            "key": key,
            "_energy": energy,
            "_vocals": vocals,
            "_timing": "steady",
            "_roles": ["warm-up"],
            "duration_seconds": 240,
        },
        "job": {"id": 100 + track_id, "library_path": str(path)},
    }


def journey(*genres: str) -> dict:
    return {
        "sections": [
            {
                "id": f"section-{index}",
                "genres": [genre],
                "characteristics": ["melodic"] if index == 1 else [],
                "energyStart": 3 + index,
                "energyEnd": 4 + index,
            }
            for index, genre in enumerate(genres, start=1)
        ]
    }


class SetCandidateRetrieverTests(unittest.TestCase):
    def test_retrieves_real_available_tracks_with_stable_ids_and_evidence(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "track.wav"
            path.touch()
            result = SetCandidateRetriever().retrieve([catalog_track(7, path)], journey("Reggaeton"))
        candidate = result["sections"][0]["candidates"][0]
        self.assertEqual(candidate["id"], "downloaded:7")
        self.assertTrue(candidate["available"])
        self.assertEqual(candidate["matchTier"], "direct")
        self.assertEqual(candidate["eligibleSectionIds"], ["section-1"])
        self.assertEqual(candidate["reasons"][0]["evidence"], "verified")

    def test_prefers_authoritative_profile_over_conflicting_legacy_values(self) -> None:
        track = catalog_track(7, Path("/missing/track.wav"), energy=0.1, key="A minor", vocals="mixed")
        track["analysis"]["musical_profile"] = {
            "version": 1,
            "key": "C# major",
            "camelot": "3B",
            "energy": 0.82,
            "vocals": "vocal-safe",
            "timing": "variable",
            "roles": ["closing"],
        }

        candidate = SetCandidateRetriever().retrieve([track], journey("Reggaeton"))["sections"][0]["candidates"][0]

        self.assertEqual(candidate["key"], "C# major")
        self.assertEqual(candidate["camelot"], "3B")
        self.assertEqual(candidate["energy"], 0.82)
        self.assertEqual(candidate["vocals"], "vocal-safe")
        self.assertEqual(candidate["timing"], "variable")
        self.assertEqual(candidate["roles"], ["closing"])

    def test_honors_exclusions_and_surfaces_missing_and_unavailable_requirements(self) -> None:
        result = SetCandidateRetriever().retrieve(
            [catalog_track(1, Path("/missing/one.wav")), catalog_track(2, Path("/missing/two.wav"))],
            journey("Reggaeton"),
            required_ids={"downloaded:1", "downloaded:99"},
            excluded_ids={"downloaded:2"},
        )
        ids = {candidate["id"] for candidate in result["sections"][0]["candidates"]}
        self.assertEqual(ids, {"downloaded:1"})
        self.assertEqual(result["missingRequiredIds"], ["downloaded:99"])
        self.assertEqual(result["unavailableRequiredIds"], ["downloaded:1"])

    def test_scarce_genre_expands_to_identity_bridge_and_fallback_candidates(self) -> None:
        tracks = [
            catalog_track(
                1,
                Path("/missing/one.wav"),
                genre="Electronic / House",
                descriptors=[{"category": "sound_character", "value": "schranz", "confidence": 0.8}],
            ),
            catalog_track(2, Path("/missing/two.wav"), genre="Electronic / House", energy=0.55),
            catalog_track(3, Path("/missing/three.wav"), genre="Pop", energy=0.05),
        ]
        result = SetCandidateRetriever().retrieve(tracks, journey("Schranz"), section_limit=3)
        self.assertEqual(
            {candidate["matchTier"] for candidate in result["sections"][0]["candidates"]},
            {"identity", "bridge", "fallback"},
        )

    def test_caps_pool_and_limits_repeated_artists(self) -> None:
        tracks = [catalog_track(index, Path(f"/missing/{index}.wav"), artist="Same") for index in range(1, 7)]
        tracks.append(catalog_track(8, Path("/missing/8.wav"), artist="Different"))
        result = SetCandidateRetriever().retrieve(tracks, journey("Reggaeton"), section_limit=6, total_limit=3)
        candidates = result["sections"][0]["candidates"]
        self.assertEqual(len(candidates), 3)
        self.assertEqual(sum(candidate["artist"] == "Same" for candidate in candidates), 2)

    def test_tracks_can_be_candidates_for_multiple_sections_without_duplicate_catalog_ids(self) -> None:
        tracks = [
            catalog_track(1, Path("/missing/one.wav"), genre="Latin / Reggaeton"),
            catalog_track(2, Path("/missing/two.wav"), genre="Latin / Salsa"),
        ]
        result = SetCandidateRetriever().retrieve(tracks, journey("Reggaeton", "Salsa"), section_limit=2)
        self.assertEqual(result["candidateCount"], 2)
        self.assertEqual([len(section["candidates"]) for section in result["sections"]], [2, 2])

    def test_large_catalog_retrieval_stays_bounded_and_responsive(self) -> None:
        for size, budget in ((100, 1), (1000, 2.5), (3000, 5)):
            with self.subTest(catalog_size=size):
                tracks = [
                    catalog_track(index, Path(f"/missing/{index}.wav"), artist=f"Artist {index}")
                    for index in range(1, size + 1)
                ]
                started = perf_counter()
                result = SetCandidateRetriever().retrieve(
                    tracks, journey("Reggaeton", "Salsa", "House"), section_limit=30, total_limit=100
                )
                elapsed = perf_counter() - started
                self.assertLessEqual(result["candidateCount"], 100)
                self.assertLess(elapsed, budget, f"{size}-track retrieval took {elapsed:.2f}s")

    def test_applies_hard_brief_constraints_but_preserves_required_tracks(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            house = catalog_track(1, root / "house.wav", genre="Electronic / House")
            techno = catalog_track(2, root / "techno.wav", genre="Electronic / Techno")
            house["analysis"]["bpm"] = 120
            techno["analysis"]["bpm"] = 140
            Path(house["job"]["library_path"]).touch()
            Path(techno["job"]["library_path"]).touch()
            constrained = SetCandidateRetriever().retrieve(
                [house, techno],
                journey("House"),
                constraints={"bpmMax": 125, "excludedGenres": ["Electronic / Techno"]},
            )
            with_required = SetCandidateRetriever().retrieve(
                [house, techno],
                journey("House"),
                required_ids={"downloaded:2"},
                constraints={"bpmMax": 125, "excludedGenres": ["Electronic / Techno"]},
            )
        constrained_ids = {track["id"] for section in constrained["sections"] for track in section["candidates"]}
        required_ids = {track["id"] for section in with_required["sections"] for track in section["candidates"]}
        self.assertEqual(constrained_ids, {"downloaded:1"})
        self.assertIn("downloaded:2", required_ids)


class SetPlanValidatorTests(unittest.TestCase):
    def test_treats_half_time_bpm_as_compatible(self) -> None:
        candidates = [
            {"id": "one", "available": True, "bpm": 75, "eligibleSectionIds": ["one"]},
            {"id": "two", "available": True, "bpm": 150, "eligibleSectionIds": ["one"]},
        ]
        result = SetPlanValidator().validate(
            [
                {"trackId": "one", "sectionId": "one", "evidence": "estimated"},
                {"trackId": "two", "sectionId": "one", "evidence": "estimated"},
            ],
            candidates,
            {"sections": [{"id": "one"}]},
        )
        self.assertNotIn("large-bpm-jump", {warning["code"] for warning in result["warnings"]})

    def setUp(self) -> None:
        self.journey = journey("Reggaeton", "Salsa")
        self.candidates = [
            {
                "id": "downloaded:1",
                "available": True,
                "durationSeconds": 240,
                "bpm": 100,
                "key": "8A",
                "vocals": "vocal-forward",
            },
            {
                "id": "downloaded:2",
                "available": True,
                "durationSeconds": 240,
                "bpm": 130,
                "key": "2B",
                "vocals": "vocal-forward",
            },
        ]

    def test_accepts_complete_plan_and_reports_transition_risks(self) -> None:
        result = SetPlanValidator(duration_tolerance=0.5).validate(
            [
                {"trackId": "downloaded:1", "sectionId": "section-1"},
                {"trackId": "downloaded:2", "sectionId": "section-2"},
            ],
            self.candidates,
            self.journey,
            required_ids={"downloaded:1"},
            target_duration_minutes=8,
            target_track_count=2,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["plan"][0]["selectionReason"]["evidence"], "ai-suggested")
        self.assertEqual(
            {warning["code"] for warning in result["warnings"]},
            {"large-bpm-jump", "weak-key-transition", "vocal-collision"},
        )

    def test_rejects_invented_duplicate_excluded_unavailable_and_incomplete_plans(self) -> None:
        unavailable = {**self.candidates[0], "available": False, "eligibleSectionIds": ["section-2"]}
        result = SetPlanValidator().validate(
            [
                {"trackId": "downloaded:1", "sectionId": "section-1"},
                {"trackId": "downloaded:1", "sectionId": "unknown", "evidence": "made-up"},
                {"trackId": "invented:9", "sectionId": "section-2"},
            ],
            [unavailable, self.candidates[1]],
            self.journey,
            required_ids={"downloaded:2"},
            excluded_ids={"downloaded:1"},
            target_duration_minutes=60,
            target_track_count=4,
        )
        codes = {error["code"] for error in result["errors"]}
        self.assertFalse(result["valid"])
        self.assertTrue(
            {
                "unknown-track",
                "duplicate-track",
                "excluded-track",
                "unavailable-file",
                "unknown-section",
                "missing-required-track",
                "empty-journey-section",
                "track-count-mismatch",
                "duration-outside-tolerance",
                "candidate-section-mismatch",
                "invalid-evidence-label",
            }.issubset(codes)
        )

    def test_rechecks_a_candidate_file_at_validation_time(self) -> None:
        candidate = {
            "id": "downloaded:1",
            "available": True,
            "path": "/missing/disconnected.wav",
            "durationSeconds": 240,
            "eligibleSectionIds": ["section-1"],
        }
        result = SetPlanValidator(duration_tolerance=1).validate(
            [{"trackId": "downloaded:1", "sectionId": "section-1"}],
            [candidate],
            journey("Reggaeton"),
            target_track_count=1,
            target_duration_minutes=4,
        )
        self.assertIn("unavailable-file", {error["code"] for error in result["errors"]})


class SetCandidatePlanningRouteTests(unittest.TestCase):
    def test_candidate_and_validation_routes_use_bounded_server_catalog(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "track.wav"
            audio.touch()
            cache = root / "catalog.json"
            cache.write_text(json.dumps({"version": 5, "tracks": [catalog_track(1, audio)]}), encoding="utf-8")
            app = FastAPI()
            app.include_router(
                create_set_planning_router(
                    SetPlanningRouteDependencies(
                        catalog_cache_path=cache,
                        ensure_catalog_current=lambda: None,
                        write_catalog_cache=lambda: None,
                        candidate_retriever=SetCandidateRetriever(),
                        plan_validator=SetPlanValidator(duration_tolerance=0.5),
                        track_planner=AITrackPlanner(Mock(), SetPlanValidator()),
                    )
                )
            )
            client = TestClient(app)
            pool_response = client.post(
                "/api/set-builder/candidate-pool",
                json={
                    "journey": journey("Reggaeton"),
                    "per_section_limit": 1,
                    "total_limit": 1,
                },
            )
            self.assertEqual(pool_response.status_code, 200)
            candidate = pool_response.json()["sections"][0]["candidates"][0]
            validation_response = client.post(
                "/api/set-builder/validate-plan",
                json={
                    "journey": journey("Reggaeton"),
                    "candidate_pool": [candidate],
                    "selections": [{"trackId": "downloaded:1", "sectionId": "section-1"}],
                    "target_duration_minutes": 4,
                    "target_track_count": 1,
                },
            )
        self.assertEqual(validation_response.status_code, 200)
        self.assertTrue(validation_response.json()["valid"])

    def test_route_rejects_candidate_pool_larger_than_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            app = FastAPI()
            app.include_router(
                create_set_planning_router(
                    SetPlanningRouteDependencies(
                        catalog_cache_path=Path(temporary) / "catalog.json",
                        ensure_catalog_current=lambda: None,
                        write_catalog_cache=lambda: None,
                        candidate_retriever=SetCandidateRetriever(),
                        plan_validator=SetPlanValidator(),
                        track_planner=AITrackPlanner(Mock(), SetPlanValidator()),
                    )
                )
            )
            response = TestClient(app).post(
                "/api/set-builder/validate-plan",
                json={
                    "journey": journey("Reggaeton"),
                    "candidate_pool": [{"id": str(index)} for index in range(101)],
                    "selections": [],
                },
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
