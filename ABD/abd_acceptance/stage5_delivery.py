"""Offline verifier for the already-completed S05 GitHub delivery receipt."""

from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "STAGE-DELIVERY-S05"
VERSION = "0.0.0.1"
RECEIPT_PATH = Path("machine/evidence/S05/STAGE_REVIEW/github_delivery_receipt.json")
STAGE_EVIDENCE_PATH = Path("machine/evidence/EVD-S05-STAGE-REVIEW.json")
STAGE_ROLLBACK_PATH = Path("machine/evidence/EVD-S05-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

PINNED_RECEIPT_SHA256 = "5926e2e8ef70c141b9453dbced4851f02499fda817d99a4922cfe3272f75ace2"
PINNED_STAGE_EVIDENCE_SHA256 = "ad479d5a395b4e80185070fb41951820659e20926abe7618482e007dde7f1152"
PINNED_STAGE_ROLLBACK_SHA256 = "0dcdded23e13c4f7c9eac0184d14024666bfdd7baf3e0bc847993557ee3f367d"

BASE_COMMIT = "b922219fa80fd0f55e8dd0d100a87ced2a77b2b8"
BRANCH_HEAD_COMMIT = "c5122925830f5e1c5678d798035124064fcc62c2"
MERGE_COMMIT = "b280104d2c67018417d84e83e1617d577aa666b7"
DELIVERED_COMMITS = [
    "6ddbf8a36b4b089ab0511bd26f7d0c0fa2662bcc",
    "8c0d0ec526e0bbbe571cc4f8dbf603bc7d4899c2",
    "3adc22b9e8bbe0b4df4def6a45caa4ebdd5df89a",
    "6aad40149a19e4012ab2520fe2002521465c24e3",
    "d48bb9ffd81ae2c269182af8e63d6ff124ff89c3",
]

EXPECTED_CHECKS = [
    {
        "workflow": "ABD continuous validation",
        "run_id": 30070333693,
        "job_id": 89409661656,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/30070333693",
        "completed_at": "2026-07-24T05:55:03Z",
    },
    {
        "workflow": "Dual-Plane Governance",
        "run_id": 30070333680,
        "job_id": 89409661418,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/30070333680",
        "completed_at": "2026-07-24T05:46:27Z",
    },
]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("decision_sha256")
    unsigned = deepcopy(dict(evidence))
    unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and _sha256_bytes(_json_bytes(unsigned)) == expected


def _load_index(root: Path) -> Sequence[Mapping[str, Any]]:
    return [
        json.loads(line)
        for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
        if line
    ]


def _git(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _check_git_history(repo_root: Path, checks: List[Dict[str, Any]]) -> None:
    parents = _git(repo_root, "show", "-s", "--format=%P", MERGE_COMMIT)
    expected_parents = "%s %s" % (BASE_COMMIT, BRANCH_HEAD_COMMIT)
    _add(
        checks,
        "S05DELIVERY-GIT-MERGE-PARENTS",
        parents.returncode == 0 and parents.stdout.decode("utf-8").strip() == expected_parents,
        parents.stdout.decode("utf-8", errors="replace").strip()
        if parents.returncode == 0
        else parents.stderr.decode("utf-8", errors="replace").strip(),
    )
    ancestry: Dict[str, bool] = {}
    for commit in DELIVERED_COMMITS:
        ancestry[commit] = _git(repo_root, "merge-base", "--is-ancestor", commit, MERGE_COMMIT).returncode == 0
    ancestry["merge_is_ancestor_of_HEAD"] = (
        _git(repo_root, "merge-base", "--is-ancestor", MERGE_COMMIT, "HEAD").returncode == 0
    )
    _add(checks, "S05DELIVERY-GIT-ANCESTRY", all(ancestry.values()), ancestry)


def verify_stage5_delivery(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    receipt = _safe_load(root / RECEIPT_PATH, checks, "S05DELIVERY-RECEIPT-STRICT-JSON")
    evidence = _safe_load(root / STAGE_EVIDENCE_PATH, checks, "S05DELIVERY-STAGE-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / STAGE_ROLLBACK_PATH, checks, "S05DELIVERY-STAGE-ROLLBACK-STRICT-JSON")

    hashes: Dict[str, str] = {}
    for relative, expected, check_id in [
        (RECEIPT_PATH, PINNED_RECEIPT_SHA256, "S05DELIVERY-RECEIPT-PINNED-HASH"),
        (STAGE_EVIDENCE_PATH, PINNED_STAGE_EVIDENCE_SHA256, "S05DELIVERY-STAGE-EVIDENCE-PINNED-HASH"),
        (STAGE_ROLLBACK_PATH, PINNED_STAGE_ROLLBACK_SHA256, "S05DELIVERY-STAGE-ROLLBACK-PINNED-HASH"),
    ]:
        try:
            actual = sha256_file(root / relative)
            hashes[relative.as_posix()] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    if isinstance(receipt, Mapping):
        expected_pr = {
            "number": 105,
            "state": "MERGED",
            "url": "https://github.com/LinzeColin/MetaDatabase/pull/105",
            "base_commit": BASE_COMMIT,
            "head_commit": BRANCH_HEAD_COMMIT,
            "merge_commit": MERGE_COMMIT,
            "merged_at": "2026-07-24T05:46:07Z",
        }
        shape_ok = (
            receipt.get("schema_version") == "1.0.0"
            and receipt.get("receipt_id") == "DELIVERY-S05-GITHUB-2026-07-24"
            and receipt.get("repository") == "LinzeColin/MetaDatabase"
            and receipt.get("repository_visibility_at_delivery") == "PUBLIC"
            and receipt.get("stage_id") == "S05"
            and receipt.get("product_version") == VERSION
            and receipt.get("observed_at") == "2026-07-24T05:55:03Z"
            and receipt.get("verification_mode") == "CAPTURED_GITHUB_API_FACTS_PLUS_OFFLINE_GIT_ANCESTRY"
            and receipt.get("delivery_status") == "VERIFIED_MERGED_AND_MAIN_CI_PASS"
            and receipt.get("next") == "S06/P01_READY_NOT_STARTED"
        )
        _add(checks, "S05DELIVERY-RECEIPT-SHAPE", shape_ok, receipt.get("receipt_id"))
        _add(checks, "S05DELIVERY-PR-IMMUTABLE-FACTS", receipt.get("pull_request") == expected_pr, receipt.get("pull_request"))
        _add(checks, "S05DELIVERY-COMMIT-SET-EXACT", receipt.get("delivered_commits") == DELIVERED_COMMITS, receipt.get("delivered_commits"))
        _add(
            checks,
            "S05DELIVERY-MAIN-CHECKS-EXACT",
            receipt.get("main_checks") == EXPECTED_CHECKS and receipt.get("all_required_main_checks_passed") is True,
            receipt.get("main_checks"),
        )
        expected_binding = {
            "path": STAGE_EVIDENCE_PATH.as_posix(),
            "sha256": PINNED_STAGE_EVIDENCE_SHA256,
            "rollback_path": STAGE_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": PINNED_STAGE_ROLLBACK_SHA256,
        }
        _add(checks, "S05DELIVERY-STAGE-EVIDENCE-BINDING", receipt.get("stage_review_evidence") == expected_binding, receipt.get("stage_review_evidence"))
        cost = receipt.get("delivery_cost_gate", {})
        cost_ok = (
            cost.get("status") == "PASS"
            and cost.get("incremental_cash_spent_aud") == "0.00"
            and cost.get("runner_classes") == ["ubuntu-latest"]
            and cost.get("chargeable_features_observed") == []
            and cost.get("billing_basis_url") == "https://docs.github.com/en/billing/concepts/product-billing/github-actions"
        )
        _add(checks, "S05DELIVERY-ZERO-CASH-DELIVERY-GATE", cost_ok, cost)
        effects = receipt.get("external_effects", {})
        effects_ok = effects == {
            "github_stage_upload_and_merge_performed": True,
            "github_api_read_performed": True,
            "wagering_provider_account_accessed": False,
            "gmail_account_accessed": False,
            "hosting_or_cdn_account_accessed": False,
            "secret_material_captured": False,
            "production_deployment_claimed": False,
            "real_order_submitted": False,
            "return_or_roi_verified": False,
        }
        _add(checks, "S05DELIVERY-EXTERNAL-EFFECTS-EXACT", effects_ok, effects)
    else:
        for check_id in [
            "S05DELIVERY-RECEIPT-SHAPE",
            "S05DELIVERY-PR-IMMUTABLE-FACTS",
            "S05DELIVERY-COMMIT-SET-EXACT",
            "S05DELIVERY-MAIN-CHECKS-EXACT",
            "S05DELIVERY-STAGE-EVIDENCE-BINDING",
            "S05DELIVERY-ZERO-CASH-DELIVERY-GATE",
            "S05DELIVERY-EXTERNAL-EFFECTS-EXACT",
        ]:
            _add(checks, check_id, False, "receipt unavailable")

    evidence_ok = (
        isinstance(evidence, Mapping)
        and evidence.get("schema_version") == "1.0.0"
        and evidence.get("evidence_id") == "EVD-S05-STAGE-REVIEW"
        and evidence.get("contract_id") == "STAGE-REVIEW-S05"
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "S05_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S05/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "NOT_READY_S06_TO_S19_AND_REAL_SOURCE_RUNTIME_ACTIVATION_REQUIRED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and _decision_hash_matches(evidence)
    )
    _add(checks, "S05DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", evidence_ok, evidence.get("status") if isinstance(evidence, Mapping) else "unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S05-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == "STAGE-REVIEW-S05"
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and rollback.get("provider_account_api_or_page_accessed") is False
        and rollback.get("scheduler_daemon_started") is False
    )
    _add(checks, "S05DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")

    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-S05-STAGE-REVIEW"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == PINNED_STAGE_EVIDENCE_SHA256
            and matching[0].get("actual_artifact") == STAGE_EVIDENCE_PATH.as_posix()
            and matching[0].get("next") == "S05/GITHUB_STAGE_UPLOAD_READY"
        )
        _add(checks, "S05DELIVERY-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S05DELIVERY-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_git_history:
        _check_git_history(root.parent, checks)
    else:
        _add(checks, "S05DELIVERY-TEST-ONLY-GIT-PROFILE", True, "Git history skipped only for isolated mutation clone")

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "stage_id": "S05",
        "product_version": VERSION,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_DELIVERED_S06_MAY_START" if not failed else "S06_START_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S06/P01_READY_NOT_STARTED" if not failed else "S05/DELIVERY_EVIDENCE_REMEDIATION_REQUIRED",
    }


def cli_verify_stage5_delivery(root: Path) -> Dict[str, Any]:
    result = verify_stage5_delivery(root, verify_git_history=True)
    return {
        "contract_id": CONTRACT_ID,
        "status": result["status"],
        "evidence_path": RECEIPT_PATH.as_posix(),
        "evidence_sha256": result.get("hashes", {}).get(RECEIPT_PATH.as_posix(), ""),
        "next": result["next"],
        "verification": result,
    }
