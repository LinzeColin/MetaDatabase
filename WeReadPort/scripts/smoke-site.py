#!/usr/bin/env python3
"""无需第三方依赖的微信读书笔记迁移线上黑盒冒烟测试。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 2 * 1024 * 1024


def origin(value: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("origin must be credential-free HTTPS")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("origin must not contain path, query or fragment")
    return f"https://{parsed.netloc}"


def fetch(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 15.0):
    started = time.monotonic()
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise RuntimeError("response_too_large")
            return int(response.status), dict(response.headers), raw, round((time.monotonic() - started) * 1000, 2)
    except HTTPError as error:
        raw = error.read(MAX_BYTES + 1)
        return int(error.code), dict(error.headers), raw, round((time.monotonic() - started) * 1000, 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("origin")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    base = origin(args.origin)
    checks: list[dict[str, object]] = []

    status, headers, raw, latency = fetch(base + "/healthz", timeout=args.timeout)
    health = json.loads(raw.decode("utf-8"))
    checks.append({"name": "health", "status": status, "latencyMs": latency, "pass": status == 200 and health.get("ok") is True})

    status, headers, raw, latency = fetch(base + "/api/version", timeout=args.timeout)
    version = json.loads(raw.decode("utf-8"))
    checks.append({
        "name": "version",
        "status": status,
        "latencyMs": latency,
        "pass": status == 200 and version.get("appVersion") == "v0.0.0.1.3" and version.get("sourceSkillVersion") == "1.0.4",
    })

    status, headers, raw, latency = fetch(base + "/", timeout=args.timeout)
    page = raw.decode("utf-8", errors="replace")
    checks.append({"name": "landing", "status": status, "latencyMs": latency, "pass": status == 200 and "微信读书笔记迁移" in page})

    # Negative security path: no credential, no upstream call, no user data.
    status, headers, raw, latency = fetch(
        base + "/api/weread/gateway",
        method="POST",
        body=b'{"api_name":"/user/notebooks"}',
        headers={"Content-Type": "application/json", "Origin": base},
        timeout=args.timeout,
    )
    text = raw.decode("utf-8", errors="replace")
    checks.append({
        "name": "unauthenticated_proxy_rejected",
        "status": status,
        "latencyMs": latency,
        "pass": status in {400, 401, 403} and "wrk-" not in text and "Authorization" not in text,
    })

    passed = all(bool(item["pass"]) for item in checks)
    result = {"status": "PASS" if passed else "FAIL", "origin": base, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
