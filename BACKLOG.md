# AudioExtender Backlog

# Architecture Modernization & Technical Debt Reduction

This roadmap comes from [`docs/audits/architecture-audit.md`](docs/audits/architecture-audit.md).
It preserves the modular monolith, existing APIs, data, musical behavior, and
completed backlog work. Confirmed refactors and investigation-only items are
distinguished explicitly. Completion marks below reflect verified implementation.

## Phase 0 — Baseline and Architecture Audit

Objective: establish stable compatibility evidence before structural changes.
Dependencies: none. Benefit: every later extraction can prove behavior and data
compatibility rather than relying on visual inspection.

- [x] **ARCH-012A — Restore and freeze a clean quality baseline.** Priority: P0.
  Effort: S. Risk: Low. Dependencies: none. Acceptance: remove the duplicate
  `IntentionPlanner` import in an approved implementation change; Ruff, MyPy,
  Python tests, and `npm run check` all pass from a clean checkout through one
  documented command. Evidence: [ARCH-012](docs/audits/architecture-audit.md#arch-012--quality-enforcement-has-gaps-and-the-checked-out-baseline-is-not-lint-clean).
  Completed 2026-10-11: `./scripts/quality/check_quality.sh` is green; the measured
  baseline and coverage limitations are recorded in `docs/operations/development-quality.md`.
- [x] **ARCH-001A — Capture web composition compatibility contracts.** Priority:
  P0. Effort: M. Risk: Low. Dependencies: ARCH-012A. Acceptance: record the
  FastAPI route inventory, successful/error response shapes, startup side
  effects, path roots, and restart behavior in automated characterization
  tests; no runtime behavior changes. Evidence: [ARCH-001](docs/audits/architecture-audit.md#arch-001--legacy-web-application-remains-an-architectural-bottleneck).
  Completed 2026-10-11: executable contracts now freeze the 152-route HTTP
  inventory, delivery shell, response/error shapes, startup provider reporting,
  runtime roots, dependency wiring, disconnected-library behavior, and existing
  restart persistence. See `docs/architecture/web-composition-contracts.md`.
- [x] **ARCH-003A — Establish musical-policy ownership and golden fixtures.**
  Priority: P0. Effort: M. Risk: Low. Dependencies: ARCH-012A. Acceptance:
  document authoritative owners for normalized key/Camelot, energy, roles,
  vocals, timing, Library match score, and Set transition cost; golden fixtures
  cover current Python and browser outputs without changing weights. Evidence:
  [ARCH-003](docs/audits/architecture-audit.md#arch-003--shared-musical-classification-is-duplicated-across-backend-and-browser).
  Completed 2026-10-11: authoritative and compatibility owners are recorded in
  `docs/architecture/musical-policy-ownership.md`; one versioned JSON fixture now drives
  Python catalog/Set-transition tests and browser profile/Library-score tests.
- [x] **ARCH-004A — Document the background-operation lifecycle matrix.**
  Priority: P1. Effort: S. Risk: Low. Dependencies: ARCH-012A. Acceptance: every
  job type lists states, persistence, cancellation checkpoints, retry rules,
  restart disposition, timestamps, errors, and receipt behavior; intentional
  differences are justified. Evidence: [ARCH-004](docs/audits/architecture-audit.md#arch-004--background-operations-have-fragmented-lifecycle-contracts).
  Completed 2026-10-11: ten user-visible operation families, their lifecycle
  gaps, and their persistence/cancellation/retry contracts are recorded in
  `docs/operations/background-operation-lifecycles.md` and its validated JSON companion.

Phase acceptance: the baseline is green, compatibility contracts are executable,
and the musical/job ownership decisions are documented.

## Phase 1 — Code Quality and Technical Debt

Objective: remove low-risk noise and expose stable contracts before extraction.
Dependencies: Phase 0. Benefit: clearer failures and less brittle test feedback.

- [x] **ARCH-011A — Replace duplicate/brittle frontend tests with behavior
  coverage.** Priority: P1. Effort: M. Risk: Low. Dependencies: ARCH-012A.
  Acceptance: repeated Set Builder tests occur once; key user workflows execute
  controller/DOM behavior; only true architecture boundaries use source-text
  assertions; all existing scenarios remain covered. Evidence: [ARCH-011](docs/audits/architecture-audit.md#arch-011--frontend-tests-contain-brittle-source-assertions-and-duplicated-cases).
  Completed 2026-10-11: repeated Set Builder scenarios now occur once;
  descriptor rendering, provider status, and editable journey validation execute
  production behavior; source inspection is limited to the composition-root
  size/ownership ratchet and shared CSS accessibility/responsive contracts.
  Request cancellation, stale responses, playback ownership, and planning
  lifecycle behavior remain covered by their focused suites.
- [x] **ARCH-010A — Inventory and normalize error contracts.** Priority: P1.
  Effort: M. Risk: Medium. Dependencies: ARCH-001A. Acceptance: expected domain,
  unavailable-resource, cancellation, and unexpected errors have documented
  mappings; broad catches remain only at justified boundaries with structured
  logs; the browser uses one backward-compatible parser. Evidence: [ARCH-010](docs/audits/architecture-audit.md#arch-010--error-handling-and-api-failure-contracts-are-inconsistent).
  Completed 2026-10-12: FastAPI failures preserve `detail` and add stable
  code/category/message/retryability metadata. Validation, expected domain, and
  unexpected failures share one delivery mapping; browser request clients use
  the backward-compatible parser. See `docs/architecture/error-contracts.md`.
- [x] **ARCH-002A — Characterize the processing pipeline stages.** Priority: P1.
  Effort: M. Risk: Low. Dependencies: ARCH-012A. Acceptance: tests freeze stage
  order, progress, cache behavior, artifacts, result timing, and injected
  failures for representative configurations without restructuring the method.
  Evidence: [ARCH-002](docs/audits/architecture-audit.md#arch-002--track-processing-is-concentrated-in-one-long-transaction-script).
  Completed 2026-10-12: behavioral tests freeze full stage order and progress,
  analysis cache miss/hit/refresh behavior, stem and non-stem configurations,
  artifact/result timing, and loading-through-export failure propagation. See
  `docs/architecture/processing-pipeline-contracts.md`.

Phase acceptance: no duplicated test cases, failure contracts are explicit, and
the long processing workflow has stage-level characterization.

## Phase 2 — Backend Architecture and Shared Services

Objective: finish backend separation while preserving public behavior.
Dependencies: Phases 0–1. Benefit: independently testable workflows and smaller
change surfaces for new backend features.

- [x] **ARCH-001B — Introduce explicit application composition.** Priority: P0.
  Effort: L. Risk: High. Dependencies: ARCH-001A, ARCH-010A. Acceptance:
  `create_app()` receives/creates an explicit runtime container under temporary
  roots; importing the module no longer performs uncontrolled production-path
  recovery or constructs unrelated mutable registries; `web_app.py` and public
  endpoints remain compatible. Evidence: [ARCH-001](docs/audits/architecture-audit.md#arch-001--legacy-web-application-remains-an-architectural-bottleneck).
  Completed 2026-10-12: `ApplicationPaths` and `ApplicationRuntime` now own
  filesystem roots, repositories, services, registries, locks, and caches;
  `create_app()` accepts either explicit paths or a runtime; import leaves the
  default app unresolved; repository recovery runs only at FastAPI startup; the
  152-route public inventory and `web_app.py` compatibility entry point remain
  unchanged. See `docs/architecture/web-composition-contracts.md`.
- [x] **ARCH-006A — Extract remaining route workflows into focused services.**
  Priority: P1. Effort: L. Risk: Medium. Dependencies: ARCH-001B. Acceptance:
  settings cleanup, descriptor inference, integrity work, downloaded catalog,
  reprocessing, and job creation handlers translate HTTP to service calls;
  filesystem/business workflows have isolated tests; endpoint URLs and payloads
  remain unchanged. Evidence: [ARCH-006](docs/audits/architecture-audit.md#arch-006--route-modules-still-contain-substantial-application-workflows).
  Completed 2026-10-12: descriptor inference, downloaded-catalog queries, job
  creation/reprocessing, settings cleanup, and integrity scan lifecycle now run
  through focused services. Route handlers retain HTTP validation and error
  translation, while the application factory injects runtime dependencies.
- [x] **ARCH-003B — Add an authoritative versioned musical profile.** Priority:
  P0. Effort: L. Risk: High. Dependencies: ARCH-003A. Acceptance: Python owns
  normalized key/Camelot, energy, roles, vocals, timing, confidence, provenance,
  and version; existing outputs are unchanged; browser and Set Builder consume
  the serialized profile; intentionally distinct scorers remain named and
  tested separately. Evidence: [ARCH-003](docs/audits/architecture-audit.md#arch-003--shared-musical-classification-is-duplicated-across-backend-and-browser).
  Completed 2026-10-12: `library/musical_profile.py` now owns the versioned
  profile and catalog serialization. DJ Library and Set Builder prefer it over
  compatibility fields; cross-runtime golden tests preserve prior musical
  behavior and keep Library match and Set transition scorers distinct.
- [x] **ARCH-002B — Decompose `TrackProcessor.process` into cohesive stages.**
  Priority: P1. Effort: L. Risk: High. Dependencies: ARCH-002A. Acceptance:
  analysis, selection, render construction, export, and result assembly have
  typed stage results; `process` remains the public transaction boundary;
  musical/audio outputs and progress behavior match the baseline. Evidence:
  [ARCH-002](docs/audits/architecture-audit.md#arch-002--track-processing-is-concentrated-in-one-long-transaction-script).
  Completed 2026-10-12: the transaction now delegates to explicit analysis,
  selection, render, export, and result-assembly stages with immutable typed
  results. `process()` retains input validation, failure cleanup, and ordering;
  characterization, stage, integration, and stability tests preserve behavior.
- [x] **ARCH-004B — Standardize background lifecycle contracts without forcing
  one executor.** Priority: P1. Effort: L. Risk: High. Dependencies: ARCH-004A,
  ARCH-010A. Acceptance: common status/receipt/cancellation/retry DTOs and
  conformance tests cover audio jobs, imports, metadata batches, planning, and
  relocation; feature-specific persistence and rollback remain; adapters keep
  endpoint payloads compatible. Evidence: [ARCH-004](docs/audits/architecture-audit.md#arch-004--background-operations-have-fragmented-lifecycle-contracts).
  Completed 2026-10-12: immutable lifecycle projections, capability declarations,
  normalized errors, and action receipts now cover every audited family. Audio
  jobs, imports, metadata batches, planning, and relocation expose the shared
  internal view while retaining their own executors, persistence, recovery,
  rollback behavior, stored state, and public HTTP payloads.
- [x] **ARCH-005A — Narrow repository capabilities and modularize schema
  initialization.** Priority: P2. Effort: L. Risk: High. Dependencies:
  ARCH-001B. Acceptance: new/extracted services receive only required repository
  capabilities; `JobRepository` remains a compatibility facade; initialization
  is an ordered idempotent sequence; existing databases and backups open with
  no data/schema behavior change. Evidence: [ARCH-005](docs/audits/architecture-audit.md#arch-005--repository-compatibility-facade-and-catalog-mixin-are-too-broad).
  Completed 2026-10-12: `JobRepository` remains the compatibility facade while
  `WebJobService` depends on a narrow job-queue protocol. Schema initialization
  is now a named seven-step idempotent sequence covering jobs, feedback, catalog,
  recording identities, relations, search, and system state. Fresh, legacy,
  restarted, backed-up, and restored databases retain their data and behavior.

Phase acceptance: backend composition is explicit, shared musical facts have one
owner, and extracted services remain compatible with existing data and APIs.

## Phase 3 — Frontend Architecture

Objective: make frequent UI changes local and behavior-testable without adopting
a framework. Dependencies: authoritative backend contracts from Phase 2.
Benefit: fewer regressions from shared closure state and broad callback wiring.

- [x] **ARCH-007A — Add a shared frontend API/error adapter and narrow feature
  contracts.** Priority: P1. Effort: M. Risk: Medium. Dependencies: ARCH-010A.
  Acceptance: Music Files, DJ Library, Settings, Reporting, and Set Builder use a
  shared request/error contract; feature factories receive cohesive collaborators
  rather than long callback lists; stale-response behavior remains intact.
  Evidence: [ARCH-007](docs/audits/architecture-audit.md#arch-007--frontend-composition-still-carries-feature-implementation-and-broad-callback-wiring).
  Completed 2026-10-13: `api-client.js` owns injected transport, normalized JSON
  requests, typed failures, and compatibility-level raw responses.
  `frontend-services.js` validates and groups API, DOM, feedback, and musical-
  identity editor capabilities before composition. Music Files, DJ Library,
  Settings, Reporting, and Set Builder now consume that immutable contract;
  lint prevents those modules from returning to global `fetch`. Existing
  debounce, abort, loading ownership, URL/session persistence, and stale-response
  rejection tests remain green.
- [x] **ARCH-008A — Decompose Set Builder state, API, commands, and views.**
  Priority: P0. Effort: L. Risk: High. Dependencies: ARCH-003B, ARCH-007A,
  ARCH-011A. Acceptance: one feature entry composes a testable state store,
  planning API, edit commands, classic fallback, and render/view helpers; AI,
  deterministic, save/load, undo/redo, alternatives, preview, and review
  workflows match characterization tests. Evidence: [ARCH-008](docs/audits/architecture-audit.md#arch-008--set-builder-browser-module-owns-too-many-change-axes).
  Completed 2026-10-13: `set-builder.js` is now a composition-oriented feature
  entry over dedicated state, API, command, classic-planning, and view-model
  modules. The API boundary owns all Set Builder routes and planning lifecycle;
  the command boundary owns bounded history, moves, undo, and redo; and the
  deterministic proposal loop is independently testable. Behavioral tests cover
  snapshots, restoration, command history, route serialization, classic fallback,
  and escaped render evidence. The entry-module size ceiling is ratcheted from
  675 to 663 lines.
- [x] **ARCH-008C — Finish decomposing the Set Builder frontend.**
  Priority: P0. Effort: L. Risk: High. Dependencies: ARCH-008A. Acceptance:
  transition previews/editing, generated-plan rendering/track edits, and saved-
  set loading/persistence/exports have focused owners while
  `createSetBuilderFeature()` remains the coordinator; existing payloads and
  planning algorithms are unchanged; AI, deterministic, edit history,
  transition, save/load, and export gates pass.
  Completed 2026-10-19: the transition editor, plan view, and durable saved-set
  controller are separate injected modules. Export serialization is pure and
  directly tested, controller behavior covers transition health/runtime, rules,
  durable/cache recovery, and persistence, and architecture ceilings ratchet the
  coordinator from 3,456 lines to at most 1,700 lines.
- [x] **ARCH-008D — Extract Set Builder planning-session orchestration.**
  Priority: P0. Effort: M. Risk: High. Dependencies: ARCH-008C. Acceptance:
  asynchronous AI planning, deterministic proposal generation, proposal
  switching, cancellation, receipts, and observability have one lifecycle
  owner; preference learning and set-review submission have a separate focused
  owner; `createSetBuilderFeature()` remains the composition coordinator.
  Completed 2026-10-19: `set-builder-planning-session.js` now owns planning-job
  lifecycle, safe deterministic fallback, proposal preservation/optimization,
  and planning receipts. `set-builder-feedback.js` owns learned-preference,
  calibration, and set-review workflows. Behavioral tests cover deterministic
  acceptance, AI cancellation and safety fallback, proposal switching, ranking
  signal loading, and receipt-backed review submission. The coordinator ceiling
  is ratcheted from 1,700 to 1,150 lines.
- [x] **UX-SET-001 — Clarify Set Builder progress, journey editing, and review state.**
  Priority: P1. Effort: S. Risk: Medium. Dependencies: ARCH-008D. Acceptance:
  brief interpretation and track planning expose accessible stage and elapsed-
  time feedback; malformed journey energy endpoints render a playable value;
  each journey section reads as one responsive card; selected Keep/Reject
  controls remain legible. Completed 2026-10-20: a focused progress presenter
  owns both long-running views, AI job percentages feed the same presentation,
  journey energy normalization is pure and tested, and browser coverage guards
  progress, responsive card geometry, invalid endpoints, and selected-review
  contrast.
- [x] **ARCH-007C — Decompose DJ Library browser orchestration.**
  Priority: P1. Effort: M. Risk: Medium. Dependencies: ARCH-007B. Acceptance:
  query/filter binding, bulk selection and mutations, and Library intelligence
  rendering have focused owners; `dj-library.js` remains the catalog-loading
  coordinator and compatibility export surface; payloads and musical policy do
  not change; behavioral and browser gates pass. Completed 2026-10-19:
  `dj-library-view.js`, `dj-library-filters.js`, `dj-library-selection.js`, and
  `dj-library-intelligence.js` own those workflows. Focused tests cover empty
  presentation, filter resets and pagination, selection synchronization, and
  compatibility rendering. The coordinator ceiling is ratcheted from 1,225 to
  250 lines.
- [x] **ARCH-007B — Reduce `app.js` to durable composition and navigation.**
  Priority: P1. Effort: L. Risk: Medium. Dependencies: ARCH-007A, ARCH-008A.
  Acceptance: processing/import feature behavior has an explicit owner; `app.js`
  contains bootstrap, navigation, and feature composition; its size ceiling is
  ratcheted downward rather than raised; DOM workflows pass. Evidence:
  [ARCH-007](docs/audits/architecture-audit.md#arch-007--frontend-composition-still-carries-feature-implementation-and-broad-callback-wiring).
  Completed 2026-10-14: import-failure loading, filtering, retry, polling,
  selection, and dismissal now belong to `import-issues.js`. Generic cancellable
  polling belongs to `background-task-controller.js` with replacement and abort
  tests. `import-workspace.js` now also owns source normalization, local-file
  deduplication, stable playlist identities, source matching, and import lifecycle
  route serialization. It now owns authorized-source inspection, queue controls,
  status polling, submission, and completion feedback as one injected feature.
  Local-audio staging, both local-import entry points, progress, and results now
  belong to `local-audio-import.js`; playlist matching, permission management,
  authorized-source handoff, and Creative Commons verification belong to
  `playlist-import.js`. Processing queue polling, refresh deduplication,
  filtering, generation/ETA derivation, route serialization, and candidate-review
  requests now belong to `processing-workspace.js`, with focused behavioral
  tests. Processing-card presentation, action binding, completed-artifact links,
  and incremental DOM reuse now belong to `processing-workspace-view.js`, backed
  by pure view-model tests. `candidate-review.js` owns review loading, candidate
  decisions, custom regions, insertion previews, transition scoring, waveforms,
  and reprocessing. The processing API owns every associated route. Behavioral
  and structural tests protect the boundary, and the `app.js` ceiling is
  ratcheted from 1,878 to 918 lines.
- [x] **ARCH-016A — Organize wide namespaces by owner.** Priority: P1.
  Effort: L. Risk: High. Dependencies: ARCH-005A, ARCH-007B, ARCH-007C,
  ARCH-008D. Acceptance: browser modules are grouped under core/shared/feature
  boundaries; FastAPI delivery is grouped into routes/contracts/assets; SQLite
  implementations are grouped by persisted aggregate while `JobRepository`
  remains the compatibility facade; styles and JavaScript tests mirror feature
  ownership; recursive tooling discovers new modules automatically; public
  routes, payloads, persistence, and behavior remain unchanged. Completed
  2026-10-19: the repository now follows the documented domain-first layout,
  architecture safeguards reject new flat dumping-ground modules, and the
  quality, coverage, stability, browser, and Graphify gates validate the move.
  See [`docs/architecture/code-organization.md`](docs/architecture/code-organization.md).
- [x] **ARCH-016B — Organize project roots and runtime data by owner.** Priority: P1.
  Effort: L. Risk: High. Dependencies: ARCH-016A. Acceptance: browser source,
  SQLite persistence, scripts, documentation, defaults, entry points, tests,
  and local runtime data each have one explicit home; compatibility launchers
  remain available; all configured paths and documentation resolve; tooling and
  architecture safeguards discover the new layout recursively. Completed
  2026-10-20: browser source moved to `frontend/`, persistence to
  `audioextender/persistence/`, defaults to `audioextender/core/defaults.py`,
  generated local data to `workspace/`, and scripts/docs into purpose-specific
  subdirectories. Package-native CLI and web launchers now own startup while
  root launchers preserve compatibility. The full quality, coverage, stability,
  browser, and Graphify gates validate the move. See
  [`docs/architecture/code-organization.md`](docs/architecture/code-organization.md).
- [x] **ARCH-009A — Decide and implement saved-set durability.** Priority: P2.
  Effort: L. Risk: High. Dependencies: ARCH-001B, ARCH-008A, product decision.
  Acceptance: editable set ownership and backup scope are explicit; version-1
  localStorage records migrate without loss; restart/browser-clear behavior,
  planning receipts, and M3U8 export are tested. Evidence: [ARCH-009](docs/audits/architecture-audit.md#arch-009--saved-set-ownership-is-split-between-browser-and-durable-backend-artifacts).
  Completed 2026-10-15: editable set aggregates are versioned backend records
  stored in SQLite system state and therefore participate in restart and existing
  database backup/restore behavior. The aggregate includes the brief, ordered
  track IDs and recovery details, transitions, locks/rules, planning mode, and
  planning receipt. Browser version-1 records migrate idempotently without
  replacing newer server records; localStorage remains a recovery cache only.
  M3U8 remains an optional export artifact, and its failure no longer makes the
  durable editable-save result ambiguous.
- [x] **ARCH-013A — Investigate CSS ownership and responsive/accessibility
  regressions.** Priority: P3. Effort: S. Risk: Low. Dependencies: ARCH-011A.
  Acceptance: selector ownership, unused/overlapping rules, supported viewports,
  keyboard focus, and reduced motion are measured; create a split task only if
  the evidence shows cascade or ownership problems. Evidence: [ARCH-013](docs/audits/architecture-audit.md#arch-013--stylesheet-ownership-may-become-a-frontend-bottleneck).
  Completed 2026-10-15: the audit measured 656 class selectors, 68 media-query
  blocks across 15 conditions, 17 static-reference cleanup candidates, and
  substantial interleaved feature ownership. Playwright now verifies 1440 px,
  720 px, and 390 px layouts without page overflow, visible keyboard focus,
  computed reduced-motion behavior, and serious/critical WCAG findings. The
  evidence confirms a behavior-preserving ownership split is warranted.
- [x] **ARCH-013B — Split CSS by explicit feature ownership.** Priority: P2.
  Effort: M. Risk: Medium. Dependencies: ARCH-013A. Acceptance: tokens/base,
  shared components, shell, imports/processing, Music Files, DJ Library, Set
  Builder, and Settings/reporting styles have explicit owners behind one ordered
  entry point; confirmed dead rules are removed, equivalent owner-local media
  conditions are consolidated, and computed behavior remains compatible at all
  supported viewports. Evidence: `docs/audits/css-ownership-audit.md`.
  Completed 2026-10-15: `frontend/styles.css` is now a stable ordered entry point for
  numbered owner fragments covering shell/base, shared components, processing,
  Library/reporting, Settings, Music Files, and Set Builder. The original
  cascade order remains explicit, all 17 confirmed unused selector candidates
  were removed, a structural test protects imports and cleanup, and the real
  browser gate protects responsive, focus, motion, and accessibility behavior.
- [x] **UX-MUSIC-001 — Simplify the Music Files workspace.** Priority: P2.
  Effort: M. Risk: Medium. Dependencies: ARCH-013B. Acceptance: search and sort
  remain immediately available; secondary filters use one disclosure with
  removable active-filter chips; catalog-wide maintenance is separate from
  selection actions; bulk controls appear only with a selection; responsive and
  behavioral coverage protects the workflow. Completed 2026-10-20: pure browse
  state and presentation helpers were extracted, the toolbar was reorganized by
  action scope, selection-specific artwork synchronization was made explicit,
  and JavaScript/browser tests cover filter dependencies, reset behavior,
  selection capabilities, disclosures, chips, and contextual actions.

Phase acceptance: feature behavior is independently testable, `app.js` is a
composition root, and no storage or UI workflow compatibility is lost.

## Phase 4 — Testing and Architecture Enforcement

Objective: prevent the confirmed problems from returning. Dependencies: stable
boundaries from Phases 2–3. Benefit: contributors receive fast, actionable gates.

- [x] **ARCH-012B — Add automated architecture boundary checks.** Priority: P1.
  Effort: M. Risk: Low. Dependencies: ARCH-001B, ARCH-003B. Acceptance: tests
  detect Python cycles, domain imports from `web`, SQL outside persistence,
  growth of designated composition/orchestration hotspots, and reintroduction of
  browser musical derivation; limits are ratchets tied to current responsibilities.
  Evidence: [ARCH-012](docs/audits/architecture-audit.md#arch-012--quality-enforcement-has-gaps-and-the-checked-out-baseline-is-not-lint-clean).
  Completed 2026-10-14: cycle, dependency-direction, SQL-boundary, current
  hotspot-growth, and `TrackProcessor.process` complexity ratchets run in the
  standard gate. Import resolution now covers package-level `from` imports,
  obsolete SQL exceptions fail closed, and browser profile derivation is guarded
  to the documented `dj-library.js` compatibility owner so feature modules must
  consume its helpers instead of recreating musical rules.
- [x] **ARCH-014A — Investigate manual-correction propagation and cache
  invalidation.** Priority: P1. Effort: M. Risk: Medium. Dependencies: ARCH-003B.
  Acceptance: a matrix/test covers manual BPM, key, genre, and identity changes
  across catalog, search index, DJ Library, Set Builder, refresh, and restart;
  any confirmed gap receives a separate refactor item. Evidence: [ARCH-014](docs/audits/architecture-audit.md#arch-014--manual-musical-corrections-may-not-flow-through-every-derived-cache).
  Completed 2026-10-14: the executable
  [`manual-correction-propagation.json`](docs/operations/manual-correction-propagation.json)
  matrix and disposable-catalog tests cover BPM, key, genre, and identity across
  durable storage, search, DJ Library, Set Builder, refresh, and restart. Key and
  identity propagation are covered. The investigation confirmed two follow-ups:
  ARCH-014B and ARCH-014C.
- [x] **ARCH-014B — Add durable verified BPM corrections.** Priority: P1.
  Effort: M. Risk: Medium. Dependencies: ARCH-014A. Acceptance: users can save or
  clear a verified BPM; catalog delivery, DJ Library, Set Builder, refresh,
  restart, and reanalysis consistently prefer the durable verified value while
  preserving the detected BPM as evidence.
  Completed 2026-10-14: BPM verification now has a dedicated durable table and
  reporting API/UI. Saving or clearing a verified BPM synchronously rebuilds the
  Library and Set Builder projections; reanalysis remains detected evidence and
  cannot overwrite the verified value. Repository, route, propagation, restart,
  and reanalysis behavior are covered by tests.
- [x] **ARCH-014C — Publish metadata corrections through one synchronous catalog
  invalidation boundary.** Priority: P1. Effort: M. Risk: Medium. Dependencies:
  ARCH-014A. Acceptance: genre and general metadata writes atomically invalidate
  in-memory facets, persisted signatures, and the Set Builder catalog; the first
  read after a successful write observes the correction, including same-second
  writes, with behavioral coverage for DJ Library and Set Builder.
  Completed 2026-10-14: one application-owned publisher clears in-memory facets
  and the persisted Set Builder catalog before synchronously rebuilding both
  projections and recording their shared source signature. Track metadata,
  genre, descriptor, verification, and metadata-batch writes use this boundary.
- [x] **ARCH-015A — Measure concurrent job and SQLite behavior.** Priority: P2.
  Effort: M. Risk: Low. Dependencies: ARCH-004B. Acceptance: an opt-in disposable
  catalog harness runs simultaneous representative operations with bounded
  resources and reports lock waits, latency, stale results, and errors; redesign
  work is added only for measured failures. Evidence: [ARCH-015](docs/audits/architecture-audit.md#arch-015--production-scale-concurrency-behavior-needs-measurement).
  Completed 2026-10-14: an opt-in harness now runs bounded job, catalog,
  descriptor, system-state, and catalog-read operations against a temporary
  SQLite database. It reports per-operation p50/p95/max latency, SQLite lock
  errors, overlapping slow operations, stale committed reads, and final
  invariants. The 25-round/6-worker acceptance run completed 100 operations with
  no errors or stale results, so no speculative ARCH-015B redesign was added.
- [x] **ARCH-011B — Add browser workflow and accessibility smoke coverage.**
  Priority: P2. Effort: M. Risk: Low. Dependencies: ARCH-007B, ARCH-008A.
  Acceptance: save/refresh/restart, overlapping search, drive reconnect, import
  path safety, single audio playback, dialog focus, keyboard navigation, and
  supported viewports have automated or explicitly documented release checks.
  Evidence: [ARCH-011](docs/audits/architecture-audit.md#arch-011--frontend-tests-contain-brittle-source-assertions-and-duplicated-cases).
  Completed 2026-10-15: an isolated Playwright/Chromium release gate now covers
  persisted settings after refresh, overlapping search requests, drive
  disconnect/reconnect, single-preview ownership, dialog focus and Escape,
  desktop/mobile-width layouts, duplicate DOM IDs, and serious/critical WCAG
  violations. Existing deterministic Python coverage remains authoritative for
  application restart and import path safety. The browser run also exposed and
  fixed three stale frontend-service consumers and searchable-select IDs that
  collided with the intro/outro search-window fields.

Phase acceptance: architectural violations and critical behavior regressions
fail with clear messages before merge.

## Phase 5 — Documentation and Developer Experience

Objective: make placement and dependency rules discoverable. Dependencies:
Phases 2–4. Benefit: future contributors and coding agents extend the intended
boundary rather than rebuilding legacy coupling.

- [x] **ARCH-DEV-001 — Update architecture maps and contribution recipes.**
  Priority: P2. Effort: M. Risk: Low. Dependencies: ARCH-012B. Acceptance:
  `docs/architecture/architecture.md`, `docs/architecture/repository-map.md`, and README explain runtime
  composition, dependency direction, API/feature placement, musical-profile
  ownership, job lifecycles, provider additions, test placement, and quality
  commands; Graphify is refreshed. Evidence: audit sections 3, 14, and 18.
  Completed 2026-10-15: the architecture guide now documents runtime dependency
  direction, focused backend/frontend ownership, and concrete recipes for API,
  persistence, browser, musical-policy, background-operation, and provider
  changes. The repository map reflects current services, safeguards, browser
  tests, and commands; the README points contributors to the authoritative
  standard and risk-based release gates. Graphify was refreshed after the update.
- [x] **ARCH-DEV-002 — Record compatibility and architecture decisions.**
  Priority: P3. Effort: S. Risk: Low. Dependencies: product decisions for
  ARCH-009A and open questions. Acceptance: short decision records explain saved
  sets, musical authority, job contracts, schema migration, and why the project
  remains a modular monolith with vanilla JavaScript. Evidence: audit section 19.
  Completed 2026-10-15: five indexed ADRs now record backend-owned saved sets,
  authoritative musical-profile precedence, shared operation contracts with
  specialized executors, ordered idempotent SQLite migrations, and the decision
  to retain the modular monolith and vanilla JavaScript. Each record states its
  compatibility guarantees, consequences, and explicit revisit conditions; the
  architecture guide, repository map, and audit link to the decision index.

Phase acceptance: a new contributor can locate the correct backend/frontend
owner and required tests without reading the composition roots end to end.

## Phase 6 — Final Regression and Stability Verification

Objective: prove modernization preserved the local DJ application. Dependencies:
all approved implementation phases. Benefit: evidence-based release confidence.

- [x] **ARCH-VERIFY-001 — Run the full compatibility and rollback release gate.**
  Priority: P0. Effort: M. Risk: Low. Dependencies: all implemented architecture
  tasks. Acceptance: Ruff, MyPy, Python/JS tests, stability gate, backup/restore,
  old database/saved-set fixtures, CLI, endpoint inventory, exports, catalog-scale
  Set Builder evaluation, optional live Ollama acceptance, and manual core DJ
  workflows pass; rollback is rehearsed; intentional differences are documented.
  Evidence: audit sections 16–18.
  Verification run 2026-10-15: quality, coverage, stability, backup/restore,
  rollback, legacy database and saved-set compatibility, CLI, endpoint, export,
  and eight browser workflow/accessibility checks passed. The release was
  provisionally approved under an explicit temporary owner waiver for DJ
  listening. After reconnecting the configured `/Volumes/YOTUO` library, 3,255
  of 3,260 catalog files were readable
  and all five Set Builder scenarios completed with valid plans, automated-ready
  status, and average quality 80.4. The optional Ollama suite was skipped because
  the local service was offline.
  Full evidence and exact rerun commands are recorded in
  [the release-gate report](docs/operations/architecture-release-gate.md).
- [ ] **ARCH-VERIFY-002 — Confirm the temporary listening waiver.**
  Priority: P0. Effort: S. Risk: Medium. Dependencies: ARCH-VERIFY-001.
  Acceptance: the owner listens to all five generated release playlists,
  records acceptance or rejection, and reopens the release gate if any scenario
  requires correction. The temporary waiver is authorization, not evidence that
  listening already occurred.

Phase acceptance: all protected interfaces, data, musical behavior, and workflows
match the Phase 0 baseline or have an explicitly approved compatibility note.

## Next work

- [x] **ARCH-017A — finish the application composition boundary.** Moved
  provider metadata and YouTube matching into `audioextender/imports/`, moved
  genre taxonomy, local-media I/O, catalog reconciliation, catalog payloads,
  and historical library-job removal into `audioextender/library/`, and moved
  the final job/import/library handlers into focused routers. Public endpoints,
  compatibility exports, stored data, and job payloads remain unchanged;
  `audioextender/web/application.py` is now limited to composition, middleware,
  startup, shared runtime policy, and small compatibility adapters.
- [x] **Extract downloaded-library metadata batch operations.** Move genre
  rescanning, WAV retagging, and artwork synchronization out of
  `audioextender/web/application.py` into focused services and routers. Preserve
  progress reporting, retry/error state, existing API contracts, and background
  batch behavior. Completed with a shared cancellable/retryable batch lifecycle,
  focused metadata routes, atomic mutation service, and relocation state parity.
- [ ] **Harden intent-driven set generation against realistic catalogs.** Use
  the new structured Set Builder interpretation to improve scarcity expansion,
  prevent irrelevant genre leakage, keep generation responsive on large
  catalogs, and make the final proposal summary distinguish direct matches,
  optional genres, bridge tracks, and relaxed preferences.
- [ ] **Complete musical-identity inference and review.** Add richer
  audio-derived evidence, improve the unknown-term review loop, and validate
  inferred descriptors at catalog scale while always preserving tracks marked
  as manually tagged.

## Implementation audit — September 21, 2026

Status definitions:

- **Complete** means the full backlog behavior is available in the current app.
- **Partial** means a useful foundation exists, but at least one requirement in
  the original item remains unfinished.
- Items not listed in this audit remain planned.

### Completed

- [x] **Manual waveform editor.** Review Queue supports custom intro/outro
  regions, draggable selection, exact timestamps, editable approximate bars,
  bar snapping, zoom, full-track and region playback, copies, source-to-output
  insertion, destination placement, and a rendered placement preview.
- [x] **Library Intelligence foundation.** DJ Library groups analyzed tracks by
  warm-up, peak-time, closing, vocal-safe, melodic, ambient, and live-timing
  roles and provides BPM/key-compatible track suggestions.
- [x] **Latest analysis overflow fix.** Long track names are bounded in the
  Process dashboard without pushing content outside the card.
- [x] **Process/DJ Library responsibility split.** Process is focused on batch
  configuration, active jobs, and recent status; collection discovery and
  set-planning filters live in DJ Library.
- [x] **Beginner-friendly mix-role explanations.** Every role explains its
  intended DJ use.
- [x] **Expandable role collections.** Role counts can reveal every matching
  track instead of limiting the user to three examples.
- [x] **Musical key and Camelot display.** DJ Library shows conventional and
  Camelot notation and remembers the selected display mode.
- [x] **Effective preset visibility.** The app distinguishes an `auto` request
  from the effective selected preset, and DJ Library can filter by the effective
  preset.
- [x] **DJ Library as a planning hub.** The page now combines analyzed-track
  browsing, DJ metadata, mix roles, compatibility, versions, downloads, genre
  editing, extension entry points, and set-planning filters.
- [x] **Initial Set Builder.** The app can generate an ordered set from genre,
  duration, BPM, energy curve, key strictness, vocal profile, timing, and edit
  preferences. Plans are explainable, manually reorderable, saveable, and
  exportable as CSV or M3U8.
- [x] **Local-first Set Builder intention interpreter.** Natural-language DJ
  briefs are converted into a schema-constrained, editable plan through local
  Ollama by default, optional OpenAI fallback when explicitly configured, and
  deterministic offline rules when no model is available. The model interprets
  language only; catalog scoring, ordering, and audio remain local.
- [x] **Required, excluded, locked, and alternate set tracks.** Set Builder
  preserves locked positions, supports required/excluded rules, and can replace
  a track with an unused alternative.
- [x] **Navigation terminology.** The primary workflow is consistently labeled
  Process, Import, Music Files, DJ Library, Set Builder, Review Queue, Analysis
  & Feedback, and Settings.
- [x] **Bulk collection interaction.** Music Files and DJ Library support
  select-all-visible, broad card-click selection, selected-row highlighting,
  bulk actions, and collapsible crate sidebars.
- [x] **Manual genre synchronization.** Genre changes move the WAV, survive
  refresh/rescan, and propagate to Music Files, DJ Library, filters, and Set
  Builder. Tracks with no genre metadata enter `Needs genre` instead of
  `Latin / Other`.

### Partially completed

- [~] **Feedback-informed candidate ranking.** Candidate feedback is captured,
  persisted, summarized in Analysis & Feedback, and protected from duplicate
  log entries. Candidate reranking is explainable and style-aware. Accepted and
  rejected feedback does not yet personalize future rankings, expose separate
  preference scores, enforce a learning threshold, or protect against
  preference overfitting.
- [~] **Preflight analysis mode.** Users can analyze without extending, request
  candidate review, inspect warnings/classifications, and open the custom
  editor before committing an edit. There is not yet one batch-level approval
  screen covering proposed presets, stems, bar lengths, candidates, and
  warnings before any audition rendering.
- [~] **Automatic A/B evaluation.** Source and edited audio have synchronized
  playback and feedback capture. The app does not yet create automatic,
  identical loudness-matched transition windows or store a direct A/B winner.
- [~] **Transition repair modes.** The processing engine has crossfade and
  compatibility-aware splice policies, including bass/timbre/tail safeguards.
  The complete selectable set of micro-crossfade, tail overlap, reverb, drum
  underlay, harmonic sustain, and progressive stem reconstruction is not
  available.
- [~] **DJ export profiles.** WAV bit depth, cue sheets, Rekordbox XML, preview
  exports, and grouped bulk downloads exist. Dedicated Serato, Engine DJ, and
  Traktor naming/cue/loop/metadata profiles remain unfinished.
- [~] **Compatibility explanations.** Match percentages expose tempo, harmonic
  key, energy, and shared-role components. Vocal density and timing behavior are
  not yet included in the displayed compatibility formula.
- [~] **Set-planning filters.** DJ Library supports search, BPM range, key,
  Camelot display, energy, role, genre, vocals, timing, extension result,
  effective preset, active chips, reset, and several sort modes. It does not yet
  filter by processing status, compatibility to a chosen track, or prior set
  usage, and chips are not individually removable.
- [~] **Clickable filter discovery.** Role and genre crates can apply filters
  directly. BPM, key, compatibility factors, and metadata values throughout
  expanded track details are not all clickable filter shortcuts yet.
- [~] **Candidate diversity.** Multiple candidates are generated and ranked
  with phrase, loop, transition, context, and safety measurements. The three
  choices are not yet deliberately assigned distinct strategies such as
  original-preserving, smoothest-loop, and strongest-DJ-utility.
- [~] **Metadata authority and consistency.** Manual genre decisions currently
  outrank inferred metadata and propagate across the main collection views.
  The same explicit authority model and stored override provenance still needs
  to cover every artist, title, version, BPM, key, duration, role, and playlist
  value.
- [~] **Duplicate control.** Tracks now receive durable, human-readable
  recording-family and version IDs, new imports match source identifiers and
  normalized recording names, exact audio fingerprints are generated, and
  Collection Integrity supports conservative merge review or an explicit
  keep-separate decision. Confirmed merges preserve playlists, jobs, feedback,
  verified keys, artwork, and the unused physical WAV. Perceptual fingerprinting
  and automatic prevention before every external download remain planned.
- [x] **Set Builder same-recording uniqueness.** Completed 2026-10-21. Safe
  normalized artist/title variants converge on one persistent recording family;
  the compact catalog now carries family/version IDs; and candidate retrieval,
  AI repair, deterministic fallback, validation, saved-set recovery, and manual
  plan edits prevent a second member of the same recording family from entering
  a set. Explicit keep-separate and manual-link decisions remain authoritative.
- [~] **Durable background jobs.** Processing jobs persist, interrupted active
  work is recovered to a truthful failure state, and the UI supports pause,
  resume, cancel, retry/reprocess, reordering, review states, and queue cleanup.
  Downloads, matching, exports, and processing do not yet share one durable job
  model, and automatic restart continuation/idempotency requires more work.
- [~] **UI consistency.** Navigation language, dense track rows, crate sidebars,
  selection behavior, destructive styling, single-audio playback, and many
  responsive layouts are aligned. A formal shared component system, complete
  status/color normalization, keyboard audit, reduced-motion support, and
  viewport regression suite remain unfinished.
- [~] **Set Builder maturity.** The current builder includes one explainable
  proposal, energy/BPM curves, manual ordering, rules, alternatives, transition
  scores, vocal-clash warnings, saved plans, and exports. Multiple proposal
  strategies, transition audio previews, used-in-set tracking, deeper warnings,
  and DJ-platform set exports remain planned.
- [~] **Restart and recovery testing.** Interrupted-job recovery and pause/resume
  behavior have automated tests. Large realistic catalog migrations, complete
  restart/retry end-to-end coverage and performance fixtures remain part of the
  milestone gate. Integrity-checked backup/restore, retention, restore preview,
  pre-restore snapshots, and recovery documentation are complete.

## Intent-driven Set Builder and musical identity

Status: **In progress — local-first interpretation, Phase 1 journey planning, Phase 2A candidate safety, Phase 2B validated AI track planning, Phase 2C quality hardening, Phase 2D comparative AI acceptance, Phase 2E conservative preference learning, and Phase 2F human review and calibration are complete.** Set
Builder accepts a natural-language intention and translates it into editable
hard requirements, weighted preferences, limits, requested and optional genres,
genre drift, vibe, energy curve, opening/ending traits, and an ordered fallback
policy. It uses local Ollama (`qwen3.5:4b`) by default, can use OpenAI only when it
is explicitly configured, and falls back to deterministic browser rules. Model
output is schema-constrained, cleaned of placeholder/schema labels, and
canonicalized against catalog vocabulary. The original brief remains intact.

The Journey Planner now converts that interpretation into editable musical
sections with runtime shares, genres, characteristics, purposes, and energy
boundaries. Invalid AI plans fall back deterministically, explicitly requested
genre order is protected, and the edited journey drives positional genre and
energy scoring. Phase 2A now provides bounded, diverse candidate pools with
stable catalog IDs, availability checks, scarcity tiers, and evidence labels,
plus deterministic validation for invented IDs, duplicates, exclusions,
required or locked tracks, duration, section coverage, BPM jumps, keys, and
vocal collisions. Phase 2B now selects and orders only those controlled
shortlists, repairs invalid model output, runs through a cancellable asynchronous
job, and falls back to a validated deterministic plan when the provider is
offline, times out, or cannot produce a valid answer. The UI exposes AI Planned,
AI Interpreted, and Classic modes rather than hiding which layer made a choice.
Phase 2C adds deterministic proposal evaluation and disclosure, reproducible
planning receipts in saved sets, persisted/retryable interrupted jobs, explicit
planning duration, small/medium/large catalog performance budgets, and an
opt-in live Ollama track-selection acceptance case. A repeatable catalog-scale
evaluation harness now measures checked-in musical scenarios, compares each run
with its prior report, and supports either the deterministic fallback or the
configured model. Remaining Set Builder work is feedback-informed
personalization and human review of real-library evaluation results, not
another unvalidated model path.

Phase 2D generates an independent deterministic baseline for every valid AI
proposal and selects AI only when it improves the shared quality score without
reducing requested-genre coverage. Dynamic schemas constrain track and section
IDs and exact counts; bounded structural repair preserves valid AI selections,
fills only missing eligible slots, and discloses each repair. Receipts and the
catalog evaluation report retain both scores, the winner, provider/model,
latency, repairs, and rejection reason. Remaining model work is improving local
model selection quality and latency—not weakening the acceptance policy.

The generator uses the structured plan during local candidate retrieval and
scoring, never relaxes hard identity requirements, discloses direct versus
expanded matches, and saves the interpreted brief with the set. Track-level
identity descriptors persist with category, provenance, confidence, and update
time; participate in scoring; are searchable; and can be edited individually
or in bulk from Music Files and DJ Library. Browser storage remains only as a
compatibility fallback for uncataloged tracks. Remaining work is richer
audio-derived identity inference, catalog-scale review, stronger scarcity
handling, and catalog-scale musical review.

### Problem

A request such as “Latin Techno” is often simultaneously too narrow and too
ambiguous. A track may be cataloged as Techno, Latin House, Guaracha, Cumbia,
Reggaeton, or Other while still being appropriate for a Latin electronic set
because of its percussion, Spanish vocals, recognizable samples, production
style, cultural association, energy, or ability to bridge into Techno. Forcing
all of those ideas into the folder genre taxonomy would make metadata less
accurate and still fail to express briefs such as “Ecuadorian party with a
Techno progression.”

### Product direction

Add a natural-language **Set intention** field alongside structured controls.
For example:

> Build a driving Latin electronic set with a Techno foundation. Favor Spanish
> vocals, recognizable Latin samples, dembow or Latin percussion, and tracks
> that would connect with an Ecuadorian party crowd. Allow Reggaeton, Latin
> House, Guaracha, Cumbia edits, and tribal tracks when they can bridge
> naturally into Techno. Avoid long stretches of generic instrumental Techno.

Translate the brief into a visible, editable weighted interpretation rather
than treating it as an opaque prompt:

- Techno foundation: high priority.
- Latin rhythmic or vocal identity: required for most tracks.
- Ecuadorian-party crate or cultural-context tag: strongly preferred.
- Genre drift: moderate.
- Recognizable samples or familiar material: medium priority.
- Peak-time energy: high.
- Generic Techno without Latin characteristics: limited.

The DJ must be able to correct the interpretation before generation and see
which preferences are hard requirements, weighted preferences, or permitted
fallbacks.

### Multidimensional track description

Keep physical folder genre and existing parent/detailed genre metadata as the
catalog authority, but add independent, many-to-many descriptors for Set
Builder. Do not turn cultural context or a personal crate into a fake genre.

- **Core genre:** Techno, House, Reggaeton, Cumbia, and similar catalog genres.
- **Regional or cultural influence:** Ecuadorian, Colombian, Caribbean,
  Brazilian, Andean, and user-defined values.
- **Rhythmic influence:** dembow, Latin percussion, tribal, salsa, cumbia,
  syncopated, four-on-the-floor.
- **Sound character:** dark, industrial, melodic, hypnotic, percussive,
  euphoric, raw.
- **Vocal identity:** Spanish vocals, vocal chops, chant-heavy, instrumental,
  singalong, language where known.
- **Energy and DJ role:** warm-up, driving, tension builder, peak-time, reset,
  bridge, anthem, closing.
- **Context or personal crate:** Ecuadorian Party, Latin Warehouse, Perreo to
  Techno, Spanish Vocal Techno, Familiar Latin Samples, and other user-created
  collections.
- **Familiarity:** underground, recognizable sample, classic, crossover, or
  crowd singalong.

Descriptors need provenance and confidence: manually assigned, imported,
inferred from audio/metadata, or inherited from a user crate. Manual values
must survive rescans, reanalysis, relocation, and metadata synchronization.

### Scarcity-aware expansion

When direct matches cannot satisfy duration, track count, or transition
quality, expand the candidate pool through an explicit ordered ladder:

1. Literal Latin Techno matches.
2. Techno with Spanish vocals, Latin samples, or Latin percussion.
3. Latin House and Guaracha with Techno-compatible energy and structure.
4. Reggaeton or Cumbia edits that bridge through BPM, key, rhythm, or
   production style.
5. Neutral bridge tracks that preserve the requested progression.
6. Pure Techno only where needed to maintain flow and runtime.

The expansion policy must be configurable per brief. Hard exclusions and
must-play tracks always take precedence; the system must never silently relax a
hard rule.

### Explainability and disclosure

Every generated proposal must report both the requested intention and what was
actually available. Example:

> Only six direct Latin Techno matches were available. Four Latin House edits,
> three Spanish-vocal Techno tracks, and two neutral bridge tracks were added.

For every fallback track, explain the relevant musical evidence, such as
“Spanish vocal and Latin percussion over a Techno-compatible 128 BPM grid” or
“Cumbia edit used as a bridge between Latin House and driving Techno.” Show
which preference was relaxed, why it was necessary, and whether an alternative
exists. Proposal health must separate intention match from transition quality
and analysis confidence.

### Suggested implementation boundary

- Store genre taxonomy separately from freeform descriptors, cultural/context
  tags, and crate membership.
- Introduce a normalized Set Builder brief model containing requirements,
  weighted preferences, exclusions, and an ordered fallback policy.
- Keep brief interpretation, candidate retrieval, candidate scoring, transition
  scoring, and proposal rendering as separate services.
- Keep natural-language interpretation behind the current structured planner:
  local Ollama first, explicitly configured OpenAI second, and deterministic
  browser rules last. Never allow provider output to bypass schema validation,
  vocabulary canonicalization, or the editable interpretation screen.
- Reuse existing genre weights, detailed genres, exclusions, must-play tracks,
  energy curves, vocal profiles, roles, and proposal strategies instead of
  creating a parallel generator.
- Save the original description and interpreted weights with every saved set so
  the result can be reproduced after restart.

### Acceptance criteria

- A DJ can request a culturally or contextually specific set without inventing
  a catalog genre.
- The interpreted brief is visible and editable before generation.
- Direct matches are preferred and fallback expansion follows the displayed
  order.
- Hard requirements are never relaxed silently.
- Every non-direct match explains why it belongs and which gap it fills.
- The proposal summarizes direct matches, expanded matches, bridge tracks, and
  relaxed preferences.
- Manual descriptors and saved briefs survive restart, reanalysis, genre moves,
  and library relocation.
- Existing genre folders and track IDs remain stable when contextual tags or
  crate membership change.

### Implemented intention-planner verification

- Unit coverage verifies provider ordering, strict structured output,
  Ollama-to-OpenAI fallback, hallucination cleanup, and catalog normalization.
- An opt-in live Ollama acceptance suite covers a chill Reggaeton/Dembow
  kickback with melodic opening, Latin Techno/House with optional Schranz and
  energy waves, an Afro House lounge warmup, and a peak-time Techno journey.
- The provider-status endpoint reports the active local/cloud model so the UI
  can truthfully label Local AI, Cloud AI, or offline-rule results.
- No audio crosses the model boundary; only the text brief and bounded catalog
  vocabulary are supplied for interpretation.

## Feedback-informed candidate ranking

Use accepted and rejected listening feedback to personalize candidate ordering
without replacing the technical safety score.

- [x] Derive preference signals from lock, remove, replace, add, save, and export actions.
- [x] Preserve technical relevance and expose a separate bounded preference adjustment.
- [x] Explain matching feedback signals and their distinct-track evidence.
- [x] Require three distinct tracks before applying a signal.
- [x] Keep feedback ranking locally inspectable, pauseable, and resettable.
- [x] Cap adjustments at ±8 and damp broad attributes to limit overfitting.
- [x] Capture overall, per-track, rejection-reason, and transition judgments.
- [x] Compare personalized and neutral acceptance and report ranking changes.
- [x] Detect contradictory feedback and broad-signal dominance.
- [x] Let the DJ dismiss individual learned signals.
- [x] Learn bounded transition preferences after three distinct track pairs.
- [x] Compare personalized and baseline plans across five checked-in musical scenarios.
- [x] Add Phase 2G timing, outcome, fallback, repair, and aggregate AI operations telemetry.
- [x] Add a strict release gate that cannot pass without valid five-scenario evidence and explicit DJ listening approval.
- [x] Reduce Ollama planning context by 85–88%, use ID-only output, and capture prompt/output timing metrics.
- [x] Distinguish silent genre-coverage loss from explicitly proven zero-candidate catalog scarcity.
- [ ] Complete the final hands-on acceptance review against the connected real library, pass `--manual-listening-approved`, and tune weights only from that evidence.

## Preflight analysis mode

Analyze a batch before rendering audio, then review proposed classifications,
presets, stem use, bar lengths, candidates, and warnings before approval.

## Automatic A/B evaluation

Compare original and edited transitions with identical, loudness-matched
listening windows and record the preferred version.

## Manual waveform editor

Drag loop and splice regions on the waveform, snap them to bars, audition the
result, and rebuild without editing JSON overrides.

## Candidate diversity

Make the three ranked choices intentionally represent different strategies:
closest to the original arrangement, smoothest technical loop, and strongest
DJ utility.

## Transition repair modes

Select among micro-crossfade, tail-preserving overlap, reverb continuation,
drum underlay, harmonic sustain, and progressive stem reconstruction.

## DJ export profiles

Provide Rekordbox, Serato, Engine DJ, and Traktor naming, bit depth, cue, loop,
and metadata profiles.

## Beat-grid verification workflow — deferred

Status: **Backlog.** Keep this design for a later milestone; it is not the
current implementation priority.

Add a dedicated review workflow for tracks whose rhythmic analysis needs
confirmation, without treating missing cues as an analysis failure.

- Surface tracks with low beat-grid confidence, tempo drift, or conflicting BPM
  and downbeat estimates.
- Show the waveform with detected beat and downbeat markers during playback.
- Provide quick corrections for half/double BPM, grid offset, and the first
  downbeat.
- Let the user mark a beat grid as verified and exclude verified tracks from the
  review queue.
- Preserve manual beat-grid corrections and verification across reanalysis,
  rescans, imports, and library moves.
- Use verified timing data in loops, cue placement, transition scoring, and Set
  Builder recommendations.

## Library intelligence

Group tracks by warm-up, peak-time, closing, vocal-safe, melodic, ambient, and
live timing behavior, with BPM/key-compatible track suggestions.

Next Library milestone:

- Fix the Workspace **Latest analysis** card so long track names never overflow
  its column. Use a bounded title area with wrapping or ellipsis, preserve the
  metadata line, and keep the card responsive at narrow widths.
- Keep Workspace focused on active processing and brief recent status. Put
  discovery, organization, compatibility, and set-planning filters in Library
  rather than duplicating them on the processing dashboard.
- Explain every mix role in beginner-friendly language, including when a DJ
  would use warm-up, peak-time, closing, vocal-safe, melodic, ambient, and live
  timing tracks.
- Make every role expandable so a count such as `16 warm-up` can reveal all 16
  tracks rather than only showing three examples.
- Explain compatibility percentages and show the individual factors behind the
  score, such as BPM distance, harmonic compatibility, energy, role, vocal
  density, and timing behavior.
- Show both conventional musical keys and Camelot Wheel notation throughout the
  Library. Make the preferred notation configurable without discarding the
  alternate value.
- Distinguish the preset requested by the user from the concrete preset chosen
  by automatic classification. Filtering by the effective detected preset must
  work even when the original job was submitted with `auto`.
- Replace the basic Library filter row with set-planning filters for BPM range,
  key/Camelot value, energy, mix role, genre/category, vocals, timing behavior,
  extension result, effective preset, and processing status.
- Support practical discovery questions such as: tracks near the current BPM,
  harmonically compatible tracks, tracks that raise or lower energy, vocal-safe
  transitions, warm-up or closing alternatives, and tracks not yet used in a
  planned set.
- Allow clicking a role, key, BPM, category, or compatibility factor anywhere
  in Library to apply it as a filter instead of requiring the user to rebuild
  the same query manually.
- Make active filters visible, removable, and easy to reset; include sorting by
  title, BPM, key, energy, compatibility, and most recently processed.
- Treat the Library as a broader DJ set-planning hub rather than only an archive
  of generated edits.

Potential follow-up: add a set builder that proposes an ordered crate or set
using harmonic compatibility, BPM progression, energy arcs, mix roles, vocal
spacing, and user-defined opening/peak/closing goals. Keep suggestions
explainable and manually reorderable.

## Automatic best-source import

Keep single-track importing simple: the user supplies a Spotify or YouTube
reference and the app recommends one source rather than making them compare
formats manually.

Use the same resolver for playlist CSV and other bulk imports. Bulk mode should
automatically download the best eligible version for every track without asking
the user to choose candidates one by one.

- Resolve Spotify metadata, then search approved external catalogs and YouTube.
- Prefer an explicitly downloadable, clearly licensed original FLAC/WAV over a
  compressed source. Accept lossless derivatives only when their provenance
  points to an original lossless master.
- If no better licensed master is available, use the existing ranked YouTube
  match as the fallback after the current authorization confirmation.
- Rank source quality separately from recording identity. Verify title, artist,
  remix/version, and duration before comparing codec or technical quality.
- Compare source codec, provenance, sample rate, bit depth, clipping, true peak,
  loudness, spectral bandwidth, and duplicate fingerprint where practical.
- Preserve the selected source URL, license URL, attribution, source identifier,
  quality tier, and import date in the catalog.
- Present one recommended result with a short explanation, while keeping
  alternate candidates and diagnostic measurements in optional details.
- In bulk mode, resolve and rank every row independently, automatically choose
  the best eligible source, and continue processing the rest of the batch when
  one track cannot be resolved.
- Apply a minimum identity-confidence threshold before automatic bulk download.
  A higher-quality file must not override a stronger title/artist/version match.
- Prefer lossless licensed sources in bulk exactly as in single-track import;
  otherwise use the validated YouTube fallback when its download authorization
  is already established for that batch.
- Produce one completion report grouping imported lossless masters, imported
  compressed sources, YouTube fallbacks, duplicates skipped, ambiguous matches,
  missing licenses, and failed downloads.
- Put ambiguous, mismatched, or unlicensed rows into **Needs review** rather than
  silently downloading them or blocking successful rows.
- Never describe a lossy YouTube source decoded to WAV as lossless; label it
  **Lossy source converted to WAV**.
- Do not substitute a different recording merely because its file format looks
  better. When identity or licensing is uncertain, keep the result for review.

Initial catalog priority: Jamendo, ccMixter, Internet Archive items with explicit
license metadata, and Free Music Archive where the individual track license and
download permission are unambiguous.

Acceptance criteria:

- The default import flow remains one paste and one recommended source.
- Bulk imports require one batch action rather than per-track source selection.
- Every eligible bulk row receives the best verified version available at the
  time of import, with resumable progress and a final exception report.
- A licensed lossless master wins over a YouTube-derived version of the same
  recording.
- YouTube remains a usable fallback when no verified better source exists.
- Every automatic choice can explain both the identity match and quality choice.
- Importing never silently changes the requested mix, edit, live recording, or
  remaster.

## Stability and scale milestone

- [x] Introduce hierarchical electronic taxonomy (Electronic → Techno/House/
  Bass/D&amp;B/Trance/Garage/Breaks/Hardcore → subgenre) and reusable,
  stateful collapsible genre trees in Music Files and DJ Library.

- [x] Add a local audio playlist importer that converts existing MP3/lossless
  collections to tagged WAV files, classifies them into genre folders, retains
  playlist membership, and skips exact catalog duplicates without extending.

- [x] Serve the DJ Library from a compact latest-generation catalog instead of
  transferring the full job history, full report, and full download catalog on
  every visit. Version history now loads only when a track requests it.
- [x] Add bounded, status-filterable job paging and cache the parsed processing
  report until its file changes.

Pause major feature expansion and harden the current workflow before deepening
Set Builder:

`Import → Music Files → Process → DJ Library → Set Builder`

Review Queue and Analysis & Feedback remain supporting branches. The objective
is to make the existing system fast, predictable, recoverable, and consistent
for large real-world DJ collections.

### 1. Library-scale performance

Phase-one hardening completed September 21, 2026:

- Downloaded-catalog filesystem migration is no longer tied to page refreshes.
- [x] Catalog migration now has a durable SQLite version checkpoint, so app
  restarts skip the legacy sidecar scan entirely. A manual background
  **Reconcile files** action compares stored modification-time and size
  signatures and processes only new or changed source records.
- Latest and latest-completed analysis jobs are joined to catalog tracks in
  indexed SQLite queries instead of scanning up to 10,000 jobs in Python.
- Music Files and DJ Library audio sources load only when the user interacts
  with a player; opening either page no longer starts hundreds of audio range
  requests.
- Both collections show bounded 50- or 100-track pages with numbered navigation
  above and below the list. Off-page cards are detached from the live document;
  filtering, sorting, page-local **Select all visible**, and cross-page
  selections remain available.
- Music Files now requests only its current page. Search, genre, playlist,
  analysis status, and sorting execute in indexed SQLite queries; the response
  includes filtered totals and catalog-wide genre/playlist facets. Rapid search
  responses are sequence-guarded and selections persist across server pages.
- Repository coverage verifies latest versus completed analysis resolution;
  the full automated suite currently contains 122 passing tests.

Remaining scale work:

- Establish measurable targets for 1,000, 5,000, and 10,000-track collections.
- Stop rendering an audio element and a full detail body for every track at
  initial page load. Load players and expanded details only when requested.
- [x] Add bounded server-paginated lists to Music Files and DJ Library while
  preserving filters, sorting, page-local selection, and numbered navigation.
- [x] Move DJ Library filtering, sorting, pagination, and sidebar aggregation to
  an indexed SQLite search table using the server-page pattern established in
  Music Files. Only the requested 50/100 Library cards are transferred and
  rendered; generation history remains lazy.
- [x] Add catalog-wide **Analyze all matching** from Music Files and reuse the
  memory planner for up to three concurrent analysis-only jobs. Stem-enabled
  processing and extensions remain exclusive, and report writes are serialized.
- Cache Library Intelligence counts and compatibility inputs, then invalidate
  only the affected track when metadata or analysis changes.
- Add loading, partial-result, and retry states so a slow catalog never appears
  empty or frozen.

Acceptance criteria:

- Opening Music Files or DJ Library remains responsive with 10,000 tracks.
- Filtering and sorting produce visible results quickly without freezing audio
  playback or the rest of the interface.
- Selecting all visible tracks works across pagination or virtualization without
  selecting hidden tracks unintentionally.

### 2. Metadata authority and consistency

Deferred workflow: **Guided Needs attention triage**

- Split attention items into missing metadata, unmapped genre, missing file,
  failed artwork, and other maintenance failures.
- Show the exact track and reason for every item, with focused single-track and
  bulk repair actions.
- Offer automatic genre suggestions and sequential metadata review without
  hiding unresolved items across pages.
- Reconcile reports automatically so repaired or removed tracks disappear and
  resolved maintenance errors do not return after refresh or restart.

- Define one precedence policy for every editable value: manual user edits,
  trusted analyzed values, imported metadata, inferred values, then fallback.
- Apply the policy consistently to genre, subgenre, artist, title, remix/version,
  BPM, key, Camelot value, duration, playlist membership, and track roles.
- Store manual overrides explicitly instead of inferring them from a filename or
  current folder, so rescans cannot overwrite user decisions.
- Display the source of important values where useful: manual, analyzed,
  imported, or inferred.
- Make a metadata change propagate immediately to Music Files, DJ Library,
  filters, Set Builder, reports, exports, and physical genre folders when
  applicable.
- Add an audit/repair command for catalog values that disagree with their stored
  metadata or on-disk location.

Acceptance criteria:

- Refreshing, rescanning, restarting, or reanalyzing never reverses a manual
  metadata choice.
- Every page shows the same effective artist, title, genre, BPM, and key for a
  track unless it intentionally labels a historical value.

### 3. Stable track identity and duplicate control

- Introduce a stable recording identity separate from filenames, import rows,
  processing jobs, and generated versions.
- Combine available identifiers such as Spotify URI, YouTube ID, normalized
  artist/title/version, duration tolerance, and an audio fingerprint.
- Distinguish an exact duplicate from a remix, edit, radio version, live version,
  remaster, or alternate recording.
- Attach multiple playlist memberships and source references to one recording
  instead of duplicating its master WAV.
- Provide a duplicate review screen for uncertain matches with merge, keep
  separate, and replace-file actions.
- Preserve analysis, edits, feedback, playlist membership, and set usage when
  records are safely merged.

Acceptance criteria:

- Reimporting the same recording does not create another master track or WAV.
- Legitimate alternate versions remain independent and are clearly labeled.
- A merge never silently discards analysis, edits, feedback, or set references.

### 4. Durable background jobs

- Persist download, matching, analysis, extension, export, and review states in
  a unified job model.
- Recover queued and interrupted jobs after an application restart without
  duplicating output or leaving tracks permanently marked as processing.
- Define clear paused, awaiting-review, dismissed, canceled, retryable-failure,
  permanent-failure, and completed states.
- Add retry controls with retained configuration and an error explanation.
- Make pause and cancel cooperative at safe processing boundaries and keep a
  canceled track available for a later retry.
- Record structured stage timing and failure context for diagnostics without
  exposing secrets or excessive logs in the UI.

Acceptance criteria:

- Restarting the app during a batch leaves every job in a truthful, recoverable
  state.
- Retrying a failed or canceled job never creates an accidental duplicate
  generation or corrupts the original file.

### 5. UI and terminology consistency

- Create a small shared design system for dense track rows, expanded details,
  filters, badges, action menus, selection bars, empty states, and dialogs.
- Standardize primary, secondary, destructive, and disabled button hierarchy.
- Keep terminology aligned with the navigation: Process, Import, Music Files,
  DJ Library, Set Builder, Review Queue, Analysis & Feedback, and Settings.
- Use the same status labels and colors across queue rows, Music Files, DJ
  Library, Review Queue, and reports.
- Make bulk selection, card expansion, audio playback, and overflow menus behave
  consistently without click conflicts.
- Complete keyboard navigation, focus indicators, accessible names, and reduced
  motion support for every primary workflow.
- Add responsive checks for laptop, narrow desktop, tablet, and mobile widths.

Acceptance criteria:

- The same action or status looks and behaves the same everywhere it appears.
- All core workflows can be completed by keyboard and remain readable at the
  supported viewport sizes.

### 6. Set Builder maturity after stabilization

- Generate multiple explainable running-order proposals rather than a single
  answer, such as safest mix, strongest energy journey, and most adventurous.
- Support required, excluded, locked, and alternate tracks while preserving
  manual ordering.
- Add transition previews using the selected original or extended versions.
- Improve energy-curve, BPM, harmonic, vocal-spacing, timing, and role controls.
- Warn about abrupt tempo/key/energy changes, repeated artists, vocal clashes,
  timing risk, unavailable files, and insufficient duration.
- Track whether a song has already been used in the current or saved sets.
- Export portable playlists and DJ-platform-ready set metadata without copying
  duplicate audio unnecessarily.

Acceptance criteria:

- Every recommendation explains why the track and transition were chosen.
- Users can alter any proposal without losing locked choices or regenerating the
  entire set unnecessarily.
- Exported running orders point to the intended source or extended version of
  every track.

### Milestone completion gate

- Add performance fixtures and a repeatable large-library benchmark.
- [x] Add a repeatable lifecycle regression fixture covering reimport,
  analysis history, verified keys, feedback, library relocation, restart,
  reanalysis, and playlist export with real WAV files and a temporary catalog.
- Add migration and recovery tests against a copy of realistic catalog data.
- Add end-to-end tests for import, analyze, review, extend, organize, build set,
  restart, retry, and export workflows.
- [x] Document and implement validated backup and restore of the catalog,
  metadata, settings, presets, reports, playlists, library identity, and
  optional analysis cache, with a pre-restore safety snapshot.
- Do not begin another major product area until the scale, consistency,
  duplicate, recovery, and core UI acceptance criteria above are met.

## Regression listening suite

Keep a curated group of difficult tracks and compare algorithm revisions
against saved candidate decisions and listening feedback.

## Recently completed: genre review and folder expansion

- Split the broad Needs genre bucket into Missing metadata, Unmapped metadata,
  and Broad Latin so each group has a clear next action.
- Added those review states as direct Music Files filters with independent
  counts under a collapsible Needs genre folder.
- Expanded Latin classification with neoperreo, flamenco, Latin rock, Latin
  indie, Latin ska, Latin hip-hop, and Latin R&B.
- Expanded electronic classification with future bass, dubstep, moombahton,
  phonk, big beat, and trip hop, plus additional hip-hop and pop mappings.
- Preserve automatic folder creation: a genre rescan creates any newly needed
  hierarchy and moves the WAV while keeping catalog and analysis paths synced.
