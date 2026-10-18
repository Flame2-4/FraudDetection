# Implemented MVP and design revisions

This is the follow-up implementation authorized after Phase 1. `AGENTS.md`,
`REFERENCES.md` and `ARCHITECTURE.md` remain byte-for-byte unchanged. Their Phase 1
scope restrictions were historical; the new user request authorizes this phase.
Implementation followed engine → mock scenarios → scoring/intervention → dashboard
→ local testing. Actual LinuxONE deployment remains unverified. A subsequent authorized integration
adds portable financial ML as documented in [FINANCIAL_MODEL.md](FINANCIAL_MODEL.md);
Phase 1 research files remain unchanged.

## Module boundaries

- `src/fraudguard/models.py`: strict versioned synthetic event schema, safe
  fictional identifiers, canonical timezone-aware timestamps and strict JSON.
- `policy.py`: transparent fusion rules, quality scaling, group caps, pair interactions,
  threshold mapping and persisted configuration; financial ML is separate.
- `storage.py`: SQLite schema and transaction-scoped connections.
- `engine.py`: deduplication, deterministic correlation, persistence, historical
  recomputation, snapshots and user-scoped simulated cooling blocks.
- `demos.py`, `demos/*.json`: fixed original synthetic fixtures and idempotent replay.
- `api.py`, `__main__.py`: local-only standard-library JSON/asset server and CLI.
- `dashboard/`: offline HTML/CSS/JS and optional Streamlit API presentation adapter.
- `tests/`: standard-library unit and local HTTP integration tests.

## Differences from the research proposal

The research architecture describes a larger future system. This MVP deliberately
uses bounded deterministic batch/event replay instead of a production watermark
engine, broker, distributed feature store or authenticated media ingestion.
Timestamp year bounds are validated, but there is no wall-clock future-event
rejection because fixtures replay historical or prospective synthetic timelines.
Device telemetry includes new-device and failed-login/session warning signals.
Events optionally carry a validated fictional `session_id` for history/context;
correlation intentionally keys on tenant/user/device across sessions within the
window, as requested. There are no measured clock offsets, authentic device attestations or trustworthy
identity links: IDs are caller-supplied fictional keys, not verified identities.

The earlier sigmoid proposal is replaced with explicitly additive rule/group
points and nonlinear pair interactions, capped at 100. This follows the new
request for transparent explainable scoring and exact 40/75 thresholds. The
explanations expose awarded/capped contributions and cross-channel bonuses.
Grouping limits duplicate media evidence; it is not a statistical independence
proof. The index is not calibrated and does not measure fraud probability.

The earlier abstract intervention states map to requested `APPROVE`, `VERIFY`,
`FREEZE` labels, always marked simulated. Blocks last exactly 60 event-time
minutes; they cover all devices for the same tenant/user. No network code talks
to payment services. Human review is documented, but no authorization, reviewer
mutation, live alert delivery or appeals service is implemented.

## Determinism, out-of-order events and atomicity

1. Validate all events in a batch before any database write; accept only synthetic
   schema v1 events. Canonicalize UTC timestamps to fixed-width microsecond text.
2. Acquire a SQLite `BEGIN IMMEDIATE` transaction, check conflicts/capacity and
   insert genuinely new tenant/event IDs with parameterized SQL. Identical
   duplicates are no-ops; changed payloads conflict and roll back the whole batch.
3. Recompute affected users from persisted raw events sorted by `(timestamp,
   event_id)`. An event may correlate only with prior events in that ordering,
   within `[event_time - window, event_time]`, on the same tenant/user/device.
   At equal timestamps, lexical event ID decides order. Queries at an explicit
   timestamp represent the end of that instant (include all events at that time).
4. Score the causal prefix. Start a block only when a **payment** scores FREEZE
   without an existing active block. While active, any payment for that tenant/user
   is simulated FREEZE regardless of device/current score; expiry never extends.
   Active means `start <= event_time < expiry`. Fresh high-risk payment after
   expiry can start another block. Future blocks never affect historical events.
5. Replace assessments, payment decisions and block projections for the affected
   user within the same transaction; readers see a consistent snapshot.

Final projections are identical for the same validated event set and policy,
regardless of arrival order, including byte-identical explanation content. A
late event can change an earlier answer and block timeline. Submitted event data
is retained, but previous decision revisions are **not** retained as an immutable
audit log. This replay simulator cannot be used to model irreversible live side
effects. The API does not freeze an account, and backdated submissions are not a
security mechanism for a real service. Repeated events cannot bypass a block at
a fixed event time; callers can intentionally advance the synthetic clock.

A request accepts at most 100 events/64 KiB; event storage is capped (defaults
2,000 per user, 50,000 total). Correlation state is window-limited, and recompute
is bounded by the user cap, but it is not optimized for production throughput.
History pagination returns at most 200 items. No real-time SLA is claimed.

## Rules and confidence

| Rule | Weight before group caps |
| --- | --- |
| Large payment | 20 |
| New beneficiary | 15 |
| Three payments within correlation window | 15 |
| New device | 20 |
| At least three failed logins | 15 |
| Suspicious simulated call | 15 |
| Simulated audio suspicion × quality | 25 × strength |
| Simulated video suspicion × quality | 25 × strength |

Large-payment minor-unit thresholds are independent scenario settings: USD
500,000; EUR 500,000; GBP 400,000; JPY 750,000. They are not exchange rates. Other
currencies are rejected. No float arithmetic represents payment amounts.

Within each rule, repeated warnings are not summed; evidence IDs are listed.
For media suspicion, select the maximum risk×quality observation per modality,
with lexical ID tie-breaking; round decimal contributions half-up to integers.
Factors are allocated in the fixed rule order above within payment/device/media
caps of 40/30/30. Zero awarded points remain visible when a group cap was exhausted.
For each pair of active warning groups, add 10 points. Bound the final index to
100 and expose the cap adjustment so explanations reconcile exactly.

Audio/video quality is caller-supplied and simulated, not measured confidence.
No real detector, feature extractor or reliability calibration is implemented.
Missing-channel lists accompany the score; the exact user-specified thresholds
still map low index to APPROVE. Therefore APPROVE with missing data is a scenario
policy result, never a safety guarantee. Reviewers should consider uncertainty
and benign alternatives before any future real-world decision.

## Security and privacy boundaries

The local API validates identifiers/types/ranges, rejects ambiguous JSON and large
requests, uses parameterized SQL, bounds stored event counts, applies request read
timeouts, rejects cross-origin/foreign-Host requests and serves a restrictive CSP.
HTML uses DOM `textContent` for untrusted data, with no CDN or dynamic HTML injection.
These controls are tested but are not a production security certification.

There is no authentication, authorization, tenant access control, TLS, database
encryption, durable reviewer audit, distributed rate limiting or automated
retention. Tenant scoping prevents accidental correlation, not access by a local
caller. Anyone with local access can submit synthetic IDs or query other tenants.
Keep it on loopback, use only fictional data, restrict filesystem/SSH access, and
do not run in an untrusted multi-user environment. Never put secrets or real
recordings in the database. The Phase 1 retention/privacy/security policies are
future requirements, not controls already implemented in this MVP. Export or
remove only stopped, disposable synthetic databases according to local policy.

Streamlit remains optional because its s390x dependency chain is unverified; the
offline HTML console fulfills the portable dashboard path without that chain.


## Financial model extension

`financial.py` now performs trained financial inference from a pinned JSON model
using only the standard library. Payment schemas optionally accept five explicit
features; assessment and decision payloads persist the actual score, >=0.30
classification and model identity. This is advisory alongside the preserved
fusion rules, not a new payment freeze rule. Audio/video detectors remain
simulated. See [financial model integration](FINANCIAL_MODEL.md) for validation,
backward-compatible database binding and manual deployment instructions.
