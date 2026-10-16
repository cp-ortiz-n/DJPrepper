"""Narrow repository capabilities consumed by application services."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class JobQueueRepository(Protocol):
    """Persistence required by the web audio-job scheduler and progress adapter."""

    def get(self, job_id: int) -> dict[str, Any] | None: ...

    def get_downloaded_track_by_path(self, file_path: Path) -> dict[str, Any] | None: ...

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def update(self, job_id: int, **fields: Any) -> None: ...
