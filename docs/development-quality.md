# Development quality baseline

This is the reproducible Phase 0 baseline for DJ Library Studio. Generated reports stay in the existing ignored `coverage/` directory; they are diagnostic artifacts, not source files or historical records.

## Commands and verification tiers

| Tier | Command | Purpose |
| --- | --- | --- |
| Focused | `.venv/bin/python -m unittest tests.unit.package.test_module` or `node --test tests/javascript/file.test.js` | Fast feedback while editing |
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
| Python application | 66.4% (7,622 / 11,472) | 47.6% (1,411 / 2,964; 503 partial) | n/a |
| JavaScript application | 14.92% (769 / 5,153) | 70.23% (302 / 430) | 59.50% (72 / 121) |

The combined Python line-and-branch score reported by coverage.py is 62.6%.
Representative modules: `set_builder/candidate_retriever.py` 91%,
`set_builder/plan_validator.py` 98%, `set_builder/track_planner.py` 86%,
`repositories/track_catalog.py` 79%, `analysis/key_detection.py` 79%,
`analysis/section_selector.py` 73%, `web/settings_routes.py` 57%,
`processing/track_processor.py` 49%, `web/application.py` 33%, and
`audio/stems.py` 14%.

Measured risk is concentrated in browser DOM workflows, web delivery/composition, media/job routes, stems, and the processing transaction. Low percentages are not confirmed bugs. The next coverage work should add observable-behavior characterization for web composition and frontend workflows rather than source-string assertions or percentage-only tests.

## Architecture safeguards

`tests/unit/architecture/test_boundaries.py` rejects internal Python import cycles,
domain-to-web imports, new SQL outside repositories, and growth in designated
composition/orchestration hotspots. Package-level `from` imports participate in
the cycle graph, and the one fingerprinted legacy backup query must be removed
from the exception list as soon as its debt is retired. The suite also ratchets
the size and branch count of `TrackProcessor.process`.

Browser musical-profile compatibility derivation has one guarded owner:
`web/dj-library.js`. Other browser modules must consume its profile helpers; the
architecture gate rejects duplicate helper declarations, Camelot maps, and
direct reads of the serialized `musical_profile`. This preserves the explicit
legacy-cache fallback without allowing another browser policy authority to grow.

Manual-correction propagation is governed by
`docs/manual-correction-propagation.json`. Its behavioral suite verifies durable
key, BPM, genre, and identity propagation. Verified BPM preserves detected
analysis as evidence while a durable user correction controls Library and Set
Builder delivery. Catalog metadata writes synchronously publish both read models
through `CatalogProjectionPublisher`, so browser refresh is never the authority
for making corrected values visible.

Current musical-policy owners remain intentionally separate: Python `analysis/`
owns processing-time BPM/key/section and splice policy; `set_builder/` owns
candidate, journey, transition, validation, and AI acceptance policy; browser
`dj-library.js` owns the interactive Library match score and compatibility
fallbacks. `docs/musical-policy-ownership.md` records exact precedence. The
versioned `tests/fixtures/musical_policy_golden.json` is exercised by Python and
Node so cross-runtime drift fails the standard quality gate. `ARCH-003A` changes
no weights or algorithms; consolidation remains scoped to `ARCH-003B`.

`tests/unit/architecture/test_background_operation_contract.py` validates that the Phase 0
background-operation inventory retains all ten audited families and a complete
lifecycle description. It is a documentation contract, not a claim that those
families already share an executor. Current differences and known gaps are
recorded in `docs/background-operation-lifecycles.md` for `ARCH-004B`.

`ARCH-011A` removed repeated Set Builder test cases and replaced implementation-
text assertions with calls to production behavior for descriptor rendering,
provider availability, and journey-duration validation. The remaining frontend
source inspection is limited to deliberate architecture contracts: the `app.js`
composition-root size/ownership ratchet and shared CSS accessibility/responsive
tokens. Focused suites own request cancellation and stale-response rejection,
single-player behavior, Set planning lifecycle, imports, and musical policy.

`ARCH-010A` adds behavioral contract coverage for legacy and normalized HTTP
errors, validation lists, expected domain failures, sanitized unexpected errors,
and browser recovery metadata. The contract is additive: success payloads and
existing `detail` values remain compatible.

Repository concurrency can be measured safely with
`scripts/measure_repository_concurrency.py`. The opt-in probe uses only a
temporary catalog, enforces bounded workers and iterations, and reports latency,
SQLite lock errors, suspected waits, stale committed reads, and final
invariants. See `docs/concurrency-measurement.md` for interpretation.

`npm run check:browser` is the opt-in release smoke gate. It starts a real app
against an isolated temporary catalog and music-library folder, then runs
Chromium workflows and axe accessibility checks. Install its pinned browser once
with `npm run check:browser:install`. The smoke server never opens the configured
user database or music library. See `docs/browser-smoke-testing.md` for the
coverage map and interpretation rules.

