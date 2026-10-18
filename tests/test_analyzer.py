"""Read-only live analysis uses actual verified inference and preserves state."""

from http.client import HTTPConnection
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from fraudguard.api import make_server
from fraudguard.demos import replay
from fraudguard.engine import Engine

REFERENCES = json.loads((Path(__file__).parent / "fixtures/financial_reference_predictions.json").read_text())


class AnalyzerAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.engine = Engine(Path(cls.tmp.name) / "analyzer.db")
        replay(cls.engine, "freeze")
        cls.server = make_server(cls.engine, port=0)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path, value=None, raw=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            post = value is not None or raw is not None
            body = json.dumps(value) if raw is None and post else raw
            connection.request("POST" if post else "GET", path, body=body,
                               headers=headers or ({"Content-Type": "application/json"} if post else {}))
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def snapshot(self):
        with sqlite3.connect(self.engine.store.path) as db:
            return {name: db.execute(f"SELECT * FROM {name} ORDER BY 1,2").fetchall()
                    for name in ("settings", "events", "assessments", "decisions", "interventions")}

    def test_all_reference_cases_use_real_model(self):
        for index, reference in enumerate(REFERENCES):
            with self.subTest(index=index):
                status, result = self.request("/api/financial/analyze", {"features": reference["features"]})
                self.assertEqual(status, 200)
                ml = result["financial_ml"]
                self.assertLessEqual(abs(ml["score"] - reference["expected_score"]), 1e-12)
                self.assertEqual(ml["is_fraud"], reference["expected_score"] >= .3)
                self.assertEqual(ml["threshold"], .3)
                self.assertEqual(ml["inference"], "trained_model")
                self.assertEqual(ml["fusion_effect"], "advisory_only")
                self.assertNotIn("risk_index", result)

    def test_valid_types_and_zero_balances(self):
        for kind in ("CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"):
            features = {**REFERENCES[0]["features"], "type": kind, "oldbalanceOrg": 0,
                        "oldbalanceDest": 0, "step": 1, "amount": .00001}
            status, result = self.request("/api/financial/analyze", {"features": features})
            self.assertEqual(status, 200)
            self.assertEqual(result["financial_ml"], self.engine.financial_model.assess(features))

    def test_missing_extra_and_wrong_input_shapes(self):
        base = REFERENCES[0]["features"]
        values = [{}, {"features": None}, {"features": []}, {"features": base, "score": .9},
                  {"features": {**base, "currency": "USD"}}, {"features": {**base, "isFraud": 1}}]
        values += [{"features": {key: value for key, value in base.items() if key != name}} for name in base]
        for value in values:
            with self.subTest(value=value):
                status, result = self.request("/api/financial/analyze", value)
                self.assertEqual(status, 400)
                self.assertIn("error", result)
                self.assertNotIn("financial_ml", result)

    def test_invalid_transaction_values(self):
        invalid = {"type": ["UNKNOWN", "", None, True],
                   "step": [0, -1, 2.5, 9007199254740992, "10", True],
                   "amount": [0, -1, "100", True, None, float("inf"), float("nan")],
                   "oldbalanceOrg": [-1, "0", False, None],
                   "oldbalanceDest": [-1, "0", False, None]}
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    status, result = self.request("/api/financial/analyze", {
                        "features": {**REFERENCES[0]["features"], name: value}})
                    self.assertEqual(status, 400)
                    self.assertIn("error", result)

    def test_read_only_repeated_requests_preserve_history_audit_and_blocks(self):
        before = self.snapshot()
        features = REFERENCES[63]["features"]
        results = [self.request("/api/financial/analyze", {"features": features}) for _ in range(5)]
        self.assertTrue(all(result == results[0] for result in results))
        status, result = results[0]
        self.assertEqual(status, 200)
        self.assertTrue(result["financial_ml"]["is_fraud"])
        self.assertTrue(result["advisory_only"])
        self.assertFalse(result["persisted"])
        self.assertEqual(result["enforcement"], "none")
        self.request("/api/financial/samples")
        self.request("/api/financial/analyze", {"features": {}})
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.engine.assessment("demo", "fictional-freeze", "device-freeze")["decision"], "FREEZE")

    def test_samples_are_verified_editable_inputs_not_predictions(self):
        status, result = self.request("/api/financial/samples")
        self.assertEqual(status, 200)
        self.assertEqual([s["id"] for s in result["samples"]], ["low", "intermediate", "high"])
        scores = []
        for sample in result["samples"]:
            self.assertEqual(sample["features"], REFERENCES[sample["reference_index"]]["features"])
            self.assertNotIn("score", sample)
            self.assertNotIn("expected_score", sample)
            status, analysis = self.request("/api/financial/analyze", {"features": sample["features"]})
            self.assertEqual(status, 200)
            scores.append(analysis["financial_ml"]["score"])
        self.assertLess(scores[0], .1)
        self.assertTrue(.3 < scores[1] < .7)
        self.assertGreater(scores[2], .9)
        self.assertEqual(scores, sorted(scores))

    def test_analysis_request_guards_and_malformed_json(self):
        for raw in ("{", '{"features":NaN}', '{"features":{},"features":{}}', "null"):
            status, _ = self.request("/api/financial/analyze", raw=raw)
            self.assertEqual(status, 400)
        status, _ = self.request("/api/financial/analyze", raw="{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _ = self.request("/api/financial/analyze", {"features": REFERENCES[0]["features"]},
                                 headers={"Content-Type": "application/json", "Origin": "https://example.com"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("/api/financial/samples?unexpected=yes")[0], 400)
        self.assertEqual(self.request("/api/financial/analyze?unexpected=yes", {})[0], 400)
