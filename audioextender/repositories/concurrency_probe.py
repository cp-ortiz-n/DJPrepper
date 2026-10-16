"""Bounded, disposable concurrency measurements for repository behavior."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any

from audioextender.repositories.facade import JobRepository


@dataclass(frozen=True)
class ConcurrencyProbeConfig:
    iterations: int = 50
    workers: int = 6
    suspected_wait_ms: float = 100.0

    def __post_init__(self) -> None:
        if not 1 <= self.iterations <= 1000:
            raise ValueError("iterations must be between 1 and 1000")
        if not 1 <= self.workers <= 16:
            raise ValueError("workers must be between 1 and 16")
        if self.suspected_wait_ms <= 0:
            raise ValueError("suspected_wait_ms must be positive")


class RepositoryConcurrencyProbe:
    """Exercise representative catalog operations without touching a user library."""

    def __init__(self, workspace: Path, config: ConcurrencyProbeConfig) -> None:
        self.workspace = workspace
        self.config = config
        self.repository = JobRepository(workspace / "probe.sqlite3")
        self._metrics_lock = threading.Lock()
        self._active_operations = 0
        self._latencies: dict[str, list[float]] = {}
        self._errors: list[dict[str, Any]] = []
        self._stale_results: list[dict[str, Any]] = []
        self._suspected_waits: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        started = perf_counter()
        operations: list[tuple[str, Callable[[], None]]] = []
        for index in range(self.config.iterations):
            operations.extend(
                (
                    ("job-write", partial(self._job_write, index)),
                    ("catalog-write", partial(self._catalog_write, index)),
                    ("state-write", partial(self._state_write, index)),
                    ("catalog-read", self._catalog_read),
                )
            )
        with ThreadPoolExecutor(max_workers=self.config.workers, thread_name_prefix="repository-probe") as pool:
            futures = [pool.submit(self._measure, name, operation) for name, operation in operations]
            for future in as_completed(futures):
                future.result()
        final_jobs = len(self.repository.list_jobs(limit=self.config.iterations + 1))
        final_tracks = len(self.repository.list_downloaded_tracks())
        if final_jobs != self.config.iterations:
            self._record_stale("final-job-count", self.config.iterations, final_jobs)
        if final_tracks != self.config.iterations:
            self._record_stale("final-track-count", self.config.iterations, final_tracks)
        locked_errors = sum(1 for error in self._errors if error["category"] == "sqlite-locked")
        status = "investigate" if self._errors or self._stale_results else "pass"
        return {
            "status": status,
            "disposable": True,
            "configuration": {
                "iterations": self.config.iterations,
                "workers": self.config.workers,
                "suspected_wait_ms": self.config.suspected_wait_ms,
                "sqlite_timeout_seconds": 30,
            },
            "summary": {
                "operations": len(operations),
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "errors": len(self._errors),
                "sqlite_locked_errors": locked_errors,
                "suspected_lock_waits": len(self._suspected_waits),
                "stale_results": len(self._stale_results),
                "final_jobs": final_jobs,
                "final_tracks": final_tracks,
            },
            "latency_ms": {name: self._latency_summary(values) for name, values in sorted(self._latencies.items())},
            "errors": self._errors,
            "suspected_lock_waits": self._suspected_waits,
            "stale_results": self._stale_results,
            "interpretation": (
                "No lock errors or stale committed reads were observed."
                if status == "pass"
                else "Measured failures require investigation before changing repository ownership."
            ),
            "recommended_follow_up": "" if status == "pass" else "ARCH-015B",
        }

    def _measure(self, name: str, operation: Callable[[], None]) -> None:
        with self._metrics_lock:
            overlap = self._active_operations
            self._active_operations += 1
        started = perf_counter()
        try:
            operation()
        except sqlite3.OperationalError as error:
            category = "sqlite-locked" if "locked" in str(error).casefold() else "sqlite-operational"
            self._record_error(name, category, error)
        except Exception as error:
            self._record_error(name, "unexpected", error)
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            with self._metrics_lock:
                self._active_operations -= 1
                self._latencies.setdefault(name, []).append(elapsed_ms)
                if overlap and elapsed_ms >= self.config.suspected_wait_ms:
                    self._suspected_waits.append(
                        {"operation": name, "elapsed_ms": round(elapsed_ms, 3), "overlapping_operations": overlap}
                    )

    def _job_write(self, index: int) -> None:
        path = self.workspace / "sources" / f"Job-{index}.wav"
        job_id = self.repository.create(path.name, path, "auto", 0, 0, False)
        self.repository.update(job_id, status="complete", bpm=120 + index % 10)
        observed = self.repository.get(job_id)
        if not observed or observed["status"] != "complete":
            self._record_stale("job-status", "complete", observed)

    def _catalog_write(self, index: int) -> None:
        path = self.workspace / "library" / f"Track-{index}.wav"
        track_id = self.repository.upsert_downloaded_track(
            title=f"Track {index}",
            artist="Concurrency Probe",
            file_path=path,
            genre="house",
            genre_category="Electronic / House",
        )
        self.repository.update_track_descriptors(
            [track_id],
            [{"category": "context", "value": f"probe-{index}", "provenance": "manual"}],
            mode="replace",
        )
        observed = self.repository.get_downloaded_track(track_id)
        descriptors = self.repository.track_descriptors(track_id)
        descriptor_values = {item["value"] for item in descriptors}
        if not observed or observed["title"] != f"Track {index}" or f"probe-{index}" not in descriptor_values:
            self._record_stale("catalog-track", f"Track {index}", observed)

    def _state_write(self, index: int) -> None:
        key, value = f"concurrency-probe-{index}", str(index)
        self.repository.set_system_state(key, value)
        observed = self.repository.get_system_state(key)
        if observed != value:
            self._record_stale("system-state", value, observed)

    def _catalog_read(self) -> None:
        self.repository.list_jobs(limit=25)
        self.repository.list_downloaded_tracks()
        self.repository.library_index_source_signature()

    def _record_error(self, operation: str, category: str, error: Exception) -> None:
        with self._metrics_lock:
            self._errors.append({"operation": operation, "category": category, "error": str(error)})

    def _record_stale(self, check: str, expected: Any, observed: Any) -> None:
        with self._metrics_lock:
            self._stale_results.append({"check": check, "expected": expected, "observed": observed})

    @staticmethod
    def _latency_summary(values: list[float]) -> dict[str, float | int]:
        ordered = sorted(values)

        def percentile(fraction: float) -> float:
            return ordered[round((len(ordered) - 1) * fraction)]

        return {
            "count": len(ordered),
            "p50": round(percentile(0.5), 3),
            "p95": round(percentile(0.95), 3),
            "max": round(ordered[-1], 3),
        }
