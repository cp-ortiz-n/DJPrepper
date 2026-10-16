from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audioextender.library.recording_identity import base_title, genre_family_code, version_kind
from audioextender.repositories.facade import JobRepository


class RecordingIdentityTests(unittest.TestCase):
    def test_version_labels_are_readable_and_share_a_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            original = root / "Artist - Song.wav"
            remix = root / "Artist - Song (Club Remix).wav"
            original.touch()
            remix.touch()
            original_id = repository.upsert_downloaded_track(
                title="Song",
                artist="Artist",
                file_path=original,
                duration_seconds=180,
                playlist_name="Originals",
            )
            remix_id = repository.upsert_downloaded_track(
                title="Song (Club Remix)",
                artist="Artist",
                file_path=remix,
                duration_seconds=240,
                playlist_name="Remixes",
            )
            original_track = repository.get_downloaded_track(original_id)
            remix_track = repository.get_downloaded_track(remix_id)
            assert original_track is not None and remix_track is not None
            self.assertEqual(original_track["recording_code"], remix_track["recording_code"])
            self.assertEqual(original_track["version_code"], "ORG")
            self.assertEqual(remix_track["version_code"], "RMX01")
            self.assertRegex(original_track["recording_code"], r"^OTH-\d{6,}$")
            page, total = repository.page_downloaded_tracks(page=1, page_size=10)
            self.assertEqual(total, 2)
            self.assertTrue(all(track["recording_code"] for track in page))

    def test_confirmed_duplicate_merge_preserves_references_and_keeps_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            first = root / "First.wav"
            duplicate = root / "Duplicate.wav"
            first.write_bytes(b"RIFF-first")
            duplicate.write_bytes(b"RIFF-duplicate")
            first_id = repository.upsert_downloaded_track(
                title="Same Song",
                artist="Same Artist",
                file_path=first,
                spotify_uri="spotify:track:same",
                duration_seconds=200,
                playlist_name="First List",
            )
            duplicate_id = repository.upsert_downloaded_track(
                title="Same Song",
                artist="Same Artist",
                file_path=duplicate,
                spotify_uri="spotify:track:same",
                duration_seconds=200.5,
                playlist_name="Second List",
            )
            job_id = repository.create(duplicate.name, duplicate, "auto", 0, 0, False)
            repository.update(job_id, status="complete", wav_path=str(duplicate))
            repository.set_key_verification(duplicate.name, "D minor", "F major", [], "Checked")
            repository.add_track_feedback(duplicate.name, "overall", True, "clean", "Keep this note")

            candidates = repository.duplicate_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["confidence"], "high")
            merged = repository.merge_downloaded_tracks(first_id, duplicate_id)

            self.assertEqual(len(repository.list_downloaded_tracks()), 1)
            self.assertEqual(set(merged["playlists"]), {"First List", "Second List"})
            merged_job = repository.get(job_id)
            verification = repository.key_verification(first.name)
            assert merged_job is not None
            assert verification is not None
            self.assertEqual(merged_job["source_path"], str(first.resolve()))
            self.assertEqual(verification["verified_key"], "D minor")
            self.assertEqual(repository.track_feedback(first.name)[0]["notes"], "Keep this note")
            self.assertTrue(duplicate.is_file())
            self.assertTrue(repository.downloaded_track_is_excluded(duplicate))
            self.assertEqual(merged["retained_file"], str(duplicate.resolve()))

    def test_exact_audio_fingerprint_finds_renamed_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            first = root / "Unknown Upload.wav"
            second = root / "Correct Artist - Correct Title.wav"
            first.write_bytes(b"RIFF-identical-audio")
            second.write_bytes(first.read_bytes())
            repository.upsert_downloaded_track(
                title="Unknown Upload",
                artist="",
                file_path=first,
            )
            repository.upsert_downloaded_track(
                title="Correct Title",
                artist="Correct Artist",
                file_path=second,
            )
            candidates = repository.duplicate_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["reason"], "Exact audio fingerprint")

    def test_false_positive_can_be_assigned_a_new_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            first = root / "One.wav"
            second = root / "Two.wav"
            first.write_bytes(b"RIFF-one")
            second.write_bytes(b"RIFF-two")
            repository.upsert_downloaded_track(
                title="Intro",
                artist="Artist",
                file_path=first,
                duration_seconds=60,
            )
            second_id = repository.upsert_downloaded_track(
                title="Intro",
                artist="Artist",
                file_path=second,
                duration_seconds=61,
            )
            before = repository.get_downloaded_track(second_id)
            separated = repository.separate_recording(second_id)
            assert before is not None
            self.assertNotEqual(before["recording_code"], separated["recording_code"])
            self.assertEqual(separated["identity_confidence"], "manual")
            self.assertEqual(repository.duplicate_candidates(), [])

    def test_title_normalization_keeps_version_meaning_out_of_family_name(self) -> None:
        self.assertEqual(base_title("Song (Extended Mix)"), "song")
        self.assertEqual(version_kind("Song (Live at Home)"), "LIVE")
        self.assertEqual(version_kind("Song - Radio Edit"), "RADIO")

    def test_parent_genres_receive_readable_three_letter_codes(self) -> None:
        self.assertEqual(genre_family_code("Electronic / House / Afro House"), "HOU")
        self.assertEqual(genre_family_code("Hip-Hop & Rap / Arabic Hip-Hop"), "HIP")
        self.assertEqual(genre_family_code("Latin / Reggaeton"), "LAT")
        self.assertEqual(genre_family_code("Unmapped"), "OTH")

    def test_manual_version_link_and_unlink_preserve_both_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            original = root / "Original.wav"
            remix = root / "Remix.wav"
            original.write_bytes(b"RIFF-original")
            remix.write_bytes(b"RIFF-remix")
            original_id = repository.upsert_downloaded_track(
                title="Atrevete",
                artist="Calle 13",
                file_path=original,
                duration_seconds=240,
            )
            remix_id = repository.upsert_downloaded_track(
                title="Calle 13 - Atrevete (Kevin Brand Remix)",
                artist="Kevin Brand",
                file_path=remix,
                duration_seconds=270,
            )
            original_track = repository.get_downloaded_track(original_id)
            remix_track = repository.get_downloaded_track(remix_id)
            assert original_track is not None
            assert remix_track is not None
            self.assertNotEqual(original_track["recording_code"], remix_track["recording_code"])

            linked = repository.link_recording_version(remix_id, original_id, "RMX")
            self.assertEqual(
                linked["recording_code"],
                original_track["recording_code"],
            )
            self.assertEqual(linked["version_code"], "RMX01")
            self.assertEqual(len(repository.recording_family(original_id)), 2)
            self.assertTrue(original.is_file() and remix.is_file())

            unlinked = repository.separate_recording(remix_id)
            self.assertNotEqual(unlinked["recording_code"], linked["recording_code"])
            self.assertEqual(len(repository.list_downloaded_tracks()), 2)


if __name__ == "__main__":
    unittest.main()
