from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.core.presets import EditPreset
from audioextender.web.preset_routes import (
    PresetRouteDependencies,
    PresetService,
    create_preset_router,
)


class PresetRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary.name) / "presets.json"
        self.service = PresetService(
            PresetRouteDependencies(
                state_path=lambda: self.state_path,
                built_in_presets={"built-in": EditPreset(8, 8, False, 70, 2)},
                supported_bar_counts=frozenset({0, 4, 8, 16}),
            )
        )
        app = FastAPI()
        app.include_router(create_preset_router(self.service))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def request(name: str, *, intro_bars: int = 4) -> dict:
        return {
            "name": name,
            "intro_bars": intro_bars,
            "outro_bars": 8,
            "use_stems": True,
            "minimum_loop_quality": 75,
            "maximum_repetitions": 3,
        }

    def test_custom_preset_survives_service_recreation_and_exposes_snapshot(self) -> None:
        response = self.client.put("/api/presets/new-preset", json=self.request("new-preset"))
        self.assertEqual(response.status_code, 200)
        recreated = PresetService(self.service._dependencies)
        self.assertEqual(recreated.available()["new-preset"].intro_bars, 4)
        self.assertEqual(recreated.snapshot("new-preset")["preset_definition"]["outro_bars"], 8)

    def test_rename_hides_built_in_and_restore_recovers_it(self) -> None:
        renamed = self.client.put("/api/presets/built-in", json=self.request("custom"))
        self.assertEqual(renamed.status_code, 200)
        names = {item["name"] for item in renamed.json()["presets"]}
        self.assertEqual(names, {"custom"})
        restored = self.client.post("/api/presets/restore")
        self.assertEqual({item["name"] for item in restored.json()["presets"]}, {"built-in"})

    def test_validation_conflict_and_missing_delete_preserve_contracts(self) -> None:
        invalid = self.client.put("/api/presets/new", json=self.request("new", intro_bars=7))
        self.assertEqual(invalid.status_code, 400)
        conflict = self.client.put("/api/presets/other", json=self.request("built-in"))
        self.assertEqual(conflict.status_code, 409)
        missing = self.client.delete("/api/presets/missing")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
