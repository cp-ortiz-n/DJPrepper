#!/usr/bin/env python3
"""Serve an isolated application instance for browser smoke tests."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audioextender.web.application import create_app
from audioextender.web.composition import ApplicationPaths


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="audioextender-browser-smoke-") as temporary:
        project = Path(temporary)
        source_project = Path(__file__).resolve().parents[1]
        (project / "node_modules").symlink_to(source_project / "node_modules", target_is_directory=True)
        library = project / "External Drive" / "AudioExtenderLibrary"
        library.mkdir(parents=True)
        paths = ApplicationPaths.from_project(
            project,
            web_root=source_project / "web",
            default_music_library=library,
        )
        uvicorn.run(create_app(paths=paths), host="127.0.0.1", port=4173, log_level="warning")


if __name__ == "__main__":
    main()
