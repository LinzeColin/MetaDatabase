"""Minimal HTTP control plane for the ABD observation runtime."""

from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from .observation_evidence import ObservationEvidenceError, build_observation_evidence


VERSION = "0.0.0.1"
OBSERVATION_MODE = "OBSERVATION_ONLY"
SHADOW_READ_ONLY_MODE = "SHADOW_READ_ONLY"
ALLOWED_RUNTIME_MODES = frozenset({OBSERVATION_MODE, SHADOW_READ_ONLY_MODE})
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"


class RuntimeConfigurationError(ValueError):
    """Raised when the runtime configuration would weaken a safety boundary."""


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeConfigurationError("%s must be an object" % label)
    return value


def build_runtime_state(config_path: Path, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Load only non-secret configuration and prove the observation boundary."""

    values = os.environ if environment is None else environment
    if values.get("ABD_ORDER_SUBMISSION_ENABLED", "false") != "false":
        raise RuntimeConfigurationError("order submission must remain disabled")
    runtime_mode = values.get("ABD_RUNTIME_MODE", OBSERVATION_MODE)
    if runtime_mode not in ALLOWED_RUNTIME_MODES:
        raise RuntimeConfigurationError("runtime mode must be observation-only or shadow-read-only")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeConfigurationError("runtime configuration is unreadable") from exc

    config = _require_mapping(payload, "runtime configuration")
    runtime = _require_mapping(config.get("runtime"), "runtime")
    network = _require_mapping(config.get("network"), "network")
    if config.get("product_version") != VERSION:
        raise RuntimeConfigurationError("product version does not match runtime")
    if config.get("activation_requested") is not False:
        raise RuntimeConfigurationError("activation_requested must be false")
    if runtime.get("order_submission_enabled") is not False:
        raise RuntimeConfigurationError("runtime order submission must be false")
    if network.get("public_business_inbound_enabled") is not False:
        raise RuntimeConfigurationError("public business inbound must be false")

    return {
        "service": "ABD",
        "version": VERSION,
        "mode": runtime_mode,
        "decision": SAFE_DECISION,
        "ready": True,
        "recommendation_enabled": False,
        "order_submission_enabled": False,
        "market_or_account_connected": False,
        "gmail_or_tab_connected": False,
    }


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _home_page() -> bytes:
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>ABD 运行状态</title></head><body><main><h1>ABD 0.0.0.1</h1>"
        "<p>运行控制面已启动，当前为只读观察。</p>"
        "<p>静态校准证据仅覆盖 2025/26 E0 单赛季描述，不能用于模型参数更新。</p>"
        "<p>系统不生成建议、不连接真实市场、账户、TAB 或 Gmail，也不执行订单。</p>"
        "<p>此页面仅通过受保护访问入口提供，不代表全球或中国大陆可达承诺。</p>"
        "<p>月度 30% 目标尚未验证且不保证。</p>"
        "</main></body></html>"
    ).encode("utf-8")


class RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: Mapping[str, Any]) -> None:
        self.runtime_state = dict(state)
        self.observation_evidence = build_observation_evidence(self.runtime_state)
        super().__init__(address, RuntimeRequestHandler)


class RuntimeRequestHandler(BaseHTTPRequestHandler):
    server: RuntimeHTTPServer
    protocol_version = "HTTP/1.1"

    def _send(self, status: HTTPStatus, content_type: str, body: bytes, *, head_only: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _route(self, *, head_only: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", _home_page(), head_only=head_only)
            return
        if path in {"/healthz", "/readyz", "/status"}:
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", _json_bytes(self.server.runtime_state), head_only=head_only)
            return
        if path == "/evidence":
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                _json_bytes(self.server.observation_evidence),
                head_only=head_only,
            )
            return
        self._send(
            HTTPStatus.NOT_FOUND,
            "application/json; charset=utf-8",
            _json_bytes({"code": "NOT_FOUND", "decision": SAFE_DECISION}),
            head_only=head_only,
        )

    def do_GET(self) -> None:
        self._route(head_only=False)

    def do_HEAD(self) -> None:
        self._route(head_only=True)

    def do_POST(self) -> None:
        self._send(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "application/json; charset=utf-8",
            _json_bytes({"code": "METHOD_NOT_ALLOWED", "decision": SAFE_DECISION}),
        )

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def log_message(self, _format: str, *_args: object) -> None:
        sys.stderr.write("abd-runtime request-complete\n")


def create_server(host: str, port: int, state: Mapping[str, Any]) -> RuntimeHTTPServer:
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise RuntimeConfigurationError("runtime port must be an integer in [1024, 65535]")
    return RuntimeHTTPServer((host, port), state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABD observation-only runtime")
    parser.add_argument("--config", default=os.environ.get("ABD_CONFIG_FILE", "/etc/abd/config.json"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default="8080")
    args = parser.parse_args(argv)
    try:
        port = int(args.port)
        state = build_runtime_state(Path(args.config))
        server = create_server(args.host, port, state)
    except (TypeError, ValueError, RuntimeConfigurationError, ObservationEvidenceError) as exc:
        print("ABD runtime configuration rejected: %s" % exc, file=sys.stderr)
        return 2
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
