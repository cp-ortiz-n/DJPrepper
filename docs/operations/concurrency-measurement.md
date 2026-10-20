# Persistence concurrency measurement

ARCH-015A uses an opt-in synthetic workload to measure SQLite and repository
behavior before considering a persistence redesign. The harness never opens the
configured music library or production database. Every run creates a new
temporary workspace and deletes it when measurement finishes.

## Run the probe

```bash
.venv/bin/python scripts/benchmarks/measure_persistence_concurrency.py
```

The default workload runs 50 rounds with six workers and writes its report to
`workspace/output/reports/persistence_concurrency.json`. Resource bounds are enforced:
iterations must remain between 1 and 1,000 and workers between 1 and 16.

For a shorter target-Mac check:

```bash
.venv/bin/python scripts/benchmarks/measure_persistence_concurrency.py \
  --iterations 25 --workers 6 --suspected-wait-ms 100
```

## Reading the report

- `sqlite_locked_errors` counts SQLite operations that actually reported a
  locked database.
- `suspected_lock_waits` records operations that overlapped other work and took
  longer than the configured observation threshold. SQLite does not expose its
  internal wait duration, so these are latency signals rather than proven lock
  waits.
- `stale_results` records a committed job, track, descriptor, or system-state
  write that was not visible to the next repository read, plus final-count
  mismatches.
- `latency_ms` reports p50, p95, and maximum duration for each operation class.

The command exits unsuccessfully only for operation errors or stale committed
results. Slow overlapping operations remain visible without automatically
justifying a database redesign. If a repeatable correctness failure appears,
create ARCH-015B with the report and target hardware details as evidence.
