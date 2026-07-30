#!/usr/bin/env python3
"""Render the non-secret remote configuration for the dedicated Tunnel."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_HOST = "social-archive.linzezhang.com"
API_HOST = "social-archive-api.linzezhang.com"
STATUS_HOST = "status.linzezhang.com"
STATUS_PROJECTION_PATH = "/social-archive.json"
STATUS_HEALTH_PATH = "/social-archive-health"
STATUS_ROUTE_PATTERN = r"^/social-archive(\.json|-health)$"
DEFAULT_CORE_LOOPBACK_PORT = 18765
DEFAULT_STATUS_LOOPBACK_PORT = 18780


def _env_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    prefix = f"{key}="
    values = [line[len(prefix):].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(prefix)]
    return values[-1] if values else None


def _port(raw: str | None, *, key: str, default: int) -> int:
    try:
        value = int(raw or default)
    except ValueError as exc:
        raise ValueError(f"{key} 必须是端口号") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{key} 必须介于 1 和 65535")
    return value


def render_remote_configuration(*, env_file: Path) -> dict[str, object]:
    core_port = _port(
        _env_value(env_file, "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT"),
        key="SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT",
        default=DEFAULT_CORE_LOOPBACK_PORT,
    )
    status_port = _port(
        _env_value(env_file, "SOCIAL_ARCHIVE_STATUS_PORT"),
        key="SOCIAL_ARCHIVE_STATUS_PORT",
        default=DEFAULT_STATUS_LOOPBACK_PORT,
    )
    return {
        "config": {
            "ingress": [
                {"hostname": LIBRARY_HOST, "service": f"http://127.0.0.1:{core_port}"},
                {"hostname": API_HOST, "service": f"http://127.0.0.1:{core_port}"},
                {
                    "hostname": STATUS_HOST,
                    "path": STATUS_ROUTE_PATTERN,
                    "service": f"http://127.0.0.1:{status_port}",
                },
                {"hostname": STATUS_HOST, "service": "http://127.0.0.1:80"},
                {"service": "http_status:404"},
            ]
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 Social Archive 专用 Cloudflare Tunnel 远端配置")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    try:
        document = render_remote_configuration(env_file=args.env_file)
    except (OSError, ValueError) as exc:
        print(f"Tunnel 配置渲染停止：{exc}")
        return 2
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
