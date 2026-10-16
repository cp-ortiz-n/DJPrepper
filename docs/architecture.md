# AudioExtender architecture

This is the maintainer map for DJ Library Studio and the AudioExtender CLI. Use
it to decide where a manual change belongs before editing.

Compatibility-sensitive rationale is recorded in the
[`decisions/` index](decisions/README.md). Read the relevant decision before
changing saved-set durability, musical authority, operation lifecycles, schema
migration, or the application's deployment/frontend shape.

## Runtime entry points

| Entry point                        | Purpose                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------- |
| `main.py`                          | CLI parsing and batch execution                                                       |
| `web_app.py`                       | Small compatibility launcher; never add feature logic here                            |
| `audioextender/web/application.py` | FastAPI factory, dependency wiring, compatibility facade, and remaining legacy routes |
| `audioextender/web/audio_quality_routes.py` | Downloaded-library audio-quality scan lifecycle and HTTP routes |
| `audioextender/imports/creative_commons_worker.py` | Creative Commons download and failed-source retry execution |
| `audioextender/library/analysis_queue.py` | Catalog-track analysis and reanalysis job creation |
| `audioextender/library/artwork_thumbnails.py` | Serialized artwork-thumbnail generation and cache ownership |
| `audioextender/library/catalog_projection_builder.py` | Library search and Set Builder projection construction |
| `audioextender/web/composition.py` | Explicit application paths, owned services, registries, locks, queues, and caches     |
| `web/index.html`                   | Browser shell and workspace markup                                                    |
| `web/app.js`                       | Browser composition, global navigation, and feature registration only                 |

Run the app with `python3 web_app.py`.

`create_app()` accepts an explicit `ApplicationRuntime` or `ApplicationPaths`.
The default `app` is a lazy compatibility proxy; importing the module performs
no repository recovery or runtime construction. Uvicorn invokes the factory,
and startup performs interrupted-job recovery against the selected runtime.

The current HTTP surface, delivery shell, startup side effects, runtime roots,
response shapes, and restart expectations are frozen in
[`web-composition-contracts.md`](web-composition-contracts.md). Update those
contracts deliberately whenever an approved public API change is made.

Current musical classifications and scoring boundaries are documented in
[`musical-policy-ownership.md`](musical-policy-ownership.md). The versioned
`library/musical_profile.py` profile is the single owner of normalized key and
Camelot, energy, roles, vocals, timing, confidence, and provenance. Catalog
routes serialize it; DJ Library and Set Builder consume it. Their older local
derivations remain compatibility-only fallbacks, while interactive Library
matching and Set transition scoring intentionally remain separate policies.
Background job state, persistence, cancellation, retry, errors, timestamps, and
receipts are inventoried in
[`background-operation-lifecycles.md`](background-operation-lifecycles.md).
`infrastructure/operation_lifecycle.py` provides their immutable common status,
capability, error, and action-receipt vocabulary. Family adapters normalize
legacy state for internal consumers while each service retains its executor,
persistence, recovery, rollback, and public response contract.
The single-track processing stage order, progress, cache, artifact, timing, and
failure contracts are frozen in
[`processing-pipeline-contracts.md`](processing-pipeline-contracts.md). ARCH-002B
expresses analysis, selection, render, export, and result assembly through
immutable stage results in `processing/track_processing_stages.py`.
`TrackProcessor.process()` remains the stable facade responsible only for input
validation and stage ordering. Analysis preparation, candidate orchestration,
render/export, result construction, and failure cleanup have independent owners
under `processing/`.

ARCH-006A moves the remaining substantial route workflows behind application
services. `DescriptorService` owns durable descriptor inference and vocabulary
decisions, `DownloadedCatalogQueryService` builds the catalog read model, and
`JobWorkflowService` owns upload/job creation and reprocessing policy. Existing
settings and library-maintenance services now own cleanup and integrity-scan
lifecycle operations; FastAPI handlers only translate requests and errors.

## Package ownership

| Package          | Responsibility                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `core`           | Configuration models, immutable results, interfaces, presets, exceptions                  |
| `audio`          | Loading, quality inspection, WAV tags/artwork, stems                                      |
| `analysis`       | Key detection, musical sections, selection, scoring, validation, splice policy, readiness |
| `processing`     | Track, batch, extended-edit, and web-job orchestration                                    |
| `library`        | Recording identity, backup, relocation, cues, exports, overrides                          |
| `imports`        | YouTube, SoundCloud, local-file, playlist, and Creative Commons workflows                 |
| `repositories`   | SQLite persistence grouped by business capability                                         |
| `infrastructure` | Caching, progress adapters, persistent background-task state                              |
| `reporting`      | Processing and listening-feedback reports                                                 |
| `set_builder`    | Natural-language intention planning and local/cloud provider fallback                     |
| `web`            | FastAPI request/response models, routers, and dependency adapters                         |

The normal dependency direction is:

```text
web / CLI
    ↓
processing · imports · library
    ↓
analysis · audio · core

web/services → repositories → SQLite
Set Builder UI → set-builder routes → intention planner → optional model provider
```

Lower layers must not import `audioextender.web.application`. Routers receive
collaborators through dependency dataclasses instead of importing application
globals.

## Repository and schema ownership

`repositories/facade.py::JobRepository` is the compatibility composition root
for existing callers; application services should depend on the smallest
protocol in `repositories/capabilities.py` that covers their work. The web audio
scheduler, for example, receives only job lookup, listing, update, and catalog
path lookup instead of settings, feedback, and the full catalog API.

`repositories/schema.py` owns the ordered idempotent schema bootstrap. Its seven
named steps run jobs before feedback foreign keys, catalog core before recording
identity migration and relations, then search and system state. Keep migrations
inside the owning step, preserve old columns and rows, and test both legacy
database and backup opening whenever this sequence changes.

## FastAPI ownership

| Module                              | Routes and behavior                                                                 |
| ----------------------------------- | ----------------------------------------------------------------------------------- |
| `web/job_routes.py`                 | Job listing, ordering, clearing, cancel, pause, resume, removal                     |
| `web/job_media_routes.py`           | Audio delivery, ZIP exports, waveforms, transition scoring, cue editing             |
| `web/library_routes.py`             | Paginated DJ Library catalog and facets                                             |
| `web/library_maintenance_routes.py` | Catalog reconciliation, integrity scans, progress, safe repairs                     |
| `web/metadata_batch_routes.py`      | Cancellable/retryable genre, WAV-tag, artwork, and catalog-propagation batches      |
| `web/reporting_routes.py`           | Track feedback and manual key verification                                          |
| `web/set_builder_routes.py`         | Set Builder catalog, intention provider/interpretation, preflight, playlist exports |
| `web/set_planning_routes.py`        | Candidate retrieval, validation, and asynchronous AI track-planning jobs            |
| `web/set_preference_routes.py`      | Inspect, record, pause, and reset local Set Builder preference signals              |
| `web/set_review_routes.py`          | Persist set, track, and transition reviews and expose calibration reports           |
| `web/settings_routes.py`            | Settings, storage, backup/restore, relocation, cleanup                              |
| `imports/routes.py`                 | Authorized source, local-file, and playlist import delivery                         |

Router factories accept explicit dependencies. Wire new dependencies in
`application.py`; never make a router import `application.py`. Repository
providers are normally lambdas so tests can replace the active repository.

## Set Builder intention planning

Set Builder uses optional language-model boundaries to understand a DJ's
natural-language brief and, in AI Planned mode, choose a running order from a
server-controlled shortlist. The model never inspects audio or the unrestricted
catalog, and every proposed order passes deterministic validation before it can
reach the browser.

```text
Natural-language brief
        ↓
POST /api/set-builder/interpret-intention → IntentionPlanner
   ├── Ollama qwen3.5:4b (default local provider)
   ├── OpenAI (optional configured fallback)
   └── browser offline rules (final fallback)
        ↓
JSON schema validation + catalog-vocabulary sanitization
        ↓
POST /api/set-builder/plan-journey → JourneyPlanner
   ├── model-planned sections when a provider is available
   └── deterministic section planning when unavailable or invalid
        ↓
Editable sections with runtime share, catalog genres, characteristics,
purpose, and start/end energy
        ↓
POST /api/set-builder/candidate-pool → SetCandidateRetriever
   ├── bounded, diverse candidates per journey section
   ├── stable catalog IDs and local file availability
   ├── direct, identity, bridge, and fallback scarcity tiers
   └── optional bounded adjustments from DJPreferenceService
        ↓
POST /api/set-builder/plan-tracks → SetPlanningJobService
   ├── cancellable candidate retrieval and stale-job supersession
   ├── AITrackPlanner with strict structured output and repair attempts
   ├── section-balanced compact model context with ID-only model output
   ├── deterministic catalog-backed fallback
   └── phase timings and persisted outcome telemetry
        ↓
SetPlanValidator
   ├── IDs, exclusions, required/locked tracks, duplicates, and files
   ├── duration, track count, and journey-section coverage
   └── BPM, Camelot-key, and vocal-transition warnings
        ↓
PlanProposalRepairer + PlanQualityComparator
   ├── preserve valid unique AI choices and repair bounded structural gaps
   ├── evaluate AI and deterministic plans with identical metrics
   └── accept AI only when quality improves without reducing genre coverage
        ↓
SetPlanEvaluator
   ├── direct, identity, bridge, and fallback disclosure
   ├── genre, journey, duration, repetition, and warning measurements
   └── reproducible quality receipt returned with the validated plan
        ↓
DeterministicTransitionOptimizer (fallback plans)
   ├── preserves chosen tracks, section allocation, and journey order
   ├── bounded beam search across BPM, Camelot key, vocals, and energy
   └── recognizes half/double-time BPM compatibility
```

The route surface is:

- `GET /api/set-builder/intention-provider` for provider and model status.
- `POST /api/set-builder/interpret-intention` for structured interpretation.
- `POST /api/set-builder/plan-journey` for a validated, editable section plan.
- `POST /api/set-builder/candidate-pool` for a bounded shortlist backed by real catalog IDs.
- `POST /api/set-builder/validate-plan` for deterministic hard errors, musical warnings, and plan metrics.
- `POST /api/set-builder/plan-tracks` to start a bounded asynchronous track-planning job.
- `GET /api/set-builder/plan-tracks/{job_id}` for progress and the validated result.
- `POST /api/set-builder/plan-tracks/{job_id}/cancel` to cancel without changing the current set.
- `POST /api/set-builder/plan-tracks/{job_id}/retry` to retry a failed or canceled request.
- `GET /api/set-builder/ai-observability` for aggregate local outcomes, latency, repairs, and fallbacks.
- `GET /api/set-builder/preferences` to inspect active and pending local signals.
- `POST /api/set-builder/preferences/events` to record accepted or rejected track choices.
- `PUT /api/set-builder/preferences/enabled` to pause or resume personalization.
- `DELETE /api/set-builder/preferences` to reset signals without changing catalog data.
- `GET /api/set-builder/reviews` for context-specific acceptance and calibration reports.
- `POST /api/set-builder/reviews` to persist overall, track, and transition judgments.
- `DELETE /api/set-builder/reviews` to reset review history independently of catalog data.

Preference learning is a deterministic ranking layer, not model training.
`DJPreferenceService` persists action evidence locally, requires three distinct
tracks per signal, separates profiles by set vibe, and caps the final adjustment
at ±8 points. `PersonalizedCandidateRanker` runs only after hard candidate
constraints, so it cannot restore excluded, missing, or otherwise ineligible
tracks. Matching signals and evidence counts are added to candidate reasons.
`SetReviewService` is a separate persistence and reporting boundary. It records
overall, per-track, and per-transition judgments; calculates personalized versus
neutral acceptance; detects contradictions and broad-signal dominance; and
builds a transition preference profile only after three distinct track pairs.
The review route translates explicit track accept/reject judgments into the
existing preference event vocabulary, keeping capture separate from scoring.

`release_gate.py` owns the final Phase 2G acceptance policy. It consumes the
evaluation report rather than planning tracks itself, so release policy remains
separate from retrieval and model orchestration. Valid plans, complete scenario
coverage, and full requested-genre coverage form the automated gate. Manual DJ
listening approval is a distinct required input and cannot be inferred from a
quality score. `SetPlanningJobService.observability()` summarizes persisted job
receipts without returning prompts, catalog rows, filesystem paths, or audio.
`bounded_model_candidates()` preserves required and locked tracks, keeps
multiple candidates per journey-section slot, removes unavailable files, and
caps model context independently of the validator's complete local pool. Model
responses contain only stable track and section IDs. `PlanProposalRepairer`
restores explanations from catalog evidence before validation. Genre coverage
may be satisfied through disclosed scarcity only when the evaluated candidate
pool contains zero available matches for every missing requested term.

Provider selection defaults to `auto`: Ollama first, OpenAI only when
configured, then deterministic offline rules in the browser. Configuration is
controlled by `AUDIOEXTENDER_LLM_PROVIDER`, `OLLAMA_HOST`,
`OLLAMA_SET_BUILDER_MODEL`, `OPENAI_API_KEY`, and
`OPENAI_SET_BUILDER_MODEL`.

Only the text brief and a bounded catalog vocabulary list cross this boundary;
audio and filesystem paths never do. AI Planned mode adds only the bounded
candidate metadata needed for selection. OpenAI requests use `store: false`. Returned genres are
canonicalized against catalog vocabulary, schema labels and placeholders are
removed, and malformed or unavailable provider responses fall through safely.
Journey percentages are normalized to 100%, energy values are bounded to 1–10,
unknown genres are rejected, and omission or reordering of required genre
sequences triggers deterministic fallback. Edited journey sections directly
control positional genre and energy targets in either safe generator. The
candidate and validator services are provider-independent. `track_planner.py`
owns provider adaptation, repair, and fallback; `planning_jobs.py` owns lifecycle
and cancellation; `planning_store.py` atomically persists job/request state and
turns interrupted jobs into explicit retryable failures after restart;
`plan_evaluator.py` owns deterministic quality measurement; and
`proposal_repairer.py` owns bounded structural cleanup without making musical
quality decisions; `plan_comparator.py` owns the AI-versus-baseline acceptance
policy; and
`set-planning-client.js` owns browser polling and abort semantics. The model cannot bypass availability, explicit brief constraints,
exclusions, duration, or journey-coverage checks.

`SavedSetService` owns version-2 editable set aggregates in SQLite-backed system
state. Each record includes the brief, ordered track IDs and recovery evidence,
transition edits, locked/required/excluded rules, planning mode, and the original
planning receipt. These records survive application restart, browser data loss,
and the existing database backup/restore workflow. Version-1 localStorage records
are migrated idempotently on first load without replacing a newer server record;
localStorage is retained only as an offline recovery cache. M3U8 is a separate,
optional interoperability artifact, so an export failure does not invalidate or
obscure a successful editable-set save. Manual edits remain possible but do not
rewrite the historical generation receipt.

`scripts/evaluate_set_builder.py` is the catalog-scale regression boundary. It
runs the checked-in scenarios in `tests/fixtures/set_builder_eval_scenarios.json`
through candidate retrieval, track planning, validation, and evaluation, then
atomically writes a comparable report. `evaluation_harness.py` contains the
provider-independent orchestration so tests can use synthetic catalogs while
operators can use the exported real catalog. The harness never weakens runtime
validation and records failed scenarios instead of hiding them from averages.
Scenario expectations can enforce quality, genre-coverage, and warning-count
floors; the Latin-party regression specifically guards against reintroducing
the avoidable BPM discontinuities found during the first connected-drive run.

## Browser request state

Music Files and DJ Library use `web/request-state-controller.js` for catalog
request ownership. The controller provides debouncing, `AbortController`
cancellation, sequence-based stale-response rejection, pagination resets,
loading state, and namespaced URL/session persistence. Page-specific modules
still own their filter fields and API query serialization; they must not add a
second request sequence, debounce timer, or request controller in `web/app.js`.

Settings exposes a consolidated library-health read model at
`/api/settings/library-health`. It combines connection and configured-root
status, missing/out-of-root tracks, active and failed metadata batches, storage,
and audio-quality coverage. `/api/settings/library-health/verify` performs the
read-only reconnect verification and invalidates stale catalog/storage status.

### Metadata mutation and batch boundary

`library/metadata_mutations.py` owns atomic propagation across WAV paths, tags,
source sidecars, and catalog records. `web/metadata_batch_routes.py` owns the
HTTP workflows for genre rescans, WAV tag synchronization, artwork updates, and
catalog propagation. Every background metadata operation publishes the shared
state model from `infrastructure/batch_operations.py`: progress, cancellation,
retry lineage, counters, result, and structured errors. Library relocation uses
the same state vocabulary while retaining its specialized copy/verify/rollback
coordinator in `library/relocation.py`.

All state-changing settings and metadata responses also expose a `receipt`
created by `core/operation_feedback.py`. The receipt is the UI/API truth source
for the requested work, actual change count, concrete write destinations,
per-item failures, and restart durability. Running batch receipts explicitly
say that progress is transient even though already-completed disk writes may
persist; terminal receipts replace that provisional statement with the outcome.

## Persistence

`JobRepository` in `repositories/facade.py` is a compatibility facade over:

| Module                | Responsibility                                                         |
| --------------------- | ---------------------------------------------------------------------- |
| `jobs.py`             | Processing jobs, queue state, generations, recovery                    |
| `track_catalog.py`    | Compatibility composition for the focused catalog repository mixins    |
| `track_core.py`       | Core downloaded-track CRUD, playlists, duplicates, and fingerprints    |
| `track_descriptors.py` | Musical-identity descriptors, inference state, and vocabulary review  |
| `recording_families.py` | Recording identities, version relationships, suggestions, and merge |
| `track_projections.py` | Catalog paging, filtering, search projections, and facets             |
| `track_metadata_state.py` | Artwork, metadata, paths, import failures, and deletion state       |
| `track_analysis_state.py` | Audio-quality and key-analysis result persistence                    |
| `library_analysis.py` | Analysis records, search index, catalog signatures, key-analysis state |
| `feedback.py`         | Candidate/track feedback and key verification                          |
| `system_state.py`     | Web settings, durable system state, import failures/background state   |
| `base.py`             | Shared connection contract                                             |

Add SQL to the mixin that owns its data, not back to `facade.py`. The database
is `output/reports/audioextender.sqlite3`. State that must survive restarts
belongs in SQLite, not module globals or browser-only storage.

## Processing pipeline

```text
track_processor.py
    → analysis_preparation.py
    → candidate_selection_orchestration.py
        → selection_coordinator.py
        → candidate_selection.py
        → candidate_reranker.py
        → candidate_validator.py
        → splice_policy.py
    → render_export_transaction.py
        → extended_edit.py
        → export_service.py / cue_export.py
    → track_result_builder.py
    → processing_failure_cleanup.py
```

Selection discovers candidates, reranking adds contextual ordering, validation
enforces safety, and the coordinator owns retry/fallback/user-choice flow.
`splice_policy.py` chooses joins; `extended_edit.py` applies them. Do not place
musical scoring in routes, CLI prompts, or rendering code.

## Import pipeline

- `imports/service.py`: authorized URL imports and durable queue work.
- `imports/local.py`: local-audio ingestion.
- `imports/playlist_match.py`: playlist-to-source matching.
- `imports/creative_commons.py`: Creative Commons batch state.
- `imports/routes.py`: HTTP translation.

Imports must use the configured library path and fail clearly if an external
library is offline. Never silently fall back to `~/Music` or a temporary folder.

## Frontend modules

| Module                           | Ownership                                                                                                     |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `api-client.js`                  | Browser transport, normalized response parsing, typed request failures, and compatibility raw responses       |
| `frontend-services.js`           | Validated immutable feature contract for API, DOM, feedback, and musical-identity editor capabilities         |
| `shared-components.js`           | DOM helpers, messages, formatting, pagination                                                                 |
| `playback.js`                    | Single audio-preview owner                                                                                    |
| `music-files.js`                 | Music Files rendering, filters, maintenance actions, metadata inspector, and recording-family inspector       |
| `dj-library.js`                  | DJ Library rendering, filtering, and selection actions                                                        |
| `dj-library-model.js`            | DJ Library query state plus authoritative browser-side key, energy, role, and compatibility projections       |
| `set-builder.js`                 | Set Builder feature composition, event binding, and cross-workflow coordination                               |
| `set-builder-policy.js`          | Pure Set Builder identity, intention, allocation, matching, and energy policy                                 |
| `set-builder-state.js`           | Mutable Set Builder session state plus plan snapshot and restoration                                          |
| `set-builder-api.js`             | Set Builder HTTP routes and asynchronous planning-client boundary                                             |
| `set-builder-commands.js`        | Plan edit commands, bounded history, undo, redo, and movement                                                 |
| `set-builder-classic-planner.js` | Deterministic proposal generation, acceptance, and safe fallback selection                                    |
| `set-builder-view-model.js`      | Escaped proposal, fallback-policy, and AI-observability presentation models                                   |
| `settings.js`                    | Settings forms, library health, relocation, backups, storage, and refresh coordination                        |
| `reporting.js`                   | Analysis & Feedback and key-verification rendering                                                            |
| `request-state-controller.js`    | Shared debounce, cancellation, stale-response rejection, pagination, and URL/session persistence              |
| `import-queue.js`                | Pause/resume/cancel/retry/reorder import state                                                                |
| `import-issues.js`               | Import-failure filtering, selection, retry progress, and dismissal                                            |
| `import-workspace.js`            | Authorized import DOM/queue coordination, shared import normalization, and browser API boundary               |
| `local-audio-import.js`          | Local-file staging, submission, progress, results, and processing-workspace import lifecycle                  |
| `playlist-import.js`             | Playlist matching, permissions, source handoff, and Creative Commons verification                             |
| `processing-workspace.js`        | Processing queue state, polling, categorization, ETA/generation derivation, and candidate-review API boundary |
| `processing-workspace-view.js`   | Processing-card view models, action binding, artifact links, and incremental queue rendering                  |
| `candidate-review.js`            | Candidate decisions and review/reprocessing workflow coordination                                             |
| `candidate-waveform-editor.js`   | Candidate region editing, insertion visualization, previews, and transition preflight scoring                 |
| `processing-job-detail.js`       | Completed-job waveform hydration, arrangement lanes, cues, and boundary overrides                             |
| `track-metadata-ui.js`           | Shared genre hierarchy, metadata forms, normalization, and genre persistence UI                               |
| `searchable-selects.js`          | Accessible searchable-select enhancement and lifecycle                                                        |
| `background-task-controller.js`  | Keyed cancellable polling with stale-task replacement and terminal callbacks                                  |
| `styles.css`                     | Shared visual system and responsive behavior                                                                  |

Do not create a second audio player, dropdown implementation, notification
system, or pagination helper inside a feature. Extend the shared module first.
`app.js` composes these features and owns global navigation; page-specific
rendering, filters, inspectors, and maintenance actions belong in their feature
module. `tests/javascript/frontend_modules.test.js` enforces this boundary and a size ceiling.

The five primary feature factories receive `frontendServices` rather than loose
transport, error, notification, confirmation, DOM, and identity-editor
callbacks. `app.js` creates that contract once. Feature modules must use its
injected `api` capability; an ESLint boundary rejects direct global `fetch`
calls in Music Files, DJ Library, Settings, Reporting, and Set Builder. The
client deliberately offers both normalized JSON requests and a raw-response
escape hatch so streaming/download workflows retain native browser semantics.
Request cancellation and stale-response ownership remain in
`request-state-controller.js`.

## Where to make common changes

| Change                                              | Start here                                                                                        |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| BPM, grid, key, confidence, energy                  | `audioextender/analysis/`                                                                         |
| Intro/outro selection                               | `selection_coordinator.py`, `candidate_selection.py`, `candidate_validator.py`                    |
| Splice sound/crossfades                             | `splice_policy.py`, then `processing/extended_edit.py`                                            |
| WAV tags/artwork/audio quality                      | `audio/wav_metadata.py`, `audio/quality.py`                                                       |
| Track IDs/related versions                          | `library/recording_identity.py`, `repositories/track_catalog.py`                                  |
| Import destination/source behavior                  | `imports/` and its injected library-root dependency                                               |
| Relocation/backup                                   | `library/relocation.py`, `library/backup.py`, `web/settings_routes.py`                            |
| Queue behavior                                      | `processing/web_jobs.py`, `web/job_routes.py`, `repositories/jobs.py`                             |
| DJ Library filtering                                | `web/library_routes.py`, `repositories/library_analysis.py`                                       |
| Musical profile ownership or scoring                | `docs/musical-policy-ownership.md`, then the named authority                                      |
| Integrity scan/repair                               | `web/library_maintenance_routes.py`                                                               |
| Browser cards/filters                               | Corresponding `web/*.js` module plus `web/styles.css`                                             |
| Set Builder language interpretation/provider policy | `set_builder/intention_planner.py`, `web/set_builder_routes.py`                                   |
| Persistent setting                                  | `web/settings_routes.py`, `repositories/system_state.py`; `settings.py` only for shipped defaults |

## Contribution recipes

These are placement rules, not templates to copy mechanically. Start with the
smallest recipe that owns the requested behavior and preserve the public
contract unless the change explicitly approves a migration.

### Add a backend API workflow

1. Put request/response translation in the focused `audioextender/web/*_routes.py`
   module. Create a router module only when no existing route family owns it.
2. Put orchestration or policy in the owning `library`, `processing`, `imports`,
   `reporting`, or `set_builder` service. A route must not become the workflow.
3. Describe collaborators with a dependency dataclass or narrow repository
   protocol from `repositories/capabilities.py`.
4. Wire the dependency and router in `web/composition.py` and
   `web/application.py`; never import application globals from a route.
5. Normalize failures with `web/error_contracts.py` and return an operation
   receipt for state-changing work.
6. Add service tests, route-contract tests, and an endpoint-inventory update when
   the public surface changes.

### Add or change persistence

1. Place SQL in the repository mixin that owns the data; do not add SQL to a
   route, service, or `repositories/facade.py`.
2. Expose only the capability required by new callers.
3. Add an ordered, idempotent step in `repositories/schema.py` when the schema
   changes. Preserve legacy rows and opening behavior.
4. Test a new database, a representative old database, restart behavior, and
   backup/restore when the data belongs in backups.

### Add a browser workflow

1. Put feature state, rendering, and page events in the owning `web/*.js`
   feature module. Keep `app.js` limited to composition and navigation.
2. Consume `frontend-services.js` for API, DOM, feedback, and descriptor-editor
   capabilities. Extend a shared capability instead of adding loose callbacks.
3. Use `request-state-controller.js` for catalog request cancellation and stale
   response rejection, `background-task-controller.js` for keyed polling, and
   `playback.js` for previews.
4. Add pure or injected behavioral coverage in `tests/javascript/*.test.js`. Add a
   Playwright scenario only when browser integration, focus, layout, or actual
   DOM lifecycle is the behavior under test.
5. Keep CSS in the shared visual system until ARCH-013A demonstrates a safer
   ownership split.

### Add musical policy

1. Check `docs/musical-policy-ownership.md` before changing an algorithm.
2. Put processing-time analysis in `analysis`, catalog delivery facts in
   `library/musical_profile.py`, and set-construction policy in `set_builder`.
3. Do not derive a second musical profile in the browser. Compatibility helpers
   remain confined to `dj-library.js`.
4. Update the shared golden fixture and both Python and JavaScript consumers for
   intentional cross-runtime policy changes.

### Add a background operation

1. Keep execution and durable recovery in the owning feature service.
2. Publish the common status, capability, error, and receipt vocabulary from
   `infrastructure/operation_lifecycle.py`.
3. Use `infrastructure/batch_operations.py` for metadata-style cancellable and
   retryable batches; do not force unrelated executors into that registry.
4. Document intentional lifecycle differences and test start, progress,
   cancellation, retry, terminal failure, restart, and truthful feedback.

### Add an intention or track-planning provider

1. Implement the existing provider protocol in `set_builder/intention_planner.py`
   or `set_builder/track_planner.py`; provider code translates structured input
   and output but does not own validation or catalog access.
2. Keep candidate retrieval bounded and catalog-backed. Never send audio,
   unrestricted catalog rows, or filesystem paths to a model.
3. Preserve deterministic schema validation, repair limits, fallback, plan
   comparison, and release gates.
4. Test provider failure, malformed output, invented IDs, timeouts, fallback,
   privacy boundaries, and a successful structured response without requiring a
   live provider in the standard suite.

## Verification matrix

| Change risk                                                         | Required checks                                                   |
| ------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Any maintained source                                               | `./scripts/check_quality.sh` and `git diff --check`               |
| Coverage-sensitive logic                                            | `./scripts/check_coverage.sh`                                     |
| Persistence, imports, relocation, export, or Set Builder durability | `./scripts/run_stability_gate.sh`                                 |
| Browser workflow, focus, responsive layout, or accessibility        | `npm run check:browser`                                           |
| Architecture/module relationships                                   | `graphify . --update --code-only --no-viz` plus the standard gate |
| Live local-model behavior                                           | Opt-in `AUDIOEXTENDER_RUN_LOCAL_LLM_TESTS=1` acceptance suite     |

Install Chromium for the browser gate once with
`npm run check:browser:install`. The Playwright server uses an isolated temporary
catalog and library; see `browser-smoke-testing.md`. Standard quality, coverage,
and stability details live in `development-quality.md`.

## Safe manual-change workflow

1. Find the owning module above.
2. Add/update a focused test under `tests/` before changing cross-layer behavior.
3. Keep HTTP parsing in routers, domain behavior below them, and SQL in repositories.
4. Run the authoritative standard gate:

   ```bash
   ./scripts/check_quality.sh
   git diff --check
   ```

5. After architecture changes, refresh Graphify:

   ```bash
   graphify . --update --code-only --no-viz
   ```

`tests/unit/architecture/test_package_structure.py` guards package/composition boundaries and
module size. `tests/javascript/frontend_modules.test.js` exercises shared frontend behavior;
its only source-text assertion is the intentional `app.js` composition-root
ownership and size ratchet. Request concurrency, playback ownership, planning
lifecycle, imports, and musical-policy behavior live in focused Node suites.
`tests/unit/set_builder/test_intention_planner.py` covers provider ordering, schema enforcement,
fallback, hallucination cleanup, and catalog normalization without a live
model. `tests/integration/set_builder/test_local_intention_acceptance.py` is an opt-in Ollama suite for
chill Latin kickbacks, Latin Techno/House with optional Schranz, Afro House
lounge warmups, and peak-time Techno journeys.

HTTP failure normalization is owned by `audioextender/web/error_contracts.py`.
It preserves legacy FastAPI `detail` values while adding machine-readable error
metadata. Browser parsing is owned by `web/api-client.js`; feature modules do
not need to interpret validation lists or object-valued details independently.
See `docs/error-contracts.md` for mappings and exception-boundary rules.

## Project hygiene

- Never add general-purpose source files under `helpers/`.
- Virtual environments and Python/tool caches are generated artifacts.
- `graphify-out/` is the generated architecture index used for future analysis.
- `input/`, `output/`, and `cache/` are local runtime data, not product source.
- Preserve compatibility exports when moving functions used by scripts/tests;
  remove them only through a deliberate migration.
