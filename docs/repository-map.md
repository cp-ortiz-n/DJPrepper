# Repository Map

This is a navigation guide to the files tracked by Git, plus a short note on
local runtime folders that are intentionally not part of the tracked tree. The
map reflects the current layout; it does not propose moving code.

## Tracked File Hierarchy

```text
.
├── .flake8
├── .gitattributes
├── .gitignore
├── .vscode/
│   ├── extensions.json
│   └── settings.json
├── BACKLOG.md
├── CONTRIBUTING.md
├── LICENSE
├── Makefile
├── README.md
├── Start AudioExtender.command
├── audioextender/
│   ├── __init__.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── candidate_reranker.py
│   │   ├── candidate_selection.py
│   │   ├── candidate_validator.py
│   │   ├── dj_readiness.py
│   │   ├── key_detection.py
│   │   ├── resource_planner.py
│   │   ├── section_context.py
│   │   ├── section_selector.py
│   │   ├── selection_coordinator.py
│   │   ├── selection_metrics.py
│   │   ├── selection_models.py
│   │   ├── splice_policy.py
│   │   ├── style_detector.py
│   │   └── transition_scorer.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── loading.py
│   │   ├── quality.py
│   │   ├── redrum.py
│   │   ├── stem_provider.py
│   │   ├── stems.py
│   │   └── wav_metadata.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── config_factory.py
│   │   ├── exceptions.py
│   │   ├── interfaces.py
│   │   ├── models.py
│   │   ├── operation_feedback.py
│   │   └── presets.py
│   ├── imports/
│   │   ├── __init__.py
│   │   ├── creative_commons.py
│   │   ├── creative_commons_worker.py
│   │   ├── local.py
│   │   ├── playlist_match.py
│   │   ├── routes.py
│   │   └── service.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── background_tasks.py
│   │   ├── batch_operations.py
│   │   ├── cache.py
│   │   ├── operation_lifecycle.py
│   │   └── progress.py
│   ├── library/
│   │   ├── __init__.py
│   │   ├── analysis_queue.py
│   │   ├── artwork_thumbnails.py
│   │   ├── backup.py
│   │   ├── catalog_projection.py
│   │   ├── catalog_projection_builder.py
│   │   ├── catalog_query_service.py
│   │   ├── cue_export.py
│   │   ├── descriptor_service.py
│   │   ├── export_service.py
│   │   ├── identity_inference.py
│   │   ├── metadata_mutations.py
│   │   ├── musical_corrections.py
│   │   ├── musical_profile.py
│   │   ├── recording_identity.py
│   │   ├── relocation.py
│   │   └── track_overrides.py
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── analysis_preparation.py
│   │   ├── batch_runner.py
│   │   ├── candidate_selection_orchestration.py
│   │   ├── extended_edit.py
│   │   ├── job_workflows.py
│   │   ├── processing_failure_cleanup.py
│   │   ├── render_export_transaction.py
│   │   ├── track_processing_stages.py
│   │   ├── track_processor.py
│   │   ├── track_result_builder.py
│   │   └── web_jobs.py
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── feedback.py
│   │   └── processing.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── capabilities.py
│   │   ├── concurrency_probe.py
│   │   ├── facade.py
│   │   ├── feedback.py
│   │   ├── jobs.py
│   │   ├── library_analysis.py
│   │   ├── musical_verification_schema.py
│   │   ├── schema.py
│   │   ├── system_state.py
│   │   ├── track_analysis_state.py
│   │   ├── track_catalog.py
│   │   ├── track_catalog_shared.py
│   │   ├── track_core.py
│   │   ├── track_descriptors.py
│   │   ├── track_metadata_state.py
│   │   ├── track_projections.py
│   │   └── recording_families.py
│   ├── set_builder/
│   │   ├── __init__.py
│   │   ├── candidate_retriever.py
│   │   ├── evaluation_harness.py
│   │   ├── intention_planner.py
│   │   ├── journey_planner.py
│   │   ├── plan_comparator.py
│   │   ├── plan_evaluator.py
│   │   ├── plan_validator.py
│   │   ├── planning_jobs.py
│   │   ├── planning_store.py
│   │   ├── preference_learning.py
│   │   ├── proposal_repairer.py
│   │   ├── release_gate.py
│   │   ├── review_service.py
│   │   ├── track_planner.py
│   │   └── transition_optimizer.py
│   └── web/
│       ├── __init__.py
│       ├── application.py
│       ├── composition.py
│       ├── descriptor_routes.py
│       ├── error_contracts.py
│       ├── job_media_routes.py
│       ├── job_routes.py
│       ├── library_maintenance_routes.py
│       ├── library_routes.py
│       ├── metadata_batch_routes.py
│       ├── reporting_routes.py
│       ├── set_builder_routes.py
│       ├── set_planning_routes.py
│       ├── set_preference_routes.py
│       ├── set_review_routes.py
│       └── settings_routes.py
├── docs/
│   ├── architecture.md
│   ├── architecture-audit.md
│   ├── browser-smoke-testing.md
│   ├── developer-guide.md
│   ├── development-quality.md
│   ├── musical-policy-ownership.md
│   ├── operator-guide.md
│   ├── repository-map.md
│   └── user-guide.md
├── graphify-out/
│   └── memory/
│       ├── query_20260930_170835_47f25d97_extract_the_authorized_youtube_and_soundcloud_impo.md
│       ├── query_20260930_172704_c9070d36_extract_remaining_import_workflows_from_web_app_py.md
│       ├── query_20260930_173204_11d80c79_continue_decomposing_all_import_workflows_and_make.md
│       ├── query_20260930_173612_54b36978_after_extracting_authorized__local_audio__and_play.md
│       ├── query_20260930_174431_eaae9f30_extract_the_creative_commons_import_lifecycle_and.md
│       ├── query_20260930_175912_23ce5382_split_the_monolithic_jobrepository_into_focused_re.md
│       └── query_20260930_project_package_organization.md
├── main.py
├── package-lock.json
├── package.json
├── pyproject.toml
├── requirements-demucs.txt
├── requirements-dev.txt
├── requirements.txt
├── scripts/
│   ├── benchmark_key_confidence.py
│   ├── clean_workspace.py
│   ├── evaluate_key_ensemble.py
│   ├── evaluate_set_builder.py
│   ├── check_coverage.sh
│   ├── check_quality.sh
│   ├── measure_repository_concurrency.py
│   ├── serve_browser_smoke.py
│   └── run_stability_gate.sh
├── settings.py
├── tests/
│   ├── __init__.py
│   ├── browser/
│   │   └── workflows.spec.js
│   ├── fixtures/              # Shared checked-in scenario data
│   ├── integration/           # Cross-package, persistence, filesystem, and provider tests
│   │   └── set_builder/       # Set Builder provider integration
│   ├── javascript/            # Node unit and frontend contract tests
│   ├── support/               # Shared test-only factories and paths
│   └── unit/                  # Mirrors Python application ownership
│       ├── analysis/
│       ├── architecture/
│       ├── audio/
│       ├── core/
│       ├── imports/
│       ├── infrastructure/
│       ├── library/
│       ├── processing/
│       ├── reporting/
│       ├── repositories/
│       ├── set_builder/
│       └── web/
├── web/
│   ├── app.js
│   ├── api-client.js
│   ├── background-task-controller.js
│   ├── candidate-review.js
│   ├── candidate-waveform-editor.js
│   ├── dj-library.js
│   ├── dj-library-filters.js
│   ├── dj-library-intelligence.js
│   ├── dj-library-model.js
│   ├── dj-library-selection.js
│   ├── dj-library-view.js
│   ├── import-queue.js
│   ├── import-issues.js
│   ├── import-workspace.js
│   ├── local-audio-import.js
│   ├── playlist-import.js
│   ├── processing-workspace.js
│   ├── processing-job-detail.js
│   ├── processing-workspace-view.js
│   ├── index.html
│   ├── music-files.js
│   ├── playback.js
│   ├── reporting.js
│   ├── request-state-controller.js
│   ├── set-builder-api.js
│   ├── set-builder-classic-planner.js
│   ├── set-builder-commands.js
│   ├── set-builder-feedback.js
│   ├── set-builder-plan-view.js
│   ├── set-builder-planning-session.js
│   ├── set-builder-saved-sets.js
│   ├── set-builder-state.js
│   ├── set-builder-transition-editor.js
│   ├── set-builder-view-model.js
│   ├── set-builder.js
│   ├── set-builder-policy.js
│   ├── searchable-selects.js
│   ├── track-metadata-ui.js
│   ├── set-planning-client.js
│   ├── settings.js
│   ├── frontend-services.js
│   ├── shared-components.js
│   └── styles.css
└── web_app.py
```

The hierarchy highlights ownership-significant files rather than promising an
exhaustive manifest. Use `rg --files` for the current tracked inventory.

## Where Things Belong

| Area                                                        | Responsibility                                                                                                                     |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `main.py`, `web_app.py`, `audioextender/web/application.py` | CLI entry, compatibility launcher, and web application composition                                                                 |
| `audioextender/core/`                                       | Shared configuration, data models, interfaces, presets, errors, and operation receipts                                             |
| `audioextender/audio/`                                      | Audio loading, quality, stems, and WAV metadata                                                                                    |
| `audioextender/analysis/`                                   | Musical analysis, candidate selection/scoring, validation, and splice policy                                                       |
| `audioextender/processing/`                                 | Track and batch workflows, edits, and web-job orchestration                                                                        |
| `audioextender/imports/`                                    | Local and external-source imports, playlist matching, and import routes                                                            |
| `audioextender/library/`                                    | Track identity, overrides, backup, relocation, metadata mutation, and exports                                                      |
| `audioextender/repositories/`                               | SQLite persistence grouped by jobs, catalog, analysis, feedback, and system state                                                  |
| `audioextender/infrastructure/`                             | Shared cache, progress, background-task, and batch-operation support                                                               |
| `audioextender/reporting/`                                  | Processing summaries and listening feedback                                                                                        |
| `audioextender/set_builder/`                                | Intention/journey planning, candidate selection, validation, evaluation, preferences, plan jobs, and production release assessment |
| `audioextender/web/`                                        | FastAPI composition and focused API route modules                                                                                  |
| `web/`                                                      | Browser shell, feature modules, shared controls, and styles                                                                        |
| `scripts/`                                                  | Quality, coverage, browser-smoke, stability, evaluation, and benchmark tools                                                       |
| `docs/`                                                     | Maintainer architecture and repository navigation documentation                                                                    |
| `graphify-out/memory/`                                      | Checked-in Graphify-generated investigation notes; not runtime code or canonical architecture docs                                 |

The intended dependency direction is described in [architecture.md](architecture.md):
HTTP/CLI delivery calls application services; business workflows use analysis,
audio, and core policy; persistence stays behind repositories. Router modules
should receive dependencies from `application.py`, not import application
globals. Keep musical decision logic out of route handlers and browser modules.

## Test Organization

Python unit tests mirror the owning application package under `tests/unit/`.
Cross-package, persistence, filesystem, and provider tests live under
`tests/integration/`. Node unit tests live in `tests/javascript/`, while real-
browser smoke scenarios live under `tests/browser/` for Playwright discovery.
Shared Python builders and path helpers live in `tests/support/`; checked-in
scenario data remains in `tests/fixtures/`.

Python uses `unittest` and `test_*.py`; Node uses `*.test.js`. Every nested
Python test directory is an importable package so focused module execution and
recursive discovery use the same names. The application itself does not use a
`src/` installation layout; changing that convention remains a separate
migration of launchers, imports, coverage, CI, and packaging.

| Test group                               | Files                       |
| ---------------------------------------- | --------------------------- |
| Architecture and compatibility           | `unit/architecture/`        |
| Python package behavior                  | `unit/<owning-package>/`    |
| Cross-boundary workflows                 | `integration/`              |
| Set Builder live-provider acceptance     | `integration/set_builder/`  |
| Browser modules and contracts            | `javascript/`               |
| Browser workflow and accessibility smoke | `browser/workflows.spec.js` |

The Set Builder scenario file is `fixtures/set_builder_eval_scenarios.json`; it
is used by both planning tests and `scripts/evaluate_set_builder.py`. The local
model acceptance test is opt-in and requires the relevant provider/model; the
ordinary suite uses deterministic behavior and mocks.
`test_set_release_gate.py` covers the production acceptance policy, including
the manual-listening requirement, provider failures, genre scarcity, and
planning-job summaries.

Run the authoritative standard gate from the repository root:

```bash
./scripts/check_quality.sh
```

Run the focused stability workflow with:

```bash
./scripts/run_stability_gate.sh
```

Run the isolated Chromium workflow/accessibility gate with:

```bash
npm run check:browser:install  # first use only
npm run check:browser
```

Coverage reporting is configured through `npm run coverage`; it writes LCOV
reports under `coverage/` for the Python application/scripts and browser code.

### Test growth guidance

- Put unit tests in the directory matching the owning application package; put
  cross-boundary workflows in `integration/` and Node tests in `javascript/`.
- Keep every Python test directory importable with `__init__.py`, and preserve
  recursive discovery through the repository-owned quality scripts.
- Keep test data builders in `support/` only when they are genuinely shared;
  keep domain-specific fixtures under `fixtures/` and avoid checking in real
  audio files or personal library data.
- Keep slow, external-provider, or catalog-scale checks explicitly opt-in or in
  dedicated scripts so the fast deterministic suite stays useful.

## Project Configuration And Operations

| File                                               | Purpose                                                                  |
| -------------------------------------------------- | ------------------------------------------------------------------------ |
| `README.md`                                        | Setup, user workflows, tests, and maintainer quick guide                 |
| `CONTRIBUTING.md`                                  | Contributor setup, placement rules, and definition-of-done commands      |
| `Makefile`                                         | Stable aliases for the repository-owned quality and verification scripts |
| `BACKLOG.md`                                       | Planned and audited product work                                         |
| `docs/decisions/`                                  | Indexed architecture decisions and compatibility guarantees              |
| `pyproject.toml`, `.flake8`                        | Python coverage, lint, and type-check configuration                      |
| `requirements.txt`                                 | Runtime Python dependencies                                              |
| `requirements-dev.txt`                             | Development/test tools, including coverage.py                            |
| `requirements-demucs.txt`                          | Optional Demucs dependency set                                           |
| `package.json`, `package-lock.json`                | JavaScript dependencies and test/check/coverage scripts                  |
| `.vscode/settings.json`, `.vscode/extensions.json` | Workspace test/editor settings and extension recommendations             |
| `settings.py`                                      | Application configuration/defaults                                       |
| `Start AudioExtender.command`                      | macOS launcher                                                           |
| `LICENSE`, `.gitattributes`, `.gitignore`          | Licensing and Git behavior                                               |

## Local Runtime Folders

The following may exist in a developer workspace but are not enumerated in the
tracked hierarchy because they contain generated data, dependencies, or user
audio rather than maintained source:

- `input/` and `output/`: source tracks, exports, reports, and local library data.
- `cache/`: reusable waveform and analysis cache files.
- `.venv/`, `node_modules/`, `__pycache__/`: installed dependencies and Python
  runtime artifacts.
- `coverage/`, `htmlcov/`: generated test coverage reports.

These folders should stay separate from source and tests. In particular, do not
add personal audio, database/report output, caches, or environment directories
to Git.
