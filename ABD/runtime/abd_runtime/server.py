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

from .alpha_skeleton import AlphaSkeletonError, build_alpha_skeleton
from .final_delivery import FinalDeliveryRuntimeError, build_final_delivery
from .ga_reconciliation import GAReconciliationRuntimeError, build_ga_reconciliation
from .observation_evidence import ObservationEvidenceError, build_observation_evidence
from .shadow_beta import ShadowBetaRuntimeError, build_shadow_beta


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
        "<title>ABD 观测台 · 0.0.0.1</title><style>"
        ":root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#07111f;color:#e8f0fb}*{box-sizing:border-box}body{margin:0;min-width:320px}"
        ".shell{width:min(960px,100%);margin:0 auto;padding:48px 24px 64px}.eyebrow{margin:0 0 10px;"
        "color:#8bb9ff;font-size:.78rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase}"
        "h1{margin:0;color:#fff;font-size:clamp(2rem,6vw,3.6rem);line-height:1.05}h2{margin:0 0 14px;"
        "font-size:1rem;color:#fff}.lead{max-width:640px;margin:18px 0 0;color:#b9c9dd;font-size:1.05rem;line-height:1.65}"
        ".badges{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0 30px}.badge{border:1px solid #28577f;"
        "border-radius:999px;padding:7px 11px;color:#b8e5ff;background:#0b2336;font-size:.86rem}.grid{display:grid;"
        "grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.card{border:1px solid #203955;border-radius:18px;"
        "padding:22px;background:linear-gradient(145deg,#0d1d31,#091524);box-shadow:0 14px 38px #0003}.card-wide{grid-column:1/-1}"
        ".facts{display:grid;grid-template-columns:auto 1fr;gap:10px 16px;margin:0}.facts dt{color:#8fa5bd}.facts dd{margin:0;"
        "color:#fff;font-weight:600}.actions{display:grid;gap:10px;margin:0;padding:0;list-style:none}.actions a{display:block;"
        "padding:13px 14px;border:1px solid #2a5f91;border-radius:12px;color:#e8f4ff;text-decoration:none;background:#102b43}"
        ".actions a:hover,.actions a:focus{background:#17456d;outline:2px solid #8bb9ff;outline-offset:2px}.notice{margin:0;"
        "color:#d8e4f1;line-height:1.65}.notice strong{color:#ffd78c}.footer{margin:24px 0 0;color:#8fa5bd;font-size:.86rem;line-height:1.55}"
        "@media(max-width:640px){.shell{padding:32px 18px 48px}.grid{grid-template-columns:1fr}.card-wide{grid-column:auto}}</style>"
        "</head><body><main class=\"shell\"><header><p class=\"eyebrow\">ABD · 0.0.0.1</p>"
        "<h1>ABD 观测台</h1><p class=\"lead\">运行中，但当前只做可审计的只读观察。"
        "这里不会生成建议、提交订单或伪造市场结论。</p></header><div class=\"badges\">"
        "<span class=\"badge\">运行状态：已启动</span><span class=\"badge\">模式：只读观察</span>"
        "<span class=\"badge\">订单：已禁用</span></div><section class=\"grid\" aria-label=\"ABD 当前状态\">"
        "<article class=\"card\"><h2>当前运行边界</h2><dl class=\"facts\"><dt>真实市场 / 账户</dt><dd>未连接</dd>"
        "<dt>TAB / Gmail</dt><dd>未连接</dd><dt>建议 / 下单</dt><dd>已禁用</dd></dl></article>"
        "<article class=\"card\"><h2>校准证据</h2><p class=\"notice\">仅保留 2025/26 E0 单赛季静态描述，"
        "不能用于模型参数更新，也不是实时赔率或市场事实。</p></article>"
        "<article class=\"card card-wide\"><h2>可查看的运行材料</h2><ul class=\"actions\">"
        "<li><a href=\"/alpha\">软件 Alpha：固定合成闭环</a></li>"
        "<li><a href=\"/beta\">Shadow Beta：合成门与阻断状态</a></li>"
        "<li><a href=\"/ga\">GA 对账：零行本地控制</a></li>"
        "<li><a href=\"/delivery\">交付状态：冻结合同与运行边界</a></li>"
        "<li><a href=\"/evidence\">观测证据：静态证据范围</a></li></ul></article>"
        "<article class=\"card card-wide\"><p class=\"notice\"><strong>重要：</strong>该入口受访问保护；"
        "它不代表全球或中国大陆可达承诺。月度 30% 目标尚未验证，也不保证。</p></article></section>"
        "<p class=\"footer\">ABD 以证据、数值与风险门为先；缺少真实来源时保持不建议、不下单。</p>"
        "</main></body></html>"
    ).encode("utf-8")


class RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: Mapping[str, Any]) -> None:
        self.runtime_state = dict(state)
        self.observation_evidence = build_observation_evidence(self.runtime_state)
        self.alpha_skeleton = build_alpha_skeleton(self.runtime_state)
        self.shadow_beta = build_shadow_beta(self.runtime_state)
        self.ga_reconciliation = build_ga_reconciliation(self.runtime_state)
        self.final_delivery = build_final_delivery(self.runtime_state)
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
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        )
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
        if path == "/alpha":
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                _json_bytes(self.server.alpha_skeleton),
                head_only=head_only,
            )
            return
        if path == "/beta":
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                _json_bytes(self.server.shadow_beta),
                head_only=head_only,
            )
            return
        if path == "/ga":
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                _json_bytes(self.server.ga_reconciliation),
                head_only=head_only,
            )
            return
        if path == "/delivery":
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                _json_bytes(self.server.final_delivery),
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
    except (
        TypeError,
        ValueError,
        RuntimeConfigurationError,
        ObservationEvidenceError,
        AlphaSkeletonError,
        FinalDeliveryRuntimeError,
        GAReconciliationRuntimeError,
        ShadowBetaRuntimeError,
    ) as exc:
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
