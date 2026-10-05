"""Stable, user-facing receipts for state-changing operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def operation_receipt(
    *,
    operation: str,
    requested: str,
    requested_count: int | None = None,
    changed: str = "Nothing changed",
    changed_count: int = 0,
    written_to: Iterable[str] = (),
    failures: Iterable[Mapping[str, Any] | str] = (),
    survives_restart: bool,
    durability: str,
    status: str | None = None,
) -> dict[str, Any]:
    """Return one predictable account of what a mutation actually accomplished."""

    failure_items = [
        dict(item) if isinstance(item, Mapping) else {"error": str(item)}
        for item in failures
    ]
    targets = list(dict.fromkeys(str(path) for path in written_to if str(path).strip()))
    resolved_status = status or ("partial" if failure_items else "complete")
    return {
        "operation": operation,
        "status": resolved_status,
        "requested": {"summary": requested, "count": requested_count},
        "changed": {"summary": changed, "count": int(changed_count)},
        "written_to": targets,
        "failures": failure_items,
        "survives_restart": bool(survives_restart),
        "durability": durability,
    }

