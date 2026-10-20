#!/usr/bin/env python3
"""Serve an isolated application instance for browser smoke tests."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from audioextender.web.application import create_app
from audioextender.web.composition import ApplicationPaths


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="audioextender-browser-smoke-") as temporary:
        project = Path(temporary)
        source_project = Path(__file__).resolve().parents[2]
        (project / "node_modules").symlink_to(source_project / "node_modules", target_is_directory=True)
        frontend_root = source_project / "frontend"
        revision_override = os.getenv("AUDIOEXTENDER_BROWSER_SMOKE_ASSET_REVISION", "").strip()
        if revision_override:
            frontend_root = project / "frontend"
            shutil.copytree(source_project / "frontend", frontend_root)
            manifest_path = frontend_root / "asset-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["revision"] = revision_override
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        library = project / "External Drive" / "AudioExtenderLibrary"
        library.mkdir(parents=True)
        paths = ApplicationPaths.from_project(
            project,
            frontend_root=frontend_root,
            default_music_library=library,
        )
        application = create_app(paths=paths)
        asset_cache_control = os.getenv("AUDIOEXTENDER_BROWSER_SMOKE_ASSET_CACHE_CONTROL", "").strip()
        if asset_cache_control:

            @application.middleware("http")
            async def override_asset_cache_control(request, call_next):
                response = await call_next(request)
                if request.url.path.startswith("/assets/"):
                    response.headers["Cache-Control"] = asset_cache_control
                return response

        port = int(os.getenv("AUDIOEXTENDER_BROWSER_SMOKE_PORT", "4173"))
        uvicorn.run(application, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
