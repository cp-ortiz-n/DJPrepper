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
| `audioextender/library/` | Catalog projections, identities, metadata, exports, backup, and relocation |
| `audioextender/imports/` | Import services and provider integrations |
| `audioextender/set_builder/` | Brief interpretation, planning, validation, learning, review, and release gates |
| `audioextender/reporting/` | Processing and feedback projections |
| `audioextender/infrastructure/` | Cache, operation lifecycle, progress, and background-task primitives |
| `audioextender/repositories/` | SQLite boundary and compatibility facade |
| `audioextender/web/` | FastAPI composition and delivery adapters |

## Persistence

```text
audioextender/repositories/
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

## Browser application

```text
web/
├── app.js                    # bootstrap and feature composition
├── index.html
├── asset-manifest.json
├── styles.css                # single ordered stylesheet entry
├── core/                     # API, navigation, request and background state
├── shared/                   # reused components, playback, metadata UI
├── features/
│   ├── dj-library/
│   ├── imports/
│   ├── music-files/
│   ├── processing/
│   ├── reporting/
│   ├── set-builder/
│   └── settings/
└── styles/
    ├── core/
    ├── shared/
    └── features/             # mirrors browser feature ownership
```

`web/asset-manifest.json` owns one revision for the complete recursive module
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
recursive through `scripts/run_javascript_tests.mjs`; syntax discovery is
recursive through `scripts/check_javascript_syntax.mjs`.

## Project tooling and documentation

| Path | Purpose |
| --- | --- |
| `scripts/` | Quality, coverage, stability, browser, evaluation, and cleanup commands |
| `docs/` | User, operator, developer, architecture, and decision records |
| `graphify-out/` | Generated architecture graph; ignored by Git |
| `main.py` | CLI entry point |
| `web_app.py` | Compatibility web launcher |
| `settings.py` | Shipped defaults |

Local `.venv`, cache, coverage, input/output, and runtime library artifacts are
not source and remain ignored. Use `scripts/clean_workspace.py` for known safe
workspace cleanup.
