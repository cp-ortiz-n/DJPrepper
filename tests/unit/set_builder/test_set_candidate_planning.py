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
    playlist_identity: list[dict] | None = None,
    title: str | None = None,
    recording_code: str = "",
    version_code: str = "ORG",
    external_rating: int | None = None,
) -> dict:
    return {
        "downloaded_id": track_id,
        "genre": genre,
        "detailed_genre": detail,
        "descriptors": descriptors or [],
        "playlist_identity": playlist_identity or [],
        "recording_code": recording_code,
        "version_code": version_code,
        "external_rating": {"source": "rekordbox", "rating": external_rating} if external_rating else None,
        "analysis": {
            "source_name": f"Track {track_id}.wav",
            "title": title or f"Track {track_id}",
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

    def test_recording_family_prefers_higher_rated_version_without_emitting_duplicates(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.wav"
            remix = root / "remix.wav"
            original.touch()
            remix.touch()
            tracks = [
                catalog_track(
                    1,
                    original,
                    title="Same Song",
                    recording_code="HOU-000001",
                    version_code="ORG",
                    external_rating=2,
                ),
                catalog_track(
                    2,
                    remix,
                    title="Same Song (Remix)",
                    recording_code="HOU-000001",
                    version_code="RMX01",
                    external_rating=5,
                ),
            ]
            result = SetCandidateRetriever().retrieve(tracks, journey("Reggaeton"))
        candidates = result["sections"][0]["candidates"]
        self.assertEqual([item["id"] for item in candidates], ["downloaded:2"])
        self.assertEqual(result["collapsedTrackIds"], ["downloaded:1"])

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

    def test_strict_journey_excludes_unrequested_bridge_and_fallback_candidates(self) -> None:
        tracks = [
            catalog_track(1, Path("/missing/direct.wav"), genre="Electronic / Techno", detail="Latin Techno"),
            catalog_track(2, Path("/missing/bridge.wav"), genre="Latin / House", detail="Latin House"),
        ]
        strict_journey = journey("Latin Techno")
        strict_journey["genrePolicy"] = {"mode": "strict", "coreGenres": ["latin techno"]}
        result = SetCandidateRetriever().retrieve(tracks, strict_journey, section_limit=4)
        self.assertEqual([candidate["id"] for candidate in result["sections"][0]["candidates"]], ["downloaded:1"])
        self.assertEqual(result["genrePolicy"], "strict")

    def test_strict_journey_accepts_any_playlist_supported_identity_without_retagging_track(self) -> None:
        for target, source in [
            ("Afro House", "Cape Town Afro House Crate"),
            ("Salsa Dura", "Classic Salsa Dura Playlist"),
            ("Drum & Bass", "Drum and Bass Favorites"),
        ]:
            with self.subTest(target=target):
                playlist_track = catalog_track(
                    1,
                    Path("/missing/playlist-track.wav"),
                    genre="Electronic / Breaks",
                    detail="Breaks",
                    playlist_identity=[
                        {
                            "value": target.casefold(),
                            "source": source,
                            "provenance": "playlist",
                            "confidence": 0.78,
                        }
                    ],
                )
                unrelated = catalog_track(
                    2,
                    Path("/missing/unrelated.wav"),
                    genre="Electronic / Breaks",
                    detail="Breaks",
                    descriptors=[{"category": "sound", "value": "melodic", "confidence": 0.9}],
                )
                strict_journey = journey(target)
                strict_journey["genrePolicy"] = {"mode": "strict", "coreGenres": [target.casefold()]}

                result = SetCandidateRetriever().retrieve([playlist_track, unrelated], strict_journey, section_limit=4)

                candidates = result["sections"][0]["candidates"]
                self.assertEqual([candidate["id"] for candidate in candidates], ["downloaded:1"])
                self.assertEqual(candidates[0]["genre"], "Electronic / Breaks")
                self.assertEqual(candidates[0]["matchTier"], "identity")
                self.assertTrue(any(source in reason["text"] for reason in candidates[0]["reasons"]))

    def test_cultural_identity_matches_strict_sections_and_normalized_exclusions(self) -> None:
        indian = catalog_track(
            1,
            Path("/missing/indian.wav"),
            genre="International / Bollywood",
            descriptors=[{"category": "cultural", "value": "Indian / South Asian", "confidence": 0.9}],
        )
        rap = catalog_track(2, Path("/missing/rap.wav"), genre="Hip-Hop & Rap", detail="Rap")
        strict_journey = journey("Indian South Asian")
        strict_journey["genrePolicy"] = {"mode": "strict"}

        result = SetCandidateRetriever().retrieve(
            [indian, rap],
            strict_journey,
            constraints={"excludedGenres": ["hip hop & rap"]},
        )

        candidates = result["sections"][0]["candidates"]
        self.assertEqual([candidate["id"] for candidate in candidates], ["downloaded:1"])
        self.assertEqual(candidates[0]["matchTier"], "identity")
        self.assertEqual(result["sections"][0]["scarcity"]["identity"], 1)

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

    def test_locked_track_is_only_emitted_for_its_preserved_journey_section(self) -> None:
        result = SetCandidateRetriever().retrieve(
            [catalog_track(1, Path("/missing/one.wav")), catalog_track(2, Path("/missing/two.wav"))],
            journey("Reggaeton", "Salsa"),
            locked_ids={"downloaded:1"},
            locked_sections={"downloaded:1": "section-2"},
            section_limit=2,
        )
        sections = {
            section["sectionId"]: {candidate["id"] for candidate in section["candidates"]}
            for section in result["sections"]
        }
        self.assertNotIn("downloaded:1", sections["section-1"])
        self.assertIn("downloaded:1", sections["section-2"])

    def test_collapses_persisted_recording_family_to_one_candidate(self) -> None:
        tracks = [
            catalog_track(1, Path("/missing/original.wav"), recording_code="DSC-000001", version_code="ORG"),
            catalog_track(2, Path("/missing/remix.wav"), recording_code="DSC-000001", version_code="RMX01"),
        ]
        result = SetCandidateRetriever().retrieve(tracks, journey("Reggaeton"), section_limit=4)
        candidates = result["sections"][0]["candidates"]
        self.assertEqual([candidate["id"] for candidate in candidates], ["downloaded:1"])
        self.assertEqual(candidates[0]["recordingKey"], "recording:DSC-000001")
        self.assertEqual(result["duplicateRecordingsCollapsed"], 1)
        self.assertEqual(result["collapsedTrackIds"], ["downloaded:2"])

    def test_reports_a_conflict_when_multiple_protected_tracks_share_one_recording(self) -> None:
        tracks = [
            catalog_track(1, Path("/missing/original.wav"), recording_code="DSC-000001", version_code="ORG"),
            catalog_track(2, Path("/missing/remix.wav"), recording_code="DSC-000001", version_code="RMX01"),
        ]

        result = SetCandidateRetriever().retrieve(
            tracks,
            journey("Reggaeton"),
            locked_ids={"downloaded:1", "downloaded:2"},
        )

        self.assertEqual(len(result["duplicateProtectedIds"]), 1)
        self.assertTrue(set(result["duplicateProtectedIds"]).issubset({"downloaded:1", "downloaded:2"}))

    def test_collapses_safe_metadata_variants_without_persisted_family(self) -> None:
        tracks = [
            catalog_track(1, Path("/missing/one.wav"), artist="Lipps Inc", title="Funkytown"),
            catalog_track(2, Path("/missing/two.wav"), artist="Lipps Inc", title="Funky Town"),
            catalog_track(3, Path("/missing/three.wav"), artist="Majestic", title="Rasputin"),
            catalog_track(4, Path("/missing/four.wav"), artist="Majestic", title="Rasputin - Majestic Club"),
        ]
        result = SetCandidateRetriever().retrieve(tracks, journey("Reggaeton"), section_limit=10)
        ids = {candidate["id"] for candidate in result["sections"][0]["candidates"]}
        self.assertEqual(ids, {"downloaded:1", "downloaded:3"})
        self.assertEqual(result["duplicateRecordingsCollapsed"], 2)

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

    def test_rejects_two_catalog_entries_from_the_same_recording_family(self) -> None:
        candidates = [
            {"id": "downloaded:1", "recordingKey": "recording:DSC-1", "available": True},
            {"id": "downloaded:2", "recordingKey": "recording:DSC-1", "available": True},
        ]
        result = SetPlanValidator(duration_tolerance=1).validate(
            [
                {"trackId": "downloaded:1", "sectionId": "section-1"},
                {"trackId": "downloaded:2", "sectionId": "section-1"},
            ],
            candidates,
            journey("Reggaeton"),
            target_track_count=2,
        )
        duplicate = next(error for error in result["errors"] if error["code"] == "duplicate-recording")
        self.assertEqual(duplicate["firstTrackId"], "downloaded:1")

    def test_rejects_a_locked_track_moved_to_another_journey_section(self) -> None:
        result = SetPlanValidator(duration_tolerance=1).validate(
            [{"trackId": "downloaded:1", "sectionId": "section-2"}],
            [self.candidates[0]],
            self.journey,
            locked_ids={"downloaded:1"},
            locked_sections={"downloaded:1": "section-1"},
            target_track_count=1,
        )
        mismatch = next(error for error in result["errors"] if error["code"] == "locked-section-mismatch")
        self.assertEqual(mismatch["expectedSectionId"], "section-1")
        self.assertEqual(mismatch["actualSectionId"], "section-2")


class SetCandidatePlanningRouteTests(unittest.TestCase):
    def test_candidate_and_validation_routes_use_bounded_server_catalog(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "track.wav"
            audio.touch()
            cache = root / "catalog.json"
            cache.write_text(json.dumps({"version": 6, "tracks": [catalog_track(1, audio)]}), encoding="utf-8")
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
