#!/usr/bin/env python3
"""Run the deterministic North-Star vertical slice in an isolated temp runtime.

The golden path proves that six isolated, independently evidenced Skill outputs
and one trusted point-in-time market snapshot can produce exactly one human-only
investment recommendation. The black path proves that an incomplete pipeline is
reported as SYSTEM_BLOCKED rather than being disguised as NO_ACTION.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signal_lattice.clock import FakeClock
from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.recommendation import validate_market_snapshot, validate_skill_signal
from signal_lattice.worker import run_once

HUMAN_ACTIONS = {"BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH", "AVOID"}
SIGNAL_FIXTURES = (
    "commercial_signal.json",
    "bottleneck_signal.json",
    "serenity_signal.json",
    "foresight_signal.json",
    "lead_lag_signal.json",
    "event_signal.json",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        runtime_root = Path(tmp)
        clock = FakeClock(datetime(2026, 7, 30, tzinfo=timezone.utc))
        db = RuntimeDB(runtime_root / "runtime.db", ROOT / "db/schema.sql", clock)

        for name in SIGNAL_FIXTURES:
            signal = validate_skill_signal(_load_json(ROOT / "fixtures/northstar" / name))
            db.upsert_skill_signal(signal)
        db.upsert_market_snapshot(
            validate_market_snapshot(_load_json(ROOT / "fixtures/northstar/market_snapshot.json"))
        )

        settings = Settings(
            state_dir=runtime_root,
            artifact_dir=runtime_root / "artifacts",
            web_dir=ROOT / "web",
            recommendation_enabled=True,
            runtime_environment="test",
            decision_policy_path=ROOT / "config/decision_policy.json",
        )

        golden_job, created = db.enqueue(
            {
                "symbol": "DEMO",
                "market": "US",
                "current_position_pct": 0.0,
                "requested_position_value_usd": 1000,
            },
            "walking-skeleton-northstar-golden",
        )
        golden_ran = run_once(db, "walking-worker", 120, settings=settings)
        golden_result = db.get_job(golden_job)

        blocked_job, _ = db.enqueue(
            {"symbol": "MISSING", "market": "US"},
            "walking-skeleton-northstar-incomplete",
        )
        blocked_ran = run_once(db, "walking-worker", 120, settings=settings)
        blocked_result = db.get_job(blocked_job)

        with db.connect() as conn:
            counts = {
                table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("actions", "outbox", "runtime_journal", "attempts", "decision_snapshots")
            }

        golden_packet = golden_result["result"] if golden_result else None
        blocked_packet = blocked_result["result"] if blocked_result else None
        checks = {
            "golden_job_created": created,
            "golden_worker_ran": golden_ran,
            "golden_job_completed": bool(golden_result and golden_result["state"] == "COMPLETED"),
            "six_independent_skills_executed": counts["decision_snapshots"] >= 1
            and golden_packet is not None
            and len(golden_packet.get("skill_refs", [])) == 6,
            "one_human_recommendation": bool(
                golden_packet
                and golden_packet.get("action") in HUMAN_ACTIONS
                and golden_packet.get("human_execution_only") is True
                and golden_packet.get("automatic_execution_allowed") is False
            ),
            "recommendation_is_buy_fixture_oracle": bool(golden_packet and golden_packet.get("action") == "BUY"),
            "recommendation_has_independent_evidence": bool(
                golden_packet
                and golden_packet.get("independent_skill_count") == 6
                and golden_packet.get("independent_evidence_root_count") == 6
                and len(golden_packet.get("evidence_refs", [])) == 6
            ),
            "blocked_worker_ran": blocked_ran,
            "incomplete_pipeline_is_system_blocked": bool(
                blocked_result
                and blocked_result["state"] == "COMPLETED"
                and blocked_packet
                and blocked_packet.get("action") == "SYSTEM_BLOCKED"
                and set(blocked_packet.get("reasons", []))
                == {"NO_TRUSTED_SKILL_SIGNALS", "NO_TRUSTED_MARKET_SNAPSHOT"}
            ),
            "system_blocked_not_mislabeled_no_action": bool(
                blocked_packet and blocked_packet.get("action") != "NO_ACTION"
            ),
            "atomic_event_counts": counts["actions"] == 2
            and counts["outbox"] == 2
            and counts["runtime_journal"] == 2
            and counts["attempts"] == 2,
            "runtime_zero_agent_zero_token": bool(
                golden_packet
                and blocked_packet
                and golden_packet.get("runtime_agent_dependency") == 0
                and golden_packet.get("runtime_llm_tokens") == 0
                and blocked_packet.get("runtime_agent_dependency") == 0
                and blocked_packet.get("runtime_llm_tokens") == 0
            ),
        }
        payload = {
            "schema_version": "3.0.0",
            "state": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "counts": counts,
            "golden_action": golden_packet.get("action") if golden_packet else None,
            "blocked_action": blocked_packet.get("action") if blocked_packet else None,
            "active_skill_count": 6,
            "independent_evidence_root_count": 6,
            "runtime_agent_dependency": 0,
            "runtime_llm_tokens": 0,
            "automatic_trading": False,
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
