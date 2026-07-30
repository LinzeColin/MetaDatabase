#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--subject-sha256", required=True)
    parser.add_argument("--new-mechanisms", type=int, required=True)
    parser.add_argument("--new-p0", type=int, required=True)
    parser.add_argument("--new-p1", type=int, required=True)
    parser.add_argument("--developer-burden-deltas", type=int, required=True)
    parser.add_argument("--previous-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = (args.new_mechanisms, args.new_p0, args.new_p1, args.developer_burden_deltas)
    if any(value < 0 for value in values) or args.sequence < 1:
        raise SystemExit("COUNTS_AND_SEQUENCE_MUST_BE_NONNEGATIVE")
    previous_sha = None
    if args.sequence == 1:
        if args.previous_receipt is not None:
            raise SystemExit("FIRST_SEQUENCE_MUST_NOT_HAVE_PREVIOUS_RECEIPT")
    else:
        if args.previous_receipt is None:
            raise SystemExit("PREVIOUS_RECEIPT_REQUIRED")
        previous = load_self_hashed(args.previous_receipt)
        if previous.get("subject_sha256") != args.subject_sha256:
            raise SystemExit("PREVIOUS_RECEIPT_SUBJECT_MISMATCH")
        if previous.get("sequence") != args.sequence - 1:
            raise SystemExit("PREVIOUS_RECEIPT_SEQUENCE_MISMATCH")
        previous_sha = sha256_file(args.previous_receipt)
    qualifies = values == (0, 0, 0, 0)
    payload = {
        "schema_version": "1.1.0",
        "round_id": args.round_id,
        "sequence": args.sequence,
        "subject_sha256": args.subject_sha256,
        "previous_receipt_sha256": previous_sha,
        "new_mechanism_count": args.new_mechanisms,
        "new_p0_count": args.new_p0,
        "new_p1_count": args.new_p1,
        "developer_burden_delta_count": args.developer_burden_deltas,
        "qualifying_no_change_round": qualifies,
    }
    atomic_json(args.output, payload)
    print(json.dumps({"state": "PASS", "sequence": args.sequence, "qualifying_no_change_round": qualifies, "output": args.output.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
