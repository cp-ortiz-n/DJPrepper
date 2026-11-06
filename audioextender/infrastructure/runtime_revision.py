"""Deterministic identity for the source code loaded by one server process."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_DIRECTORIES = ("audioextender", "frontend")
_SOURCE_SUFFIXES = frozenset({".css", ".html", ".js", ".json", ".py"})
_REVISION_FORMAT = b"audioextender-runtime-v1\0"


@dataclass(frozen=True)
class RuntimeRevision:
    """Immutable source fingerprint captured while a process is composed."""

    value: str
    file_count: int

    @classmethod
    def capture(cls, project_root: Path = _PROJECT_ROOT) -> RuntimeRevision:
        """Hash every backend and frontend source file in a stable order."""
        project_root = project_root.resolve()
        sources = sorted(
            (
                path
                for directory in _SOURCE_DIRECTORIES
                for path in (project_root / directory).rglob("*")
                if path.is_file() and path.suffix in _SOURCE_SUFFIXES
            ),
            key=lambda path: path.relative_to(project_root).as_posix(),
        )
        digest = hashlib.sha256(_REVISION_FORMAT)
        for path in sources:
            relative_path = path.relative_to(project_root).as_posix().encode("utf-8")
            content = path.read_bytes()
            digest.update(len(relative_path).to_bytes(4, "big"))
            digest.update(relative_path)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        return cls(value=digest.hexdigest(), file_count=len(sources))


def current_runtime_revision() -> str:
    """Return the revision expected from a server started from this checkout."""
    return RuntimeRevision.capture().value


if __name__ == "__main__":
    print(current_runtime_revision())
