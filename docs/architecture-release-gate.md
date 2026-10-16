# Architecture compatibility and rollback release gate

This document is the durable evidence record for `ARCH-VERIFY-001`. A run is a
release approval only when every required row is `PASS`. Optional checks may be
`SKIP` when their dependency is unavailable, but required manual approval can
never be inferred from an automated result.

## 2026-10-15 verification run

Overall result: **NOT RELEASED**. The code, compatibility, rollback, and browser
automation gates passed. The connected-catalog evaluation could not run because
the configured external volume was not mounted, and the required DJ listening
approval has not been recorded.

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
| Catalog-scale Set Builder | **BLOCKED** | The fresh 3,260-track run found zero readable candidates because `/Volumes/YOTUO/AudioExtenderLibrary` was not mounted; all five scenarios correctly failed closed |
| Live Ollama acceptance | SKIP (optional) | `127.0.0.1:11434` was unavailable; deterministic fallback remains covered by the standard suite |
| Manual DJ listening approval | **PENDING** | The release policy requires the DJ to listen to all five generated scenario plans; automation cannot grant this approval |

The catalog-scale failure report was written to
`/tmp/arch-verify-set-builder.json`. It is intentionally outside the repository
and did not replace the last successful report. The last checked-in workspace
report, generated on 2026-10-11, completed 5/5 scenarios with average quality
81.6 and was automated-ready, but it still had manual listening pending. It is
historical evidence, not a substitute for the current release run.

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

After the external drive is mounted, rerun the catalog evaluation without
`--manual-listening-approved`. Listen to every selected plan first; only then
rerun it with that flag to record the human decision. If Ollama is available,
also run:

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

1. Mount `/Volumes/YOTUO/AudioExtenderLibrary` and confirm representative files
   are readable.
2. Rerun the catalog-scale command and require 5/5 completed scenarios with an
   automated-ready release report.
3. Optionally start Ollama and run the live acceptance suite.
4. Listen to all five plans, record the approval with
   `--manual-listening-approved`, and require `released: true`.
5. Mark `ARCH-VERIFY-001` complete only after the report contains no required
   failure or pending item.
