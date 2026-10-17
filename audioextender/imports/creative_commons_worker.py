"""Workers for Creative Commons imports and failed-source retries."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from audioextender.infrastructure.background_tasks import BackgroundTaskRegistry


class CreativeCommonsBatchWorker:
    """Execute batch downloads while the lifecycle service owns scheduling."""

    def __init__(
        self,
        *,
        registry: BackgroundTaskRegistry,
        repository: Any,
        output: Path,
        require_library_online: Callable[[], Path],
        safe_folder_name: Callable[[str], str],
        generalized_genre: Callable[[str], str],
        normalize_genre_category: Callable[[str], str],
        safe_audio_name: Callable[[str], str],
        duplicate_lookup: Callable[[str], dict[str, Any] | None],
        genre_path_parts: Callable[[str], Sequence[str]],
        source_metadata_path: Callable[[Path], Path],
        cache_track_artwork: Callable[[str, Path], str],
        write_wav_metadata: Callable[..., None],
        write_source_metadata: Callable[[Path, dict[str, Any]], Any],
        best_youtube_match: Callable[..., tuple[dict[str, Any], Any, Any]],
        spotify_source_metadata: Callable[[str], dict[str, Any]],
        original_import_metadata: Callable[[str, str, str], dict[str, str]],
        match_factory: Callable[..., Any],
    ) -> None:
        self._registry = registry
        self._repository = repository
        self._output = output
        self._require_library_online = require_library_online
        self._safe_folder_name = safe_folder_name
        self._generalized_genre = generalized_genre
        self._normalize_genre_category = normalize_genre_category
        self._safe_audio_name = safe_audio_name
        self._duplicate_lookup = duplicate_lookup
        self._genre_path_parts = genre_path_parts
        self._source_metadata_path = source_metadata_path
        self._cache_track_artwork = cache_track_artwork
        self._write_wav_metadata = write_wav_metadata
        self._write_source_metadata = write_source_metadata
        self._best_youtube_match = best_youtube_match
        self._spotify_source_metadata = spotify_source_metadata
        self._original_import_metadata = original_import_metadata
        self._match_factory = match_factory

    def run(self, batch_id: str, tracks: list[Any], playlist_name: str) -> None:
        report: dict[str, list[dict]] = {
            "downloaded": [],
            "already_downloaded": [],
            "skipped_not_creative_commons": [],
            "failed": [],
        }
        safe_playlist = self._safe_folder_name(playlist_name)
        try:
            destination_dir = self._require_library_online()
        except Exception as error:
            with self._registry.lock:
                self._registry[batch_id].update(status="failed", stage="Music library disconnected", error=str(error))
            return
        report_dir = self._output / "reports" / "imports" / safe_playlist
        destination_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        try:
            import yt_dlp

            for index, track in enumerate(tracks, start=1):
                base = track.model_dump()
                track_playlist = track.playlist_name or playlist_name
                try:
                    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as inspector:
                        info = inspector.extract_info(track.url, download=False) or {}
                    license_name = str(info.get("license") or "").strip()
                    video_id = str(info.get("id") or "").strip()
                    artwork_url = track.artwork_url or (
                        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""
                    )
                    base.update(license=license_name, youtube_id=video_id, artwork_url=artwork_url)
                    # if "creative commons" not in license_name.casefold():
                    #    report["skipped_not_creative_commons"].append(base)
                    # else:
                    category = (
                        self._generalized_genre(track.genre)
                        if track.genre
                        else self._normalize_genre_category(track.genre_category)
                    )
                    base.update(genre=track.genre, genre_category=category)
                    output_name = self._safe_audio_name(f"{track.artist} - {track.title}") + ".wav"
                    existing_download = self._duplicate_lookup(video_id)
                    if existing_download:
                        destination = Path(existing_download["file_path"])
                        category = str(existing_download.get("genre_category") or category)
                        base.update(
                            filename=destination.name,
                            genre_category=category,
                        )
                        report["already_downloaded"].append(base)
                    else:
                        category_dir = destination_dir.joinpath(*self._genre_path_parts(category))
                        category_dir.mkdir(parents=True, exist_ok=True)
                        destination = category_dir / output_name
                        source_record = self._source_metadata_path(destination)
                        recorded_video_id = ""
                        if source_record.exists():
                            try:
                                recorded_video_id = str(
                                    json.loads(source_record.read_text(encoding="utf-8")).get("youtube_id", "")
                                )
                            except (OSError, json.JSONDecodeError):
                                recorded_video_id = ""
                        if destination.exists() and recorded_video_id == video_id:
                            base["filename"] = output_name
                            report["already_downloaded"].append(base)
                            self._repository.upsert_downloaded_track(
                                title=track.title,
                                artist=track.artist,
                                file_path=destination,
                                genre=track.genre,
                                genre_category=category,
                                spotify_uri=track.spotify_uri,
                                youtube_id=video_id,
                                youtube_url=track.url,
                                duration_seconds=float(info.get("duration") or 0) or None,
                                artwork_url=artwork_url,
                                artwork_path=self._cache_track_artwork(artwork_url, destination),
                                playlist_name=track_playlist,
                            )
                            self._repository.resolve_import_failure(
                                playlist_name=track_playlist, title=track.title, artist=track.artist
                            )
                            continue
                        if destination.exists():
                            original_stem = destination.stem
                            copy_number = 2
                            while destination.exists():
                                destination = destination.with_name(
                                    f"{original_stem} ({copy_number}){destination.suffix}"
                                )
                                copy_number += 1
                            output_name = destination.name
                            source_record = self._source_metadata_path(destination)
                        with tempfile.TemporaryDirectory(prefix="audioextender-cc-import-") as temporary:
                            options = {
                                "format": "bestaudio/best",
                                "outtmpl": str(Path(temporary) / "source.%(ext)s"),
                                "noplaylist": True,
                                "quiet": True,
                                "no_warnings": True,
                                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
                            }
                            with yt_dlp.YoutubeDL(options) as downloader:
                                downloader.extract_info(track.url, download=True)
                            wavs = list(Path(temporary).glob("*.wav"))
                            if not wavs:
                                raise RuntimeError("YouTube audio could not be converted to WAV")
                            shutil.move(str(wavs[0]), destination)
                        self._write_wav_metadata(
                            destination,
                            title=track.title,
                            artist=track.artist,
                            genre=category,
                            album=track_playlist,
                        )
                        self._write_source_metadata(
                            destination,
                            {
                                "youtube_id": video_id,
                                "youtube_url": track.url,
                                "title": track.title,
                                "artist": track.artist,
                                "playlist_name": track_playlist,
                                "genre": track.genre,
                                "genre_category": category,
                                "artwork_url": artwork_url,
                            },
                        )
                        base["filename"] = output_name
                        report["downloaded"].append(base)
                    self._repository.upsert_downloaded_track(
                        title=track.title,
                        artist=track.artist,
                        file_path=destination,
                        genre=track.genre,
                        genre_category=category,
                        spotify_uri=track.spotify_uri,
                        youtube_id=video_id,
                        youtube_url=track.url,
                        duration_seconds=float(info.get("duration") or 0) or None,
                        artwork_url=artwork_url,
                        artwork_path=self._cache_track_artwork(artwork_url, destination),
                        playlist_name=track_playlist,
                    )
                    self._repository.resolve_import_failure(
                        playlist_name=track_playlist, title=track.title, artist=track.artist
                    )
                except Exception as error:
                    report["failed"].append({**base, "error": str(error)})
                    self._repository.record_import_failure(
                        playlist_name=track_playlist,
                        title=track.title,
                        artist=track.artist,
                        spotify_uri=track.spotify_uri,
                        youtube_url=track.url,
                        error=str(error),
                    )
                with self._registry.lock:
                    self._registry[batch_id].update(
                        stage=f"Verified {index} of {len(tracks)}",
                        progress=round(index * 100 / len(tracks), 1),
                        counts={key: len(value) for key, value in report.items()},
                    )
            included = report["downloaded"] + report["already_downloaded"]
            report_path = report_dir / f"{safe_playlist} - Import Report.json"
            genre_summary: dict[str, int] = {}
            for item in included:
                category = item.get("genre_category", "Other")
                genre_summary[category] = genre_summary.get(category, 0) + 1
            report_document = {
                "playlist_name": playlist_name,
                "export_folder": str(destination_dir),
                "genre_summary": dict(sorted(genre_summary.items())),
                "results": report,
            }
            report_path.write_text(json.dumps(report_document, indent=2), encoding="utf-8")
            with self._registry.lock:
                self._registry[batch_id].update(
                    status="complete",
                    stage="Download complete",
                    progress=100,
                    counts={key: len(value) for key, value in report.items()},
                    report=report,
                    genre_summary=dict(sorted(genre_summary.items())),
                    report_path=str(report_path),
                )
        except Exception as error:
            with self._registry.lock:
                self._registry[batch_id].update(status="failed", stage="Batch import failed", error=str(error))

    def retry(self, batch_id: str, failures: list[dict]) -> None:
        """Refresh failed source matches, then reuse the normal batch downloader."""
        try:
            import yt_dlp

            tracks: list[Any] = []
            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": True,
                "playlistend": 8,
                "socket_timeout": 15,
                "retries": 1,
                "extractor_retries": 1,
            }
            with yt_dlp.YoutubeDL(options) as searcher:
                for index, failure in enumerate(failures, start=1):
                    query = " - ".join(
                        part for part in (str(failure.get("artist") or ""), str(failure.get("title") or "")) if part
                    )
                    old_url = str(failure.get("youtube_url") or "")
                    old_id_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]+)", old_url)
                    old_id = old_id_match.group(1) if old_id_match else ""
                    info = searcher.extract_info(f"ytsearch8:{query}", download=False) or {}
                    entries = [entry for entry in (info.get("entries") or []) if str(entry.get("id") or "") != old_id]
                    match, _, _ = self._best_youtube_match(failure, entries)
                    video_id = str(match.get("id") or "")
                    source_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else old_url
                    if not source_url:
                        self._repository.record_import_failure(
                            playlist_name=str(failure.get("playlist_name") or "Imported Playlist"),
                            title=str(failure.get("title") or "Unknown track"),
                            artist=str(failure.get("artist") or ""),
                            spotify_uri=str(failure.get("spotify_uri") or ""),
                            youtube_url="",
                            error="No reliable replacement source was found",
                        )
                        continue
                    artwork_url = ""
                    spotify_uri = str(failure.get("spotify_uri") or "")
                    if spotify_uri.startswith("spotify:track:"):
                        try:
                            artwork_url = str(
                                self._spotify_source_metadata(
                                    "https://open.spotify.com/track/" + spotify_uri.rsplit(":", 1)[-1]
                                ).get("thumbnail_url")
                                or ""
                            )
                        except Exception:
                            pass
                    original_metadata = self._original_import_metadata(
                        str(failure.get("playlist_name") or "Imported Playlist"),
                        str(failure.get("title") or "Unknown track"),
                        str(failure.get("artist") or "Unknown artist"),
                    )
                    tracks.append(
                        self._match_factory(
                            url=source_url,
                            title=str(failure.get("title") or "Unknown track"),
                            artist=str(failure.get("artist") or "Unknown artist"),
                            spotify_uri=spotify_uri,
                            genre=original_metadata["genre"],
                            genre_category=original_metadata["genre_category"],
                            artwork_url=artwork_url,
                            playlist_name=str(failure.get("playlist_name") or "Imported Playlist"),
                        )
                    )
                    with self._registry.lock:
                        self._registry[batch_id].update(
                            stage=f"Refreshing sources {index} of {len(failures)}",
                            progress=round(index * 25 / max(1, len(failures)), 1),
                        )
            if not tracks:
                with self._registry.lock:
                    self._registry[batch_id].update(
                        status="complete",
                        stage="No retryable sources were found",
                        progress=100,
                        counts={"downloaded": 0, "already_downloaded": 0, "failed": len(failures)},
                    )
                return
            self.run(batch_id, tracks, "Retry imports")
        except Exception as error:
            with self._registry.lock:
                self._registry[batch_id].update(status="failed", stage="Retry preparation failed", error=str(error))
