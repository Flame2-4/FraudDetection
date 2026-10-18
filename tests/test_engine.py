from copy import deepcopy
from itertools import permutations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fraudguard.demos import load_scenario, replay
from fraudguard.engine import Engine
from fraudguard.models import CapacityError, ConflictError, ValidationError
from fraudguard.policy import Policy
from helpers import event


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"test.sqlite3"
        self.engine=Engine(self.path)

    def submit(self,*values):
        return self.engine.submit(list(values))["assessments"][-1]

    def frozen(self):
        return replay(self.engine,"freeze")["assessments"][-1]

    def payment_after_freeze(self,at,event_id="later",device="device-freeze"):
        return event(event_id,at=at,tenant="demo",user="fictional-freeze",device=device)

    def test_all_demo_scenarios(self):
        for name,score,decision in (("normal",0,"APPROVE"),("verify",45,"VERIFY"),("freeze",100,"FREEZE")):
            with self.subTest(name=name):
                result=replay(self.engine,name)["assessments"][-1]
                self.assertEqual((result["risk_index"],result["decision"]),(score,decision))

    def test_replay_idempotency(self):
        first=replay(self.engine,"freeze")
        again=replay(self.engine,"freeze")
        self.assertEqual(first["assessments"],again["assessments"])
        self.assertEqual(again["accepted"],0)
        self.assertEqual(again["duplicates"],4)
        self.assertEqual(len(self.engine.history("events","demo")),4)
        self.assertEqual(len(self.engine.history("blocks","demo")),1)
        self.assertEqual(len(self.engine.history("decisions","demo")),1)

    def test_persistence_and_policy_mismatch(self):
        self.frozen()
        fresh=Engine(self.path)
        self.assertEqual(fresh.history("decisions","demo"),self.engine.history("decisions","demo"))
        with self.assertRaises(ConflictError):
            Engine(self.path,Policy(window_seconds=60))

    def test_conflicting_duplicate_rolls_back_batch(self):
        self.submit(event())
        with self.assertRaises(ConflictError):
            self.engine.submit([event("e2"),event(amount_minor=50000)])
        self.assertEqual(len(self.engine.history("events","t")),1)

    def test_duplicates_within_batch(self):
        result=self.engine.submit([event(),event()])
        self.assertEqual((result["accepted"],result["duplicates"]),(1,1))
        self.assertEqual(len(result["assessments"]),1)

    def test_schema_error_is_atomic(self):
        with self.assertRaises(ValidationError):
            self.engine.submit([event(),{**event("bad"),"data":{}}])
        self.assertEqual(self.engine.history("events","t"),[])

    def test_batch_and_history_limits(self):
        for values in ([],{},[event()]*101):
            with self.assertRaises(ValidationError):
                self.engine.submit(values)
        for limit in (0,201):
            with self.assertRaises(ValidationError):
                self.engine.history("events","t",limit=limit)

    def test_capacity(self):
        limited=Engine(Path(self.tmp.name)/"limited.db",Policy(max_subject_events=1))
        limited.submit([event()])
        with self.assertRaises(CapacityError):
            limited.submit([event("e2")])
        self.assertEqual(limited.submit([event()])["duplicates"],1)

    def test_out_of_order_rebuild_no_future_leakage(self):
        scenario=load_scenario("freeze")["events"]
        payment=scenario[-1]
        initial=self.submit(payment)
        self.assertEqual(initial["decision"],"APPROVE")
        self.engine.submit(scenario[:-1])
        after=self.engine.history("decisions","demo")[0]
        self.assertEqual(after["decision"],"FREEZE")
        self.assertTrue(all(r["risk_index"]<100 for r in self.engine.history("assessments","demo")
                            if r["event_type"]!="payment"))

    def test_permutations_have_identical_final_projections(self):
        scenario=load_scenario("freeze")["events"]
        expected=None
        for i,order in enumerate(permutations(scenario)):
            engine=Engine(Path(self.tmp.name)/f"permutation-{i}.db")
            for e in order:
                engine.submit([e])
            output={kind:engine.history(kind,"demo") for kind in ("events","assessments","decisions","blocks")}
            if expected is None:
                expected=output
            self.assertEqual(output,expected)

    def test_time_window_inclusive_start_exclusive_past(self):
        self.submit(event("d",kind="device",new_device=True))
        at_boundary=self.submit(event("p",at="2026-01-01T12:02:00Z"))
        self.assertIn("d",at_boundary["correlated_event_ids"])
        outside=self.submit(event("p2",at="2026-01-01T12:02:00.000001Z"))
        self.assertNotIn("d",outside["correlated_event_ids"])
        self.assertEqual(outside["risk_index"],0)

    def test_configurable_window(self):
        engine=Engine(Path(self.tmp.name)/"short.db",Policy(window_seconds=30))
        engine.submit([event("d",kind="device",new_device=True)])
        result=engine.submit([event("p",at="2026-01-01T12:00:31Z")])["assessments"][0]
        self.assertEqual(result["risk_index"],0)

    def test_no_cross_user_device_or_tenant_correlation(self):
        self.submit(event("d",kind="device",new_device=True,tenant="t",user="other"),
                    event("d2",kind="device",new_device=True,device="other"),
                    event("d3",kind="device",new_device=True,tenant="other"))
        result=self.submit(event())
        self.assertEqual(result["risk_index"],0)
        self.assertEqual(result["correlated_event_ids"],["e1"])

    def test_freeze_has_exact_start_expiry(self):
        result=self.frozen()
        self.assertTrue(result["block_activated"])
        self.assertEqual(result["active_block"]["start"],"2026-01-01T12:02:00.000000Z")
        self.assertEqual(result["active_block"]["expiry"],"2026-01-01T13:02:00.000000Z")

    def test_block_enforced_at_59_minutes_and_different_device(self):
        self.frozen()
        result=self.submit(self.payment_after_freeze("2026-01-01T13:01:59.999999Z",device="another"))
        self.assertEqual(result["risk_index"],0)
        self.assertEqual(result["decision"],"FREEZE")
        self.assertTrue(result["block_enforced"])
        self.assertFalse(result["block_activated"])

    def test_expiry_boundary_and_after(self):
        self.frozen()
        exact=self.submit(self.payment_after_freeze("2026-01-01T13:02:00Z"))
        after=self.submit(self.payment_after_freeze("2026-01-01T13:02:01Z","later2"))
        self.assertEqual(exact["decision"],"APPROVE")
        self.assertEqual(after["decision"],"APPROVE")
        self.assertIsNone(exact["active_block"])

    def test_repeated_events_do_not_reset_cooling_expiry(self):
        original=self.frozen()
        self.submit(self.payment_after_freeze("2026-01-01T12:03:00Z"))
        replay(self.engine,"freeze")
        blocks=self.engine.history("blocks","demo")
        self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0]["expiry"],original["active_block"]["expiry"])

    def test_new_high_risk_after_expiry_starts_new_block(self):
        self.frozen()
        rows=deepcopy(load_scenario("freeze")["events"])
        for e in rows:
            e["event_id"]+="-second"
            e["timestamp"]=e["timestamp"].replace("T12:","T14:")
        result=self.engine.submit(rows)["assessments"][-1]
        self.assertTrue(result["block_activated"])
        self.assertEqual(len(self.engine.history("blocks","demo")),2)

    def test_historical_queries_do_not_enforce_future_blocks(self):
        self.frozen()
        result=self.engine.assessment("demo","fictional-freeze","device-freeze","2026-01-01T11:59:00Z")
        self.assertEqual(result["decision"],"APPROVE")
        self.assertIsNone(result["active_block"])

    def test_assessment_expiry_and_default_clock(self):
        self.frozen()
        current=self.engine.assessment("demo","fictional-freeze","device-freeze")
        self.assertIsNotNone(current["active_block"])
        expired=self.engine.assessment("demo","fictional-freeze","device-freeze","2026-01-01T13:02:00Z")
        self.assertIsNone(expired["active_block"])
        self.assertEqual(expired["decision"],"APPROVE")

    def test_subject_block_does_not_cross_tenants(self):
        self.frozen()
        result=self.submit(event("other",tenant="other",user="fictional-freeze",at="2026-01-01T12:03:00Z"))
        self.assertEqual(result["decision"],"APPROVE")

    def test_sql_like_identifiers_rejected(self):
        with self.assertRaises(ValidationError):
            self.engine.history("events","t' OR 1=1")
