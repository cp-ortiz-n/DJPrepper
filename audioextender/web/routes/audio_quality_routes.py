"""Audio-quality scan workflow and HTTP routes for the downloaded library."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException


class AudioQualityResult(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


class StartableThread(Protocol):
    def start(self) -> None: ...


@dataclass(frozen=True)
class AudioQualityRouteDependencies:
    repository: Callable[[], Any]
    analyze: Callable[..., AudioQualityResult]
    batches: dict[str, dict[str, Any]]
    batch_lock: threading.Lock
    library_status_cache: dict[str, object]
    library_status_lock: threading.Lock
    thread_factory: Callable[..., StartableThread] = threading.Thread


class AudioQualityScanService:
    """Own the process-local lifecycle of downloaded-library quality scans."""

    def __init__(self, dependencies: AudioQualityRouteDependencies) -> None:
        self.dependencies = dependencies

    @property
    def repository(self) -> Any:
        return self.dependencies.repository()

    def run(self, batch_id: str) -> None:
        tracks = self.repository.list_downloaded_tracks()

        def inspect(track: dict[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any] | None, str]:
            path = Path(str(track.get("file_path") or ""))
            try:
                if not path.is_file():
                    raise FileNotFoundError("Audio file is unavailable")
                result = self.dependencies.analyze(
                    path,
                    window_seconds=0.5,
                    source_is_transcoded_lossy=bool(track.get("youtube_id") or track.get("youtube_url")),
                ).to_dict()
                return track, path, result, ""
            except (OSError, RuntimeError, ValueError) as exc:
                return track, path, None, str(exc)

        # Audio decoding and FFT work release the GIL. A small pool improves a
        # full external-drive scan without overwhelming the drive.
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="audio-quality") as executor:
            futures = [executor.submit(inspect, track) for track in tracks]
            for index, future in enumerate(as_completed(futures), start=1):
                track, path, result, error = future.result()
                if result is not None:
                    self.repository.update_audio_quality(int(track["id"]), result)
                with self.dependencies.batch_lock:
                    batch = self.dependencies.batches[batch_id]
                    batch["processed"] = index
                    batch["failed"] += int(bool(error))
                    batch["current"] = str(track.get("filename") or track.get("title") or "")
                    if error and len(batch["errors"]) < 30:
                        batch["errors"].append({"id": track.get("id"), "filename": path.name, "error": error})

        summary = self.repository.audio_quality_summary()
        with self.dependencies.batch_lock:
            self.dependencies.batches[batch_id].update(
                status="complete",
                stage="Quality scan complete",
                summary=summary,
            )
        with self.dependencies.library_status_lock:
            self.dependencies.library_status_cache.update(payload=None, expires_at=0.0)

    def start(self) -> dict[str, Any]:
        with self.dependencies.batch_lock:
            active = next(
                (
                    {"batch_id": key, **value}
                    for key, value in self.dependencies.batches.items()
                    if value["status"] == "processing"
                ),
                None,
            )
            if active:
                return active
            total = len(self.repository.list_downloaded_tracks())
            batch_id = uuid.uuid4().hex
            batch = {
                "status": "processing",
                "stage": "Analyzing audio quality",
                "total": total,
                "processed": 0,
                "failed": 0,
                "current": "",
                "errors": [],
            }
            self.dependencies.batches[batch_id] = batch
            response = {"batch_id": batch_id, **batch}

        self.dependencies.thread_factory(
            target=self.run,
            args=(batch_id,),
            daemon=True,
            name=f"audio-quality-{batch_id[:8]}",
        ).start()
        return response

    def latest(self) -> dict[str, Any]:
        with self.dependencies.batch_lock:
            if not self.dependencies.batches:
                return {"status": "none", "summary": self.repository.audio_quality_summary()}
            batch_id = next(reversed(self.dependencies.batches))
            return {"batch_id": batch_id, **self.dependencies.batches[batch_id]}

    def status(self, batch_id: str) -> dict[str, Any]:
        with self.dependencies.batch_lock:
            batch = self.dependencies.batches.get(batch_id)
            if batch is None:
                raise HTTPException(404, "Audio-quality scan not found")
            return {"batch_id": batch_id, **batch}


def create_audio_quality_router(service: AudioQualityScanService) -> APIRouter:
    router = APIRouter()

    @router.post("/api/downloaded-library/audio-quality")
    def start_audio_quality_scan() -> dict[str, Any]:
        return service.start()

    @router.get("/api/downloaded-library/audio-quality-latest")
    def latest_audio_quality_scan() -> dict[str, Any]:
        return service.latest()

    @router.get("/api/downloaded-library/audio-quality/{batch_id}")
    def audio_quality_scan_status(batch_id: str) -> dict[str, Any]:
        return service.status(batch_id)

    return router
