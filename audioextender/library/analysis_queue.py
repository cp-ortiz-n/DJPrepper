"""Application service for queuing catalog tracks for analysis."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


class DownloadedTrackAnalysisQueue:
    """Create analysis jobs for available catalog tracks without duplicates."""

    def __init__(
        self,
        *,
        repository: Any,
        processor: Any,
        effective_settings: Callable[[], dict[str, Any]],
    ) -> None:
        self._repository = repository
        self._processor = processor
        self._effective_settings = effective_settings

    def queue(self, tracks: list[dict[str, Any]], *, force: bool = False) -> dict[str, list[int]]:
        excluded_statuses = {"queued", "processing", "paused"}
        if not force:
            excluded_statuses.add("complete")
        existing_paths = {
            str(Path(job["source_path"]).resolve())
            for job in self._repository.list_jobs(limit=10_000)
            if job["status"] in excluded_statuses
        }
        effective = self._effective_settings()
        created: list[int] = []
        skipped: list[int] = []
        unavailable: list[int] = []
        for track in tracks:
            track_id = int(track["id"])
            source = Path(track["file_path"])
            if not source.is_file():
                unavailable.append(track_id)
                continue
            resolved_source = str(source.resolve())
            if resolved_source in existing_paths:
                skipped.append(track_id)
                continue
            if force:
                self._repository.reassess_recording_family(track_id)
            job_id = self._repository.create(
                source.name,
                source,
                "auto",
                0,
                0,
                False,
                {
                    **effective,
                    "use_stems": False,
                    "analysis_only": True,
                    "refresh_cache": force,
                    "reanalyze": force,
                    "intro_bars_auto": False,
                    "outro_bars_auto": False,
                    "review_candidates": False,
                },
                parent_job_id=(
                    int(track["completed_library_job_id"]) if force and track.get("completed_library_job_id") else None
                ),
            )
            created.append(job_id)
            existing_paths.add(resolved_source)
        self._processor.enqueue_many(created)
        return {"job_ids": created, "skipped": skipped, "unavailable": unavailable}
