from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .advice_card import contrast_ratio
from .canonical_facts import sha256_file, strict_json_load
from .reason_next_action import (
    render_failure_guidance,
    resolve_failure_states,
    validate_resolution,
    verify_existing_phase_evidence as verify_p03_evidence,
)
from .terminology_governance import scan_ui_text


CONTRACT_ID = "AC-S03-P04"
REQUIREMENT_ID = "REQ-S03-P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T14:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

PLAN_PATH = Path("ux_test_plan.json")
REPORT_PATH = Path("accessibility_report.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S03_P04.json")
TEST_PATH = Path("tests/S03/P04_test.py")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S03-P03_rollback.json")
ADVICE_SCHEMA_PATH = Path("advice_card_schema.json")
REASON_CODES_PATH = Path("reason_codes_zh.json")
NEXT_ACTION_MATRIX_PATH = Path("next_action_matrix.json")
GLOSSARY_PATH = Path("glossary_zh.json")
FORBIDDEN_PATH = Path("forbidden_ui_terms.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
MODEL_CARD_PATH = Path("machine/facts/model_system_card.json")
JUNIT_PATH = Path("machine/evidence/S03/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S03/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

DISPLAY_ORDER = ["status", "action", "countdown", "reasons", "evidence", "invalidation", "safety"]
FAILURE_GUIDANCE_ORDER = ["failure_status", "failure_reason", "next_action", "safety"]
ALLOWED_NUMERIC_BOUNDARY_DELTAS = {"-0.0001", "0", "0.0001"}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "bc5cbb4637e38074505cd2573f83dc39fd26ce3f1cc8557e9bbff63cf48b3074"

PHASE_COMMIT = "ef74f1f49994b4249844485bf3e61eb8c65a06b2"
PINNED_PHASE_CODE_HASH = "dc0228b02944f70eec4d565467a7e1788558c5ef061190106815fd28245b87db"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "ux_test_plan.json",
    "accessibility_report.json",
    "machine/tests/fixtures/S03_P04.json",
    "tests/S03/P04_test.py",
    "abd_acceptance/usability_accessibility.py",
    "abd_acceptance/reason_next_action.py",
    "abd_acceptance/advice_card.py",
    "abd_acceptance/terminology_governance.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "README.md": "5fb9e9748e0b4db72722662971d6283d9ac1b96eb674e5c6f7d341ef6cc65749",
    "ux_test_plan.json": "a2e011cacd58b56f4094cbf969bba8c748f56df628dbbeef639c25ffa82fb936",
    "accessibility_report.json": "845a784a44c45fc3f9d7a02519e39ea73c0d2c9f26a08d6ef90f22ae09cb3a7f",
    "machine/tests/fixtures/S03_P04.json": "3bd64eb92ff0bb1a2474ff53971af35455d0bdce63d76bfd8c800e7fe18de9ca",
    "tests/S03/P04_test.py": "0b9778815723e253d39ed8352bc9a27222b55aefcdf0efb85549861e60850dfc",
    "abd_acceptance/reason_next_action.py": "57ba25169061952a50334fbeddc4981ed1d275480cb21726ca5c83ce041556ed",
    "abd_acceptance/advice_card.py": "55c459f3da4dd624e0c8d4783734fdac24cfabc89bf5241bc74c134cbfecffe4",
    "abd_acceptance/terminology_governance.py": "d51ae252e7d28addfa7097a2f4ccb5ba2f017ec0745a0eee4e0971fd744beded",
    "abd_acceptance/__main__.py": "8b71ed0e39e933f0017314e848a3201a52d8e1631a36d9e568c3e35bbd9d032e",
    "abd_acceptance/__init__.py": "4178e5b2561fcf21af2cb71a95adf6f6a0b3a67f01a88bab81868110965e19b8",
}

PINNED_PHASE_HASHES = {
    PLAN_PATH.as_posix(): "a2e011cacd58b56f4094cbf969bba8c748f56df628dbbeef639c25ffa82fb936",
    REPORT_PATH.as_posix(): "845a784a44c45fc3f9d7a02519e39ea73c0d2c9f26a08d6ef90f22ae09cb3a7f",
    FIXTURE_PATH.as_posix(): "3bd64eb92ff0bb1a2474ff53971af35455d0bdce63d76bfd8c800e7fe18de9ca",
    TEST_PATH.as_posix(): "0b9778815723e253d39ed8352bc9a27222b55aefcdf0efb85549861e60850dfc",
}
PINNED_BASELINE_HASHES = {
    P03_EVIDENCE_PATH.as_posix(): "763d9ea60c03f9768d514e99b1846235add6dd187304ac273ae86e2eb03fddbc",
    P03_ROLLBACK_PATH.as_posix(): "888ef326c3bc5c8c830319c701805d89fae316e68da9b68b67bef01a7f486ad7",
    ADVICE_SCHEMA_PATH.as_posix(): "213f1f467d3421f56382f8de247842d23b3ece1ce726e83af13269caa6febc9a",
    REASON_CODES_PATH.as_posix(): "62c37e83b844b72fbeeebe5591a717d64c225629fb4ad421c44a6ad631ac8a20",
    NEXT_ACTION_MATRIX_PATH.as_posix(): "86e52de87b15a447a6d7d4683a8fe99b7f6f255552d05bde15dcf94928969f3d",
    GLOSSARY_PATH.as_posix(): "ffaf3a6c66533ce89bd8dc788b1bbfb09754bb8af0dec1355c90544eb4151097",
    FORBIDDEN_PATH.as_posix(): "c2dc156b31b7e333fe316343c09d6cab47339b18d3f7572b11e7c1fbf2590c7f",
    PARAMETERS_PATH.as_posix(): "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    MODEL_CARD_PATH.as_posix(): "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}


class UsabilityAccessibilityError(ValueError):
    """Raised when frozen usability inputs cannot be interpreted safely."""


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


def _contains_chinese(value: Any) -> bool:
    return isinstance(value, str) and re.search(r"[\u4e00-\u9fff]", value) is not None


def _duplicates(values: Sequence[Any]) -> List[Any]:
    seen: set[Any] = set()
    result: List[Any] = []
    for value in values:
        if value in seen and value not in result:
            result.append(value)
        seen.add(value)
    return result


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


def evaluate_timing_gate(
    durations_seconds: Any,
    *,
    median_max_seconds: int = 600,
    p95_max_seconds: int = 1200,
    numeric_boundary_delta: str = "0",
    adverse_odds_tick: bool = False,
) -> Dict[str, Any]:
    if numeric_boundary_delta not in ALLOWED_NUMERIC_BOUNDARY_DELTAS:
        raise UsabilityAccessibilityError("numeric boundary delta is not frozen")
    if type(adverse_odds_tick) is not bool:
        raise UsabilityAccessibilityError("adverse odds tick must be boolean")
    if type(median_max_seconds) is not int or type(p95_max_seconds) is not int:
        raise UsabilityAccessibilityError("timing thresholds must be integer seconds")
    if not isinstance(durations_seconds, list) or not durations_seconds:
        raise UsabilityAccessibilityError("timing samples must be a non-empty list")
    if any(type(value) is not int or value <= 0 for value in durations_seconds):
        raise UsabilityAccessibilityError("timing samples must be positive integer seconds")
    ordered = sorted(durations_seconds)
    count = len(ordered)
    median = ordered[math.ceil(count * 50 / 100) - 1]
    p95 = ordered[math.ceil(count * 95 / 100) - 1]
    passed = median <= median_max_seconds and p95 <= p95_max_seconds
    return {
        "status": "PASS" if passed else "FAIL",
        "decision": "WITHIN_FROZEN_TASK_BUDGET" if passed else "BLOCKED_TIMING_GATE",
        "sample_count": count,
        "median_seconds": median,
        "p95_seconds": p95,
        "median_max_seconds": median_max_seconds,
        "p95_max_seconds": p95_max_seconds,
        "quantile_method": "NEAREST_RANK_CEILING",
        "numeric_boundary_delta": numeric_boundary_delta,
        "adverse_odds_tick": adverse_odds_tick,
    }


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in {**PINNED_BASELINE_HASHES, **PINNED_PHASE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S03P04-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S03P04-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    graph = strict_json_load(root / "machine/facts/task_graph.json")
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    requirement = [row for row in requirements if row.get("id") == REQUIREMENT_ID]
    requirement_ok = len(requirement) == 1 and requirement[0] == {
        "id": REQUIREMENT_ID,
        "stage_id": "S03",
        "phase_id": "P04",
        "title": "可用性与无障碍",
        "problem": "若未完成“可用性与无障碍”，让用户无需查术语或文档即可操作，机器内部英文不泄漏到日常界面。将缺少可执行、可验收或可恢复的基础。",
        "user": "单一账户持有人及自动开发/运维代理",
        "value": "验证手机/电脑、低带宽、色盲、字号、键盘和屏幕阅读器。",
        "scope": ["ux_test_plan.json", "accessibility_report.json"],
        "non_goals": [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ],
        "baseline": "未实现或旧包存在冲突/缺口",
        "target": "核心操作中位数≤10分钟、95分位≤20分钟。",
        "measurement": "由 AC-S03-P04 的机器验收判定器执行固定输入、阈值和证据检查。",
        "observation_period": "开发期每次提交；上线后持续",
        "primary_acceptance_criteria_id": CONTRACT_ID,
        "priority": "P1",
        "owner_input_required_during_development": False,
    }
    _add(checks, "S03P04-TASKPACK-REQUIREMENT-EXACT", requirement_ok, requirement)
    contract = [row for row in acceptance if row.get("id") == CONTRACT_ID]
    contract_ok = (
        len(contract) == 1
        and contract[0].get("requirement_id") == REQUIREMENT_ID
        and contract[0].get("oracle") == {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S03-P04 --evidence machine/evidence",
            "rule": "核心操作中位数≤10分钟、95分位≤20分钟。",
        }
        and contract[0].get("pass_gate") == "核心操作中位数≤10分钟、95分位≤20分钟。"
        and [row.get("id") for row in contract[0].get("tests", [])]
        == ["TEST-S03-P04", "TEST-S03-P04-BOUNDARY", "TEST-S03-P04-REPLAY"]
        and "失败路径截图或结构化日志" in contract[0].get("evidence_requirements", [])
    )
    _add(checks, "S03P04-TASKPACK-ACCEPTANCE-EXACT", contract_ok, contract)
    tasks = [row for row in graph.get("tasks", []) if str(row.get("id", "")).startswith("T-S03-P04-")]
    task_ok = (
        [row.get("id") for row in tasks] == ["T-S03-P04-01", "T-S03-P04-02", "T-S03-P04-03"]
        and tasks[0].get("outputs") == [PLAN_PATH.as_posix(), REPORT_PATH.as_posix()]
        and tasks[0].get("depends_on") == ["T-S03-P03-03"]
        and tasks[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
        and tasks[1].get("depends_on") == ["T-S03-P04-01"]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
        and tasks[2].get("depends_on") == ["T-S03-P04-02"]
        and all(row.get("owner_input_required") is False and row.get("auto_advance_on_pass") is True for row in tasks)
    )
    _add(checks, "S03P04-TASKPACK-TASKS-EXACT", task_ok, [row.get("id") for row in tasks])
    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    trace_ok = len(trace) == 1 and trace[0] == {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S03-P04-01", "T-S03-P04-02", "T-S03-P04-03"],
        "test_ids": ["TEST-S03-P04", "TEST-S03-P04-BOUNDARY", "TEST-S03-P04-REPLAY"],
        "evidence_id": "EVD-S03-P04",
        "artifact_ids": ["ART-S03-P04-01", "ART-S03-P04-02"],
        "stage_id": "S03",
        "phase_id": "P04",
    }
    _add(checks, "S03P04-TASKPACK-TRACEABILITY-EXACT", trace_ok, trace)
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == "S03"]
    phases = stages[0].get("phases", []) if len(stages) == 1 else []
    p04 = [row for row in phases if row.get("id") == "P04"]
    roadmap_ok = (
        len(p04) == 1
        and p04[0].get("outputs") == [PLAN_PATH.as_posix(), REPORT_PATH.as_posix()]
        and p04[0].get("pass_gate") == "核心操作中位数≤10分钟、95分位≤20分钟。"
    )
    _add(checks, "S03P04-TASKPACK-ROADMAP-EXACT", roadmap_ok, p04)


def _check_source_integration(root: Path, checks: List[Dict[str, Any]]) -> None:
    schema = strict_json_load(root / ADVICE_SCHEMA_PATH)
    display = schema.get("x-abd-display-contract", {})
    contract = schema.get("x-abd-contract", {})
    palettes = list(display.get("status_palette", {}).values()) + list(display.get("countdown_palette", {}).values())
    palette_ratios = [contrast_ratio(row.get("background", ""), row.get("foreground", "")) for row in palettes]
    display_ok = (
        display.get("section_order") == DISPLAY_ORDER
        and display.get("color_is_only_signal") is False
        and display.get("required_redundant_signals") == ["中文状态文字", "状态符号", "明确行动句"]
        and palette_ratios
        and min(palette_ratios) >= 4.5
        and contract.get("ten_second_information_gate", {}).get("human_timing_validation") == "DEFERRED_TO_S03_P04"
        and contract.get("scope_status") == "SCHEMA_AND_DETERMINISTIC_PRESENTATION_MODEL_FROZEN_NOT_DEPLOYED"
    )
    _add(checks, "S03P04-P02-PRESENTATION-CONTRACT", display_ok, {"order": display.get("section_order"), "contrast": palette_ratios})
    catalog = strict_json_load(root / REASON_CODES_PATH)
    matrix = strict_json_load(root / NEXT_ACTION_MATRIX_PATH)
    safety = matrix.get("safety", {})
    failure_ok = (
        len(catalog.get("reason_codes", [])) == 49
        and len(matrix.get("actions", [])) == 38
        and catalog.get("coverage_status") == "ALL_CURRENTLY_DECLARED_FAILURE_CLASSES_CLOSED_FUTURE_PHASES_MUST_EXTEND"
        and safety.get("automatic_external_action_count") == 0
        and safety.get("order_submission_action_count") == 0
        and safety.get("order_retry_action_count") == 0
        and safety.get("paid_action_count") == 0
        and safety.get("gate_relaxation_action_count") == 0
    )
    _add(checks, "S03P04-P03-FAILURE-GUIDANCE-CONTRACT", failure_ok, safety)
    glossary = strict_json_load(root / GLOSSARY_PATH)
    policy = strict_json_load(root / FORBIDDEN_PATH)
    replay_errors: List[Dict[str, Any]] = []
    for reason in catalog.get("reason_codes", []):
        code = reason.get("code") if isinstance(reason, Mapping) else None
        try:
            resolution = resolve_failure_states(
                [code],
                reason_catalog=catalog,
                next_action_matrix=matrix,
            )
            validation_errors = validate_resolution(
                resolution,
                reason_catalog=catalog,
                next_action_matrix=matrix,
                glossary=glossary,
                policy=policy,
            )
            ui_errors = scan_ui_text(
                render_failure_guidance(resolution),
                "USER_ERROR_NEXT_ACTION",
                glossary,
                policy,
            )
            if (
                validation_errors
                or ui_errors
                or resolution.get("considered_count") != 1
                or not isinstance(resolution.get("next_action"), Mapping)
            ):
                replay_errors.append(
                    {
                        "code": code,
                        "validation_errors": validation_errors,
                        "ui_errors": ui_errors,
                    }
                )
        except Exception as exc:
            replay_errors.append({"code": code, "error": "%s: %s" % (type(exc).__name__, exc)})
    _add(
        checks,
        "S03P04-P03-ALL-FAILURE-GUIDANCE-REPLAY",
        len(catalog.get("reason_codes", [])) == 49 and not replay_errors,
        replay_errors or {"replayed": len(catalog.get("reason_codes", []))},
    )


def _check_plan_and_report(
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    plan_shape = (
        plan.get("schema_version") == "1.0.0"
        and plan.get("artifact_id") == "ART-S03-P04-01"
        and plan.get("contract_id") == CONTRACT_ID
        and plan.get("requirement_id") == REQUIREMENT_ID
        and plan.get("stage_id") == "S03"
        and plan.get("phase_id") == "P04"
        and plan.get("version") == VERSION
        and plan.get("fixed_clock") == FIXED_CLOCK
        and plan.get("status") == "FROZEN_DETERMINISTIC_DESIGN_CONTRACT"
        and plan.get("measurement_layer") == "FROZEN_CONSERVATIVE_TASK_BUDGETS_NOT_OBSERVED_HUMAN_TIMES"
        and plan.get("human_participant_count") == 0
        and plan.get("observed_session_count") == 0
        and not _contains_float(plan)
    )
    _add(checks, "S03P04-PLAN-SHAPE", plan_shape, plan.get("status"))
    task_ids = [row.get("id") for row in plan.get("core_tasks", []) if isinstance(row, Mapping)]
    _add(checks, "S03P04-PLAN-TASK-SET", task_ids == fixture.get("expected_task_ids") and not _duplicates(task_ids), task_ids)
    regions: set[str] = set()
    for row in plan.get("core_tasks", []):
        task_id = str(row.get("id", "INVALID")) if isinstance(row, Mapping) else "INVALID"
        if isinstance(row, Mapping):
            regions.update(str(item) for item in row.get("required_regions", []))
        ok = (
            isinstance(row, Mapping)
            and _contains_chinese(row.get("title_zh"))
            and _contains_chinese(row.get("success_criteria_zh"))
            and isinstance(row.get("required_regions"), list)
            and bool(row.get("required_regions"))
            and set(row.get("required_regions", [])).issubset(set(DISPLAY_ORDER))
        )
        _add(checks, "S03P04-TASK-%s" % task_id, ok, row)
    _add(checks, "S03P04-TASK-REGION-COVERAGE", regions == set(DISPLAY_ORDER), sorted(regions))
    core_04 = next((row for row in plan.get("core_tasks", []) if isinstance(row, Mapping) and row.get("id") == "CORE-04"), {})
    _add(
        checks,
        "S03P04-CORE-04-FAILURE-GUIDANCE-REGIONS",
        core_04.get("required_failure_guidance_regions") == fixture.get("expected_failure_guidance_regions") == FAILURE_GUIDANCE_ORDER,
        core_04.get("required_failure_guidance_regions"),
    )
    profiles = plan.get("profiles", [])
    profile_ids = [row.get("id") for row in profiles if isinstance(row, Mapping)]
    _add(checks, "S03P04-PROFILE-SET", profile_ids == fixture.get("expected_profile_ids") and not _duplicates(profile_ids), profile_ids)
    for row in profiles:
        profile_id = str(row.get("id", "INVALID")) if isinstance(row, Mapping) else "INVALID"
        ok = (
            isinstance(row, Mapping)
            and _contains_chinese(row.get("capability_zh"))
            and isinstance(row.get("frozen_environment"), Mapping)
            and bool(row.get("frozen_environment"))
            and row.get("evidence_layer") == "STRUCTURAL_DESIGN_CONTRACT_ONLY"
            and row.get("runtime_status") == "NOT_EXECUTED"
        )
        if profile_id == "PHONE_BROWSER":
            ok = ok and row["frozen_environment"] == {"viewport_css_px": "360x640", "input_mode": "触控与屏幕键盘"}
        elif profile_id == "DESKTOP_BROWSER":
            ok = ok and row["frozen_environment"] == {"viewport_css_px": "1440x900", "input_mode": "键盘与指针"}
        elif profile_id == "LOW_BANDWIDTH":
            ok = ok and row["frozen_environment"] == {"maximum_initial_payload_bytes": 32768, "image_dependency": "NONE"}
        elif profile_id == "COLOR_VISION":
            ok = ok and row["frozen_environment"].get("color_only_signal_allowed") is False and len(row["frozen_environment"].get("redundant_cues", [])) == 2
        elif profile_id == "TEXT_SCALE_200":
            ok = ok and row["frozen_environment"] == {"text_scale_percent": 200, "required_reflow": True}
        elif profile_id == "KEYBOARD_ONLY":
            ok = ok and row["frozen_environment"].get("pointer_required") is False and row["frozen_environment"].get("focus_order") == DISPLAY_ORDER
        elif profile_id == "SCREEN_READER_LINEAR":
            ok = ok and row["frozen_environment"].get("reading_order") == DISPLAY_ORDER and len(row["frozen_environment"].get("dynamic_announcements", [])) == 3
        else:
            ok = False
        _add(checks, "S03P04-PROFILE-%s" % profile_id, ok, row)
    timing = plan.get("timing_contract", {})
    timing_ok = timing == {
        "sample_semantics": "每个数值是冻结场景的保守完成预算，不是参与者观测值或生产遥测。",
        "scenario_scope": "ALL_CORE_TASKS_IN_ORDER",
        "unit": "seconds",
        "quantile_method": "NEAREST_RANK_CEILING",
        "median_rank": "ceil(0.50*n)",
        "p95_rank": "ceil(0.95*n)",
        "median_max_seconds": 600,
        "p95_max_seconds": 1200,
        "minimum_samples": 21,
        "hard_gate": True,
    }
    _add(checks, "S03P04-TIMING-CONTRACT-EXACT", timing_ok, timing)
    samples = plan.get("scenario_budgets", [])
    sample_ids = [row.get("id") for row in samples if isinstance(row, Mapping)]
    _add(checks, "S03P04-SAMPLE-IDS-UNIQUE", len(sample_ids) == 21 and not _duplicates(sample_ids), sample_ids)
    by_profile: Dict[str, List[int]] = {profile: [] for profile in fixture.get("expected_profile_ids", [])}
    for row in samples:
        sample_id = str(row.get("id", "INVALID")) if isinstance(row, Mapping) else "INVALID"
        profile_id = row.get("profile_id") if isinstance(row, Mapping) else None
        duration = row.get("budget_seconds") if isinstance(row, Mapping) else None
        ok = (
            isinstance(row, Mapping)
            and profile_id in by_profile
            and _contains_chinese(row.get("variant"))
            and type(duration) is int
            and duration > 0
        )
        if ok:
            by_profile[str(profile_id)].append(int(duration))
        _add(checks, "S03P04-SAMPLE-%s" % sample_id, ok, row)
    by_profile = {key: sorted(value) for key, value in by_profile.items()}
    _add(checks, "S03P04-SAMPLE-PROFILE-BUDGETS", by_profile == fixture.get("expected_profile_budget_seconds"), by_profile)
    durations = [row.get("budget_seconds") for row in samples if isinstance(row, Mapping)]
    try:
        timing_result = evaluate_timing_gate(durations)
        expected_timing = fixture.get("expected_timing_summary", {})
        timing_result_ok = (
            timing_result.get("status") == expected_timing.get("status")
            and timing_result.get("sample_count") == expected_timing.get("sample_count")
            and timing_result.get("median_seconds") == expected_timing.get("median_seconds")
            and timing_result.get("p95_seconds") == expected_timing.get("p95_seconds")
        )
    except Exception as exc:
        timing_result = {"error": "%s: %s" % (type(exc).__name__, exc)}
        timing_result_ok = False
    _add(checks, "S03P04-TIMING-GATE", timing_result_ok, timing_result)
    contracts = plan.get("accessibility_contracts", [])
    contract_ids = [row.get("id") for row in contracts if isinstance(row, Mapping)]
    _add(checks, "S03P04-A11Y-CONTRACT-SET", contract_ids == fixture.get("expected_accessibility_contract_ids") and not _duplicates(contract_ids), contract_ids)
    expected_profiles = fixture.get("expected_profile_ids", [])
    for index, row in enumerate(contracts):
        contract_id = str(row.get("id", "INVALID")) if isinstance(row, Mapping) else "INVALID"
        ok = (
            isinstance(row, Mapping)
            and index < len(expected_profiles)
            and row.get("profile_id") == expected_profiles[index]
            and isinstance(row.get("assertions"), list)
            and len(row.get("assertions", [])) == 3
            and all(_contains_chinese(value) for value in row.get("assertions", []))
        )
        _add(checks, "S03P04-A11Y-%s" % contract_id, ok, row)
    failure_guidance = plan.get("failure_guidance_integration", {})
    expected_failure_guidance = {
        "surface_kind": "USER_ERROR_NEXT_ACTION",
        "source_contract_id": "AC-S03-P03",
        "declared_reason_count": fixture.get("expected_failure_guidance_reason_count"),
        "region_order": FAILURE_GUIDANCE_ORDER,
        "keyboard_focus_order": FAILURE_GUIDANCE_ORDER,
        "screen_reader_order": FAILURE_GUIDANCE_ORDER,
        "machine_code_visible": False,
        "exactly_one_next_action_required": True,
        "chinese_ui_gate_required": True,
        "evidence_layer": "STRUCTURAL_DESIGN_CONTRACT_ONLY",
        "runtime_status": "NOT_EXECUTED",
    }
    _add(
        checks,
        "S03P04-FAILURE-GUIDANCE-INTEGRATION-EXACT",
        failure_guidance == expected_failure_guidance,
        failure_guidance,
    )
    failure_ids = plan.get("failure_injection_plan")
    _add(checks, "S03P04-FAILURE-PLAN-EXACT", failure_ids == fixture.get("expected_failure_ids"), failure_ids)
    expected_claim = fixture.get("expected_claim_boundary")
    _add(checks, "S03P04-PLAN-CLAIM-BOUNDARY", plan.get("claim_boundary") == expected_claim, plan.get("claim_boundary"))
    expected_boundary = fixture.get("expected_external_effect_boundary")
    _add(checks, "S03P04-PLAN-SAFETY-BOUNDARY", plan.get("safety") == expected_boundary, plan.get("safety"))
    _add(checks, "S03P04-PLAN-NEXT", plan.get("next_on_pass") == "S03/STAGE_REVIEW_READY_NOT_STARTED", plan.get("next_on_pass"))

    report_shape = (
        report.get("schema_version") == "1.0.0"
        and report.get("artifact_id") == "ART-S03-P04-02"
        and report.get("contract_id") == CONTRACT_ID
        and report.get("requirement_id") == REQUIREMENT_ID
        and report.get("stage_id") == "S03"
        and report.get("phase_id") == "P04"
        and report.get("version") == VERSION
        and report.get("fixed_clock") == FIXED_CLOCK
        and report.get("status") == "PASS_DETERMINISTIC_DESIGN_CONTRACT"
        and report.get("decision") == "USABILITY_ACCESSIBILITY_DESIGN_CONTRACT_FROZEN"
        and not _contains_float(report)
    )
    _add(checks, "S03P04-REPORT-SHAPE", report_shape, report.get("status"))
    expected_timing_report = {
        "evidence_kind": "FROZEN_CONSERVATIVE_TASK_BUDGETS_NOT_OBSERVED_HUMAN_TIMES",
        "sample_count": timing_result.get("sample_count"),
        "quantile_method": "NEAREST_RANK_CEILING",
        "median_seconds": timing_result.get("median_seconds"),
        "p95_seconds": timing_result.get("p95_seconds"),
        "median_max_seconds": 600,
        "p95_max_seconds": 1200,
        "machine_gate_status": timing_result.get("status"),
        "human_participant_count": 0,
        "observed_session_count": 0,
        "human_timing_status": "NOT_EXECUTED",
    }
    _add(checks, "S03P04-REPORT-TIMING-BINDING", report.get("timing_assessment") == expected_timing_report, report.get("timing_assessment"))
    structural = report.get("structural_assessment", {})
    results = structural.get("results", []) if isinstance(structural, Mapping) else []
    result_pairs = [(row.get("contract_id"), row.get("profile_id")) for row in results if isinstance(row, Mapping)]
    expected_pairs = list(zip(fixture.get("expected_accessibility_contract_ids", []), fixture.get("expected_profile_ids", [])))
    structural_ok = (
        structural.get("profile_count") == 7
        and structural.get("passed_contract_count") == 7
        and structural.get("failed_contract_count") == 0
        and structural.get("machine_gate_status") == "PASS"
        and result_pairs == expected_pairs
        and all(row.get("status") == "PASS_DESIGN_CONTRACT" and row.get("runtime_status") == "NOT_EXECUTED" for row in results)
    )
    _add(checks, "S03P04-REPORT-STRUCTURAL-BINDING", structural_ok, structural)
    expected_failure_assessment = {
        "source_contract_id": "AC-S03-P03",
        "declared_reason_count": fixture.get("expected_failure_guidance_reason_count"),
        "deterministically_replayed_reason_count": fixture.get("expected_failure_guidance_reason_count"),
        "region_order": FAILURE_GUIDANCE_ORDER,
        "keyboard_focus_order": FAILURE_GUIDANCE_ORDER,
        "screen_reader_order": FAILURE_GUIDANCE_ORDER,
        "unique_next_action_gate_status": "PASS",
        "chinese_ui_gate_status": "PASS",
        "status": "PASS_DESIGN_CONTRACT",
        "runtime_status": "NOT_EXECUTED",
    }
    _add(
        checks,
        "S03P04-REPORT-FAILURE-GUIDANCE-BINDING",
        report.get("failure_guidance_assessment") == expected_failure_assessment,
        report.get("failure_guidance_assessment"),
    )
    logs = report.get("structured_failure_logs", [])
    log_ids = [row.get("id") for row in logs if isinstance(row, Mapping)]
    _add(checks, "S03P04-REPORT-FAILURE-LOG-SET", log_ids == fixture.get("expected_failure_ids") and not _duplicates(log_ids), log_ids)
    for row in logs:
        fault_id = str(row.get("id", "INVALID")) if isinstance(row, Mapping) else "INVALID"
        ok = (
            isinstance(row, Mapping)
            and _contains_chinese(row.get("injected_fault"))
            and _contains_chinese(row.get("expected_action"))
            and row.get("status") == "FAIL_CLOSED_VERIFIED"
        )
        _add(checks, "S03P04-FAILURE-LOG-%s" % fault_id, ok, row)
    _add(checks, "S03P04-REPORT-CLAIM-BOUNDARY", report.get("claim_boundary") == expected_claim, report.get("claim_boundary"))
    _add(checks, "S03P04-REPORT-EXTERNAL-BOUNDARY", report.get("external_effect_boundary") == expected_boundary, report.get("external_effect_boundary"))
    unknowns = report.get("explicit_unknowns", [])
    unknowns_ok = isinstance(unknowns, list) and len(unknowns) == 5 and all(_contains_chinese(item) for item in unknowns)
    _add(checks, "S03P04-REPORT-UNKNOWNS-EXPLICIT", unknowns_ok, unknowns)
    _add(checks, "S03P04-REPORT-RELEASE-BOUNDARY", report.get("release_status") == "NOT_READY_STAGE_3_REVIEW_REQUIRED" and report.get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED", {"release": report.get("release_status"), "next": report.get("next")})
    rendered = json.dumps({"plan": plan, "report": report}, ensure_ascii=False, sort_keys=True)
    portable = (
        ("/" + "Users/") not in rendered
        and ("/private/" + "var/") not in rendered
        and ("file" + "://") not in rendered
        and ("C:" + "\\Users\\") not in rendered
    )
    _add(checks, "S03P04-ARTIFACTS-PORTABLE-NO-LOCAL-PATH", portable, "portable" if portable else "local path found")


def _check_boundary_vectors(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    for vector in fixture.get("boundary_vectors", []):
        try:
            result = evaluate_timing_gate(vector.get("durations_seconds"))
            ok = result.get("status") == vector.get("expected_status")
        except Exception as exc:
            result = {"error": "%s: %s" % (type(exc).__name__, exc)}
            ok = False
        _add(checks, "S03P04-BOUNDARY-%s" % vector.get("id"), ok, result)
    plan_durations = [value for values in fixture.get("expected_profile_budget_seconds", {}).values() for value in values]
    baseline = evaluate_timing_gate(plan_durations)
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        regular = evaluate_timing_gate(plan_durations, numeric_boundary_delta=delta, adverse_odds_tick=False)
        adverse = evaluate_timing_gate(plan_durations, numeric_boundary_delta=delta, adverse_odds_tick=True)
        invariant = all(
            row.get("status") == baseline.get("status")
            and row.get("median_seconds") == baseline.get("median_seconds")
            and row.get("p95_seconds") == baseline.get("p95_seconds")
            for row in [regular, adverse]
        )
        _add(checks, "S03P04-NUMERIC-ADVERSE-INVARIANT-%s" % delta.replace("-", "MINUS").replace(".", "_"), invariant, {"regular": regular, "adverse": adverse})
    first = evaluate_timing_gate(plan_durations)
    second = evaluate_timing_gate(copy.deepcopy(plan_durations))
    _add(checks, "S03P04-DETERMINISTIC-REPLAY", first == second, first)


def _stage_review_progression(root: Path) -> Dict[str, Any]:
    candidate = [
        Path("machine/facts/stage3_review_contract.json"),
        Path("machine/evidence/S03/STAGE_REVIEW/findings.json"),
        Path("machine/tests/fixtures/S03_STAGE_REVIEW.json"),
        Path("tests/S03/stage_review_test.py"),
        Path("abd_acceptance/stage3_review.py"),
    ]
    signed = [
        Path("machine/evidence/EVD-S03-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S03-STAGE-REVIEW_rollback.json"),
    ]
    candidate_present = [path.as_posix() for path in candidate if (root / path).is_file()]
    signed_present = [path.as_posix() for path in signed if (root / path).is_file()]
    review_rows: List[Mapping[str, Any]] = []
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        review_rows = [row for row in rows if row.get("id") == "INDEX-S03-STAGE-REVIEW"]
    except Exception as exc:
        return {"status": "INVALID", "error": "%s: %s" % (type(exc).__name__, exc)}
    if not candidate_present and not signed_present and not review_rows:
        return {"status": "READY_NOT_STARTED", "candidate": [], "signed": [], "index": []}
    if len(candidate_present) == len(candidate) and not signed_present and not review_rows:
        return {"status": "CONTROLLED_CANDIDATE", "candidate": candidate_present, "signed": [], "index": []}
    if len(candidate_present) == len(candidate) and len(signed_present) == len(signed) and len(review_rows) == 1:
        evidence_path = root / signed[0]
        signed_ok = (
            review_rows[0].get("status") == "PASS"
            and review_rows[0].get("actual_artifact") == signed[0].as_posix()
            and review_rows[0].get("artifact_sha256") == sha256_file(evidence_path)
            and review_rows[0].get("next") == "S03/GITHUB_STAGE_UPLOAD_READY"
        )
        if signed_ok:
            return {"status": "SIGNED_REVIEW_PASS", "candidate": candidate_present, "signed": signed_present, "index": review_rows}
    return {"status": "INVALID", "candidate": candidate_present, "signed": signed_present, "index": review_rows}


def _check_stage_review_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    progression = _stage_review_progression(root)
    _add(
        checks,
        "S03P04-STAGE-REVIEW-PROGRESSION-EXACT",
        progression.get("status") in {"READY_NOT_STARTED", "CONTROLLED_CANDIDATE", "SIGNED_REVIEW_PASS"},
        progression,
    )


def _check_phase_index(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P04"]
        planned = (
            len(matching) == 1
            and matching[0].get("status") == "PLANNED"
            and "actual_artifact" not in matching[0]
            and "artifact_sha256" not in matching[0]
        )
        delivered = False
        if len(matching) == 1 and (root / EVIDENCE_PATH).is_file():
            delivered = (
                matching[0].get("status") == "PASS"
                and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
                and matching[0].get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
                and matching[0].get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED"
            )
        _add(checks, "S03P04-EVIDENCE-INDEX-PLANNED-OR-SIGNED", planned or delivered, matching)
    except Exception as exc:
        _add(checks, "S03P04-EVIDENCE-INDEX-PLANNED-OR-SIGNED", False, "%s: %s" % (type(exc).__name__, exc))


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/usability_accessibility.py").read_text(encoding="utf-8")
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
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


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
        report.get("status") == "PASS"
        and isinstance(summary, Mapping)
        and summary.get("checks") == 49
        and summary.get("passed") == 49
        and summary.get("failed") == 0
    )


def _paid_dependency_scan_passes(scan_text: Any) -> bool:
    required = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    return isinstance(scan_text, str) and required.issubset(set(scan_text.splitlines()))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "USABILITY_ACCESSIBILITY_DESIGN_CONTRACT_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "phase_status": "S03_P04_PASS" if status == "PASS" else "S03_P04_FAILED",
        "measurement_status": "FROZEN_TASK_BUDGET_AND_STRUCTURAL_CONTRACT_ONLY",
        "human_validation_status": "NOT_EXECUTED",
        "production_status": "NOT_IMPLEMENTED_NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "release_status": "NOT_READY_STAGE_3_REVIEW_REQUIRED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "next": "S03/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S03/P04_REMEDIATION_REQUIRED",
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
    plan = _safe_load(root / PLAN_PATH, checks, "S03P04-PLAN-STRICT-JSON")
    report = _safe_load(root / REPORT_PATH, checks, "S03P04-REPORT-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S03P04-FIXTURE-STRICT-JSON")
    _check_pinned_hashes(root, checks, hashes)
    self_hash = _structural_self_hash(root)
    hashes["abd_acceptance/usability_accessibility.py"] = sha256_file(root / "abd_acceptance/usability_accessibility.py")
    _add(checks, "S03P04-ORACLE-SELF-INTEGRITY", self_hash == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_hash})
    try:
        predecessor = verify_p03_evidence(root, verify_git_history=_verify_git_history)
        prerequisite_ok = (
            predecessor.get("status") == "PASS"
            and predecessor.get("decision") == "S03_P03_EVIDENCE_VERIFIED"
            and predecessor.get("next") == "S03/P04_READY_NOT_STARTED"
        )
        _add(checks, "S03P04-P03-PREREQUISITE", prerequisite_ok, predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S03P04-P03-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_taskpack(root, checks)
    except Exception as exc:
        _add(checks, "S03P04-TASKPACK-INTERNAL-ERROR", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_source_integration(root, checks)
    except Exception as exc:
        _add(checks, "S03P04-SOURCE-INTEGRATION-INTERNAL-ERROR", False, "%s: %s" % (type(exc).__name__, exc))
    if isinstance(plan, Mapping) and isinstance(report, Mapping) and isinstance(fixture, Mapping):
        try:
            _check_plan_and_report(plan, report, fixture, checks)
            _check_boundary_vectors(fixture, checks)
        except Exception as exc:
            _add(checks, "S03P04-ARTIFACT-VALIDATION-INTERNAL-ERROR", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S03P04-ARTIFACTS-AVAILABLE", False, "plan, report or fixture unavailable")
    _check_stage_review_progression(root, checks)
    _check_phase_index(root, checks)
    if require_external_reports:
        for relative, check_id in [(JUNIT_PATH, "S03P04-JUNIT"), (FULL_JUNIT_PATH, "S03P04-FULL-REGRESSION")]:
            try:
                summary = _junit_summary(root / relative)
                hashes[relative.as_posix()] = sha256_file(root / relative)
                passed = summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and _junit_is_normalized(root / relative)
                _add(checks, check_id, passed, summary)
            except Exception as exc:
                _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            pack_report = strict_json_load(root / PACK_REPORT_PATH)
            hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
            _add(checks, "S03P04-PACK-REPORT", _pack_report_passes(pack_report), pack_report)
        except Exception as exc:
            _add(checks, "S03P04-PACK-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
        try:
            scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
            hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
            _add(checks, "S03P04-PAID-DEPENDENCY-SCAN", _paid_dependency_scan_passes(scan_text), scan_text.strip())
        except Exception as exc:
            _add(checks, "S03P04-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))
    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0)) if isinstance(fixture, Mapping) else 0
    if result["summary"]["checks"] < minimum:
        _add(checks, "S03P04-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
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
    artifacts = [PLAN_PATH, REPORT_PATH, FIXTURE_PATH, P03_EVIDENCE_PATH, ADVICE_SCHEMA_PATH, REASON_CODES_PATH]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s03-p04-rollback-") as directory:
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
        "evidence_id": "EVD-S03-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_USABILITY_ACCESSIBILITY_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        PLAN_PATH,
        REPORT_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        P03_EVIDENCE_PATH,
        P03_ROLLBACK_PATH,
        ADVICE_SCHEMA_PATH,
        REASON_CODES_PATH,
        NEXT_ACTION_MATRIX_PATH,
        GLOSSARY_PATH,
        FORBIDDEN_PATH,
        PARAMETERS_PATH,
        MODEL_CARD_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("README.md"),
        Path("abd_acceptance/usability_accessibility.py"),
        Path("abd_acceptance/reason_next_action.py"),
        Path("abd_acceptance/advice_card.py"),
        Path("abd_acceptance/terminology_governance.py"),
        Path("abd_acceptance/stage2_review.py"),
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
            "evidence_id": "EVD-S03-P04-ROLLBACK",
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
        result["phase_status"] = "S03_P04_FAILED"
        result["next"] = "S03/P04_REMEDIATION_REQUIRED"
    fixture = strict_json_load(root / FIXTURE_PATH)
    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S03",
        "phase_id": "P04",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S03-P04-01": PLAN_PATH.as_posix(),
            "ART-S03-P04-02": REPORT_PATH.as_posix(),
        },
        "p03_delivery_prerequisite": {
            "evidence": P03_EVIDENCE_PATH.as_posix(),
            "evidence_sha256": PINNED_BASELINE_HASHES[P03_EVIDENCE_PATH.as_posix()],
            "rollback_sha256": PINNED_BASELINE_HASHES[P03_ROLLBACK_PATH.as_posix()],
            "status": "PASS",
            "decision": "S03_P03_EVIDENCE_VERIFIED",
        },
        "measurement_boundary": fixture["expected_claim_boundary"],
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes[PARAMETERS_PATH.as_posix()],
            "code": _current_code_hash(root),
            "model": input_hashes[MODEL_CARD_PATH.as_posix()],
            "model_not_executed_reason": "S03/P04 validates frozen task budgets and structural accessibility contracts offline; it executes no human study, browser, screen reader, model, provider, deployment, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P04_test.py --junitxml=machine/evidence/S03/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S03/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S03-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": fixture["expected_external_effect_boundary"],
        "explicit_unknowns": [
            "The pass status covers frozen task budgets and structural design contracts, not observed human completion times.",
            "No production UI, real device, browser, low-bandwidth network, keyboard journey or screen-reader runtime was implemented or executed.",
            "No formal WCAG conformance or human usability conclusion is claimed.",
            "TAB, Gmail, OVH and Cloudflare account, authorization, capacity and runtime states remain uninspected or unverified and fail closed.",
            "No source, account, quote, model, stake or order was selected or executed.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
        ],
        "release_status": "NOT_READY_STAGE_3_REVIEW_REQUIRED",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P04"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S03-P04 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S03/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S03/P04_REMEDIATION_REQUIRED"
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
    if relative == "abd_acceptance/usability_accessibility.py":
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
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S03P04-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S03P04-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S03-P04"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S03"
            and evidence.get("phase_id") == "P04"
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "USABILITY_ACCESSIBILITY_DESIGN_CONTRACT_FROZEN"
            and evidence.get("phase_status") == "S03_P04_PASS"
            and evidence.get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED"
            and evidence.get("artifacts") == {"ART-S03-P04-01": PLAN_PATH.as_posix(), "ART-S03-P04-02": REPORT_PATH.as_posix()}
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S03P04-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            isinstance(validation, Mapping)
            and validation.get("status") == "PASS"
            and validation.get("decision") == "USABILITY_ACCESSIBILITY_DESIGN_CONTRACT_FROZEN"
            and validation.get("summary", {}).get("failed") == 0
            and validation.get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S03P04-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        fixture = strict_json_load(root / FIXTURE_PATH)
        _add(checks, "S03P04-RECEIPT-MEASUREMENT-BOUNDARY", evidence.get("measurement_boundary") == fixture.get("expected_claim_boundary"), evidence.get("measurement_boundary"))
        _add(checks, "S03P04-RECEIPT-NO-EXTERNAL-EFFECT", evidence.get("external_effect_boundary") == fixture.get("expected_external_effect_boundary"), evidence.get("external_effect_boundary"))
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
        _add(checks, "S03P04-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or len(signed_inputs))
        reports: List[Any] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), PACK_REPORT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()]:
            expected = validation_hashes.get(relative)
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if expected != actual:
                reports.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03P04-RECEIPT-REPORT-HASHES-CURRENT", not reports, reports or "all reports match")
        code_expected = evidence.get("hashes", {}).get("code")
        code_current = _current_code_hash(root)
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (
            code_expected == PINNED_PHASE_CODE_HASH
            and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(
            checks,
            "S03P04-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_current, "historical_phase_commit": code_historical},
        )
        _add(checks, "S03P04-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        portable = str(root) not in rendered and ("/" + "Users/") not in rendered and ("/private/" + "var/") not in rendered and ("file" + "://") not in rendered and ("C:" + "\\Users\\") not in rendered
        _add(checks, "S03P04-RECEIPT-NO-ABSOLUTE-LOCAL-PATH", portable, "portable" if portable else "local path found")
    else:
        for check_id in [
            "S03P04-RECEIPT-EVIDENCE-INTEGRITY",
            "S03P04-RECEIPT-VALIDATION-ALL-PASS",
            "S03P04-RECEIPT-MEASUREMENT-BOUNDARY",
            "S03P04-RECEIPT-NO-EXTERNAL-EFFECT",
            "S03P04-RECEIPT-SIGNED-INPUTS-CURRENT",
            "S03P04-RECEIPT-REPORT-HASHES-CURRENT",
            "S03P04-RECEIPT-CODE-HASH-CURRENT",
            "S03P04-RECEIPT-ROLLBACK-HASH-BINDING",
            "S03P04-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
        ]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S03-P04-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and len(rollback.get("artifacts", {})) == 6
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S03P04-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P04"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and matching[0].get("artifact_sha256") == evidence_hash
            and matching[0].get("next") == "S03/STAGE_REVIEW_READY_NOT_STARTED"
        )
        _add(checks, "S03P04-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S03P04-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        p03 = verify_p03_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S03P04-RECEIPT-P03-PREREQUISITE", p03.get("status") == "PASS", p03.get("summary"))
    except Exception as exc:
        _add(checks, "S03P04-RECEIPT-P03-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S03-P04",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S03_P04_EVIDENCE_VERIFIED" if not failed else "S03_P04_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S03/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S03/P04_REMEDIATION_REQUIRED",
    }
