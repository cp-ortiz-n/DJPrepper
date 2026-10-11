"""Behavioral compatibility contracts for the legacy web composition root."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from audioextender.repositories.facade import JobRepository
from audioextender.web import application as web


def public_route_inventory() -> list[tuple[str, str]]:
    schema = web.app.openapi()
    supported_methods = {"get", "post", "put", "patch", "delete", "options", "head"}
    return sorted(
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in supported_methods
    )


class WebCompositionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(web.app)

    def test_public_route_inventory_is_compatible(self) -> None:
        inventory = public_route_inventory()
        encoded = json.dumps(inventory, separators=(",", ":")).encode()

        self.assertEqual(len(inventory), 152)
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            "ea143280700e65f754a37efb2a2782ab76dbafcd04513ddda844a83c3c57f3d3",
            "Public route inventory changed:\n" + json.dumps(inventory, indent=2),
        )

    def test_delivery_shell_contract_is_stable(self) -> None:
        shell = web.create_app()

        self.assertEqual(shell.title, "DJ Library Studio")
        self.assertEqual(shell.docs_url, "/api/docs")
        self.assertIsNone(shell.redoc_url)
        self.assertEqual(
            {(getattr(route, "path", ""), getattr(route, "name", "")) for route in shell.routes},
            {
                ("/openapi.json", "openapi"),
                ("/api/docs", "swagger_ui_html"),
                ("/docs/oauth2-redirect", "swagger_ui_redirect"),
                ("/vendor/wavesurfer", "wavesurfer"),
                ("/assets", "assets"),
            },
        )
        self.assertEqual(len(shell.user_middleware), 1)
        self.assertIs(shell.user_middleware[0].cls, GZipMiddleware)
        self.assertEqual(shell.user_middleware[0].kwargs, {"minimum_size": 1024, "compresslevel": 5})

    def test_runtime_paths_and_composed_dependencies_remain_project_local(self) -> None:
        project = Path(__file__).resolve().parents[1]

        self.assertEqual(web.PROJECT, project)
        self.assertEqual(web.INPUT, project / "input")
        self.assertEqual(web.OUTPUT, project / "output")
        self.assertEqual(web.WEB, project / "web")
        self.assertEqual(web.DATABASE, project / "output" / "reports" / "audioextender.sqlite3")
        self.assertEqual(web.repository.path, web.DATABASE)
        self.assertIs(web.service.repository, web.repository)
        self.assertEqual(web.service.project, project)

    def test_success_and_framework_error_shapes_are_stable(self) -> None:
        config = self.client.get("/api/config")
        missing = self.client.get("/api/route-that-does-not-exist")
        invalid = self.client.post("/api/jobs", json={})

        self.assertEqual(config.status_code, 200)
        self.assertEqual(
            set(config.json()),
            {"presets", "preset_details", "bar_counts", "defaults", "effective", "overrides"},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json(), {"detail": "Not Found"})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(set(invalid.json()), {"detail"})
        self.assertTrue(invalid.json()["detail"])
        self.assertEqual(
            {"type", "loc", "msg", "input"},
            set(invalid.json()["detail"][0]),
        )

    def test_disconnected_library_response_contract_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "state.sqlite3")
            unavailable = root / "Disconnected Drive" / "Library"
            web.library_status_cache.update(payload=None, expires_at=0.0)
            with (
                patch.object(web, "repository", repository),
                patch.object(web, "_music_library_root", return_value=unavailable),
            ):
                response = self.client.get("/api/settings/library-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "path",
                "online",
                "cataloged_tracks",
                "available_tracks",
                "offline_tracks",
                "library_id",
                "file_count",
                "total_bytes",
                "song_bytes",
                "supporting_bytes",
                "capacity_bytes",
                "free_bytes",
                "audio_quality",
                "location_integrity",
                "storage_scan_ms",
            },
        )
        self.assertFalse(payload["online"])
        self.assertEqual(payload["path"], str(unavailable))

    def test_startup_reports_the_selected_ai_provider_without_mutating_state(self) -> None:
        status = {
            "available": True,
            "provider": "ollama",
            "model": "contract-model",
            "local_runtime": True,
        }
        with (
            patch.object(type(web.intention_planner), "status", return_value=status),
            patch.object(web.logger, "info") as info,
            TestClient(web.app),
        ):
            pass

        info.assert_called_once_with(
            "Set Builder AI ready: provider=%s model=%s local_runtime=%s",
            "ollama",
            "contract-model",
            True,
        )


if __name__ == "__main__":
    unittest.main()
