# Developer guide

This guide covers repository ownership, configuration, generated artifacts, tests, coverage, and maintainer workflows. Start with `CONTRIBUTING.md` for setup and the definition of done.

## Project layout

```text
AudioExtender/
├── main.py              # CLI and batch runner
├── settings.py          # User-editable application defaults
├── audioextender/       # Application package, organized by domain
│   ├── analysis/        # Key analysis, selection, validation, and scoring
│   ├── audio/           # Loading, quality, WAV metadata, and stems
│   ├── core/            # Configuration, models, interfaces, and presets
│   ├── imports/         # Source import workflows and route handlers
│   ├── infrastructure/  # Background tasks, caching, and progress
│   ├── library/         # Library identity, metadata mutations, relocation, backup, and export
│   ├── processing/      # Track, batch, and web-job orchestration
│   ├── reporting/       # Feedback and processing reports
│   ├── repositories/    # Jobs, catalog, analysis, feedback, and system-state persistence
│   ├── set_builder/     # Natural-language intention planning and provider fallback
│   └── web/
│       ├── application.py               # FastAPI factory, wiring, and legacy routes
│       ├── composition.py               # Explicit paths and owned runtime dependencies
│       ├── job_routes.py                 # Queue lifecycle
│       ├── job_media_routes.py           # Audio, waveform, cues, and downloads
│       ├── library_routes.py             # Paginated DJ Library catalog
│       ├── library_maintenance_routes.py # Integrity and reconciliation
│       ├── metadata_batch_routes.py       # Genre, tags, artwork, propagation batches
│       ├── reporting_routes.py           # Feedback and key verification
│       ├── set_builder_routes.py          # Set catalog and playlist exports
│       └── settings_routes.py             # Settings, storage, backup, relocation
├── web/                  # Browser shell, feature modules, shared UI, and styles
├── tests/               # Unit/contract tests, fixtures, and isolated browser smoke workflows
├── scripts/             # Quality, coverage, stability, browser-smoke, and evaluation commands
├── docs/                # Architecture, ownership contracts, audits, and operating guides
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

See [`architecture.md`](architecture.md) for package ownership,
dependency rules, contribution recipes, and the verification matrix. The
current file inventory and test locations are in
[`repository-map.md`](repository-map.md). Compatibility-sensitive
rationale and revisit conditions are indexed in
[`decisions/`](decisions/README.md).
Contributor setup, placement rules, and the supported verification commands are
summarized in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Maintainer quick guide

The project is organized by responsibility so manual changes can stay local.
Use this table before searching through the larger composition files:

| If you need to change…                                                                      | Start in…                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| BPM, beat grid, key, confidence, energy, or readiness                                       | `audioextender/analysis/`                                                                                                                                                              |
| Candidate selection or safety                                                               | `analysis/selection_coordinator.py`, `candidate_selection.py`, `candidate_validator.py`                                                                                                |
| Crossfades and audible splice behavior                                                      | `analysis/splice_policy.py`, `processing/extended_edit.py`                                                                                                                             |
| WAV metadata, artwork embedding, or audio quality                                           | `audio/wav_metadata.py`, `audio/quality.py`                                                                                                                                            |
| Recording IDs, versions, duplicates, or track paths                                         | `library/recording_identity.py`, `repositories/track_catalog.py`                                                                                                                       |
| Processing queue behavior                                                                   | `processing/web_jobs.py`, `web/job_routes.py`, `repositories/jobs.py`                                                                                                                  |
| Audio delivery, waveform, cues, or batch downloads                                          | `web/job_media_routes.py`                                                                                                                                                              |
| DJ Library API filters                                                                      | `web/library_routes.py`                                                                                                                                                                |
| Integrity scan, catalog reconciliation, or repair                                           | `web/library_maintenance_routes.py`                                                                                                                                                    |
| Bulk genre, WAV-tag, artwork, or catalog propagation                                        | `web/metadata_batch_routes.py`, `library/metadata_mutations.py`                                                                                                                        |
| Settings, storage, backup, or relocation                                                    | `web/settings_routes.py` and `audioextender/library/`                                                                                                                                  |
| Library health and post-reconnect verification                                              | `web/settings_routes.py` (`/api/settings/library-health`)                                                                                                                              |
| YouTube, SoundCloud, local, or playlist imports                                             | `audioextender/imports/`                                                                                                                                                               |
| Import failure review and retries                                                           | `web/import-issues.js`                                                                                                                                                                 |
| Authorized/local import browser state, queue coordination, and API routes                   | `web/import-workspace.js`                                                                                                                                                              |
| Local-audio staging, progress, and workspace import lifecycle                               | `web/local-audio-import.js`                                                                                                                                                            |
| Playlist matching, permissions, and Creative Commons verification                           | `web/playlist-import.js`                                                                                                                                                               |
| Cancellable browser polling                                                                 | `web/background-task-controller.js`                                                                                                                                                    |
| Music Files UI                                                                              | `web/music-files.js` and `web/styles.css`                                                                                                                                              |
| DJ Library UI                                                                               | `web/dj-library.js`, `web/dj-library-model.js`, and `web/styles.css`                                                                                                                   |
| Set Builder UI composition                                                                  | `web/set-builder.js`, `web/set-builder-policy.js`, and `web/styles.css`                                                                                                                |
| Candidate review waveforms                                                                  | `web/candidate-review.js` and `web/candidate-waveform-editor.js`                                                                                                                       |
| Processing detail waveforms                                                                 | `web/processing-job-detail.js`                                                                                                                                                         |
| Shared genre and metadata UI                                                                | `web/track-metadata-ui.js`                                                                                                                                                             |
| Set Builder state and edit history                                                          | `web/set-builder-state.js`, `web/set-builder-commands.js`                                                                                                                              |
| Set Builder browser API and planning lifecycle                                              | `web/set-builder-api.js`, `web/set-planning-client.js`                                                                                                                                 |
| Deterministic proposal/fallback policy                                                      | `web/set-builder-classic-planner.js`                                                                                                                                                   |
| Set Builder presentation helpers                                                            | `web/set-builder-view-model.js`                                                                                                                                                        |
| Set Builder brief interpretation or AI providers                                            | `audioextender/set_builder/intention_planner.py`                                                                                                                                       |
| Set Builder candidate shortlists or plan validation                                         | `audioextender/set_builder/candidate_retriever.py`, `audioextender/set_builder/plan_validator.py`                                                                                      |
| AI track ordering, comparison, repairs, fallback, evaluation, persistence, or job lifecycle | `audioextender/set_builder/track_planner.py`, `plan_comparator.py`, `proposal_repairer.py`, `plan_evaluator.py`, `planning_jobs.py`, `planning_store.py`, `web/set-planning-client.js` |
| Shared dropdowns, notices, formatting, or pagination                                        | `web/shared-components.js`                                                                                                                                                             |
| Catalog cancellation, debounce, stale-response protection, or filter persistence            | `web/request-state-controller.js`                                                                                                                                                      |
| Preview playback behavior                                                                   | `web/playback.js`                                                                                                                                                                      |
| Shared frontend API, DOM, feedback, or descriptor capabilities                              | `web/frontend-services.js`, `web/api-client.js`                                                                                                                                        |
| Browser workflow, focus, responsive, accessibility, or warm-cache restart regression        | `tests/browser/workflows.spec.js`, `tests/browser/frontend-restart.spec.js`, `docs/browser-smoke-testing.md`                                                                           |
| Architecture dependency or placement rule                                                   | `docs/architecture.md`, `docs/decisions/`, `tests/unit/architecture/test_boundaries.py`                                                                                                |

`web_app.py` is only a compatibility launcher. The server is composed in
`audioextender/web/application.py`, which constructs services and injects them
into router factories. New HTTP functionality should normally live in a
focused `*_routes.py` module with a dependency dataclass, rather than adding
another feature directly to `application.py`.

Long-running work is likewise owned outside the composition root. Creative
Commons download/retry execution, artwork thumbnail generation, downloaded-track
analysis queuing, audio-quality scanning, and catalog projection construction
live in their import, library, or focused web service modules. Creative Commons
delivery and import-issue report recovery are owned by
`imports/creative_commons_routes.py`. Preset persistence and downloaded-library
read/media delivery are owned by `web/preset_routes.py` and
`web/downloaded_library_routes.py`. Recording-family operations live in
`web/recording_family_routes.py`; downloaded-track deletion and metadata
workflows live in `web/downloaded_track_mutation_routes.py` and delegate atomic
file/tag/sidecar/catalog changes to `library/metadata_mutations.py`.
Downloaded analysis selection lives in `web/downloaded_analysis_routes.py` and
delegates job creation to `library/analysis_queue.py`. Job reprocessing,
candidate auditions, review rejection, and candidate feedback live in
`web/job_review_routes.py`; queue controls and rendered media remain in their
existing focused job routers.
Reporting projections, analytics, track overrides, report audio availability,
and completed-library job details are owned by `web/reporting_routes.py`.
`create_app()` delegates service-family construction to private builders and
uses `_register_routers()` as the single delivery composition boundary.
`application.py` wires those owners and retains only small compatibility
wrappers where scripts and integration tests still rely on the historical entry
point.

`JobRepository` remains the stable persistence facade, but SQL is divided among
focused mixins under `audioextender/repositories/`. The downloaded-track catalog
is itself composed by `track_catalog.py` from core CRUD, descriptor, recording
family, projection, metadata-state, and analysis-state mixins. Add a database
method to the narrow mixin that owns the data instead of expanding either
`track_catalog.py` or `repositories/facade.py`.

The music-library path saved in Settings is durable SQLite state. Import code
must obtain it through the injected library-root callback, reject an offline
external drive, and never silently write to `~/Music` or a temporary folder.

Before committing any maintained-source change, run the authoritative standard
gate:

```bash
make quality
git diff --check
```

Add the relevant extended gate for the risk being changed:

```bash
make coverage   # coverage-sensitive behavior
make stability  # persistence/import/relocation/export/Set Builder durability
make browser    # browser workflow, focus, viewport, or accessibility
```

Install the pinned Chromium binary once with
`npm run check:browser:install`. Browser smoke tests use a temporary database and
library and never open the user's configured catalog or music folder.

Provider fallback, schema, and sanitization tests do not require a running
model. The live local-model acceptance suite is opt-in:

```bash
AUDIOEXTENDER_RUN_LOCAL_LLM_TESTS=1 .venv/bin/python -m unittest tests.integration.set_builder.test_local_intention_acceptance
```

When moving modules or changing architectural relationships, also refresh the
Graphify map. The CLI `update` command re-extracts code and regenerates the
interactive web graph. Documentation changes need Graphify's semantic
`--update` skill workflow (or its headless `extract` command with a configured
model); the code-only CLI update does not incorporate them:

```bash
graphify update .
# If only the web visualization needs refreshing:
graphify export html
```

Downloaded-library metadata batches share one lifecycle in
`infrastructure/batch_operations.py`. Add new batch work through that registry
so progress, cancellation, retry, results, and structured errors remain
consistent with genre, WAV-tag, artwork, catalog-propagation, and relocation
operations.

All user-visible background work also has an executor-neutral internal view in
`infrastructure/operation_lifecycle.py`. Use its immutable projection,
capability, error, and action-receipt types when code must inspect multiple
operation families. Keep feature-specific execution and persistence in the
owning service, and preserve existing endpoint serializers for compatibility.

Mutation APIs return an operation `receipt` with five user-facing facts: what
was requested, what changed, where data was written, what failed, and whether
the result survives restart. Use `core/operation_feedback.py` for new saves and
the batch registry for new background work; do not invent route-specific
success strings that can drift from the actual result.

`repositories/facade.py::JobRepository` remains the backwards-compatible
repository entry point. New services should accept a narrow protocol from
`repositories/capabilities.py`. Database creation and compatibility migrations
belong to the named, ordered steps in `repositories/schema.py`; do not add new
table setup to the facade constructor.

### Architecture boundaries

The application keeps musical policy separate from delivery and signal
processing:

- `library/musical_profile.py` owns the versioned musical facts delivered to
  DJ Library and Set Builder: normalized key/Camelot, energy, DJ roles, vocals,
  timing, confidence, and provenance. Change its shared Python/browser golden
  fixture whenever the policy intentionally changes.
- `candidate_selection.py` accepts one typed `SelectionRequest` for either an
  intro or outro. Automatic-length policy can be tested without the CLI.
- `selection_coordinator.py` applies the same protected-boundary retries,
  Demucs-aware reranking, user choice, and safety fallback workflow to both
  intros and outros.
- `stem_provider.py` owns optional Demucs execution, cache validation,
  temporary-file cleanup, reliability data, and vocal-boundary detection.
- `export_service.py` writes final WAVs, splice previews, candidate auditions,
  cue points, and per-track cue sheets through one testable artifact boundary.
- `track_processor.py` is the stable single-track transaction facade and owns
  only validation and stage ordering. `analysis_preparation.py`,
  `candidate_selection_orchestration.py`, `render_export_transaction.py`,
  `track_result_builder.py`, and `processing_failure_cleanup.py` own the five
  transaction responsibilities. `track_processing_stages.py` owns only the
  immutable handoff models and arrangement projection. `main.py` retains only
  CLI parsing, batch scheduling, summaries, and a compatibility facade.
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

Edit [`settings.py`](../settings.py) when you want permanent defaults without
typing the same CLI options each time. Command-line arguments still take priority
for an individual run, while per-song musical timestamps remain in
`track_overrides.json`.

| Setting                                        |             Shipped value | Usage and effect                                                                                                          |
| ---------------------------------------------- | ------------------------: | ------------------------------------------------------------------------------------------------------------------------- |
| `SUPPORTED_BAR_COUNTS`                         |    `(0, 2, 4, 8, 16, 32)` | Values accepted by `--intro-bars` and `--outro-bars`. Keep `0` if you want the disable option.                            |
| `DEFAULT_AUTO_BAR_SELECTION`                   |                    `True` | Chooses the most suitable shorter length up to the configured default when no explicit bar count is supplied.             |
| `AUTO_BAR_MAXIMUM_QUALITY_LOSS`                |                     `4.0` | Maximum loop-quality points a longer automatic choice may lose before receiving an extra penalty.                         |
| `DEFAULT_INTRO_BARS`                           |                       `8` | Intro length used when `--intro-bars` is omitted. Try `4` for less repetition.                                            |
| `DEFAULT_OUTRO_BARS`                           |                       `8` | Outro length used when `--outro-bars` is omitted. Set `0` to preserve original endings by default.                        |
| `DEFAULT_MINIMUM_INTRO_LOOP_QUALITY`           |                    `65.0` | Hard intro quality floor. Candidates below this percentage are not exported.                                              |
| `DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY`           |                    `65.0` | Hard outro quality floor. Candidates below this percentage are not exported.                                              |
| `PREFERRED_LOOP_QUALITY_TARGET`                |                    `70.0` | Ranking target. A musically competitive 70%+ candidate is preferred over a lower-scoring option.                          |
| `SUPPORTED_PCM_BITS`                           |                `(16, 24)` | Values accepted by `--bit-depth`. WAV export currently supports these PCM depths.                                         |
| `DEFAULT_PCM_BITS`                             |                      `24` | Normal output depth. `24` is recommended for editing quality; `16` produces smaller files.                                |
| `INPUT_FOLDER_NAME`                            |                 `"input"` | Batch folder relative to the project. CLI `--input-dir` overrides it.                                                     |
| `OUTPUT_FOLDER_NAME`                           |                `"output"` | Export folder relative to the project. CLI `--output-dir` overrides it.                                                   |
| `TRACK_OVERRIDES_FILENAME`                     |  `"track_overrides.json"` | Default per-song rules filename. CLI `--overrides` overrides it.                                                          |
| `CACHE_FOLDER_NAME`                            |                 `"cache"` | Folder for reusable track and Demucs-derived analysis files.                                                              |
| `DEFAULT_CACHE_ENABLED`                        |                    `True` | Enables cache reads and writes during normal runs.                                                                        |
| `DEFAULT_PREVIEW_SECONDS`                      |                     `8.0` | Audio included on each side of a splice in preview files. Total preview length is up to twice this value.                 |
| `DEFAULT_EXPORT_CUES`                          |                    `True` | Writes per-track JSON cue sheets and a batch Rekordbox XML playlist.                                                      |
| `REKORDBOX_XML_FILENAME`                       |         `"rekordbox.xml"` | Filename used for the importable playlist at the output-folder root.                                                      |
| `DEFAULT_CANDIDATE_COUNT`                      |                       `3` | Number of distinct intro/outro alternatives ranked internally for each enabled side.                                      |
| `SUPPORTED_WORKER_CHOICES`                     | `("auto", "1", "2", "3")` | Values accepted by `--workers`. Increase carefully if you also increase the maximum worker count.                         |
| `DEFAULT_WORKERS`                              |                  `"auto"` | Normal concurrency mode. `auto` is recommended, especially with Demucs.                                                   |
| `BEATS_PER_BAR`                                |                       `4` | Assumed meter. Keep `4` for ordinary 4/4 music; changing it alters bar grouping throughout analysis.                      |
| `INTRO_SEARCH_SECONDS`                         |                   `120.0` | Maximum opening search window when no manual boundary re-anchors selection.                                               |
| `OUTRO_SEARCH_SECONDS`                         |                   `150.0` | Maximum closing search window when no manual boundary re-anchors selection.                                               |
| `ANALYSIS_HOP_LENGTH`                          |                     `512` | Analysis resolution. Smaller values are more precise but slower and more memory-intensive.                                |
| `MINIMUM_CROSSFADE_MS`                         |                    `10.0` | Shortest splice fade. The adaptive editor may increase it to 30 ms for difficult seams.                                   |
| `PERCUSSION_PRIORITY_THRESHOLD`                |                    `0.65` | Drum-strength level that permits a short, transient-preserving splice.                                                    |
| `BASS_PRESERVING_RISK_THRESHOLD`               |                    `0.40` | Bass-reset risk that activates a longer low-end-preserving join.                                                          |
| `HARMONIC_TAIL_COMPATIBILITY_THRESHOLD`        |                    `0.55` | Timbre/tail score below which sustained synth, chord, or reverb material receives extra carry-over.                       |
| `INTERACTIVE_CANDIDATE_POOL`                   |                      `12` | Maximum alternatives available through `R` during interactive review. Only three are shown at once.                       |
| `MAXIMUM_VOCAL_COVERAGE`                       |                    `0.45` | With Demucs, disables a selected side when sustained vocals occupy more than 45% of its candidate.                        |
| `MAXIMUM_VOCAL_BOUNDARY_RISK`                  |                    `0.55` | With Demucs, disables a selected side when an active vocal phrase overlaps a splice edge too strongly.                    |
| `MINIMUM_STEM_CONSTRUCTION_RELIABILITY`        |                    `0.65` | Minimum aligned Demucs reconstruction score required before stems may be heard in an edit.                                |
| `MINIMUM_VOCAL_COVERAGE_FOR_INSTRUMENTAL_EDIT` |                    `0.08` | Uses instrumental construction only when enough vocal content exists to justify changing the full mix.                    |
| `MAXIMUM_BUILDUP_RISK`                         |                    `0.60` | Disables a candidate that behaves too strongly like a runway into a drop or new section.                                  |
| `MINIMUM_ARRANGEMENT_FIT`                      |                   `-0.35` | Disables a technically clean candidate when its section role is strongly wrong, such as a chorus used as an outro.        |
| `MINIMUM_FALLBACK_LOOP_QUALITY`                |                    `45.0` | Prevents recovery from replacing a rejected loop with an audibly weak fallback merely because its section label is safer. |
| `MAXIMUM_BASS_RESET_RISK`                      |                    `0.65` | Disables a candidate whose loop would noticeably reset or remove low-frequency energy.                                    |
| `PREFER_UNIQUE_MATERIAL`                       |                    `True` | Prefers compatible longer source phrases over repeating a shorter unit.                                                   |
| `UNIQUE_MATERIAL_SCORE_TOLERANCE`              |                    `0.12` | Maximum internal-score sacrifice allowed to gain more unique musical material. Lower values are stricter.                 |
| `UNIQUE_MATERIAL_QUALITY_TOLERANCE`            |                    `12.0` | Maximum loop-quality percentage-point sacrifice allowed for a longer unit.                                                |
| `MINIMUM_UNIQUE_STRUCTURE_MATCH`               |                    `0.45` | Minimum structural similarity required between the beginning and ending blocks of a longer phrase.                        |
| `DEFAULT_USE_STEMS`                            |                   `False` | Set `True` to use Demucs by default. This makes normal runs substantially slower.                                         |
| `DEFAULT_OVERWRITE`                            |                   `False` | Set `True` to rebuild existing output files during normal runs.                                                           |
| `DEFAULT_PRESET`                               |                    `None` | Sets a named strategy for normal runs. Keep `None` to use the individual defaults above.                                  |
| `PRESET_DEFINITIONS`                           |        Six named profiles | Edit, add, or remove presets exposed by the `--preset` option.                                                            |

The most useful personal setup for shorter edits would be:

```python
DEFAULT_INTRO_BARS = 4
DEFAULT_OUTRO_BARS = 0
```

Avoid changing scoring formulas inside `audioextender/analysis/` unless you are intentionally
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

## Developer note: generated artifacts

Graphify-generated architecture and analysis artifacts live under
`graphify-out/`. They are not required for normal development and new artifacts
are ignored by Git. Move durable architecture notes into `docs/`; if Graphify
outputs are intentionally retained in the repository, treat them as generated
documentation rather than source.

## Automated tests

DJ Library Studio includes fast unit tests built on Python's standard `unittest`
library, so running the normal suite does not require another test framework:

```bash
python3 -m unittest discover -s tests -t . -v
```

The suite uses synthetic audio and mocks for hardware/resource decisions. It
does not run Demucs or process the songs in `input`, keeping feedback fast and
repeatable. It covers configuration validation, overrides, CLI helpers,
candidate-quality calibration, adaptive splices, progress/slow-task reporting,
memory-aware worker selection, persistent reports, and safe cache cleanup.

Run the focused stability gate when changing imports, catalog persistence,
reanalysis, relocation, or Set Builder exports:

```bash
./scripts/run_stability_gate.sh
```

This creates a temporary library containing a real small WAV and verifies that
playlist membership, artwork, genre metadata, completed analysis history,
manual key verification, listening feedback, relocated paths, and playlist
exports survive reimport, application restart, and reanalysis. It never reads
or modifies the user's music library.

### Code coverage in VS Code

Install the development requirements and JavaScript dependencies, then run
coverage with the project virtual environment active:

```bash
python3 -m pip install -r requirements-dev.txt
npm install
npm run coverage
```

This creates LCOV reports for all maintained Python application and script code
and every JavaScript file under `web/`. The recommended **Code Coverage**
extension by Markis Taylor is configured to load both reports automatically.
Tests, dependencies, caches, and generated output are not coverage targets.

Use Node 20 or newer for JavaScript coverage (`nvm use 22` is recommended).
Run the complete local quality gate after installing the development
requirements:

```bash
./scripts/check_quality.sh
./scripts/check_coverage.sh
```

GitHub Actions runs the standard quality and stability gates on Python 3.12 and
Node 22, plus the isolated Playwright browser and accessibility workflows. The
quality runner installs FFmpeg and libsndfile before exercising audio metadata
and WAV workflows. The workflow is defined in
[`ci.yml`](../.github/workflows/ci.yml).
Static audit findings and interpretation are recorded in
[`dead-code-dependency-audit.md`](dead-code-dependency-audit.md).

The quality command is the authoritative standard check and does not modify
source files. Coverage is a separate diagnostic tier, while
`./scripts/run_stability_gate.sh` remains the extended check for high-risk
persistence, import, relocation, export, and Set Builder changes. See
[`development-quality.md`](development-quality.md) for the verified
tool versions, current coverage, formatting debt ratchets, exclusions, and
regression policy. Permanent contribution rules are in [`AGENTS.md`](../AGENTS.md).

## Deferred structural migrations

The current repository shape is intentional. Do not mix any of the following
changes into routine feature, cleanup, or documentation work:

- moving the Python package under a `src/` directory;
- moving root tool configuration into a separate `config/` directory;
- introducing npm workspaces or a `packages/` hierarchy; or
- replacing the `unittest` suite with pytest.

Each change would affect launchers, imports, test discovery, CI, coverage, and
developer workflows. Revisit one only as a dedicated, measured migration with a
compatibility plan and rollback path.

The tests follow the same separation as the application modules: domain logic
is tested independently from file I/O, terminal presentation, and expensive
external stem separation. When adding a feature, place its policy in a small
helper and inject external dependencies where practical; this keeps the code
open to new behavior without coupling tests to Demucs, FFmpeg, or real tracks.

Set Builder prepares prompt briefs through `/api/set-builder/prepare-brief`.
This asks the configured model for interpretation and editable journey sections
in a single request. Invalid or reordered journeys use the shared deterministic
journey policy, with evidence shown as AI interpreted. The older
interpretation and journey endpoints remain available for compatibility.
Identical brief, vocabulary, duration, and model requests share in-flight work
and reuse results for 30 minutes (up to 64 entries per application process).
Restarting the application clears this cache.

Routine library status requests check catalogued tracks without recursively
walking the library drive. Supporting-file sizes reuse the previous full scan;
an explicit library verification refreshes the complete filesystem totals.

Primary navigation binds before feature construction, so a failed feature cannot
prevent tab clicks from switching views. View-loading failures are surfaced as
notifications. Because a cached child ES module with obsolete exports can stop
`app.js` before any initialization runs, the HTML shell also has a minimal
pre-module tab switcher and shows **Copy diagnostics** and **Reload app** actions
if startup does not complete. After successful initialization the normal
navigation controller takes over. Application HTML and `/assets` responses use
`Cache-Control: no-store`.

`web/asset-manifest.json` is the only frontend revision authority. When a
frontend release changes, bump its `revision` once. The server renders a complete
import map so the entrypoint, stylesheet, and every JavaScript module receive
the same revision. Do not add `?v=` query strings to module imports or edit
version strings in `app.js`, feature modules, or `index.html`. The macOS launcher
adds a fresh query parameter when opening the app so relaunching does not reuse a
stale entry page.

When changing module exports, test both a fresh browser and an already-open
browser with stale cached modules. The browser smoke suite covers a failed entry
module, fallback navigation, reload recovery, diagnostic capture, and a true
same-tab restart from one cacheable frontend revision to another. The Python
web-composition contract checks cache headers, the manifest-rendered module
graph, and the absence of independent module versions.
