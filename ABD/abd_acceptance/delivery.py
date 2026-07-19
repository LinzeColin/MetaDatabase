from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "STAGE-DELIVERY-S00"
VERSION = "0.0.0.1"
RECEIPT_PATH = Path("machine/evidence/S00/STAGE_REVIEW/github_delivery_receipt.json")
STAGE_EVIDENCE_PATH = Path("machine/evidence/EVD-S00-STAGE-REVIEW.json")
STAGE_ROLLBACK_PATH = Path("machine/evidence/EVD-S00-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

PINNED_RECEIPT_SHA256 = "cf6832b72b6f82dfe8d8e5f98aeb8df7c5f86cb75175e8997cb7a2f21c13109c"
PINNED_STAGE_EVIDENCE_SHA256 = "48966ee6a98ad93224f11eb99890448cad6105840141dc4016520a932a857e0d"
PINNED_STAGE_ROLLBACK_SHA256 = "e418fe62d0084255a26b12b9e2f42bd49cbeb5e19e86879e61d6023c3f752ed8"

BASE_COMMIT = "b57c8dbae8913b2c4d53f17c5e2743afb34bd593"
BRANCH_HEAD_COMMIT = "92e13c024c194e85497cc75aa4cc7557fa865401"
MERGE_COMMIT = "277f9c6da43b62e8a89d9b8d4b42a2a935b755ef"
DELIVERED_COMMITS = [
    "a5e3f3539f49cb733b3c017e70dc12423470139a",
    "aee20d6cd5ad1ee9c974b80d38a012c5f39a5c56",
    "0f6bea1e1632f8983513c9bc6793d786d06bdbaa",
    "922b5d1ec3fe70924c3253c2aaf9f5035d68555b",
    "c5cf634460a663a515168749e3e43cf17d648bec",
]

EXPECTED_CHECKS = [
    {
        "workflow": "ABD Stage 0 validation",
        "run_id": 29684295907,
        "job_id": 88185790409,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29684295907",
        "completed_at": "2026-07-19T10:59:23Z",
    },
    {
        "workflow": "Dual-Plane Governance",
        "run_id": 29684295894,
        "job_id": 88185790238,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29684295894",
        "completed_at": "2026-07-19T10:58:42Z",
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
        "DELIVERY-GIT-MERGE-PARENTS",
        parents.returncode == 0 and parents.stdout.decode("utf-8").strip() == expected_parents,
        parents.stdout.decode("utf-8", errors="replace").strip()
        if parents.returncode == 0
        else parents.stderr.decode("utf-8", errors="replace").strip(),
    )

    ancestry = {}
    for commit in DELIVERED_COMMITS:
        result = _git(repo_root, "merge-base", "--is-ancestor", commit, MERGE_COMMIT)
        ancestry[commit] = result.returncode == 0
    head_result = _git(repo_root, "merge-base", "--is-ancestor", MERGE_COMMIT, "HEAD")
    ancestry["merge_is_ancestor_of_HEAD"] = head_result.returncode == 0
    _add(checks, "DELIVERY-GIT-ANCESTRY", all(ancestry.values()), ancestry)


def verify_stage0_delivery(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    receipt = _safe_load(root / RECEIPT_PATH, checks, "DELIVERY-RECEIPT-STRICT-JSON")
    evidence = _safe_load(root / STAGE_EVIDENCE_PATH, checks, "DELIVERY-STAGE-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / STAGE_ROLLBACK_PATH, checks, "DELIVERY-STAGE-ROLLBACK-STRICT-JSON")

    hashes: Dict[str, str] = {}
    for relative, expected, check_id in [
        (RECEIPT_PATH, PINNED_RECEIPT_SHA256, "DELIVERY-RECEIPT-PINNED-HASH"),
        (STAGE_EVIDENCE_PATH, PINNED_STAGE_EVIDENCE_SHA256, "DELIVERY-STAGE-EVIDENCE-PINNED-HASH"),
        (STAGE_ROLLBACK_PATH, PINNED_STAGE_ROLLBACK_SHA256, "DELIVERY-STAGE-ROLLBACK-PINNED-HASH"),
    ]:
        try:
            actual = sha256_file(root / relative)
            hashes[relative.as_posix()] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    if isinstance(receipt, dict):
        pull_request = receipt.get("pull_request")
        receipt_shape_ok = (
            receipt.get("schema_version") == "1.0.0"
            and receipt.get("receipt_id") == "DELIVERY-S00-GITHUB-2026-07-19"
            and receipt.get("repository") == "LinzeColin/MetaDatabase"
            and receipt.get("stage_id") == "S00"
            and receipt.get("product_version") == VERSION
            and receipt.get("verification_mode") == "CAPTURED_GITHUB_API_FACTS_PLUS_OFFLINE_GIT_ANCESTRY"
            and receipt.get("delivery_status") == "VERIFIED_MERGED_AND_MAIN_CI_PASS"
            and receipt.get("next") == "S01/P01_READY_NOT_STARTED"
        )
        _add(checks, "DELIVERY-RECEIPT-SHAPE", receipt_shape_ok, receipt.get("receipt_id"))
        expected_pr = {
            "number": 58,
            "state": "MERGED",
            "url": "https://github.com/LinzeColin/MetaDatabase/pull/58",
            "base_commit": BASE_COMMIT,
            "head_commit": BRANCH_HEAD_COMMIT,
            "merge_commit": MERGE_COMMIT,
            "merged_at": "2026-07-19T10:58:24Z",
        }
        _add(checks, "DELIVERY-PR-IMMUTABLE-FACTS", pull_request == expected_pr, pull_request)
        _add(
            checks,
            "DELIVERY-COMMIT-SET-EXACT",
            receipt.get("delivered_commits") == DELIVERED_COMMITS,
            receipt.get("delivered_commits"),
        )
        _add(
            checks,
            "DELIVERY-MAIN-CHECKS-EXACT",
            receipt.get("main_checks") == EXPECTED_CHECKS and receipt.get("all_required_main_checks_passed") is True,
            receipt.get("main_checks"),
        )
        expected_evidence = {
            "path": STAGE_EVIDENCE_PATH.as_posix(),
            "sha256": PINNED_STAGE_EVIDENCE_SHA256,
            "rollback_path": STAGE_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": PINNED_STAGE_ROLLBACK_SHA256,
        }
        _add(
            checks,
            "DELIVERY-STAGE-EVIDENCE-BINDING",
            receipt.get("stage_review_evidence") == expected_evidence,
            receipt.get("stage_review_evidence"),
        )
        boundary_ok = (
            receipt.get("external_account_or_provider_accessed") is False
            and receipt.get("secret_material_captured") is False
            and receipt.get("incremental_cash_spent_aud") == "0.00"
            and receipt.get("production_deployment_claimed") is False
            and receipt.get("return_guaranteed") is False
        )
        _add(checks, "DELIVERY-NO-EXTERNAL-EFFECT-OR-COST-CLAIM", boundary_ok, "bounded")
    else:
        for check_id in [
            "DELIVERY-RECEIPT-SHAPE",
            "DELIVERY-PR-IMMUTABLE-FACTS",
            "DELIVERY-COMMIT-SET-EXACT",
            "DELIVERY-MAIN-CHECKS-EXACT",
            "DELIVERY-STAGE-EVIDENCE-BINDING",
            "DELIVERY-NO-EXTERNAL-EFFECT-OR-COST-CLAIM",
        ]:
            _add(checks, check_id, False, "receipt unavailable")

    if isinstance(evidence, dict):
        evidence_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S00-STAGE-REVIEW"
            and evidence.get("contract_id") == "STAGE-REVIEW-S00"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S00_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("next") == "S00/GITHUB_STAGE_UPLOAD_READY"
            and evidence.get("release_status") == "NOT_READY"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", evidence_ok, evidence.get("status"))
    else:
        _add(checks, "DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", False, "evidence unavailable")

    if isinstance(rollback, dict):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S00-STAGE-REVIEW-ROLLBACK"
            and rollback.get("contract_id") == "STAGE-REVIEW-S00"
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
        )
        _add(checks, "DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", False, "rollback unavailable")

    try:
        rows = _load_index(root)
        matching = [row for row in rows if row.get("id") == "INDEX-S00-STAGE-REVIEW"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == PINNED_STAGE_EVIDENCE_SHA256
            and matching[0].get("actual_artifact") == STAGE_EVIDENCE_PATH.as_posix()
        )
        _add(checks, "DELIVERY-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "DELIVERY-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_git_history:
        _check_git_history(root.parent, checks)

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "stage_id": "S00",
        "product_version": VERSION,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S00_DELIVERED_S01_MAY_START" if not failed else "S01_START_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S01/P01_READY_NOT_STARTED" if not failed else "S00/DELIVERY_EVIDENCE_REMEDIATION_REQUIRED",
    }


def cli_verify_stage0_delivery(root: Path) -> Dict[str, Any]:
    result = verify_stage0_delivery(root, verify_git_history=True)
    return {
        "contract_id": CONTRACT_ID,
        "status": result["status"],
        "evidence_path": RECEIPT_PATH.as_posix(),
        "evidence_sha256": result.get("hashes", {}).get(RECEIPT_PATH.as_posix(), ""),
        "next": result["next"],
        "verification": result,
    }
