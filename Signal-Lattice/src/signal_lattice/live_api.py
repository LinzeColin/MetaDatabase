"""V2 只读 API。阻断态清晰说明数据链路不完整且没有任何投资动作。"""

from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .aggregate import blocked_decision
from .live_config import APP_VERSION, LiveSettings
from .live_runtime import LiveStore


HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def blocked_report() -> dict:
    return {
        "state": "SYSTEM_BLOCKED",
        "message": "数据链路不完整，不出结论",
        "decision": blocked_decision(),
    }


def handler(settings: LiveSettings, store: LiveStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return None

        def _send(self, status: int, payload, content_type: str = "application/json; charset=utf-8") -> None:
            raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            for key, value in HEADERS.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def _latest(self) -> dict:
            return store.latest()

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            latest = self._latest()
            if path == "/health/live":
                return self._send(200, {"status": "alive", "version": APP_VERSION})
            if path == "/health/ready":
                ready = latest.get("state") == "DATA_READY"
                return self._send(200 if ready else 503, {"status": "ready" if ready else "blocked", "state": latest.get("state", "SYSTEM_BLOCKED")})
            if path == "/api/v1/report/latest":
                return self._send(200 if latest else 503, latest or blocked_report())
            if path == "/api/v1/whitebox/summary":
                return self._send(200, {
                    "state": latest.get("state", "SYSTEM_BLOCKED"),
                    "weight_mode": latest.get("weight_mode", "COLD_START_EQUAL"),
                    "weight_sample_count": latest.get("weight_sample_count", 0),
                    "contribution_weights": latest.get("contribution_weights", {"branches": []}),
                    "branch_count": len(latest.get("branches", [])),
                    "quote_observed_at": latest.get("quote_observed_at"),
                    "data_cutoff": latest.get("data_cutoff"),
                    "profitability_status": latest.get("profitability_status", "SAMPLE_INSUFFICIENT"),
                    "automatic_trading": False,
                })
            if path == "/api/v1/whitebox/skills":
                return self._send(200, {"state": latest.get("state", "SYSTEM_BLOCKED"), "items": latest.get("branches", [])})
            if path == "/api/v1/whitebox/backtest/latest":
                return self._send(200, latest.get("backtest", {"status": "SAMPLE_INSUFFICIENT", "message": "样本不足，未出具收益结论"}))
            if path in {"/api/v1/heartbeat", "/api/v1/metadata", "/api/v1/system/status"}:
                return self._send(200, {
                    "application_version": APP_VERSION,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                    "state": latest.get("state", "SYSTEM_BLOCKED"),
                    "quote_observed_at": latest.get("quote_observed_at"),
                    "data_cutoff": latest.get("data_cutoff"),
                    "automatic_trading": False,
                    "public_url": settings.public_url,
                })
            filename = "index.html" if path in {"", "/"} else path.lstrip("/")
            target = (settings.web_dir / filename).resolve()
            if settings.web_dir.resolve() not in target.parents and target != settings.web_dir.resolve():
                return self._send(403, {"error": "FORBIDDEN"})
            if target.is_file():
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type == "application/javascript":
                    content_type += "; charset=utf-8"
                return self._send(200, target.read_bytes(), content_type)
            return self._send(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:
            self._send(405, {"error": "READ_ONLY_RESEARCH_SYSTEM"})
    return Handler


def serve(settings: LiveSettings) -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), handler(settings, LiveStore(settings.state_dir)))
    server.serve_forever()
