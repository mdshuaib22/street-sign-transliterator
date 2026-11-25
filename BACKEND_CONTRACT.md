# SignLens — Backend Service Contract (prepared, not observed)

Status: prepared from source inspection on 2026-11-25. No server was started, no endpoint was called, no test was run, and no code was changed. A contract is not a running service.

## backend_service_contract/v1

Surface (observed in `main.py`):

| Endpoint | Operation | Safe / idempotent | Caller class | Request | Response (observed) | Rate / latency / payload bound |
| --- | --- | --- | --- | --- | --- | --- |
| `GET /` | Serve `index.html` via `FileResponse` | Safe | public browser | none | `text/html` | unknown / unknown / not applicable |
| `GET /api/health` | Liveness probe | Safe | public browser, machine probe | none | `{"status":"ok"}` | unknown / unknown / not applicable |
| `POST /api/upload-image` | Decode → preprocess → OCR → translate → encode preview | No persisted effect; idempotent by input, but each call spends an upstream translation request | public browser | `multipart/form-data`: `file` (required), `language` (form string, default `en`) | `{"confidence": float, "detected_text": str, "translated_text": str, "preprocessed_image": str}` | unknown / unknown / unknown |

Supporting domain modules: `vision.py` (decode, grayscale + Otsu threshold, base64 PNG), `ocr.py` (Tesseract `image_to_data`, average confidence), `translator.py` (deep-translator `GoogleTranslator`, source `auto`).

Concurrency and integrity: the endpoint keeps no state and writes no rows, so uniqueness constraints, stored idempotency keys, and lost-update guards are not applicable today. The retry guard that *is* needed is a client-side bound: a replay duplicates the upstream translation call. If scan history is added later, every write two requests can reach must name its guard before handoff.

Boundaries that are **not** in this contract: no auth endpoints are designed. The trust model is unresolved (see auth map), so adding login/session endpoints would assume a decision the repository does not make.

Blocking inputs still unknown from the repository: expected request rate, latency target, maximum upload size, deployment exposure, and whether the app is reachable outside localhost. Rate limits, timeouts, and payload caps must not be chosen until these are answered.

## auth_boundary_map/v1

| Path | Caller class | Authentication | Authorization | Failure mode when missing |
| --- | --- | --- | --- | --- |
| `GET /` | public browser | none | none | any internet caller reaches the app shell |
| `GET /api/health` | public browser, machine probe | none | none | any caller can probe availability |
| `POST /api/upload-image` | public browser | none | none | any caller can spend OCR and translation resources; no per-caller attribution |

Where trust changes today: **nowhere on the server.** `index.html` has a demo login gate (`DEMO_AUTH`, `handleLogin`) that compares email and password in client-side JavaScript and hides a DOM section on success. It sends no credential and no token to the API. It is a UI state, not an authentication boundary.

Additional observed risk: `CORSMiddleware` uses `allow_origins=["*"]` together with `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. Any origin can drive the API from a browser.

Authentication (who) and authorization (may they) are deliberately separate rows once a model is chosen. Stop condition: do not design login, token, or per-user routes until the owner states the trust model, where identity is established (proxy, middleware, or dependency), and what an authenticated caller may do that an unauthenticated one may not.

## error_path_table/v1

Current handling versus the required contract. "Current" is observed source behaviour; "required" is the proposed contract, not implemented.

| Failure mode | Current behaviour | Required status / code | Required body shape | Retryable | Log / redaction |
| --- | --- | --- | --- | --- | --- |
| Missing `file` part | FastAPI 422 | 422 `validation_error` | error envelope with field path `file` | no | log field name, never file bytes |
| Invalid `language` code | upstream error string returned inside HTTP 200 `translated_text` | 422 `unsupported_language` | error envelope with field path `language` and allowed values | no | log requested code |
| Undecodable / corrupted image | `ValueError` → catch-all → 500 with raw `str(e)` | 422 `invalid_image` | error envelope, no exception text | no | log decode result, never body |
| Empty OCR result | HTTP 200 with `detected_text: "No text detected."` | 200 with explicit `detected_text: null` plus `no_text` status, or 422 — owner decision | success envelope with a machine-readable status | no | log confidence and word count |
| Translation upstream unreachable | HTTP 200 with `translated_text: "[Translation Error]…"` | 503 `translation_unavailable` | error envelope, `Retry-After` | yes, bounded backoff | log upstream identity and duration |
| Translation upstream timeout | no timeout configured; library default applies | 504 `upstream_timeout` | error envelope | yes, bounded backoff | log duration and budget |
| Tesseract binary missing | catch-all → 500 with raw OS path/string | 503 `ocr_unavailable` | error envelope | yes, after operator action | log dependency identity, never stack trace to client |
| Payload over bound | none; whole body read into memory | 413 `payload_too_large` | error envelope naming the bound | no | log size, never bytes |
| Rate limit / quota | none | 429 `rate_limited` | error envelope naming limit, `Retry-After` | yes, after `Retry-After` | log caller class and limit, never credentials |
| Frontend source file missing | `FileResponse` raises → 500 | 500 `internal_error` | error envelope, no detail | no | log absolute path server-side only |
| Any unhandled exception | 500 with `detail: str(e)` | 500 `internal_error` with request id | error envelope, no exception text | no | log stack server-side, redact inputs |

The 200-with-error-string rows are the most damaging: the frontend reads them as success and shows the error text as translated output. They must be converted to real error statuses, which is a breaking change graded below.

## response_shape_contract/v1

Observed: each endpoint invents its own bare object. There is no version, no request id, and no stable error code. The frontend branches on `payload.detail || payload.message || "Server error " + status`.

Proposed canonical shape for the whole surface:

- Success: `{ "version": 1, "request_id": "...", "data": { ...endpoint-specific payload... } }`
- Error: `{ "version": 1, "request_id": "...", "error": { "code": "stable_machine_code", "message": "human readable", "field_errors": [{"field": "language", "message": "..."}], "retryable": false } }`

Rules: clients branch on `error.code`, never on `message`; a field is absent or present, never sometimes `null`; one time representation across the surface; 429 and 503 carry `Retry-After`; no pagination exists today, so if scan history is added use one cursor style keyed on `(created_at, id)` with a server-side maximum page size.

Compatibility during the window: keep the current top-level fields on `/api/upload-image` alongside `data`, and keep `detail` on errors alongside `error`, so the deployed frontend keeps working while it migrates. Remove the legacy fields only at sunset.

## schema_migration_plan/v1

Not applicable. The service has no datastore, ORM, tables, or migration tooling; all state is in the request and the client. No expand/backfill/switch/contract order is required, and there is no migration rollback point to name.

If scan history, rate-limit counters, or stored idempotency keys are added, this section becomes applicable: load `omh-relational-db` and the schema-migration reference, and order each change as expand → backfill → switch → contract with a rollback point per step before any DDL is applied.

## consumer_impact_and_sunset/v1

Enumerated sources searched:

| Source | Result |
| --- | --- |
| This repository (all tracked files) | `index.html` is the only caller: `GET /api/health` at line 1344, `POST /api/upload-image` at line 1618. It reads `confidence`, `detected_text`, `translated_text`, `preprocessed_image`, and on errors `detail` or `message`. |
| Generated client packages | none found in the repository |
| Spec history / commits | three commits; no published spec file (`pom.xml` is empty, no OpenAPI document) |
| Access logs, user agents, partner registries | not available in this workspace |

External consumers: **`consumers_not_enumerable`**. The API is public and CORS is open to every origin, and Docker binds `0.0.0.0`, so callers outside this repository cannot be discovered from code. This is not a claim of zero breakage.

Per-consumer grading of the proposed changes:

- `index.html` (in-repo): changing the success envelope to `data.*` breaks every field read unless legacy top-level fields are kept during the window. Changing error statuses breaks the `payload.detail` fallback unless `detail` is kept.
- External callers (not enumerable): adding fields is safe; removing top-level fields or changing a status code may break retry and error logic. The open set lengthens the window and requires a public announcement.

Proposed evolution policy (owner decision pending — these dates are a recommendation, not an executed plan):

- Compatibility window: 2026-11-25 → 2027-02-23 (90 days), sized for an open consumer set.
- Migration path: frontend reads `data.confidence`, `data.detected_text`, `data.translated_text`, `data.preprocessed_image` with a fallback to the legacy top-level fields; errors read `error.code`/`error.message` with a fallback to `detail`.
- Announcement: a `CHANGELOG.md` entry in this repository plus a response header on both endpoints. A changelog nobody reads is prepared, not delivered.
- During the window: every response from the legacy shape carries `Sunset` (HTTP-date) and `Deprecation` (structured-field date) headers.
- Sunset: 2027-02-24, conditional on observed legacy traffic falling to zero or to a known set of consumers that accepted the break. After sunset the legacy shape returns 410 Gone with an error body naming the replacement.

## backend_implementation_handoff/v1

Executor: to be selected by the user. Stack: Python 3.11 (Docker), FastAPI 0.111.0, uvicorn 0.29, python-multipart, pytesseract with a Windows-pinned Tesseract binary in `ocr.py`, deep-translator 1.11.4. Datastore: none. No webhooks, queues, or connection pools today.

Read first: FastAPI's own routing, dependency-injection, and request-validation documentation, then `main.py` as the nearest sibling handler. Do not restate framework docs in the contract.

Implementation shape: `main.py::process_image` currently performs validation, orchestration, and error mapping in one handler. Split it so the handler parses and validates input, calls one domain function, and maps the result or typed error onto the envelope. Keep `vision.py`, `ocr.py`, and `translator.py` as the domain seams; a fake translator used by tests is the second implementation that earns that interface.

Test plan derived from this contract (when implementation is requested):

- One negative test per `auth_boundary_map/v1` row once the trust model exists — today all three rows are public, so the test asserts the known open behaviour rather than a guard.
- One negative test per `error_path_table/v1` row using the same Tesseract dependency and a fake translator with the same interface; no database stand-in is needed.
- Verify the frontend still reads both the legacy and canonical shapes during the compatibility window.
- Concurrency: two simultaneous uploads to a stateless endpoint must not share mutable module state; no stored idempotency key is required today.

Observed evidence: **not available**. No integration run, migration, load test, or deployment was performed for this contract.

## Open decisions (owner's to make)

1. Trust model for the API: remain public, or add an auth boundary (and where it is enforced).
2. Rate, latency, and upload-size targets — needed before any cap, timeout, or cache is chosen.
3. Whether the 90-day compatibility window and 2027-02-24 sunset date above are acceptable.
4. Whether `No text detected.` remains a 200 status with a machine-readable flag or becomes a 422.
