"""Validated standard-library inference for the supplied portable PaySim ensemble.

The user-supplied verifier defines the export contract: numeric passthrough,
one-hot categories, sequential already-scaled leaf sums and a stable sigmoid.
No artifact is executed and no pickle/scientific-Python runtime is used.
"""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any

from .models import ValidationError, strict_json

FEATURES = ("step", "type", "amount", "oldbalanceOrg", "oldbalanceDest")
NUMERIC_FEATURES = ("step", "amount", "oldbalanceOrg", "oldbalanceDest")
MODEL_SHA256 = "4bb42e763b1f698818a33ae10f8891b0a6c60a5514ea93e62219a112553d0e24"
MODEL_PATH = Path(__file__).resolve().parents[2] / "models/financial/portable_model.json"
MODEL_THRESHOLD = 0.30
INFERENCE_VERSION = "paysim-hgb-stdlib-v1"
MAX_MODEL_BYTES = 2 * 1024 * 1024


def finite_number(value: Any, name: str) -> float:
    """Accept JSON numeric values, excluding booleans, overflow and NaN/Infinity."""
    if type(value) not in (int, float):
        raise ValidationError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValidationError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValidationError(f"{name} must be a finite number")
    return result


def validate_features(value: Any) -> dict[str, Any]:
    """Require all five explicit trained features; do not invent balances or units."""
    if not isinstance(value, dict) or set(value) != set(FEATURES):
        raise ValidationError(f"financial_features must contain exactly {list(FEATURES)}")
    category = value["type"]
    if not isinstance(category, str) or not 1 <= len(category) <= 80:
        raise ValidationError("financial feature type must be a nonempty string of at most 80 characters")
    return {"type": category, **{name: finite_number(value[name], name) for name in NUMERIC_FEATURES}}


@dataclass(frozen=True)
class _Node:
    value: float
    feature: int
    threshold: float
    left: int
    right: int
    leaf: bool


def _compile_model(value: Any) -> tuple[float, tuple[str, ...], tuple[tuple[_Node, ...], ...]]:
    """Check export structure and finite, reachable, acyclic binary trees once."""
    if not isinstance(value, dict) or set(value) != {"baseline_prediction", "learning_rate", "categories", "trees"}:
        raise ValidationError("unsupported portable model schema")
    baseline = finite_number(value["baseline_prediction"], "baseline_prediction")
    rate = finite_number(value["learning_rate"], "learning_rate")
    if not 0 < rate <= 1:
        raise ValidationError("invalid model learning_rate")
    categories = value["categories"]
    if (not isinstance(categories, list) or len(categories) != 5
            or any(not isinstance(c, str) or not 1 <= len(c) <= 80 for c in categories)
            or len(set(categories)) != 5):
        raise ValidationError("expected five unique model categories")
    iterations = value["trees"]
    if not isinstance(iterations, list) or not 1 <= len(iterations) <= 1024:
        raise ValidationError("invalid ensemble size")
    trees = []
    for iteration in iterations:
        # The supplied binary classifier has one tree per boosting iteration.
        if not isinstance(iteration, list) or len(iteration) != 1:
            raise ValidationError("expected one tree per binary boosting iteration")
        rows = iteration[0]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
            raise ValidationError("invalid tree size")
        nodes = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 13:
                raise ValidationError("expected 13 fields per tree node")
            for index, item in enumerate(row):
                finite_number(item, f"node[{index}]")
            for index in (1, 2, 4, 5, 6, 8, 9, 10, 11, 12):
                if type(row[index]) is not int or row[index] < 0:
                    raise ValidationError("invalid integer tree-node field")
            if row[4] not in (0, 1) or row[9] not in (0, 1) or row[11] != 0:
                raise ValidationError("unsupported tree-node flags or categorical split")
            if not row[9] and (row[2] >= 4 + len(categories) or row[5] >= len(rows) or row[6] >= len(rows)):
                raise ValidationError("tree feature/child index out of range")
            nodes.append(_Node(float(row[0]), row[2], float(row[3]), row[5], row[6], bool(row[9])))
        visited = set()
        pending = [0]
        while pending:
            index = pending.pop()
            if index in visited:
                raise ValidationError("cyclic or shared-child tree is unsupported")
            visited.add(index)
            node = nodes[index]
            if not node.leaf:
                pending.extend((node.left, node.right))
        if len(visited) != len(nodes):
            raise ValidationError("unreachable tree nodes")
        trees.append(tuple(nodes))
    return baseline, tuple(categories), tuple(trees)


class FinancialModel:
    """Pinned, immutable inference data loaded from a bounded local JSON file."""

    def __init__(self, path: str | Path = MODEL_PATH):
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_MODEL_BYTES + 1)
        if len(raw) > MAX_MODEL_BYTES:
            raise ValidationError("portable model exceeds size limit")
        if hashlib.sha256(raw).hexdigest() != MODEL_SHA256:
            raise ValidationError("portable model checksum mismatch")
        self._baseline, self._categories, self._trees = _compile_model(strict_json(raw))

    @property
    def identity(self) -> dict[str, Any]:
        return {"version": INFERENCE_VERSION, "sha256": MODEL_SHA256,
                "threshold": MODEL_THRESHOLD, "positive_class": 1, "comparison": ">=",
                "score_semantics": "Uncalibrated model score", "fusion_effect": "advisory_only"}

    def predict(self, features: dict[str, Any]) -> float:
        """Match the supplied verifier's float operations and <= branch semantics."""
        features = validate_features(features)
        vector = [features[name] for name in NUMERIC_FEATURES]
        vector.extend(float(features["type"] == category) for category in self._categories)
        raw_score = self._baseline
        for tree in self._trees:
            index = 0
            while not tree[index].leaf:
                node = tree[index]
                index = node.left if vector[node.feature] <= node.threshold else node.right
            # Values already include learning_rate. Preserve sequential summation.
            raw_score += tree[index].value
        if raw_score >= 0:
            return 1.0 / (1.0 + math.exp(-raw_score))
        exponent = math.exp(raw_score)
        return exponent / (1.0 + exponent)

    def assess(self, features: dict[str, Any]) -> dict[str, Any]:
        score = self.predict(features)
        return {**self.identity, "status": "scored", "score": score,
                "is_fraud": score >= MODEL_THRESHOLD,
                "classification": "FRAUD" if score >= MODEL_THRESHOLD else "NOT_FRAUD",
                "category_known": features["type"] in self._categories,
                "inference": "trained_model"}

    def unavailable(self, reason: str) -> dict[str, Any]:
        return {**self.identity, "status": "unavailable", "score": None,
                "is_fraud": None, "classification": None, "reason": reason}
