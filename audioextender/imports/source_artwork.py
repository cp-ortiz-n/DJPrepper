"""Provider-independent artwork resolution for imports and catalog repairs."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse


class SourceMetadataProvider(Protocol):
    """Metadata lookups required to recover provider-native artwork."""

    def spotify_metadata(self, url: str) -> dict: ...

    def soundcloud_metadata(self, url: str) -> dict: ...


@dataclass(frozen=True)
class ArtworkCandidate:
    """One ordered artwork URL and the evidence that produced it."""

    url: str
    source: str


@dataclass(frozen=True)
class ArtworkSyncResult:
    """Artwork that was successfully cached and embedded."""

    url: str
    path: str
    source: str


@dataclass(frozen=True)
class SourceArtworkService:
    """Resolve, prioritize, cache, and embed artwork from supported providers."""

    metadata: SourceMetadataProvider
    cache_artwork: Callable[[str, Path], str]

    def sync_import(
        self,
        *,
        source_url: str,
        destination: Path,
        spotify_uri: str = "",
        supplied_url: str = "",
        provider_info: Mapping[str, Any] | None = None,
    ) -> ArtworkSyncResult | None:
        candidates = self.import_candidates(
            source_url=source_url,
            spotify_uri=spotify_uri,
            supplied_url=supplied_url,
            provider_info=provider_info or {},
        )
        return self._cache_first(candidates, destination)

    def sync_track(self, track: Mapping[str, Any], destination: Path) -> ArtworkSyncResult | None:
        return self._cache_first(self.track_candidates(track), destination)

    def import_candidates(
        self,
        *,
        source_url: str,
        spotify_uri: str = "",
        supplied_url: str = "",
        provider_info: Mapping[str, Any] | None = None,
    ) -> tuple[ArtworkCandidate, ...]:
        candidates: list[ArtworkCandidate] = []
        self._add(candidates, self._spotify_artwork(spotify_uri), "spotify")
        provider = self._provider(source_url)
        if provider == "soundcloud":
            self._add(candidates, supplied_url, "soundcloud")
            if not supplied_url:
                self._add(candidates, self._soundcloud_artwork(source_url), "soundcloud")
        elif provider == "youtube":
            self._add(candidates, supplied_url, "matched-source")
            self._add_youtube_info(candidates, provider_info or {})
            self._add(candidates, self._youtube_artwork(source_url=source_url), "youtube")
        else:
            self._add(candidates, supplied_url, "supplied")
        return tuple(candidates)

    def track_candidates(self, track: Mapping[str, Any]) -> tuple[ArtworkCandidate, ...]:
        candidates: list[ArtworkCandidate] = []
        spotify_uri = str(track.get("spotify_uri") or "")
        source_url = str(track.get("youtube_url") or "")
        self._add(candidates, self._spotify_artwork(spotify_uri), "spotify")
        self._add(candidates, str(track.get("artwork_url") or ""), "stored")
        provider = self._provider(source_url)
        if provider == "soundcloud":
            self._add(candidates, self._soundcloud_artwork(source_url), "soundcloud")
        elif provider != "soundcloud":
            self._add(
                candidates,
                self._youtube_artwork(source_url=source_url, source_id=str(track.get("youtube_id") or "")),
                "youtube",
            )
        return tuple(candidates)

    def _cache_first(
        self,
        candidates: tuple[ArtworkCandidate, ...],
        destination: Path,
    ) -> ArtworkSyncResult | None:
        for candidate in candidates:
            try:
                path = self.cache_artwork(candidate.url, destination)
            except Exception:
                path = ""
            if path:
                return ArtworkSyncResult(candidate.url, path, candidate.source)
        return None

    def _spotify_artwork(self, spotify_uri: str) -> str:
        if not spotify_uri.startswith("spotify:track:"):
            return ""
        try:
            metadata = self.metadata.spotify_metadata(
                "https://open.spotify.com/track/" + spotify_uri.rsplit(":", 1)[-1]
            )
            return str(metadata.get("thumbnail_url") or "")
        except Exception:
            return ""

    def _soundcloud_artwork(self, source_url: str) -> str:
        try:
            return str(self.metadata.soundcloud_metadata(source_url).get("thumbnail_url") or "")
        except Exception:
            return ""

    @staticmethod
    def _provider(source_url: str) -> str:
        host = (urlparse(source_url).hostname or "").casefold()
        if host == "youtu.be" or host.endswith(".youtube.com") or host == "youtube.com":
            return "youtube"
        if host == "soundcloud.com" or host.endswith(".soundcloud.com"):
            return "soundcloud"
        return ""

    @staticmethod
    def _youtube_artwork(*, source_url: str, source_id: str = "") -> str:
        video_id = source_id if re.fullmatch(r"[A-Za-z0-9_-]{6,}", source_id) else ""
        parsed = urlparse(source_url)
        if not video_id and (parsed.hostname or "").casefold() == "youtu.be":
            video_id = parsed.path.strip("/").split("/", 1)[0]
        if not video_id:
            video_id = str(parse_qs(parsed.query).get("v", [""])[0])
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
            return ""
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    @classmethod
    def _add_youtube_info(cls, candidates: list[ArtworkCandidate], info: Mapping[str, Any]) -> None:
        cls._add(candidates, str(info.get("thumbnail") or ""), "youtube")
        thumbnails = info.get("thumbnails") or []
        if not isinstance(thumbnails, list):
            return
        ordered = sorted(
            (item for item in thumbnails if isinstance(item, Mapping)),
            key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0),
            reverse=True,
        )
        for item in ordered:
            cls._add(candidates, str(item.get("url") or ""), "youtube")

    @staticmethod
    def _add(candidates: list[ArtworkCandidate], url: str, source: str) -> None:
        normalized = url.strip()
        if normalized and all(candidate.url != normalized for candidate in candidates):
            candidates.append(ArtworkCandidate(normalized, source))
