"""Process-local API performance diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, cast


@dataclass(frozen=True)
class PerformanceDiagnostics:
    """Record and summarize a bounded process-local request timing window."""

    samples: Any
    cache_stats: dict[str, dict[str, int]]
    lock: Any

    def record_cache_result(self, cache_name: str, hit: bool) -> None:
        with self.lock:
            counters = self.cache_stats.setdefault(cache_name, {"hits": 0, "misses": 0})
            counters["hits" if hit else "misses"] += 1

    async def middleware(self, request, call_next):
        if not request.url.path.startswith("/api/") or request.url.path == "/api/diagnostics/performance":
            return await call_next(request)
        started = perf_counter()
        status = 500
        response_bytes = 0
        try:
            response = await call_next(request)
            status = response.status_code
            try:
                response_bytes = int(response.headers.get("content-length") or 0)
            except ValueError:
                response_bytes = 0
            return response
        finally:
            elapsed_ms = round((perf_counter() - started) * 1000, 1)
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            with self.lock:
                self.samples.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                        "method": request.method,
                        "path": route_path,
                        "status": status,
                        "duration_ms": elapsed_ms,
                        "response_bytes": response_bytes,
                    }
                )

    def report(self) -> dict:
        with self.lock:
            samples = list(self.samples)
            cache_snapshot = {name: dict(values) for name, values in self.cache_stats.items()}
        grouped: dict[str, list[dict[str, object]]] = {}
        for sample in samples:
            key = f"{sample['method']} {sample['path']}"
            grouped.setdefault(key, []).append(sample)
        operations = []
        for operation, entries in grouped.items():
            durations = sorted(float(cast(Any, entry["duration_ms"])) for entry in entries)
            percentile_index = round((len(durations) - 1) * 0.95)
            operations.append(
                {
                    "operation": operation,
                    "count": len(entries),
                    "average_ms": round(sum(durations) / len(durations), 1),
                    "p95_ms": durations[percentile_index],
                    "maximum_ms": durations[-1],
                    "failures": sum(int(cast(Any, entry["status"])) >= 400 for entry in entries),
                    "average_response_bytes": round(
                        sum(int(cast(Any, entry.get("response_bytes") or 0)) for entry in entries) / len(entries)
                    ),
                }
            )
        operations.sort(key=lambda item: (-float(cast(Any, item["p95_ms"])), -int(cast(Any, item["count"]))))
        cache = []
        for name, counters in cache_snapshot.items():
            total = counters["hits"] + counters["misses"]
            cache.append(
                {
                    "name": name,
                    **counters,
                    "hit_rate": round(counters["hits"] * 100 / total, 1) if total else None,
                }
            )
        slow = [sample for sample in reversed(samples) if float(cast(Any, sample["duration_ms"])) >= 250][:20]
        durations = [float(cast(Any, sample["duration_ms"])) for sample in samples]
        return {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "window_size": len(samples),
            "window_limit": self.samples.maxlen,
            "overall_average_ms": round(sum(durations) / len(durations), 1) if durations else 0,
            "operations": operations,
            "recent_slow_operations": slow,
            "cache": cache,
        }
