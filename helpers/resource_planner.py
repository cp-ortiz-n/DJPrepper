"""Choose safe batch concurrency from track and machine characteristics."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

GIB = 1024 ** 3


@dataclass(frozen=True)
class WorkloadEstimate:
    path: Path
    duration: float
    working_bytes: int


def _physical_memory() -> int:
    """Return macOS physical RAM, falling back conservatively to 8 GiB."""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
            check=True, timeout=2,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 8 * GIB


def estimate_track(path: Path) -> WorkloadEstimate:
    """Estimate peak analysis memory from decoded audio metadata.

    Spectrograms and HPSS working arrays are much larger than the source MP3.
    Ten decoded copies plus a fixed numerical-library allowance is deliberately
    conservative and works across compressed and lossless inputs.
    """
    try:
        info = sf.info(path)
        duration = float(info.duration)
        decoded_bytes = int(info.frames) * max(2, int(info.channels)) * 4
    except (RuntimeError, sf.LibsndfileError):
        duration = 0.0
        decoded_bytes = max(path.stat().st_size * 12, 128 * 1024 ** 2)
    working_bytes = max(900 * 1024 ** 2, decoded_bytes * 10 + 384 * 1024 ** 2)
    return WorkloadEstimate(path, duration, working_bytes)


def choose_worker_count(
    paths: list[Path], requested: str, use_stems: bool
) -> tuple[int, list[WorkloadEstimate], int]:
    estimates = [estimate_track(path) for path in paths]
    memory = _physical_memory()
    if requested != "auto":
        return min(int(requested), max(1, len(paths))), estimates, memory
    if use_stems:
        return 1, estimates, memory

    # Keep over half of RAM available to macOS, Python overhead, and DJ apps.
    budget = int(memory * 0.42)
    largest = max((estimate.working_bytes for estimate in estimates), default=budget)
    memory_limit = max(1, budget // max(largest, 1))
    workers = min(3, max(1, len(paths)), memory_limit)
    return workers, estimates, memory
