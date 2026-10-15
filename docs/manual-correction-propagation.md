# Manual correction propagation

ARCH-014A traces user-confirmed BPM, key, genre, and musical-identity values
from their authoritative write through the downloaded catalog, Library search
projection, DJ Library, Set Builder, refresh, and application restart. The
machine-readable contract is
[`manual-correction-propagation.json`](manual-correction-propagation.json), and
`tests/test_manual_correction_propagation.py` exercises the durable paths and
projection behavior against a disposable catalog.

## Results

| Correction | Durable owner | Music Files/catalog | DJ Library | Set Builder | Refresh/restart | Result |
| --- | --- | --- | --- | --- | --- | --- |
| BPM | None | No supported manual write | No propagation | No propagation | No durable correction | Confirmed gap: ARCH-014B |
| Key | `key_verifications` | Verification survives restart | Synchronous index rebuild applies the verified key | Catalog cache is rewritten with the verified key | Immediate after save; durable after restart | Covered |
| Genre | `downloaded_tracks`, WAV tags, source sidecar, file location | Durable and searchable | Index source signature schedules a background rebuild | A version-valid catalog file can be read before that rebuild finishes | Eventually correct; durable after restart | Confirmed stale-read gap: ARCH-014C |
| Musical identity | `downloaded_track_descriptors` | Durable and searched through the descriptor table | Descriptor values are joined live | Descriptor service removes the Set Builder cache before the next read | Immediate after save; durable after restart | Covered |

## Confirmed gaps

### ARCH-014B — durable manual BPM correction

There is no supported command or persistence field for a user-confirmed BPM.
Job BPM remains analysis output, so reanalysis can replace it and neither the
Library nor Set Builder has a durable manual value to prefer. The follow-up must
add an explicit verified BPM owner and the same precedence guarantees already
used for verified keys.

### ARCH-014C — synchronous projection invalidation after catalog metadata writes

Genre and general metadata writes update the durable track row, but the Library
index refresh is normally scheduled in the background. The request that detects
the changed signature can still return the old index, while Set Builder may read
an existing cache whose schema version is valid but whose contents are stale.
The follow-up must provide one application-owned invalidation operation that
clears in-memory facets and the persisted signature/catalog, then synchronously
publishes the corrected projection (or blocks reads until publication).

## Invariants retained

- Analysis caches remain evidence caches. Manual values do not rewrite raw audio
  analysis and must be applied as catalog precedence at delivery time.
- A restart must reconstruct the same effective corrected values from durable
  owners without depending on browser storage.
- Browser refresh is not the authority; it only requests current server state.
- Any future correction type must identify its durable owner and projection
  invalidation behavior in the JSON matrix before release.
