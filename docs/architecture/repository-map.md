# Repository map

This is the concise navigation map for DJ Library Studio. Placement rules and
the complete ownership rationale live in [code-organization.md](code-organization.md).

## Application source

| Path | Owner |
| --- | --- |
| `audioextender/core/` | Stable configuration, models, interfaces, presets, and exceptions |
| `audioextender/audio/` | Audio loading, quality, stems, rendering, and WAV metadata |
| `audioextender/analysis/` | Musical analysis, candidate selection, scoring, and validation |
| `audioextender/processing/` | Track pipeline, batch, extended-edit, and job orchestration |
| `audioextender/library/` | Catalog reconciliation/projections, identities, taxonomy, local media, metadata, exports, backup, and relocation |
| `audioextender/imports/` | Import services, playlist parsing, source metadata lookup, and provider matching |
| `audioextender/set_builder/` | Brief interpretation, planning, validation, learning, review, and release gates |
| `audioextender/reporting/` | Processing and feedback projections |
| `audioextender/infrastructure/` | Cache, operation lifecycle, progress, and background-task primitives |
| `audioextender/persistence/` | SQLite boundary and compatibility facade |
| `audioextender/web/` | FastAPI composition and delivery adapters |

## Persistence

```text
audioextender/persistence/
├── base.py
├── capabilities.py
├── facade.py                 # JobRepository compatibility composition
├── catalog/                  # tracks, descriptors, metadata, projections, families
├── jobs/                     # queue, feedback, analysis evidence
├── migrations/               # ordered schema initialization
└── system/                   # application state and concurrency diagnostics
```

SQL belongs only in this tree. New consumers should depend on a protocol from
`capabilities.py` when they do not need the full facade.

## FastAPI delivery

```text
audioextender/web/
├── application.py            # create_app, wiring, middleware, compatibility exports
├── composition.py            # paths, runtime container, owned services
├── routes/                   # feature routers and HTTP translation
├── contracts/                # shared models and error contracts
└── assets/                   # frontend manifest and static delivery
```

Reusable workflows belong in their domain package, not in `routes/`.
Import routes delegate source matching and playlist parsing to `imports/`.
Library routes delegate catalog migration, local-media handling, taxonomy, and
historical job removal to `library/`; these workflows must not return to the
composition root.

## Browser application

```text
frontend/
├── app.js                    # bootstrap and feature composition
├── index.html
├── asset-manifest.json
├── styles.css                # single ordered stylesheet entry
├── core/                     # API, navigation, request and background state
├── shared/                   # reused components, playback, metadata UI
├── features/
│   ├── dj-library/
│   ├── imports/
│   ├── music-files/            # coordinator, browse state, and toolbar presentation
│   │   ├── index.js            # catalog workflow and track interactions
│   │   ├── state.js            # pure filter/query/selection projections
│   │   └── view.js             # filter chips and disclosure presentation
│   ├── processing/
│   ├── reporting/
│   ├── set-builder/
│   └── settings/
└── styles/
    ├── core/
    ├── shared/
    └── features/             # mirrors browser feature ownership
```

`frontend/asset-manifest.json` owns one revision for the complete recursive module
graph. Nested asset paths are versioned by the server-generated import map.

## Tests

```text
tests/
├── unit/                     # mirrors Python package ownership
├── integration/              # cross-package and persistence workflows
├── javascript/
│   ├── architecture/
│   ├── core/
│   ├── shared/
│   └── features/
├── browser/                  # Playwright workflows and warm-cache restart
├── fixtures/
└── support/
```

Python test directories remain importable packages. JavaScript discovery is
recursive through `scripts/quality/run_javascript_tests.mjs`; syntax discovery is
recursive through `scripts/quality/check_javascript_syntax.mjs`.

## Project tooling and documentation

| Path | Purpose |
| --- | --- |
| `scripts/quality/` | Quality, coverage, stability, formatting, and recursive JS discovery |
| `scripts/benchmarks/` | Opt-in key, Set Builder, and persistence measurements |
| `scripts/maintenance/` | Safe workspace cleanup |
| `scripts/development/` | Browser-smoke application server |
| `docs/guides/` | User, operator, and developer guidance |
| `docs/flows/` | End-to-end workflow diagrams, functions, models, persistence, and failure paths |
| `docs/architecture/` | Current ownership, maps, and technical contracts |
| `docs/operations/` | Operational procedures and release gates |
| `docs/audits/` | Point-in-time architecture and dependency audits |
| `graphify-out/` | Generated architecture graph; ignored by Git |
| `audioextender/cli.py` | Package-owned CLI implementation |
| `main.py` | Compatibility CLI launcher |
| `web_app.py` | Compatibility web launcher |
| `audioextender/core/defaults.py` | Shipped application defaults |
| `workspace/` | Ignored local CLI input, output, and cache data |

Local `.venv`, workspace data, coverage, and runtime library artifacts are
not source and remain ignored. Use `scripts/maintenance/clean_workspace.py` for known safe
workspace cleanup.
