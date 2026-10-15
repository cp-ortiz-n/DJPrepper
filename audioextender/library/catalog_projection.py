"""Synchronous publication boundary for catalog-derived read models."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CatalogProjectionPublisher:
    """Invalidate stale projections and publish one consistent catalog version."""

    repository: Callable[[], Any]
    rebuild: Callable[[], None]
    report_path: Callable[[], Path]
    catalog_path: Callable[[], Path]
    memory_cache: dict[str, Any]
    memory_cache_lock: Any
    schema_version: int = 5
    _publication_lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def signature(self) -> tuple[tuple[tuple[int, int], tuple[int, int]], str]:
        report = self.report_path()
        report_signature = (report.stat().st_mtime_ns, report.stat().st_size) if report.exists() else (0, 0)
        source_signature = self.repository().library_index_source_signature()
        signature = (report_signature, (hash(source_signature), len(source_signature)))
        serialized = json.dumps(
            {"version": self.schema_version, "report": report_signature, "sources": source_signature},
            separators=(",", ":"),
        )
        return signature, serialized

    def publish(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Remove stale state, rebuild both projections, and publish their signature."""
        with self._publication_lock:
            with self.memory_cache_lock:
                self.memory_cache.clear()
            self.catalog_path().unlink(missing_ok=True)
            self.rebuild()
            signature, serialized = self.signature()
            self.repository().set_system_state("library_search_index_signature", serialized)
            with self.memory_cache_lock:
                self.memory_cache.clear()
                self.memory_cache["signature"] = signature
            return signature
