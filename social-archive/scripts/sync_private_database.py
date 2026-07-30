from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.private_facts import (
    PRIVATE_DATABASE_EVENT,
    completed_content_facts,
    fact_bytes,
    fact_sha256,
)
from social_archive.utils import redact, utcnow


PRIVATE_DATABASE_AREA = "Private-MetaDatabase"
PRIVATE_DATABASE_DOMAIN = "SocialArchive"
_VERIFY_SUMMARY = re.compile(
    r"Private-MetaDatabase:\s*账本\s*(?P<total>\d+)\s*条，\s*对象在仓\s*(?P<present>\d+)\s*，\s*缺\s*(?P<missing>\d+)",
)


def _private_database_client() -> tuple[Path | None, str | None]:
    raw = os.getenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", "").strip()
    if not raw:
        return None, "缺少 SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT；禁止回退到本地 Private-Database 工作树"
    candidate = Path(raw).expanduser()
    try:
        client = candidate.resolve(strict=True)
    except OSError:
        return None, "配置的 Private-Database API client 不存在"
    if not client.is_file() or client.name != "private_db_client.py":
        return None, "Private-Database API client 必须是可读的 private_db_client.py"
    return client, None


def _run_client(client: Path, argv: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(client), *argv],
        cwd=client.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    detail = redact((result.stderr or result.stdout or "").strip()[-500:])
    return int(result.returncode), detail


def _verify_summary_is_complete(output: str) -> bool:
    """The official client currently prints missing-object counts but exits zero.

    Treat an unparseable summary, a nonzero missing count, or an inconsistent
    total as an unverified delivery rather than trusting its process status.
    """
    match = _VERIFY_SUMMARY.search(output)
    if not match:
        return False
    total = int(match.group("total"))
    present = int(match.group("present"))
    missing = int(match.group("missing"))
    return total > 0 and missing == 0 and total == present


def _blocked(message: str, *, error_code: str = "PRIVATE_DATABASE_CLIENT_UNAVAILABLE") -> int:
    print(json.dumps({
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": "BLOCKED_ENVIRONMENT",
        "error_code": error_code,
        "message": message,
    }, ensure_ascii=False))
    return 3


def _dry_run(store: RuntimeStore, *, limit: int) -> int:
    facts = completed_content_facts(store, limit=limit)
    delivered = 0
    for fact in facts:
        event = store.get_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT,
            aggregate_id=str(fact["content"]["id"]),
            payload_sha256=fact_sha256(fact),
        )
        delivered += int(bool(event and event.get("status") == "delivered"))
    print(json.dumps({
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": "READY",
        "dry_run": True,
        "candidate_fact_count": len(facts),
        "already_delivered_count": delivered,
        "pending_count": len(facts) - delivered,
        "transport": "Private-Database API client",
        "local_checkout": False,
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize completed Social Archive facts through the official clone-free Private-Database API client."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true", help="run one bounded, idempotent pass")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    settings = Settings.from_env()
    client, client_error = _private_database_client()
    if client_error or client is None:
        return _blocked(client_error or "Private-Database API client 不可用")

    limit = min(max(args.limit, 1), 1000)
    if args.dry_run:
        if not settings.runtime_db.is_file():
            print(json.dumps({
                "schema_version": "1.0",
                "generated_at": utcnow(),
                "status": "NO_CHANGE",
                "dry_run": True,
                "candidate_fact_count": 0,
                "message": "Runtime Journal 尚未初始化；dry-run 不创建本地状态",
                "transport": "Private-Database API client",
                "local_checkout": False,
            }, ensure_ascii=False))
            return 0
        try:
            return _dry_run(RuntimeStore(settings.runtime_db), limit=limit)
        except Exception as exc:  # noqa: BLE001 - malformed runtime is an environment boundary
            return _blocked(redact(f"Runtime Journal 不可读：{exc}"), error_code="RUNTIME_JOURNAL_UNREADABLE")

    settings.ensure_directories()
    store = RuntimeStore(settings.runtime_db)
    store.initialize()
    facts = completed_content_facts(store, limit=limit)
    if not facts:
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "NO_CHANGE",
            "candidate_fact_count": 0,
            "transport": "Private-Database API client",
            "local_checkout": False,
        }, ensure_ascii=False))
        return 0

    pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
    delivered = 0
    for fact in facts:
        event = store.ensure_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT,
            aggregate_id=str(fact["content"]["id"]),
            payload=fact,
        )
        if event.get("status") == "delivered":
            delivered += 1
        else:
            pending.append((fact, event))
    if not pending:
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "NO_CHANGE",
            "candidate_fact_count": len(facts),
            "already_delivered_count": delivered,
            "transport": "Private-Database API client",
            "local_checkout": False,
        }, ensure_ascii=False))
        return 0

    failures: list[dict[str, str]] = []
    attempted_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="social-archive-facts-") as temp_dir:
        temporary_root = Path(temp_dir)
        for fact, event in pending:
            content_id = str(fact["content"]["id"])
            digest = fact_sha256(fact)
            source = temporary_root / f"social-archive-fact-{content_id}-{digest[:12]}.json"
            source.write_bytes(fact_bytes(fact))
            code, detail = _run_client(
                client,
                ["ingest", PRIVATE_DATABASE_AREA, str(source), "--domain", PRIVATE_DATABASE_DOMAIN, "--batch", digest],
            )
            attempted_events.append(event)
            if code:
                store.mark_outbox_failed(str(event["id"]), "PRIVATE_DATABASE_INGEST_FAILED")
                failures.append({"content_id": content_id, "error_code": "PRIVATE_DATABASE_INGEST_FAILED", "detail": detail})

        if not failures:
            code, detail = _run_client(client, ["verify", PRIVATE_DATABASE_AREA])
            if code == 0 and not _verify_summary_is_complete(detail):
                code = 1
                detail = "Private-Database verify 未证明账本对象完整"
            if code:
                for event in attempted_events:
                    store.mark_outbox_failed(str(event["id"]), "PRIVATE_DATABASE_VERIFY_FAILED")
                failures.append({"content_id": "*", "error_code": "PRIVATE_DATABASE_VERIFY_FAILED", "detail": detail})
            else:
                for event in attempted_events:
                    store.mark_outbox_delivered(str(event["id"]))
        else:
            for event in attempted_events:
                current = store.get_outbox_event(
                    event_type=PRIVATE_DATABASE_EVENT,
                    aggregate_id=str(event["aggregate_id"]),
                    payload_sha256=str(event["payload_sha256"]),
                )
                if current and current.get("status") != "pending":
                    store.mark_outbox_failed(str(event["id"]), "PRIVATE_DATABASE_BATCH_INCOMPLETE")

    status = "PASS" if not failures else "DEGRADED"
    report = {
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": status,
        "candidate_fact_count": len(facts),
        "attempted_fact_count": len(pending),
        "already_delivered_count": delivered,
        "delivered_this_run": len(pending) if status == "PASS" else 0,
        "failures": failures,
        "transport": "Private-Database API client",
        "local_checkout": False,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if status == "PASS" else 4


if __name__ == "__main__":
    raise SystemExit(main())
