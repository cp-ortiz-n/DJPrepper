"""Version and render the browser shell from one frontend asset manifest."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

_REVISION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_REVISION_TOKEN = "__DJLS_ASSET_REVISION__"
_STYLESHEET_TOKEN = "__DJLS_STYLESHEET_URL__"
_IMPORT_MAP_TOKEN = "__DJLS_IMPORT_MAP__"
_ENTRYPOINT_TOKEN = "__DJLS_ENTRYPOINT_URL__"


@dataclass(frozen=True)
class FrontendAssetManifest:
    """Validated names and shared revision for one frontend release."""

    revision: str
    entrypoint: str
    stylesheet: str

    @classmethod
    def load(cls, path: Path) -> FrontendAssetManifest:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load frontend asset manifest: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Frontend asset manifest must contain a JSON object")
        revision = str(payload.get("revision", "")).strip()
        if not _REVISION_PATTERN.fullmatch(revision):
            raise ValueError("Frontend asset revision may contain only letters, numbers, '.', '_', and '-'")
        return cls(
            revision=revision,
            entrypoint=cls._asset_name(payload.get("entrypoint"), ".js"),
            stylesheet=cls._asset_name(payload.get("stylesheet"), ".css"),
        )

    @staticmethod
    def _asset_name(value: object, suffix: str) -> str:
        name = str(value or "").strip()
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or path.suffix != suffix:
            raise ValueError(f"Frontend asset must be a relative {suffix} path")
        return path.as_posix()

    def url(self, asset: str) -> str:
        return f"/assets/{quote(asset, safe='/')}?v={quote(self.revision)}"


@dataclass(frozen=True)
class RenderedFrontendShell:
    html: str
    revision: str


class FrontendAssetService:
    """Render a coherent, versioned ES-module graph for the browser."""

    def __init__(self, web_root: Path) -> None:
        self.web_root = web_root

    def render_index(self) -> RenderedFrontendShell:
        manifest = FrontendAssetManifest.load(self.web_root / "asset-manifest.json")
        self._require_asset(manifest.entrypoint)
        self._require_asset(manifest.stylesheet)
        template = (self.web_root / "index.html").read_text(encoding="utf-8")
        imports = {
            f"/assets/{path.relative_to(self.web_root).as_posix()}": manifest.url(
                path.relative_to(self.web_root).as_posix()
            )
            for path in sorted(self.web_root.rglob("*.js"))
            if path.is_file()
        }
        import_map = json.dumps({"imports": imports}, separators=(",", ":")).replace("<", "\\u003c")
        replacements = {
            _REVISION_TOKEN: manifest.revision,
            _STYLESHEET_TOKEN: manifest.url(manifest.stylesheet),
            _IMPORT_MAP_TOKEN: import_map,
            _ENTRYPOINT_TOKEN: manifest.url(manifest.entrypoint),
        }
        for token, value in replacements.items():
            if template.count(token) != 1:
                raise ValueError(f"Frontend shell must contain exactly one {token} placeholder")
            template = template.replace(token, value)
        return RenderedFrontendShell(template, manifest.revision)

    def _require_asset(self, relative_path: str) -> None:
        if not (self.web_root / relative_path).is_file():
            raise ValueError(f"Frontend asset does not exist: {relative_path}")
