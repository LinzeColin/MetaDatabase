#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.formal_identity import verify_subject_against_root
from signal_lattice.receipts import atomic_json, canonical_json_bytes, load_self_hashed, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--owner-approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    approval = load_self_hashed(args.owner_approval)
    if approval.get("approved") is not True or approval.get("version") != VERSION:
        raise SystemExit("OWNER_APPROVAL_INVALID")
    if approval.get("formal_release_pass_claimed") is not False or approval.get("live_action_enabled") is not False:
        raise SystemExit("OWNER_APPROVAL_SCOPE_INVALID")
    subject = json.loads((root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
    findings = verify_subject_against_root(subject, root, require_frozen=False)
    if findings:
        raise SystemExit("PREPARED_SUBJECT_INVALID:" + ",".join(findings[:5]))
    if subject.get("state") != "PREPARED" or approval.get("prepared_subject_sha256") != subject.get("subject_sha256"):
        raise SystemExit("OWNER_APPROVAL_SUBJECT_MISMATCH")
    canonical = json.loads((root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))
    gate = canonical.get("owner_gate", {})
    if canonical.get("current_phase") != "SEALED_TASKPACK" or gate.get("owner_override_authorized") is not True:
        raise SystemExit("CANONICAL_STATE_NOT_SEALED_TASKPACK")
    if gate.get("owner_approval_receipt") != "evidence/owner_gate/taskpack_owner_approval.json":
        raise SystemExit("OWNER_APPROVAL_RECEIPT_BINDING_MISMATCH")
    latest = canonical.get("latest_iteration", {})
    if latest.get("open_p0") != 0 or latest.get("open_p1") != 0:
        raise SystemExit("OPEN_P0_P1_PREVENTS_TASKPACK_SEAL")
    prebuild = load_self_hashed(root / "evidence/prebuild/pre_manifest_checks.json")
    if prebuild.get("state") != "PASS":
        raise SystemExit("PREBUILD_CHECKS_NOT_PASS")
    manifest = root / "MANIFEST.json"
    guard = subprocess.run(
        [sys.executable, "scripts/verify_package.py", "--root", str(root), "--manifest", str(manifest)],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "PYTHONPATH": str(root / "src"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if guard.returncode != 0:
        raise SystemExit("PACKAGE_GUARD_NOT_PASS:" + (guard.stdout + guard.stderr)[-500:])
    residual = json.loads((root / "machine/facts/residual_environment_tasks.json").read_text(encoding="utf-8"))
    tasks = residual.get("tasks", [])
    if not tasks or any(row.get("environment_bound") is not True for row in tasks):
        raise SystemExit("RESIDUAL_ENVIRONMENT_TASKS_INVALID")
    rows = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    taskpack_sha = hashlib.sha256(canonical_json_bytes({
        "version": VERSION,
        "prepared_subject_sha256": subject["subject_sha256"],
        "manifest_rows": rows,
        "owner_approval_sha256": sha256_file(args.owner_approval),
        "residual_environment_tasks_sha256": sha256_file(root / "machine/facts/residual_environment_tasks.json"),
    })).hexdigest()
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "scope": "SEALED_DEVELOPMENT_TASKPACK_ONLY",
        "version": VERSION,
        "taskpack_sha256": taskpack_sha,
        "prepared_subject_sha256": subject["subject_sha256"],
        "owner_approval_sha256": sha256_file(args.owner_approval),
        "manifest_sha256": sha256_file(manifest),
        "prebuild_checks_sha256": sha256_file(root / "evidence/prebuild/pre_manifest_checks.json"),
        "residual_environment_tasks_sha256": sha256_file(root / "machine/facts/residual_environment_tasks.json"),
        "residual_environment_task_count": len(tasks),
        "deferred_release_gates": ["UPSTREAM_FORMAL_SEAL", "FORMAL_INDEPENDENT_REVIEW", "FROZEN_CANDIDATE", "VERIFY_AND_RELEASE"],
        "formal_release_pass_claimed": False,
        "live_action_enabled": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_token_budget": 0,
        "owner_override_used": True,
        "owner_override_scope": "TASKPACK_SEAL_ONLY_NOT_RELEASE_PASS",
    }
    output = args.output if args.output.is_absolute() else root / args.output
    atomic_json(output, payload)
    print(json.dumps({"state": "PASS", "scope": payload["scope"], "taskpack_sha256": taskpack_sha, "output": output.as_posix()}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
