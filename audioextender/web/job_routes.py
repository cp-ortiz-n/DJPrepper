"""Job queue services and HTTP controls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel


class ReorderRequest(BaseModel):
    job_ids: list[int]


@dataclass
class JobQueueService:
    repository: Callable[[], Any]
    processor: Callable[[], Any]
    watchdog_last: float = 0.0

    def list(
        self, *, paged: bool, page: int, page_size: int, statuses: list[str]
    ) -> list[dict] | dict:
        repository = self.repository()
        if perf_counter() - self.watchdog_last >= 60:
            repository.fail_stalled_jobs()
            self.watchdog_last = perf_counter()
        if paged:
            rows, total = repository.list_jobs_page(
                page=page, page_size=page_size, statuses=tuple(statuses)
            )
        else:
            rows = repository.list_job_summaries()
            active_rows, _ = repository.list_jobs_page(
                page=1, page_size=10_000, statuses=("queued", "processing")
            )
            rows_by_id = {int(row["id"]): row for row in rows}
            rows_by_id.update({int(row["id"]): row for row in active_rows})
            rows = sorted(rows_by_id.values(), key=lambda row: int(row["id"]), reverse=True)
        queue = self.processor().snapshot()
        pending = {job_id: index for index, job_id in enumerate(queue["pending"])}
        active_ids = set(
            queue.get("active_ids") or ([] if queue["active"] is None else [queue["active"]])
        )
        paused_ids = set(queue.get("paused_ids") or [])
        for row in rows:
            row["queue_index"] = pending.get(int(row["id"]))
            row["is_active"] = int(row["id"]) in active_ids
            row["pause_requested"] = int(row["id"]) in paused_ids
        if not paged:
            return rows
        return {
            "jobs": rows,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": max(1, (total + page_size - 1) // page_size),
            },
        }

    def clear(self) -> dict:
        repository = self.repository()
        active_ids = set(self.processor().snapshot().get("active_ids") or [])
        cleared = 0
        for job in repository.list_jobs(1000):
            job_id = int(job["id"])
            if job_id in active_ids:
                continue
            if job["status"] == "queued":
                self.processor().cancel(job_id)
                cleared += int(repository.delete(job_id))
            elif job["status"] in {"failed", "canceled"}:
                cleared += int(repository.delete(job_id))
            elif job.get("review_status") in {"pending", "rejected"}:
                repository.update(job_id, review_status="resolved")
                cleared += 1
        return {"cleared": cleared, "active_preserved": bool(active_ids)}


def create_job_router(queue: JobQueueService) -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("")
    def jobs(
        paged: bool = False,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        status: Annotated[list[str] | None, Query()] = None,
    ) -> list[dict] | dict:
        return queue.list(paged=paged, page=page, page_size=page_size, statuses=status or [])

    @router.post("/reorder")
    def reorder_jobs(request: ReorderRequest) -> dict:
        queue.processor().reorder(request.job_ids)
        return {"ok": True}

    @router.post("/clear")
    def clear_jobs() -> dict:
        return queue.clear()

    @router.post("/{job_id}/cancel")
    def cancel_job(job_id: int) -> dict:
        if not queue.processor().cancel(job_id):
            raise HTTPException(409, "Only queued jobs can be canceled")
        return {"ok": True}

    @router.post("/{job_id}/pause")
    def pause_job(job_id: int) -> dict:
        if not queue.processor().pause(job_id):
            raise HTTPException(409, "Only the actively processing job can be paused")
        return {"ok": True}

    @router.post("/{job_id}/resume")
    def resume_job(job_id: int) -> dict:
        if not queue.processor().resume(job_id):
            raise HTTPException(409, "Only the actively processing job can be resumed")
        return {"ok": True}

    @router.delete("/{job_id}")
    def remove_job(job_id: int) -> dict:
        job = queue.repository().get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["status"] in {"queued", "processing"}:
            raise HTTPException(409, "Cancel or finish the job before removing it")
        return {"removed": queue.repository().delete(job_id)}

    return router
