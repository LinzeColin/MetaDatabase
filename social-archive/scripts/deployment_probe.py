from __future__ import annotations

import argparse
import json
import socket
import ssl
import urllib.error
import urllib.request


def _not_run(domain: str) -> int:
    print(json.dumps({
        "domain": domain,
        "status": "NOT_RUN",
        "network_attempted": False,
        "reason": "需要显式 --network-confirmed；--read-only 不执行 DNS 或 HTTPS 请求",
    }, ensure_ascii=False))
    return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only deployment probe")
    parser.add_argument("--domain", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--read-only", action="store_true", help="只输出未执行状态；不访问网络")
    mode.add_argument("--network-confirmed", action="store_true", help="明确授权后才执行只读 DNS/HTTPS 探针")
    args = parser.parse_args()
    if not args.network_confirmed:
        return _not_run(args.domain)

    result: dict[str, object] = {"domain": args.domain, "dns": [], "https": None, "network_attempted": True}
    try:
        result["dns"] = sorted({item[4][0] for item in socket.getaddrinfo(args.domain, 443)})
    except Exception as exc:  # noqa: BLE001 - normalized deployment evidence
        result["dns_error"] = exc.__class__.__name__
    try:
        with urllib.request.urlopen(
            f"https://{args.domain}/health",
            timeout=8,
            context=ssl.create_default_context(),
        ) as response:
            result["https"] = {"status": response.status, "body": response.read(1000).decode(errors="replace")}
    except urllib.error.HTTPError as exc:
        # A public non-2xx response is useful deployment evidence. Keep only its
        # status class: the error body may contain provider-specific diagnostics.
        result["https"] = {"status": exc.code, "error_type": "HTTPError"}
    except Exception as exc:  # noqa: BLE001 - normalized deployment evidence
        result["https"] = {"error_type": exc.__class__.__name__}
    result["status"] = "PASS" if result["dns"] and isinstance(result["https"], dict) and result["https"].get("status") == 200 else "BLOCKED_ENVIRONMENT"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
