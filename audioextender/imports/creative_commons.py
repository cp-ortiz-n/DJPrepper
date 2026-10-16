"""Lifecycle service for Creative Commons batches and retry jobs."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from audioextender.infrastructure.background_tasks import BackgroundTaskRegistry
from audioextender.infrastructure.operation_lifecycle import CREATIVE_COMMONS_IMPORTS, LifecycleProjection


class CreativeCommonsNotFoundError(LookupError):
    """Raised when a Creative Commons import batch is not found in the registry."""

    pass


class CreativeCommonsImportService:
    """Lifecycle service for Creative Commons import batches and retry jobs."""

    def __init__(
        self,
        registry: BackgroundTaskRegistry,
        *,
        require_library_online: Callable[[], Any],
        worker: Callable[[str, list[Any], str], None],
        retry_worker: Callable[[str, list[dict[str, Any]]], None],
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self.registry = registry
        self._require_library_online = require_library_online
        self._worker = worker
        self._retry_worker = retry_worker
        self._thread_factory = thread_factory

    def start(self, tracks: list[Any], playlist_name: str) -> dict[str, Any]:
        """Start a new Creative Commons import batch for the given tracks."""

        allowed = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        if any((urlparse(track.url).hostname or "").casefold() not in allowed for track in tracks):
            raise ValueError("Every batch item must use a YouTube URL")
        self._require_library_online()
        batch_id = uuid.uuid4().hex
        self.registry[batch_id] = {
            "id": batch_id,
            "status": "processing",
            "stage": "Preparing Creative Commons verification",
            "progress": 0,
            "counts": {},
            "playlist_name": playlist_name,
        }
        self._thread_factory(
            target=self._worker,
            args=(batch_id, tracks, playlist_name),
            daemon=True,
            name=f"creative-commons-{batch_id[:8]}",
        ).start()
        return {"batch_id": batch_id}

    def start_retry(self, failures: list[dict[str, Any]]) -> dict[str, Any]:
        """Start a new retry job for the given failed import items."""

        self._require_library_online()
        batch_id = uuid.uuid4().hex
        self.registry[batch_id] = {
            "id": batch_id,
            "status": "processing",
            "stage": "Preparing retries",
            "progress": 0,
            "counts": {},
            "playlist_name": "Retry imports",
        }
        self._thread_factory(
            target=self._retry_worker,
            args=(batch_id, failures),
            daemon=True,
            name=f"import-retry-{batch_id[:8]}",
        ).start()
        return {"batch_id": batch_id, "retry_count": len(failures)}

    def status(self, batch_id: str, *, private: bool = False) -> dict[str, Any]:
        """Return the current status of a Creative Commons import batch."""

        state = self.registry.get(batch_id)
        if state is None:
            raise CreativeCommonsNotFoundError("Creative Commons import not found")
        return dict(state) if private else {key: value for key, value in state.items() if not key.endswith("_path")}

    def lifecycle_status(self, batch_id: str) -> LifecycleProjection:
        """Return a stable projection of the current lifecycle state for a Creative Commons import batch."""
        return CREATIVE_COMMONS_IMPORTS.project(self.status(batch_id))

    def has_active_imports(self) -> bool:
        """Return True if any Creative Commons import batch is currently in progress."""
        return any(state.get("status") == "processing" for state in self.registry.values())

    def clear(self) -> None:
        """Clear all Creative Commons import batches from the registry."""
        self.registry.clear()
