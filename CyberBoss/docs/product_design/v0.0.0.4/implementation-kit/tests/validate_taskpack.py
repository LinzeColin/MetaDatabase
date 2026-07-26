#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = [
    "00_README_FIRST.md",
    "01_PRFAQ_STRATEGY_OKR.md",
    "02_PRD_ACCEPTANCE_CONTRACT.md",
    "03_ARCHITECTURE_DATA_SECURITY.md",
    "04_TASK_DAG_EXECUTION_PACK.yaml",
    "05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md",
    "06_OPERATIONS_STATUS_HANDOVER.md",
    "07_RESEARCH_COMPETITOR_UPSTREAM_FINDINGS.md",
    "08_UPSTREAM_CODE_CHANGE_MAP.md",
    "09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "10_TRACEABILITY_RELEASE_CHECKLIST.md",
    "11_AGENT_EXECUTION_PROMPTS.md",
    "12_CURRENT_ROADMAP.md",
    "13_STAGE2B_STAGE3_UPGRADES.md",
    "14_PURSUING_GOAL.txt",
    "implementation-kit",
]
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{30,}"),
]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    for item in REQUIRED:
        if not (root / item).exists():
            errors.append(f"required_missing:{item}")

    files = [p for p in root.rglob("*") if p.is_file()]
    if len(files) <= 7:
        errors.append(f"file_count_wrongly_limited:{len(files)}")

    for path in files:
        rel = path.relative_to(root).as_posix()
        if rel.endswith("MANIFEST.sha256") or rel == "implementation-kit/tests/validate_taskpack.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "starter-kit/" in text or "05_TEST_MODEL_SECURITY_RELEASE.md" in text:
            errors.append(f"stale_filename_reference:{rel}")
        if re.search(r"Root authority files:\s*exactly\s*7|根目录(?:严格)?(?:只|仅).*7", text, re.I):
            errors.append(f"hard_seven_file_limit:{rel}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"secret_pattern:{rel}:{pattern.pattern}")

    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("TASKPACK_VALIDATION=FAIL")
        return 1
    print(f"TASKPACK_VALIDATION=PASS files={len(files)} required_items={len(REQUIRED)} seven_is_minimum_not_limit=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
