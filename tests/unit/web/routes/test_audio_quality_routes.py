from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.web.routes.audio_quality_routes import (
    AudioQualityRouteDependencies,
    AudioQualityScanService,
    create_audio_quality_router,
)


class _Repository:
    def __init__(self, tracks: list[dict[str, Any]] | None = None) -> None:
        self.tracks = tracks or []
        self.updates: list[tuple[int, dict[str, Any]]] = []

    def list_downloaded_tracks(self) -> list[dict[str, Any]]:
        return self.tracks

    def update_audio_quality(self, track_id: int, result: dict[str, Any]) -> None:
        self.updates.append((track_id, result))

    def audio_quality_summary(self) -> dict[str, int]:
        return {"total": len(self.tracks), "analyzed": len(self.updates)}


class _Result:
    def __init__(self, score: float = 91.0) -> None:
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "label": "excellent"}


class _DeferredThread:
    instances: list[_DeferredThread] = []

    def __init__(self, *, target, args, daemon: bool, name: str) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
        self.started = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True


class AudioQualityRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        _DeferredThread.instances.clear()
        self.repository = _Repository()
        self.batches: dict[str, dict[str, Any]] = {}
        self.cache: dict[str, object] = {"payload": {"stale": True}, "expires_at": 100.0}
        self.service = AudioQualityScanService(
            AudioQualityRouteDependencies(
                repository=lambda: self.repository,
                analyze=lambda *_args, **_kwargs: _Result(),
                batches=self.batches,
                batch_lock=threading.Lock(),
                library_status_cache=self.cache,
                library_status_lock=threading.Lock(),
                thread_factory=_DeferredThread,
            )
        )
        app = FastAPI()
        app.include_router(create_audio_quality_router(self.service))
        self.client = TestClient(app)

    def test_start_preserves_route_contract_and_reuses_active_scan(self) -> None:
        response = self.client.post("/api/downloaded-library/audio-quality")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "processing")
        self.assertEqual(payload["stage"], "Analyzing audio quality")
        self.assertEqual(payload["total"], 0)
        self.assertTrue(_DeferredThread.instances[0].started)
        self.assertTrue(_DeferredThread.instances[0].name.startswith("audio-quality-"))

        repeated = self.client.post("/api/downloaded-library/audio-quality").json()
        self.assertEqual(repeated["batch_id"], payload["batch_id"])
        self.assertEqual(len(_DeferredThread.instances), 1)

    def test_latest_and_unknown_status_preserve_existing_responses(self) -> None:
        latest = self.client.get("/api/downloaded-library/audio-quality-latest")
        missing = self.client.get("/api/downloaded-library/audio-quality/missing")

        self.assertEqual(latest.json(), {"status": "none", "summary": {"total": 0, "analyzed": 0}})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "Audio-quality scan not found")

    def test_run_updates_successes_records_missing_files_and_invalidates_health_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            available = Path(temporary) / "available.wav"
            available.touch()
            self.repository.tracks = [
                {"id": 1, "file_path": str(available), "filename": available.name, "youtube_id": "source"},
                {"id": 2, "file_path": str(Path(temporary) / "missing.wav"), "title": "Missing"},
            ]
            self.batches["batch"] = {
                "status": "processing",
                "processed": 0,
                "failed": 0,
                "current": "",
                "errors": [],
            }

            self.service.run("batch")

        self.assertEqual(self.repository.updates, [(1, {"score": 91.0, "label": "excellent"})])
        batch = self.batches["batch"]
        self.assertEqual(batch["status"], "complete")
        self.assertEqual(batch["stage"], "Quality scan complete")
        self.assertEqual(batch["processed"], 2)
        self.assertEqual(batch["failed"], 1)
        self.assertEqual(len(batch["errors"]), 1)
        self.assertEqual(batch["summary"], {"total": 2, "analyzed": 1})
        self.assertEqual(self.cache, {"payload": None, "expires_at": 0.0})


if __name__ == "__main__":
    unittest.main()
