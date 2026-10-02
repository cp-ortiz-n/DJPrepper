"""Shared lifecycle primitives for cancellable, retryable background batches."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

TERMINAL_BATCH_STATUSES = frozenset({"complete", "failed", "canceled"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class BatchCanceled(RuntimeError):
    """Raised cooperatively when a batch has been canceled."""


class BatchContext:
    """Worker-facing API for publishing consistent progress and results."""

    def __init__(self, registry: BatchOperationRegistry, batch_id: str) -> None:
        self.registry = registry
        self.batch_id = batch_id

    def check_canceled(self) -> None:
        if self.registry.is_cancel_requested(self.batch_id):
            raise BatchCanceled("Canceled safely")

    def progress(
        self,
        *,
        processed: int,
        total: int | None = None,
        stage: str | None = None,
        counters: dict[str, int] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.registry.progress(
            self.batch_id,
            processed=processed,
            total=total,
            stage=stage,
            counters=counters,
            error=error,
        )


class BatchOperationRegistry:
    """Own background batch state independent of any particular web route."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._states: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._workers: dict[str, Callable[[BatchContext, list[Any]], dict[str, Any] | None]] = {}
        self._items: dict[str, list[Any]] = {}

    def start(
        self,
        kind: str,
        items: Iterable[Any],
        worker: Callable[[BatchContext, list[Any]], dict[str, Any] | None],
        *,
        stage: str,
        counters: dict[str, int] | None = None,
        retry_of: str | None = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> dict[str, Any]:
        values = list(items)
        with self.lock:
            active = next(
                (
                    state for state in reversed(tuple(self._states.values()))
                    if state["kind"] == kind and state["status"] in {"pending", "processing", "canceling"}
                ),
                None,
            )
            if active is not None:
                return deepcopy(active)
            batch_id = uuid.uuid4().hex
            state: dict[str, Any] = {
                "batch_id": batch_id,
                "kind": kind,
                "status": "processing",
                "stage": stage,
                "progress": 0,
                "processed": 0,
                "total": len(values),
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [],
                "result": {},
                "retryable": False,
                "retry_of": retry_of,
                "created_at": _now(),
                "updated_at": _now(),
            }
            state.update(counters or {})
            self._states[batch_id] = state
            self._cancel[batch_id] = threading.Event()
            self._workers[batch_id] = worker
            self._items[batch_id] = values
        thread_factory(
            target=self._run,
            args=(batch_id,),
            daemon=True,
            name=f"metadata-{kind}-{batch_id[:8]}",
        ).start()
        return self.status(batch_id)

    def _run(self, batch_id: str) -> None:
        with self.lock:
            self._states[batch_id].update(status="processing", updated_at=_now())
            worker = self._workers[batch_id]
            items = list(self._items[batch_id])
        try:
            result = worker(BatchContext(self, batch_id), items) or {}
            with self.lock:
                state = self._states[batch_id]
                state.update(
                    status="complete",
                    stage=result.pop("stage", "Complete"),
                    progress=100,
                    result=result,
                    retryable=bool(state["errors"]),
                    completed_at=_now(),
                    updated_at=_now(),
                )
        except BatchCanceled as error:
            with self.lock:
                self._states[batch_id].update(
                    status="canceled", stage=str(error), retryable=True,
                    canceled_at=_now(), updated_at=_now(),
                )
        except Exception as error:
            with self.lock:
                state = self._states[batch_id]
                state["errors"].append({"error": str(error)})
                state.update(
                    status="failed", stage="Failed", error=str(error),
                    failed=max(1, int(state.get("failed") or 0)),
                    retryable=True, completed_at=_now(), updated_at=_now(),
                )

    def progress(
        self,
        batch_id: str,
        *,
        processed: int,
        total: int | None = None,
        stage: str | None = None,
        counters: dict[str, int] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        with self.lock:
            state = self._states[batch_id]
            if total is not None:
                state["total"] = total
            state["processed"] = processed
            state["progress"] = round(processed / max(1, int(state["total"])) * 100)
            if stage is not None:
                state["stage"] = stage
            state.update(counters or {})
            if error is not None:
                state["errors"].append(error)
            state["updated_at"] = _now()

    def cancel(self, batch_id: str) -> dict[str, Any]:
        with self.lock:
            state = self._require(batch_id)
            if state["status"] not in TERMINAL_BATCH_STATUSES:
                self._cancel[batch_id].set()
                state.update(status="canceling", stage="Canceling safely", updated_at=_now())
            return deepcopy(state)

    def retry(self, batch_id: str) -> dict[str, Any]:
        with self.lock:
            state = self._require(batch_id)
            if state["status"] not in TERMINAL_BATCH_STATUSES:
                raise ValueError("Only a finished batch can be retried")
            failed_ids = {
                item.get("id") for item in state.get("errors", []) if item.get("id") is not None
            }
            original = self._items[batch_id]
            items = [item for item in original if not failed_ids or self._item_id(item) in failed_ids]
            worker = self._workers[batch_id]
            kind = str(state["kind"])
        return self.start(
            kind, items, worker, stage="Retrying", retry_of=batch_id,
            counters={key: 0 for key in state if key in {"tagged", "updated", "unchanged", "unresolved", "resolved"}},
        )

    @staticmethod
    def _item_id(item: Any) -> Any:
        return item.get("id") if isinstance(item, dict) else item

    def is_cancel_requested(self, batch_id: str) -> bool:
        with self.lock:
            return self._cancel[batch_id].is_set()

    def status(self, batch_id: str) -> dict[str, Any]:
        with self.lock:
            return deepcopy(self._require(batch_id))

    def latest(self, kind: str) -> dict[str, Any] | None:
        with self.lock:
            return next(
                (deepcopy(state) for state in reversed(tuple(self._states.values())) if state["kind"] == kind),
                None,
            )

    def _require(self, batch_id: str) -> dict[str, Any]:
        try:
            return self._states[batch_id]
        except KeyError as error:
            raise KeyError("Metadata batch was not found") from error
