# Web composition compatibility contracts

This document records the externally visible and startup contracts that must be
preserved while `audioextender/web/application.py` is incrementally reduced to a
composition root. The executable authority is
`tests/test_web_composition_contracts.py`.

## HTTP surface

The OpenAPI schema currently exposes **152 method/path pairs**. The canonical
sorted inventory has SHA-256
`ea143280700e65f754a37efb2a2782ab76dbafcd04513ddda844a83c3c57f3d3`.
The contract deliberately hashes methods and paths, not Python function names,
so internal extraction remains possible. An intentional API addition, removal,
or method change must update this record and the test in the same reviewed
change.

The application also serves:

- `/` from `web/index.html`;
- `/assets` from the project `web/` directory;
- `/vendor/wavesurfer` from the installed WaveSurfer distribution;
- Swagger UI at `/api/docs`, with ReDoc disabled;
- gzip responses at 1,024 bytes or larger, compression level 5.

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

- input: `<project>/input`;
- output: `<project>/output`;
- database: `<project>/output/reports/audioextender.sqlite3`;
- browser files: `<project>/web`.

Import currently constructs the repository and services, initializes the
database schema, and recovers interrupted jobs. This import-time behavior is a
legacy constraint captured for the later `ARCH-001B` extraction, not the desired
final design. Application startup reports whether the configured Set Builder AI
provider is available. Tests isolate provider status and filesystem state; they
must never access or modify the user's music library.

## Safe refactoring rule

Internal modules, dependency containers, and router factories may change while
these observable contracts remain stable. If a contract must change, update the
behavior test and this document deliberately; never change the inventory hash
just to make a failing test pass.
