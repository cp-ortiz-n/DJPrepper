# Musical policy ownership and golden contract

This document freezes the current musical-policy boundaries before consolidation.
It describes ownership, not a claim that every current rule belongs in its final
module. `tests/fixtures/musical_policy_golden.json` is the cross-runtime contract:
Python and browser tests consume the same examples, and this phase does not alter
any classification threshold, score weight, or fallback.

## Authoritative owners

| Musical fact or decision | Current authority | Consumers and compatibility boundary |
| --- | --- | --- |
| Detected standard key and confidence | `audioextender/analysis/key_detection.py` | Processing writes the estimate; verified/catalog overrides may replace it before delivery. |
| Key spelling normalization and Camelot display | Catalog serialization in `audioextender/web/application.py`; browser display in `web/dj-library.js` | Both use the same 24-key map. Set ordering consumes an already-serialized Camelot value in `set_builder/transition_optimizer.py`. The golden key cases prevent drift until `ARCH-003B` establishes one serialized owner. |
| Energy classification | `_library_energy` in `audioextender/web/application.py` for serialized catalog data | `songEnergy` in `web/dj-library.js` honors serialized `_energy` first and retains the same calculation as a compatibility fallback. Thresholds are low below `0.4`, medium below `0.67`, otherwise high. |
| DJ roles | `_library_roles` in `audioextender/web/application.py` for serialized catalog data | `libraryRoles` in `web/dj-library.js` honors serialized `_roles` first and retains the same rules as a compatibility fallback. |
| Vocal profile | Catalog serialization in `_refresh_library_search_index` in `audioextender/web/application.py` | `vocalProfile` in `web/dj-library.js` honors `_vocals` first. Instrumentalness at or above `0.72` is vocal-safe; below `0.45` is vocal-forward; otherwise mixed. |
| Timing profile | Catalog serialization in `_refresh_library_search_index` in `audioextender/web/application.py` | `timingProfile` in `web/dj-library.js` honors `_timing` first. Live/variable labels or tempo drift at or above `0.08` are variable; all else is steady. |
| DJ Library match score | `compatibility` in `web/dj-library.js` | This is an interactive comparison score: tempo 45, harmonic compatibility 35, energy 10, shared roles 10. It is not a Set Builder ranking or transition score. |
| Set Builder transition cost | `transition_cost` in `audioextender/set_builder/transition_optimizer.py` | Used by deterministic running-order optimization. It is a penalty over BPM distance, weak Camelot movement, vocal collision, and energy movement; lower is better. |
| Manual splice/insertion score | `audioextender/analysis/transition_scorer.py` | This evaluates an edit point from audio-analysis evidence. It intentionally remains separate from catalog match and set-order policies. |

## Precedence and invariants

1. Processing analysis produces musical evidence; catalog delivery may apply a
   verified key or saved catalog data.
2. Serialized `_roles`, `_energy`, `_vocals`, and `_timing` take precedence in
   the browser. Browser derivation exists only for older/incomplete payloads.
3. DJ Library compatibility is a higher-is-better UI score. Set Builder
   transition cost is a lower-is-better sequencing penalty. They must not be
   substituted for one another.
4. Unknown keys remain unknown. Half/double-time tempo relationships are valid
   for both Library matching and Set ordering.
5. Any intentional policy change updates the implementation, the shared golden
   fixture, both runtime tests, and this document in the same change.

## Golden fixture scope

The versioned fixture covers enharmonic key normalization, Camelot conversion,
role combinations, energy fallback/bands, vocal and timing boundaries,
serialized-value precedence, DJ Library score components, half/double-time,
weak harmonic movement, vocal collision, and Set Builder transition cost.

`ARCH-003B` may move these facts into one versioned Python profile. It must keep
the fixture green first, then change expected values only as an explicit musical
product decision.
