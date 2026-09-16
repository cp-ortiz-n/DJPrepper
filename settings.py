"""User-editable defaults for AudioExtender.

Change values in this file to customize normal runs without editing the audio
processing modules. Command-line options still override these defaults.
"""

# Extension lengths offered by --intro-bars and --outro-bars. Zero disables that
# side of the edit. Keeping powers/multiples of two gives predictable DJ phrasing.
SUPPORTED_BAR_COUNTS = (0, 2, 4, 8, 16, 32)
DEFAULT_INTRO_BARS = 8
DEFAULT_OUTRO_BARS = 8

# When a bar count is not explicitly supplied on the command line, compare
# shorter musical lengths up to the configured default and choose the best fit.
# An explicit --intro-bars/--outro-bars value always wins.
DEFAULT_AUTO_BAR_SELECTION = True
AUTO_BAR_MAXIMUM_QUALITY_LOSS = 4.0

# Output format. Valid PCM depths are 16 and 24; 24 preserves more editing
# headroom and is the recommended Rekordbox default.
SUPPORTED_PCM_BITS = (16, 24)
DEFAULT_PCM_BITS = 24

# Folder names are relative to the AudioExtender project directory.
INPUT_FOLDER_NAME = "input"
OUTPUT_FOLDER_NAME = "output"
TRACK_OVERRIDES_FILENAME = "track_overrides.json"
CACHE_FOLDER_NAME = "cache"
DEFAULT_CACHE_ENABLED = True

# Transition-preview defaults. Context is included on both sides of each splice,
# so 8 seconds produces a preview up to 16 seconds long.
DEFAULT_PREVIEW_SECONDS = 8.0

# Companion cue exports. JSON files are written under output/cue_sheets and one
# rekordbox XML playlist is written at the output-folder root after each batch.
DEFAULT_EXPORT_CUES = False
REKORDBOX_XML_FILENAME = "rekordbox.xml"

# Number of distinct intro/outro alternatives ranked for every enabled side.
DEFAULT_CANDIDATE_COUNT = 3
INTERACTIVE_CANDIDATE_POOL = 12

# Batch concurrency. Valid defaults are "auto", "1", "2", or "3". Auto uses
# song size and physical memory, and limits Demucs runs to one worker.
SUPPORTED_WORKER_CHOICES = ("auto", "1", "2", "3")
DEFAULT_WORKERS = "auto"

# Analysis defaults. Four beats per bar assumes 4/4 music. Search windows control
# how far from each end the normal selector may inspect when no hard track
# boundary re-anchors it.
BEATS_PER_BAR = 4
INTRO_SEARCH_SECONDS = 120.0
OUTRO_SEARCH_SECONDS = 150.0

# Smaller hop lengths provide finer analysis timing but consume more CPU and
# memory. 512 is a good balance at common 44.1/48 kHz sample rates.
ANALYSIS_HOP_LENGTH = 512

# Minimum splice fade. The editor can automatically increase this up to 30 ms
# for difficult seams. Very large values can soften drum transients.
MINIMUM_CROSSFADE_MS = 10.0

# Automatic splice-mode thresholds. These select how the editor treats the
# exact join without changing the chosen bars. Lowering a threshold makes that
# mode activate more often.
PERCUSSION_PRIORITY_THRESHOLD = 0.65
BASS_PRESERVING_RISK_THRESHOLD = 0.40
HARMONIC_TAIL_COMPATIBILITY_THRESHOLD = 0.55

# Demucs vocal safety limits. If even the best candidate exceeds either limit,
# that side is disabled instead of repeating a lyric or cutting through a sung
# phrase. Values are proportions from 0.0 to 1.0.
MAXIMUM_VOCAL_COVERAGE = 0.45
MAXIMUM_VOCAL_BOUNDARY_RISK = 0.55

# Arrangement safety limits. Candidates above these risks are disabled even if
# their exact waveform splice is clean, preventing buildup resets and abrupt bass
# withdrawals from being repeated.
MAXIMUM_BUILDUP_RISK = 0.60
MAXIMUM_BASS_RESET_RISK = 0.65

# A strongly negative section-role match means the technically best loop comes
# from the wrong narrative part (for example, a chorus used as an outro).
MINIMUM_ARRANGEMENT_FIT = -0.35
MINIMUM_FALLBACK_LOOP_QUALITY = 45.0

# Unique-material preference. When a longer candidate is nearly as strong as the
# top short loop, prefer the longer phrase to avoid repeating the same four bars.
# An 8-bar candidate naturally combines two adjacent four-bar phrases.
PREFER_UNIQUE_MATERIAL = True
UNIQUE_MATERIAL_SCORE_TOLERANCE = 0.12
UNIQUE_MATERIAL_QUALITY_TOLERANCE = 12.0
MINIMUM_UNIQUE_STRUCTURE_MATCH = 0.45

# Stem separation is optional and considerably slower. Setting this to True makes
# --use-stems the normal behavior; the CLI flag can only enable, not disable it.
DEFAULT_USE_STEMS = False

# Stem construction runs only when Demucs can reconstruct the source reliably
# and the selected phrase contains enough vocal material to benefit from removal.
MINIMUM_STEM_CONSTRUCTION_RELIABILITY = 0.65
MINIMUM_VOCAL_COVERAGE_FOR_INSTRUMENTAL_EDIT = 0.08

# Existing output files are normally skipped. Set True to rebuild them on every
# run; --overwrite can enable rebuilding for an individual run.
DEFAULT_OVERWRITE = False

# Optional named strategy used when --preset is omitted. Use None for the normal
# settings above, "auto", or one of: "club", "subtle", "slow-song",
# "vocal-safe", "intro-only", "outro-only".
DEFAULT_PRESET = None

# Preset definitions. You may edit these values, add a new named preset, or
# remove one you never use. Every preset requires all five fields:
#
# - intro_bars / outro_bars: total extension length; 0 disables that side.
# - use_stems: whether Demucs runs automatically for this preset.
# - minimum_loop_quality: 0–100 safety floor. A weaker candidate is disabled.
# - maximum_repetitions: maximum times one short source unit may be copied.
#
# Bar values must also appear in SUPPORTED_BAR_COUNTS above.
PRESET_DEFINITIONS = {
    "club": {
        "intro_bars": 16,
        "outro_bars": 16,
        "use_stems": False,
        "minimum_loop_quality": 45.0,
        "maximum_repetitions": 4,
    },
    "subtle": {
        "intro_bars": 4,
        "outro_bars": 4,
        "use_stems": False,
        "minimum_loop_quality": 58.0,
        "maximum_repetitions": 1,
    },
    "slow-song": {
        "intro_bars": 4,
        "outro_bars": 0,
        "use_stems": False,
        "minimum_loop_quality": 62.0,
        "maximum_repetitions": 1,
    },
    "vocal-safe": {
        "intro_bars": 8,
        "outro_bars": 0,
        "use_stems": True,
        "minimum_loop_quality": 60.0,
        "maximum_repetitions": 2,
    },
    "intro-only": {
        "intro_bars": 8,
        "outro_bars": 0,
        "use_stems": False,
        "minimum_loop_quality": 50.0,
        "maximum_repetitions": 2,
    },
    "outro-only": {
        "intro_bars": 0,
        "outro_bars": 8,
        "use_stems": False,
        "minimum_loop_quality": 50.0,
        "maximum_repetitions": 2,
    },
}
