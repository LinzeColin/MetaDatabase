from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import APP_VERSION
from .api import serve
from .config import Settings
from .engine import V19Engine
from .storage import RuntimeStorage


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="signal-lattice-v19")
    root.add_argument("--version", action="version", version=APP_VERSION)
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("once")
    sub.add_parser("loop")
    sub.add_parser("serve")
    sub.add_parser("bootstrap")
    sub.add_parser("print-latest")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings.from_env(project_root())
    storage = RuntimeStorage(settings.state_dir)
    if args.command == "bootstrap":
        state = storage.bootstrap(settings.canonical_state)
        print(json.dumps({"state": "READY", "code": state.get("code"), "prompt_version": settings.prompt_version}, ensure_ascii=False))
        return 0
    if args.command == "once":
        envelope = V19Engine(settings).run_once()
        print(envelope["rendered"])
        return 0
    if args.command == "loop":
        V19Engine(settings).run_loop()
        return 0
    if args.command == "serve":
        serve(settings, storage)
        return 0
    if args.command == "print-latest":
        envelope = storage.latest()
        if not envelope:
            print("NO_V19_REPORT")
            return 4
        print(envelope.get("rendered", ""))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
