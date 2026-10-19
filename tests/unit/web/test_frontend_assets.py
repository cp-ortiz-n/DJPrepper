"""Focused contracts for coherent frontend asset delivery."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from audioextender.web.frontend_assets import FrontendAssetManifest, FrontendAssetService


class FrontendAssetTests(unittest.TestCase):
    def test_manifest_rejects_invalid_revisions_and_unsafe_asset_paths(self) -> None:
        invalid_payloads = (
            {"revision": "bad revision", "entrypoint": "app.js", "stylesheet": "styles.css"},
            {"revision": "release-1", "entrypoint": "../app.js", "stylesheet": "styles.css"},
            {"revision": "release-1", "entrypoint": "app.js", "stylesheet": "/styles.css"},
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "asset-manifest.json"
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        FrontendAssetManifest.load(manifest_path)

    def test_renderer_requires_every_shell_placeholder_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            web_root = Path(temporary)
            (web_root / "asset-manifest.json").write_text(
                json.dumps({"revision": "release-1", "entrypoint": "app.js", "stylesheet": "styles.css"}),
                encoding="utf-8",
            )
            (web_root / "app.js").write_text("export {};\n", encoding="utf-8")
            (web_root / "styles.css").write_text("body {}\n", encoding="utf-8")
            (web_root / "index.html").write_text("<html>missing placeholders</html>\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "placeholder"):
                FrontendAssetService(web_root).render_index()


if __name__ == "__main__":
    unittest.main()
