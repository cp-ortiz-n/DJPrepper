from __future__ import annotations

import json
import io
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from helpers.config import EditConfig
from helpers.exceptions import ConfigurationError
from helpers.web_database import JobRepository
from helpers.web_jobs import DatabaseProgress, WebJobService
import web_app as web_module
from web_app import (
    AuthorizedImportRequest,
    BatchDownloadRequest,
    _best_youtube_match,
    _catalog_genre_category,
    _generalized_genre,
    _genre_path_parts,
    _playlist_csv_tracks,
    app,
)


class JobRepositoryTests(unittest.TestCase):
    def test_report_audio_jobs_include_old_completed_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            old_id = repository.create("Old.wav", Path(temporary) / "Old.wav", "auto", 8, 8, False)
            repository.update(old_id, status="complete", wav_path=str(Path(temporary) / "Old.wav"))
            for index in range(110):
                job_id = repository.create(
                    f"New {index}.wav", Path(temporary) / f"New {index}.wav", "auto", 8, 8, False
                )
                repository.update(job_id, status="complete")

            rows = repository.list_report_audio_jobs()
            self.assertEqual(len(rows), 111)
            self.assertTrue(any(row["source_name"] == "Old.wav" for row in rows))

    def test_key_verification_persists_updates_and_removes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            saved = repository.set_key_verification(
                "Song.wav", "G major", "B minor",
                [{"key": "G major", "detectors": "harmonic, CQT"}], "checked",
            )
            self.assertEqual(saved["verified_key"], "G major")
            self.assertEqual(saved["candidates"][0]["key"], "G major")

            repository.set_key_verification("Song.wav", "A minor", "B minor", [], "")
            self.assertEqual(repository.key_verification("song.wav")["verified_key"], "A minor")
            self.assertTrue(repository.delete_key_verification("SONG.WAV"))
            self.assertIsNone(repository.key_verification("Song.wav"))

    def test_import_failures_persist_retries_and_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            values = {
                "playlist_name": "Party List", "title": "Missing Song",
                "artist": "Artist", "spotify_uri": "spotify:track:123",
                "youtube_url": "https://youtube.com/watch?v=abc",
            }
            repository.record_import_failure(**values, error="network error")
            repository.record_import_failure(**values, error="video unavailable")

            failures = repository.list_import_failures()
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["attempts"], 2)
            self.assertEqual(failures[0]["error"], "video unavailable")

            repository.resolve_import_failure(
                playlist_name="Party List", title="Missing Song", artist="Artist"
            )
            self.assertEqual(repository.list_import_failures(), [])

    def test_library_search_index_filters_sorts_and_pages_in_sql(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = JobRepository(Path(temporary) / "jobs.sqlite3")
            entries = []
            for index, (title, category, bpm, role) in enumerate((
                ("Opening Track", "Electronic / House / Deep House", 112.0, "warm-up"),
                ("Peak Track", "Electronic / Techno / Hard Techno", 145.0, "peak-time"),
                ("Closing Track", "Latin / Salsa", 124.0, "closing"),
            ), start=1):
                source = Path(temporary) / f"{title}.wav"
                job_id = catalog.create(source.name, source, "auto", 8, 8, False)
                catalog.update(job_id, status="complete", bpm=bpm)
                entries.append({
                    "job_id": job_id, "source_name": source.name, "title": title,
                    "artist": "Test Artist", "downloaded_id": None, "category": category,
                    "detail_genre": category.split(" / ")[-1].casefold(),
                    "roles": f"|{role}|", "preset": "default", "requested_preset": "auto",
                    "result": "preserved", "bpm": bpm, "musical_key": "A minor",
                    "camelot": "8A", "energy": .8 if role == "peak-time" else .4,
                    "energy_band": "high" if role == "peak-time" else "medium",
                    "vocals": "mixed", "timing": "steady", "updated_at": f"2026-01-0{index}T00:00:00+00:00",
                    "analysis_json": json.dumps({"source_name": source.name, "bpm": bpm}),
                })
            organized_path = Path(temporary) / "Library" / "Opening Track.wav"
            organized_path.parent.mkdir()
            organized_path.touch()
            entries[0]["downloaded_id"] = catalog.upsert_downloaded_track(
                title="Opening Track", artist="Test Artist", file_path=organized_path,
            )
            catalog.replace_library_search_index(entries)
            tracks, total = catalog.page_library_tracks(
                page=1, page_size=10, category="electronic", role="peak-time",
            )
            self.assertEqual(total, 1)
            self.assertEqual(tracks[0]["library_title"], "Peak Track")
            tracks, total = catalog.page_library_tracks(
                page=1, page_size=10, category="electronic / house",
                detail_genre="deep house",
            )
            self.assertEqual(total, 1)
            self.assertEqual(tracks[0]["library_title"], "Opening Track")
            tracks, total = catalog.page_library_tracks(
                page=1, page_size=2, sort="bpm-down",
            )
            self.assertEqual(total, 3)
            self.assertEqual([track["library_title"] for track in tracks], ["Peak Track", "Closing Track"])
            facets = catalog.library_search_facets()
            self.assertEqual(facets["total"], 3)
            self.assertEqual(facets["roles"]["warm-up"], 1)
            self.assertEqual(facets["detailed_genres"]["deep house"], 1)
            self.assertEqual(
                facets["detailed_genres_by_category"]["Electronic / House / Deep House"]["deep house"],
                1,
            )
            set_tracks = catalog.list_set_builder_tracks()
            self.assertEqual(len(set_tracks), 3)
            opening = next(track for track in set_tracks if track["source_name"] == "Opening Track.wav")
            self.assertEqual(opening["library_path"], str(organized_path.resolve()))
            self.assertEqual(
                {track["category"] for track in set_tracks},
                {
                    "Electronic / House / Deep House",
                    "Electronic / Techno / Hard Techno",
                    "Latin / Salsa",
                },
            )

    def test_internal_state_and_source_signatures_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = JobRepository(Path(temporary) / "jobs.sqlite3")
            catalog.set_system_state("migration", "3")
            catalog.upsert_catalog_source_signatures([
                ("/music/one.json", 123, 456),
                ("/music/two.json", 789, 12),
            ])
            reopened = JobRepository(Path(temporary) / "jobs.sqlite3")
            self.assertEqual(reopened.get_system_state("migration"), "3")
            self.assertEqual(reopened.catalog_source_signatures(), {
                "/music/one.json": (123, 456),
                "/music/two.json": (789, 12),
            })

    def test_catalog_migration_checkpoint_skips_restart_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = JobRepository(Path(temporary) / "jobs.sqlite3")
            original = web_module.downloaded_catalog_migrated
            try:
                web_module.downloaded_catalog_migrated = False
                with patch.object(web_module, "repository", catalog), patch.object(
                    web_module, "_migrate_downloaded_catalog", return_value={}
                ) as migrate:
                    web_module._ensure_downloaded_catalog_migrated()
                    migrate.assert_called_once_with()
                    self.assertEqual(
                        catalog.get_system_state("downloaded_catalog_migration"),
                        web_module.DOWNLOADED_CATALOG_MIGRATION_VERSION,
                    )
                    web_module.downloaded_catalog_migrated = False
                    web_module._ensure_downloaded_catalog_migrated()
                    migrate.assert_called_once_with()
            finally:
                web_module.downloaded_catalog_migrated = original

    def test_integrity_scan_reports_without_changing_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = JobRepository(root / "jobs.sqlite3")
            tracked = root / "Other" / "Tracked.wav"
            extra = root / "Other" / "Extra.wav"
            tracked.parent.mkdir(parents=True)
            tracked.touch(); extra.touch()
            track_id = catalog.upsert_downloaded_track(
                title="Tracked", artist="Artist", file_path=tracked,
                genre_category="Other", playlist_name="Inbox",
            )
            batch_id = "integrity-test"
            web_module.integrity_scan_batches[batch_id] = {
                "status":"processing", "processed":0, "total":1,
            }
            with patch.object(web_module, "repository", catalog), patch.object(
                web_module, "_music_library_root", return_value=root
            ), patch.object(web_module, "read_wav_metadata", return_value={
                "title":"Tracked", "artist":"Artist", "genre":"Other", "album":"Inbox",
            }):
                web_module._run_integrity_scan(batch_id)
            batch = web_module.integrity_scan_batches.pop(batch_id)
            self.assertEqual(batch["status"], "complete")
            self.assertEqual(batch["counts"]["uncataloged_files"], 1)
            self.assertEqual(batch["counts"]["tag_mismatches"], 0)
            self.assertEqual(catalog.get_downloaded_track(track_id)["title"], "Tracked")

    def test_downloaded_tracks_are_cataloged_separately_with_playlist_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = JobRepository(root / "jobs.sqlite3")
            wav = root / "Artist - Song.wav"
            wav.touch()
            first = catalog.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=wav,
                genre="hard techno", genre_category="Techno",
                playlist_name="Warehouse Set",
            )
            second = catalog.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=wav,
                genre="hard techno", genre_category="Techno",
                playlist_name="Peak Time",
            )
            self.assertEqual(first, second)
            tracks = catalog.list_downloaded_tracks()
            self.assertEqual(len(tracks), 1)
            self.assertEqual(set(tracks[0]["playlists"]), {"Warehouse Set", "Peak Time"})
            self.assertEqual(catalog.list_jobs(), [])
            self.assertTrue(catalog.delete_downloaded_track(first))
            self.assertTrue(catalog.downloaded_track_is_excluded(wav))
            self.assertEqual(catalog.list_downloaded_tracks(), [])
            catalog.replace_settings({"preset": "club"})
            catalog.create("Edit.mp3", root / "Edit.mp3", "auto", 8, 8, False)
            catalog.reset_track_data()
            self.assertEqual(catalog.list_jobs(), [])
            self.assertEqual(catalog.get_settings(), {"preset": "club"})
            self.assertFalse(catalog.downloaded_track_is_excluded(wav))

    def test_catalog_upsert_does_not_erase_existing_artwork(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = JobRepository(root / "jobs.sqlite3")
            wav = root / "Electronic" / "House" / "Song.wav"
            wav.parent.mkdir(parents=True)
            wav.touch()
            catalog.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=wav,
                artwork_url="https://i.scdn.co/image/cover",
                artwork_path=str(root / "cover.jpg"),
            )
            catalog.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=wav,
                genre_category="Electronic / House / House",
            )
            track = catalog.list_downloaded_tracks()[0]
            self.assertEqual(track["artwork_url"], "https://i.scdn.co/image/cover")
            self.assertEqual(track["artwork_path"], str((root / "cover.jpg").resolve()))

    def test_job_lifecycle_is_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3", Path(temporary) / "Song.mp3", "auto", 8, 4, False
            )
            repository.update(job_id, status="processing", progress=42, stage="Analysis")
            job = repository.get(job_id)
            assert job is not None
            self.assertEqual(job["status"], "processing")
            self.assertEqual(job["progress"], 42)
            self.assertEqual(repository.list_jobs()[0]["source_name"], "Song.mp3")

    def test_job_pages_and_lazy_library_versions_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            first_source = root / "First.wav"
            second_source = root / "Second.wav"
            first = repository.create("First.wav", first_source, "auto", 0, 0, False)
            repository.update(first, status="complete")
            newest = repository.create("First.wav", first_source, "auto", 0, 0, False)
            repository.update(newest, status="complete")
            queued = repository.create("Second.wav", second_source, "auto", 0, 0, False)

            rows, total = repository.list_jobs_page(
                page=1, page_size=1, statuses=("complete",)
            )
            self.assertEqual(total, 2)
            self.assertEqual([row["id"] for row in rows], [newest])
            latest = repository.list_latest_completed_jobs()
            self.assertEqual(len(latest), 1)
            self.assertEqual(latest[0]["id"], newest)
            self.assertEqual(latest[0]["generation_count"], 2)
            self.assertEqual(
                [row["id"] for row in repository.list_completed_versions(str(first_source.resolve()))],
                [newest, first],
            )
            self.assertEqual(repository.get(queued)["status"], "queued")

    def test_downloaded_genre_relocation_updates_catalog_and_job_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            old_path = root / "Other" / "Song.wav"
            new_path = root / "House" / "Song.wav"
            old_path.parent.mkdir()
            old_path.touch()
            track_id = repository.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=old_path,
                genre_category="Other",
            )
            job_id = repository.create("Song.wav", old_path, "auto", 0, 0, False)
            repository.update(job_id, wav_path=str(old_path), status="complete")
            repository.relocate_downloaded_tracks(
                [(track_id, old_path, new_path, "House")]
            )
            track = repository.get_downloaded_track(track_id)
            job = repository.get(job_id)
            assert track is not None and job is not None
            self.assertEqual(track["genre_category"], "House")

    def test_downloaded_metadata_update_synchronizes_catalog_playlist_and_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            old_path = root / "Other" / "Unknown.wav"
            new_path = root / "Latin" / "Salsa" / "Artist - Song.wav"
            old_path.parent.mkdir(parents=True)
            old_path.touch()
            track_id = repository.upsert_downloaded_track(
                title="Unknown", artist="", file_path=old_path,
                genre="", genre_category="Other", playlist_name="Inbox",
            )
            job_id = repository.create("Unknown.wav", old_path, "auto", 0, 0, False)
            repository.update(job_id, wav_path=str(old_path), status="complete")
            repository.update_downloaded_track_metadata(
                track_id=track_id, old_path=old_path, new_path=new_path,
                title="Song", artist="Artist", genre="salsa, timba",
                genre_category="Latin / Salsa", playlist_name="Latin Set",
            )
            track = repository.get_downloaded_track(track_id)
            job = repository.get(job_id)
            assert track is not None and job is not None
            self.assertEqual(track["title"], "Song")
            self.assertEqual(track["artist"], "Artist")
            self.assertEqual(track["genre"], "salsa, timba")
            self.assertEqual(track["genre_category"], "Latin / Salsa")
            self.assertEqual(track["playlists"], ["Latin Set"])
            self.assertEqual(job["source_name"], new_path.name)
            self.assertEqual(job["source_path"], str(new_path.resolve()))
            self.assertEqual(track["file_path"], str(new_path.resolve()))
            self.assertEqual(job["source_path"], str(new_path.resolve()))
            self.assertEqual(job["wav_path"], str(new_path.resolve()))

    def test_downloaded_catalog_joins_latest_and_completed_analysis_in_sql(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            wav = root / "Artist - Song.wav"
            wav.touch()
            repository.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=wav,
                genre_category="House", playlist_name="Night Set",
            )
            completed_id = repository.create("Song.wav", wav, "auto", 0, 0, False)
            repository.update(completed_id, status="complete")
            latest_id = repository.create("Song.wav", wav, "auto", 0, 0, False)
            repository.update(latest_id, status="failed")

            track = repository.list_downloaded_tracks_with_jobs()[0]
            self.assertEqual(track["analysis_status"], "failed")
            self.assertEqual(track["library_job_id"], latest_id)
            self.assertEqual(track["completed_library_job_id"], completed_id)
            self.assertEqual(track["playlists"], ["Night Set"])

    def test_downloaded_catalog_pages_filter_and_sort_in_sql(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            for title, artist, genre, playlist in (
                ("Zulu", "Beta", "Techno", "Peak"),
                ("Alpha", "Gamma", "House", "Warmup"),
                ("Middle", "Alpha", "House", "Peak"),
            ):
                path = root / f"{artist} - {title}.wav"
                path.touch()
                repository.upsert_downloaded_track(
                    title=title, artist=artist, file_path=path,
                    genre_category=genre, playlist_name=playlist,
                )
            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=1, genre="House", sort="title",
            )
            self.assertEqual(total, 2)
            self.assertEqual([track["title"] for track in tracks], ["Alpha"])
            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, search="alpha", playlist="Peak",
            )
            self.assertEqual(total, 1)
            self.assertEqual(tracks[0]["title"], "Middle")
            facets = repository.downloaded_catalog_facets()
            self.assertEqual(facets["total"], 3)
            self.assertEqual(facets["genres"]["House"], 2)
            self.assertEqual(facets["playlists"]["Peak"], 2)

            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, genre="House",
            )
            self.assertEqual(total, 2)

    def test_downloaded_catalog_filters_saved_audio_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            for title, score, label in (
                ("Excellent", 94, "excellent"),
                ("Good", 81, "good"),
                ("Review", 63, "review"),
                ("Poor", 42, "poor"),
            ):
                path = root / f"{title}.wav"
                path.touch()
                track_id = repository.upsert_downloaded_track(
                    title=title, artist="Artist", file_path=path,
                    genre_category="House",
                )
                repository.update_audio_quality(track_id, {"score": score, "label": label})

            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, quality="good",
            )
            self.assertEqual(total, 1)
            self.assertEqual(tracks[0]["title"], "Good")
            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, quality="below-target",
            )
            self.assertEqual(total, 2)
            self.assertEqual({track["title"] for track in tracks}, {"Review", "Poor"})

    def test_downloaded_catalog_exposes_and_filters_exact_detailed_genres(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            fixtures = (
                ("Arabic", "arabic hip hop, egyptian hip hop"),
                ("Southern", "southern hip hop, trap"),
                ("House", "deep house, house"),
            )
            for title, detailed_genre in fixtures:
                path = root / f"{title}.wav"
                path.touch()
                repository.upsert_downloaded_track(
                    title=title, artist="Artist", file_path=path,
                    genre=detailed_genre, genre_category="Hip-Hop & Rap",
                )

            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, detailed_genre="hip hop",
            )
            self.assertEqual(total, 0)
            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, detailed_genre="arabic hip hop",
            )
            self.assertEqual(total, 1)
            self.assertEqual(tracks[0]["title"], "Arabic")
            facets = repository.downloaded_catalog_facets()
            self.assertEqual(facets["detailed_genres"]["arabic hip hop"], 1)
            self.assertEqual(facets["detailed_genres"]["house"], 1)
            self.assertEqual(
                facets["detailed_genres_by_category"]["Hip-Hop & Rap"]["arabic hip hop"],
                1,
            )

    def test_downloaded_catalog_filters_tracks_by_artwork_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            for title, artwork_path in (
                ("Needs Cover", ""),
                ("Has Cover", str(root / "cover.jpg")),
            ):
                wav = root / f"{title}.wav"
                wav.touch()
                repository.upsert_downloaded_track(
                    title=title, artist="Artist", file_path=wav,
                    artwork_path=artwork_path,
                )

            missing, missing_total = repository.page_downloaded_tracks(
                page=1, page_size=10, artwork="missing",
            )
            available, available_total = repository.page_downloaded_tracks(
                page=1, page_size=10, artwork="available",
            )

            self.assertEqual(missing_total, 1)
            self.assertEqual(missing[0]["title"], "Needs Cover")
            self.assertEqual(available_total, 1)
            self.assertEqual(available[0]["title"], "Has Cover")

    def test_downloaded_catalog_splits_attention_analysis_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            fixtures = (
                ("Missing", "", "Other"),
                ("Unmapped", "southern gothic", "Other"),
                ("Broad Latin", "latin", "Latin / Other"),
                ("Ready", "deep house", "Electronic / House / Deep House"),
            )
            for title, detailed_genre, category in fixtures:
                path = root / f"{title}.wav"
                path.touch()
                repository.upsert_downloaded_track(
                    title=title,
                    artist="Artist",
                    file_path=path,
                    genre=detailed_genre,
                    genre_category=category,
                )

            expected = {
                "missing_genre": "Missing",
                "unmapped_genre": "Unmapped",
                "broad_genre": "Broad Latin",
            }
            for analysis_filter, title in expected.items():
                tracks, total = repository.page_downloaded_tracks(
                    page=1, page_size=10, analysis=analysis_filter,
                )
                self.assertEqual(total, 1)
                self.assertEqual(tracks[0]["title"], title)

            tracks, total = repository.page_downloaded_tracks(
                page=1, page_size=10, genre="Electronic",
            )
            self.assertEqual(total, 1)
            self.assertEqual(tracks[0]["title"], "Ready")

            facets = repository.downloaded_catalog_facets()
            self.assertEqual(facets["review_states"]["missing_genre"], 1)
            self.assertEqual(facets["review_states"]["unmapped_genre"], 1)
            self.assertEqual(facets["review_states"]["broad_genre"], 1)
            self.assertEqual(facets["review_states"]["needs_attention"], 4)

    def test_recover_interrupted_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3", Path(temporary) / "Song.mp3", "auto", 8, 8, False
            )
            repository.update(job_id, status="processing")
            repository.recover_interrupted()
            job = repository.get(job_id)
            assert job is not None
            self.assertEqual(job["status"], "failed")

    def test_settings_replace_and_reset_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            repository.replace_settings({"preview_seconds": 12.0, "use_stems": True})
            self.assertEqual(
                repository.get_settings(),
                {"preview_seconds": 12.0, "use_stems": True},
            )
            repository.replace_settings({})
            self.assertEqual(repository.get_settings(), {})

    def test_candidate_feedback_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3", Path(temporary) / "Song.mp3", "auto", 8, 8, False
            )
            feedback_id = repository.add_feedback(
                job_id, "intro", 2, False, "buildup,bass reset", "Wrong energy arc"
            )
            self.assertGreater(feedback_id, 0)
            feedback = repository.feedback(job_id)[0]
            self.assertEqual(feedback["candidate_rank"], 2)
            self.assertEqual(feedback["notes"], "Wrong energy arc")

    def test_review_jobs_have_an_explicit_inbox_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            pending_id = repository.create(
                "Song.mp3",
                Path(temporary) / "Song.mp3",
                "auto",
                8,
                8,
                False,
                {"review_candidates": True},
            )
            resolved_id = repository.create(
                "Chosen.mp3",
                Path(temporary) / "Chosen.mp3",
                "auto",
                8,
                8,
                False,
                {"review_candidates": True, "manual_candidate_selection": True},
            )
            pending = repository.get(pending_id)
            resolved = repository.get(resolved_id)
            assert pending is not None and resolved is not None
            self.assertEqual(pending["review_status"], "pending")
            self.assertEqual(resolved["review_status"], "resolved")
            repository.update(pending_id, review_status="rejected")
            dismissed = repository.get(pending_id)
            assert dismissed is not None
            self.assertEqual(dismissed["review_status"], "rejected")

    def test_candidate_feedback_replaces_the_previous_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3", Path(temporary) / "Song.mp3", "auto", 8, 8, False
            )
            repository.add_feedback(job_id, "intro", 1, True, "smooth", "Good")
            repository.add_feedback(job_id, "intro", 1, False, "choppy", "Changed")
            feedback = repository.feedback(job_id)
            self.assertEqual(len(feedback), 1)
            self.assertEqual(feedback[0]["accepted"], 0)
            self.assertEqual(feedback[0]["notes"], "Changed")

    def test_accepting_another_candidate_keeps_one_choice_per_side(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3", Path(temporary) / "Song.mp3", "auto", 8, 8, False
            )
            repository.add_feedback(job_id, "intro", 1, True, "", "First")
            repository.add_feedback(job_id, "intro", 3, True, "", "Third")
            feedback = repository.feedback(job_id)
            self.assertEqual(len(feedback), 1)
            self.assertEqual(feedback[0]["candidate_rank"], 3)

    def test_track_feedback_supports_cli_only_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            feedback_id = repository.add_track_feedback(
                "Song.mp3", "overall", True, "smooth", "Ready for a set"
            )
            self.assertGreater(feedback_id, 0)
            feedback = repository.track_feedback("song.mp3")[0]
            self.assertEqual(feedback["position"], "overall")
            self.assertEqual(feedback["notes"], "Ready for a set")


class WebJobConfigurationTests(unittest.TestCase):
    def test_web_generations_archive_their_extended_audio_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            repository = JobRepository(project / "jobs.sqlite3")
            service = WebJobService(project, repository)
            source = project / "Song.mp3"
            output = project / "output" / "extended" / "Song (Extended Edit).wav"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"generation audio")
            result = type(
                "Result",
                (),
                {
                    "output": output,
                    "intro_preview": None,
                    "outro_preview": None,
                    "cue_sheet": None,
                },
            )()
            try:
                archived = service._archive_artifacts(42, source, result)
                self.assertEqual(archived["extended"].read_bytes(), b"generation audio")
                self.assertIn("versions/Song/job-42", archived["extended"].as_posix())
            finally:
                service.executor.shutdown(wait=True)

    def test_web_auto_bars_unlocks_each_side_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            repository = JobRepository(project / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3",
                project / "Song.mp3",
                "auto",
                8,
                4,
                False,
                {"intro_bars_auto": True, "outro_bars_auto": False},
            )
            service = WebJobService(project, repository)
            try:
                job = repository.get(job_id)
                assert job is not None
                config = service._config(job)
                self.assertFalse(config.intro_bars_locked)
                self.assertTrue(config.outro_bars_locked)
            finally:
                service.executor.shutdown(wait=True)

    def test_candidate_audio_is_only_created_for_explicit_review_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            repository = JobRepository(project / "jobs.sqlite3")
            normal_id = repository.create("Normal.mp3", project / "Normal.mp3", "auto", 8, 8, False)
            review_id = repository.create(
                "Review.mp3",
                project / "Review.mp3",
                "auto",
                8,
                8,
                False,
                {"review_candidates": True},
            )
            service = WebJobService(project, repository)
            try:
                normal = repository.get(normal_id)
                review = repository.get(review_id)
                assert normal is not None and review is not None
                normal_config = service._config(normal)
                review_config = service._config(review)
                self.assertFalse(normal_config.create_previews)
                self.assertFalse(normal_config.create_candidate_auditions)
                self.assertTrue(review_config.create_previews)
                self.assertTrue(review_config.create_candidate_auditions)
            finally:
                service.executor.shutdown(wait=True)

    def test_web_job_honors_transition_and_repetition_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            repository = JobRepository(project / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3",
                project / "Song.mp3",
                "subtle",
                4,
                4,
                False,
                {"maximum_repetitions": 3, "crossfade_ms": 24.0},
            )
            service = WebJobService(project, repository)
            try:
                job = repository.get(job_id)
                assert job is not None
                config = service._config(job)
                self.assertEqual(config.maximum_repetitions, 3)
                self.assertEqual(config.crossfade_ms, 24.0)
            finally:
                service.executor.shutdown(wait=True)

    def test_web_job_uses_the_snapshotted_custom_preset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            repository = JobRepository(project / "jobs.sqlite3")
            definition = {
                "intro_bars": 4,
                "outro_bars": 0,
                "use_stems": True,
                "minimum_loop_quality": 74.0,
                "maximum_repetitions": 2,
            }
            job_id = repository.create(
                "Song.mp3",
                project / "Song.mp3",
                "my-preset",
                4,
                0,
                True,
                {"preset_definition": definition},
            )
            service = WebJobService(project, repository)
            try:
                job = repository.get(job_id)
                assert job is not None
                config = service._config(job)
                self.assertEqual(config.minimum_loop_quality, 74.0)
                self.assertEqual(config.maximum_repetitions, 2)
            finally:
                service.executor.shutdown(wait=True)

    def test_review_flag_is_persisted_in_job_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3",
                Path(temporary) / "Song.mp3",
                "auto",
                8,
                8,
                False,
                {"review_candidates": True},
            )
            job = repository.get(job_id)
            assert job is not None
            self.assertTrue(json.loads(job["config_json"])["review_candidates"])


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_index_is_the_audio_workspace(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DJ Library Studio", response.text)
        self.assertIn("Bring music into your workspace", response.text)
        self.assertIn("Analyze for Library", response.text)
        self.assertIn("Set Builder", response.text)
        self.assertIn("Generate set plan", response.text)

    def test_import_failures_can_be_retried_as_a_background_batch(self) -> None:
        failure = {
            "id": 91, "playlist_name": "House", "title": "Retry Me",
            "artist": "Artist", "spotify_uri": "spotify:track:123",
            "youtube_url": "https://youtube.com/watch?v=old", "error": "403 Forbidden",
        }
        with (
            patch.object(web_module.repository, "list_import_failures", return_value=[failure]),
            patch.object(web_module, "_require_music_library_online"),
            patch.object(web_module.threading, "Thread") as thread,
        ):
            response = self.client.post(
                "/api/imports/failures/retry", json={"failure_ids": [91]}
            )
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["retry_count"], 1)
        self.assertEqual(web_module.creative_commons_batches[payload["batch_id"]]["status"], "processing")
        thread.return_value.start.assert_called_once()
        web_module.creative_commons_batches.pop(payload["batch_id"], None)

    def test_set_export_preflight_reports_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "Ready.wav"
            existing.write_bytes(b"audio")
            missing = Path(temporary) / "Missing.wav"
            response = self.client.post(
                "/api/set-builder/export-preflight",
                json={"paths": [str(existing), str(missing)]},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertFalse(payload["ready"])
            self.assertEqual(payload["valid"], 1)
            self.assertEqual(payload["missing"], 1)

    def test_save_set_playlist_writes_to_library_playlist_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "Electronic" / "Track.wav"
            audio.parent.mkdir()
            audio.write_bytes(b"audio")
            with patch("web_app._music_library_root", return_value=root):
                response = self.client.post(
                    "/api/set-builder/save-playlist",
                    json={"name": "Friday Set", "tracks": [{
                        "path": str(audio), "title": "Artist - Track", "duration_seconds": 180,
                    }]},
                )
            self.assertEqual(response.status_code, 200)
            playlist = root / "_Playlist" / "Friday Set.m3u8"
            self.assertTrue(playlist.is_file())
            self.assertIn(str(audio.resolve()), playlist.read_text(encoding="utf-8"))

    def test_config_exposes_supported_controls(self) -> None:
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("auto", payload["presets"])
        self.assertIn(8, payload["bar_counts"])
        self.assertEqual(payload["preset_details"]["subtle"]["maximum_repetitions"], 1)

    def test_unknown_audio_kind_is_rejected(self) -> None:
        response = self.client.get("/api/jobs/999999/audio/not-a-kind")
        self.assertEqual(response.status_code, 404)

    def test_report_audio_index_distinguishes_available_and_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            available = Path(temporary) / "Available.wav"
            available.write_bytes(b"audio")
            jobs = [
                {"id": 1, "source_name": "Available.wav", "wav_path": str(available), "extended_path": ""},
                {"id": 2, "source_name": "Missing.wav", "wav_path": str(Path(temporary) / "Missing.wav"), "extended_path": ""},
            ]
            with patch.object(web_module.repository, "list_report_audio_jobs", return_value=jobs):
                response = self.client.get("/api/report-audio-index")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload[0]["wav_available"])
        self.assertFalse(payload[1]["wav_available"])
        self.assertNotIn("wav_path", payload[0])

    def test_analyze_download_rejects_unknown_catalog_track(self) -> None:
        response = self.client.post(
            "/api/downloaded-library/analyze", json={"track_ids": [999_999_999]}
        )
        self.assertEqual(response.status_code, 404)

    def test_analyze_all_matching_queues_tracks_beyond_one_page(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = JobRepository(root / "jobs.sqlite3")
            for index in range(3):
                path = root / f"Track {index}.wav"
                path.write_bytes(b"audio")
                catalog.upsert_downloaded_track(
                    title=f"Track {index}", artist="Artist", file_path=path,
                    genre_category="Electronic / House", playlist_name="Bulk Test",
                )
            queue = Mock()
            with patch.object(web_module, "repository", catalog), patch.object(web_module, "service", queue):
                response = self.client.post("/api/downloaded-library/analyze-matching", json={
                    "playlist": "Bulk Test", "analysis": "needs",
                })
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["matched"], 3)
            self.assertEqual(len(response.json()["job_ids"]), 3)
            queue.enqueue_many.assert_called_once()

    def test_reanalyze_creates_analysis_only_generation_for_completed_track(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = JobRepository(root / "jobs.sqlite3")
            path = root / "Track.wav"
            path.write_bytes(b"audio")
            track_id = catalog.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=path,
                genre_category="Electronic / House", playlist_name="Test",
            )
            previous = catalog.create(path.name, path, "auto", 0, 0, False, {"analysis_only": True})
            catalog.update(previous, status="complete")
            queue = Mock()
            with patch.object(web_module, "repository", catalog), patch.object(web_module, "service", queue):
                response = self.client.post(
                    "/api/downloaded-library/reanalyze", json={"track_ids": [track_id]}
                )
            self.assertEqual(response.status_code, 202)
            created = response.json()["job_ids"]
            self.assertEqual(len(created), 1)
            job = catalog.get(created[0])
            config = json.loads(job["config_json"])
            self.assertTrue(config["analysis_only"])
            self.assertTrue(config["refresh_cache"])
            self.assertEqual(job["parent_job_id"], previous)
            queue.enqueue_many.assert_called_once_with(created)

    def test_playlist_wav_zip_is_generated_on_demand_without_persistent_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "Electronic" / "House" / "Track.wav"
            wav.parent.mkdir(parents=True)
            wav.write_bytes(b"RIFF-test-audio")
            batch_id = "on-demand-zip-test"
            web_module.creative_commons_batches[batch_id] = {
                "status": "complete", "playlist_name": "Test Playlist",
                "report": {"downloaded": [{
                    "filename": wav.name, "genre_category": "Electronic / House",
                    "youtube_id": "",
                }], "already_downloaded": []},
            }
            with patch.object(web_module, "_music_library_root", return_value=root):
                response = self.client.get(f"/api/imports/creative-commons/{batch_id}/download")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "application/zip")
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                self.assertEqual(archive.namelist(), ["Test Playlist/Electronic/House/Track.wav"])
            self.assertEqual(list(root.rglob("*.zip")), [])

    def test_settings_fall_back_to_application_defaults_after_reset(self) -> None:
        payload = {
            "music_library_path": str(Path(tempfile.gettempdir()) / "AudioExtender Library"),
            "preset": "auto",
            "intro_bars": 4,
            "outro_bars": 0,
            "use_stems": False,
            "auto_bars": True,
            "minimum_intro_loop_quality": 72,
            "minimum_outro_loop_quality": 70,
            "pcm_bits": 24,
            "preview_seconds": 10,
            "export_cues": True,
        }
        response = self.client.put("/api/settings", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["effective"]["intro_bars"], 4)
        self.assertEqual(
            response.json()["effective"]["music_library_path"],
            str((Path(tempfile.gettempdir()) / "AudioExtender Library").resolve()),
        )
        reset = self.client.delete("/api/settings")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["overrides"], {})
        self.assertEqual(
            reset.json()["effective"]["intro_bars"],
            reset.json()["defaults"]["intro_bars"],
        )

    def test_analytics_endpoint_has_feedback_fields(self) -> None:
        response = self.client.get("/api/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("acceptance_rate", response.json())
        self.assertIn("common_tags", response.json())

    def test_batch_download_defaults_to_extended_wav(self) -> None:
        request = BatchDownloadRequest(job_ids=[1, 2])
        self.assertEqual(request.file_types, ["extended"])

    def test_batch_download_requires_at_least_one_file_type(self) -> None:
        response = self.client.post(
            "/api/library/download", json={"job_ids": [1], "file_types": []}
        )
        self.assertEqual(response.status_code, 422)

    def test_authorized_import_rejects_non_youtube_sources(self) -> None:
        response = self.client.post(
            "/api/imports/authorized",
            json={
                "url": "https://example.com/audio",
                "rights_basis": "own-upload",
                "confirmation": True,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_authorized_import_requires_rights_confirmation(self) -> None:
        response = self.client.post(
            "/api/imports/authorized",
            json={
                "url": "https://www.youtube.com/watch?v=authorized",
                "rights_basis": "permission",
                "confirmation": False,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_local_audio_import_rejects_non_audio_files(self) -> None:
        response = self.client.post(
            "/api/imports/local-audio",
            data={"playlist_name": "My Playlist"},
            files=[("files", ("notes.txt", b"not audio", "text/plain"))],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported audio file", response.json()["detail"])

    def test_application_cleanup_requires_exact_confirmation(self) -> None:
        response = self.client.post(
            "/api/settings/cleanup", json={"confirmation": "delete everything"}
        )
        self.assertEqual(response.status_code, 400)

    def test_settings_reject_relative_music_library_path(self) -> None:
        response = self.client.put(
            "/api/settings",
            json={"music_library_path": "relative/music", "preset": "auto"},
        )
        self.assertEqual(response.status_code, 400)

    def test_authorized_import_does_not_extend_by_default(self) -> None:
        request = AuthorizedImportRequest(
            url="https://www.youtube.com/watch?v=authorized",
            rights_basis="permission",
            confirmation=True,
        )
        self.assertFalse(request.process_with_extender)

    def test_playlist_csv_matches_exported_spotify_columns(self) -> None:
        tracks = _playlist_csv_tracks(
            b"Track URI,Track Name,Artist Name(s),Duration (ms),Genres,Tempo\n"
            b"spotify:track:123,Freestyler,FAULHABER,179612,slap house,155.002\n"
        )
        self.assertEqual(tracks[0]["title"], "Freestyler")
        self.assertEqual(tracks[0]["artist"], "FAULHABER")
        self.assertEqual(tracks[0]["duration_ms"], 179612)
        self.assertEqual(tracks[0]["genre"], "slap house")
        self.assertEqual(tracks[0]["genre_category"], "Electronic / House / House")

    def test_playlist_genres_are_generalized_for_dj_folders(self) -> None:
        self.assertEqual(_generalized_genre("hard techno, schranz"), "Electronic / Techno / Schranz")
        self.assertEqual(_generalized_genre("afro house"), "Electronic / House / Afro House")
        self.assertEqual(_generalized_genre("liquid drum and bass"), "Electronic / Drum & Bass / Liquid")
        self.assertEqual(_generalized_genre("reggaeton, urbano latino"), "Latin / Reggaeton")
        self.assertEqual(_generalized_genre("salsa, timba"), "Latin / Salsa")
        self.assertEqual(_generalized_genre("corridos tumbados"), "Latin / Corridos")
        self.assertEqual(_generalized_genre("cumbia sonidera"), "Latin / Cumbia")
        self.assertEqual(_generalized_genre("latin house"), "Electronic / House / Latin House")
        self.assertEqual(_generalized_genre("deep house"), "Electronic / House / Deep House")
        self.assertEqual(_generalized_genre("deep bass"), "Electronic / Bass / Deep Bass")
        self.assertEqual(_generalized_genre("acid techno"), "Electronic / Techno / Acid Techno")
        self.assertEqual(_generalized_genre("merengue,salsa"), "Latin / Merengue")
        self.assertEqual(_generalized_genre("salsa,merengue"), "Latin / Salsa")
        self.assertEqual(_generalized_genre("latin jazz, salsa"), "Latin / Latin Jazz")
        self.assertEqual(_generalized_genre("vallenato, latin"), "Latin / Vallenato")
        self.assertEqual(_generalized_genre("neoperreo"), "Latin / Reggaeton")
        self.assertEqual(_generalized_genre("latin rock"), "Latin / Latin Rock")
        self.assertEqual(_generalized_genre("future bass"), "Electronic / Bass / Future Bass")
        self.assertEqual(_generalized_genre("dubstep"), "Electronic / Bass / Dubstep")
        self.assertEqual(_generalized_genre("trip hop"), "Electronic / Downtempo / Trip Hop")
        self.assertEqual(_generalized_genre("phonk"), "Electronic / Bass / Phonk")
        self.assertEqual(_generalized_genre("chanson"), "Pop / Chanson")
        self.assertEqual(_generalized_genre("salsa, latin dance, edm"), "Latin / Salsa")
        self.assertEqual(_generalized_genre("merengue, latin dance, electronic"), "Latin / Merengue")
        self.assertEqual(_generalized_genre("rock, alternative, edm"), "Rock & Alternative")
        self.assertEqual(_generalized_genre("electronic, edm"), "Electronic / General")
        self.assertEqual(_genre_path_parts("Latin / Merengue"), ("Latin", "Merengue"))
        self.assertEqual(_genre_path_parts("Techno"), ("Electronic", "Techno", "Techno"))
        self.assertEqual(_genre_path_parts("Electronic / Techno / Schranz"), ("Electronic", "Techno", "Schranz"))
        self.assertEqual(_genre_path_parts("Latin / Other"), ("Latin", "Other"))
        self.assertEqual(_genre_path_parts("Other"), ("Other",))
        self.assertEqual(_generalized_genre(""), "Other")

    def test_catalog_genre_preserves_manual_folder_over_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wav = Path(temporary) / "Artist - Vanity.wav"
            self.assertEqual(
                _catalog_genre_category(wav, "Rock & Alternative", "italo disco"),
                "Rock & Alternative",
            )

    def test_catalog_genre_preserves_complete_nested_folder_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "Electronic" / "House" / "Afro House" / "Song.wav"
            wav.parent.mkdir(parents=True)
            wav.touch()
            with patch.object(web_module, "_music_library_root", return_value=root.resolve()):
                self.assertEqual(
                    _catalog_genre_category(wav, "Electronic / General", "afro house"),
                    "Electronic / House / Afro House",
                )

    def test_catalog_without_metadata_uses_needs_genre_not_latin_other(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wav = Path(temporary) / "Latin" / "Other" / "Unknown.wav"
            self.assertEqual(
                _catalog_genre_category(wav, "Latin / Other", ""),
                "Other",
            )

    def test_non_latin_metadata_does_not_inherit_latin_other_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wav = Path(temporary) / "Latin" / "Other" / "Unknown.wav"
            self.assertEqual(
                _catalog_genre_category(wav, "Latin / Other", "experimental electronic"),
                "Electronic / General",
            )
            self.assertEqual(
                _catalog_genre_category(wav, "Latin / Other", "uncategorized"),
                "Other",
            )
            self.assertEqual(
                _catalog_genre_category(wav, "Latin / Other", "latin"),
                "Latin / Other",
            )

    def test_playlist_csv_requires_track_and_artist_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "Track Name"):
            _playlist_csv_tracks(b"Album,Year\nExample,2026\n")

    def test_youtube_match_ranks_artist_title_and_duration_together(self) -> None:
        track = {
            "title": "Fiesta Loca",
            "artist": "Activator",
            "duration_ms": 214000,
        }
        match, score, warnings = _best_youtube_match(
            track,
            [
                {
                    "id": "wrong",
                    "title": "Ricky Martin - Livin La Vida Loca",
                    "duration": 214,
                    "channel": "Ricky Martin",
                },
                {
                    "id": "right",
                    "title": "Activator - Fiesta Loca",
                    "duration": 216,
                    "channel": "Activator",
                },
            ],
        )
        self.assertEqual(match["id"], "right")
        self.assertGreater(score, 80)
        self.assertEqual(warnings, [])

    def test_youtube_match_rejects_tutorials_and_long_mixes(self) -> None:
        track = {"title": "Baile93", "artist": "HELLBOUND!", "duration_ms": 190000}
        match, _, warnings = _best_youtube_match(
            track,
            [
                {
                    "id": "tutorial",
                    "title": "HELLBOUND Baile93 production tutorial",
                    "duration": 920,
                    "channel": "HELLBOUND",
                }
            ],
        )
        self.assertEqual(match, {})
        self.assertIn("no reliable match selected", warnings)


class QueueControlTests(unittest.TestCase):
    def test_analysis_only_jobs_use_memory_aware_parallel_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "jobs.sqlite3")
            service = WebJobService(root, repository)
            release = threading.Event()
            started: list[int] = []

            def hold(job_id: int) -> None:
                started.append(job_id)
                release.wait(timeout=2)

            service._run = hold  # type: ignore[method-assign]
            job_ids = []
            for index in range(3):
                source = root / f"Track {index}.wav"
                source.write_bytes(b"audio")
                job_ids.append(repository.create(
                    source.name, source, "auto", 0, 0, False,
                    {"analysis_only": True},
                ))
            try:
                with patch("helpers.web_jobs.choose_worker_count", return_value=(3, [], 16 * 1024**3)):
                    service.enqueue_many(job_ids)
                    deadline = time.time() + 1
                    while len(service.snapshot()["active_ids"]) < 3 and time.time() < deadline:
                        time.sleep(.01)
                self.assertEqual(set(service.snapshot()["active_ids"]), set(job_ids))
                self.assertEqual(set(started), set(job_ids))
            finally:
                release.set()
                service.executor.shutdown(wait=True)

    def test_progress_waits_while_paused_and_resumes_at_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            job_id = repository.create(
                "Song.mp3", Path(temporary) / "Song.mp3", "auto", 8, 8, False
            )
            gate = threading.Event()
            reporter = DatabaseProgress(repository, job_id, gate)
            worker = threading.Thread(target=reporter.update, args=(35.0, "Analysis"))
            worker.start()
            time.sleep(0.05)
            self.assertTrue(worker.is_alive())
            paused = repository.get(job_id)
            assert paused is not None
            self.assertEqual(paused["stage"], "Paused")
            gate.set()
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            resumed = repository.get(job_id)
            assert resumed is not None
            self.assertEqual(resumed["progress"], 35.0)

    def test_scheduler_snapshot_exposes_pending_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "jobs.sqlite3")
            service = WebJobService(Path(temporary), repository)
            try:
                with service._lock:
                    service._pending = [8, 3, 12]
                self.assertEqual(service.snapshot()["pending"], [8, 3, 12])
            finally:
                service.executor.shutdown(wait=True)


class CustomCandidateTests(unittest.TestCase):
    def test_custom_candidate_bounds_are_validated(self) -> None:
        EditConfig(
            custom_intro_start=4.0,
            custom_intro_end=12.0,
            custom_intro_copies=2,
        ).validate()
        with self.assertRaises(ConfigurationError):
            EditConfig(custom_intro_start=12.0, custom_intro_end=4.0).validate()

    def test_custom_candidate_requires_both_bounds(self) -> None:
        with self.assertRaises(ConfigurationError):
            EditConfig(custom_outro_start=30.0).validate()

    def test_arrangement_insertion_requires_complete_valid_bounds(self) -> None:
        EditConfig(
            insert_source_start=8.0,
            insert_source_end=16.0,
            insert_destination=64.0,
            insert_copies=2,
        ).validate()
        with self.assertRaises(ConfigurationError):
            EditConfig(insert_source_start=8.0, insert_source_end=16.0).validate()
        with self.assertRaises(ConfigurationError):
            EditConfig(
                insert_source_start=16.0,
                insert_source_end=8.0,
                insert_destination=64.0,
            ).validate()


if __name__ == "__main__":
    unittest.main()
