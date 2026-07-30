#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.formal_identity import verify_subject_against_root
from signal_lattice.receipts import canonical_json_bytes, load_self_hashed, sha256_file
from signal_lattice.state_machine import load_state, validate_state


TRANSIENT_PARTS = {".git", ".pytest_cache", "__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache"}


def embedded_stock_skill_payload_sha256(root: Path) -> str:
    stock_root = root / "Stock_Skill"
    if not stock_root.is_dir() or stock_root.is_symlink():
        raise ValueError("EMBEDDED_STOCK_SKILL_SOURCE_REQUIRED")
    rows = []
    for path in sorted(stock_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("EMBEDDED_STOCK_SKILL_SYMLINK_FORBIDDEN")
        if not path.is_file() or any(part in TRANSIENT_PARTS for part in path.relative_to(stock_root).parts):
            continue
        rows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": sha256_file(path)})
    if not rows:
        raise ValueError("EMBEDDED_STOCK_SKILL_SOURCE_EMPTY")
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[str] = []
    subject: dict[str, object] = {}
    try:
        state = load_state(root / "CANONICAL_STATE.json")
        result = validate_state(state, VERSION)
        findings.extend(result.findings)
        if result.current_phase != "SEALED_TASKPACK":
            findings.append("CURRENT_PHASE_NOT_SEALED_TASKPACK")
    except Exception as exc:
        findings.append("CANONICAL_STATE_INVALID:" + type(exc).__name__)
        state = {}
    try:
        approval = load_self_hashed(root / "evidence/owner_gate/taskpack_owner_approval.json")
        if approval.get("approved") is not True or approval.get("version") != VERSION:
            findings.append("OWNER_APPROVAL_INVALID")
        if approval.get("formal_release_pass_claimed") is not False or approval.get("live_action_enabled") is not False:
            findings.append("OWNER_APPROVAL_SCOPE_INVALID")
    except Exception as exc:
        findings.append("OWNER_APPROVAL_INVALID:" + type(exc).__name__)
        approval = {}
    try:
        seal = load_self_hashed(root / "evidence/owner_gate/taskpack_seal.json")
        if seal.get("state") != "PASS" or seal.get("scope") != "SEALED_DEVELOPMENT_TASKPACK_ONLY":
            findings.append("TASKPACK_SEAL_NOT_PASS")
        if seal.get("formal_release_pass_claimed") is not False or seal.get("live_action_enabled") is not False:
            findings.append("TASKPACK_SEAL_SCOPE_INVALID")
        if seal.get("owner_approval_sha256") != sha256_file(root / "evidence/owner_gate/taskpack_owner_approval.json"):
            findings.append("TASKPACK_SEAL_OWNER_BINDING_DRIFT")
        if seal.get("manifest_sha256") != sha256_file(root / "MANIFEST.json"):
            findings.append("TASKPACK_SEAL_MANIFEST_BINDING_DRIFT")
        if seal.get("embedded_stock_skill_payload_sha256") != embedded_stock_skill_payload_sha256(root):
            findings.append("TASKPACK_SEAL_STOCK_SKILL_BINDING_DRIFT")
    except Exception as exc:
        findings.append("TASKPACK_SEAL_INVALID:" + type(exc).__name__)
        seal = {}
    try:
        subject = json.loads((root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
        findings.extend(verify_subject_against_root(subject, root, require_frozen=False))
        if subject.get("state") != "PREPARED":
            findings.append("TASKPACK_REQUIRES_PREPARED_SUBJECT")
        if approval and approval.get("prepared_subject_sha256") != subject.get("subject_sha256"):
            findings.append("OWNER_APPROVAL_SUBJECT_DRIFT")
        if seal and seal.get("prepared_subject_sha256") != subject.get("subject_sha256"):
            findings.append("TASKPACK_SEAL_SUBJECT_DRIFT")
    except Exception as exc:
        findings.append("SUBJECT_INVALID:" + type(exc).__name__)
    residual = root / "machine/facts/residual_environment_tasks.json"
    try:
        tasks = json.loads(residual.read_text(encoding="utf-8"))
        if tasks.get("non_environment_unknown_count") != 0 or tasks.get("developer_research_required") is not False:
            findings.append("RESIDUAL_TASK_SCOPE_INVALID")
        if not tasks.get("tasks") or any(row.get("environment_bound") is not True for row in tasks.get("tasks", [])):
            findings.append("RESIDUAL_TASKS_NOT_ENVIRONMENT_BOUND")
    except Exception as exc:
        findings.append("RESIDUAL_TASKS_INVALID:" + type(exc).__name__)
        tasks = {}
    try:
        manifest_rows = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
        expected_taskpack_sha = hashlib.sha256(canonical_json_bytes({
            "version": VERSION,
            "prepared_subject_sha256": subject["subject_sha256"],
            "manifest_rows": manifest_rows,
            "embedded_stock_skill_payload_sha256": embedded_stock_skill_payload_sha256(root),
            "owner_approval_sha256": sha256_file(root / "evidence/owner_gate/taskpack_owner_approval.json"),
            "residual_environment_tasks_sha256": sha256_file(residual),
        })).hexdigest()
        if seal and seal.get("taskpack_sha256") != expected_taskpack_sha:
            findings.append("TASKPACK_SEAL_IDENTITY_DRIFT")
    except Exception as exc:
        findings.append("TASKPACK_SEAL_IDENTITY_INVALID:" + type(exc).__name__)
    payload = {
        "state": "PASS" if not findings else "FAIL",
        "version": VERSION,
        "findings": findings,
        "formal_release_pass_claimed": False,
        "live_action_enabled": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_token_budget": 0,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
