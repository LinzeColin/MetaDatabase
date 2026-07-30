from __future__ import annotations

from .action import decide
from .db import RuntimeDB


def run_once(db: RuntimeDB, worker_id: str = "worker-1", lease_seconds: int = 120) -> bool:
    item = db.claim(worker_id, lease_seconds=lease_seconds)
    if not item:
        return False
    # Trusted gates are derived only from server-side sealed evidence. The prebuild worker
    # intentionally supplies no trusted live-market gates, therefore the safe result is NO_ACTION.
    packet = decide(item["request"], {}, db.clock.now())
    db.complete(item["job_id"], worker_id, item["fencing_token"], packet)
    return True
