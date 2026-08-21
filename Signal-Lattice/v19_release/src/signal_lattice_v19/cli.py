from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import APP_VERSION
from .api import serve
from .backtest import load_episodes, load_prices, run_walk_forward
from .config import Settings
from .engine import V19Engine
from .storage import RuntimeStorage
from .whitebox import WhiteboxLedger


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
    sub.add_parser("whitebox-summary")
    sub.add_parser("whitebox-skills")
    backtest = sub.add_parser("backtest")
    backtest.add_argument("--prices", required=True)
    backtest.add_argument("--episodes", required=True)
    backtest.add_argument("--benchmark", required=True)
    backtest.add_argument("--source-label", default="user-supplied-real-data")
    backtest.add_argument("--output")
    backtest.add_argument("--switch-cost-pct", type=float, default=1.16)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings.from_env(project_root())
    storage = RuntimeStorage(settings.state_dir)
    whitebox = WhiteboxLedger(storage.whitebox_db_file)
    if args.command == "bootstrap":
        state = storage.bootstrap(settings.canonical_state)
        print(json.dumps({
            "state": "READY",
            "code": state.get("code"),
            "prompt_version": settings.prompt_version,
            "application_version": settings.app_version,
            "whitebox_database": str(storage.whitebox_db_file),
        }, ensure_ascii=False))
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
    if args.command == "whitebox-summary":
        print(json.dumps(whitebox.summary(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "whitebox-skills":
        print(json.dumps({"mode": "SHADOW_ONLY", "items": whitebox.skills()}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "backtest":
        result = run_walk_forward(
            load_prices(Path(args.prices)),
            load_episodes(Path(args.episodes)),
            benchmark_symbol=args.benchmark,
            cash_rate_annual_pct=float(settings.runtime.get("cash_rate_annual_pct", 0.0)),
            switch_cost_pct=float(args.switch_cost_pct),
            nominal_aud=float(settings.runtime.get("nominal_aud", 10000.0)),
        )
        whitebox.record_backtest(result, str(args.source_label))
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if result["gate_status"] == "PASS" else 5
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
