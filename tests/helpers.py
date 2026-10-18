"""Fictional event factory shared only by isolated tests."""


def event(event_id="e1", kind="payment", at="2026-01-01T12:00:00Z", user="u", device="d", tenant="t", **data):
    defaults = {
        "payment": {"amount_minor": 1000, "currency": "USD", "new_payee": False},
        "device": {"new_device": False, "failed_logins": 0},
        "call": {"suspicious": False},
        "audio": {"spoof_risk": 0.0, "quality": 1.0, "observation_id": "synthetic-o1"},
        "video": {"manipulation_risk": 0.0, "quality": 1.0, "observation_id": "synthetic-o1"},
    }
    return {"schema_version": 1, "event_id": event_id, "event_type": kind, "timestamp": at,
            "tenant_id": tenant, "user_id": user, "device_id": device, "source_id": "mock-"+kind,
            "data": {**defaults[kind], **data}, "simulated": True}
