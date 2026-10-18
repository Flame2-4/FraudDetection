"""Local API and deterministic scenario replay command line."""

import argparse
import json
import sqlite3

from .api import make_server
from .demos import SCENARIOS, replay
from .engine import Engine
from .models import ValidationError
from .policy import Policy


def main() -> None:
    parser = argparse.ArgumentParser(description="FraudGuard AI — simulation only")
    parser.add_argument("--db", default="var/fraudguard.sqlite3")
    parser.add_argument("--window-seconds", type=int, default=120)
    parser.add_argument("--verify-threshold", type=int, default=40)
    parser.add_argument("--freeze-threshold", type=int, default=75)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="serve loopback API and offline HTML dashboard")
    serve.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    demo = commands.add_parser("replay", help="idempotently load a fixed synthetic scenario")
    demo.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args()
    try:
        policy = Policy(window_seconds=args.window_seconds, verify_threshold=args.verify_threshold,
                        freeze_threshold=args.freeze_threshold)
        engine = Engine(args.db, policy)
        if args.command == "replay":
            print(json.dumps(replay(engine, args.scenario), indent=2))
        else:
            with make_server(engine, args.host, args.port) as server:
                print(f"Local simulation API/dashboard listening on {args.host}:{server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
