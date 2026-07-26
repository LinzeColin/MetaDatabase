#!/usr/bin/env python3
"""CB-200 entrypoint for the shared exact-commit cloud artifact builder."""

from __future__ import annotations

import os
import sys
from pathlib import Path


BUILDER = Path(__file__).with_name("build-cloud-process-artifacts.py")


if __name__ == "__main__":
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(BUILDER),
            "--task-id",
            "CB-200",
            *sys.argv[1:],
        ],
    )
