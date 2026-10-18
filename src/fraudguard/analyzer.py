"""Read-only presentation adapter for the verified portable financial model."""

from pathlib import Path
from typing import Any

from .financial import FinancialModel, validate_features
from .models import ValidationError, strict_json

TRANSACTION_TYPES = ("CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER")
SAMPLES_PATH = Path(__file__).resolve().parents[2] / "demos/financial_samples.json"


def transaction_features(value: Any) -> dict[str, Any]:
    """Validate analyzer transaction semantics without changing the event API."""
    features = validate_features(value)
    if features["type"] not in TRANSACTION_TYPES:
        raise ValidationError("Transaction type must be CASH_IN, CASH_OUT, DEBIT, PAYMENT or TRANSFER")
    if features["amount"] <= 0:
        raise ValidationError("Transaction amount must be greater than zero in PaySim units")
    if features["oldbalanceOrg"] < 0 or features["oldbalanceDest"] < 0:
        raise ValidationError("Balances before the transaction must be zero or greater")
    step = features["step"]
    if not step.is_integer() or not 1 <= step <= 9007199254740991:
        raise ValidationError("Transaction step must be a positive whole number within the safe integer range")
    return features


def analyze(value: Any, model: FinancialModel) -> dict[str, Any]:
    """Call the existing model once. No database, fusion or intervention writes."""
    if not isinstance(value, dict) or set(value) != {"features"}:
        raise ValidationError("Analysis requires one features object containing all five trained fields")
    features = transaction_features(value["features"])
    return {"features": features, "financial_ml": model.assess(features),
            "advisory_only": True, "enforcement": "none", "persisted": False,
            "research_demo": True, "units": "Original PaySim simulation units; no currency conversion"}


def samples(model: FinancialModel) -> dict[str, Any]:
    """Return three original reference inputs, never precomputed predictions."""
    values = strict_json(SAMPLES_PATH.read_bytes())
    for sample in values:
        transaction_features(sample["features"])
    return {"samples": values, "model": model.identity, "research_demo": True}
