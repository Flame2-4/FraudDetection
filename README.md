# FraudGuard AI

An original, local cross-channel fraud **simulation** using Python's standard
library, transparent rules and SQLite. It correlates fictional payments, device
telemetry, calls, and simulated audio/video suspicion. It now includes a trained
portable financial model when five explicit features are supplied. Audio/video inputs remain simulated: there is no real deepfake
detector, bank integration, money movement or real account freeze.
The heuristic fusion risk index and uncalibrated financial ML score are separate.

Target: Python **3.12**, CPU-only LinuxONE **s390x**. Current validation was on
Python 3.12.14 / x86_64 Linux, not LinuxONE. Core/API/offline dashboard need no
third-party Python packages. The original `src/fraud_detector.py` remains a legacy
starter and is not used by this application.

## Live Transaction Analyzer

The HTML dashboard now opens with an interactive transaction form. Enter the five
PaySim features or load an editable low/intermediate/high model-score example,
then click **Analyze Transaction**. The real backend model returns its score and
>=0.30 classification immediately; no Python commands are needed during judging.
The new analyzer is read-only: it does not save events or alter fusion decisions,
history or cooling-off blocks. Original PaySim units are preserved, with no USD
assumption. All enforcement remains simulated and audio/video inputs stay mocked.

See [the presentation workflow and read-only API](docs/LIVE_ANALYZER.md).

## Financial ML integration

Payment events can optionally include `data.financial_features` with `step`,
`type`, `amount`, `oldbalanceOrg`, and `oldbalanceDest`. Standard-library inference
returns `financial_ml.score`, `is_fraud` (score >= **0.30**), classification and
model provenance in API assessments, stored decisions and the dashboard. Missing
features mean ML unavailable, not zero. Fusion thresholds **40/75** and all cooling
behavior are unchanged; ML is advisory and does not silently create a new freeze
rule. Existing demos stay reproducible and explicitly simulated.

See [the input/API example, verification and manual LinuxONE upgrade](docs/FINANCIAL_MODEL.md).
The supplied model's s390x parity is user-reported; this integration was tested
locally, not deployed. Do not install joblib, sklearn or ONNX Runtime to serve it.

## Local development and startup

From the repository root (use the existing checkout):

```bash
python3.12 --version
PYTHONPATH=src python3.12 -m unittest discover -s tests -v
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 serve
```

The server binds `127.0.0.1:8000`; stop it with Ctrl-C. On a local machine, open
`http://127.0.0.1:8000/` for the offline HTML dashboard. It has no CDN, remote font
or internet dependency. Choose a scenario and click **Load / replay**. It shows
risk, simulated decisions, explanations, user/device correlation, missing channels,
block start/expiry and histories. Optional “As of” timestamps inspect event-time
expiry. This is not a production server; it implements no authentication, TLS,
encryption at rest or human-review authorization.

Cloud onboarding does not support a browser preview link; local HTTP requests
can validate the service. For a remote LinuxONE host use an approved SSH tunnel,
not a public bind. See [deployment](docs/DEPLOYMENT.md).

## Deterministic demo scenarios

```bash
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 replay normal
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 replay verify
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 replay freeze
```

| Scenario | Fictional behavior | Final risk | Simulated decision |
| --- | --- | --- | --- |
| `normal` | Known device, ordinary call and small payment | 0 | APPROVE |
| `verify` | New device and suspicious-call flag before a payment | 45 | VERIFY |
| `freeze` | Failed logins/new device, suspicious call, simulated audio risk and large new-payee payment | 100 | FREEZE |

All fixtures use fixed timestamps on 2026-01-01, tenant `demo`, users
`fictional-normal`, `fictional-verify`, `fictional-freeze` and corresponding
`device-normal`, `device-verify`, `device-freeze`. They contain no real customers
or recordings. Replays reuse stable event IDs. The accepted/duplicate counters
change on replay; assessments, decisions, blocks and database row counts do not.

The simulation clock is **event time**, not wall-clock time: a current assessment
without `at` uses that user's latest event timestamp. The freeze fixture activates
a block at `12:02:00Z` and expires at `13:02:00Z`. It is active on `[start, expiry)`;
at the exact expiry instant it no longer overrides the score. Late submissions
recompute affected historical simulated decisions, so prior answers may change.

## API examples

In a second terminal while the API is running:

```bash
curl -sS http://127.0.0.1:8000/api/health
curl -sS -X POST http://127.0.0.1:8000/api/demos/freeze \
  -H 'Content-Type: application/json' -d '{}'
curl -sS 'http://127.0.0.1:8000/api/assessment?tenant_id=demo&user_id=fictional-freeze&device_id=device-freeze'
curl -sS 'http://127.0.0.1:8000/api/assessment?tenant_id=demo&user_id=fictional-freeze&device_id=device-freeze&at=2026-01-01T13:02:00Z'
curl -sS 'http://127.0.0.1:8000/api/decisions?tenant_id=demo&user_id=fictional-freeze'
```

The current freeze assessment includes `"risk_index":100`, `"decision":"FREEZE"`,
`"simulated":true`, explanatory factors and an active block. At exact expiry
(without new signals), it returns index 0, `APPROVE`, and no active block.
See [the full API contract](docs/API.md) for event submission and response/error
examples, history pagination and request limits.

## Rules and persistence

Default bands: `<40` APPROVE; `40–75` VERIFY; `>75` FREEZE. When a payment exceeds
the freeze threshold, start a simulated 60-minute block for that tenant/user,
including attempts from other devices. Repeated events do not reset expiry.
During a block a payment can have risk 0 and decision FREEZE: the override is
explained separately from the score.

Payment/device/media groups have caps. Every pair of active independent warning
groups adds 10 interaction points (two groups +10, three groups +30), then total
risk is capped at 100. Call, audio and video share one media group; they are not
assumed independent. Quality scales simulated audio/video inputs. The output
includes weights, strengths, awarded contributions, evidence IDs and cap adjustment.
Missing observations mean unknown, not evidence of safety.

The default same-tenant/user/device correlation window is 120 seconds, inclusive
of both endpoints. Configuration is persisted with the database:

```bash
PYTHONPATH=src python3.12 -m fraudguard --db var/custom.sqlite3 \
  --window-seconds 300 --verify-threshold 40 --freeze-threshold 75 serve --port 8001
```

Use the same options on restart/replay; a policy mismatch fails instead of silently
mixing decisions. SQLite stores events, assessments, payment decisions and block
records atomically. It rejects changed content under an existing tenant/event ID.
History is the latest deterministic projection, not an immutable financial audit.
Limits: 100 events/request, 64 KiB body, 2,000 events/user and 50,000 total. There
is no automatic retention/deletion or production broker. Export/archive synthetic
data and use a new database when at capacity; do not remove a live database.

## Dashboard modes

- **Default/verified:** locally served offline HTML at `/`, started with the API.
  Works without Streamlit, NumPy, pandas, PyArrow or a package installation.
- **Optional/unverified:** `dashboard/streamlit_app.py` consumes the same API.
  It requires an independently verified compatible Streamlit environment:
  `python3.12 -m streamlit run dashboard/streamlit_app.py --server.address 127.0.0.1`.
  Start the API first. Optional `FRAUDGUARD_API_URL` defaults to the loopback API.
  Streamlit is not a core requirement and is not installed or runtime-tested here.
  A PyPI-only Python 3.12/s390x wheel-resolution attempt failed on NumPy; do not
  assume a universal Streamlit wheel makes its dependency stack portable.

## Tests and documentation

```bash
PYTHONPATH=src python3.12 -m unittest discover -s tests -v
```

Tests use temporary databases, deterministic synthetic data and only loopback
HTTP for API integration. They require no external network, external model downloads, GPU,
financial service or credentials. Tests cover schema/timestamps, boundaries,
linkage/window isolation, nonlinear explanations, permutations, duplicates,
persistence, cooling, API failures, concurrency, scenarios and replay.

- [Permanent instructions](AGENTS.md)
- [Phase 1 bibliography](docs/REFERENCES.md) and [original proposed architecture](docs/ARCHITECTURE.md), preserved unchanged
- [Implemented architecture and design revisions](docs/IMPLEMENTATION.md)
- [API](docs/API.md), [LinuxONE/local deployment](docs/DEPLOYMENT.md), [validation evidence](docs/VALIDATION.md)

For flagged cases, a future authorized reviewer must examine the evidence and
benign alternatives, independently verify the user, and record a disposition and
rationale. This MVP has no authenticated review-action endpoint; demo controls
only replay synthetic events. No simulated decision is a real financial action.
