"""Strict, synthetic-only event contracts and canonical UTC timestamps."""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import re
from typing import Any


class ValidationError(ValueError):
    """A request violates the public contract."""


class ConflictError(ValueError):
    """An event ID or persisted policy has conflicting contents."""


class CapacityError(ValueError):
    """The bounded local simulation has reached its capacity."""


def timestamp(value: Any) -> datetime:
    """Parse an explicit timezone-bearing ISO-8601 timestamp; normalize to UTC."""
    if not isinstance(value, str) or len(value) > 40:
        raise ValidationError("timestamp must be an ISO-8601 string with timezone")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value):
        raise ValidationError("timestamp must include seconds and Z or a timezone offset")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        result = result.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ValidationError("invalid timestamp") from exc
    if not 2000 <= result.year <= 2100:
        raise ValidationError("timestamp year must be between 2000 and 2100")
    return result


def iso(value: datetime) -> str:
    """Use fixed-width UTC text so SQLite ordering matches datetime ordering."""
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value):
        raise ValidationError(f"{field} must contain 1–80 ASCII letters, digits, _, ., : or -")
    return value


def strict_json(raw: bytes | str) -> Any:
    """Reject ambiguous duplicate keys and non-standard NaN/Infinity JSON."""
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result: dict = {}
        for key, value in items:
            if key in result:
                raise ValidationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ValidationError("JSON numbers must be finite")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("invalid JSON: " + str(exc)[:150]) from exc


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Event:
    """Validated envelope; identifiers are fictional, caller-supplied links."""

    event_id: str
    event_type: str
    timestamp: str
    tenant_id: str
    user_id: str
    device_id: str
    source_id: str
    data: dict[str, Any]
    simulated: bool = True
    schema_version: int = 1
    session_id: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> "Event":
        if not isinstance(value, dict):
            raise ValidationError("event must be a JSON object")
        required = {"event_id", "event_type", "timestamp", "tenant_id", "user_id",
                    "device_id", "source_id", "data", "simulated", "schema_version"}
        if not required <= value.keys() or value.keys() - (required | {"session_id"}):
            raise ValidationError(f"event requires {sorted(required)}; optional session_id")
        if value["simulated"] is not True:
            raise ValidationError("only simulated=true events are accepted")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValidationError("schema_version must be integer 1")
        kinds = {"payment", "device", "call", "audio", "video"}
        if not isinstance(value["event_type"], str) or value["event_type"] not in kinds:
            raise ValidationError(f"event_type must be one of {sorted(kinds)}")
        clean = {key: identifier(value[key], key) for key in
                 ("event_id", "tenant_id", "user_id", "device_id", "source_id")}
        data = value["data"]
        schemas = {
            "payment": {"amount_minor": int, "currency": str, "new_payee": bool},
            "device": {"new_device": bool, "failed_logins": int},
            "call": {"suspicious": bool},
            "audio": {"spoof_risk": float, "quality": float, "observation_id": str},
            "video": {"manipulation_risk": float, "quality": float, "observation_id": str},
        }
        schema = schemas[value["event_type"]]
        if not isinstance(data, dict) or set(data) != set(schema):
            raise ValidationError(f"data fields for {value['event_type']} must be {sorted(schema)}")
        for key, expected in schema.items():
            item = data[key]
            if expected is float:
                if type(item) not in (float, int) or not 0 <= item <= 1 or not math.isfinite(item):
                    raise ValidationError(f"{key} must be a finite number between 0 and 1")
            elif type(item) is not expected:
                raise ValidationError(f"{key} must have type {expected.__name__}")
        if "amount_minor" in data and not 0 < data["amount_minor"] <= 10**12:
            raise ValidationError("amount_minor must be between 1 and 1000000000000")
        if "currency" in data and data["currency"] not in {"USD", "EUR", "GBP", "JPY"}:
            raise ValidationError("currency must be USD, EUR, GBP or JPY")
        if "failed_logins" in data and not 0 <= data["failed_logins"] <= 10000:
            raise ValidationError("failed_logins must be between 0 and 10000")
        if "observation_id" in data:
            identifier(data["observation_id"], "observation_id")
        return cls(**clean, event_type=value["event_type"], timestamp=iso(timestamp(value["timestamp"])),
                   data=dict(data), session_id=identifier(value["session_id"], "session_id")
                   if "session_id" in value else None)

    def to_dict(self) -> dict[str, Any]:
        value = {"event_id": self.event_id, "event_type": self.event_type,
                "timestamp": self.timestamp, "tenant_id": self.tenant_id,
                "user_id": self.user_id, "device_id": self.device_id,
                "source_id": self.source_id, "data": dict(self.data),
                "simulated": True, "schema_version": 1}
        if self.session_id is not None:
            value["session_id"] = self.session_id
        return value
