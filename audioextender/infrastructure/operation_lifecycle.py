"""Typed, executor-neutral contracts for user-visible background operations.

Feature services keep ownership of execution, persistence, and rollback.  This
module only projects their existing state into one stable internal vocabulary.
Public API serializers may continue returning their legacy payloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LifecycleStatus(StrEnum):
    QUEUED = "queued"
    PENDING = "pending"
    PLANNED = "planned"
    PROCESSING = "processing"
    CANCELING = "canceling"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"
    ROLLED_BACK = "rolled_back"

    @property
    def terminal(self) -> bool:
        return self in {
            self.COMPLETE,
            self.FAILED,
            self.CANCELED,
            self.ROLLED_BACK,
        }


class LifecyclePersistence(StrEnum):
    MEMORY = "memory"
    JSON = "json"
    SQLITE = "sqlite"


@dataclass(frozen=True)
class LifecycleCapabilities:
    cancel: bool
    retry: bool
    rollback: bool = False
    pause: bool = False


@dataclass(frozen=True)
class LifecycleError:
    message: str
    item_id: str | int | None = None
    code: str | None = None


@dataclass(frozen=True)
class LifecycleProjection:
    """Canonical read model shared by every background-operation family."""

    family: str
    operation_id: str
    status: LifecycleStatus
    stage: str
    progress: float
    retryable: bool
    persistence: LifecyclePersistence
    capabilities: LifecycleCapabilities
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    retry_of: str | None = None
    errors: tuple[LifecycleError, ...] = ()
    receipt: Mapping[str, Any] | None = None
    result: Mapping[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status.terminal


@dataclass(frozen=True)
class LifecycleActionReceipt:
    """Canonical response from cancellation, retry, pause, or rollback."""

    action: str
    accepted: bool
    operation_id: str
    status: LifecycleStatus
    linked_operation_id: str | None = None
    message: str = ""


@dataclass(frozen=True)
class LifecycleFamily:
    name: str
    persistence: LifecyclePersistence
    capabilities: LifecycleCapabilities
    id_fields: tuple[str, ...] = ("id", "batch_id", "jobId")
    created_fields: tuple[str, ...] = ("created_at", "createdAt")
    updated_fields: tuple[str, ...] = ("updated_at", "updatedAt")
    completed_fields: tuple[str, ...] = ("completed_at", "completedAt", "canceled_at", "rolled_back_at")
    retry_fields: tuple[str, ...] = ("retry_of", "retryOf")

    def project(self, state: Mapping[str, Any]) -> LifecycleProjection:
        status = LifecycleStatus(str(state.get("status") or "pending"))
        operation_id = str(_first(state, self.id_fields) or "")
        errors = _errors(state)
        raw_result = state.get("result")
        result = raw_result if isinstance(raw_result, Mapping) else {}
        raw_receipt = state.get("receipt")
        receipt = raw_receipt if isinstance(raw_receipt, Mapping) else None
        return LifecycleProjection(
            family=self.name,
            operation_id=operation_id,
            status=status,
            stage=str(state.get("stage") or ""),
            progress=float(state.get("progress") or 0),
            retryable=bool(state.get("retryable")),
            persistence=self.persistence,
            capabilities=self.capabilities,
            created_at=_string_or_none(_first(state, self.created_fields)),
            updated_at=_string_or_none(_first(state, self.updated_fields)),
            completed_at=_string_or_none(_first(state, self.completed_fields)),
            retry_of=_string_or_none(_first(state, self.retry_fields)),
            errors=errors,
            receipt=receipt,
            result=result,
        )

    def action_receipt(
        self,
        action: str,
        state: Mapping[str, Any],
        *,
        accepted: bool = True,
        linked_state: Mapping[str, Any] | None = None,
        message: str = "",
    ) -> LifecycleActionReceipt:
        current = self.project(state)
        linked_id = self.project(linked_state).operation_id if linked_state else None
        return LifecycleActionReceipt(
            action=action,
            accepted=accepted,
            operation_id=current.operation_id,
            status=current.status,
            linked_operation_id=linked_id,
            message=message,
        )


def _first(state: Mapping[str, Any], fields: tuple[str, ...]) -> Any:
    return next((state[field] for field in fields if state.get(field) is not None), None)


def _string_or_none(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _errors(state: Mapping[str, Any]) -> tuple[LifecycleError, ...]:
    values: list[Any] = list(state.get("errors") or [])
    if state.get("error") and not values:
        values.append(state["error"])
    normalized = []
    for value in values:
        if isinstance(value, Mapping):
            normalized.append(
                LifecycleError(
                    message=str(value.get("error") or value.get("message") or "Unknown error"),
                    item_id=value.get("id"),
                    code=_string_or_none(value.get("code")),
                )
            )
        else:
            normalized.append(LifecycleError(message=str(value)))
    return tuple(normalized)


AUDIO_JOBS = LifecycleFamily(
    "audio-jobs",
    LifecyclePersistence.SQLITE,
    LifecycleCapabilities(cancel=True, retry=True, pause=True),
)
AUTHORIZED_IMPORTS = LifecycleFamily(
    "authorized-import",
    LifecyclePersistence.MEMORY,
    LifecycleCapabilities(cancel=True, retry=False),
)
LOCAL_AUDIO_IMPORTS = LifecycleFamily(
    "local-audio-import",
    LifecyclePersistence.MEMORY,
    LifecycleCapabilities(cancel=False, retry=False),
)
PLAYLIST_MATCHES = LifecycleFamily(
    "playlist-match",
    LifecyclePersistence.MEMORY,
    LifecycleCapabilities(cancel=False, retry=False),
)
CREATIVE_COMMONS_IMPORTS = LifecycleFamily(
    "creative-commons-import",
    LifecyclePersistence.JSON,
    LifecycleCapabilities(cancel=False, retry=True),
)
METADATA_BATCHES = LifecycleFamily(
    "metadata-batches",
    LifecyclePersistence.MEMORY,
    LifecycleCapabilities(cancel=True, retry=True),
)
INTEGRITY_SCANS = LifecycleFamily(
    "integrity-scan",
    LifecyclePersistence.MEMORY,
    LifecycleCapabilities(cancel=False, retry=True),
)
AUDIO_QUALITY_SCANS = LifecycleFamily(
    "audio-quality-scan",
    LifecyclePersistence.MEMORY,
    LifecycleCapabilities(cancel=False, retry=True),
)
SET_PLANNING = LifecycleFamily(
    "set-planning",
    LifecyclePersistence.JSON,
    LifecycleCapabilities(cancel=True, retry=True),
    id_fields=("jobId", "id"),
)
LIBRARY_RELOCATION = LifecycleFamily(
    "library-relocation",
    LifecyclePersistence.JSON,
    LifecycleCapabilities(cancel=True, retry=True, rollback=True),
)

LIFECYCLE_FAMILIES = {
    family.name: family
    for family in (
        AUDIO_JOBS,
        AUTHORIZED_IMPORTS,
        LOCAL_AUDIO_IMPORTS,
        PLAYLIST_MATCHES,
        CREATIVE_COMMONS_IMPORTS,
        METADATA_BATCHES,
        INTEGRITY_SCANS,
        AUDIO_QUALITY_SCANS,
        SET_PLANNING,
        LIBRARY_RELOCATION,
    )
}
