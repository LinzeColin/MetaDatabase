from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "STAGE-DELIVERY-S01"
VERSION = "0.0.0.1"
RECEIPT_PATH = Path("machine/evidence/S01/STAGE_REVIEW/github_delivery_receipt.json")
STAGE_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-STAGE-REVIEW.json")
STAGE_ROLLBACK_PATH = Path("machine/evidence/EVD-S01-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

PINNED_RECEIPT_SHA256 = "ca4f4d34507a11afaa72a261b6603699264460a078335ff4a36a1d8791e35dde"
PINNED_STAGE_EVIDENCE_SHA256 = "3e5a64f3b99fae7b67aeb0d18d94cd13eb0077b1c856dadbac0d8bbff6f5886d"
PINNED_STAGE_ROLLBACK_SHA256 = "e58704772cc350fedece3b3780c6d344c1f4fcee5c61013981072882cc3677f7"

BASE_COMMIT = "7109a4a6af1354428b80088f262b59575919e3f1"
BRANCH_HEAD_COMMIT = "946382d971b04e5a8d4a482993dbabbe5df8fbac"
MERGE_COMMIT = "ea459444f1cf67c5432600b39cac479a4c2cac2f"
DELIVERED_COMMITS = [
    "7c52659e2f6de6ebfff6d3079ba0a29cf542867e",
    "214232879e068c9703695ab098e92e010ac2db7f",
    "a4d5e3076f1e327072680207944a2d75514b1f03",
    "78c92ca58c45226ede9d7705d039c5abe7ea91c0",
    "ddd7664acdd12e51b590233da7d65322a378c3d2",
    BRANCH_HEAD_COMMIT,
]

EXPECTED_CHECKS = [
    {
        "workflow": "ABD continuous validation",
        "run_id": 29691089138,
        "job_id": 88203836547,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29691089138",
        "completed_at": "2026-07-19T14:35:44Z",
    },
    {
        "workflow": "Dual-Plane Governance",
        "run_id": 29691089152,
        "job_id": 88203836514,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29691089152",
        "completed_at": "2026-07-19T14:34:25Z",
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


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _check_git_history(repo_root: Path, checks: List[Dict[str, Any]]) -> None:
    parents = _git(repo_root, "show", "-s", "--format=%P", MERGE_COMMIT)
    expected_parents = "%s %s" % (BASE_COMMIT, BRANCH_HEAD_COMMIT)
    _add(
        checks,
        "S01DELIVERY-GIT-MERGE-PARENTS",
        parents.returncode == 0 and parents.stdout.decode("utf-8").strip() == expected_parents,
        parents.stdout.decode("utf-8", errors="replace").strip()
        if parents.returncode == 0
        else parents.stderr.decode("utf-8", errors="replace").strip(),
    )

    ancestry: Dict[str, bool] = {}
    for commit in DELIVERED_COMMITS:
        result = _git(repo_root, "merge-base", "--is-ancestor", commit, MERGE_COMMIT)
        ancestry[commit] = result.returncode == 0
    head_result = _git(repo_root, "merge-base", "--is-ancestor", MERGE_COMMIT, "HEAD")
    ancestry["merge_is_ancestor_of_HEAD"] = head_result.returncode == 0
    _add(checks, "S01DELIVERY-GIT-ANCESTRY", all(ancestry.values()), ancestry)


def verify_stage1_delivery(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    receipt = _safe_load(root / RECEIPT_PATH, checks, "S01DELIVERY-RECEIPT-STRICT-JSON")
    evidence = _safe_load(root / STAGE_EVIDENCE_PATH, checks, "S01DELIVERY-STAGE-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / STAGE_ROLLBACK_PATH, checks, "S01DELIVERY-STAGE-ROLLBACK-STRICT-JSON")

    hashes: Dict[str, str] = {}
    for relative, expected, check_id in [
        (RECEIPT_PATH, PINNED_RECEIPT_SHA256, "S01DELIVERY-RECEIPT-PINNED-HASH"),
        (STAGE_EVIDENCE_PATH, PINNED_STAGE_EVIDENCE_SHA256, "S01DELIVERY-STAGE-EVIDENCE-PINNED-HASH"),
        (STAGE_ROLLBACK_PATH, PINNED_STAGE_ROLLBACK_SHA256, "S01DELIVERY-STAGE-ROLLBACK-PINNED-HASH"),
    ]:
        try:
            actual = sha256_file(root / relative)
            hashes[relative.as_posix()] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    if isinstance(receipt, dict):
        expected_pr = {
            "number": 64,
            "state": "MERGED",
            "url": "https://github.com/LinzeColin/MetaDatabase/pull/64",
            "base_commit": BASE_COMMIT,
            "head_commit": BRANCH_HEAD_COMMIT,
            "merge_commit": MERGE_COMMIT,
            "merged_at": "2026-07-19T14:34:04Z",
        }
        shape_ok = (
            receipt.get("schema_version") == "1.0.0"
            and receipt.get("receipt_id") == "DELIVERY-S01-GITHUB-2026-07-20"
            and receipt.get("repository") == "LinzeColin/MetaDatabase"
            and receipt.get("repository_visibility_at_delivery") == "PUBLIC"
            and receipt.get("stage_id") == "S01"
            and receipt.get("product_version") == VERSION
            and receipt.get("verification_mode") == "CAPTURED_GITHUB_API_FACTS_PLUS_OFFLINE_GIT_ANCESTRY"
            and receipt.get("delivery_status") == "VERIFIED_MERGED_AND_MAIN_CI_PASS"
            and receipt.get("next") == "S02/P01_READY_NOT_STARTED"
        )
        _add(checks, "S01DELIVERY-RECEIPT-SHAPE", shape_ok, receipt.get("receipt_id"))
        _add(checks, "S01DELIVERY-PR-IMMUTABLE-FACTS", receipt.get("pull_request") == expected_pr, receipt.get("pull_request"))
        _add(
            checks,
            "S01DELIVERY-COMMIT-SET-EXACT",
            receipt.get("delivered_commits") == DELIVERED_COMMITS,
            receipt.get("delivered_commits"),
        )
        _add(
            checks,
            "S01DELIVERY-MAIN-CHECKS-EXACT",
            receipt.get("main_checks") == EXPECTED_CHECKS and receipt.get("all_required_main_checks_passed") is True,
            receipt.get("main_checks"),
        )
        expected_binding = {
            "path": STAGE_EVIDENCE_PATH.as_posix(),
            "sha256": PINNED_STAGE_EVIDENCE_SHA256,
            "rollback_path": STAGE_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": PINNED_STAGE_ROLLBACK_SHA256,
        }
        _add(
            checks,
            "S01DELIVERY-STAGE-EVIDENCE-BINDING",
            receipt.get("stage_review_evidence") == expected_binding,
            receipt.get("stage_review_evidence"),
        )
        cost = receipt.get("delivery_cost_gate", {})
        cost_ok = (
            cost.get("status") == "PASS"
            and cost.get("incremental_cash_spent_aud") == "0.00"
            and cost.get("runner_classes") == ["ubuntu-latest"]
            and cost.get("chargeable_features_observed") == []
            and cost.get("billing_basis_url") == "https://docs.github.com/en/billing/concepts/product-billing/github-actions"
        )
        _add(checks, "S01DELIVERY-ZERO-CASH-DELIVERY-GATE", cost_ok, cost)
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
        _add(checks, "S01DELIVERY-EXTERNAL-EFFECTS-EXACT", effects_ok, effects)
    else:
        for check_id in [
            "S01DELIVERY-RECEIPT-SHAPE",
            "S01DELIVERY-PR-IMMUTABLE-FACTS",
            "S01DELIVERY-COMMIT-SET-EXACT",
            "S01DELIVERY-MAIN-CHECKS-EXACT",
            "S01DELIVERY-STAGE-EVIDENCE-BINDING",
            "S01DELIVERY-ZERO-CASH-DELIVERY-GATE",
            "S01DELIVERY-EXTERNAL-EFFECTS-EXACT",
        ]:
            _add(checks, check_id, False, "receipt unavailable")

    if isinstance(evidence, dict):
        evidence_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S01-STAGE-REVIEW"
            and evidence.get("contract_id") == "STAGE-REVIEW-S01"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S01_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("next") == "S01/GITHUB_STAGE_UPLOAD_READY"
            and evidence.get("release_status") == "NOT_READY"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S01DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", evidence_ok, evidence.get("status"))
    else:
        _add(checks, "S01DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", False, "evidence unavailable")

    if isinstance(rollback, dict):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S01-STAGE-REVIEW-ROLLBACK"
            and rollback.get("contract_id") == "STAGE-REVIEW-S01"
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
        )
        _add(checks, "S01DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S01DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", False, "rollback unavailable")

    try:
        rows = _load_index(root)
        matching = [row for row in rows if row.get("id") == "INDEX-S01-STAGE-REVIEW"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == PINNED_STAGE_EVIDENCE_SHA256
            and matching[0].get("actual_artifact") == STAGE_EVIDENCE_PATH.as_posix()
            and matching[0].get("next") == "S01/GITHUB_STAGE_UPLOAD_READY"
        )
        _add(checks, "S01DELIVERY-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S01DELIVERY-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_git_history:
        _check_git_history(root.parent, checks)
    else:
        _add(checks, "S01DELIVERY-TEST-ONLY-GIT-PROFILE", True, "Git history skipped only for isolated mutation clone")

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "stage_id": "S01",
        "product_version": VERSION,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S01_DELIVERED_S02_MAY_START" if not failed else "S02_START_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S02/P01_READY_NOT_STARTED" if not failed else "S01/DELIVERY_EVIDENCE_REMEDIATION_REQUIRED",
    }


def cli_verify_stage1_delivery(root: Path) -> Dict[str, Any]:
    result = verify_stage1_delivery(root, verify_git_history=True)
    return {
        "contract_id": CONTRACT_ID,
        "status": result["status"],
        "evidence_path": RECEIPT_PATH.as_posix(),
        "evidence_sha256": result.get("hashes", {}).get(RECEIPT_PATH.as_posix(), ""),
        "next": result["next"],
        "verification": result,
    }
