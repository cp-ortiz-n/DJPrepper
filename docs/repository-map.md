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
├── LICENSE
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
│   │   ├── local.py
│   │   ├── playlist_match.py
│   │   ├── routes.py
│   │   └── service.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── background_tasks.py
│   │   ├── batch_operations.py
│   │   ├── cache.py
│   │   └── progress.py
│   ├── library/
│   │   ├── __init__.py
│   │   ├── backup.py
│   │   ├── cue_export.py
│   │   ├── export_service.py
│   │   ├── identity_inference.py
│   │   ├── metadata_mutations.py
│   │   ├── recording_identity.py
│   │   ├── relocation.py
│   │   └── track_overrides.py
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── batch_runner.py
│   │   ├── extended_edit.py
│   │   ├── track_processor.py
│   │   └── web_jobs.py
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── feedback.py
│   │   └── processing.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── facade.py
│   │   ├── feedback.py
│   │   ├── jobs.py
│   │   ├── library_analysis.py
│   │   ├── system_state.py
│   │   └── track_catalog.py
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
│       ├── descriptor_routes.py
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
│   └── repository-map.md
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
│   ├── evaluate_key_ensemble.py
│   ├── evaluate_set_builder.py
│   └── run_stability_gate.sh
├── settings.py
├── tests/
│   ├── __init__.py
│   ├── factories.py
│   ├── fixtures/
│   │   └── set_builder_eval_scenarios.json
│   ├── frontend_modules.test.js
│   ├── import_queue.test.js
│   ├── playback_behavior.test.js
│   ├── request_state_controller.test.js
│   ├── set_planning_client.test.js
│   ├── test_application_services.py
│   ├── test_architecture_services.py
│   ├── test_audio_quality.py
│   ├── test_background_tasks.py
│   ├── test_batch_operations.py
│   ├── test_behavior_workflows.py
│   ├── test_cli_helpers.py
│   ├── test_config_and_overrides.py
│   ├── test_dj_readiness.py
│   ├── test_export_service.py
│   ├── test_feedback_and_reranking.py
│   ├── test_frontend_contracts.py
│   ├── test_import_service.py
│   ├── test_integration_synthetic.py
│   ├── test_intention_planner.py
│   ├── test_journey_planner.py
│   ├── test_key_analysis.py
│   ├── test_library_backup.py
│   ├── test_library_relocation.py
│   ├── test_local_intention_acceptance.py
│   ├── test_package_structure.py
│   ├── test_plan_comparator.py
│   ├── test_playlist_match_service.py
│   ├── test_progress_and_resources.py
│   ├── test_proposal_repairer.py
│   ├── test_recording_identity.py
│   ├── test_reports_and_cache.py
│   ├── test_scoring_and_splices.py
│   ├── test_set_candidate_planning.py
│   ├── test_set_plan_evaluator.py
│   ├── test_set_release_gate.py
│   ├── test_set_preference_learning.py
│   ├── test_set_review_service.py
│   ├── test_stability_workflow.py
│   ├── test_stem_provider.py
│   ├── test_style_detector.py
│   ├── test_track_descriptors.py
│   ├── test_track_planner.py
│   ├── test_transition_optimizer.py
│   ├── test_transition_scorer.py
│   ├── test_wav_metadata.py
│   └── test_web_app.py
├── web/
│   ├── app.js
│   ├── background-task-controller.js
│   ├── dj-library.js
│   ├── import-queue.js
│   ├── import-issues.js
│   ├── import-workspace.js
│   ├── local-audio-import.js
│   ├── playlist-import.js
│   ├── processing-workspace.js
│   ├── index.html
│   ├── music-files.js
│   ├── playback.js
│   ├── reporting.js
│   ├── request-state-controller.js
│   ├── set-builder-api.js
│   ├── set-builder-classic-planner.js
│   ├── set-builder-commands.js
│   ├── set-builder-state.js
│   ├── set-builder-view-model.js
│   ├── set-builder.js
│   ├── set-planning-client.js
│   ├── settings.js
│   ├── shared-components.js
│   └── styles.css
└── web_app.py
```

## Where Things Belong

| Area | Responsibility |
| --- | --- |
| `main.py`, `web_app.py`, `audioextender/web/application.py` | CLI entry, compatibility launcher, and web application composition |
| `audioextender/core/` | Shared configuration, data models, interfaces, presets, errors, and operation receipts |
| `audioextender/audio/` | Audio loading, quality, stems, and WAV metadata |
| `audioextender/analysis/` | Musical analysis, candidate selection/scoring, validation, and splice policy |
| `audioextender/processing/` | Track and batch workflows, edits, and web-job orchestration |
| `audioextender/imports/` | Local and external-source imports, playlist matching, and import routes |
| `audioextender/library/` | Track identity, overrides, backup, relocation, metadata mutation, and exports |
| `audioextender/repositories/` | SQLite persistence grouped by jobs, catalog, analysis, feedback, and system state |
| `audioextender/infrastructure/` | Shared cache, progress, background-task, and batch-operation support |
| `audioextender/reporting/` | Processing summaries and listening feedback |
| `audioextender/set_builder/` | Intention/journey planning, candidate selection, validation, evaluation, preferences, plan jobs, and production release assessment |
| `audioextender/web/` | FastAPI composition and focused API route modules |
| `web/` | Browser shell, feature modules, shared controls, and styles |
| `scripts/` | Manual evaluation/benchmark tools and a focused stability-test launcher |
| `docs/` | Maintainer architecture and repository navigation documentation |
| `graphify-out/memory/` | Checked-in Graphify-generated investigation notes; not runtime code or canonical architecture docs |

The intended dependency direction is described in [architecture.md](architecture.md):
HTTP/CLI delivery calls application services; business workflows use analysis,
audio, and core policy; persistence stays behind repositories. Router modules
should receive dependencies from `application.py`, not import application
globals. Keep musical decision logic out of route handlers and browser modules.

## Test Organization

Tests live in one directory and are grouped by descriptive filename, not by
subdirectory. Python tests use `unittest` and the `test_*.py` naming pattern;
JavaScript tests use Node's test runner and `*.test.js`. `factories.py` contains
shared test data builders, and `fixtures/` contains checked-in scenario data.

| Test group | Files |
| --- | --- |
| Application wiring, architecture, package boundaries, and API | `test_application_services.py`, `test_architecture_services.py`, `test_package_structure.py`, `test_web_app.py` |
| Audio, musical analysis, and edit quality | `test_audio_quality.py`, `test_dj_readiness.py`, `test_key_analysis.py`, `test_scoring_and_splices.py`, `test_stem_provider.py`, `test_style_detector.py`, `test_track_descriptors.py`, `test_transition_scorer.py`, `test_wav_metadata.py` |
| Processing, resources, and persistence/reporting | `test_background_tasks.py`, `test_batch_operations.py`, `test_behavior_workflows.py`, `test_cli_helpers.py`, `test_config_and_overrides.py`, `test_export_service.py`, `test_integration_synthetic.py`, `test_progress_and_resources.py`, `test_reports_and_cache.py` |
| Imports and library identity/lifecycle | `test_import_service.py`, `test_library_backup.py`, `test_library_relocation.py`, `test_playlist_match_service.py`, `test_recording_identity.py`, `test_stability_workflow.py` |
| Set Builder planning, evaluation, release, and personalization | `test_feedback_and_reranking.py`, `test_intention_planner.py`, `test_journey_planner.py`, `test_local_intention_acceptance.py`, `test_plan_comparator.py`, `test_proposal_repairer.py`, `test_set_candidate_planning.py`, `test_set_plan_evaluator.py`, `test_set_preference_learning.py`, `test_set_release_gate.py`, `test_set_review_service.py`, `test_track_planner.py`, `test_transition_optimizer.py` |
| Browser contracts and feature modules | `test_frontend_contracts.py`, `frontend_modules.test.js`, `import_queue.test.js`, `playback_behavior.test.js`, `request_state_controller.test.js`, `set_planning_client.test.js` |

The Set Builder scenario file is `fixtures/set_builder_eval_scenarios.json`; it
is used by both planning tests and `scripts/evaluate_set_builder.py`. The local
model acceptance test is opt-in and requires the relevant provider/model; the
ordinary suite uses deterministic behavior and mocks.
`test_set_release_gate.py` covers the production acceptance policy, including
the manual-listening requirement, provider failures, genre scarcity, and
planning-job summaries.

Run the regular suites from the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -q
npm run check
```

Run the focused stability workflow with:

```bash
./scripts/run_stability_gate.sh
```

Coverage reporting is configured through `npm run coverage`; it writes LCOV
reports under `coverage/` for the Python application/scripts and browser code.

### Test growth guidance

- Keep tests near the current flat `tests/` layout while discovery and ownership
  remain easy to scan. Use descriptive names and add new behavior to its owning
  test module where that stays focused.
- If the suite grows enough to need nested folders, move by language/domain in
  one deliberate change and preserve the root test commands and discovery
  patterns; avoid partial nesting that silently stops `unittest` discovery.
- Keep test data builders in `factories.py` only when they are genuinely shared;
  keep domain-specific fixtures under `fixtures/` and avoid checking in real
  audio files or personal library data.
- Keep slow, external-provider, or catalog-scale checks explicitly opt-in or in
  dedicated scripts so the fast deterministic suite stays useful.

## Project Configuration And Operations

| File | Purpose |
| --- | --- |
| `README.md` | Setup, user workflows, tests, and maintainer quick guide |
| `BACKLOG.md` | Planned and audited product work |
| `pyproject.toml`, `.flake8` | Python coverage, lint, and type-check configuration |
| `requirements.txt` | Runtime Python dependencies |
| `requirements-dev.txt` | Development/test tools, including coverage.py |
| `requirements-demucs.txt` | Optional Demucs dependency set |
| `package.json`, `package-lock.json` | JavaScript dependencies and test/check/coverage scripts |
| `.vscode/settings.json`, `.vscode/extensions.json` | Workspace test/editor settings and extension recommendations |
| `settings.py` | Application configuration/defaults |
| `Start AudioExtender.command` | macOS launcher |
| `LICENSE`, `.gitattributes`, `.gitignore` | Licensing and Git behavior |

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
