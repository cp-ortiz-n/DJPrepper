# Code organization

DJ Library Studio is a modular monolith. Code is organized first by the feature
or domain that owns a behavior, then by technical role only inside that owner.
This keeps related files together without creating a generic `utils`, `helpers`,
or `services` dumping ground.

## Repository shape

```text
audioextender/
  analysis/               # musical analysis and selection policy
  audio/                  # audio loading, rendering, stems, and WAV metadata
  core/                   # stable configuration, models, interfaces, and errors
  imports/                # import workflows and provider integrations
  infrastructure/         # cross-domain runtime adapters and operation primitives
  library/                # catalog, identity, metadata, export, and relocation use cases
  processing/             # processing pipeline and job orchestration
  reporting/              # reports and feedback projections
  persistence/           # SQLite persistence boundary
    catalog/              # downloaded-track and recording-family persistence
    jobs/                 # processing jobs, feedback, and analysis evidence
    migrations/           # ordered idempotent schema initialization
    system/               # application state and persistence diagnostics
    capabilities.py       # narrow repository protocols
    facade.py             # backwards-compatible JobRepository composition
  set_builder/            # set planning, validation, learning, and review
  web/                    # FastAPI composition and delivery
    routes/               # HTTP route adapters only
    contracts/            # shared request/response/error contracts
    assets/               # frontend shell and static asset delivery
    application.py        # dependency wiring and compatibility composition
    composition.py        # runtime paths and owned service container

frontend/
  app.js                  # browser bootstrap and feature composition only
  core/                   # navigation, API, request state, and app-wide controllers
  shared/                 # genuinely reusable UI and playback capabilities
  features/               # one folder per user-facing workflow
    dj-library/
    imports/
    music-files/            # catalog workflow, pure browse state, and view helpers
    processing/
    reporting/
    set-builder/
    settings/
  styles/
    core/
    shared/
    features/             # mirrors browser feature ownership

tests/
  unit/                   # mirrors Python package ownership
  integration/            # cross-package, persistence, filesystem, and provider behavior
  javascript/
    architecture/         # browser ownership and composition safeguards
    core/
    shared/
    features/             # mirrors frontend/features
  browser/                # full browser workflows and restart/cache coverage
```

Supporting project areas follow the same ownership rule:

```text
scripts/
  quality/                # lint, type, coverage, stability, and JS discovery gates
  benchmarks/             # opt-in catalog and model evaluation tools
  maintenance/            # safe local workspace housekeeping
  development/            # local browser-smoke infrastructure

docs/
  guides/                 # user, operator, and developer guidance
  architecture/           # current ownership and technical contracts
  operations/             # release gates and operational procedures
  audits/                 # point-in-time architecture and dependency audits

workspace/
  input/                   # local CLI inputs
  output/                  # generated edits, reports, backups, and exports
  cache/                   # regenerable analysis cache
```

## Placement rules

1. Put business behavior in its owning Python domain or browser feature.
2. Put FastAPI translation in `audioextender/web/routes`; route modules do not
   own reusable workflows.
3. Put SQL only in `audioextender/persistence` and group it by persisted
   aggregate. Consumers depend on narrow protocols where practical.
4. Keep `JobRepository` as the compatibility facade. Repository subpackages may
   depend on `base.py`, but never on the facade that composes them.
5. Put browser-wide transport and lifecycle primitives in `frontend/core`.
6. Put a browser module in `frontend/shared` only when at least two features use the
   same semantic capability. Similar appearance alone is not shared ownership.
7. A feature entry is named `index.js`; feature-internal files use role names
   such as `model.js`, `view.js`, `selection.js`, or `api.js` rather than
   repeating the feature prefix.
8. Tests mirror the owner. Architecture tests guard dependency and placement
   rules; behavior tests should not inspect implementation text.

## When to create another subpackage

Create a subpackage when a namespace has at least four closely related modules,
when one feature has distinct API/state/view owners, or when the package root no
longer communicates ownership at a glance. Do not split a cohesive module only
to reduce its line count.

The following root files are intentional composition surfaces:

- `frontend/app.js`
- `audioextender/web/application.py`
- `audioextender/web/composition.py`
- `audioextender/persistence/facade.py`
- `audioextender/persistence/capabilities.py`

Architecture tests reject new flat browser feature modules, flat persistence
implementations, and flat FastAPI delivery modules.
