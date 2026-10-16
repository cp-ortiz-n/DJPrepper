# Architecture compatibility and rollback release gate

This document is the durable evidence record for `ARCH-VERIFY-001`. A run is a
release approval only when every required row is `PASS` or the owner records an
explicit, visible waiver. Optional checks may be `SKIP` when their dependency is
unavailable, but manual approval can never be inferred from automation.

## 2026-10-15 verification run

Overall result: **PROVISIONALLY RELEASED**. The code, compatibility, rollback,
browser automation, and connected-catalog gates passed. On 2026-10-15, the
project owner authorized a temporary listening waiver and committed to validate
the generated playlists afterward. This waiver is release authorization, not a
claim that listening has already happened.

| Gate | Result | Evidence |
| --- | --- | --- |
| Ruff lint | PASS | `./scripts/check_quality.sh`: all checks passed |
| Python formatting ratchet | PASS | 12 known legacy files; no new formatting debt |
| MyPy | PASS | 174 source files, no issues |
| Python tests | PASS | 352 passed, 6 opt-in live-provider tests skipped |
| JavaScript quality and tests | PASS | ESLint, formatting ratchet, syntax, and 65 behavioral tests passed |
| Python coverage | PASS | 65.3% aggregate statement/branch report generated in `coverage/` |
| JavaScript coverage | PASS | 25.16% statements, 71.42% branches, 59.09% functions, 25.16% lines |
| Stability workflow | PASS | Reimport, relocation, restart, reanalysis, and export lifecycle passed |
| Backup and restore | PASS | Valid backup restored catalog and metadata; tampering and retention behavior passed |
| Rollback rehearsal | PASS | Disposable relocation copy/move/relink tests and SQLite-backup reopen passed without touching the user library |
| Legacy database fixture | PASS | Ordered migrations upgraded the old schema in place without replacing rows |
| Legacy saved-set fixture | PASS | Version-1 migration was idempotent and preserved newer server records |
| CLI contract | PASS | Discovery, validation, naming, duration, and timestamp helpers passed |
| Endpoint inventory | PASS | Public route inventory, delivery shell, response shapes, and disconnected-library contract passed |
| Export contract | PASS | WAV, cue, preview-only, path isolation, and writer-failure tests passed |
| Browser workflows | PASS | 8 Playwright workflows passed, including persistence, saved-set recovery, overlapping search, reconnect, focus, single preview, viewport/accessibility, and reduced motion |
| Catalog-scale Set Builder | PASS | After reconnect, 3,255 of 3,260 catalog files were readable; 5/5 scenarios completed with valid plans, automated-ready status, and average quality 80.4 |
| Live Ollama acceptance | SKIP (optional) | `127.0.0.1:11434` was unavailable; deterministic fallback remains covered by the standard suite |
| Manual DJ listening approval | TEMPORARY OWNER WAIVER | The owner explicitly authorized provisional approval before listening; post-release validation remains required |

The current catalog-scale report was written to
`/tmp/arch-verify-set-builder.json`. It is intentionally outside the repository
and did not replace the workspace report before human approval. The first run
failed closed while the volume was disconnected; after reconnect, the same
command completed all five scenarios. Scenario quality scores were 82 for Latin
kickback, 82 for Latin Techno waves, 61 for the Latin party journey, 90 for the
Afro House lounge, and 87 for peak Techno. The Latin Techno scenario's 0.667
literal genre coverage was accepted under the explicit zero-candidate scarcity
policy; the other scenarios reported 0.857–1.0 coverage.

For the required listening review, M3U8 files containing the exact evaluated
track order were generated under `/tmp/audioextender-release-listening/`. These
are temporary review artifacts and are not application-owned saved sets.
The provisionally approved machine-readable report is
`/tmp/arch-verify-set-builder-approved.json`; it records `released: true`, 5/5
completed scenarios, and average quality 80.4.

## Commands

Run from the repository root with Node 20 or newer:

```sh
PATH="$HOME/.nvm/versions/node/v22.23.3/bin:$PATH" ./scripts/check_quality.sh
PATH="$HOME/.nvm/versions/node/v22.23.3/bin:$PATH" ./scripts/check_coverage.sh
./scripts/run_stability_gate.sh
.venv/bin/python -m unittest -v \
  tests.test_library_backup tests.test_library_relocation \
  tests.test_repository_schema tests.test_saved_sets tests.test_cli_helpers \
  tests.test_export_service tests.test_web_composition_contracts \
  tests.test_set_release_gate
PATH="$HOME/.nvm/versions/node/v22.23.3/bin:$PATH" npm run check:browser
env AUDIOEXTENDER_LLM_PROVIDER=offline .venv/bin/python \
  scripts/evaluate_set_builder.py \
  --output /tmp/arch-verify-set-builder.json \
  --preferences /tmp/arch-verify-preferences.json
```

For a normal release without a waiver, rerun the catalog evaluation without
`--manual-listening-approved`, listen to every selected plan, and only then rerun
it with that flag to record the human decision. If Ollama is available, also run:

```sh
env AUDIOEXTENDER_RUN_LOCAL_LLM_TESTS=1 \
  .venv/bin/python -m unittest -v tests.test_local_intention_acceptance
```

## Compatibility and intentional differences

No unintended public endpoint, CLI, export, legacy database, or saved-set
compatibility difference was detected. The approved architecture changes remain
intentional and additive:

- saved sets are backend-owned, with version-1 browser records migrated through
  the compatibility reader;
- normalized error metadata is additive and preserves legacy `detail` values;
- schema upgrades are ordered, idempotent, and in place, with backup/restore as
  the rollback boundary;
- feature services and browser modules replace internal composition-root
  ownership without changing public routes;
- Set Builder provider failures retain deterministic fallback, while release
  evaluation still fails closed for unavailable files or invalid plans.

## Closure procedure

1. Optionally start Ollama and run the live acceptance suite.
2. Listen to all five temporary playlists and record any rejection or required
   correction.
3. Replace the temporary waiver with confirmed listening evidence; reopen the
   release gate if any scenario is rejected.
