from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .advice_card import (
    build_advice_card,
    safe_build_advice_card,
    verify_existing_phase_evidence as verify_p02_evidence,
)
from .canonical_facts import sha256_file, strict_json_load
from .terminology_governance import scan_ui_text


CONTRACT_ID = "AC-S03-P03"
REQUIREMENT_ID = "REQ-S03-P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T12:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

REASON_CODES_PATH = Path("reason_codes_zh.json")
NEXT_ACTION_MATRIX_PATH = Path("next_action_matrix.json")
ORACLE_FIXTURE_PATH = Path("machine/tests/fixtures/S03_P03.json")
TEST_PATH = Path("tests/S03/P03_test.py")
GLOSSARY_PATH = Path("glossary_zh.json")
FORBIDDEN_PATH = Path("forbidden_ui_terms.json")
ADVICE_SCHEMA_PATH = Path("advice_card_schema.json")
ADVICE_FIXTURES_PATH = Path("advice_card_fixtures.json")
P02_ORACLE_FIXTURE_PATH = Path("machine/tests/fixtures/S03_P02.json")
P02_TEST_PATH = Path("tests/S03/P02_test.py")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S03-P02_rollback.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
MODEL_CARD_PATH = Path("machine/facts/model_system_card.json")
JUNIT_PATH = Path("machine/evidence/S03/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S03/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PINNED_PHASE_HASHES = {
    REASON_CODES_PATH.as_posix(): "62c37e83b844b72fbeeebe5591a717d64c225629fb4ad421c44a6ad631ac8a20",
    NEXT_ACTION_MATRIX_PATH.as_posix(): "86e52de87b15a447a6d7d4683a8fe99b7f6f255552d05bde15dcf94928969f3d",
    ORACLE_FIXTURE_PATH.as_posix(): "3c73939012825ab70109d0814e4ff44ab6fb6c4ab72e805072893a7c51a97ea2",
    TEST_PATH.as_posix(): "39bbb785926ae83dc84768d83b28ad2c21d3acbed05c588284b2d1682a639f71",
}
PINNED_BASELINE_HASHES = {
    P02_EVIDENCE_PATH.as_posix(): "5e6c4e710a1b74d374f60c91ff26cd365beb5f2b5ca244bea2add10df9d82c97",
    P02_ROLLBACK_PATH.as_posix(): "4d104a9f6167721e3f9d62a1f94bc336155c8405febc0d8b8693299087edf2eb",
    ADVICE_SCHEMA_PATH.as_posix(): "213f1f467d3421f56382f8de247842d23b3ece1ce726e83af13269caa6febc9a",
    ADVICE_FIXTURES_PATH.as_posix(): "2f9a5f892eebf01dfbdf91e3c14c96ee59005cd801f169460514d8c4e5476eb5",
    P02_ORACLE_FIXTURE_PATH.as_posix(): "26bdaef3a2335204e5acaecb4e7ed8a91959c649c42aed637192e089efc8978d",
    P02_TEST_PATH.as_posix(): "04463326c983d22d53093609429c8ced6589445cb4cde40702f34ce3b33a54f0",
    GLOSSARY_PATH.as_posix(): "ffaf3a6c66533ce89bd8dc788b1bbfb09754bb8af0dec1355c90544eb4151097",
    FORBIDDEN_PATH.as_posix(): "c2dc156b31b7e333fe316343c09d6cab47339b18d3f7572b11e7c1fbf2590c7f",
    PARAMETERS_PATH.as_posix(): "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    MODEL_CARD_PATH.as_posix(): "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "machine/facts/decision_prerequisites.json": "e9b54b985aff11faceaa7a2d6e6db42e070c96c0a8286a348ff767bc62921ccc",
    "machine/facts/provider_contracts.json": "a9d0fd864fad7ac4c14ec6a324d447abbc8497b256a232f9ca04b3115b15364a",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/risk_register.json": "6f50e159f000ac4a1c714d08cff239e524a58c679cd77c05d7b4944a7b602888",
    "machine/facts/email_ingestion.json": "7d40a142a482b5179aa6bb11fa0694fa5576a770f0b2a5af751615da3dea53cd",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "ea52f91cfd9339e079113da7ee568c375d39ed915ba0944c9022128ee9ce8133"

PHASE_COMMIT = "86f268310e24eeab10639c6c36cbfcec544f9c74"
PINNED_PHASE_CODE_HASH = "eba903e5593fcc5aebfb1432ec8b8f3614680d1898fc5e101e4a9de07fd564b2"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/reason_next_action.py",
    "abd_acceptance/advice_card.py",
    "abd_acceptance/terminology_governance.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S03/P03_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES = {
    "README.md": "f91f296f892cf19e002c75765805ec478f242e05c66a5ab8dee6176cc17cbc26",
    "abd_acceptance/advice_card.py": "9c837a0e787425beebbf096741e313199370f00c6630a48becde615a18fa03b3",
    "abd_acceptance/terminology_governance.py": "d51ae252e7d28addfa7097a2f4ccb5ba2f017ec0745a0eee4e0971fd744beded",
    "abd_acceptance/__main__.py": "bd6c8452099c408358b89734e9d785f92384a3d63a06bd800e8a06b83cb65124",
    "abd_acceptance/__init__.py": "2b394b3fd25d68c920031d01e17da4c39cfafd80a4c27933c8ebe5a6d794e562",
    "tests/S03/P03_test.py": "39bbb785926ae83dc84768d83b28ad2c21d3acbed05c588284b2d1682a639f71",
}

ALLOWED_NUMERIC_BOUNDARY_DELTAS = {"-0.0001", "0", "0.0001"}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class FailureGuidanceError(ValueError):
    """Raised when a failure-guidance request cannot be interpreted safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _contains_chinese(value: Any) -> bool:
    return isinstance(value, str) and re.search(r"[\u4e00-\u9fff]", value) is not None


def _duplicates(values: Sequence[Any]) -> List[Any]:
    seen: set[Any] = set()
    duplicates: List[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
        _add(checks, check_id, True, path.name)
        return value
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _reason_by_code(catalog: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = catalog.get("reason_codes", [])
    if not isinstance(rows, list):
        raise FailureGuidanceError("reason catalog rows must be a list")
    result: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("code"), str):
            raise FailureGuidanceError("reason catalog row is malformed")
        code = str(row["code"])
        if code in result:
            raise FailureGuidanceError("duplicate reason code: %s" % code)
        result[code] = row
    return result


def _action_by_id(matrix: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = matrix.get("actions", [])
    if not isinstance(rows, list):
        raise FailureGuidanceError("action rows must be a list")
    result: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("action_id"), str):
            raise FailureGuidanceError("action row is malformed")
        action_id = str(row["action_id"])
        if action_id in result:
            raise FailureGuidanceError("duplicate action id: %s" % action_id)
        result[action_id] = row
    return result


def _mapping_by_code(matrix: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = matrix.get("reason_code_mappings", [])
    if not isinstance(rows, list):
        raise FailureGuidanceError("reason mappings must be a list")
    result: Dict[str, Mapping[str, Any]] = {}
    priorities: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("reason_code"), str):
            raise FailureGuidanceError("reason mapping is malformed")
        code = str(row["reason_code"])
        priority = row.get("priority")
        if code in result or not isinstance(priority, int) or isinstance(priority, bool) or priority in priorities:
            raise FailureGuidanceError("reason mappings are not uniquely ordered")
        result[code] = row
        priorities.add(priority)
    return result


def _normalize_failure_item(
    item: Any,
    known_codes: Mapping[str, Mapping[str, Any]],
    matrix: Mapping[str, Any],
) -> str:
    fallback = str(matrix.get("selection_rule", {}).get("unknown_or_malformed_input", "UNKNOWN_FAILURE_STATE"))
    if isinstance(item, str):
        return item if item in known_codes else fallback
    if not isinstance(item, Mapping):
        return fallback
    code = item.get("code")
    if code == "UPSTREAM_GATE_FAILED":
        refs = item.get("evidence_refs")
        gate_map = matrix.get("p02_upstream_gate_reference_map", {})
        if not isinstance(refs, list) or len(refs) != 1 or not isinstance(gate_map, Mapping):
            return fallback
        mapped = gate_map.get(refs[0])
        return str(mapped) if isinstance(mapped, str) and mapped in known_codes else fallback
    return str(code) if isinstance(code, str) and code in known_codes else fallback


def _resolution_artifact_hash(value: Mapping[str, Any]) -> str:
    unsigned = copy.deepcopy(dict(value))
    unsigned.get("provenance", {})["artifact_sha256"] = "0" * 64
    return _canonical_sha256(unsigned)


def resolve_failure_states(
    failure_states: Any,
    *,
    reason_catalog: Mapping[str, Any],
    next_action_matrix: Mapping[str, Any],
    numeric_boundary_delta: str = "0",
) -> Dict[str, Any]:
    if numeric_boundary_delta not in ALLOWED_NUMERIC_BOUNDARY_DELTAS:
        raise FailureGuidanceError("numeric boundary delta is not frozen")
    if not isinstance(failure_states, list):
        raise FailureGuidanceError("failure states must be a list")
    reasons = _reason_by_code(reason_catalog)
    actions = _action_by_id(next_action_matrix)
    mappings = _mapping_by_code(next_action_matrix)
    if set(reasons) != set(mappings):
        raise FailureGuidanceError("reason catalog and next-action matrix differ")
    normalized = [_normalize_failure_item(item, reasons, next_action_matrix) for item in failure_states]
    if not normalized:
        normalized = [str(reason_catalog.get("default_reason_code", "UNKNOWN_FAILURE_STATE"))]
    normalized = sorted(set(normalized), key=lambda code: (int(mappings[code]["priority"]), code))
    selected_code = normalized[0]
    reason = reasons[selected_code]
    mapping = mappings[selected_code]
    action_id = mapping.get("next_action_id")
    action = actions.get(str(action_id))
    if action is None or mapping.get("action_count") != 1:
        raise FailureGuidanceError("selected reason does not have exactly one action")
    source_hash = _canonical_sha256(failure_states)
    resolution = {
        "schema_version": "1.0.0",
        "status": "FAIL_CLOSED",
        "selected_reason": {
            "code": selected_code,
            "title_zh": reason.get("title_zh"),
            "message_zh": reason.get("message_zh"),
            "severity": reason.get("severity"),
        },
        "next_action": {
            "action_id": action_id,
            "title_zh": action.get("title_zh"),
            "system_behavior_zh": action.get("system_behavior_zh"),
            "owner_guidance_zh": action.get("owner_guidance_zh"),
        },
        "considered_reason_codes": normalized,
        "considered_count": len(normalized),
        "numeric_boundary_delta": numeric_boundary_delta,
        "safety": {
            "automatic_selection_only": True,
            "external_effect_performed": False,
            "order_submitted": False,
            "order_retried": False,
            "incremental_cash_spent_aud": "0.00",
            "evidence_numeric_risk_or_safety_gate_relaxed": False,
            "owner_final_order_only": True,
            "boundary_zh": "当前只展示一个安全下一步，不执行外部动作；最终下单只能由用户在全部门通过后自行决定并完成。",
        },
        "provenance": {
            "input_sha256": source_hash,
            "reason_catalog_sha256": _canonical_sha256(reason_catalog),
            "next_action_matrix_sha256": _canonical_sha256(next_action_matrix),
            "artifact_sha256": "0" * 64,
        },
    }
    resolution["provenance"]["artifact_sha256"] = _resolution_artifact_hash(resolution)
    return resolution


def safe_resolve_failure_states(
    failure_states: Any,
    *,
    reason_catalog: Mapping[str, Any],
    next_action_matrix: Mapping[str, Any],
    numeric_boundary_delta: Any = "0",
) -> Dict[str, Any]:
    try:
        return resolve_failure_states(
            failure_states,
            reason_catalog=reason_catalog,
            next_action_matrix=next_action_matrix,
            numeric_boundary_delta=numeric_boundary_delta,
        )
    except Exception:
        return resolve_failure_states(
            ["UNKNOWN_FAILURE_STATE"],
            reason_catalog=reason_catalog,
            next_action_matrix=next_action_matrix,
            numeric_boundary_delta="0",
        )


def render_failure_guidance(resolution: Mapping[str, Any]) -> str:
    reason = resolution.get("selected_reason", {})
    action = resolution.get("next_action", {})
    safety = resolution.get("safety", {})
    visible = [
        "当前状态",
        reason.get("title_zh"),
        reason.get("message_zh"),
        "下一步",
        action.get("title_zh"),
        action.get("system_behavior_zh"),
        action.get("owner_guidance_zh"),
        "安全边界",
        safety.get("boundary_zh"),
    ]
    return "\n".join(str(item) for item in visible if isinstance(item, str) and item)


def validate_resolution(
    resolution: Any,
    *,
    reason_catalog: Mapping[str, Any],
    next_action_matrix: Mapping[str, Any],
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []
    if not isinstance(resolution, Mapping):
        return ["resolution must be an object"]
    try:
        reasons = _reason_by_code(reason_catalog)
        actions = _action_by_id(next_action_matrix)
        mappings = _mapping_by_code(next_action_matrix)
    except FailureGuidanceError as exc:
        return [str(exc)]
    selected = resolution.get("selected_reason")
    action = resolution.get("next_action")
    safety = resolution.get("safety")
    provenance = resolution.get("provenance")
    if not isinstance(selected, Mapping) or selected.get("code") not in reasons:
        errors.append("selected reason is not in the catalog")
    if not isinstance(action, Mapping) or action.get("action_id") not in actions:
        errors.append("selected action is not in the matrix")
    if isinstance(selected, Mapping) and isinstance(action, Mapping):
        mapping = mappings.get(str(selected.get("code")), {})
        if mapping.get("next_action_id") != action.get("action_id") or mapping.get("action_count") != 1:
            errors.append("selected reason does not resolve to exactly one action")
    expected_safety = {
        "automatic_selection_only": True,
        "external_effect_performed": False,
        "order_submitted": False,
        "order_retried": False,
        "incremental_cash_spent_aud": "0.00",
        "evidence_numeric_risk_or_safety_gate_relaxed": False,
        "owner_final_order_only": True,
        "boundary_zh": "当前只展示一个安全下一步，不执行外部动作；最终下单只能由用户在全部门通过后自行决定并完成。",
    }
    if safety != expected_safety:
        errors.append("resolution safety boundary differs")
    if resolution.get("status") != "FAIL_CLOSED":
        errors.append("resolution status is not fail closed")
    if resolution.get("numeric_boundary_delta") not in ALLOWED_NUMERIC_BOUNDARY_DELTAS:
        errors.append("numeric boundary delta is not frozen")
    if not isinstance(provenance, Mapping):
        errors.append("resolution provenance is unavailable")
    else:
        for key in ["input_sha256", "reason_catalog_sha256", "next_action_matrix_sha256", "artifact_sha256"]:
            if not isinstance(provenance.get(key), str) or SHA256_PATTERN.fullmatch(str(provenance.get(key))) is None:
                errors.append("invalid provenance hash: %s" % key)
        if provenance.get("reason_catalog_sha256") != _canonical_sha256(reason_catalog):
            errors.append("reason catalog hash differs")
        if provenance.get("next_action_matrix_sha256") != _canonical_sha256(next_action_matrix):
            errors.append("next action matrix hash differs")
        if provenance.get("artifact_sha256") != _resolution_artifact_hash(resolution):
            errors.append("resolution artifact hash differs")
    violations = scan_ui_text(
        render_failure_guidance(resolution),
        "USER_ERROR_NEXT_ACTION",
        glossary,
        policy,
    )
    if violations:
        errors.append("visible guidance violates Chinese UI policy: %s" % violations)
    return errors


def _json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("invalid JSON pointer")
    current = value
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, Mapping):
            current = current[part]
        else:
            raise ValueError("JSON pointer traversed a scalar")
    return current


def _coverage_source_keys(root: Path, group: Mapping[str, Any]) -> List[str]:
    kind = group.get("source_kind")
    if kind == "P02_DERIVED_FAILURE_CODES":
        values = group.get("expected_source_keys")
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError("derived P02 coverage keys are malformed")
        return list(values)
    artifact = group.get("source_artifact")
    pointer = group.get("source_pointer")
    if not isinstance(artifact, str) or not isinstance(pointer, str):
        raise ValueError("coverage source path is malformed")
    source = strict_json_load(root / artifact)
    collection = _json_pointer(source, pointer)
    if kind == "ARRAY_OBJECT_KEY":
        key_field = group.get("key_field")
        if not isinstance(collection, list) or not isinstance(key_field, str):
            raise ValueError("array-object coverage source is malformed")
        return [str(row[key_field]) for row in collection]
    if kind == "OBJECT_KEYS":
        if not isinstance(collection, Mapping):
            raise ValueError("object coverage source is malformed")
        return [str(key) for key in collection]
    if kind == "ARRAY_SCALAR":
        if not isinstance(collection, list) or not all(isinstance(item, str) for item in collection):
            raise ValueError("scalar-array coverage source is malformed")
        return list(collection)
    raise ValueError("unknown coverage source kind: %s" % kind)


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in {**PINNED_BASELINE_HASHES, **PINNED_PHASE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S03P03-HASH-" + relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
    workflow = root.parent / CONTINUOUS_WORKFLOW_PATH
    actual_workflow = sha256_file(workflow) if workflow.is_file() else "MISSING"
    hashes[CONTINUOUS_WORKFLOW_PATH.as_posix()] = actual_workflow
    _add(
        checks,
        "S03P03-HASH-CONTINUOUS-WORKFLOW",
        actual_workflow == "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
        actual_workflow,
    )


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    graph = strict_json_load(root / "machine/facts/task_graph.json")
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    requirement = [row for row in requirements if row.get("id") == REQUIREMENT_ID]
    expected_scope = [REASON_CODES_PATH.as_posix(), NEXT_ACTION_MATRIX_PATH.as_posix()]
    requirement_ok = (
        len(requirement) == 1
        and requirement[0].get("scope") == expected_scope
        and requirement[0].get("target") == "每个失败状态只有一个明确下一步。"
        and requirement[0].get("non_goals") == [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
    )
    _add(checks, "S03P03-TASKPACK-REQUIREMENT-EXACT", requirement_ok, requirement)
    contracts = [row for row in acceptance if row.get("id") == CONTRACT_ID]
    contract_ok = (
        len(contracts) == 1
        and contracts[0].get("requirement_id") == REQUIREMENT_ID
        and contracts[0].get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S03-P03 --evidence machine/evidence"
        and contracts[0].get("threshold") == "每个失败状态只有一个明确下一步。"
        and contracts[0].get("pass_gate") == "每个失败状态只有一个明确下一步。"
        and len(contracts[0].get("tests", [])) == 3
    )
    _add(checks, "S03P03-TASKPACK-ACCEPTANCE-EXACT", contract_ok, contracts)
    tasks = [row for row in graph.get("tasks", []) if row.get("stage_id") == "S03" and row.get("phase_id") == "P03"]
    task_ok = (
        [row.get("id") for row in tasks] == ["T-S03-P03-01", "T-S03-P03-02", "T-S03-P03-03"]
        and tasks[0].get("outputs") == expected_scope
        and tasks[1].get("outputs") == [TEST_PATH.as_posix(), ORACLE_FIXTURE_PATH.as_posix()]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
        and tasks[0].get("depends_on") == ["T-S03-P02-03"]
        and tasks[1].get("depends_on") == ["T-S03-P03-01"]
        and tasks[2].get("depends_on") == ["T-S03-P03-02"]
    )
    _add(checks, "S03P03-TASKPACK-TASK-GRAPH-EXACT", task_ok, [row.get("id") for row in tasks])
    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    trace_ok = len(trace) == 1 and trace[0] == {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S03-P03-01", "T-S03-P03-02", "T-S03-P03-03"],
        "test_ids": ["TEST-S03-P03", "TEST-S03-P03-BOUNDARY", "TEST-S03-P03-REPLAY"],
        "evidence_id": "EVD-S03-P03",
        "artifact_ids": ["ART-S03-P03-01", "ART-S03-P03-02"],
        "stage_id": "S03",
        "phase_id": "P03",
    }
    _add(checks, "S03P03-TASKPACK-TRACEABILITY-EXACT", trace_ok, trace)


def _check_catalog_and_matrix(
    root: Path,
    catalog: Any,
    matrix: Any,
    fixture: Any,
    checks: List[Dict[str, Any]],
) -> None:
    if not isinstance(catalog, Mapping) or not isinstance(matrix, Mapping) or not isinstance(fixture, Mapping):
        _add(checks, "S03P03-CORE-ARTIFACTS-AVAILABLE", False, "one or more artifacts unavailable")
        return
    catalog_shape = (
        catalog.get("schema_version") == "1.0.0"
        and catalog.get("product_version") == VERSION
        and catalog.get("stage_id") == "S03"
        and catalog.get("phase_id") == "P03"
        and catalog.get("contract_id") == CONTRACT_ID
        and catalog.get("requirement_id") == REQUIREMENT_ID
        and catalog.get("default_reason_code") == "UNKNOWN_FAILURE_STATE"
        and catalog.get("coverage_status") == "ALL_CURRENTLY_DECLARED_FAILURE_CLASSES_CLOSED_FUTURE_PHASES_MUST_EXTEND"
        and catalog.get("render_contract", {}).get("machine_code_visible") is False
        and catalog.get("safety", {}).get("automatic_order_present") is False
        and catalog.get("safety", {}).get("order_retry_present") is False
        and catalog.get("safety", {}).get("target_shortfall_may_relax_gate") is False
        and catalog.get("safety", {}).get("incremental_cash_budget_aud") == "0.00"
        and not _contains_float(catalog)
    )
    _add(checks, "S03P03-CATALOG-SHAPE-AND-SAFETY", catalog_shape, catalog.get("catalog_id"))
    matrix_shape = (
        matrix.get("schema_version") == "1.0.0"
        and matrix.get("product_version") == VERSION
        and matrix.get("stage_id") == "S03"
        and matrix.get("phase_id") == "P03"
        and matrix.get("contract_id") == CONTRACT_ID
        and matrix.get("selection_rule", {}).get("mode") == "LOWEST_UNIQUE_PRIORITY_WINS"
        and matrix.get("selection_rule", {}).get("input_order_changes_result") is False
        and matrix.get("selection_rule", {}).get("output_action_count") == 1
        and matrix.get("selection_rule", {}).get("numeric_boundary_delta_allowed") == ["-0.0001", "0", "0.0001"]
        and matrix.get("safety", {}).get("automatic_external_action_count") == 0
        and matrix.get("safety", {}).get("order_submission_action_count") == 0
        and matrix.get("safety", {}).get("order_retry_action_count") == 0
        and matrix.get("safety", {}).get("paid_action_count") == 0
        and matrix.get("safety", {}).get("gate_relaxation_action_count") == 0
        and matrix.get("safety", {}).get("irreversible_action_count") == 0
        and not _contains_float(matrix)
    )
    _add(checks, "S03P03-MATRIX-SHAPE-AND-SAFETY", matrix_shape, matrix.get("matrix_id"))
    try:
        reasons = _reason_by_code(catalog)
        actions = _action_by_id(matrix)
        mappings = _mapping_by_code(matrix)
    except Exception as exc:
        _add(checks, "S03P03-UNIQUE-LOOKUPS", False, "%s: %s" % (type(exc).__name__, exc))
        return
    expected_codes = fixture.get("expected_reason_codes")
    expected_actions = fixture.get("expected_action_ids")
    _add(checks, "S03P03-REASON-CODE-SET-EXACT", list(reasons) == expected_codes, list(reasons))
    _add(checks, "S03P03-ACTION-SET-EXACT", list(actions) == expected_actions, list(actions))
    _add(checks, "S03P03-MAPPING-SET-EXACT", list(mappings) == expected_codes, list(mappings))
    for code, reason in reasons.items():
        fields_ok = (
            reason.get("code") == code
            and reason.get("category") in {
                "SYSTEM", "SECURITY", "EVIDENCE", "LEDGER", "COMPLIANCE", "AUTHORIZATION",
                "BUDGET", "GOVERNANCE", "EMAIL", "BUILD", "RUNTIME", "NUMERIC", "COVERAGE",
                "MODEL", "MARKET", "SOURCE", "RISK", "INPUT", "DELIVERY", "ACCOUNT",
                "LANGUAGE", "TARGET",
            }
            and reason.get("severity") in {"CRITICAL", "BLOCKING", "DEGRADED", "INFORMATION"}
            and isinstance(reason.get("priority"), int)
            and not isinstance(reason.get("priority"), bool)
            and _contains_chinese(reason.get("title_zh"))
            and _contains_chinese(reason.get("message_zh"))
            and isinstance(reason.get("coverage_refs"), list)
            and bool(reason.get("coverage_refs"))
            and reason.get("default_next_action_id") in actions
        )
        _add(checks, "S03P03-REASON-%s" % code, fields_ok, reason)
    for action_id, action in actions.items():
        flags_ok = (
            action.get("action_id") == action_id
            and _contains_chinese(action.get("title_zh"))
            and _contains_chinese(action.get("system_behavior_zh"))
            and _contains_chinese(action.get("owner_guidance_zh"))
            and action.get("automatic_selection") is True
            and action.get("external_effect_performed") is False
            and action.get("may_submit_order") is False
            and action.get("may_retry_order") is False
            and action.get("may_spend_cash") is False
            and action.get("may_relax_evidence_numeric_risk_or_safety_gate") is False
            and action.get("irreversible") is False
            and action.get("incremental_cash_cost_aud") == "0.00"
        )
        visible = "\n".join(
            str(action.get(key, ""))
            for key in ["title_zh", "system_behavior_zh", "owner_guidance_zh"]
        )
        flags_ok = flags_ok and not scan_ui_text(visible, "USER_ERROR_NEXT_ACTION", strict_json_load(root / GLOSSARY_PATH), strict_json_load(root / FORBIDDEN_PATH))
        _add(checks, "S03P03-ACTION-%s" % action_id, flags_ok, action)
    for code, mapping in mappings.items():
        exact = (
            mapping.get("reason_code") == code
            and mapping.get("priority") == reasons[code].get("priority")
            and mapping.get("next_action_id") == reasons[code].get("default_next_action_id")
            and mapping.get("next_action_id") in actions
            and mapping.get("action_count") == 1
            and mapping.get("retry_policy") == "NO_ORDER_RETRY"
        )
        _add(checks, "S03P03-MAPPING-%s" % code, exact, mapping)

    expected_refs: Dict[str, str] = {}
    groups = fixture.get("coverage_groups", [])
    for group in groups if isinstance(groups, list) else []:
        group_id = group.get("id")
        mappings_for_group = group.get("mappings")
        try:
            actual_keys = _coverage_source_keys(root, group)
        except Exception as exc:
            _add(checks, "S03P03-COVERAGE-SOURCE-%s" % group_id, False, "%s: %s" % (type(exc).__name__, exc))
            continue
        expected_keys = list(mappings_for_group) if isinstance(mappings_for_group, Mapping) else []
        _add(checks, "S03P03-COVERAGE-SOURCE-%s" % group_id, actual_keys == expected_keys, {"actual": actual_keys, "expected": expected_keys})
        for key, code in mappings_for_group.items() if isinstance(mappings_for_group, Mapping) else []:
            reference = "%s:%s" % (group_id, key)
            expected_refs[reference] = str(code)
            present = code in reasons and reference in reasons[str(code)].get("coverage_refs", [])
            _add(checks, "S03P03-COVERAGE-REF-%s" % _sha256_bytes(reference.encode("utf-8"))[:12].upper(), present, {"reference": reference, "reason_code": code})
    actual_refs = {
        reference: code
        for code, reason in reasons.items()
        for reference in reason.get("coverage_refs", [])
        if isinstance(reference, str)
    }
    _add(
        checks,
        "S03P03-COVERAGE-REFERENCE-SET-EXACT",
        actual_refs == expected_refs and len(actual_refs) == fixture.get("expected_coverage_reference_count"),
        {"actual": len(actual_refs), "expected": fixture.get("expected_coverage_reference_count")},
    )


def _build_p02_card(root: Path, decision: Mapping[str, Any], *, safe: bool = False) -> Dict[str, Any]:
    kwargs = {
        "schema": strict_json_load(root / ADVICE_SCHEMA_PATH),
        "glossary": strict_json_load(root / GLOSSARY_PATH),
        "policy": strict_json_load(root / FORBIDDEN_PATH),
        "parameters_sha256": sha256_file(root / PARAMETERS_PATH),
        "model_sha256": sha256_file(root / MODEL_CARD_PATH),
    }
    if safe:
        return safe_build_advice_card(decision, **kwargs)
    return build_advice_card(decision, **kwargs)


def _check_p02_integration(
    root: Path,
    catalog: Mapping[str, Any],
    matrix: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    p02 = strict_json_load(root / ADVICE_FIXTURES_PATH)
    observed_raw_codes: set[str] = set()
    no_opportunity = _build_p02_card(root, copy.deepcopy(p02["base_no_recommendation_input"]))
    observed_raw_codes.update(str(row.get("code")) for row in no_opportunity.get("reasons", []))
    for vector in p02.get("boundary_vectors", []):
        decision = copy.deepcopy(p02["base_recommendation_input"])
        decision.update(vector.get("overrides", {}))
        decision["vector_id"] = "P03-" + str(vector.get("id"))
        card = _build_p02_card(root, decision)
        if card.get("status") == "NO_RECOMMENDATION":
            observed_raw_codes.update(str(row.get("code")) for row in card.get("reasons", []))
    for vector in p02.get("gate_failure_vectors", []):
        decision = copy.deepcopy(p02["base_recommendation_input"])
        decision["vector_id"] = "P03-" + str(vector.get("id"))
        decision["gates"][vector["gate"]] = False
        card = _build_p02_card(root, decision)
        observed_raw_codes.update(str(row.get("code")) for row in card.get("reasons", []))
        resolved = resolve_failure_states(
            card.get("reasons"),
            reason_catalog=catalog,
            next_action_matrix=matrix,
        )
        group = next(row for row in fixture["coverage_groups"] if row["id"] == "P02-GATES")
        expected = group["mappings"][vector["id"]]
        _add(checks, "S03P03-P02-GATE-%s" % vector["id"], resolved["selected_reason"]["code"] == expected, resolved)
    malformed = copy.deepcopy(p02["base_recommendation_input"])
    malformed["platform_zh"] = None
    invalid_card = _build_p02_card(root, malformed, safe=True)
    observed_raw_codes.update(str(row.get("code")) for row in invalid_card.get("reasons", []))
    expected_raw = set(fixture.get("expected_p02_raw_failure_codes", []))
    _add(checks, "S03P03-P02-RAW-FAILURE-CODES-EXACT", observed_raw_codes == expected_raw, sorted(observed_raw_codes))
    for vector in fixture.get("p02_reason_vectors", []):
        resolution = resolve_failure_states(
            vector.get("input"),
            reason_catalog=catalog,
            next_action_matrix=matrix,
        )
        _add(
            checks,
            "S03P03-P02-REASON-%s" % vector.get("id"),
            resolution["selected_reason"]["code"] == vector.get("expected_reason_code")
            and not validate_resolution(
                resolution,
                reason_catalog=catalog,
                next_action_matrix=matrix,
                glossary=strict_json_load(root / GLOSSARY_PATH),
                policy=strict_json_load(root / FORBIDDEN_PATH),
            ),
            resolution,
        )


def _check_resolution_vectors(
    root: Path,
    catalog: Mapping[str, Any],
    matrix: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    glossary = strict_json_load(root / GLOSSARY_PATH)
    policy = strict_json_load(root / FORBIDDEN_PATH)
    for vector in fixture.get("multi_failure_vectors", []):
        first = resolve_failure_states(vector.get("input"), reason_catalog=catalog, next_action_matrix=matrix)
        second = resolve_failure_states(copy.deepcopy(vector.get("input")), reason_catalog=catalog, next_action_matrix=matrix)
        ok = (
            first == second
            and first["selected_reason"]["code"] == vector.get("expected_reason_code")
            and first["considered_count"] == len(set(first["considered_reason_codes"]))
            and not validate_resolution(first, reason_catalog=catalog, next_action_matrix=matrix, glossary=glossary, policy=policy)
        )
        _add(checks, "S03P03-MULTI-%s" % vector.get("id"), ok, first)
    for vector in fixture.get("malformed_inputs", []):
        resolved = safe_resolve_failure_states(vector.get("input"), reason_catalog=catalog, next_action_matrix=matrix)
        ok = (
            resolved["selected_reason"]["code"] == "UNKNOWN_FAILURE_STATE"
            and resolved["next_action"]["action_id"] == "STOP_AND_PRESERVE"
            and not validate_resolution(resolved, reason_catalog=catalog, next_action_matrix=matrix, glossary=glossary, policy=policy)
        )
        _add(checks, "S03P03-MALFORMED-%s" % vector.get("id"), ok, resolved)
    base = ["CURRENT_ODDS_BELOW_MINIMUM"]
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        resolved = resolve_failure_states(base, reason_catalog=catalog, next_action_matrix=matrix, numeric_boundary_delta=delta)
        _add(
            checks,
            "S03P03-NUMERIC-BOUNDARY-%s" % delta.replace("-", "MINUS").replace(".", "_"),
            resolved["selected_reason"]["code"] == "CURRENT_ODDS_BELOW_MINIMUM"
            and resolved["next_action"]["action_id"] == "WAIT_FOR_ACCEPTABLE_ODDS"
            and not validate_resolution(resolved, reason_catalog=catalog, next_action_matrix=matrix, glossary=glossary, policy=policy),
            resolved,
        )


def _check_p04_not_started(
    root: Path,
    checks: List[Dict[str, Any]],
    *,
    verify_git_history: bool,
) -> None:
    core = [
        Path("ux_test_plan.json"),
        Path("accessibility_report.json"),
        Path("tests/S03/P04_test.py"),
        Path("machine/tests/fixtures/S03_P04.json"),
    ]
    receipts = [
        Path("machine/evidence/EVD-S03-P04.json"),
        Path("machine/evidence/EVD-S03-P04_rollback.json"),
    ]
    later = [
        Path("machine/facts/stage3_review_contract.json"),
        Path("machine/evidence/S03/STAGE_REVIEW/findings.json"),
        Path("machine/tests/fixtures/S03_STAGE_REVIEW.json"),
        Path("tests/S03/stage_review_test.py"),
        Path("machine/evidence/EVD-S03-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S03-STAGE-REVIEW_rollback.json"),
    ]
    present_core = [path for path in core if (root / path).is_file()]
    present_receipts = [path for path in receipts if (root / path).is_file()]
    present_later = [path for path in later if (root / path).exists()]
    stage_progression: Mapping[str, Any] = {"status": "READY_NOT_STARTED"}
    if present_later:
        try:
            from .usability_accessibility import _stage_review_progression

            stage_progression = _stage_review_progression(root)
        except Exception as exc:
            stage_progression = {"status": "INVALID", "error": "%s: %s" % (type(exc).__name__, exc)}
    stage_progression_ok = stage_progression.get("status") in {"CONTROLLED_CANDIDATE", "SIGNED_REVIEW_PASS"}
    mode = "INVALID_PARTIAL_OR_LATER_SUCCESSOR"
    artifacts_ok = False
    successor: Any = None
    if not present_core and not present_receipts and not present_later:
        mode = "P04_NOT_STARTED"
        artifacts_ok = True
    elif len(present_core) == len(core) and not present_receipts and not present_later:
        from .usability_accessibility import PINNED_PHASE_HASHES as P04_PINNED_PHASE_HASHES

        actual = {path.as_posix(): sha256_file(root / path) for path in core}
        artifacts_ok = actual == {path.as_posix(): P04_PINNED_PHASE_HASHES[path.as_posix()] for path in core}
        mode = "P04_CONTROLLED_BUILD" if artifacts_ok else "P04_CONTROLLED_BUILD_HASH_MISMATCH"
        successor = actual
    elif len(present_core) == len(core) and len(present_receipts) == len(receipts) and (not present_later or stage_progression_ok):
        from .usability_accessibility import verify_existing_phase_evidence as verify_p04_evidence

        successor = verify_p04_evidence(root, verify_git_history=verify_git_history)
        artifacts_ok = successor.get("status") == "PASS" and successor.get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED"
        if artifacts_ok:
            mode = "P04_SIGNED_DELIVERY_WITH_STAGE_REVIEW" if present_later else "P04_SIGNED_DELIVERY"
        else:
            mode = "P04_SIGNED_DELIVERY_INVALID"
    _add(
        checks,
        "S03P03-SUCCESSOR-ARTIFACTS-NOT-STARTED",
        artifacts_ok,
        {
            "mode": mode,
            "core": [path.as_posix() for path in present_core],
            "receipts": [path.as_posix() for path in present_receipts],
            "later": [path.as_posix() for path in present_later],
            "stage_progression": stage_progression,
            "successor": successor,
        },
    )
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P04"]
        if mode in {"P04_SIGNED_DELIVERY", "P04_SIGNED_DELIVERY_WITH_STAGE_REVIEW"}:
            ok = (
                len(matching) == 1
                and matching[0].get("status") == "PASS"
                and matching[0].get("actual_artifact") == "machine/evidence/EVD-S03-P04.json"
                and matching[0].get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED"
            )
        else:
            ok = (
                artifacts_ok
                and len(matching) == 1
                and matching[0].get("status") == "PLANNED"
                and "actual_artifact" not in matching[0]
                and "artifact_sha256" not in matching[0]
            )
        _add(checks, "S03P03-SUCCESSOR-INDEX-PLANNED", ok, matching)
    except Exception as exc:
        _add(checks, "S03P03-SUCCESSOR-INDEX-PLANNED", False, "%s: %s" % (type(exc).__name__, exc))


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/reason_next_action.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r'\1<NORMALIZED>\2',
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    for element in root.iter():
        if element.tag == "testsuite":
            if element.attrib.get("hostname") is not None:
                return False
            if element.attrib.get("timestamp") != JUNIT_FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _pack_report_passes(report: Any) -> bool:
    if not isinstance(report, Mapping):
        return False
    summary = report.get("summary", {})
    return (
        isinstance(summary, Mapping)
        and report.get("status") == "PASS"
        and summary.get("checks") == 49
        and summary.get("passed") == 49
        and summary.get("failed") == 0
    )


def _paid_dependency_scan_passes(scan_text: Any) -> bool:
    if not isinstance(scan_text, str):
        return False
    required_lines = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    return required_lines.issubset(set(scan_text.splitlines()))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "FAILURE_REASON_AND_UNIQUE_NEXT_ACTION_CONTRACT_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "phase_status": "S03_P03_PASS" if status == "PASS" else "S03_P03_FAILED",
        "user_interface_status": "CHINESE_REASON_AND_LOCAL_GUIDANCE_CONTRACT_ONLY_NOT_DEPLOYED",
        "coverage_status": "ALL_CURRENTLY_DECLARED_FAILURE_CLASSES_CLOSED_FUTURE_PHASES_MUST_EXTEND" if status == "PASS" else "UNVERIFIED",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "release_status": "NOT_READY_S03_P04_AND_STAGE_REVIEW_REQUIRED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "next": "S03/P04_READY_NOT_STARTED" if status == "PASS" else "S03/P03_REMEDIATION_REQUIRED",
    }


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    catalog = _safe_load(root / REASON_CODES_PATH, checks, "S03P03-CATALOG-STRICT-JSON")
    matrix = _safe_load(root / NEXT_ACTION_MATRIX_PATH, checks, "S03P03-MATRIX-STRICT-JSON")
    fixture = _safe_load(root / ORACLE_FIXTURE_PATH, checks, "S03P03-FIXTURE-STRICT-JSON")
    _check_pinned_hashes(root, checks, hashes)
    self_hash = _structural_self_hash(root)
    hashes["abd_acceptance/reason_next_action.py"] = sha256_file(root / "abd_acceptance/reason_next_action.py")
    _add(checks, "S03P03-ORACLE-SELF-INTEGRITY", self_hash == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_hash})
    try:
        predecessor = verify_p02_evidence(root, verify_git_history=_verify_git_history)
        _add(
            checks,
            "S03P03-P02-PREREQUISITE",
            predecessor.get("status") == "PASS"
            and predecessor.get("decision") == "S03_P02_EVIDENCE_VERIFIED"
            and predecessor.get("next") == "S03/P03_READY_NOT_STARTED",
            predecessor.get("summary"),
        )
    except Exception as exc:
        _add(checks, "S03P03-P02-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_taskpack(root, checks)
    except Exception as exc:
        _add(checks, "S03P03-TASKPACK-AVAILABLE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_catalog_and_matrix(root, catalog, matrix, fixture, checks)
    if isinstance(catalog, Mapping) and isinstance(matrix, Mapping) and isinstance(fixture, Mapping):
        try:
            _check_p02_integration(root, catalog, matrix, fixture, checks)
        except Exception as exc:
            _add(checks, "S03P03-P02-INTEGRATION", False, "%s: %s" % (type(exc).__name__, exc))
        try:
            _check_resolution_vectors(root, catalog, matrix, fixture, checks)
        except Exception as exc:
            _add(checks, "S03P03-RESOLUTION-VECTORS", False, "%s: %s" % (type(exc).__name__, exc))
        _check_p04_not_started(root, checks, verify_git_history=_verify_git_history)
    else:
        _add(checks, "S03P03-CORE-ARTIFACTS-AVAILABLE", False, "one or more core artifacts unavailable")

    if require_external_reports and isinstance(fixture, Mapping):
        for relative, check_id, minimum_key in [
            (JUNIT_PATH, "S03P03-TARGETED-JUNIT", "minimum_targeted_pytest_cases"),
            (FULL_JUNIT_PATH, "S03P03-FULL-JUNIT", "minimum_full_pytest_cases"),
        ]:
            try:
                summary = _junit_summary(root / relative)
                normalized = _junit_is_normalized(root / relative)
                hashes[relative.as_posix()] = sha256_file(root / relative)
                passed = (
                    summary["tests"] >= int(fixture.get(minimum_key, 0))
                    and summary["failures"] == 0
                    and summary["errors"] == 0
                    and summary["skipped"] == 0
                    and normalized
                )
                _add(checks, check_id, passed, {**summary, "normalized": normalized})
            except Exception as exc:
                _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            report = strict_json_load(root / PACK_REPORT_PATH)
            hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
            _add(checks, "S03P03-PACK-REPORT", _pack_report_passes(report), report)
        except Exception as exc:
            _add(checks, "S03P03-PACK-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
        try:
            scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
            hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
            _add(checks, "S03P03-PAID-DEPENDENCY-SCAN", _paid_dependency_scan_passes(scan_text), scan_text.strip())
        except Exception as exc:
            _add(checks, "S03P03-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))

    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0)) if isinstance(fixture, Mapping) else 0
    if result["summary"]["checks"] < minimum:
        _add(checks, "S03P03-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
        result = _build_result(checks, hashes)
    return result


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = [
        REASON_CODES_PATH,
        NEXT_ACTION_MATRIX_PATH,
        ORACLE_FIXTURE_PATH,
        P02_EVIDENCE_PATH,
        ADVICE_SCHEMA_PATH,
        GLOSSARY_PATH,
    ]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s03-p03-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(artifacts):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
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
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_REASON_AND_ACTION_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        REASON_CODES_PATH,
        NEXT_ACTION_MATRIX_PATH,
        ORACLE_FIXTURE_PATH,
        TEST_PATH,
        GLOSSARY_PATH,
        FORBIDDEN_PATH,
        ADVICE_SCHEMA_PATH,
        ADVICE_FIXTURES_PATH,
        P02_ORACLE_FIXTURE_PATH,
        P02_TEST_PATH,
        P02_EVIDENCE_PATH,
        P02_ROLLBACK_PATH,
        PARAMETERS_PATH,
        MODEL_CARD_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("machine/facts/decision_prerequisites.json"),
        Path("machine/facts/provider_contracts.json"),
        Path("machine/facts/release_policy.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/risk_register.json"),
        Path("machine/facts/email_ingestion.json"),
        Path("README.md"),
        Path("abd_acceptance/reason_next_action.py"),
        Path("abd_acceptance/advice_card.py"),
        Path("abd_acceptance/terminology_governance.py"),
        Path("abd_acceptance/__main__.py"),
        Path("abd_acceptance/__init__.py"),
        Path("tests/__init__.py"),
        Path("tests/S03/__init__.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[CONTINUOUS_WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / CONTINUOUS_WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S03-P03-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
            "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["phase_status"] = "S03_P03_FAILED"
        result["next"] = "S03/P03_REMEDIATION_REQUIRED"
    input_hashes = _input_hashes(root)
    boundary = strict_json_load(root / ORACLE_FIXTURE_PATH)["expected_external_effect_boundary"]
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S03",
        "phase_id": "P03",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S03-P03-01": REASON_CODES_PATH.as_posix(),
            "ART-S03-P03-02": NEXT_ACTION_MATRIX_PATH.as_posix(),
        },
        "p02_delivery_prerequisite": {
            "evidence": P02_EVIDENCE_PATH.as_posix(),
            "evidence_sha256": PINNED_BASELINE_HASHES[P02_EVIDENCE_PATH.as_posix()],
            "rollback_sha256": PINNED_BASELINE_HASHES[P02_ROLLBACK_PATH.as_posix()],
            "status": "PASS",
            "decision": "S03_P02_EVIDENCE_VERIFIED",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes[PARAMETERS_PATH.as_posix()],
            "code": _current_code_hash(root),
            "model": input_hashes[MODEL_CARD_PATH.as_posix()],
            "model_not_executed_reason": "S03/P03 freezes deterministic Chinese failure guidance from current signed facts and synthetic fixtures; it executes no prediction model, provider interaction, deployment, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P03_test.py --junitxml=machine/evidence/S03/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S03/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S03-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {
            "artifact": ROLLBACK_EVIDENCE_PATH.as_posix(),
            "status": rollback.get("status"),
        },
        "external_effect_boundary": dict(boundary),
        "explicit_unknowns": [
            "S03/P03 freezes Chinese failure guidance and one local safe next action for every currently declared failure class; it does not implement future phase runtime behavior.",
            "No web, mobile, accessibility, notification or browser interface has been implemented or deployed; S03/P04 human usability and accessibility validation has not started.",
            "TAB, Gmail, OVH and Cloudflare account, authorization, capacity and runtime states remain uninspected or unverified and fail closed.",
            "All resolution vectors are synthetic and offline; no source, account, quote, model, stake or order was selected or executed.",
            "Future phases must version and extend the closed catalog before a new failure state can enter a user interface.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
        ],
        "release_status": "NOT_READY_S03_P04_AND_STAGE_REVIEW_REQUIRED",
        "phase_status": result["phase_status"],
        "next": result["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P03"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S03-P03 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S03/P04_READY_NOT_STARTED" if status == "PASS" else "S03/P03_REMEDIATION_REQUIRED"
    payload = b"".join(
        (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for item in rows
    )
    _atomic_write(path, payload)


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence directory must be inside the ABD project root") from exc
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


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(
    root: Path,
    relative: str,
    expected_sha256: str,
    verify_git_history: bool,
) -> bool:
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
    if relative == "abd_acceptance/reason_next_action.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    evolved = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return evolved is not None and (root / relative).is_file() and sha256_file(root / relative) == evolved


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


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S03P03-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S03P03-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S03-P03"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S03"
            and evidence.get("phase_id") == "P03"
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "FAILURE_REASON_AND_UNIQUE_NEXT_ACTION_CONTRACT_FROZEN"
            and evidence.get("phase_status") == "S03_P03_PASS"
            and evidence.get("next") == "S03/P04_READY_NOT_STARTED"
            and evidence.get("artifacts") == {
                "ART-S03-P03-01": REASON_CODES_PATH.as_posix(),
                "ART-S03-P03-02": NEXT_ACTION_MATRIX_PATH.as_posix(),
            }
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S03P03-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            isinstance(validation, Mapping)
            and validation.get("status") == "PASS"
            and validation.get("decision") == "FAILURE_REASON_AND_UNIQUE_NEXT_ACTION_CONTRACT_FROZEN"
            and validation.get("summary", {}).get("failed") == 0
            and validation.get("next") == "S03/P04_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S03P03-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        boundary = strict_json_load(root / ORACLE_FIXTURE_PATH).get("expected_external_effect_boundary")
        _add(checks, "S03P03-RECEIPT-NO-EXTERNAL-EFFECT", evidence.get("external_effect_boundary") == boundary, evidence.get("external_effect_boundary"))
        input_errors: List[Any] = []
        signed_inputs = evidence.get("hashes", {}).get("inputs", {})
        if not isinstance(signed_inputs, Mapping):
            signed_inputs = {}
            input_errors.append("signed inputs unavailable")
        for relative, expected in signed_inputs.items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "reason": "unsafe path"})
                continue
            path = root.parent / candidate if str(relative).startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                if _historical_file_matches(root, relative, expected, verify_git_history):
                    continue
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03P03-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or len(signed_inputs))
        reports: List[Any] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), PACK_REPORT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()]:
            expected = validation_hashes.get(relative)
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if expected != actual:
                reports.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03P03-RECEIPT-REPORT-HASHES-CURRENT", not reports, reports or "all reports match")
        code_expected = evidence.get("hashes", {}).get("code")
        code_current = _current_code_hash(root)
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (
            code_expected == PINNED_PHASE_CODE_HASH
            and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(
            checks,
            "S03P03-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_current, "historical_phase_commit": code_historical},
        )
        _add(checks, "S03P03-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        portable = (
            str(root) not in rendered
            and ("/" + "Users/") not in rendered
            and ("/private/" + "var/") not in rendered
            and ("file" + "://") not in rendered
            and ("C:" + "\\Users\\") not in rendered
        )
        _add(checks, "S03P03-RECEIPT-NO-ABSOLUTE-LOCAL-PATH", portable, "portable" if portable else "local path found")
    else:
        for check_id in [
            "S03P03-RECEIPT-EVIDENCE-INTEGRITY",
            "S03P03-RECEIPT-VALIDATION-ALL-PASS",
            "S03P03-RECEIPT-NO-EXTERNAL-EFFECT",
            "S03P03-RECEIPT-SIGNED-INPUTS-CURRENT",
            "S03P03-RECEIPT-REPORT-HASHES-CURRENT",
            "S03P03-RECEIPT-CODE-HASH-CURRENT",
            "S03P03-RECEIPT-ROLLBACK-HASH-BINDING",
            "S03P03-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
        ]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S03-P03-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and len(rollback.get("artifacts", {})) == 6
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S03P03-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P03"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and matching[0].get("artifact_sha256") == evidence_hash
            and matching[0].get("next") == "S03/P04_READY_NOT_STARTED"
        )
        _add(checks, "S03P03-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S03P03-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        p02 = verify_p02_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S03P03-RECEIPT-P02-PREREQUISITE", p02.get("status") == "PASS", p02.get("summary"))
    except Exception as exc:
        _add(checks, "S03P03-RECEIPT-P02-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S03-P03",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S03_P03_EVIDENCE_VERIFIED" if not failed else "S03_P03_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S03/P04_READY_NOT_STARTED" if not failed else "S03/P03_REMEDIATION_REQUIRED",
    }
