"""Persistent human-readable and machine-readable processing reports."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_DIRECTORY_NAME = "reports"
REPORT_JSON_NAME = "processing_report.json"
REPORT_MARKDOWN_NAME = "Processing Report.md"
_REPORT_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _candidate(
    candidate: Any,
    construction: str,
    automatic: bool,
    output_start: float | None,
    output_end: float | None,
) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "source_start": candidate.start,
        "source_end": candidate.end,
        "output_start": output_start,
        "output_end": output_end,
        "loop_quality": candidate.loop_quality,
        "phrase_suitability": candidate.phrase_suitability,
        "transition_quality": candidate.transition_quality,
        "instrumental_construction_quality": (
            candidate.instrumental_loop_quality if construction == "instrumental stems" else None
        ),
        "instrumentalness": candidate.instrumentalness,
        "unit_bars": candidate.unit_bars,
        "extension_bars": candidate.unit_bars * candidate.repetitions,
        "copies": candidate.repetitions,
        "automatic_length": automatic,
        "energy": candidate.energy_shape,
        "buildup_risk": candidate.buildup_risk,
        "bass_reset_risk": candidate.bass_reset_risk,
        "context_match": candidate.energy_context_match,
        "chord_return": candidate.chord_return_compatibility,
        "resolution_risk": candidate.harmonic_resolution_risk,
        "section": candidate.section_label,
        "section_confidence": candidate.section_confidence,
        "arrangement_fit": candidate.arrangement_fit,
        "local_grid": candidate.local_grid_confidence,
        "boundary_grid": candidate.boundary_grid_confidence,
        "regional_style": candidate.regional_style,
        "regional_compatibility": candidate.regional_compatibility,
        "regional_boundary_risk": candidate.regional_boundary_risk,
        "vocal_coverage": candidate.vocal_coverage,
        "vocal_boundary_risk": candidate.vocal_boundary_risk,
        "splice_mode": candidate.splice_mode,
        "construction": construction,
    }


def _result_record(result: Any) -> dict[str, Any]:
    return {
        "source_name": result.source_name,
        "output_name": result.output.name,
        "output_path": str(result.output.resolve()),
        "wav_name": result.wav_output.name if result.wav_output else None,
        "wav_path": str(result.wav_output.resolve()) if result.wav_output else None,
        "status": "updated",
        "updated_at": _now(),
        "processing_seconds": result.elapsed,
        "stage_timings": dict(getattr(result, "stage_timings", ())),
        "duration_seconds": result.output_duration,
        "bpm": result.bpm,
        "key": result.key_label,
        "key_confidence": result.key_confidence / 100.0,
        "key_candidates": list(getattr(result, "key_candidates", ())),
        "beats": result.beats,
        "bars": result.bars,
        "beat_grid_confidence": result.beat_grid_confidence / 100.0,
        "tempo_drift": result.tempo_drift_percent / 100.0,
        "groove": result.groove_label,
        "timing": result.timing_label,
        "downbeat_continuity": result.downbeat_continuity / 100.0,
        "preset": result.preset_name,
        "detected_style": result.detected_style,
        "preset_reason": result.preset_reason,
        "section_profiles": [asdict(profile) for profile in getattr(result, "section_profiles", ())],
        "arrangement_sections": [asdict(section) for section in getattr(result, "arrangement_sections", ())],
        "dj_readiness": {
            "intro_mixable_bars": result.intro_existing_mix_bars,
            "outro_mixable_bars": result.outro_existing_mix_bars,
            "intro_preserved": result.intro_already_dj_ready,
            "outro_preserved": result.outro_already_dj_ready,
        },
        "stem_reliability": result.stem_reliability,
        "cache": {
            "track_analysis": result.analysis_cache_hit,
            "vocal_analysis": result.vocal_cache_hit,
        },
        "intro": _candidate(
            result.intro,
            result.intro_construction,
            result.automatic_intro_length,
            result.intro_output_start,
            result.intro_output_end,
        ),
        "intro_disabled_reason": result.intro_rejection_reason,
        "intro_candidate_rank": result.intro_candidate_rank,
        "intro_fallback": result.intro_fallback,
        "outro": _candidate(
            result.outro,
            result.outro_construction,
            result.automatic_outro_length,
            result.outro_output_start,
            result.outro_output_end,
        ),
        "outro_disabled_reason": result.outro_rejection_reason,
        "outro_candidate_rank": result.outro_candidate_rank,
        "outro_fallback": result.outro_fallback,
        "mix_in": result.mix_in,
        "mix_out": result.mix_out,
        "cue_sheet": str(result.cue_sheet.resolve()) if result.cue_sheet else None,
        "cues": [asdict(cue) for cue in result.cue_points],
    }


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes:02d}:{remainder:02d}"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{100.0 * value:.0f}%"


def _candidate_markdown(label: str, data: dict[str, Any] | None, reason: str | None) -> list[str]:
    if data is None:
        lines = [f"### {label}", "", "Disabled."]
        if reason:
            lines.append(f" Reason: {reason}.")
        return lines + [""]
    quality = (
        data["instrumental_construction_quality"]
        if data["instrumental_construction_quality"] is not None
        else data["loop_quality"]
    )
    return [
        f"### {label}",
        "",
        f"- Source: {_clock(data['source_start'])}–{_clock(data['source_end'])}",
        f"- Extended WAV placement: {_clock(data.get('output_start'))}–{_clock(data.get('output_end'))}",
        f"- Phrase: {data.get('phrase_suitability', 0):.0f}% · "
        f"Loop: {quality:.0f}% · Transition: "
        f"{data.get('transition_quality', 0):.0f}%",
        f"- Construction: {data['construction']} · Splice: {data['splice_mode']}",
        f"- Material: {data['unit_bars']} unique bars · {data['extension_bars']} added bars · {data['copies']} copies",
        f"- Section: {data['section']} ({_percent(data['section_confidence'])}) · "
        f"Arrangement fit: {data['arrangement_fit']:+.0%}",
        f"- Energy: {data['energy']} · Buildup: {_percent(data['buildup_risk'])} · "
        f"Bass reset: {_percent(data['bass_reset_risk'])} · Context: {_percent(data['context_match'])}",
        f"- Harmony: chord return {_percent(data['chord_return'])} · "
        f"Resolution risk {_percent(data['resolution_risk'])}",
        f"- Grid: local {_percent(data['local_grid'])} · Boundary {_percent(data['boundary_grid'])}",
        f"- Regional context: {data.get('regional_style', 'unknown')} · "
        f"Compatibility {_percent(data.get('regional_compatibility'))} · "
        f"Boundary risk {_percent(data.get('regional_boundary_risk'))}",
        f"- Vocals: coverage {_percent(data['vocal_coverage'])} · "
        f"Boundary risk {_percent(data['vocal_boundary_risk'])}",
        "",
    ]


def _render_markdown(document: dict[str, Any]) -> str:
    lines = [
        "# DJPrepper Processing Report",
        "",
        f"Last report update: {document['updated_at']}",
        "",
        "This report is persistent: skipped songs retain their last analysis, while rebuilt songs replace "
        "their previous record.",
        "",
        "| Song | Status | BPM | Key | Intro | Outro | Mix cues |",
        "|---|---|---:|---|---|---|---|",
    ]
    records = sorted(document["songs"].values(), key=lambda item: item["source_name"].casefold())
    for record in records:
        intro = record.get("intro")
        outro = record.get("outro")
        intro_text = "disabled" if intro is None else f"{intro['extension_bars']} bars / {intro['loop_quality']:.0f}%"
        outro_text = "disabled" if outro is None else f"{outro['extension_bars']} bars / {outro['loop_quality']:.0f}%"
        cues = f"{_clock(record.get('mix_in'))} / {_clock(record.get('mix_out'))}"
        lines.append(
            f"| {record['source_name']} | {record['status']} | {record.get('bpm', 0):.1f} | "
            f"{record.get('key') or '—'} | {intro_text} | {outro_text} | {cues} |"
        )
    for record in records:
        lines.extend(["", f"## {record['source_name']}", ""])
        if record["status"] == "skipped":
            lines.extend(["> Skipped in the latest run; the analysis below is from the last successful update.", ""])
        lines.extend(
            [
                f"- Output: `{record['output_name']}`",
                f"- Source WAV: `{record.get('wav_name') or '—'}`",
                f"- Last processed: {record.get('updated_at', 'unknown')} · "
                f"Processing time: {_clock(record.get('processing_seconds'))}",
                f"- BPM: {record.get('bpm', 0):.1f} · Key: {record.get('key') or '—'} "
                f"({_percent(record.get('key_confidence'))})",
                f"- Beat grid: {_percent(record.get('beat_grid_confidence'))} · "
                f"Tempo drift: {_percent(record.get('tempo_drift'))} · "
                f"Downbeat continuity: {_percent(record.get('downbeat_continuity'))}",
                f"- Groove: {record.get('groove') or '—'} · Timing: {record.get('timing') or '—'} · "
                f"Preset: {record.get('preset') or 'default'}",
                "- Section behavior: "
                + " · ".join(
                    f"{profile['name']} {profile['style']} ({_percent(profile['confidence'])})"
                    for profile in record.get("section_profiles", [])
                )
                if record.get("section_profiles")
                else "- Section behavior: unavailable for this older analysis",
                f"- Existing mixing room: intro "
                f"{record.get('dj_readiness', {}).get('intro_mixable_bars', 0)} bars · outro "
                f"{record.get('dj_readiness', {}).get('outro_mixable_bars', 0)} bars",
                f"- Suggested cues: mix in {_clock(record.get('mix_in'))} · mix out {_clock(record.get('mix_out'))}",
                "",
            ]
        )
        lines.extend(_candidate_markdown("Intro", record.get("intro"), record.get("intro_disabled_reason")))
        lines.extend(_candidate_markdown("Outro", record.get("outro"), record.get("outro_disabled_reason")))
    return "\n".join(lines).rstrip() + "\n"


def update_processing_report(
    output_directory: Path,
    results: Iterable[Any],
    skipped: Iterable[tuple[Path, Path]],
) -> tuple[Path, Path]:
    with _REPORT_LOCK:
        return _update_processing_report_locked(output_directory, results, skipped)


def _update_processing_report_locked(
    output_directory: Path,
    results: Iterable[Any],
    skipped: Iterable[tuple[Path, Path]],
) -> tuple[Path, Path]:
    report_directory = output_directory.expanduser().resolve() / REPORT_DIRECTORY_NAME
    json_path = report_directory / REPORT_JSON_NAME
    markdown_path = report_directory / REPORT_MARKDOWN_NAME
    document: dict[str, Any] = {"version": 1, "updated_at": _now(), "songs": {}}
    if json_path.exists():
        try:
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(loaded.get("songs"), dict):
                document["songs"] = loaded["songs"]
        except (OSError, ValueError, TypeError):
            pass
    for result in results:
        document["songs"][result.source_name.casefold()] = _result_record(result)
    for source, output in skipped:
        key = source.name.casefold()
        if key in document["songs"]:
            document["songs"][key]["status"] = "skipped"
            document["songs"][key]["last_seen_at"] = _now()
        else:
            document["songs"][key] = {
                "source_name": source.name,
                "output_name": output.name,
                "output_path": str(output.resolve()),
                "status": "skipped",
                "updated_at": None,
                "processing_seconds": None,
                "bpm": 0.0,
                "key": None,
                "intro": None,
                "outro": None,
                "mix_in": None,
                "mix_out": None,
            }
    document["updated_at"] = _now()
    _atomic_text(json_path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    _atomic_text(markdown_path, _render_markdown(document))
    return markdown_path, json_path
