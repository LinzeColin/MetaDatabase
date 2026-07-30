#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.receipts import load_self_hashed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[str] = []
    try:
        subject = json.loads((root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
        receipt = load_self_hashed(root / "evidence/skill_router/pass_c.json")
    except Exception as exc:
        subject, receipt = {}, {}
        findings.append("SKILL_PASS_C_INPUT_INVALID:" + type(exc).__name__)
    if receipt.get("state") != "PASS" or receipt.get("formal_pass_claimed") is not True:
        findings.append("SKILL_PASS_C_NOT_PASS")
    if receipt.get("subject_sha256") != subject.get("subject_sha256"):
        findings.append("SKILL_PASS_C_SUBJECT_MISMATCH")
    if receipt.get("runtime_agent_dependency") != 0 or receipt.get("runtime_llm_tokens") != 0:
        findings.append("SKILL_PASS_C_RUNTIME_CONTRACT_DRIFT")
    result = {"state": "PASS" if not findings else "BLOCKED", "findings": findings, "subject_sha256": subject.get("subject_sha256")}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
