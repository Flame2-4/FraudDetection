# Validation evidence

The original MVP results below are historical. Current financial integration
results are recorded in the final section of this document.

Executed 2026-10-18 in the current cloud environment. No LinuxONE/s390x host,
real customer data, trained model, financial service, GPU or proprietary
credentials were used. No application package dependencies were installed.

## Runtime observed

- CPython **3.12.14**.
- Architecture **x86_64**.
- Linux kernel **6.18.55**, glibc **2.41**.
- SQLite **3.53.1** (`sqlite3.sqlite_version`).
- Browser smoke checks used the environment's existing Playwright installation
  and system Chromium at `/usr/bin/chromium`; these are optional validation
  tools, not application/runtime/test-suite requirements.

## Executed checks

From the repository root:

```bash
PYTHONPATH=src python3.12 -m unittest discover -s tests -q
PYTHONPATH=src python3.12 tests/browser_smoke.py
node --check dashboard/dashboard.js
PYTHONPATH=src python3.12 -m fraudguard --db /tmp/fraudguard-cli-check.sqlite3 replay normal
PYTHONPATH=src python3.12 -m fraudguard --db /tmp/fraudguard-cli-check.sqlite3 replay verify
PYTHONPATH=src python3.12 -m fraudguard --db /tmp/fraudguard-cli-check.sqlite3 replay freeze
PYTHONPATH=src python3.12 -m fraudguard --db /tmp/fraudguard-cli-check.sqlite3 replay freeze
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 serve
```

- **53 unittest tests passed**. This includes thresholds 39/40/75/76; validation
  of types, optional session IDs, finite/range constraints, malformed/ambiguous
  JSON and timestamps; offset normalization; tenant/user/device separation;
  configurable inclusive time windows; duplicate/conflict atomicity; persistence;
  policy mismatches; capacity; exact additive explanation reconciliation and
  nonlinear escalation; media quality and group caps; and all scenarios.
- Out-of-order checks submitted every permutation of the four freeze events in
  separate temporary databases: all **24 permutations** converged to identical
  event, assessment, decision and block histories. No future event affected a
  prior prefix assessment.
- Cooling tests passed for activation, different-device attempts, repeated/replayed
  events, one microsecond before expiry, exact expiry, after expiry, historical
  queries, tenant isolation, and a fresh high-risk block after expiry.
- API integration passed real local HTTP success/error checks, SQLite-backed
  health/history, duplicate/concurrent submission, body limits, media type,
  cross-origin/foreign-Host rejection, static assets, and scenario replay.
- Process-level end-to-end checks against the CLI-started server passed: normal
  **0/APPROVE**, verify **45/VERIFY**, freeze **100/FREEZE**. A second replay
  returned zero accepted events and byte-equivalent assessment JSON objects.
  Persistent fixture totals were 10 events, 10 assessments, 3 payment decisions,
  and 1 block; replay did not add records. At exact block expiry, the API returned
  APPROVE with no active block.
- Chromium exercised actual dashboard controls for all scenarios, replay,
  rendered risk/history, active block start/expiry, exact expiry refresh and
  visible invalid-timestamp errors. A 390-pixel viewport had no body overflow.
  **No browser JavaScript errors or external/CDN requests** occurred in the
  passing run. The initial browser harness attempted an eval-style wait blocked
  by the app's CSP; the harness was corrected to use function predicates. The
  restrictive application CSP was preserved.
- `node --check` passed. Every Python source was parsed, including the optional
  Streamlit adapter; parsing is not Streamlit runtime validation.
- The final Git review checks the target branch, whitespace, changed-file scope,
  ignored database/cache artifacts and byte equality of the Phase 1 documents
  (`AGENTS.md`, `docs/REFERENCES.md`, `docs/ARCHITECTURE.md`) and legacy starter.

The default automated suite uses only stdlib and temporary databases, with
loopback sockets for HTTP integration and no external network. The optional
browser script requires already installed Playwright/Chromium; do not interpret
it as a new mandatory dependency or try downloading a browser during offline
unit tests.

## Expected dependency failure and unverified paths

The PyPI metadata and wheel-only resolution check documented in DEPLOYMENT.md
ran for Python 3.12/s390x. Resolution of Streamlit 1.66.0 failed with
`No matching distribution found for numpy<3,>=1.25.0`. This is a diagnosed optional
dependency limitation for the selected PyPI tags/version, not a failing core
check or proof that native/vendor builds cannot work.

**Not run:** Streamlit runtime/browser checks, actual s390x import/runtime tests,
LinuxONE deployment/load tests, production penetration testing, real-media model
inference, fraud model training or accuracy evaluation. Only the HTML dashboard
is verified. There is no claim of production readiness, authenticated human
review, live financial enforcement, or validated fraud accuracy. The simulation
clock and revisable historical projections must not be used as real payment
controls. Actual LinuxONE verification remains a target-environment task.


## Portable financial integration validation

The uploaded JSON model and reviewed user-supplied verifier were inspected before
execution. No joblib/pickle model was loaded; no third-party inference package was
installed. No running application, existing database or LinuxONE service was
upgraded or restarted. Temporary integration processes used ephemeral loopback
ports and temporary SQLite databases.

Executed in this environment (CPython 3.12.14, x86_64):

```bash
python3.12 tools/fraudguard_portable_verify.py models/financial/portable_model.json tests/fixtures/financial_reference_predictions.json
PYTHONPATH=src python3.12 -S -m unittest discover -s tests -v
PYTHONPATH=src python3.12 tests/browser_smoke.py
node --check dashboard/dashboard.js
```

- Supplied verifier: 100/100 reference cases passed; maximum absolute difference
  **1.1102230246251565e-16**, zero score mismatches at 1e-6, zero >=0.30
  classification mismatches. The backend's original stdlib implementation also
  matched all 100 at the stricter 1e-12 tolerance.
- **73 automated tests passed**, including all original 53 regressions. All 100
  references additionally passed through event validation, backend inference and
  SQLite decision persistence. `-S` excluded site packages throughout that suite.
- New coverage includes malformed/missing/non-finite/boolean features; JSON model
  checksum/size and tree corruption; unknown categories; exact <= branches;
  already-scaled leaf values; 0.30 threshold boundaries; model identity binding;
  old-history preservation; no stale/future/cross-device score leakage; replay
  and out-of-order convergence. High ML classifications do not silently change
  fusion APPROVE or activate payment blocks.
- CLI-started ephemeral test server passed health, all three legacy demos, real
  financial ML event scoring, duplicate replay, and persisted ML score/hash/
  threshold after an explicit **test-process** restart.
- Chromium passed the legacy UI workflow plus actual ML score/classification,
  separate 0.30 threshold, ML decision-history display, simulation labeling and
  390-pixel layout. An initial narrow-layout issue from the model hash was fixed
  with text wrapping. The passing run had no JS errors or external/CDN requests.
- The original optional Streamlit adapter was updated to show ML output but its
  third-party runtime was not installed or executed; HTML is the verified mode.

The user reports the same portable artifact independently passed on LinuxONE
s390x. That is not a claim that this task ran the new integrated backend there.
Run the parity and regression gates from FINANCIAL_MODEL.md on the target before
manually deploying. Parity demonstrates inference equivalence, not calibration,
fraud accuracy, independent test splits or production banking safety.
