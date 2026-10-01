"""Command-line entry point for single-file and batch extended edits."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from audioextender.audio.loading import SUPPORTED_EXTENSIONS
from audioextender.processing.batch_runner import BatchRunner, TrackJob
from audioextender.infrastructure.cache import clear_cache
from audioextender.core.config_factory import ConfigFactory
from audioextender.library.cue_export import write_rekordbox_xml
from audioextender.reporting.feedback import append_candidate_feedback
from audioextender.core.models import FileResult
from audioextender.core.presets import PRESETS
from audioextender.reporting.processing import update_processing_report
from audioextender.analysis.resource_planner import GIB, choose_worker_count
from audioextender.library.track_overrides import load_track_overrides
from settings import (
    CACHE_FOLDER_NAME,
    DEFAULT_AUTO_BAR_SELECTION,
    DEFAULT_CANDIDATE_COUNT,
    DEFAULT_EXPORT_CUES,
    DEFAULT_OVERWRITE,
    DEFAULT_PCM_BITS,
    DEFAULT_PRESET,
    DEFAULT_PREVIEW_SECONDS,
    DEFAULT_WORKERS,
    EXTENDED_OUTPUT_FOLDER_NAME,
    INPUT_FOLDER_NAME,
    OUTPUT_FOLDER_NAME,
    REKORDBOX_XML_FILENAME,
    SUPPORTED_BAR_COUNTS,
    SUPPORTED_PCM_BITS,
    SUPPORTED_WORKER_CHOICES,
    TRACK_OVERRIDES_FILENAME,
    WAV_OUTPUT_FOLDER_NAME,
)

PROJECT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_INPUT_DIRECTORY = PROJECT_DIRECTORY / INPUT_FOLDER_NAME
DEFAULT_OUTPUT_DIRECTORY = PROJECT_DIRECTORY / OUTPUT_FOLDER_NAME
DEFAULT_OVERRIDES_FILE = PROJECT_DIRECTORY / TRACK_OVERRIDES_FILENAME
DEFAULT_CACHE_DIRECTORY = PROJECT_DIRECTORY / CACHE_FOLDER_NAME


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create beat-aligned DJ extended edits. With no filenames, every "
            "supported audio file in the input folder is processed."
        )
    )
    parser.add_argument(
        "inputs", nargs="*", type=Path,
        help="Optional audio files; defaults to every supported file in ./input",
    )
    parser.add_argument(
        "--intro-bars", type=int, choices=SUPPORTED_BAR_COUNTS,
        default=None,
    )
    parser.add_argument(
        "--outro-bars", type=int, choices=SUPPORTED_BAR_COUNTS,
        default=None,
    )
    parser.add_argument(
        "--auto-bars", action=argparse.BooleanOptionalAction,
        default=DEFAULT_AUTO_BAR_SELECTION,
        help=(
            "Automatically choose 2/4/8/16/32 bars up to the configured "
            "length unless that side is explicitly set (default: enabled)"
        ),
    )
    parser.add_argument(
        "--use-stems", action=argparse.BooleanOptionalAction, default=None,
        help="Enable or disable Demucs vocal-energy scoring",
    )
    parser.add_argument(
        "--preset", choices=("auto", *PRESETS), default=DEFAULT_PRESET,
        help="Editing strategy; explicit bar and stem options override it",
    )
    parser.add_argument(
        "--input-dir", type=Path, default=DEFAULT_INPUT_DIRECTORY,
        help="Batch input folder (default: ./input)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY,
        help="Destination folder (default: ./output)",
    )
    parser.add_argument(
        "--bit-depth", type=int, choices=SUPPORTED_PCM_BITS, default=DEFAULT_PCM_BITS
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=DEFAULT_OVERWRITE,
        help="Replace existing extended edits instead of skipping them",
    )
    parser.add_argument(
        "--workers", choices=SUPPORTED_WORKER_CHOICES, default=DEFAULT_WORKERS,
        help="Concurrent songs (default: auto; Demucs auto mode uses one)",
    )
    parser.add_argument(
        "--intro-before", type=float,
        help="Hard latest source time, in seconds, for intro material",
    )
    parser.add_argument(
        "--outro-after", type=float,
        help="Hard earliest source time, in seconds, for outro material",
    )
    parser.add_argument(
        "--outro-before", type=float,
        help="Hard latest source time, in seconds, for outro material",
    )
    parser.add_argument(
        "--overrides", type=Path, default=DEFAULT_OVERRIDES_FILE,
        help="Per-track musical boundaries JSON (default: ./track_overrides.json)",
    )
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--no-cache", action="store_true",
        help="Do not read or write analysis cache files for this run",
    )
    cache_group.add_argument(
        "--refresh-cache", action="store_true",
        help="Recompute analysis and replace cache entries",
    )
    parser.add_argument(
        "--clear-cache", action="store_true",
        help="Delete cached analysis files and exit",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=DEFAULT_CACHE_DIRECTORY,
        help="Analysis cache folder (default: ./cache)",
    )
    preview_group = parser.add_mutually_exclusive_group()
    preview_group.add_argument(
        "--previews", action="store_true",
        help="Export short intro/outro splice previews with the full edit",
    )
    preview_group.add_argument(
        "--preview-only", action="store_true",
        help="Export splice previews without writing the full extended WAV",
    )
    parser.add_argument(
        "--preview-seconds", type=float, default=DEFAULT_PREVIEW_SECONDS,
        help="Seconds included before and after each previewed splice",
    )
    parser.add_argument(
        "--cues", action=argparse.BooleanOptionalAction,
        default=DEFAULT_EXPORT_CUES,
        help="Write JSON cue sheets and a rekordbox XML playlist (default: enabled)",
    )
    parser.add_argument(
        "--intro-candidate", type=int,
        choices=tuple(range(0, DEFAULT_CANDIDATE_COUNT + 1)), default=1,
        help="Use ranked intro candidate 1–3, or 0 for none (default: 1)",
    )
    parser.add_argument(
        "--outro-candidate", type=int,
        choices=tuple(range(0, DEFAULT_CANDIDATE_COUNT + 1)), default=1,
        help="Use ranked outro candidate 1–3, or 0 for none (default: 1)",
    )
    parser.add_argument(
        "--choose-candidates", action="store_true",
        help="Show ranked choices and ask which intro/outro to use",
    )
    parser.add_argument(
        "--review", action="store_true",
        help=(
            "Audition candidates, choose interactively, and capture listening "
            "reasons/notes in the persistent feedback document"
        ),
    )
    return parser


def _discover_inputs(paths: list[Path], input_directory: Path) -> list[Path]:
    """Resolve explicit inputs or discover supported files in the batch folder."""
    if paths:
        resolved = [path.expanduser().resolve() for path in paths]
        unsupported = [path for path in resolved if path.suffix.lower() not in SUPPORTED_EXTENSIONS]
        if unsupported:
            names = ", ".join(path.name for path in unsupported)
            raise ValueError(f"Unsupported input format: {names}")
        return resolved

    directory = input_directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return sorted(
        path.resolve()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _output_path(source: Path, output_directory: Path) -> Path:
    output_directory = output_directory.expanduser().resolve()
    extended_directory = output_directory / EXTENDED_OUTPUT_FOLDER_NAME
    extended_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / WAV_OUTPUT_FOLDER_NAME).mkdir(parents=True, exist_ok=True)
    return extended_directory / f"{source.stem} (Extended Edit).wav"


def _wav_path(source: Path, output_directory: Path) -> Path:
    return output_directory.expanduser().resolve() / WAV_OUTPUT_FOLDER_NAME / f"{source.stem}.wav"


def _format_time(seconds: float) -> str:
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _format_duration(seconds: float) -> str:
    minutes, remainder = divmod(max(0, round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes:02d}:{remainder:02d}"


def _print_compact_results(results: list[FileResult], total_elapsed: float) -> None:
    """Keep the terminal actionable; the persistent report holds diagnostics."""
    if not results:
        return
    print("\nCompleted edits")
    print("=" * 72)
    for result in sorted(results, key=lambda item: item.source_name.casefold()):
        print(
            f"✓ {result.source_name}  ·  {_format_duration(result.elapsed)}  ·  "
            f"{result.bpm:.1f} BPM  ·  {result.key_label}"
        )
        sides = []
        if result.intro is None:
            sides.append("intro disabled")
        else:
            bars = result.intro.unit_bars * result.intro.repetitions
            quality = (
                result.intro.instrumental_loop_quality
                if result.intro_construction == "instrumental stems"
                else result.intro.loop_quality
            )
            sides.append(f"intro {bars} bars / {quality:.0f}%")
        if result.outro is None:
            sides.append("outro disabled")
        else:
            bars = result.outro.unit_bars * result.outro.repetitions
            quality = (
                result.outro.instrumental_loop_quality
                if result.outro_construction == "instrumental stems"
                else result.outro.loop_quality
            )
            sides.append(f"outro {bars} bars / {quality:.0f}%")
        print(f"  {'  ·  '.join(sides)}")
        warnings = []
        if result.intro_rejection_reason:
            warnings.append(f"intro: {result.intro_rejection_reason}")
        if result.outro_rejection_reason:
            warnings.append(f"outro: {result.outro_rejection_reason}")
        if warnings:
            print(f"  Decision: {'; '.join(warnings)}")
        cues = []
        if result.mix_in is not None:
            cues.append(f"mix in {_format_time(result.mix_in)}")
        if result.mix_out is not None:
            cues.append(f"mix out {_format_time(result.mix_out)}")
        if cues:
            print(f"  {'  ·  '.join(cues)}")
    print("-" * 72)
    print(f"Total batch time: {_format_duration(total_elapsed)}")


def run(args: argparse.Namespace) -> int:
    batch_started = time.monotonic()
    cache_directory = args.cache_dir.expanduser().resolve()
    if args.clear_cache:
        removed = clear_cache(cache_directory)
        print(f"Cleared {removed} cached file{'s' if removed != 1 else ''} from {cache_directory}")
        return 0
    config = ConfigFactory.from_arguments(args)
    track_overrides = load_track_overrides(args.overrides.expanduser().resolve())
    sources = _discover_inputs(args.inputs, args.input_dir)
    if not sources:
        print(f"No supported audio files found in: {args.input_dir.expanduser().resolve()}")
        print("Add MP3, WAV, FLAC, or AIFF files there, then run this command again.")
        return 0

    print(f"Found {len(sources)} song{'s' if len(sources) != 1 else ''} to process")
    workers, estimates, physical_memory = choose_worker_count(
        sources, args.workers, config.use_stems
    )
    if config.choose_candidates:
        workers = 1
    largest_gib = max((estimate.working_bytes for estimate in estimates), default=0) / GIB
    mode = "automatic" if args.workers == "auto" else "manual"
    print(
        f"Workers: {workers} ({mode}; {physical_memory / GIB:.0f} GB RAM, "
        f"largest estimated job {largest_gib:.1f} GB)"
    )
    desired_workers = min(3, max(1, len(sources)))
    if args.workers == "auto" and not config.use_stems and workers < desired_workers:
        print(
            f"Memory adjustment: workers reduced {desired_workers} → {workers} "
            f"to keep analysis within the safe RAM budget"
        )
    if config.use_stems and args.workers == "auto":
        print("Demucs enabled: limiting automatic processing to 1 worker")
    if config.choose_candidates:
        mode_label = "Listening review" if config.review_mode else "Interactive candidate selection"
        print(f"{mode_label}: using 1 worker")

    skipped = 0
    skipped_items: list[tuple[Path, Path]] = []
    jobs: list[TrackJob] = []
    for source in sources:
        output = _output_path(source, args.output_dir)
        wav_output = _wav_path(source, args.output_dir)
        if (
            output.exists() and wav_output.exists()
            and not args.overwrite and not args.preview_only
        ):
            print(
                f"Skipping existing outputs: {source.stem} "
                "(use --overwrite to replace them)"
            )
            skipped += 1
            skipped_items.append((source, output))
            continue
        intro_before = args.intro_before
        outro_after = args.outro_after
        outro_before = args.outro_before
        override = track_overrides.get(source.name.casefold())
        if override is not None:
            if intro_before is None:
                intro_before = override.intro_before
            if outro_after is None:
                outro_after = override.outro_after
            if outro_before is None:
                outro_before = override.outro_before
        jobs.append((source, output, intro_before, outro_after, outro_before))

    results, failures = BatchRunner().run(jobs, config, workers)

    total_elapsed = time.monotonic() - batch_started
    rekordbox_xml_path = None
    if config.export_cues and results and not config.preview_only:
        rekordbox_xml_path = args.output_dir.expanduser().resolve() / REKORDBOX_XML_FILENAME
        write_rekordbox_xml(results, rekordbox_xml_path)
    report_markdown, report_json = update_processing_report(
        args.output_dir, results, skipped_items
    )
    feedback_path = append_candidate_feedback(args.output_dir, results)
    _print_compact_results(results, total_elapsed)
    print("\nBatch complete")
    print(f"Created: {len(results)} | Skipped: {skipped} | Failed: {len(failures)}")
    print(f"Output folder: {args.output_dir.expanduser().resolve()}")
    print(f"Detailed report: {report_markdown}")
    print(f"Report data: {report_json}")
    print(f"Candidate feedback: {feedback_path}")
    if rekordbox_xml_path is not None:
        print(f"Rekordbox XML: {rekordbox_xml_path}")
    if failures:
        print("Failed files:", file=sys.stderr)
        for source, error in failures:
            print(f"  - {source.name}: {error}", file=sys.stderr)
    return 1 if failures else 0


def main() -> int:
    try:
        return run(_parser().parse_args())
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
