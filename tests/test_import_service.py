from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

from audioextender.imports.service import ImportNotFoundError, ImportService, LibraryOfflineError


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
    def make_service(self, root: Path, thread: Mock | None = None) -> ImportService:
        thread = thread or Mock()
        return ImportService(
            repository=Mock(),
            processing_service=Mock(),
            library_root=lambda: root,
            effective_settings=lambda: {},
            preset_snapshot=lambda _name: {},
            duplicate_lookup=lambda _source_id: None,
            probe_audio=lambda _path: {},
            cache_artwork=lambda _url, _path: "",
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


if __name__ == "__main__":
    unittest.main()
