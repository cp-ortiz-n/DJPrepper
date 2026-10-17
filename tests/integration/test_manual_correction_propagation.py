from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from audioextender.library.catalog_projection import CatalogProjectionPublisher
from audioextender.repositories.facade import JobRepository
from audioextender.web import application
from tests.support.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT
MATRIX_PATH = ROOT / "docs" / "manual-correction-propagation.json"


class ManualCorrectionPropagationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "catalog.sqlite3"
        self.repository = JobRepository(self.database)
        self.audio = self.root / "Electronic" / "Track.wav"
        self.audio.parent.mkdir(parents=True)
        self.audio.touch()
        self.track_id = self.repository.upsert_downloaded_track(
            title="Track",
            artist="Artist",
            file_path=self.audio,
            genre="deep house",
            genre_category="Electronic / House / Deep House",
        )
        self.job_id = self.repository.create(self.audio.name, self.audio, "auto", 0, 0, False)
        self.repository.update(self.job_id, status="complete", bpm=124.0, wav_path=str(self.audio))
        self.report = {
            "songs": {
                "track": {
                    "source_name": self.audio.name,
                    "bpm": 124.0,
                    "key": "C major",
                    "key_confidence": 0.8,
                    "beat_grid_confidence": 0.9,
                    "duration_seconds": 180.0,
                    "detected_style": "melodic",
                    "timing": "steady",
                    "intro": {"instrumentalness": 0.8},
                    "outro": {"instrumentalness": 0.7},
                }
            }
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def rebuild_projections(self) -> dict:
        cache = self.root / "set_builder_catalog.json"
        with (
            patch.object(application, "repository", self.repository, create=True),
            patch.object(application, "_load_processing_report", return_value=self.report),
            patch.object(application, "SET_BUILDER_CATALOG_CACHE", cache),
        ):
            application._refresh_library_search_index()
        return json.loads(cache.read_text(encoding="utf-8"))

    def test_contract_covers_every_manual_correction_consumer(self) -> None:
        contract = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        rows = {row["field"]: row for row in contract["corrections"]}
        self.assertEqual(set(rows), {"bpm", "key", "genre", "identity"})
        required = {
            "authoritative_write",
            "catalog",
            "search_index",
            "dj_library",
            "set_builder",
            "refresh",
            "restart",
            "status",
            "follow_up",
        }
        for field, row in rows.items():
            with self.subTest(field=field):
                self.assertTrue(required <= row.keys())
                if row["status"] == "confirmed-gap":
                    self.assertRegex(row["follow_up"], r"^ARCH-014[A-Z]$")

    def test_verified_key_reaches_library_set_builder_and_restart(self) -> None:
        self.repository.set_key_verification(self.audio.name, "G minor", "C major", [], "Checked by ear")
        payload = self.rebuild_projections()
        rows, total = self.repository.page_library_tracks(page=1, page_size=10, musical_key="G minor")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["musical_key"], "G minor")
        self.assertEqual(payload["tracks"][0]["analysis"]["key"], "G minor")
        restarted = JobRepository(self.database)
        verification = restarted.key_verification(self.audio.name)
        self.assertIsNotNone(verification)
        assert verification is not None
        self.assertEqual(verification["verified_key"], "G minor")

    def test_verified_bpm_reaches_library_set_builder_and_survives_reanalysis(self) -> None:
        self.repository.set_bpm_verification(self.audio.name, 126.25, 124.0, "Checked against the grid")
        payload = self.rebuild_projections()
        rows, total = self.repository.page_library_tracks(page=1, page_size=10, bpm_min=126, bpm_max=126.5)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["library_bpm"], 126.25)
        self.assertEqual(payload["tracks"][0]["analysis"]["bpm"], 126.25)
        self.assertEqual(payload["tracks"][0]["analysis"]["detected_bpm"], 124.0)
        self.repository.update(self.job_id, bpm=132.0)
        self.report["songs"]["track"]["bpm"] = 132.0
        refreshed = self.rebuild_projections()
        self.assertEqual(refreshed["tracks"][0]["analysis"]["bpm"], 126.25)
        self.assertEqual(refreshed["tracks"][0]["analysis"]["detected_bpm"], 132.0)
        restarted = JobRepository(self.database)
        verification = restarted.bpm_verification(self.audio.name)
        self.assertIsNotNone(verification)
        assert verification is not None
        self.assertEqual(verification["verified_bpm"], 126.25)

    def test_identity_is_live_in_search_and_durable_for_set_builder(self) -> None:
        self.rebuild_projections()
        self.repository.update_track_descriptors(
            [self.track_id],
            [{"category": "context", "value": "ecuadorian party", "provenance": "manual"}],
            mode="replace",
        )
        downloaded, downloaded_total = self.repository.page_downloaded_tracks(page=1, page_size=10, search="ecuadorian")
        library, library_total = self.repository.page_library_tracks(page=1, page_size=10, search="ecuadorian")
        payload = self.rebuild_projections()
        self.assertEqual(downloaded_total, 1)
        self.assertEqual(library_total, 1)
        self.assertIn("ecuadorian party", downloaded[0]["descriptors_json"])
        self.assertIn("ecuadorian party", library[0]["descriptors_json"])
        self.assertEqual(payload["tracks"][0]["descriptors"][0]["value"], "ecuadorian party")
        restarted = JobRepository(self.database)
        self.assertEqual(restarted.track_descriptors(self.track_id)[0]["value"], "ecuadorian party")

    def test_genre_publication_updates_library_and_set_builder_before_return(self) -> None:
        self.rebuild_projections()
        destination = self.root / "Latin" / self.audio.name
        destination.parent.mkdir(parents=True)
        destination.touch()
        self.repository.update_downloaded_track_metadata(
            track_id=self.track_id,
            old_path=self.audio,
            new_path=destination,
            title="Track",
            artist="Artist",
            genre="latin house",
            genre_category="Latin / Latin House",
            playlist_name="Party",
        )
        cache = self.root / "set_builder_catalog.json"

        def rebuild() -> None:
            self.rebuild_projections()

        publisher = CatalogProjectionPublisher(
            repository=lambda: self.repository,
            rebuild=rebuild,
            report_path=lambda: self.root / "processing_report.json",
            catalog_path=lambda: cache,
            memory_cache={"facets": {"genres": {"Electronic / House / Deep House": 1}}},
            memory_cache_lock=threading.Lock(),
        )
        publisher.publish()
        payload = json.loads(cache.read_text(encoding="utf-8"))
        refreshed, refreshed_total = self.repository.page_library_tracks(
            page=1, page_size=10, category="Latin / Latin House"
        )
        self.assertEqual(refreshed_total, 1)
        self.assertEqual(refreshed[0]["library_category"], "Latin / Latin House")
        self.assertEqual(payload["tracks"][0]["genre"], "Latin / Latin House")
        restarted = JobRepository(self.database)
        durable = restarted.get_downloaded_track(self.track_id)
        self.assertIsNotNone(durable)
        assert durable is not None
        self.assertEqual(durable["genre_category"], "Latin / Latin House")


if __name__ == "__main__":
    unittest.main()
