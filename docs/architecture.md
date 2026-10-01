# AudioExtender architecture

Application code lives under `audioextender/` and is grouped by business responsibility.

| Package | Responsibility |
| --- | --- |
| `core` | Shared configuration, immutable models, interfaces, and presets |
| `audio` | Audio loading, quality inspection, WAV metadata, and stem operations |
| `analysis` | Key detection, section selection, scoring, and candidate policy |
| `processing` | Track, batch, and background job orchestration |
| `library` | Track identity, backup, relocation, metadata, and export |
| `imports` | YouTube, SoundCloud, local-file, playlist, and Creative Commons imports |
| `repositories` | SQLite persistence grouped by business capability |
| `infrastructure` | Caching, progress, and background task state |
| `reporting` | Processing and feedback reports |
| `web` | FastAPI routers and delivery adapters with explicit application dependencies |

## Dependency direction

- `core` must stay independent of delivery code and database persistence.
- `audio` and `analysis` contain reusable domain behavior; they must not depend on web routes.
- `processing`, `library`, and `imports` orchestrate domain services.
- `repositories` owns persistence only; route and UI concerns stay outside it.
- `web` translates HTTP requests and responses but does not own persistence or domain policy.
- `web_app.py` is the composition root that wires routers and services into the FastAPI application.

Do not add general-purpose source files under `helpers/`. If a new module does not fit one of
the packages above, define its responsibility first and add a deliberately named package.
`tests/test_package_structure.py` enforces this rule.
