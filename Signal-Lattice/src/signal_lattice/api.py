from __future__ import annotations

import hmac
import json
import mimetypes
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .constants import PROJECT_ID, VERSION
from .db import RuntimeDB
from .recommendation import validate_market_snapshot, validate_skill_signal
from .status import default_matrix

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cache-Control": "no-store",
}


def _limit(value: str | None, default: int = 50) -> int:
    try:
        return min(max(int(value or default), 1), 200)
    except (TypeError, ValueError):
        return default


def _runtime_status(settings: Settings, db: RuntimeDB) -> dict[str, object]:
    latest = db.latest_action()
    action = latest.get("action") if latest else "NO_ACTION"
    mode = "HUMAN_DECISION_SUPPORT" if settings.recommendation_enabled else "RESEARCH_AND_NO_ACTION"
    return {
        "schema_version": "1.0.0",
        "project_id": PROJECT_ID,
        "state": "PASS" if settings.runtime_environment == "production" else "DEGRADED",
        "version": VERSION,
        "mode": mode,
        "current_action": action,
        "recommendation_enabled": settings.recommendation_enabled,
        "automatic_trading": False,
        "human_execution_only": True,
        "agent_dependency": 0,
        "runtime_agent_dependency": 0,
        "llm_tokens": 0,
        "runtime_llm_tokens": 0,
        "model_mode": "DISABLED",
        "public_url": settings.public_url,
        "status_url": settings.status_url,
        "counts": db.runtime_counts(),
    }


def handler(settings: Settings, db: RuntimeDB):
    class H(BaseHTTPRequestHandler):
        server_version = f"SignalLattice/{VERSION}"
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(settings.request_timeout_seconds)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

        def _send(self, status: int, payload: object, ctype: str = "application/json; charset=utf-8") -> None:
            body = (
                json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                if not isinstance(payload, (bytes, bytearray))
                else bytes(payload)
            )
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _json(self) -> object | None:
            if self.headers.get_content_type() != "application/json":
                return None
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if size <= 0 or size > settings.max_request_bytes:
                return None
            try:
                return json.loads(self.rfile.read(size))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlparse(self.path).query, keep_blank_values=False)

        def _ingest_authorized(self) -> bool:
            token_file = settings.ingest_token_file
            try:
                if not token_file.is_file() or token_file.is_symlink() or token_file.stat().st_size > 4096:
                    return False
                expected = token_file.read_text(encoding="utf-8").strip()
            except OSError:
                return False
            if len(expected) < 32:
                return False
            header = self.headers.get("Authorization", "")
            prefix = "Bearer "
            if not header.startswith(prefix):
                return False
            provided = header[len(prefix):].strip()
            return hmac.compare_digest(provided, expected)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/health/live":
                return self._send(200, {"status": "alive", "version": VERSION})
            if path == "/health/ready":
                status = _runtime_status(settings, db)
                return self._send(200, {"status": "ready", **status})
            if path in {"/api/v1/status", "/api/v1/system/status"}:
                return self._send(200, _runtime_status(settings, db))
            if path == "/api/v1/business-lines":
                return self._send(200, default_matrix())
            if path in {"/api/v1/actions", "/api/v1/recommendations"}:
                limit = _limit((query.get("limit") or [None])[0])
                return self._send(200, {"items": db.actions(limit), "mode": _runtime_status(settings, db)["mode"]})
            if path == "/api/v1/opportunities":
                signals = db.skill_signals(limit=_limit((query.get("limit") or [None])[0], 100))
                ranked = sorted(
                    signals,
                    key=lambda item: (float(item.get("expected_return_pct", 0.0)), float(item.get("confidence", 0.0))),
                    reverse=True,
                )
                return self._send(200, {"items": ranked[:50]})
            if path == "/api/v1/consensus":
                symbol = (query.get("symbol") or [None])[0]
                market = (query.get("market") or [None])[0]
                signals = db.skill_signals(symbol=symbol, market=market)
                positive = sum(1 for item in signals if item.get("direction") == 1)
                neutral = sum(1 for item in signals if item.get("direction") == 0)
                negative = sum(1 for item in signals if item.get("direction") == -1)
                roots = sorted({root for item in signals for root in item.get("evidence_roots", [])})
                return self._send(200, {"signal_count": len(signals), "positive": positive, "neutral": neutral, "negative": negative, "independent_evidence_roots": roots})
            if path == "/api/v1/quant":
                latest = db.latest_action()
                return self._send(200, {"latest": latest or {"action": "NO_ACTION", "reasons": ["NO_COMPLETED_DECISION"]}})
            if path == "/api/v1/skills":
                return self._send(200, {"items": db.skill_overview()})
            if path == "/api/v1/evolution":
                return self._send(200, {"items": db.evolution_overview()})
            if path == "/api/v1/decision-snapshots":
                return self._send(200, {"items": db.decision_snapshots(_limit((query.get("limit") or [None])[0]))})
            match = re.fullmatch(r"/api/v1/jobs/([A-Za-z0-9-]+)", path)
            if match:
                item = db.get_job(match.group(1))
                return self._send(200, item) if item else self._send(404, {"error": "NOT_FOUND"})
            file_name = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (settings.web_dir / file_name).resolve()
            web_root = settings.web_dir.resolve()
            if web_root not in target.parents and target != web_root:
                return self._send(403, {"error": "FORBIDDEN"})
            if target.is_file():
                return self._send(
                    200,
                    target.read_bytes(),
                    mimetypes.guess_type(target.name)[0] or "application/octet-stream",
                )
            return self._send(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            data = self._json()
            if not isinstance(data, dict):
                return self._send(400, {"error": "INVALID_JSON_OR_SIZE"})
            if len(data) > 64:
                return self._send(400, {"error": "TOO_MANY_FIELDS"})
            try:
                if path == "/api/v1/research":
                    key = self.headers.get("Idempotency-Key") or str(uuid.uuid4())
                    job_id, created = db.enqueue(data, key)
                    return self._send(202 if created else 200, {"job_id": job_id, "created": created, "state": "QUEUED" if created else "EXISTING"})
                if path == "/api/v1/inputs/skill-signal":
                    if not self._ingest_authorized():
                        return self._send(401, {"error": "INGEST_AUTH_REQUIRED"})
                    signal = validate_skill_signal(data)
                    db.upsert_skill_signal(signal)
                    return self._send(201, {"state": "PASS", "skill_id": signal["skill_id"], "symbol": signal["symbol"], "market": signal["market"]})
                if path == "/api/v1/inputs/market-snapshot":
                    if not self._ingest_authorized():
                        return self._send(401, {"error": "INGEST_AUTH_REQUIRED"})
                    snapshot = validate_market_snapshot(data)
                    db.upsert_market_snapshot(snapshot)
                    return self._send(201, {"state": "PASS", "symbol": snapshot["symbol"], "market": snapshot["market"]})
            except (ValueError, KeyError) as exc:
                return self._send(422, {"error": str(exc)})
            return self._send(404, {"error": "NOT_FOUND"})

    return H


def serve(settings: Settings, db: RuntimeDB) -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), handler(settings, db))
    server.daemon_threads = True
    server.serve_forever()
