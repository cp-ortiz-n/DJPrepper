# Musical policy ownership and golden contract

This document defines the musical-policy boundaries after the ARCH-003B
consolidation. `audioextender/library/musical_profile.py` is the authoritative
owner of the versioned catalog facts. `tests/fixtures/musical_policy_golden.json`
is the cross-runtime contract: Python and browser tests consume the same examples,
and the consolidation does not alter a classification threshold, score weight,
or fallback.

## Authoritative owners

| Musical fact or decision | Current authority | Consumers and compatibility boundary |
| --- | --- | --- |
| Detected standard key and confidence | `audioextender/analysis/key_detection.py` | Processing writes the estimate; verified/catalog overrides may replace it before delivery. |
| Normalized key and Camelot | `audioextender/library/musical_profile.py` | Catalog routes serialize both values. DJ Library and Set Builder consume them from `musical_profile`; browser calculation remains only for old cached payloads. |
| Energy value and band | `audioextender/library/musical_profile.py` | Catalog routes serialize both values. Thresholds are low below `0.4`, medium below `0.67`, otherwise high. |
| DJ roles | `audioextender/library/musical_profile.py` | Catalog routes serialize the ordered role list; browser and Set Builder prefer it over compatibility fields. |
| Vocal profile | `audioextender/library/musical_profile.py` | Instrumentalness at or above `0.72` is vocal-safe; below `0.45` is vocal-forward; otherwise mixed. |
| Timing profile | `audioextender/library/musical_profile.py` | Live/variable labels or tempo drift at or above `0.08` are variable; all else is steady. |
| Confidence and provenance | `audioextender/library/musical_profile.py` | Every fact group carries bounded confidence and an explicit source so consumers do not infer certainty from the value alone. |
| DJ Library match score | `compatibility` in `web/dj-library.js` | This is an interactive comparison score: tempo 45, harmonic compatibility 35, energy 10, shared roles 10. It is not a Set Builder ranking or transition score. |
| Set Builder transition cost | `transition_cost` in `audioextender/set_builder/transition_optimizer.py` | Used by deterministic running-order optimization. It is a penalty over BPM distance, weak Camelot movement, vocal collision, and energy movement; lower is better. |
| Manual splice/insertion score | `audioextender/analysis/transition_scorer.py` | This evaluates an edit point from audio-analysis evidence. It intentionally remains separate from catalog match and set-order policies. |

## Precedence and invariants

1. Processing analysis produces musical evidence; catalog delivery may apply a
   verified key or saved catalog data.
2. A `musical_profile` with a supported version takes precedence in the browser
   and Set Builder. Legacy `_roles`, `_energy`, `_vocals`, `_timing`, and browser
   derivation exist only for older/incomplete cached payloads.
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

The profile schema starts at version 1. Any schema or musical-policy change must
bump the appropriate cache/catalog version, update the shared fixture, and keep
legacy reads explicit rather than silently reintroducing a second authority.
