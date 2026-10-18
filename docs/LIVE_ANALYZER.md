# Live Transaction Analyzer

A presentation interface for the existing verified financial model. The whole
application remains a research/demo prototype. Financial inference is genuine;
transaction enforcement and audio/video detector observations remain simulated.

## Judge workflow

Open the existing HTML dashboard after an operator manually starts the reviewed
application version. No commands, JSON editing, packages or notebook are needed
during the presentation:

1. Use **Transaction analyzer** in the left navigation.
2. Enter a transaction type, amount, sender/recipient balances before the
   transaction, and simulation step. All five values are required.
3. Optionally choose **Low model score**, **Intermediate model score**, or
   **High model score**. These populate editable inputs only, not predictions.
4. Click **Analyze Transaction**. The backend runs the existing portable model;
   the panel displays the actual score, FRAUD/NOT_FRAUD classification, the
   inclusive 0.30 threshold, score indicator and model identity.
5. Change any input or choose another example and analyze again without refresh.
   Changing inputs hides stale results. Errors never substitute a score.

Amounts/balances are in the original PaySim simulation units, **not USD**, and
nothing converts them. `step` is the positive whole-number PaySim simulation
counter (hourly steps), **not a calendar date or an event timestamp**. The analyzer
accepts only the five supported transaction categories, positive finite amounts,
nonnegative finite balances and positive safe-integer steps (up to 2^53 - 1).
These checks apply to this new transaction form/API; existing event API validation
and the underlying inference contract remain unchanged.

The uncalibrated 0–1 score is not a real-world fraud probability. Model
classification uses `score >= 0.30`. The score is not converted into the separate
0–100 fusion risk index, and FRAUD does not mean a real account was frozen.
A NOT_FRAUD result does not guarantee legitimacy or approve a payment.

## Read-only API

### POST `/api/financial/analyze`

Use the same local API server, Host/Origin checks, JSON/body limits and timeout
behavior as existing routes. Request example:

```json
{"features":{"type":"CASH_OUT","amount":8838.19,"oldbalanceOrg":8838.19,"oldbalanceDest":15334.27,"step":714}}
```

HTTP 200 returns `financial_ml` from the existing `FinancialModel.assess`, including
its actual score, classification, threshold, inference version, hash and advisory
semantics. It also returns validated `features`, `advisory_only=true`,
`enforcement="none"`, `persisted=false`, `research_demo=true`, and a units notice.
Missing/extra fields, invalid categories/types/ranges, non-finite numbers and
fractional steps return meaningful HTTP 400 errors without a model result.
Existing 403/413/415 request guards apply. Repeated submissions are independent
read-only calculations; there are no IDs to collide or records to duplicate.

This endpoint does **not** call `Engine.submit`, insert transactions, mutate
settings, change risk assessments, create decisions, alter cooling blocks, or
rewrite audit/history records. Inputs/results are not persisted. It provides a
prediction, not a simulated policy decision. Existing `/api/events` remains the
separate path for persisted mock telemetry and fusion analysis.

### GET `/api/financial/samples`

Returns three editable feature objects and the current model identity, never
precomputed scores. Input provenance is in `demos/financial_samples.json`:

| Sample | Zero-based reference index | Purpose |
| --- | --- | --- |
| Low model score | 51 | Lower model output example |
| Intermediate model score | 5 | Intermediate model output example |
| High model score | 63 | Higher model output example |

All samples come unchanged from the supplied verified 100-case reference set.
Tests compare those inputs to their reference records and calculate their scores
using the actual model. The labels describe **model output**, not known fraud
outcomes or calibrated risk. Selecting a sample runs no prediction; Analyze
always issues a new backend request, including after edits.

## Implementation and deployment

`analyzer.py` validates presentation inputs and calls the existing standard-library
financial evaluator; it contains no alternative inference. The HTML/CSS/JS extends
the current offline dashboard with a sidebar, accessible labels/help, inline
validation, loading/success/error states, keyboard focus, reduced-motion handling,
responsive layout and separate model/fusion views. JavaScript only gathers inputs,
requests and renders backend results. No React, Node, CDN, font download, sklearn,
ONNX Runtime or serving dependency is introduced.

The existing operator startup command serves the new page and endpoints. For a
manual LinuxONE update, follow the reviewed revision/backup/target-test process in
[FINANCIAL_MODEL.md](FINANCIAL_MODEL.md), then manually restart through your usual
operator workflow. No automatic deployment, restart, remote access or changes to
the running IBM LinuxONE instance were performed in this task. Tests here used
Python 3.12.14/x86_64; run them on s390x before presentation deployment.

The default suite needs only stdlib and temporary SQLite databases:

```bash
PYTHONPATH=src python3.12 -S -m unittest discover -s tests -v
```

The optional existing browser smoke script requires already available Playwright
and Chromium, only as development test tools. Neither Node nor Playwright is a
serving requirement. The optional Streamlit dashboard is unchanged; the Live
Transaction Analyzer is in the HTML dashboard.
