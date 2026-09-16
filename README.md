# DJ Audio Extender

A local macOS command-line tool that analyzes an existing track, selects strong
beat-aligned phrases near the beginning and end, and exports a stereo WAV with a
DJ-friendly intro and outro. The full original track remains present between the
added sections.

The selector does **not** blindly copy the opening bars. It evaluates 8-, 16-, or
32-bar candidates on an inferred 4/4 grid using percussion strength, onset
activity, loudness, spectral stability, and transition intensity. Optional Demucs
analysis adds a penalty for vocal-heavy regions.

## Requirements

- macOS 12 or newer recommended
- Python 3.10–3.12 recommended
- FFmpeg (recommended for broad MP3 decoding support)
- Enough free disk space for an uncompressed stereo WAV

Install Homebrew and FFmpeg if needed:

```bash
brew install python ffmpeg
```

Create an isolated environment and install the dependencies:

```bash
cd /Users/cortizn/Documents/LocalScripts/AudioExtender
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Project layout

```text
AudioExtender/
├── main.py              # CLI and batch runner
├── settings.py          # User-editable application defaults
├── helpers/             # Audio loading, analysis, selection, editing, stems
├── tests/               # Fast unit tests and synthetic test fixtures
├── input/               # Drop source songs here
├── output/
│   ├── wav/             # Straight PCM WAV conversions of the source files
│   └── extended/        # DJ edits named "(Extended Edit).wav"
├── cache/               # Reusable analysis data; safe to clear
├── track_overrides.json # Optional per-song musical boundaries
├── requirements.txt
├── requirements-dev.txt # Optional coverage tooling
└── requirements-demucs.txt
```

The contents of `input/` and `output/` are ignored by Git, while the directories
themselves remain part of the project.

### Architecture boundaries

The application keeps musical policy separate from delivery and signal
processing:

- `candidate_selection.py` accepts one typed `SelectionRequest` for either an
  intro or outro. Automatic-length policy can be tested without the CLI.
- `selection_coordinator.py` applies the same protected-boundary retries,
  Demucs-aware reranking, user choice, and safety fallback workflow to both
  intros and outros.
- `stem_provider.py` owns optional Demucs execution, cache validation,
  temporary-file cleanup, reliability data, and vocal-boundary detection.
- `export_service.py` writes final WAVs, splice previews, candidate auditions,
  cue points, and per-track cue sheets through one testable artifact boundary.
- `track_processor.py` is the single-track application service connecting
  analysis, cache, stems, selection, rendering, and export. `main.py` retains
  only CLI parsing, batch scheduling, summaries, and a compatibility facade.
- `candidate_validator.py` applies one final safety and repetition policy to
  both intro and outro candidates.
- `config_factory.py` owns CLI → preset → `settings.py` precedence and boundary
  validation.
- `batch_runner.py` owns serial/multiprocessing execution and collision-free
  aggregate progress.
- `selection_models.py` and `selection_metrics.py` separate the candidate
  domain model and reusable musical metrics from the ranking loop.
- `splice_policy.py` decides splice mode, crossfade duration, and harmonic-tail
  duration; `extended_edit.py` only applies those decisions to audio samples.
- `models.py` owns immutable application results shared by the CLI, reports,
  and cue exporters.
- `interfaces.py` defines the progress-reporting contract. Terminal, worker,
  silent, and test implementations can be substituted without changing music
  processing.
- `exceptions.py` distinguishes configuration, analysis, candidate, stem, and
  export failures while preserving friendly CLI error handling.

Keep new musical rules in policy/services rather than `main.py`. Keep terminal
formatting, interactive prompts, and filesystem discovery out of the analysis
and audio-assembly modules.

## Customizing defaults in code

Edit [`settings.py`](./settings.py) when you want permanent defaults without
typing the same CLI options each time. Command-line arguments still take priority
for an individual run, while per-song musical timestamps remain in
`track_overrides.json`.

| Setting | Shipped value | Usage and effect |
|---|---:|---|
| `SUPPORTED_BAR_COUNTS` | `(0, 2, 4, 8, 16, 32)` | Values accepted by `--intro-bars` and `--outro-bars`. Keep `0` if you want the disable option. |
| `DEFAULT_AUTO_BAR_SELECTION` | `True` | Chooses the most suitable shorter length up to the configured default when no explicit bar count is supplied. |
| `AUTO_BAR_MAXIMUM_QUALITY_LOSS` | `4.0` | Maximum loop-quality points a longer automatic choice may lose before receiving an extra penalty. |
| `DEFAULT_INTRO_BARS` | `8` | Intro length used when `--intro-bars` is omitted. Try `4` for less repetition. |
| `DEFAULT_OUTRO_BARS` | `8` | Outro length used when `--outro-bars` is omitted. Set `0` to preserve original endings by default. |
| `DEFAULT_MINIMUM_INTRO_LOOP_QUALITY` | `65.0` | Hard intro quality floor. Candidates below this percentage are not exported. |
| `DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY` | `65.0` | Hard outro quality floor. Candidates below this percentage are not exported. |
| `PREFERRED_LOOP_QUALITY_TARGET` | `70.0` | Ranking target. A musically competitive 70%+ candidate is preferred over a lower-scoring option. |
| `SUPPORTED_PCM_BITS` | `(16, 24)` | Values accepted by `--bit-depth`. WAV export currently supports these PCM depths. |
| `DEFAULT_PCM_BITS` | `24` | Normal output depth. `24` is recommended for editing quality; `16` produces smaller files. |
| `INPUT_FOLDER_NAME` | `"input"` | Batch folder relative to the project. CLI `--input-dir` overrides it. |
| `OUTPUT_FOLDER_NAME` | `"output"` | Export folder relative to the project. CLI `--output-dir` overrides it. |
| `TRACK_OVERRIDES_FILENAME` | `"track_overrides.json"` | Default per-song rules filename. CLI `--overrides` overrides it. |
| `CACHE_FOLDER_NAME` | `"cache"` | Folder for reusable track and Demucs-derived analysis files. |
| `DEFAULT_CACHE_ENABLED` | `True` | Enables cache reads and writes during normal runs. |
| `DEFAULT_PREVIEW_SECONDS` | `8.0` | Audio included on each side of a splice in preview files. Total preview length is up to twice this value. |
| `DEFAULT_EXPORT_CUES` | `True` | Writes per-track JSON cue sheets and a batch Rekordbox XML playlist. |
| `REKORDBOX_XML_FILENAME` | `"rekordbox.xml"` | Filename used for the importable playlist at the output-folder root. |
| `DEFAULT_CANDIDATE_COUNT` | `3` | Number of distinct intro/outro alternatives ranked internally for each enabled side. |
| `SUPPORTED_WORKER_CHOICES` | `("auto", "1", "2", "3")` | Values accepted by `--workers`. Increase carefully if you also increase the maximum worker count. |
| `DEFAULT_WORKERS` | `"auto"` | Normal concurrency mode. `auto` is recommended, especially with Demucs. |
| `BEATS_PER_BAR` | `4` | Assumed meter. Keep `4` for ordinary 4/4 music; changing it alters bar grouping throughout analysis. |
| `INTRO_SEARCH_SECONDS` | `120.0` | Maximum opening search window when no manual boundary re-anchors selection. |
| `OUTRO_SEARCH_SECONDS` | `150.0` | Maximum closing search window when no manual boundary re-anchors selection. |
| `ANALYSIS_HOP_LENGTH` | `512` | Analysis resolution. Smaller values are more precise but slower and more memory-intensive. |
| `MINIMUM_CROSSFADE_MS` | `10.0` | Shortest splice fade. The adaptive editor may increase it to 30 ms for difficult seams. |
| `PERCUSSION_PRIORITY_THRESHOLD` | `0.65` | Drum-strength level that permits a short, transient-preserving splice. |
| `BASS_PRESERVING_RISK_THRESHOLD` | `0.40` | Bass-reset risk that activates a longer low-end-preserving join. |
| `HARMONIC_TAIL_COMPATIBILITY_THRESHOLD` | `0.55` | Timbre/tail score below which sustained synth, chord, or reverb material receives extra carry-over. |
| `INTERACTIVE_CANDIDATE_POOL` | `12` | Maximum alternatives available through `R` during interactive review. Only three are shown at once. |
| `MAXIMUM_VOCAL_COVERAGE` | `0.45` | With Demucs, disables a selected side when sustained vocals occupy more than 45% of its candidate. |
| `MAXIMUM_VOCAL_BOUNDARY_RISK` | `0.55` | With Demucs, disables a selected side when an active vocal phrase overlaps a splice edge too strongly. |
| `MINIMUM_STEM_CONSTRUCTION_RELIABILITY` | `0.65` | Minimum aligned Demucs reconstruction score required before stems may be heard in an edit. |
| `MINIMUM_VOCAL_COVERAGE_FOR_INSTRUMENTAL_EDIT` | `0.08` | Uses instrumental construction only when enough vocal content exists to justify changing the full mix. |
| `MAXIMUM_BUILDUP_RISK` | `0.60` | Disables a candidate that behaves too strongly like a runway into a drop or new section. |
| `MINIMUM_ARRANGEMENT_FIT` | `-0.35` | Disables a technically clean candidate when its section role is strongly wrong, such as a chorus used as an outro. |
| `MINIMUM_FALLBACK_LOOP_QUALITY` | `45.0` | Prevents recovery from replacing a rejected loop with an audibly weak fallback merely because its section label is safer. |
| `MAXIMUM_BASS_RESET_RISK` | `0.65` | Disables a candidate whose loop would noticeably reset or remove low-frequency energy. |
| `PREFER_UNIQUE_MATERIAL` | `True` | Prefers compatible longer source phrases over repeating a shorter unit. |
| `UNIQUE_MATERIAL_SCORE_TOLERANCE` | `0.12` | Maximum internal-score sacrifice allowed to gain more unique musical material. Lower values are stricter. |
| `UNIQUE_MATERIAL_QUALITY_TOLERANCE` | `12.0` | Maximum loop-quality percentage-point sacrifice allowed for a longer unit. |
| `MINIMUM_UNIQUE_STRUCTURE_MATCH` | `0.45` | Minimum structural similarity required between the beginning and ending blocks of a longer phrase. |
| `DEFAULT_USE_STEMS` | `False` | Set `True` to use Demucs by default. This makes normal runs substantially slower. |
| `DEFAULT_OVERWRITE` | `False` | Set `True` to rebuild existing output files during normal runs. |
| `DEFAULT_PRESET` | `None` | Sets a named strategy for normal runs. Keep `None` to use the individual defaults above. |
| `PRESET_DEFINITIONS` | Six named profiles | Edit, add, or remove presets exposed by the `--preset` option. |

The most useful personal setup for shorter edits would be:

```python
DEFAULT_INTRO_BARS = 4
DEFAULT_OUTRO_BARS = 0
```

Avoid changing scoring formulas inside `helpers/` unless you are intentionally
tuning the audio-selection algorithm. The settings above are the supported
high-level controls.

To customize a preset, edit its entry in `PRESET_DEFINITIONS`. For example, this
makes `subtle` an intro-only two-bar edit with a stricter quality requirement:

```python
"subtle": {
    "intro_bars": 2,
    "outro_bars": 0,
    "use_stems": False,
    "minimum_loop_quality": 65.0,
    "maximum_repetitions": 1,
},
```

To add a preset, copy an entire entry, give it a unique name, and adjust its five
values. It appears automatically in `python3 main.py --help`. Invalid bar counts,
missing fields, quality values outside 0–100, and repetition limits below one are
reported immediately at startup.

## Usage

The easiest workflow is to place one or many songs in `input/`, then run:

```bash
python3 main.py
```

Every MP3, WAV, FLAC, AIF, and AIFF file directly inside `input/` is processed.
Every completed track produces two 24-bit WAV files:

```text
output/wav/Song Name.wav
output/extended/Song Name (Extended Edit).wav
```

The file under `wav/` is a format conversion only: stereo, source sample rate,
and no arrangement edits or normalization beyond emergency clipping protection.
The file under `extended/` contains the generated DJ intro/outro.

### Command reference

All options can be combined in one command. Boundary timestamps are source-song
times expressed in seconds; decimals are accepted, such as `12.5`.

| Command or option | Accepted value | Default | What it does |
|---|---:|---:|---|
| `python3 main.py` | — | — | Processes every supported song directly inside `input/`. |
| `python3 main.py "song.mp3"` | One or more file paths | `input/` batch | Processes only the named file or files. Quote paths containing spaces. |
| `--intro-bars` | `0`, `2`, `4`, `8`, `16`, or `32` | From `settings.py` | Sets the added intro length. `0` disables the intro extension. |
| `--outro-bars` | `0`, `2`, `4`, `8`, `16`, or `32` | From `settings.py` | Sets the added outro length. `0` preserves the original ending without an added outro. |
| `--auto-bars` / `--no-auto-bars` | Flag; no value | On | Enables automatic length selection for sides without an explicit bar count, or restores fixed defaults. |
| `--preset` | `auto` or a named profile below | None | Detects or applies a coordinated editing strategy. Explicit bar and stem options take priority. |
| `--intro-before` | Positive seconds | None | Requires selected intro material to end by this source timestamp. |
| `--outro-after` | Positive seconds | None | Requires selected outro material to begin at or after this source timestamp. |
| `--outro-before` | Positive seconds | None | Requires selected outro material to end by this source timestamp. |
| `--use-stems` / `--no-use-stems` | Flag; no value | From preset/settings | Enables or disables Demucs vocal scoring and automatic sustained-vocal boundaries. |
| `--input-dir` | Folder path | `./input` | Changes the folder scanned when no individual input files are supplied. |
| `--output-dir` | Folder path | `./output` | Changes where completed WAV files are written. |
| `--bit-depth` | `16` or `24` | `24` | Selects the output WAV PCM bit depth. |
| `--workers` | `auto`, `1`, `2`, or `3` | `auto` | Controls how many songs are processed concurrently. Automatic Demucs mode uses one worker. |
| `--overwrite` | Flag; no value | Off | Replaces existing extended-edit files instead of skipping them. |
| `--overrides` | JSON file path | `./track_overrides.json` | Loads musical boundaries from a different overrides file. |
| `--no-cache` | Flag; no value | Off | Runs without reading or writing cached analysis. |
| `--refresh-cache` | Flag; no value | Off | Recomputes analysis and replaces the applicable cache entries. |
| `--clear-cache` | Flag; no value | Off | Deletes AudioExtender cache entries and exits without processing songs. |
| `--cache-dir` | Folder path | `./cache` | Uses a different analysis-cache folder. |
| `--previews` | Flag; no value | Off | Writes intro/outro splice previews in addition to the full extended WAV. |
| `--preview-only` | Flag; no value | Off | Writes splice previews without exporting the full extended WAV. |
| `--preview-seconds` | Positive seconds | `8` | Sets how much audio appears before and after each previewed splice. |
| `--intro-candidate` | `0`, `1`, `2`, or `3` | `1` | Uses a ranked intro alternative; `0` rejects every intro candidate. |
| `--outro-candidate` | `0`, `1`, `2`, or `3` | `1` | Uses a ranked outro alternative; `0` rejects every outro candidate. |
| `--choose-candidates` | Flag; no value | Off | Displays three ranked options at a time. Choose `1–3`, `0` for none, `R` for the next page, or `C` for a custom source-time range. Forces one worker. |
| `--cues` / `--no-cues` | Flag; no value | On | Enables companion JSON cue sheets and Rekordbox XML, or disables both. |
| `--help` or `-h` | — | — | Displays the built-in command help. |

### Common commands

| Goal | Command |
|---|---|
| Process everything in `input/` | `python3 main.py` |
| Process one song | `python3 main.py "input/Song.mp3"` |
| Process several named songs | `python3 main.py "Song One.mp3" "Song Two.flac" "Song Three.aiff"` |
| Make an 8-bar intro and 8-bar outro | `python3 main.py --intro-bars 8 --outro-bars 8` |
| Make a short 4-bar intro only | `python3 main.py --intro-bars 4 --outro-bars 0` |
| Make a minimal 2-bar extension | `python3 main.py --intro-bars 2 --outro-bars 2` |
| Make an intro only | `python3 main.py --intro-bars 16 --outro-bars 0` |
| Make an outro only | `python3 main.py --intro-bars 0 --outro-bars 16` |
| Preserve both sides and only convert to WAV | `python3 main.py --intro-bars 0 --outro-bars 0` |
| Keep intro material before 12 seconds | `python3 main.py "input/Song.mp3" --intro-before 12` |
| Keep outro material after 3:00 | `python3 main.py "input/Song.mp3" --outro-after 180` |
| Keep outro material before 3:25 | `python3 main.py "input/Song.mp3" --outro-before 205` |
| Restrict outro material to 3:00–3:25 | `python3 main.py "input/Song.mp3" --outro-after 180 --outro-before 205` |
| Enable Demucs vocal analysis | `python3 main.py --use-stems` |
| Rebuild existing results | `python3 main.py --overwrite` |
| Process with two workers | `python3 main.py --workers 2` |
| Use custom input and output folders | `python3 main.py --input-dir "/Music/Input" --output-dir "/Music/Edits"` |
| Export 16-bit WAV | `python3 main.py --bit-depth 16` |
| Use another override file | `python3 main.py --overrides "/path/to/rules.json"` |
| Use a vocal-safe profile | `python3 main.py --preset vocal-safe` |
| Detect the editing profile automatically | `python3 main.py --preset auto` |
| Ignore cached data once | `python3 main.py --no-cache` |
| Rebuild cached analysis | `python3 main.py --refresh-cache --overwrite` |
| Delete all cached analysis | `python3 main.py --clear-cache` |
| Export full edits and splice previews | `python3 main.py --previews` |
| Export only splice previews | `python3 main.py --preview-only` |
| Use 10 seconds around each splice | `python3 main.py --previews --preview-seconds 10` |
| Choose ranked alternatives interactively | `python3 main.py "input/Song.mp3" --choose-candidates` |
| Let the tool choose extension lengths | `python3 main.py "input/Song.mp3" --auto-bars` |
| Use the fixed configured defaults | `python3 main.py "input/Song.mp3" --no-auto-bars` |
| Use candidate 2 without prompting | `python3 main.py "input/Song.mp3" --intro-candidate 2 --outro-candidate 2` |
| Reject every ranked intro choice | `python3 main.py "input/Song.mp3" --intro-candidate 0` |

### Preset profiles

| Preset | Intro/outro | Demucs | Quality floor | Intended use |
|---|---:|---:|---:|---|
| `auto` | Detected | Optional | From selected profile | Classifies the track after analysis and chooses `club`, `subtle`, `slow-song`, or—with stems—`vocal-safe`. |
| `club` | 16 / 16 bars | No | 45% | Longer, conventional DJ phrasing for rhythm-forward tracks. |
| `subtle` | 4 / 4 bars | No | 58% | Short additions with no repeated loop unit. |
| `slow-song` | 4 / 0 bars | No | 62% | Conservative intro-only treatment for slower or less electronic music. |
| `vocal-safe` | 8 / 0 bars | Yes | 60% | Demucs-aware intro with the original ending preserved. |
| `intro-only` | 8 / 0 bars | No | 50% | General intro extension without altering the ending. |
| `outro-only` | 0 / 8 bars | No | 50% | General outro extension without altering the opening. |

The quality floor is a safety rule: if the best candidate scores below it, that
side is disabled rather than forcing a questionable loop. Presets also limit how
many times a short unit may repeat. You can override lengths while retaining the
rest of a preset, for example:

```bash
python3 main.py "input/Song.mp3" --preset slow-song --intro-bars 2
```

Automatic mode evaluates BPM, normalized percussion strength, beat-grid
confidence, onset consistency, and whole-track dynamic range. When Demucs is
explicitly enabled, it also measures vocal density and can select `vocal-safe`:

```bash
python3 main.py --preset auto
python3 main.py --preset auto --use-stems
```

The result report shows the detected style, chosen preset, and the measurements
that drove the decision. `--preset auto --intro-bars 4` still chooses the other
profile settings automatically but keeps the explicit four-bar intro.

### Track override reference

The default override file is
[`track_overrides.json`](./track_overrides.json). Its top-level keys are exact
filenames, including extensions. Filename matching is case-insensitive. Each song
can contain any of these fields:

| Field | Value | Meaning |
|---|---:|---|
| `intro_before` | Positive seconds | The selected intro phrase must end at or before this source timestamp. Useful for protecting the first recognizable vocal. |
| `outro_after` | Positive seconds | The selected outro phrase must begin at or after this source timestamp. Useful for excluding a late verse or chorus. |
| `outro_before` | Positive seconds | The selected outro phrase must end at or before this source timestamp. The original closing section after it then plays naturally. |

Example with several different rule styles:

```json
{
  "DtMF.mp3": {
    "intro_before": 12.0
  },
  "Song With Protected Ending.mp3": {
    "outro_before": 205.0
  },
  "Song With Exact Outro Range.flac": {
    "intro_before": 18.5,
    "outro_after": 180.0,
    "outro_before": 205.0
  }
}
```

Rules apply automatically during both individual and batch processing. A CLI
boundary overrides the matching JSON field for that run. For example,
`--intro-before 10` replaces every selected song's JSON `intro_before` value,
while its JSON outro fields remain active. When both `outro_after` and
`outro_before` are present, `outro_after` must be earlier than `outro_before`.
Bar counts are command options and are not currently stored in the overrides
file. Supported lengths are 2, 4, 8, 16, and 32 bars; use zero when you want to
disable that side of the extension.

### Analysis cache

AudioExtender caches expensive feature analysis in `cache/`. The first run still
performs normal analysis; later runs of the same unchanged source can reuse it and
proceed quickly to phrase selection and export. Demucs-derived vocal measurements
are cached separately, so they can also be reused without repeating stem
separation. Temporary full stem audio is still removed.

Changing intro/outro bars, presets, boundaries, bit depth, or the output folder
does not invalidate analysis because those choices do not change the underlying
audio features. Cache entries automatically change when any of these do:

- Source path, file size, or modification time
- Beats-per-bar setting
- Analysis hop length
- Internal cache schema version

Use `--refresh-cache` after changing analysis code or when you suspect stale
results. Use `--no-cache` for a one-off uncached run. Use `--clear-cache` to remove
all `.npz` entries from the selected cache folder and exit. The cache is optional,
ignored by Git, and safe to delete; it never contains your source audio.

### Splice previews

Use previews to audition edited transitions without searching through the full
song:

```bash
python3 main.py "input/Song.mp3" --previews
python3 main.py "input/Song.mp3" --preview-only
python3 main.py "input/Song.mp3" --previews --preview-seconds 10
```

Review files are organized below the output folder while finished edits remain at
the top level:

```text
output/
├── Song (Extended Edit).wav
└── previews/
    └── Song/
        ├── Intro Preview.wav
        └── Outro Preview.wav
```

Every preview auditions the complete inserted section in musical context:

```text
Intro: original lead-in (if any) → complete added intro → original next section
Outro: original lead-in          → complete added outro → original ending (if any)
```

The original context on each side uses `--preview-seconds`. The inserted section
is always included in full, so a 16-bar preview can be substantially longer than
twice the context setting. This lets you judge entry into the loop, repetition
inside it, and the return to the untouched song. If one side is disabled or
rejected by a safety rule, no preview is created for that side. Preview-only mode
does not replace or write the full extended WAV.

### Ranked candidate choices

For every enabled intro and outro, AudioExtender ranks three musically distinct
locations by default. Normal runs automatically use candidate 1. Interactive
runs keep a larger pool available in pages of three. Overlapping
versions of the same location are filtered so alternatives represent genuinely
different parts of the song whenever enough options exist.

To see the choices and select them in the terminal:

```bash
python3 main.py "input/Song.mp3" --choose-candidates
```

Each option shows its source timestamps, loop quality, energy shape, buildup
risk, bass-reset risk, and unique bar count. Before each prompt, AudioExtender
writes `Intro Candidate 1.wav` through candidate 3 inside
`output/previews/Song/`. Outro candidates use the same folder. Listen to them
while the prompt is waiting. Press Enter for the best option on the current page,
type `1`, `2`, or `3`, enter `0` for no extension, or type `R` to reject that page
and audition the next three. The same three preview filenames are overwritten on
each page, so the output folder does not accumulate every rejected option. Type
`C` to enter a preferred source start/end such as `12`, `12.5`, or `1:05`; the
tool snaps it to the nearest analyzed, bar-aligned candidate. Interactive mode
uses one worker to keep prompts readable.

For scripts and repeatable batches, select ranks without prompting:

```bash
python3 main.py "input/Song.mp3" --intro-candidate 2
python3 main.py --intro-candidate 2 --outro-candidate 3
python3 main.py "input/Song.mp3" --intro-candidate 0 --outro-candidate 0
```

If fewer than the requested number of distinct candidates exist, the song fails
with a clear message instead of silently choosing a different rank. Candidate
ranking reuses cached analysis, so trying another rank normally avoids the
expensive feature and Demucs stages.

One bad or unusually short track will not stop the rest of a batch. A summary
reports created, skipped, and failed files. Existing outputs are skipped by
default so rerunning a batch does not waste time. Use `--overwrite` to rebuild
them.

Batch processing automatically chooses one, two, or three worker processes using
the Mac's physical memory plus each song's decoded duration, sample rate, channel
count, and estimated analysis working size. It keeps most memory available for
macOS and other applications. Automatic mode uses one worker with Demucs because
stem separation is substantially heavier. You can override the decision:

```bash
python3 main.py --workers 1
python3 main.py --workers 2
python3 main.py --workers 3
```

Interactive terminals show a compact three-line display:

```text
Batch [████████░░░░░░░░░░░░░░] 2/5 · ETA ~03:41 · workers 3
Song  [██████████████░░░░░░░░] 64% · Babydoll.mp3 · Separating stems
✓ Load  ✓ Analyze  ◉ Stems  ○ Select  ○ Render  ○ Export
```

The batch ETA blends the current song's progress with measured times from songs
already completed, so it becomes better calibrated during a batch. Demucs gets a
dedicated stem bar and reports `Apple GPU (MPS)` or `CPU`. If a calculation makes
no percentage progress for 15 seconds, `still active` and its elapsed duration
appear instead of leaving a seemingly frozen spinner. Redirected/log output uses
sparse checkpoint lines rather than terminal cursor animation.

When automatic concurrency is lower than the normal three-worker target because
of estimated RAM requirements, the terminal prints a `Memory adjustment` notice
showing the worker reduction. Demucs still uses one automatic worker because its
memory and compute requirements are substantially heavier.

After the batch, the terminal prints only vital song outcomes and total wall-clock
time. The persistent report lists BPM, beat/bar details, selected phrase ranges,
scores, construction decisions, and output filenames.

The report also includes an estimated intro/outro loop-quality percentage, a
beat-grid confidence percentage, and suggested mix-in/mix-out cues. Cue times are
for the generated extended WAV and account for the inserted intro phrase. These
measurements are decision aids rather than guarantees; verify low-confidence grids
and cue positions by ear in Rekordbox.

Automatic bar selection compares every supported nonzero length up to the normal
configured maximum. It combines loop quality, phrase structure, surrounding
energy, stability, instrumentalness, section type, buildup risk, and bass-reset risk. Two-bar
fragments receive a small penalty; 8 bars or more are preferred only for stable,
rhythm-forward material. The results line marks the chosen extension as
`automatic length`. Supplying `--intro-bars` or `--outro-bars` always fixes that
side at the requested length, even while automatic selection remains enabled for
the other side.

### Understanding the processing report

| Report item | Meaning | How to interpret it |
|---|---|---|
| `Time` | Wall-clock processing time for that song. | Demucs, longer tracks, and lower analysis hop lengths increase it. It says nothing about edit quality. |
| `BPM` | Estimated tempo used to construct the beat grid. | Compare it with Rekordbox. Half-time and double-time readings can describe the same pulse but change perceived phrase length. |
| `Tempo drift` | Spread between the track's faster and slower local beat intervals, relative to its median tempo. | Near zero suggests quantized timing. Larger values flag live playing, tempo automation, or an uncertain tracker; projected opening/ending bars use local timing rather than only the global BPM. |
| `beats / bars` | Detected beats and inferred 4/4 bars. | Bars are groups of four beats. The count is approximate because sparse openings and endings may not provide detectable beats. |
| `Beat-grid confidence` | Confidence that beats are regularly timed, supported by onsets, and assigned a plausible downbeat phase. | This measures timing placement—not whether the chosen loop is musically good. |
| `Groove` | Subdivision pattern inferred between the main beats: `straight`, `swing`, `syncopated`, `loose/syncopated`, or `undetermined`. | This describes feel; swing and syncopation are not errors and are preserved rather than quantized. |
| `Timing` | Interpretation of local tempo movement combined with grid support: `steady`, `mildly variable`, `variable/live`, or `uncertain grid`. | Variable/live can be musically intentional. Uncertain grid indicates that beat evidence itself is weak. |
| `Downbeat continuity` | Consistency of beat placement, onset support, local timing, and recurring four-beat accent shape across bars. | Higher means inferred beat one remains convincing throughout the song. |
| `Preset` | Manual profile or profile selected by `--preset auto`. | Automatic reports use the form `auto → club`. Explicit bar options may still override its lengths. |
| `Detected style` | Heuristic style used by automatic mode. | Its reason lists measurements such as percussion, grid confidence, and dynamics. It is an editing strategy, not a genre label. |
| `Intro` / `Outro` times | Start and end of the selected phrase in the original source. | These are source timestamps, not positions in the longer exported WAV. |
| `Estimated key` | Global major/minor key inferred from the track's chroma distribution. | Higher confidence means one tonal profile separated clearly from alternatives. Modulation, borrowed chords, sparse harmony, and percussion can reduce reliability. |
| `Loop quality` | Combined estimate of seam, harmony, chord return, timbre, bass, stability, structure, fills, pickups, and energy behavior. | It evaluates the artificial loop-back transition, but cannot guarantee that repetition is artistically tasteful. |
| `Energy` | Arrangement shape across the selected phrase and its surrounding bars. | Reported as `stable`, `buildup`, `losing-bass`, `fading`, or `section-change`. Stable is normally preferred. |
| `Buildup risk` | Heuristic 0–100 measure that the phrase is progressing toward a drop or transition. | Lower is safer. Candidates above the configured limit are disabled. |
| `Bass-reset risk` | Estimated severity of low-end discontinuity when the phrase loops. | Lower is safer. High values correspond to bass entering, withdrawing, or restarting conspicuously. |
| `Context` | Energy-flow agreement across four bars before, the candidate, and four bars after. | Higher means the phrase belongs naturally in its surrounding arrangement. |
| `Splice mode` | Automatically selected join treatment: `percussion-priority`, `bass-preserving`, `harmonic-tail`, `zero-crossing`, or `adaptive`. | It controls micro-fade and sustained-tail behavior without moving the edit to different musical bars. |
| `Chord return` | Compatibility of the candidate's final-bar harmony with its first-bar harmony, including common cadence motion in the estimated key. | Higher is safer. Unlike simple chord equality, a dominant-to-tonic return can score well because it forms a musically natural loop. |
| `Resolution risk` | How much more strongly the ending chord appears to lead into the original next bar than back to the loop's beginning. | Lower is safer. High risk identifies phrases that sound unfinished when reset, even if the cut itself is clean. |
| `Section` | Approximate arrangement role inferred bar by bar: `intro`, `verse`, `chorus`, `breakdown`, `buildup`, `drop`, `closing`, or `fade`. | Intro selection favors `intro`; outro selection favors `closing` and gentle `fade` material. Peaks, drops, and buildups are penalized when used in the wrong role. |
| `Section confidence` | Strength and consistency of the dominant section label across the selected bars. | A low value means the candidate crosses labels or has ambiguous energy behavior, so treat the label cautiously. |
| `Arrangement fit` | Signed score showing whether that section type suits its intended intro/outro role. | Positive is favorable, zero is neutral, and negative means the candidate resembles the wrong part of the song. It is one ranking factor, not a hard rejection. |
| `Local grid` | Average rhythmic-grid confidence across the candidate's bars. | Lower values indicate sparse or ambiguous beats inside the phrase. |
| `Boundary grid` | Confidence of the weaker first or last candidate bar. | This specifically guards the loop splice from landing on a displaced or poorly supported bar boundary. |
| `Instrumental` | Percussion-to-mix ratio used as an instrumentalness proxy. | Higher values favor drum-led material. It is not a probability that vocals are absent; Demucs is more reliable for vocals. |
| `Vocal coverage` | Proportion of the selected candidate classified as sustained vocal activity. | Lower is safer for repetition. Candidates above the configured maximum are disabled. |
| `Boundary risk` | Vocal activity immediately around the phrase's start or end. | High values suggest a clipped lyric, sustained word, or vocal pickup crossing the artificial splice. |
| `Stem separation reliability` | Similarity between the time-aligned sum of Demucs stems and the decoded source. | Instrumental construction requires the configured minimum; lower values keep the full mix. This measures reconstruction, not artistic isolation quality. |
| `Construction` | Whether added copies use the `full mix` or `instrumental stems`. | Only the repeated extension changes. Untouched portions always use the original source audio. |
| `Instrumental construction quality` | Loop-quality estimate with penalties caused solely by removed vocals excluded. | Use this instead of the full-mix quality when the report says `instrumental stems`. |
| `Unique material / extension / copies` | Unique source length, total added length, and copy count. | `8 / 16 / 2` means two compatible four-bar halves form an eight-bar unit that is copied twice. More unique bars and fewer copies usually sound less mechanical. |
| `Protected vocal entrance` | Active `intro_before` boundary, automatic or manual. | Intro material cannot extend beyond this source timestamp. |
| `Protected vocal release` | Active `outro_after` boundary, automatic or manual. | Outro material cannot begin before this source timestamp. |
| `Protected closing section` | Active `outro_before` boundary. | Outro material must end by this time so the recognizable closing section continues naturally. |
| `Suggested cues` | Suggested mix-in and mix-out positions in the completed WAV. | These account for inserted audio. Confirm them in Rekordbox before performing. |
| `Created / Skipped / Failed` | Batch result counts. | Skipped normally means an output existed; use `--overwrite` to rebuild it. |

#### Beat-grid confidence ranges

| Confidence | Practical interpretation |
|---:|---|
| `80–100%` | Strong, steady grid. Usually reliable, but still verify beat one. |
| `60–79%` | Generally usable. Check the first downbeat and several later phrases in Rekordbox. |
| `40–59%` | Uncertain. Sparse drums, syncopation, live timing, or tempo movement may be affecting detection. |
| Below `40%` | Treat the grid as unreliable and verify it manually before trusting an edit. |

Downbeat phase is inferred from recurring four-beat accent patterns across many
bars, not simply the loudest individual beat. This is still an approximation;
syncopated music and songs whose first strong beat is not beat one should be
checked in Rekordbox.

#### Tempo-drift ranges

| Drift | Practical interpretation |
|---:|---|
| Below `3%` | Usually steady or quantized. |
| `3–8%` | Mild movement, expressive timing, or occasional tracker variation. |
| Above `8%` | Variable-tempo/live material or a grid that deserves manual verification. |

These are diagnostics, not quality grades. Syncopation and sparse percussion can
inflate the measurement even when the recording itself has a steady tempo.

#### Arrangement-section limitations

Section labels are inferred from bar position, loudness, drums, harmonic energy,
onset activity, and short-term energy direction. They do not recognize lyrics or
know the artist's intended narrative. Unusual forms, ambient openings, repeated
choruses, and songs without clear energy changes can be mislabeled. Use
`--choose-candidates` when section confidence is low or the song has a distinctive
arrangement.

### Automatic fallback behavior

When automatically selected candidate 1 violates a vocal, buildup, bass-reset,
arrangement, or preset-quality safety rule, AudioExtender first checks the other
ranked locations at the same extension length. If the length was also selected
automatically, it then tries progressively shorter bar counts. Every replacement
must pass the normal safety rules and `MINIMUM_FALLBACK_LOOP_QUALITY`.

The report records both the rejected reason and the chosen recovery, for example:

```text
Fallback: rejected section chorus, fit -53%; alternate candidate 2 at the same length
```

If no safe recovery exists, that extension is disabled and the original audio is
preserved. A non-default rank selected with `--intro-candidate` or
`--outro-candidate`, or any choice made through `--choose-candidates`, is
considered intentional and is not silently replaced; existing hard safety checks
can still disable it.

#### Loop-quality ranges

| Quality | Practical interpretation |
|---:|---|
| `85–100%` | Excellent measured seam compatibility. Still audition for repetition and recognizable lyrics. |
| `70–84%` | Strong candidate that will usually splice cleanly. |
| `55–69%` | Potentially usable, but audition it carefully. |
| `40–54%` | Weak or context-dependent; a buildup, chord change, bass reset, or pickup may remain audible. |
| Below `40%` | Poor candidate. Prefer another range, a shorter edit, or disabling that side. |

#### Instrumentalness ranges

| Value | Practical interpretation |
|---:|---|
| `0.75–1.00` | Strongly percussion-led according to the mix-only proxy. |
| `0.55–0.74` | Mixed material with useful rhythm but potentially prominent harmonic or vocal content. |
| `0.35–0.54` | Harmonic, melodic, vocal, or relatively drum-light material. |
| Below `0.35` | Usually a poor conventional DJ loop unless an ambient or very subtle edit is intended. |

The temporary `score=...` shown during candidate selection is an internal ranking
value, not a percentage. It can be negative and is only meaningful when comparing
candidates from the same song and position. Use `loop quality` for the calibrated
0–100 summary.

#### Automatic-style reason values

| Measurement | Scale | Practical interpretation |
|---|---:|---|
| `percussion` | Usually `0.00–1.00` | Mean normalized drum/percussion energy. Around `0.40` or higher supports a rhythm-forward classification; it is relative to that recording. |
| `grid` | `0–100%` | The same beat-grid confidence described above. Automatic mode becomes more conservative below approximately 60%. |
| `dynamics` | Usually `0.00–1.00` | Difference between the track's quiet and loud energy percentiles. Lower values imply a steady arrangement; higher values imply larger builds, breakdowns, or acoustic variation. |
| `vocals occupy` | `0–100%` | With Demucs, the proportion of analyzed frames containing sustained vocal energy. High density favors `vocal-safe`. |

The output retains the source sample rate whenever the decoder exposes it, is
always stereo, and is written as PCM WAV. Gain is unchanged unless a constructed
boundary exceeds digital full scale; in that case only the minimum global gain
needed to avoid clipping is applied.

## Rekordbox cues and cue sheets

Normal exports also create:

```text
output/
├── Song (Extended Edit).wav
├── rekordbox.xml
├── reports/
│   ├── Processing Report.md
│   └── processing_report.json
└── cue_sheets/
    └── Song (Extended Edit).json
```

The JSON file records exact seconds, purpose, confidence, BPM, key, groove, and
grid statistics. The Rekordbox XML contains an `AudioExtender Edits` playlist,
one basic 4/4 tempo-grid anchor per track, memory cues, and saved intro/outro
loops. Suggested points include the first reliable downbeat, mix in, return to
the original song, mix out, start of the added outro, and return to the natural
ending. Coincident memory cues are deduplicated, while a saved loop may share a
position with a named memory cue.
`rekordbox.xml` represents the successfully created tracks from the current run;
a later run replaces it rather than merging with an older XML collection.

To import it in Rekordbox, open Preferences and select the generated XML under
the Bridge/Imported Library setting. Open `rekordbox xml` in the browser tree,
open Playlists, and drag `AudioExtender Edits` into the normal Playlists area.
The XML uses documented memory cues (`Num=-1`) rather than Hot Cues, so it does
not assign Hot Cue A–H for you. Rekordbox should still analyze each WAV normally;
verify the imported grid and cues before performing. Disable companion exports
with `--no-cues`.

Format and import behavior follow the official
[rekordbox developer XML documentation](https://rekordbox.com/en/support/developer/).

## Persistent processing report

The terminal intentionally shows only the essentials for each completed song:
processing time, BPM, key, intro/outro length and quality, safety warnings, and
mix cues. Full diagnostics are stored in `output/reports/Processing Report.md`.
The adjacent `processing_report.json` is the durable backing record and can be
used by other tools.

Reports are updated by source filename:

- A newly processed song adds or replaces its record.
- `--overwrite` replaces that song's old measurements with the new result.
- A song skipped because its output already exists keeps its previous analysis
  and is marked `skipped` for the latest run.
- A skipped legacy output with no previous report receives a minimal record;
  processing it once with `--overwrite` fills in the complete analysis.
- Songs not involved in the current command remain in the report unchanged.

The Markdown report begins with a compact library table, followed by detailed
per-song sections covering grid, key, groove, arrangement, harmony, vocals,
construction method, safety decisions, and cue points.

## Optional Demucs support

Demucs is not needed for normal operation. To use vocal-stem analysis and optional
instrumental edit construction:

```bash
python -m pip install -r requirements-demucs.txt
python3 main.py --use-stems
```

The first Demucs run may download a model. Separation is CPU-intensive and can
take several minutes. AudioExtender caches the aligned `drums + bass + other`
instrumental mix as a lossless floating-point WAV alongside the compact analysis
cache. Subsequent runs can therefore construct stem edits without rerunning
Demucs. `--clear-cache` removes both analysis entries and cached instrumentals.
AudioExtender supplies Demucs with the virtual environment's maintained `certifi`
certificate bundle for secure model downloads on Python.org macOS installations.
Demucs's own separation percentage is forwarded into AudioExtender's live progress
bar. On Apple Silicon, use a native ARM64 Python installation; an Intel Python
running through Rosetta can make stem separation dramatically slower and prevents
PyTorch from using Apple's MPS acceleration.
When PyTorch reports MPS as available, AudioExtender explicitly runs Demucs on the
Apple GPU. It falls back to CPU automatically on systems where MPS is unavailable.

When Demucs is enabled, AudioExtender also detects sustained vocal regions. Unless
a manual rule exists, the first sustained vocal entrance becomes the latest intro
boundary and the final sustained vocal release becomes the earliest outro boundary.
The detector smooths brief breaths, ad-libs, and stem leakage. If an automatically
detected boundary leaves no complete loopable phrase, the track falls back to its
normal musical search; explicit CLI and JSON boundaries remain strict.
The same vocal activity map is analyzed at every candidate's exact edges. The
selector distinguishes isolated short activity from sustained phrases, measures
how much of the candidate contains vocals, detects rising vocal pickups near its
end, and penalizes lyrics crossing either splice boundary. If the best remaining
candidate exceeds the safety limits in `settings.py`, that extension is disabled
instead of forcing a lyrically awkward repeat.

For audible construction, AudioExtender aligns the separated stems with the
original decode to compensate for MP3 encoder delay, then measures how accurately
all stems reconstruct the source. If reliability clears the configured threshold
and the candidate contains meaningful vocal activity, only `drums + bass + other`
is used for the added repetitions. The untouched original—including its vocals—
returns at the selected phrase boundary. Candidates with little vocal activity,
low separation reliability, or no Demucs data continue using the original full
mix. Reports distinguish `full-mix loop quality` from `instrumental construction
quality` and state which construction was used for each side.

## How it works

1. The source is decoded without resampling and retained as stereo floating-point
   samples for editing.
2. A mono analysis copy is split into harmonic/percussive components. Percussive
   onset strength drives BPM and beat detection.
3. The strongest recurring beat accent estimates the downbeat phase. Beats are
   grouped into 4/4 bars; four-bar candidate steps approximate phrase boundaries.
   When detection begins after a sparse opening, the stable bar period is projected
   backward so pre-vocal opening material remains available on the musical grid.
4. Complete bar-aligned regions in the early and late search windows are scored,
   including bar-smoothed energy, bass-band continuity, 32-band timbral similarity,
   final-bar energy trends, harmonic/chroma compatibility, ending fills, vocal
   pickups, and suitability as a seamless musical loop.
   The selector also compares the first and last four-bar blocks, the bar before
   entry, the bar after exit, and the natural post-phrase release. This helps
   distinguish a stable groove from a buildup intended to lead into another section.
   If a full requested phrase is progressive, a cleaner 4- or 8-bar unit may be
   repeated enough times to preserve the requested 8/16/32-bar extension length.
   When scores are close, the selector now prefers a compatible eight-bar unit
   (two adjacent four-bar phrases in their original order) over repeating one
   four-bar phrase twice. The same rule can prefer a safe 16-bar unit over two
   copies of eight bars. Configurable score, loop-quality, and structural limits
   ensure variety is chosen only when it remains musically competitive.
   Intro candidates are confined to the first 16 detected bars and outro candidates
   to the final 16 detected bars (expanded only when a 32-bar request requires it),
   keeping slower songs out of their first verse and inside their natural ending.
   An intro loop must also begin within the first eight detected bars, preventing a
   short unit from being chosen at the very end of the opening zone.
   Arrangement analysis also examines four bars before and four bars after every
   candidate. It compares energy direction, entry/exit levels, post-phrase jumps,
   and bass movement to classify stable grooves, buildups, bass withdrawals,
   fades, and section changes. High buildup or bass-reset risks can disable an
   extension even when its exact waveform seam appears clean.
5. The best early phrase is repeated immediately before its original occurrence.
   The best late phrase is repeated before the song's untouched natural tail. The
   original slow opening and natural ending therefore stay in the correct order.
   Short adaptive 10–30 ms complementary fades are used only at artificial loop
   seams. Each splice is first shifted by up to 20 ms to find a cleaner waveform
   match while preserving the exact phrase duration and beat alignment.
   Sustained content receives separate treatment: 250–750 ms of the song's real
   post-phrase synth, bass, and reverb continuation is carried across the loop and
   blended into the repeated phrase. Percussion is excluded from this longer blend
   so kicks and other drum transients remain sharp.
   With reliable Demucs stems, added copies containing vocals can instead use the
   aligned instrumental mix while every untouched portion of the song remains the
   original full stereo master.
6. The result is exported to a Rekordbox-friendly stereo PCM WAV.

## Known limitations

- Downbeat detection is heuristic. Syncopated music, live drums, non-4/4 meters,
  tempo changes, and beatless intros can produce an incorrect bar phase.
- Without stems, vocal avoidance is inferred only indirectly. Use `--use-stems`
  when clean instrumental selection matters.
- A phrase that scores well acoustically may not be the most tasteful musical
  choice. Audition the intro-to-song and song-to-outro boundaries before playing
  the edit live.
- The MVP copies source phrases; it does not synthesize drums, time-stretch audio,
  change tempo, or rebuild an instrumental from stems.
- Lossy inputs cannot regain quality when exported to WAV. WAV prevents another
  lossy encoding pass but does not undo MP3 compression.

## Rekordbox workflow

Import the generated WAV, analyze it in Rekordbox, and verify the first downbeat
and phrase grid by ear. Set a memory cue at the start of the added intro and near
the added outro. Because the edit adds audio before the source, previously saved
cue timestamps from the original file will not match the new file.
## Automated tests

AudioExtender includes fast unit tests built on Python's standard `unittest`
library, so running the normal suite does not require another test framework:

```bash
python3 -m unittest discover -s tests -v
```

The suite uses synthetic audio and mocks for hardware/resource decisions. It
does not run Demucs or process the songs in `input`, keeping feedback fast and
repeatable. It covers configuration validation, overrides, CLI helpers,
candidate-quality calibration, adaptive splices, progress/slow-task reporting,
memory-aware worker selection, persistent reports, and safe cache cleanup.

Optional coverage reporting is available with the development requirements:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report -m
```

Run the complete local quality gate after installing the development
requirements:

```bash
python3 -m unittest discover -s tests
python3 -m ruff check .
python3 -m mypy
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report
```

The tests follow the same separation as the application modules: domain logic
is tested independently from file I/O, terminal presentation, and expensive
external stem separation. When adding a feature, place its policy in a small
helper and inject external dependencies where practical; this keeps the code
open to new behavior without coupling tests to Demucs, FFmpeg, or real tracks.
