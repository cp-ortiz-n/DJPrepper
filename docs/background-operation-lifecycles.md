# Background-operation lifecycle matrix

This is the Phase 0 contract for every user-visible background operation. It
records current behavior, including gaps; it does not imply that all operations
already use one executor or response shape. The machine-readable companion is
[`background-operation-lifecycles.json`](background-operation-lifecycles.json).

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

These are explicit inputs to `ARCH-004B`, not hidden assumptions:

1. Integrity and audio-quality worker exceptions do not consistently publish a
   terminal `failed` state.
2. Six operation families keep lifecycle state only in memory.
3. Only metadata/maintenance batches use the generic operation receipt; Set
   planning has a separate domain receipt and the other families have none.
4. Timestamp coverage and field naming differ (`snake_case`, `camelCase`, or no
   timestamps).
5. Active audio processing can pause but cannot be cooperatively canceled.
6. Creative Commons, local import, and playlist-match states do not share the
   authorized-import cancellation/error contract.
7. The unused `key_analysis_batches` and `library_consolidation_batches`
   dictionaries in `web/application.py` are not operation families; they are
   legacy state declarations to remove during the owning cleanup.

## Change rule

Any new user-visible background operation must be added to the JSON contract and
this summary. `ARCH-004B` may introduce common status, receipt, cancellation,
and retry DTOs, but feature-specific persistence and rollback behavior must
remain explicit. Public endpoints and stored jobs remain compatible unless a
separate migration is approved.
