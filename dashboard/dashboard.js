"use strict";
const el = id => document.getElementById(id);
async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {...options, signal: controller.signal});
    let value;
    try { value = await response.json(); }
    catch { throw new Error("The server returned an unreadable response. Please try again."); }
    if (!response.ok) throw new Error(value.error || `Request failed (HTTP ${response.status}).`);
    return value;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The request timed out. Check the server connection and try again.");
    if (error instanceof TypeError) throw new Error("Unable to reach FraudGuard. Check the local server connection and try again.");
    throw error;
  } finally { clearTimeout(timeout); }
}
function rows(id, values) {
  const body = el(id);
  body.replaceChildren();
  for (const valuesRow of values) {
    const row = document.createElement("tr");
    for (const value of valuesRow) {
      const cell = document.createElement("td");
      cell.textContent = String(value); // Never interpolate event data into HTML.
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
}
async function refresh() {
  const query = new URLSearchParams({tenant_id: el("tenant").value,
    user_id: el("user").value, device_id: el("device").value});
  if (el("at").value.trim()) query.set("at", el("at").value.trim());
  const history = new URLSearchParams({tenant_id: el("tenant").value, user_id: el("user").value});
  const [assessment, events, decisions] = await Promise.all([
    request(`/api/assessment?${query}`), request(`/api/events?${history}`), request(`/api/decisions?${history}`)
  ]);
  const ml = assessment.financial_ml;
  el("financial-score").textContent = ml?.status === "scored" ? String(ml.score) : "Unavailable";
  el("financial-classification").textContent = ml?.status === "scored" ?
    `${ml.classification}: score >= ${ml.threshold.toFixed(2)} = ${ml.is_fraud}. Unknown category: ${!ml.category_known}.` :
    `No ML score: ${ml?.reason || "legacy record without ML assessment"}. Missing features are not a score of zero.`;
  el("financial-detail").textContent = ml?.status === "scored" ?
    `Payment ${ml.event_id} at ${ml.event_time}. Uncalibrated trained-model score; advisory only, separate from fusion risk. Model ${ml.version}, SHA-256 ${ml.sha256}.` :
    "Uncalibrated model threshold 0.30; fusion bands remain 40/75. Audio/video detection remains simulated.";
  el("risk").textContent = assessment.risk_index;
  el("decision").textContent = assessment.decision;
  el("reason").textContent = assessment.decision_reason;
  el("block").textContent = assessment.active_block ? "ACTIVE · SIMULATED" : "No active block";
  el("expiry").textContent = assessment.active_block ?
    `Start ${assessment.active_block.start}; expires ${assessment.active_block.expiry} (exclusive)` : `As of ${assessment.as_of}`;
  el("correlation").textContent = JSON.stringify({tenant: assessment.tenant_id, user: assessment.user_id,
    device: assessment.device_id, clock: assessment.clock_mode, as_of: assessment.as_of,
    window: [assessment.window_start, assessment.window_end], events: assessment.correlated_event_ids,
    observed: assessment.observed_channels, missing: assessment.missing_channels}, null, 2);
  rows("factors", assessment.factors.map(f => [
    `${f.rule} / ${f.independence_group}`, f.weight, f.strength, f.points,
    `${f.event_ids.join(", ")}: ${f.explanation}`]));
  el("interaction").textContent = `Nonlinear interactions: ${JSON.stringify(assessment.interactions)}; raw points ${assessment.raw_points}; cap adjustment ${assessment.cap_adjustment}. Missing channels mean unknown.`;
  rows("events", events.items.map(e => [e.timestamp, `${e.event_id} / ${e.event_type}`,
    `${e.user_id} / ${e.device_id} / session: ${e.session_id || "not supplied"}`, JSON.stringify(e.data)]));
  rows("decisions", decisions.items.map(d => [`${d.as_of} / ${d.event_id}`, d.risk_index,
    d.decision, d.financial_ml?.status === "scored" ? `${d.financial_ml.score} / ${d.financial_ml.classification} (>= ${d.financial_ml.threshold})` : "ML unavailable",
    `${d.decision_reason}; expiry ${d.active_block?.expiry || "—"}`]));
  el("status").textContent = `Loaded ${events.items.length} recent events and ${decisions.items.length} payment decisions (up to 100 each). Simulation only.`;
}
async function guarded(action) {
  el("replay").disabled = el("refresh").disabled = true;
  try { await action(); }
  catch (error) { el("status").textContent = error.message; }
  finally { el("replay").disabled = el("refresh").disabled = false; }
}
el("refresh").addEventListener("click", () => guarded(refresh));
el("replay").addEventListener("click", () => guarded(async () => {
  const name = el("scenario").value;
  const result = await request(`/api/demos/${name}`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
  });
  el("tenant").value = "demo";
  el("user").value = `fictional-${name}`;
  el("device").value = `device-${name}`;
  el("at").value = "";
  await refresh();
  el("status").textContent += ` Replay: ${result.accepted} new, ${result.duplicates} reused.`;
}));

// Presentation analyzer: inputs and display only. All inference stays in Python.
const analyzerForm = el("analyzer-form");
const analyzerFields = {
  type: el("transaction-type"), step: el("transaction-step"),
  amount: el("transaction-amount"), oldbalanceOrg: el("sender-balance"),
  oldbalanceDest: el("recipient-balance")
};
const sampleButtons = [...document.querySelectorAll("[data-sample]")];
const analyzerPanel = el("analyzer-result");
let analyzerBusy = false;
let analyzerSamples = new Map();

function setAnalyzerBusy(busy) {
  analyzerBusy = busy;
  el("analyzer-fields").disabled = busy;
  el("analyze-submit").disabled = busy;
  el("analyze-submit").querySelector(".button-label").textContent = busy ? "Analyzing transaction…" : "Analyze Transaction";
  sampleButtons.forEach(button => { button.disabled = busy || !analyzerSamples.has(button.dataset.sample); });
  analyzerPanel.setAttribute("aria-busy", String(busy));
}
function clearAnalyzerErrors() {
  el("analyzer-error").hidden = true;
  el("analyzer-error").textContent = "";
  for (const [name, field] of Object.entries(analyzerFields)) {
    field.removeAttribute("aria-invalid");
    el(`${name}-error`).textContent = "";
  }
}
function resetAnalyzerResult(message) {
  el("analyzer-output").hidden = true;
  el("analyzer-empty").hidden = false;
  analyzerPanel.dataset.state = "empty";
  delete analyzerPanel.dataset.outcome;
  el("analyzer-status").textContent = message;
}
function readAnalyzerFeatures() {
  const features = {};
  let firstInvalid = null;
  for (const [name, field] of Object.entries(analyzerFields)) {
    let message = "";
    if (name === "type") {
      features[name] = field.value;
      if (!["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"].includes(field.value)) message = "Choose a valid transaction type.";
    } else {
      const number = field.valueAsNumber;
      features[name] = number;
      if (field.value.trim() === "" || !Number.isFinite(number)) message = "Enter a finite number; this field is required.";
      else if (name === "step" && (!Number.isSafeInteger(number) || number < 1)) message = "Use a positive whole PaySim step, not a date.";
      else if (name === "amount" && number <= 0) message = "Enter an amount greater than zero in original PaySim units.";
      else if ((name === "oldbalanceOrg" || name === "oldbalanceDest") && number < 0) message = "The balance before the transaction must be zero or greater.";
    }
    if (message) {
      field.setAttribute("aria-invalid", "true");
      el(`${name}-error`).textContent = message;
      firstInvalid ||= field;
    }
  }
  if (firstInvalid) {
    firstInvalid.focus();
    throw new Error("Check the highlighted transaction fields, then analyze again.");
  }
  return features;
}
function showAnalyzerResult(result) {
  const ml = result.financial_ml;
  if (!ml || ml.status !== "scored" || ml.inference !== "trained_model" ||
      !Number.isFinite(ml.score) || ml.score < 0 || ml.score > 1 || ml.threshold !== 0.30 ||
      typeof ml.is_fraud !== "boolean" || !["FRAUD", "NOT_FRAUD"].includes(ml.classification) ||
      result.advisory_only !== true || result.enforcement !== "none" || result.persisted !== false) {
    throw new Error("The server returned an unexpected model result. No prediction has been displayed.");
  }
  el("analyzer-empty").hidden = true;
  el("analyzer-output").hidden = false;
  analyzerPanel.dataset.state = "success";
  analyzerPanel.dataset.outcome = ml.classification;
  el("analyzer-score").textContent = ml.score.toPrecision(6);
  el("analyzer-exact-score").textContent = String(ml.score);
  el("analyzer-classification").textContent = ml.classification;
  el("analyzer-meter").value = ml.score;
  el("analyzer-meter").setAttribute("aria-valuetext", `${ml.score}, uncalibrated model score on a 0 to 1 scale`);
  el("analyzer-threshold").textContent = `Decision threshold ${ml.threshold.toFixed(2)}`;
  el("analyzer-rule").textContent = `Score >= ${ml.threshold.toFixed(2)}: ${ml.is_fraud}. Positive class: ${ml.positive_class}.`;
  el("analyzer-model-version").textContent = ml.version;
  el("analyzer-model-hash").textContent = ml.sha256;
  el("analyzer-interpretation").textContent = ml.is_fraud ?
    "Model threshold met. The trained model flags this transaction for review. Consider additional context; this advisory classification takes no payment action." :
    "Model threshold not met. The trained model does not flag this transaction at 0.30. This is not a guarantee of legitimacy or a payment approval.";
  el("analyzer-status").textContent = `Analysis complete: ${ml.classification}. Model score ${ml.score.toPrecision(6)}. No event was saved and no enforcement action was taken.`;
  el("analyzer-connection").textContent = "Portable model · connected";
  el("analyzer-connection").dataset.state = "ready";
}

analyzerForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (analyzerBusy) return;
  clearAnalyzerErrors();
  resetAnalyzerResult("Validating transaction…");
  try {
    const features = readAnalyzerFeatures();
    setAnalyzerBusy(true);
    analyzerPanel.dataset.state = "loading";
    el("analyzer-status").textContent = "Running the verified financial model on the server…";
    const result = await request("/api/financial/analyze", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({features})
    });
    showAnalyzerResult(result);
  } catch (error) {
    analyzerPanel.dataset.state = "error";
    el("analyzer-error").textContent = error.message;
    el("analyzer-error").hidden = false;
    el("analyzer-status").textContent = "Analysis was not completed. Correct the input or retry; no result was substituted.";
  } finally { setAnalyzerBusy(false); }
});
for (const field of Object.values(analyzerFields)) {
  field.addEventListener("input", () => {
    clearAnalyzerErrors();
    sampleButtons.forEach(button => button.setAttribute("aria-pressed", "false"));
    resetAnalyzerResult("Inputs changed. Analyze again for a fresh model prediction.");
  });
}
sampleButtons.forEach(button => button.addEventListener("click", () => {
  const sample = analyzerSamples.get(button.dataset.sample);
  if (!sample || analyzerBusy) return;
  clearAnalyzerErrors();
  for (const [name, field] of Object.entries(analyzerFields)) field.value = sample.features[name];
  sampleButtons.forEach(other => other.setAttribute("aria-pressed", String(other === button)));
  resetAnalyzerResult(`${sample.label} example loaded from a verified reference case. Edit any value, then click Analyze Transaction.`);
}));
async function initializeAnalyzer() {
  try {
    const result = await request("/api/financial/samples");
    if (!Array.isArray(result.samples) || result.samples.length !== 3) throw new Error("Sample transactions are unavailable.");
    analyzerSamples = new Map(result.samples.map(sample => [sample.id, sample]));
    sampleButtons.forEach(button => { button.disabled = !analyzerSamples.has(button.dataset.sample); });
    el("analyzer-connection").textContent = "Portable model · connected";
    el("analyzer-connection").dataset.state = "ready";
  } catch (error) {
    el("analyzer-connection").textContent = "Model connection unavailable";
    el("analyzer-connection").dataset.state = "error";
    el("analyzer-status").textContent = `Examples could not load. ${error.message} You can still enter values and retry analysis.`;
  }
}
function updateNavigation() {
  for (const link of document.querySelectorAll('.sidebar nav a')) {
    if (link.hash === (location.hash || "#analyzer")) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  }
}
window.addEventListener("hashchange", updateNavigation);
updateNavigation();
initializeAnalyzer();
