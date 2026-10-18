"""Optional presentation adapter. Requires a separately verified Streamlit stack.

Run only after platform/dependency checks; the standard-library HTML dashboard
is always available. All scoring and persistence stay in the local JSON API.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import streamlit as st

BASE = os.environ.get("FRAUDGUARD_API_URL", "http://127.0.0.1:8000").rstrip("/")
parsed = urlsplit(BASE)
if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path or parsed.username:
    raise ValueError("FRAUDGUARD_API_URL must point to the loopback HTTP API")


def api(path: str, post: bool = False) -> dict:
    request = Request(BASE + path, data=b"{}" if post else None,
                      headers={"Content-Type": "application/json"} if post else {})
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(json.load(exc).get("error", str(exc))) from exc
    except URLError as exc:
        raise ValueError("Start the local FraudGuard API first") from exc


st.set_page_config(page_title="FraudGuard AI — Simulation", layout="wide")
st.title("FraudGuard AI · SIMULATION ONLY")
st.warning("Synthetic inputs and explicit rules. No real deepfake detection or financial actions.")
scenario = st.selectbox("Fictional scenario", ["normal", "verify", "freeze"])
if st.button("Load / replay deterministically"):
    try:
        result = api(f"/api/demos/{scenario}", post=True)
        st.success(f"{result['accepted']} new events; {result['duplicates']} identical events reused")
    except ValueError as exc:
        st.error(str(exc))

tenant = st.text_input("Tenant", "demo")
user = st.text_input("Fictional user", f"fictional-{scenario}", key=f"user-{scenario}")
device = st.text_input("Device", f"device-{scenario}", key=f"device-{scenario}")
at = st.text_input("As-of event timestamp (optional; not wall-clock time)", "")
if st.button("Refresh assessment and history"):
    query = {"tenant_id": tenant, "user_id": user, "device_id": device}
    if at:
        query["at"] = at
    try:
        assessment = api("/api/assessment?" + urlencode(query))
        st.metric("Risk index (not probability)", assessment["risk_index"])
        st.subheader("Simulated decision: " + assessment["decision"])
        st.write(assessment["decision_reason"])
        st.subheader("Active simulated cooling-off block")
        st.json(assessment["active_block"] or {"active": False, "as_of": assessment["as_of"]})
        st.subheader("User/device correlation, confidence and missing channels")
        st.json({key: assessment[key] for key in ("tenant_id", "user_id", "device_id", "as_of",
                 "window_start", "window_end", "correlated_event_ids", "observed_channels", "missing_channels")})
        st.subheader("Factors, weights and nonlinear interactions")
        st.json({key: assessment[key] for key in ("factors", "interactions", "raw_points", "cap_adjustment")})
        history = urlencode({"tenant_id": tenant, "user_id": user})
        for kind in ("events", "decisions", "blocks"):
            st.subheader("Simulated " + kind + " history")
            st.json(api(f"/api/{kind}?" + history)["items"])
    except ValueError as exc:
        st.error(str(exc))
st.info("Human review requires evidence, independent identity verification and a recorded rationale. "
        "No authentication or review mutation workflow is implemented in this local demo.")
