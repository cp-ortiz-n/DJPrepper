"""Serial and multiprocessing execution for prepared track jobs."""

from __future__ import annotations

import multiprocessing
import queue
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from typing import Any

from helpers.config import EditConfig
from helpers.models import FileResult
from helpers.progress import ProgressBar
from helpers.track_processor import process_file

TrackJob = tuple[Path, Path, float | None, float | None, float | None]


class _QueueProgress:
    def __init__(self, events: Any, song: str) -> None:
        self.events = events
        self.song = song

    def update(self, percent: float, label: str) -> None:
        self.events.put(("progress", self.song, float(percent), label))

    def log(self, message: str) -> None:
        return

    def complete(self, label: str = "Complete") -> None:
        self.update(100.0, label)

    def stop(self) -> None:
        return

    def pause_for_input(self) -> None:
        return

    def resume_after_input(self) -> None:
        return


def _process_job(job: TrackJob, config: EditConfig, events: Any) -> FileResult:
    source, output, intro_before, outro_after, outro_before = job
    return process_file(
        source,
        output,
        config,
        _QueueProgress(events, source.name),
        intro_before,
        outro_after,
        outro_before,
    )


class BatchRunner:
    """Run prepared jobs while keeping progress output collision-free."""

    def run(
        self, jobs: list[TrackJob], config: EditConfig, workers: int
    ) -> tuple[list[FileResult], list[tuple[Path, str]]]:
        if workers > 1 and len(jobs) > 1:
            return self._parallel(jobs, config, min(workers, len(jobs)))
        return self._serial(jobs, config)

    @staticmethod
    def _serial(
        jobs: list[TrackJob], config: EditConfig
    ) -> tuple[list[FileResult], list[tuple[Path, str]]]:
        results: list[FileResult] = []
        failures: list[tuple[Path, str]] = []
        completed_durations: list[float] = []
        for number, job in enumerate(jobs, start=1):
            source, output, intro_before, outro_after, outro_before = job
            print(f"\n[{number}/{len(jobs)}] {source.name}")
            try:
                progress = ProgressBar(
                    show_logs=config.choose_candidates,
                    song=source.name,
                    batch_index=number,
                    batch_total=len(jobs),
                    completed_durations=completed_durations,
                    workers=1,
                    use_stems=config.use_stems,
                )
                result = process_file(
                    source,
                    output,
                    config,
                    progress,
                    intro_before,
                    outro_after,
                    outro_before,
                )
                results.append(result)
                completed_durations.append(result.elapsed)
            except (FileNotFoundError, ValueError, RuntimeError) as error:
                print(f"Failed: {error}", file=sys.stderr)
                failures.append((source, str(error)))
        return results, failures

    @staticmethod
    def _parallel(
        jobs: list[TrackJob], config: EditConfig, workers: int
    ) -> tuple[list[FileResult], list[tuple[Path, str]]]:
        states = {job[0].name: 0.0 for job in jobs}
        progress = ProgressBar(
            song=f"{workers} active workers",
            batch_total=len(jobs),
            workers=workers,
            use_stems=config.use_stems,
            aggregate=True,
        )
        progress.update(0, f"Starting {workers} workers")
        failures: list[tuple[Path, str]] = []
        results: list[FileResult] = []

        with multiprocessing.Manager() as manager:
            events = manager.Queue()
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_process_job, job, config, events): job[0]
                    for job in jobs
                }
                remaining = set(futures)
                while remaining:
                    BatchRunner._drain_events(events, states, results, jobs, progress)
                    done, remaining = wait(
                        remaining, timeout=0.10, return_when=FIRST_COMPLETED
                    )
                    for future in done:
                        source = futures[future]
                        try:
                            result = future.result()
                            states[source.name] = 100.0
                            results.append(result)
                            progress.set_batch_state(
                                len(results),
                                [item.elapsed for item in results],
                                source.name,
                            )
                        except Exception as error:
                            states[source.name] = 100.0
                            failures.append((source, str(error)))
                            progress.log(f"Failed — {source.name}: {error}")
                BatchRunner._drain_events(events, states, results, jobs, progress)

        progress.set_batch_state(
            len(results), [result.elapsed for result in results], "Batch complete"
        )
        progress.complete(f"{len(results)}/{len(jobs)} songs complete")
        return results, failures

    @staticmethod
    def _drain_events(events, states, results, jobs, progress) -> None:
        while True:
            try:
                kind, song, value, *rest = events.get_nowait()
            except queue.Empty:
                return
            if kind == "progress":
                states[song] = value
                label = rest[0] if rest else "Processing"
                progress.set_batch_state(
                    len(results), [result.elapsed for result in results], song
                )
                progress.update(
                    sum(states.values()) / len(states),
                    f"{len(results)}/{len(jobs)} done · {label}",
                )
            else:
                progress.log(f"{song}: {value}")
