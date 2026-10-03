# AudioExtender architecture

This is the maintainer map for DJ Library Studio and the AudioExtender CLI. Use
it to decide where a manual change belongs before editing.

## Runtime entry points

| Entry point | Purpose |
| --- | --- |
| `main.py` | CLI parsing and batch execution |
| `web_app.py` | Small compatibility launcher; never add feature logic here |
| `audioextender/web/application.py` | FastAPI composition, shared service construction, dependency injection, and remaining legacy routes |
| `web/index.html` | Browser shell and workspace markup |
| `web/app.js` | Browser composition and remaining cross-feature UI behavior |

Run the app with `python3 web_app.py`.

## Package ownership

| Package | Responsibility |
| --- | --- |
| `core` | Configuration models, immutable results, interfaces, presets, exceptions |
| `audio` | Loading, quality inspection, WAV tags/artwork, stems |
| `analysis` | Key detection, musical sections, selection, scoring, validation, splice policy, readiness |
| `processing` | Track, batch, extended-edit, and web-job orchestration |
| `library` | Recording identity, backup, relocation, cues, exports, overrides |
| `imports` | YouTube, SoundCloud, local-file, playlist, and Creative Commons workflows |
| `repositories` | SQLite persistence grouped by business capability |
| `infrastructure` | Caching, progress adapters, persistent background-task state |
| `reporting` | Processing and listening-feedback reports |
| `web` | FastAPI request/response models, routers, and dependency adapters |

The normal dependency direction is:

```text
web / CLI
    ↓
processing · imports · library
    ↓
analysis · audio · core

web/services → repositories → SQLite
```

Lower layers must not import `audioextender.web.application`. Routers receive
collaborators through dependency dataclasses instead of importing application
globals.

## FastAPI ownership

| Module | Routes and behavior |
| --- | --- |
| `web/job_routes.py` | Job listing, ordering, clearing, cancel, pause, resume, removal |
| `web/job_media_routes.py` | Audio delivery, ZIP exports, waveforms, transition scoring, cue editing |
| `web/library_routes.py` | Paginated DJ Library catalog and facets |
| `web/library_maintenance_routes.py` | Catalog reconciliation, integrity scans, progress, safe repairs |
| `web/metadata_batch_routes.py` | Cancellable/retryable genre, WAV-tag, artwork, and catalog-propagation batches |
| `web/reporting_routes.py` | Track feedback and manual key verification |
| `web/set_builder_routes.py` | Set Builder catalog, preflight, playlist exports |
| `web/settings_routes.py` | Settings, storage, backup/restore, relocation, cleanup |
| `imports/routes.py` | Authorized source, local-file, and playlist import delivery |

Router factories accept explicit dependencies. Wire new dependencies in
`application.py`; never make a router import `application.py`. Repository
providers are normally lambdas so tests can replace the active repository.

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

| Module | Responsibility |
| --- | --- |
| `jobs.py` | Processing jobs, queue state, generations, recovery |
| `track_catalog.py` | Downloaded tracks, identities/families, playlists, duplicates, paths |
| `library_analysis.py` | Analysis records, search index, catalog signatures, key-analysis state |
| `feedback.py` | Candidate/track feedback and key verification |
| `system_state.py` | Web settings, durable system state, import failures/background state |
| `base.py` | Shared connection contract |

Add SQL to the mixin that owns its data, not back to `facade.py`. The database
is `output/reports/audioextender.sqlite3`. State that must survive restarts
belongs in SQLite, not module globals or browser-only storage.

## Processing pipeline

```text
track_processor.py
    → selection_coordinator.py
        → candidate_selection.py
        → candidate_reranker.py
        → candidate_validator.py
        → splice_policy.py
    → extended_edit.py
    → export_service.py / cue_export.py
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

| Module | Ownership |
| --- | --- |
| `shared-components.js` | DOM helpers, messages, formatting, pagination |
| `playback.js` | Single audio-preview owner |
| `music-files.js` | Music Files filters and request serialization |
| `dj-library.js` | DJ Library state and compatibility helpers |
| `set-builder.js` | Set Builder state and proposal policy |
| `settings.js` | Settings initialization and refresh coordination |
| `import-queue.js` | Pause/resume/cancel/retry/reorder import state |
| `styles.css` | Shared visual system and responsive behavior |

Do not create a second audio player, dropdown implementation, notification
system, or pagination helper inside a feature. Extend the shared module first.

## Where to make common changes

| Change | Start here |
| --- | --- |
| BPM, grid, key, confidence, energy | `audioextender/analysis/` |
| Intro/outro selection | `selection_coordinator.py`, `candidate_selection.py`, `candidate_validator.py` |
| Splice sound/crossfades | `splice_policy.py`, then `processing/extended_edit.py` |
| WAV tags/artwork/audio quality | `audio/wav_metadata.py`, `audio/quality.py` |
| Track IDs/related versions | `library/recording_identity.py`, `repositories/track_catalog.py` |
| Import destination/source behavior | `imports/` and its injected library-root dependency |
| Relocation/backup | `library/relocation.py`, `library/backup.py`, `web/settings_routes.py` |
| Queue behavior | `processing/web_jobs.py`, `web/job_routes.py`, `repositories/jobs.py` |
| DJ Library filtering | `web/library_routes.py`, `repositories/library_analysis.py` |
| Integrity scan/repair | `web/library_maintenance_routes.py` |
| Browser cards/filters | Corresponding `web/*.js` module plus `web/styles.css` |
| Persistent setting | `web/settings_routes.py`, `repositories/system_state.py`; `settings.py` only for shipped defaults |

## Safe manual-change workflow

1. Find the owning module above.
2. Add/update a focused test under `tests/` before changing cross-layer behavior.
3. Keep HTTP parsing in routers, domain behavior below them, and SQL in repositories.
4. Run:

   ```bash
   .venv/bin/python -m unittest discover -s tests -q
   npm run check
   .venv/bin/ruff check <changed-python-files>
   git diff --check
   ```

5. After architecture changes, refresh Graphify:

   ```bash
   graphify . --update --code-only --no-viz
   ```

`tests/test_package_structure.py` guards package/composition boundaries and
module size. `tests/frontend_modules.test.js` guards shared frontend behavior.

## Project hygiene

- Never add general-purpose source files under `helpers/`.
- Virtual environments and Python/tool caches are generated artifacts.
- `graphify-out/` is the generated architecture index used for future analysis.
- `input/`, `output/`, and `cache/` are local runtime data, not product source.
- Preserve compatibility exports when moving functions used by scripts/tests;
  remove them only through a deliberate migration.
