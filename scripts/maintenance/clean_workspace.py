#!/usr/bin/env python3
"""Preview or remove known generated workspace artifacts safely."""

from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".venv-inte-l-backup",
    ".venv-intel-backup",
    "node_modules",
    "workspace",
}
_GENERATED_DIRECTORIES = {
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    "playwright-report",
    "test-results",
}


def validate_project_root(root: Path) -> None:
    """Reject cleanup outside a DJPrepper repository root."""
    if not (root / "pyproject.toml").is_file() or not (root / "audioextender").is_dir():
        raise ValueError(f"Refusing cleanup: {root} is not the DJPrepper repository root")


def _runtime_cache_targets(root: Path) -> Iterable[Path]:
    cache_root = root / "workspace" / "cache"
    if not cache_root.is_dir():
        return ()
    return (path for path in cache_root.iterdir() if path.name != ".gitkeep")


def discover_cleanup_targets(root: Path, *, include_analysis_cache: bool = False) -> tuple[Path, ...]:
    """Return removable generated paths without modifying the workspace."""
    root = root.resolve()
    validate_project_root(root)
    targets: set[Path] = set()

    for name in _GENERATED_DIRECTORIES:
        candidate = root / name
        if candidate.exists() or candidate.is_symlink():
            targets.add(candidate)
    for candidate in root.glob(".coverage*"):
        if candidate.is_file() or candidate.is_symlink():
            targets.add(candidate)

    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for directory_name in directory_names:
            candidate = current_path / directory_name
            if directory_name in _EXCLUDED_DIRECTORIES or candidate in targets:
                continue
            if directory_name == "__pycache__":
                targets.add(candidate)
                continue
            kept_directories.append(directory_name)
        directory_names[:] = kept_directories

        for file_name in file_names:
            candidate = current_path / file_name
            if file_name == ".DS_Store" or candidate.suffix in {".pyc", ".pyo"}:
                targets.add(candidate)

    if include_analysis_cache:
        targets.update(_runtime_cache_targets(root))

    return tuple(sorted(targets, key=lambda path: path.relative_to(root).as_posix()))


def remove_cleanup_targets(targets: Iterable[Path]) -> None:
    """Remove targets returned by :func:`discover_cleanup_targets`."""
    for target in targets:
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove the listed artifacts; without this flag the command is a dry run",
    )
    parser.add_argument(
        "--include-analysis-cache",
        action="store_true",
        help="also clear workspace/cache contents (preserves .gitkeep)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    targets = discover_cleanup_targets(PROJECT_ROOT, include_analysis_cache=args.include_analysis_cache)
    mode = "Removing" if args.apply else "Would remove"
    if not targets:
        print("No generated workspace artifacts found.")
        return 0

    print(f"{mode} {len(targets)} generated workspace artifact(s):")
    for target in targets:
        print(f"  {target.relative_to(PROJECT_ROOT)}")

    if args.apply:
        remove_cleanup_targets(targets)
        print("Workspace cleanup complete.")
    else:
        print("Dry run only. Re-run with --apply to remove these paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
