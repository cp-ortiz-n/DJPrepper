"""Bounded background generation for cached artwork thumbnails."""

from __future__ import annotations

import hashlib
import queue
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


class ArtworkThumbnailService:
    """Own the thumbnail queue and its single FFmpeg worker."""

    def __init__(
        self,
        *,
        thumbnail_root: Callable[[], Path],
        record_cache_result: Callable[[str, bool], None],
        thread_factory: Callable[..., Any] = threading.Thread,
    ) -> None:
        self._thumbnail_root = thumbnail_root
        self._record_cache_result = record_cache_result
        self._thread_factory = thread_factory
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[Path, Path, int]] = queue.Queue()
        self._pending: set[Path] = set()
        self._worker_started = False

    def get_or_queue(self, source: Path, size: int = 96) -> Path:
        """Return a cached thumbnail or queue generation and return the source."""
        stat = source.stat()
        identity = f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{size}"
        thumbnail = self._thumbnail_root() / f"{hashlib.sha256(identity.encode()).hexdigest()[:24]}.jpg"
        if thumbnail.is_file():
            self._record_cache_result("artwork_thumbnail", True)
            return thumbnail
        with self._lock:
            if thumbnail.is_file():
                self._record_cache_result("artwork_thumbnail", True)
                return thumbnail
            self._record_cache_result("artwork_thumbnail", False)
            if thumbnail not in self._pending:
                self._pending.add(thumbnail)
                self._queue.put((source, thumbnail, size))
            if not self._worker_started:
                self._worker_started = True
                self._thread_factory(
                    target=self.run,
                    name="artwork-thumbnail-worker",
                    daemon=True,
                ).start()
        return source

    def run(self) -> None:
        """Generate queued thumbnails serially to avoid an FFmpeg stampede."""
        while True:
            source, thumbnail, size = self._queue.get()
            temporary = thumbnail.with_suffix(".pending.jpg")
            try:
                thumbnail.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(source),
                        "-vf",
                        f"scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size}",
                        "-frames:v",
                        "1",
                        "-q:v",
                        "4",
                        str(temporary),
                    ],
                    check=True,
                    timeout=15,
                )
                temporary.replace(thumbnail)
            except (OSError, subprocess.SubprocessError):
                temporary.unlink(missing_ok=True)
            finally:
                with self._lock:
                    self._pending.discard(thumbnail)
                self._queue.task_done()
