# DJPrepper development standards

These rules apply to every change in this repository.

## Architecture

- Preserve the modular monolith, FastAPI, SQLite, and vanilla JavaScript architecture.
- Follow package ownership and dependency direction in `docs/architecture/architecture.md`.
- Keep HTTP handlers focused on delivery; put reusable workflows in application/domain services.
- Keep SQL inside `audioextender/persistence/` or an approved migration boundary.
- Preserve authoritative musical calculations and existing scoring behavior. Do not duplicate shared musical policy.
- Add an abstraction only when it reduces real coupling, improves testing, or supports a replaceable implementation.

## Code quality and scope

- Keep changes focused; do not mix feature work, broad formatting, schema changes, and architectural restructuring.
- Introduce no unused or duplicate imports, unused variables, unnecessary dependencies, or avoidable duplication.
- Use clear names, explicit public contracts, appropriate typing, and intentional error handling.
- Resolve safe pre-existing issues in directly affected code; record unrelated debt instead of expanding scope.
- Preserve public APIs, stored data, saved sets, planning receipts, jobs, exports, and backup compatibility unless a change is explicitly approved.

## Testing and validation

- Add behavior tests for new behavior and regression tests for bug fixes when practical.
- Add characterization tests before risky refactoring. Cover important failures, cancellation, and recovery paths.
- Do not weaken assertions or replace behavior tests with source-string checks.
- During development, run focused lint/type/test commands. Before completion, run `./scripts/quality/check_quality.sh`.
- Run `./scripts/quality/check_coverage.sh` for significant refactoring and evaluate meaningful coverage changes.
- Run `./scripts/quality/run_stability_gate.sh` for high-risk persistence, import, relocation, export, or Set Builder changes.
- Never claim a check passed unless it was executed.

## Definition of done

- Requested work and appropriate tests are complete; existing behavior and compatibility are preserved.
- Modified code meets lint, type, formatting-ratchet, and architecture checks.
- No new architecture violations, unnecessary dependencies, unused code, or unrelated changes exist.
- Coverage regressions are evaluated where relevant; documentation and backlog are updated when needed.
- The final diff is reviewed and remaining risks are reported.

## Completion report

Every completed task must state what changed and why, files modified, tests run, lint/format/type results, coverage changes when measured, architecture-check results, and remaining risks.
