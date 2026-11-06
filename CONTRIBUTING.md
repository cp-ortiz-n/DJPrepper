# Contributing to DJPrepper

DJPrepper is a modular monolith with a Python/FastAPI backend and a
vanilla JavaScript frontend. Keep changes within the ownership boundaries in
[`docs/architecture/architecture.md`](docs/architecture/architecture.md); use
[`docs/architecture/repository-map.md`](docs/architecture/repository-map.md) to find the owning module and
its tests.

## Set up the development environment

The supported toolchain is Python 3.12 and Node.js 22.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

Install the pinned Chromium build only when you need the browser gate:

```sh
npm run check:browser:install
```

## Make a focused change

- Put Python behavior in the domain package that owns it under
  `audioextender/`; keep reusable workflows out of FastAPI route handlers.
- Keep SQL inside `audioextender/persistence/` or an approved migration
  boundary.
- Put browser behavior in the owning feature under `frontend/features/`; keep
  `frontend/app.js` focused on composition and navigation. Follow
  [`docs/architecture/code-organization.md`](docs/architecture/code-organization.md) for backend,
  frontend, persistence, style, and test placement.
- Preserve public APIs, persisted data, jobs, saved sets, exports, and backup
  compatibility unless the change explicitly migrates them.
- Add characterization tests before risky refactors and behavior tests for new
  behavior or bug fixes.

Python unit tests use `unittest` and mirror the application packages under
`tests/unit/`. Cross-package, persistence, filesystem, and live-provider tests
live under `tests/integration/`. JavaScript unit tests use Node's test runner in
`tests/javascript/`; Playwright workflows live in `tests/browser/`.

The application itself intentionally remains a root package. Moving it to a
`src/` layout still requires a dedicated migration of launchers, imports,
coverage, CI, and packaging—not a partial file move.

Shared test builders belong in `tests/factories.py`; checked-in scenario data
belongs in `tests/fixtures/`. Do not use application source modules as a home
for test helpers.

## Run verification

The repository scripts are authoritative; the Make targets are concise aliases.

```sh
make quality       # lint, format ratchets, types, Python tests, and JS tests
make stability     # persistence/import/relocation/export/Set Builder checks
make browser       # real-browser workflows and accessibility
make coverage      # Python and JavaScript coverage reports
```

Run focused tests while developing:

```sh
.venv/bin/python -m unittest tests.unit.analysis.test_key_analysis
node --test tests/javascript/core/api_client.test.js
```

Before submitting a normal change, run `make quality` and `git diff --check`.
Add the stability, browser, or coverage gate when the affected behavior calls
for it. CI runs the quality, stability, dependency, and browser gates on pushes
and pull requests.

## Documentation and generated files

Update `docs/` when ownership, compatibility, or an operator workflow changes.
Record planned work in `BACKLOG.md`. Generated coverage, runtime cache, audio,
dependency, and Graphify outputs are not maintained source and must remain
ignored unless a specific artifact is intentionally accepted as documentation.

Preview safe generated-artifact cleanup with `make clean`. Use
`make clean-apply` after reviewing the list. The regenerable runtime analysis
cache is deliberately excluded unless `make clean-analysis-cache` is requested.

