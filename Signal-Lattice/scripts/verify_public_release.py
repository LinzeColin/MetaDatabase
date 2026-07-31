#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_HOST = "signal-lattice.linzezhang.com"


def canonical_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.chmod(name, 0o600); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def request(url: str, *, timeout: int) -> tuple[int, bytes, dict[str, str]]:
    headers = {"User-Agent": "Signal-Lattice-North-Star-Verifier/2.0", "Accept": "application/json,text/html;q=0.9,*/*;q=0.1"}
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
    client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
    if bool(client_id) ^ bool(client_secret):
        raise ValueError("CLOUDFLARE_ACCESS_SERVICE_TOKEN_INCOMPLETE")
    if client_id:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret or ""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as response:
        body = response.read(3_000_001)
        if len(body) > 3_000_000:
            raise ValueError("PUBLIC_RESPONSE_TOO_LARGE")
        return int(response.status), body, {k.lower(): v for k, v in response.headers.items()}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://signal-lattice.linzezhang.com")
    p.add_argument("--version", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--allow-local-test", action="store_true")
    args = p.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    checks: dict[str, bool] = {
        "https": parsed.scheme == "https" or (args.allow_local_test and parsed.scheme == "http"),
        "expected_host": parsed.hostname == EXPECTED_HOST or (args.allow_local_test and parsed.hostname in {"127.0.0.1", "localhost"}),
    }
    diagnostics: dict[str, object] = {}
    try:
        base = args.url.rstrip("/")
        ui_status, ui_body, ui_headers = request(base + "/", timeout=args.timeout)
        api_status, api_body, api_headers = request(base + "/api/v1/system/status", timeout=args.timeout)
        cycle_status, cycle_body, _ = request(base + "/api/v1/cycles/latest", timeout=args.timeout)
        rec_status, rec_body, _ = request(base + "/api/v1/recommendations", timeout=args.timeout)
        skills_status, skills_body, _ = request(base + "/api/v1/skills", timeout=args.timeout)
        ui_text = ui_body.decode("utf-8", errors="replace")
        api = json.loads(api_body.decode("utf-8"))
        cycle = json.loads(cycle_body.decode("utf-8"))
        rec_response = json.loads(rec_body.decode("utf-8"))
        skills_response = json.loads(skills_body.decode("utf-8"))
        current = rec_response.get("current") if isinstance(rec_response, dict) else None
        items = rec_response.get("items") if isinstance(rec_response, dict) else None
        items = items if isinstance(items, list) else []
        skill_runs = cycle.get("skill_runs") if isinstance(cycle, dict) else []
        skill_runs = skill_runs if isinstance(skill_runs, list) else []
        completed_at = cycle.get("completed_at")
        age_seconds = None
        if completed_at:
            age_seconds = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))).total_seconds())
        missing_pipeline_reasons = {
            "ACTIVE_SKILL_COUNT_BELOW_NORTHSTAR_MINIMUM", "COMPLETED_SKILL_COUNT_BELOW_NORTHSTAR_MINIMUM",
            "MARKET_UNIVERSE_EMPTY", "NOT_ALL_ACTIVE_SKILLS_RETURNED_THIS_MINUTE",
            "NO_COMPLETED_MINUTE_CYCLE", "NO_TRUSTED_SKILL_SIGNALS", "NO_TRUSTED_MARKET_SNAPSHOT",
        }
        reasons = set(str(x) for x in (current or {}).get("reasons", []))
        checks.update({
            "ui_http_200": ui_status == 200,
            "api_http_200": api_status == 200,
            "cycle_api_200": cycle_status == 200,
            "recommendation_api_200": rec_status == 200,
            "skills_api_200": skills_status == 200,
            "ui_identity": "Signal Lattice" in ui_text and "唯一投资建议" in ui_text,
            "ui_north_star": "每分钟" in ui_text and "Skill 隔离判断" in ui_text and "中枢协调" in ui_text,
            "api_version": api.get("version") == args.version,
            "api_runtime_pass": api.get("state") == "PASS",
            "runtime_agent_zero": api.get("runtime_agent_dependency") == 0,
            "runtime_token_zero": api.get("runtime_llm_tokens") == 0,
            "automatic_trading_false": api.get("automatic_trading") is False,
            "human_execution_only": api.get("human_execution_only") is True,
            "human_decision_support": api.get("mode") == "HUMAN_DECISION_SUPPORT",
            "cycle_completed": cycle.get("state") == "COMPLETED",
            "cycle_fresh": age_seconds is not None and age_seconds <= 120,
            "active_skills_minimum": int(cycle.get("active_skill_count", 0)) >= 5,
            "all_active_skills_returned": int(cycle.get("completed_skill_count", -1)) == int(cycle.get("active_skill_count", -2)),
            "no_failed_skills": int(cycle.get("failed_skill_count", -1)) == 0,
            "skill_run_receipt_for_every_active_skill": len(skill_runs) == int(cycle.get("active_skill_count", -1)) and all(row.get("state") in {"PASS", "ABSTAIN"} for row in skill_runs),
            "exactly_one_recommendation": len(items) == 1 and isinstance(current, dict) and current == items[0],
            "recommendation_not_system_blocked": isinstance(current, dict) and current.get("action") != "SYSTEM_BLOCKED",
            "full_cycle_flag": isinstance(current, dict) and current.get("full_cycle_completed") is True,
            "effective_skills_minimum": isinstance(current, dict) and int(current.get("effective_skill_count", 0)) >= 3,
            "production_market_data": isinstance(current, dict) and current.get("market_data_production_eligible") is True,
            "market_license_confirmed": isinstance(current, dict) and current.get("market_data_license_ok") is True,
            "no_empty_pipeline_no_action": not bool(reasons & missing_pipeline_reasons),
            "public_url_exact": api.get("public_url") == args.url.rstrip("/") or (args.allow_local_test and api.get("public_url") == "https://signal-lattice.linzezhang.com"),
            "security_headers": all(key in ui_headers for key in ("content-security-policy", "x-frame-options", "x-content-type-options")),
            "api_no_store": "no-store" in api_headers.get("cache-control", ""),
        })
        diagnostics = {
            "cycle_id": cycle.get("cycle_id"), "cycle_state": cycle.get("state"),
            "cycle_age_seconds": age_seconds, "active_skill_count": cycle.get("active_skill_count"),
            "completed_skill_count": cycle.get("completed_skill_count"), "failed_skill_count": cycle.get("failed_skill_count"),
            "current_action": (current or {}).get("action"), "current_symbol": (current or {}).get("symbol"),
            "market_data_source": (current or {}).get("market_data_source"),
            "recommendation_count": len(items), "skill_registry_count": skills_response.get("active_count"),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError, ssl.SSLError) as exc:
        diagnostics["error"] = type(exc).__name__ + ":" + str(exc)[:500]
    payload = {
        "schema_version": "2.0.0",
        "state": "PASS" if checks and all(checks.values()) else "BLOCKED",
        "public_url": args.url.rstrip("/"), "expected_version": args.version,
        "verified_at": datetime.now(timezone.utc).isoformat(), "checks": checks,
        "diagnostics": diagnostics, "north_star_chain_verified": bool(checks and all(checks.values())),
        "runtime_agent_dependency": 0, "runtime_llm_tokens": 0, "automatic_trading": False,
    }
    payload["receipt_sha256"] = canonical_hash(payload)
    atomic_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
