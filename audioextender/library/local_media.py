"""Local media probing, source sidecars, and artwork caching."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class LocalMediaService:
    """Own filesystem-adjacent metadata operations for catalog media."""

    music_library_root: Callable[[], Path]
    require_library_online: Callable[[], Path]
    embed_artwork: Callable[[Path, Path, str], Any]
    http_get: Callable[..., Any] = httpx.get

    def source_metadata_path(self, audio_path: Path) -> Path:
        key = hashlib.sha256(str(audio_path.resolve()).encode("utf-8")).hexdigest()
        return self.music_library_root() / ".audioextender" / "sources" / f"{key}.json"

    def write_source_metadata(self, audio_path: Path, metadata: dict) -> Path:
        destination = self.source_metadata_path(audio_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({**metadata, "file_path": str(audio_path.resolve())}, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    def cache_artwork(self, artwork_url: str, destination: Path) -> str:
        """Cache trusted provider artwork and embed it in a WAV when possible."""
        if not artwork_url:
            return ""
        artwork_host = (urlparse(artwork_url).hostname or "").casefold()
        trusted = (
            artwork_host == "i.ytimg.com"
            or artwork_host.endswith(".spotifycdn.com")
            or artwork_host.endswith(".scdn.co")
            or artwork_host.endswith(".sndcdn.com")
        )
        if not trusted:
            return ""
        try:
            response = self.http_get(artwork_url, timeout=15, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
            if content_type not in {"image/jpeg", "image/png"} or len(response.content) > 8_000_000:
                return ""
            artwork_dir = self.require_library_online() / ".artwork"
            artwork_dir.mkdir(parents=True, exist_ok=True)
            suffix = ".png" if content_type == "image/png" else ".jpg"
            artwork_file = artwork_dir / f"{hashlib.sha256(artwork_url.encode()).hexdigest()[:24]}{suffix}"
            artwork_file.write_bytes(response.content)
            self.embed_artwork(destination, artwork_file, content_type)
            return str(artwork_file)
        except Exception:
            return ""

    @staticmethod
    def probe(path: Path) -> dict:
        """Read common file tags without decoding the complete recording."""
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:format_tags",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout or "{}")
        format_data = payload.get("format") or {}
        tags = {str(key).casefold(): str(value).strip() for key, value in (format_data.get("tags") or {}).items()}
        stem = path.stem
        pieces = [piece.strip() for piece in stem.split(" - ", 1)]
        artist = tags.get("artist", "") or (pieces[0] if len(pieces) == 2 else "")
        title = tags.get("title", "") or (pieces[1] if len(pieces) == 2 else stem)
        genre = tags.get("genre", "")
        try:
            duration = float(format_data.get("duration") or 0) or None
        except (TypeError, ValueError):
            duration = None
        return {"title": title, "artist": artist, "genre": genre, "duration": duration}
