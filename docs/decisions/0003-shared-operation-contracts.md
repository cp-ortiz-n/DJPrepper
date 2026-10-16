# ADR-0003: Shared operation contracts, specialized executors

- Status: Accepted
- Date: 2026-10-15

## Context

Imports, processing jobs, metadata batches, library maintenance, and Set Builder
planning all report long-running work, but they have different recovery,
rollback, persistence, cancellation, and retry needs. A universal executor would
either erase those differences or accumulate feature switches.

## Decision

Background operations share immutable status, capability, error, timestamp, and
action-receipt vocabulary from `infrastructure/operation_lifecycle.py`. Each
feature keeps its focused executor and durable state. Metadata-style batches may
use the shared batch registry; unrelated workflows use adapters that normalize
their lifecycle for internal consumers without changing existing public APIs.

## Compatibility guarantees

- Existing endpoint shapes and terminal status meanings remain compatible.
- Every operation reports what was requested, what changed, failures, durable
  destinations, and restart durability when applicable.
- Unsupported cancel or retry actions are explicit capabilities, not no-ops.
- Recovery and rollback remain owned and tested by the feature that performs the
  work.

## Consequences

Some executor code remains intentionally separate. Conformance tests target the
shared lifecycle contract, while feature tests cover persistence, recovery, and
side effects.

## Revisit when

Multiple operation families acquire genuinely identical execution and recovery
semantics, demonstrated by implementations rather than superficial status-name
similarity.

