from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from audioextender.imports.creative_commons import CreativeCommonsImportService
from audioextender.imports.creative_commons_routes import (
    CreativeCommonsArchiveDependencies,
    CreativeCommonsArchiveService,
    ImportIssueDependencies,
    ImportIssueService,
    create_creative_commons_router,
)


class _IssueRepository:
    def __init__(self) -> None:
        self.failures: list[dict[str, Any]] = []
        self.recorded: list[dict[str, str]] = []
        self.resolved: list[tuple[str, str, str]] = []

    def list_import_failures(self, *, include_resolved: bool = False) -> list[dict[str, Any]]:
        return list(self.failures)

    def record_import_failure(self, **values: str) -> None:
        self.recorded.append(values)
        self.failures.append({"id": len(self.failures) + 1, **values})

    def resolve_import_failure(self, *, playlist_name: str, title: str, artist: str) -> None:
        self.resolved.append((playlist_name, title, artist))


class CreativeCommonsRoutesTests(unittest.TestCase):
    def _issues(self, root: Path, repository: _IssueRepository, lifecycle: Mock) -> ImportIssueService:
        return ImportIssueService(
            ImportIssueDependencies(
                repository=lambda: repository,
                lifecycle=lambda: cast(CreativeCommonsImportService, lifecycle),
                report_root=root,
                safe_folder_name=lambda value: value.replace("/", "-") or "Imported Playlist",
                generalized_genre=lambda genre: f"general:{genre}",
                normalize_genre=lambda genre: f"normalized:{genre}",
            )
        )

    def test_import_issue_listing_backfills_legacy_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "Party" / "Party - Import Report.json"
            report.parent.mkdir()
            report.write_text(
                json.dumps(
                    {
                        "playlist_name": "Party",
                        "results": {
                            "failed": [
                                {
                                    "title": "Missing",
                                    "artist": "Artist",
                                    "spotify_uri": "spotify:track:1",
                                    "url": "https://youtube.com/watch?v=1",
                                    "error": "Unavailable",
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            repository = _IssueRepository()
            payload = self._issues(root, repository, Mock()).list()

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["failures"][0]["title"], "Missing")
        self.assertEqual(repository.recorded[0]["youtube_url"], "https://youtube.com/watch?v=1")

    def test_retry_and_dismiss_validate_current_failures(self) -> None:
        repository = _IssueRepository()
        repository.failures = [{"id": 7, "playlist_name": "Party", "title": "Track", "artist": "DJ"}]
        lifecycle = Mock()
        lifecycle.start_retry.return_value = {"batch_id": "retry", "retry_count": 1}
        service = self._issues(Path("/unused"), repository, lifecycle)

        self.assertEqual(service.retry([7]), {"batch_id": "retry", "retry_count": 1})
        lifecycle.start_retry.assert_called_once_with(repository.failures)
        self.assertEqual(service.dismiss(7), {"resolved": True, "id": 7})
        self.assertEqual(repository.resolved, [("Party", "Track", "DJ")])
        with self.assertRaises(HTTPException) as context:
            service.retry([99])
        self.assertEqual(context.exception.status_code, 404)

    def test_original_metadata_prefers_matching_playlist_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "Party" / "Party Import Report.json"
            report.parent.mkdir()
            report.write_text(
                json.dumps(
                    {
                        "results": {
                            "downloaded": [
                                {"title": "Track", "artist": "DJ", "genre": "Afro House", "genre_category": ""}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            service = self._issues(root, _IssueRepository(), Mock())
            metadata = service.original_metadata("Party", " track ", "dj")

        self.assertEqual(metadata, {"genre": "Afro House", "genre_category": "general:Afro House"})
        self.assertEqual(
            service.original_metadata("Unknown", "Missing", "DJ"),
            {"genre": "", "genre_category": "Other"},
        )

    def test_archive_uses_cataloged_master_and_preserves_playlist_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            master = root / "Master.wav"
            master.write_bytes(b"RIFF-audio")
            lifecycle = Mock()
            lifecycle.status.return_value = {
                "playlist_name": "Friday Party",
                "report": {"downloaded": [{"filename": "Old.wav", "genre_category": "Other", "youtube_id": "video-1"}]},
            }
            service = CreativeCommonsArchiveService(
                CreativeCommonsArchiveDependencies(
                    lifecycle=cast(CreativeCommonsImportService, lifecycle),
                    music_library_root=lambda: root,
                    safe_folder_name=lambda value: value,
                    genre_path_parts=lambda category: category.split(" / "),
                    cataloged_download=lambda video_id: (
                        {
                            "file_path": str(master),
                            "genre_category": "Electronic / House",
                        }
                        if video_id == "video-1"
                        else None
                    ),
                )
            )

            archive_path, filename = service.wav_archive("batch")
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    self.assertEqual(archive.namelist(), ["Friday Party/Electronic/House/Master.wav"])
            finally:
                archive_path.unlink(missing_ok=True)

        self.assertEqual(filename, "Friday Party - WAVs.zip")
        lifecycle.status.assert_called_once_with("batch", private=True)

    def test_router_preserves_validation_and_not_found_contracts(self) -> None:
        lifecycle = Mock()
        lifecycle.start.side_effect = ValueError("Every batch item must use a YouTube URL")
        lifecycle.status.side_effect = LookupError("Creative Commons import not found")
        archives = Mock()
        issues = Mock()
        app = FastAPI()
        app.include_router(
            create_creative_commons_router(
                cast(CreativeCommonsImportService, lifecycle),
                cast(CreativeCommonsArchiveService, archives),
                cast(ImportIssueService, issues),
            )
        )
        client = TestClient(app)

        invalid = client.post(
            "/api/imports/creative-commons",
            json={
                "playlist_name": "Party",
                "tracks": [{"url": "https://example.com", "title": "Track", "artist": "DJ"}],
            },
        )
        missing = client.get("/api/imports/creative-commons/missing")

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["detail"], "Every batch item must use a YouTube URL")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "Creative Commons import not found")


if __name__ == "__main__":
    unittest.main()
