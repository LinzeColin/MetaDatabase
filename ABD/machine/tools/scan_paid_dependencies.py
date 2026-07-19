#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abd_acceptance.budget import SCAN_REPORT_PATH, write_scan_report


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD deterministic paid and unknown dependency scanner")
    parser.add_argument("--root", default=str(ROOT), help="ABD project root")
    parser.add_argument(
        "--output",
        default=SCAN_REPORT_PATH.as_posix(),
        help="report path, relative to --root unless absolute",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    result = write_scan_report(root, output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
