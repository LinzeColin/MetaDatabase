#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from signal_lattice.constants import VERSION
from signal_lattice.state_machine import load_state, validate_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("CANONICAL_STATE.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_state(load_state(args.state), VERSION)
    payload = {"state": result.state, "current_phase": result.current_phase, "findings": list(result.findings)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if result.state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
