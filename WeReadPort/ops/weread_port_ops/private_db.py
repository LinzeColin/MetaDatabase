from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .db import RuntimeDB
from .sanitize import assert_public_safe, sanitize_public

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_fact_batch(db: RuntimeDB) -> dict[str, Any]:
    """Build a retry-stable, privacy-safe batch from the exact pending outbox rows.

    The batch intentionally excludes volatile runtime counters and the current wall clock.
    A retry of the same pending facts therefore produces the same bytes and content digest.
    """
    pending = db.pending(5000)
    events: list[dict[str, Any]] = []
    for row in pending:
        events.append(
            {
                "outboxId": str(row["outbox_id"]),
                "topic": str(row["topic"]),
                "createdAt": str(row["created_at"]),
                "payload": json.loads(row["payload_json"]),
            }
        )
    events.sort(key=lambda item: (item["createdAt"], item["outboxId"]))
    if not events:
        return {
            "schemaVersion": 2,
            "service": "weread-port",
            "batchId": None,
            "date": None,
            "events": [],
            "privacy": {
                "sensitiveDataRetention": "none",
                "userContentRetention": "none",
                "archiveRetention": "none",
            },
        }
    event_digest = hashlib.sha256(_canonical_json(events).encode("utf-8")).hexdigest()
    batch = {
        "schemaVersion": 2,
        "service": "weread-port",
        "batchId": event_digest,
        "date": events[-1]["createdAt"][:10],
        "events": events,
        "privacy": {
            "sensitiveDataRetention": "none",
            "userContentRetention": "none",
            "archiveRetention": "none",
        },
    }
    clean = sanitize_public(batch)
    assert_public_safe(clean)
    return clean


def _probe_client(client: Path, runner: Runner) -> set[str]:
    result = runner(
        ["python3", str(client), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return set()
    text = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    return {name for name in ("ingest", "put", "get", "list", "verify") if name in text}


def sync_pending(
    settings: Settings,
    db: RuntimeDB,
    *,
    at: datetime | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Synchronize pending privacy-safe facts using the existing no-clone client.

    `ingest` is preferred because it is the public repository contract and provides
    content addressing plus manifest verification. `put` is a bounded compatibility
    fallback for an older client that exposes the command but not `ingest`.
    """
    moment = at or datetime.now(timezone.utc)
    client = settings.private_db_client
    if client is None or not client.is_file():
        return {"status": "unconfigured", "reason": "PRIVATE_DB_CLIENT_NOT_FOUND", "delivered": 0}
    pending = db.pending(5000)
    if not pending:
        return {"status": "idle", "reason": "NO_PENDING_FACTS", "delivered": 0}

    commands = _probe_client(client, runner)
    if not ({"ingest", "put"} & commands):
        db.mark_failed([str(row["outbox_id"]) for row in pending], "PRIVATE_DB_CLIENT_UNSUPPORTED")
        return {
            "status": "failed",
            "reason": "PRIVATE_DB_CLIENT_UNSUPPORTED",
            "delivered": 0,
            "requiredCommands": ["ingest"],
        }

    payload = build_fact_batch(db)
    digest = str(payload["batchId"])
    date = str(payload["date"] or moment.date().isoformat())
    with tempfile.TemporaryDirectory(prefix="weread-port-private-db-") as folder:
        payload_path = Path(folder) / f"weread-port-operations-{digest}.json"
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if "ingest" in commands:
            command = [
                "python3",
                str(client),
                "ingest",
                settings.private_db_area,
                str(payload_path),
                "--domain",
                "weread-port-operations",
                "--batch",
                date,
            ]
            mode = "ingest"
            destination = f"objects/<sha256>/{payload_path.name}"
        else:
            relpath = f"{settings.private_db_relroot}/facts/{date}/{digest}.json"
            command = ["python3", str(client), "put", settings.private_db_area, relpath, str(payload_path)]
            mode = "put-compatibility"
            destination = relpath
        result = runner(command, capture_output=True, text=True, timeout=120)

    identifiers = [str(row["outbox_id"]) for row in pending]
    if result.returncode == 0:
        db.mark_delivered(identifiers, delivered_at=moment)
        return {
            "status": "delivered",
            "mode": mode,
            "batchId": digest,
            "destination": destination,
            "delivered": len(identifiers),
        }
    db.mark_failed(identifiers, f"PRIVATE_DB_EXIT_{result.returncode}")
    return {
        "status": "failed",
        "reason": f"PRIVATE_DB_EXIT_{result.returncode}",
        "mode": mode,
        "batchId": digest,
        "delivered": 0,
        "stderrTail": sanitize_public((result.stderr or "")[-1000:]),
    }


def sync_daily(
    settings: Settings,
    db: RuntimeDB,
    *,
    at: datetime | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Compatibility entry point used by the CLI and older tests."""
    return sync_pending(settings, db, at=at, runner=runner)
