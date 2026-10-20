# API error contracts

All JSON API failures retain FastAPI's existing `detail` member for backward
compatibility and add a stable `error` object:

```json
{"detail":"Track not found","error":{"code":"not_found","category":"not_found","message":"Track not found","retryable":false}}
```

`detail` may remain a string, validation list, or feature-specific object.
Browser code displays errors through `apiErrorMessage`; new request clients use
`apiResponseJson` or `apiRequest`, which expose recovery metadata on
`ApiRequestError`.

## Status mapping

| HTTP status | Code | Category | Retryable |
| --- | --- | --- | --- |
| 400, 405, 413, 415, 422 | `validation_error` | `validation` | No |
| 404 | `not_found` | `not_found` | No |
| 408, 423, 429, 502, 503, 504 | `resource_unavailable` | `unavailable` | Yes |
| 409 | `conflict` | `conflict` | No |
| 499 | `canceled` | `canceled` | No |
| Other 5xx | `internal_error` | `unexpected` | Yes, except 501 |

A feature may provide a stable `code` in object-valued `detail`; status remains
authoritative for category and retryability. Responses also carry
`X-AudioExtender-Error-Code`.

## Exception ownership

- Routes and services raise `HTTPException` for expected delivery failures.
- `AudioExtenderError` reaching HTTP becomes an expected validation failure.
- The application boundary logs unexpected exceptions with request path and
  type, then returns a generic message without leaking exception text.
- Broad catches in background workers are justified when they record each item
  failure and let unrelated work finish.
- Broad catches around optional metadata, external tools, cache reads, or UI
  polling may degrade only to an explicit fallback state. New broad catches need
  a comment or a narrower exception.

Success payloads and legacy `detail` values are unchanged. Browser aborts remain
local canceled states. ARCH-004B will align feature-level background lifecycle
status, error, and receipt DTOs.
