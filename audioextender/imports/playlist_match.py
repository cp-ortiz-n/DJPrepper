"""Background orchestration for playlist-to-source matching."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any

from audioextender.infrastructure.operation_lifecycle import PLAYLIST_MATCHES, LifecycleProjection


class PlaylistMatchNotFoundError(LookupError):
    """Raised when a playlist match job is not found in the registry."""

    pass


class PlaylistMatchService:
    """Background orchestration for playlist-to-source matching."""

    def __init__(
        self,
        matcher: Callable[[list[dict[str, Any]], Callable[..., None]], list[dict[str, Any]]],
        *,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._matcher = matcher
        self._thread_factory = thread_factory
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, tracks: list[dict[str, Any]], playlist_name: str) -> dict[str, Any]:
        """Start a new playlist match job for the given tracks."""
        match_id = uuid.uuid4().hex
        with self._lock:
            self._states[match_id] = {
                "id": match_id,
                "status": "processing",
                "stage": f"Loaded {len(tracks)} tracks from CSV",
                "progress": 0,
                "matched": 0,
                "total": len(tracks),
                "playlist_name": playlist_name,
            }
        self._thread_factory(
            target=self.run,
            args=(match_id, tracks),
            daemon=True,
            name=f"playlist-match-{match_id[:8]}",
        ).start()
        return {"match_id": match_id, "track_count": len(tracks), "playlist_name": playlist_name}

    def run(self, match_id: str, tracks: list[dict[str, Any]]) -> None:
        """Run the playlist matching process in a background thread."""
        try:
            results = self._matcher(
                tracks,
                lambda **values: self._update(match_id, **values),
            )
            self._update(
                match_id,
                status="complete",
                stage="Playlist matching complete",
                progress=100,
                results=results,
            )
        except Exception as error:
            self._update(
                match_id,
                status="failed",
                stage="Playlist matching failed",
                error=str(error),
            )

    def status(self, match_id: str) -> dict[str, Any]:
        """Return the current state of a playlist match job."""
        with self._lock:
            state = self._states.get(match_id)
            if state is None:
                raise PlaylistMatchNotFoundError("Playlist match job not found")
            return dict(state)

    def lifecycle_status(self, match_id: str) -> LifecycleProjection:
        """Return a stable projection of the current state of a playlist match job."""
        return PLAYLIST_MATCHES.project(self.status(match_id))

    def has_active_imports(self) -> bool:
        """Return True if any playlist match job is currently in progress."""
        with self._lock:
            return any(state.get("status") == "processing" for state in self._states.values())

    def clear(self) -> None:
        """Clear all playlist match jobs from the registry."""
        with self._lock:
            self._states.clear()

    def _update(self, match_id: str, **values: Any) -> None:
        """Update the state of a playlist match job with new values."""
        with self._lock:
            self._states[match_id].update(values)
