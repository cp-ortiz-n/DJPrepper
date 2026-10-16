from __future__ import annotations

from datetime import UTC, datetime


def catalog_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
