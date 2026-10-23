from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.imports.rekordbox_ratings import (
    RekordboxRatingImportError,
    RekordboxRatingSyncService,
    parse_rekordbox_ratings,
)
from audioextender.persistence.facade import JobRepository
from audioextender.web.routes.rekordbox_rating_routes import create_rekordbox_rating_router


def collection_xml(*tracks: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="{len(tracks)}">'
        f"{''.join(tracks)}</COLLECTION></DJ_PLAYLISTS>"
    ).encode()


def collection_text(*rows: str) -> bytes:
    header = "#\tTrack Title\tArtist\tBPM\tKey\tAlbum\tGenre\tRating\tTime\tDate Added"
    return (header + "\n" + "\n".join(rows)).encode("utf-16")


class RekordboxRatingParserTests(unittest.TestCase):
    def test_parses_five_star_and_native_rekordbox_rating_scales(self) -> None:
        tracks, summary = parse_rekordbox_ratings(
            collection_xml(
                '<TRACK TrackID="1" Name="One" Artist="DJ" Rating="5"/>',
                '<TRACK TrackID="2" Name="Two" Artist="DJ" Rating="204"/>',
                '<TRACK TrackID="3" Name="Unknown" Rating="0"/>',
                '<TRACK TrackID="4" Name="Invalid" Rating="9"/>',
            )
        )

        self.assertEqual([track.rating for track in tracks], [5, 4])
        self.assertEqual(
            summary,
            {"format": "xml", "total_export_tracks": 4, "unrated_tracks": 1, "invalid_rows": 1},
        )

    def test_parses_utf16_tab_separated_star_ratings_and_duration(self) -> None:
        tracks, summary = parse_rekordbox_ratings(
            collection_text(
                "1\tDolce Vita\tMs Project, Ryan Paris\t121.58\t4B\tDisco\tDisco & Funk\t***  \t04:14\t2026-10-03",
                "2\tMust Be Love\tYung Bae\t123.00\t5A\tDisco\tDisco & Funk\t*****\t03:00\t2026-10-03",
                "3\tLast Dance\tDonna Summer\t125.37\t5A\tDisco\tDisco & Funk\t     \t04:56\t2026-10-03",
            )
        )

        self.assertEqual(
            [(track.title, track.rating, track.duration_seconds) for track in tracks],
            [
                ("Dolce Vita", 3, 254.0),
                ("Must Be Love", 5, 180.0),
            ],
        )
        self.assertEqual(
            summary,
            {"format": "txt", "total_export_tracks": 3, "unrated_tracks": 1, "invalid_rows": 0},
        )

    def test_rejects_non_rekordbox_and_entity_xml(self) -> None:
        with self.assertRaises(RekordboxRatingImportError):
            parse_rekordbox_ratings(b"<library />")
        with self.assertRaises(RekordboxRatingImportError):
            parse_rekordbox_ratings(b'<!DOCTYPE x [<!ENTITY y "z">]><DJ_PLAYLISTS/>')


class RekordboxRatingSyncServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = JobRepository(self.root / "catalog.sqlite3")
        self.published = 0
        self.service = RekordboxRatingSyncService(self.repository, self._publish)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _publish(self) -> None:
        self.published += 1

    def _track(
        self,
        title: str,
        artist: str,
        duration: float = 180.0,
        *,
        filename: str | None = None,
    ) -> tuple[int, Path]:
        path = self.root / (filename or f"{artist} - {title}.wav")
        path.write_bytes(b"RIFF" + title.encode())
        return (
            self.repository.upsert_downloaded_track(
                title=title,
                artist=artist,
                file_path=path,
                duration_seconds=duration,
            ),
            path,
        )

    def test_previews_conservative_match_order_and_applies_idempotently(self) -> None:
        direct_id, _ = self._track("Direct", "Artist")
        path_id, path = self._track("Moved title", "Path Artist")
        metadata_id, _ = self._track("Metadata", "Exact Artist", 201.0)
        xml = collection_xml(
            f'<TRACK TrackID="11" Name="Wrong" Artist="Wrong" Rating="255" Comments="DJLS:downloaded:{direct_id}"/>',
            f'<TRACK TrackID="12" Name="Old" Artist="Old" Rating="4" Location="{path.as_uri()}"/>',
            '<TRACK TrackID="13" Name="Metadata" Artist="Exact Artist" TotalTime="201" Rating="3"/>',
            '<TRACK TrackID="14" Name="Missing" Artist="Nobody" TotalTime="90" Rating="2"/>',
        )

        preview = self.service.preview(xml, "rekordbox.xml")

        self.assertEqual(preview["matched_tracks"], 3)
        self.assertEqual(preview["unmatched_rows"], 1)
        self.assertEqual(
            preview["match_methods"],
            {"catalog-identity": 1, "file-location": 1, "artist-title-duration": 1},
        )
        result = self.service.apply(preview["token"])
        self.assertEqual(result["changed"], 3)
        self.assertEqual(self.published, 1)
        stored = {item["track_id"]: item["rating"] for item in self.repository.external_track_ratings("rekordbox")}
        self.assertEqual(stored, {direct_id: 5, path_id: 4, metadata_id: 3})

        repeated = self.service.preview(xml, "rekordbox.xml")
        self.assertEqual(repeated["proposed_changes"], 0)
        self.assertEqual(self.service.apply(repeated["token"])["changed"], 0)
        self.assertEqual(self.published, 1)

    def test_ambiguous_metadata_is_never_applied_and_clear_is_source_scoped(self) -> None:
        self._track("Duplicate", "Artist", 180, filename="Duplicate A.wav")
        self._track("Duplicate", "Artist", 180, filename="Duplicate B.wav")
        preview = self.service.preview(
            collection_xml('<TRACK TrackID="1" Name="Duplicate" Artist="Artist" TotalTime="180" Rating="5"/>')
        )
        self.assertEqual(preview["ambiguous_rows"], 1)
        self.assertEqual(preview["matched_tracks"], 0)
        self.assertEqual(self.service.apply(preview["token"])["changed"], 0)
        self.assertEqual(self.service.clear(), {"removed": 0, "status": self.service.status()})

    def test_http_preview_apply_status_and_clear_workflow(self) -> None:
        track_id, _ = self._track("Rated", "Artist")
        app = FastAPI()
        app.include_router(create_rekordbox_rating_router(self.service))
        client = TestClient(app)
        xml = collection_xml(
            f'<TRACK TrackID="1" Name="Rated" Artist="Artist" Rating="5" Comments="DJLS:downloaded:{track_id}"/>'
        )

        preview = client.post(
            "/api/settings/rekordbox-ratings/preview",
            files={"file": ("collection.xml", xml, "application/xml")},
        )
        self.assertEqual(preview.status_code, 200)
        applied = client.post(
            "/api/settings/rekordbox-ratings/apply",
            json={"token": preview.json()["token"]},
        )
        self.assertEqual(applied.json()["changed"], 1)
        self.assertEqual(client.get("/api/settings/rekordbox-ratings").json()["ratings"]["5"], 1)
        self.assertEqual(client.delete("/api/settings/rekordbox-ratings").json()["removed"], 1)

    def test_http_accepts_rekordbox_text_export(self) -> None:
        self._track("Must Be Love", "Yung Bae", 180)
        app = FastAPI()
        app.include_router(create_rekordbox_rating_router(self.service))
        response = TestClient(app).post(
            "/api/settings/rekordbox-ratings/preview",
            files={
                "file": (
                    "collection.txt",
                    collection_text(
                        "1\tMust Be Love\tYung Bae\t123.00\t5A\tDisco\tDisco & Funk\t*****\t03:00\t2026-10-03"
                    ),
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["format"], "txt")
        self.assertEqual(response.json()["matched_tracks"], 1)


if __name__ == "__main__":
    unittest.main()
