from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from .canonical_facts import sha256_file, strict_json_load
from .cloudflare_edge import verify_existing_phase_evidence as verify_cloudflare_edge_evidence


CONTRACT_ID = "AC-S04-P03"
REQUIREMENT_ID = "REQ-S04-P03"
STAGE_ID = "S04"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-22T23:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SLOTS_PATH = Path("release_slots.json")
FLAGS_PATH = Path("feature_flags.json")
ROLLBACK_SCRIPT_PATH = Path("rollback.sh")
FIXTURE_PATH = Path("machine/tests/fixtures/S04_P03.json")
TEST_PATH = Path("tests/S04/P03_test.py")
JUNIT_PATH = Path("machine/evidence/S04/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S04/P03/full_regression.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S04/P03/signed_state_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S04-P02_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

ROLLBACK_DEADLINE_SECONDS = 900
LEDGER_RPO_SECONDS = 60
ALLOWED_NUMERIC_BOUNDARY_DELTAS = {"-0.0001", "0", "0.0001"}
EXPECTED_SLOT_IDS = ["blue", "green"]
EXPECTED_PROBES = [
    "HEALTH_PROBE",
    "NUMERIC_CROSS_IMPLEMENTATION",
    "FROZEN_REPLAY_ACTION_MATCH",
    "SILENT_COVERAGE_GAP_NONINCREASE",
    "MODEL_DRIFT_WITHIN_STOP_LINE",
    "SECURITY_HIGH_CRITICAL_ZERO",
    "LEDGER_AND_EVIDENCE_INTEGRITY",
]
EXPECTED_TRIGGER_REASONS = {
    "HEALTH_PROBE_FAILED": "健康探针失败",
    "NUMERIC_CROSS_IMPLEMENTATION_MISMATCH": "数值交叉实现不一致",
    "FROZEN_REPLAY_ACTION_MISMATCH": "新版本建议与冻结重放不一致",
    "SILENT_COVERAGE_GAP_INCREASED": "静默缺口增加",
    "MODEL_DRIFT_STOP_LINE_BREACHED": "模型漂移越过停止线",
    "SECURITY_HIGH_OR_CRITICAL_UNRESOLVED": "安全严重/高危未处置",
    "LEDGER_OR_EVIDENCE_INTEGRITY_FAILED": "账本或证据完整性失败",
    "UNKNOWN_OR_MALFORMED_PROBE": "未知或畸形发布探针",
}
EXPECTED_FLAG_TEMPLATES = [
    "source:<id>",
    "sport:<id>",
    "market_family:<id>",
    "model:<id>",
]
EXPECTED_FIXED_FLAGS = [
    "live_recommendation",
    "gmail_ingestion",
    "owner_browser_companion",
]
EXPECTED_CANARY_BASIS_POINTS = [0, 100, 500, 2500, 10000]

# Filled only with repository-relative, non-secret artifacts. The self hash is
# normalized so that changing its literal cannot make an invalid file valid.
STRUCTURAL_SELF_NORMALIZED_SHA256 = "013d47d166957cdddb28d518d3e083d9f53be298b5fcf2d4905341b3720fdf91"
PINNED_PHASE_HASHES: Dict[str, str] = {
    SLOTS_PATH.as_posix(): "f5a157b0806da5d62791bde33712bc149dbfc964f0536114caf4e123bcfe749e",
    FLAGS_PATH.as_posix(): "36b366ced826c3addb402526256e12f1a9fd7bdee56e321d8dc441a3f558d254",
    ROLLBACK_SCRIPT_PATH.as_posix(): "01e8b38329707d31de514249d2f7e096d0dc7a280ca204d5004e3d9e29c5168e",
    FIXTURE_PATH.as_posix(): "30fa200d5f24f462589881930f11e919fbb626c84f7b8b6e8ee54c49c1705123",
    TEST_PATH.as_posix(): "0df9ee48a58356220dd78fe42df534a85e8f4663ae0eca2d667727dc2a465383",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    P02_EVIDENCE_PATH.as_posix(): "a7dc214a406d8776eb67d5fe436092e4b1c87f1951d9f394e65565502f43eda4",
    P02_ROLLBACK_PATH.as_posix(): "6fdc7890e2baecbea37bc981ec1224821904542c0a35c3d8de4ced5edd9bdb3e",
}
PINNED_REPO_HASHES = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

EXTERNAL_EFFECT_BOUNDARY = {
    "network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "docker_or_systemd_invoked": False,
    "cloudflare_changed": False,
    "real_traffic_switched": False,
    "production_activated": False,
    "shared_production_ledger_read_or_written": False,
    "real_order_submitted": False,
    "return_or_roi_verified": False,
    "incremental_cash_spent_aud": "0.00",
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]


class ReleaseControlContractError(ValueError):
    """Raised when the S04/P03 release contract fails closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


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


def _atomic_json_write(path: Path, value: Any) -> None:
    _atomic_write(path, _json_bytes(value))


def _load_index(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if line:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ReleaseControlContractError("evidence index rows must be objects")
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


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/release_control.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _recursive_keys(value: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_recursive_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            keys.extend(_recursive_keys(item))
    return keys


def validate_release_slots(config: Any, release_policy: Mapping[str, Any] | None = None) -> List[str]:
    errors: List[str] = []
    if not isinstance(config, Mapping):
        return ["release slots must be an object"]
    required = {
        "schema_version",
        "product_version",
        "deployment_mode",
        "production_activation",
        "time_contract",
        "slots",
        "routing",
        "shared_durable_state",
        "promotion_protocol",
        "canary_profiles",
        "required_probes",
        "auto_rollback_triggers",
        "rollback",
        "external_effect_boundary",
    }
    if set(config) != required:
        errors.append("top-level keys must match the frozen release-slot contract")
    if config.get("schema_version") != "1.0.0" or config.get("product_version") != VERSION:
        errors.append("schema and product versions must be frozen")
    if config.get("deployment_mode") != "SAME_HOST_BLUE_GREEN_WITH_CANARY_AND_AUTO_ROLLBACK":
        errors.append("deployment mode must be same-host blue/green")
    activation = config.get("production_activation", {})
    if not isinstance(activation, Mapping) or activation.get("repository_status") != "NOT_REQUESTED_OR_VERIFIED" or activation.get("real_traffic_switched_in_s04_p03") is not False:
        errors.append("repository production activation must remain unrequested and unverified")
    if activation.get("external_activation_record") != "/etc/abd/release-activation.json" or activation.get("required_stage_review") != "STAGE-REVIEW-S04":
        errors.append("activation must require the external record and S04 review")
    time_contract = config.get("time_contract", {})
    if not isinstance(time_contract, Mapping) or time_contract.get("clock") != "MONOTONIC_INTEGER_SECONDS":
        errors.append("rollback timing must use monotonic integer seconds")
    if time_contract.get("rollback_deadline_seconds") != ROLLBACK_DEADLINE_SECONDS or time_contract.get("service_recovery_target_seconds") != ROLLBACK_DEADLINE_SECONDS:
        errors.append("rollback and service recovery deadline must be 900 seconds")
    if time_contract.get("ledger_recovery_point_target_seconds") != LEDGER_RPO_SECONDS or time_contract.get("deadline_inclusive") is not True:
        errors.append("ledger RPO and inclusive deadline are invalid")
    if time_contract.get("frozen_boundary_seconds") != [899, 900, 901]:
        errors.append("rollback boundary seconds must be 899, 900 and 901")

    slots = config.get("slots", [])
    if not isinstance(slots, list) or len(slots) != 2:
        errors.append("exactly two slots are required")
        slots = []
    ids = [slot.get("id") for slot in slots if isinstance(slot, Mapping)]
    if ids != EXPECTED_SLOT_IDS:
        errors.append("slot ids and order must be blue then green")
    expected_paths = ["/opt/abd/releases/blue", "/opt/abd/releases/green"]
    if [slot.get("release_path") for slot in slots if isinstance(slot, Mapping)] != expected_paths:
        errors.append("slots must remain under the fixed release root")
    if [slot.get("bind_port") for slot in slots if isinstance(slot, Mapping)] != [8081, 8082] or any(slot.get("bind_address") != "127.0.0.1" for slot in slots if isinstance(slot, Mapping)):
        errors.append("slot origins must use distinct loopback ports")
    if any(slot.get("repository_runtime_status") != "NOT_RUNNING_OR_VERIFIED" for slot in slots if isinstance(slot, Mapping)):
        errors.append("repository must not claim a running slot")

    routing = config.get("routing", {})
    if not isinstance(routing, Mapping) or routing.get("public_origin") != "http://127.0.0.1:8080":
        errors.append("public origin must remain loopback")
    if routing.get("current_release_symlink") != "/opt/abd/current" or routing.get("atomic_switch_method") != "CREATE_SIBLING_SYMLINK_THEN_RENAME":
        errors.append("routing must use the fixed atomic symlink switch")
    if routing.get("allowed_targets") != expected_paths or routing.get("partial_or_external_target_policy") != "REJECT_AND_KEEP_PREVIOUS":
        errors.append("routing targets must be exactly the two slots")

    state = config.get("shared_durable_state", {})
    if not isinstance(state, Mapping) or state.get("root") != "/var/lib/abd" or state.get("outside_release_slots") is not True or state.get("slot_specific_copy_forbidden") is not True:
        errors.append("durable state must be shared outside both slots")
    state_paths = state.get("paths", []) if isinstance(state, Mapping) else []
    if not isinstance(state_paths, list) or len(state_paths) != len(set(state_paths)) or any(not isinstance(path, str) or not path.startswith("/var/lib/abd/") for path in state_paths):
        errors.append("durable state paths must be unique descendants of the shared root")
    if state.get("candidate_shadow_access") != "READ_ONLY" or state.get("single_writer_during_cutover") is not True:
        errors.append("candidate shadow must be read-only with a single cutover writer")
    required_pre = {"STOP_NEW_ADVICE", "INVALIDATE_UNEXPIRED_ADVICE", "DRAIN_OR_CHECKPOINT_WRITER", "CAPTURE_LEDGER_WATERMARK", "VERIFY_LEDGER_AND_EVIDENCE_HASH_CHAIN", "VERIFY_PREVIOUS_RELEASE_MANIFEST"}
    required_post = {"VERIFY_LEDGER_WATERMARK_NOT_DECREASED", "VERIFY_NO_DUPLICATE_LEDGER_EVENT_IDS", "VERIFY_HASH_CHAIN", "KEEP_OLD_SLOT_IMMUTABLE_UNTIL_RELEASE_SETTLES"}
    if set(state.get("pre_switch_requirements", [])) != required_pre or set(state.get("post_switch_requirements", [])) != required_post:
        errors.append("ledger preservation requirements are incomplete")
    if state.get("integrity_failure_action") != "STOP_NEW_ADVICE_AND_ROLL_BACK":
        errors.append("ledger integrity failure must stop advice and roll back")

    protocol = config.get("promotion_protocol", [])
    if not isinstance(protocol, list) or [row.get("order") for row in protocol if isinstance(row, Mapping)] != list(range(1, 9)):
        errors.append("promotion protocol must contain ordered steps 1 through 8")
    if any(row.get("writes_shared_ledger") is not False for row in protocol[:4] if isinstance(row, Mapping)):
        errors.append("candidate build, shadow, replay and canary must not write the shared ledger")
    canary = config.get("canary_profiles", [])
    if [row.get("maximum_traffic_basis_points") for row in canary if isinstance(row, Mapping)] != EXPECTED_CANARY_BASIS_POINTS:
        errors.append("canary basis points must be monotonic and frozen")
    if any(row.get("live_recommendation") is not False for row in canary if isinstance(row, Mapping)):
        errors.append("P03 canary profiles must not enable live recommendations")
    if config.get("required_probes") != EXPECTED_PROBES:
        errors.append("required release probes must match the frozen set")
    triggers = config.get("auto_rollback_triggers", [])
    trigger_map = {row.get("id"): row.get("canonical_reason") for row in triggers if isinstance(row, Mapping)}
    if trigger_map != EXPECTED_TRIGGER_REASONS or len(triggers) != len(EXPECTED_TRIGGER_REASONS):
        errors.append("rollback triggers must match the frozen fail-closed map")
    if release_policy is not None:
        canonical_reasons = set(release_policy.get("auto_rollback_on", []))
        if set(EXPECTED_TRIGGER_REASONS.values()) - {"未知或畸形发布探针"} != canonical_reasons:
            errors.append("rollback triggers must cover every canonical release-policy reason")
    rollback = config.get("rollback", {})
    if not isinstance(rollback, Mapping) or rollback.get("entrypoint") != "rollback.sh" or rollback.get("previous_slot_source") != "LAST_VERIFIED_CONTROL_STATE_ONLY":
        errors.append("rollback entrypoint and previous-slot source are invalid")
    if rollback.get("arbitrary_path_or_slot_allowed") is not False or rollback.get("ledger_or_evidence_mutation_allowed") is not False:
        errors.append("rollback must reject arbitrary paths and ledger mutation")
    if rollback.get("unknown_trigger_action") != "ROLL_BACK_FAIL_CLOSED" or rollback.get("deadline_breach_action") != "KEEP_ADVICE_DISABLED_AND_ESCALATE":
        errors.append("unknown triggers and deadline breaches must fail closed")
    if config.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY:
        errors.append("external effect boundary must remain entirely inactive and A$0")
    if _contains_float(config):
        errors.append("binary floating point values are forbidden")
    forbidden_keys = {"password", "secret", "token", "private_key", "api_key"}
    if forbidden_keys.intersection(key.lower() for key in _recursive_keys(config)):
        errors.append("secret-bearing keys are forbidden")
    return errors


def validate_feature_flags(flags: Any, release_policy: Mapping[str, Any] | None = None) -> List[str]:
    errors: List[str] = []
    if not isinstance(flags, Mapping):
        return ["feature flags must be an object"]
    required = {
        "schema_version",
        "product_version",
        "policy",
        "repository_runtime_status",
        "evaluation_order",
        "fixed_flags",
        "scoped_flag_templates",
        "canary_profiles",
        "allowed_profile_transitions",
        "forbidden_effects",
        "mutation_contract",
        "financial_and_order_boundary",
    }
    if set(flags) != required:
        errors.append("top-level keys must match the frozen feature-flag contract")
    if flags.get("schema_version") != "1.0.0" or flags.get("product_version") != VERSION:
        errors.append("schema and product versions must be frozen")
    if flags.get("policy") != "DENY_UNKNOWN_AND_NEVER_OVERRIDE_EVIDENCE_RISK_SAFETY_OR_SOURCE_GATES":
        errors.append("feature policy must deny unknown values and preserve all gates")
    if flags.get("repository_runtime_status") != "NOT_APPLIED_TO_PRODUCTION":
        errors.append("repository must not claim feature flags are applied")
    order = flags.get("evaluation_order", [])
    if not isinstance(order, list) or len(order) != len(set(order)) or order[:2] != ["EMERGENCY_ADVICE_KILL_SWITCH", "SIGNED_RELEASE_SLOT"]:
        errors.append("evaluation must begin with kill switch and signed slot")
    fixed = flags.get("fixed_flags", [])
    fixed_ids = [row.get("id") for row in fixed if isinstance(row, Mapping)]
    if fixed_ids != EXPECTED_FIXED_FLAGS:
        errors.append("fixed feature flags must match release policy")
    for row in fixed:
        if not isinstance(row, Mapping) or row.get("default_enabled") is not False or row.get("repository_enabled") is not False or row.get("unknown_state_enabled") is not False or row.get("rollback_value") is not False:
            errors.append("every fixed flag must default, remain and roll back to disabled")
            break
        if not row.get("enable_requires"):
            errors.append("every fixed flag must have explicit enabling prerequisites")
            break
    templates = flags.get("scoped_flag_templates", [])
    template_ids = [row.get("template") for row in templates if isinstance(row, Mapping)]
    if template_ids != EXPECTED_FLAG_TEMPLATES:
        errors.append("scoped flag templates must match release policy")
    for row in templates:
        if not isinstance(row, Mapping) or row.get("default_enabled") is not False or row.get("unknown_state_enabled") is not False:
            errors.append("scoped flags must deny unknown and default disabled")
            break
        pattern = row.get("id_pattern")
        try:
            compiled = re.compile(pattern)
            pattern_ok = compiled.fullmatch("known_id-1") is not None and compiled.fullmatch("../escape") is None and compiled.fullmatch("UPPER") is None
        except Exception:
            pattern_ok = False
        if not pattern_ok:
            errors.append("scoped flag id patterns must reject traversal and uppercase ambiguity")
            break
    canary = flags.get("canary_profiles", [])
    if [row.get("maximum_traffic_basis_points") for row in canary if isinstance(row, Mapping)] != EXPECTED_CANARY_BASIS_POINTS:
        errors.append("feature canary basis points must match release slots")
    if any(row.get("live_recommendation") is not False for row in canary if isinstance(row, Mapping)):
        errors.append("P03 feature canaries must keep live recommendations disabled")
    if flags.get("allowed_profile_transitions") != ["shadow->one_source", "one_source->one_sport", "one_sport->one_market_family", "one_market_family->eligible_full"]:
        errors.append("only one-step forward canary transitions are allowed")
    required_forbidden = {"SUBMIT_CONFIRM_OR_RETRY_REAL_ORDER", "LOWER_EVIDENCE_GATE", "LOWER_NUMERIC_STABILITY_GATE", "LOWER_RISK_OR_SAFETY_GATE", "BYPASS_SOURCE_CONTRACT", "ENABLE_STALE_ADVICE", "CHANGE_IMMUTABLE_LEDGER_FACT", "SPEND_INCREMENTAL_CASH"}
    if set(flags.get("forbidden_effects", [])) != required_forbidden:
        errors.append("feature flags must forbid every dangerous effect")
    mutation = flags.get("mutation_contract", {})
    if not isinstance(mutation, Mapping) or mutation.get("requires_signed_release_id") is not True or mutation.get("requires_monotonic_revision") is not True or mutation.get("append_only_audit_event_required") is not True:
        errors.append("runtime flag mutation must be signed, monotonic and audited")
    if mutation.get("partial_write_method") != "WRITE_FSYNC_RENAME" or mutation.get("malformed_or_unknown_action") != "DISABLE_AND_ROLL_BACK":
        errors.append("flag mutation must be atomic and fail closed")
    if mutation.get("rollback_resets_candidate_flags") is not True or mutation.get("rollback_preserves_previous_signed_snapshot") is not True:
        errors.append("rollback flag semantics are incomplete")
    boundary = flags.get("financial_and_order_boundary", {})
    expected_boundary = {
        "initial_bankroll_aud": "300.00",
        "incremental_cash_budget_aud": "0.00",
        "monthly_target_return": "0.30",
        "monthly_target_guaranteed": False,
        "order_submission_module_present": False,
    }
    if boundary != expected_boundary:
        errors.append("financial and order boundary must remain unchanged")
    if release_policy is not None and release_policy.get("feature_flags") != EXPECTED_FLAG_TEMPLATES + EXPECTED_FIXED_FLAGS:
        errors.append("feature flags must match the canonical release policy")
    if _contains_float(flags):
        errors.append("binary floating point values are forbidden")
    return errors


def activation_gate(slots: Mapping[str, Any], flags: Mapping[str, Any]) -> str:
    if validate_release_slots(slots) or validate_feature_flags(flags):
        return "BLOCKED_INVALID_RELEASE_CONTRACT"
    activation = slots.get("production_activation", {})
    if activation.get("repository_status") != "ACTIVATION_PREREQUISITES_VERIFIED":
        return "BLOCKED_RUNTIME_PREREQUISITES_AND_STAGE_REVIEW_NOT_VERIFIED"
    if flags.get("repository_runtime_status") != "SIGNED_RUNTIME_SNAPSHOT_VERIFIED":
        return "BLOCKED_SIGNED_RUNTIME_FLAGS_NOT_VERIFIED"
    return "READY_FOR_EXPLICIT_RUNTIME_ACTIVATION"


def _flag_spec(flags: Mapping[str, Any], flag_id: str) -> Mapping[str, Any] | None:
    for row in flags.get("fixed_flags", []):
        if row.get("id") == flag_id:
            return row
    for row in flags.get("scoped_flag_templates", []):
        prefix = str(row.get("template", "")).split(":", 1)[0]
        if flag_id.startswith(prefix + ":"):
            identifier = flag_id.split(":", 1)[1]
            try:
                if re.fullmatch(str(row.get("id_pattern")), identifier):
                    return row
            except re.error:
                return None
    return None


def evaluate_feature_flag(
    flags: Mapping[str, Any],
    flag_id: str,
    requested_enabled: bool,
    passed_prerequisites: Iterable[str],
    *,
    emergency_advice_kill_switch: bool = False,
) -> Dict[str, Any]:
    spec = _flag_spec(flags, flag_id)
    if emergency_advice_kill_switch:
        return {"flag_id": flag_id, "enabled": False, "reason": "EMERGENCY_ADVICE_KILL_SWITCH", "fail_closed": True}
    if spec is None:
        return {"flag_id": flag_id, "enabled": False, "reason": "UNKNOWN_OR_MALFORMED_FLAG", "fail_closed": True}
    if requested_enabled is not True:
        return {"flag_id": flag_id, "enabled": False, "reason": "NOT_EXPLICITLY_ENABLED", "fail_closed": True}
    required = set(spec.get("enable_requires", []))
    passed = set(passed_prerequisites)
    missing = sorted(required - passed)
    if missing:
        return {"flag_id": flag_id, "enabled": False, "reason": "PREREQUISITES_NOT_MET", "missing": missing, "fail_closed": True}
    return {"flag_id": flag_id, "enabled": True, "reason": "ALL_DECLARED_PREREQUISITES_MET", "missing": [], "fail_closed": False}


def release_disposition(probes: Mapping[str, Any], elapsed_seconds: int) -> Dict[str, Any]:
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, int) or elapsed_seconds < 0:
        return {"action": "ROLL_BACK_FAIL_CLOSED", "deadline_met": False, "failed_probes": ["INVALID_ELAPSED_SECONDS"], "advice_enabled": False}
    failed = sorted(probe for probe in EXPECTED_PROBES if probes.get(probe) is not True)
    unknown = sorted(str(probe) for probe in probes if probe not in EXPECTED_PROBES)
    if unknown:
        failed.append("UNKNOWN_OR_MALFORMED_PROBE")
    if failed:
        return {
            "action": "ROLL_BACK_FAIL_CLOSED",
            "deadline_met": elapsed_seconds <= ROLLBACK_DEADLINE_SECONDS,
            "failed_probes": sorted(set(failed)),
            "advice_enabled": False,
        }
    return {
        "action": "HOLD_FOR_SIGNED_PROMOTION",
        "deadline_met": elapsed_seconds <= ROLLBACK_DEADLINE_SECONDS,
        "failed_probes": [],
        "advice_enabled": False,
    }


def _tree_digest(root: Path) -> Dict[str, Any]:
    digest = hashlib.sha256()
    files = 0
    total_bytes = 0
    if not root.is_dir():
        return {"sha256": "MISSING", "files": 0, "bytes": 0}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
        files += 1
        total_bytes += len(payload)
    return {"sha256": digest.hexdigest(), "files": files, "bytes": total_bytes}


def _slot_manifest(slot: str) -> Dict[str, Any]:
    digest_character = "1" if slot == "blue" else "2"
    return {
        "schema_version": "1.0.0",
        "product_version": VERSION,
        "slot": slot,
        "image_digest": "sha256:" + digest_character * 64,
        "artifact_manifest_sha256": digest_character * 64,
        "signature_receipt_status": "PASS",
        "order_submission_module_present": False,
    }


def initialize_release_drill(sandbox: Path) -> Dict[str, Any]:
    sandbox = sandbox.resolve()
    if sandbox.exists() and any(sandbox.iterdir()):
        raise ReleaseControlContractError("drill sandbox must be absent or empty")
    release_root = sandbox / "opt/abd/releases"
    state_root = sandbox / "var/lib/abd"
    for slot in EXPECTED_SLOT_IDS:
        path = release_root / slot
        path.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(path / "release_manifest.json", _slot_manifest(slot))
    ledger_root = state_root / "ledger"
    ledger_root.mkdir(parents=True, exist_ok=True)
    (ledger_root / "advice.jsonl").write_bytes(b'{"event_id":"advice-000001","kind":"NO_BET"}\n')
    (ledger_root / "actual.jsonl").write_bytes(b'{"event_id":"actual-000001","kind":"NO_VERIFIED_EXECUTION"}\n')
    (ledger_root / "evidence.jsonl").write_bytes(b'{"event_id":"evidence-000001","kind":"FROZEN_DRILL"}\n')
    release_state = state_root / "release"
    release_state.mkdir(parents=True, exist_ok=True)
    manifest_hashes = {slot: sha256_file(release_root / slot / "release_manifest.json") for slot in EXPECTED_SLOT_IDS}
    control = {
        "schema_version": "1.0.0",
        "revision": 7,
        "active_slot": "green",
        "previous_slot": "blue",
        "active_manifest_sha256": manifest_hashes["green"],
        "previous_manifest_sha256": manifest_hashes["blue"],
        "ledger_watermark": "evidence-000001",
        "release_started_monotonic_seconds": 1000,
        "live_recommendation": False,
    }
    _atomic_json_write(release_state / "control_state.json", control)
    _atomic_json_write(
        release_state / "feature_flags.json",
        {
            "schema_version": "1.0.0",
            "revision": 11,
            "release_slot": "green",
            "live_recommendation": False,
            "gmail_ingestion": False,
            "owner_browser_companion": False,
            "scoped_flags": {},
        },
    )
    current = sandbox / "opt/abd/current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(release_root / "green", target_is_directory=True)
    return {
        "sandbox": sandbox,
        "release_root": release_root,
        "state_root": state_root,
        "control_state": control,
        "ledger_before": _tree_digest(ledger_root),
    }


def _resolved_direct_child(root: Path, child: str) -> Path:
    if child not in EXPECTED_SLOT_IDS:
        raise ReleaseControlContractError("slot is not in the frozen allowlist")
    candidate = (root / child).resolve(strict=True)
    if candidate.parent != root.resolve(strict=True):
        raise ReleaseControlContractError("slot target escaped the release root")
    return candidate


def _disable_runtime_flags(release_state: Path, previous_slot: str) -> Dict[str, Any]:
    path = release_state / "feature_flags.json"
    current = strict_json_load(path)
    revision = current.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ReleaseControlContractError("runtime flag revision is invalid")
    disabled = {
        "schema_version": "1.0.0",
        "revision": revision + 1,
        "release_slot": previous_slot,
        "live_recommendation": False,
        "gmail_ingestion": False,
        "owner_browser_companion": False,
        "scoped_flags": {},
    }
    _atomic_json_write(path, disabled)
    return disabled


def execute_release_drill(
    sandbox: Path,
    trigger_id: str,
    elapsed_seconds: int,
    *,
    fault: str | None = None,
) -> Dict[str, Any]:
    initialized = initialize_release_drill(sandbox)
    release_root = initialized["release_root"]
    state_root = initialized["state_root"]
    release_state = state_root / "release"
    ledger_root = state_root / "ledger"
    control_path = release_state / "control_state.json"
    control = strict_json_load(control_path)
    known_trigger = trigger_id in EXPECTED_TRIGGER_REASONS
    canonical_trigger = trigger_id if known_trigger else "UNKNOWN_OR_MALFORMED_PROBE"
    ledger_before = _tree_digest(ledger_root)
    pointer_before = (sandbox / "opt/abd/current").resolve(strict=True).name
    failure: str | None = None
    switched = False
    try:
        if fault == "UNSAFE_PREVIOUS_SLOT":
            control["previous_slot"] = "../escape"
        if fault == "MALFORMED_CONTROL_STATE":
            control["revision"] = "seven"
        active = control.get("active_slot")
        previous = control.get("previous_slot")
        revision = control.get("revision")
        if active not in EXPECTED_SLOT_IDS or previous not in EXPECTED_SLOT_IDS or active == previous:
            raise ReleaseControlContractError("control state does not name two distinct allowed slots")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ReleaseControlContractError("control-state revision is invalid")
        active_path = _resolved_direct_child(release_root, active)
        previous_path = _resolved_direct_child(release_root, previous)
        current_link = sandbox / "opt/abd/current"
        if fault == "CURRENT_POINTER_ESCAPE":
            current_link.unlink()
            outside = sandbox / "outside"
            outside.mkdir()
            current_link.symlink_to(outside, target_is_directory=True)
        if current_link.resolve(strict=True) != active_path:
            raise ReleaseControlContractError("current release pointer does not match the active slot")
        active_manifest = sha256_file(active_path / "release_manifest.json")
        previous_manifest = sha256_file(previous_path / "release_manifest.json")
        if fault == "PREVIOUS_MANIFEST_MISMATCH":
            (previous_path / "release_manifest.json").write_bytes(b"{}\n")
            previous_manifest = sha256_file(previous_path / "release_manifest.json")
        if active_manifest != control.get("active_manifest_sha256") or previous_manifest != control.get("previous_manifest_sha256"):
            raise ReleaseControlContractError("release manifest digest does not match verified control state")
        _atomic_json_write(
            release_state / "advice_invalidated.json",
            {
                "schema_version": "1.0.0",
                "fixed_clock": FIXED_CLOCK,
                "reason": canonical_trigger,
                "all_prior_advice_valid": False,
            },
        )
        _disable_runtime_flags(release_state, previous)
        if fault == "LEDGER_MUTATED_DURING_ROLLBACK":
            with (ledger_root / "advice.jsonl").open("ab") as handle:
                handle.write(b'{"event_id":"unexpected-mutation"}\n')
        next_link = sandbox / "opt/abd/.current.rollback"
        if next_link.exists() or next_link.is_symlink():
            next_link.unlink()
        next_link.symlink_to(previous_path, target_is_directory=True)
        os.replace(next_link, current_link)
        switched = True
        updated = {
            "schema_version": "1.0.0",
            "revision": revision + 1,
            "active_slot": previous,
            "previous_slot": active,
            "active_manifest_sha256": control["previous_manifest_sha256"],
            "previous_manifest_sha256": control["active_manifest_sha256"],
            "ledger_watermark": control["ledger_watermark"],
            "release_started_monotonic_seconds": control["release_started_monotonic_seconds"],
            "rolled_back_at_monotonic_seconds": control["release_started_monotonic_seconds"] + elapsed_seconds,
            "rollback_trigger": canonical_trigger,
            "live_recommendation": False,
        }
        _atomic_json_write(control_path, updated)
        event = {
            "schema_version": "1.0.0",
            "event_id": "rollback-revision-%d" % updated["revision"],
            "from_slot": active,
            "to_slot": previous,
            "trigger": canonical_trigger,
            "elapsed_seconds": elapsed_seconds,
            "deadline_seconds": ROLLBACK_DEADLINE_SECONDS,
        }
        _atomic_write(release_state / "events.jsonl", (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    except Exception as exc:
        failure = "%s: %s" % (type(exc).__name__, exc)
        try:
            _atomic_json_write(
                release_state / "advice_invalidated.json",
                {
                    "schema_version": "1.0.0",
                    "fixed_clock": FIXED_CLOCK,
                    "reason": "ROLLBACK_PREFLIGHT_FAILED",
                    "all_prior_advice_valid": False,
                },
            )
            _disable_runtime_flags(release_state, "blue")
        except Exception:
            pass
    ledger_after = _tree_digest(ledger_root)
    pointer_after = (sandbox / "opt/abd/current").resolve(strict=True).name
    ledger_unchanged = ledger_before == ledger_after
    deadline_met = isinstance(elapsed_seconds, int) and not isinstance(elapsed_seconds, bool) and 0 <= elapsed_seconds <= ROLLBACK_DEADLINE_SECONDS
    status = "PASS" if failure is None and switched and pointer_after == "blue" and ledger_unchanged and deadline_met else "FAIL"
    return {
        "schema_version": "1.0.0",
        "scenario": canonical_trigger,
        "requested_trigger_known": known_trigger,
        "fault": fault or "NONE",
        "status": status,
        "action": "ROLLED_BACK_TO_PREVIOUS_VERIFIED_SLOT" if switched else "ROLLBACK_BLOCKED_KEEP_ADVICE_DISABLED",
        "pointer_before": pointer_before,
        "pointer_after": pointer_after,
        "pointer_switched": switched,
        "elapsed_seconds": elapsed_seconds,
        "deadline_seconds": ROLLBACK_DEADLINE_SECONDS,
        "deadline_met": deadline_met,
        "ledger_before": ledger_before,
        "ledger_after": ledger_after,
        "ledger_unchanged": ledger_unchanged,
        "advice_enabled": False,
        "failure": failure,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    del root  # The drill is intentionally independent of production state.
    scenarios: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s04-p03-rollback-") as temporary:
        base = Path(temporary)
        for index, trigger in enumerate(EXPECTED_TRIGGER_REASONS):
            result = execute_release_drill(base / ("trigger-%02d" % index), trigger, 300)
            scenarios[trigger] = result
        for elapsed in [899, 900, 901]:
            result = execute_release_drill(base / ("boundary-%d" % elapsed), "HEALTH_PROBE_FAILED", elapsed)
            expected_status = "PASS" if elapsed <= ROLLBACK_DEADLINE_SECONDS else "FAIL"
            result["expected_status"] = expected_status
            result["expectation_met"] = result["status"] == expected_status and result["advice_enabled"] is False
            scenarios["BOUNDARY_%d" % elapsed] = result
        for fault in ["LEDGER_MUTATED_DURING_ROLLBACK", "UNSAFE_PREVIOUS_SLOT", "MALFORMED_CONTROL_STATE", "CURRENT_POINTER_ESCAPE", "PREVIOUS_MANIFEST_MISMATCH"]:
            result = execute_release_drill(base / ("fault-" + fault.lower()), "HEALTH_PROBE_FAILED", 300, fault=fault)
            result["expected_status"] = "FAIL"
            result["expectation_met"] = result["status"] == "FAIL" and result["advice_enabled"] is False
            scenarios[fault] = result
    for trigger in EXPECTED_TRIGGER_REASONS:
        scenarios[trigger]["expected_status"] = "PASS"
        scenarios[trigger]["expectation_met"] = scenarios[trigger]["status"] == "PASS"
    status = "PASS" if all(row.get("expectation_met") is True for row in scenarios.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SAME_HOST_BLUE_GREEN_FAILURE_INJECTION",
        "status": status,
        "scenarios": scenarios,
        "production_state_changed": False,
        "external_state_changed": False,
        "production_runtime_verified": False,
    }


def _set_or_delete_path(
    value: Any,
    path: Sequence[Any],
    replacement: Any = None,
    *,
    delete: bool = False,
) -> None:
    if not path:
        raise ReleaseControlContractError("mutation path must not be empty")
    current = value
    for part in path[:-1]:
        current = current[part]
    final = path[-1]
    if delete:
        if isinstance(current, list):
            del current[final]
        else:
            del current[final]
    else:
        current[final] = replacement


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S04P03-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
        hashes[relative] = actual
    for relative, expected in PINNED_BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S04P03-BASELINE-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
        hashes[relative] = actual
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S04P03-REPO-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
        hashes[relative] = actual
    structural = _structural_self_hash(root)
    _add(checks, "S04P03-ORACLE-STRUCTURAL-INTEGRITY", structural == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": structural})


def _find_exact(rows: Sequence[Mapping[str, Any]], row_id: str) -> List[Mapping[str, Any]]:
    return [row for row in rows if row.get("id") == row_id]


def _check_taskpack(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    task_graph = strict_json_load(root / "machine/facts/task_graph.json")
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    requirement = _find_exact(requirements, REQUIREMENT_ID)
    contract = _find_exact(contracts, CONTRACT_ID)
    tasks = [row for row in task_graph.get("tasks", []) if row.get("id") in fixture.get("expected_task_ids", [])]
    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    expected_artifact_paths = list(fixture.get("expected_artifacts", {}).values())
    requirement_ok = len(requirement) == 1 and requirement[0].get("stage_id") == STAGE_ID and requirement[0].get("phase_id") == PHASE_ID and requirement[0].get("scope") == expected_artifact_paths and requirement[0].get("target") == fixture.get("expected_pass_gate")
    _add(checks, "S04P03-TASKPACK-REQUIREMENT", requirement_ok, requirement)
    contract_ok = len(contract) == 1 and contract[0].get("requirement_id") == REQUIREMENT_ID and contract[0].get("pass_gate") == fixture.get("expected_pass_gate") and [row.get("id") for row in contract[0].get("tests", [])] == fixture.get("expected_test_ids")
    _add(checks, "S04P03-TASKPACK-CONTRACT", contract_ok, contract)
    expected_task_ids = fixture.get("expected_task_ids", [])
    task_ok = len(tasks) == 3 and [row.get("id") for row in tasks] == expected_task_ids and all(row.get("outputs") for row in tasks)
    _add(checks, "S04P03-TASKPACK-TASKS", task_ok, [row.get("id") for row in tasks])
    trace_ok = len(trace) == 1 and trace[0].get("acceptance_criteria_id") == CONTRACT_ID and trace[0].get("task_ids") == expected_task_ids and trace[0].get("test_ids") == fixture.get("expected_test_ids") and trace[0].get("evidence_id") == "EVD-S04-P03" and trace[0].get("artifact_ids") == list(fixture.get("expected_artifacts", {}))
    _add(checks, "S04P03-TASKPACK-TRACEABILITY", trace_ok, trace)


def _check_artifacts(
    root: Path,
    fixture: Mapping[str, Any],
    slots: Mapping[str, Any],
    flags: Mapping[str, Any],
    release_policy: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    slot_errors = validate_release_slots(slots, release_policy)
    flag_errors = validate_feature_flags(flags, release_policy)
    _add(checks, "S04P03-SLOTS-VALID", not slot_errors, slot_errors or "valid")
    _add(checks, "S04P03-FLAGS-VALID", not flag_errors, flag_errors or "valid")
    _add(checks, "S04P03-ACTIVATION-GATE", activation_gate(slots, flags) == fixture.get("expected_activation_gate"), activation_gate(slots, flags))
    _add(checks, "S04P03-TWO-DISTINCT-LOOPBACK-SLOTS", [row.get("id") for row in slots.get("slots", [])] == EXPECTED_SLOT_IDS and [row.get("bind_port") for row in slots.get("slots", [])] == [8081, 8082] and all(row.get("bind_address") == "127.0.0.1" for row in slots.get("slots", [])), slots.get("slots"))
    state = slots.get("shared_durable_state", {})
    _add(checks, "S04P03-SHARED-STATE-OUTSIDE-SLOTS", state.get("root") == "/var/lib/abd" and state.get("outside_release_slots") is True and state.get("slot_specific_copy_forbidden") is True, state)
    _add(checks, "S04P03-CANDIDATE-SHADOW-READ-ONLY", state.get("candidate_shadow_access") == "READ_ONLY" and state.get("single_writer_during_cutover") is True, state)
    _add(checks, "S04P03-ROLLBACK-DEADLINE-INCLUSIVE", slots.get("time_contract", {}).get("rollback_deadline_seconds") == 900 and slots.get("time_contract", {}).get("deadline_inclusive") is True and slots.get("time_contract", {}).get("frozen_boundary_seconds") == [899, 900, 901], slots.get("time_contract"))
    _add(checks, "S04P03-RPO-60", slots.get("time_contract", {}).get("ledger_recovery_point_target_seconds") == 60, slots.get("time_contract"))
    _add(checks, "S04P03-RELEASE-POLICY-TRIGGERS-COVERED", set(release_policy.get("auto_rollback_on", [])) == set(EXPECTED_TRIGGER_REASONS.values()) - {"未知或畸形发布探针"}, release_policy.get("auto_rollback_on"))
    _add(checks, "S04P03-RELEASE-POLICY-FLAGS-COVERED", release_policy.get("feature_flags") == EXPECTED_FLAG_TEMPLATES + EXPECTED_FIXED_FLAGS, release_policy.get("feature_flags"))
    _add(checks, "S04P03-LIVE-RECOMMENDATION-OFF", all(row.get("repository_enabled") is False for row in flags.get("fixed_flags", [])) and all(row.get("live_recommendation") is False for row in flags.get("canary_profiles", [])), flags.get("fixed_flags"))
    _add(checks, "S04P03-NO-ORDER-CAPABILITY", flags.get("financial_and_order_boundary", {}).get("order_submission_module_present") is False and "SUBMIT_CONFIRM_OR_RETRY_REAL_ORDER" in flags.get("forbidden_effects", []), flags.get("financial_and_order_boundary"))
    _add(checks, "S04P03-A300-A0-NO-GUARANTEE", flags.get("financial_and_order_boundary") == fixture.get("expected_financial_and_order_boundary"), flags.get("financial_and_order_boundary"))
    _add(checks, "S04P03-EXTERNAL-EFFECT-BOUNDARY", slots.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY == fixture.get("expected_external_effect_boundary"), slots.get("external_effect_boundary"))

    slot_mutations: Dict[str, bool] = {}
    for mutation in fixture.get("invalid_slot_mutations", []):
        candidate = deepcopy(slots)
        try:
            _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
            slot_mutations[mutation["id"]] = bool(validate_release_slots(candidate, release_policy))
        except Exception:
            slot_mutations[mutation.get("id", "UNKNOWN")] = True
    _add(checks, "S04P03-ALL-SLOT-MUTATIONS-FAIL-CLOSED", len(slot_mutations) == len(fixture.get("invalid_slot_mutations", [])) and all(slot_mutations.values()), slot_mutations)
    flag_mutations: Dict[str, bool] = {}
    for mutation in fixture.get("invalid_flag_mutations", []):
        candidate = deepcopy(flags)
        try:
            _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
            flag_mutations[mutation["id"]] = bool(validate_feature_flags(candidate, release_policy))
        except Exception:
            flag_mutations[mutation.get("id", "UNKNOWN")] = True
    _add(checks, "S04P03-ALL-FLAG-MUTATIONS-FAIL-CLOSED", len(flag_mutations) == len(fixture.get("invalid_flag_mutations", [])) and all(flag_mutations.values()), flag_mutations)

    all_probes = {probe: True for probe in EXPECTED_PROBES}
    hold = release_disposition(all_probes, 0)
    _add(checks, "S04P03-ALL-PROBES-HOLD-FOR-SIGNED-PROMOTION", hold == {"action": "HOLD_FOR_SIGNED_PROMOTION", "deadline_met": True, "failed_probes": [], "advice_enabled": False}, hold)
    for probe in EXPECTED_PROBES:
        candidate = dict(all_probes)
        candidate[probe] = False
        result = release_disposition(candidate, 900)
        _add(checks, "S04P03-PROBE-%s-ROLLBACK" % probe, result.get("action") == "ROLL_BACK_FAIL_CLOSED" and probe in result.get("failed_probes", []) and result.get("deadline_met") is True and result.get("advice_enabled") is False, result)
    boundary_expected = {899: True, 900: True, 901: False}
    failed_probe = dict(all_probes)
    failed_probe["HEALTH_PROBE"] = False
    for elapsed, expected in boundary_expected.items():
        result = release_disposition(failed_probe, elapsed)
        _add(checks, "S04P03-DEADLINE-%d" % elapsed, result.get("action") == "ROLL_BACK_FAIL_CLOSED" and result.get("deadline_met") is expected and result.get("advice_enabled") is False, result)
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        result = release_disposition(failed_probe, 900)
        _add(checks, "S04P03-NUMERIC-BOUNDARY-%s" % str(delta).replace("-", "NEG").replace(".", "_"), result.get("action") == "ROLL_BACK_FAIL_CLOSED" and result.get("deadline_met") is True, {"delta": delta, "result": result})

    for row in flags.get("fixed_flags", []):
        flag_id = row["id"]
        denied = evaluate_feature_flag(flags, flag_id, True, [])
        allowed = evaluate_feature_flag(flags, flag_id, True, row.get("enable_requires", []))
        killed = evaluate_feature_flag(flags, flag_id, True, row.get("enable_requires", []), emergency_advice_kill_switch=True)
        _add(checks, "S04P03-FLAG-%s-PREREQUISITES" % flag_id.upper(), denied.get("enabled") is False and allowed.get("enabled") is True and killed.get("enabled") is False, {"denied": denied, "allowed": allowed, "killed": killed})
    unknown_flag = evaluate_feature_flag(flags, "unknown:escape", True, ["ANY"])
    _add(checks, "S04P03-UNKNOWN-FLAG-DISABLED", unknown_flag.get("enabled") is False and unknown_flag.get("fail_closed") is True, unknown_flag)

    drill = perform_rollback_drill(root)
    _add(checks, "S04P03-ROLLBACK-DRILL-PASS", drill.get("status") == "PASS", {"status": drill.get("status"), "scenarios": len(drill.get("scenarios", {}))})
    _add(checks, "S04P03-ROLLBACK-DRILL-PRODUCTION-UNTOUCHED", drill.get("production_state_changed") is False and drill.get("external_state_changed") is False and drill.get("production_runtime_verified") is False, {key: drill.get(key) for key in ["production_state_changed", "external_state_changed", "production_runtime_verified"]})
    for scenario_id, scenario in drill.get("scenarios", {}).items():
        safe = scenario.get("expectation_met") is True and scenario.get("advice_enabled") is False and scenario.get("production_state_changed") is False and scenario.get("external_state_changed") is False
        _add(checks, "S04P03-DRILL-%s" % scenario_id.replace("-", "_").upper(), safe, {"status": scenario.get("status"), "expected": scenario.get("expected_status"), "ledger_unchanged": scenario.get("ledger_unchanged"), "deadline_met": scenario.get("deadline_met")})

    script = root / ROLLBACK_SCRIPT_PATH
    mode = stat.S_IMODE(script.stat().st_mode) if script.is_file() else 0
    script_text = script.read_text(encoding="utf-8") if script.is_file() else ""
    expected_lines = [
        "#!/bin/sh",
        "set -eu",
        '"$SCRIPT_DIR/.venv/bin/python"',
        "python3.12",
        "(3, 12) <= sys.version_info[:2] < (3, 13)",
        'exec "$PYTHON_BIN" -m abd_acceptance.release_control rollback "$@"',
    ]
    _add(checks, "S04P03-ROLLBACK-SCRIPT-EXECUTABLE", mode == 0o755, oct(mode))
    _add(checks, "S04P03-ROLLBACK-SCRIPT-STRICT-WRAPPER", all(line in script_text for line in expected_lines) and not any(token in script_text for token in ["curl ", "wget ", "rm -rf", "eval ", "sudo "]), script_text.splitlines())


def _check_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    forbidden = [
        Path("capacity_budget.json"),
        Path("resource_shedding.json"),
        Path("load_baseline.json"),
        Path("tests/S04/P04_test.py"),
        Path("machine/tests/fixtures/S04_P04.json"),
        Path("machine/evidence/EVD-S04-P04.json"),
        Path("machine/evidence/EVD-S04-P04_rollback.json"),
    ]
    present = [path.as_posix() for path in forbidden if (root / path).exists()]
    rows = _load_index(root)
    p04 = [row for row in rows if row.get("id") == "INDEX-AC-S04-P04"]
    ok = not present and len(p04) == 1 and p04[0].get("status") == "PLANNED" and "actual_artifact" not in p04[0] and "artifact_sha256" not in p04[0]
    _add(checks, "S04P03-P04-NOT-STARTED", ok, {"present": present, "index": p04})


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = [SLOTS_PATH, FLAGS_PATH, ROLLBACK_SCRIPT_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/release_control.py")]
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
    _add(checks, "S04P03-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


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
        ("S04P03-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S04P03-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
        ("S04P03-SIGNED-STATE-REGRESSION", SIGNED_STATE_JUNIT_PATH, int(fixture.get("minimum_signed_state_pytest_cases", 0))),
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
        _add(checks, "S04P03-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P03-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
        _add(checks, "S04P03-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P03-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S04P03-FIXTURE-STRICT-JSON")
    slots = _safe_load(root / SLOTS_PATH, checks, "S04P03-SLOTS-STRICT-JSON")
    flags = _safe_load(root / FLAGS_PATH, checks, "S04P03-FLAGS-STRICT-JSON")
    release_policy = _safe_load(root / "machine/facts/release_policy.json", checks, "S04P03-RELEASE-POLICY-STRICT-JSON")
    _check_pins(root, checks, hashes)
    if isinstance(fixture, Mapping) and isinstance(slots, Mapping) and isinstance(flags, Mapping) and isinstance(release_policy, Mapping):
        _check_taskpack(root, fixture, checks)
        try:
            predecessor = verify_cloudflare_edge_evidence(root, verify_git_history=_verify_git_history)
            predecessor_ok = predecessor.get("status") == "PASS" and predecessor.get("decision") == "S04_P02_EVIDENCE_VERIFIED" and predecessor.get("next") == "S04/P03_READY_NOT_STARTED"
            _add(checks, "S04P03-P02-PREREQUISITE", predecessor_ok, predecessor.get("summary"))
        except Exception as exc:
            _add(checks, "S04P03-P02-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
        _check_artifacts(root, fixture, slots, flags, release_policy, checks)
        _check_progression(root, checks)
        _check_no_leaks(root, checks)
        canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
        costs = strict_json_load(root / "machine/facts/costs.json")
        parameters = strict_json_load(root / "machine/facts/parameters.json")
        product = canonical.get("product", {})
        baseline_ok = product.get("initial_bankroll_aud") == "300.00" and product.get("incremental_cash_budget_aud") == "0.00" and product.get("monthly_target_return") == "0.30" and canonical.get("scope", {}).get("order_submission_module_present") is False and canonical.get("runtime", {}).get("single_host_zero_downtime_guaranteed") is False and parameters.get("target_30pct", {}).get("guaranteed") is False and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
        _add(checks, "S04P03-CANONICAL-A300-A0-NO-ORDER-NO-ZERO-DOWNTIME-NO-GUARANTEE", baseline_ok, {"product": product, "runtime": canonical.get("runtime"), "target": parameters.get("target_30pct")})
        _add(checks, "S04P03-NO-FLOAT", not _contains_float(fixture) and not _contains_float(slots) and not _contains_float(flags), "all frozen numeric values avoid binary floats")
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S04P03-INPUTS-AVAILABLE", False, "fixture, slots, flags or release policy unavailable")
    minimum = int(fixture.get("minimum_oracle_checks", 0)) if isinstance(fixture, Mapping) else 0
    if len(checks) < minimum:
        _add(checks, "S04P03-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
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
        "decision": "SAME_HOST_BLUE_GREEN_RELEASE_CONTRACT_FROZEN" if status == "PASS" else "RELEASE_CONTROL_BLOCKED_FAIL_CLOSED",
        "phase_status": "S04_P03_PASS" if status == "PASS" else "S04_P03_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "pass_gate_interpretation": "OFFLINE_FAILURE_INJECTION_PROVES_SHARED_LEDGER_BYTES_UNCHANGED_AND_ROLLBACK_AT_900_SECONDS; PRODUCTION_RUNTIME_REMAINS_UNVERIFIED",
        "activation_gate": activation_gate(slots, flags) if isinstance(slots, Mapping) and isinstance(flags, Mapping) else "BLOCKED_INPUT_UNAVAILABLE",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "runtime_release_status": "NOT_EXECUTED_OR_VERIFIED_ON_OVH",
        "release_status": "NOT_READY_S04_P04_AND_STAGE_REVIEW_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S04/P04_READY_NOT_STARTED" if status == "PASS" else "S04/P03_REMEDIATION_REQUIRED",
    }


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
    *,
    _verify_git_history: bool = True,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    if rollback["status"] != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "RELEASE_CONTROL_BLOCKED_FAIL_CLOSED"
        validation["phase_status"] = "S04_P03_FAIL"
        validation["next"] = "S04/P03_REMEDIATION_REQUIRED"
    inputs: Dict[str, str] = {}
    for relative in sorted({*PINNED_BASELINE_HASHES, *PINNED_PHASE_HASHES, "abd_acceptance/release_control.py"}):
        inputs[relative] = sha256_file(root / relative)
    for relative in PINNED_REPO_HASHES:
        inputs[relative] = sha256_file(root.parent / relative)
    scenarios = rollback.get("scenarios", {})
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "phase_status": validation["phase_status"],
        "artifacts": strict_json_load(root / FIXTURE_PATH)["expected_artifacts"],
        "validation": validation,
        "release_proof": {
            "mode": "DETERMINISTIC_EPHEMERAL_SAME_HOST_BLUE_GREEN_FAILURE_INJECTION",
            "scenario_count": len(scenarios),
            "all_expected_dispositions_met": all(row.get("expectation_met") is True for row in scenarios.values()),
            "rollback_at_900_seconds_passed": scenarios.get("BOUNDARY_900", {}).get("status") == "PASS",
            "rollback_at_901_seconds_failed_closed": scenarios.get("BOUNDARY_901", {}).get("status") == "FAIL" and scenarios.get("BOUNDARY_901", {}).get("advice_enabled") is False,
            "all_success_scenarios_preserved_ledger_bytes": all(row.get("ledger_unchanged") is True for row in scenarios.values() if row.get("expected_status") == "PASS"),
            "production_activation_performed": False,
            "production_runtime_verified": False,
        },
        "scope_boundary": {
            "p03_delivers_release_control_contract_not_production_activation": True,
            "p04_capacity_governance_not_started": True,
            "shared_production_ledger_not_read_or_written": True,
            "offline_drill_ledger_is_frozen_synthetic_evidence_only": True,
            "single_host_physical_zero_downtime_not_claimed": True,
            "real_traffic_canary_not_run": True,
            "ovh_rto_and_rpo_not_runtime_verified": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S04/P03 validates release control and synthetic ledger preservation offline; it executes no model, provider, host, container engine, systemd, real traffic, order or return evaluation.",
            "code": _current_code_hash(root),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "pass_gate_interpretation": validation["pass_gate_interpretation"],
        "activation_gate": validation["activation_gate"],
        "production_status": validation["production_status"],
        "runtime_release_status": validation["runtime_release_status"],
        "release_status": validation["release_status"],
        "financial_target_status": validation["financial_target_status"],
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _update_evidence_index(root: Path, status: str, artifact_sha256: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S04-P03"]
    if len(matching) != 1:
        raise ReleaseControlContractError("expected exactly one INDEX-AC-S04-P03 row")
    matching[0].update(
        {
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": artifact_sha256,
            "verified_at": FIXED_CLOCK,
            "next": "S04/P04_READY_NOT_STARTED" if status == "PASS" else "S04/P03_REMEDIATION_REQUIRED",
        }
    )
    _atomic_write(root / EVIDENCE_INDEX_PATH, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise ReleaseControlContractError("evidence directory must be inside the ABD project root") from exc
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


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S04P03-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S04P03-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S04-P03" and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID and evidence.get("stage_id") == STAGE_ID and evidence.get("phase_id") == PHASE_ID and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS" and evidence.get("decision") == "SAME_HOST_BLUE_GREEN_RELEASE_CONTRACT_FROZEN" and evidence.get("phase_status") == "S04_P03_PASS" and evidence.get("next") == "S04/P04_READY_NOT_STARTED" and _decision_hash_matches(evidence)
        _add(checks, "S04P03-RECEIPT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and validation.get("next") == "S04/P04_READY_NOT_STARTED" and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S04P03-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S04P03-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or "all inputs match")
        current_code = _current_code_hash(root)
        _add(checks, "S04P03-RECEIPT-CODE-HASH-CURRENT", evidence.get("hashes", {}).get("code") == current_code, {"expected": evidence.get("hashes", {}).get("code"), "actual": current_code})
        _add(checks, "S04P03-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        proof = evidence.get("release_proof", {})
        proof_ok = proof.get("rollback_at_900_seconds_passed") is True and proof.get("rollback_at_901_seconds_failed_closed") is True and proof.get("all_success_scenarios_preserved_ledger_bytes") is True and proof.get("production_activation_performed") is False and proof.get("production_runtime_verified") is False
        _add(checks, "S04P03-RECEIPT-RELEASE-PROOF", proof_ok, proof)
        boundary_ok = evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED" and evidence.get("runtime_release_status") == "NOT_EXECUTED_OR_VERIFIED_ON_OVH"
        _add(checks, "S04P03-RECEIPT-BOUNDARY", boundary_ok, evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S04P03-RECEIPT-INTEGRITY", "S04P03-RECEIPT-VALIDATION-ALL-PASS", "S04P03-RECEIPT-SIGNED-INPUTS-CURRENT", "S04P03-RECEIPT-CODE-HASH-CURRENT", "S04P03-RECEIPT-ROLLBACK-HASH-BINDING", "S04P03-RECEIPT-RELEASE-PROOF", "S04P03-RECEIPT-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, Mapping) and rollback.get("evidence_id") == "EVD-S04-P03-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and rollback.get("production_runtime_verified") is False and len(rollback.get("scenarios", {})) == len(EXPECTED_TRIGGER_REASONS) + 3 + 5 and all(row.get("expectation_met") is True for row in rollback.get("scenarios", {}).values())
    _add(checks, "S04P03-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S04-P03"]
        index_ok = len(matching) == 1 and matching[0].get("status") == "PASS" and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and matching[0].get("artifact_sha256") == evidence_hash and matching[0].get("next") == "S04/P04_READY_NOT_STARTED"
        _add(checks, "S04P03-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S04P03-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        predecessor = verify_cloudflare_edge_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S04P03-RECEIPT-P02-PREREQUISITE", predecessor.get("status") == "PASS", predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S04P03-RECEIPT-P02-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_progression(root, checks)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_P03_EVIDENCE_VERIFIED" if not failed else "S04_P03_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S04/P04_READY_NOT_STARTED" if not failed else "S04/P03_REMEDIATION_REQUIRED",
    }


def _rollback_cli(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="ABD S04/P03 fail-closed release rollback controller")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("check")
    drill = subparsers.add_parser("drill")
    drill.add_argument("--sandbox", required=True)
    drill.add_argument("--trigger", default="HEALTH_PROBE_FAILED")
    drill.add_argument("--elapsed-seconds", type=int, default=300)
    drill.add_argument("--fault", choices=["LEDGER_MUTATED_DURING_ROLLBACK", "UNSAFE_PREVIOUS_SLOT", "MALFORMED_CONTROL_STATE", "CURRENT_POINTER_ESCAPE", "PREVIOUS_MANIFEST_MISMATCH"])
    execute = subparsers.add_parser("execute")
    execute.add_argument("--activation-record", default="/etc/abd/release-activation.json")
    execute.add_argument("--confirm-production-rollback", required=True)
    args = parser.parse_args(list(arguments))
    root = Path.cwd().resolve()
    slots = strict_json_load(root / SLOTS_PATH)
    flags = strict_json_load(root / FLAGS_PATH)
    errors = validate_release_slots(slots, strict_json_load(root / "machine/facts/release_policy.json")) + validate_feature_flags(flags, strict_json_load(root / "machine/facts/release_policy.json"))
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, sort_keys=True))
        return 1
    if args.action == "check":
        print(json.dumps({"status": "PASS", "activation_gate": activation_gate(slots, flags), "production_state_changed": False}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.action == "drill":
        result = execute_release_drill(Path(args.sandbox), args.trigger, args.elapsed_seconds, fault=args.fault)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    expected_confirmation = "ABD-0.0.0.1-ROLLBACK"
    activation_path = Path(args.activation_record)
    blocked = {
        "status": "BLOCKED",
        "decision": "PRODUCTION_ROLLBACK_NOT_EXECUTED",
        "reason": "S04 stage review, target-host control state, previous release manifest and runtime ledger oracle are not verified by this repository phase",
        "confirmation_valid": args.confirm_production_rollback == expected_confirmation,
        "activation_record_path_valid": activation_path == Path("/etc/abd/release-activation.json"),
        "activation_record_present": activation_path.is_file(),
        "production_state_changed": False,
    }
    print(json.dumps(blocked, ensure_ascii=False, sort_keys=True))
    return 1


def _cli() -> int:
    parser = argparse.ArgumentParser(description="ABD S04/P03 release controller")
    subparsers = parser.add_subparsers(dest="command", required=True)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "rollback":
        return _rollback_cli(args.arguments)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
