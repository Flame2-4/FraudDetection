"""Versioned transparent scoring. Values are scenario rules, not ML probabilities."""

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from typing import Any

from .models import Event, ValidationError


@dataclass(frozen=True)
class Policy:
    window_seconds: int = 120
    verify_threshold: int = 40
    freeze_threshold: int = 75
    cooling_minutes: int = 60
    # A 60-minute cooling period is a fixed MVP requirement.
    max_subject_events: int = 2000
    max_total_events: int = 50000

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if type(value) is not int:
                raise ValidationError("policy values must be integers")
        if not 1 <= self.window_seconds <= 3600:
            raise ValidationError("window_seconds must be between 1 and 3600")
        if not 1 <= self.verify_threshold <= self.freeze_threshold < 100:
            raise ValidationError("require 1 <= verify_threshold <= freeze_threshold < 100")
        if self.cooling_minutes != 60:
            raise ValidationError("the simulation cooling period is exactly 60 minutes")
        if not 1 <= self.max_subject_events <= 10000 or not 1 <= self.max_total_events <= 100000:
            raise ValidationError("invalid simulation event capacity")

    def to_dict(self) -> dict[str, Any]:
        return {"version": "rules-v1", **asdict(self)}

    def decision(self, score: int) -> str:
        if type(score) is not int or not 0 <= score <= 100:
            raise ValidationError("score must be an integer from 0 through 100")
        if score < self.verify_threshold:
            return "APPROVE"
        if score <= self.freeze_threshold:
            return "VERIFY"
        return "FREEZE"


def score_events(events: list[Event], policy: Policy) -> dict[str, Any]:
    """Select each warning once; reward distinct evidence groups nonlinearly.

    Call/audio/video share a media group to avoid asserting their independence.
    Repeated or derived observations cannot multiply a rule's weight.
    """
    factors: list[dict] = []

    def add(rule: str, channel: str, group: str, weight: int, candidates: list[Event],
            explanation: str, strength: Decimal = Decimal(1)) -> None:
        if not candidates:
            return
        points = int((Decimal(weight) * strength).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if points <= 0:
            return
        factors.append({"rule": rule, "channel": channel, "independence_group": group,
                        "weight": weight, "strength": float(strength), "points": points,
                        "event_ids": sorted(e.event_id for e in candidates),
                        "explanation": explanation})

    payments = [e for e in events if e.event_type == "payment"]
    # Independent scenario thresholds, not currency conversion or market rates.
    large = {"USD": 500000, "EUR": 500000, "GBP": 400000, "JPY": 750000}
    add("large_payment", "payment", "payment", 20,
        [e for e in payments if e.data["amount_minor"] >= large[e.data["currency"]]],
        "Amount meets the currency-specific simulated large-payment threshold")
    add("new_payee", "payment", "payment", 15, [e for e in payments if e.data["new_payee"]],
        "Payment to a simulated new beneficiary")
    add("payment_velocity", "payment", "payment", 15, payments if len(payments) >= 3 else [],
        "At least three distinct payments in the correlation window")
    devices = [e for e in events if e.event_type == "device"]
    add("new_device", "device", "device", 20, [e for e in devices if e.data["new_device"]],
        "Simulated device is unfamiliar")
    add("failed_logins", "device", "device", 15, [e for e in devices if e.data["failed_logins"] >= 3],
        "At least three simulated failed logins")
    add("suspicious_call", "call", "media", 15,
        [e for e in events if e.event_type == "call" and e.data["suspicious"]],
        "Caller-supplied simulated suspicious-call flag; no speech analysis")
    # Pick one maximum-quality-weighted media observation per modality.
    for kind, field in (("audio", "spoof_risk"), ("video", "manipulation_risk")):
        candidates = [e for e in events if e.event_type == kind]
        if candidates:
            def strength(e: Event) -> Decimal:
                return Decimal(str(e.data[field])) * Decimal(str(e.data["quality"]))
            best = sorted(candidates, key=lambda e: (-strength(e), e.event_id))[0]
            add(f"simulated_{kind}_risk", kind, "media", 25, [best],
                f"Simulated {kind} suspicion × quality; no real deepfake detector", strength(best))
    # Group caps and exact awarded contributions keep explanations additive.
    caps = {"payment": 40, "device": 30, "media": 30}
    remaining = dict(caps)
    for factor in factors:
        group = factor["independence_group"]
        factor["uncapped_points"] = factor["points"]
        factor["points"] = min(factor["points"], remaining[group])
        remaining[group] -= factor["points"]
    groups = sorted({f["independence_group"] for f in factors if f["points"]})
    # Pair interactions yield +10 for two groups, +30 for three.
    interactions = [{"rule": "cross_channel_pair", "groups": list(pair), "points": 10,
                     "explanation": "Independent simulated warning groups coincide"}
                    for pair in combinations(groups, 2)]
    raw = sum(f["points"] for f in factors) + sum(i["points"] for i in interactions)
    score = min(100, raw)
    observed = sorted({e.event_type for e in events})
    return {"risk_index": score, "raw_points": raw, "cap_adjustment": score - raw,
            "factors": factors, "interactions": interactions, "warning_groups": groups,
            "observed_channels": observed,
            "missing_channels": sorted({"payment", "device", "call", "audio", "video"} - set(observed)),
            "score_meaning": "heuristic risk index, not a probability or trained model",
            "base_decision": policy.decision(score)}
