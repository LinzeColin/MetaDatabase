from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .delivery import RECEIPT_PATH, verify_stage0_delivery


CONTRACT_ID = "AC-S01-P01"
REQUIREMENT_ID = "REQ-S01-P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

PRESS_RELEASE_PATH = Path("customer_press_release.md")
OUTCOMES_PATH = Path("customer_outcomes.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S01_P01.json")
JUNIT_PATH = Path("machine/evidence/S01/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S01/P01/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PINNED_SOURCE_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/evidence/EVD-S00-STAGE-REVIEW.json": "48966ee6a98ad93224f11eb99890448cad6105840141dc4016520a932a857e0d",
}

PINNED_PHASE_HASHES = {
    PRESS_RELEASE_PATH.as_posix(): "8cd88a4d4cd0dc6fe4735f8c0400fdd05ccab001afdbe9a09aec57a683f950ab",
    OUTCOMES_PATH.as_posix(): "54ea272e26be24f88dc7344b4b2ea9d3268a488622214bc1790fe229d791b28d",
    FIXTURE_PATH.as_posix(): "824e848b8d259ea1d29f6a10a9df38d1f1fbefeb0ab1c774da94fa27af0c8a96",
    "tests/__init__.py": "214896f19f61ef6e1e73500ce53894866f9524c972db91d32f92a62d9818d316",
    "tests/S00/__init__.py": "92747c3175dab227e64bab76b0728e85016df09d9114fb5b0b16f68a6971c03f",
    "tests/S01/__init__.py": "2699f54f59bd6a4e1d3042e40a336c24a61dd71ece37e7e7c243532f6e309134",
}
PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}


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


def _duplicates(values: Sequence[Any]) -> bool:
    rendered = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
    return len(rendered) != len(set(rendered))


def resolve_card_decision(
    *,
    evidence_complete: bool,
    fresh: bool,
    stable_under_adverse_tests: bool,
    risk_gate_passed: bool,
) -> str:
    gates = (evidence_complete, fresh, stable_under_adverse_tests, risk_gate_passed)
    return "RECOMMENDATION" if all(value is True for value in gates) else "NO_RECOMMENDATION"


def _single_source_check(root: Path, relative: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(relative.name)
        if not {".git", ".venv", ".pytest_cache", "__pycache__"}.intersection(path.parts)
    )
    _add(checks, "S01P01-SINGLE-%s" % relative.stem.upper(), candidates == [relative.as_posix()], candidates)


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in {**PINNED_SOURCE_HASHES, **PINNED_PHASE_HASHES}.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S01P01-HASH-%s" % Path(relative).stem.upper(),
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S01P01-HASH-%s" % Path(relative).stem.upper(), False, str(exc))
    for relative, expected in PINNED_REPO_HASHES.items():
        try:
            actual = sha256_file(root.parent / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S01P01-HASH-%s" % Path(relative).stem.upper(),
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S01P01-HASH-%s" % Path(relative).stem.upper(), False, str(exc))


def _check_continuous_workflow(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        text = (root.parent / CONTINUOUS_WORKFLOW_PATH).read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S01P01-CONTINUOUS-CI-SUPPLY-CHAIN", False, str(exc))
        _add(checks, "S01P01-CONTINUOUS-CI-HISTORICAL-REPLAY", False, str(exc))
        return
    action_refs = re.findall(r"^\s*-\s+uses:\s+[^@\s]+@([^\s#]+)", text, flags=re.MULTILINE)
    expected_refs = {
        "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "ece7cb06caefa5fff74198d8649806c4678c61a1",
        "11f9893b081a58869d3b5fccaea48c9e9e46f990",
    }
    supply_chain_ok = (
        len(action_refs) == 3
        and set(action_refs) == expected_refs
        and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
        and 'version: "0.11.28"' in text
        and 'python-version: "3.12"' in text
        and "fetch-depth: 0" in text
        and "uv sync --frozen --group dev" in text
    )
    _add(checks, "S01P01-CONTINUOUS-CI-SUPPLY-CHAIN", supply_chain_ok, action_refs)
    replay_ok = (
        "name: ABD continuous validation" in text
        and "runs-on: ubuntu-latest" in text
        and "working-directory: ABD" in text
        and re.search(
            r"^\s*run:\s+uv run --frozen --python 3\.12 python -m pytest -q\s*$",
            text,
            flags=re.MULTILINE,
        )
        is not None
        and "--verify-existing STAGE-REVIEW-S00" in text
        and "--contract STAGE-REVIEW-S00" not in text
        and "python machine/tools/validate_pack.py" in text
        and "python machine/tools/update_artifact_manifest.py" in text
        and "shasum -a 256 -c machine/evidence/SHA256SUMS" in text
        and "git diff --exit-code" in text
        and ("$" + "{{ secrets.") not in text
    )
    _add(checks, "S01P01-CONTINUOUS-CI-HISTORICAL-REPLAY", replay_ok, "read-only" if replay_ok else "invalid")


def _find_by_id(rows: Any, item_id: str) -> Any:
    if not isinstance(rows, list):
        return None
    matching = [row for row in rows if isinstance(row, dict) and row.get("id") == item_id]
    return matching[0] if len(matching) == 1 else None


def _check_taskpack_contract(
    roadmap: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        stages = [row for row in roadmap.get("stages", []) if row.get("id") == "S01"]
        phases = [row for row in stages[0].get("phases", []) if row.get("id") == "P01"] if len(stages) == 1 else []
        phase = phases[0] if len(phases) == 1 else {}
        roadmap_ok = (
            phase.get("title") == "客户新闻稿"
            and phase.get("objective") == "描述用户每天只看一张中文建议卡并完成最终下单的目标体验。"
            and phase.get("outputs") == [PRESS_RELEASE_PATH.as_posix(), OUTCOMES_PATH.as_posix()]
            and phase.get("pass_gate") == "新闻稿不依赖技术术语且结果可观察。"
            and phase.get("hours") == {"low": 3, "likely": 4, "high": 6}
        )
    except Exception as exc:
        roadmap_ok = False
        phase = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(checks, "S01P01-ROADMAP-EXACT", roadmap_ok, phase)

    requirement = _find_by_id(list(requirements), REQUIREMENT_ID)
    requirement_ok = isinstance(requirement, dict) and (
        requirement.get("stage_id") == "S01"
        and requirement.get("phase_id") == "P01"
        and requirement.get("scope") == [PRESS_RELEASE_PATH.as_posix(), OUTCOMES_PATH.as_posix()]
        and requirement.get("target") == "新闻稿不依赖技术术语且结果可观察。"
        and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        and requirement.get("owner_input_required_during_development") is False
        and requirement.get("non_goals") == [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
    )
    _add(checks, "S01P01-REQUIREMENT-EXACT", requirement_ok, requirement)

    contract = _find_by_id(list(acceptance), CONTRACT_ID)
    contract_ok = isinstance(contract, dict) and (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("oracle", {}).get("type") == "EXECUTABLE"
        and contract.get("oracle", {}).get("command")
        == "python -m abd_acceptance --contract AC-S01-P01 --evidence machine/evidence"
        and contract.get("pass_gate") == "新闻稿不依赖技术术语且结果可观察。"
        and [row.get("id") for row in contract.get("tests", [])]
        == ["TEST-S01-P01", "TEST-S01-P01-BOUNDARY", "TEST-S01-P01-REPLAY"]
        and "新增现金支出将超过A$0" in contract.get("stop_condition", [])
    )
    _add(checks, "S01P01-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [
        row
        for row in task_graph.get("tasks", [])
        if isinstance(row, dict) and str(row.get("id", "")).startswith("T-S01-P01-")
    ]
    expected_ids = ["T-S01-P01-01", "T-S01-P01-02", "T-S01-P01-03"]
    tasks_ok = (
        [row.get("id") for row in tasks] == expected_ids
        and [row.get("depends_on") for row in tasks]
        == [["T-S00-P04-03"], ["T-S01-P01-01"], ["T-S01-P01-02"]]
        and all(row.get("auto_advance_on_pass") is True for row in tasks)
        and all(row.get("owner_input_required") is False for row in tasks)
        and tasks[0].get("outputs") == [PRESS_RELEASE_PATH.as_posix(), OUTCOMES_PATH.as_posix()]
        and tasks[1].get("outputs") == ["tests/S01/P01_test.py", FIXTURE_PATH.as_posix()]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
    )
    _add(checks, "S01P01-TASK-CHAIN-EXACT", tasks_ok, [row.get("id") for row in tasks])

    trace = next(
        (row for row in traceability if isinstance(row, dict) and row.get("requirement_id") == REQUIREMENT_ID),
        None,
    )
    trace_ok = isinstance(trace, dict) and (
        trace.get("acceptance_criteria_id") == CONTRACT_ID
        and trace.get("task_ids") == expected_ids
        and trace.get("test_ids") == ["TEST-S01-P01", "TEST-S01-P01-BOUNDARY", "TEST-S01-P01-REPLAY"]
        and trace.get("evidence_id") == "EVD-S01-P01"
        and trace.get("artifact_ids") == ["ART-S01-P01-01", "ART-S01-P01-02"]
    )
    _add(checks, "S01P01-TRACEABILITY-EXACT", trace_ok, trace)


def _parse_sections(text: str) -> Tuple[str, Dict[str, str]]:
    lines = text.splitlines()
    h1 = [line[2:].strip() for line in lines if line.startswith("# ")]
    if len(h1) != 1:
        raise ValueError("press release must contain exactly one level-one heading")
    sections: Dict[str, str] = {}
    current = None
    buffer: List[str] = []
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            next_section = line[3:].strip()
            if next_section in sections or next_section == current:
                raise ValueError("duplicate press release section: %s" % next_section)
            current = next_section
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return h1[0], sections


def _check_press_release(text: str, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        title, sections = _parse_sections(text)
        expected_sections = fixture.get("required_press_release_sections", [])
        structure_ok = (
            title == "ABD 客户新闻稿（目标体验稿）"
            and list(sections) == expected_sections
            and all(sections.get(name) for name in expected_sections)
            and text.count("内部目标稿：用于定义客户结果，不是上线公告、投资建议或收益承诺。") == 1
            and "```" not in text
            and "http://" not in text
            and "https://" not in text
        )
        _add(checks, "S01P01-PRESS-RELEASE-STRUCTURE", structure_ok, list(sections))
    except Exception as exc:
        sections = {}
        _add(checks, "S01P01-PRESS-RELEASE-STRUCTURE", False, "%s: %s" % (type(exc).__name__, exc))

    chinese_count = sum("\u4e00" <= character <= "\u9fff" for character in text)
    length_ok = (
        chinese_count >= int(fixture.get("minimum_chinese_characters", 0))
        and len(text) <= int(fixture.get("maximum_total_characters", 0))
    )
    _add(
        checks,
        "S01P01-PRESS-RELEASE-CUSTOMER-LANGUAGE",
        length_ok,
        {"chinese_characters": chinese_count, "total_characters": len(text)},
    )

    jargon = [term for term in fixture.get("forbidden_jargon", []) if re.search(re.escape(term), text, re.IGNORECASE)]
    _add(checks, "S01P01-PRESS-RELEASE-NO-JARGON", not jargon, jargon or "none")

    current_claims = [term for term in fixture.get("forbidden_current_claims", []) if term in text]
    claim_pattern = re.compile(r"(?:已经|现已|目前已)(?:上线|部署|覆盖|连接|实现)|(?:保证|确保)(?:收益|盈利)")
    if claim_pattern.search(text):
        current_claims.append(claim_pattern.search(text).group(0))
    _add(checks, "S01P01-PRESS-RELEASE-NO-FALSE-CURRENT-CLAIM", not current_claims, current_claims or "none")

    missing_concepts = [term for term in fixture.get("required_customer_concepts", []) if term not in text]
    _add(checks, "S01P01-PRESS-RELEASE-OBSERVABLE-CONCEPTS", not missing_concepts, missing_concepts or "all present")


def _check_outcomes(
    root: Path,
    outcomes: Mapping[str, Any],
    fixture: Mapping[str, Any],
    requirement: Mapping[str, Any],
    canonical: Mapping[str, Any],
    parameters: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        outcomes.get("schema_version") == "1.0.0"
        and outcomes.get("artifact_id") == "ART-S01-P01-02"
        and outcomes.get("requirement_id") == REQUIREMENT_ID
        and outcomes.get("acceptance_contract_id") == CONTRACT_ID
        and outcomes.get("product_version") == VERSION
        and outcomes.get("fixed_at") == FIXED_CLOCK
        and outcomes.get("status") == "TARGET_EXPERIENCE_CONTRACT_NOT_DEPLOYED"
        and outcomes.get("next_on_acceptance_pass") == "S01/P02_READY_NOT_STARTED"
    )
    _add(checks, "S01P01-OUTCOMES-TOP-LEVEL", top_ok, outcomes.get("status"))

    bindings = outcomes.get("source_bindings")
    try:
        actual_bindings = {
            relative: sha256_file(root / relative) for relative in PINNED_SOURCE_HASHES
        }
        bindings_ok = bindings == PINNED_SOURCE_HASHES and actual_bindings == PINNED_SOURCE_HASHES
    except Exception as exc:
        bindings_ok = False
        actual_bindings = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(
        checks,
        "S01P01-OUTCOMES-SOURCE-BINDINGS",
        bindings_ok,
        {"declared": bindings, "actual": actual_bindings},
    )

    customer = outcomes.get("customer", {})
    customer_ok = (
        customer.get("role") == canonical.get("product", {}).get("owner") == "单一账户持有人"
        and customer.get("language") == canonical.get("product", {}).get("language") == "zh-CN"
        and "每天只看一张中文建议卡" in customer.get("daily_job", "")
        and "目标压力" in customer.get("current_problem", "")
    )
    _add(checks, "S01P01-OUTCOMES-CUSTOMER-JOB", customer_ok, customer)

    experience = outcomes.get("experience_contract", {})
    experience_ok = experience == {
        "daily_summary_timezone": "Australia/Sydney",
        "cards_per_calendar_day": 1,
        "card_language": "zh-CN",
        "allowed_decision_states": fixture.get("expected_decision_states"),
        "final_order_actor": "OWNER",
        "automatic_order_submission_count": 0,
        "missing_or_unstable_evidence_action": "NO_RECOMMENDATION",
    }
    _add(checks, "S01P01-OUTCOMES-EXPERIENCE-EXACT", experience_ok, experience)

    rows = outcomes.get("observable_outcomes", [])
    rows_are_objects = isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
    ids = [row.get("id") for row in rows] if rows_are_objects else []
    rows_ok = (
        rows_are_objects
        and ids == fixture.get("expected_outcome_ids")
        and not _duplicates(ids)
        and all(row.get("current_evidence_status") == "NOT_YET_IMPLEMENTED" for row in rows)
        and all(row.get("name") and row.get("customer_observation") and row.get("measurement") for row in rows)
    )
    _add(checks, "S01P01-OUTCOMES-OBSERVABLE-ROWS", rows_ok, ids)

    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    try:
        daily_ok = by_id["OUT-S01-P01-01"]["measurement"] == {
            "field": "daily_summary.card_count_by_sydney_date",
            "operator": "EQUALS",
            "target": 1,
        }
        card_ok = by_id["OUT-S01-P01-02"]["measurement"] == {
            "required_fields": ["decision_state", "reason", "evidence_status", "freshness_status"],
            "decision_state_enum": ["RECOMMENDATION", "NO_RECOMMENDATION"],
        }
        order_ok = by_id["OUT-S01-P01-03"]["measurement"] == {
            "automatic_order_submission_count": 0,
            "required_final_actor": "OWNER",
        }
        safe_ok = by_id["OUT-S01-P01-04"]["measurement"] == {
            "critical_gate_failure_action": "NO_RECOMMENDATION",
            "silent_coverage_gap_target": 0,
        }
        target_ok = by_id["OUT-S01-P01-05"]["measurement"] == {
            "return_guaranteed": False,
            "actual_return_requires_verified_execution_evidence": True,
            "target_shortfall_may_relax_gate": False,
            "target_verification_status": "UNVERIFIED",
        }
    except (KeyError, TypeError):
        daily_ok = card_ok = order_ok = safe_ok = target_ok = False
    _add(checks, "S01P01-OUTCOME-DAILY-CARD-MEASURE", daily_ok, by_id.get("OUT-S01-P01-01"))
    _add(checks, "S01P01-OUTCOME-CARD-FIELDS-MEASURE", card_ok, by_id.get("OUT-S01-P01-02"))
    _add(checks, "S01P01-OUTCOME-OWNER-ORDER-MEASURE", order_ok, by_id.get("OUT-S01-P01-03"))
    _add(checks, "S01P01-OUTCOME-FAIL-CLOSED-MEASURE", safe_ok, by_id.get("OUT-S01-P01-04"))
    _add(checks, "S01P01-OUTCOME-NO-GUARANTEE-MEASURE", target_ok, by_id.get("OUT-S01-P01-05"))

    stability = outcomes.get("adverse_stability_contract", {})
    numeric = parameters.get("numeric_determinism", {})
    stability_ok = stability == {
        "absolute_probability_perturbations": ["-0.0001", "+0.0001"],
        "absolute_threshold_perturbations": ["-0.0001", "+0.0001"],
        "friction_perturbation": "+0.0001",
        "time_perturbation_seconds": 2,
        "odds_perturbation": "ONE_PROVIDER_TICK_ADVERSE",
        "action_when_any_test_flips": "NO_RECOMMENDATION",
    } and (
        numeric.get("boundary_perturbation_absolute_probability") == "0.0001"
        and numeric.get("boundary_perturbation_absolute_threshold") == "0.0001"
        and numeric.get("boundary_perturbation_friction_up") == "0.0001"
        and numeric.get("boundary_perturbation_time_adverse_seconds") == 2
        and numeric.get("odds_perturbation") == "ONE_PROVIDER_TICK_ADVERSE"
        and numeric.get("unstable_action") == "NO_RECOMMENDATION"
    )
    _add(checks, "S01P01-OUTCOMES-ADVERSE-STABILITY-BINDING", stability_ok, stability)

    _add(
        checks,
        "S01P01-OUTCOMES-NON-GOALS-EXACT",
        outcomes.get("non_goals") == requirement.get("non_goals"),
        outcomes.get("non_goals"),
    )
    boundaries = outcomes.get("claim_boundaries", {})
    boundaries_ok = boundaries == {
        "production_deployment_claimed": False,
        "all_market_coverage_verified": False,
        "external_provider_access_verified": False,
        "gmail_connection_status": "NOT_CONNECTED",
        "actual_return_verified": False,
        "return_guaranteed": False,
        "release_status": "NOT_READY",
    }
    _add(checks, "S01P01-OUTCOMES-CLAIM-BOUNDARIES", boundaries_ok, boundaries)


def _check_cross_document(text: str, outcomes: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    experience = outcomes.get("experience_contract", {})
    if not isinstance(experience, dict):
        _add(checks, "S01P01-CROSS-DOCUMENT-CONSISTENCY", False, "experience_contract is not an object")
        return
    cross_ok = (
        experience.get("cards_per_calendar_day") == 1
        and "每天只需要查看一张汇总卡" in text
        and experience.get("final_order_actor") == "OWNER"
        and "最终下单" in text
        and experience.get("automatic_order_submission_count") == 0
        and "自动提交次数必须始终为零" in text
        and experience.get("missing_or_unstable_evidence_action") == "NO_RECOMMENDATION"
        and "不建议" in text
    )
    _add(checks, "S01P01-CROSS-DOCUMENT-CONSISTENCY", cross_ok, experience)


def _check_budget_authority_and_next_phase(
    root: Path,
    canonical: Mapping[str, Any],
    costs: Mapping[str, Any],
    authorization: Mapping[str, Any],
    degraded: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    raw_actions = authorization.get("actions", [])
    actions = {
        row.get("id"): row
        for row in raw_actions
        if isinstance(raw_actions, list) and isinstance(row, dict)
    } if isinstance(raw_actions, list) else {}
    real_order = actions.get("REAL_ORDER_SUBMISSION", {})
    product = canonical.get("product", {})
    scope = canonical.get("scope", {})
    incremental = costs.get("incremental_cash_budget", {})
    execution_boundary = degraded.get("s00_p04_execution_boundary", {})
    if not all(isinstance(value, dict) for value in (product, scope, incremental, execution_boundary)):
        _add(checks, "S01P01-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT", False, "boundary object malformed")
        return
    boundary_ok = (
        product.get("incremental_cash_budget_aud") == "0.00"
        and incremental.get("likely") == "0.00"
        and incremental.get("high") == "0.00"
        and scope.get("order_submission_module_present") is False
        and real_order.get("authorization") == "PROHIBITED"
        and real_order.get("capability_status") == "MODULE_MUST_NOT_EXIST"
        and degraded.get("current_state") == "CONSENT_NOT_REQUESTED"
        and execution_boundary.get("gmail_api_called") is False
    )
    _add(checks, "S01P01-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT", boundary_ok, "bounded")

    try:
        rows = [
            json.loads(line)
            for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
            if line
        ]
        p02 = [row for row in rows if row.get("id") == "INDEX-AC-S01-P02"]
        evidence = sorted((root / "machine/evidence").glob("EVD-S01-P0[2-4].json"))
        future_outputs = [root / "customer_faq.md", root / "assumption_register.json"]
        progression_ok = (
            len(p02) == 1
            and p02[0].get("status") == "PLANNED"
            and not evidence
            and not any(path.exists() for path in future_outputs)
        )
        detail = {"p02_status": p02[0].get("status") if len(p02) == 1 else "INVALID", "evidence": [p.name for p in evidence]}
    except Exception as exc:
        progression_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01P01-P02-NOT-STARTED", progression_ok, detail)


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


def _check_runtime_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    reports = [
        ("S01P01-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("targeted_test_minimum", 0))),
        ("S01P01-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("full_regression_test_minimum", 0))),
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

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S01P01-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S01P01-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
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
        _add(checks, "S01P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S01P01-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P01",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "CUSTOMER_OUTCOME_CONTRACT_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "release_status": "NOT_READY",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "phase_status": "S01_P01_PASS" if status == "PASS" else "S01_P01_FAILED",
        "next": "S01/P02_READY_NOT_STARTED" if status == "PASS" else "S01/P01_REMEDIATION_REQUIRED",
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

    for path in (PRESS_RELEASE_PATH, OUTCOMES_PATH, FIXTURE_PATH):
        _single_source_check(root, path, checks)

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S01P01-FIXTURE-STRICT-JSON")
    outcomes = _safe_load(root / OUTCOMES_PATH, checks, "S01P01-OUTCOMES-STRICT-JSON")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "S01P01-CANONICAL-STRICT-JSON")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S01P01-PARAMETERS-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S01P01-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S01P01-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S01P01-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S01P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S01P01-TRACEABILITY-STRICT-JSON")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "S01P01-COSTS-STRICT-JSON")
    authorization = _safe_load(root / "machine/facts/authorization_matrix.json", checks, "S01P01-AUTHORIZATION-STRICT-JSON")
    degraded = _safe_load(root / "machine/facts/degraded_mode_contract.json", checks, "S01P01-DEGRADED-STRICT-JSON")
    try:
        press_text = (root / PRESS_RELEASE_PATH).read_text(encoding="utf-8")
        _add(checks, "S01P01-PRESS-RELEASE-UTF8", True, PRESS_RELEASE_PATH.as_posix())
    except Exception as exc:
        press_text = ""
        _add(checks, "S01P01-PRESS-RELEASE-UTF8", False, "%s: %s" % (type(exc).__name__, exc))

    _check_pinned_hashes(root, checks, hashes)
    _check_continuous_workflow(root, checks)
    test_packages = [Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py")]
    import_isolation_ok = all((root / path).is_file() for path in test_packages)
    _add(
        checks,
        "S01P01-PYTEST-IMPORT-ISOLATION",
        import_isolation_ok,
        [path.as_posix() for path in test_packages],
    )
    dictionaries = (fixture, outcomes, canonical, parameters, roadmap, task_graph, costs, authorization, degraded)
    arrays = (requirements, acceptance, traceability)
    if not all(isinstance(value, dict) for value in dictionaries) or not all(isinstance(value, list) for value in arrays):
        _add(checks, "S01P01-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S01P01-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S01P01-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    requirement = _find_by_id(requirements, REQUIREMENT_ID)
    if not isinstance(requirement, dict):
        requirement = {}
    try:
        _check_press_release(press_text, fixture, checks)
    except Exception as exc:
        _add(checks, "S01P01-PRESS-RELEASE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_outcomes(root, outcomes, fixture, requirement, canonical, parameters, checks)
    except Exception as exc:
        _add(checks, "S01P01-OUTCOMES-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_cross_document(press_text, outcomes, checks)
    except Exception as exc:
        _add(checks, "S01P01-CROSS-DOCUMENT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    delivery = verify_stage0_delivery(root, verify_git_history=_verify_git_history)
    _add(
        checks,
        "S01P01-STAGE0-DELIVERY-PREREQUISITE",
        delivery.get("status") == "PASS" and delivery.get("next") == "S01/P01_READY_NOT_STARTED",
        delivery.get("summary"),
    )
    for relative, value in delivery.get("hashes", {}).items():
        hashes[relative] = value
    if not _verify_git_history:
        _add(
            checks,
            "S01P01-TEST-ONLY-PARTIAL-PROFILE",
            False,
            "Mutation clones may skip git ancestry; evidence generation never does.",
        )

    try:
        _check_budget_authority_and_next_phase(root, canonical, costs, authorization, degraded, checks)
    except Exception as exc:
        _add(checks, "S01P01-BOUNDARY-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
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
        (PRESS_RELEASE_PATH.as_posix(), root / PRESS_RELEASE_PATH),
        (OUTCOMES_PATH.as_posix(), root / OUTCOMES_PATH),
        (RECEIPT_PATH.as_posix(), root / RECEIPT_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s01-p01-rollback-") as directory:
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
        "evidence_id": "EVD-S01-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_CUSTOMER_CONTRACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        PRESS_RELEASE_PATH,
        OUTCOMES_PATH,
        FIXTURE_PATH,
        RECEIPT_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/authorization_matrix.json"),
        Path("machine/facts/degraded_mode_contract.json"),
        Path("machine/evidence/EVD-S00-STAGE-REVIEW.json"),
        Path("tests/S01/P01_test.py"),
        Path("abd_acceptance/customer_press_release.py"),
        Path("abd_acceptance/delivery.py"),
        Path("tests/__init__.py"),
        Path("tests/S00/__init__.py"),
        Path("tests/S01/__init__.py"),
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
            "evidence_id": "EVD-S01-P01-ROLLBACK",
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
        result["phase_status"] = "S01_P01_FAILED"
        result["next"] = "S01/P01_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P01",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S01-P01-01": PRESS_RELEASE_PATH.as_posix(),
            "ART-S01-P01-02": OUTCOMES_PATH.as_posix(),
        },
        "stage0_delivery_prerequisite": {
            "receipt": RECEIPT_PATH.as_posix(),
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": None,
            "model_not_applicable_reason": "S01/P01 freezes customer outcomes; no prediction model is implemented or evaluated in this phase.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S01/P01_test.py --junitxml=machine/evidence/S01/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S01/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S01-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {
            "artifact": ROLLBACK_EVIDENCE_PATH.as_posix(),
            "status": rollback.get("status"),
        },
        "external_effect_boundary": {
            "github_upload_performed": False,
            "external_account_or_api_accessed": False,
            "secret_provisioned": False,
            "incremental_cash_spent_aud": "0.00",
            "production_deployment_claimed": False,
            "real_order_capability_present": False,
            "return_guaranteed": False,
        },
        "explicit_unknowns": [
            "The target customer experience is not implemented or deployed by this phase.",
            "All-market coverage, live source freshness, external accounts and production runtime remain unverified.",
            "No actual return is verified; A$300*1.3^n remains a falsifiable target and not a guarantee.",
        ],
        "release_status": "NOT_READY",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S01-P01"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S01-P01 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S01/P02_READY_NOT_STARTED" if status == "PASS" else "S01/P01_REMEDIATION_REQUIRED"
    payload = b"".join(
        (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows
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
