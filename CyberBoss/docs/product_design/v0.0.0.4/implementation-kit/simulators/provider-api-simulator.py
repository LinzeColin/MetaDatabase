#!/usr/bin/env python3
"""Bounded Cloudflare-shaped API simulator for CB-020 contract tests."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


STATE: dict[str, object] = {
    "apps": [],
    "buckets": [],
    "dns_records": [],
    "operation_log": [],
}


class Handler(BaseHTTPRequestHandler):
    server_version = "CyberBossProviderFixture/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, value: object) -> None:
        payload = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("body_too_large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("body_not_object")
        return value

    def _success(self, result: object) -> None:
        self._json(200, {"success": True, "errors": [], "messages": [], "result": result})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/__state":
            self._success(STATE)
            return
        if path.endswith("/access/apps"):
            items = list(STATE["apps"])
            domain = (query.get("domain") or [None])[0]
            if domain:
                items = [item for item in items if item.get("domain") == domain]
            self._success(items)
            return
        if path.endswith("/r2/buckets"):
            self._success(list(STATE["buckets"]))
            return
        if path.endswith("/dns_records"):
            items = list(STATE["dns_records"])
            name = (query.get("name") or [None])[0]
            record_type = (query.get("type") or [None])[0]
            if name:
                items = [item for item in items if item.get("name") == name]
            if record_type:
                items = [item for item in items if item.get("type") == record_type]
            self._success(items)
            return
        self._json(404, {"success": False, "errors": [{"code": 404}]})

    def do_POST(self) -> None:
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"success": False, "errors": [{"code": 400}]})
            return
        path = urlparse(self.path).path
        if path.endswith("/access/apps"):
            item = dict(body)
            item["id"] = f"app-{len(STATE['apps']) + 1}"
            STATE["apps"].append(item)
            STATE["operation_log"].extend(["access_application", "access_policy"])
            self._success(item)
            return
        if path.endswith("/r2/buckets"):
            item = dict(body)
            STATE["buckets"].append(item)
            STATE["operation_log"].append("r2_bucket")
            self._success(item)
            return
        if path.endswith("/dns_records"):
            item = dict(body)
            item["id"] = f"dns-{len(STATE['dns_records']) + 1}"
            STATE["dns_records"].append(item)
            STATE["operation_log"].append("dns")
            self._success(item)
            return
        self._json(404, {"success": False, "errors": [{"code": 404}]})

    def do_PUT(self) -> None:
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"success": False, "errors": [{"code": 400}]})
            return
        path = urlparse(self.path).path
        if "/access/apps/" in path:
            identifier = path.rsplit("/", 1)[-1]
            for index, item in enumerate(STATE["apps"]):
                if item.get("id") == identifier:
                    replacement = dict(body)
                    replacement["id"] = identifier
                    STATE["apps"][index] = replacement
                    STATE["operation_log"].extend(
                        ["access_application", "access_policy"]
                    )
                    self._success(replacement)
                    return
        if "/dns_records/" in path:
            identifier = path.rsplit("/", 1)[-1]
            for index, item in enumerate(STATE["dns_records"]):
                if item.get("id") == identifier:
                    replacement = dict(body)
                    replacement["id"] = identifier
                    STATE["dns_records"][index] = replacement
                    STATE["operation_log"].append("dns")
                    self._success(replacement)
                    return
        self._json(404, {"success": False, "errors": [{"code": 404}]})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "status": "ready",
                "host": args.host,
                "port": server.server_address[1],
                "real_provider": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
