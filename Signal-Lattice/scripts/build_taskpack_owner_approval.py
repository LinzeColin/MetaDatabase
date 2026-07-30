#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.receipts import atomic_json, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source-attachment", type=Path, required=True)
    parser.add_argument("--source-message", required=True)
    parser.add_argument("--approved-at", default="2026-07-28T00:00:00Z")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    subject = json.loads((root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
    if subject.get("state") != "PREPARED" or subject.get("version") != VERSION:
        raise SystemExit("PREPARED_SUBJECT_REQUIRED")
    scope = root / "machine/facts/final_scope_summary.json"
    if not scope.is_file():
        raise SystemExit("FINAL_SCOPE_SUMMARY_REQUIRED")
    source = args.source_attachment.resolve()
    if not source.is_file():
        raise SystemExit("APPROVAL_SOURCE_ATTACHMENT_REQUIRED")
    # Validate date-time shape without introducing a runtime dependency.
    datetime.fromisoformat(args.approved_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    payload = {
        "schema_version": "1.0.0",
        "approval_kind": "OWNER_AUTHORIZED_FINAL_TASKPACK_DELIVERY",
        "approved": True,
        "version": VERSION,
        "prepared_subject_sha256": subject["subject_sha256"],
        "scope_summary_sha256": sha256_file(scope),
        "residual_environment_tasks_accepted": True,
        "formal_release_pass_claimed": False,
        "live_action_enabled": False,
        "source_message": args.source_message,
        "source_attachment_sha256": sha256_file(source),
        "approved_at": args.approved_at,
        "owner_override_scope": "TASKPACK_SEAL_ONLY_NOT_RELEASE_PASS",
    }
    output = args.output if args.output.is_absolute() else root / args.output
    atomic_json(output, payload)
    print(json.dumps({"state": "PASS", "output": output.as_posix(), "prepared_subject_sha256": subject["subject_sha256"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
