from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_TESTS = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, ACCEPTANCE_TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
