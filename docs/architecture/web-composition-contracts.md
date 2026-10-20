# Web composition compatibility contracts

This document records the externally visible and startup contracts that must be
preserved while `audioextender/web/application.py` is incrementally reduced to a
composition root. The executable authority is
`tests/unit/web/test_web_composition_contracts.py`.

## HTTP surface

The OpenAPI schema currently exposes **152 method/path pairs**. The canonical
sorted inventory has SHA-256
`ea143280700e65f754a37efb2a2782ab76dbafcd04513ddda844a83c3c57f3d3`.
The contract deliberately hashes methods and paths, not Python function names,
so internal extraction remains possible. An intentional API addition, removal,
or method change must update this record and the test in the same reviewed
change.

The application also serves:

- `/` from `frontend/index.html`;
- `/assets` from the project `frontend/` directory;
- `/vendor/wavesurfer` from the installed WaveSurfer distribution;
- Swagger UI at `/api/docs`, with ReDoc disabled;
- gzip responses at 1,024 bytes or larger, compression level 5.

The HTML shell and local `/assets` responses use `Cache-Control: no-store`,
including conditional responses. This prevents an older browser-cached ES
module from being linked against a newer entry module after a local restart.
The shell provides basic view switching, failed-resource diagnostics, and a
reload action until `app.js` initializes normal navigation; a failed module load
must not leave every tab unclickable.

`frontend/asset-manifest.json` is the single asset-revision authority.
`FrontendAssetService` validates the manifest and renders the shell with one
revision applied to the stylesheet, entrypoint, and a complete import map of
all JavaScript modules. Browser modules may not carry independent `?v=` import
strings. `GET /` exposes the rendered revision in both the HTML metadata and
`X-DJLS-Asset-Revision` response header. The browser release gate restarts an
isolated server from one cacheable revision to another in the same tab and
verifies that no mixed module graph is linked.

## Response contracts

- `GET /api/config` returns exactly the top-level keys `presets`,
  `preset_details`, `bar_counts`, `defaults`, `effective`, and `overrides`.
- Unknown routes return HTTP 404 with `{"detail": "Not Found"}`.
- FastAPI request validation returns HTTP 422 with a non-empty `detail` list;
  each issue includes `type`, `loc`, `msg`, and `input`.
- A disconnected configured library is a successful status response, not an
  exception. It reports its path, connection flag, catalog/availability counts,
  storage totals, audio-quality summary, and location-integrity summary.
- Existing settings behavior tests prove settings survive save, refresh, and a
  fresh `JobRepository` created against the same database.

## Startup and paths

Runtime roots are derived from the checkout containing `web_app.py`:

- input: `<project>/workspace/input`;
- output: `<project>/workspace/output`;
- database: `<project>/workspace/output/reports/audioextender.sqlite3`;
- browser files: `<project>/frontend`.

`ApplicationPaths` defines every mutable filesystem location. Production uses
paths derived from the checkout, while tests can create a complete path set
under a temporary root and retain the real browser-asset directory.

`ApplicationRuntime` owns the repository, processing service, relocation
coordinator, task/batch registries, locks, queues, and process-local caches.
`create_app()` accepts an explicit runtime or paths and stores the selected
runtime on `app.state.runtime`. Passing both is rejected.

Importing `audioextender.web.application` leaves the compatibility `app` proxy
unresolved: it does not construct the repository, registries, services, or run
recovery. Uvicorn uses `create_app` as an application factory. Interrupted-job
recovery and Set Builder provider reporting run at FastAPI startup. Tests verify
temporary-root ownership, deferred recovery, and import laziness without
accessing the user's music library.

## Safe refactoring rule

Internal modules, dependency containers, and router factories may change while
these observable contracts remain stable. If a contract must change, update the
behavior test and this document deliberately; never change the inventory hash
just to make a failing test pass.
