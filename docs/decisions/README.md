# Architecture decision records

These records capture decisions that constrain compatibility or the placement
of future work. They complement [`../architecture/architecture.md`](../architecture/architecture.md): the
architecture guide explains where code belongs, while these records explain why
the boundary exists and what must remain compatible.

## Index

| Record | Decision |
| --- | --- |
| [ADR-0001](0001-backend-owned-saved-sets.md) | Editable saved sets are versioned backend aggregates |
| [ADR-0002](0002-authoritative-musical-profile.md) | The versioned musical profile is the cross-surface musical authority |
| [ADR-0003](0003-shared-operation-contracts.md) | Background operations share contracts, not a universal executor |
| [ADR-0004](0004-idempotent-in-place-schema-migrations.md) | SQLite schema changes use ordered, idempotent, in-place migrations |
| [ADR-0005](0005-modular-monolith-and-vanilla-javascript.md) | The product remains a modular monolith with vanilla JavaScript |

## Record lifecycle

- **Accepted** records describe the current contract.
- A material reversal requires a new record that supersedes the old one; do not
  rewrite the original rationale.
- Implementation details may evolve without a new record when the compatibility
  guarantees and ownership boundary remain unchanged.
- Link new records here and from the relevant architecture section.

