"""Compact multi-line terminal progress for songs and batches."""

from __future__ import annotations

import re
import sys
import threading
import time


class ProgressBar:
    """Render batch/song progress, stages, learned ETA, and slow-task notices."""

    def __init__(
        self,
        width: int = 22,
        show_logs: bool = False,
        song: str = "Current song",
        batch_index: int = 1,
        batch_total: int = 1,
        completed_durations: list[float] | None = None,
        workers: int = 1,
        use_stems: bool = False,
        aggregate: bool = False,
    ) -> None:
        self.width = width
        self.started = time.monotonic()
        self.percent = 0.0
        self.label = "Starting"
        self.song = song
        self.batch_index = batch_index
        self.batch_total = max(1, batch_total)
        self.completed_count = max(0, batch_index - 1)
        self.completed_durations = list(completed_durations or [])
        self.workers = workers
        self.use_stems = use_stems
        self.aggregate = aggregate
        self.show_logs = show_logs
        self._interactive = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self._last_noninteractive_bucket = -1
        self._spinner_frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        self._spinner_index = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._spinner_thread: threading.Thread | None = None
        self._rendered = False
        self._last_progress_change = self.started
        self._last_percent = 0.0

    @staticmethod
    def _time(value: float) -> str:
        seconds = max(0, round(value))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def _bar(self, fraction: float) -> str:
        filled = min(self.width, round(self.width * max(0.0, min(1.0, fraction))))
        return "█" * filled + "░" * (self.width - filled)

    def _song_eta(self, elapsed: float) -> float | None:
        fraction = self.percent / 100.0
        return elapsed * (1.0 - fraction) / fraction if fraction >= 0.03 else None

    def _batch_eta(self, elapsed: float) -> float | None:
        if self.aggregate:
            fraction = self.percent / 100.0
            return elapsed * (1.0 - fraction) / fraction if fraction >= 0.03 else None
        later = max(0, self.batch_total - self.batch_index)
        estimates = list(self.completed_durations)
        if self.percent >= 5.0:
            estimates.append(elapsed / (self.percent / 100.0))
        if not estimates:
            return None
        typical = sum(estimates) / len(estimates)
        current = self._song_eta(elapsed) or typical
        return current + later * typical

    def _stage(self, name: str, complete: bool, active: bool, skipped: bool = False) -> str:
        symbol = "–" if skipped else "✓" if complete else "◉" if active else "○"
        return f"{symbol} {name}"

    def _stage_line(self) -> str:
        p = self.percent
        return "  ".join(
            (
                self._stage("Load", p >= 8, p < 8),
                self._stage("Analyze", p >= 70, 8 <= p < 70),
                self._stage("Stems", p >= 80, self.use_stems and 70 <= p < 80, not self.use_stems),
                self._stage("Select", p >= 90, 80 <= p < 90),
                self._stage("Render", p >= 97, 90 <= p < 97),
                self._stage("Export", p >= 100, 97 <= p < 100),
            )
        )

    def _lines(self) -> list[str]:
        elapsed = time.monotonic() - self.started
        batch_fraction = (
            self.percent / 100.0 if self.aggregate else (self.batch_index - 1 + self.percent / 100.0) / self.batch_total
        )
        batch_eta = self._batch_eta(elapsed)
        batch_timing = f" · ETA ~{self._time(batch_eta)}" if batch_eta is not None else ""
        batch_line = (
            f"Batch [{self._bar(batch_fraction)}] {self.completed_count}/{self.batch_total}"
            f"{batch_timing} · workers {self.workers}"
        )
        spinner = self._spinner_frames[self._spinner_index] if self.percent < 100 else "✓"
        song_eta = self._song_eta(elapsed)
        timing = f" · ETA ~{self._time(song_eta)}" if song_eta is not None else ""
        slow_for = time.monotonic() - self._last_progress_change
        slow = f" · still active {self._time(slow_for)}" if slow_for >= 15.0 else ""
        demucs = re.search(r"Demucs\s+(MPS|CPU).*?(\d{1,3})%", self.label, re.I)
        if demucs:
            device = "Apple GPU (MPS)" if demucs.group(1).upper() == "MPS" else "CPU"
            stem_fraction = min(1.0, int(demucs.group(2)) / 100.0)
            current_line = (
                f"Stems [{self._bar(stem_fraction)}] {int(stem_fraction * 100):3d}% · {device} · {self.song}{slow}"
            )
        else:
            current_line = (
                f"Song  [{self._bar(self.percent / 100.0)}] {self.percent:5.1f}% {spinner} "
                f"{self.song} · {self.label}{timing}{slow}"
            )
        return [batch_line, current_line, self._stage_line()]

    def _render_interactive(self) -> None:
        with self._lock:
            if self._rendered:
                sys.stdout.write("\033[3F")
            for line in self._lines():
                sys.stdout.write(f"\r\033[2K{line}\n")
            sys.stdout.flush()
            self._rendered = True

    def _clear_interactive_unlocked(self) -> None:
        if not self._interactive or not self._rendered:
            return
        sys.stdout.write("\033[3F")
        for _ in range(3):
            sys.stdout.write("\r\033[2K\n")
        sys.stdout.write("\033[3F")
        sys.stdout.flush()
        self._rendered = False

    def _spin(self) -> None:
        while not self._stop_event.wait(0.10):
            self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
            self._render_interactive()

    def _start_spinner(self) -> None:
        if not self._interactive or self._spinner_thread is not None:
            return
        self._spinner_thread = threading.Thread(target=self._spin, name="audio-extender-progress", daemon=True)
        self._spinner_thread.start()

    def _stop_spinner(self) -> None:
        self._stop_event.set()
        if self._spinner_thread is not None:
            self._spinner_thread.join(timeout=0.5)

    def update(self, percent: float, label: str) -> None:
        new_percent = max(self.percent, min(100.0, float(percent)))
        if new_percent > self._last_percent + 0.05:
            self._last_progress_change = time.monotonic()
            self._last_percent = new_percent
        self.percent = new_percent
        self.label = label
        if self._interactive:
            self._start_spinner()
            self._render_interactive()
        else:
            bucket = int(self.percent // 10)
            if bucket > self._last_noninteractive_bucket or self.percent >= 100:
                print(
                    f"[{self._bar(self.percent / 100.0)}] {self.percent:5.1f}% "
                    f"{self.song} · {self.label} · elapsed {self._time(time.monotonic() - self.started)}"
                )
                self._last_noninteractive_bucket = bucket

    def set_batch_state(self, completed: int, durations: list[float], song: str | None = None) -> None:
        self.completed_count = completed
        self.completed_durations = list(durations)
        if song:
            self.song = song

    def log(self, message: str) -> None:
        if not self.show_logs:
            return
        if self._interactive:
            with self._lock:
                self._clear_interactive_unlocked()
                print(message)
            self._render_interactive()
        else:
            print(message)

    def complete(self, label: str = "Complete") -> None:
        elapsed = time.monotonic() - self.started
        if self._interactive:
            self._stop_spinner()
            with self._lock:
                self._clear_interactive_unlocked()
                print(f"✓ {self.song} · {self._time(elapsed)}")
        else:
            self.update(100.0, label)

    def stop(self) -> None:
        if self._interactive:
            self._stop_spinner()
            with self._lock:
                self._clear_interactive_unlocked()

    def pause_for_input(self) -> None:
        if self._interactive:
            self._stop_spinner()
            with self._lock:
                self._clear_interactive_unlocked()

    def resume_after_input(self) -> None:
        if self._interactive:
            self._stop_event = threading.Event()
            self._spinner_thread = None
            self._start_spinner()
            self._render_interactive()
