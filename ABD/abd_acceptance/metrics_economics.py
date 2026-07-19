from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .delivery import verify_stage0_delivery


CONTRACT_ID = "AC-S01-P04"
REQUIREMENT_ID = "REQ-S01-P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

METRICS_PATH = Path("metrics.json")
ECONOMICS_PATH = Path("economics.json")
KILL_PATH = Path("kill_criteria.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S01_P04.json")
JUNIT_PATH = Path("machine/evidence/S01/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S01/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S01-P03_rollback.json")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

P03_COMMIT = "a4d5e3076f1e327072680207944a2d75514b1f03"
P03_EVIDENCE_SHA256 = "f2a547b995f92cc45e94e7ce21198f88f4b331212144be6f2f11207b7b768d46"
P03_ROLLBACK_SHA256 = "237b2ecf3f70be28f86e6be7967c98f0c99e0fce07d57f6ce3162b1dc2ecdf7d"

METRIC_SOURCE_BINDINGS = {
    "assumption_register.json": "b51e164e16fcf4c3cbd0708565583f91f7b5bf08f6a325d65a288872b03d9426",
    "business_flows.json": "5b5da6955582f383980186a6f69ff089139ae71b919e09bb2ade9b39d3026648",
    "customer_outcomes.json": "54ea272e26be24f88dc7344b4b2ea9d3268a488622214bc1790fe229d791b28d",
    P03_EVIDENCE_PATH.as_posix(): P03_EVIDENCE_SHA256,
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/degraded_mode_contract.json": "823a92ee03a468aaa1df6a4706aa0f1af3472b7f9c96c530877578f2f072d02f",
    "machine/facts/decision_prerequisites.json": "e9b54b985aff11faceaa7a2d6e6db42e070c96c0a8286a348ff767bc62921ccc",
    "machine/facts/email_ingestion.json": "7d40a142a482b5179aa6bb11fa0694fa5576a770f0b2a5af751615da3dea53cd",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/risk_register.json": "6f50e159f000ac4a1c714d08cff239e524a58c679cd77c05d7b4944a7b602888",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/security_assurance.json": "03543d4356f3718047293329d6b4e7cc3c14735b521e47f03079ff101f3205dd",
    "machine/facts/strategy_spec.json": "d77f047219632145a71f0f2932149654ae24205bbdc291fa604b93bfcff5117d",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "requirements.json": "ec1d098d5855b5835fbef315e276852454a7a43d66accd5a4ea5a193cd99f68d",
    "scope_boundary.json": "b1efc644928df96357a0eb65583c1ff100fcdc35239fde1b07e170411528a383",
}

ECONOMICS_SOURCE_BINDINGS = {
    "assumption_register.json": METRIC_SOURCE_BINDINGS["assumption_register.json"],
    "business_flows.json": METRIC_SOURCE_BINDINGS["business_flows.json"],
    "customer_outcomes.json": METRIC_SOURCE_BINDINGS["customer_outcomes.json"],
    P03_EVIDENCE_PATH.as_posix(): P03_EVIDENCE_SHA256,
    "machine/facts/canonical_facts.json": METRIC_SOURCE_BINDINGS["machine/facts/canonical_facts.json"],
    "machine/facts/costs.json": METRIC_SOURCE_BINDINGS["machine/facts/costs.json"],
    "machine/facts/parameters.json": METRIC_SOURCE_BINDINGS["machine/facts/parameters.json"],
    "machine/facts/requirements.json": METRIC_SOURCE_BINDINGS["machine/facts/requirements.json"],
    "machine/facts/risk_register.json": METRIC_SOURCE_BINDINGS["machine/facts/risk_register.json"],
    "machine/facts/strategy_spec.json": METRIC_SOURCE_BINDINGS["machine/facts/strategy_spec.json"],
    METRICS_PATH.as_posix(): "4eb776d819f6e3fe79715155876c8329cfa2e15db0eb0939e0360763eb2bcd5c",
    "requirements.json": METRIC_SOURCE_BINDINGS["requirements.json"],
    "scope_boundary.json": METRIC_SOURCE_BINDINGS["scope_boundary.json"],
}

KILL_SOURCE_BINDINGS = {
    ECONOMICS_PATH.as_posix(): "eafa8e9c959d77bd8cfc50fe97767040f8d163f5934f3e5573205a3cb38774f0",
    P03_EVIDENCE_PATH.as_posix(): P03_EVIDENCE_SHA256,
    "machine/facts/acceptance_contracts.json": METRIC_SOURCE_BINDINGS["machine/facts/acceptance_contracts.json"],
    "machine/facts/canonical_facts.json": METRIC_SOURCE_BINDINGS["machine/facts/canonical_facts.json"],
    "machine/facts/costs.json": METRIC_SOURCE_BINDINGS["machine/facts/costs.json"],
    "machine/facts/degraded_mode_contract.json": METRIC_SOURCE_BINDINGS["machine/facts/degraded_mode_contract.json"],
    "machine/facts/email_ingestion.json": METRIC_SOURCE_BINDINGS["machine/facts/email_ingestion.json"],
    "machine/facts/parameters.json": METRIC_SOURCE_BINDINGS["machine/facts/parameters.json"],
    "machine/facts/release_policy.json": METRIC_SOURCE_BINDINGS["machine/facts/release_policy.json"],
    "machine/facts/requirements.json": METRIC_SOURCE_BINDINGS["machine/facts/requirements.json"],
    "machine/facts/risk_register.json": METRIC_SOURCE_BINDINGS["machine/facts/risk_register.json"],
    "machine/facts/security_assurance.json": METRIC_SOURCE_BINDINGS["machine/facts/security_assurance.json"],
    "machine/facts/strategy_spec.json": METRIC_SOURCE_BINDINGS["machine/facts/strategy_spec.json"],
    METRICS_PATH.as_posix(): ECONOMICS_SOURCE_BINDINGS[METRICS_PATH.as_posix()],
    "requirements.json": METRIC_SOURCE_BINDINGS["requirements.json"],
    "scope_boundary.json": METRIC_SOURCE_BINDINGS["scope_boundary.json"],
}

PINNED_SOURCE_HASHES = dict(METRIC_SOURCE_BINDINGS)
PINNED_PHASE_HASHES = {
    METRICS_PATH.as_posix(): ECONOMICS_SOURCE_BINDINGS[METRICS_PATH.as_posix()],
    ECONOMICS_PATH.as_posix(): KILL_SOURCE_BINDINGS[ECONOMICS_PATH.as_posix()],
    KILL_PATH.as_posix(): "9432ec41dc80ff2b329f0f21b8f432222f339455121929b9d4f82fc05bf348cb",
    FIXTURE_PATH.as_posix(): "7abb7982198c21a41b04f677c64fe8c6b5ad23b5068b0d2171b18569759c3b14",
}
PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}
P03_SIGNED_ARTIFACT_HASHES = {
    "requirements.json": "ec1d098d5855b5835fbef315e276852454a7a43d66accd5a4ea5a193cd99f68d",
    "scope_boundary.json": "b1efc644928df96357a0eb65583c1ff100fcdc35239fde1b07e170411528a383",
    "business_flows.json": "5b5da6955582f383980186a6f69ff089139ae71b919e09bb2ade9b39d3026648",
    "machine/tests/fixtures/S01_P03.json": "cc077019262accae8982f4892f9b7752c88926db675b433ef47f14d173d94761",
}

NON_GOALS = [
    "不自动提交、确认或重试真实订单",
    "不以降低证据或风险门追赶30%月目标",
    "不引入付费数据或付费程序接口依赖",
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


def _find_by_id(rows: Any, item_id: str) -> Any:
    if not isinstance(rows, list):
        return None
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == item_id]
    return matches[0] if len(matches) == 1 else None


def _duplicates(values: Sequence[Any]) -> bool:
    rendered = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
    return len(rendered) != len(set(rendered))


def _json_pointer(value: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("invalid JSON pointer: %r" % pointer)
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit():
                raise KeyError(token)
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(token)
    return current


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_float(child) for child in value)
    return False


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("decimal input must be a canonical non-empty string or null")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("decimal must be finite")
    return result


def classify_target_evidence(
    *,
    complete_days: int,
    complete_months: int,
    signals: int,
    median_monthly_log_growth: Optional[str],
    monthly_log_growth_p05: Optional[str],
    capacity_pass: bool,
    monthly_return_95pct_upper_bound: Optional[str],
    cashflow_adjusted_geometric_monthly_return: Optional[str],
    complete_execution_evidence: bool,
    unresolved_reconciliation_differences: Optional[int],
) -> str:
    integer_values = [complete_days, complete_months, signals]
    if any(type(value) is not int or value < 0 for value in integer_values):
        return "INVALID_TARGET_EVIDENCE"
    if type(capacity_pass) is not bool or type(complete_execution_evidence) is not bool:
        return "INVALID_TARGET_EVIDENCE"
    if unresolved_reconciliation_differences is not None and (
        type(unresolved_reconciliation_differences) is not int or unresolved_reconciliation_differences < 0
    ):
        return "INVALID_TARGET_EVIDENCE"
    try:
        median = _decimal_or_none(median_monthly_log_growth)
        p05 = _decimal_or_none(monthly_log_growth_p05)
        upper = _decimal_or_none(monthly_return_95pct_upper_bound)
        geometric = _decimal_or_none(cashflow_adjusted_geometric_monthly_return)
    except ValueError:
        return "INVALID_TARGET_EVIDENCE"

    falsified = complete_months >= 6 and signals >= 1000 and upper is not None and upper < Decimal("0.30")
    verified = (
        complete_months >= 12
        and geometric is not None
        and geometric >= Decimal("0.30")
        and complete_execution_evidence
        and unresolved_reconciliation_differences == 0
    )
    plausible = (
        complete_days >= 90
        and signals >= 1000
        and median is not None
        and median >= Decimal("0.26236426446749106")
        and p05 is not None
        and p05 > Decimal("0")
        and capacity_pass
    )
    if falsified and verified:
        return "INVALID_CONFLICTING_TARGET_EVIDENCE"
    if verified:
        return "VERIFIED_HISTORICAL_NOT_GUARANTEED"
    if falsified:
        return "FALSIFIED"
    if plausible:
        return "PLAUSIBLE_NOT_VERIFIED"
    return "UNVERIFIED"


def resolve_incremental_cost_gate(value: Optional[str]) -> str:
    if value is None:
        return "BLOCK_UNKNOWN_INCREMENTAL_COST"
    try:
        amount = _decimal_or_none(value)
    except ValueError:
        return "FAIL_INVALID_INCREMENTAL_COST"
    if amount is None:
        return "BLOCK_UNKNOWN_INCREMENTAL_COST"
    if amount < 0:
        return "FAIL_INVALID_INCREMENTAL_COST"
    if amount > 0:
        return "BLOCK_POSITIVE_INCREMENTAL_COST"
    return "CONTINUE_ZERO_INCREMENTAL_COST"


def resolve_roi_default(
    verified_benefit_aud: Optional[str], complete_total_economic_cost_aud: Optional[str]
) -> Dict[str, Optional[str]]:
    try:
        benefit = _decimal_or_none(verified_benefit_aud)
        cost = _decimal_or_none(complete_total_economic_cost_aud)
    except ValueError:
        return {"status": "INVALID_INPUT", "value": None}
    if benefit is None or cost is None or cost == 0:
        return {"status": "NOT_COMPUTABLE", "value": None}
    if cost < 0:
        return {"status": "INVALID_COST", "value": None}
    value = (benefit - cost) / cost
    return {"status": "COMPUTABLE_VERIFIED_INPUTS", "value": format(value.normalize(), "f")}


def resolve_kill_default(*, evidence_complete: bool, threshold_evaluable: bool, triggered: bool) -> str:
    if any(type(value) is not bool for value in (evidence_complete, threshold_evaluable, triggered)):
        return "BLOCK_MALFORMED_KILL_EVALUATION"
    if not evidence_complete or not threshold_evaluable:
        return "UNVERIFIED_BLOCK_AFFECTED_DECISION"
    if triggered:
        return "APPLY_PREREGISTERED_KILL_ACTION"
    return "CLEARED_FOR_PREREGISTERED_SCOPE_ONLY"


def _single_source_check(root: Path, relative: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(relative.name)
        if not {".git", ".venv", ".pytest_cache", "__pycache__"}.intersection(path.parts)
    )
    expected = [relative.as_posix()]
    _add(checks, "S01P04-SINGLE-%s" % relative.stem.upper(), candidates == expected, candidates)


def _check_id_suffix(relative: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", relative.upper()).strip("-")


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in {**PINNED_SOURCE_HASHES, **PINNED_PHASE_HASHES}.items():
        check_id = "S01P04-HASH-%s" % _check_id_suffix(relative)
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, str(exc))
    for relative, expected in PINNED_REPO_HASHES.items():
        check_id = "S01P04-HASH-%s" % _check_id_suffix(relative)
        try:
            actual = sha256_file(root.parent / relative)
            hashes[relative] = actual
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, str(exc))


def _check_continuous_workflow(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        text = (root.parent / CONTINUOUS_WORKFLOW_PATH).read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S01P04-CONTINUOUS-CI", False, str(exc))
        return
    refs = re.findall(r"^\s*-\s+uses:\s+[^@\s]+@([^\s#]+)", text, flags=re.MULTILINE)
    expected_refs = {
        "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "ece7cb06caefa5fff74198d8649806c4678c61a1",
        "11f9893b081a58869d3b5fccaea48c9e9e46f990",
    }
    passed = (
        "name: ABD continuous validation" in text
        and "runs-on: ubuntu-latest" in text
        and "working-directory: ABD" in text
        and len(refs) == 3
        and set(refs) == expected_refs
        and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)
        and 'version: "0.11.28"' in text
        and 'python-version: "3.12"' in text
        and "uv sync --frozen --group dev" in text
        and re.search(r"^\s*run:\s+uv run --frozen --python 3\.12 python -m pytest -q\s*$", text, re.MULTILINE)
        is not None
        and "--verify-existing STAGE-REVIEW-S00" in text
        and "python machine/tools/validate_pack.py" in text
        and "python machine/tools/update_artifact_manifest.py" in text
        and "shasum -a 256 -c machine/evidence/SHA256SUMS" in text
        and "git diff --exit-code" in text
        and ("$" + "{{ secrets.") not in text
    )
    _add(checks, "S01P04-CONTINUOUS-CI", passed, refs)


def _check_taskpack_contract(
    roadmap: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        stage = [row for row in roadmap.get("stages", []) if row.get("id") == "S01"]
        phases = [row for row in stage[0].get("phases", []) if row.get("id") == "P04"] if len(stage) == 1 else []
        phase = phases[0] if len(phases) == 1 else {}
        roadmap_ok = (
            phase.get("title") == "指标与经济性"
            and phase.get("objective") == "建立现状基线、目标值、测量、观察周期、成本收益区间和机会成本。"
            and phase.get("outputs") == [METRICS_PATH.as_posix(), ECONOMICS_PATH.as_posix(), KILL_PATH.as_posix()]
            and phase.get("pass_gate") == "不承诺伪精确收益；30%目标可证伪可验证。"
            and phase.get("hours") == {"low": 3, "likely": 4, "high": 6}
        )
    except Exception as exc:
        phase = {"error": "%s: %s" % (type(exc).__name__, exc)}
        roadmap_ok = False
    _add(checks, "S01P04-ROADMAP-EXACT", roadmap_ok, phase)

    requirement = _find_by_id(list(requirements), REQUIREMENT_ID)
    requirement_ok = isinstance(requirement, dict) and (
        requirement.get("stage_id") == "S01"
        and requirement.get("phase_id") == "P04"
        and requirement.get("value") == "建立现状基线、目标值、测量、观察周期、成本收益区间和机会成本。"
        and requirement.get("scope") == [METRICS_PATH.as_posix(), ECONOMICS_PATH.as_posix(), KILL_PATH.as_posix()]
        and requirement.get("non_goals") == NON_GOALS
        and requirement.get("target") == "不承诺伪精确收益；30%目标可证伪可验证。"
        and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        and requirement.get("owner_input_required_during_development") is False
    )
    _add(checks, "S01P04-REQUIREMENT-EXACT", requirement_ok, requirement)

    contract = _find_by_id(list(acceptance), CONTRACT_ID)
    contract_ok = isinstance(contract, dict) and (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("oracle", {}).get("type") == "EXECUTABLE"
        and contract.get("oracle", {}).get("command")
        == "python -m abd_acceptance --contract AC-S01-P04 --evidence machine/evidence"
        and contract.get("oracle", {}).get("rule") == "不承诺伪精确收益；30%目标可证伪可验证。"
        and contract.get("pass_gate") == "不承诺伪精确收益；30%目标可证伪可验证。"
        and [row.get("id") for row in contract.get("tests", [])]
        == ["TEST-S01-P04", "TEST-S01-P04-BOUNDARY", "TEST-S01-P04-REPLAY"]
        and "新增现金支出将超过A$0" in contract.get("stop_condition", [])
    )
    _add(checks, "S01P04-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [
        row
        for row in task_graph.get("tasks", [])
        if isinstance(row, dict) and str(row.get("id", "")).startswith("T-S01-P04-")
    ]
    expected_ids = ["T-S01-P04-01", "T-S01-P04-02", "T-S01-P04-03"]
    tasks_ok = (
        [row.get("id") for row in tasks] == expected_ids
        and [row.get("depends_on") for row in tasks]
        == [["T-S01-P03-03"], ["T-S01-P04-01"], ["T-S01-P04-02"]]
        and all(row.get("auto_advance_on_pass") is True for row in tasks)
        and all(row.get("owner_input_required") is False for row in tasks)
        and tasks[0].get("outputs") == [METRICS_PATH.as_posix(), ECONOMICS_PATH.as_posix(), KILL_PATH.as_posix()]
        and tasks[1].get("outputs") == ["tests/S01/P04_test.py", FIXTURE_PATH.as_posix()]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
    )
    _add(checks, "S01P04-TASK-CHAIN-EXACT", tasks_ok, [row.get("id") for row in tasks])

    trace = next(
        (row for row in traceability if isinstance(row, dict) and row.get("requirement_id") == REQUIREMENT_ID),
        None,
    )
    trace_ok = isinstance(trace, dict) and (
        trace.get("acceptance_criteria_id") == CONTRACT_ID
        and trace.get("task_ids") == expected_ids
        and trace.get("test_ids") == ["TEST-S01-P04", "TEST-S01-P04-BOUNDARY", "TEST-S01-P04-REPLAY"]
        and trace.get("evidence_id") == "EVD-S01-P04"
        and trace.get("artifact_ids") == ["ART-S01-P04-01", "ART-S01-P04-02", "ART-S01-P04-03"]
    )
    _add(checks, "S01P04-TRACEABILITY-EXACT", trace_ok, trace)


def _check_source_bindings(
    root: Path,
    artifact: Mapping[str, Any],
    expected: Mapping[str, str],
    check_id: str,
    checks: List[Dict[str, Any]],
) -> None:
    actual: Dict[str, str] = {}
    try:
        actual = {relative: sha256_file(root / relative) for relative in expected}
        passed = artifact.get("source_bindings") == dict(expected) and actual == dict(expected)
    except Exception as exc:
        passed = False
        actual = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(checks, check_id, passed, {"declared": artifact.get("source_bindings"), "actual": actual})


def _walk_source_evidence(value: Any, prefix: str = "") -> Iterable[Tuple[str, Mapping[str, Any]]]:
    if isinstance(value, dict):
        if set(value) >= {"path", "pointers"}:
            yield prefix or "/", value
        for key, child in value.items():
            yield from _walk_source_evidence(child, prefix + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_source_evidence(child, prefix + "/" + str(index))


def _check_source_pointers(
    artifact: Mapping[str, Any],
    source_documents: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    check_id: str,
) -> None:
    detail: Dict[str, str] = {}
    passed = True
    rows = list(_walk_source_evidence(artifact))
    for location, reference in rows:
        relative = reference.get("path")
        pointers = reference.get("pointers")
        if relative not in source_documents or not isinstance(pointers, list) or not pointers:
            detail[location] = "UNKNOWN_SOURCE_OR_EMPTY_POINTERS"
            passed = False
            continue
        try:
            for pointer in pointers:
                _json_pointer(source_documents[relative], pointer)
            detail[location] = "PASS"
        except Exception as exc:
            detail[location] = "%s: %s" % (type(exc).__name__, exc)
            passed = False
    _add(checks, check_id, passed and bool(rows), detail)


def _check_metrics(
    root: Path,
    metrics: Mapping[str, Any],
    fixture: Mapping[str, Any],
    product_requirements: Mapping[str, Any],
    source_documents: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        metrics.get("schema_version") == "1.0.0"
        and metrics.get("artifact_id") == "ART-S01-P04-01"
        and metrics.get("requirement_id") == REQUIREMENT_ID
        and metrics.get("acceptance_contract_id") == CONTRACT_ID
        and metrics.get("product_version") == VERSION
        and metrics.get("fixed_at") == FIXED_CLOCK
        and metrics.get("status") == "METRICS_CONTRACT_BASELINES_MOSTLY_UNMEASURED_NOT_PERFORMANCE_PROOF"
        and metrics.get("next_on_acceptance_pass") == "S01/STAGE_REVIEW_READY_NOT_STARTED"
    )
    _add(checks, "S01P04-METRICS-TOP-LEVEL", top_ok, metrics.get("status"))
    _check_source_bindings(root, metrics, METRIC_SOURCE_BINDINGS, "S01P04-METRICS-SOURCE-BINDINGS", checks)

    rows = metrics.get("metrics", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    names = [row.get("name") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    expected_ids = fixture.get("expected_metric_ids")
    _add(checks, "S01P04-METRIC-IDS-EXACT-UNIQUE", ids == expected_ids and not _duplicates(ids), ids)
    _add(checks, "S01P04-METRIC-NAMES-UNIQUE", len(names) == len(ids) and not _duplicates(names), names)

    requirement_ids = {
        row.get("id")
        for row in product_requirements.get("requirements", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    complete = True
    routes_ok = True
    baseline_ok = True
    measurements_ok = True
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            complete = routes_ok = baseline_ok = measurements_ok = False
            continue
        complete = complete and all(
            row.get(key) not in (None, "", [])
            for key in ["id", "name", "dimension", "target", "measurement", "source_evidence", "failure_default"]
        )
        refs = row.get("requirement_ids")
        routes_ok = routes_ok and isinstance(refs, list) and bool(refs) and not _duplicates(refs) and set(refs).issubset(requirement_ids)
        baseline = row.get("baseline", {})
        baseline_ok = baseline_ok and (
            isinstance(baseline, dict)
            and baseline.get("evidence_maturity") == "CONTRACT_ONLY"
            and isinstance(baseline.get("status"), str)
            and baseline.get("status") not in {"PASS", "MEASURED", "VERIFIED", "RUNTIME_PASS"}
            and (baseline.get("value") is None or baseline.get("status") in {
                "LOCAL_CONTRACT_NEGATIVE_CAPABILITY_ONLY",
                "FROZEN_POLICY_ONLY_NO_LIVE_STRATEGY",
                "NO_90_DAY_1000_SIGNAL_CAPACITY_EVIDENCE",
                "NO_6_MONTH_1000_SIGNAL_CONFIDENCE_EVIDENCE",
                "NO_12_MONTH_ACTUAL_EXECUTION_AND_RECONCILIATION_EVIDENCE",
            })
        )
        measurement = row.get("measurement", {})
        measurements_ok = measurements_ok and (
            isinstance(measurement, dict)
            and isinstance(measurement.get("method"), str)
            and isinstance(measurement.get("cadence"), str)
            and isinstance(measurement.get("minimum_observation"), str)
            and type(measurement.get("minimum_sample")) is int
            and measurement.get("minimum_sample") >= 1
        )
    _add(checks, "S01P04-METRIC-ROWS-COMPLETE", complete, len(rows) if isinstance(rows, list) else "invalid")
    _add(checks, "S01P04-METRIC-REQUIREMENT-ROUTES", routes_ok, sorted(requirement_ids))
    covered_requirement_ids = {
        requirement_id
        for row in rows if isinstance(row, dict)
        for requirement_id in row.get("requirement_ids", []) if isinstance(requirement_id, str)
    }
    _add(
        checks,
        "S01P04-ALL-REQUIREMENTS-MEASURED-EXACT",
        covered_requirement_ids == requirement_ids,
        {"required": sorted(requirement_ids), "covered": sorted(covered_requirement_ids)},
    )
    _add(checks, "S01P04-NULL-BASELINES-NEVER-PASS", baseline_ok, "all baselines remain CONTRACT_ONLY")
    _add(checks, "S01P04-MEASUREMENT-CONTRACTS-COMPLETE", measurements_ok, "method cadence observation sample")

    semantics = metrics.get("metric_semantics", {})
    semantics_ok = semantics == {
        "missing_or_null_baseline": "UNMEASURED_NOT_PASS",
        "contract_value_is_runtime_measurement": False,
        "shadow_value_is_actual_return": False,
        "advice_ledger_is_actual_ledger": False,
        "target_curve_is_forecast": False,
        "unknown_external_state_default": "UNVERIFIED_OR_BLOCK_AFFECTED_CAPABILITY",
        "decimal_strings_required_for_authoritative_thresholds": True,
        "target_shortfall_may_relax_gate": False,
        "return_guaranteed": False,
    }
    _add(checks, "S01P04-METRIC-SEMANTICS-FAIL-CLOSED", semantics_ok, semantics)
    summary = metrics.get("traceability_summary", {})
    summary_ok = summary == {
        "metric_count": 31,
        "duplicate_metric_ids_allowed": 0,
        "untraced_metrics_allowed": 0,
        "null_baseline_may_pass": False,
        "all_authoritative_thresholds_source_bound": True,
    }
    _add(checks, "S01P04-METRIC-SUMMARY-EXACT", summary_ok, summary)

    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    exact_targets = {
        "MET-S01-P04-003": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-006": {"operator": "GREATER_THAN_OR_EQUAL", "value": "0.995", "classification": "HARD_GATE"},
        "MET-S01-P04-007": {"operator": "GREATER_THAN_OR_EQUAL", "value": "0.98", "classification": "HARD_GATE"},
        "MET-S01-P04-008": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-009": {"operator": "BETWEEN_INCLUSIVE", "minimum": "0.90", "maximum": "1.10", "classification": "MODEL_PROMOTION_GATE"},
        "MET-S01-P04-010": {"operator": "LESS_THAN_OR_EQUAL", "value": "0.02", "classification": "MODEL_PROMOTION_GATE"},
        "MET-S01-P04-011": {"operator": "LESS_THAN_OR_EQUAL", "value": "0.025", "classification": "MODEL_PROMOTION_GATE"},
        "MET-S01-P04-012": {"operator": "LESS_THAN_OR_EQUAL", "value": "0.04", "classification": "MODEL_PROMOTION_GATE"},
        "MET-S01-P04-017": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-022": {"operator": "EQUALS", "value": "0.00", "classification": "HARD_GATE"},
        "MET-S01-P04-027": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-028": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-029": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-030": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
        "MET-S01-P04-031": {"operator": "EQUALS", "value": 0, "classification": "HARD_GATE"},
    }
    exact_ok = all(by_id.get(item_id, {}).get("target") == expected for item_id, expected in exact_targets.items())
    _add(checks, "S01P04-CORE-METRIC-THRESHOLDS-EXACT", exact_ok, sorted(exact_targets))

    target_thresholds = fixture.get("expected_target_thresholds", {})
    plausible = by_id.get("MET-S01-P04-024", {}).get("target", {})
    falsified = by_id.get("MET-S01-P04-025", {}).get("target", {})
    verified = by_id.get("MET-S01-P04-026", {}).get("target", {})
    targets_ok = (
        plausible.get("minimum_days") == target_thresholds.get("plausibility_days")
        and plausible.get("minimum_independent_equivalent_signals") == target_thresholds.get("minimum_signals")
        and plausible.get("median_monthly_log_growth_min") == target_thresholds.get("monthly_log_growth")
        and plausible.get("monthly_log_growth_p05_min_exclusive") == "0"
        and plausible.get("capacity_pass_required") is True
        and falsified.get("minimum_complete_calendar_months") == target_thresholds.get("falsification_months")
        and falsified.get("minimum_independent_equivalent_signals") == target_thresholds.get("minimum_signals")
        and falsified.get("monthly_return_95pct_upper_bound_below") == target_thresholds.get("monthly_return")
        and verified.get("minimum_complete_calendar_months") == target_thresholds.get("verification_months")
        and verified.get("cashflow_adjusted_geometric_monthly_return_min") == target_thresholds.get("monthly_return")
        and verified.get("complete_execution_evidence_required") is True
        and verified.get("unresolved_reconciliation_difference_count") == target_thresholds.get("reconciliation_differences")
    )
    _add(checks, "S01P04-TARGET-CLASSIFICATION-GATES-EXACT", targets_ok, target_thresholds)

    boundary = metrics.get("s01_p04_execution_boundary", {})
    boundary_ok = boundary == {
        "metrics_measured_against_runtime": False,
        "model_or_strategy_evaluated": False,
        "target_plausibility_or_return_verified": False,
        "external_account_or_api_accessed": False,
        "production_deployed": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
        "return_or_guarantee_claimed": False,
        "stage_review_started": False,
    }
    _add(checks, "S01P04-METRICS-NO-RUNTIME-OR-RETURN-CLAIM", boundary_ok, boundary)
    _add(checks, "S01P04-METRICS-NO-BINARY-FLOAT", not _contains_float(metrics), "authoritative JSON contains no floats")
    _check_source_pointers(metrics, source_documents, checks, "S01P04-METRIC-SOURCE-POINTERS-RESOLVE")


def _check_economics(
    root: Path,
    economics: Mapping[str, Any],
    fixture: Mapping[str, Any],
    metric_ids: Sequence[str],
    source_documents: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        economics.get("schema_version") == "1.0.0"
        and economics.get("artifact_id") == "ART-S01-P04-02"
        and economics.get("requirement_id") == REQUIREMENT_ID
        and economics.get("acceptance_contract_id") == CONTRACT_ID
        and economics.get("product_version") == VERSION
        and economics.get("fixed_at") == FIXED_CLOCK
        and economics.get("currency") == "AUD"
        and economics.get("status") == "ECONOMICS_CONTRACT_REALIZED_BENEFIT_AND_TOTAL_COST_UNVERIFIED"
        and economics.get("next_on_acceptance_pass") == "S01/STAGE_REVIEW_READY_NOT_STARTED"
    )
    _add(checks, "S01P04-ECONOMICS-TOP-LEVEL", top_ok, economics.get("status"))
    _check_source_bindings(root, economics, ECONOMICS_SOURCE_BINDINGS, "S01P04-ECONOMICS-SOURCE-BINDINGS", checks)

    semantics = economics.get("economic_semantics", {})
    semantics_ok = (
        semantics.get("target_curve_is_forecast") is False
        and semantics.get("total_system_cost_is_zero") is False
        and semantics.get("return_guaranteed") is False
        and "A$300" in semantics.get("bankroll_principal", "")
        and "不是开发或基础设施预算" in semantics.get("bankroll_principal", "")
    )
    _add(checks, "S01P04-ECONOMIC-SEMANTICS-NO-ZERO-COST-OR-GUARANTEE", semantics_ok, semantics)

    cost = economics.get("cost_envelope", {})
    cost_ok = (
        cost.get("incremental_cash_budget_aud")
        == {"low": "0.00", "likely": "0.00", "high": "0.00", "status": "HARD_MAXIMUM_NOT_TOTAL_COST"}
        and cost.get("current_phase_incremental_cash_spent_aud") == "0.00"
        and cost.get("program_actual_incremental_cash_cost_aud", {}).get("value") is None
        and cost.get("program_actual_incremental_cash_cost_aud", {}).get("unknown_action") == "BLOCK_AFFECTED_CAPABILITY"
        and cost.get("existing_recurring_cash_cost_aud", {}).get("low") is None
        and cost.get("existing_recurring_cash_cost_aud", {}).get("likely") is None
        and cost.get("existing_recurring_cash_cost_aud", {}).get("high") is None
        and cost.get("development_effort_hours")
        == {"low": 240, "likely": 320, "high": 480, "status": "TASKPACK_ESTIMATE_NOT_ACTUAL_HOURS"}
        and len(cost.get("cost_categories_that_must_not_be_hidden", [])) == 6
    )
    _add(checks, "S01P04-COST-ENVELOPE-EXACT-UNKNOWN-NOT-ZERO", cost_ok, cost)
    opportunity_ok = economics.get("opportunity_cost_sensitivity", {}).get("scenarios") == fixture.get(
        "expected_opportunity_cost_scenarios"
    )
    _add(checks, "S01P04-OPPORTUNITY-COST-SENSITIVITY-EXACT", opportunity_ok, economics.get("opportunity_cost_sensitivity"))

    target = economics.get("target_curve_contract", {})
    target_ok = (
        target.get("initial_bankroll_aud") == "300.00"
        and target.get("formula") == "B_n = 300 * 1.3^n"
        and target.get("monthly_target_return") == "0.30"
        and target.get("monthly_target_log_growth") == "0.26236426446749106"
        and target.get("current_status") == "UNVERIFIED_FALSIFIABLE_TARGET"
        and target.get("is_cash_benefit_forecast") is False
        and target.get("is_expected_value_estimate") is False
        and target.get("is_guarantee") is False
        and target.get("may_be_used_as_roi_numerator") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and target.get("classification_metric_ids")
        == ["MET-S01-P04-024", "MET-S01-P04-025", "MET-S01-P04-026", "MET-S01-P04-027"]
    )
    _add(checks, "S01P04-TARGET-CURVE-NOT-FORECAST-OR-GUARANTEE", target_ok, target)

    benefit = economics.get("benefit_envelope", {})
    cash = benefit.get("realized_cash_benefit_aud", {})
    loss = benefit.get("loss_range_aud", {})
    benefit_ok = (
        cash.get("low") is None
        and cash.get("likely") is None
        and cash.get("high") is None
        and cash.get("null_is_not_zero") is True
        and benefit.get("realized_return", {}).get("value") is None
        and benefit.get("realized_return", {}).get("advice_or_shadow_performance_may_substitute") is False
        and benefit.get("loss_possible") is True
        and loss.get("low") is None
        and loss.get("likely") is None
        and loss.get("high") is None
    )
    _add(checks, "S01P04-BENEFIT-AND-LOSS-RANGES-UNVERIFIED", benefit_ok, benefit)
    non_cash = benefit.get("non_cash_benefits", [])
    non_cash_ok = (
        len(non_cash) == 5
        and not _duplicates([row.get("id") for row in non_cash])
        and all(row.get("monetized_value_aud") is None for row in non_cash)
        and all(bool(row.get("measurement_metric_ids")) for row in non_cash)
        and all(set(row.get("measurement_metric_ids", [])).issubset(set(metric_ids)) for row in non_cash)
    )
    _add(checks, "S01P04-NONCASH-BENEFITS-TRACEABLE-NOT-MONETIZED", non_cash_ok, non_cash)

    roi = economics.get("roi_contract", {})
    roi_ok = (
        roi.get("current_status") == "NOT_COMPUTABLE_WITHOUT_VERIFIED_BENEFIT_AND_COMPLETE_COST_LEDGER"
        and roi.get("numerator_aud") is None
        and roi.get("denominator_aud") is None
        and roi.get("roi") is None
        and roi.get("payback_period") is None
        and roi.get("net_present_value") is None
        and roi.get("division_by_zero_or_unknown_allowed") is False
        and roi.get("target_curve_or_shadow_result_allowed_as_verified_benefit") is False
        and roi.get("unknown_default") == "DO_NOT_REPORT_ROI"
    )
    _add(checks, "S01P04-ROI-NPV-PAYBACK-NOT-FABRICATED", roi_ok, roi)

    feasibility = economics.get("capacity_and_feasibility_contract", {})
    feasibility_ok = (
        feasibility.get("current_status") == "UNVERIFIED"
        and feasibility.get("cash_budget_feasible") == "CONDITIONAL_ONLY_IF_EVERY_INCREMENTAL_COST_REMAINS_EXACTLY_0.00"
        and str(feasibility.get("technical_capacity_feasible", "")).startswith("UNVERIFIED")
        and feasibility.get("target_economic_feasibility") == "UNVERIFIED"
        and feasibility.get("minimum_plausibility_evidence")
        == {"complete_days": 90, "independent_equivalent_signals": 1000, "capacity_pass": True}
        and feasibility.get("falsification_evidence")
        == {"complete_calendar_months": 6, "independent_equivalent_signals": 1000, "monthly_return_95pct_upper_bound_below": "0.30"}
        and feasibility.get("verification_evidence")
        == {"complete_calendar_months": 12, "cashflow_adjusted_geometric_monthly_return_min": "0.30", "complete_evidence": True, "unresolved_reconciliation_differences": 0}
        and feasibility.get("on_shortfall") == "REPORT_ONLY_NO_CHASE_LOSS_NO_GATE_RELAXATION"
    )
    _add(checks, "S01P04-FEASIBILITY-GATES-EXACT-UNVERIFIED", feasibility_ok, feasibility)

    decisions = economics.get("decision_rules", [])
    decision_ok = (
        [row.get("id") for row in decisions] == ["ECO-DEC-001", "ECO-DEC-002", "ECO-DEC-003", "ECO-DEC-004", "ECO-DEC-005"]
        and decisions[0].get("action") == "BLOCK_AFFECTED_CAPABILITY"
        and decisions[1].get("action") == "DO_NOT_REPORT_ROI"
        and "RELAX_EVIDENCE" in decisions[3].get("never", "")
        and "AUTO_UPGRADE" in decisions[4].get("never", "")
    )
    _add(checks, "S01P04-ECONOMIC-DECISIONS-FAIL-CLOSED", decision_ok, decisions)

    boundary = economics.get("s01_p04_execution_boundary", {})
    boundary_ok = boundary == {
        "economic_model_is_empirical_forecast": False,
        "roi_computed_or_claimed": False,
        "external_billing_or_account_inspected": False,
        "external_account_or_api_accessed": False,
        "production_deployed": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
        "actual_return_or_guarantee_claimed": False,
        "stage_review_started": False,
    }
    _add(checks, "S01P04-ECONOMICS-NO-EXTERNAL-OR-RETURN-EFFECT", boundary_ok, boundary)
    _add(checks, "S01P04-ECONOMICS-NO-BINARY-FLOAT", not _contains_float(economics), "authoritative JSON contains no floats")
    _check_source_pointers(economics, source_documents, checks, "S01P04-ECONOMICS-SOURCE-POINTERS-RESOLVE")


def _check_kill_criteria(
    root: Path,
    artifact: Mapping[str, Any],
    fixture: Mapping[str, Any],
    metric_ids: Sequence[str],
    source_documents: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        artifact.get("schema_version") == "1.0.0"
        and artifact.get("artifact_id") == "ART-S01-P04-03"
        and artifact.get("requirement_id") == REQUIREMENT_ID
        and artifact.get("acceptance_contract_id") == CONTRACT_ID
        and artifact.get("product_version") == VERSION
        and artifact.get("fixed_at") == FIXED_CLOCK
        and artifact.get("status") == "PROSPECTIVE_FAIL_CLOSED_KILL_CONTRACT_NOT_CURRENT_TRIGGER_EVIDENCE"
        and artifact.get("next_on_acceptance_pass") == "S01/STAGE_REVIEW_READY_NOT_STARTED"
    )
    _add(checks, "S01P04-KILL-TOP-LEVEL", top_ok, artifact.get("status"))
    _check_source_bindings(root, artifact, KILL_SOURCE_BINDINGS, "S01P04-KILL-SOURCE-BINDINGS", checks)

    rows = artifact.get("criteria", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    expected_ids = fixture.get("expected_kill_criterion_ids")
    _add(checks, "S01P04-KILL-IDS-EXACT-UNIQUE", ids == expected_ids and not _duplicates(ids), ids)
    complete = True
    metric_routes = True
    safe_actions = True
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            complete = metric_routes = safe_actions = False
            continue
        complete = complete and all(row.get(key) not in (None, "", []) for key in ["id", "name", "category", "condition", "action", "reentry_gate"])
        metric_routes = metric_routes and isinstance(row.get("metric_ids"), list) and set(row.get("metric_ids", [])).issubset(set(metric_ids))
        action = str(row.get("action", ""))
        safe_actions = safe_actions and not any(
            term in action
            for term in ["SUBMIT_ORDER", "CONFIRM_ORDER", "RETRY_ORDER", "PURCHASE_NOW", "UPGRADE_TO_PAID"]
        )
    _add(checks, "S01P04-KILL-ROWS-COMPLETE", complete, len(rows) if isinstance(rows, list) else "invalid")
    _add(checks, "S01P04-KILL-METRIC-ROUTES-VALID", metric_routes, metric_ids)
    _add(checks, "S01P04-KILL-ACTIONS-NO-ORDER-OR-SPEND", safe_actions, [row.get("action") for row in rows if isinstance(row, dict)])

    semantics = artifact.get("evaluation_semantics", {})
    semantics_ok = (
        semantics.get("criteria_are_prospective") is True
        and semantics.get("current_trigger_evaluation_performed") is False
        and semantics.get("missing_or_incomplete_evidence_is_pass") is False
        and semantics.get("missing_or_incomplete_evidence_default") == "UNVERIFIED_BLOCK_AFFECTED_DECISION"
        and semantics.get("contract_only_baseline_may_trigger_empirical_kill") is False
        and semantics.get("kill_requires_preregistered_scope_threshold_and_evidence") is True
        and semantics.get("target_shortfall_may_relax_any_gate") is False
        and semantics.get("target_shortfall_may_authorize_chase_loss") is False
        and semantics.get("kill_action_may_submit_cancel_confirm_or_retry_order") is False
        and semantics.get("unknown_total_cost_or_return_is_zero") is False
        and semantics.get("unknown_total_cost_or_return_supports_roi") is False
    )
    _add(checks, "S01P04-KILL-SEMANTICS-FAIL-CLOSED", semantics_ok, semantics)

    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    thresholds_ok = (
        by_id.get("KC-S01-P04-001", {}).get("condition", {}).get("threshold") == "0.00"
        and by_id.get("KC-S01-P04-002", {}).get("condition", {}).get("threshold") == 0
        and by_id.get("KC-S01-P04-005", {}).get("condition", {}).get("threshold") == 0
        and by_id.get("KC-S01-P04-006", {}).get("condition", {}).get("threshold") == "0.995"
        and by_id.get("KC-S01-P04-007", {}).get("condition", {}).get("minimum_observation")
        == "BOUNDARY_PLUS_OR_MINUS_0.0001_AND_ONE_ADVERSE_PROVIDER_TICK_REPLAY"
        and by_id.get("KC-S01-P04-008", {}).get("condition", {}).get("threshold") == "0"
        and by_id.get("KC-S01-P04-009", {}).get("condition", {}).get("threshold") == "FALSIFIED"
        and by_id.get("KC-S01-P04-010", {}).get("condition", {}).get("threshold") == "0.100"
        and by_id.get("KC-S01-P04-011", {}).get("condition", {}).get("threshold") == "0.700"
        and by_id.get("KC-S01-P04-012", {}).get("condition", {}).get("threshold") == 0
        and by_id.get("KC-S01-P04-015", {}).get("condition", {}).get("threshold") == "1.00"
        and by_id.get("KC-S01-P04-016", {}).get("condition", {}).get("threshold")
        == {"population_stability_index": "0.20", "jensen_shannon": "0.10"}
        and by_id.get("KC-S01-P04-017", {}).get("condition", {}).get("threshold") == 0
        and by_id.get("KC-S01-P04-018", {}).get("condition", {}).get("threshold") == 0
        and by_id.get("KC-S01-P04-019", {}).get("condition", {}).get("threshold") == 0
    )
    _add(checks, "S01P04-KILL-THRESHOLDS-EXACT", thresholds_ok, sorted(by_id))

    current = artifact.get("current_evaluation", {})
    current_ok = (
        current.get("performed") is False
        and current.get("status") == "NOT_EVALUATED_NO_RUNTIME_OR_EMPIRICAL_COHORT"
        and current.get("triggered_criterion_ids") is None
        and current.get("cleared_criterion_ids") is None
        and current.get("unknown_criterion_ids") == [item for item in expected_ids if item != "KC-S01-P04-002"]
        and current.get("contract_only_negative_capability_criterion_ids") == ["KC-S01-P04-002"]
        and current.get("target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and current.get("roi_status") == "NOT_COMPUTABLE"
        and current.get("release_effect") == "NO_RELEASE_AUTHORIZATION"
    )
    _add(checks, "S01P04-NO-FABRICATED-CURRENT-KILL-EVALUATION", current_ok, current)

    boundary = artifact.get("s01_p04_execution_boundary", {})
    boundary_ok = boundary == {
        "kill_criteria_evaluated_against_runtime": False,
        "model_strategy_or_target_killed_by_current_phase": False,
        "external_account_or_api_accessed": False,
        "production_deployed": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
        "actual_return_or_guarantee_claimed": False,
        "stage_review_started": False,
    }
    _add(checks, "S01P04-KILL-NO-RUNTIME-OR-EXTERNAL-EFFECT", boundary_ok, boundary)
    _add(checks, "S01P04-KILL-NO-BINARY-FLOAT", not _contains_float(artifact), "authoritative JSON contains no floats")
    _check_source_pointers(artifact, source_documents, checks, "S01P04-KILL-SOURCE-POINTERS-RESOLVE")


def _verify_p03_prerequisite(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    verify_git_history: bool,
) -> None:
    evidence = _safe_load(root / P03_EVIDENCE_PATH, checks, "S01P04-P03-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / P03_ROLLBACK_PATH, checks, "S01P04-P03-ROLLBACK-STRICT-JSON")
    if not isinstance(evidence, dict) or not isinstance(rollback, dict):
        _add(checks, "S01P04-P03-IMMUTABLE-RECEIPT", False, "receipt unavailable")
        return
    try:
        evidence_hash = sha256_file(root / P03_EVIDENCE_PATH)
        rollback_hash = sha256_file(root / P03_ROLLBACK_PATH)
        hashes[P03_EVIDENCE_PATH.as_posix()] = evidence_hash
        hashes[P03_ROLLBACK_PATH.as_posix()] = rollback_hash
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        integrity_ok = decision_hash == _sha256_bytes(_json_bytes(unsigned))
        receipt_ok = (
            evidence_hash == P03_EVIDENCE_SHA256
            and rollback_hash == P03_ROLLBACK_SHA256
            and evidence.get("evidence_id") == "EVD-S01-P03"
            and evidence.get("contract_id") == "AC-S01-P03"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "REQUIREMENTS_SCOPE_AND_FLOWS_FROZEN"
            and evidence.get("phase_status") == "S01_P03_PASS"
            and evidence.get("next") == "S01/P04_READY_NOT_STARTED"
            and evidence.get("artifacts")
            == {
                "ART-S01-P03-01": "requirements.json",
                "ART-S01-P03-02": "scope_boundary.json",
                "ART-S01-P03-03": "business_flows.json",
            }
            and evidence.get("hashes", {}).get("rollback_evidence") == P03_ROLLBACK_SHA256
            and evidence.get("external_effect_boundary", {}).get("github_upload_performed") is False
            and evidence.get("external_effect_boundary", {}).get("incremental_cash_spent_aud") == "0.00"
            and evidence.get("external_effect_boundary", {}).get("real_order_capability_present") is False
            and evidence.get("external_effect_boundary", {}).get("return_or_guarantee_claimed") is False
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and integrity_ok
        )
    except Exception as exc:
        receipt_ok = False
        evidence_hash = rollback_hash = "unavailable"
        integrity_ok = False
        _add(checks, "S01P04-P03-RECEIPT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _add(
        checks,
        "S01P04-P03-IMMUTABLE-RECEIPT",
        receipt_ok,
        {"evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "decision_integrity": integrity_ok},
    )

    signed_inputs = evidence.get("hashes", {}).get("inputs", {})
    artifact_ok = isinstance(signed_inputs, dict)
    detail = {}
    for relative, expected in P03_SIGNED_ARTIFACT_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
        signed = signed_inputs.get(relative) if isinstance(signed_inputs, dict) else None
        row_ok = actual == expected and signed == expected
        detail[relative] = {"expected": expected, "signed": signed, "actual": actual}
        artifact_ok = artifact_ok and row_ok
    _add(checks, "S01P04-P03-SIGNED-ARTIFACTS", artifact_ok, detail)

    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p03_rows = [row for row in rows if row.get("id") == "INDEX-AC-S01-P03"]
        index_ok = (
            len(p03_rows) == 1
            and p03_rows[0].get("status") == "PASS"
            and p03_rows[0].get("artifact_sha256") == P03_EVIDENCE_SHA256
            and p03_rows[0].get("actual_artifact") == P03_EVIDENCE_PATH.as_posix()
            and p03_rows[0].get("next") == "S01/P04_READY_NOT_STARTED"
        )
    except Exception as exc:
        p03_rows = []
        index_ok = False
        _add(checks, "S01P04-P03-INDEX-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _add(checks, "S01P04-P03-EVIDENCE-INDEX", index_ok, p03_rows)

    stage0 = verify_stage0_delivery(root, verify_git_history=verify_git_history)
    _add(
        checks,
        "S01P04-STAGE0-DELIVERY-CHAIN",
        stage0.get("status") == "PASS" and stage0.get("next") == "S01/P01_READY_NOT_STARTED",
        stage0.get("summary"),
    )
    hashes.update(stage0.get("hashes", {}))

    if verify_git_history:
        try:
            resolved = subprocess.run(
                ["git", "-C", str(root.parent), "rev-parse", "%s^{commit}" % P03_COMMIT],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            ancestor = subprocess.run(
                ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", P03_COMMIT, "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            git_ok = resolved.returncode == 0 and resolved.stdout.strip() == P03_COMMIT and ancestor.returncode == 0
            detail = {"resolved": resolved.stdout.strip(), "ancestor_exit": ancestor.returncode}
        except Exception as exc:
            git_ok = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S01P04-P03-GIT-ANCESTRY", git_ok, detail)
    else:
        _add(checks, "S01P04-TEST-ONLY-GIT-PROFILE", True, "Git ancestry skipped only for isolated mutation clone")


def _check_frozen_semantics(source_documents: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    canonical = source_documents["machine/facts/canonical_facts.json"]
    parameters = source_documents["machine/facts/parameters.json"]
    costs = source_documents["machine/facts/costs.json"]
    product = canonical.get("product", {})
    scope = canonical.get("scope", {})
    runtime = canonical.get("runtime", {})
    truth = canonical.get("truth_and_evidence", {})
    canonical_ok = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("target_curve") == "B_n = 300 * (1.3 ** n)"
        and scope.get("product_role") == "ANALYSIS_AND_ADVICE_ONLY"
        and scope.get("order_submission_module_present") is False
        and scope.get("normal_owner_action") == "FINAL_ORDER_ONLY"
        and scope.get("discovery_scope") == "ALL_OBSERVABLE_MARKETS"
        and scope.get("recommendation_scope") == "EVIDENCE_GATED"
        and runtime.get("primary") == "OVH_SINGAPORE_VPS1_24X7"
        and runtime.get("remote_access") == "CLOUDFLARE_ACCESS_AND_NAMED_TUNNEL"
        and runtime.get("availability_slo") == "0.995"
        and runtime.get("single_host_zero_downtime_guaranteed") is False
        and truth.get("advice_ledger_separate_from_actual_ledger") is True
        and truth.get("actual_return_requires_verified_execution_evidence") is True
    )
    _add(checks, "S01P04-CANONICAL-BOUNDARIES-FROZEN", canonical_ok, "principal budget role runtime evidence")

    target = parameters.get("target_30pct", {})
    target_ok = (
        target.get("monthly_return") == "0.30"
        and target.get("monthly_log_growth") == "0.26236426446749106"
        and target.get("shadow_min_days") == 90
        and target.get("shadow_min_independent_equivalent_signals") == 1000
        and len(target.get("plausible_gate", [])) == 3
        and len(target.get("falsification_gate", [])) == 3
        and len(target.get("verification_gate", [])) == 4
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
    )
    _add(checks, "S01P04-TARGET-FACTS-FROZEN", target_ok, target)

    risk = parameters.get("risk", {})
    risk_ok = risk == {
        "kelly_fraction_alpha": "0.00",
        "kelly_fraction_beta": "0.20",
        "kelly_fraction_ga": "0.25",
        "single_ticket_cap_beta": "0.015",
        "single_ticket_cap_ga": "0.020",
        "event_cap": "0.050",
        "correlation_cluster_cap": "0.050",
        "total_open_exposure_cap": "0.150",
        "daily_loss_soft_stop": "0.030",
        "seven_day_drawdown_diagnostic": "0.075",
        "strategy_slice_kill_drawdown": "0.100",
        "absolute_disaster_line": "0.700",
        "chase_loss_prohibited": True,
        "target_shortfall_may_relax_gate": False,
    }
    _add(checks, "S01P04-RISK-LIMITS-FROZEN", risk_ok, risk)

    numeric = parameters.get("numeric_determinism", {})
    numeric_ok = (
        numeric.get("independent_implementation_absolute_tolerance") == "1e-12"
        and numeric.get("action_must_match_across_implementations") is True
        and numeric.get("boundary_perturbation_absolute_probability") == "0.0001"
        and numeric.get("boundary_perturbation_absolute_threshold") == "0.0001"
        and numeric.get("boundary_perturbation_friction_up") == "0.0001"
        and numeric.get("unstable_action") == "NO_RECOMMENDATION"
        and numeric.get("binary_float_for_authoritative_decision") is False
    )
    _add(checks, "S01P04-NUMERIC-STABILITY-FROZEN", numeric_ok, numeric)

    cost_ok = (
        costs.get("incremental_cash_budget") == {"low": "0.00", "likely": "0.00", "high": "0.00"}
        and costs.get("incremental_cash_gate", {}).get("positive_boundary_aud") == "0.0001"
        and costs.get("incremental_cash_gate", {}).get("automatic_purchase_allowed") is False
        and costs.get("incremental_cash_gate", {}).get("automatic_paid_upgrade_allowed") is False
        and costs.get("incremental_cash_gate", {}).get("automatic_overage_billing_allowed") is False
        and costs.get("development_effort_hours") == {"low": 240, "likely": 320, "high": 480}
        and len(costs.get("opportunity_cost_sensitivity", [])) == 4
        and costs.get("benefit_model", {}).get("return_guaranteed") is False
    )
    _add(checks, "S01P04-COST-AND-BENEFIT-FACTS-FROZEN", cost_ok, "zero incremental gate and disclosed economic cost")


def _check_stage_review_not_started(
    root: Path,
    checks: List[Dict[str, Any]],
    *,
    allow_review_candidate: bool = False,
    verify_git_history: bool = True,
) -> None:
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        stage_rows = [row for row in rows if "S01" in str(row.get("id", "")) and "STAGE" in str(row.get("id", ""))]
        evidence = sorted(path for path in (root / "machine/evidence").rglob("*") if path.is_file() and "S01" in path.name and "STAGE" in path.name.upper())
        review_dirs = [root / "machine/evidence/S01/STAGE_REVIEW", root / "machine/evidence/S01/REVIEW"]
        if allow_review_candidate:
            row = stage_rows[0] if len(stage_rows) == 1 else {}
            evidence_names = [path.name for path in evidence]
            s02_evidence_names = sorted(path.name for path in (root / "machine/evidence").glob("EVD-S02-*.json"))
            successor_status = "NOT_PRESENT"
            successor_ok = not s02_evidence_names
            if s02_evidence_names == ["EVD-S02-P01.json", "EVD-S02-P01_rollback.json"]:
                from .official_platform_research import verify_existing_phase_evidence

                successor = verify_existing_phase_evidence(
                    root,
                    verify_git_history=verify_git_history,
                )
                successor_status = successor.get("status", "FAIL")
                successor_ok = successor_status == "PASS"
            elif s02_evidence_names == [
                "EVD-S02-P01.json",
                "EVD-S02-P01_rollback.json",
                "EVD-S02-P02.json",
                "EVD-S02-P02_rollback.json",
            ]:
                from .model_risk_research import verify_existing_phase_evidence as verify_p02_evidence

                successor = verify_p02_evidence(
                    root,
                    verify_git_history=verify_git_history,
                )
                successor_status = successor.get("status", "FAIL")
                successor_ok = successor_status == "PASS" and successor.get("next") == "S02/P03_READY_NOT_STARTED"
            elif s02_evidence_names == [
                "EVD-S02-P01.json",
                "EVD-S02-P01_rollback.json",
                "EVD-S02-P02.json",
                "EVD-S02-P02_rollback.json",
                "EVD-S02-P03.json",
                "EVD-S02-P03_rollback.json",
            ]:
                from .open_source_reuse import verify_existing_phase_evidence as verify_p03_evidence

                successor = verify_p03_evidence(
                    root,
                    verify_git_history=verify_git_history,
                )
                successor_status = successor.get("status", "FAIL")
                successor_ok = successor_status == "PASS" and successor.get("next") == "S02/P04_READY_NOT_STARTED"
            elif s02_evidence_names == [
                "EVD-S02-P01.json",
                "EVD-S02-P01_rollback.json",
                "EVD-S02-P02.json",
                "EVD-S02-P02_rollback.json",
                "EVD-S02-P03.json",
                "EVD-S02-P03_rollback.json",
                "EVD-S02-P04.json",
                "EVD-S02-P04_rollback.json",
            ]:
                from .research_gap_audit import verify_existing_phase_evidence as verify_p04_evidence

                successor = verify_p04_evidence(
                    root,
                    verify_git_history=verify_git_history,
                )
                successor_status = successor.get("status", "FAIL")
                successor_ok = (
                    successor_status == "PASS"
                    and successor.get("next") == "S02/STAGE_REVIEW_READY_NOT_STARTED"
                )
            elif s02_evidence_names == [
                "EVD-S02-P01.json",
                "EVD-S02-P01_rollback.json",
                "EVD-S02-P02.json",
                "EVD-S02-P02_rollback.json",
                "EVD-S02-P03.json",
                "EVD-S02-P03_rollback.json",
                "EVD-S02-P04.json",
                "EVD-S02-P04_rollback.json",
                "EVD-S02-STAGE-REVIEW.json",
                "EVD-S02-STAGE-REVIEW_rollback.json",
            ]:
                from .stage2_review import verify_existing_stage_review_evidence

                successor = verify_existing_stage_review_evidence(
                    root,
                    verify_phase_prerequisites=False,
                )
                successor_status = successor.get("status", "FAIL")
                successor_ok = (
                    successor_status == "PASS"
                    and successor.get("next") == "S02/GITHUB_STAGE_UPLOAD_READY"
                )
            elif s02_evidence_names:
                successor_status = "UNRECOGNIZED_S02_SUCCESSOR_SET"
                successor_ok = False
            status = row.get("status")
            planned_ok = status == "PLANNED" and not evidence_names and not s02_evidence_names
            completed_ok = status == "PASS" and sorted(evidence_names) == [
                "EVD-S01-STAGE-REVIEW.json",
                "EVD-S01-STAGE-REVIEW_rollback.json",
            ] and successor_ok
            passed = (
                row.get("id") == "INDEX-S01-STAGE-REVIEW"
                and (planned_ok or completed_ok)
                and (root / "machine/facts/stage1_review_contract.json").is_file()
                and (root / "machine/tests/fixtures/S01_STAGE_REVIEW.json").is_file()
                and (root / "abd_acceptance/stage1_review.py").is_file()
                and (root / "tests/S01/stage_review_test.py").is_file()
            )
        else:
            passed = not stage_rows and not evidence and not any(path.exists() for path in review_dirs)
        if allow_review_candidate:
            detail = {
                "mode": "GATED_REVIEW_CANDIDATE",
                "review_contract_present": (root / "machine/facts/stage1_review_contract.json").is_file(),
                "s02_evidence": s02_evidence_names,
                "verified_successor_status": successor_status,
            }
        else:
            detail = {
                "mode": "P04_ONLY",
                "index_rows": [row.get("id") for row in stage_rows],
                "index_status": [row.get("status") for row in stage_rows],
                "evidence": [path.name for path in evidence],
                "directories": [path.name for path in review_dirs if path.exists()],
            }
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01P04-STAGE-REVIEW-NOT-STARTED", passed, detail)


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
            if element.attrib.get("timestamp") != FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(
    root: Path,
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    reports = [
        ("S01P04-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S01P04-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
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

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S01P04-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S01P04-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)

    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = (
            "STATUS: PASS" in scan_text
            and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan_text
            and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
            and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in scan_text
        )
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        _add(checks, "S01P04-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S01P04-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P04",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "METRICS_ECONOMICS_AND_KILL_CONTRACT_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "release_status": "NOT_READY_STAGE_REVIEW_REQUIRED",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "roi_status": "NOT_COMPUTABLE",
        "phase_status": "S01_P04_PASS" if status == "PASS" else "S01_P04_FAILED",
        "next": "S01/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S01/P04_REMEDIATION_REQUIRED",
    }


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
    _allow_stage_review_candidate: bool = False,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}

    for path in (METRICS_PATH, ECONOMICS_PATH, KILL_PATH, FIXTURE_PATH):
        _single_source_check(root, path, checks)

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S01P04-FIXTURE-STRICT-JSON")
    metrics = _safe_load(root / METRICS_PATH, checks, "S01P04-METRICS-STRICT-JSON")
    economics = _safe_load(root / ECONOMICS_PATH, checks, "S01P04-ECONOMICS-STRICT-JSON")
    kill = _safe_load(root / KILL_PATH, checks, "S01P04-KILL-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S01P04-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S01P04-TASKPACK-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S01P04-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S01P04-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S01P04-TRACEABILITY-STRICT-JSON")
    product_requirements = _safe_load(root / "requirements.json", checks, "S01P04-PRODUCT-REQUIREMENTS-STRICT-JSON")

    source_paths = set(METRIC_SOURCE_BINDINGS) | set(ECONOMICS_SOURCE_BINDINGS) | set(KILL_SOURCE_BINDINGS)
    source_documents = {
        relative: _safe_load(root / relative, checks, "S01P04-SOURCE-%s-STRICT-JSON" % _check_id_suffix(relative))
        for relative in sorted(source_paths)
        if relative.endswith(".json")
    }

    _check_pinned_hashes(root, checks, hashes)
    _check_continuous_workflow(root, checks)
    import_isolation_ok = all(
        (root / path).is_file()
        for path in [Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py")]
    )
    _add(checks, "S01P04-PYTEST-IMPORT-ISOLATION", import_isolation_ok, "package markers")

    dictionaries = [fixture, metrics, economics, kill, roadmap, task_graph, product_requirements]
    arrays = [requirements, acceptance, traceability]
    if (
        not all(isinstance(value, dict) for value in dictionaries)
        or not all(isinstance(value, list) for value in arrays)
        or not all(value is not None for value in source_documents.values())
    ):
        _add(checks, "S01P04-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S01P04-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S01P04-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_metrics(root, metrics, fixture, product_requirements, source_documents, checks)
    except Exception as exc:
        _add(checks, "S01P04-METRICS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    metric_ids = fixture.get("expected_metric_ids", [])
    try:
        _check_economics(root, economics, fixture, metric_ids, source_documents, checks)
    except Exception as exc:
        _add(checks, "S01P04-ECONOMICS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_kill_criteria(root, kill, fixture, metric_ids, source_documents, checks)
    except Exception as exc:
        _add(checks, "S01P04-KILL-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    _verify_p03_prerequisite(root, checks, hashes, _verify_git_history)
    try:
        _check_frozen_semantics(source_documents, checks)
    except Exception as exc:
        _add(checks, "S01P04-FROZEN-SEMANTICS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _check_stage_review_not_started(
        root,
        checks,
        allow_review_candidate=_allow_stage_review_candidate,
        verify_git_history=_verify_git_history,
    )
    if require_external_reports:
        _check_runtime_reports(root, fixture, checks, hashes)
    return _build_result(checks, hashes)


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
        (METRICS_PATH.as_posix(), root / METRICS_PATH),
        (ECONOMICS_PATH.as_posix(), root / ECONOMICS_PATH),
        (KILL_PATH.as_posix(), root / KILL_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (P03_EVIDENCE_PATH.as_posix(), root / P03_EVIDENCE_PATH),
        (P03_ROLLBACK_PATH.as_posix(), root / P03_ROLLBACK_PATH),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s01-p04-rollback-") as directory:
        temporary = Path(directory)
        for index, (label, source) in enumerate(artifacts):
            expected_hash = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted_hash = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored_hash = sha256_file(active)
            results[label] = {
                "status": "PASS" if corrupted_hash != expected_hash and restored_hash == expected_hash else "FAIL",
                "signed_sha256": expected_hash,
                "corrupted_sha256": corrupted_hash,
                "restored_sha256": restored_hash,
            }
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_METRICS_ECONOMICS_KILL_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        METRICS_PATH,
        ECONOMICS_PATH,
        KILL_PATH,
        FIXTURE_PATH,
        P03_EVIDENCE_PATH,
        P03_ROLLBACK_PATH,
        *[Path(relative) for relative in PINNED_SOURCE_HASHES if relative != P03_EVIDENCE_PATH.as_posix()],
        Path("tests/S01/P03_test.py"),
        Path("tests/S01/P04_test.py"),
        Path("abd_acceptance/metrics_economics.py"),
        Path("abd_acceptance/requirements_scope.py"),
        Path("abd_acceptance/delivery.py"),
        Path("abd_acceptance/__main__.py"),
        Path("abd_acceptance/__init__.py"),
        Path("tests/__init__.py"),
        Path("tests/S00/__init__.py"),
        Path("tests/S01/__init__.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[CONTINUOUS_WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / CONTINUOUS_WORKFLOW_PATH)
    return result


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
    *,
    _allow_stage_review_candidate: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(
        root,
        require_external_reports=require_external_reports,
        _allow_stage_review_candidate=_allow_stage_review_candidate,
    )
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S01-P04-ROLLBACK",
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
        result["phase_status"] = "S01_P04_FAILED"
        result["next"] = "S01/P04_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P04",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S01-P04-01": METRICS_PATH.as_posix(),
            "ART-S01-P04-02": ECONOMICS_PATH.as_posix(),
            "ART-S01-P04-03": KILL_PATH.as_posix(),
        },
        "p03_prerequisite": {
            "evidence": P03_EVIDENCE_PATH.as_posix(),
            "sha256": P03_EVIDENCE_SHA256,
            "commit": P03_COMMIT,
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S01/P04 freezes metrics and economics contracts but executes no prediction model, strategy or target verification.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing STAGE-REVIEW-S00",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S01/P04_test.py --junitxml=machine/evidence/S01/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S01/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S01-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": {
            "github_upload_performed": False,
            "external_account_or_api_accessed": False,
            "secret_provisioned": False,
            "incremental_cash_spent_aud": "0.00",
            "production_deployment_claimed": False,
            "all_market_coverage_claimed": False,
            "gmail_connected_claimed": False,
            "real_order_capability_present": False,
            "return_or_guarantee_claimed": False,
            "stage_review_started": False,
        },
        "explicit_unknowns": [
            "The 30% monthly target remains unverified, falsifiable and not guaranteed.",
            "Realized cash benefit, actual return, ROI, NPV, payback and complete total economic cost remain unknown or not computable.",
            "OVH, Cloudflare, Gmail, betting accounts, billing, capacity, source freshness and all-market production coverage remain unverified.",
            "The S01/P04 outputs are prospective measurement and kill contracts, not runtime, deployment, model-performance or actual-return evidence.",
            "No external account, secret, real email, order, deployment, stage review or actual return was observed in this phase.",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S01-P04"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S01-P04 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S01/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S01/P04_REMEDIATION_REQUIRED"
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
