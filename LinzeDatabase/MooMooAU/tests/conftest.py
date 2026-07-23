from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "machine/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
