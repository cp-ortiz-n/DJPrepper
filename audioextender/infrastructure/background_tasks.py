"""Thread-safe, restart-aware state storage for background web tasks."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any


class _TaskState(dict[str, Any]):
    def __init__(self, value: dict[str, Any], changed: Any) -> None:
        super().__init__(value)
        self._changed = changed

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._changed()


class BackgroundTaskRegistry(MutableMapping[str, dict[str, Any]]):
    """Persist task progress and mark interrupted work retryable after restart."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self._states: dict[str, _TaskState] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        for task_id, raw in payload.items():
            state = dict(raw)
            if state.get("status") == "processing":
                state.update(
                    status="failed",
                    stage="Interrupted by application restart",
                    error="Retry this task when the library is available.",
                    retryable=True,
                )
            self._states[str(task_id)] = _TaskState(state, self._save)
        if payload:
            self._save()

    def _save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self._states, indent=2, default=str), encoding="utf-8"
            )
            temporary.replace(self.path)

    def __getitem__(self, key: str) -> dict[str, Any]:
        with self.lock:
            return self._states[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        with self.lock:
            self._states[key] = _TaskState(value, self._save)
            self._save()

    def __delitem__(self, key: str) -> None:
        with self.lock:
            del self._states[key]
            self._save()

    def __iter__(self) -> Iterator[str]:
        with self.lock:
            return iter(tuple(self._states))

    def __len__(self) -> int:
        with self.lock:
            return len(self._states)

    def clear(self) -> None:
        with self.lock:
            self._states.clear()
            self._save()
