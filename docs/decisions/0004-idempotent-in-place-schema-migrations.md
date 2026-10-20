# ADR-0004: Idempotent in-place schema migrations

- Status: Accepted
- Date: 2026-10-15

## Context

The application is local-first and opens long-lived user databases directly at
startup. Requiring a separate migration service or destructive database rebuild
would make ordinary upgrades fragile and could strand catalog, correction, and
saved-set data.

## Decision

`audioextender/persistence/migrations/schema.py` owns ordered, named,
idempotent SQLite migration steps. Startup applies missing steps in place within
the persistence boundary. New SQL stays in `audioextender/persistence`, and
changes preserve readable older databases. Backups
remain the rollback boundary for destructive or data-transforming changes.

## Compatibility guarantees

- Opening a supported older database upgrades it without deleting user rows.
- Re-running initialization produces the same schema and data.
- Dependency order is explicit, including tables referenced by foreign keys.
- New required values receive deterministic migration defaults or an explicit
  data migration.
- Backup and restore include every backend-owned durable aggregate.

## Consequences

Schema work requires old-database fixtures and restart tests. The project does
not add an external migration framework while the ordered bootstrap remains
small, observable, and sufficient.

## Revisit when

Migrations require online rollout, multiple application versions writing the
same database, cross-database deployment, or operational tooling beyond a local
startup transaction.

