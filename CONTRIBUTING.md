# Contributing to DJ Library Studio

DJ Library Studio is a modular monolith with a Python/FastAPI backend and a
vanilla JavaScript frontend. Keep changes within the ownership boundaries in
[`docs/architecture.md`](docs/architecture.md); use
[`docs/repository-map.md`](docs/repository-map.md) to find the owning module and
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
- Keep SQL inside `audioextender/repositories/` or an approved migration
  boundary.
- Put browser behavior in the owning feature module under `web/`; keep
  `web/app.js` focused on composition and navigation.
- Preserve public APIs, persisted data, jobs, saved sets, exports, and backup
  compatibility unless the change explicitly migrates them.
- Add characterization tests before risky refactors and behavior tests for new
  behavior or bug fixes.

Python tests use `unittest` and live in `tests/test_*.py`. JavaScript unit tests
use Node's test runner and live in `tests/*.test.js`. Playwright workflows live
in `tests/browser/`. This established layout is intentionally retained: moving
to a `src/` package or nested test tree would require a dedicated migration of
launchers, import paths, discovery, coverage, CI, and packaging—not a partial
file move.

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
.venv/bin/python -m unittest tests.test_module
node --test tests/feature.test.js
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

