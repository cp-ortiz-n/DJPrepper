"""Failure cleanup policy for single-track processing."""

from __future__ import annotations

from audioextender.core.interfaces import ProgressReporter


class ProcessingFailureCleanup:
    """Return progress reporters to a stopped state before errors escape."""

    @staticmethod
    def run(progress: ProgressReporter) -> None:
        progress.stop()
