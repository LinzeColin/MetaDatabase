from __future__ import annotations

from .config import Settings
from .db import RuntimeDB
from .orchestrator import build_for_request


def run_once(
    db: RuntimeDB,
    worker_id: str = "worker-1",
    lease_seconds: int = 120,
    settings: Settings | None = None,
) -> bool:
    item = db.claim(worker_id, lease_seconds=lease_seconds)
    if not item:
        return False
    settings = settings or Settings.from_env()
    packet, _snapshot = build_for_request(db, settings, item["request"], now=db.clock.now())
    db.complete(item["job_id"], worker_id, item["fencing_token"], packet)
    return True
