"""Authorized YouTube and SoundCloud import lifecycle.

The service owns transient import state and the download worker.  Web routing is
kept in ``import_routes`` so imports can be exercised without loading the full
application module.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from audioextender.infrastructure.operation_lifecycle import AUTHORIZED_IMPORTS, LifecycleProjection


class AuthorizedImport(Protocol):
    url: str
    rights_basis: Any
    confirmation: bool
    process_with_extender: bool
    title: str
    artist: str
    spotify_uri: str
    artwork_url: str


class ImportServiceError(RuntimeError):
    """Base error surfaced by the authorized import API."""


class ImportNotFoundError(ImportServiceError):
    """Raised when an import identifier is unknown."""


class LibraryOfflineError(ImportServiceError):
    """Raised when the configured library root is unavailable."""


def authorized_source_provider(url: str) -> str | None:
    """Return the supported downloadable provider for an authorized URL."""
    host = (urlparse(url).hostname or "").casefold()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return "youtube"
    if host in {
        "soundcloud.com",
        "www.soundcloud.com",
        "m.soundcloud.com",
        "on.soundcloud.com",
    }:
        return "soundcloud"
    return None


def scdl_executable() -> str:
    """Locate scdl beside the running Python interpreter or on PATH."""
    adjacent = Path(sys.executable).with_name("scdl")
    executable = str(adjacent) if adjacent.is_file() else shutil.which("scdl")
    if not executable:
        raise RuntimeError("scdl is not installed. Run pip install -r requirements.txt.")
    return executable


def scdl_download_command(url: str, destination: Path) -> list[str]:
    """Build the constrained single-track/mix scdl invocation used by imports."""
    return [
        scdl_executable(),
        "-l",
        url,
        "--path",
        str(destination),
        "--no-playlist",
        "--original-art",
        "--hide-progress",
        "--overwrite",
    ]


class ImportService:
    """Run and track individual authorized audio imports."""

    def __init__(
        self,
        *,
        repository: Any,
        processing_service: Any,
        library_root: Callable[[], Path],
        effective_settings: Callable[[], dict[str, Any]],
        preset_snapshot: Callable[[str], dict[str, Any]],
        duplicate_lookup: Callable[[str], dict[str, Any] | None],
        probe_audio: Callable[[Path], dict[str, Any]],
        cache_artwork: Callable[[str, Path], str],
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._repository = repository
        self._processing_service = processing_service
        self._library_root = library_root
        self._effective_settings = effective_settings
        self._preset_snapshot = preset_snapshot
        self._duplicate_lookup = duplicate_lookup
        self._probe_audio = probe_audio
        self._cache_artwork = cache_artwork
        self._thread_factory = thread_factory
        self._states: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def require_library_online(self) -> Path:
        """Resolve the configured root without ever creating a missing mount path."""
        root = self._library_root()
        if not root.is_dir():
            raise LibraryOfflineError("Music library is offline. Connect the configured drive before importing audio.")
        return root

    def start(self, request: AuthorizedImport) -> str:
        provider = authorized_source_provider(request.url)
        if provider is None:
            raise ValueError("Only YouTube and SoundCloud URLs are supported in this importer")
        if not request.confirmation:
            raise ValueError("Confirm that you have permission to download this audio")
        self.require_library_online()
        import_id = uuid.uuid4().hex
        with self._lock:
            self._cancel_events[import_id] = threading.Event()
            self._states[import_id] = {
                "id": import_id,
                "status": "processing",
                "stage": "Preparing authorized import",
                "progress": 0,
                "rights_basis": request.rights_basis,
                "source_provider": provider,
            }
        self._thread_factory(
            target=self.run,
            args=(import_id, request),
            daemon=True,
            name=f"authorized-import-{import_id[:8]}",
        ).start()
        return import_id

    def cancel(self, import_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._states.get(import_id)
            cancel_event = self._cancel_events.get(import_id)
            if state is None or cancel_event is None:
                raise ImportNotFoundError("Import not found")
            if state.get("status") != "processing":
                return {"canceled": False, "status": state.get("status")}
            cancel_event.set()
            state.update(stage="Canceling import")
        return {"canceled": True, "status": "canceling"}

    def status(self, import_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._states.get(import_id)
            if state is None:
                raise ImportNotFoundError("Import not found")
            return {key: value for key, value in state.items() if key != "file_path"}

    def lifecycle_status(self, import_id: str) -> LifecycleProjection:
        return AUTHORIZED_IMPORTS.project(self.status(import_id))

    def download_path(self, import_id: str) -> Path:
        with self._lock:
            state = self._states.get(import_id)
            path = Path(state["file_path"]) if state and state.get("file_path") else None
        if path is None or not path.is_file():
            raise ImportNotFoundError("Imported WAV is not available")
        return path

    def has_active_imports(self) -> bool:
        with self._lock:
            return any(state.get("status") == "processing" for state in self._states.values())

    def clear(self) -> None:
        with self._lock:
            self._states.clear()
            self._cancel_events.clear()

    def _update(self, import_id: str, **values: Any) -> None:
        with self._lock:
            self._states[import_id].update(values)

    def run(self, import_id: str, request: AuthorizedImport) -> None:
        """Execute one import. Public for deterministic worker tests."""
        try:
            cancel_event = self._cancel_events[import_id]
            provider = authorized_source_provider(request.url)
            if provider is None:
                raise RuntimeError("Unsupported authorized audio source")
            # Fail before network work when the external drive is disconnected.
            library_root = self.require_library_online()
            if provider == "youtube":
                try:
                    import yt_dlp
                except ImportError as error:
                    raise RuntimeError("yt-dlp is not installed. Run pip install -r requirements.txt.") from error
            with tempfile.TemporaryDirectory(prefix="audioextender-import-") as temporary:
                temporary_path = Path(temporary)
                template = str(temporary_path / "%(title).180B.%(ext)s")

                def progress(update: dict[str, Any]) -> None:
                    if cancel_event.is_set():
                        raise RuntimeError("Import canceled")
                    if update.get("status") != "downloading":
                        return
                    total = update.get("total_bytes") or update.get("total_bytes_estimate")
                    downloaded = update.get("downloaded_bytes") or 0
                    percent = round(100 * downloaded / total, 1) if total else 0
                    self._update(
                        import_id,
                        stage="Downloading authorized audio",
                        progress=percent,
                    )

                if provider == "soundcloud":
                    self._update(
                        import_id,
                        stage="Downloading from SoundCloud with scdl",
                        progress=15,
                    )
                    process = subprocess.Popen(
                        scdl_download_command(request.url, temporary_path),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    while process.poll() is None:
                        if cancel_event.wait(0.2):
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            raise RuntimeError("Import canceled")
                    stdout, stderr = process.communicate()
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
                    extensions = {
                        ".mp3",
                        ".m4a",
                        ".aac",
                        ".opus",
                        ".ogg",
                        ".flac",
                        ".wav",
                        ".aif",
                        ".aiff",
                    }
                    downloaded_audio = next(
                        (
                            path
                            for path in temporary_path.rglob("*")
                            if path.is_file() and path.suffix.casefold() in extensions
                        ),
                        None,
                    )
                    if downloaded_audio is None:
                        detail = (stderr or stdout or "").strip()
                        raise RuntimeError(detail[-1000:] or "scdl did not produce an audio file")
                    source_metadata = self._probe_audio(downloaded_audio)
                    converted = temporary_path / "soundcloud-import.wav"
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-v",
                            "error",
                            "-i",
                            str(downloaded_audio),
                            "-vn",
                            "-c:a",
                            "pcm_s24le",
                            str(converted),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    info = {
                        "id": hashlib.sha256(request.url.encode()).hexdigest()[:24],
                        "title": source_metadata["title"],
                        "artist": source_metadata["artist"],
                        "uploader": source_metadata["artist"],
                        "duration": source_metadata["duration"],
                        "thumbnail": request.artwork_url,
                    }
                    wavs = [converted]
                    self._update(
                        import_id,
                        stage="SoundCloud audio converted to WAV",
                        progress=75,
                    )
                else:
                    options = {
                        "format": "bestaudio/best",
                        "outtmpl": template,
                        "noplaylist": True,
                        "restrictfilenames": True,
                        "progress_hooks": [progress],
                        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
                        "quiet": True,
                        "no_warnings": True,
                    }
                    with yt_dlp.YoutubeDL(options) as downloader:
                        info = downloader.extract_info(request.url, download=True)
                    wavs = list(temporary_path.glob("*.wav"))
                if not wavs:
                    raise RuntimeError("The authorized source could not be converted to WAV")
                if cancel_event.is_set():
                    raise RuntimeError("Import canceled")
                title = str(request.title or info.get("title") or wavs[0].stem).strip()
                title = title or "Imported Audio"
                safe_name = (
                    "".join(character for character in title if character not in '<>:"/\\|?*').strip()[:180]
                    or "Imported Audio"
                )
                raw_source_id = str(info.get("id") or "").strip()
                catalog_source_id = raw_source_id if provider == "youtube" else f"{provider}:{raw_source_id}"
                existing_download = self._duplicate_lookup(catalog_source_id)
                # Revalidate immediately before writing. Never mkdir the configured
                # root, because doing so can silently recreate a missing mountpoint.
                if not library_root.is_dir() or self.require_library_online() != library_root:
                    raise LibraryOfflineError("Music library disconnected before the import could be saved.")
                destination_dir = library_root / "Other"
                destination_dir.mkdir(parents=True, exist_ok=True)
                if existing_download:
                    destination = Path(existing_download["file_path"])
                else:
                    destination = destination_dir / f"{safe_name}.wav"
                    counter = 2
                    while destination.exists():
                        destination = destination_dir / f"{safe_name} ({counter}).wav"
                        counter += 1
                    shutil.move(str(wavs[0]), destination)
            artist = str(request.artist or info.get("artist") or info.get("uploader") or "").strip()
            artwork_url = str(request.artwork_url or info.get("thumbnail") or "")
            artwork_path = self._cache_artwork(artwork_url, destination)
            self._repository.upsert_downloaded_track(
                title=title,
                artist=artist,
                file_path=destination,
                youtube_id=catalog_source_id,
                youtube_url=request.url,
                spotify_uri=request.spotify_uri,
                artwork_url=artwork_url,
                artwork_path=artwork_path,
                duration_seconds=float(info.get("duration") or 0) or None,
                playlist_name=("SoundCloud Imports" if provider == "soundcloud" else "Imported Singles"),
            )
            if not request.process_with_extender:
                self._update(
                    import_id,
                    status="complete",
                    stage="WAV import complete",
                    progress=100,
                    filename=destination.name,
                    file_path=str(destination),
                    processed_with_extender=False,
                )
                return
            effective = self._effective_settings()
            preset = str(effective["preset"])
            job_id = self._repository.create(
                destination.name,
                destination,
                preset,
                int(effective["intro_bars"]),
                int(effective["outro_bars"]),
                bool(effective["use_stems"]),
                {
                    **effective,
                    **self._preset_snapshot(preset),
                    "authorized_source_url": request.url,
                    "rights_basis": request.rights_basis,
                    "intro_bars_auto": True,
                    "outro_bars_auto": True,
                },
            )
            self._processing_service.enqueue(job_id)
            self._update(
                import_id,
                status="complete",
                stage="Imported and added to processing queue",
                progress=100,
                job_id=job_id,
                filename=destination.name,
                file_path=str(destination),
                processed_with_extender=True,
            )
        except Exception as error:
            message = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                detail = str(error.stderr or error.stdout or "").strip()
                if detail:
                    message = detail[-1500:]
            with self._lock:
                final_cancel_event = self._cancel_events.get(import_id)
                canceled = bool(final_cancel_event and final_cancel_event.is_set())
                self._states[import_id].update(
                    status="canceled" if canceled else "failed",
                    stage="Import canceled" if canceled else "Import failed",
                    error="Canceled by user" if canceled else message,
                )
