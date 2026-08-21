from __future__ import annotations

import json
import mimetypes
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import APP_VERSION, PROMPT_VERSION
from .config import Settings
from .storage import RuntimeStorage
from .whitebox import WhiteboxLedger

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


def _input_provenance(settings: Settings, envelope: dict | None) -> dict[str, str]:
    internal = envelope.get("internal") if isinstance(envelope, dict) else None
    market_context = internal.get("market_context") if isinstance(internal, dict) else None
    raw_state = str(market_context.get("provider_state", "") if isinstance(market_context, dict) else "").strip().lower()
    provider_state = raw_state if raw_state in {"live", "fixture", "last_snapshot", "full_scan_pending", "error"} else "unknown"

    if settings.market_provider == "moomoo" and provider_state == "live":
        return {
            "market_provider": "moomoo",
            "provider_state": "live",
            "input_provenance": "LIVE_MOOMOO_QUOTE",
            "acceptance_scope": "LIVE_PROVIDER_REVIEW_ONLY",
        }
    if settings.market_provider == "fixture" and provider_state == "fixture":
        return {
            "market_provider": "fixture",
            "provider_state": "fixture",
            "input_provenance": "FIXTURE_DATA",
            "acceptance_scope": "STRUCTURAL_FIXTURE_ONLY",
        }
    return {
        "market_provider": settings.market_provider,
        "provider_state": provider_state,
        "input_provenance": "UNVERIFIED_OR_DEGRADED",
        "acceptance_scope": "NOT_ACCEPTABLE",
    }


def handler(settings: Settings, storage: RuntimeStorage):
    whitebox = WhiteboxLedger(storage.whitebox_db_file)

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

        def _heartbeat(self) -> dict:
            envelope = self._latest()
            age = _age_seconds(envelope)
            provenance = _input_provenance(settings, envelope)
            report = envelope.get("report", {}) if envelope else {}
            first = report.get("第一板块", {}) if isinstance(report, dict) else {}
            summary = whitebox.summary()
            report_state = "通" if age is not None and age <= settings.report_stale_seconds else "不确定"
            return {
                "project_id": "signal-lattice",
                "application_version": APP_VERSION,
                "decision_contract_version": PROMPT_VERSION,
                "server_time_utc": datetime.now(timezone.utc).isoformat(),
                "api_state": "通",
                "report_state": report_state,
                "report_age_seconds": round(age, 2) if age is not None else None,
                "ui_heartbeat_seconds": 1,
                "quote_observation_seconds": settings.refresh_seconds,
                "formal_review_clock": "每小时Australia/Sydney",
                "last_observed_at": summary.get("latest_observed_at"),
                "quote_observed_at": summary.get("quote_observed_at"),
                "last_decision_id": summary.get("latest_decision_id"),
                "last_decision_opened_at": summary.get("latest_decision_opened_at"),
                "observation_count": summary.get("observation_count", 0),
                "decision_count": summary.get("decision_count", 0),
                "unchanged_observations": summary.get("unchanged_observations", 0),
                "current_action": first.get("唯一操作", "持有"),
                "current_symbol": first.get("代码", "SPY"),
                "next_formal_review": first.get("下一正式复核"),
                "data_cutoff": report.get("数据截止"),
                "shadow_weight_mode": "SHADOW_ONLY",
                "profitability_status": "NOT_ISSUED",
                "business_release_status": "NOT_ISSUED",
                "automatic_trading": False,
                "shadow_only": True,
                **provenance,
            }

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health/live":
                return self._send_json(200, {"status": "alive", "version": APP_VERSION})
            if path == "/health/ready":
                envelope = self._latest()
                age = _age_seconds(envelope)
                ready = age is not None and age <= settings.report_stale_seconds
                provenance = _input_provenance(settings, envelope)
                return self._send_json(200 if ready else 503, {
                    "status": "ready" if ready else "stale",
                    "version": APP_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "refresh_seconds": settings.refresh_seconds,
                    "ui_heartbeat_seconds": 1,
                    "age_seconds": round(age, 2) if age is not None else None,
                    **provenance,
                })
            if path == "/api/v1/heartbeat":
                return self._send_json(200, self._heartbeat())
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
                return self._send_json(200, {
                    "meaning": "material decision episodes only",
                    "items": [row.get("report") for row in rows if isinstance(row.get("report"), dict)],
                })
            if path == "/api/v1/whitebox/summary":
                return self._send_json(200, whitebox.summary())
            if path == "/api/v1/whitebox/skills":
                return self._send_json(200, {
                    "mode": "SHADOW_ONLY",
                    "items": whitebox.skills(),
                })
            if path == "/api/v1/whitebox/decisions":
                query = parse_qs(parsed.query)
                try:
                    limit = int((query.get("limit") or ["50"])[0])
                except ValueError:
                    limit = 50
                return self._send_json(200, {"items": whitebox.decisions(limit)})
            if path == "/api/v1/whitebox/outcomes":
                return self._send_json(200, {"items": whitebox.outcomes()})
            if path == "/api/v1/whitebox/backtest/latest":
                result = whitebox.latest_backtest()
                return self._send_json(200, result or {
                    "status": "NOT_RUN",
                    "gate_status": "NOT_RUN",
                    "profitability_claim": "NOT_ISSUED",
                })
            if path in {"/api/v1/metadata", "/api/v1/system/status"}:
                envelope = self._latest()
                age = _age_seconds(envelope)
                report = envelope.get("report", {}) if envelope else {}
                first = report.get("第一板块", {}) if isinstance(report, dict) else {}
                state = "READY" if age is not None and age <= settings.report_stale_seconds else "DEGRADED"
                summary = whitebox.summary()
                provenance = _input_provenance(settings, envelope)
                return self._send_json(200, {
                    "project_id": "signal-lattice",
                    "version": APP_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "refresh_seconds": settings.refresh_seconds,
                    "ui_heartbeat_seconds": 1,
                    "state": state,
                    "public_url": settings.public_url,
                    "status_url": settings.status_url,
                    "automatic_trading": False,
                    "shadow_only": True,
                    "current_action": first.get("唯一操作", "持有"),
                    "current_symbol": first.get("代码", "SPY"),
                    "report_age_seconds": round(age, 2) if age is not None else None,
                    "decision_id": summary.get("latest_decision_id"),
                    "observation_count": summary.get("observation_count", 0),
                    "decision_count": summary.get("decision_count", 0),
                    "profitability_status": "NOT_ISSUED",
                    "business_release_status": "NOT_ISSUED",
                    **provenance,
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
