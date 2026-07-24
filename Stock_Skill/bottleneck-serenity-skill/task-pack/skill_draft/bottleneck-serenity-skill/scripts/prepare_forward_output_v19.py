#!/usr/bin/env python3
"""Prepare a v19 forward result using the frozen exact-byte replay harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_forward_output_v18 import prepare


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--preexecution-seal-sha", required=True)
    args = parser.parse_args()
    try:
        output = prepare(
            args.draft.resolve(),
            args.output.resolve(),
            args.preexecution_seal_sha,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(
        "PASS: prepared v19 output; "
        f"decision={output['decision_label']}; "
        "replay=evidence/opportunity/portfolio"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
