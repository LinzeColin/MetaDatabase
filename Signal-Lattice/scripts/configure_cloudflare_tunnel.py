#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

API_BASE = "https://api.cloudflare.com/client/v4"


def canonical_sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CloudflareError(RuntimeError):
    pass


class Client:
    def __init__(self, token: str, opener: Callable[..., Any] = urllib.request.urlopen, api_base: str = API_BASE):
        if not token:
            raise CloudflareError("CLOUDFLARE_API_TOKEN_REQUIRED")
        self.token = token
        self.opener = opener
        self.api_base = api_base.rstrip("/")

    def request(self, method: str, path: str, payload: object | None = None) -> Any:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        req = urllib.request.Request(
            self.api_base + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "signal-lattice/0.0.0.1.40",
            },
        )
        try:
            with self.opener(req, timeout=30) as response:
                data = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise CloudflareError(f"CLOUDFLARE_API_ERROR:{type(exc).__name__}") from exc
        if not isinstance(data, dict) or data.get("success") is not True:
            errors = data.get("errors") if isinstance(data, dict) else None
            raise CloudflareError("CLOUDFLARE_API_REJECTED:" + json.dumps(errors, separators=(",", ":")))
        return data.get("result")


def _tunnel_id(client: Client, account_id: str, name: str) -> tuple[str, bool, str | None]:
    query = urllib.parse.urlencode({"name": name, "is_deleted": "false", "per_page": 100})
    result = client.request("GET", f"/accounts/{account_id}/cfd_tunnel?{query}")
    rows = result if isinstance(result, list) else []
    exact = [row for row in rows if isinstance(row, dict) and row.get("name") == name and not row.get("deleted_at")]
    if len(exact) > 1:
        raise CloudflareError("DUPLICATE_TUNNEL_NAME")
    if exact:
        return str(exact[0]["id"]), False, None
    created = client.request("POST", f"/accounts/{account_id}/cfd_tunnel", {"name": name, "config_src": "cloudflare"})
    if not isinstance(created, dict) or not created.get("id"):
        raise CloudflareError("TUNNEL_CREATE_RESPONSE_INVALID")
    return str(created["id"]), True, str(created.get("token")) if created.get("token") else None


def _ensure_dns(client: Client, zone_id: str, hostname: str, content: str) -> tuple[str, str]:
    query = urllib.parse.urlencode({"type": "CNAME", "name": hostname, "per_page": 100})
    result = client.request("GET", f"/zones/{zone_id}/dns_records?{query}")
    rows = result if isinstance(result, list) else []
    payload = {"type": "CNAME", "name": hostname, "content": content, "proxied": True, "ttl": 1}
    if len(rows) > 1:
        raise CloudflareError("DUPLICATE_DNS_RECORD")
    if rows:
        record_id = str(rows[0]["id"])
        current = rows[0]
        if current.get("content") != content or current.get("proxied") is not True:
            client.request("PUT", f"/zones/{zone_id}/dns_records/{record_id}", payload)
            return record_id, "UPDATED"
        return record_id, "UNCHANGED"
    created = client.request("POST", f"/zones/{zone_id}/dns_records", payload)
    if not isinstance(created, dict) or not created.get("id"):
        raise CloudflareError("DNS_CREATE_RESPONSE_INVALID")
    return str(created["id"]), "CREATED"


def _write_secret(path: Path, value: str) -> None:
    if not value or "\n" in value or "\r" in value:
        raise CloudflareError("TUNNEL_TOKEN_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def configure(
    *, account_id: str, zone_id: str, hostname: str, origin: str, tunnel_name: str,
    token_file: Path, api_token: str, existing_tunnel_token: str = "",
    opener: Callable[..., Any] = urllib.request.urlopen, api_base: str = API_BASE,
) -> dict[str, Any]:
    if not account_id or not zone_id:
        raise CloudflareError("CLOUDFLARE_ACCOUNT_AND_ZONE_REQUIRED")
    if hostname != "signal-lattice.linzezhang.com":
        raise CloudflareError("UNAPPROVED_HOSTNAME")
    if origin not in {"http://127.0.0.1:8787", "http://localhost:8787"}:
        raise CloudflareError("UNAPPROVED_ORIGIN")
    client = Client(api_token, opener=opener, api_base=api_base)
    tunnel_id, created, created_token = _tunnel_id(client, account_id, tunnel_name)
    client.request("PUT", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations", {
        "config": {"ingress": [
            {"hostname": hostname, "service": origin, "originRequest": {"connectTimeout": 10, "noHappyEyeballs": False}},
            {"service": "http_status:404"},
        ]}
    })
    record_id, dns_state = _ensure_dns(client, zone_id, hostname, f"{tunnel_id}.cfargotunnel.com")
    tunnel_token = existing_tunnel_token or created_token
    if not tunnel_token:
        tunnel_token = client.request("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/token")
    if not isinstance(tunnel_token, str):
        raise CloudflareError("TUNNEL_TOKEN_RESPONSE_INVALID")
    _write_secret(token_file, tunnel_token)
    payload: dict[str, Any] = {
        "schema_version": "1.0.0", "state": "PASS", "hostname": hostname, "origin": origin,
        "tunnel_name": tunnel_name, "tunnel_id": tunnel_id, "tunnel_created": created,
        "dns_record_id": record_id, "dns_state": dns_state, "token_file": str(token_file),
        "token_sha256": hashlib.sha256(tunnel_token.encode()).hexdigest(), "secret_emitted": False,
    }
    payload["receipt_sha256"] = canonical_sha(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    parser.add_argument("--zone-id", default=os.environ.get("CLOUDFLARE_ZONE_ID", ""))
    parser.add_argument("--hostname", default="signal-lattice.linzezhang.com")
    parser.add_argument("--origin", default="http://127.0.0.1:8787")
    parser.add_argument("--tunnel-name", default="signal-lattice")
    parser.add_argument("--token-file", type=Path, default=Path("/etc/signal-lattice/credentials/cloudflare_tunnel_token"))
    parser.add_argument("--receipt", type=Path, default=Path("/var/lib/signal-lattice/artifacts/cloudflare_tunnel.json"))
    args = parser.parse_args()
    try:
        result = configure(
            account_id=args.account_id, zone_id=args.zone_id, hostname=args.hostname, origin=args.origin,
            tunnel_name=args.tunnel_name, token_file=args.token_file,
            api_token=os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            existing_tunnel_token=os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", ""),
        )
    except CloudflareError as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc), "developer_research_required": False}, sort_keys=True))
        return 2
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(args.receipt, 0o600)
    print(json.dumps({k: v for k, v in result.items() if k != "token_sha256"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
