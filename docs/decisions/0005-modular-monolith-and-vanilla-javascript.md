# ADR-0005: Modular monolith and vanilla JavaScript

- Status: Accepted
- Date: 2026-10-15

## Context

DJ Library Studio is a single-user local application. Its complexity has come
from blurred responsibilities in large modules, not from deployment scale or a
failure of FastAPI, SQLite, or browser ES modules.

## Decision

Keep one local FastAPI modular monolith, one SQLite persistence boundary, and a
vanilla JavaScript ES-module frontend. Improve explicit composition, focused
services, immutable state, and feature ownership instead of introducing
microservices or a frontend framework. `application.py` and `web/app.js` remain
composition and compatibility roots rather than feature owners.

## Compatibility guarantees

- The CLI and local web application continue to share domain and persistence
  modules in one installable project.
- Backend packages follow the documented inward dependency direction.
- Frontend features communicate through focused APIs/controllers rather than
  hidden global state.
- Framework or service extraction is justified by measured product or
  operational needs, not file size alone.

## Consequences

Module-size guards, ownership tests, and composition contracts are required to
prevent the monolith from becoming unstructured. Browser behavior is tested at
module and Playwright levels without adding a framework runtime.

## Revisit when

Independent deployment, multiple concurrent users, remote synchronization,
server rendering, or frontend state requirements create a demonstrated cost
that focused modules cannot address.

