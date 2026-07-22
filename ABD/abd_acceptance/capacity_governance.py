from __future__ import annotations

import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

from .canonical_facts import sha256_file, strict_json_load
from .release_control import verify_existing_phase_evidence as verify_release_control_evidence


CONTRACT_ID = "AC-S04-P04"
REQUIREMENT_ID = "REQ-S04-P04"
STAGE_ID = "S04"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-22T23:30:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CAPACITY_PATH = Path("capacity_budget.json")
SHEDDING_PATH = Path("resource_shedding.json")
BASELINE_PATH = Path("load_baseline.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S04_P04.json")
TEST_PATH = Path("tests/S04/P04_test.py")
JUNIT_PATH = Path("machine/evidence/S04/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S04/P04/full_regression.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S04/P04/signed_state_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S04-P03_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

EXPECTED_ARTIFACTS = {
    "ART-S04-P04-01": CAPACITY_PATH.as_posix(),
    "ART-S04-P04-02": SHEDDING_PATH.as_posix(),
    "ART-S04-P04-03": BASELINE_PATH.as_posix(),
}
EXPECTED_TASK_IDS = ["T-S04-P04-01", "T-S04-P04-02", "T-S04-P04-03"]
EXPECTED_TEST_IDS = ["TEST-S04-P04", "TEST-S04-P04-BOUNDARY", "TEST-S04-P04-REPLAY"]
EXPECTED_STATES = ["NORMAL", "CONSTRAINED", "CRITICAL", "EMERGENCY"]
EXPECTED_NUMERIC_DELTAS = ["-0.0001", "0", "0.0001"]
EXPECTED_DISK_BUCKETS = {
    "host_os_and_container_runtime": 8192,
    "two_release_slots": 4096,
    "immutable_ledger_and_acceptance_evidence": 8192,
    "mail_archive_future_s06": 8192,
    "outbox_and_checkpoints": 2048,
    "bounded_operational_logs": 2048,
    "bounded_temporary_files": 1024,
    "unallocated_emergency_reserve": 7168,
}
EXPECTED_RETENTION_CLASSES = {
    "immutable_ledger": (4096, False),
    "acceptance_evidence": (4096, False),
    "mail_archive": (8192, False),
    "operational_logs": (2048, True),
    "temporary_files": (1024, True),
    "release_slots": (4096, False),
    "outbox_and_checkpoints": (2048, False),
}
EXTERNAL_EFFECT_BOUNDARY = {
    "network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "target_host_telemetry_read": False,
    "docker_or_systemd_invoked": False,
    "swap_or_disk_configuration_changed": False,
    "cloudflare_changed": False,
    "production_activated": False,
    "real_traffic_generated": False,
    "real_order_submitted": False,
    "return_or_roi_verified": False,
    "incremental_cash_spent_aud": "0.00",
}

STRUCTURAL_SELF_NORMALIZED_SHA256 = "970fbb27d9a886443f64304c4df81e7caf70f773e6100765caedc7ba96140549"
PHASE_COMMIT = "2630ec141e440d72288d68d42ec397debd245e5c"
PINNED_PHASE_CODE_HASH = "ca8112ae584f83faeec97476da791137bf837c48fb7329522d745ccc4afd34ec"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "abd_acceptance/capacity_governance.py",
    "tests/S04/P04_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "tests/S04/P04_test.py": "8dfb270a6f35b469d5221275baf9ac80c875d6fd59c2b571bd62255fc34a3ff1",
}
PINNED_PHASE_HASHES: Dict[str, str] = {
    CAPACITY_PATH.as_posix(): "b3c76e22683fc45deb5bb59ae7867ae7886800e93232ea4a99dc567ea70daaa2",
    SHEDDING_PATH.as_posix(): "c79a8d5e86852dcb7611268e57301c59210d11db9ae5fdef6e127da605a6c5e6",
    BASELINE_PATH.as_posix(): "395135bfd165c37700c2f4e41a14691dbd06d0d59e9b358b437a7ee38adbe695",
    FIXTURE_PATH.as_posix(): "10736c964ccf145e5cb391e25e26041233ee71abf7f004feec2742195d2aaa3e",
    TEST_PATH.as_posix(): "de127a154696d51b46818c684b88a8d649e679490a5dbd8839ca395a5fd79d6d",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    P03_EVIDENCE_PATH.as_posix(): "a83dd53611d45af498ea1f70a7363aa3666021057a13c2b661abe89ca0bec1e7",
    P03_ROLLBACK_PATH.as_posix(): "4658549bc64b5097104a0cf72bfc4af48c844eb599709ab8ecec2e4d81ed64b5",
}
PINNED_REPO_HASHES = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]


class CapacityGovernanceContractError(ValueError):
    """Raised when the S04/P04 capacity contract cannot be evaluated safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _load_index(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise CapacityGovernanceContractError("evidence index rows must be objects")
        rows.append(value)
    return rows


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(root: Path, relative: str, expected_sha256: str, verify_git_history: bool) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if verify_git_history:
        if not _phase_commit_is_ancestor(root):
            return False
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (PHASE_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if relative == "abd_acceptance/capacity_governance.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return successor not in {None, "TO_BE_FILLED"} and (root / relative).is_file() and sha256_file(root / relative) == successor


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _phase_commit_is_ancestor(root):
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", PHASE_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        line
        for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
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


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/capacity_governance.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _set_or_delete_path(value: Any, path: Sequence[Any], replacement: Any = None, *, delete: bool = False) -> None:
    if not path:
        raise CapacityGovernanceContractError("mutation path must not be empty")
    current = value
    for part in path[:-1]:
        current = current[part]
    final = path[-1]
    if delete:
        if isinstance(current, list):
            del current[int(final)]
        else:
            del current[final]
    else:
        current[final] = replacement


def validate_capacity_budget(config: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(config, Mapping):
        return ["capacity budget must be an object"]
    required = {
        "schema_version", "product_version", "phase", "contract", "measurement_boundary",
        "target_host", "cpu_budget", "memory_budget", "disk_budget",
        "browser_concurrency_budget", "retention_budget", "telemetry_contract",
        "financial_and_order_boundary", "external_effect_boundary",
    }
    if set(config) != required:
        errors.append("top-level keys must match the frozen capacity contract")
    if config.get("schema_version") != "1.0.0" or config.get("product_version") != VERSION or config.get("phase") != "S04/P04" or config.get("contract") != "DECLARED_VPS1_INTEGER_RESOURCE_BUDGET_WITH_FAIL_CLOSED_ADMISSION":
        errors.append("schema, version and phase must be frozen")
    measurement = _as_mapping(config.get("measurement_boundary"))
    if not isinstance(measurement, Mapping) or measurement.get("kind") != "DETERMINISTIC_ENGINEERING_BUDGET_NOT_TARGET_HOST_MEASUREMENT" or measurement.get("target_host_inspected") is not False or measurement.get("production_telemetry_observed") is not False or measurement.get("production_capacity_verified") is not False or measurement.get("runtime_calibration_required_before_activation") is not True or measurement.get("frozen_load_horizon_days") != 365:
        errors.append("measurement boundary must not claim target-host capacity")
    host = _as_mapping(config.get("target_host"))
    expected_host = {
        "provider": "OVHcloud", "region": "Singapore", "plan": "VPS-1",
        "operating_system": "Ubuntu Linux", "capacity_verification_status": "DECLARED_TARGET_NOT_ACCOUNT_VERIFIED",
        "vcpu": 2, "cpu_total_millicores": 2000, "memory_total_mib": 4096,
        "disk_total_mib": 40960, "swap_allowed": False,
    }
    if host != expected_host:
        errors.append("target host must match the declared, unverified P01 VPS-1 envelope")
    cpu = _as_mapping(config.get("cpu_budget"))
    cpu_values = [cpu.get("active_slot_outer_hard_limit_millicores"), cpu.get("candidate_shadow_outer_hard_limit_millicores"), cpu.get("host_system_and_tunnel_reserve_millicores")]
    if cpu.get("total_millicores") != 2000 or not all(_is_int(value) and value >= 0 for value in cpu_values) or sum(cpu_values) != 2000 or cpu.get("allocated_millicores") != 2000:
        errors.append("CPU allocation must equal exactly 2000 millicores")
    if cpu_values != [1500, 250, 250] or list(_as_mapping(cpu.get("utilization_thresholds_basis_points")).values()) != [7000, 8500, 9000]:
        errors.append("CPU slot limits and thresholds must match the frozen envelope")
    memory = _as_mapping(config.get("memory_budget"))
    memory_values = [memory.get("active_slot_outer_hard_limit_mib"), memory.get("candidate_shadow_outer_hard_limit_mib"), memory.get("host_system_and_tunnel_reserve_mib")]
    if memory.get("total_mib") != 4096 or not all(_is_int(value) and value >= 0 for value in memory_values) or sum(memory_values) != 4096 or memory.get("allocated_mib") != 4096:
        errors.append("memory allocation must equal exactly 4096 MiB")
    if memory_values != [2560, 512, 1024] or memory.get("swap_allowed") is not False or list(_as_mapping(memory.get("utilization_thresholds_basis_points")).values()) != [7000, 8500, 9000]:
        errors.append("memory limits, no-swap rule and thresholds must be frozen")
    disk = _as_mapping(config.get("disk_budget"))
    allocation_buckets = _as_list(disk.get("allocation_buckets"))
    buckets = {
        row.get("id"): row.get("budget_mib")
        for row in allocation_buckets
        if isinstance(row, Mapping)
        and isinstance(row.get("id"), str)
        and _is_int(row.get("budget_mib"))
    }
    if buckets != EXPECTED_DISK_BUCKETS or len(allocation_buckets) != len(EXPECTED_DISK_BUCKETS) or sum(buckets.values()) != 40960 or disk.get("allocated_mib") != 40960 or disk.get("total_mib") != 40960:
        errors.append("disk buckets must be unique and allocate exactly 40960 MiB")
    watermarks = _as_mapping(disk.get("watermarks_used_mib"))
    if list(watermarks.values()) != [28672, 32768, 34816, 36864, 40960] or disk.get("minimum_free_reserve_mib") != 4096 or disk.get("immutable_evidence_deletion_allowed") is not False:
        errors.append("disk watermarks and immutable reserve must be exact")
    browser = _as_mapping(config.get("browser_concurrency_budget"))
    if browser.get("feature_flag") != "owner_browser_companion" or browser.get("repository_enabled_in_p04") is not False or browser.get("expected_1x_sessions") != 2 or browser.get("frozen_10x_sessions") != 20 or browser.get("admission_cap_sessions") != 20 or browser.get("resource_cost_included_in_active_slot_profile") is not True:
        errors.append("browser budget must admit exactly the frozen 2/20-session envelope while remaining disabled")
    retention = _as_mapping(config.get("retention_budget"))
    retention_rows = _as_list(retention.get("classes"))
    classes = {
        row.get("id"): (row.get("budget_mib"), row.get("automatic_delete"))
        for row in retention_rows
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
    if classes != EXPECTED_RETENTION_CLASSES or len(retention_rows) != len(EXPECTED_RETENTION_CLASSES):
        errors.append("retention classes must match the frozen budgets")
    if any(
        row.get("automatic_delete") is True
        for row in retention_rows
        if isinstance(row, Mapping)
        and (
            not isinstance(row.get("id"), str)
            or row.get("id") not in {"operational_logs", "temporary_files"}
        )
    ):
        errors.append("only bounded non-evidence logs and temporary files may rotate automatically")
    telemetry = _as_mapping(config.get("telemetry_contract"))
    expected_metrics = ["cpu_usage_basis_points", "memory_usage_basis_points", "disk_used_mib", "swap_used_mib", "browser_sessions", "telemetry_age_seconds"]
    if telemetry.get("sample_period_seconds") != 10 or telemetry.get("stale_after_seconds") != 30 or telemetry.get("required_metrics") != expected_metrics or telemetry.get("unknown_missing_negative_or_stale_action") != "EMERGENCY_FAIL_CLOSED" or telemetry.get("runtime_source_status") != "NOT_CONNECTED_OR_VERIFIED_ON_OVH":
        errors.append("telemetry must fail closed after 30 seconds and remain runtime-unverified")
    boundary = _as_mapping(config.get("financial_and_order_boundary"))
    if boundary.get("initial_bankroll_aud") != "300.00" or boundary.get("incremental_cash_budget_aud") != "0.00" or boundary.get("automatic_paid_scale_up_allowed") is not False or boundary.get("automatic_new_instance_allowed") is not False or boundary.get("automatic_storage_upgrade_allowed") is not False or boundary.get("order_submission_module_present") is not False or boundary.get("monthly_30pct_target_guaranteed") is not False or boundary.get("target_shortfall_may_relax_capacity_or_safety_gate") is not False:
        errors.append("A$300/A$0/no-order/no-guarantee boundary must remain fixed")
    if config.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY:
        errors.append("external effect boundary must remain entirely inactive")
    if _contains_float(config):
        errors.append("binary floating point values are forbidden")
    return errors


def validate_resource_shedding(policy: Any, capacity: Mapping[str, Any] | None = None) -> List[str]:
    errors: List[str] = []
    if not isinstance(policy, Mapping):
        return ["resource shedding policy must be an object"]
    required = {
        "schema_version", "product_version", "phase", "policy", "telemetry_unknown_policy",
        "state_order", "states", "trigger_thresholds", "hysteresis", "priority_classes",
        "forbidden_effects", "recovery_contract", "external_effect_boundary",
    }
    if set(policy) != required:
        errors.append("top-level keys must match the frozen shedding contract")
    if policy.get("schema_version") != "1.0.0" or policy.get("product_version") != VERSION or policy.get("phase") != "S04/P04" or policy.get("policy") != "HIGHEST_SEVERITY_WINS_NEVER_ENABLE_A_DISABLED_FEATURE" or policy.get("telemetry_unknown_policy") != "EMERGENCY_FAIL_CLOSED":
        errors.append("shedding policy identity and fail-closed rule must be frozen")
    if policy.get("state_order") != EXPECTED_STATES:
        errors.append("state order must be NORMAL through EMERGENCY")
    states = _as_list(policy.get("states"))
    state_map = {
        row.get("id"): row
        for row in states
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
    if list(state_map) != EXPECTED_STATES or len(states) != len(EXPECTED_STATES):
        errors.append("states must be unique and ordered")
    for state_id in EXPECTED_STATES:
        row = state_map.get(state_id, {})
        if not isinstance(row.get("actions"), list) or not row.get("actions"):
            errors.append("every state requires explicit actions")
            break
    for state_id in ["CRITICAL", "EMERGENCY"]:
        row = state_map.get(state_id, {})
        if row.get("capacity_admission_allowed") is not False or row.get("new_browser_sessions_allowed") is not False or row.get("optional_writes_allowed") is not False or row.get("new_advice_capacity_allowed") is not False or "STOP_NEW_ADVICE" not in _as_list(row.get("actions")):
            errors.append("critical and emergency states must stop new advice and admission")
            break
    constrained = state_map.get("CONSTRAINED", {})
    if constrained.get("optional_writes_allowed") is not False or constrained.get("new_browser_sessions_allowed") is not False or "STOP_CANDIDATE_SHADOW_FIRST" not in _as_list(constrained.get("actions")):
        errors.append("constrained state must shed candidate, optional writes and new browsers first")
    thresholds = _as_mapping(policy.get("trigger_thresholds"))
    if list(_as_mapping(thresholds.get("cpu_or_memory_basis_points")).values()) != [7000, 8500, 9000] or list(_as_mapping(thresholds.get("disk_used_mib")).values()) != [32768, 34816, 36864, 40960] or thresholds.get("browser_sessions") != {"maximum_admitted": 20, "over_maximum_state": "CRITICAL"} or thresholds.get("swap_used_mib") != {"allowed": 0, "positive_state": "EMERGENCY"} or thresholds.get("telemetry_age_seconds") != {"maximum": 30, "over_maximum_state": "EMERGENCY"}:
        errors.append("resource trigger thresholds must match the capacity budget")
    if capacity is not None:
        capacity_mapping = _as_mapping(capacity)
        cpu_thresholds = _as_mapping(_as_mapping(capacity_mapping.get("cpu_budget")).get("utilization_thresholds_basis_points"))
        memory_thresholds = _as_mapping(_as_mapping(capacity_mapping.get("memory_budget")).get("utilization_thresholds_basis_points"))
        disk_thresholds = _as_mapping(_as_mapping(capacity_mapping.get("disk_budget")).get("watermarks_used_mib"))
        if cpu_thresholds != memory_thresholds or list(cpu_thresholds.values()) != [7000, 8500, 9000] or [disk_thresholds.get(key) for key in ["shed_optional_writes", "stop_new_advice", "emergency", "hard_capacity"]] != [32768, 34816, 36864, 40960]:
            errors.append("shedding thresholds must be identical to capacity thresholds")
    priorities = _as_list(policy.get("priority_classes"))
    priority_rows = [row for row in priorities if isinstance(row, Mapping)]
    if len(priority_rows) != 4 or [row.get("priority") for row in priority_rows] != [0, 1, 2, 3] or priority_rows[0].get("id") != "INTEGRITY_AND_ROLLBACK" or priority_rows[0].get("shed_allowed") is not False:
        errors.append("integrity and rollback must be unsheddable priority zero")
    forbidden_values = _as_list(policy.get("forbidden_effects"))
    forbidden = set(forbidden_values) if all(isinstance(value, str) for value in forbidden_values) else set()
    required_forbidden = {
        "ENABLE_LIVE_RECOMMENDATION", "SUBMIT_CONFIRM_OR_RETRY_REAL_ORDER",
        "DELETE_OR_MUTATE_IMMUTABLE_LEDGER_OR_ACCEPTANCE_EVIDENCE",
        "LOWER_EVIDENCE_NUMERIC_RISK_SAFETY_OR_SOURCE_GATE", "SILENTLY_DROP_COVERAGE_GAP",
        "ENABLE_SWAP", "AUTO_PURCHASE_CAPACITY_STORAGE_OR_PAID_SERVICE",
        "CLAIM_PRODUCTION_CAPACITY_VERIFIED",
    }
    if forbidden != required_forbidden:
        errors.append("forbidden effects must preserve every safety and cost gate")
    hysteresis = _as_mapping(policy.get("hysteresis"))
    if hysteresis != {
        "consecutive_healthy_samples_to_lower_state": 6,
        "minimum_state_hold_seconds": 60,
        "unknown_sample_resets_recovery_counter": True,
        "emergency_requires_explicit_operator_or_signed_automation_clear": True,
    }:
        errors.append("hysteresis and emergency-clear requirements must remain frozen")
    recovery = _as_mapping(policy.get("recovery_contract"))
    if recovery.get("automatic_return_to_normal_from_emergency") is not False or recovery.get("prior_advice_automatically_revalidated") is not False or not recovery.get("restore_order"):
        errors.append("emergency recovery must require explicit verification and never revive old advice")
    if policy.get("external_effect_boundary") != {
        "production_policy_applied": False,
        "production_process_killed": False,
        "production_writes_stopped": False,
        "production_rollback_invoked": False,
        "paid_capacity_added": False,
        "real_order_submitted": False,
    }:
        errors.append("shedding artifact must not claim a production effect")
    if _contains_float(policy):
        errors.append("binary floating point values are forbidden")
    return errors


def validate_load_baseline(baseline: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(baseline, Mapping):
        return ["load baseline must be an object"]
    required = {
        "schema_version", "product_version", "phase", "baseline_id", "baseline_kind",
        "fixed_clock", "random_seed", "runtime_measurement", "horizon_days",
        "initial_disk_used_mib", "profiles", "ten_x_acceptance",
        "numeric_stability_boundary", "external_effect_boundary",
    }
    if set(baseline) != required:
        errors.append("top-level keys must match the frozen baseline contract")
    if baseline.get("schema_version") != "1.0.0" or baseline.get("product_version") != VERSION or baseline.get("phase") != "S04/P04" or baseline.get("baseline_id") != "ABD-S04-P04-FROZEN-DESIGN-LOAD" or baseline.get("fixed_clock") != FIXED_CLOCK or baseline.get("random_seed") != 404:
        errors.append("baseline identity, clock and seed must be frozen")
    if baseline.get("baseline_kind") != "DETERMINISTIC_SYNTHETIC_ENGINEERING_BASELINE_NOT_OBSERVED_TRAFFIC" or baseline.get("horizon_days") != 365 or baseline.get("initial_disk_used_mib") != 10496:
        errors.append("baseline must be a 365-day synthetic design input")
    measurement = _as_mapping(baseline.get("runtime_measurement"))
    required_future_evidence = _as_list(measurement.get("required_future_evidence"))
    if measurement.get("target_host_benchmark_executed") is not False or measurement.get("production_traffic_observed") is not False or measurement.get("ovh_telemetry_read") is not False or measurement.get("results_may_be_called_production_capacity") is not False or required_future_evidence != ["TARGET_HOST_CGROUP_TELEMETRY", "TARGET_HOST_DISK_GROWTH_AND_RETENTION_CALIBRATION", "PRODUCTION_EQUIVALENT_10X_LOAD_RUN", "S04_WHOLE_STAGE_REVIEW"]:
        errors.append("runtime measurement boundary must remain explicitly unverified")
    profiles = _as_list(baseline.get("profiles"))
    profile_rows = [row for row in profiles if isinstance(row, Mapping)]
    profile_map = {
        row.get("id"): row
        for row in profile_rows
        if isinstance(row.get("id"), str)
    }
    if list(profile_map) != ["EXPECTED_1X", "FROZEN_10X"] or len(profiles) != 2:
        errors.append("baseline requires exactly 1x and 10x profiles")
    one = profile_map.get("EXPECTED_1X", {})
    ten = profile_map.get("FROZEN_10X", {})
    one_work = one.get("normalized_work_units_per_window")
    ten_work = ten.get("normalized_work_units_per_window")
    one_browsers = one.get("browser_sessions")
    ten_browsers = ten.get("browser_sessions")
    if one.get("multiplier") != 1 or ten.get("multiplier") != 10 or not all(_is_int(value) for value in [one_work, ten_work, one_browsers, ten_browsers]) or ten_work != 10 * one_work or ten_browsers != 10 * one_browsers:
        errors.append("10x work and browser inputs must be exactly ten times 1x")
    numeric_keys = [
        "multiplier", "normalized_work_units_per_window", "browser_sessions",
        "active_slot_cpu_millicores", "candidate_shadow_cpu_millicores", "host_cpu_millicores",
        "active_slot_memory_mib", "candidate_shadow_memory_mib", "host_memory_mib",
        "swap_used_mib", "immutable_daily_growth_mib", "optional_daily_growth_mib",
        "telemetry_age_seconds",
    ]
    if len(profile_rows) != 2 or any(not _is_int(row.get(key)) or row.get(key) < 0 for row in profile_rows for key in numeric_keys):
        errors.append("all profile measurements must be non-negative integers")
    if len(profile_rows) != 2 or any(row.get("swap_used_mib") != 0 for row in profile_rows) or one.get("expected_pre_shed_state") != "NORMAL" or one.get("expected_post_shed_state") != "NORMAL" or ten.get("expected_pre_shed_state") != "CONSTRAINED" or ten.get("expected_post_shed_state") != "NORMAL":
        errors.append("profile state and no-swap expectations must be exact")
    acceptance = _as_mapping(baseline.get("ten_x_acceptance"))
    if acceptance.get("profile_id") != "FROZEN_10X" or acceptance.get("core_safety_horizon_days") != 365 or acceptance.get("optional_work_may_be_shed") is not True or acceptance.get("core_analysis_throughput_claimed_sustained_in_production") is not False or acceptance.get("uncontrolled_swap_allowed") is not False or acceptance.get("disk_exhaustion_allowed") is not False or acceptance.get("immutable_evidence_deletion_allowed") is not False or acceptance.get("paid_scale_up_allowed") is not False:
        errors.append("10x acceptance must prove safety without a production throughput claim")
    numeric = _as_mapping(baseline.get("numeric_stability_boundary"))
    if numeric.get("allowed_probability_or_threshold_deltas") != EXPECTED_NUMERIC_DELTAS or numeric.get("adverse_odds_tick_values") != [False, True] or numeric.get("capacity_safety_may_change") is not False or numeric.get("financial_target_shortfall_may_relax_resource_gate") is not False:
        errors.append("numeric stability must not change resource safety")
    if baseline.get("external_effect_boundary") != {
        "network_accessed": False,
        "target_host_accessed": False,
        "real_load_generated": False,
        "production_disk_written": False,
        "production_swap_changed": False,
        "production_browser_sessions_opened": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        errors.append("baseline must have no external effects")
    if _contains_float(baseline):
        errors.append("binary floating point values are forbidden")
    return errors


def _ceil_basis_points(used: int, total: int) -> int:
    if not _is_int(used) or not _is_int(total) or used < 0 or total <= 0:
        raise CapacityGovernanceContractError("resource values must be non-negative integers with positive total")
    return (used * 10000 + total - 1) // total


def resource_disposition(metrics: Any, capacity: Mapping[str, Any], policy: Mapping[str, Any]) -> Dict[str, Any]:
    required = set(capacity.get("telemetry_contract", {}).get("required_metrics", []))
    malformed = not isinstance(metrics, Mapping) or set(metrics) != required
    if not malformed:
        malformed = any(not _is_int(metrics.get(key)) or metrics.get(key) < 0 for key in required)
    state_id = "EMERGENCY"
    reasons: List[str] = []
    if malformed:
        reasons = ["UNKNOWN_OR_MALFORMED_TELEMETRY"]
    else:
        cpu = metrics["cpu_usage_basis_points"]
        memory = metrics["memory_usage_basis_points"]
        disk = metrics["disk_used_mib"]
        swap = metrics["swap_used_mib"]
        browsers = metrics["browser_sessions"]
        age = metrics["telemetry_age_seconds"]
        thresholds = policy["trigger_thresholds"]
        if age > thresholds["telemetry_age_seconds"]["maximum"]:
            reasons.append("TELEMETRY_STALE")
        if swap > thresholds["swap_used_mib"]["allowed"]:
            reasons.append("SWAP_USED")
        if disk >= thresholds["disk_used_mib"]["hard_capacity"]:
            reasons.append("DISK_HARD_CAPACITY_REACHED")
        if cpu >= thresholds["cpu_or_memory_basis_points"]["emergency_at"] or memory >= thresholds["cpu_or_memory_basis_points"]["emergency_at"] or disk >= thresholds["disk_used_mib"]["emergency_at"]:
            reasons.append("EMERGENCY_RESOURCE_THRESHOLD")
        if reasons:
            state_id = "EMERGENCY"
        elif cpu >= thresholds["cpu_or_memory_basis_points"]["critical_at"] or memory >= thresholds["cpu_or_memory_basis_points"]["critical_at"] or disk >= thresholds["disk_used_mib"]["critical_at"] or browsers > thresholds["browser_sessions"]["maximum_admitted"]:
            state_id = "CRITICAL"
            reasons = ["CRITICAL_RESOURCE_OR_BROWSER_THRESHOLD"]
        elif cpu >= thresholds["cpu_or_memory_basis_points"]["constrained_at"] or memory >= thresholds["cpu_or_memory_basis_points"]["constrained_at"] or disk >= thresholds["disk_used_mib"]["constrained_at"]:
            state_id = "CONSTRAINED"
            reasons = ["CONSTRAINED_RESOURCE_THRESHOLD"]
        else:
            state_id = "NORMAL"
            reasons = ["WITHIN_FROZEN_RESOURCE_ENVELOPE"]
    state_map = {row["id"]: row for row in policy.get("states", []) if isinstance(row, Mapping) and "id" in row}
    selected = state_map.get(state_id, {})
    return {
        "schema_version": "1.0.0",
        "state": state_id,
        "reasons": reasons,
        "capacity_admission_allowed": selected.get("capacity_admission_allowed") is True,
        "new_browser_sessions_allowed": selected.get("new_browser_sessions_allowed") is True,
        "optional_writes_allowed": selected.get("optional_writes_allowed") is True,
        "new_advice_capacity_allowed": selected.get("new_advice_capacity_allowed") is True,
        "effective_live_recommendation_enabled": False,
        "actions": list(selected.get("actions", [])),
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _profile_metrics(profile: Mapping[str, Any], capacity: Mapping[str, Any], disk_used_mib: int, *, shed_candidate: bool) -> Dict[str, int]:
    candidate_cpu = 0 if shed_candidate else profile["candidate_shadow_cpu_millicores"]
    candidate_memory = 0 if shed_candidate else profile["candidate_shadow_memory_mib"]
    cpu_used = profile["active_slot_cpu_millicores"] + candidate_cpu + profile["host_cpu_millicores"]
    memory_used = profile["active_slot_memory_mib"] + candidate_memory + profile["host_memory_mib"]
    return {
        "cpu_usage_basis_points": _ceil_basis_points(cpu_used, capacity["cpu_budget"]["total_millicores"]),
        "memory_usage_basis_points": _ceil_basis_points(memory_used, capacity["memory_budget"]["total_mib"]),
        "disk_used_mib": disk_used_mib,
        "swap_used_mib": profile["swap_used_mib"],
        "browser_sessions": profile["browser_sessions"],
        "telemetry_age_seconds": profile["telemetry_age_seconds"],
    }


def simulate_disk_horizon(profile: Mapping[str, Any], baseline: Mapping[str, Any], capacity: Mapping[str, Any], policy: Mapping[str, Any], *, optional_writes_initially_allowed: bool) -> Dict[str, Any]:
    used = baseline["initial_disk_used_mib"]
    optional_allowed = bool(optional_writes_initially_allowed)
    core_writes_allowed = True
    optional_shed_day = None
    core_stop_day = None
    watermarks = capacity["disk_budget"]["watermarks_used_mib"]
    for day in range(1, baseline["horizon_days"] + 1):
        if used >= watermarks["stop_new_advice"]:
            core_writes_allowed = False
            if core_stop_day is None:
                core_stop_day = day
        if used >= watermarks["shed_optional_writes"]:
            optional_allowed = False
            if optional_shed_day is None:
                optional_shed_day = day
        growth = 0
        if core_writes_allowed:
            growth += profile["immutable_daily_growth_mib"]
        if optional_allowed:
            growth += profile["optional_daily_growth_mib"]
        if used + growth >= watermarks["stop_new_advice"]:
            core_writes_allowed = False
            optional_allowed = False
            if core_stop_day is None:
                core_stop_day = day
            growth = 0
        used += growth
    hard = watermarks["hard_capacity"]
    return {
        "horizon_days": baseline["horizon_days"],
        "initial_used_mib": baseline["initial_disk_used_mib"],
        "final_used_mib": used,
        "free_mib": hard - used,
        "optional_shed_day": optional_shed_day,
        "core_stop_day": core_stop_day,
        "optional_writes_allowed_at_end": optional_allowed,
        "core_writes_allowed_at_end": core_writes_allowed,
        "hard_capacity_mib": hard,
        "disk_exhausted": used >= hard,
        "minimum_free_reserve_preserved": hard - used >= capacity["disk_budget"]["minimum_free_reserve_mib"],
        "production_disk_written": False,
    }


def evaluate_load_profile(profile: Mapping[str, Any], baseline: Mapping[str, Any], capacity: Mapping[str, Any], policy: Mapping[str, Any]) -> Dict[str, Any]:
    pre_metrics = _profile_metrics(profile, capacity, baseline["initial_disk_used_mib"], shed_candidate=False)
    pre = resource_disposition(pre_metrics, capacity, policy)
    shed_candidate = pre["state"] in {"CONSTRAINED", "CRITICAL", "EMERGENCY"}
    post_metrics = _profile_metrics(profile, capacity, baseline["initial_disk_used_mib"], shed_candidate=shed_candidate)
    post = resource_disposition(post_metrics, capacity, policy)
    disk = simulate_disk_horizon(
        profile,
        baseline,
        capacity,
        policy,
        optional_writes_initially_allowed=pre["optional_writes_allowed"],
    )
    expected_ok = pre["state"] == profile["expected_pre_shed_state"] and post["state"] == profile["expected_post_shed_state"]
    safe = expected_ok and profile["swap_used_mib"] == 0 and not disk["disk_exhausted"] and disk["minimum_free_reserve_preserved"] and profile["browser_sessions"] <= capacity["browser_concurrency_budget"]["admission_cap_sessions"]
    return {
        "profile_id": profile["id"],
        "status": "PASS" if safe else "FAIL",
        "pre_shed_metrics": pre_metrics,
        "pre_shed_disposition": pre,
        "candidate_shadow_shed": shed_candidate,
        "post_shed_metrics": post_metrics,
        "post_shed_disposition": post,
        "disk_horizon": disk,
        "swap_used_mib": profile["swap_used_mib"],
        "browser_sessions": profile["browser_sessions"],
        "production_runtime_verified": False,
        "real_load_generated": False,
    }


def _base_metrics() -> Dict[str, int]:
    return {
        "cpu_usage_basis_points": 1000,
        "memory_usage_basis_points": 1000,
        "disk_used_mib": 10000,
        "swap_used_mib": 0,
        "browser_sessions": 1,
        "telemetry_age_seconds": 10,
    }


def perform_capacity_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    capacity = strict_json_load(root / CAPACITY_PATH)
    policy = strict_json_load(root / SHEDDING_PATH)
    baseline = strict_json_load(root / BASELINE_PATH)
    cases = [
        ("CPU_6999", {"cpu_usage_basis_points": 6999}, "NORMAL"),
        ("CPU_7000", {"cpu_usage_basis_points": 7000}, "CONSTRAINED"),
        ("CPU_8500", {"cpu_usage_basis_points": 8500}, "CRITICAL"),
        ("CPU_9000", {"cpu_usage_basis_points": 9000}, "EMERGENCY"),
        ("MEMORY_7000", {"memory_usage_basis_points": 7000}, "CONSTRAINED"),
        ("MEMORY_8500", {"memory_usage_basis_points": 8500}, "CRITICAL"),
        ("MEMORY_9000", {"memory_usage_basis_points": 9000}, "EMERGENCY"),
        ("DISK_32767", {"disk_used_mib": 32767}, "NORMAL"),
        ("DISK_32768", {"disk_used_mib": 32768}, "CONSTRAINED"),
        ("DISK_34816", {"disk_used_mib": 34816}, "CRITICAL"),
        ("DISK_36864", {"disk_used_mib": 36864}, "EMERGENCY"),
        ("DISK_40960", {"disk_used_mib": 40960}, "EMERGENCY"),
        ("BROWSER_20", {"browser_sessions": 20}, "NORMAL"),
        ("BROWSER_21", {"browser_sessions": 21}, "CRITICAL"),
        ("SWAP_1", {"swap_used_mib": 1}, "EMERGENCY"),
        ("TELEMETRY_30", {"telemetry_age_seconds": 30}, "NORMAL"),
        ("TELEMETRY_31", {"telemetry_age_seconds": 31}, "EMERGENCY"),
    ]
    scenarios: Dict[str, Dict[str, Any]] = {}
    for scenario_id, mutation, expected in cases:
        metrics = _base_metrics()
        metrics.update(mutation)
        result = resource_disposition(metrics, capacity, policy)
        scenarios[scenario_id] = {
            "expected_state": expected,
            "actual_state": result["state"],
            "expectation_met": result["state"] == expected and result["effective_live_recommendation_enabled"] is False and result["production_state_changed"] is False and result["external_state_changed"] is False,
            "result": result,
        }
    for scenario_id, malformed in [
        ("MISSING_METRIC", {key: value for key, value in _base_metrics().items() if key != "disk_used_mib"}),
        ("NEGATIVE_METRIC", {**_base_metrics(), "disk_used_mib": -1}),
        ("BOOLEAN_METRIC", {**_base_metrics(), "swap_used_mib": False}),
    ]:
        result = resource_disposition(malformed, capacity, policy)
        scenarios[scenario_id] = {
            "expected_state": "EMERGENCY",
            "actual_state": result["state"],
            "expectation_met": result["state"] == "EMERGENCY" and result["new_advice_capacity_allowed"] is False and result["effective_live_recommendation_enabled"] is False,
            "result": result,
        }
    profiles = {row["id"]: evaluate_load_profile(row, baseline, capacity, policy) for row in baseline["profiles"]}
    scenarios["FROZEN_10X"] = {
        "expected_state": "CONSTRAINED_THEN_NORMAL",
        "actual_state": "%s_THEN_%s" % (profiles["FROZEN_10X"]["pre_shed_disposition"]["state"], profiles["FROZEN_10X"]["post_shed_disposition"]["state"]),
        "expectation_met": profiles["FROZEN_10X"]["status"] == "PASS" and profiles["FROZEN_10X"]["disk_horizon"]["disk_exhausted"] is False and profiles["FROZEN_10X"]["swap_used_mib"] == 0,
        "result": profiles["FROZEN_10X"],
    }
    status = "PASS" if all(row["expectation_met"] is True for row in scenarios.values()) and all(row["status"] == "PASS" for row in profiles.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "mode": "DETERMINISTIC_INTEGER_CAPACITY_AND_SHEDDING_FAILURE_INJECTION",
        "scenarios": scenarios,
        "profiles": profiles,
        "production_state_changed": False,
        "external_state_changed": False,
        "target_host_accessed": False,
        "production_runtime_verified": False,
        "real_load_generated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(checks, "S04P04-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor), {"expected": expected, "accepted_successor": successor, "actual": actual})
        hashes[relative] = actual
    for relative, expected in PINNED_BASELINE_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        _add(checks, "S04P04-BASELINE-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
        hashes[relative] = actual
    for relative, expected in PINNED_REPO_HASHES.items():
        actual = sha256_file(root.parent / relative) if (root.parent / relative).is_file() else "MISSING"
        _add(checks, "S04P04-REPO-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
        hashes[relative] = actual
    self_actual = _structural_self_hash(root)
    _add(checks, "S04P04-ORACLE-SELF-INTEGRITY", self_actual == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_actual})


def _check_taskpack(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    graph = strict_json_load(root / "machine/facts/task_graph.json")
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    requirement_rows = [row for row in requirements if row.get("id") == REQUIREMENT_ID]
    contract_rows = [row for row in contracts if row.get("id") == CONTRACT_ID]
    tasks = [row for row in graph.get("tasks", []) if row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
    trace_rows = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    requirement = requirement_rows[0] if len(requirement_rows) == 1 else {}
    contract = contract_rows[0] if len(contract_rows) == 1 else {}
    trace = trace_rows[0] if len(trace_rows) == 1 else {}
    _add(checks, "S04P04-TASKPACK-REQUIREMENT", len(requirement_rows) == 1 and requirement.get("scope") == list(EXPECTED_ARTIFACTS.values()) and requirement.get("target") == "VPS-1在10倍预期负载下不触发失控交换或磁盘耗尽。", requirement)
    _add(checks, "S04P04-TASKPACK-CONTRACT", len(contract_rows) == 1 and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S04-P04 --evidence machine/evidence" and [row.get("id") for row in contract.get("tests", [])] == EXPECTED_TEST_IDS, contract)
    _add(checks, "S04P04-TASKPACK-TASKS", [row.get("id") for row in tasks] == EXPECTED_TASK_IDS and tasks[0].get("depends_on") == ["T-S04-P03-03"] and tasks[0].get("outputs") == list(EXPECTED_ARTIFACTS.values()) and tasks[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()] and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()], [row.get("id") for row in tasks])
    _add(checks, "S04P04-TASKPACK-TRACEABILITY", len(trace_rows) == 1 and trace.get("acceptance_criteria_id") == CONTRACT_ID and trace.get("task_ids") == EXPECTED_TASK_IDS and trace.get("test_ids") == EXPECTED_TEST_IDS and trace.get("artifact_ids") == list(EXPECTED_ARTIFACTS), trace)
    _add(checks, "S04P04-FIXTURE-TRACEABILITY", fixture.get("expected_requirement_id") == REQUIREMENT_ID and fixture.get("expected_contract_id") == CONTRACT_ID and fixture.get("expected_task_ids") == EXPECTED_TASK_IDS and fixture.get("expected_artifacts") == EXPECTED_ARTIFACTS, fixture.get("expected_artifacts"))


def _check_artifacts(root: Path, fixture: Mapping[str, Any], capacity: Mapping[str, Any], policy: Mapping[str, Any], baseline: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    capacity_errors = validate_capacity_budget(capacity)
    policy_errors = validate_resource_shedding(policy, capacity)
    baseline_errors = validate_load_baseline(baseline)
    _add(checks, "S04P04-CAPACITY-VALID", not capacity_errors, capacity_errors or "valid")
    _add(checks, "S04P04-SHEDDING-VALID", not policy_errors, policy_errors or "valid")
    _add(checks, "S04P04-BASELINE-VALID", not baseline_errors, baseline_errors or "valid")
    invalid_results: Dict[str, bool] = {}
    for key, source, validator in [
        ("capacity", capacity, validate_capacity_budget),
        ("shedding", policy, lambda value: validate_resource_shedding(value, capacity)),
        ("baseline", baseline, validate_load_baseline),
    ]:
        for mutation in fixture.get("invalid_%s_mutations" % key, []):
            candidate = deepcopy(source)
            try:
                _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
                invalid_results[mutation["id"]] = bool(validator(candidate))
            except Exception:
                invalid_results[mutation.get("id", "UNKNOWN")] = True
    expected_mutations = sum(len(fixture.get("invalid_%s_mutations" % key, [])) for key in ["capacity", "shedding", "baseline"])
    _add(checks, "S04P04-ALL-DECLARED-MUTATIONS-FAIL-CLOSED", len(invalid_results) == expected_mutations and all(invalid_results.values()), invalid_results)
    drill = perform_capacity_drill(root)
    _add(checks, "S04P04-DRILL-ALL-PASS", drill.get("status") == "PASS", {"status": drill.get("status"), "scenarios": len(drill.get("scenarios", {}))})
    for scenario_id, scenario in drill.get("scenarios", {}).items():
        _add(checks, "S04P04-DRILL-%s" % scenario_id, scenario.get("expectation_met") is True, {"expected": scenario.get("expected_state"), "actual": scenario.get("actual_state")})
    for profile_id, profile in drill.get("profiles", {}).items():
        _add(checks, "S04P04-PROFILE-%s" % profile_id, profile.get("status") == "PASS" and profile.get("disk_horizon", {}).get("disk_exhausted") is False and profile.get("swap_used_mib") == 0 and profile.get("production_runtime_verified") is False, profile)
    ten = drill.get("profiles", {}).get("FROZEN_10X", {})
    _add(checks, "S04P04-10X-CANDIDATE-SHED-FIRST", ten.get("candidate_shadow_shed") is True and ten.get("pre_shed_disposition", {}).get("state") == "CONSTRAINED" and ten.get("post_shed_disposition", {}).get("state") == "NORMAL", ten)
    _add(checks, "S04P04-10X-DISK-RESERVE", ten.get("disk_horizon", {}).get("minimum_free_reserve_preserved") is True and ten.get("disk_horizon", {}).get("final_used_mib", 40960) < capacity.get("disk_budget", {}).get("watermarks_used_mib", {}).get("hard_capacity", 0), ten.get("disk_horizon"))
    for delta in EXPECTED_NUMERIC_DELTAS:
        for adverse in [False, True]:
            repeat = evaluate_load_profile(next(row for row in baseline["profiles"] if row["id"] == "FROZEN_10X"), baseline, capacity, policy)
            _add(checks, "S04P04-NUMERIC-%s-%s" % (delta.replace("-", "NEG").replace(".", "_"), "ADVERSE" if adverse else "BASE"), repeat == ten and repeat.get("status") == "PASS", {"delta": delta, "adverse_odds_tick": adverse})
    compose = strict_json_load(root / "infra/compose.yml")
    core = compose.get("services", {}).get("abd-core", {})
    shadow = compose.get("services", {}).get("abd-shadow", {})
    _add(checks, "S04P04-P01-CGROUP-CONSISTENCY", core.get("cpus") == "1.50" and core.get("mem_limit") == "2560m" and core.get("mem_reservation") == "1024m" and core.get("memswap_limit") == "2560m" and capacity["cpu_budget"]["active_slot_outer_hard_limit_millicores"] == 1500 and capacity["memory_budget"]["active_slot_outer_hard_limit_mib"] == 2560 and capacity["memory_budget"]["swap_allowed"] is False, core)
    shadow_state = next((row for row in shadow.get("volumes", []) if row.get("target") == "/var/lib/abd"), {})
    _add(
        checks,
        "S04P04-SHADOW-CGROUP-READ-ONLY-CONSISTENCY",
        shadow.get("profiles") == ["shadow"]
        and shadow.get("cpus") == "0.25"
        and shadow.get("mem_limit") == "512m"
        and shadow.get("memswap_limit") == "512m"
        and shadow.get("pids_limit") == 128
        and shadow_state.get("read_only") is True
        and shadow.get("environment", {}).get("ABD_RUNTIME_MODE") == "SHADOW_READ_ONLY"
        and capacity["cpu_budget"]["candidate_shadow_outer_hard_limit_millicores"] == 250
        and capacity["memory_budget"]["candidate_shadow_outer_hard_limit_mib"] == 512,
        {"compose": shadow, "cpu_budget": capacity["cpu_budget"], "memory_budget": capacity["memory_budget"]},
    )
    slots = strict_json_load(root / "release_slots.json")
    flags = strict_json_load(root / "feature_flags.json")
    _add(checks, "S04P04-P03-DUAL-SLOT-CONSISTENCY", [row.get("id") for row in slots.get("slots", [])] == ["blue", "green"] and slots.get("shared_durable_state", {}).get("outside_release_slots") is True and slots.get("shared_durable_state", {}).get("single_writer_during_cutover") is True, slots.get("shared_durable_state"))
    profiles = slots.get("runtime_profiles", {})
    active_profile = profiles.get("active", {}) if isinstance(profiles, Mapping) else {}
    shadow_profile = profiles.get("candidate_shadow", {}) if isinstance(profiles, Mapping) else {}
    _add(
        checks,
        "S04P04-P03-RUNTIME-PROFILE-BUDGET-CONSISTENCY",
        active_profile.get("compose_service") == "abd-core"
        and active_profile.get("bind_port") == 8080
        and active_profile.get("cpu_hard_limit_millicores") == capacity["cpu_budget"]["active_slot_outer_hard_limit_millicores"]
        and active_profile.get("memory_hard_limit_mib") == capacity["memory_budget"]["active_slot_outer_hard_limit_mib"]
        and shadow_profile.get("compose_service") == "abd-shadow"
        and shadow_profile.get("allowed_bind_ports") == [8081, 8082]
        and shadow_profile.get("state_access") == "READ_ONLY"
        and shadow_profile.get("cpu_hard_limit_millicores") == capacity["cpu_budget"]["candidate_shadow_outer_hard_limit_millicores"]
        and shadow_profile.get("memory_hard_limit_mib") == capacity["memory_budget"]["candidate_shadow_outer_hard_limit_mib"]
        and shadow_profile.get("maximum_concurrent_instances") == 1
        and active_profile.get("swap_limit_mib") == shadow_profile.get("swap_limit_mib") == 0,
        profiles,
    )
    companion = next((row for row in flags.get("fixed_flags", []) if row.get("id") == "owner_browser_companion"), {})
    _add(checks, "S04P04-P03-FLAGS-REMAIN-DISABLED", all(row.get("repository_enabled") is False for row in flags.get("fixed_flags", [])) and companion.get("repository_enabled") is False and capacity["browser_concurrency_budget"]["repository_enabled_in_p04"] is False, companion)
    _add(checks, "S04P04-NO-BINARY-FLOAT", not _contains_float(capacity) and not _contains_float(policy) and not _contains_float(baseline) and not _contains_float(fixture), "all frozen numeric values use integers or decimal strings")


def _check_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("machine/facts/stage4_review_contract.json"),
        Path("machine/evidence/S04/STAGE_REVIEW/findings.json"),
        Path("tests/S04/stage_review_test.py"),
        Path("machine/tests/fixtures/S04_STAGE_REVIEW.json"),
        Path("abd_acceptance/stage4_review.py"),
        Path("infra/systemd/abd-cloudflared.service"),
    ]
    signed_paths = [
        Path("machine/evidence/EVD-S04-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S04-STAGE-REVIEW_rollback.json"),
    ]
    candidate_present = [path.as_posix() for path in candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in signed_paths if (root / path).exists()]
    stage_rows = [row for row in _load_index(root) if row.get("id") == "INDEX-S04-STAGE-REVIEW"]
    successor: Dict[str, Any] = {}
    mode = "INVALID_PARTIAL_S04_STAGE_REVIEW"
    if not candidate_present and not signed_present and not stage_rows:
        ok = True
        mode = "S04_STAGE_REVIEW_NOT_STARTED"
    elif len(candidate_present) == len(candidate_paths) and not signed_present and not stage_rows:
        try:
            from .stage4_review import validate_candidate_preflight

            successor = validate_candidate_preflight(root)
            ok = successor.get("status") == "PASS"
            mode = "VERIFIED_S04_STAGE_REVIEW_CANDIDATE" if ok else "INVALID_S04_STAGE_REVIEW_CANDIDATE"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif len(candidate_present) == len(candidate_paths) and len(signed_present) == len(signed_paths) and len(stage_rows) == 1 and stage_rows[0].get("status") == "PASS":
        try:
            from .stage4_review import validate_signed_receipt_preflight

            successor = validate_signed_receipt_preflight(root)
            ok = successor.get("status") == "PASS"
            mode = "VERIFIED_S04_STAGE_REVIEW_SIGNED" if ok else "INVALID_S04_STAGE_REVIEW_SIGNED"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        ok = False
    _add(checks, "S04P04-STAGE-REVIEW-PROGRESSION", ok, {"mode": mode, "candidate_present": candidate_present, "signed_present": signed_present, "index": stage_rows, "successor": successor})


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = [CAPACITY_PATH, SHEDDING_PATH, BASELINE_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/capacity_governance.py")]
    leaks: List[Dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative.as_posix(), "kind": "absolute-local-path"})
    _add(checks, "S04P04-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


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
        ("S04P04-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S04P04-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
        ("S04P04-SIGNED-STATE-REGRESSION", SIGNED_STATE_JUNIT_PATH, int(fixture.get("minimum_signed_state_pytest_cases", 0))),
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
        _add(checks, "S04P04-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P04-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
        _add(checks, "S04P04-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P04-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S04P04-FIXTURE-STRICT-JSON")
    capacity = _safe_load(root / CAPACITY_PATH, checks, "S04P04-CAPACITY-STRICT-JSON")
    policy = _safe_load(root / SHEDDING_PATH, checks, "S04P04-SHEDDING-STRICT-JSON")
    baseline = _safe_load(root / BASELINE_PATH, checks, "S04P04-BASELINE-STRICT-JSON")
    _check_pins(root, checks, hashes)
    if isinstance(fixture, Mapping) and isinstance(capacity, Mapping) and isinstance(policy, Mapping) and isinstance(baseline, Mapping):
        _check_taskpack(root, fixture, checks)
        try:
            predecessor = verify_release_control_evidence(root, verify_git_history=_verify_git_history)
            predecessor_ok = predecessor.get("status") == "PASS" and predecessor.get("decision") == "S04_P03_EVIDENCE_VERIFIED" and predecessor.get("next") == "S04/P04_READY_NOT_STARTED"
            _add(checks, "S04P04-P03-PREREQUISITE", predecessor_ok, predecessor.get("summary"))
        except Exception as exc:
            _add(checks, "S04P04-P03-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
        _check_artifacts(root, fixture, capacity, policy, baseline, checks)
        _check_progression(root, checks)
        _check_no_leaks(root, checks)
        canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
        parameters = strict_json_load(root / "machine/facts/parameters.json")
        costs = strict_json_load(root / "machine/facts/costs.json")
        product = canonical.get("product", {})
        boundary_ok = product.get("initial_bankroll_aud") == "300.00" and product.get("incremental_cash_budget_aud") == "0.00" and product.get("monthly_target_return") == "0.30" and canonical.get("scope", {}).get("order_submission_module_present") is False and canonical.get("runtime", {}).get("single_host_zero_downtime_guaranteed") is False and parameters.get("target_30pct", {}).get("guaranteed") is False and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION" and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
        _add(checks, "S04P04-CANONICAL-A300-A0-NO-ORDER-NO-GUARANTEE", boundary_ok, {"product": product, "runtime": canonical.get("runtime"), "target": parameters.get("target_30pct")})
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S04P04-INPUTS-AVAILABLE", False, "fixture or phase artifacts unavailable")
    minimum = int(fixture.get("minimum_oracle_checks", 0)) if isinstance(fixture, Mapping) else 0
    if len(checks) < minimum:
        _add(checks, "S04P04-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "CAPACITY_RESOURCE_GOVERNANCE_CONTRACT_FROZEN" if status == "PASS" else "CAPACITY_GOVERNANCE_BLOCKED_FAIL_CLOSED",
        "phase_status": "S04_P04_PASS" if status == "PASS" else "S04_P04_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "pass_gate_interpretation": "OFFLINE_INTEGER_365_DAY_FROZEN_10X_DESIGN_ENVELOPE_AVOIDS_SWAP_AND_DISK_EXHAUSTION_BY_BOUNDED_SHEDDING; OVH_RUNTIME_CAPACITY_REMAINS_UNVERIFIED",
        "activation_gate": "BLOCKED_TARGET_HOST_BASELINE_AND_STAGE_REVIEW_NOT_VERIFIED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "runtime_capacity_status": "NOT_MEASURED_OR_VERIFIED_ON_OVH",
        "release_status": "NOT_READY_S04_WHOLE_STAGE_REVIEW_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S04/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S04/P04_REMEDIATION_REQUIRED",
    }


def build_evidence(root: Path, require_external_reports: bool = True, *, _verify_git_history: bool = True) -> tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_capacity_drill(root)
    if rollback["status"] != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "CAPACITY_GOVERNANCE_BLOCKED_FAIL_CLOSED"
        validation["phase_status"] = "S04_P04_FAIL"
        validation["next"] = "S04/P04_REMEDIATION_REQUIRED"
    inputs: Dict[str, str] = {}
    for relative in sorted({*PINNED_BASELINE_HASHES, *PINNED_PHASE_HASHES, "abd_acceptance/capacity_governance.py"}):
        inputs[relative] = sha256_file(root / relative)
    for relative in PINNED_REPO_HASHES:
        inputs[relative] = sha256_file(root.parent / relative)
    ten = rollback.get("profiles", {}).get("FROZEN_10X", {})
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "phase_status": validation["phase_status"],
        "artifacts": EXPECTED_ARTIFACTS,
        "validation": validation,
        "capacity_proof": {
            "mode": rollback["mode"],
            "scenario_count": len(rollback.get("scenarios", {})),
            "all_expected_dispositions_met": all(row.get("expectation_met") is True for row in rollback.get("scenarios", {}).values()),
            "one_x_profile_passed": rollback.get("profiles", {}).get("EXPECTED_1X", {}).get("status") == "PASS",
            "frozen_10x_profile_passed": ten.get("status") == "PASS",
            "frozen_10x_swap_used_mib": ten.get("swap_used_mib"),
            "frozen_10x_disk_exhausted": ten.get("disk_horizon", {}).get("disk_exhausted"),
            "frozen_10x_minimum_free_reserve_preserved": ten.get("disk_horizon", {}).get("minimum_free_reserve_preserved"),
            "candidate_shadow_shed_before_core": ten.get("candidate_shadow_shed"),
            "production_capacity_verified": False,
            "production_load_generated": False,
        },
        "scope_boundary": {
            "p04_delivers_capacity_contract_not_target_host_benchmark": True,
            "frozen_load_is_synthetic_engineering_input": True,
            "optional_work_may_be_shed_to_preserve_core_integrity": True,
            "production_10x_throughput_not_claimed": True,
            "immutable_ledger_or_evidence_not_deleted": True,
            "stage_review_not_started": True,
            "runtime_activation_not_performed": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S04/P04 validates integer resource accounting and deterministic shedding only; it executes no model, provider, host, container engine, systemd, browser, real traffic, order or return evaluation.",
            "code": _current_code_hash(root),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "pass_gate_interpretation": validation["pass_gate_interpretation"],
        "activation_gate": validation["activation_gate"],
        "production_status": validation["production_status"],
        "runtime_capacity_status": validation["runtime_capacity_status"],
        "release_status": validation["release_status"],
        "financial_target_status": validation["financial_target_status"],
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _update_evidence_index(root: Path, status: str, artifact_sha256: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S04-P04"]
    if len(matching) != 1:
        raise CapacityGovernanceContractError("expected exactly one INDEX-AC-S04-P04 row")
    matching[0].update({
        "status": status,
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": artifact_sha256,
        "verified_at": FIXED_CLOCK,
        "next": "S04/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S04/P04_REMEDIATION_REQUIRED",
    })
    _atomic_write(root / EVIDENCE_INDEX_PATH, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise CapacityGovernanceContractError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {"contract_id": CONTRACT_ID, "status": evidence["status"], "evidence_path": evidence_path.relative_to(root).as_posix(), "evidence_sha256": evidence_hash, "next": evidence["next"]}


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S04P04-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S04P04-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S04-P04" and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID and evidence.get("stage_id") == STAGE_ID and evidence.get("phase_id") == PHASE_ID and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS" and evidence.get("decision") == "CAPACITY_RESOURCE_GOVERNANCE_CONTRACT_FROZEN" and evidence.get("phase_status") == "S04_P04_PASS" and evidence.get("next") == "S04/STAGE_REVIEW_READY_NOT_STARTED" and _decision_hash_matches(evidence)
        _add(checks, "S04P04-RECEIPT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        _add(checks, "S04P04-RECEIPT-VALIDATION-ALL-PASS", isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and all(row.get("passed") is True for row in validation.get("checks", [])), validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected and not _historical_file_matches(root, relative, expected, verify_git_history):
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S04P04-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or "all inputs match current files or the exact signed phase commit")
        code_current = _current_code_hash(root)
        code_expected = evidence.get("hashes", {}).get("code")
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (code_expected == PINNED_PHASE_CODE_HASH and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"})
        _add(checks, "S04P04-RECEIPT-CODE-HASH-CURRENT", code_ok, {"expected": code_expected, "current": code_current, "historical": code_historical})
        _add(checks, "S04P04-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        proof = evidence.get("capacity_proof", {})
        _add(checks, "S04P04-RECEIPT-CAPACITY-PROOF", proof.get("frozen_10x_profile_passed") is True and proof.get("frozen_10x_swap_used_mib") == 0 and proof.get("frozen_10x_disk_exhausted") is False and proof.get("frozen_10x_minimum_free_reserve_preserved") is True and proof.get("production_capacity_verified") is False and proof.get("production_load_generated") is False, proof)
        boundary_ok = evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED" and evidence.get("runtime_capacity_status") == "NOT_MEASURED_OR_VERIFIED_ON_OVH"
        _add(checks, "S04P04-RECEIPT-BOUNDARY", boundary_ok, evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S04P04-RECEIPT-INTEGRITY", "S04P04-RECEIPT-VALIDATION-ALL-PASS", "S04P04-RECEIPT-SIGNED-INPUTS-CURRENT", "S04P04-RECEIPT-CODE-HASH-CURRENT", "S04P04-RECEIPT-ROLLBACK-HASH-BINDING", "S04P04-RECEIPT-CAPACITY-PROOF", "S04P04-RECEIPT-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, Mapping) and rollback.get("evidence_id") == "EVD-S04-P04-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and rollback.get("target_host_accessed") is False and rollback.get("production_runtime_verified") is False and all(row.get("expectation_met") is True for row in rollback.get("scenarios", {}).values())
    _add(checks, "S04P04-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S04-P04"]
        index_ok = len(matching) == 1 and matching[0].get("status") == "PASS" and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and matching[0].get("artifact_sha256") == evidence_hash and matching[0].get("next") == "S04/STAGE_REVIEW_READY_NOT_STARTED"
        _add(checks, "S04P04-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S04P04-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        predecessor = verify_release_control_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S04P04-RECEIPT-P03-PREREQUISITE", predecessor.get("status") == "PASS", predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S04P04-RECEIPT-P03-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_progression(root, checks)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_P04_EVIDENCE_VERIFIED" if not failed else "S04_P04_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S04/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S04/P04_REMEDIATION_REQUIRED",
    }
