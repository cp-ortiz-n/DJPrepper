"""Append-only candidate listening log safe for handwritten user feedback."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from audioextender.analysis.candidate_reranker import assess_candidate
from audioextender.analysis.candidate_selection import Position

FEEDBACK_NAME = "Candidate Feedback.md"
_FEEDBACK_LOCK = threading.RLock()


def _clock(seconds: float) -> str:
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _fingerprint(result: Any) -> str:
    fields = [result.source_name]
    for position in ("intro", "outro"):
        for candidate in getattr(result, f"{position}_candidates", ()):
            fields.append(
                f"{position}:{candidate.start:.3f}:{candidate.end:.3f}:"
                f"{candidate.unit_bars}:{candidate.repetitions}:"
                f"{candidate.phrase_suitability:.2f}:{candidate.loop_quality:.2f}:"
                f"{candidate.transition_quality:.2f}"
            )
        fields.extend(
            [
                str(getattr(result, f"{position}_candidate_rank")),
                str(getattr(result, f"{position}_review_reason")),
                str(getattr(result, f"{position}_review_notes")),
            ]
        )
    return hashlib.sha256("|".join(fields).encode()).hexdigest()[:16]


def _side(result: Any, position: Position) -> list[str]:
    candidates = getattr(result, f"{position}_candidates", ())
    selected = getattr(result, f"{position}_candidate_rank")
    reason = getattr(result, f"{position}_review_reason")
    notes = getattr(result, f"{position}_review_notes")
    lines = [f"### {position.title()}", ""]
    if not candidates:
        lines.extend(["No candidates were generated for this side.", ""])
    else:
        lines.extend([
            "| Rank | Source | Bars | Phrase | Loop | Transition | Checks |",
            "|---:|---|---:|---:|---:|---:|---|",
        ])
        for rank, candidate in enumerate(candidates, start=1):
            assessment = assess_candidate(candidate, position, result.preset_name)
            checks = "; ".join(assessment.warnings) or "pass"
            lines.append(
                f"| {rank} | {_clock(candidate.start)}–{_clock(candidate.end)} | "
                f"{candidate.unit_bars} × {candidate.repetitions} | "
                f"{assessment.phrase:.0f}% | {assessment.loop:.0f}% | "
                f"{assessment.transition:.0f}% | {checks} |"
            )
        lines.append("")
    chosen = "None" if selected is None else str(selected)
    lines.extend([
        f"- Generated selection: **{chosen}**",
        f"- Review reason captured by CLI: {reason or '—'}",
        f"- Review notes captured by CLI: {notes or '—'}",
        "- My final selection: ",
        "- Accepted? [ ] Yes  [ ] No",
        "- Problem tags: ",
        "- Listening notes: ",
        "",
    ])
    return lines


def append_candidate_feedback(output_directory: Path, results: Iterable[Any]) -> Path:
    """Append only unseen candidate generations; never rewrite user text."""
    with _FEEDBACK_LOCK:
        return _append_candidate_feedback_locked(output_directory, results)


def _append_candidate_feedback_locked(output_directory: Path, results: Iterable[Any]) -> Path:
    report_directory = output_directory.expanduser().resolve() / "reports"
    report_directory.mkdir(parents=True, exist_ok=True)
    path = report_directory / FEEDBACK_NAME
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    blocks: list[str] = []
    if not existing:
        blocks.extend([
            "# Candidate Feedback",
            "",
            "This is an append-only listening log. Edit the `My final selection`, "
            "checkboxes, tags, and notes directly. DJ Library Studio will not rewrite "
            "existing sections. A changed candidate set creates a new generation.",
            "",
            "Suggested tags: `good`, `chopped`, `wrong phrase`, `vocals`, "
            "`buildup`, `bass reset`, `too repetitive`, `other`.",
            "",
        ])
    for result in results:
        token = _fingerprint(result)
        marker = f"<!-- generation:{token} -->"
        if marker in existing:
            continue
        blocks.extend([
            marker,
            f"## {result.source_name} — {datetime.now().astimezone().isoformat(timespec='minutes')}",
            "",
            f"Style/preset: {result.detected_style or '—'} / {result.preset_name or 'default'}",
            "",
            *_side(result, "intro"),
            *_side(result, "outro"),
            "---",
            "",
        ])
    if blocks:
        with path.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("\n".join(blocks).rstrip() + "\n")
    return path


def append_web_feedback(
    output_directory: Path,
    source_name: str,
    position: str,
    candidate_rank: int | None,
    accepted: bool,
    tags: str,
    notes: str,
) -> Path:
    """Append a web listening decision without rewriting handwritten feedback."""
    path = output_directory.expanduser().resolve() / "reports" / FEEDBACK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "",
        f"### Web review — {source_name}",
        "",
        f"- Recorded: {datetime.now().astimezone().isoformat(timespec='minutes')}",
        f"- Side: {position}",
        f"- Candidate: {candidate_rank if candidate_rank is not None else 'None'}",
        f"- Accepted: {'Yes' if accepted else 'No'}",
        f"- Tags: {tags or '—'}",
        f"- Notes: {notes or '—'}",
        "",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return path
