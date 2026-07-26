#!/usr/bin/env python3
"""CB-230 entrypoint for the shared exact-commit cloud artifact builder."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    script = Path(__file__).resolve().with_name(
        "build-cloud-process-artifacts.py",
    )
    return subprocess.call(
        [
            sys.executable,
            str(script),
            "--task-id",
            "CB-230",
            *sys.argv[1:],
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
