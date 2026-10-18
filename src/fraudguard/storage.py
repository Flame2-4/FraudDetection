"""SQLite persistence with parameterized queries and atomic subject projections."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from .models import ConflictError, canonical
from .policy import Policy

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
 tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, user_id TEXT NOT NULL,
 device_id TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (tenant_id, event_id));
CREATE INDEX IF NOT EXISTS events_subject ON events(tenant_id,user_id,timestamp,event_id);
CREATE TABLE IF NOT EXISTS assessments (
 tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, user_id TEXT NOT NULL,
 timestamp TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(tenant_id,event_id));
CREATE TABLE IF NOT EXISTS decisions (
 tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, user_id TEXT NOT NULL,
 timestamp TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(tenant_id,event_id));
CREATE TABLE IF NOT EXISTS interventions (
 tenant_id TEXT NOT NULL, trigger_event_id TEXT NOT NULL, user_id TEXT NOT NULL,
 start TEXT NOT NULL, expiry TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant_id,trigger_event_id));
"""


class Store:
    """Open a fresh connection per operation; serialize mutations with SQLite."""

    def __init__(self, path: str | Path, policy: Policy, financial_model: dict):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("use a file database (temporary files work in tests)")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            expected = canonical(policy.to_dict())
            row = db.execute("SELECT value FROM settings WHERE name='policy'").fetchone()
            if row and row[0] != expected:
                raise ConflictError("database policy differs; use the original options or a fresh database")
            db.execute("INSERT OR IGNORE INTO settings(name,value) VALUES('policy',?)", (expected,))
            # Additive binding: do not rewrite existing event/decision history on startup.
            model_identity = canonical(financial_model)
            row = db.execute("SELECT value FROM settings WHERE name='financial_model'").fetchone()
            if row and row[0] != model_identity:
                raise ConflictError("database financial model differs; explicit migration or a fresh database is required")
            db.execute("INSERT OR IGNORE INTO settings(name,value) VALUES('financial_model',?)", (model_identity,))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()
