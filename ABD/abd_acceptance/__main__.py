from __future__ import annotations

import argparse
import json
from pathlib import Path

from .canonical_facts import write_phase_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD fail-closed acceptance oracle")
    parser.add_argument("--contract", required=True, help="acceptance contract id")
    parser.add_argument(
        "--evidence",
        default="machine/evidence",
        help="evidence directory, relative to --root unless absolute",
    )
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()

    if args.contract != "AC-S00-P01":
        parser.error("only AC-S00-P01 is implemented in this run")

    root = Path(args.root).resolve()
    evidence_dir = Path(args.evidence)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir

    result = write_phase_evidence(root, evidence_dir)
    print(
        json.dumps(
            {
                "contract_id": result["contract_id"],
                "status": result["status"],
                "evidence": result["evidence_path"],
                "evidence_sha256": result["evidence_sha256"],
                "next": result["next"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
