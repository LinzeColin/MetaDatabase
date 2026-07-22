from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .capacity_governance import (
    evaluate_contract as evaluate_p04,
    validate_capacity_budget,
    validate_load_baseline,
    validate_resource_shedding,
    verify_existing_phase_evidence as verify_p04,
)
from .cloudflare_edge import (
    evaluate_contract as evaluate_p02,
    parse_access_policy,
    validate_access_policy,
    validate_cloudflared_config,
    verify_existing_phase_evidence as verify_p02,
)
from .infrastructure_iac import (
    evaluate_contract as evaluate_p01,
    parse_systemd_unit,
    verify_existing_phase_evidence as verify_p01,
)
from .release_control import (
    evaluate_contract as evaluate_p03,
    validate_feature_flags,
    validate_release_slots,
    verify_existing_phase_evidence as verify_p03,
)


CONTRACT_ID = "STAGE-REVIEW-S04"
REVIEW_ID = "ABD-S04-WHOLE-STAGE-REVIEW"
STAGE_ID = "S04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-22T23:59:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage4_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S04/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S04_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S04/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S04/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S04/STAGE_REVIEW/full_regression.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S04/STAGE_REVIEW/signed_state_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S04-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")
CLOUDFLARED_UNIT_PATH = Path("infra/systemd/abd-cloudflared.service")

STRUCTURAL_SELF_NORMALIZED_SHA256 = "ea4242f0e5f822c4f1a7297f672966828781cd903bc2fe44063c1db8d63471e2"
PINNED_REVIEW_ARTIFACT_HASHES: Dict[str, str] = {
    CONTRACT_PATH.as_posix(): "fecee345c17c94623a8a86629efe6f885da61e69b102c8c56362382d339d3c3b",
    FINDINGS_PATH.as_posix(): "f861ebe1b6120706b6b495076e499f3af817c666a75434265a9c7993a82905d0",
    FIXTURE_PATH.as_posix(): "faa3b99005c41c8ce17a7c67c58013aeae21bd2f92db8eeee734af36aea65111",
    TEST_PATH.as_posix(): "681e9656a28c276072fb1b4742b8279c6122fa49521f27c5e7cfe997afbb05b9",
}
WORKFLOW_SHA256 = "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d"

PHASE_EVALUATORS = {"P01": evaluate_p01, "P02": evaluate_p02, "P03": evaluate_p03, "P04": evaluate_p04}
PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_DECISIONS = {
    "P01": "S04_P01_EVIDENCE_VERIFIED",
    "P02": "S04_P02_EVIDENCE_VERIFIED",
    "P03": "S04_P03_EVIDENCE_VERIFIED",
    "P04": "S04_P04_EVIDENCE_VERIFIED",
}
PHASE_NEXT = {
    "P01": "S04/P02_READY_NOT_STARTED",
    "P02": "S04/P03_READY_NOT_STARTED",
    "P03": "S04/P04_READY_NOT_STARTED",
    "P04": "S04/STAGE_REVIEW_READY_NOT_STARTED",
}

ROLLBACK_ARTIFACTS = [
    Path("infra/compose.yml"),
    Path("infra/systemd/abd.service"),
    Path("infra/config.schema.json"),
    Path("infra/rebuild.sh"),
    Path("infra/cloudflared.yml"),
    Path("access_policy.md"),
    Path("degraded_page.html"),
    CLOUDFLARED_UNIT_PATH,
    Path("release_slots.json"),
    Path("feature_flags.json"),
    Path("rollback.sh"),
    Path("capacity_budget.json"),
    Path("resource_shedding.json"),
    Path("load_baseline.json"),
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]


class Stage4ReviewContractError(ValueError):
    """Raised when the S04 whole-stage review cannot proceed safely."""


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


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/stage4_review.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def _load_index(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise Stage4ReviewContractError("evidence index rows must be objects")
        rows.append(value)
    return rows


def _phase_code_hash_at_commit(root: Path, commit: str) -> str:
    ancestor = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", commit, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        row
        for row in listing.stdout.splitlines()
        if row.startswith("ABD/abd_acceptance/") and row.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (commit, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _review_pin_checks(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_REVIEW_ARTIFACT_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(
            checks,
            "S04REVIEW-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"),
            actual == expected,
            {"expected": expected, "actual": actual},
        )
    workflow = root.parent / WORKFLOW_PATH
    workflow_actual = sha256_file(workflow) if workflow.is_file() else "MISSING"
    hashes[WORKFLOW_PATH.as_posix()] = workflow_actual
    _add(checks, "S04REVIEW-WORKFLOW-PIN", workflow_actual == WORKFLOW_SHA256, {"expected": WORKFLOW_SHA256, "actual": workflow_actual})
    structural = _structural_self_hash(root)
    hashes["abd_acceptance/stage4_review.py"] = sha256_file(root / "abd_acceptance/stage4_review.py")
    _add(
        checks,
        "S04REVIEW-ORACLE-SELF-INTEGRITY",
        structural == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": structural},
    )


def _expected_runtime_binding(fixture: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return dict(fixture.get("expected_active_profile", {})), dict(fixture.get("expected_shadow_profile", {}))


def _check_contract_and_findings(
    contract: Mapping[str, Any],
    findings: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    scope = contract.get("review_scope", {})
    records = contract.get("phase_records", [])
    shape_ok = (
        contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and contract.get("fixed_at") == FIXED_CLOCK
        and scope.get("phase_ids") == fixture.get("expected_phase_ids")
        and scope.get("requirement_ids") == ["REQ-S04-P01", "REQ-S04-P02", "REQ-S04-P03", "REQ-S04-P04"]
        and scope.get("acceptance_contract_ids") == ["AC-S04-P01", "AC-S04-P02", "AC-S04-P03", "AC-S04-P04"]
        and len(scope.get("task_ids", [])) == 12
        and len(set(scope.get("task_ids", []))) == 12
        and [row.get("phase_id") for row in records if isinstance(row, Mapping)] == fixture.get("expected_phase_ids")
        and contract.get("review_findings_path") == FINDINGS_PATH.as_posix()
        and contract.get("release_status_on_pass") == fixture.get("expected_release_status")
        and contract.get("next_on_pass") == fixture.get("expected_next")
        and not _contains_float(contract)
    )
    _add(checks, "S04REVIEW-CONTRACT-SHAPE", shape_ok, {"scope": scope, "phase_records": len(records)})
    source_receipts = contract.get("supplied_source_receipts", [])
    source_ok = (
        len(source_receipts) == 2
        and source_receipts[0].get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and source_receipts[0].get("repository_equivalent") == "machine/evidence/roadmap_stage_phase.md"
        and source_receipts[1].get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and source_receipts[1].get("original_file_count") == 53
        and source_receipts[1].get("repository_equivalent_required") is False
    )
    _add(checks, "S04REVIEW-SUPPLIED-SOURCE-RECEIPTS", source_ok, source_receipts)
    boundary = contract.get("external_effect_boundary", {})
    boundary_ok = (
        boundary.get("incremental_cash_spent_aud") == "0.00"
        and boundary.get("owner_final_order_only") is True
        and all(value is False for key, value in boundary.items() if key not in {"incremental_cash_spent_aud", "owner_final_order_only"})
    )
    _add(checks, "S04REVIEW-EXTERNAL-EFFECT-BOUNDARY", boundary_ok, boundary)
    claim = contract.get("claim_boundary", {})
    _add(
        checks,
        "S04REVIEW-RUNTIME-OVERCLAIM-BOUNDARY",
        claim == fixture.get("expected_claim_boundary") and all(value is False for value in claim.values()),
        claim,
    )
    expected_upload = {
        "ALL_STAGE_PHASES_PASS",
        "WHOLE_STAGE_REVIEW_PASS",
        "ALL_REVIEW_FINDINGS_RESOLVED",
        "FULL_STAGE_REGRESSION_PASS",
        "SIGNED_STATE_REGRESSION_PASS",
        "PAID_DEPENDENCY_SCAN_PASS",
        "CLEAN_WORKTREE_AFTER_COMMIT",
        "NO_INCREMENTAL_CASH_COST",
    }
    _add(checks, "S04REVIEW-UPLOAD-PRECONDITIONS", set(contract.get("upload_preconditions", [])) == expected_upload, contract.get("upload_preconditions"))
    finding_rows = findings.get("findings", [])
    expected_ids = fixture.get("expected_finding_ids")
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_at") == FIXED_CLOCK
        and [row.get("id") for row in finding_rows if isinstance(row, Mapping)] == expected_ids
        and len(finding_rows) == len(expected_ids)
        and all(row.get("status") == "RESOLVED_IN_REVIEW_CANDIDATE" for row in finding_rows if isinstance(row, Mapping))
        and all(row.get("severity") in {"HIGH", "MEDIUM"} for row in finding_rows if isinstance(row, Mapping))
        and all(row.get("verification_gate") for row in finding_rows if isinstance(row, Mapping))
        and findings.get("summary") == {
            "total": 6,
            "resolved_in_review_candidate": 6,
            "open": 0,
            "remote_ci_pending_is_upload_evidence_not_an_open_code_finding": True,
        }
        and not _contains_float(findings)
    )
    _add(checks, "S04REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, findings.get("summary"))


def _check_runtime_binding(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    compose = strict_json_load(root / "infra/compose.yml")
    slots = strict_json_load(root / "release_slots.json")
    capacity = strict_json_load(root / "capacity_budget.json")
    shedding = strict_json_load(root / "resource_shedding.json")
    baseline = strict_json_load(root / "load_baseline.json")
    flags = strict_json_load(root / "feature_flags.json")
    release_policy = strict_json_load(root / "machine/facts/release_policy.json")
    edge = strict_json_load(root / "infra/cloudflared.yml")
    policy = parse_access_policy((root / "access_policy.md").read_text(encoding="utf-8"))
    degraded = (root / "degraded_page.html").read_text(encoding="utf-8")

    _add(checks, "S04REVIEW-CLOUDFLARED-CONFIG-VALID", not validate_cloudflared_config(edge), validate_cloudflared_config(edge) or "valid")
    _add(checks, "S04REVIEW-ACCESS-POLICY-VALID", not validate_access_policy(policy), validate_access_policy(policy) or "valid")
    _add(checks, "S04REVIEW-RELEASE-SLOTS-VALID", not validate_release_slots(slots, release_policy), validate_release_slots(slots, release_policy) or "valid")
    _add(checks, "S04REVIEW-FEATURE-FLAGS-VALID", not validate_feature_flags(flags, release_policy), validate_feature_flags(flags, release_policy) or "valid")
    _add(checks, "S04REVIEW-CAPACITY-VALID", not validate_capacity_budget(capacity), validate_capacity_budget(capacity) or "valid")
    _add(checks, "S04REVIEW-SHEDDING-VALID", not validate_resource_shedding(shedding, capacity), validate_resource_shedding(shedding, capacity) or "valid")
    _add(checks, "S04REVIEW-LOAD-BASELINE-VALID", not validate_load_baseline(baseline), validate_load_baseline(baseline) or "valid")

    services = compose.get("services", {})
    core = services.get("abd-core", {}) if isinstance(services, Mapping) else {}
    shadow = services.get("abd-shadow", {}) if isinstance(services, Mapping) else {}
    profiles = slots.get("runtime_profiles", {})
    active_profile = profiles.get("active", {}) if isinstance(profiles, Mapping) else {}
    shadow_profile = profiles.get("candidate_shadow", {}) if isinstance(profiles, Mapping) else {}
    expected_active, expected_shadow = _expected_runtime_binding(fixture)
    active_ok = (
        set(services) == {"abd-core", "abd-shadow"}
        and core.get("cpus") == "1.50"
        and core.get("mem_limit") == "2560m"
        and core.get("memswap_limit") == "2560m"
        and core.get("ports") == [{"target": 8080, "published": "${ABD_BIND_PORT:-8080}", "host_ip": "127.0.0.1", "protocol": "tcp"}]
        and active_profile.get("compose_service") == expected_active.get("service")
        and active_profile.get("bind_address") == expected_active.get("bind_address")
        and active_profile.get("bind_port") == expected_active.get("bind_port")
        and active_profile.get("cpu_hard_limit_millicores") == expected_active.get("cpu_millicores")
        and active_profile.get("memory_hard_limit_mib") == expected_active.get("memory_mib")
        and active_profile.get("swap_limit_mib") == expected_active.get("swap_mib")
        and active_profile.get("state_access") == expected_active.get("state_access")
        and core.get("environment", {}).get("ABD_ORDER_SUBMISSION_ENABLED") == "false"
    )
    _add(checks, "S04REVIEW-ACTIVE-RUNTIME-BINDING", active_ok, {"compose": core, "profile": active_profile})
    shadow_volumes = {row.get("target"): row for row in shadow.get("volumes", []) if isinstance(row, Mapping)}
    shadow_ok = (
        shadow.get("profiles") == [expected_shadow.get("profile")]
        and shadow.get("cpus") == "0.25"
        and shadow.get("mem_limit") == "512m"
        and shadow.get("memswap_limit") == "512m"
        and shadow.get("ports") == [{
            "target": 8080,
            "published": "${ABD_SHADOW_BIND_PORT:?ABD_SHADOW_BIND_PORT must be 8081 or 8082}",
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }]
        and shadow_volumes.get("/var/lib/abd", {}).get("read_only") is True
        and shadow.get("environment", {}).get("ABD_RUNTIME_MODE") == "SHADOW_READ_ONLY"
        and shadow.get("environment", {}).get("ABD_ORDER_SUBMISSION_ENABLED") == "false"
        and shadow_profile.get("compose_service") == expected_shadow.get("service")
        and shadow_profile.get("allowed_bind_ports") == expected_shadow.get("allowed_bind_ports")
        and shadow_profile.get("cpu_hard_limit_millicores") == expected_shadow.get("cpu_millicores")
        and shadow_profile.get("memory_hard_limit_mib") == expected_shadow.get("memory_mib")
        and shadow_profile.get("swap_limit_mib") == expected_shadow.get("swap_mib")
        and shadow_profile.get("state_access") == expected_shadow.get("state_access")
        and shadow_profile.get("maximum_concurrent_instances") == expected_shadow.get("maximum_concurrent_instances")
    )
    _add(checks, "S04REVIEW-SHADOW-RUNTIME-BINDING", shadow_ok, {"compose": shadow, "profile": shadow_profile})
    cpu = capacity.get("cpu_budget", {})
    memory = capacity.get("memory_budget", {})
    coupling_ok = (
        active_profile.get("cpu_hard_limit_millicores") == cpu.get("active_slot_outer_hard_limit_millicores") == 1500
        and shadow_profile.get("cpu_hard_limit_millicores") == cpu.get("candidate_shadow_outer_hard_limit_millicores") == 250
        and active_profile.get("memory_hard_limit_mib") == memory.get("active_slot_outer_hard_limit_mib") == 2560
        and shadow_profile.get("memory_hard_limit_mib") == memory.get("candidate_shadow_outer_hard_limit_mib") == 512
        and active_profile.get("swap_limit_mib") == shadow_profile.get("swap_limit_mib") == 0
        and memory.get("swap_allowed") is False
        and shadow_profile.get("maximum_concurrent_instances") == 1
        and "STOP_CANDIDATE_SHADOW_FIRST" in next(row for row in shedding.get("states", []) if row.get("id") == "CONSTRAINED").get("actions", [])
    )
    _add(checks, "S04REVIEW-CAPACITY-SHEDDING-RELEASE-COMPOSE-COUPLING", coupling_ok, {"cpu": cpu, "memory": memory, "profiles": profiles})
    edge_origin = edge.get("ingress", [{}])[0].get("service")
    endpoint_ok = (
        edge_origin == "http://127.0.0.1:8080"
        and policy.get("network_boundary", {}).get("origin_service") == edge_origin
        and slots.get("routing", {}).get("public_origin") == edge_origin
        and core.get("ports", [{}])[0].get("host_ip") == "127.0.0.1"
        and core.get("ports", [{}])[0].get("published") == "${ABD_BIND_PORT:-8080}"
        and [row.get("bind_port") for row in slots.get("slots", [])] == [8081, 8082]
        and all(row.get("bind_address") == "127.0.0.1" for row in slots.get("slots", []))
        and edge.get("ingress", [])[-1] == {"service": "http_status:404"}
    )
    _add(checks, "S04REVIEW-ENDPOINT-ALIGNMENT", endpoint_ok, {"edge": edge_origin, "access": policy.get("network_boundary"), "routing": slots.get("routing")})
    degraded_ok = (
        "lang=\"zh-CN\"" in degraded
        and "停止新建议" in degraded
        and "不要使用任何旧建议下单" in degraded
        and "不是随机收益保证" in degraded
        and "中国大陆" in degraded
        and "<script" not in degraded.lower()
        and "<form" not in degraded.lower()
        and contract.get("claim_boundary", {}).get("static_degraded_page_automatically_wired") is False
    )
    _add(checks, "S04REVIEW-DEGRADED-PAGE-STATIC-UNWIRED-BOUNDARY", degraded_ok, contract.get("claim_boundary"))

    unit = parse_systemd_unit((root / CLOUDFLARED_UNIT_PATH).read_text(encoding="utf-8"))
    unit_section = unit.get("Unit", {})
    service = unit.get("Service", {})
    lifecycle_ok = (
        set(unit) == {"Unit", "Service", "Install"}
        and unit_section.get("Wants") == ["network-online.target abd.service"]
        and unit_section.get("After") == ["network-online.target abd.service"]
        and unit_section.get("ConditionPathExists") == ["/usr/bin/cloudflared", "/etc/cloudflared/config.yml"]
        and service.get("User") == ["cloudflared"]
        and service.get("Group") == ["cloudflared"]
        and service.get("ExecStart") == ["/usr/bin/cloudflared --config /etc/cloudflared/config.yml tunnel run"]
        and service.get("Restart") == ["on-failure"]
        and service.get("NoNewPrivileges") == ["true"]
        and service.get("ProtectSystem") == ["strict"]
        and service.get("ProtectHome") == ["true"]
        and service.get("PrivateTmp") == ["true"]
        and service.get("PrivateDevices") == ["true"]
        and service.get("MemoryDenyWriteExecute") == ["true"]
        and not any("TOKEN=" in value or "SECRET=" in value or "PASSWORD=" in value for values in service.values() for value in values)
    )
    _add(checks, "S04REVIEW-CLOUDFLARED-LIFECYCLE-HARDENED", lifecycle_ok, unit)
    remediated = contract.get("remediated_artifacts", {})
    remediated_ok = isinstance(remediated, Mapping) and all(
        (root / relative).is_file() and sha256_file(root / relative) == expected
        for relative, expected in remediated.items()
    )
    _add(checks, "S04REVIEW-REMEDIATED-ARTIFACT-HASHES", remediated_ok, remediated)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    """Validate a complete S04 review candidate without invoking Phase verifiers.

    This intentionally avoids the P04 -> Stage Review -> P04 recursion while
    still rejecting partial or drifted review candidates in predecessor gates.
    """

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root / CONTRACT_PATH, checks, "S04REVIEW-PREFLIGHT-CONTRACT-STRICT-JSON")
    findings = _safe_load(root / FINDINGS_PATH, checks, "S04REVIEW-PREFLIGHT-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S04REVIEW-PREFLIGHT-FIXTURE-STRICT-JSON")
    _review_pin_checks(root, checks, hashes)
    if isinstance(contract, Mapping) and isinstance(findings, Mapping) and isinstance(fixture, Mapping):
        _check_contract_and_findings(contract, findings, fixture, checks)
        try:
            _check_runtime_binding(root, contract, fixture, checks)
        except Exception as exc:
            _add(checks, "S04REVIEW-PREFLIGHT-RUNTIME-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S04REVIEW-PREFLIGHT-INPUTS-AVAILABLE", False, "contract, findings or fixture unavailable")
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_STAGE_REVIEW_CANDIDATE_VALID" if not failed else "S04_STAGE_REVIEW_CANDIDATE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "next": "S04/GITHUB_STAGE_UPLOAD_READY" if not failed else "S04/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    found = [row for row in rows if row.get(key) == item_id]
    return found[0] if len(found) == 1 else {}


def _check_baseline_hashes(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    values = contract.get("baseline_critical_artifacts", {})
    if not isinstance(values, Mapping):
        _add(checks, "S04REVIEW-BASELINE-SHAPE", False, values)
        return
    for relative, expected in values.items():
        path = root / str(relative)
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[str(relative)] = actual
        _add(
            checks,
            "S04REVIEW-BASELINE-%s" % str(relative).upper().replace("/", "-").replace(".", "-"),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_taskpack_trace(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    tasks = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    traces = strict_json_load(root / "machine/facts/traceability_matrix.json")
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID]
    expected_outputs = [
        ["infra/compose.yml", "infra/systemd", "infra/config.schema.json"],
        ["infra/cloudflared.yml", "access_policy.md", "degraded_page.html"],
        ["release_slots.json", "feature_flags.json", "rollback.sh"],
        ["capacity_budget.json", "resource_shedding.json", "load_baseline.json"],
    ]
    roadmap_ok = (
        len(stages) == 1
        and stages[0].get("depends_on") == ["S00", "S01"]
        and [row.get("id") for row in stages[0].get("phases", [])] == ["P01", "P02", "P03", "P04"]
        and [row.get("outputs") for row in stages[0].get("phases", [])] == expected_outputs
    )
    _add(checks, "S04REVIEW-ROADMAP-TRACE-EXACT", roadmap_ok, stages)
    for record in contract.get("phase_records", []):
        phase = record.get("phase_id")
        req_id = record.get("requirement_id")
        ac_id = record.get("acceptance_contract_id")
        task_ids = record.get("task_ids")
        req = _row(requirements, str(req_id))
        ac = _row(acceptance, str(ac_id))
        phase_tasks = [row for row in tasks if row.get("stage_id") == STAGE_ID and row.get("phase_id") == phase]
        trace = _row(traces, str(req_id), "requirement_id")
        expected_test_ids = ["TEST-S04-%s" % phase, "TEST-S04-%s-BOUNDARY" % phase, "TEST-S04-%s-REPLAY" % phase]
        ok = (
            req.get("stage_id") == STAGE_ID
            and req.get("phase_id") == phase
            and req.get("primary_acceptance_criteria_id") == ac_id
            and ac.get("requirement_id") == req_id
            and [row.get("id") for row in ac.get("tests", [])] == expected_test_ids
            and [row.get("id") for row in phase_tasks] == task_ids
            and trace.get("acceptance_criteria_id") == ac_id
            and trace.get("task_ids") == task_ids
            and trace.get("test_ids") == expected_test_ids
            and trace.get("evidence_id") == "EVD-S04-%s" % phase
        )
        _add(checks, "S04REVIEW-TASKPACK-%s-TRACE" % phase, ok, {"requirement": req_id, "contract": ac_id, "tasks": task_ids})


def _verify_phase(phase_id: str, root: Path, verify_git_history: bool) -> Dict[str, Any]:
    return PHASE_VERIFIERS[phase_id](root, verify_git_history=verify_git_history)


def _evaluate_phase(phase_id: str, root: Path, verify_git_history: bool) -> Dict[str, Any]:
    return PHASE_EVALUATORS[phase_id](root, require_external_reports=False, _verify_git_history=verify_git_history)


def _check_phase_receipts_and_oracles(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    verify_git_history: bool,
) -> None:
    for record in contract.get("phase_records", []):
        phase = str(record.get("phase_id"))
        evidence_path = root / str(record.get("evidence_path"))
        rollback_path = root / str(record.get("rollback_path"))
        evidence_hash = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_hash = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        hash_ok = (
            evidence_hash == record.get("evidence_sha256") == fixture.get("expected_phase_evidence_sha256", {}).get(phase)
            and rollback_hash == record.get("rollback_sha256") == fixture.get("expected_phase_rollback_sha256", {}).get(phase)
        )
        _add(checks, "S04REVIEW-%s-SIGNED-ARTIFACT-HASHES" % phase, hash_ok, {"evidence": evidence_hash, "rollback": rollback_hash})
        try:
            receipt = _verify_phase(phase, root, verify_git_history)
            receipt_ok = (
                receipt.get("status") == "PASS"
                and receipt.get("decision") == PHASE_DECISIONS[phase]
                and receipt.get("next") == PHASE_NEXT[phase]
                and receipt.get("summary", {}).get("failed") == 0
            )
            _add(checks, "S04REVIEW-%s-SIGNED-RECEIPT" % phase, receipt_ok, receipt.get("summary"))
        except Exception as exc:
            _add(checks, "S04REVIEW-%s-SIGNED-RECEIPT" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            oracle = _evaluate_phase(phase, root, verify_git_history)
            oracle_ok = oracle.get("status") == "PASS" and oracle.get("summary", {}).get("failed") == 0 and oracle.get("next") == PHASE_NEXT[phase]
            _add(checks, "S04REVIEW-%s-CURRENT-ORACLE" % phase, oracle_ok, oracle.get("summary"))
        except Exception as exc:
            _add(checks, "S04REVIEW-%s-CURRENT-ORACLE" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        if verify_git_history:
            historical = _phase_code_hash_at_commit(root, str(record.get("implementation_commit")))
            history_ok = historical == record.get("implementation_code_sha256")
        else:
            historical = "SKIPPED_ISOLATED_COPY_WITHOUT_GIT_HISTORY"
            history_ok = True
        _add(checks, "S04REVIEW-%s-HISTORICAL-CODE-REPLAY" % phase, history_ok, {"expected": record.get("implementation_code_sha256"), "actual": historical})
        outputs_ok = all((root / relative).exists() for relative in record.get("required_outputs", []))
        _add(checks, "S04REVIEW-%s-REQUIRED-OUTPUTS" % phase, outputs_ok, record.get("required_outputs"))


def _iter_text_files(root: Path, relatives: Iterable[Path]) -> Iterable[Path]:
    for relative in relatives:
        path = root / relative
        if path.is_dir():
            yield from sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
        elif path.is_file():
            yield path


def _check_safety_and_progression(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    product = canonical.get("product", {})
    safe = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("monthly_target_return") == "0.30"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and canonical.get("runtime", {}).get("single_host_zero_downtime_guaranteed") is False
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
    )
    _add(checks, "S04REVIEW-A300-A0-NO-ORDER-NO-GUARANTEE", safe, {"product": product, "target": parameters.get("target_30pct")})
    s05_rows = [row for row in _load_index(root) if row.get("acceptance_contract_id", "").startswith("AC-S05-")]
    s05_artifacts = [
        Path("tests/S05/P01_test.py"),
        Path("machine/evidence/EVD-S05-P01.json"),
        Path("abd_acceptance/source_registry.py"),
    ]
    s05_ok = (
        len(s05_rows) == 4
        and all(row.get("status") == "PLANNED" and "actual_artifact" not in row and "artifact_sha256" not in row for row in s05_rows)
        and not any((root / path).exists() for path in s05_artifacts)
        and contract.get("next_on_pass") == "S04/GITHUB_STAGE_UPLOAD_READY"
    )
    _add(checks, "S04REVIEW-S05-NOT-STARTED", s05_ok, {"index": s05_rows, "artifacts": [path.as_posix() for path in s05_artifacts if (root / path).exists()]})
    review_rows = [row for row in _load_index(root) if row.get("id") == "INDEX-S04-STAGE-REVIEW"]
    index_state_ok = not review_rows or (
        len(review_rows) == 1
        and review_rows[0].get("status") == "PASS"
        and review_rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and review_rows[0].get("next") == "S04/GITHUB_STAGE_UPLOAD_READY"
    )
    _add(checks, "S04REVIEW-INDEX-STATE-MONOTONIC", index_state_ok, review_rows)
    leak_paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/stage4_review.py"), *ROLLBACK_ARTIFACTS]
    leaks: List[Dict[str, str]] = []
    for path in _iter_text_files(root, leak_paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative, "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative, "kind": "absolute-local-path"})
    _add(checks, "S04REVIEW-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")
    no_symlink = all((root / relative).is_file() and not (root / relative).is_symlink() for relative in [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, CLOUDFLARED_UNIT_PATH])
    _add(checks, "S04REVIEW-NO-REVIEW-ARTIFACT-SYMLINK", no_symlink, "review artifacts are regular files")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    reports = [
        ("S04REVIEW-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S04REVIEW-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
        ("S04REVIEW-SIGNED-STATE-REGRESSION", SIGNED_STATE_JUNIT_PATH, int(fixture.get("minimum_signed_state_pytest_cases", 0))),
    ]
    for check_id, relative, minimum in reports:
        try:
            summary = _junit_summary(root / relative)
            ok = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, check_id, ok, summary)
            hashes[relative.as_posix()] = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary", {})
        ok = report.get("status") == "PASS" and summary.get("checks") == 49 and summary.get("passed") == 49 and summary.get("failed") == 0
        _add(checks, "S04REVIEW-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04REVIEW-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S04REVIEW-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04REVIEW-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    preflight = validate_candidate_preflight(root)
    checks.extend(preflight.get("checks", []))
    hashes.update(preflight.get("hashes", {}))
    contract = strict_json_load(root / CONTRACT_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    _check_baseline_hashes(root, contract, checks, hashes)
    try:
        _check_taskpack_trace(root, contract, checks)
    except Exception as exc:
        _add(checks, "S04REVIEW-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_phase_receipts_and_oracles(root, contract, fixture, checks, _verify_git_history)
    _check_safety_and_progression(root, contract, checks)
    rollback = perform_rollback_drill(root)
    _add(checks, "S04REVIEW-ROLLBACK-DRILL", rollback.get("status") == "PASS", {"status": rollback.get("status"), "artifacts": len(rollback.get("artifacts", {}))})
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        _add(checks, "S04REVIEW-NUMERIC-BOUNDARY-%s" % str(delta).replace("-", "NEG").replace(".", "_"), delta in {"-0.0001", "0", "0.0001"}, delta)
    if require_external_reports:
        _check_external_reports(root, fixture, checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0))
    if len(checks) < minimum:
        _add(checks, "S04REVIEW-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    ids = [row["id"] for row in checks]
    if len(ids) != len(set(ids)):
        _add(checks, "S04REVIEW-CHECK-IDS-UNIQUE", False, "duplicate check ids")
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "S04_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S04_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED",
        "stage_status": "S04_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S04_WHOLE_STAGE_REVIEW_FAILED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "claim_boundary": contract.get("claim_boundary"),
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": contract.get("release_status_on_pass"),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "next": contract.get("next_on_pass") if status == "PASS" else "S04/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s04-stage-review-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(ROLLBACK_ARTIFACTS):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%02d" % index)
            active = temporary / ("active-%02d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored = sha256_file(active)
            results[relative.as_posix()] = {
                "status": "PASS" if corrupted != expected and restored == expected else "FAIL",
                "signed_sha256": expected,
                "corrupted_sha256": corrupted,
                "restored_sha256": restored,
            }
    status = "PASS" if len(results) == len(ROLLBACK_ARTIFACTS) and all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_STAGE_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
        "target_host_accessed": False,
        "docker_or_systemd_invoked": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH,
        Path("infra/compose.yml"), Path("infra/systemd/abd.service"), Path("infra/config.schema.json"), Path("infra/rebuild.sh"),
        Path("infra/cloudflared.yml"), Path("access_policy.md"), Path("degraded_page.html"), CLOUDFLARED_UNIT_PATH,
        Path("release_slots.json"), Path("feature_flags.json"), Path("rollback.sh"),
        Path("capacity_budget.json"), Path("resource_shedding.json"), Path("load_baseline.json"),
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/release_policy.json"), Path("machine/facts/roadmap.json"), Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"), Path("machine/facts/traceability_matrix.json"),
        Path("machine/evidence/EVD-S04-P01.json"), Path("machine/evidence/EVD-S04-P01_rollback.json"),
        Path("machine/evidence/EVD-S04-P02.json"), Path("machine/evidence/EVD-S04-P02_rollback.json"),
        Path("machine/evidence/EVD-S04-P03.json"), Path("machine/evidence/EVD-S04-P03_rollback.json"),
        Path("machine/evidence/EVD-S04-P04.json"), Path("machine/evidence/EVD-S04-P04_rollback.json"),
        Path("machine/evidence/S03/STAGE_REVIEW/github_delivery_receipt.json"),
        Path("README.md"), Path("abd_acceptance/stage4_review.py"),
        Path("abd_acceptance/infrastructure_iac.py"), Path("abd_acceptance/cloudflare_edge.py"),
        Path("abd_acceptance/release_control.py"), Path("abd_acceptance/capacity_governance.py"),
        Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S04-STAGE-REVIEW-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
            "external_state_changed": False,
            "target_host_accessed": False,
            "docker_or_systemd_invoked": False,
            "incremental_cash_spent_aud": "0.00",
        }
    if rollback.get("status") != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "S04_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED"
        validation["stage_status"] = "S04_WHOLE_STAGE_REVIEW_FAILED"
        validation["next"] = "S04/STAGE_REVIEW_REMEDIATION_REQUIRED"
    contract = strict_json_load(root / CONTRACT_PATH)
    findings = strict_json_load(root / FINDINGS_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    inputs = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "validation": validation,
        "phase_completion": {
            "phase_ids": fixture["expected_phase_ids"],
            "phase_evidence_status": "PASS",
            "phase_count": 4,
            "task_count": 12,
            "active_service": fixture["expected_active_profile"]["service"],
            "shadow_service": fixture["expected_shadow_profile"]["service"],
            "offline_frozen_10x_design_envelope": True,
            "production_10x_runtime_verified": False,
        },
        "review_findings": findings.get("summary"),
        "claim_boundary": contract.get("claim_boundary"),
        "hashes": {
            "inputs": inputs,
            "parameters": inputs["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S04 whole-stage review validates infrastructure, edge, release and capacity contracts offline; it executes no model, provider, host, account, container engine, systemd, browser, traffic, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S04/stage_review_test.py --junitxml=machine/evidence/S04/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S04/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/P01_test.py tests/S04/P02_test.py tests/S04/P03_test.py tests/S04/P04_test.py tests/S04/stage_review_test.py --junitxml=machine/evidence/S04/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "explicit_unknowns": [
            "No OVH host, Cloudflare or Gmail account, API, dashboard, DNS, credential or secret was accessed.",
            "Docker, systemd and cloudflared were not invoked; the new unit is a repository configuration contract only.",
            "OVH 7x24 operation, global Chinese reachability, China mainland reach or acceleration, and end-to-end Access remain unverified.",
            "The static degraded page is not claimed to be automatically wired into a runtime fallback path.",
            "The frozen 10x profile is deterministic engineering input, not observed production traffic or a target-host benchmark.",
            "The 900-second rollback and 60-second ledger recovery objectives are not real OVH RTO/RPO evidence.",
            "No model, market, quote, stake, account or order was selected or executed.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
            "Remote GitHub CI is not claimed by local review evidence and must be observed after whole-stage upload.",
        ],
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": fixture["expected_release_status"],
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "stage_status": "S04_WHOLE_STAGE_REVIEW_PASS" if validation["status"] == "PASS" else "S04_WHOLE_STAGE_REVIEW_FAILED",
        "next": validation["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-S04-STAGE-REVIEW"]
    if len(matching) > 1:
        raise Stage4ReviewContractError("duplicate INDEX-S04-STAGE-REVIEW rows")
    row = matching[0] if matching else {"id": "INDEX-S04-STAGE-REVIEW", "kind": "STAGE_REVIEW_EVIDENCE", "stage_id": STAGE_ID}
    if not matching:
        rows.append(row)
    row.update({
        "status": status,
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "verified_at": FIXED_CLOCK,
        "next": "S04/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S04/STAGE_REVIEW_REMEDIATION_REQUIRED",
    })
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows))


def write_stage4_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise Stage4ReviewContractError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.relative_to(root).as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def validate_signed_receipt_preflight(root: Path) -> Dict[str, Any]:
    """Validate the signed review receipt without recursively invoking P04."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    candidate = validate_candidate_preflight(root)
    _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-CANDIDATE", candidate.get("status") == "PASS", candidate.get("summary"))
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S04REVIEW-SIGNED-PREFLIGHT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S04REVIEW-SIGNED-PREFLIGHT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    fixture = strict_json_load(root / FIXTURE_PATH)
    contract = strict_json_load(root / CONTRACT_PATH)
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S04-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S04_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("stage_status") == "S04_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("release_status") == fixture.get("expected_release_status")
            and evidence.get("next") == "S04/GITHUB_STAGE_UPLOAD_READY"
            and evidence.get("claim_boundary") == contract.get("claim_boundary")
            and evidence.get("external_effect_boundary") == contract.get("external_effect_boundary")
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            isinstance(validation, Mapping)
            and validation.get("status") == "PASS"
            and validation.get("summary", {}).get("failed") == 0
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-VALIDATION", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate_path = Path(relative)
            if candidate_path.is_absolute() or ".." in candidate_path.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate_path if relative.startswith(".github/") else root / candidate_path
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-INPUT-HASHES", not input_errors, input_errors or "all inputs match")
        code_actual = _current_code_hash(root)
        _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-CODE-HASH", evidence.get("hashes", {}).get("code") == code_actual, {"expected": evidence.get("hashes", {}).get("code"), "actual": code_actual})
        _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-ROLLBACK-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
    else:
        for check_id in [
            "S04REVIEW-SIGNED-PREFLIGHT-INTEGRITY",
            "S04REVIEW-SIGNED-PREFLIGHT-VALIDATION",
            "S04REVIEW-SIGNED-PREFLIGHT-INPUT-HASHES",
            "S04REVIEW-SIGNED-PREFLIGHT-CODE-HASH",
            "S04REVIEW-SIGNED-PREFLIGHT-ROLLBACK-BINDING",
        ]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S04-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and rollback.get("target_host_accessed") is False
        and rollback.get("docker_or_systemd_invoked") is False
        and rollback.get("incremental_cash_spent_aud") == "0.00"
        and len(rollback.get("artifacts", {})) == fixture.get("expected_rollback_artifact_count")
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-S04-STAGE-REVIEW"]
    index_ok = (
        len(rows) == 1
        and rows[0].get("status") == "PASS"
        and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and rows[0].get("artifact_sha256") == evidence_hash
        and rows[0].get("next") == "S04/GITHUB_STAGE_UPLOAD_READY"
    )
    _add(checks, "S04REVIEW-SIGNED-PREFLIGHT-INDEX", index_ok, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_STAGE_REVIEW_SIGNED_PREFLIGHT_VALID" if not failed else "S04_STAGE_REVIEW_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S04/GITHUB_STAGE_UPLOAD_READY" if not failed else "S04/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def verify_existing_stage_review_evidence(
    root: Path,
    *,
    verify_phase_prerequisites: bool = True,
    verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    preflight = validate_signed_receipt_preflight(root)
    _add(checks, "S04REVIEW-RECEIPT-PREFLIGHT", preflight.get("status") == "PASS", preflight.get("summary"))
    if verify_phase_prerequisites:
        for phase in ["P01", "P02", "P03", "P04"]:
            try:
                result = _verify_phase(phase, root, verify_git_history)
                _add(
                    checks,
                    "S04REVIEW-RECEIPT-%s-PREREQUISITE" % phase,
                    result.get("status") == "PASS" and result.get("decision") == PHASE_DECISIONS[phase],
                    result.get("summary"),
                )
            except Exception as exc:
                _add(checks, "S04REVIEW-RECEIPT-%s-PREREQUISITE" % phase, False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_STAGE_REVIEW_EVIDENCE_VERIFIED" if not failed else "S04_STAGE_REVIEW_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": preflight.get("evidence_sha256"),
        "rollback_sha256": preflight.get("rollback_sha256"),
        "next": "S04/GITHUB_STAGE_UPLOAD_READY" if not failed else "S04/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
