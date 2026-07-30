#!/usr/bin/env python3
from __future__ import annotations

import os
import time
from pathlib import Path

from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.worker import run_once


def main() -> None:
    settings = Settings.from_env()
    runtime = RuntimeDB(settings.state_dir / "runtime.db", Path(__file__).resolve().parents[1] / "db/schema.sql")
    worker = os.environ.get("SIGNAL_LATTICE_WORKER_ID", "worker-1")
    while True:
        did = run_once(runtime, worker, settings.worker_lease_seconds, settings)
        time.sleep(0.2 if did else 2.0)


if __name__ == "__main__":
    main()
