# ADR-0001: Backend-owned saved sets

- Status: Accepted
- Date: 2026-10-15

## Context

Editable set plans were stored only in browser local storage. Clearing browser
data, changing browser profiles, or restoring the application database could
therefore lose work even though exported M3U8 files survived.

## Decision

Editable saved sets are versioned aggregates owned by the backend
`SavedSetService` and persisted in SQLite. The browser API is the source of
truth. Legacy local-storage sets are imported through an idempotent migration;
local storage remains a recovery cache, not an independent authority. Playlist
export remains a separate output operation.

## Compatibility guarantees

- Existing version-1 browser records can be imported without duplication.
- Unknown or malformed saved-set payloads fail explicitly rather than silently
  replacing valid data.
- Saved sets participate in database backup and restore.
- Stable set and track identifiers survive application restart.
- Public saved-set responses remain versioned before their shape changes.

## Consequences

Saving and editing require the local application backend, but the result now
survives browser data loss and follows the same durability boundary as the
catalog. Browser-only fallback data must never overwrite a newer backend copy.

## Revisit when

Multi-user synchronization, remote collaboration, or a non-SQLite persistence
boundary becomes an actual product requirement.

