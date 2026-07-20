from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .open_source_reuse import verify_existing_phase_evidence as verify_s02_p03_evidence


CONTRACT_ID = "AC-S02-P04"
REQUIREMENT_ID = "REQ-S02-P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

GAPS_PATH = Path("research_gaps.json")
COUNTEREVIDENCE_PATH = Path("counterevidence.json")
REVIEW_SCHEDULE_PATH = Path("review_schedule.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S02_P04.json")
TEST_PATH = Path("tests/S02/P04_test.py")
JUNIT_PATH = Path("machine/evidence/S02/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S02/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P04_rollback.json")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S02-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")
PHASE_COMMIT = "d8577c4fabdfe646dd5293a3f6e0f09afa2b1843"
PINNED_PHASE_CODE_HASH = "e79af4ae9b7c97c77c79b1b97c8427c3b7ef4124763fc60132b3b84840e96834"

SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "counterevidence.json",
    "review_schedule.json",
    "machine/tests/fixtures/S02_P04.json",
    "tests/S02/P04_test.py",
    "abd_acceptance/research_gap_audit.py",
    "abd_acceptance/official_platform_research.py",
    "abd_acceptance/model_risk_research.py",
    "abd_acceptance/open_source_reuse.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S02/P01_test.py",
    "tests/S02/P02_test.py",
    "tests/S02/P03_test.py",
}
SUCCESSOR_EVOLVED_SIGNED_INPUT_HASHES: Dict[str, str] = {
    "counterevidence.json": "2cbc2eb289d3278bc106778e4e11e755f8cb1681a0c3e74d619317023d63cae8",
    "review_schedule.json": "6987822fa590d31dc10d0f92f787e94098b82fa9a3a40ed328c840aa45f552ea",
    "machine/tests/fixtures/S02_P04.json": "d4404ae17bfeece51574367ce16ac6f8dfe8bf349615dc6bed8fff86af253923",
    "tests/S02/P04_test.py": "daa8d04cf507be5e37d5c381e83b8ea5243172460b26324c0613c2a33fbb50af",
    "abd_acceptance/__main__.py": "77ed53daf201c59aedd72c9e5d10207997353a5bbd097fa599fd65f9ebb8806a",
    "abd_acceptance/__init__.py": "969ef9ecfa9c9a05e36167b68da678913439fd7e73ff28bbf92f7fa91a512234",
    "abd_acceptance/official_platform_research.py": "e63aa2ddaa020fc85c139c11c9ec9a4e0cb7e25689e67e72d621fe0ba64fbbb4",
    "abd_acceptance/model_risk_research.py": "7bd44e852d3d95fed70c4f4468ac593b82162a71cc15b8ef91efe74d5d4de94d",
    "abd_acceptance/open_source_reuse.py": "678bd7bfec7afd5a19c540d6d4066610fc96d531375632cd02550b469f24e324",
    "tests/S02/P01_test.py": "bc800d7bd6ac82ba5bf8b709013a0e16287750b635d838f6cd4ac885c7364377",
    "tests/S02/P02_test.py": "dcafa1f4120415cf0d191f69654c58392bece7dcfb86e8e698d436ae1f2f68bd",
    "tests/S02/P03_test.py": "3e0bd2ec5eb089a09c6c311ecaca8dd757f3ba9a2dd96f3574434630a2d7d8ae",
}
STAGE2_REVIEW_EXECUTABLE_HASHES = {
    "abd_acceptance/stage2_review.py": "1a57f621620ecb171535c3d77c467c308cc713b1578ee9455a433e961ed52325",
    "tests/S02/stage_review_test.py": "40431438418cb4212c00c3e241b980b4188cd017af2722ffb267670a8aa0f124",
}

P03_EVIDENCE_SHA256 = "5e920362b7ef4070c4507e8707ab749c0863ad76f76f61c0ecefeae8a2f4626a"
P03_ROLLBACK_SHA256 = "f2d2201f4e9c2e202afdc1242e4f15e516684ac4e3fbc698ca255afc62503ee0"

PINNED_PHASE_HASHES = {
    GAPS_PATH.as_posix(): "2c1e1b4b0bbc18859e985066953d72bb60fe08e5d0592da802bf0afd0916bd35",
    COUNTEREVIDENCE_PATH.as_posix(): "2cbc2eb289d3278bc106778e4e11e755f8cb1681a0c3e74d619317023d63cae8",
    REVIEW_SCHEDULE_PATH.as_posix(): "6987822fa590d31dc10d0f92f787e94098b82fa9a3a40ed328c840aa45f552ea",
    FIXTURE_PATH.as_posix(): "d4404ae17bfeece51574367ce16ac6f8dfe8bf349615dc6bed8fff86af253923",
    TEST_PATH.as_posix(): "daa8d04cf507be5e37d5c381e83b8ea5243172460b26324c0613c2a33fbb50af",
}

PINNED_BASELINE_HASHES = {
    "provider_facts_snapshot.json": "a76b514469243d7b0a5c7c4ed3e2b388452d5fd5ded7fdc42aad48d5ebb17b06",
    "regulatory_matrix.json": "5022031f18d910d040221d4e526b87c1b05b118bed4c1da9e655bc7b9d08227f",
    "research_evidence_matrix.json": "5a5dc1a9bbbde177f065f4725df5e7f86f763a43a2530671b2b946135c8f2709",
    "model_claims.json": "66bb20b471a218008b29df81cac77b03c55557b9d07f26b6ef37d0cea7eccd4c",
    "research_reuse_matrix.json": "e5d049c5e4049195f537cce7b27cc8713269d211f55ce4840c10fdf67feac0e8",
    "license_inventory.json": "b09ce2ae8e60ba91d3c436f4116b032c772a19902cfebdcc9f37027c53393379",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    P03_EVIDENCE_PATH.as_posix(): P03_EVIDENCE_SHA256,
    P03_ROLLBACK_PATH.as_posix(): P03_ROLLBACK_SHA256,
}

PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

ALLOWED_GAP_STATES = {"OPEN_EXPLICIT", "RESOLVED_VERIFIED"}
ALLOWED_NUMERIC_DELTA_STRINGS = {"-0.0001", "0", "0.0001"}
ALLOWED_NUMERIC_DELTAS = {Decimal("-0.0001"), Decimal("0"), Decimal("0.0001")}


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


def _duplicates(values: Sequence[Any]) -> List[Any]:
    seen: Set[str] = set()
    result: List[Any] = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen and value not in result:
            result.append(value)
        seen.add(marker)
    return result


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    matches = [row for row in rows if row.get(key) == item_id]
    return matches[0] if len(matches) == 1 else {}


def _valid_routes(mapping: Mapping[str, Any], valid_gap_ids: Set[str]) -> bool:
    return bool(mapping) and all(
        isinstance(routes, list)
        and bool(routes)
        and not _duplicates(routes)
        and set(routes).issubset(valid_gap_ids)
        for routes in mapping.values()
    )


def resolve_gap_disposition(
    *,
    gap_state: str,
    registered: bool,
    has_safe_default: bool,
    review_route_count: int,
    closure_evidence_verified: bool,
    blocks_capability: bool,
    numeric_delta: str,
    adverse_odds_tick: bool,
) -> str:
    if gap_state not in ALLOWED_GAP_STATES:
        raise ValueError("unsupported gap_state")
    for value in (registered, has_safe_default, closure_evidence_verified, blocks_capability, adverse_odds_tick):
        if type(value) is not bool:
            raise TypeError("gap disposition flags must be booleans")
    if type(review_route_count) is not int or review_route_count < 0:
        raise TypeError("review_route_count must be a non-negative integer")
    if not isinstance(numeric_delta, str):
        raise TypeError("numeric_delta must be an exact decimal string")
    if numeric_delta not in ALLOWED_NUMERIC_DELTA_STRINGS:
        raise ValueError("numeric_delta must use a frozen representation")
    try:
        parsed = Decimal(numeric_delta)
    except InvalidOperation as exc:
        raise ValueError("invalid numeric_delta") from exc
    if parsed not in ALLOWED_NUMERIC_DELTAS:
        raise ValueError("numeric_delta is outside the frozen boundary set")

    if not registered:
        return "BLOCK_SILENT_GAP"
    if not has_safe_default:
        return "BLOCK_UNSAFE_OPEN_GAP"
    if review_route_count == 0:
        return "BLOCK_UNSCHEDULED_GAP"
    if gap_state == "RESOLVED_VERIFIED" and not closure_evidence_verified:
        return "BLOCK_FALSE_RESOLUTION"
    if gap_state == "OPEN_EXPLICIT" and closure_evidence_verified:
        return "BLOCK_CONTRADICTORY_GAP_STATE"
    if gap_state == "OPEN_EXPLICIT":
        return "REGISTERED_OPEN_CAPABILITY_BLOCKED" if blocks_capability else "REGISTERED_OPEN_MONITOR"
    return "RESOLVED_VERIFIED"


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in {**PINNED_PHASE_HASHES, **PINNED_BASELINE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S02P04-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S02P04-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack_contract(
    roadmap: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    requirement = _row(requirements, REQUIREMENT_ID)
    req_ok = (
        requirement.get("stage_id") == "S02"
        and requirement.get("phase_id") == "P04"
        and requirement.get("scope") == fixture.get("expected_outputs")
        and requirement.get("target") == "不宣称穷尽互联网；静默研究缺口为零。"
        and requirement.get("non_goals")
        == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
    )
    _add(checks, "S02P04-TASKPACK-REQUIREMENT-EXACT", req_ok, requirement.get("title"))

    contract = _row(acceptance, CONTRACT_ID)
    contract_ok = (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("oracle", {}).get("command")
        == "python -m abd_acceptance --contract AC-S02-P04 --evidence machine/evidence"
        and contract.get("pass_gate") == "不宣称穷尽互联网；静默研究缺口为零。"
        and [row.get("id") for row in contract.get("tests", [])] == fixture.get("expected_test_ids")
        and contract.get("evidence_requirements", [None])[0] == EVIDENCE_PATH.as_posix()
    )
    _add(checks, "S02P04-TASKPACK-ACCEPTANCE-EXACT", contract_ok, contract.get("title"))

    stage = _row(roadmap.get("stages", []), "S02")
    phase = _row(stage.get("phases", []), "P04")
    roadmap_ok = (
        phase.get("title") == "调研缺口与反证"
        and phase.get("outputs") == fixture.get("expected_outputs")
        and phase.get("pass_gate") == "不宣称穷尽互联网；静默研究缺口为零。"
        and stage.get("goal") == "只研究与ABD直接相关的官方文档、论文和开源项目，明确采用、适配、拒绝和许可证。"
    )
    _add(checks, "S02P04-TASKPACK-ROADMAP-EXACT", roadmap_ok, phase.get("objective"))

    tasks = [_row(task_graph.get("tasks", []), task_id) for task_id in fixture.get("expected_task_ids", [])]
    dependencies_ok = (
        len(tasks) == 3
        and tasks[0].get("depends_on") == ["T-S02-P03-03"]
        and tasks[1].get("depends_on") == ["T-S02-P04-01"]
        and tasks[2].get("depends_on") == ["T-S02-P04-02"]
    )
    _add(checks, "S02P04-TASKPACK-TASK-DAG-EXACT", dependencies_ok, [row.get("id") for row in tasks])
    outputs_ok = tasks[0].get("outputs") == fixture.get("expected_outputs") and tasks[1].get("outputs") == [
        TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()
    ] and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
    _add(checks, "S02P04-TASKPACK-TASK-OUTPUTS-EXACT", outputs_ok, [row.get("outputs") for row in tasks])
    task_gates_ok = all(
        row.get("requirement_ids") == [REQUIREMENT_ID]
        and row.get("acceptance_criteria_ids") == [CONTRACT_ID]
        and row.get("pass_gate") == "不宣称穷尽互联网；静默研究缺口为零。"
        and row.get("owner_input_required") is False
        for row in tasks
    )
    _add(checks, "S02P04-TASKPACK-TASK-GATES-EXACT", task_gates_ok, [row.get("pass_gate") for row in tasks])

    trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
    trace_ok = trace == {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": fixture.get("expected_task_ids"),
        "test_ids": fixture.get("expected_test_ids"),
        "evidence_id": "EVD-S02-P04",
        "artifact_ids": fixture.get("expected_artifact_ids"),
        "stage_id": "S02",
        "phase_id": "P04",
    }
    _add(checks, "S02P04-TASKPACK-TRACEABILITY-EXACT", trace_ok, trace)

    stop_expected = {
        "发现法律、监管或来源合同实质冲突且无安全默认",
        "需要不可逆操作",
        "新增现金支出将超过A$0",
        "严重安全事故或证据完整性失败",
        "阶段终止条件被触发",
    }
    _add(checks, "S02P04-TASKPACK-STOP-CONDITIONS-EXACT", set(contract.get("stop_condition", [])) == stop_expected, contract.get("stop_condition"))


def _check_gap_artifact(gaps: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    shape_ok = (
        gaps.get("schema_version") == "1.0.0"
        and gaps.get("artifact_id") == "ART-S02-P04-01"
        and gaps.get("version") == VERSION
        and gaps.get("stage_id") == "S02"
        and gaps.get("phase_id") == "P04"
        and gaps.get("requirement_id") == REQUIREMENT_ID
        and gaps.get("acceptance_contract_id") == CONTRACT_ID
        and gaps.get("as_of") == "2026-07-20"
        and gaps.get("status") == "FROZEN_OPEN_GAPS_EXPLICIT_NO_SILENT_GAPS"
        and gaps.get("next_on_acceptance_pass") == fixture.get("expected_next")
    )
    _add(checks, "S02P04-GAPS-SHAPE", shape_ok, gaps.get("status"))

    rows = gaps.get("gaps", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    expected_ids = fixture.get("expected_gap_ids", [])
    _add(checks, "S02P04-GAPS-IDS-EXACT", ids == expected_ids and not _duplicates(ids), ids)
    gap_map = {row.get("id"): row for row in rows if isinstance(row, dict)}
    required = {
        "id", "domain", "title", "gap_state", "evidence_maturity", "assessment_confidence", "source_refs",
        "safe_default", "closure_evidence", "review_ids", "blocks", "owner_input_required_for_closure",
    }
    complete = all(
        required.issubset(row)
        and row.get("gap_state") == "OPEN_EXPLICIT"
        and isinstance(row.get("source_refs"), list) and bool(row.get("source_refs")) and not _duplicates(row.get("source_refs", []))
        and isinstance(row.get("safe_default"), str) and bool(row.get("safe_default"))
        and isinstance(row.get("closure_evidence"), list) and bool(row.get("closure_evidence"))
        and isinstance(row.get("review_ids"), list) and bool(row.get("review_ids")) and not _duplicates(row.get("review_ids", []))
        and isinstance(row.get("blocks"), list) and bool(row.get("blocks"))
        and type(row.get("owner_input_required_for_closure")) is bool
        for row in rows
    )
    _add(checks, "S02P04-GAPS-ROWS-COMPLETE-OPEN", complete, len(rows))
    _add(checks, "S02P04-GAPS-NONE-FALSELY-RESOLVED", all(row.get("gap_state") != "RESOLVED_VERIFIED" for row in rows), "all 26 remain open")

    semantics = gaps.get("gap_semantics", {})
    semantics_ok = semantics == {
        "registered_gap_is_resolved": False,
        "open_gap_may_pass_affected_capability": False,
        "silent_gap": "An in-scope unknown, limitation, unverified prerequisite or future-reuse condition with no explicit gap route, safe default and review route.",
        "silent_gap_target": 0,
        "internet_or_literature_exhaustive_claimed": False,
        "missing_or_unrouted_input": "BLOCK_SILENT_GAP",
        "missing_safe_default": "BLOCK_UNSAFE_OPEN_GAP",
        "missing_review_route": "BLOCK_UNSCHEDULED_GAP",
        "closure_without_independent_evidence": "BLOCK_FALSE_RESOLUTION",
        "target_shortfall_may_relax_gap_gate": False,
    }
    _add(checks, "S02P04-GAPS-SEMANTICS-FAIL-CLOSED", semantics_ok, semantics)
    _add(checks, "S02P04-GAPS-UPSTREAM-BINDINGS-EXACT", gaps.get("upstream_bindings") == {key: value for key, value in fixture.get("expected_upstream_hashes", {}).items() if key in gaps.get("upstream_bindings", {})}, gaps.get("upstream_bindings"))
    return gap_map


def _check_gap_coverage(
    gaps: Mapping[str, Any],
    gap_map: Mapping[str, Mapping[str, Any]],
    fixture: Mapping[str, Any],
    provider_facts: Mapping[str, Any],
    regulatory: Mapping[str, Any],
    model_claims: Mapping[str, Any],
    reuse_matrix: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    valid_gap_ids = set(gap_map)
    receipt_rows = gaps.get("receipt_unknown_coverage", [])
    unknown_ids = [row.get("unknown_id") for row in receipt_rows if isinstance(row, dict)]
    receipt_ok = not _duplicates(unknown_ids)
    actual_counts: Dict[str, int] = {}
    seen_indexes: Dict[str, Set[int]] = {}
    for row in receipt_rows if isinstance(receipt_rows, list) else []:
        evidence_id = row.get("evidence_id")
        index = row.get("index")
        routes = row.get("gap_ids")
        receipt = receipts.get(str(evidence_id), {})
        unknowns = receipt.get("explicit_unknowns", []) if isinstance(receipt, dict) else []
        valid = (
            isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(unknowns)
            and isinstance(routes, list) and bool(routes) and not _duplicates(routes) and set(routes).issubset(valid_gap_ids)
        )
        receipt_ok = receipt_ok and valid
        actual_counts[str(evidence_id)] = actual_counts.get(str(evidence_id), 0) + 1
        seen_indexes.setdefault(str(evidence_id), set()).add(index) if isinstance(index, int) else None
    receipt_ok = receipt_ok and actual_counts == fixture.get("expected_receipt_unknown_counts")
    for evidence_id, count in fixture.get("expected_receipt_unknown_counts", {}).items():
        receipt_ok = receipt_ok and seen_indexes.get(evidence_id) == set(range(count))
    _add(checks, "S02P04-COVERAGE-ALL-RECEIPT-UNKNOWNS-ROUTED", receipt_ok, actual_counts)

    provider_unknown_ids = sorted(
        fact.get("fact_id")
        for provider in provider_facts.get("providers", [])
        for fact in provider.get("facts", [])
        if "UNKNOWN" in str(fact.get("fact_status")) or "UNVERIFIED" in str(fact.get("fact_status"))
    )
    provider_routes = gaps.get("provider_unknown_fact_coverage", {})
    provider_ok = provider_unknown_ids == sorted(fixture.get("expected_provider_unknown_fact_ids", [])) and set(provider_routes) == set(provider_unknown_ids) and _valid_routes(provider_routes, valid_gap_ids)
    _add(checks, "S02P04-COVERAGE-ALL-PROVIDER-UNKNOWNS-ROUTED", provider_ok, provider_unknown_ids)

    prerequisites = regulatory.get("runtime_prerequisite_state", {})
    false_keys = sorted(key for key, value in prerequisites.items() if value is False)
    prereq_routes = gaps.get("runtime_prerequisite_coverage", {})
    prereq_ok = false_keys == sorted(fixture.get("expected_runtime_prerequisite_keys", [])) and set(prereq_routes) == set(false_keys) and _valid_routes(prereq_routes, valid_gap_ids)
    _add(checks, "S02P04-COVERAGE-ALL-RUNTIME-PREREQUISITES-ROUTED", prereq_ok, false_keys)

    claim_ids = [row.get("id") for row in model_claims.get("claims", []) if isinstance(row, dict)]
    claim_routes = gaps.get("model_claim_coverage", {})
    claim_ok = claim_ids == fixture.get("expected_model_claim_ids") and set(claim_routes) == set(claim_ids) and _valid_routes(claim_routes, valid_gap_ids)
    _add(checks, "S02P04-COVERAGE-ALL-MODEL-CLAIMS-ROUTED", claim_ok, claim_ids)

    threshold_pointers = [row.get("parameter_pointer") for row in model_claims.get("local_threshold_inventory", []) if isinstance(row, dict)]
    threshold_routes = gaps.get("local_threshold_coverage", {})
    threshold_ok = threshold_pointers == fixture.get("expected_local_threshold_pointers") and set(threshold_routes) == set(threshold_pointers) and _valid_routes(threshold_routes, valid_gap_ids)
    _add(checks, "S02P04-COVERAGE-ALL-LOCAL-THRESHOLDS-ROUTED", threshold_ok, threshold_pointers)

    reuse_routes = gaps.get("reuse_unknown_coverage", {})
    reuse_counts = {row.get("source_id"): len(row.get("unverified", [])) for row in reuse_matrix.get("projects", []) if isinstance(row, dict)}
    reuse_ok = reuse_counts == fixture.get("expected_reuse_unknown_counts") and set(reuse_routes) == set(reuse_counts)
    for source_id, expected_count in reuse_counts.items():
        route = reuse_routes.get(source_id, {})
        reuse_ok = reuse_ok and route.get("expected_unknown_count") == expected_count and isinstance(route.get("gap_ids"), list) and bool(route.get("gap_ids")) and set(route.get("gap_ids", [])).issubset(valid_gap_ids)
    _add(checks, "S02P04-COVERAGE-ALL-REUSE-UNKNOWNS-ROUTED", reuse_ok, reuse_counts)

    rule_ids = [row.get("rule_id") for row in regulatory.get("rules", []) if isinstance(row, dict)]
    rule_routes = gaps.get("regulatory_rule_coverage", {})
    rule_ok = rule_ids == fixture.get("expected_regulatory_rule_ids") and set(rule_routes) == set(rule_ids) and _valid_routes(rule_routes, valid_gap_ids)
    _add(checks, "S02P04-COVERAGE-ALL-REGULATORY-RULES-ROUTED", rule_ok, rule_ids)

    routed_gap_ids: Set[str] = set()
    for mapping in [provider_routes, prereq_routes, claim_routes, threshold_routes, rule_routes]:
        for routes in mapping.values():
            routed_gap_ids.update(routes)
    for row in receipt_rows:
        routed_gap_ids.update(row.get("gap_ids", []))
    for row in reuse_routes.values():
        routed_gap_ids.update(row.get("gap_ids", []))
    _add(checks, "S02P04-COVERAGE-EVERY-GAP-HAS-UPSTREAM-ROUTE", routed_gap_ids == valid_gap_ids, {"missing": sorted(valid_gap_ids - routed_gap_ids)})

    summary = gaps.get("coverage_summary", {})
    summary_ok = summary == {
        "registered_gap_count": 26,
        "open_gap_count": 26,
        "resolved_gap_count": 0,
        "receipt_unknown_count": 22,
        "provider_unknown_fact_count": 9,
        "runtime_prerequisite_count": 7,
        "model_claim_count": 14,
        "local_threshold_count": 18,
        "reuse_project_count": 6,
        "reuse_unknown_item_count": 18,
        "regulatory_rule_count": 9,
        "unrouted_obligation_count": 0,
        "gap_without_safe_default_count": 0,
        "gap_without_review_route_count": 0,
        "silent_gap_count": 0,
        "internet_or_literature_exhaustive_claimed": False,
        "all_open_gaps_remain_non_pass": True,
    }
    _add(checks, "S02P04-COVERAGE-SUMMARY-EXACT", summary_ok, summary)
    _add(checks, "S02P04-SILENT-GAP-COUNT-ZERO-NOT-RESOLUTION", summary.get("silent_gap_count") == 0 and summary.get("open_gap_count") == 26 and summary.get("resolved_gap_count") == 0, summary)


def _reference_ids(
    provider_facts: Mapping[str, Any],
    regulatory: Mapping[str, Any],
    papers: Mapping[str, Any],
    model_claims: Mapping[str, Any],
    reuse_matrix: Mapping[str, Any],
    licenses: Mapping[str, Any],
    gap_ids: Set[str],
) -> Dict[str, Set[str]]:
    return {
        "provider_facts_snapshot.json": {fact.get("fact_id") for provider in provider_facts.get("providers", []) for fact in provider.get("facts", [])},
        "regulatory_matrix.json": {row.get("rule_id") for row in regulatory.get("rules", [])},
        "research_evidence_matrix.json": {row.get("id") for row in papers.get("papers", [])},
        "model_claims.json": {row.get("id") for row in model_claims.get("claims", [])},
        "research_reuse_matrix.json": {row.get("source_id") for row in reuse_matrix.get("projects", [])},
        "license_inventory.json": {row.get("id") for row in licenses.get("entries", [])},
        "machine/evidence/EVD-S02-P01.json": {"EVD-S02-P01"},
        "machine/evidence/EVD-S02-P02.json": {"EVD-S02-P02"},
        "machine/evidence/EVD-S02-P03.json": {"EVD-S02-P03"},
        "machine/facts/parameters.json": {"target_30pct"},
        "research_gaps.json": gap_ids | {"coverage_summary", "gap_semantics"},
    }


def _check_counterevidence(
    counter: Mapping[str, Any],
    fixture: Mapping[str, Any],
    gap_ids: Set[str],
    reference_ids: Mapping[str, Set[str]],
    checks: List[Dict[str, Any]],
) -> Dict[str, Mapping[str, Any]]:
    shape_ok = (
        counter.get("schema_version") == "1.0.0"
        and counter.get("artifact_id") == "ART-S02-P04-02"
        and counter.get("version") == VERSION
        and counter.get("stage_id") == "S02"
        and counter.get("phase_id") == "P04"
        and counter.get("requirement_id") == REQUIREMENT_ID
        and counter.get("acceptance_contract_id") == CONTRACT_ID
        and counter.get("as_of") == "2026-07-20"
        and counter.get("status") == "FROZEN_COUNTEREVIDENCE_AND_NON_PROOF_BOUNDARIES"
        and counter.get("next_on_acceptance_pass") == fixture.get("expected_next")
    )
    _add(checks, "S02P04-COUNTER-SHAPE", shape_ok, counter.get("status"))
    binding_ok = counter.get("research_gaps_binding") == {"path": GAPS_PATH.as_posix(), "sha256": PINNED_PHASE_HASHES[GAPS_PATH.as_posix()]}
    _add(checks, "S02P04-COUNTER-GAPS-BINDING", binding_ok, counter.get("research_gaps_binding"))

    rows = counter.get("records", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    _add(checks, "S02P04-COUNTER-IDS-EXACT", ids == fixture.get("expected_counterevidence_ids") and not _duplicates(ids), ids)
    row_map = {row.get("id"): row for row in rows if isinstance(row, dict)}
    review_ids = set(fixture.get("expected_review_ids", []))
    row_errors: List[Any] = []
    for row in rows if isinstance(rows, list) else []:
        if not all(isinstance(row.get(key), str) and row.get(key) for key in ["id", "proposition", "verdict", "implication", "safe_default"]):
            row_errors.append({"id": row.get("id"), "reason": "required text"})
        if not isinstance(row.get("gap_ids"), list) or not row.get("gap_ids") or not set(row.get("gap_ids", [])).issubset(gap_ids):
            row_errors.append({"id": row.get("id"), "reason": "gap routes"})
        if not isinstance(row.get("review_ids"), list) or not row.get("review_ids") or not set(row.get("review_ids", [])).issubset(review_ids):
            row_errors.append({"id": row.get("id"), "reason": "review routes"})
        refs = row.get("evidence_refs", [])
        if not isinstance(refs, list) or not refs:
            row_errors.append({"id": row.get("id"), "reason": "evidence refs"})
            continue
        for ref in refs:
            artifact = ref.get("artifact") if isinstance(ref, dict) else None
            item_ids = ref.get("ids") if isinstance(ref, dict) else None
            if artifact not in reference_ids or not isinstance(item_ids, list) or not item_ids or not set(item_ids).issubset(reference_ids.get(str(artifact), set())):
                row_errors.append({"id": row.get("id"), "reason": "unresolved ref", "ref": ref})
    _add(checks, "S02P04-COUNTER-ROWS-COMPLETE-LOCAL-REFS", not row_errors, row_errors or len(rows))
    covered_gap_ids = {gap_id for row in rows if isinstance(row, dict) for gap_id in row.get("gap_ids", [])}
    _add(
        checks,
        "S02P04-COUNTER-ALL-GAPS-COVERED",
        covered_gap_ids == gap_ids,
        {"missing": sorted(gap_ids - covered_gap_ids), "covered": len(covered_gap_ids)},
    )

    semantics = counter.get("semantics", {})
    semantics_ok = semantics == {
        "counterevidence_is_universal_impossibility_proof": False,
        "not_established_is_authorized_or_available": False,
        "repository_or_paper_self_report_is_abd_runtime_proof": False,
        "official_document_is_account_or_runtime_proof": False,
        "research_phase_pass_is_production_or_return_proof": False,
        "target_curve_is_forecast_or_guarantee": False,
        "negative_or_limiting_evidence_action": "PRESERVE_GAP_AND_FAIL_CLOSED",
    }
    _add(checks, "S02P04-COUNTER-SEMANTICS-FAIL-CLOSED", semantics_ok, semantics)
    summary = counter.get("summary", {})
    summary_ok = summary == {
        "counterevidence_record_count": 22,
        "registered_gap_count": 26,
        "gap_with_counterevidence_count": 26,
        "gap_without_counterevidence_count": 0,
        "records_without_evidence_refs": 0,
        "records_without_gap_routes": 0,
        "records_without_safe_defaults": 0,
        "records_without_review_routes": 0,
        "universal_impossibility_claims": 0,
        "production_or_return_claims_supported": 0,
        "thirty_percent_target_verified_or_guaranteed": False,
    }
    _add(checks, "S02P04-COUNTER-SUMMARY-EXACT", summary_ok, summary)
    _add(checks, "S02P04-COUNTER-30PCT-IS-NOT-FORECAST", "UNVERIFIED" in row_map.get("CE-S02-P04-018", {}).get("safe_default", "") and row_map.get("CE-S02-P04-018", {}).get("verdict") == "REFUTED_BY_MISSING_DURATION_SAMPLE_CAPACITY_AND_EXECUTION_EVIDENCE", row_map.get("CE-S02-P04-018"))
    _add(checks, "S02P04-COUNTER-REGISTRATION-IS-NOT-CLOSURE", row_map.get("CE-S02-P04-019", {}).get("safe_default") == "ALL_OPEN_GAPS_REMAIN_NON_PASS", row_map.get("CE-S02-P04-019"))
    return row_map


def _check_review_schedule(
    schedule: Mapping[str, Any],
    fixture: Mapping[str, Any],
    gap_map: Mapping[str, Mapping[str, Any]],
    counter_map: Mapping[str, Mapping[str, Any]],
    costs: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    shape_ok = (
        schedule.get("schema_version") == "1.0.0"
        and schedule.get("artifact_id") == "ART-S02-P04-03"
        and schedule.get("version") == VERSION
        and schedule.get("stage_id") == "S02"
        and schedule.get("phase_id") == "P04"
        and schedule.get("requirement_id") == REQUIREMENT_ID
        and schedule.get("acceptance_contract_id") == CONTRACT_ID
        and schedule.get("as_of") == "2026-07-20"
        and schedule.get("status") == "FROZEN_REVIEW_ROUTES_NOT_EXECUTED"
        and schedule.get("next_on_acceptance_pass") == fixture.get("expected_next")
    )
    _add(checks, "S02P04-REVIEW-SHAPE", shape_ok, schedule.get("status"))
    bindings_ok = schedule.get("artifact_bindings") == {
        GAPS_PATH.as_posix(): PINNED_PHASE_HASHES[GAPS_PATH.as_posix()],
        COUNTEREVIDENCE_PATH.as_posix(): PINNED_PHASE_HASHES[COUNTEREVIDENCE_PATH.as_posix()],
        "machine/facts/costs.json": PINNED_BASELINE_HASHES["machine/facts/costs.json"],
        "machine/facts/parameters.json": PINNED_BASELINE_HASHES["machine/facts/parameters.json"],
    }
    _add(checks, "S02P04-REVIEW-ARTIFACT-BINDINGS", bindings_ok, schedule.get("artifact_bindings"))

    rows = schedule.get("reviews", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    expected_ids = fixture.get("expected_review_ids", [])
    _add(checks, "S02P04-REVIEW-IDS-EXACT", ids == expected_ids and not _duplicates(ids), ids)
    review_map = {row.get("id"): row for row in rows if isinstance(row, dict)}
    gap_ids = set(gap_map)
    row_errors: List[Any] = []
    for row in rows if isinstance(rows, list) else []:
        required_text = ["id", "title", "review_type", "scheduled_for", "date_basis", "overdue_action", "current_status"]
        if not all(isinstance(row.get(key), str) and row.get(key) for key in required_text):
            row_errors.append({"id": row.get("id"), "reason": "required text"})
        for key in ["trigger", "required_inputs", "required_outputs", "gap_ids"]:
            if not isinstance(row.get(key), list) or not row.get(key) or _duplicates(row.get(key, [])):
                row_errors.append({"id": row.get("id"), "reason": key})
        if not set(row.get("gap_ids", [])).issubset(gap_ids):
            row_errors.append({"id": row.get("id"), "reason": "unknown gap"})
        if type(row.get("owner_input_required")) is not bool or row.get("external_access_allowed_in_p04") is not False:
            row_errors.append({"id": row.get("id"), "reason": "flags"})
        if "EXECUTED" in str(row.get("current_status")) and row.get("current_status") not in {"SCHEDULED_NOT_EXECUTED", "NOT_REQUESTED_NOT_EXECUTED", "NOT_EXECUTED"}:
            row_errors.append({"id": row.get("id"), "reason": "executed claim"})
    _add(checks, "S02P04-REVIEW-ROWS-COMPLETE-NOT-EXECUTED", not row_errors, row_errors or len(rows))

    all_covered = {gap_id for row in rows for gap_id in row.get("gap_ids", [])}
    non_stage_covered = {gap_id for row in rows if row.get("id") != "REV-S02-P04-001" for gap_id in row.get("gap_ids", [])}
    _add(checks, "S02P04-REVIEW-ALL-GAPS-COVERED", all_covered == gap_ids, {"missing": sorted(gap_ids - all_covered)})
    _add(checks, "S02P04-REVIEW-ALL-GAPS-HAVE-NON-STAGE-ROUTE", non_stage_covered == gap_ids, {"missing": sorted(gap_ids - non_stage_covered)})

    reciprocal_errors = []
    for gap_id, gap in gap_map.items():
        routes = gap.get("review_ids", [])
        if not set(routes).issubset(set(review_map)) or any(gap_id not in review_map.get(review_id, {}).get("gap_ids", []) for review_id in routes):
            reciprocal_errors.append(gap_id)
    _add(checks, "S02P04-REVIEW-GAP-ROUTES-RECIPROCAL", not reciprocal_errors, reciprocal_errors or len(gap_map))

    counter_routes_ok = all(
        isinstance(row.get("review_ids"), list)
        and bool(row.get("review_ids"))
        and set(row.get("review_ids", [])).issubset(set(review_map))
        for row in counter_map.values()
    )
    _add(checks, "S02P04-REVIEW-COUNTEREVIDENCE-ROUTES-VALID", counter_routes_ok, len(counter_map))

    absolute_date = fixture.get("expected_review_absolute_date")
    date_source = costs.get("freshness_policy", {}).get("reverify_before", [])
    date_ok = absolute_date in date_source and all(
        absolute_date in json.dumps(review_map.get(review_id, {}), ensure_ascii=False)
        and "costs.json#/freshness_policy/reverify_before" in review_map.get(review_id, {}).get("date_basis", "")
        for review_id in ["REV-S02-P04-002", "REV-S02-P04-005", "REV-S02-P04-011"]
    )
    _add(checks, "S02P04-REVIEW-ABSOLUTE-DATE-SOURCE-BOUND", date_ok, {"date": absolute_date, "source": date_source})

    target = review_map.get("REV-S02-P04-009", {})
    target_ok = (
        target.get("review_type") == "OBSERVATION_GATE"
        and any("90 complete shadow days" in item for item in target.get("trigger", []))
        and any("6 complete calendar months" in item for item in target.get("trigger", []))
        and any("12 complete calendar months" in item for item in target.get("trigger", []))
        and target.get("overdue_action") == "KEEP_TARGET_UNVERIFIED_NOT_GUARANTEED"
    )
    _add(checks, "S02P04-REVIEW-30PCT-GATES-EXACT", target_ok, target.get("trigger"))
    stage_review = review_map.get("REV-S02-P04-001", {})
    stage_review_ok = stage_review.get("scheduled_for") == "S02/STAGE_REVIEW_READY_NOT_STARTED" and stage_review.get("current_status") == "READY_AFTER_P04_PASS_NOT_STARTED" and stage_review.get("overdue_action") == "DO_NOT_UPLOAD_STAGE_2_AND_DO_NOT_START_DOWNSTREAM_STAGE_DEPENDENCIES"
    _add(checks, "S02P04-REVIEW-STAGE2-READY-NOT-STARTED", stage_review_ok, stage_review.get("current_status"))

    semantics = schedule.get("schedule_semantics", {})
    semantics_ok = semantics == {
        "scheduled_is_executed": False,
        "review_route_closes_gap": False,
        "missing_review_result": "KEEP_GAP_OPEN_AND_AFFECTED_CAPABILITY_BLOCKED",
        "stale_or_changed_source": "FAIL_CLOSED_OR_DEGRADE_WITHOUT_PAID_SUBSTITUTION",
        "event_trigger_precedes_date": True,
        "overdue_review_may_silently_pass": False,
        "owner_input_is_automated_authorization": False,
        "review_may_relax_gate_for_target_shortfall": False,
    }
    _add(checks, "S02P04-REVIEW-SEMANTICS-FAIL-CLOSED", semantics_ok, semantics)

    summary = schedule.get("coverage_summary", {})
    summary_ok = summary == {
        "review_count": 12,
        "registered_gap_count": 26,
        "gap_without_any_review_route_count": 0,
        "gap_without_non_stage_review_route_count": 0,
        "counterevidence_record_count": 22,
        "counterevidence_without_review_route_count": 0,
        "absolute_revalidation_date": "2026-10-19",
        "absolute_date_source_bound": True,
        "stage2_review_started": False,
        "current_phase_reviews_executed": 0,
        "overdue_review_may_pass": False,
    }
    _add(checks, "S02P04-REVIEW-SUMMARY-EXACT", summary_ok, summary)


def _check_baseline_and_boundaries(
    gaps: Mapping[str, Any],
    counter: Mapping[str, Any],
    schedule: Mapping[str, Any],
    fixture: Mapping[str, Any],
    canonical: Mapping[str, Any],
    parameters: Mapping[str, Any],
    costs: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    canonical_ok = (
        canonical.get("product", {}).get("initial_bankroll_aud") == "300.00"
        and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00"
        and canonical.get("scope", {}).get("product_role") == "ANALYSIS_AND_ADVICE_ONLY"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and canonical.get("scope", {}).get("discovery_scope") == "ALL_OBSERVABLE_MARKETS"
        and canonical.get("truth_and_evidence", {}).get("silent_coverage_gap_target") == 0
        and canonical.get("truth_and_evidence", {}).get("actual_return_requires_verified_execution_evidence") is True
    )
    _add(checks, "S02P04-BASELINE-CANONICAL-SAFETY", canonical_ok, canonical.get("scope"))
    numeric = parameters.get("numeric_determinism", {})
    parameter_ok = (
        parameters.get("coverage_and_freshness", {}).get("silent_gap_max") == 0
        and numeric.get("boundary_perturbation_absolute_probability") == "0.0001"
        and numeric.get("boundary_perturbation_absolute_threshold") == "0.0001"
        and numeric.get("odds_perturbation") == "ONE_PROVIDER_TICK_ADVERSE"
        and numeric.get("unstable_action") == "NO_RECOMMENDATION"
        and parameters.get("target_30pct", {}).get("monthly_return") == "0.30"
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
    )
    _add(checks, "S02P04-BASELINE-NUMERIC-AND-TARGET-SAFETY", parameter_ok, numeric)
    source_policy = costs.get("future_source_admission_policy", {})
    cost_ok = (
        costs.get("incremental_cash_budget") == {"low": "0.00", "likely": "0.00", "high": "0.00"}
        and source_policy.get("unknown_cost_or_terms_action") == "DO_NOT_ADMIT_SOURCE_MARK_COVERAGE_GAP"
        and source_policy.get("paid_source_action") == "BLOCK_WITH_INCREMENTAL_CASH_BUDGET_EXCEEDED"
        and source_policy.get("coverage_gap_behavior") == "DISCOVERED_BUT_NOT_RECOMMENDABLE_OR_UNOBSERVABLE_NOT_SILENTLY_DROPPED"
    )
    _add(checks, "S02P04-BASELINE-A-ZERO-SOURCE-POLICY", cost_ok, source_policy)

    expected_effects = fixture.get("expected_external_effect_boundary")
    effect_errors = {
        path: artifact.get("external_effect_boundary")
        for path, artifact in [(GAPS_PATH.as_posix(), gaps), (COUNTEREVIDENCE_PATH.as_posix(), counter), (REVIEW_SCHEDULE_PATH.as_posix(), schedule)]
        if artifact.get("external_effect_boundary") != expected_effects
    }
    _add(checks, "S02P04-NO-EXTERNAL-EFFECT-ALL-ARTIFACTS", not effect_errors, effect_errors or expected_effects)
    _add(checks, "S02P04-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS", not any(_contains_float(value) for value in [gaps, counter, schedule, fixture]), "authoritative values use strings, integers and booleans")
    rendered = json.dumps([gaps, counter, schedule], ensure_ascii=False, sort_keys=True)
    path_ok = ("/" + "Users/") not in rendered and ("/private/" + "var/") not in rendered
    _add(checks, "S02P04-NO-ABSOLUTE-LOCAL-PATH", path_ok, "portable artifacts")


def _check_fixture_vectors(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    vectors = fixture.get("decision_vectors", [])
    errors = []
    for vector in vectors:
        try:
            actual = resolve_gap_disposition(**vector.get("inputs", {}))
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
        if actual != vector.get("expected"):
            errors.append({"id": vector.get("id"), "expected": vector.get("expected"), "actual": actual})
    _add(checks, "S02P04-FIXTURE-DECISION-VECTORS", not errors and len(vectors) == 8, errors or len(vectors))
    invariance = []
    for delta in fixture.get("allowed_numeric_delta_strings", []):
        actual = resolve_gap_disposition(
            gap_state="OPEN_EXPLICIT",
            registered=True,
            has_safe_default=True,
            review_route_count=2,
            closure_evidence_verified=False,
            blocks_capability=True,
            numeric_delta=delta,
            adverse_odds_tick=True,
        )
        invariance.append({"delta": delta, "actual": actual})
    _add(checks, "S02P04-FIXTURE-PLUS-MINUS-0001-AND-ADVERSE-TICK-INVARIANT", all(row["actual"] == "REGISTERED_OPEN_CAPABILITY_BLOCKED" for row in invariance), invariance)
    _add(checks, "S02P04-FIXTURE-FAULT-MUTATIONS-COMPLETE", len(fixture.get("fault_mutations", [])) == 26 and not _duplicates(fixture.get("fault_mutations", [])), fixture.get("fault_mutations"))


def _check_p03_prerequisite(root: Path, checks: List[Dict[str, Any]], verify_git_history: bool) -> None:
    try:
        result = verify_s02_p03_evidence(
            root,
            verify_git_history=verify_git_history,
            verify_p02_prerequisite=True,
            verify_successor_state=False,
        )
        passed = (
            result.get("status") == "PASS"
            and result.get("decision") == "S02_P03_EVIDENCE_VERIFIED"
            and result.get("evidence_sha256") == P03_EVIDENCE_SHA256
            and result.get("rollback_sha256") == P03_ROLLBACK_SHA256
            and result.get("next") == "S02/P04_READY_NOT_STARTED"
        )
        detail = {"status": result.get("status"), "summary": result.get("summary"), "next": result.get("next")}
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P04-P03-IMMUTABLE-PREREQUISITE", passed, detail)


def _check_stage2_review_not_started(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("machine/facts/stage2_review_contract.json"),
        Path("machine/evidence/S02/STAGE_REVIEW/findings.json"),
        Path("machine/tests/fixtures/S02_STAGE_REVIEW.json"),
        Path("tests/S02/stage_review_test.py"),
        Path("abd_acceptance/stage2_review.py"),
    ]
    signed_paths = [
        Path("machine/evidence/EVD-S02-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json"),
    ]
    candidate_existing = [path.as_posix() for path in candidate_paths if (root / path).is_file()]
    signed_existing = [path.as_posix() for path in signed_paths if (root / path).is_file()]
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        stage_rows = [row for row in rows if row.get("id") == "INDEX-S02-STAGE-REVIEW"]
        if not candidate_existing and not signed_existing and not stage_rows:
            passed = True
            detail: Any = {"state": "STAGE2_REVIEW_NOT_STARTED", "candidate": [], "signed": []}
        elif (
            candidate_existing == [path.as_posix() for path in candidate_paths]
            and not signed_existing
            and len(stage_rows) == 1
            and stage_rows[0].get("status") == "PLANNED"
            and "actual_artifact" not in stage_rows[0]
        ):
            try:
                from .stage2_review import validate_candidate_preflight

                candidate = validate_candidate_preflight(root)
                executable_hashes = {
                    relative: sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
                    for relative in STAGE2_REVIEW_EXECUTABLE_HASHES
                }
                passed = candidate.get("status") == "PASS" and executable_hashes == STAGE2_REVIEW_EXECUTABLE_HASHES
                detail = {
                    "state": "STAGE2_REVIEW_CANDIDATE_VALID" if passed else "INVALID_STAGE2_REVIEW_CANDIDATE",
                    "candidate_summary": candidate.get("summary"),
                    "executable_hashes": executable_hashes,
                }
            except Exception as exc:
                passed = False
                detail = {"state": "INVALID_STAGE2_REVIEW_CANDIDATE", "error": "%s: %s" % (type(exc).__name__, exc)}
        elif (
            candidate_existing == [path.as_posix() for path in candidate_paths]
            and signed_existing == [path.as_posix() for path in signed_paths]
            and len(stage_rows) == 1
            and stage_rows[0].get("status") == "PASS"
        ):
            try:
                from .stage2_review import verify_existing_stage_review_evidence

                successor = verify_existing_stage_review_evidence(root, verify_phase_prerequisites=False)
                passed = successor.get("status") == "PASS" and successor.get("next") == "S02/GITHUB_STAGE_UPLOAD_READY"
                detail = {
                    "state": "STAGE2_REVIEW_SIGNED_VERIFIED" if passed else "INVALID_SIGNED_STAGE2_REVIEW",
                    "successor_summary": successor.get("summary"),
                }
            except Exception as exc:
                passed = False
                detail = {"state": "INVALID_SIGNED_STAGE2_REVIEW", "error": "%s: %s" % (type(exc).__name__, exc)}
        else:
            passed = False
            detail = {"state": "PARTIAL_OR_UNRECOGNIZED_STAGE2_REVIEW", "candidate": candidate_existing, "signed": signed_existing, "stage_index_rows": stage_rows}
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P04-STAGE2-REVIEW-NOT-STARTED", passed, detail)


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites: Iterable[ET.Element] = [root] if root.tag == "testsuite" else root.findall("testsuite")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(float(suite.attrib.get(key, "0")))
    return totals


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


def _check_runtime_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    reports = [
        ("S02P04-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S02P04-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
    ]
    for check_id, relative, minimum in reports:
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            passed = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and normalized
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S02P04-PACK-REPORT-PARSE")
    report_ok = isinstance(report, dict) and report.get("status") == "PASS" and report.get("summary", {}).get("checks") == 49 and report.get("summary", {}).get("failed") == 0
    _add(checks, "S02P04-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in text and "MAX_INCREMENTAL_CASH_AUD: 0.00" in text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in text and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in text
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        _add(checks, "S02P04-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S02P04-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P04",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "RESEARCH_GAPS_COUNTEREVIDENCE_AND_REVIEW_ROUTES_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for row in checks if row["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "gap_status": "26_OPEN_EXPLICIT_0_RESOLVED_0_SILENT" if status == "PASS" else "INVALID_OR_SILENT_GAP_BLOCKED",
        "exhaustiveness_status": "SCOPED_NON_EXHAUSTIVE_NO_INTERNET_EXHAUSTION_CLAIM",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "release_status": "NOT_READY_STAGE_REVIEW_REQUIRED",
        "phase_status": "S02_P04_PASS" if status == "PASS" else "S02_P04_FAILED",
        "next": "S02/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S02/P04_REMEDIATION_REQUIRED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S02P04-FIXTURE-STRICT-JSON")
    gaps = _safe_load(root / GAPS_PATH, checks, "S02P04-GAPS-STRICT-JSON")
    counter = _safe_load(root / COUNTEREVIDENCE_PATH, checks, "S02P04-COUNTER-STRICT-JSON")
    schedule = _safe_load(root / REVIEW_SCHEDULE_PATH, checks, "S02P04-REVIEW-STRICT-JSON")
    provider_facts = _safe_load(root / "provider_facts_snapshot.json", checks, "S02P04-PROVIDER-FACTS-STRICT-JSON")
    regulatory = _safe_load(root / "regulatory_matrix.json", checks, "S02P04-REGULATORY-STRICT-JSON")
    papers = _safe_load(root / "research_evidence_matrix.json", checks, "S02P04-PAPERS-STRICT-JSON")
    model_claims = _safe_load(root / "model_claims.json", checks, "S02P04-MODEL-CLAIMS-STRICT-JSON")
    reuse_matrix = _safe_load(root / "research_reuse_matrix.json", checks, "S02P04-REUSE-STRICT-JSON")
    licenses = _safe_load(root / "license_inventory.json", checks, "S02P04-LICENSE-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S02P04-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S02P04-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S02P04-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S02P04-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S02P04-TRACEABILITY-STRICT-JSON")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "S02P04-CANONICAL-STRICT-JSON")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S02P04-PARAMETERS-STRICT-JSON")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "S02P04-COSTS-STRICT-JSON")
    receipts = {
        "EVD-S02-P01": _safe_load(root / "machine/evidence/EVD-S02-P01.json", checks, "S02P04-P01-RECEIPT-STRICT-JSON"),
        "EVD-S02-P02": _safe_load(root / "machine/evidence/EVD-S02-P02.json", checks, "S02P04-P02-RECEIPT-STRICT-JSON"),
        "EVD-S02-P03": _safe_load(root / P03_EVIDENCE_PATH, checks, "S02P04-P03-RECEIPT-STRICT-JSON"),
    }
    _check_pinned_hashes(root, checks, hashes)
    import_markers = [Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py"), Path("tests/S02/__init__.py")]
    _add(checks, "S02P04-PYTEST-IMPORT-ISOLATION", all((root / path).is_file() for path in import_markers), [path.as_posix() for path in import_markers])

    dictionaries = [fixture, gaps, counter, schedule, provider_facts, regulatory, papers, model_claims, reuse_matrix, licenses, roadmap, task_graph, canonical, parameters, costs, *receipts.values()]
    arrays = [requirements, acceptance, traceability]
    if not all(isinstance(value, dict) for value in dictionaries) or not all(isinstance(value, list) for value in arrays):
        _add(checks, "S02P04-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S02P04-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, fixture, checks)
    except Exception as exc:
        _add(checks, "S02P04-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        gap_map = _check_gap_artifact(gaps, fixture, checks)
        _check_gap_coverage(gaps, gap_map, fixture, provider_facts, regulatory, model_claims, reuse_matrix, receipts, checks)
    except Exception as exc:
        gap_map = {}
        _add(checks, "S02P04-GAP-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        references = _reference_ids(provider_facts, regulatory, papers, model_claims, reuse_matrix, licenses, set(gap_map))
        counter_map = _check_counterevidence(counter, fixture, set(gap_map), references, checks)
    except Exception as exc:
        counter_map = {}
        _add(checks, "S02P04-COUNTER-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_review_schedule(schedule, fixture, gap_map, counter_map, costs, checks)
    except Exception as exc:
        _add(checks, "S02P04-REVIEW-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_baseline_and_boundaries(gaps, counter, schedule, fixture, canonical, parameters, costs, checks)
        _check_fixture_vectors(fixture, checks)
    except Exception as exc:
        _add(checks, "S02P04-BASELINE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _check_p03_prerequisite(root, checks, _verify_git_history)
    _check_stage2_review_not_started(root, checks)
    if require_external_reports:
        _check_runtime_reports(root, fixture, checks, hashes)
    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0))
    if result["summary"]["checks"] < minimum:
        _add(checks, "S02P04-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
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
        (GAPS_PATH.as_posix(), root / GAPS_PATH),
        (COUNTEREVIDENCE_PATH.as_posix(), root / COUNTEREVIDENCE_PATH),
        (REVIEW_SCHEDULE_PATH.as_posix(), root / REVIEW_SCHEDULE_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (P03_EVIDENCE_PATH.as_posix(), root / P03_EVIDENCE_PATH),
        (P03_ROLLBACK_PATH.as_posix(), root / P03_ROLLBACK_PATH),
        ("provider_facts_snapshot.json", root / "provider_facts_snapshot.json"),
        ("model_claims.json", root / "model_claims.json"),
        ("research_reuse_matrix.json", root / "research_reuse_matrix.json"),
        ("license_inventory.json", root / "license_inventory.json"),
    ]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s02-p04-rollback-") as directory:
        temporary = Path(directory)
        for index, (label, source) in enumerate(artifacts):
            expected = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored = sha256_file(active)
            results[label] = {
                "status": "PASS" if corrupted != expected and restored == expected else "FAIL",
                "signed_sha256": expected,
                "corrupted_sha256": corrupted,
                "restored_sha256": restored,
            }
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S02-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_RESEARCH_GAP_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        GAPS_PATH, COUNTEREVIDENCE_PATH, REVIEW_SCHEDULE_PATH, FIXTURE_PATH,
        *[Path(relative) for relative in PINNED_BASELINE_HASHES],
        TEST_PATH,
        Path("tests/S02/P03_test.py"), Path("tests/S02/P02_test.py"), Path("tests/S02/P01_test.py"), Path("tests/S02/__init__.py"),
        Path("abd_acceptance/research_gap_audit.py"), Path("abd_acceptance/open_source_reuse.py"), Path("abd_acceptance/model_risk_research.py"), Path("abd_acceptance/official_platform_research.py"),
        Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
        Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py"),
    ]
    unique = {path.as_posix(): path for path in paths}
    result = {relative: sha256_file(root / path) for relative, path in unique.items()}
    result[CONTINUOUS_WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / CONTINUOUS_WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0", "evidence_id": "EVD-S02-P04-ROLLBACK", "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False, "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["phase_status"] = "S02_P04_FAILED"
        result["next"] = "S02/P04_REMEDIATION_REQUIRED"
    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S02-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P04",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S02-P04-01": GAPS_PATH.as_posix(),
            "ART-S02-P04-02": COUNTEREVIDENCE_PATH.as_posix(),
            "ART-S02-P04-03": REVIEW_SCHEDULE_PATH.as_posix(),
        },
        "p03_prerequisite": {
            "evidence": P03_EVIDENCE_PATH.as_posix(), "evidence_sha256": P03_EVIDENCE_SHA256,
            "rollback": P03_ROLLBACK_PATH.as_posix(), "rollback_sha256": P03_ROLLBACK_SHA256, "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S02/P04 registers research gaps, counterevidence and review routes only; it executes no model, strategy, provider interaction, deployment, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S02/P04_test.py --junitxml=machine/evidence/S02/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S02-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": dict(strict_json_load(root / FIXTURE_PATH)["expected_external_effect_boundary"]),
        "explicit_unknowns": [
            "All 26 registered research gaps remain open; registration and a review route do not resolve any affected capability.",
            "The Stage 2 research scope is not an exhaustive review of the internet, regulations, literature, repositories, sports, markets or sources.",
            "Provider, account, Gmail, Cloudflare and OVH runtime states remain uninspected or unauthorized and fail closed.",
            "Model, calibration, robustness, numeric stability, Kelly, capacity, friction and actual execution evidence remain unvalidated.",
            "Repository code licenses do not establish external source, service, data or account authorization; no package was installed or copied.",
            "All-observable-market coverage, production readiness and actual return remain unverified.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
            "Stage 2 whole-stage review, remediation and upload have not started and are required next.",
        ],
        "release_status": "NOT_READY_STAGE_REVIEW_REQUIRED",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S02-P04"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S02-P04 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S02/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S02/P04_REMEDIATION_REQUIRED"
    payload = b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows)
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


def _historical_file_matches(root: Path, relative: str, expected_sha256: str, verify_git_history: bool) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if not verify_git_history:
        if relative == "abd_acceptance/research_gap_audit.py":
            return True
        evolved = SUCCESSOR_EVOLVED_SIGNED_INPUT_HASHES.get(relative)
        return evolved is not None and (root / relative).is_file() and sha256_file(root / relative) == evolved
    if not _phase_commit_is_ancestor(root):
        return False
    result = subprocess.run(
        ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (PHASE_COMMIT, relative)],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256


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
    for repo_path in sorted(line for line in listing.stdout.splitlines() if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")):
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


def verify_existing_phase_evidence(
    root: Path,
    *,
    verify_git_history: bool = True,
    verify_p03_prerequisite: bool = True,
    verify_successor_state: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S02P04-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S02P04-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, dict):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S02-P04"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S02"
            and evidence.get("phase_id") == "P04"
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "RESEARCH_GAPS_COUNTEREVIDENCE_AND_REVIEW_ROUTES_FROZEN"
            and evidence.get("phase_status") == "S02_P04_PASS"
            and evidence.get("next") == "S02/STAGE_REVIEW_READY_NOT_STARTED"
            and evidence.get("artifacts") == {
                "ART-S02-P04-01": GAPS_PATH.as_posix(),
                "ART-S02-P04-02": COUNTEREVIDENCE_PATH.as_posix(),
                "ART-S02-P04-03": REVIEW_SCHEDULE_PATH.as_posix(),
            }
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S02P04-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = validation.get("status") == "PASS" and validation.get("decision") == "RESEARCH_GAPS_COUNTEREVIDENCE_AND_REVIEW_ROUTES_FROZEN" and validation.get("summary", {}).get("failed") == 0 and validation.get("next") == "S02/STAGE_REVIEW_READY_NOT_STARTED" and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S02P04-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        effects = evidence.get("external_effect_boundary", {})
        _add(checks, "S02P04-RECEIPT-NO-EXTERNAL-EFFECT", effects == strict_json_load(root / FIXTURE_PATH).get("expected_external_effect_boundary"), effects)

        signed_inputs = evidence.get("hashes", {}).get("inputs", {})
        input_errors: List[Any] = []
        if not isinstance(signed_inputs, dict):
            input_errors.append("signed inputs unavailable")
            signed_inputs = {}
        historical_inputs = []
        for relative, expected in signed_inputs.items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "reason": "unsafe path"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                if _historical_file_matches(root, relative, expected, verify_git_history):
                    historical_inputs.append(relative)
                else:
                    input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(
            checks,
            "S02P04-RECEIPT-SIGNED-INPUTS-CURRENT",
            not input_errors,
            input_errors or {"current": len(signed_inputs) - len(historical_inputs), "historical_phase_commit": historical_inputs},
        )

        report_errors = []
        validation_hashes = validation.get("hashes", {})
        for relative in [JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), PACK_REPORT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()]:
            expected = validation_hashes.get(relative)
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if expected != actual:
                report_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S02P04-RECEIPT-REPORT-HASHES-CURRENT", not report_errors, report_errors or "all reports match")
        code_expected = evidence.get("hashes", {}).get("code")
        code_actual = _current_code_hash(root)
        historical_code = _historical_code_hash(root, verify_git_history) if code_expected != code_actual else code_actual
        code_ok = code_expected == code_actual or (
            code_expected == PINNED_PHASE_CODE_HASH
            and (
                (not verify_git_history and historical_code == "UNVERIFIED_UNIT_TEST_HISTORY")
                or code_expected == historical_code
            )
        )
        _add(checks, "S02P04-RECEIPT-CODE-HASH-CURRENT", code_ok, {"expected": code_expected, "current": code_actual, "historical_phase_commit": historical_code})
        _add(checks, "S02P04-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        _add(checks, "S02P04-RECEIPT-NO-ABSOLUTE-LOCAL-PATH", str(root) not in rendered and ("/" + "Users/") not in rendered and ("/private/" + "var/") not in rendered, "portable evidence")
    else:
        for check_id in ["S02P04-RECEIPT-EVIDENCE-INTEGRITY", "S02P04-RECEIPT-VALIDATION-ALL-PASS", "S02P04-RECEIPT-NO-EXTERNAL-EFFECT", "S02P04-RECEIPT-SIGNED-INPUTS-CURRENT", "S02P04-RECEIPT-REPORT-HASHES-CURRENT", "S02P04-RECEIPT-CODE-HASH-CURRENT", "S02P04-RECEIPT-ROLLBACK-HASH-BINDING", "S02P04-RECEIPT-NO-ABSOLUTE-LOCAL-PATH"]:
            _add(checks, check_id, False, "evidence unavailable")

    rollback_ok = isinstance(rollback, dict) and rollback.get("evidence_id") == "EVD-S02-P04-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and len(rollback.get("artifacts", {})) == 10 and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S02P04-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, dict) else "unavailable")
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p04 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P04"]
        index_ok = len(p04) == 1 and p04[0].get("status") == "PASS" and p04[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and p04[0].get("artifact_sha256") == evidence_hash and p04[0].get("next") == "S02/STAGE_REVIEW_READY_NOT_STARTED"
        _add(checks, "S02P04-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, p04)
    except Exception as exc:
        _add(checks, "S02P04-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    if verify_p03_prerequisite:
        _check_p03_prerequisite(root, checks, verify_git_history)
    if verify_successor_state:
        _check_stage2_review_not_started(root, checks)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S02-P04",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S02_P04_EVIDENCE_VERIFIED" if not failed else "S02_P04_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": sum(1 for row in checks if row["passed"]), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S02/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S02/P04_REMEDIATION_REQUIRED",
    }
