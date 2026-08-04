from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from social_archive.config import Settings
from social_archive.status_projection import sanitize_status_document


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
STATUS_PATH = "/social-archive.json"
STATUS_HEALTH_PATH = "/social-archive-health"
MAX_STATUS_BYTES = 256 * 1024


def server_config_from_env() -> tuple[str, int, Path]:
    host = os.getenv("SOCIAL_ARCHIVE_STATUS_BIND_HOST", "127.0.0.1").strip()
    if host not in LOOPBACK_HOSTS:
        raise ValueError("状态投影服务只能绑定 loopback 地址")
    try:
        port = int(os.getenv("SOCIAL_ARCHIVE_STATUS_PORT", "18780"))
    except ValueError as exc:
        raise ValueError("SOCIAL_ARCHIVE_STATUS_PORT 必须是端口号") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SOCIAL_ARCHIVE_STATUS_PORT 必须介于 1 和 65535")
    return host, port, Settings.from_env().data_root / "status" / "social-archive.json"


def public_status_bytes(path: Path) -> bytes | None:
    """Return a second allowlisted serialization, or no document when unavailable."""
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_STATUS_BYTES:
            return None
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    safe_document = sanitize_status_document(document)
    return (json.dumps(safe_document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _project_version() -> str:
    """版本只有一个真源：仓根的 VERSION 文件。读不到就说不知道，不猜。"""
    try:
        return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def make_server(host: str, port: int, status_file: Path) -> ThreadingHTTPServer:
    class StatusProjectionHandler(BaseHTTPRequestHandler):
        # 版本读仓根 VERSION。写死会让状态站在升级后一直自报旧版本。
        server_version = f"SocialArchiveStatus/{_project_version()}"
        sys_version = ""

        def log_message(self, _format: str, *_args: object) -> None:
            # Request paths can contain user-supplied query strings. This public
            # service intentionally emits no request log with those values.
            return

        def _send_json(self, code: HTTPStatus, document: dict[str, object], *, include_body: bool) -> None:
            body = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'")
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def _serve(self, *, include_body: bool) -> None:
            path = urlsplit(self.path).path
            if path in {"/health", STATUS_HEALTH_PATH}:
                self._send_json(HTTPStatus.OK, {"status": "ok"}, include_body=include_body)
                return
            if path in {"/", STATUS_PATH}:
                body = public_status_bytes(status_file)
                if body is None:
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unavailable"}, include_body=include_body)
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                if include_body:
                    self.wfile.write(body)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "not_found"}, include_body=include_body)

        def _method_not_allowed(self) -> None:
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"status": "method_not_allowed"}, include_body=True)

        def do_GET(self) -> None:
            self._serve(include_body=True)

        def do_HEAD(self) -> None:
            self._serve(include_body=False)

        def do_POST(self) -> None:
            self._method_not_allowed()

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

    return ThreadingHTTPServer((host, port), StatusProjectionHandler)


def main() -> int:
    try:
        host, port, status_file = server_config_from_env()
    except ValueError as exc:
        print(f"状态投影服务未启动：{exc}")
        return 2
    server = make_server(host, port, status_file)
    print(f"状态投影只读服务：http://{host}:{port}{STATUS_PATH}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
