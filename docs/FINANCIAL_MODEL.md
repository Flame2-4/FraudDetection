# Financial ML integration

This change adds actual trained-model inference to the existing simulation backend.
All payment actions remain simulated; audio/video signals remain simulated inputs.
It does not train a model, access a bank or deploy a service.

## Runtime and policy contract

`src/fraudguard/financial.py` uses only Python's standard library. It loads the
pinned local `models/financial/portable_model.json`, rejects changed bytes, limits
input file size, validates finite values and supported acyclic tree structure,
and compiles immutable node tuples. It never executes the supplied Python verifier,
loads pickle/joblib, or imports NumPy, sklearn or ONNX Runtime.

Inference follows the verified export: four numeric values in trained order plus
five category indicators, <= splits, sequential sums of already-scaled leaves,
then a numerically stable sigmoid. Unknown category strings get an all-zero
one-hot vector, matching the exported OneHotEncoder contract; `category_known`
is false. Missing features, booleans, strings posing as numbers, overflow, NaN and
Infinity are rejected. Nothing imputes balances or derives model `step` from UTC.

Two outputs have deliberately separate meanings:

| Output | Meaning and threshold |
| --- | --- |
| `financial_ml.score` | Actual trained financial model score in [0,1], uncalibrated |
| `financial_ml.is_fraud` | `score >= 0.30`, inclusive; positive class 1 |
| Existing `risk_index` and `decision` | Fusion rules unchanged: <40 APPROVE, 40–75 VERIFY, >75 FREEZE; active simulated blocks still override |

**ML is advisory in this integration.** No new fusion weight or automatic freeze
rule has been invented. A high model score can coexist with fusion APPROVE; a
model-negative payment can still be simulated FREEZE under an existing block.
A later policy change to make ML affect fusion requires explicit design and
validation; multiplying a model score by 100 is not a calibrated fusion policy.

## Backward-compatible event input

Existing API paths, event types, required payment fields, demos, thresholds,
cooling logic, history pagination and simulation flags remain supported. Payments
may now additionally provide `data.financial_features`, with exactly these keys:

```json
{
  "step": 659.0,
  "type": "PAYMENT",
  "amount": 23162.1,
  "oldbalanceOrg": 0.0,
  "oldbalanceDest": 0.0
}
```

These are original model units/semantics, not the outer envelope's event type or
an automatic conversion from `amount_minor`. A caller must explicitly establish
consistent units and provenance for its use case. The synthetic wrapper below
chooses USD minor units only as a local demo convention, not a claim about PaySim
currency. Do not invent missing balances, account links or dataset time origins.

From the repository root, with a manually started test server:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/events \
  -H 'Content-Type: application/json' \
  -d '{"schema_version":1,"simulated":true,"event_id":"financial-example-1","event_type":"payment","timestamp":"2026-01-01T12:00:00Z","tenant_id":"financial-demo","user_id":"fictional-user","device_id":"fictional-device","source_id":"mock-paysim","data":{"amount_minor":2316210,"currency":"USD","new_payee":false,"financial_features":{"step":659.0,"type":"PAYMENT","amount":23162.1,"oldbalanceOrg":0.0,"oldbalanceDest":0.0}}}'
curl -sS 'http://127.0.0.1:8000/api/assessment?tenant_id=financial-demo&user_id=fictional-user&device_id=fictional-device'
```

The result includes `financial_ml.status="scored"`, score approximately
0.0004521563016246734, threshold 0.3, `is_fraud=false`, classification NOT_FRAUD,
model/inference version, model SHA-256, event ID/time, uncalibrated semantics and
`fusion_effect="advisory_only"`. It remains a simulated financial action even
though its ML inference is real. No actual-fraud label is passed to inference.

Without financial features, the payment's ML result is `unavailable`, with null
score/classification rather than a fabricated zero. The legacy three scenarios
therefore remain 0/APPROVE, 45/VERIFY and 100/FREEZE with ML unavailable. An
assessment reports the latest payment in its same-tenant/user/device causal
window (timestamp/event ID ordering), not the highest model score. A newer
unscored payment does not inherit an older payment's ML result; an expired window
returns no payment score. Audio/video observations cannot supply financial features.

## Storage, history and model provenance

New assessment and payment-decision JSON payloads persist ML score, classification,
threshold, hash and inference version within the existing atomic transaction.
The raw event preserves the five inputs. Replay/deduplication and out-of-order
recomputation retain deterministic behavior; no extra payment actions occur.

SQLite gets an additive `settings.financial_model` binding. Its identity includes
the artifact hash, inference version, threshold and advisory policy. A later
identity mismatch refuses startup; it does not silently rescore old records with
a new model. Existing history is not rewritten on upgrade. Old history records
without an ML key remain readable and the dashboard displays ML unavailable.
The assessment endpoint computes the current view using the validated model.
Existing history is still a latest deterministic projection, not a newly claimed
immutable compliance audit. No new authenticated human-review control is claimed.

The default HTML dashboard shows the actual model score, >=0.30 classification,
source payment, version/hash, and ML history next to the existing fusion/cooling
views. Its legacy controls and offline assets remain. The optional Streamlit
adapter displays the same ML JSON; its third-party runtime remains unverified.

## Verification and manual LinuxONE upgrade

The user reports the original portable model passed on s390x. This task ran the
same 100-case parity check and the complete integration suite on CPython 3.12.14,
x86_64. These are distinct claims; no new integrated s390x deployment was run.

1. Arrange a maintenance window and record the current code revision. Stop only
   your FraudGuard process using its usual service manager or foreground Ctrl-C.
2. Back up the synthetic SQLite database using SQLite's backup facility (and
   preserve the old code revision). For the default path, for example:

   ```bash
   python3.12 -c "import sqlite3; s=sqlite3.connect('var/fraudguard.sqlite3'); d=sqlite3.connect('var/fraudguard-before-financial.sqlite3'); s.backup(d); d.close(); s.close()"
   ```

3. Update the existing checkout to the reviewed integration revision. No pip
   installation, retraining, joblib conversion, OS changes or hardware acceleration
   is needed. Ensure the `models/financial/` artifact is included in deployment.
4. Check the actual target and run both parity and regression gates:

   ```bash
   uname -m
   python3.12 --version
   python3.12 tools/fraudguard_portable_verify.py models/financial/portable_model.json tests/fixtures/financial_reference_predictions.json
   PYTHONPATH=src python3.12 -S -m unittest discover -s tests -v
   ```

   Require all 100 references to match and zero >=0.30 classification mismatches.
   The supplied verifier's tolerance is 1e-6; integrated reference tests use 1e-12.
   Do not relax these gates to hide discrepancies. `-S` excludes site packages
   to confirm the backend/test suite needs no third-party Python dependencies.
5. Only after those checks, manually start the service with its original DB and
   policy options, e.g. `PYTHONPATH=src python3.12 -m fraudguard serve`. Check
   `/api/health`, the three legacy demos, the example payment above, persistence
   across a manual restart, and dashboard display through your existing SSH tunnel.
   No public bind or real payment endpoint is introduced.

For rollback, restore the database backup together with the previous code; old
validators do not understand the new optional financial-feature payload.

No automatic rollout/restart is included. This task does not touch the running
server, production databases or LinuxONE instance. Keep the existing local-only,
synthetic-data and access restrictions; trained inference does not add banking
security, calibration or a real payment intervention mechanism.
