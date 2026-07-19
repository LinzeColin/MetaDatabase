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
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.parse import urlsplit

from .canonical_facts import sha256_file, strict_json_load
from .official_platform_research import verify_existing_phase_evidence as verify_s02_p01_evidence


CONTRACT_ID = "AC-S02-P02"
REQUIREMENT_ID = "REQ-S02-P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

MATRIX_PATH = Path("research_evidence_matrix.json")
CLAIMS_PATH = Path("model_claims.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S02_P02.json")
TEST_PATH = Path("tests/S02/P02_test.py")
JUNIT_PATH = Path("machine/evidence/S02/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S02/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P02_rollback.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S02-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")
PHASE_COMMIT = "07304376c661ef178f8fa433e4bd58ed50e7c40b"
PINNED_PHASE_CODE_HASH = "8b98772df0378f239c114ddbd5b1eff43b77386aae20006d1d1470b109ad834e"

SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "abd_acceptance/official_platform_research.py",
    "abd_acceptance/model_risk_research.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S02/P01_test.py",
    "tests/S02/P02_test.py",
}
SUCCESSOR_EVOLVED_TEST_HASHES = {
    "tests/S02/P01_test.py": "bc800d7bd6ac82ba5bf8b709013a0e16287750b635d838f6cd4ac885c7364377",
    "tests/S02/P02_test.py": "dcafa1f4120415cf0d191f69654c58392bece7dcfb86e8e698d436ae1f2f68bd",
}

P01_EVIDENCE_SHA256 = "9b9dc18e33a04847135e021ecfb53dcf9aefde94fb503ec59f114b4b4871eaec"
P01_ROLLBACK_SHA256 = "538b25f45a99e1c550914a8c5cb4e338339f9a6a6874a32af2ae330323e0652d"

PINNED_PHASE_HASHES = {
    MATRIX_PATH.as_posix(): "5a5dc1a9bbbde177f065f4725df5e7f86f763a43a2530671b2b946135c8f2709",
    CLAIMS_PATH.as_posix(): "66bb20b471a218008b29df81cac77b03c55557b9d07f26b6ef37d0cea7eccd4c",
    FIXTURE_PATH.as_posix(): "19a52e8941aafc3c4808e471af0f7a183d1315283e08e496b3fa8e807bc302b4",
    TEST_PATH.as_posix(): "df4492150ed681839ea2fd1eaae7add1f42b51e5df6fd71b1160bae8027a6492",
}

PINNED_BASELINE_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/strategy_spec.json": "d77f047219632145a71f0f2932149654ae24205bbdc291fa604b93bfcff5117d",
    "machine/facts/sources.json": "387df5c4cf54fcad59072c46ee7bbcd67f13e66adf2f5ccf9b115b71182784d8",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    P01_EVIDENCE_PATH.as_posix(): P01_EVIDENCE_SHA256,
    P01_ROLLBACK_PATH.as_posix(): P01_ROLLBACK_SHA256,
}

PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

ALLOWED_PUBLICATION_STATUSES = {
    "PEER_REVIEWED_JOURNAL",
    "PEER_REVIEWED_PROCEEDINGS",
    "PREPRINT_NOT_PEER_REVIEWED",
    "PEER_REVIEWED_JOURNAL_WITH_AUTHOR_PREPRINT",
    "PEER_REVIEWED_JOURNAL_WITH_AUTHOR_MANUSCRIPT",
}

ALLOWED_USE_DECISIONS = {
    "ADOPT_DESIGN_EVIDENCE",
    "ADAPT_WITH_DOMAIN_LIMITATIONS",
    "ADAPT_RESEARCH_ONLY",
}

LOCAL_THRESHOLD_CLASS = "LOCAL_ENGINEERING_THRESHOLD_NOT_PAPER_DERIVED"


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
    seen = set()
    result = []
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


def _row(rows: Sequence[Mapping[str, Any]], item_id: str) -> Mapping[str, Any]:
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == item_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s row, found %d" % (item_id, len(matches)))
    return matches[0]


def _json_pointer_get(value: Mapping[str, Any], pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/") or "~" in pointer:
        raise ValueError("unsupported JSON pointer: %r" % pointer)
    current: Any = value
    for part in pointer[1:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(pointer)
        current = current[part]
    return current


def resolve_claim_admission(
    evidence_classification: Any,
    citation_relation: Any,
    source_level: Any,
    has_runtime_proof: Any,
) -> str:
    allowed_levels = {
        "L1_PEER_REVIEWED_PRIMARY_PUBLISHER",
        "L1_OFFICIAL_PROCEEDINGS_PRIMARY",
        "L1_AUTHOR_MANUSCRIPT_PEER_REVIEWED",
        "L2_AUTHOR_PREPRINT_PRIMARY",
    }
    if source_level not in allowed_levels:
        return "REJECT_UNSUPPORTED_SOURCE_LEVEL"
    if has_runtime_proof is not False:
        return "REJECT_FALSE_RUNTIME_PROOF"
    if evidence_classification == LOCAL_THRESHOLD_CLASS:
        if citation_relation != "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE":
            return "REJECT_THRESHOLD_OVERCLAIM"
        return "ADMIT_LOCAL_THRESHOLD_UNVALIDATED"
    if evidence_classification not in {
        "SUPPORTED_DESIGN_DIRECTION",
        "SUPPORTED_WITH_DOMAIN_LIMITATIONS",
        "RESEARCH_ONLY_NOT_RUNTIME_PROOF",
    }:
        return "REJECT_UNKNOWN_EVIDENCE_CLASSIFICATION"
    if citation_relation not in {"DIRECT_PAPER_FINDING", "ABD_DESIGN_INFERENCE", "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE"}:
        return "REJECT_UNKNOWN_CITATION_RELATION"
    if source_level == "L2_AUTHOR_PREPRINT_PRIMARY":
        return "ADMIT_PREPRINT_WITH_LIMITATIONS"
    return "ADMIT_RESEARCH_ONLY"


def resolve_stability_contract(
    probability_perturbation: Any,
    threshold_perturbation: Any,
    friction_perturbation: Any,
    odds_perturbation: Any,
    action_if_flip: Any,
) -> str:
    raw_values = [probability_perturbation, threshold_perturbation, friction_perturbation]
    if not all(isinstance(value, str) and value.strip() == value and value for value in raw_values):
        return "REJECT_INVALID_STABILITY_INPUT"
    try:
        values = [Decimal(value) for value in raw_values]
    except InvalidOperation:
        return "REJECT_INVALID_STABILITY_INPUT"
    if not all(value.is_finite() and value >= Decimal("0") for value in values):
        return "REJECT_INVALID_STABILITY_INPUT"
    if action_if_flip != "NO_RECOMMENDATION":
        return "REJECT_UNSAFE_FLIP_ACTION"
    if odds_perturbation != "ONE_PROVIDER_TICK_ADVERSE":
        return "REJECT_MISSING_ADVERSE_ODDS_TICK"
    if any(value == Decimal("0") for value in values):
        return "REJECT_INCOMPLETE_STABILITY_CONTRACT"
    if all(value == Decimal("0.0001") for value in values):
        return "LOCAL_THRESHOLD_RESEARCH_ONLY"
    return "REJECT_UNFROZEN_STABILITY_THRESHOLD"


def _check_pinned_hashes(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    verify_git_history: bool,
) -> None:
    for relative, expected in {**PINNED_PHASE_HASHES, **PINNED_BASELINE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S02P02-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        historical = actual != expected and _historical_file_matches(root, relative, expected, verify_git_history)
        _add(
            checks,
            check_id,
            actual == expected or historical,
            {"expected": expected, "actual": actual, "historical_phase_commit": historical},
        )
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S02P02-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack_contract(
    roadmap: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    stages = [row for row in roadmap.get("stages", []) if isinstance(row, dict) and row.get("id") == "S02"]
    stage = stages[0] if len(stages) == 1 else {}
    phases = [row for row in stage.get("phases", []) if isinstance(row, dict) and row.get("id") == "P02"]
    expected_phase = {
        "id": "P02",
        "title": "模型与风险论文调研",
        "objective": "固化市场先验、校准、不建议区域、异常值和受限凯利证据。",
        "outputs": ["research_evidence_matrix.json", "model_claims.json"],
        "pass_gate": "每个模型设计主张可回溯论文。",
        "hours": {"low": 3, "likely": 4, "high": 6},
    }
    _add(
        checks,
        "S02P02-ROADMAP-EXACT",
        len(stages) == 1
        and stage.get("title") == "公开网络与 GitHub 调研复用"
        and len(phases) == 1
        and phases[0] == expected_phase,
        phases[0] if len(phases) == 1 else phases,
    )

    requirement = _row(requirements, REQUIREMENT_ID)
    expected_requirement = {
        "id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P02",
        "title": "模型与风险论文调研",
        "problem": "若未完成“模型与风险论文调研”，只研究与ABD直接相关的官方文档、论文和开源项目，明确采用、适配、拒绝和许可证。将缺少可执行、可验收或可恢复的基础。",
        "user": "单一账户持有人及自动开发/运维代理",
        "value": "固化市场先验、校准、不建议区域、异常值和受限凯利证据。",
        "scope": ["research_evidence_matrix.json", "model_claims.json"],
        "non_goals": [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ],
        "baseline": "未实现或旧包存在冲突/缺口",
        "target": "每个模型设计主张可回溯论文。",
        "measurement": "由 AC-S02-P02 的机器验收判定器执行固定输入、阈值和证据检查。",
        "observation_period": "开发期每次提交；上线后持续",
        "primary_acceptance_criteria_id": CONTRACT_ID,
        "priority": "P1",
        "owner_input_required_during_development": False,
    }
    _add(checks, "S02P02-REQUIREMENT-EXACT", requirement == expected_requirement, requirement)

    contract = _row(acceptance, CONTRACT_ID)
    contract_ok = (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("title") == "模型与风险论文调研唯一主验收"
        and contract.get("oracle")
        == {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S02-P02 --evidence machine/evidence",
            "rule": "每个模型设计主张可回溯论文。",
        }
        and contract.get("threshold") == "每个模型设计主张可回溯论文。"
        and contract.get("pass_gate") == "每个模型设计主张可回溯论文。"
        and contract.get("evidence_requirements", [None])[0] == EVIDENCE_PATH.as_posix()
        and [row.get("id") for row in contract.get("tests", [])]
        == ["TEST-S02-P02", "TEST-S02-P02-BOUNDARY", "TEST-S02-P02-REPLAY"]
        and "固定时钟" in contract.get("environment", [])
        and "无外部网络的确定性测试模式" in contract.get("environment", [])
    )
    _add(checks, "S02P02-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [_row(task_graph.get("tasks", []), "T-S02-P02-%02d" % index) for index in range(1, 4)]
    task_ok = (
        tasks[0].get("depends_on") == ["T-S02-P01-03"]
        and tasks[0].get("outputs") == [MATRIX_PATH.as_posix(), CLAIMS_PATH.as_posix()]
        and tasks[1].get("depends_on") == ["T-S02-P02-01"]
        and tasks[1].get("outputs") == ["tests/S02/P02_test.py", FIXTURE_PATH.as_posix()]
        and tasks[2].get("depends_on") == ["T-S02-P02-02"]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
        and all(row.get("stage_id") == "S02" and row.get("phase_id") == "P02" for row in tasks)
        and all(row.get("requirement_ids") == [REQUIREMENT_ID] for row in tasks)
        and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks)
        and all(row.get("oracle", {}).get("mode") == "DETERMINISTIC_FAIL_CLOSED" for row in tasks)
        and all(row.get("pass_gate") == "每个模型设计主张可回溯论文。" for row in tasks)
        and all(row.get("owner_input_required") is False and row.get("auto_advance_on_pass") is True for row in tasks)
    )
    _add(checks, "S02P02-TASK-CHAIN-EXACT", task_ok, [row.get("id") for row in tasks])

    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    expected_trace = {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S02-P02-01", "T-S02-P02-02", "T-S02-P02-03"],
        "test_ids": ["TEST-S02-P02", "TEST-S02-P02-BOUNDARY", "TEST-S02-P02-REPLAY"],
        "evidence_id": "EVD-S02-P02",
        "artifact_ids": ["ART-S02-P02-01", "ART-S02-P02-02"],
        "stage_id": "S02",
        "phase_id": "P02",
    }
    _add(checks, "S02P02-TRACEABILITY-EXACT", len(trace) == 1 and trace[0] == expected_trace, trace)


def _check_matrix(matrix: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    expected_ids = fixture.get("expected_paper_ids", [])
    papers = [row for row in matrix.get("papers", []) if isinstance(row, dict)]
    paper_ids = [row.get("id") for row in papers]
    top_ok = (
        matrix.get("schema_version") == "1.0.0"
        and matrix.get("version") == VERSION
        and matrix.get("stage_id") == "S02"
        and matrix.get("phase_id") == "P02"
        and matrix.get("as_of") == fixture.get("as_of")
        and matrix.get("status") == "FROZEN_RESEARCH_BASELINE"
        and matrix.get("next_on_acceptance_pass") == "S02/P03_READY_NOT_STARTED"
    )
    _add(checks, "S02P02-MATRIX-TOP-LEVEL", top_ok, matrix.get("status"))
    _add(
        checks,
        "S02P02-PAPER-IDS-EXACT-UNIQUE",
        paper_ids == expected_ids and not _duplicates(paper_ids),
        {"actual": paper_ids, "duplicates": _duplicates(paper_ids)},
    )
    _add(checks, "S02P02-PAPER-COUNT-EXACT", len(papers) == 8, len(papers))
    _add(
        checks,
        "S02P02-PAPER-TITLES-UNIQUE",
        not _duplicates([row.get("title") for row in papers]),
        _duplicates([row.get("title") for row in papers]) or "all unique",
    )

    mode = matrix.get("research_mode", {})
    mode_ok = (
        mode.get("method") == "READ_ONLY_PUBLIC_PRIMARY_SOURCE_REVIEW"
        and mode.get("primary_sources_only") is True
        and mode.get("network_retrieval_performed") is True
        and mode.get("account_login_performed") is False
        and mode.get("paid_source_or_api_used") is False
        and mode.get("paper_body_or_dataset_copied_into_repository") is False
        and mode.get("prediction_model_executed") is False
        and mode.get("training_or_backtest_performed") is False
        and mode.get("provider_or_cloud_account_accessed") is False
        and mode.get("real_order_submitted") is False
        and mode.get("github_upload_performed") is False
        and mode.get("production_deployment_performed") is False
        and mode.get("exhaustive_literature_review_claimed") is False
        and mode.get("legal_or_financial_advice_provided") is False
        and mode.get("s02_p03_started") is False
    )
    _add(checks, "S02P02-READ-ONLY-RESEARCH-BOUNDARY", mode_ok, mode)

    source_definitions = matrix.get("source_level_definitions", {})
    allowed_levels = fixture.get("allowed_source_levels", [])
    _add(
        checks,
        "S02P02-SOURCE-LEVEL-DEFINITIONS-EXACT",
        list(source_definitions) == allowed_levels
        and all(isinstance(source_definitions.get(level), str) and source_definitions[level] for level in allowed_levels),
        list(source_definitions),
    )
    _add(
        checks,
        "S02P02-CATEGORIES-EXACT",
        matrix.get("categories") == fixture.get("required_categories"),
        matrix.get("categories"),
    )

    paper_map = {str(row.get("id")): row for row in papers}
    metadata_errors: List[Any] = []
    identifier_errors: List[Any] = []
    source_errors: List[Any] = []
    category_errors: List[Any] = []
    finding_errors: List[Any] = []
    for paper_id in expected_ids:
        paper = paper_map.get(paper_id, {})
        if not (
            isinstance(paper.get("title"), str)
            and paper.get("title")
            and isinstance(paper.get("authors"), list)
            and paper.get("authors")
            and all(isinstance(author, str) and author for author in paper.get("authors", []))
            and isinstance(paper.get("published_year"), int)
            and 1900 <= paper.get("published_year", 0) <= 2026
            and isinstance(paper.get("venue"), str)
            and paper.get("venue")
            and paper.get("publication_status") in ALLOWED_PUBLICATION_STATUSES
        ):
            metadata_errors.append(paper_id)
        expected_identifiers = fixture.get("expected_identifiers", {}).get(paper_id)
        identifiers = paper.get("identifiers")
        if identifiers != expected_identifiers:
            identifier_errors.append({"paper_id": paper_id, "expected": expected_identifiers, "actual": identifiers})
        else:
            doi = identifiers.get("doi") if isinstance(identifiers, dict) else None
            arxiv = identifiers.get("arxiv") if isinstance(identifiers, dict) else None
            if doi is not None and not re.fullmatch(r"10\.[A-Za-z0-9./()_-]+", doi):
                identifier_errors.append({"paper_id": paper_id, "doi": doi})
            if arxiv is not None and not re.fullmatch(r"\d{4}\.\d{5}", arxiv):
                identifier_errors.append({"paper_id": paper_id, "arxiv": arxiv})
        url = paper.get("primary_url")
        parsed = urlsplit(url) if isinstance(url, str) else None
        source_level = paper.get("source_level")
        publication_status = paper.get("publication_status")
        level_status_ok = (
            (source_level == "L2_AUTHOR_PREPRINT_PRIMARY" and publication_status == "PREPRINT_NOT_PEER_REVIEWED")
            or (source_level == "L1_OFFICIAL_PROCEEDINGS_PRIMARY" and publication_status == "PEER_REVIEWED_PROCEEDINGS")
            or (
                source_level == "L1_AUTHOR_MANUSCRIPT_PEER_REVIEWED"
                and publication_status in {"PEER_REVIEWED_JOURNAL_WITH_AUTHOR_PREPRINT", "PEER_REVIEWED_JOURNAL_WITH_AUTHOR_MANUSCRIPT"}
            )
            or (source_level == "L1_PEER_REVIEWED_PRIMARY_PUBLISHER" and publication_status == "PEER_REVIEWED_JOURNAL")
        )
        if not (
            url == fixture.get("expected_primary_urls", {}).get(paper_id)
            and parsed is not None
            and parsed.scheme == "https"
            and parsed.hostname
            and paper.get("retrieved_on") == fixture.get("as_of")
            and source_level == fixture.get("expected_source_levels", {}).get(paper_id)
            and level_status_ok
        ):
            source_errors.append(paper_id)
        categories = paper.get("categories", [])
        claims = paper.get("claim_ids", [])
        if not (
            isinstance(categories, list)
            and categories
            and set(categories) <= set(fixture.get("required_categories", []))
            and not _duplicates(categories)
            and isinstance(claims, list)
            and claims
            and set(claims) <= set(fixture.get("expected_claim_ids", []))
            and not _duplicates(claims)
        ):
            category_errors.append(paper_id)
        if not (
            isinstance(paper.get("paper_finding"), str)
            and len(paper.get("paper_finding", "")) >= 30
            and isinstance(paper.get("abd_inference"), str)
            and len(paper.get("abd_inference", "")) >= 20
            and isinstance(paper.get("limitations"), list)
            and len(paper.get("limitations", [])) >= 2
            and all(isinstance(item, str) and len(item) >= 10 for item in paper.get("limitations", []))
            and paper.get("use_decision") in ALLOWED_USE_DECISIONS
            and paper.get("threshold_basis_decision") == "REJECT_AS_EXACT_ABD_THRESHOLD_BASIS"
        ):
            finding_errors.append(paper_id)
    _add(checks, "S02P02-PAPER-METADATA-COMPLETE", not metadata_errors, metadata_errors or len(papers))
    _add(checks, "S02P02-PAPER-IDENTIFIERS-EXACT", not identifier_errors, identifier_errors or "all identifiers exact")
    _add(checks, "S02P02-PAPER-URL-DATE-LEVEL-EXACT", not source_errors, source_errors or "all primary sources exact")
    _add(checks, "S02P02-PAPER-CATEGORY-CLAIM-BINDINGS", not category_errors, category_errors or "all bindings complete")
    _add(checks, "S02P02-PAPER-FINDING-INFERENCE-LIMITATIONS", not finding_errors, finding_errors or "all findings bounded")
    _add(
        checks,
        "S02P02-PEER-REVIEW-STATUS-NOT-INFLATED",
        sum(row.get("publication_status") == "PREPRINT_NOT_PEER_REVIEWED" for row in papers) == 1
        and paper_map.get("PAPER-S02-P02-003", {}).get("publication_status") == "PREPRINT_NOT_PEER_REVIEWED",
        {row.get("id"): row.get("publication_status") for row in papers},
    )
    _add(
        checks,
        "S02P02-SOURCE-LEVEL-COVERAGE",
        {row.get("source_level") for row in papers} == set(fixture.get("allowed_source_levels", [])),
        sorted({str(row.get("source_level")) for row in papers}),
    )
    _add(
        checks,
        "S02P02-PRIMARY-DOMAINS-ALLOWLISTED",
        {urlsplit(str(row.get("primary_url"))).hostname for row in papers}
        <= {
            "journals.plos.org",
            "arxiv.org",
            "doi.org",
            "proceedings.mlr.press",
            "onlinelibrary.wiley.com",
            "web.stanford.edu",
        },
        sorted({str(urlsplit(str(row.get("primary_url"))).hostname) for row in papers}),
    )
    _add(
        checks,
        "S02P02-NO-PAPER-USED-AS-EXACT-THRESHOLD-BASIS",
        all(row.get("threshold_basis_decision") == "REJECT_AS_EXACT_ABD_THRESHOLD_BASIS" for row in papers),
        {row.get("id"): row.get("threshold_basis_decision") for row in papers},
    )

    expected_coverage = {
        category: [paper_id for paper_id in expected_ids if category in paper_map.get(paper_id, {}).get("categories", [])]
        for category in fixture.get("required_categories", [])
    }
    _add(
        checks,
        "S02P02-CATEGORY-COVERAGE-CLOSED",
        matrix.get("category_coverage") == expected_coverage and all(expected_coverage.values()),
        matrix.get("category_coverage"),
    )
    boundaries = matrix.get("global_claim_boundaries", [])
    boundary_text = "\n".join(boundaries) if isinstance(boundaries, list) else ""
    boundary_ok = (
        isinstance(boundaries, list)
        and len(boundaries) == 5
        and "不证明 ABD 已训练、已回测、已上线或已产生收益" in boundary_text
        and "不是论文" in boundary_text
        and "全部可观察市场" in boundary_text
        and "A$300×1.3^n" in boundary_text
        and "不是穷尽性综述" in boundary_text
    )
    _add(checks, "S02P02-GLOBAL-CLAIM-BOUNDARIES", boundary_ok, boundaries)

    reconciliation = matrix.get("legacy_baseline_reconciliation", [])
    reconciliation_ok = (
        [row.get("baseline_source_id") for row in reconciliation if isinstance(row, dict)] == ["SRC-020", "SRC-021", "SRC-022"]
        and all(row.get("historical_baseline_mutated") is False for row in reconciliation)
        and "正式标题" in reconciliation[0].get("p02_resolution", "")
        and "L2_AUTHOR_PREPRINT_PRIMARY" in reconciliation[1].get("p02_resolution", "")
        and "1%" in reconciliation[2].get("legacy_issue", "")
        and "本地工程阈值" in reconciliation[2].get("p02_resolution", "")
    )
    _add(checks, "S02P02-LEGACY-BASELINE-RECONCILED-NONMUTATING", reconciliation_ok, reconciliation)
    return paper_map


def _check_claims(
    claims_artifact: Mapping[str, Any],
    matrix: Mapping[str, Any],
    paper_map: Mapping[str, Mapping[str, Any]],
    parameters: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    claims = [row for row in claims_artifact.get("claims", []) if isinstance(row, dict)]
    claim_ids = [row.get("id") for row in claims]
    expected_ids = fixture.get("expected_claim_ids", [])
    top_ok = (
        claims_artifact.get("schema_version") == "1.0.0"
        and claims_artifact.get("version") == VERSION
        and claims_artifact.get("stage_id") == "S02"
        and claims_artifact.get("phase_id") == "P02"
        and claims_artifact.get("as_of") == fixture.get("as_of")
        and claims_artifact.get("status") == "FROZEN_RESEARCH_CLAIMS"
        and claims_artifact.get("next_on_acceptance_pass") == "S02/P03_READY_NOT_STARTED"
    )
    _add(checks, "S02P02-CLAIMS-TOP-LEVEL", top_ok, claims_artifact.get("status"))
    _add(
        checks,
        "S02P02-CLAIM-IDS-EXACT-UNIQUE",
        claim_ids == expected_ids and not _duplicates(claim_ids),
        {"actual": claim_ids, "duplicates": _duplicates(claim_ids)},
    )
    _add(checks, "S02P02-CLAIM-COUNT-EXACT", len(claims) == 14, len(claims))
    expected_classifications = fixture.get("expected_claim_classifications", {})
    _add(
        checks,
        "S02P02-CLAIM-SEMANTICS-DEFINED",
        list(claims_artifact.get("claim_semantics", {}))
        == [
            "SUPPORTED_DESIGN_DIRECTION",
            "SUPPORTED_WITH_DOMAIN_LIMITATIONS",
            LOCAL_THRESHOLD_CLASS,
            "RESEARCH_ONLY_NOT_RUNTIME_PROOF",
        ]
        and list(claims_artifact.get("citation_relation_semantics", {}))
        == ["DIRECT_PAPER_FINDING", "ABD_DESIGN_INFERENCE", "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE"],
        {
            "claim_semantics": list(claims_artifact.get("claim_semantics", {})),
            "citation_semantics": list(claims_artifact.get("citation_relation_semantics", {})),
        },
    )

    field_errors: List[Any] = []
    citation_errors: List[Any] = []
    overclaim_errors: List[Any] = []
    citation_edges = set()
    claim_map = {str(row.get("id")): row for row in claims}
    for claim_id in expected_ids:
        claim = claim_map.get(claim_id, {})
        classification = claim.get("evidence_classification")
        citations = claim.get("citations", [])
        if not (
            claim.get("category") in fixture.get("required_categories", [])
            and isinstance(claim.get("claim"), str)
            and len(claim.get("claim", "")) >= 25
            and classification == expected_classifications.get(claim_id)
            and claim.get("direct_finding_or_inference") == "ABD_DESIGN_INFERENCE"
            and isinstance(claim.get("runtime_status"), str)
            and claim.get("runtime_status")
            and isinstance(claim.get("not_proven"), str)
            and len(claim.get("not_proven", "")) >= 15
            and isinstance(citations, list)
            and citations
        ):
            field_errors.append(claim_id)
        relations = []
        for citation in citations if isinstance(citations, list) else []:
            paper_id = citation.get("paper_id") if isinstance(citation, dict) else None
            paper = paper_map.get(str(paper_id), {})
            relation = citation.get("relation") if isinstance(citation, dict) else None
            relations.append(relation)
            citation_edges.add((paper_id, claim_id))
            if not (
                paper
                and relation in claims_artifact.get("citation_relation_semantics", {})
                and citation.get("primary_url") == paper.get("primary_url")
                and citation.get("retrieved_on") == paper.get("retrieved_on")
                and citation.get("source_level") == paper.get("source_level")
                and claim_id in paper.get("claim_ids", [])
            ):
                citation_errors.append({"claim_id": claim_id, "paper_id": paper_id})
        if classification == LOCAL_THRESHOLD_CLASS and (
            not relations or any(relation != "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE" for relation in relations)
        ):
            overclaim_errors.append(claim_id)
        if classification != LOCAL_THRESHOLD_CLASS and claim_id != "CLM-S02-P02-014" and all(
            relation == "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE" for relation in relations
        ):
            overclaim_errors.append(claim_id)
    _add(checks, "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION", not field_errors, field_errors or len(claims))
    _add(checks, "S02P02-CITATIONS-RESOLVE-EXACTLY", not citation_errors, citation_errors or len(citation_edges))
    _add(checks, "S02P02-LOCAL-THRESHOLDS-NOT-PAPER-OVERCLAIMED", not overclaim_errors, overclaim_errors or "all bounded")
    _add(
        checks,
        "S02P02-EVERY-CLAIM-EXPLICIT-INFERENCE-BOUNDARY",
        all(row.get("direct_finding_or_inference") == "ABD_DESIGN_INFERENCE" for row in claims),
        {row.get("id"): row.get("direct_finding_or_inference") for row in claims},
    )
    _add(
        checks,
        "S02P02-PREPRINT-CLAIM-REMAINS-RESEARCH-ONLY",
        claim_map.get("CLM-S02-P02-003", {}).get("runtime_status")
        == "RESEARCH_ONLY_PREPRINT_REQUIRES_INDEPENDENT_REPLICATION",
        claim_map.get("CLM-S02-P02-003", {}).get("runtime_status"),
    )
    _add(
        checks,
        "S02P02-NO-DUPLICATE-CITATION-PER-CLAIM",
        all(
            not _duplicates([citation.get("paper_id") for citation in row.get("citations", [])])
            for row in claims
        ),
        "all citation lists unique",
    )

    paper_edges = {
        (paper_id, claim_id)
        for paper_id, paper in paper_map.items()
        for claim_id in paper.get("claim_ids", [])
    }
    _add(
        checks,
        "S02P02-PAPER-CLAIM-GRAPH-CLOSED",
        citation_edges == paper_edges,
        {"missing_citations": sorted(paper_edges - citation_edges), "orphan_citations": sorted(citation_edges - paper_edges)},
    )
    _add(
        checks,
        "S02P02-EVERY-PAPER-IS-CITED",
        {paper_id for paper_id, _ in citation_edges} == set(paper_map),
        sorted({str(paper_id) for paper_id, _ in citation_edges}),
    )

    categories_with_claims = {row.get("category") for row in claims}
    _add(
        checks,
        "S02P02-EVERY-CATEGORY-HAS-CLAIM",
        categories_with_claims == set(fixture.get("required_categories", [])),
        sorted(categories_with_claims),
    )

    inventory = claims_artifact.get("local_threshold_inventory", [])
    expected_inventory = fixture.get("expected_local_thresholds", [])
    inventory_errors: List[Any] = []
    pointers = []
    for row in inventory if isinstance(inventory, list) else []:
        pointer = row.get("parameter_pointer") if isinstance(row, dict) else None
        pointers.append(pointer)
        try:
            actual_value = _json_pointer_get(parameters, pointer)
        except Exception as exc:
            inventory_errors.append({"pointer": pointer, "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        claim = claim_map.get(str(row.get("claim_id")), {})
        status_ok = (
            row.get("status") == LOCAL_THRESHOLD_CLASS and claim.get("evidence_classification") == LOCAL_THRESHOLD_CLASS
        ) or (
            row.get("status") == "UNVERIFIED_RESEARCH_TARGET_NOT_PAPER_DERIVED"
            and row.get("claim_id") == "CLM-S02-P02-014"
            and claim.get("evidence_classification") == "RESEARCH_ONLY_NOT_RUNTIME_PROOF"
        )
        if actual_value != row.get("value") or not status_ok:
            inventory_errors.append(
                {"pointer": pointer, "parameter": actual_value, "declared": row.get("value"), "status": row.get("status")}
            )
    inventory_ok = (
        inventory == expected_inventory
        and not _duplicates(pointers)
        and not inventory_errors
        and {row.get("claim_id") for row in inventory}
        == {
            "CLM-S02-P02-002",
            "CLM-S02-P02-005",
            "CLM-S02-P02-008",
            "CLM-S02-P02-010",
            "CLM-S02-P02-013",
            "CLM-S02-P02-014",
        }
    )
    _add(
        checks,
        "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT",
        inventory_ok,
        inventory_errors or {"count": len(inventory), "duplicates": _duplicates(pointers)},
    )

    target_claim = claim_map.get("CLM-S02-P02-014", {})
    target_text = "%s\n%s" % (target_claim.get("claim", ""), target_claim.get("not_proven", ""))
    _add(
        checks,
        "S02P02-TARGET-IS-UNVERIFIED-NON-GUARANTEE",
        target_claim.get("runtime_status") == "UNVERIFIED_NOT_GUARANTEED"
        and "A$300×1.3^n" in target_text
        and "30%" in target_text
        and "不证明" in target_text
        and "不得降低门槛" in target_text,
        target_claim.get("runtime_status"),
    )

    boundary = claims_artifact.get("external_effect_boundary", {})
    expected_boundary = {
        "incremental_cash_spent_aud": "0.00",
        "paid_dependency_added": False,
        "external_account_accessed": False,
        "provider_api_called": False,
        "real_order_capability_present": False,
        "production_deployment_claimed": False,
        "model_or_strategy_executed": False,
        "return_or_roi_verified": False,
        "return_or_guarantee_claimed": False,
        "all_market_coverage_claimed": False,
        "github_upload_performed": False,
        "s02_p03_started": False,
    }
    _add(checks, "S02P02-CLAIMS-NO-EXTERNAL-EFFECT", boundary == expected_boundary, boundary)


def _check_fixture_vectors(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    admission_rows = fixture.get("claim_admission_vectors", [])
    admission_actual = []
    for row in admission_rows:
        actual = resolve_claim_admission(
            row.get("evidence_classification"),
            row.get("citation_relation"),
            row.get("source_level"),
            row.get("has_runtime_proof"),
        )
        admission_actual.append({"id": row.get("id"), "expected": row.get("expected"), "actual": actual})
    _add(
        checks,
        "S02P02-CLAIM-ADMISSION-VECTORS",
        len(admission_rows) == 7 and all(row["actual"] == row["expected"] for row in admission_actual),
        admission_actual,
    )

    stability_rows = fixture.get("stability_boundary_vectors", [])
    stability_actual = []
    for row in stability_rows:
        actual = resolve_stability_contract(
            row.get("probability_perturbation"),
            row.get("threshold_perturbation"),
            row.get("friction_perturbation"),
            row.get("odds_perturbation"),
            row.get("action_if_flip"),
        )
        stability_actual.append({"id": row.get("id"), "expected": row.get("expected"), "actual": actual})
    _add(
        checks,
        "S02P02-STABILITY-BOUNDARY-VECTORS",
        len(stability_rows) == 6 and all(row["actual"] == row["expected"] for row in stability_actual),
        stability_actual,
    )


def _check_baseline_alignment(
    canonical: Mapping[str, Any],
    costs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    model_card: Mapping[str, Any],
    strategy: Mapping[str, Any],
    legacy_sources: Sequence[Mapping[str, Any]],
    matrix: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    product = canonical.get("product", {})
    scope = canonical.get("scope", {})
    truth = canonical.get("truth_and_evidence", {})
    canonical_ok = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("monthly_target_return") == "0.30"
        and product.get("target_curve") == "B_n = 300 * (1.3 ** n)"
        and scope.get("product_role") == "ANALYSIS_AND_ADVICE_ONLY"
        and scope.get("order_submission_module_present") is False
        and scope.get("normal_owner_action") == "FINAL_ORDER_ONLY"
        and truth.get("actual_return_requires_verified_execution_evidence") is True
    )
    _add(checks, "S02P02-CANONICAL-SCOPE-FROZEN", canonical_ok, "A$300, A$0, advice-only, target unverified")

    cash_gate = costs.get("incremental_cash_gate", {})
    costs_ok = (
        costs.get("incremental_cash_budget") == {"low": "0.00", "likely": "0.00", "high": "0.00"}
        and cash_gate.get("maximum_aud") == "0.00"
        and cash_gate.get("automatic_purchase_allowed") is False
        and cash_gate.get("automatic_paid_upgrade_allowed") is False
        and cash_gate.get("automatic_overage_billing_allowed") is False
    )
    _add(checks, "S02P02-ZERO-INCREMENTAL-CASH-FROZEN", costs_ok, cash_gate)

    market = parameters.get("market_model", {})
    calibration = parameters.get("calibration", {})
    numeric = parameters.get("numeric_determinism", {})
    risk = parameters.get("risk", {})
    target = parameters.get("target_30pct", {})
    parameter_ok = (
        market.get("market_prior_weight_min") == "0.50"
        and market.get("conservative_probability_percentile") == 10
        and market.get("edge_haircut_fraction") == "0.25"
        and market.get("remove_top_profit_fraction_for_robustness") == "0.01"
        and calibration.get("slope_min") == "0.90"
        and calibration.get("slope_max") == "1.10"
        and calibration.get("intercept_abs_max") == "0.02"
        and numeric.get("boundary_perturbation_absolute_probability") == "0.0001"
        and numeric.get("boundary_perturbation_absolute_threshold") == "0.0001"
        and numeric.get("odds_perturbation") == "ONE_PROVIDER_TICK_ADVERSE"
        and numeric.get("unstable_action") == "NO_RECOMMENDATION"
        and risk.get("kelly_fraction_alpha") == "0.00"
        and risk.get("kelly_fraction_beta") == "0.20"
        and risk.get("kelly_fraction_ga") == "0.25"
        and risk.get("target_shortfall_may_relax_gate") is False
        and target.get("monthly_return") == "0.30"
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
    )
    _add(checks, "S02P02-LOCAL-PARAMETER-BASELINE-FROZEN", parameter_ok, "all research-only thresholds remain unchanged")

    expected_safety = [
        "市场权重至少50%",
        "保守概率第10百分位",
        "25%优势削减",
        "删除最高盈利1%复测",
        "万分之一和赔率跳动不利扰动",
        "证据层和受限凯利",
        "NO_BET优先",
    ]
    model_ok = (
        model_card.get("intended_use")
        == "分析可观察市场，生成中文BET/NO_BET建议、最低赔率和保守仓位；用户自行完成最终下单。"
        and model_card.get("safety_measures") == expected_safety
        and model_card.get("model_families", {}).get("unmodelled") == "仅市场共识或不建议"
    )
    _add(checks, "S02P02-MODEL-CARD-RESEARCH-SUBJECT-FROZEN", model_ok, model_card.get("safety_measures"))

    formulas = strategy.get("formulas", {})
    strategy_ok = (
        formulas.get("market_residual")
        == "logit(p_final)=logit(p_market)+alpha*(logit(p_domain)-logit(p_domain_reference))"
        and formulas.get("conservative_probability") == "p_L=percentile_10(block_bootstrap(p_final))"
        and formulas.get("full_kelly") == "f_K=(p_L*odds-1)/(odds-1)"
        and formulas.get("monthly_target_log_growth") == "ln(1.3)"
    )
    _add(checks, "S02P02-STRATEGY-FORMULAS-RESEARCH-ONLY", strategy_ok, formulas)

    source_map = {row.get("id"): row for row in legacy_sources if isinstance(row, dict)}
    expected_legacy_urls = {
        "SRC-019": "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0198668",
        "SRC-020": "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0287601",
        "SRC-021": "https://arxiv.org/abs/2303.06021",
        "SRC-022": "https://arxiv.org/abs/2306.01740",
        "SRC-023": "https://arxiv.org/abs/1603.06183",
    }
    reconciliation_ids = [row.get("baseline_source_id") for row in matrix.get("legacy_baseline_reconciliation", [])]
    legacy_ok = (
        {source_id: source_map.get(source_id, {}).get("url") for source_id in expected_legacy_urls} == expected_legacy_urls
        and reconciliation_ids == ["SRC-020", "SRC-021", "SRC-022"]
    )
    _add(checks, "S02P02-LEGACY-SOURCE-URL-CONTINUITY", legacy_ok, expected_legacy_urls)


def _check_p01_prerequisite(root: Path, checks: List[Dict[str, Any]], verify_git_history: bool) -> None:
    try:
        result = verify_s02_p01_evidence(
            root,
            verify_git_history=verify_git_history,
            verify_successor_state=False,
        )
        passed = (
            result.get("status") == "PASS"
            and result.get("decision") == "S02_P01_EVIDENCE_VERIFIED"
            and result.get("evidence_sha256") == P01_EVIDENCE_SHA256
            and result.get("rollback_sha256") == P01_ROLLBACK_SHA256
            and result.get("next") == "S02/P02_READY_NOT_STARTED"
        )
        detail = result.get("summary")
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P02-P01-IMMUTABLE-PREREQUISITE", passed, detail)


def _check_s02_p03_not_started(
    root: Path,
    checks: List[Dict[str, Any]],
    verify_git_history: bool = True,
) -> None:
    try:
        rows = [
            json.loads(line)
            for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
            if line
        ]
        p03 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P03"]
        forbidden_paths = [
            root / "research_reuse_matrix.json",
            root / "license_inventory.json",
            root / "tests/S02/P03_test.py",
            root / "machine/tests/fixtures/S02_P03.json",
            root / "machine/evidence/EVD-S02-P03.json",
            root / "machine/evidence/EVD-S02-P03_rollback.json",
        ]
        existing = [path.relative_to(root).as_posix() for path in forbidden_paths if path.exists()]
        not_started = (
            len(p03) == 1
            and p03[0].get("status") == "PLANNED"
            and "actual_artifact" not in p03[0]
            and not existing
        )
        if not_started:
            passed = True
            detail = {"state": "P03_NOT_STARTED", "index": p03, "forbidden_existing": existing}
        elif (
            len(p03) == 1
            and p03[0].get("status") == "PLANNED"
            and "actual_artifact" not in p03[0]
            and existing
            == [
                "research_reuse_matrix.json",
                "license_inventory.json",
                "tests/S02/P03_test.py",
                "machine/tests/fixtures/S02_P03.json",
            ]
        ):
            try:
                from .open_source_reuse import evaluate_contract as evaluate_p03_candidate

                candidate = evaluate_p03_candidate(
                    root,
                    require_external_reports=False,
                    _verify_git_history=verify_git_history,
                )
                passed = candidate.get("status") == "PASS" and candidate.get("next") == "S02/P04_READY_NOT_STARTED"
                detail = {
                    "state": "P03_IN_PROGRESS_VALIDATED_NOT_ACCEPTED" if passed else "INVALID_P03_CANDIDATE",
                    "candidate_summary": candidate.get("summary"),
                    "index": p03,
                    "existing": existing,
                }
            except Exception as exc:
                passed = False
                detail = {
                    "state": "INVALID_P03_CANDIDATE",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "index": p03,
                    "existing": existing,
                }
        else:
            try:
                from .open_source_reuse import verify_existing_phase_evidence as verify_p03_evidence

                successor = verify_p03_evidence(
                    root,
                    verify_git_history=verify_git_history,
                    verify_p02_prerequisite=False,
                )
                passed = (
                    successor.get("status") == "PASS"
                    and successor.get("decision") == "S02_P03_EVIDENCE_VERIFIED"
                    and successor.get("next") == "S02/P04_READY_NOT_STARTED"
                )
                detail = {
                    "state": "P03_VERIFIED_SUCCESSOR" if passed else "INVALID_OR_PARTIAL_P03_SUCCESSOR",
                    "successor_summary": successor.get("summary"),
                    "index": p03,
                    "existing": existing,
                }
            except Exception as exc:
                passed = False
                detail = {
                    "state": "INVALID_OR_PARTIAL_P03_SUCCESSOR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "index": p03,
                    "existing": existing,
                }
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P02-P03-NOT-STARTED", passed, detail)


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


def _check_runtime_reports(
    root: Path,
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    reports = [
        ("S02P02-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S02P02-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
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

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S02P02-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S02P02-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
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
        _add(checks, "S02P02-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S02P02-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P02",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "MODEL_AND_RISK_RESEARCH_CLAIMS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
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
        "model_status": "RESEARCH_ONLY_NOT_TRAINED_OR_VALIDATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "phase_status": "S02_P02_PASS" if status == "PASS" else "S02_P02_FAILED",
        "next": "S02/P03_READY_NOT_STARTED" if status == "PASS" else "S02/P02_REMEDIATION_REQUIRED",
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

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S02P02-FIXTURE-STRICT-JSON")
    matrix = _safe_load(root / MATRIX_PATH, checks, "S02P02-MATRIX-STRICT-JSON")
    claims = _safe_load(root / CLAIMS_PATH, checks, "S02P02-CLAIMS-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S02P02-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S02P02-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S02P02-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S02P02-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S02P02-TRACEABILITY-STRICT-JSON")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "S02P02-CANONICAL-STRICT-JSON")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "S02P02-COSTS-STRICT-JSON")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S02P02-PARAMETERS-STRICT-JSON")
    model_card = _safe_load(root / "machine/facts/model_system_card.json", checks, "S02P02-MODEL-CARD-STRICT-JSON")
    strategy = _safe_load(root / "machine/facts/strategy_spec.json", checks, "S02P02-STRATEGY-STRICT-JSON")
    legacy_sources = _safe_load(root / "machine/facts/sources.json", checks, "S02P02-LEGACY-SOURCES-STRICT-JSON")

    _check_pinned_hashes(root, checks, hashes, _verify_git_history)
    import_markers = [
        Path("tests/__init__.py"),
        Path("tests/S00/__init__.py"),
        Path("tests/S01/__init__.py"),
        Path("tests/S02/__init__.py"),
    ]
    _add(
        checks,
        "S02P02-PYTEST-IMPORT-ISOLATION",
        all((root / path).is_file() for path in import_markers),
        [path.as_posix() for path in import_markers],
    )

    dictionaries = [fixture, matrix, claims, roadmap, task_graph, canonical, costs, parameters, model_card, strategy]
    arrays = [requirements, acceptance, traceability, legacy_sources]
    if not all(isinstance(value, dict) for value in dictionaries) or not all(isinstance(value, list) for value in arrays):
        _add(checks, "S02P02-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S02P02-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S02P02-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        paper_map = _check_matrix(matrix, fixture, checks)
    except Exception as exc:
        paper_map = {}
        _add(checks, "S02P02-MATRIX-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_claims(claims, matrix, paper_map, parameters, fixture, checks)
    except Exception as exc:
        _add(checks, "S02P02-CLAIMS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_fixture_vectors(fixture, checks)
    except Exception as exc:
        _add(checks, "S02P02-FIXTURE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_baseline_alignment(canonical, costs, parameters, model_card, strategy, legacy_sources, matrix, checks)
    except Exception as exc:
        _add(checks, "S02P02-BASELINE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    _add(
        checks,
        "S02P02-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS",
        not any(_contains_float(value) for value in [fixture, matrix, claims]),
        "decimal thresholds remain strings or exact integers",
    )
    _check_p01_prerequisite(root, checks, _verify_git_history)
    _check_s02_p03_not_started(root, checks, _verify_git_history)
    if require_external_reports:
        _check_runtime_reports(root, fixture, checks, hashes)
    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0))
    if result["summary"]["checks"] < minimum:
        _add(checks, "S02P02-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
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
    if not verify_git_history:
        evolved_test_hash = SUCCESSOR_EVOLVED_TEST_HASHES.get(relative)
        return evolved_test_hash is None or sha256_file(root / relative) == evolved_test_hash
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
    paths = sorted(
        line
        for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    )
    digest = hashlib.sha256()
    for repo_path in paths:
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        relative = repo_path.removeprefix("ABD/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = [
        (MATRIX_PATH.as_posix(), root / MATRIX_PATH),
        (CLAIMS_PATH.as_posix(), root / CLAIMS_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (P01_EVIDENCE_PATH.as_posix(), root / P01_EVIDENCE_PATH),
        (P01_ROLLBACK_PATH.as_posix(), root / P01_ROLLBACK_PATH),
        ("machine/facts/parameters.json", root / "machine/facts/parameters.json"),
        ("machine/facts/model_system_card.json", root / "machine/facts/model_system_card.json"),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s02-p02-rollback-") as directory:
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
        "evidence_id": "EVD-S02-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_MODEL_RISK_RESEARCH_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        MATRIX_PATH,
        CLAIMS_PATH,
        FIXTURE_PATH,
        *[Path(relative) for relative in PINNED_BASELINE_HASHES],
        TEST_PATH,
        Path("tests/S02/P01_test.py"),
        Path("tests/S02/__init__.py"),
        Path("abd_acceptance/model_risk_research.py"),
        Path("abd_acceptance/official_platform_research.py"),
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
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S02-P02-ROLLBACK",
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
        result["phase_status"] = "S02_P02_FAILED"
        result["next"] = "S02/P02_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S02-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P02",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S02-P02-01": MATRIX_PATH.as_posix(),
            "ART-S02-P02-02": CLAIMS_PATH.as_posix(),
        },
        "p01_prerequisite": {
            "evidence": P01_EVIDENCE_PATH.as_posix(),
            "evidence_sha256": P01_EVIDENCE_SHA256,
            "rollback": P01_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": P01_ROLLBACK_SHA256,
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S02/P02 freezes paper-to-claim research evidence only; it executes no model, training, backtest, strategy, provider interaction, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S02/P02_test.py --junitxml=machine/evidence/S02/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S02-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": {
            "github_upload_performed": False,
            "wagering_provider_account_accessed": False,
            "provider_or_cloud_account_accessed": False,
            "provider_api_called": False,
            "secret_provisioned": False,
            "incremental_cash_spent_aud": "0.00",
            "production_deployment_claimed": False,
            "all_market_coverage_claimed": False,
            "real_order_capability_present": False,
            "model_or_strategy_executed": False,
            "return_or_guarantee_claimed": False,
            "s02_p03_started": False,
        },
        "explicit_unknowns": [
            "No paper establishes ABD's fixed market or residual weights.",
            "No paper establishes ABD's calibration slope, intercept, error or skill thresholds.",
            "No paper establishes ABD's 0.0001 stability perturbation or adverse-tick action boundary.",
            "No paper establishes ABD's percentile-10, 25% edge haircut or top-profit 1% sensitivity thresholds.",
            "No paper establishes ABD's fractional-Kelly values, exposure caps, drawdown gates or A$300 suitability.",
            "No model, data pipeline, training, backtest, provider account, OVH runtime or Cloudflare path was exercised in S02/P02.",
            "All-observable-market coverage, capacity, friction, actual return and production readiness remain unverified.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; no gate may be relaxed to chase it.",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S02-P02"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S02-P02 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S02/P03_READY_NOT_STARTED" if status == "PASS" else "S02/P02_REMEDIATION_REQUIRED"
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


def verify_existing_phase_evidence(
    root: Path,
    *,
    verify_git_history: bool = True,
    verify_p01_prerequisite: bool = True,
    verify_successor_state: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S02P02-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S02P02-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"

    if isinstance(evidence, dict):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S02-P02"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S02"
            and evidence.get("phase_id") == "P02"
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "MODEL_AND_RISK_RESEARCH_CLAIMS_FROZEN"
            and evidence.get("phase_status") == "S02_P02_PASS"
            and evidence.get("next") == "S02/P03_READY_NOT_STARTED"
            and evidence.get("artifacts")
            == {"ART-S02-P02-01": MATRIX_PATH.as_posix(), "ART-S02-P02-02": CLAIMS_PATH.as_posix()}
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S02P02-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            validation.get("status") == "PASS"
            and validation.get("decision") == "MODEL_AND_RISK_RESEARCH_CLAIMS_FROZEN"
            and validation.get("summary", {}).get("failed") == 0
            and validation.get("next") == "S02/P03_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S02P02-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        effects = evidence.get("external_effect_boundary", {})
        effects_ok = (
            effects.get("github_upload_performed") is False
            and effects.get("wagering_provider_account_accessed") is False
            and effects.get("provider_or_cloud_account_accessed") is False
            and effects.get("provider_api_called") is False
            and effects.get("incremental_cash_spent_aud") == "0.00"
            and effects.get("production_deployment_claimed") is False
            and effects.get("all_market_coverage_claimed") is False
            and effects.get("real_order_capability_present") is False
            and effects.get("model_or_strategy_executed") is False
            and effects.get("return_or_guarantee_claimed") is False
            and effects.get("s02_p03_started") is False
        )
        _add(checks, "S02P02-RECEIPT-NO-EXTERNAL-EFFECT", effects_ok, effects)

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
            "S02P02-RECEIPT-SIGNED-INPUTS-CURRENT",
            not input_errors,
            input_errors or {"current": len(signed_inputs) - len(historical_inputs), "historical_phase_commit": historical_inputs},
        )

        validation_hashes = validation.get("hashes", {})
        report_errors = []
        for relative in [JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), PACK_REPORT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()]:
            expected = validation_hashes.get(relative)
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if expected != actual:
                report_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S02P02-RECEIPT-REPORT-HASHES-CURRENT", not report_errors, report_errors or "all reports match")

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
        _add(
            checks,
            "S02P02-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_actual, "historical_phase_commit": historical_code},
        )
        rollback_binding = evidence.get("hashes", {}).get("rollback_evidence")
        _add(
            checks,
            "S02P02-RECEIPT-ROLLBACK-HASH-BINDING",
            rollback_binding == rollback_hash,
            {"expected": rollback_binding, "actual": rollback_hash},
        )
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        _add(
            checks,
            "S02P02-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
            str(root) not in rendered and ("/" + "Users/") not in rendered and ("/private/" + "var/") not in rendered,
            "portable evidence",
        )
    else:
        for check_id in [
            "S02P02-RECEIPT-EVIDENCE-INTEGRITY",
            "S02P02-RECEIPT-VALIDATION-ALL-PASS",
            "S02P02-RECEIPT-NO-EXTERNAL-EFFECT",
            "S02P02-RECEIPT-SIGNED-INPUTS-CURRENT",
            "S02P02-RECEIPT-REPORT-HASHES-CURRENT",
            "S02P02-RECEIPT-CODE-HASH-CURRENT",
            "S02P02-RECEIPT-ROLLBACK-HASH-BINDING",
            "S02P02-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
        ]:
            _add(checks, check_id, False, "evidence unavailable")

    if isinstance(rollback, dict):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S02-P02-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("fixed_clock") == FIXED_CLOCK
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and len(rollback.get("artifacts", {})) == 8
            and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
        )
        _add(checks, "S02P02-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S02P02-RECEIPT-ROLLBACK-INTEGRITY", False, "rollback unavailable")

    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p02 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P02"]
        index_ok = (
            len(p02) == 1
            and p02[0].get("status") == "PASS"
            and p02[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and p02[0].get("artifact_sha256") == evidence_hash
            and p02[0].get("next") == "S02/P03_READY_NOT_STARTED"
        )
        _add(checks, "S02P02-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, p02)
    except Exception as exc:
        _add(checks, "S02P02-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_p01_prerequisite:
        _check_p01_prerequisite(root, checks, verify_git_history)
    if verify_successor_state:
        _check_s02_p03_not_started(root, checks, verify_git_history)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S02-P02",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S02_P02_EVIDENCE_VERIFIED" if not failed else "S02_P02_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for row in checks if row["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S02/P03_READY_NOT_STARTED" if not failed else "S02/P02_REMEDIATION_REQUIRED",
    }
