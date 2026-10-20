# DJ Library Studio — Architecture Audit

Audit date: 2026-10-11  
Scope: repository architecture, technical debt, and an incremental modernization plan.  
Decision: retain the modular monolith and vanilla JavaScript frontend.

## 1. Executive Summary

DJ Library Studio has a sound architectural direction and unusually strong behavioral safeguards for a local application of its age. Domain packages exist, SQL is contained in repositories, the Set Builder has explicit validation and deterministic fallback, dependency injection is used where external work matters, and the current test suite is broad and fast. The audit found no Python import cycles and no reason to replace the modular monolith, SQLite, FastAPI, or vanilla JavaScript.

The main concern is incomplete migration rather than a failed architecture. `audioextender/web/application.py` remains both the composition root and a 3,693-line legacy feature host with 55 route handlers, 128 top-level definitions, 37 internal package dependencies, and substantial global mutable state. The audio pipeline has a similarly concentrated 662-line `TrackProcessor.process` method. In the browser, feature extraction has reduced `web/app.js`, but `app.js` is still 1,878 lines and `set-builder.js` combines state, API orchestration, deterministic planning, rendering, editing, playback, persistence, and review in 675 dense lines.

The most important correctness risk is shared musical policy implemented in multiple places. Library roles and energy are calculated in both Python and JavaScript, Camelot mappings exist in both layers, and transition compatibility is scored differently by the browser and the backend planner. Some differences are legitimate presentation or planning policies; the duplicated normalization and classification rules are not. Structural work must first characterize current behavior, designate authoritative owners, and preserve algorithm outputs.

This report records **12 confirmed issues** and **3 suspected risks requiring investigation**. The recommended path is a sequence of small extractions and contract-preserving adapters, backed by characterization tests. It is not a rewrite.

## 2. Audit Scope and Methodology

### Inspected

- `README.md`, `BACKLOG.md`, `docs/architecture.md`, and `docs/repository-map.md`
- `pyproject.toml`, `package.json`, requirements, scripts, and repository layout
- all Python packages under `audioextender/`
- FastAPI composition and route modules
- JavaScript feature modules and shared browser utilities
- SQLite repositories and initialization logic
- audio analysis, processing, library, import, Set Builder, and job services
- Python and JavaScript tests, including architecture guards and synthetic evaluations
- the refreshed Graphify graph (`graphify-out/graph.json`: 2,584 nodes and 6,401 edges)

### Measurements and checks

- source line counts, AST top-level-definition counts, long-function and branch counts
- internal import fan-out/fan-in and strongly connected components
- searches for SQL, filesystem access, global mutable state, broad exceptions, browser storage, and repeated musical rules
- Graphify traversal for coupling, persistence boundaries, and background-task relationships
- existing quality and test commands

### Executed baseline

| Command | Result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -v` | 288 passed, 6 skipped |
| `npm run check` | 44 tests passed; JavaScript syntax checks passed |
| `.venv/bin/mypy` | Passed, 143 source files |
| `.venv/bin/ruff check .` | Failed: duplicate/unsorted `IntentionPlanner` import in `audioextender/web/application.py` |
| custom Python import-graph scan | 0 strongly connected components with more than one module |

No application source, schema, configuration, or test was changed. The audit did not process a real music library, run Demucs/FFmpeg workloads, perform a live Ollama evaluation, measure browser accessibility with assistive technology, or benchmark production-scale SQLite concurrency.

## 3. Current Architecture

The application is a local modular monolith:

```text
CLI (main.py)                    Browser (web/*.js)
      |                                  |
      v                                  v
processing/application APIs      FastAPI delivery and composition
      |                                  |
      +----------------+-----------------+
                       v
 analysis | audio | processing | library | imports | set_builder | reporting
                       |
                       v
       repositories + infrastructure adapters
                       |
                       v
          SQLite + filesystem + Ollama/OpenAI + media tools
```

Major ownership is generally clear:

| Area | Current owner | Assessment |
|---|---|---|
| audio decoding/stems/WAV metadata | `audioextender/audio/` | cohesive |
| musical analysis and selection | `audioextender/analysis/` | cohesive, highly reused |
| file processing/export orchestration | `audioextender/processing/` | correct boundary, concentrated orchestration |
| catalog and maintenance workflows | `audioextender/library/` | increasingly cohesive |
| authorized/local imports | `audioextender/imports/` | separated, lifecycle varies |
| AI and deterministic set planning | `audioextender/set_builder/` | strong safeguards and provider boundaries |
| persistence | `audioextender/repositories/` | SQL boundary is respected; interfaces are broad |
| HTTP delivery | `audioextender/web/` | extracted routers coexist with many legacy routes |
| browser features | `web/*.js` | feature modules exist; state/render/API concerns remain mixed |

The documented dependency direction—delivery to application/domain services to infrastructure—is mostly true. Important exceptions are not reverse imports but hidden runtime wiring: module-level service instances, mutable caches, locks, and callbacks in `application.py` make initialization and isolation depend on import order.

## 4. Existing Strengths

- **No Python import cycles.** The package graph is acyclic in the static import scan.
- **SQL is contained.** Search found SQL in `audioextender/repositories/`; no confirmed SQL statements occur in web, domain, or processing modules.
- **Replaceable external behavior.** `TrackProcessor`, import services, Set Builder providers, thread factories, progress reporters, and planning stores expose useful seams without excessive framework machinery.
- **Safe AI pipeline.** Candidate retrieval constrains the catalog, validation blocks invented IDs and hard-constraint violations, deterministic baselines compete with AI proposals, and invalid/weak model results fall back predictably.
- **Human feedback is separate from model output.** Review, preferences, evaluation, release gates, and planning are distinct modules.
- **Durability is treated explicitly.** Processing jobs, planning jobs, settings, catalog records, receipts, and backups have restart-aware behavior and tests.
- **Meaningful behavioral tests.** The suite covers settings persistence, drive reconnects, imports, catalog identities, relocation, background cancellation, planning repair, preference learning, and production gates.
- **Existing architecture guards.** `test_package_structure.py` and `frontend_modules.test.js` protect package presence, extracted-route boundaries, and selected size limits.
- **Shared request controller and playback utilities.** These directly address stale responses and multiple-audio playback.
- **Pragmatic technology choices.** SQLite, FastAPI, and vanilla JavaScript remain appropriate for a single-user local macOS application.

These protections should remain while boundaries are improved.

## 5. Dependency and Coupling Analysis

Static internal import fan-out is concentrated in `audioextender.web.application` (37 internal modules), `processing.track_processor` (20), and `processing.web_jobs` (13). The most reused modules are `analysis.key_detection` (13 importers), `analysis.section_selector` (11), `core.config` (10), and `audio.loading` (10). High fan-in for stable analysis and core contracts is appropriate; high fan-out in orchestration modules is expected but currently amplified by mixed responsibilities.

No circular import chain was found. The principal dependency violations are hidden dependencies and duplicated policy rather than cyclic imports:

- `application.py` constructs repositories/services and also owns routes, classification, caching, migrations, imports, and workers.
- frontend feature factories accept large collections of callbacks and shared mutable objects from `app.js`; the dependency direction is explicit but too broad.
- browser Set Builder logic imports classification functions from DJ Library, coupling planning to another feature module rather than a neutral musical-policy module.
- several job systems each own status vocabularies, cancellation events, restart recovery, progress, and retention.

Potential dependency inversion is justified only at volatile or costly boundaries: model providers, clocks/thread factories, media tools, planning stores, and repository capabilities. The project already does much of this. Introducing interfaces for every internal class would add ceremony without reducing risk.

## 6. Code Smells and Technical Debt

### ARCH-001 — Legacy web application remains an architectural bottleneck

**Status:** Confirmed  
**Category:** Architecture / Backend  
**Severity:** High  
**Affected files:** `audioextender/web/application.py`  
**Evidence:** 3,693 lines; 128 top-level definitions; 55 `@app` routes; 37 internal imports. Lines 154–220 construct the app, repository, services, caches, locks, queues, and mutable batch state at import time. Lines 3100–3350 still contain library/Set Builder transformation policy; lines 3440 onward mix remaining routes with dependency composition.  
**Problem:** The module is simultaneously a composition root, legacy HTTP controller, cache owner, worker host, classification layer, and service factory.  
**Impact:** Changes to unrelated features collide in one file; isolated startup tests require patching module globals; import has filesystem/database and recovery side effects; service initialization order is implicit.  
**Recommendation:** Incrementally extract remaining feature routes and their application services. Introduce an `ApplicationContainer` (plain dataclass is sufficient) created by `create_app(settings/paths)` and passed to routers. Keep a temporary compatibility facade for tests and `web_app.py`.  
**Dependencies:** characterization of current endpoint contracts and startup behavior.  
**Estimated effort:** XL  
**Regression risk:** High  
**Validation:** endpoint contract tests, import-with-temporary-path test, startup/restart tests, route inventory comparison, full stability gate.

### ARCH-002 — Track processing is concentrated in one long transaction script

**Status:** Confirmed  
**Category:** Code Smell / Backend  
**Severity:** High  
**Affected files:** `audioextender/processing/track_processor.py`  
**Evidence:** `TrackProcessor.process` spans lines 213–874 (662 lines) with approximately 75 branch/control-flow nodes. It loads/caches analysis, runs stems, chooses and validates candidates, constructs audio, exports artifacts, calculates output timing, and assembles `FileResult`.  
**Problem:** One method coordinates several already-separable stages while retaining extensive intermediate mutable state.  
**Impact:** A change to one stage risks the whole pipeline; failure behavior and resource cleanup are difficult to reason about; focused tests cannot exercise stage boundaries without running or mocking much of the method.  
**Recommendation:** Preserve algorithms and extract typed stage-result helpers for analysis, candidate selection, render construction, and result assembly. Keep `TrackProcessor.process` as the transaction/orchestration boundary.  
**Dependencies:** golden/characterization results for representative configurations.  
**Estimated effort:** L  
**Regression risk:** High  
**Validation:** byte/metadata-equivalence fixtures where stable, existing synthetic integration test, failure injection at each stage, unchanged public method contract.

### ARCH-003 — Shared musical classification is duplicated across backend and browser

**Status:** Confirmed  
**Category:** Duplication / Architecture  
**Severity:** High  
**Affected files:** `audioextender/web/application.py`, `web/dj-library.js`, `audioextender/set_builder/transition_optimizer.py`, `web/set-builder.js`  
**Evidence:** Python `_library_roles` and `_library_energy` at `application.py:3100–3144` mirror `libraryRoles` and `songEnergy` at `dj-library.js:26–79`, including thresholds such as BPM 122, key confidence .65, instrumentalness .72, and tempo drift .08. Camelot tables exist at `application.py:3227–3252` and `dj-library.js:11–14`. Browser `compatibility` assigns 45/35/10/10 weights, while backend `transition_cost` uses BPM/key/vocal/energy penalties for planning.  
**Problem:** Normalization/classification rules are duplicated. Transition formulas also differ, but those differences partly serve distinct UI-shortlist and optimization purposes.  
**Impact:** A threshold or mapping can change in one surface but not another; manually corrected values may be represented differently; users can see scores that do not explain planner choices.  
**Recommendation:** First define an authoritative, versioned musical profile payload produced by Python (normalized key/Camelot, energy, vocals, timing, roles, provenance). Make the browser render that payload. Document intentionally distinct `library_match_score` and `set_transition_cost` policies, sharing only primitives. Do not alter weights during extraction.  
**Dependencies:** cross-language golden fixtures and explicit policy naming.  
**Estimated effort:** L  
**Regression risk:** High  
**Validation:** identical profiles for golden tracks before/after; frontend fixtures consume serialized backend payloads; existing planning quality baselines remain unchanged.

### ARCH-004 — Background operations have fragmented lifecycle contracts

**Status:** Confirmed  
**Category:** Architecture / Backend  
**Severity:** High  
**Affected files:** `audioextender/infrastructure/background_tasks.py`, `audioextender/infrastructure/batch_operations.py`, `audioextender/processing/web_jobs.py`, `audioextender/set_builder/planning_jobs.py`, `audioextender/imports/service.py`, `audioextender/library/relocation.py`, `audioextender/web/application.py`  
**Evidence:** `BackgroundTaskRegistry`, `BatchOperationRegistry`, `WebJobService`, `SetPlanningJobService`, `ImportService`, and `LibraryRelocationCoordinator` independently implement states, locks/events, cancellation, retry/recovery, and error payloads. `application.py:190–203` also owns several raw batch dictionaries and locks. Durability varies from SQLite to JSON to memory.  
**Problem:** Similar lifecycle concepts have incompatible field names (`updated_at`/`updatedAt`), persistence, terminal states, retry rules, and receipts.  
**Impact:** UI polling and operational feedback need feature-specific handling; restart semantics are easy to misstate; new batch features repeat concurrency code.  
**Recommendation:** Specify a small shared lifecycle vocabulary and immutable status DTO first. Reuse cancellation/progress/receipt primitives where semantics match, but retain distinct executors and durable stores for audio jobs, imports, relocation, and AI planning.  
**Dependencies:** lifecycle matrix and restart characterization tests.  
**Estimated effort:** L  
**Regression risk:** High  
**Validation:** contract tests applied to each implementation; cancellation and restart tests; no endpoint payload changes without adapters.

### ARCH-005 — Repository compatibility facade and catalog mixin are too broad

**Status:** Confirmed  
**Category:** Persistence / Architecture  
**Severity:** Medium  
**Affected files:** `audioextender/repositories/facade.py`, `audioextender/repositories/track_catalog.py`  
**Evidence:** `JobRepository` inherits five capability mixins and exposes job, system-state, feedback, analysis, and catalog operations. `_initialize` is 342 lines and creates/evolves all tables. `TrackCatalogRepositoryMixin` is 1,301 lines and owns vocabulary, descriptors, identities, duplicates, paging, quality, failures, relocation, metadata, and deletion.  
**Problem:** Callers depend on a single concrete object with a very broad surface; transaction ownership across capabilities is implicit.  
**Impact:** Tests and services receive more authority than needed; schema evolution is hard to review; changes in one catalog concern increase conflict and regression scope.  
**Recommendation:** Preserve `JobRepository` as a compatibility/composition facade, but inject narrow capability protocols into new services and split schema initialization into ordered, idempotent migration units. Split the catalog mixin by cohesive capability only when touched. Avoid a schema change during this structural work.  
**Dependencies:** repository capability inventory and database compatibility fixtures.  
**Estimated effort:** L  
**Regression risk:** High  
**Validation:** open existing database copies, compare schema/data, exercise backup/restore and all repository tests.

### ARCH-006 — Route modules still contain substantial application workflows

**Status:** Confirmed  
**Category:** Backend / Code Smell  
**Severity:** Medium  
**Affected files:** `audioextender/web/settings_routes.py`, `audioextender/web/descriptor_routes.py`, `audioextender/web/library_maintenance_routes.py`, `audioextender/web/application.py`  
**Evidence:** `create_settings_router` spans 316 lines; `cleanup_application` directly deletes catalog/files at lines 685–730; `create_descriptor_router` spans 245 lines; `run_integrity_scan` is 141 lines; remaining `application.py` routes `downloaded_library`, `reprocess_job`, and `create_jobs` are 130+ lines.  
**Problem:** HTTP translation, filesystem mutation, batch orchestration, and business policy coexist in route factories/handlers.  
**Impact:** Workflows are harder to call outside HTTP, error mapping is repeated, and unit tests drift toward full application setup.  
**Recommendation:** Move workflows into focused services returning typed/domain results; keep route handlers responsible for validation, status-code mapping, and serialization. Do not split trivial handlers.  
**Dependencies:** ARCH-001 container and response characterization.  
**Estimated effort:** L  
**Regression risk:** Medium  
**Validation:** service unit tests plus unchanged API contract tests.

### ARCH-007 — Frontend composition still carries feature implementation and broad callback wiring

**Status:** Confirmed  
**Category:** Frontend / Architecture  
**Severity:** Medium  
**Affected files:** `web/app.js`, `web/dj-library.js`, `web/music-files.js`, `web/settings.js`  
**Evidence:** `app.js` is 1,878 lines and is only 22 lines below its enforced ceiling. It imports nearly all shared/feature exports and passes large callback/object argument lists into feature factories. `dj-library.js` is 595 lines, `music-files.js` 673, and `settings.js` 326; each combines API calls, DOM strings, event binding, state mutation, and orchestration.  
**Remediation update (2026-10-19):** ARCH-007B reduced `app.js` to durable composition. ARCH-007C moved DJ Library card/sidebar rendering, filters, selection/mutations, and intelligence rendering into focused modules while keeping `dj-library.js` as the catalog coordinator and compatibility facade. Ratcheted ownership ceilings and behavioral tests prevent those responsibilities from returning to the facade.
**Problem:** Feature modules exist, but their contracts expose too much of the composition root and mix concerns internally.  
**Impact:** Small UI changes require understanding many callbacks and mutable stores; feature tests rely on source-string assertions because controllers and renderers are not independently callable.  
**Recommendation:** Introduce a small shared API client/error adapter and per-feature controller objects. Extract pure render/view-model functions when doing so unlocks behavior tests. Keep vanilla JS and avoid file splitting by line count alone.  
**Dependencies:** inventory of feature factory dependencies and browser behavior baselines.  
**Estimated effort:** L  
**Regression risk:** Medium  
**Validation:** DOM-level feature tests, request race tests, accessibility smoke tests, existing module tests.

### ARCH-008 — Set Builder browser module owns too many change axes

**Status:** Resolved by ARCH-008A, ARCH-008C, and ARCH-008D (2026-10-19)
**Category:** Frontend / Code Smell  
**Severity:** High  
**Affected files:** `web/set-builder.js`, `web/set-planning-client.js`  
**Evidence:** Before the extraction, `set-builder.js` owned mutable plan/history/review state, offline interpretation, deterministic generation, remote AI planning, rendering, transition audition, alternatives, identity editing, preference/review submission, local persistence, and exports in one closure.
**Problem:** Independent Set Builder capabilities cannot be changed or tested without the entire feature closure.  
**Impact:** This is a frequent-change area with high regression potential; async generation, rendering, and editing share state and nonce logic; unit tests largely assert source text.  
**Recommendation:** Keep one feature entry point but extract a plan-state store, API adapter, deterministic/classic planner, editor commands, and pure render/view-model helpers. Backend remains authoritative for AI-planned proposals and validation.  
**Dependencies:** ARCH-003 musical profile contract and characterization of all current Set Builder modes.  
**Estimated effort:** L  
**Regression risk:** High  
**Validation:** reducer/command tests, DOM workflow tests, save/load compatibility fixtures, live fallback tests.

**Resolution:** The feature entry now coordinates explicit state, API, command,
workflow, deterministic-planning, transition-editor, plan-view, and saved-set
owners. `set-builder-planning-session.js` owns asynchronous AI/deterministic
planning, cancellation, safe fallback, proposal switching, observability, and
planning receipts. `set-builder-feedback.js` owns learned preferences,
calibration, personalization, and receipt-backed review submission.
`set-builder-transition-editor.js` owns transition health, cue
optimization, preview playback, and editor cleanup;
`set-builder-plan-view.js` owns plan rendering and interactive track edits; and
`set-builder-saved-sets.js` owns durable loading, browser recovery, persistence,
and CSV/M3U8 serialization. Behavioral tests exercise health/runtime policy,
rule rendering, durable/cache loading, saving, and export formats. Architecture
ceilings prevent these responsibilities from collapsing back into the
coordinator.

### ARCH-009 — Saved-set ownership is split between browser and durable backend artifacts

**Status:** Resolved by ARCH-009A (2026-10-15)
**Category:** Persistence / Frontend  
**Severity:** Medium  
**Affected files:** `web/set-builder.js`, `audioextender/set_builder/planning_store.py`, `audioextender/web/set_builder_routes.py`  
**Evidence:** `set-builder.js:614–670` stores the set record, brief, receipt, track IDs, transitions, and locks in `localStorage`; saving separately writes an M3U8 through the backend. Planning job state is stored independently in JSON.  
**Problem:** A “saved set” is partly browser-local and partly a filesystem artifact; the durable planning receipt is copied into browser storage rather than owned by one backend record.  
**Impact:** Browser data clearing or using another browser loses editable plans while the playlist remains; backup/restore cannot fully guarantee saved-set compatibility; partial save is a normal state.  
**Recommendation:** Define the saved-set aggregate and durability contract. Add a backend store only after compatibility/export/import tests exist; retain localStorage migration and offline recovery.  
**Dependencies:** product decision on editable-set durability and backup scope.  
**Estimated effort:** L  
**Regression risk:** High  
**Validation:** migrate version-1 local records, restart/browser-clear tests, backup/restore, M3U8 compatibility.

**Resolution:** Editable saved sets are now versioned backend aggregates in the
SQLite database. Existing browser records migrate without overwriting newer
server data, localStorage is a recovery cache, and M3U8 remains a separately
reported export artifact. Restart, browser-clear, migration, and database
backup/restore behavior are covered by deterministic and browser tests.

### ARCH-010 — Error handling and API failure contracts are inconsistent

**Status:** Confirmed  
**Category:** Backend / Frontend  
**Severity:** Medium  
**Affected files:** `audioextender/web/application.py`, `audioextender/infrastructure/batch_operations.py`, `audioextender/imports/`, `web/settings.js`, `web/set-builder.js`, `web/reporting.js`  
**Evidence:** at least 24 broad `except Exception` sites exist across Python, some appropriate at job boundaries and some suppressing details; browser modules alternately use `apiErrorMessage`, raw `payload.detail`, fixed strings, or empty `catch {}` (for example settings background refreshes).  
**Problem:** Expected domain failures, unavailable resources, cancellation, and unexpected defects do not share a stable error vocabulary.  
**Impact:** Users see ambiguous messages; logs may lack causal context; clients need endpoint-specific parsing; silent refresh failures hide regressions.  
**Recommendation:** Inventory exception sites, keep broad catches only at process/job boundaries with structured logging, define a backward-compatible API error envelope, and centralize browser parsing.  
**Dependencies:** endpoint error contract inventory.  
**Estimated effort:** M  
**Regression risk:** Medium  
**Validation:** failure-path contract tests and log-capture tests; unchanged successful responses.

### ARCH-011 — Frontend tests contain brittle source assertions and duplicated cases

**Status:** Confirmed  
**Category:** Testing / Frontend  
**Severity:** Medium  
**Affected files:** `tests/javascript/frontend_modules.test.js`, `tests/unit/web/test_frontend_contracts.py`
**Evidence:** tests inspect source with regex/string matching for implementation details; the exact Set Builder allocation/intention/identity test group is repeated multiple times around lines 142–245 and 247–329. Python frontend contracts also read JS/CSS as text.  
**Problem:** Some tests verify that text exists rather than that user-visible behavior works, and duplicated cases add noise without coverage.  
**Impact:** Safe refactors fail tests while broken runtime wiring can pass; maintenance cost obscures meaningful regression coverage.  
**Recommendation:** Preserve a few architecture/source guards, remove duplicate cases during an approved test-only change, and move feature behavior to DOM/controller tests using existing Node tooling before frontend refactors.  
**Dependencies:** extract testable controllers/renderers under ARCH-007/008; no new framework required initially.  
**Estimated effort:** M  
**Regression risk:** Low  
**Validation:** mutation-oriented checks (break handler/state update and prove tests fail), same scenario coverage, faster or equal runtime.

### ARCH-012 — Quality enforcement has gaps and the checked-out baseline is not lint-clean

**Status:** Confirmed  
**Category:** Developer Experience / Testing  
**Severity:** Medium  
**Affected files:** `audioextender/web/application.py`, `pyproject.toml`, `package.json`, repository root  
**Evidence:** Ruff reports a duplicated `IntentionPlanner` import and import-order violation. MyPy and tests pass. No checked-in CI workflow or pre-commit configuration was found. Existing architecture ceilings cover selected extracted modules and `app.js`, but not `application.py`, `track_processor.py`, repository capability boundaries, SQL placement, or dependency cycles.  
**Problem:** The documented local gate is not consistently green and architectural checks do not protect today’s largest risks.  
**Impact:** Contributors and agents lack one authoritative pass/fail command; coupling and duplicate policy can regress unnoticed.  
**Recommendation:** First restore a clean baseline in a separate approved change. Add a repository quality script/CI workflow using existing tools, plus focused boundary checks that ratchet current architecture rather than impose arbitrary universal limits.  
**Dependencies:** baseline decision and CI environment selection.  
**Estimated effort:** M  
**Regression risk:** Low  
**Validation:** clean checkout runs the same gate locally and in CI; intentional violations produce clear failures.

### ARCH-013 — Stylesheet ownership may become a frontend bottleneck

**Status:** Resolved
**Category:** Frontend  
**Severity:** Low  
**Affected files:** `web/styles.css`  
**Evidence:** the completed [`css-ownership-audit.md`](css-ownership-audit.md) found 656 class selectors, 68 media-query blocks across 15 conditions, 17 static-reference removal candidates, and substantial feature-owned selector groups interleaved with shared rules. Browser coverage now measures desktop, compact, and narrow layouts, keyboard focus, reduced motion, and WCAG A/AA findings.
**Problem:** Accessibility primitives are present and working, but feature ownership and responsive overrides are distributed through one cascade, making safe removal and isolated feature changes unnecessarily difficult.
**Impact:** Confirmed dead-rule risk and avoidable cascade regression risk; no current critical responsive or accessibility failure was found.
**Resolution:** ARCH-013B split the stylesheet behind one ordered entry point into numbered shell, shared-component, processing, Library/reporting, Settings, Music Files, and Set Builder fragments. The original cascade order is preserved, placement rules are documented beside the styles, confirmed dead selectors were removed, and structural plus browser tests protect import order and computed behavior.
**Dependencies:** viewport screenshots and selector usage report.  
**Estimated effort:** S investigation; M if confirmed  
**Regression risk:** Medium  
**Validation:** visual comparisons at supported viewports and reduced-motion/keyboard checks.

### ARCH-014 — Manual musical corrections may not flow through every derived cache

**Status:** Suspected / Needs Investigation  
**Category:** Architecture / Musical Analysis  
**Severity:** Medium  
**Affected files:** `audioextender/web/application.py`, `audioextender/repositories/library_analysis.py`, `audioextender/repositories/track_catalog.py`, `audioextender/set_builder/candidate_retriever.py`  
**Evidence:** manual descriptors and key verifications are persisted, while `library_search_index` stores denormalized `camelot`, `energy`, roles, and `set_analysis_json`. Multiple refresh paths rebuild parts of this index. The audit did not trace every correction through every cache/restart path.  
**Problem:** A stale derived profile could cause Library and Set Builder behavior to disagree with a manual correction.  
**Impact:** User authority would be violated and planning could use stale evidence.  
**Recommendation:** Build a correction-propagation matrix and tests before changing cache design; only then consolidate invalidation/versioning if gaps are proven.  
**Dependencies:** representative corrections and restart fixtures.  
**Estimated effort:** M investigation  
**Regression risk:** Medium  
**Validation:** correct BPM/key/genre/identity, refresh, restart, and assert every consumer sees authoritative values.

### ARCH-015 — Production-scale concurrency behavior needs measurement

**Status:** Measured / No correctness failure observed
**Category:** Performance / Persistence  
**Severity:** Medium  
**Affected files:** `audioextender/repositories/base.py`, `audioextender/repositories/facade.py`, background services  
**Evidence:** repository calls open SQLite connections with a process lock and 30-second timeout; several daemon threads can perform catalog/filesystem work. Unit and synthetic tests pass, but the audit did not stress concurrent imports, analysis, metadata batches, planning, relocation, and backup on a real catalog.  
**Problem:** Contention, stale reads, or long lock waits may exist only under realistic concurrency.  
**Impact:** Local UI stalls or partial operational failures on resource-constrained Macs.  
**Recommendation:** Add an opt-in synthetic concurrency/stress harness and measure before redesigning connection or queue ownership.  
**Dependencies:** disposable large catalog fixture and explicit safety limits.  
**Estimated effort:** M investigation  
**Regression risk:** Low  
**Validation:** repeatable latency/error report; no user library access.

**Follow-up measurement (2026-10-15):**
`scripts/measure_repository_concurrency.py` now creates an isolated temporary
catalog and exercises bounded concurrent job writes, catalog/descriptor writes,
system-state writes, and catalog reads. A 25-round run with six workers completed
100 operations with zero errors, zero SQLite lock failures, zero stale committed
reads, and correct final counts. A small number of overlapping catalog reads
exceeded the conservative 100 ms observation threshold across repeated runs;
these are retained as latency evidence, not classified as correctness failures. No repository
redesign is currently justified; rerun the harness on target Macs as catalog and
workload sizes grow.

## 7. Backend Findings

Backend package boundaries are mostly sensible. Domain modules do not import FastAPI, SQL remains behind repositories, and external tools are generally injected or wrapped. The main backend work is finishing the separation already underway:

1. reduce `application.py` to path/config creation, dependency composition, router registration, middleware, and startup/shutdown hooks;
2. turn long route workflows into application services without adding a generic service layer everywhere;
3. decompose `TrackProcessor.process` by pipeline stages while keeping one public transaction boundary;
4. replace broad repository injection with capability-specific dependencies in new/extracted services;
5. standardize expected error/result contracts at HTTP and background boundaries.

Direct filesystem access in `audio`, `library`, `imports`, and `processing` is usually legitimate because files are their domain resource. The problematic access is filesystem mutation embedded in delivery handlers. Configuration is partly centralized in `settings.py`/`core.config`, but web defaults, persisted overrides, and path constants are assembled in `application.py`; moving that assembly into an explicit runtime configuration object would make tests and alternate roots safer.

## 8. Frontend Findings

The earlier feature extraction is valuable and should not be reversed. `request-state-controller.js`, `playback.js`, and `shared-components.js` solve genuine cross-feature concerns. Remaining work should improve feature-internal cohesion rather than create dozens of small files.

A practical frontend boundary is:

- feature entry: bind navigation and feature lifetime;
- controller/store: own state transitions and async coordination;
- API adapter: serialize requests and normalize errors;
- view model/render helpers: pure transformations where practical;
- components: only truly repeated controls/dialogs/playback.

Set Builder now follows this boundary through dedicated transition-editor,
plan-view, and saved-set controllers while retaining one feature coordinator.
`app.js` should continue to be ratcheted downward as responsibilities leave;
raising its ceiling would conceal regression. `styles.css` requires
investigation, not an automatic split. A framework migration is not justified:
current complexity comes from responsibility boundaries, not an inability of
vanilla JavaScript to express the UI.

## 9. Musical Analysis Findings

### Authoritative implementations today

- BPM/key/beat-grid/structure analysis: `audioextender/analysis/key_detection.py`
- section/candidate ranking: `audioextender/analysis/section_selector.py` and related selection services
- splice/transition assessment: `audioextender/analysis/transition_scorer.py`
- analysis caching: `audioextender/infrastructure/cache.py`
- Set Builder transition optimization: `audioextender/set_builder/transition_optimizer.py`
- manual catalog corrections/descriptors: repositories plus descriptor/settings routes

### Confirmed duplication and inconsistency

- key normalization/Camelot display tables exist in Python and JavaScript;
- energy, role, vocals, and timing profiles are derived on both sides;
- Library compatibility and Set Builder transition cost use different formula shapes and labels;
- untyped dictionaries carry musical profiles through routes, caches, repositories, and planning.

The UI shortlist score and optimizer cost need not become one algorithm: they answer different questions. They should use the same normalized inputs and clearly named/versioned policies. The target is an immutable `MusicalProfile`/serialized schema with value, confidence, provenance, and analysis version for shared facts; contextual scorers consume that profile independently. Structural extraction must freeze current outputs before any musical improvement.

## 10. Set Builder Findings

The Set Builder backend is the strongest-separated feature. Intention, journey, retrieval, AI planning, deterministic planning, validation, repair, comparison, evaluation, optimization, preference learning, review, storage, observability, and release gates are separate modules. AI providers are replaceable; candidates and hard constraints remain authoritative; deterministic fallback is explicit; preference learning cannot bypass validation; receipts retain model/baseline evidence.

The main Set Builder risks are browser orchestration (ARCH-008), shared musical-profile duplication (ARCH-003), and saved-set ownership (ARCH-009). Backend `TrackPlanner.plan` is 189 lines and remains a moderate orchestration hotspot, but its collaborators are already separated; it should only be simplified after the higher-value browser and shared-policy work. Do not collapse validation, comparison, review, or release gates simply to reduce module count—their separation protects correctness.

## 11. Persistence Findings

SQLite is suitable and repository encapsulation is real. The facade remains useful for compatibility and multi-capability transactions, especially duplicate merging and relocation. It should not be deleted. The improvement is to narrow what each consumer receives and make transaction ownership explicit.

Schema creation/evolution is currently centralized in the 342-line `_initialize`. It works and tests pass, but a versioned sequence of idempotent migrations would make compatibility auditable. This can initially reorganize code without changing schema. Any future saved-set persistence must preserve localStorage records, planning receipts, preferences, feedback, recording identities, jobs, and backup format.

## 12. Background Job Findings

Different jobs legitimately require different executors: audio processing is queued and persistent; AI planning is cancellable and supersedable; metadata batches are item-oriented; relocation has rollback; imports coordinate network/download/file operations. One universal job engine would overfit these differences.

Shared concepts should be standardized instead: identifiers, states, progress, cancellation request, timestamps, retry linkage, error items, operation receipt, durability, and restart disposition. A conformance test suite can apply to each implementation while feature-specific fields and stores remain. Raw in-memory registries in `application.py` should migrate first to the existing batch/registry primitives or receive explicit justification.

## 13. Testing and Tooling Findings

The Python suite is broad and quick (288 tests in about nine seconds during this audit). Set Builder has strong synthetic, provider-failure, repair, evaluation, preference, review, and release-gate coverage. The stability script is a valuable end-to-end persistence gate. MyPy covers 143 files with `check_untyped_defs`; Ruff has sensible rules.

Gaps:

- frontend tests are only 44 Node tests and many inspect source text rather than runtime DOM behavior;
- duplicated JavaScript test cases should be removed in a test-only cleanup;
- no checked-in CI/pre-commit configuration was found;
- architecture rules do not yet detect cycles, SQL leakage, domain-to-web imports, or duplicated musical policy;
- the current Ruff baseline is red;
- no real-browser accessibility/viewport regression gate was found;
- concurrency and real-library evaluations are opt-in/manual rather than normal PR gates, which is reasonable but should be documented as release gates.

Coverage percentage alone should not become the goal. Protect risky behavior and boundaries, and retain fast local feedback.

## 14. Recommended Target Architecture

Retain a modular monolith with explicit feature composition:

```text
audioextender/
  core/                         # stable configuration, models, errors, operation contracts
  analysis/                     # authoritative audio/musical facts and selection algorithms
    musical_profile.py          # proposed normalized/versioned shared facts
  audio/                        # media loading, stems, WAV I/O
  processing/                   # processing use cases and pipeline orchestration
    stages/                     # only cohesive extracted stages from TrackProcessor
  library/                      # catalog/metadata/identity/backup/relocation services
  imports/                      # import use cases and providers
  set_builder/                  # existing planning/review/evaluation modules
  reporting/
  repositories/
    migrations/                 # ordered schema initialization, no initial schema change
    capabilities/               # optional narrow protocols, not duplicate implementations
  infrastructure/              # cache, lifecycle primitives, provider/media adapters
  web/
    application.py              # small create_app/container/router composition
    routes/                     # eventual feature route grouping; preserve public URLs
    schemas/                    # only shared HTTP contracts that justify reuse

web/
  core/                         # navigation/bootstrap/request/error client
  shared/                       # reusable dialogs, playback, pagination, formatting
  features/
    music-files/
    dj-library/
    set-builder/
      index.js                  # feature entry
      controller.js             # async/state coordination
      state.js                  # plan/edit state and commands
      api.js                    # HTTP adapter
      classic-planner.js        # deterministic browser fallback, if retained
      views.js                  # pure view models/render helpers
    settings/
    reporting/
```

This is a migration destination, not a required one-shot move. Existing files should remain until a focused extraction has behavior tests and a clear owner. `analysis`, `audio`, `set_builder`, SQLite repositories, and current endpoint URLs should remain. Eventually removable items are compatibility re-exports, legacy routes, duplicate browser musical derivation, and obsolete local state adapters—but only after callers and stored data have migrated.

## 15. Prioritized Refactoring Opportunities

### Quick wins

1. Restore the Ruff-clean baseline and add one authoritative quality command (ARCH-012).
2. Add dependency-cycle, SQL-boundary, and domain-to-web import checks using the standard library (ARCH-012).
3. Remove duplicate frontend test cases and replace the most brittle source assertions with behavior checks (ARCH-011).
4. Document a job lifecycle matrix and musical-policy ownership before code movement (ARCH-003/004).

### Highest-value larger work

1. Characterize and extract `application.py` legacy responsibilities (ARCH-001/006).
2. Create authoritative serialized musical profiles without changing algorithms (ARCH-003/014).
3. Decompose Set Builder browser state/API/render concerns (ARCH-008).
4. Decompose `TrackProcessor.process` into tested stages (ARCH-002).
5. Narrow repository capabilities and migrations while keeping the facade (ARCH-005).

## 16. Migration Risks and Compatibility

| Risk | Protection |
|---|---|
| endpoint or payload drift | snapshot/contract tests and compatibility adapters |
| musical output drift | golden profiles, candidate/ranking fixtures, no weight changes during extraction |
| existing SQLite/backup incompatibility | copy real-shaped databases, open/restore with old and new code, no structural schema change in first pass |
| lost saved sets | versioned localStorage migration and export/import fixtures before backend ownership changes |
| job restart/cancel regression | shared conformance tests plus feature-specific recovery tests |
| import-time path/database changes | temporary-root startup tests and explicit container creation |
| frontend race/focus/accessibility regressions | DOM/browser workflow tests, stale-response tests, keyboard/focus checks |
| resource pressure on Macs | bounded fixtures, retain current worker limits, opt-in stress tests |

Every refactor should be independently reviewable and avoid simultaneous algorithm, schema, and UI changes. Preserve CLI behavior, URLs, files, identifiers, receipts, preferences, feedback, jobs, exports, and backups.

## 17. Testing and Verification Strategy

1. Record the current route inventory, response shapes, settings defaults, schema, and serialized musical profiles.
2. Add characterization tests at the boundary being changed, including failures and restart behavior.
3. Extract behind the existing function/class/endpoint; retain a compatibility adapter.
4. Run focused unit tests while iterating.
5. Run Ruff, MyPy, all Python tests, and `npm run check` for every change.
6. Run `scripts/run_stability_gate.sh` for persistence/import/relocation/Set Builder export changes.
7. For musical-policy work, compare golden analysis/profile/planning results and the checked-in evaluation harness.
8. For frontend work, test save/refresh/restart, overlapping search, reconnect, import path safety, and single-preview behavior.
9. For release candidates, run opt-in live Ollama and disposable catalog-scale/concurrency evaluations.
10. Validate rollback by opening a pre-change database/backup and by retaining old serialized-data readers for at least one compatibility cycle.

## 18. Phased Implementation Plan

### Phase 0 — Baseline and Architecture Audit

Freeze route/schema/profile/job contracts; restore the clean quality baseline; document the dependency rules and lifecycle/policy matrices. These are prerequisites for structural work.

### Phase 1 — Code Quality and Technical Debt

Remove confirmed test duplication, classify broad exceptions, add shared error parsing, and characterize long orchestration methods. Do not yet move algorithms.

### Phase 2 — Backend Architecture and Shared Services

Extract `application.py` features incrementally; introduce explicit runtime composition; create shared musical-profile primitives; decompose processing stages; narrow repository dependencies; standardize job lifecycle contracts.

### Phase 3 — Frontend Architecture

Create shared API/error adapters; decompose Set Builder state/API/rendering; reduce `app.js` wiring; investigate CSS ownership; decide and implement saved-set durability only with migrations.

### Phase 4 — Testing and Architecture Enforcement

Add dependency/SQL/domain boundary checks, lifecycle conformance tests, musical golden fixtures, DOM workflows, and optional stress/accessibility gates.

### Phase 5 — Documentation and Developer Experience

Update architecture/repository maps, add contribution placement guides and decision records, document release gates and compatibility windows.

### Phase 6 — Final Regression and Stability Verification

Run all local gates, stability workflows, catalog-scale evaluation, live provider acceptance, backup/restore, rollback rehearsal, and manual core DJ workflows. Compare metrics to the Phase 0 baseline.

Each phase should be delivered as focused pull requests: characterization first, one boundary extraction second, cleanup/guard third.

## 19. Decision status and remaining questions

The compatibility questions about saved-set durability, musical authority,
operation contracts, schema migration, and the project's application shape are
resolved in the [`docs/decisions/`](decisions/README.md) records. Classic
planning remains available through deterministic backend fallback when Ollama
is unavailable; the local model is an optional planner, not an availability
dependency.

The remaining release-capacity questions are empirical rather than architecture
decisions:

1. What catalog size and concurrent workload represent the supported upper
   bound on target Macs?
2. Which additional browsers and viewports, beyond the current Chromium smoke
   matrix, are release requirements?

## 20. Conclusion

DJ Library Studio does not need a new architecture. It needs completion and enforcement of the architecture it has already begun: explicit composition, focused application services, authoritative musical facts, narrow persistence capabilities, consistent operation contracts, and testable frontend state. The work should start with baselines and characterization, then remove one source of coupling at a time. No refactoring described here has been started by this audit.
