"""Cue-sheet and rekordbox XML export for completed extended edits."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate
from audioextender.processing.extended_edit import adaptive_crossfade_ms


@dataclass(frozen=True)
class CuePoint:
    name: str
    start: float
    end: float | None = None
    kind: str = "memory"
    purpose: str = ""
    confidence: float | None = None


def build_cue_points(
    analysis: TrackAnalysis,
    intro: SectionCandidate | None,
    outro: SectionCandidate | None,
    crossfade_ms: float,
    output_duration: float,
) -> tuple[CuePoint, ...]:
    """Map analysis and inserted phrases onto the completed WAV timeline."""
    intro_added = 0.0
    if intro is not None:
        if intro.splice_mode == "redrum":
            intro_fade = 0.0
            intro_added = intro.repetitions * max(0.0, intro.end - intro.start)
        else:
            intro_fade = adaptive_crossfade_ms(intro, crossfade_ms) / 1000.0
            intro_added = intro.repetitions * max(
                0.0, intro.end - intro.start - intro_fade
            )

    def original_to_output(source_time: float) -> float:
        if intro is not None and intro.splice_mode == "redrum":
            return source_time + intro_added
        if intro is None or source_time < intro.start:
            return source_time
        # The first inserted copy occupies the source phrase's original clock
        # position. Later untouched source material is shifted by the full add.
        if source_time <= intro.end:
            return source_time
        return source_time + intro_added

    cues: list[CuePoint] = []
    downbeats: Any = getattr(analysis, "downbeat_indices", ())
    beat_times: Any = getattr(analysis, "beat_times", ())
    grid_confidence = float(getattr(analysis, "beat_grid_confidence", 0.0))
    if len(downbeats) and grid_confidence >= 55.0:
        beat_index = int(downbeats[0])
        if beat_index < len(beat_times):
            cues.append(CuePoint(
                "Beat Grid Anchor",
                original_to_output(float(beat_times[beat_index])),
                purpose="First observed downbeat used to anchor the inferred 4/4 grid",
                confidence=grid_confidence / 100.0,
            ))

    if intro is not None:
        unit = intro.end - intro.start
        if intro.splice_mode == "redrum":
            cues.extend((
                CuePoint("Mix In", 0.0, purpose="Suggested DJ mix-in point",
                         confidence=intro.boundary_grid_confidence),
                CuePoint("Extended Intro", 0.0, intro_added,
                         kind="loop", purpose="Generated progressive redrum intro",
                         confidence=intro.loop_quality / 100.0),
                CuePoint("Original Song Starts", intro_added,
                         purpose="Original source begins fading into the redrum",
                         confidence=intro.energy_context_match),
            ))
        else:
            cues.extend((
                CuePoint("Mix In", intro.start, purpose="Suggested DJ mix-in point",
                         confidence=intro.boundary_grid_confidence),
                CuePoint("Extended Intro", intro.start, intro.start + intro_added,
                         kind="loop", purpose="Added intro material",
                         confidence=intro.loop_quality / 100.0),
                CuePoint("Original Song Starts", intro.start + intro_added,
                         purpose="Added intro ends and untouched source resumes",
                         confidence=intro.energy_context_match),
            ))

    if outro is not None:
        fade = adaptive_crossfade_ms(outro, crossfade_ms) / 1000.0
        unit = max(0.0, outro.end - outro.start - fade)
        original_outro_start = original_to_output(outro.start)
        extension_start = original_to_output(outro.end) - fade
        extension_end = min(output_duration, extension_start + outro.repetitions * unit)
        cues.extend((
            CuePoint("Mix Out", original_outro_start,
                     purpose="Suggested DJ mix-out point",
                     confidence=outro.boundary_grid_confidence),
            CuePoint("Extended Outro Starts", extension_start,
                     purpose="First added outro repetition begins",
                     confidence=outro.energy_context_match),
            CuePoint("Extended Outro", extension_start,
                     min(extension_end, extension_start + unit), kind="loop",
                     purpose="Saved loop for the selected outro unit",
                     confidence=outro.loop_quality / 100.0),
            CuePoint("Original Ending Resumes", extension_end,
                     purpose="Untouched natural song ending resumes",
                     confidence=outro.tail_release_compatibility),
        ))

    # Remove nearly identical memory cues while retaining saved loops.
    unique: list[CuePoint] = []
    for cue in sorted(cues, key=lambda item: (item.start, item.kind != "loop")):
        if cue.kind != "loop" and any(
            existing.kind != "loop" and abs(existing.start - cue.start) < 0.025
            for existing in unique
        ):
            continue
        unique.append(cue)
    return tuple(unique)


def write_cue_sheet(
    path: Path,
    source: Path,
    output: Path,
    metadata: dict[str, Any],
    cues: Iterable[CuePoint],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": "DJ Library Studio cue sheet",
        "version": 1,
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        **metadata,
        "cues": [asdict(cue) for cue in cues],
    }
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_rekordbox_xml(results: Iterable[Any], path: Path) -> None:
    """Write the documented rekordbox XML playlist-sharing format."""
    tracks = [result for result in results if result.full_exported and result.output.exists()]
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(
        root, "PRODUCT", Name="DJ Library Studio", Version="1.0", Company="Local"
    )
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))
    for track_id, result in enumerate(tracks, start=1):
        attributes = {
            "TrackID": str(track_id),
            "Name": str(getattr(result, "title", "") or result.output.stem),
            "Kind": "WAV File",
            "Size": str(result.output.stat().st_size),
            "TotalTime": str(round(result.output_duration)),
            "AverageBpm": f"{result.bpm:.3f}",
            "Tonality": result.key_label,
            "Location": result.output.resolve().as_uri(),
        }
        if getattr(result, "artist", ""):
            attributes["Artist"] = str(result.artist)
        if getattr(result, "genre", ""):
            attributes["Genre"] = str(result.genre)
        if getattr(result, "album", ""):
            attributes["Album"] = str(result.album)
        track = ET.SubElement(
            collection,
            "TRACK",
            **attributes,
        )
        first_downbeat = next(
            (
                cue for cue in result.cue_points
                if cue.name in {"Beat Grid Anchor", "First Reliable Downbeat"}
            ),
            None,
        )
        if first_downbeat is not None:
            ET.SubElement(
                track, "TEMPO", Inizio=f"{first_downbeat.start:.6f}",
                Bpm=f"{result.bpm:.6f}", Metro="4/4", Battito="1",
            )
        for cue in result.cue_points:
            attributes = {
                "Name": cue.name,
                "Type": "4" if cue.kind == "loop" else "0",
                "Start": f"{cue.start:.6f}",
                "Num": "-1",
            }
            if cue.end is not None:
                attributes["End"] = f"{cue.end:.6f}"
            ET.SubElement(track, "POSITION_MARK", **attributes)

    playlists = ET.SubElement(root, "PLAYLISTS")
    playlist_root = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    playlist = ET.SubElement(
        playlist_root, "NODE", Type="1", Name="DJ Library Studio Edits",
        KeyType="0", Entries=str(len(tracks)),
    )
    for track_id in range(1, len(tracks) + 1):
        ET.SubElement(playlist, "TRACK", Key=str(track_id))

    ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
