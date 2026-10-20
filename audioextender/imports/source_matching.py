"""Metadata lookup and conservative YouTube matching for import sources."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx


class SourceMatchError(RuntimeError):
    """A source could not be validated or queried."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def match_tokens(value: object) -> set[str]:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode().casefold()
    return set(re.findall(r"[a-z0-9]+", ascii_text))


def best_youtube_match(track: dict, entries: Iterable[dict]) -> tuple[dict, int, list[str]]:
    """Return the safest title/artist/duration match from search results."""
    expected_title = match_tokens(track.get("title"))
    expected_artist = match_tokens(track.get("artist"))
    expected_duration = float(track.get("duration_ms") or 0) / 1000
    expected_all = expected_title | expected_artist
    version_tokens = {"remix", "edit", "rework", "mix", "version", "extended", "original"}
    unwanted = {
        "tutorial",
        "reaction",
        "karaoke",
        "cover",
        "compilation",
        "playlist",
        "slowed",
        "sped",
        "hour",
        "hours",
    }
    best: tuple[float, dict, list[str]] | None = None
    for entry in entries:
        candidate_title = match_tokens(entry.get("title"))
        candidate_context = candidate_title | match_tokens(entry.get("channel")) | match_tokens(entry.get("uploader"))
        title_coverage = len(expected_title & candidate_title) / max(1, len(expected_title))
        artist_coverage = len(expected_artist & candidate_context) / len(expected_artist) if expected_artist else 1.0
        extra_bad = (unwanted & candidate_title) - expected_all
        expected_versions = expected_title & version_tokens
        candidate_versions = candidate_title & version_tokens
        version_mismatch = bool(candidate_versions - expected_versions)
        duration = float(entry.get("duration") or 0)
        duration_difference = abs(duration - expected_duration) if duration and expected_duration else 0
        duration_tolerance = max(15.0, expected_duration * 0.12)
        duration_score = (
            max(0.0, 1.0 - duration_difference / max(duration_tolerance, 1.0))
            if duration and expected_duration
            else 0.35
        )
        warnings: list[str] = []
        if title_coverage < 0.7:
            warnings.append("title mismatch")
        if expected_artist and artist_coverage < 0.5:
            warnings.append("artist mismatch")
        if extra_bad:
            warnings.append("non-track upload: " + ", ".join(sorted(extra_bad)))
        if version_mismatch:
            warnings.append("version or remix mismatch")
        if duration and expected_duration and duration_difference > duration_tolerance:
            warnings.append(f"duration differs by {round(duration_difference)}s")
        score = 100 * (0.48 * title_coverage + 0.27 * artist_coverage + 0.25 * duration_score)
        score -= 30 * bool(extra_bad)
        score -= 22 * version_mismatch
        if warnings:
            score -= 8 * len(warnings)
        if best is None or score > best[0]:
            best = (score, entry, warnings)
    if best is None:
        return {}, 0, ["no YouTube results"]
    score, entry, warnings = best
    if score < 48 or "title mismatch" in warnings or "artist mismatch" in warnings:
        return {}, max(0, round(score)), warnings + ["no reliable match selected"]
    if any(warning.startswith("duration differs") for warning in warnings):
        return {}, max(0, round(score)), warnings + ["no reliable match selected"]
    return entry, min(100, max(0, round(score))), warnings


@dataclass(frozen=True)
class SourceMatchingService:
    """Resolve provider metadata and rank catalog-safe YouTube matches."""

    http_get: Callable[..., Any] = httpx.get

    def match(self, url: str) -> dict:
        host = (urlparse(url).hostname or "").casefold()
        if host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}:
            return self.soundcloud_metadata(url)
        if host not in {"open.spotify.com", "www.open.spotify.com"}:
            raise SourceMatchError(400, "Source matching accepts Spotify or SoundCloud track links")
        metadata = self.spotify_metadata(url)
        entries = self._youtube_search(" - ".join(part for part in (metadata["artist"], metadata["title"]) if part))
        match, score, warnings = best_youtube_match(metadata, entries)
        video_id = str(match.get("id") or "")
        if not metadata["artist"] and match:
            metadata["artist"] = str(match.get("channel") or match.get("uploader") or "").strip()
        return {
            **metadata,
            "youtube_title": match.get("title"),
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
            "youtube_duration": match.get("duration"),
            "match_score": score,
            "match_warnings": warnings,
        }

    def match_tracks(self, tracks: list[dict], progress: Callable[..., None]) -> list[dict]:
        """Match a playlist while reporting deterministic progress."""
        try:
            import yt_dlp
        except ImportError as error:
            raise SourceMatchError(500, "yt-dlp is not installed") from error
        results: list[dict] = []
        with yt_dlp.YoutubeDL(self._youtube_options()) as searcher:
            for index, track in enumerate(tracks, start=1):
                spotify_uri = str(track.get("spotify_uri") or "")
                if spotify_uri.startswith("spotify:track:"):
                    try:
                        metadata = self.spotify_metadata(
                            "https://open.spotify.com/track/" + spotify_uri.rsplit(":", 1)[-1]
                        )
                        track["artwork_url"] = metadata.get("thumbnail_url", "")
                    except SourceMatchError:
                        track["artwork_url"] = ""
                info = (
                    searcher.extract_info(
                        f"ytsearch8:{track['artist']} - {track['title']}",
                        download=False,
                    )
                    or {}
                )
                match, score, warnings = best_youtube_match(track, info.get("entries") or [])
                video_id = str(match.get("id") or "")
                results.append(
                    {
                        **track,
                        "youtube_title": match.get("title"),
                        "youtube_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                        "youtube_duration": match.get("duration"),
                        "match_score": score,
                        "match_warnings": warnings,
                    }
                )
                progress(
                    stage=f"Matching {index} of {len(tracks)}",
                    progress=round(index * 100 / len(tracks), 1),
                    matched=index,
                    total=len(tracks),
                )
        return results

    def spotify_metadata(self, url: str) -> dict:
        track_id_match = re.search(r"open\.spotify\.com/track/([A-Za-z0-9]+)", url)
        if not track_id_match:
            raise SourceMatchError(400, "Paste a Spotify track link, not an album or playlist link")
        endpoint = "https://open.spotify.com/oembed?" + urlencode({"url": url})
        try:
            response = self.http_get(
                endpoint,
                headers={"User-Agent": "DJ-Library-Studio/1.0"},
                timeout=12,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise SourceMatchError(502, "Spotify metadata could not be loaded") from error
        raw_title = str(payload.get("title") or "").strip()
        title = raw_title
        artist = str(payload.get("author_name") or "").strip()
        for pattern in (r"^(.+?)\s+[–-]\s+song and lyrics by\s+(.+)$", r"^(.+?)\s+by\s+(.+)$"):
            matched = re.match(pattern, raw_title, flags=re.IGNORECASE)
            if matched:
                title, artist = matched.group(1).strip(), matched.group(2).strip()
                break
        return {
            "title": title or "Spotify track",
            "artist": artist,
            "spotify_uri": f"spotify:track:{track_id_match.group(1)}",
            "spotify_url": url,
            "thumbnail_url": str(payload.get("thumbnail_url") or ""),
        }

    def soundcloud_metadata(self, url: str) -> dict:
        try:
            response = self.http_get(
                "https://soundcloud.com/oembed",
                params={"format": "json", "url": url},
                headers={"User-Agent": "DJ-Library-Studio/1.0"},
                timeout=12,
                follow_redirects=True,
            )
            response.raise_for_status()
            info = response.json()
        except Exception as error:
            raise SourceMatchError(502, "SoundCloud metadata could not be loaded") from error
        return {
            "source_type": "soundcloud",
            "title": str(info.get("title") or "SoundCloud track").strip(),
            "artist": str(info.get("author_name") or "").strip(),
            "thumbnail_url": str(info.get("thumbnail_url") or ""),
            "duration": None,
            "soundcloud_url": url,
        }

    @staticmethod
    def _youtube_search(query: str) -> list[dict]:
        try:
            import yt_dlp
        except ImportError as error:
            raise SourceMatchError(500, "yt-dlp is not installed") from error
        with yt_dlp.YoutubeDL(SourceMatchingService._youtube_options()) as searcher:
            info = searcher.extract_info(f"ytsearch8:{query}", download=False) or {}
        return list(info.get("entries") or [])

    @staticmethod
    def _youtube_options() -> dict[str, Any]:
        return {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": 8,
        }
