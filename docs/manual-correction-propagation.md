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
| BPM | `bpm_verifications` | Verification survives restart and preserves detected BPM | Synchronous index rebuild applies the verified BPM | Catalog cache is rewritten with verified and detected BPM | Immediate after save; protected across reanalysis and restart | Covered |
| Key | `key_verifications` | Verification survives restart | Synchronous index rebuild applies the verified key | Catalog cache is rewritten with the verified key | Immediate after save; durable after restart | Covered |
| Genre | `downloaded_tracks`, WAV tags, source sidecar, file location | Durable and searchable | Synchronous publisher rebuilds the search index | Publisher removes the stale cache before rebuilding it | Immediate after save or batch completion; durable after restart | Covered |
| Musical identity | `downloaded_track_descriptors` | Durable and searched through the descriptor table | Descriptor values are joined live | Descriptor service removes the Set Builder cache before the next read | Immediate after save; durable after restart | Covered |

## Publication boundary

`CatalogProjectionPublisher` owns invalidation and publication after catalog
corrections. It removes in-memory Library facets and the persisted Set Builder
catalog before rebuilding both read models, then records their shared source
signature. A successful write or metadata batch cannot report completion while
either projection still contains the previous catalog values.

## Invariants retained

- Analysis caches remain evidence caches. Manual values do not rewrite raw audio
  analysis and must be applied as catalog precedence at delivery time.
- A restart must reconstruct the same effective corrected values from durable
  owners without depending on browser storage.
- Browser refresh is not the authority; it only requests current server state.
- Any future correction type must identify its durable owner and projection
  invalidation behavior in the JSON matrix before release.
