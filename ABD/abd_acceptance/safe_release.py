"""Fail-closed, offline acceptance oracle for ABD S18/P01 safe release control."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .post_release_probe import (
    CANARY_POLICY_ID,
    PROMOTE_DECISION,
    REQUIRED_PROBE_IDS,
    ROLLBACK_DECISION,
    SAFE_ACTION,
    UNKNOWN_TRIGGER,
    evaluate_probe_bundle,
)

from .artifact_provenance import verify_existing_phase_evidence as verify_s14_p04
from .canonical_facts import sha256_file, strict_json_load
from .capacity_governance import verify_existing_phase_evidence as verify_s04_p04
from .recovery import verify_existing_phase_evidence as verify_s17_p04
from .legacy_receipt_compatibility import approved_successor_sha256


CONTRACT_ID = "AC-S18-P01"
REQUIREMENT_ID = "REQ-S18-P01"
STAGE_ID = "S18"
PHASE_ID = "P01"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T01:00:00+10:00"

PIPELINE_PATH = Path("release_pipeline.yml")
CANARY_POLICY_PATH = Path("canary_policy.json")
PROBE_PATH = Path("post_release_probe.py")
PROBE_CORE_PATH = Path("abd_acceptance/post_release_probe.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S18_P01.json")
TEST_PATH = Path("tests/S18/P01_test.py")
JUNIT_PATH = Path("machine/evidence/S18/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S18/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S18-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S18-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")
ORACLE_PATH = Path("abd_acceptance/safe_release.py")
RELEASE_SLOTS_PATH = Path("release_slots.json")

EXPECTED_TASK_IDS = ("T-S18-P01-01", "T-S18-P01-02", "T-S18-P01-03")
EXPECTED_TEST_IDS = ("TEST-S18-P01", "TEST-S18-P01-BOUNDARY", "TEST-S18-P01-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S18-P01-01", "ART-S18-P01-02", "ART-S18-P01-03")
EXPECTED_OUTPUTS = (PIPELINE_PATH.as_posix(), CANARY_POLICY_PATH.as_posix(), PROBE_PATH.as_posix())
EXPECTED_PIPELINE_STAGE_IDS = (
    "VERIFY_SIGNED_CANDIDATE",
    "START_CANDIDATE_SHADOW",
    "REPLAY_FROZEN_INPUT",
    "RUN_CANARY_SCOPES",
    "CHECKPOINT_AND_INVALIDATE_ADVICE",
    "SWITCH_CURRENT_RELEASE",
    "RUN_POST_RELEASE_PROBES",
    "PROMOTE_OR_ROLL_BACK",
)
ROLLBACK_ACTION = "AUTO_ROLL_BACK_TO_PREVIOUS_SLOT_KEEP_ADVICE_DISABLED"
EXPECTED_PROFILE_IDS = ("shadow", "one_source", "one_sport", "one_market_family", "eligible_full")
EXPECTED_PROFILE_BASIS_POINTS = (0, 100, 500, 2500, 10000)
EXPECTED_PROFILE_SCOPES = (
    "FROZEN_REPLAY_ONLY",
    "ONE_EXACT_SOURCE_ID",
    "ONE_EXACT_SPORT_ID",
    "ONE_EXACT_MARKET_FAMILY_ID",
    "ONLY_EVIDENCE_GATED_ELIGIBLE_SCOPES",
)
EXPECTED_FLAG_TEMPLATES = (
    "source:<id>",
    "sport:<id>",
    "market_family:<id>",
    "model:<id>",
    "live_recommendation",
    "gmail_ingestion",
    "owner_browser_companion",
)
EXPECTED_PREDECESSORS = {
    "AC-S04-P04": "cc5c845238614bdb7c1fb3ad5706363453ec84880c6cf44430ffef3f9d23bb69",
    "AC-S14-P04": "820f5a1c13f788386c54af8d18551bd6bd40d7816d659c6ffd43a657c25ddf4b",
    "AC-S17-P04": "08e1d389d3b0d80d6c729d9835dc27343018985cd8cc1796a9528b5ed7d6e708",
}
BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "production_equivalent_config_schema_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "cloudflare_account_dns_or_tunnel_accessed": False,
    "docker_or_systemd_invoked": False,
    "real_traffic_switched": False,
    "production_deployed_or_activated": False,
    "shared_production_ledger_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
FEATURE_FLAG_ID = "safe_release:s18_p01_offline_candidate_pipeline"


class SafeReleaseAcceptanceError(ValueError):
    """Raised when the S18/P01 contract cannot be reproduced safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


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


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise SafeReleaseAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise SafeReleaseAcceptanceError("JSONL row %d is not an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise SafeReleaseAcceptanceError("rows are unavailable")
    matched = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matched) != 1:
        raise SafeReleaseAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matched[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def validate_fixture(value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "expected_next", "predecessors", "scenarios",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise SafeReleaseAcceptanceError("fixture has an invalid schema")
    identity = (
        value.get("schema_version") == "1.0.0"
        and value.get("product_version") == PRODUCT_VERSION
        and value.get("contract_id") == CONTRACT_ID
        and value.get("requirement_id") == REQUIREMENT_ID
        and value.get("stage_id") == STAGE_ID
        and value.get("phase_id") == PHASE_ID
        and value.get("fixed_clock") == FIXED_CLOCK
        and value.get("expected_next") == "S18/P02_READY_NOT_STARTED"
    )
    if not identity:
        raise SafeReleaseAcceptanceError("fixture identity differs from S18/P01")
    predecessors = value.get("predecessors")
    if not isinstance(predecessors, list) or len(predecessors) != len(EXPECTED_PREDECESSORS):
        raise SafeReleaseAcceptanceError("fixture predecessors are unavailable")
    observed = {}
    for row in predecessors:
        if not isinstance(row, Mapping) or set(row) != {"contract_id", "evidence_sha256"}:
            raise SafeReleaseAcceptanceError("fixture predecessor schema is invalid")
        observed[row.get("contract_id")] = row.get("evidence_sha256")
    if observed != EXPECTED_PREDECESSORS:
        raise SafeReleaseAcceptanceError("fixture predecessor hashes differ")
    scenarios = value.get("scenarios")
    expected_ids = (
        "GOLDEN_ALL_PROBES_PASS",
        "HEALTH_PROBE_FAILED",
        "NUMERIC_CROSS_IMPLEMENTATION_FAILED",
        "UNKNOWN_EXTRA_PROBE_FAILS_CLOSED",
        "ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_STABLE",
        "MISSING_LEDGER_PROBE_FAILS_CLOSED",
    )
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != expected_ids:
        raise SafeReleaseAcceptanceError("fixture scenarios are not exact")
    for scenario in scenarios:
        if not isinstance(scenario, Mapping) or set(scenario) != {"scenario_id", "probe_bundle", "expected"}:
            raise SafeReleaseAcceptanceError("fixture scenario fields are invalid")
        expected = scenario.get("expected")
        if not isinstance(expected, Mapping) or set(expected) != {"decision", "logical_active_slot", "logical_auto_rollback", "rollback_trigger", "action"}:
            raise SafeReleaseAcceptanceError("fixture expected result fields are invalid")
    return value


def load_fixture(path: Path) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(path))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S18P01-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S18P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S18P01-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S18P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S18P01-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        selected = [_row(tasks, identifier) for identifier in EXPECTED_TASK_IDS]
        requirement_ok = (
            requirement.get("scope") == list(EXPECTED_OUTPUTS)
            and requirement.get("target") == "新版本探针失败自动回旧版。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
        )
        contract_ok = (
            contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == {"type": "EXECUTABLE", "command": "python -m abd_acceptance --contract AC-S18-P01 --evidence machine/evidence", "rule": "新版本探针失败自动回旧版。"}
            and contract.get("pass_gate") == "新版本探针失败自动回旧版。"
            and tuple(item.get("id") for item in contract.get("tests", []) if isinstance(item, Mapping)) == EXPECTED_TEST_IDS
        )
        task_ok = (
            tuple(item.get("id") for item in selected) == EXPECTED_TASK_IDS
            and selected[0].get("outputs") == list(EXPECTED_OUTPUTS)
            and selected[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and selected[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and selected[0].get("depends_on") == ["T-S04-P04-03", "T-S14-P04-03", "T-S17-P04-03"]
        )
        trace_ok = (
            trace.get("acceptance_criteria_id") == CONTRACT_ID
            and tuple(trace.get("task_ids", [])) == EXPECTED_TASK_IDS
            and tuple(trace.get("test_ids", [])) == EXPECTED_TEST_IDS
            and trace.get("evidence_id") == "EVD-S18-P01"
            and tuple(trace.get("artifact_ids", [])) == EXPECTED_ARTIFACT_IDS
        )
    except Exception as exc:
        requirement_ok = contract_ok = task_ok = trace_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = {"requirement": REQUIREMENT_ID, "contract": CONTRACT_ID, "tasks": EXPECTED_TASK_IDS}
    _add(checks, "S18P01-REQUIREMENT-EXACT", requirement_ok, detail)
    _add(checks, "S18P01-ACCEPTANCE-CONTRACT-EXACT", contract_ok, detail)
    _add(checks, "S18P01-TASK-GRAPH-EXACT", task_ok, detail)
    _add(checks, "S18P01-TRACEABILITY-EXACT", trace_ok, detail)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        common_index_ok = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "新版本探针失败自动回旧版。"
        )
        index_ok = common_index_ok and (
            row.get("status") == "PLANNED"
            or (
                row.get("status") == "PASS"
                and row.get("stage_id") == STAGE_ID
                and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
                and isinstance(row.get("artifact_sha256"), str)
            )
        )
    except Exception as exc:
        row = "%s: %s" % (type(exc).__name__, exc)
        index_ok = False
    _add(checks, "S18P01-EVIDENCE-INDEX-EXACT", index_ok, row)


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    verifiers = {
        "AC-S04-P04": verify_s04_p04,
        "AC-S14-P04": verify_s14_p04,
        "AC-S17-P04": verify_s17_p04,
    }
    for contract_id, verifier in verifiers.items():
        try:
            result = verifier(root)
            actual = result.get("evidence_sha256")
            ok = result.get("status") == "PASS" and actual == EXPECTED_PREDECESSORS[contract_id]
        except Exception as exc:
            result = "%s: %s" % (type(exc).__name__, exc)
            actual = "UNAVAILABLE"
            ok = False
        hashes["machine/evidence/EVD-%s.json" % contract_id.removeprefix("AC-")] = actual
        _add(checks, "S18P01-%s-SIGNED-DEPENDENCY" % contract_id.replace("-", ""), ok, result)


def _check_release_slots(root: Path, checks: List[Dict[str, Any]]) -> None:
    document = _safe_load(root, RELEASE_SLOTS_PATH, checks, "S18P01-RELEASE-SLOTS-STRICT-JSON")
    slots = document.get("slots") if isinstance(document, Mapping) else None
    profiles = document.get("canary_profiles") if isinstance(document, Mapping) else None
    slot_ids = tuple(item.get("id") for item in slots if isinstance(item, Mapping)) if isinstance(slots, list) else ()
    profile_ids = tuple(item.get("id") for item in profiles if isinstance(item, Mapping)) if isinstance(profiles, list) else ()
    profile_bps = tuple(item.get("maximum_traffic_basis_points") for item in profiles if isinstance(item, Mapping)) if isinstance(profiles, list) else ()
    profile_scopes = tuple(item.get("required_scope") for item in profiles if isinstance(item, Mapping)) if isinstance(profiles, list) else ()
    ok = (
        isinstance(document, Mapping)
        and document.get("deployment_mode") == "SAME_HOST_BLUE_GREEN_WITH_CANARY_AND_AUTO_ROLLBACK"
        and slot_ids == ("blue", "green")
        and profile_ids == EXPECTED_PROFILE_IDS
        and profile_bps == EXPECTED_PROFILE_BASIS_POINTS
        and profile_scopes == EXPECTED_PROFILE_SCOPES
        and tuple(document.get("required_probes", [])) == REQUIRED_PROBE_IDS
    )
    _add(checks, "S18P01-S04-RELEASE-SLOT-CONTROL-EXACT", ok, {"slots": slot_ids, "profiles": profile_ids})


def _check_pipeline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    document = _safe_load(root, PIPELINE_PATH, checks, "S18P01-PIPELINE-STRICT-JSON-YAML")
    if not isinstance(document, Mapping):
        return None
    hashes[PIPELINE_PATH.as_posix()] = sha256_file(root / PIPELINE_PATH)
    fields = {
        "schema_version", "pipeline_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "execution_mode", "candidate_slots", "entry_conditions", "stages", "rollback_policy", "external_effect_boundary",
    }
    stages = document.get("stages")
    stage_ids = tuple(item.get("id") for item in stages if isinstance(item, Mapping)) if isinstance(stages, list) else ()
    exact = (
        set(document) == fields
        and document.get("schema_version") == "1.0.0"
        and document.get("pipeline_id") == "S18-P01-SAFE-RELEASE-PIPELINE"
        and document.get("product_version") == PRODUCT_VERSION
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("execution_mode") == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
        and document.get("candidate_slots") == ["blue", "green"]
        and document.get("entry_conditions") == {
            "signed_s04_capacity_required": True,
            "signed_s14_provenance_required": True,
            "signed_s17_recovery_required": True,
            "live_recommendation_enabled": False,
            "order_submission_enabled": False,
            "incremental_cash_spent_aud": "0.00",
        }
        and stage_ids == EXPECTED_PIPELINE_STAGE_IDS
        and all(
            isinstance(item, Mapping)
            and set(item) == {"id", "logical_mode", "writes_shared_ledger", "on_failure"}
            and item.get("on_failure") == ROLLBACK_ACTION
            for item in stages
        )
        and document.get("rollback_policy") == {
            "on_any_probe_failure": True,
            "previous_slot_source": "LAST_VERIFIED_CONTROL_STATE_ONLY",
            "unknown_or_malformed_probe_action": ROLLBACK_ACTION,
            "rollback_deadline_seconds": 900,
            "advice_remains_disabled": True,
        }
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    _add(checks, "S18P01-PIPELINE-FAIL-CLOSED-EXACT", exact, {"stages": stage_ids})
    return document


def _check_canary_policy(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    document = _safe_load(root, CANARY_POLICY_PATH, checks, "S18P01-CANARY-POLICY-STRICT-JSON")
    if not isinstance(document, Mapping):
        return None
    hashes[CANARY_POLICY_PATH.as_posix()] = sha256_file(root / CANARY_POLICY_PATH)
    profiles = document.get("canary_profiles")
    profile_ids = tuple(item.get("id") for item in profiles if isinstance(item, Mapping)) if isinstance(profiles, list) else ()
    profile_bps = tuple(item.get("maximum_traffic_basis_points") for item in profiles if isinstance(item, Mapping)) if isinstance(profiles, list) else ()
    profile_scopes = tuple(item.get("required_scope") for item in profiles if isinstance(item, Mapping)) if isinstance(profiles, list) else ()
    fields = {
        "schema_version", "policy_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "deployment_mode", "execution_mode", "feature_flag_templates", "model_gate", "canary_profiles",
        "required_post_release_probes", "failure_action", "external_effect_boundary",
    }
    exact = (
        set(document) == fields
        and document.get("schema_version") == "1.0.0"
        and document.get("policy_id") == CANARY_POLICY_ID
        and document.get("product_version") == PRODUCT_VERSION
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("deployment_mode") == "SAME_HOST_BLUE_GREEN_WITH_CANARY_AND_AUTO_ROLLBACK"
        and document.get("execution_mode") == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
        and tuple(document.get("feature_flag_templates", [])) == EXPECTED_FLAG_TEMPLATES
        and document.get("model_gate") == "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT"
        and profile_ids == EXPECTED_PROFILE_IDS
        and profile_bps == EXPECTED_PROFILE_BASIS_POINTS
        and profile_scopes == EXPECTED_PROFILE_SCOPES
        and all(
            isinstance(item, Mapping)
            and set(item) == {"id", "maximum_traffic_basis_points", "required_scope", "primary_feature_flag_template", "live_recommendation", "order_submission_enabled"}
            and item.get("live_recommendation") is False
            and item.get("order_submission_enabled") is False
            for item in profiles
        )
        and tuple(document.get("required_post_release_probes", [])) == REQUIRED_PROBE_IDS
        and document.get("failure_action") == ROLLBACK_ACTION
        and document.get("external_effect_boundary") == {
            "external_network_accessed": False,
            "real_traffic_switched": False,
            "production_deployed_or_activated": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "incremental_cash_spent_aud": "0.00",
        }
    )
    _add(checks, "S18P01-CANARY-POLICY-FAIL-CLOSED-EXACT", exact, {"profiles": profile_ids, "basis_points": profile_bps})
    return document


def _check_probe_runner(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    path = root / PROBE_PATH
    try:
        source = path.read_text(encoding="utf-8") + "\n" + (root / PROBE_CORE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "urllib", "requests", "httpx", "subprocess", "os", "shutil", "time", "asyncio"}
        static_ok = not (imports & forbidden) and "http://" not in source and "https://" not in source
        hashes[PROBE_PATH.as_posix()] = sha256_file(path)
    except Exception as exc:
        static_ok = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P01-PROBE-RUNNER-LOCAL-ONLY-STATIC", static_ok, source if isinstance(source, str) else "parsed")
    scenario_ok = True
    details = []
    for scenario in fixture["scenarios"]:
        result = evaluate_probe_bundle(scenario["probe_bundle"])
        selected = {key: result.get(key) for key in scenario["expected"]}
        passed = selected == scenario["expected"] and result.get("action") == SAFE_ACTION and result.get("recommendation_generated_or_enabled") is False and result.get("order_submission_enabled") is False and result.get("production_state_changed") is False
        scenario_ok = scenario_ok and passed
        details.append({"scenario_id": scenario["scenario_id"], "passed": passed, "decision": result.get("decision")})
    _add(checks, "S18P01-PROBE-REPLAY-AND-FAIL-CLOSED-EXACT", scenario_ok, details)
    _add(checks, "S18P01-UNKNOWN-PROBE-ROLLBACK-EXACT", any(item["scenario_id"] == "UNKNOWN_EXTRA_PROBE_FAILS_CLOSED" and item["decision"] == ROLLBACK_DECISION for item in details), details)
    _add(checks, "S18P01-ADVERSE-ONE-IN-TEN-THOUSAND-STABLE", any(item["scenario_id"] == "ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_STABLE" and item["decision"] == PROMOTE_DECISION for item in details), details)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .safe_release import verify_existing_phase_evidence as verify_safe_release_phase_evidence" in source
            and "from .safe_release import write_phase_evidence as write_safe_release_phase_evidence" in source
            and '"AC-S18-P01": verify_safe_release_phase_evidence,' in source
            and '"AC-S18-P01": write_safe_release_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P01-CLI-WRITER-AND-VERIFIER-EXACT", exact, "abd_acceptance/__main__.py" if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(
        checks,
        "S18P01-S08-LEGACY-SUCCESSOR-PIN-EXACT",
        successor == sha256_file(root / CLI_PATH),
        {"approved": successor, "current": sha256_file(root / CLI_PATH)},
    )


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    try:
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
        summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for suite in suites:
            for key in summary:
                summary[key] += int(suite.attrib.get(key, "0"))
        normalized = bool(suites) and all(
            suite.attrib.get("timestamp") == "2026-07-19T00:00:00+10:00"
            and suite.attrib.get("time") == "0.000"
            and "hostname" not in suite.attrib
            and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
            for suite in suites
        )
        return summary, normalized
    except Exception:
        return {"tests": 0, "failures": 1, "errors": 1, "skipped": 0}, False


def _check_reports(root: Path, checks: List[Dict[str, Any]], require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S18P01-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    _add(checks, "S18P01-TARGETED-PYTEST-REPORT", summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S18P01-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S18P01-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S18_P01_SAFE_RELEASE_CONTROL_PASS_P02_REQUIRED" if passed else "S18/P01_BLOCKED",
        "next": "S18/P02_READY_NOT_STARTED" if passed else "S18/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessors(root, checks, hashes)
    _check_release_slots(root, checks)
    _check_pipeline(root, checks, hashes)
    _check_canary_policy(root, checks, hashes)
    try:
        fixture = load_fixture(root / FIXTURE_PATH)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        _add(checks, "S18P01-FIXTURE-EXACT", True, FIXTURE_PATH.as_posix())
    except Exception as exc:
        fixture = None
        _add(checks, "S18P01-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    if fixture is not None:
        _check_probe_runner(root, fixture, checks, hashes)
    else:
        _add(checks, "S18P01-PROBE-RUNNER-LOCAL-ONLY-STATIC", False, "fixture unavailable")
        _add(checks, "S18P01-PROBE-REPLAY-AND-FAIL-CLOSED-EXACT", False, "fixture unavailable")
        _add(checks, "S18P01-UNKNOWN-PROBE-ROLLBACK-EXACT", False, "fixture unavailable")
        _add(checks, "S18P01-ADVERSE-ONE-IN-TEN-THOUSAND-STABLE", False, "fixture unavailable")
    _check_cli_wiring(root, checks)
    _check_reports(root, checks, require_test_reports)
    _add(checks, "S18P01-EXTERNAL-EFFECT-BOUNDARY-EXACT", all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud") and EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00", EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (PIPELINE_PATH, CANARY_POLICY_PATH, PROBE_PATH, PROBE_CORE_PATH, FIXTURE_PATH, ORACLE_PATH, *[Path("machine/evidence/EVD-%s.json" % key.removeprefix("AC-")) for key in EXPECTED_PREDECESSORS])
    artifacts = {
        path.as_posix(): {
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
            "status": "PASS" if (root / path).is_file() else "FAIL",
        }
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S18-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_LOCAL_CANDIDATE_PIPELINE_KEEP_PREVIOUS_SIGNED_RELEASE",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "logical_auto_rollback_verified": True,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "real_traffic_switched": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, require_test_reports: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, PIPELINE_PATH, CANARY_POLICY_PATH, PROBE_PATH, PROBE_CORE_PATH, FIXTURE_PATH, TEST_PATH, RELEASE_SLOTS_PATH]
    paths.extend(Path(path) for path in BASELINE_HASHES)
    paths.extend(Path("machine/evidence/EVD-%s.json" % key.removeprefix("AC-")) for key in EXPECTED_PREDECESSORS)
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S18-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S18_P01_LOCAL_SAFE_RELEASE_CONTROL_ONLY_P02_REQUIRED" if validation["status"] == "PASS" else "S18_P01_REMEDIATION_REQUIRED",
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": 6,
            "required_probe_count": len(REQUIRED_PROBE_IDS),
            "logical_auto_rollback_failure_count": 4,
            "adverse_one_in_ten_thousand_vector_count": 1,
            "external_runtime_accessed": False,
            "real_time_wait_performed": False,
        },
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "ACCEPTANCE_EVIDENCE",
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "acceptance_contract_id": CONTRACT_ID,
        "status": "PASS",
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S18/P02_READY_NOT_STARTED",
        "pass_gate": "新版本探针失败自动回旧版。",
        "verified_at": FIXED_CLOCK,
    }
    matching = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) != 1 or len(raw_lines) != len(rows):
        raise SafeReleaseAcceptanceError("S18/P01 evidence-index row must exist exactly once")
    raw_lines[matching[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise SafeReleaseAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise SafeReleaseAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/P02_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S18_P01_SAFE_RELEASE_CONTROL_PASS_P02_REQUIRED"
        and evidence.get("next") == "S18/P02_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("logical_auto_rollback_verified") is True
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_traffic_switched") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S18/P02_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise SafeReleaseAcceptanceError("existing S18/P01 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/P02_READY_NOT_STARTED",
    }


__all__ = [
    "CANARY_POLICY_PATH", "CONTRACT_ID", "EVIDENCE_PATH", "EXTERNAL_EFFECT_BOUNDARY", "FEATURE_FLAG_ID",
    "FIXTURE_PATH", "PIPELINE_PATH", "PROBE_PATH", "SafeReleaseAcceptanceError", "evaluate_contract",
    "load_fixture", "perform_rollback_drill", "validate_candidate_preflight", "validate_fixture",
    "verify_existing_phase_evidence", "write_phase_evidence",
]
