# ADR-0002: Authoritative musical profile

- Status: Accepted
- Date: 2026-10-15

## Context

Analysis, catalog views, DJ Library filters, and Set Builder historically
derived overlapping musical facts. Divergent key, energy, vocal, timing, and
identity interpretations made manual corrections unreliable across surfaces.

## Decision

`audioextender/library/musical_profile.py` owns the versioned, serialized
cross-surface musical profile: normalized key and Camelot, energy, DJ roles,
vocals, timing, confidence, and provenance. Analysis modules produce evidence;
the library profile resolves it with saved manual corrections and exposes the
result to catalog and Set Builder consumers.

Set transition scoring and interactive DJ Library matching remain distinct
policies. They consume the same facts but answer different questions and must
not be collapsed into the profile.

## Compatibility guarantees

- Manual corrections outrank inferred and analyzed values until explicitly
  cleared.
- Every serialized profile declares its schema version and provenance.
- Catalog, detail, and Set Builder projections agree on authoritative facts.
- Legacy local derivations are compatibility fallbacks only and cannot override
  a valid authoritative value.
- Golden musical fixtures protect normalization and precedence behavior.

## Consequences

New shared musical facts belong in the profile schema and migration path.
Feature-specific ranking belongs beside the feature. Consumers should not
silently recreate profile precedence rules.

## Revisit when

A second authoritative catalog is introduced or evidence shows that one profile
cannot represent the product's shared musical facts without feature leakage.

