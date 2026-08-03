#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import os
import json
import secrets
import time
from pathlib import Path

PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def human_pairing_code() -> str:
    compact = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(12))
    return "-".join(compact[index:index + 4] for index in range(0, 12, 4))


def atomic_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (value + "\n").encode("utf-8")
    if path.exists():
        # Compose bind-mounts every secret as an individual file, so a running
        # container follows the *inode* rather than the path.  Rotating by
        # rename therefore published a new host file that Core could never see:
        # it kept serving the pre-rotation record until the container was
        # recreated, which is why a refreshed pairing code stayed unavailable.
        # Rewrite in place under an exclusive lock instead; this also preserves
        # the mode and the 10001:10001 shared-Secret ownership that production
        # host preparation assigns.
        descriptor = os.open(path, os.O_WRONLY)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            except OSError:
                pass
            os.lseek(descriptor, 0, os.SEEK_SET)
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
            os.ftruncate(descriptor, len(payload))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_bytes(payload)
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Social Archive 一次性配对码和长期设备令牌")
    parser.add_argument("--code-file", type=Path, default=Path("/run/secrets/social_archive_pairing_code"))
    parser.add_argument("--token-file", type=Path, default=Path("/run/secrets/social_archive_api_token"))
    parser.add_argument("--ttl-seconds", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=5)
    args = parser.parse_args()
    if args.ttl_seconds < 60 or args.ttl_seconds > 600:
        raise SystemExit("ttl-seconds 必须在 60–600 之间")
    if args.max_attempts < 1 or args.max_attempts > 20:
        raise SystemExit("max-attempts 必须在 1–20 之间")
    code = human_pairing_code()
    record = {
        "code": code,
        "created_at_epoch": int(time.time()),
        "expires_at_epoch": int(time.time()) + args.ttl_seconds,
        "attempts_remaining": args.max_attempts,
    }
    atomic_secret(args.code_file, json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    if not args.token_file.exists() or not args.token_file.read_text(encoding="utf-8").strip():
        atomic_secret(args.token_file, secrets.token_urlsafe(48))
    print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
