"""Portable inference parity, rejection paths, compatibility and persistent outputs."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fraudguard.demos import ROOT, replay
from fraudguard.engine import Engine
from fraudguard.financial import (
    FinancialModel, MODEL_PATH, MODEL_SHA256, _compile_model, validate_features,
)
from fraudguard.models import ConflictError, Event, ValidationError
from fraudguard.policy import Policy
from helpers import event

REFERENCE_PATH = Path(__file__).parent / "fixtures/financial_reference_predictions.json"
REFERENCES = json.loads(REFERENCE_PATH.read_text())
HIGH = next(row for row in REFERENCES if row["expected_score"] >= 0.3)
LOW = next(row for row in REFERENCES if row["expected_score"] < 0.3)


class FinancialInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = FinancialModel()

    def test_all_100_scores_and_classifications(self):
        self.assertEqual(len(REFERENCES), 100)
        for index, row in enumerate(REFERENCES):
            with self.subTest(index=index):
                result = self.model.assess(row["features"])
                self.assertLessEqual(abs(result["score"] - row["expected_score"]), 1e-12)
                self.assertEqual(result["is_fraud"], row["expected_score"] >= 0.3)
                self.assertEqual(result["sha256"], MODEL_SHA256)
                self.assertEqual(result["inference"], "trained_model")

    def test_supplied_verifier(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools/fraudguard_portable_verify.py"),
             str(MODEL_PATH), str(REFERENCE_PATH)], capture_output=True, text=True, check=True,
        )
        self.assertIn("PASS: all 100 reference cases match", completed.stdout)

    def test_classification_at_model_threshold(self):
        for score, is_fraud in ((math.nextafter(.3, 0), False), (.3, True),
                                (math.nextafter(.3, 1), True)):
            with self.subTest(score=score), patch.object(self.model, "predict", return_value=score):
                result = self.model.assess(LOW["features"])
                self.assertEqual(result["is_fraud"], is_fraud)
                self.assertEqual(result["threshold"], .3)

    def test_fusion_thresholds_are_separate(self):
        self.assertEqual(self.model.identity["fusion_effect"], "advisory_only")
        for score, decision in ((39, "APPROVE"), (40, "VERIFY"), (75, "VERIFY"), (76, "FREEZE")):
            self.assertEqual(Policy().decision(score), decision)

    def test_unknown_category_matches_all_zero_encoding(self):
        features = {**LOW["features"], "type": "UNKNOWN_SYNTHETIC_TYPE"}
        result = self.model.assess(features)
        self.assertFalse(result["category_known"])
        # Any unknown category produces the same all-zero one-hot vector.
        self.assertEqual(result["score"], self.model.predict({**features, "type": "OTHER"}))
        self.assertTrue(0 <= result["score"] <= 1)

    def test_finite_extreme_inputs_remain_bounded(self):
        for value in (-1e300, 1e300):
            features = {name: value for name in ("step", "amount", "oldbalanceOrg", "oldbalanceDest")}
            score = self.model.predict({**features, "type": "TRANSFER"})
            self.assertTrue(math.isfinite(score) and 0 <= score <= 1)

    def test_missing_extra_and_invalid_features(self):
        for value in (None, [], {k: v for k, v in LOW["features"].items() if k != "oldbalanceDest"},
                      {**LOW["features"], "isFraud": 1}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_features(value)
        for name in ("step", "amount", "oldbalanceOrg", "oldbalanceDest"):
            for value in (True, "1", None, math.inf, math.nan, 10**1000):
                with self.subTest(name=name, value=str(value)[:30]), self.assertRaises(ValidationError):
                    validate_features({**LOW["features"], name: value})
        for value in (None, 1, "", "A" * 81):
            with self.assertRaises(ValidationError):
                validate_features({**LOW["features"], "type": value})

    def test_model_checksum_and_size(self):
        self.assertEqual(hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(), MODEL_SHA256)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tampered.json"
            path.write_bytes(MODEL_PATH.read_bytes() + b" ")
            with self.assertRaisesRegex(ValidationError, "checksum"):
                FinancialModel(path)
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValidationError, "size"):
                FinancialModel(path)

    def test_corrupt_model_structures_rejected(self):
        base = json.loads(MODEL_PATH.read_text())
        mutations = [lambda m: m.update(baseline_prediction=math.inf),
                     lambda m: m.update(learning_rate=0),
                     lambda m: m.update(categories=["X"] * 5),
                     lambda m: m.update(trees=[]),
                     lambda m: m["trees"][0][0][0].__setitem__(2, 99),
                     lambda m: m["trees"][0][0][0].__setitem__(5, 99999),
                     lambda m: m["trees"][0][0][0].__setitem__(5, 0),
                     lambda m: m["trees"][0][0][0].__setitem__(11, 1),
                     lambda m: m["trees"][0][0][0].__setitem__(9, True),
                     lambda m: m["trees"][0][0][0].pop(),
                     lambda m: m["trees"][0].append(m["trees"][0][0])]
        for index, change in enumerate(mutations):
            model = deepcopy(base)
            change(model)
            with self.subTest(index=index), self.assertRaises(ValidationError):
                _compile_model(model)

    def test_split_equality_and_no_second_learning_rate(self):
        # Tiny independent contract fixture: <= goes left; leaves are already scaled.
        root = [0., 2, 0, 5., 0, 1, 2, 0., 0, 0, 0, 0, 0]
        left = [2., 1, 0, 0., 0, 0, 0, 0., 1, 1, 0, 0, 0]
        right = [-2., 1, 0, 0., 0, 0, 0, 0., 1, 1, 0, 0, 0]
        data = {"baseline_prediction": 0., "learning_rate": .08,
                "categories": ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"],
                "trees": [[[root, left, right]]]}
        baseline, categories, trees = _compile_model(data)
        model = FinancialModel()
        model._baseline, model._categories, model._trees = baseline, categories, trees
        self.assertEqual(model.predict({**LOW["features"], "step": 5.}), 1 / (1 + math.exp(-2)))
        self.assertEqual(model.predict({**LOW["features"], "step": 5.01}), math.exp(-2) / (1 + math.exp(-2)))


class FinancialIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "financial.db"
        self.engine = Engine(self.path)

    def test_all_100_through_event_pipeline(self):
        events = [event(f"ml-{i}", user=f"u-{i}", financial_features=row["features"])
                  for i, row in enumerate(REFERENCES)]
        results = self.engine.submit(events)["assessments"]
        by_id = {result["event_id"]: result for result in results}
        for index, row in enumerate(REFERENCES):
            actual = by_id[f"ml-{index}"]
            self.assertLessEqual(abs(actual["financial_ml"]["score"] - row["expected_score"]), 1e-12)
            self.assertEqual(actual["financial_ml"]["is_fraud"], row["expected_score"] >= .3)
            # ML does not silently modify rule-based risk or payment intervention.
            self.assertEqual((actual["risk_index"], actual["decision"]), (0, "APPROVE"))
        self.assertEqual(len(self.engine.history("decisions", "t", limit=200)), 100)

    def test_persistence_replay_and_current_assessment(self):
        value = event(financial_features=HIGH["features"])
        first = self.engine.submit([value])["assessments"][0]
        second = self.engine.submit([value])
        self.assertEqual(second["accepted"], 0)
        self.assertEqual(second["assessments"][0], first)
        fresh = Engine(self.path)
        self.assertEqual(fresh.history("decisions", "t")[0], first)
        current = fresh.assessment("t", "u", "d")
        self.assertEqual(current["financial_ml"], first["financial_ml"])
        self.assertEqual(len(fresh.history("events", "t")), 1)

    def test_legacy_scenarios_and_unavailable_are_preserved(self):
        for name, score, decision in (("normal", 0, "APPROVE"), ("verify", 45, "VERIFY"), ("freeze", 100, "FREEZE")):
            result = replay(self.engine, name)["assessments"][-1]
            self.assertEqual((result["risk_index"], result["decision"]), (score, decision))
            self.assertIsNone(result["financial_ml"]["score"])
            self.assertIsNone(result["financial_ml"]["is_fraud"])
            self.assertEqual(result["financial_ml"]["status"], "unavailable")

    def test_no_stale_score_on_latest_unscored_payment_or_expired_window(self):
        self.engine.submit([event("a", financial_features=HIGH["features"]),
                            event("b", at="2026-01-01T12:00:01Z")])
        self.assertEqual(self.engine.assessment("t", "u", "d")["financial_ml"]["status"], "unavailable")
        expired = self.engine.assessment("t", "u", "d", "2026-01-01T12:05:00Z")["financial_ml"]
        self.assertEqual(expired["reason"], "no_payment_in_window")

    def test_no_future_or_cross_device_score_leakage(self):
        self.engine.submit([event("future", at="2026-01-01T12:02:00Z", financial_features=HIGH["features"])])
        past = self.engine.submit([event("past")])["assessments"][0]
        self.assertIsNone(past["financial_ml"]["score"])
        self.assertIsNone(self.engine.assessment("t", "u", "other")["financial_ml"]["score"])
        self.assertIsNone(self.engine.assessment("other", "u", "d", "2026-01-01T12:02:00Z")["financial_ml"]["score"])

    def test_out_of_order_replay_converges(self):
        values = [event("a", financial_features=HIGH["features"]),
                  event("b", at="2026-01-01T12:01:00Z", financial_features=LOW["features"])]
        self.engine.submit(values)
        other = Engine(Path(self.tmp.name) / "other.db")
        for value in reversed(values):
            other.submit([value])
        for kind in ("events", "assessments", "decisions", "blocks"):
            self.assertEqual(self.engine.history(kind, "t"), other.history(kind, "t"))

    def test_invalid_features_rejected_atomically_and_not_allowed_on_audio(self):
        for features in ({}, {**HIGH["features"], "amount": "not-a-number"}):
            with self.assertRaises(ValidationError):
                self.engine.submit([event("valid"), event("bad", financial_features=features)])
        with self.assertRaises(ValidationError):
            Event.from_dict(event(kind="audio", financial_features=HIGH["features"]))
        self.assertEqual(self.engine.history("events", "t"), [])

    def test_model_binding_rejects_different_inference_identity(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE settings SET value=? WHERE name='financial_model'", ('{}',))
        with self.assertRaisesRegex(ConflictError, "financial model"):
            Engine(self.path)

    def test_old_database_history_not_rewritten_on_open(self):
        self.engine.submit([event()])
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM settings WHERE name='financial_model'")
            for table in ("assessments", "decisions"):
                row = json.loads(db.execute(f"SELECT payload FROM {table}").fetchone()[0])
                row.pop("financial_ml")
                db.execute(f"UPDATE {table} SET payload=?", (json.dumps(row),))
            old = db.execute("SELECT payload FROM decisions").fetchone()[0]
        engine = Engine(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT payload FROM decisions").fetchone()[0], old)
        self.assertNotIn("financial_ml", engine.history("decisions", "t")[0])
        self.assertEqual(engine.assessment("t", "u", "d")["financial_ml"]["status"], "unavailable")
