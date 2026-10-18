"use strict";
const el = id => document.getElementById(id);
async function request(path, options = {}) {
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
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
    d.decision, `${d.decision_reason}; expiry ${d.active_block?.expiry || "—"}`]));
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
