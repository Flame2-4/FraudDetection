"""Deterministic event-time fusion and simulation-only cooling-off policy."""

from collections import defaultdict, deque
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any

from .models import CapacityError, ConflictError, Event, ValidationError, canonical, identifier, iso, timestamp
from .financial import FinancialModel
from .policy import Policy, score_events
from .storage import Store


class Engine:
    """Persist raw events and atomically rebuild affected users' projections.

    Backdated submissions revise historical simulated decisions. No external
    financial actions occur. Sorting by (timestamp,event_id) makes the final
    projection independent of arrival order; historical answers can be revised.
    """

    def __init__(self, path: str | Path, policy: Policy | None = None):
        self.policy = policy or Policy()
        self.financial_model = FinancialModel()
        self.store = Store(path, self.policy, self.financial_model.identity)

    def submit(self, values: list[dict]) -> dict[str, Any]:
        if not isinstance(values, list) or not 1 <= len(values) <= 100:
            raise ValidationError("submit between 1 and 100 events per request")
        events = [Event.from_dict(value) for value in values]
        affected: set[tuple[str, str]] = set()
        duplicate_count = 0
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT count(*) FROM events").fetchone()[0]
            for event in events:
                payload = canonical(event.to_dict())
                row = db.execute("SELECT payload FROM events WHERE tenant_id=? AND event_id=?",
                                 (event.tenant_id, event.event_id)).fetchone()
                if row:
                    if row[0] != payload:
                        raise ConflictError("event_id already exists with different content")
                    duplicate_count += 1
                    continue
                count = db.execute("SELECT count(*) FROM events WHERE tenant_id=? AND user_id=?",
                                   (event.tenant_id, event.user_id)).fetchone()[0]
                if count >= self.policy.max_subject_events or total >= self.policy.max_total_events:
                    raise CapacityError("local event capacity reached; export/archive and use a new database")
                db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                           (event.tenant_id, event.event_id, event.user_id, event.device_id,
                            event.timestamp, payload))
                total += 1
                affected.add((event.tenant_id, event.user_id))
            for tenant, user in sorted(affected):
                self._rebuild(db, tenant, user)
            results = []
            unique = {(e.tenant_id, e.event_id): e for e in events}
            for event in sorted(unique.values(), key=lambda e: (e.timestamp, e.tenant_id, e.event_id)):
                row = db.execute("SELECT payload FROM assessments WHERE tenant_id=? AND event_id=?",
                                 (event.tenant_id, event.event_id)).fetchone()
                results.append(json.loads(row[0]))
        return {"simulated": True, "accepted": len(events) - duplicate_count,
                "duplicates": duplicate_count, "assessments": results}

    def _assessment(self, events: list[Event], tenant: str, user: str, device: str,
                    at: str, block: dict | None) -> dict:
        score = score_events(events, self.policy)
        payments = [event for event in events if event.event_type == "payment"]
        if payments:
            latest = payments[-1]
            features = latest.data.get("financial_features")
            financial = (self.financial_model.assess(features) if features is not None else
                         self.financial_model.unavailable("financial_features_not_supplied"))
            financial.update(event_id=latest.event_id, event_time=latest.timestamp)
        else:
            financial = self.financial_model.unavailable("no_payment_in_window")
        active = block is not None and block["start"] <= at < block["expiry"]
        return {**score, "financial_ml": financial, "tenant_id": tenant, "user_id": user, "device_id": device,
                "as_of": at, "clock_mode": "event_time", "simulated": True,
                "policy": self.policy.to_dict(), "window_start": iso(timestamp(at) - timedelta(
                    seconds=self.policy.window_seconds)), "window_end": at,
                "correlated_event_ids": [e.event_id for e in events],
                "decision": "FREEZE" if active else score["base_decision"],
                "block_enforced": active, "active_block": block if active else None,
                "decision_reason": "active simulated cooling-off block" if active else "risk thresholds",
                "limitations": "Simulated payment policy; financial ML is advisory and uncalibrated; audio/video inputs are simulated"}

    def _rebuild(self, db: sqlite3.Connection, tenant: str, user: str) -> None:
        rows = db.execute("SELECT payload FROM events WHERE tenant_id=? AND user_id=? "
                          "ORDER BY timestamp,event_id", (tenant, user)).fetchall()
        for table in ("assessments", "decisions", "interventions"):
            db.execute(f"DELETE FROM {table} WHERE tenant_id=? AND user_id=?", (tenant, user))
        windows: dict[str, deque[Event]] = defaultdict(deque)
        block: dict | None = None
        for row in rows:
            event = Event.from_dict(json.loads(row[0]))
            cutoff = iso(timestamp(event.timestamp) - timedelta(seconds=self.policy.window_seconds))
            window = windows[event.device_id]
            while window and window[0].timestamp < cutoff:
                window.popleft()
            window.append(event)
            result = self._assessment(list(window), tenant, user, event.device_id, event.timestamp, block)
            if event.event_type == "payment" and result["decision"] == "FREEZE" and not result["block_enforced"]:
                block = {"block_id": event.event_id, "trigger_event_id": event.event_id,
                         "tenant_id": tenant, "user_id": user, "device_id": event.device_id,
                         "start": event.timestamp,
                         "expiry": iso(timestamp(event.timestamp) + timedelta(minutes=60)),
                         "simulated": True, "reason": "risk index exceeded freeze threshold"}
                db.execute("INSERT INTO interventions VALUES(?,?,?,?,?,?)",
                           (tenant, event.event_id, user, block["start"], block["expiry"], canonical(block)))
                result["active_block"] = block
                result["block_activated"] = True
            else:
                result["block_activated"] = False
            result["event_id"] = event.event_id
            result["event_type"] = event.event_type
            db.execute("INSERT INTO assessments VALUES(?,?,?,?,?)",
                       (tenant, event.event_id, user, event.timestamp, canonical(result)))
            if event.event_type == "payment":
                db.execute("INSERT INTO decisions VALUES(?,?,?,?,?)",
                           (tenant, event.event_id, user, event.timestamp, canonical(result)))

    def assessment(self, tenant: str, user: str, device: str, at: str | None = None) -> dict:
        for name, value in (("tenant_id", tenant), ("user_id", user), ("device_id", device)):
            identifier(value, name)
        with self.store.connect() as db:
            # A read transaction keeps event and block projections consistent.
            db.execute("BEGIN")
            if at is None:
                row = db.execute("SELECT max(timestamp) FROM events WHERE tenant_id=? AND user_id=?",
                                 (tenant, user)).fetchone()
                if row[0] is None:
                    raise ValidationError("no events for user; supply an explicit at timestamp")
                at = row[0]
            at = iso(timestamp(at))
            start = iso(timestamp(at) - timedelta(seconds=self.policy.window_seconds))
            rows = db.execute("SELECT payload FROM events WHERE tenant_id=? AND user_id=? AND device_id=? "
                              "AND timestamp>=? AND timestamp<=? ORDER BY timestamp,event_id",
                              (tenant, user, device, start, at)).fetchall()
            row = db.execute("SELECT payload FROM interventions WHERE tenant_id=? AND user_id=? "
                             "AND start<=? AND expiry>? ORDER BY start DESC LIMIT 1",
                             (tenant, user, at, at)).fetchone()
            return self._assessment([Event.from_dict(json.loads(r[0])) for r in rows],
                                    tenant, user, device, at, json.loads(row[0]) if row else None)

    def history(self, kind: str, tenant: str, user: str | None = None,
                limit: int = 100, offset: int = 0) -> list[dict]:
        tables = {"events": "events", "assessments": "assessments", "decisions": "decisions",
                  "blocks": "interventions"}
        if kind not in tables:
            raise ValidationError("unknown history kind")
        identifier(tenant, "tenant_id")
        if user is not None:
            identifier(user, "user_id")
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValidationError("limit must be 1–200; offset must be nonnegative")
        where = "tenant_id=?" + (" AND user_id=?" if user is not None else "")
        params: list[Any] = [tenant] + ([user] if user is not None else []) + [limit, offset]
        order = "start DESC,trigger_event_id DESC" if kind == "blocks" else "timestamp DESC,event_id DESC"
        with self.store.connect() as db:
            rows = db.execute(f"SELECT payload FROM {tables[kind]} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                              params).fetchall()
        return [json.loads(r[0]) for r in rows]
