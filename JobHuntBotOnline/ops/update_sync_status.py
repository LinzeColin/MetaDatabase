from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--channel", choices=("structured", "objects"), required=True)
    parser.add_argument("--state", choices=("synced", "failed", "not_configured", "pending_sync"), required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), dict) else {}
    channels[args.channel] = {
        "state": args.state,
        "message": args.message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    states = {item.get("state") for item in channels.values() if isinstance(item, dict)}
    if "failed" in states:
        aggregate = "failed"
    elif states and states <= {"synced"}:
        aggregate = "synced"
    elif "pending_sync" in states:
        aggregate = "pending_sync"
    else:
        aggregate = "not_configured"
    messages = [item.get("message", "") for item in channels.values() if isinstance(item, dict) and item.get("message")]
    result = {
        "state": aggregate,
        "message": "；".join(messages) or "长期同步尚未配置。",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "channels": channels,
    }
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.chmod(0o660)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    path.chmod(0o660)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
