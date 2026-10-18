"""Loopback JSON API and offline HTML dashboard; no production authentication."""

from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import sqlite3
import threading
from urllib.parse import parse_qs, urlsplit

from .video import VideoJobs, MAX_BODY as VIDEO_MAX_BODY
from .analyzer import analyze, samples
from .demos import ROOT, SCENARIOS, replay
from .engine import Engine
from .models import CapacityError, ConflictError, ValidationError, strict_json

MAX_BODY = 65536
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
          "/media-info.js": ("media-info.js", "text/javascript; charset=utf-8"),
          "/videoguard.js": ("videoguard.js", "text/javascript; charset=utf-8"),
          "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    """One bounded request per connection, with fresh SQLite connections."""

    server_version = "FraudGuardSimulation/0.1"

    def __init__(self, *args, engine: Engine, **kwargs):
        self.engine = engine
        super().__init__(*args, **kwargs)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args) -> None:
        # Do not log query strings or submitted identifiers/payloads.
        logging.getLogger(__name__).info("HTTP response completed")

    def _respond(self, status: int, body: dict | list | bytes, content_type: str = "application/json") -> None:
        raw = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def _request(self, post: bool) -> None:
        try:
            if len(self.path) > 4096:
                self._respond(414, {"error": "request URI too long"})
                return
            host = self.headers.get("Host", "")
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if port == 80:
                allowed |= {"127.0.0.1", "localhost"}
            if host not in allowed:
                self._respond(403, {"error": "only the local API host is accepted"})
                return
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{host}":
                self._respond(403, {"error": "cross-origin requests are not allowed"})
                return
            url = urlsplit(self.path)
            if url.scheme or url.netloc:
                raise ValidationError("use an origin-form request path")
            query_lists = parse_qs(url.query, keep_blank_values=True, max_num_fields=12)
            if any(len(values) != 1 for values in query_lists.values()):
                raise ValidationError("duplicate query parameters are not allowed")
            query = {k: v[0] for k, v in query_lists.items()}
            if post:
                if url.path == "/api/video/jobs":
                    if not self.server.video_uploads.acquire(blocking=False):
                        self._respond(429, {"error": "Video upload capacity reached"})
                        return
                    try:
                        self._post(url.path, query)
                    finally:
                        self.server.video_uploads.release()
                else:
                    self._post(url.path, query)
            else:
                self._get(url.path, query)
        except (ValidationError, ValueError) as exc:
            # Conflict/Capacity have distinct responses despite deriving from ValueError.
            status = 409 if isinstance(exc, ConflictError) else 429 if isinstance(exc, CapacityError) else 400
            self._respond(status, {"error": str(exc), "simulated": True})
        except sqlite3.OperationalError:
            self._respond(503, {"error": "database unavailable or busy; retry later"})
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except Exception:
            logging.getLogger(__name__).exception("internal API error")
            self._respond(500, {"error": "internal error"})

    def do_GET(self) -> None:
        self._request(False)

    def do_POST(self) -> None:
        self._request(True)

    def _get(self, path: str, query: dict) -> None:
        if path in ASSETS:
            if query:
                raise ValidationError("dashboard assets do not accept query parameters")
            name, mime = ASSETS[path]
            self._respond(200, (ROOT / "dashboard" / name).read_bytes(), mime)
        elif path == "/api/health":
            if query:
                raise ValidationError("health does not accept query parameters")
            with self.engine.store.connect() as db:
                db.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
            self._respond(200, {"status": "ok", "simulated": True, "model": "explicit fusion rules + portable financial ML",
                                "financial_model": self.engine.financial_model.identity,
                                "audio_video": "simulated fusion inputs; VideoGuard analysis is separate",
                                "policy": self.engine.policy.to_dict()})
        elif path.startswith("/api/video/jobs/"):
            if query:
                raise ValidationError("video jobs do not accept query parameters")
            job = self.server.video_jobs.get(path.removeprefix("/api/video/jobs/"))
            self._respond(200 if job else 404, job or {"error": "job unavailable or expired"})
        elif path == "/api/financial/samples":
            if query:
                raise ValidationError("financial samples do not accept query parameters")
            self._respond(200, samples(self.engine.financial_model))
        elif path == "/api/scenarios":
            if query:
                raise ValidationError("scenarios does not accept query parameters")
            self._respond(200, {"scenarios": list(SCENARIOS), "simulated": True})
        elif path == "/api/assessment":
            if not {"tenant_id", "user_id", "device_id"} <= query.keys() or query.keys() - {
                    "tenant_id", "user_id", "device_id", "at"}:
                raise ValidationError("assessment requires tenant_id, user_id, device_id; optional at")
            self._respond(200, self.engine.assessment(query["tenant_id"], query["user_id"],
                                                     query["device_id"], query.get("at")))
        elif path in {"/api/events", "/api/assessments", "/api/decisions", "/api/blocks"}:
            if "tenant_id" not in query or query.keys() - {"tenant_id", "user_id", "limit", "offset"}:
                raise ValidationError("history requires tenant_id; optional user_id, limit, offset")
            limit, offset = int(query.get("limit", "100")), int(query.get("offset", "0"))
            items = self.engine.history(path.removeprefix("/api/"), query["tenant_id"],
                                        query.get("user_id"), limit, offset)
            self._respond(200, {"items": items, "limit": limit, "offset": offset, "simulated": True})
        else:
            self._respond(404, {"error": "unknown endpoint"})

    def _post(self, path: str, query: dict) -> None:
        if query:
            raise ValidationError("POST endpoints do not accept query parameters")
        if self.headers.get("Transfer-Encoding"):
            self._respond(400, {"error": "transfer encoding is not supported"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            self._respond(411, {"error": "one Content-Length header is required"})
            return
        try:
            length = int(lengths[0])
        except ValueError as exc:
            raise ValidationError("invalid Content-Length") from exc
        limit = VIDEO_MAX_BODY if path == "/api/video/jobs" else MAX_BODY
        if not 1 <= length <= limit:
            self._respond(413, {"error": f"request body must be 1–{limit} bytes"})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._respond(415, {"error": "Content-Type must be application/json"})
            return
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValidationError("incomplete request body")
        value = strict_json(raw)
        if path == "/api/video/jobs":
            self._respond(202, self.server.video_jobs.submit(value))
        elif path == "/api/financial/analyze":
            self._respond(200, analyze(value, self.engine.financial_model))
        elif path == "/api/events":
            events = value["events"] if isinstance(value, dict) and set(value) == {"events"} else [value]
            result = self.engine.submit(events)
            self._respond(201 if result["accepted"] else 200, result)
        elif path.startswith("/api/demos/"):
            if value != {}:
                raise ValidationError("demo submission body must be {}")
            result = replay(self.engine, path.removeprefix("/api/demos/"))
            self._respond(201 if result["accepted"] else 200, result)
        else:
            self._respond(404, {"error": "unknown endpoint"})


class VideoServer(ThreadingHTTPServer):
    """Clean up the ephemeral inference worker with the HTTP server."""

    def server_close(self):
        super().server_close()
        self.video_jobs.close()


def make_server(engine: Engine, host: str = "127.0.0.1", port: int = 8000, *, video_jobs=None) -> ThreadingHTTPServer:
    """Return a local-only server. Port zero supports isolated integration tests."""
    if host not in {"localhost", "127.0.0.1"}:
        raise ValidationError("the simulation API must bind localhost or 127.0.0.1")
    server = VideoServer((host, port), partial(Handler, engine=engine))
    server.video_uploads = threading.BoundedSemaphore(2)
    server.video_jobs = video_jobs if video_jobs is not None else VideoJobs()
    return server
