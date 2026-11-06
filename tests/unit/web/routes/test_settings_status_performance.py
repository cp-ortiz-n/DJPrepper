from __future__ import annotations

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from audioextender.web.routes.settings_routes import SettingsRouteDependencies, SettingsRouteService


class SettingsStatusPerformanceTests(unittest.TestCase):
    def test_normal_status_avoids_recursive_library_scan(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            track = root / "Track.wav"
            track.write_bytes(b"audio")
            repository = Mock()
            repository.list_downloaded_tracks.return_value = [{"file_path": str(track)}]
            repository.audio_quality_summary.return_value = {}
            dependencies = Mock(
                spec=SettingsRouteDependencies,
                music_library_root=lambda: root,
                library_status_cache={"payload": None, "expires_at": 0.0},
                library_status_lock=threading.Lock(),
                repository=lambda: repository,
                library_location_summary=lambda: {},
                metadata_batches=Mock(latest=Mock(return_value=None)),
            )

            with patch(
                "audioextender.web.routes.settings_routes.os.scandir",
                side_effect=AssertionError("recursive scan"),
            ):
                service = SettingsRouteService(dependencies)
                status = service.library_status()
                self.assertEqual(service.library_status(), status)
                repository.list_downloaded_tracks.assert_called_once()

            (root / "support.txt").write_bytes(b"support")
            verified = service.library_status(refresh=True)
            self.assertEqual(verified["total_bytes"], 12)
            self.assertEqual(verified["file_count"], 2)
            dependencies.library_status_cache["expires_at"] = 0
            with patch(
                "audioextender.web.routes.settings_routes.os.scandir",
                side_effect=AssertionError("recursive scan"),
            ):
                routine = service.library_status()
                self.assertEqual(routine["supporting_bytes"], 7)
                self.assertEqual(routine["file_count"], 2)

            with (
                patch.object(
                    service,
                    "storage_inventory",
                    side_effect=AssertionError("health must not crawl storage"),
                ),
                patch.object(service, "cached_storage_inventory", return_value={"reclaimable_bytes": 17}),
            ):
                health = service.library_health()
                self.assertEqual(health["storage"]["reclaimable_bytes"], 17)

        self.assertEqual(status["available_tracks"], 1)
        self.assertEqual(status["total_bytes"], 5)
        self.assertEqual(status["file_count"], 1)


if __name__ == "__main__":
    unittest.main()
