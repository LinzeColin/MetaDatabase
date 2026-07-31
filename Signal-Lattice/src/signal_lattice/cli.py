from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .api import serve
from .backup import backup_sqlite, restore_sqlite
from .calibration import load_weights, update_weights
from .config import Settings
from .constants import VERSION
from .db import RuntimeDB
from .orchestrator import build_for_request
from .recommendation import validate_market_snapshot, validate_skill_signal
from .status import default_matrix
from .util import atomic_write
from .worker import run_once
from .cycle_engine import run_minute_cycle
from .skill_registry import reconcile_runtime_registry


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_db(settings: Settings) -> RuntimeDB:
    return RuntimeDB(settings.state_dir / "runtime.db", Path(__file__).with_name("schema.sql"))


def _load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ValueError("INPUT_FILE_INVALID")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("INPUT_JSON_OBJECT_REQUIRED")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="signal-lattice")
    root.add_argument("--version", action="version", version=VERSION)
    sub = root.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("worker-once")
    sub.add_parser("verify-runtime")
    sub.add_parser("run-cycle")
    sub.add_parser("reconcile-sources")
    sub.add_parser("cycle-status")
    backup = sub.add_parser("backup")
    backup.add_argument("output", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("backup", type=Path)
    restore.add_argument("sha256")
    status = sub.add_parser("status-fixture")
    status.add_argument("output", type=Path)
    ingest_signal = sub.add_parser("ingest-skill-signal")
    ingest_signal.add_argument("input", type=Path)
    ingest_market = sub.add_parser("ingest-market-snapshot")
    ingest_market.add_argument("input", type=Path)
    decide = sub.add_parser("decide-once")
    decide.add_argument("symbol")
    decide.add_argument("market")
    decide.add_argument("--current-position-pct", type=float, default=0.0)
    decide.add_argument("--requested-position-value-usd", type=float, default=0.0)
    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("outcomes", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings.from_env(project_root())
    db = runtime_db(settings)
    if args.cmd == "serve":
        serve(settings, db)
        return 0
    if args.cmd == "worker-once":
        return 0 if run_once(db, settings=settings, lease_seconds=settings.worker_lease_seconds) else 3
    if args.cmd == "run-cycle":
        result = run_minute_cycle(db, settings)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("state") in {"COMPLETED", "DEGRADED"} else 4
    if args.cmd == "reconcile-sources":
        result = reconcile_runtime_registry(db, settings)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("state") in {"PASS", "DEGRADED"} else 4
    if args.cmd == "cycle-status":
        print(json.dumps(db.latest_minute_cycle() or {"state": "SYSTEM_BLOCKED", "reason": "NO_MINUTE_CYCLE"}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "verify-runtime":
        forbidden = [
            key for key in os.environ
            if key.upper() in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"}
        ]
        payload = {
            "state": "PASS" if not forbidden else "FAIL",
            "version": VERSION,
            "agent_dependency": 0,
            "model_mode": "DISABLED",
            "token_budget": 0,
            "automatic_trading": False,
            "forbidden_env": forbidden,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not forbidden else 2
    if args.cmd == "backup":
        print(json.dumps(backup_sqlite(settings.state_dir / "runtime.db", args.output), ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "restore":
        restore_sqlite(args.backup, settings.state_dir / "runtime.db", args.sha256)
        return 0
    if args.cmd == "status-fixture":
        atomic_write(args.output, json.dumps(default_matrix(), ensure_ascii=False, indent=2).encode("utf-8"))
        return 0
    if args.cmd == "ingest-skill-signal":
        signal = validate_skill_signal(_load_json(args.input))
        db.upsert_skill_signal(signal)
        print(json.dumps({"state": "PASS", "skill_id": signal["skill_id"], "symbol": signal["symbol"], "market": signal["market"]}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "ingest-market-snapshot":
        snapshot = validate_market_snapshot(_load_json(args.input))
        db.upsert_market_snapshot(snapshot)
        print(json.dumps({"state": "PASS", "symbol": snapshot["symbol"], "market": snapshot["market"]}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "decide-once":
        request = {
            "symbol": args.symbol,
            "market": args.market,
            "current_position_pct": args.current_position_pct,
            "requested_position_value_usd": args.requested_position_value_usd,
        }
        packet, snapshot = build_for_request(db, settings, request)
        print(json.dumps({"packet": packet, "snapshot": snapshot}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if packet["action"] != "NO_ACTION" else 4
    if args.cmd == "calibrate":
        data = _load_json(args.outcomes)
        outcomes = data.get("outcomes")
        if not isinstance(outcomes, list):
            raise ValueError("OUTCOMES_ARRAY_REQUIRED")
        current = load_weights(settings.state_dir / "calibration" / "weights.json")
        result = update_weights(current, outcomes)
        target = settings.state_dir / "calibration" / "weights.json"
        atomic_write(target, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
