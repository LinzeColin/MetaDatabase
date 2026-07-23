#!/usr/bin/env python3
"""Consume and validate the pinned shared Governance without vendoring it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from build_governance_facts import PROJECT_ROOT, write_or_check


SEVEN = [
    "00_我在哪.md",
    "01_产品需求.md",
    "02_系统架构.md",
    "03_口径字典.md",
    "04_操作流程.md",
    "05_执行与验收.md",
    "06_运维手册.md",
]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def validate(root: Path, governance_root: Path, *, render: bool = False) -> dict[str, Any]:
    root = root.resolve()
    governance_root = governance_root.resolve()
    binding = _load(root / "machine/contracts/governance_binding.json")
    failures: list[str] = []

    if not governance_root.is_dir():
        failures.append("external Governance checkout is missing")
        return {"status": "FAIL", "failures": failures}
    commit = _run(["git", "rev-parse", "HEAD"], cwd=governance_root)
    if commit.returncode != 0 or commit.stdout.strip() != binding["commit"]:
        failures.append("Governance checkout commit does not match the pin")

    tools: dict[str, Path] = {}
    for item in binding["tools"]:
        path = governance_root / item["path"]
        tools[Path(item["path"]).name] = path
        if not path.is_file() or _sha256(path) != item["sha256"]:
            failures.append(f"pinned tool hash mismatch: {Path(item['path']).name}")
    mismatches = write_or_check(root, write=False)
    if mismatches:
        failures.append("derived Governance facts are stale")
    if failures:
        return {"status": "FAIL", "failures": failures, "fact_mismatches": mismatches}

    if render:
        rendered = _run(
            [sys.executable, str(tools["render_human.py"]), "--root", str(root)],
            cwd=root,
        )
        if rendered.returncode != 0:
            failures.append("shared renderer failed")
        return {"status": "PASS" if not failures else "FAIL", "mode": "render", "failures": failures}

    with tempfile.TemporaryDirectory(prefix="moomooau-governance-") as temp_name:
        temp_root = Path(temp_name)
        shutil.copytree(root / "machine/facts", temp_root / "machine/facts")
        shutil.copytree(root / "machine/runs", temp_root / "machine/runs")
        (temp_root / "文档").mkdir(parents=True)
        rendered = _run(
            [sys.executable, str(tools["render_human.py"]), "--root", str(temp_root)],
            cwd=temp_root,
        )
        if rendered.returncode != 0:
            failures.append("shared renderer failed in temporary project")
        drift = []
        for name in SEVEN:
            expected = temp_root / "文档" / name
            committed = root / "文档" / name
            if not expected.is_file() or not committed.is_file() or expected.read_bytes() != committed.read_bytes():
                drift.append(name)
        if drift:
            failures.append("seven-file render drift")

        budget = _run(
            [sys.executable, str(tools["check_doc_budget.py"]), "--docs", str(temp_root / "文档")],
            cwd=temp_root,
        )
        blocker = _run(
            [sys.executable, str(tools["check_blocker_stop.py"]), "--machine", str(temp_root / "machine")],
            cwd=temp_root,
        )
        if budget.returncode != 0:
            failures.append("shared document gates failed: " + budget.stdout.strip().replace("\n", " | "))
        if blocker.returncode != 0:
            failures.append("shared blocker gate failed: " + blocker.stdout.strip().replace("\n", " | "))

    return {
        "status": "PASS" if not failures else "FAIL",
        "mode": "check",
        "governance_commit": binding["commit"],
        "fact_mismatches": mismatches,
        "render_drift": drift,
        "shared_budget_gate": "PASS" if budget.returncode == 0 else "FAIL",
        "shared_blocker_gate": "PASS" if blocker.returncode == 0 else "FAIL",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--governance-root",
        type=Path,
        default=Path(os.environ["MOOMOOAU_GOVERNANCE_ROOT"]) if os.environ.get("MOOMOOAU_GOVERNANCE_ROOT") else None,
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if args.governance_root is None:
        print(json.dumps({"status": "FAIL", "failures": ["MOOMOOAU_GOVERNANCE_ROOT or --governance-root is required"]}))
        return 1
    result = validate(args.root, args.governance_root, render=args.render)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
