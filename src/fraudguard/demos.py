"""Load original fixed synthetic scenarios without duplicating persisted events."""

from pathlib import Path

from .engine import Engine
from .models import ValidationError, strict_json

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ("normal", "verify", "freeze")


def load_scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise ValidationError("scenario must be normal, verify or freeze")
    return strict_json((ROOT / "demos" / f"{name}.json").read_bytes())


def replay(engine: Engine, name: str) -> dict:
    scenario = load_scenario(name)
    result = engine.submit(scenario["events"])
    return {"scenario": name, "expected_decision": scenario["expected_decision"], **result}
