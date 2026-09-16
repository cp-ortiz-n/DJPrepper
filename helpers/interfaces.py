"""Small dependency contracts shared by application services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    """Progress sink used by processing code, terminals, and test doubles."""

    def update(self, percent: float, label: str) -> None: ...

    def log(self, message: str) -> None: ...

    def complete(self, label: str = "Complete") -> None: ...

    def stop(self) -> None: ...

    def pause_for_input(self) -> None: ...

    def resume_after_input(self) -> None: ...


class NullProgressReporter:
    """No-op reporter for library use and deterministic tests."""

    def update(self, percent: float, label: str) -> None:
        pass

    def log(self, message: str) -> None:
        pass

    def complete(self, label: str = "Complete") -> None:
        pass

    def stop(self) -> None:
        pass

    def pause_for_input(self) -> None:
        pass

    def resume_after_input(self) -> None:
        pass
