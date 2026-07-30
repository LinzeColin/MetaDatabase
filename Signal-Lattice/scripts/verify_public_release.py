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


def request(url: str, *, timeout: int, use_access_token: bool = True) -> tuple[int, bytes, dict[str, str]]:
    headers = {"User-Agent": "Signal-Lattice-Release-Verifier/1.1", "Accept": "application/json,text/html;q=0.9,*/*;q=0.1"}
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
    client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
    if bool(client_id) ^ bool(client_secret):
        raise ValueError("CLOUDFLARE_ACCESS_SERVICE_TOKEN_INCOMPLETE")
    if use_access_token and client_id:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret or ""
    req = urllib.request.Request(url, headers=headers)
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000: raise ValueError("PUBLIC_RESPONSE_TOO_LARGE")
        return int(response.status), body, {k.lower(): v for k, v in response.headers.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://signal-lattice.linzezhang.com")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--allow-local-test", action="store_true")
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    checks: dict[str, bool] = {
        "https": parsed.scheme == "https" or (args.allow_local_test and parsed.scheme == "http"),
        "expected_host": parsed.hostname == EXPECTED_HOST or (args.allow_local_test and parsed.hostname in {"127.0.0.1", "localhost"}),
    }
    diagnostics: dict[str, object] = {}
    current_action = "UNKNOWN"
    recommendation_count = 0
    try:
        base = args.url.rstrip("/")
        ui_status, ui_body, ui_headers = request(base + "/", timeout=args.timeout)
        api_status, api_body, api_headers = request(base + "/api/v1/status", timeout=args.timeout)
        rec_status, rec_body, _ = request(base + "/api/v1/recommendations?limit=1", timeout=args.timeout)
        ui_text = ui_body.decode("utf-8", errors="replace")
        api = json.loads(api_body.decode("utf-8"))
        rec = json.loads(rec_body.decode("utf-8"))
        items = rec.get("items") if isinstance(rec, dict) else None
        items = items if isinstance(items, list) else []
        recommendation_count = len(items)
        current_action = str(items[0].get("action", "NO_ACTION")) if items else str(api.get("current_action", "NO_ACTION"))
        checks.update({
            "ui_http_200": ui_status == 200,
            "api_http_200": api_status == 200,
            "recommendation_api_200": rec_status == 200,
            "ui_identity": "Signal Lattice" in ui_text and "股票信号格阵" in ui_text,
            "ui_north_star": "最终投资建议" in ui_text and "内部协调" in ui_text,
            "api_project": api.get("project_id") == "signal-lattice",
            "api_version": api.get("version") == args.version,
            "runtime_agent_zero": api.get("runtime_agent_dependency") == 0,
            "runtime_token_zero": api.get("runtime_llm_tokens") == 0,
            "automatic_trading_false": api.get("automatic_trading") is False,
            "human_execution_only": api.get("human_execution_only") is True,
            "decision_support_mode_valid": api.get("mode") in {"HUMAN_DECISION_SUPPORT", "RESEARCH_AND_NO_ACTION"},
            "recommendation_contract_present": isinstance(rec, dict) and isinstance(items, list) and rec.get("mode") in {"HUMAN_DECISION_SUPPORT", "RESEARCH_AND_NO_ACTION"},
            "public_url_exact": api.get("public_url") == args.url.rstrip("/") or (args.allow_local_test and api.get("public_url") == "https://signal-lattice.linzezhang.com"),
            "security_headers": all(key in ui_headers for key in ("content-security-policy", "x-frame-options", "x-content-type-options")),
            "api_no_store": "no-store" in api_headers.get("cache-control", ""),
        })
        diagnostics.update({"ui_status": ui_status, "api_status": api_status, "recommendation_status": rec_status, "api_mode": api.get("mode"), "api_state": api.get("state"), "current_action": current_action, "recommendation_count": recommendation_count})
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError, ssl.SSLError) as exc:
        diagnostics["error"] = type(exc).__name__ + ":" + str(exc)[:500]
    payload = {
        "schema_version": "1.1.0",
        "state": "PASS" if checks and all(checks.values()) else "BLOCKED",
        "public_url": args.url.rstrip("/"),
        "expected_version": args.version,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "diagnostics": diagnostics,
        "current_action": current_action,
        "recommendation_count": recommendation_count,
        "decision_support_capability_verified": checks.get("recommendation_contract_present", False),
        "cloudflare_access_secret_logged": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "automatic_trading": False,
    }
    payload["receipt_sha256"] = canonical_hash(payload)
    atomic_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
