"""Library operations over completed processing-job generations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LibraryTrackRemovalError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class LibraryJobCatalogService:
    """Manage library visibility for historical processing generations."""

    repository: Callable[[], Any]
    processing_report: Path

    def remove(self, source_name: str) -> dict:
        """Remove inactive generations from the Library without deleting exports."""
        repository = self.repository()
        matching = [
            job for job in repository.list_jobs(10_000) if str(job["source_name"]).casefold() == source_name.casefold()
        ]
        if not matching:
            raise LibraryTrackRemovalError(404, "Library track not found")
        if any(job["status"] in {"queued", "processing"} for job in matching):
            raise LibraryTrackRemovalError(409, "Cancel or finish this track before removing it")
        removed = sum(int(repository.delete(int(job["id"]))) for job in matching)
        try:
            report = json.loads(self.processing_report.read_text(encoding="utf-8"))
            record = report.get("songs", {}).get(source_name.casefold())
            if isinstance(record, dict):
                record["status"] = "removed"
                temporary = self.processing_report.with_suffix(".tmp")
                temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                temporary.replace(self.processing_report)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return {"removed_generations": removed, "files_preserved": True}
