# Data, persistence, and propagation flow

“Repository” means the boundary that reads and writes durable SQLite records.
It does not mean the Git repository. Services should depend on the narrowest
capability in `persistence/capabilities.py`.

![Data and persistence propagation flowchart](diagrams/data-and-persistence.svg)

## Durable state map

| State                            | Authority                                  | Recovery rule                             |
| -------------------------------- | ------------------------------------------ | ----------------------------------------- |
| Processing jobs and feedback     | SQLite job capabilities                    | Recover interrupted jobs on startup       |
| Downloaded-track catalog         | SQLite catalog plus verified managed files | Reconcile both sides explicitly           |
| Settings and named state         | SQLite system-state capability             | Apply ordered migrations before use       |
| Creative Commons tasks           | Durable JSON registry                      | Project persisted lifecycle after restart |
| Set planning jobs and saved sets | Versioned JSON/system state                | Mark stale work retryable                 |
| Relocation                       | Durable relocation manifest                | Resume, roll back, or fail safely         |
| Analysis/stem caches             | Rebuildable workspace cache                | Validate against source/config revision   |
| Browser filters                  | Local/session storage                      | Never authoritative for catalog facts     |

## Repository composition

`JobRepository` remains the compatibility facade. Focused job, feedback,
catalog, recording-family, descriptor, projection, analysis, metadata, and
system-state modules own their SQL. Routes and frontend code never own SQL.

Schema creation belongs to ordered, idempotent steps in
`persistence/migrations/schema.py`.

## Propagation guarantee

An authoritative mutation commits once, synchronizes approved managed-file
state, invalidates only affected caches, and republishes the DJ Library and Set
Builder read models. Source signatures avoid unnecessary rebuilds without
hiding a manual correction.

Track IDs identify one catalog entry; recording-family IDs identify versions of
the same song; file paths identify movable local assets. Workflows must use the
identity level appropriate to the decision.

## Verification

`tests/unit/persistence/`,
`tests/integration/test_manual_correction_propagation.py`, web composition
contracts, and `docs/operations/manual-correction-propagation.md`.
