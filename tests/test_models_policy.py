import math
import unittest

from fraudguard.models import Event, ValidationError, iso, strict_json, timestamp
from fraudguard.policy import Policy, score_events
from helpers import event


class ModelTests(unittest.TestCase):
    def test_timestamp_offsets_normalize(self):
        self.assertEqual(iso(timestamp("2026-01-01T13:00:00+01:00")), "2026-01-01T12:00:00.000000Z")

    def test_malformed_timestamps(self):
        for value in (None, 12, "2026-01-01", "2026-01-01T12:00:00", "2026-02-30T12:00:00Z",
                      "1999-01-01T00:00:00Z", "2026-01-01T25:00:00Z", "2026-01-01T12:00:00+25:00", "2026-01-01T12:00:00+00:60"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                timestamp(value)

    def test_required_fields(self):
        for field in event():
            value = event()
            del value[field]
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Event.from_dict(value)

    def test_extra_fields_and_non_objects(self):
        for value in ([], None, "event", {**event(), "secret": "no"}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Event.from_dict(value)

    def test_simulated_and_version_required(self):
        for field, value in (("simulated", False), ("simulated", 1), ("schema_version", True),
                             ("schema_version", 2), ("event_type", "real-bank"), ("event_type", [])):
            with self.subTest(field=field,value=value), self.assertRaises(ValidationError):
                Event.from_dict({**event(), field: value})

    def test_safe_identifiers(self):
        for field in ("event_id", "tenant_id", "user_id", "device_id", "source_id"):
            for value in ("", "a"*81, "<script>", "a b", "a' OR 1=1", None):
                with self.subTest(field=field,value=value), self.assertRaises(ValidationError):
                    Event.from_dict({**event(),field:value})

    def test_payment_data_validation(self):
        for data in ({"amount_minor":0}, {"amount_minor":-1}, {"amount_minor":True},
                     {"amount_minor":1.5}, {"amount_minor":10**13}, {"currency":"BTC"},
                     {"new_payee":"false"}, {"unknown":1}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                Event.from_dict(event(**data))

    def test_device_data_validation(self):
        for value in (-1,10001,True,1.2):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Event.from_dict(event(kind="device",failed_logins=value))

    def test_simulated_media_validation(self):
        for value in (-0.1,1.1,True,None,math.inf,math.nan,10**1000):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Event.from_dict(event(kind="audio",spoof_risk=value))
        self.assertEqual(Event.from_dict(event(kind="video")).event_type,"video")

    def test_session_telemetry_identifiers(self):
        value = {**event(kind="device"), "session_id": "fictional-session-1"}
        self.assertEqual(Event.from_dict(value).to_dict()["session_id"], "fictional-session-1")
        with self.assertRaises(ValidationError):
            Event.from_dict({**value, "session_id": "bad session"})

    def test_strict_json(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', 'null trailing', b'\xff', '{'):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                strict_json(raw)


class PolicyTests(unittest.TestCase):
    def test_threshold_boundaries(self):
        for score, expected in ((39,"APPROVE"),(40,"VERIFY"),(75,"VERIFY"),(76,"FREEZE")):
            with self.subTest(score=score):
                self.assertEqual(Policy().decision(score),expected)

    def test_configuration_and_score_validation(self):
        self.assertEqual(Policy(verify_threshold=20,freeze_threshold=60).decision(21),"VERIFY")
        for options in ({"window_seconds":0},{"window_seconds":3601},{"verify_threshold":76},
                        {"cooling_minutes":30},{"freeze_threshold":100},{"window_seconds":True}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                Policy(**options)
        for value in (-1,101,True,0.5):
            with self.assertRaises(ValidationError):
                Policy().decision(value)

    def score(self,*values):
        return score_events([Event.from_dict(e) for e in values],Policy())

    def test_nonlinear_independent_escalation(self):
        device = event("d",kind="device",new_device=True)
        call = event("c",kind="call",suspicious=True)
        self.assertEqual(self.score(device)["risk_index"],20)
        self.assertEqual(self.score(call)["risk_index"],15)
        both=self.score(device,call)
        self.assertEqual(both["risk_index"],45)
        self.assertEqual(both["interactions"][0]["points"],10)

    def test_explanations_add_up_and_cap(self):
        result=self.score(event("p",amount_minor=950000,new_payee=True),
                          event("d",kind="device",new_device=True,failed_logins=4),
                          event("c",kind="call",suspicious=True),
                          event("a",kind="audio",spoof_risk=1))
        self.assertEqual(result["risk_index"],100)
        self.assertEqual(sum(f["points"] for f in result["factors"])+
                         sum(i["points"] for i in result["interactions"])+result["cap_adjustment"],100)
        self.assertTrue(all(f["event_ids"] and f["explanation"] for f in result["factors"]))

    def test_correlated_media_not_independent(self):
        result=self.score(event("c",kind="call",suspicious=True),
                          event("a",kind="audio",spoof_risk=1),
                          event("v",kind="video",manipulation_risk=1))
        self.assertEqual(result["risk_index"],30)
        self.assertEqual(result["interactions"],[])

    def test_quality_and_repeated_warnings(self):
        result=self.score(event("a",kind="audio",spoof_risk=1,quality=0))
        self.assertEqual(result["risk_index"],0)
        device=event("d",kind="device",new_device=True)
        repeat=event("d2",kind="device",new_device=True)
        self.assertEqual(self.score(device,repeat)["risk_index"],20)

    def test_empty_bounds_and_missingness(self):
        result=self.score()
        self.assertEqual(result["risk_index"],0)
        self.assertEqual(len(result["missing_channels"]),5)

    def test_currency_thresholds(self):
        self.assertEqual(self.score(event(currency="JPY",amount_minor=750000))["risk_index"],20)
        self.assertEqual(self.score(event(currency="JPY",amount_minor=749999))["risk_index"],0)
