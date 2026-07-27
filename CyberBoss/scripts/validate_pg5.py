#!/usr/bin/env python3
"""Fail-closed local seal for the PG-5 native final exit gate."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/PG-5"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB540_CLOSURE = "70086d4686975dd4dea39ef30ccefa1562f7302d"
CB540_SUBJECT_SHA256 = "0286ab849a57769557ac661a906cae29443e6a4babc367f992d085e04ef9ee00"
DEPLOYMENT_DIGEST = "feb6ee99d3c13960a93d912f7878c48b51c587419618b79cef75eea2a890a5c9"
CURRENT_RELEASE = "fd3cd1e19d70caa148c3785288aaabfb909fed85"
PREVIOUS_RELEASE = "25670bf32c6d27e3668fcf59bc9ab754035e161d"
RELEASE_MANIFEST_SHA256 = "4829f41e002e5c6fa242182d851317df376d6f407a8c593577612af738490ff7"
CRITICAL_ACCEPTANCE = {
    "FA-AC-001": "PASS", "FA-AC-020": "PASS", "FA-AC-021": "PASS",
    "FA-AC-022": "PASS", "FA-AC-023": "PASS", "FA-AC-024": "PASS",
    "FA-AC-025": "PASS", "FA-AC-027": "PASS", "FA-AC-028": "PASS",
    "FA-AC-029": "PASS", "FA-AC-030": "PASS",
}
ROUTER_RESULT = {
    "task_id": "PG-5", "selected_skill": None, "mode": "DETERMINISTIC_TEST_ONLY",
    "max_lightweight_skill_loads": 0, "prohibited_skill_loads": 0, "actual_skill_body_loads": 0,
}
EVIDENCE_FILES = {"summary.json", "subject.json", "final-publication.md", "external-acceptance-candidate.json"}
RECEIPTS = ("real_e2e_receipt", "private_database_receipt", "r2_restore_receipt", "oci_restore_receipt", "access_status_receipt", "rollback_receipt")
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}", re.IGNORECASE,
)


def git(*args: str, check: bool = True) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git_failed")
    return result.returncode, result.stdout.rstrip()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("json_root")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def validate_state(errors: list[str]) -> None:
    try:
        state = load_json(PROJECT / "machine/facts/task_state.json")
    except (OSError, ValueError, TypeError):
        errors.append("task_state_read")
        return
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    required = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230", "CB-240", "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440", "CB-500", "CB-510", "CB-520", "CB-530", "CB-540",
    )
    report(errors, "task_state_tasks", all(statuses.get(task) == "passed" for task in required))
    report(errors, "task_state_pg5", state.get("pass_gates", {}).get("PG-5") == "passed")
    report(errors, "task_state_current_run", state.get("current_run") == {
        "run_id": "PG-5", "gate_id": "PG-5", "task_id": None,
        "scope": "native_final_exit_gate_mvp_degraded_subject_seal_and_external_candidate", "status": "passed",
    })
    overlay = state.get("taskpack_overlay", {})
    report(errors, "task_state_overlay", all((
        state.get("schema_version") == 1, state.get("taskpack_version") == TASKPACK_VERSION,
        overlay.get("product_version") == PRODUCT_VERSION, overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256,
        overlay.get("skill_router") == ROUTER_RESULT, overlay.get("pg_5_executed") is True,
        overlay.get("pg_5_native_decision") == "MVP_DEGRADED",
        overlay.get("pg_5_external_formal_acceptance") == "BLOCKED_EXTERNAL_INDEPENDENT_CONTEXTS_NOT_RUN",
        overlay.get("pg_5_deployment_digest") == DEPLOYMENT_DIGEST,
        overlay.get("pg_5_critical_acceptance") == "all_pass",
        overlay.get("formal_final_acceptance") == "blocked_external_independent_contexts_not_run",
        overlay.get("control_plane_llm_calls") == 0, overlay.get("operations_llm_calls") == 0,
        overlay.get("macos_launchd_dependency") is False,
    )))


def validate_evidence(errors: list[str]) -> None:
    inventory = {candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()} if EVIDENCE.is_dir() else set()
    report(errors, "evidence_inventory", inventory == EVIDENCE_FILES)
    if inventory != EVIDENCE_FILES:
        return
    try:
        summary = load_json(EVIDENCE / "summary.json")
        subject = load_json(EVIDENCE / "subject.json")
        external = load_json(EVIDENCE / "external-acceptance-candidate.json")
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return
    report(errors, "summary_contract", all((
        summary.get("schema_version") == "cyberboss.pg5.final-exit-summary.v1", summary.get("task_id") == "PG-5",
        summary.get("product_version") == PRODUCT_VERSION, summary.get("taskpack_version") == TASKPACK_VERSION,
        summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256, summary.get("cb_540_closure_commit") == CB540_CLOSURE,
        summary.get("cb_540_subject_sha256") == CB540_SUBJECT_SHA256,
        summary.get("deployment") == {
            "digest": DEPLOYMENT_DIGEST, "current": CURRENT_RELEASE, "previous": PREVIOUS_RELEASE,
            "source_archive_sha256": "288147fde6622cb76c5e21a3600d16d71134510b9215554a8a8261bbe309c1c2",
            "release_manifest_sha256": RELEASE_MANIFEST_SHA256,
        },
        summary.get("skill_router") == ROUTER_RESULT, summary.get("critical_acceptance") == CRITICAL_ACCEPTANCE,
        summary.get("development_candidate", {}).get("decision") == "MVP_DEGRADED",
        summary.get("development_candidate", {}).get("unaccepted_p0") == [],
        summary.get("development_candidate", {}).get("unaccepted_p1") == [],
        isinstance(summary.get("development_candidate", {}).get("degraded_components"), list),
        summary.get("receipts", {}).get("rollback") == "PASS_current_previous_current",
        summary.get("receipts", {}).get("self_heal") == "PASS_exact_channel_pending_no_restart",
        summary.get("external_formal_acceptance") == {
            "verdict": "BLOCKED", "blockers": ["two independent verifier contexts missing"],
            "development_must_not_wait": True,
        },
        summary.get("publication", {}).get("intermediate_pushes") == 0,
        summary.get("publication", {}).get("intermediate_pull_requests") == 0,
        summary.get("publication", {}).get("intermediate_tags") == 0,
        summary.get("safety", {}).get("control_plane_llm_calls") == 0,
        summary.get("safety", {}).get("operations_llm_calls") == 0,
        summary.get("safety", {}).get("real_time_waits") == 0,
        summary.get("safety", {}).get("macos_launchd_dependency") is False,
        summary.get("result") == "passed_mvp_degraded_external_formal_blocked",
        summary.get("formal_final_acceptance") == "BLOCKED_EXTERNAL_INDEPENDENT_CONTEXTS_NOT_RUN",
    )))
    report(errors, "subject_contract", all((
        subject.get("schema_version") == "cyberboss.pg5.subject.v1", subject.get("task_id") == "PG-5",
        subject.get("product_version") == PRODUCT_VERSION, subject.get("taskpack_version") == TASKPACK_VERSION,
        subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256, subject.get("cb_540_closure_commit") == CB540_CLOSURE,
        subject.get("cb_540_subject_sha256") == CB540_SUBJECT_SHA256,
        subject.get("deployment_digest") == DEPLOYMENT_DIGEST, subject.get("deployment_current") == CURRENT_RELEASE,
        subject.get("deployment_previous") == PREVIOUS_RELEASE, subject.get("release_manifest_sha256") == RELEASE_MANIFEST_SHA256,
        subject.get("summary_sha256") == sha256(EVIDENCE / "summary.json"),
        subject.get("final_publication_sha256") == sha256(EVIDENCE / "final-publication.md"),
        subject.get("external_acceptance_candidate_sha256") == sha256(EVIDENCE / "external-acceptance-candidate.json"),
        subject.get("run_contract_sha256") == sha256(PROJECT / "docs/governance/RUN_CONTRACT_PG_5.md"),
        subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256"),
        subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256"),
        subject.get("development_candidate") == "MVP_DEGRADED", subject.get("critical_acceptance") == "all_pass",
        subject.get("formal_final_acceptance") == "BLOCKED_EXTERNAL_INDEPENDENT_CONTEXTS_NOT_RUN",
        subject.get("independent_verifier_contexts") == 0,
        all(subject.get(key) == 0 for key in ("control_plane_llm_calls", "operations_llm_calls", "real_time_waits")),
        subject.get("macos_launchd_dependency") is False,
    )))
    report(errors, "external_candidate", all((
        external.get("verdict") == "BLOCKED", external.get("subject", {}).get("deployment_digest") == DEPLOYMENT_DIGEST,
        external.get("critical_acceptance") == CRITICAL_ACCEPTANCE, external.get("independent_verifier_receipts") == [],
        external.get("unaccepted_p0") == [], external.get("unaccepted_p1") == [],
        "两个独立 contexts" in external.get("reason", ""),
        all(isinstance(external.get(key), dict) and external[key].get("status") == "PASS" and bool(external[key].get("sha256")) for key in RECEIPTS),
    )))
    publication = (EVIDENCE / "final-publication.md").read_text(encoding="utf-8")
    report(errors, "publication_markers", all(marker in publication for marker in (
        "MVP_DEGRADED", "FORMAL_FINAL_ACCEPTANCE=BLOCKED", "不创建仓库", "一次该 branch 的 push", "clean",
    )))
    for candidate in EVIDENCE.iterdir():
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            if SECRET_PATTERN.search(content) or "/Users/" in content or "/var/lib/" in content:
                errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")


def validate_source(errors: list[str]) -> None:
    report(errors, "contract_exists", (PROJECT / "docs/governance/RUN_CONTRACT_PG_5.md").is_file())
    report(errors, "cb540_closure_exists", git("cat-file", "-e", f"{CB540_CLOSURE}^{{commit}}", check=False)[0] == 0)
    report(errors, "cb540_closure_ancestor", git("merge-base", "--is-ancestor", CB540_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "frozen_design_unchanged", git("diff", "--quiet", CB540_CLOSURE, "--", "CyberBoss/docs/product_design/v0.0.0.4", check=False)[0] == 0)
    report(errors, "diff_check", git("diff", "--check", CB540_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "clean_worktree", git("status", "--porcelain")[1] == "")


def main() -> int:
    errors: list[str] = []
    validate_state(errors)
    validate_evidence(errors)
    validate_source(errors)
    print(f"mode=final\nerrors={len(errors)}")
    for error in errors:
        print(error)
    print("PG5_VALIDATION=PASS" if not errors else "PG5_VALIDATION=FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
