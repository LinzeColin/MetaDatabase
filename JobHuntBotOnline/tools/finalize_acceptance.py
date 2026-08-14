#!/usr/bin/env python3
"""Create the single production acceptance verdict from sealed evidence files.

Missing, malformed, BLOCKED, NOT_RUN, UNKNOWN, or FAIL critical evidence never
becomes PASS. This tool does not execute tests; deploy/acceptance.sh executes and
then calls this independent deterministic finalizer.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def verdict_of(path: Path, *, accepted: set[str] | None = None) -> tuple[str, str]:
    accepted = accepted or {"PASS"}
    payload = load(path)
    if payload is None:
        return "BLOCKED", "missing or invalid evidence"
    if payload.get("production_claimed", False) is not False:
        return "BLOCKED", "non-root evidence improperly claims production"
    value = str(payload.get("verdict") or payload.get("core_verdict") or "UNKNOWN").upper()
    if value in accepted:
        return "PASS", value
    if value in {"FAIL", "FAILED"}:
        return "FAIL", value
    return "BLOCKED", value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ACCEPTANCE_RESULT.json")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--deployment-id", default="")
    parser.add_argument("--rollback-target", default="")
    parser.add_argument("--evidence-root", default="evidence")
    args = parser.parse_args()

    ev = Path(args.evidence_root)
    if not ev.is_absolute():
        ev = ROOT / ev

    checks = [
        ("PACK", True, ev / "target-taskpack.json"),
        ("HTTPS_BROWSER_EMAIL", True, ev / "target-browser.json"),
        ("TENANT_ISOLATION", True, ev / "target-browser.json"),
        ("DEEPSEEK", True, ev / "target-deepseek.json"),
        ("DISCOVERY_AND_UX", True, ev / "target-browser.json"),
        ("SIX_HOUR_STATE", True, ev / "target-state-after.json"),
        ("MIGRATION", True, ev / "migration-result.json"),
        ("AUTHORIZED_SOURCES", True, ev / "target-sources.json"),
        ("RESTART_READBACK", True, ev / "target-restart.json"),
        ("BACKUP_VERIFY", True, ev / "target-recovery.json"),
        ("OPERATIONS", False, ev / "target-ops.json"),
    ]
    results: list[dict[str, Any]] = []
    critical_bad = False
    for name, critical, path in checks:
        accepted = {"PASS", "NO_CHANGE"} if name == "MIGRATION" else {"PASS"}
        verdict, observed = verdict_of(path, accepted=accepted)
        if critical and verdict != "PASS":
            critical_bad = True
        results.append({
            "name": name,
            "critical": critical,
            "verdict": verdict,
            "observed": observed,
            "evidence": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        })

    base_url = args.base_url.strip()
    identity_errors: list[str] = []
    if not base_url.startswith("https://"):
        identity_errors.append("base_url is not HTTPS")
    if not args.commit.strip():
        identity_errors.append("commit identity is missing")
    if not args.deployment_id.strip():
        identity_errors.append("deployment identity is missing")
    if not args.rollback_target.strip():
        identity_errors.append("rollback target is missing")
    if identity_errors:
        critical_bad = True

    ops = next(item for item in results if item["name"] == "OPERATIONS")
    overall = "PASS" if not critical_bad and ops["verdict"] == "PASS" else (
        "PASS_WITH_RISKS" if not critical_bad else "BLOCKED"
    )
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    is_root_result = output.resolve() == (ROOT / "ACCEPTANCE_RESULT.json").resolve()
    is_production_environment = os.getenv("APP_ENV", "").strip().lower() == "production"
    production_claimed = (
        overall in {"PASS", "PASS_WITH_RISKS"}
        and is_root_result
        and is_production_environment
    )
    result = {
        "product": "JobHuntBot Online",
        "product_version": os.getenv("APP_VERSION", "0.4.0").strip() or "0.4.0",
        "core_verdict": "PASS" if not critical_bad else "BLOCKED",
        "verdict": overall,
        "production_claimed": production_claimed,
        "completion_authority": "root ACCEPTANCE_RESULT.json on the production target only",
        "base_url": base_url,
        "commit": args.commit.strip(),
        "deployment_id": args.deployment_id.strip(),
        "rollback_target": args.rollback_target.strip(),
        "refresh_interval_hours": 6,
        "checks": results,
        "identity_errors": identity_errors,
        "rule": "Every critical item must PASS on the exact HTTPS deployment; noncritical operations may yield PASS_WITH_RISKS only after core PASS.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["core_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
