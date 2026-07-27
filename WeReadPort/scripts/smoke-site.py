#!/usr/bin/env python3
"""无需第三方依赖的微信读书笔记迁移生产黑盒冒烟测试。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 2 * 1024 * 1024
EXPECTED_APP_VERSION = "v0.0.0.1.8"
EXPECTED_SKILL_VERSION = "1.0.4"
EXPECTED_BUSINESS_SCHEMA_VERSION = "2.0.0"
EXPECTED_BUSINESS_LINES = {
    "public-trust", "identity-access", "account-storage", "cross-device-sync",
    "provider-imports", "weread-wide-sync", "analytics-recommendations",
    "legacy-migration", "release-supply-chain", "operations-recovery", "facts-backup",
}


def origin(value: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("生产网址必须是无凭据 HTTPS origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("生产网址不得包含路径、查询参数或片段")
    return f"https://{parsed.netloc}"


def fetch(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 15.0):
    started = time.monotonic()
    request_headers = {
        "User-Agent": "WeReadPort-Smoke/0.0.0.1.8",
        "Accept": "application/json, text/html;q=0.9",
    }
    request_headers.update(headers or {})
    request = Request(url, data=body, method=method, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise RuntimeError("response_too_large")
            return int(response.status), {k.lower(): v for k, v in response.headers.items()}, raw, round((time.monotonic() - started) * 1000, 2)
    except HTTPError as error:
        raw = error.read(MAX_BYTES + 1)
        return int(error.code), {k.lower(): v for k, v in error.headers.items()}, raw, round((time.monotonic() - started) * 1000, 2)


def add(checks: list[dict[str, object]], name: str, status: int, latency: float, passed: bool, detail: str = "") -> None:
    checks.append({"name": name, "status": status, "latencyMs": latency, "pass": passed, "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("origin")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", help="可选：写入脱敏 JSON 证据文件")
    args = parser.parse_args()
    base = origin(args.origin)
    checks: list[dict[str, object]] = []

    status, headers, raw, latency = fetch(base + "/healthz", timeout=args.timeout)
    health = json.loads(raw.decode("utf-8"))
    add(checks, "liveness", status, latency, status == 200 and health.get("status") == "ALIVE", str(health.get("status")))

    status, headers, raw, latency = fetch(base + "/readyz", timeout=args.timeout)
    readiness = json.loads(raw.decode("utf-8"))
    readiness_ok = (
        status == 200
        and readiness.get("status") == "READY"
        and readiness.get("checks", {}).get("staticAssets", {}).get("ready") is True
        and readiness.get("checks", {}).get("accountPlatformService", {}).get("ready") is True
        and readiness.get("checks", {}).get("businessGovernanceContract", {}).get("schemaVersion") == EXPECTED_BUSINESS_SCHEMA_VERSION
    )
    add(checks, "readiness", status, latency, readiness_ok, str(readiness.get("status")))

    status, headers, raw, latency = fetch(base + "/api/status", timeout=args.timeout)
    public_status = json.loads(raw.decode("utf-8"))
    status_text = raw.decode("utf-8", errors="replace")
    safe = all(item not in status_text for item in ["wrk-", "Authorization", "PRIVATE_DATABASE_TOKEN", "R2_SECRET", "笔记正文"])
    governance = public_status.get("businessGovernance") if isinstance(public_status.get("businessGovernance"), dict) else {}
    lines = governance.get("lines") if isinstance(governance.get("lines"), list) else []
    observed_ids = {str(line.get("id")) for line in lines if isinstance(line, dict)}
    governance_ok = (
        governance.get("schemaVersion") == EXPECTED_BUSINESS_SCHEMA_VERSION
        and governance.get("graphStatus") == "VALID"
        and observed_ids == EXPECTED_BUSINESS_LINES
        and len(lines) == len(EXPECTED_BUSINESS_LINES)
        and all(isinstance(line, dict) and line.get("state") != "BLOCKED" for line in lines)
        and public_status.get("dataBoundary", {}).get("businessGovernanceContainsUserContent") is False
    )
    add(checks, "public_status", status, latency, status == 200 and public_status.get("status") == "OPERATIONAL" and safe and governance_ok, f"status={public_status.get('status')};governance={governance.get('graphStatus')}")
    add(checks, "business_governance", status, latency, governance_ok, f"schema={governance.get('schemaVersion')};lines={len(lines)}")

    status, headers, raw, latency = fetch(base + "/api/version", timeout=args.timeout)
    version = json.loads(raw.decode("utf-8"))
    add(checks, "version", status, latency, status == 200 and version.get("appVersion") == EXPECTED_APP_VERSION and version.get("sourceSkillVersion") == EXPECTED_SKILL_VERSION and version.get("businessGovernanceSchemaVersion") == EXPECTED_BUSINESS_SCHEMA_VERSION, str(version))

    for route, required in [
        ("/", ["一个账户", "用密钥快速开始", "用 Google 创建", "使用邮箱和密码"]),
        ("/privacy/", ["隐私政策", "账户隔离", "长期存储", "一键导入"]),
        ("/terms/", ["使用条款", "禁止用途", "账户", "同步"]),
        ("/status/", ["系统状态", "/healthz", "/readyz", "/api/status", "账户与多平台身份", "四平台一键导入", "画像、热度与推荐"]),
    ]:
        status, headers, raw, latency = fetch(base + route, timeout=args.timeout)
        page = raw.decode("utf-8", errors="replace")
        security = all(name in headers for name in ["content-security-policy", "referrer-policy", "x-content-type-options"])
        add(checks, f"page:{route}", status, latency, status == 200 and all(text in page for text in required) and security, f"required={required};security={security}")

    # 负向安全路径：没有凭据时必须在调用上游前拒绝，且不得泄露认证信息。
    status, headers, raw, latency = fetch(
        base + "/api/weread/gateway",
        method="POST",
        body=b'{"api_name":"/user/notebooks"}',
        headers={"Content-Type": "application/json", "Origin": base, "Sec-Fetch-Site": "same-origin"},
        timeout=args.timeout,
    )
    text = raw.decode("utf-8", errors="replace")
    add(checks, "unauthenticated_proxy_rejected", status, latency, status in {400, 401, 403} and "wrk-" not in text and "Authorization" not in text, text[:160])

    passed = all(bool(item["pass"]) for item in checks)
    result = {"status": "PASS" if passed else "FAIL", "origin": base, "checks": checks}
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        from pathlib import Path
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
