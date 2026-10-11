# Development quality baseline

This is the reproducible Phase 0 baseline for DJ Library Studio. Generated reports stay in the existing ignored `coverage/` directory; they are diagnostic artifacts, not source files or historical records.

## Commands and verification tiers

| Tier | Command | Purpose |
| --- | --- | --- |
| Focused | `.venv/bin/python -m unittest tests.test_module` or `node --test tests/file.test.js` | Fast feedback while editing |
| Standard | `./scripts/check_quality.sh` | Ruff lint/format ratchet, MyPy, Python tests and architecture safeguards, ESLint, Prettier ratchet, JS syntax and tests |
| Coverage | `./scripts/check_coverage.sh` | Regenerate Python JSON/LCOV and JavaScript LCOV summaries |
| Stability | `./scripts/run_stability_gate.sh` | Persistence, import, relocation, export, and Set Builder compatibility |

JavaScript coverage requires Node 20 or newer (`nvm use 22` is recommended). The application and standard tests remain usable on the older system Node, but V8 coverage crashes in Node 18.12. Coverage measures `audioextender/`, maintained top-level Python modules, and `web/**/*.js`; dependencies, tests, generated files, and vendor assets are excluded. There is no arbitrary percentage threshold in Phase 0. A meaningful decrease from this baseline must be investigated and either restored or justified in the change report.

## Verified baseline — 2026-10-11

| Tool | Version | Command | Before | Phase 0 result |
| --- | --- | --- | --- | --- |
| Ruff | 0.16.7 | `.venv/bin/ruff check .` | 2 import findings from one duplicate import | clean; C4 enabled |
| Ruff formatter | 0.16.7 | `.venv/bin/python scripts/check_python_format.py` | 14 legacy files | ratchet passes; no new debt |
| MyPy | 1.20.2 | `.venv/bin/mypy` | clean across 143 files | clean across 144 files |
| unittest | Python 3.13.15 | `.venv/bin/python -m unittest discover -s tests` | 288 passed, 6 skipped, 1 deprecation warning | 293 passed, 6 skipped, same external warning |
| ESLint | 8.57.x | `npm run lint` | not configured | correctness gate clean; four undefined-state references found and corrected |
| Prettier | 3.9.x | `npm run format:check` | 18 legacy frontend files | ratchet passes; no new debt |
| Node tests | Node 22.23.3 | `npm run check` | 44 passed | 44 passed |

Ruff SIM found 14 cleanup candidates, ARG found four intentional/false-positive callback parameters, and C90 found eight existing complexity hotspots. They are deferred rather than globally suppressed or mixed into Phase 0. ESLint unused-variable findings are likewise recorded as extraction-era debt; correctness rules such as undefined names remain enforced.

## Measured coverage

The reports were regenerated from this checkout, not inferred from older HTML. Python uses branch coverage. JavaScript uses c8/V8 under Node 22.

| Surface | Statements/lines | Branches | Functions |
| --- | ---: | ---: | ---: |
| Python application | 66.0% (7,525 / 11,406) | 46.7% (1,376 / 2,946; 498 partial) | n/a |
| JavaScript application | 12.95% (657 / 5,072) | 57.23% (174 / 304) | 52.13% (61 / 117) |

The combined Python line-and-branch score reported by coverage.py is 62.0%.
Representative modules: `set_builder/candidate_retriever.py` 91%,
`set_builder/plan_validator.py` 98%, `set_builder/track_planner.py` 86%,
`repositories/track_catalog.py` 79%, `analysis/key_detection.py` 79%,
`analysis/section_selector.py` 73%, `web/settings_routes.py` 57%,
`processing/track_processor.py` 49%, `web/application.py` 33%, and
`audio/stems.py` 14%.

Measured risk is concentrated in browser DOM workflows, web delivery/composition, media/job routes, stems, and the processing transaction. Low percentages are not confirmed bugs. The next coverage work should add observable-behavior characterization for web composition and frontend workflows rather than source-string assertions or percentage-only tests.

## Architecture safeguards

`tests/test_architecture_boundaries.py` rejects internal Python import cycles, domain-to-web imports, new SQL outside repositories, and growth in four verified hotspots. One existing backup query is fingerprinted as legacy debt. The test also ratchets the size and branch count of `TrackProcessor.process`.

Current musical-policy owners remain intentionally separate: Python `analysis/` owns processing-time BPM/key/section and splice policy; `set_builder/` owns candidate, journey, transition, validation, and AI acceptance policy; browser `dj-library.js` owns display compatibility helpers. Consolidation and golden cross-runtime fixtures belong to `ARCH-003A`; Phase 0 does not change weights or algorithms.

