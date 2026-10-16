"""Asynchronous, cancellable lifecycle for AI Set Builder planning."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol

from audioextender.infrastructure.operation_lifecycle import SET_PLANNING, LifecycleProjection
from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.plan_evaluator import SetPlanEvaluator
from audioextender.set_builder.planning_store import PlanningJobStore
from audioextender.set_builder.release_gate import summarize_planning_jobs
from audioextender.set_builder.track_planner import AITrackPlanner


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PlanningCanceled(RuntimeError):
    """Raised at safe checkpoints after a planning cancellation request."""


class StartableThread(Protocol):
    def start(self) -> None: ...


@dataclass
class SetPlanningJobService:
    catalog_loader: Callable[[], list[dict[str, Any]]]
    candidate_retriever: SetCandidateRetriever
    track_planner: AITrackPlanner
    evaluator: SetPlanEvaluator = field(default_factory=SetPlanEvaluator)
    store: PlanningJobStore | None = None
    thread_factory: Callable[..., StartableThread] = threading.Thread
    maximum_retained_jobs: int = 50
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _states: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _requests: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _cancel: dict[str, threading.Event] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.store is None:
            return
        states, requests = self.store.load()
        self._states = states
        self._requests = requests
        for job_id, state in self._states.items():
            self._cancel[job_id] = threading.Event()
            if state.get("status") in {"pending", "processing", "canceling"}:
                state.update(
                    status="failed",
                    stage="Interrupted by application restart",
                    error="Planning stopped when the application restarted. Retry to build a fresh validated plan.",
                    retryable=True,
                    updatedAt=_now(),
                )
        self._persist()

    def _persist(self) -> None:
        if self.store is not None:
            self.store.save(self._states, self._requests)

    def start(self, request: dict[str, Any], *, retry_of: str | None = None) -> dict[str, Any]:
        with self._lock:
            terminal = [
                job_id
                for job_id, state in self._states.items()
                if state["status"] in {"complete", "failed", "canceled"}
            ]
            while len(self._states) >= self.maximum_retained_jobs and terminal:
                expired = terminal.pop(0)
                self._states.pop(expired, None)
                self._requests.pop(expired, None)
                self._cancel.pop(expired, None)
            for job_id, state in self._states.items():
                if state["status"] in {"pending", "processing", "canceling"}:
                    self._cancel[job_id].set()
                    state.update(status="canceling", stage="Superseded by a newer plan", updatedAt=_now())
            job_id = uuid.uuid4().hex
            self._states[job_id] = {
                "jobId": job_id,
                "status": "pending",
                "stage": "Waiting to retrieve candidates",
                "progress": 0,
                "result": None,
                "error": None,
                "retryable": False,
                "retryOf": retry_of,
                "createdAt": _now(),
                "updatedAt": _now(),
            }
            self._requests[job_id] = deepcopy(request)
            self._cancel[job_id] = threading.Event()
            self._persist()
        self.thread_factory(
            target=self._run,
            args=(job_id,),
            daemon=True,
            name=f"set-planning-{job_id[:8]}",
        ).start()
        return self.status(job_id)

    def _run(self, job_id: str) -> None:
        started = perf_counter()
        timings: dict[str, int] = {}
        try:
            self._update(job_id, status="processing", stage="Retrieving bounded catalog candidates", progress=10)
            self._check_canceled(job_id)
            request = self._requests[job_id]
            phase_started = perf_counter()
            pool = self.candidate_retriever.retrieve(
                self.catalog_loader(),
                request["journey"],
                required_ids=set(request["required_track_ids"]),
                excluded_ids=set(request["excluded_track_ids"]),
                locked_ids=set(request["locked_track_ids"]),
                constraints=request["brief"],
                section_limit=request["per_section_limit"],
                total_limit=request["total_limit"],
            )
            timings["candidateRetrievalMs"] = round((perf_counter() - phase_started) * 1000)
            if pool["missingRequiredIds"] or pool["unavailableRequiredIds"]:
                raise ValueError(
                    "Required tracks are missing or unavailable: "
                    f"{pool['missingRequiredIds'] + pool['unavailableRequiredIds']}"
                )
            self._update(job_id, stage="Planning and validating the running order", progress=35)
            phase_started = perf_counter()
            result = self.track_planner.plan(
                brief=request["brief"],
                journey=request["journey"],
                candidate_pool=pool,
                target_track_count=request["target_track_count"],
                target_duration_minutes=request["target_duration_minutes"],
                required_ids=set(request["required_track_ids"]),
                excluded_ids=set(request["excluded_track_ids"]),
                locked_ids=set(request["locked_track_ids"]),
                cancel_check=lambda: self._check_canceled(job_id),
            )
            timings["planningAndValidationMs"] = round((perf_counter() - phase_started) * 1000)
            self._check_canceled(job_id)
            result["candidatePool"] = {
                "candidateCount": pool["candidateCount"],
                "sections": [
                    {"sectionId": section["sectionId"], "scarcity": section["scarcity"]} for section in pool["sections"]
                ],
            }
            phase_started = perf_counter()
            result["evaluation"] = self.evaluator.evaluate(
                result["plan"],
                request["journey"],
                result["warnings"],
                target_duration_minutes=request["target_duration_minutes"],
                candidate_pool=pool,
            )
            timings["evaluationMs"] = round((perf_counter() - phase_started) * 1000)
            result["planningDurationMs"] = round((perf_counter() - started) * 1000)
            result["observability"] = {
                **timings,
                **result.get("observability", {}),
                "totalMs": result["planningDurationMs"],
                "outcome": result["mode"],
            }
            self._update(
                job_id,
                status="complete",
                stage="Validated running order ready",
                progress=100,
                result=result,
                retryable=False,
            )
        except PlanningCanceled as error:
            self._update(
                job_id,
                status="canceled",
                stage=str(error),
                error=None,
                retryable=True,
            )
        except Exception as error:
            self._update(
                job_id,
                status="failed",
                stage="Planning failed safely",
                error=str(error),
                retryable=True,
            )

    def _check_canceled(self, job_id: str) -> None:
        if self._cancel[job_id].is_set():
            raise PlanningCanceled("Planning canceled; no set changes were applied")

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self._states[job_id].update(changes, updatedAt=_now())
            self._persist()

    def status(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                return deepcopy(self._states[job_id])
            except KeyError as error:
                raise KeyError("Set-planning job was not found") from error

    def lifecycle_status(self, job_id: str) -> LifecycleProjection:
        """Return the executor-neutral lifecycle view for internal consumers."""
        return SET_PLANNING.project(self.status(job_id))

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            state = self.status(job_id)
            if state["status"] not in {"complete", "failed", "canceled"}:
                self._cancel[job_id].set()
                self._states[job_id].update(status="canceling", stage="Canceling safely", updatedAt=_now())
                self._persist()
            return deepcopy(self._states[job_id])

    def retry(self, job_id: str) -> dict[str, Any]:
        state = self.status(job_id)
        if state["status"] not in {"failed", "canceled"}:
            raise ValueError("Only a failed or canceled planning job can be retried")
        return self.start(self._requests[job_id], retry_of=job_id)

    def observability(self) -> dict[str, Any]:
        with self._lock:
            return summarize_planning_jobs(list(self._states.values()))
