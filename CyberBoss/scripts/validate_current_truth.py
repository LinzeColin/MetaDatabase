#!/usr/bin/env python3
"""Local guard for the Current Truth consensus (AC-001).

The frozen taskpack probe reads only the first 140 lines of HANDOFF.md and the
status section of README.md. A node that appends its narrative below that window
silently drops the file's accepted high watermark and puts the repository into
`split_brain` — which happened once during Stage 7 and is fixed by leading the
Current state section with the latest accepted node.

This script reproduces the probe's consensus rule against the three in-repo
sources so the condition is caught at node close instead of at the next probe.
Run it after updating task_state.json, README.md and HANDOFF.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT = Path(__file__).resolve().parents[1]
TASK_RE = re.compile(r"\bCB-(\d{3})\b")
PASS_WORD_RE = re.compile(r"(?:已通过|通过|passed|complete(?:d)?)", re.IGNORECASE)
NOT_STARTED_RE = re.compile(r"(?:未开始|not_started)", re.IGNORECASE)
# The canonical node numbers, matching the frozen probe's range expansion.
CANONICAL = [0, 10, 20, 30, 40, 100, 110, 120, 130, 140, 200, 210, 220, 230, 240,
             300, 310, 320, 330, 340, 400, 410, 420, 430, 440, 500, 510, 520,
             530, 540, 600, 610, 620, 630, 640, 700, 710, 720, 730, 740,
             800, 810, 820, 830, 840]
HANDOFF_WINDOW = 140
README_WINDOW = 140


def task_number(task_id: str) -> int:
    return int(TASK_RE.search(task_id).group(1))


def extract_status_section(text: str, limit: int) -> str:
    lines = text.splitlines()[:limit]
    for index, line in enumerate(lines):
        if index > 3 and re.search(
            r"^(?:#|##)\s*(?:唯一身份|Identity|Architecture|权威入口)", line, re.IGNORECASE
        ):
            return "\n".join(lines[:index])
    return "\n".join(lines)


def high_watermark(text: str, limit: int) -> str | None:
    section = extract_status_section(text, limit)
    lines = section.splitlines()
    passed: set[str] = set()
    for index, line in enumerate(lines):
        context = " ".join(lines[max(0, index - 1) : min(len(lines), index + 2)])
        ids = {f"CB-{number}" for number in TASK_RE.findall(line)}
        if NOT_STARTED_RE.search(context):
            continue
        if PASS_WORD_RE.search(context):
            passed.update(ids)
        range_match = re.search(
            r"CB-(\d{3})\s*(?:`?\s*)?(?:–|—|-|至|through)\s*`?CB-(\d{3})", line, re.IGNORECASE
        )
        if range_match and PASS_WORD_RE.search(context):
            start, end = int(range_match.group(1)), int(range_match.group(2))
            passed.update(f"CB-{value:03d}" for value in CANONICAL if start <= value <= end)
    if not passed:
        return None
    return max(passed, key=task_number)


def main() -> int:
    state = json.loads(
        (PROJECT / "machine/facts/task_state.json").read_text(encoding="utf-8")
    )
    state_passed = [
        row["id"] for row in state["tasks"] if row.get("status") == "passed"
    ]
    claims = {
        "machine_task_state": max(state_passed, key=task_number) if state_passed else None,
        "readme": high_watermark(
            (PROJECT / "README.md").read_text(encoding="utf-8"), README_WINDOW
        ),
        "handoff": high_watermark(
            (PROJECT / "HANDOFF.md").read_text(encoding="utf-8"), HANDOFF_WINDOW
        ),
    }
    distinct = sorted({value for value in claims.values() if value}, key=task_number)
    missing = [name for name, value in claims.items() if not value]

    report: dict[str, Any] = {
        "schema_version": "cyberboss.current_truth_guard.v1",
        "accepted_high_watermark_claims": claims,
        "distinct_claims": distinct,
        "sources_without_a_claim": missing,
        "handoff_parsed_lines": HANDOFF_WINDOW,
        "readme_parsed_lines": README_WINDOW,
        "status": "consistent" if len(distinct) == 1 and not missing else "split_brain",
        "remedy": (
            "lead the README status section and the HANDOFF Current state section with the "
            "latest accepted node so both stay inside the probe's parsed window"
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "consistent" else 1


if __name__ == "__main__":
    raise SystemExit(main())
