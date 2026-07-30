from __future__ import annotations

import json
import os
import urllib.request

from social_archive.config import Settings
from social_archive.status_projection import sanitize_status_document
from social_archive.utils import atomic_write, read_secret, utcnow


def _down_document(exc: Exception) -> dict[str, object]:
    return {
        "project": "Social Archive",
        "version": "0.0.0.4",
        "generated_at": utcnow(),
        "overall": "down",
        "connectors": [],
        "destinations": [],
        "storage": [],
        "replicas": [],
        "recovery": {"last_backup": "unknown", "last_restore_drill": "unknown"},
        "error_type": exc.__class__.__name__,
    }


def _core_projection_url() -> str:
    raw_port = os.getenv("SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT", "18765").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT 必须是端口号") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT 必须介于 1 和 65535")
    return f"http://127.0.0.1:{port}/v1/status-projection"


def main() -> int:
    settings = Settings.from_env()
    try:
        headers: dict[str, str] = {}
        token = read_secret(settings.api_token_file)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(_core_projection_url(), headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            document = json.load(response)
        safe_document = sanitize_status_document(document)
    except Exception as exc:  # The projection must still state that Core is down.
        safe_document = _down_document(exc)
    output = settings.data_root / "status" / "social-archive.json"
    atomic_write(output, (json.dumps(safe_document, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), mode=0o640)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
