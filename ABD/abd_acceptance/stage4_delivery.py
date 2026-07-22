from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "STAGE-DELIVERY-S04"
VERSION = "0.0.0.1"
RECEIPT_PATH = Path("machine/evidence/S04/STAGE_REVIEW/github_delivery_receipt.json")
STAGE_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-STAGE-REVIEW.json")
STAGE_ROLLBACK_PATH = Path("machine/evidence/EVD-S04-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

PINNED_RECEIPT_SHA256 = "d9b83cc0ebc1464c9f52c87e49bed32887323297118c595be1f97a475b78ed36"
PINNED_STAGE_EVIDENCE_SHA256 = "1dc45c997a4544370e724b9828459ac8ba8e0d3990aec9b380528818a15bf708"
PINNED_STAGE_ROLLBACK_SHA256 = "0cb65c9b4c37a0d20cd98d732bf4d8bc4aab8739080f3604de587ce2a787be79"

BASE_COMMIT = "711f092d304cce117b7268755476db6ba382caa1"
BRANCH_HEAD_COMMIT = "b1584c6938e3273fdde3ca6bffd6849f3737415e"
MERGE_COMMIT = "33c9ca3d60128243d9d853059c6d546d12453a4a"
DELIVERED_COMMITS = [
    "4cd838a3fa27ee29857afd4a2bce632252d2c0b8",
    "52e85f6626cde511c9b9679e126cfb536d612ddd",
    "f9bc7b2c4a1bf06caafca977730fc7c0085b5a4b",
    "8711b419369886b907bd69633c4122489c65b748",
    "eead856a87fc15a7b25d08723e021111265c85e6",
    "2630ec141e440d72288d68d42ec397debd245e5c",
    "7b314be320356beadbf4adc5a7e660c8a3e468af",
    "258e335ed01a40e6b6ae197bbb8b92398c73b64b",
    BRANCH_HEAD_COMMIT,
]

EXPECTED_CHECKS = [
    {
        "workflow": "ABD continuous validation",
        "run_id": 29930378507,
        "job_id": 88958226053,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29930378507",
        "completed_at": "2026-07-22T14:54:53Z",
    },
    {
        "workflow": "Dual-Plane Governance",
        "run_id": 29930378441,
        "job_id": 88958225925,
        "event": "push",
        "head_commit": MERGE_COMMIT,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/LinzeColin/MetaDatabase/actions/runs/29930378441",
        "completed_at": "2026-07-22T14:49:02Z",
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
        "S04DELIVERY-GIT-MERGE-PARENTS",
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
    _add(checks, "S04DELIVERY-GIT-ANCESTRY", all(ancestry.values()), ancestry)


def verify_stage4_delivery(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    receipt = _safe_load(root / RECEIPT_PATH, checks, "S04DELIVERY-RECEIPT-STRICT-JSON")
    evidence = _safe_load(root / STAGE_EVIDENCE_PATH, checks, "S04DELIVERY-STAGE-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / STAGE_ROLLBACK_PATH, checks, "S04DELIVERY-STAGE-ROLLBACK-STRICT-JSON")

    hashes: Dict[str, str] = {}
    for relative, expected, check_id in [
        (RECEIPT_PATH, PINNED_RECEIPT_SHA256, "S04DELIVERY-RECEIPT-PINNED-HASH"),
        (STAGE_EVIDENCE_PATH, PINNED_STAGE_EVIDENCE_SHA256, "S04DELIVERY-STAGE-EVIDENCE-PINNED-HASH"),
        (STAGE_ROLLBACK_PATH, PINNED_STAGE_ROLLBACK_SHA256, "S04DELIVERY-STAGE-ROLLBACK-PINNED-HASH"),
    ]:
        try:
            actual = sha256_file(root / relative)
            hashes[relative.as_posix()] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    if isinstance(receipt, Mapping):
        expected_pr = {
            "number": 79,
            "state": "MERGED",
            "url": "https://github.com/LinzeColin/MetaDatabase/pull/79",
            "base_commit": BASE_COMMIT,
            "head_commit": BRANCH_HEAD_COMMIT,
            "merge_commit": MERGE_COMMIT,
            "merged_at": "2026-07-22T14:48:39Z",
        }
        shape_ok = (
            receipt.get("schema_version") == "1.0.0"
            and receipt.get("receipt_id") == "DELIVERY-S04-GITHUB-2026-07-23"
            and receipt.get("repository") == "LinzeColin/MetaDatabase"
            and receipt.get("repository_visibility_at_delivery") == "PUBLIC"
            and receipt.get("stage_id") == "S04"
            and receipt.get("product_version") == VERSION
            and receipt.get("observed_at") == "2026-07-22T15:02:53Z"
            and receipt.get("verification_mode") == "CAPTURED_GITHUB_API_FACTS_PLUS_OFFLINE_GIT_ANCESTRY"
            and receipt.get("delivery_status") == "VERIFIED_MERGED_AND_MAIN_CI_PASS"
            and receipt.get("next") == "S05/P01_READY_NOT_STARTED"
        )
        _add(checks, "S04DELIVERY-RECEIPT-SHAPE", shape_ok, receipt.get("receipt_id"))
        _add(checks, "S04DELIVERY-PR-IMMUTABLE-FACTS", receipt.get("pull_request") == expected_pr, receipt.get("pull_request"))
        _add(checks, "S04DELIVERY-COMMIT-SET-EXACT", receipt.get("delivered_commits") == DELIVERED_COMMITS, receipt.get("delivered_commits"))
        _add(
            checks,
            "S04DELIVERY-MAIN-CHECKS-EXACT",
            receipt.get("main_checks") == EXPECTED_CHECKS and receipt.get("all_required_main_checks_passed") is True,
            receipt.get("main_checks"),
        )
        expected_binding = {
            "path": STAGE_EVIDENCE_PATH.as_posix(),
            "sha256": PINNED_STAGE_EVIDENCE_SHA256,
            "rollback_path": STAGE_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": PINNED_STAGE_ROLLBACK_SHA256,
        }
        _add(checks, "S04DELIVERY-STAGE-EVIDENCE-BINDING", receipt.get("stage_review_evidence") == expected_binding, receipt.get("stage_review_evidence"))
        cost = receipt.get("delivery_cost_gate", {})
        cost_ok = (
            cost.get("status") == "PASS"
            and cost.get("incremental_cash_spent_aud") == "0.00"
            and cost.get("runner_classes") == ["ubuntu-latest"]
            and cost.get("chargeable_features_observed") == []
            and cost.get("billing_basis_url") == "https://docs.github.com/en/billing/concepts/product-billing/github-actions"
        )
        _add(checks, "S04DELIVERY-ZERO-CASH-DELIVERY-GATE", cost_ok, cost)
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
        _add(checks, "S04DELIVERY-EXTERNAL-EFFECTS-EXACT", effects_ok, effects)
    else:
        for check_id in [
            "S04DELIVERY-RECEIPT-SHAPE",
            "S04DELIVERY-PR-IMMUTABLE-FACTS",
            "S04DELIVERY-COMMIT-SET-EXACT",
            "S04DELIVERY-MAIN-CHECKS-EXACT",
            "S04DELIVERY-STAGE-EVIDENCE-BINDING",
            "S04DELIVERY-ZERO-CASH-DELIVERY-GATE",
            "S04DELIVERY-EXTERNAL-EFFECTS-EXACT",
        ]:
            _add(checks, check_id, False, "receipt unavailable")

    evidence_ok = (
        isinstance(evidence, Mapping)
        and evidence.get("schema_version") == "1.0.0"
        and evidence.get("evidence_id") == "EVD-S04-STAGE-REVIEW"
        and evidence.get("contract_id") == "STAGE-REVIEW-S04"
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "S04_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S04/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "NOT_READY_S05_TO_S19_AND_TARGET_RUNTIME_ACTIVATION_REQUIRED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and _decision_hash_matches(evidence)
    )
    _add(checks, "S04DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY", evidence_ok, evidence.get("status") if isinstance(evidence, Mapping) else "unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S04-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == "STAGE-REVIEW-S04"
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and rollback.get("target_host_accessed") is False
        and rollback.get("docker_or_systemd_invoked") is False
    )
    _add(checks, "S04DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")

    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-S04-STAGE-REVIEW"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == PINNED_STAGE_EVIDENCE_SHA256
            and matching[0].get("actual_artifact") == STAGE_EVIDENCE_PATH.as_posix()
            and matching[0].get("next") == "S04/GITHUB_STAGE_UPLOAD_READY"
        )
        _add(checks, "S04DELIVERY-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S04DELIVERY-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_git_history:
        _check_git_history(root.parent, checks)
    else:
        _add(checks, "S04DELIVERY-TEST-ONLY-GIT-PROFILE", True, "Git history skipped only for isolated mutation clone")

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "stage_id": "S04",
        "product_version": VERSION,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_DELIVERED_S05_MAY_START" if not failed else "S05_START_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S05/P01_READY_NOT_STARTED" if not failed else "S04/DELIVERY_EVIDENCE_REMEDIATION_REQUIRED",
    }


def cli_verify_stage4_delivery(root: Path) -> Dict[str, Any]:
    result = verify_stage4_delivery(root, verify_git_history=True)
    return {
        "contract_id": CONTRACT_ID,
        "status": result["status"],
        "evidence_path": RECEIPT_PATH.as_posix(),
        "evidence_sha256": result.get("hashes", {}).get(RECEIPT_PATH.as_posix(), ""),
        "next": result["next"],
        "verification": result,
    }
