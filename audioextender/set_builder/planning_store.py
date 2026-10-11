"""Persistence boundary for recoverable Set Builder planning jobs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class PlanningJobStore(Protocol):
    def load(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]: ...

    def save(self, states: dict[str, dict[str, Any]], requests: dict[str, dict[str, Any]]) -> None: ...


@dataclass(frozen=True)
class JsonPlanningJobStore:
    path: Path

    def load(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}, {}
        states = payload.get("states", {})
        requests = payload.get("requests", {})
        return (
            states if isinstance(states, dict) else {},
            requests if isinstance(requests, dict) else {},
        )

    def save(self, states: dict[str, dict[str, Any]], requests: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".pending.json")
        temporary.write_text(
            json.dumps({"version": 1, "states": states, "requests": requests}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)
