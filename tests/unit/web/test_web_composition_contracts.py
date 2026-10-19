"""Behavioral compatibility contracts for the legacy web composition root."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from audioextender.repositories.facade import JobRepository
from audioextender.web import application as web
from audioextender.web.composition import ApplicationPaths, ApplicationRuntime
from tests.support.paths import PROJECT_ROOT

web_runtime = cast(Any, web)


def public_route_inventory(application=None) -> list[tuple[str, str]]:
    schema = (application or web.app).openapi()
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
        self.assertIn(("POST", "/api/set-builder/prepare-brief"), inventory)
        inventory.remove(("POST", "/api/set-builder/prepare-brief"))
        encoded = json.dumps(inventory, separators=(",", ":")).encode()

        self.assertEqual(len(inventory), 159)
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            "9e8b73fccf3268d8cffdaf9d36e35d9f623cd9831ec19fc974bf88d5f5e1d01c",
            "Public route inventory changed:\n" + json.dumps(inventory, indent=2),
        )

    def test_import_keeps_default_runtime_lazy(self) -> None:
        project = PROJECT_ROOT
        command = (
            "from audioextender.web import application as web; "
            "import json; "
            "print(json.dumps({'resolved': web.app._resolved is not None, "
            "'repository_bound': 'repository' in web.__dict__}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), {"resolved": False, "repository_bound": False})

    def test_shell_and_changed_modules_require_cache_revalidation(self) -> None:
        for path in ("/", "/assets/app.js", "/assets/navigation-controller.js"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-cache")
            conditional = self.client.get(path, headers={"If-None-Match": response.headers["etag"]})
            self.assertEqual(conditional.headers["cache-control"], "no-cache")

    def test_delivery_shell_contract_is_stable(self) -> None:
        shell = web.create_app()

        self.assertEqual(shell.title, "DJ Library Studio")
        self.assertEqual(shell.docs_url, "/api/docs")
        self.assertIsNone(shell.redoc_url)
        routes = {(getattr(route, "path", ""), getattr(route, "name", "")) for route in shell.routes}
        self.assertTrue(
            {
                ("/openapi.json", "openapi"),
                ("/api/docs", "swagger_ui_html"),
                ("/docs/oauth2-redirect", "swagger_ui_redirect"),
                ("/vendor/wavesurfer", "wavesurfer"),
                ("/assets", "assets"),
            }.issubset(routes)
        )
        self.assertEqual(public_route_inventory(shell), public_route_inventory())
        gzip = [middleware for middleware in shell.user_middleware if middleware.cls is GZipMiddleware]
        self.assertEqual(len(gzip), 1)
        self.assertEqual(gzip[0].kwargs, {"minimum_size": 1024, "compresslevel": 5})

    def test_explicit_runtime_stays_under_temporary_roots_and_recovers_only_on_startup(self) -> None:
        default_runtime = web.app.state.runtime
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = ApplicationPaths.from_project(
                root,
                web_root=PROJECT_ROOT / "web",
                default_music_library=root / "External Library",
            )
            try:
                runtime = ApplicationRuntime.create(paths)
                with patch.object(runtime.repository, "recover_interrupted") as recover:
                    isolated = web.create_app(runtime)
                    recover.assert_not_called()
                    self.assertIs(isolated.state.runtime, runtime)
                    self.assertEqual(runtime.repository.path, paths.database)
                    self.assertEqual(runtime.job_service.project, paths.project)
                    self.assertEqual(
                        runtime.relocation.manifest_path,
                        paths.output / "reports" / "library_relocation.json",
                    )
                    self.assertTrue(
                        all(
                            str(path).startswith(str(paths.project))
                            for path in paths.__dict__.values()
                            if isinstance(path, Path) and path != paths.web
                        )
                    )
                    planner = runtime.services["intention_planner"]
                    with (
                        patch.object(type(planner), "status", return_value={"available": False}),
                        TestClient(isolated),
                    ):
                        pass
                    recover.assert_called_once_with()
                generated = web.create_app(paths=paths)
                self.assertEqual(generated.state.runtime.paths, paths)
                with self.assertRaisesRegex(ValueError, "either runtime or paths"):
                    web.create_app(runtime, paths=paths)
            finally:
                web._bind_runtime(default_runtime)

    def test_runtime_paths_and_composed_dependencies_remain_project_local(self) -> None:
        project = PROJECT_ROOT

        self.assertEqual(web.PROJECT, project)
        self.assertEqual(web.INPUT, project / "input")
        self.assertEqual(web.OUTPUT, project / "output")
        self.assertEqual(web.WEB, project / "web")
        self.assertEqual(web.DATABASE, project / "output" / "reports" / "audioextender.sqlite3")
        self.assertEqual(web_runtime.repository.path, web.DATABASE)
        self.assertIs(web_runtime.service.repository, web_runtime.repository)
        self.assertEqual(web_runtime.service.project, project)

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
        self.assertEqual(missing.json()["detail"], "Not Found")
        self.assertEqual(missing.json()["error"]["code"], "not_found")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(set(invalid.json()), {"detail", "error"})
        self.assertEqual(invalid.json()["error"]["category"], "validation")
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
            web_runtime.library_status_cache.update(payload=None, expires_at=0.0)
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
            patch.object(type(web_runtime.intention_planner), "status", return_value=status),
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
