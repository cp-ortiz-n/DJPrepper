from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from audioextender.imports.service import ImportNotFoundError, ImportService, LibraryOfflineError
from audioextender.imports.source_artwork import ArtworkSyncResult, SourceArtworkService


@dataclass
class ImportRequest:
    url: str = "https://soundcloud.com/example/authorized-mix"
    rights_basis: str = "permission"
    confirmation: bool = True
    process_with_extender: bool = False
    title: str = ""
    artist: str = ""
    spotify_uri: str = ""
    artwork_url: str = ""


class ImportServiceTests(unittest.TestCase):
    def make_service(
        self,
        root: Path,
        thread: Mock | None = None,
        repository: Mock | None = None,
        source_artwork: Mock | None = None,
    ) -> ImportService:
        thread = thread or Mock()
        return ImportService(
            repository=repository or Mock(),
            processing_service=Mock(),
            library_root=lambda: root,
            effective_settings=lambda: {},
            preset_snapshot=lambda _name: {},
            duplicate_lookup=lambda _source_id: None,
            probe_audio=lambda _path: {},
            source_artwork=source_artwork or Mock(spec=SourceArtworkService),
            thread_factory=lambda **_kwargs: thread,
        )

    def test_offline_root_is_rejected_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "disconnected-drive" / "AudioExtenderLibrary"
            local_fallback = Path(temporary) / "Music" / "AudioExtender Library"
            local_fallback.mkdir(parents=True)
            worker = Mock()
            service = self.make_service(missing, worker)
            with self.assertRaises(LibraryOfflineError):
                service.start(ImportRequest())
            self.assertFalse(missing.exists())
            self.assertEqual(list(local_fallback.iterdir()), [])
            worker.start.assert_not_called()

    def test_start_cancel_status_and_clear_share_one_state_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = Mock()
            service = self.make_service(Path(temporary), worker)
            import_id = service.start(ImportRequest())
            self.assertEqual(service.status(import_id)["source_provider"], "soundcloud")
            self.assertTrue(service.has_active_imports())
            self.assertEqual(service.cancel(import_id)["status"], "canceling")
            self.assertEqual(service.status(import_id)["stage"], "Canceling import")
            worker.start.assert_called_once()
            service.clear()
            with self.assertRaises(ImportNotFoundError):
                service.status(import_id)

    def test_youtube_worker_persists_artwork_selected_by_shared_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = Mock()
            artwork = Mock(spec=SourceArtworkService)
            artwork.sync_import.return_value = ArtworkSyncResult(
                "https://i.scdn.co/cover.jpg",
                str(root / ".artwork" / "cover.jpg"),
                "spotify",
            )
            service = self.make_service(root, repository=repository, source_artwork=artwork)
            request = ImportRequest(
                url="https://www.youtube.com/watch?v=abcDEF12345",
                spotify_uri="spotify:track:spotify123",
                artwork_url="https://i.scdn.co/cover.jpg",
            )

            class FakeYoutubeDownloader:
                def __init__(self, options: dict) -> None:
                    self.options = options

                def __enter__(self):
                    return self

                def __exit__(self, *_args) -> None:
                    return None

                def extract_info(self, _url: str, *, download: bool) -> dict:
                    self.assert_download(download)
                    Path(self.options["outtmpl"]).parent.joinpath("source.wav").write_bytes(b"audio")
                    return {
                        "id": "abcDEF12345",
                        "title": "Imported Track",
                        "uploader": "DJ Example",
                        "duration": 180,
                        "thumbnail": "https://i.ytimg.com/youtube.jpg",
                    }

                @staticmethod
                def assert_download(download: bool) -> None:
                    if not download:
                        raise AssertionError("worker must download the authorized source")

            import_id = service.start(request)
            with patch(
                "audioextender.imports.service.importlib.import_module",
                return_value=SimpleNamespace(YoutubeDL=FakeYoutubeDownloader),
            ):
                service.run(import_id, request)

            artwork.sync_import.assert_called_once()
            artwork_call = artwork.sync_import.call_args.kwargs
            self.assertEqual(artwork_call["source_url"], request.url)
            self.assertEqual(artwork_call["spotify_uri"], request.spotify_uri)
            self.assertEqual(artwork_call["provider_info"]["thumbnail"], "https://i.ytimg.com/youtube.jpg")
            stored = repository.upsert_downloaded_track.call_args.kwargs
            self.assertEqual(stored["artwork_url"], "https://i.scdn.co/cover.jpg")
            self.assertEqual(stored["artwork_path"], str(root / ".artwork" / "cover.jpg"))
            status = service.status(import_id)
            self.assertEqual(status["status"], "complete")
            self.assertTrue(status["artwork_synced"])
            self.assertEqual(status["artwork_source"], "spotify")


if __name__ == "__main__":
    unittest.main()
