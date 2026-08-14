from __future__ import annotations

import json
import mimetypes
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import APP_VERSION, PROMPT_VERSION
from .config import Settings
from .storage import RuntimeStorage

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cache-Control": "no-store",
}


def _age_seconds(envelope: dict | None) -> float | None:
    if not envelope:
        return None
    value = envelope.get("generated_at")
    if not value:
        return None
    try:
        generated = datetime.fromisoformat(str(value)).astimezone(timezone.utc)
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - generated).total_seconds())


def handler(settings: Settings, storage: RuntimeStorage):
    class H(BaseHTTPRequestHandler):
        server_version = f"SignalLatticeV19/{APP_VERSION}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            return None

        def _headers(self) -> None:
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._headers()
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _send_text(self, status: int, payload: str) -> None:
            self._send_bytes(status, payload.encode("utf-8"), "text/plain; charset=utf-8")

        def _latest(self) -> dict | None:
            return storage.latest()

        def _stream(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            for key, value in SECURITY_HEADERS.items():
                if key != "Cache-Control":
                    self.send_header(key, value)
            self.end_headers()
            last_modified = 0
            heartbeat_at = 0.0
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                try:
                    modified = storage.latest_file.stat().st_mtime_ns if storage.latest_file.is_file() else 0
                    if modified and modified != last_modified:
                        envelope = self._latest()
                        if envelope and isinstance(envelope.get("report"), dict):
                            payload = json.dumps(envelope["report"], ensure_ascii=False, separators=(",", ":"))
                            self.wfile.write(f"event: report\ndata: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                            last_modified = modified
                            heartbeat_at = time.monotonic()
                    elif time.monotonic() - heartbeat_at >= 10:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        heartbeat_at = time.monotonic()
                    time.sleep(1)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
            self.close_connection = True

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health/live":
                return self._send_json(200, {"status": "alive", "version": APP_VERSION})
            if path == "/health/ready":
                envelope = self._latest()
                age = _age_seconds(envelope)
                ready = age is not None and age <= settings.report_stale_seconds
                return self._send_json(200 if ready else 503, {
                    "status": "ready" if ready else "stale",
                    "version": APP_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "refresh_seconds": settings.refresh_seconds,
                    "age_seconds": round(age, 2) if age is not None else None,
                })
            if path == "/api/v1/report/latest":
                envelope = self._latest()
                if not envelope:
                    return self._send_json(503, {"error": "NO_V19_REPORT"})
                return self._send_json(200, envelope["report"])
            if path == "/api/v1/report/latest.txt":
                envelope = self._latest()
                if not envelope:
                    return self._send_text(503, "NO_V19_REPORT")
                return self._send_text(200, str(envelope.get("rendered", "")))
            if path == "/api/v1/stream":
                return self._stream()
            if path == "/api/v1/history":
                query = parse_qs(parsed.query)
                try:
                    limit = min(max(int((query.get("limit") or ["50"])[0]), 1), 200)
                except ValueError:
                    limit = 50
                rows = storage.history(limit)
                return self._send_json(200, {"items": [row.get("report") for row in rows if isinstance(row.get("report"), dict)]})
            if path in {"/api/v1/metadata", "/api/v1/system/status"}:
                envelope = self._latest()
                age = _age_seconds(envelope)
                report = envelope.get("report", {}) if envelope else {}
                first = report.get("第一板块", {}) if isinstance(report, dict) else {}
                state = "PASS" if age is not None and age <= settings.report_stale_seconds else "DEGRADED"
                return self._send_json(200, {
                    "project_id": "signal-lattice",
                    "version": APP_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "refresh_seconds": settings.refresh_seconds,
                    "state": state,
                    "public_url": settings.public_url,
                    "status_url": settings.status_url,
                    "automatic_trading": False,
                    "shadow_only": True,
                    "current_action": first.get("唯一操作", "持有"),
                    "current_symbol": first.get("代码", "SPY"),
                    "report_age_seconds": round(age, 2) if age is not None else None,
                })

            file_name = "index.html" if path in {"", "/"} else path.lstrip("/")
            target = (settings.web_dir / file_name).resolve()
            web_root = settings.web_dir.resolve()
            if target != web_root and web_root not in target.parents:
                return self._send_json(403, {"error": "FORBIDDEN"})
            if target.is_file():
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
                    content_type += "; charset=utf-8"
                return self._send_bytes(200, target.read_bytes(), content_type)
            return self._send_json(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:
            self._send_json(405, {"error": "READ_ONLY_SHADOW_SYSTEM"})

    return H


def serve(settings: Settings, storage: RuntimeStorage) -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), handler(settings, storage))
    server.daemon_threads = True
    server.serve_forever()
