from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "STAGE-DELIVERY-S03"
VERSION = "0.0.0.1"
RECEIPT_PATH = Path("machine/evidence/S03/STAGE_REVIEW/github_delivery_receipt.json")
STAGE_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-STAGE-REVIEW.json")
STAGE_ROLLBACK_PATH = Path("machine/evidence/EVD-S03-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

PINNED_RECEIPT_SHA256 = "617b7e18f615b46a3217569b271a553434673f26a494c846c3aef032c800f5c0"
PINNED_STAGE_EVIDENCE_SHA256 = "f636457a578723a5c98799bf4450754d331291fa29444c453630c5d0b81aea21"
PINNED_STAGE_ROLLBACK_SHA256 = "41111279b9a900947cd6b09df182028909887fad145d19d3719f638749422451"

BASE_COMMIT = "e4a8016786c9140b1900db9d0b6f02b2b0a1786e"
BRANCH_HEAD_COMMIT = "4e5c90b554c505517312407f20b8c12c463e37af"
MERGE_COMMIT = "d3536089a7ba366b40ce32e5df0dbbdf592b528a"
DELIVERED_COMMITS = [
    "436e8e7168a383e0ebcac150bef8dd9f79c32c24",
    "b21f7a49f1d2f17c772cc6c1bd55e1add410cda2",
    "d600affe30f33c5d128901f617a6dd7b87b41bdb",
    "86f268310e24eeab10639c6c36cbfcec544f9c74",
    "9baacbc381eba75cf6c747fc5c0478ab4bdb05db",
    "ef74f1f49994b4249844485bf3e61eb8c65a06b2",
    "1245015b34dbf8d8aa92bdaaadd0ed44040ed36e",
    "d7547ccd445a32a3cfca1f310cbb7a456ffd4005",
    "4168321dee17540bdba5763271694f78b33e3c42",
    BRANCH_HEAD_COMMIT,
]

EXPECTED_CHECKS = [
    {
        "workflow": "ABD continuous validation",
        "run_id": 29719343079,
        "job_id": 88278837548,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29719343079",
        "completed_at": "2026-07-20T05:34:57Z",
    },
    {
        "workflow": "Dual-Plane Governance",
        "run_id": 29719343054,
        "job_id": 88278837315,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29719343054",
        "completed_at": "2026-07-20T05:32:04Z",
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
        "S03DELIVERY-GIT-MERGE-PARENTS",
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
    _add(checks, "S03DELIVERY-GIT-ANCESTRY", all(ancestry.values()), ancestry)


def verify_stage3_delivery(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    receipt = _safe_load(root / RECEIPT_PATH, checks, "S03DELIVERY-RECEIPT-STRICT-JSON")
    evidence = _safe_load(root / STAGE_EVIDENCE_PATH, checks, "S03DELIVERY-STAGE-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / STAGE_ROLLBACK_PATH, checks, "S03DELIVERY-STAGE-ROLLBACK-STRICT-JSON")

    hashes: Dict[str, str] = {}
    for relative, expected, check_id in [
        (RECEIPT_PATH, PINNED_RECEIPT_SHA256, "S03DELIVERY-RECEIPT-PINNED-HASH"),
        (STAGE_EVIDENCE_PATH, PINNED_STAGE_EVIDENCE_SHA256, "S03DELIVERY-STAGE-EVIDENCE-PINNED-HASH"),
        (STAGE_ROLLBACK_PATH, PINNED_STAGE_ROLLBACK_SHA256, "S03DELIVERY-STAGE-ROLLBACK-PINNED-HASH"),
    ]:
        try:
            actual = sha256_file(root / relative)
            hashes[relative.as_posix()] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    if isinstance(receipt, Mapping):
        expected_pr = {
            "number": 69,
            "state": "MERGED",
            "url": "https://github.com/LinzeColin/MetaDatabase/pull/69",
            "base_commit": BASE_COMMIT,
            "head_commit": BRANCH_HEAD_COMMIT,
            "merge_commit": MERGE_COMMIT,
            "merged_at": "2026-07-20T05:31:41Z",
        }
        shape_ok = (
            receipt.get("schema_version") == "1.0.0"
            and receipt.get("receipt_id") == "DELIVERY-S03-GITHUB-2026-07-22"
            and receipt.get("repository") == "LinzeColin/MetaDatabase"
            and receipt.get("repository_visibility_at_delivery") == "PUBLIC"
            and receipt.get("stage_id") == "S03"
            and receipt.get("product_version") == VERSION
            and receipt.get("observed_at") == "2026-07-22T05:18:43Z"
            and receipt.get("verification_mode") == "CAPTURED_GITHUB_API_FACTS_PLUS_OFFLINE_GIT_ANCESTRY"
            and receipt.get("delivery_status") == "VERIFIED_MERGED_AND_MAIN_CI_PASS"
            and receipt.get("next") == "S04/P01_READY_NOT_STARTED"
        )
        _add(checks, "S03DELIVERY-RECEIPT-SHAPE", shape_ok, receipt.get("receipt_id"))
        _add(checks, "S03DELIVERY-PR-IMMUTABLE-FACTS", receipt.get("pull_request") == expected_pr, receipt.get("pull_request"))
        _add(checks, "S03DELIVERY-COMMIT-SET-EXACT", receipt.get("delivered_commits") == DELIVERED_COMMITS, receipt.get("delivered_commits"))
        _add(
            checks,
            "S03DELIVERY-MAIN-CHECKS-EXACT",
            receipt.get("main_checks") == EXPECTED_CHECKS and receipt.get("all_required_main_checks_passed") is True,
            receipt.get("main_checks"),
        )
        expected_binding = {
            "path": STAGE_EVIDENCE_PATH.as_posix(),
            "sha256": PINNED_STAGE_EVIDENCE_SHA256,
            "rollback_path": STAGE_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": PINNED_STAGE_ROLLBACK_SHA256,
        }
        _add(checks, "S03DELIVERY-STAGE-EVIDENCE-BINDING", receipt.get("stage_review_evidence") == expected_binding, receipt.get("stage_review_evidence"))
        cost = receipt.get("delivery_cost_gate", {})
        cost_ok = (
            cost.get("status") == "PASS"
            and cost.get("incremental_cash_spent_aud") == "0.00"
            and cost.get("runner_classes") == ["ubuntu-latest"]
            and cost.get("chargeable_features_observed") == []
            and cost.get("billing_basis_url") == "https://docs.github.com/en/actions/concepts/billing-and-usage"
        )
        _add(checks, "S03DELIVERY-ZERO-CASH-DELIVERY-GATE", cost_ok, cost)
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
        _add(checks, "S03DELIVERY-EXTERNAL-EFFECTS-EXACT", effects_ok, effects)
    else:
        for check_id in [
            "S03DELIVERY-RECEIPT-SHAPE",
            "S03DELIVERY-PR-IMMUTABLE-FACTS",
            "S03DELIVERY-COMMIT-SET-EXACT",
            "S03DELIVERY-MAIN-CHECKS-EXACT",
            "S03DELIVERY-STAGE-EVIDENCE-BINDING",
            "S03DELIVERY-ZERO-CASH-DELIVERY-GATE",
            "S03DELIVERY-EXTERNAL-EFFECTS-EXACT",
        ]:
            _add(checks, check_id, False, "receipt unavailable")

    evidence_ok = (
        isinstance(evidence, Mapping)
        and evidence.get("schema_version") == "1.0.0"
        and evidence.get("evidence_id") == "EVD-S03-STAGE-REVIEW"
        and evidence.get("contract_id") == "STAGE-REVIEW-S03"
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "S03_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S03/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "NOT_READY_STAGE_4_TO_19_AND_PRODUCTION_VALIDATION_REQUIRED"
        and _decision_hash_matches(evidence)
    )
    _add(checks, "S03DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", evidence_ok, evidence.get("status") if isinstance(evidence, Mapping) else "unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S03-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == "STAGE-REVIEW-S03"
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
    )
    _add(checks, "S03DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")

    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-S03-STAGE-REVIEW"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == PINNED_STAGE_EVIDENCE_SHA256
            and matching[0].get("actual_artifact") == STAGE_EVIDENCE_PATH.as_posix()
            and matching[0].get("next") == "S03/GITHUB_STAGE_UPLOAD_READY"
        )
        _add(checks, "S03DELIVERY-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S03DELIVERY-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_git_history:
        _check_git_history(root.parent, checks)
    else:
        _add(checks, "S03DELIVERY-TEST-ONLY-GIT-PROFILE", True, "Git history skipped only for isolated mutation clone")

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "stage_id": "S03",
        "product_version": VERSION,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S03_DELIVERED_S04_MAY_START" if not failed else "S04_START_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S04/P01_READY_NOT_STARTED" if not failed else "S03/DELIVERY_EVIDENCE_REMEDIATION_REQUIRED",
    }


def cli_verify_stage3_delivery(root: Path) -> Dict[str, Any]:
    result = verify_stage3_delivery(root, verify_git_history=True)
    return {
        "contract_id": CONTRACT_ID,
        "status": result["status"],
        "evidence_path": RECEIPT_PATH.as_posix(),
        "evidence_sha256": result.get("hashes", {}).get(RECEIPT_PATH.as_posix(), ""),
        "next": result["next"],
        "verification": result,
    }
