# Background-operation lifecycle matrix

This is the contract for every user-visible background operation. It records
feature-specific behavior without requiring one executor or public response
shape. The machine-readable companion is
[`background-operation-lifecycles.json`](background-operation-lifecycles.json).

## Canonical internal contract

`infrastructure/operation_lifecycle.py` defines immutable lifecycle projections,
capability declarations, errors, and action receipts. Each operation family has
an adapter that accepts its existing state shape, including legacy camelCase and
snake_case fields. Services expose `lifecycle_status()` for internal consumers;
their existing `status()`, cancel, retry, pause, rollback, persistence, and HTTP
payloads remain unchanged.

The shared contract standardizes vocabulary and inspection, not execution.
Audio jobs remain in SQLite, planning and relocation retain their JSON recovery
rules, and memory-only imports and batches remain memory-only. Unsupported
actions are explicit capabilities instead of implied missing methods.

## Lifecycle summary

| Operation | States | State store | Restart disposition | Cancel | Retry | Receipt |
| --- | --- | --- | --- | --- | --- | --- |
| Audio analysis/edit jobs | queued → processing → complete/failed; queued may become canceled | SQLite | queued resumes; processing becomes failed | queued only; active work can pause but not cancel | reprocess creates linked job | No |
| Authorized source import | processing → complete/failed/canceled | Memory | state lost; completed writes remain | cooperative | resubmit | No |
| Local audio import | processing → complete/failed | Memory | state lost; completed writes remain | No | re-upload | No |
| Playlist matching | processing → complete/failed | Memory | state lost | No | re-upload | No |
| Creative Commons import/retry | processing → complete/failed | JSON registry | processing becomes failed/retryable | No | failed records create new batch | No |
| Metadata batches: WAV tags, artwork, genre rescan, catalog propagation | processing ↔ canceling → complete/failed/canceled | Memory | state/retry inputs lost; completed writes remain | item checkpoints | terminal batch creates linked retry | Yes |
| Library integrity scan | processing → complete | Memory | findings lost; rerun | No | rerun | Yes |
| Audio-quality scan | processing → complete | Memory; results in SQLite | state lost; written measurements remain | No | rerun | No |
| Set planning | pending → processing/canceling → complete/failed/canceled | JSON | active becomes failed/retryable | cooperative and superseding | failed/canceled creates linked retry | Planning receipt, not generic receipt |
| Full-library relocation | planned → processing/canceling → complete/failed/canceled; complete may become rolled_back | JSON manifest | processing becomes failed; plan retained | copy/verify checkpoints | restart saved plan | No |

## State and persistence rules

- **Persistent lifecycle state:** audio jobs, Creative Commons imports, Set
  planning, and full-library relocation survive restart as inspectable terminal
  or resumable/retryable records.
- **Memory-only lifecycle state:** authorized/local imports, playlist matching,
  metadata batches, integrity scans, and audio-quality scans disappear on
  restart. Durable writes completed before interruption are not rolled back.
- **Pause is not a persisted status:** audio-job pause gates an active worker and
  updates its stage. A restart still treats that job as interrupted processing.
- **Retry creates new work:** audio reprocessing, import failure retries,
  metadata retries, and Set planning retries preserve history by creating a new
  linked job/batch. Full-library relocation reuses its persisted plan instead.
- **Cancellation is cooperative:** where supported, it is observed only at the
  checkpoints listed in the JSON contract. Canceling never promises rollback of
  earlier durable writes.

## Known lifecycle gaps

Remaining operational limitations are explicit rather than hidden:

1. Integrity and audio-quality worker exceptions do not consistently publish a
   terminal `failed` state.
2. Six operation families keep lifecycle state only in memory.
3. Only metadata/maintenance batches publish the generic operation receipt in
   their public payload; the canonical projection preserves domain receipts and
   represents absent receipts explicitly.
4. Source timestamp coverage and field naming still differ, but adapters expose
   consistent `created_at`, `updated_at`, and `completed_at` fields.
5. Active audio processing can pause but cannot be cooperatively canceled.
6. Creative Commons, local import, and playlist-match states do not share the
   authorized-import cancellation/error contract.
7. The unused `key_analysis_batches` and `library_consolidation_batches`
   dictionaries in `audioextender/web/application.py` are not operation families; they are
   legacy state declarations to remove during the owning cleanup.

## Change rule

Any new user-visible background operation must be added to the JSON contract,
the `LIFECYCLE_FAMILIES` registry, and this summary. Feature-specific persistence
and rollback behavior must remain explicit. Public endpoints and stored jobs
remain compatible unless a separate migration is approved.
