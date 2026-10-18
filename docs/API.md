# Local JSON API (simulation only)

Start from the repository root:

```bash
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 serve
```

Default base: `http://127.0.0.1:8000`. No authentication or TLS is implemented.
The CLI accepts only localhost/127.0.0.1 binds. No CORS access is granted. Requests
with foreign Host/Origin headers are rejected. This protects a local demo; it is
not identity verification, authorization, or a production deployment boundary.

## Routes

| Method / path | Request | Response |
| --- | --- | --- |
| GET `/api/health` | No query | Status, simulation flag, policy; checks SQLite access |
| GET `/api/scenarios` | No query | Available scenario names |
| POST `/api/events` | One event object or `{"events":[...]}` | New/duplicate counts and deterministic assessments |
| POST `/api/demos/normal` | `{}` | Normal fixture replay |
| POST `/api/demos/verify` | `{}` | Verification fixture replay |
| POST `/api/demos/freeze` | `{}` | Freeze fixture replay |
| GET `/api/assessment` | `tenant_id`, `user_id`, `device_id`; optional `at` | Current/as-of score, explanation, simulated decision and active block |
| GET `/api/events` | `tenant_id`; optional `user_id`, `limit`, `offset` | Synthetic event history |
| GET `/api/assessments` | Same history query | Assessment history for all event types |
| GET `/api/decisions` | Same history query | Payment-decision history |
| GET `/api/blocks` | Same history query | All simulated block records, including expired blocks |
| GET `/` | None | Offline HTML dashboard; JS/CSS served at `/dashboard.js`, `/dashboard.css` |

History is descending by `(timestamp,event_id)`; defaults `limit=100`, `offset=0`,
maximum 200/page. Blocks sort by start/trigger ID. History payloads use
`{"items":[...],"limit":100,"offset":0,"simulated":true}`. Histories contain the
latest recomputed projection; concurrent new/backdated events may change page
contents. Block history alone does not establish whether a block is currently
active; use an assessment at a specified timestamp.

## Event schema and example

All envelope fields in the example below are required; an additional optional
`session_id` may identify a fictional authentication/call session. Unknown fields
are rejected. Session IDs use the same identifier constraints; they are context,
not authenticated identity or a required correlation key. IDs use
1–80 ASCII letters/digits/`_.:-`, and identify fictional data only. Event IDs are
unique **within a tenant**. Types: `payment`, `device`, `call`, `audio`, `video`.
Timestamps require ISO-8601 with seconds and timezone, years 2000–2100, up to six
fractional digits; normalized UTC is returned. Only integer `schema_version=1`
and literal `simulated=true` are accepted. Source IDs are caller-supplied
provenance labels, not authenticated sources.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/events \
  -H 'Content-Type: application/json' \
  -d '{"schema_version":1,"simulated":true,"event_id":"manual-payment-1","event_type":"payment","timestamp":"2026-01-01T12:00:00Z","tenant_id":"sandbox","user_id":"fictional-user","device_id":"fictional-device","source_id":"mock-payment","data":{"amount_minor":2400,"currency":"USD","new_payee":false}}'
```

Data objects have exactly these fields:

| Type | Required data and constraints |
| --- | --- |
| payment | `amount_minor`: integer 1–1,000,000,000,000 (booleans rejected); `currency`: USD/EUR/GBP/JPY; `new_payee`: boolean |
| device | `new_device`: boolean; `failed_logins`: integer 0–10,000 |
| call | `suspicious`: boolean; manually simulated flag, no speech analysis |
| audio | `spoof_risk`: number [0,1]; `quality`: number [0,1]; `observation_id`: fictional identifier |
| video | `manipulation_risk`: number [0,1]; `quality`: number [0,1]; `observation_id`: fictional identifier |

Audio/video inputs are simulated suspicion, **not real deepfake detection**.
Finite JSON numbers only; duplicate JSON keys are rejected. Batches are atomic:
any invalid event, conflict or capacity failure rolls back the whole submission.
Identical events (after UTC normalization) are reused; changed contents under
an existing tenant/event ID cause a 409 conflict. Numeric JSON representation
changes such as `1` versus `1.0` can be a content conflict: replay identical fixtures.

POST success: HTTP 201 when at least one new event was accepted, 200 when every
event was an identical duplicate. Example response shape below is **abridged**;
actual assessments also include versions, windows, coverage and explanations:

```json
{
  "simulated": true,
  "accepted": 1,
  "duplicates": 0,
  "assessments": [{"event_id":"manual-payment-1","risk_index":0,"decision":"APPROVE","base_decision":"APPROVE","active_block":null,"simulated":true}]
}
```

## Assessment semantics and cooling boundaries

```bash
curl -sS 'http://127.0.0.1:8000/api/assessment?tenant_id=demo&user_id=fictional-freeze&device_id=device-freeze&at=2026-01-01T13:01:59Z'
curl -sS 'http://127.0.0.1:8000/api/assessment?tenant_id=demo&user_id=fictional-freeze&device_id=device-freeze&at=2026-01-01T13:02:00Z'
```

After loading the freeze fixture, the first returns risk 0/base APPROVE but final
FREEZE due to the active block; the second returns APPROVE with no active block.
The block starts at `2026-01-01T12:02:00.000000Z` and expires at
`2026-01-01T13:02:00.000000Z`. The start is inclusive, expiry exclusive. It is
user-scoped across devices within the tenant. Repeated events do not extend it.

Without `at`, use the latest event time for that tenant/user, including all events
at that instant. With no events and no `at`, return 400; an explicit `at` can
return an empty-evidence assessment (index 0 with all channels missing). A GET
assessment never creates a block or payment decision. Only submitted payment
events can activate a block; non-payment high scores are warning assessments.

Each assessment reports `risk_index`, `raw_points`, `cap_adjustment`, `factors`
(rule, weight, strength, awarded points, evidence IDs, explanation), `interactions`,
observed/missing channels, correlated IDs, window, `base_decision`, final `decision`,
`decision_reason`, `block_enforced`, and `active_block` with start/expiry.
Submitted-event assessments also contain `event_id`, `event_type`, `block_activated`.
All carry `simulated=true`. Neither scores nor user/device links are calibrated.

Out-of-order submissions recompute affected users in `(event time,event ID)`
order. Earlier decisions may change, but replaying the same set converges to
identical projections without duplicate rows. There is no immutable revision
history or live side effect. Changing synthetic time is allowed; this is not a
real-time fraud-prevention enforcement service.

## Errors and resource limits

POST requires one Content-Length, `Content-Type: application/json`, no transfer
encoding, 1–65,536 bytes and at most 100 events. Socket read timeout is five
seconds. URL length is capped at 4,096 characters. All SQL values are bound;
table/ordering choices come from internal allowlists. Unknown/duplicate query
parameters are rejected. SQLite contention may return 503; retry the same IDs.

| Status | Meaning |
| --- | --- |
| 400 | Invalid JSON/schema/parameters, unknown demo, invalid transfer encoding |
| 403 | Foreign Host or cross-origin request |
| 404 | Unknown route/static path |
| 409 | Same tenant/event ID with different contents |
| 411 | Missing or repeated Content-Length |
| 413 | Empty or oversized body |
| 414 | Oversized URL |
| 415 | Unsupported content type |
| 429 | Local event-count capacity reached (not a production rate limiter) |
| 503 | Database temporarily unavailable/busy |
| 500 | Unexpected internal error, details not returned to callers |

Example validation response: `{"error":"only simulated=true events are accepted","simulated":true}`.
No sensitive payloads are intentionally logged. Standard-library HTTP serving
is for local development, not a hardened internet-facing service.
