#!/usr/bin/env python3
"""Prepare a v18 forward result and bind its trace to exact validator bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import presentation_contract


HEADINGS = (
    "## Decision",
    "## Funded demand",
    "## System map",
    "## Constraint proof",
    "## Security map",
    "## Equity capture",
    "## Three clocks",
    "## Valuation",
    "## Catalysts",
    "## Red team",
    "## Kill switches",
    "## Portfolio fit",
    "## Open questions",
    "## Sources",
)
FIELDS = {
    "memo_markdown",
    "evidence_json",
    "opportunity_json",
    "portfolio_json",
    "decision_label",
    "research_trace",
}
TRACE_FIELDS = {
    "files_read",
    "web_searches",
    "pages_opened",
    "files_written",
    "limitations",
}
REPLAYS = {
    "evidence": (
        "evidence_json",
        ("scripts/validate_evidence.py", "-"),
    ),
    "opportunity": (
        "opportunity_json",
        ("scripts/score_opportunity.py", "-", "--format", "json"),
    ),
    "portfolio": (
        "portfolio_json",
        ("scripts/analyze_portfolio_clusters.py", "-"),
    ),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a nonempty-string array")
    return value


def replay(
    skill_root: Path,
    field: str,
    value: str,
    argv: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stdin = value.encode("utf-8")
    completed = subprocess.run(
        [sys.executable, *argv],
        cwd=skill_root,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"{field} validator failed: "
            + completed.stderr.decode("utf-8", errors="replace")
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} validator stdout is not JSON") from exc
    return (
        {
            "field": field,
            "command": "python3 " + " ".join(argv),
            "exit_code": completed.returncode,
            "stdin_sha256": sha256(stdin),
            "stdout_sha256": sha256(completed.stdout),
        },
        parsed,
    )


def prepare(draft_path: Path, output_path: Path, seal_sha256: str) -> dict[str, Any]:
    if len(seal_sha256) != 64 or any(character not in "0123456789abcdef" for character in seal_sha256):
        raise ValueError("preexecution seal SHA-256 must be lowercase hexadecimal")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict) or set(draft) != FIELDS:
        raise ValueError("draft fields do not match the v18 preparation contract")
    for field in FIELDS - {"research_trace"}:
        if not isinstance(draft[field], str) or not draft[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    trace = draft["research_trace"]
    if not isinstance(trace, dict) or set(trace) != TRACE_FIELDS:
        raise ValueError("research_trace fields do not match the v18 contract")
    for field in TRACE_FIELDS:
        string_list(trace[field], f"research_trace.{field}")

    decoded: list[dict[str, Any]] = []
    for field in ("evidence_json", "opportunity_json", "portfolio_json"):
        value = json.loads(draft[field])
        if not isinstance(value, dict):
            raise ValueError(f"{field} must encode one JSON object")
        decoded.append(value)
    headings = tuple(
        line for line in draft["memo_markdown"].splitlines() if line.startswith("## ")
    )
    if headings != HEADINGS:
        raise ValueError("memo heading order does not match the v18 contract")
    violations = presentation_contract.find_role_neutral_violations(
        draft["memo_markdown"],
        "## Security map",
        decoded,
    )
    if violations:
        raise ValueError(
            "issuer/security marker before Security map: " + ", ".join(violations)
        )

    skill_root = Path(__file__).resolve().parents[1]
    validator_replay: dict[str, dict[str, Any]] = {}
    parsed_replay: dict[str, dict[str, Any]] = {}
    for label, (field, argv) in REPLAYS.items():
        trace_row, parsed = replay(skill_root, field, draft[field], argv)
        validator_replay[label] = trace_row
        parsed_replay[label] = parsed
    opportunity_result = parsed_replay["opportunity"]
    if opportunity_result.get("decision", {}).get("label") != draft["decision_label"]:
        raise ValueError("decision_label does not match deterministic scorer")
    if opportunity_result.get("warnings") != []:
        raise ValueError("opportunity replay contains unresolved validator warnings")
    if parsed_replay["evidence"] != {
        **parsed_replay["evidence"],
        "valid": True,
        "errors": [],
        "warnings": [],
    }:
        raise ValueError("evidence replay did not pass cleanly")
    portfolio_result = parsed_replay["portfolio"]
    if portfolio_result.get("valid") is not True or portfolio_result.get("errors") != []:
        raise ValueError("portfolio replay did not pass cleanly")

    output = {
        field: draft[field]
        for field in (
            "memo_markdown",
            "evidence_json",
            "opportunity_json",
            "portfolio_json",
            "decision_label",
        )
    }
    output["execution_trace"] = {
        "trace_version": "1.0",
        "preexecution_seal_sha256": seal_sha256,
        "files_read": trace["files_read"],
        "web_searches": trace["web_searches"],
        "pages_opened": trace["pages_opened"],
        "files_written": trace["files_written"],
        "validator_replay": validator_replay,
        "limitations": trace["limitations"],
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


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
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS: prepared v18 output; "
        f"decision={output['decision_label']}; "
        "replay=evidence/opportunity/portfolio"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
