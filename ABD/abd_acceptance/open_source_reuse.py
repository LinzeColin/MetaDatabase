from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.parse import urlsplit

from .canonical_facts import sha256_file, strict_json_load
from .model_risk_research import verify_existing_phase_evidence as verify_s02_p02_evidence


CONTRACT_ID = "AC-S02-P03"
REQUIREMENT_ID = "REQ-S02-P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

REUSE_MATRIX_PATH = Path("research_reuse_matrix.json")
LICENSE_INVENTORY_PATH = Path("license_inventory.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S02_P03.json")
TEST_PATH = Path("tests/S02/P03_test.py")
JUNIT_PATH = Path("machine/evidence/S02/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S02/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P03_rollback.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S02-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")
PHASE_COMMIT = "6fd05aefc6a5f8269909504d36e1907da336628c"
PINNED_PHASE_CODE_HASH = "92a071e3f5fff10b834c85d8f9eb0636a01b610a934904b07bdc29a5673c8c7b"

SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "abd_acceptance/official_platform_research.py",
    "abd_acceptance/model_risk_research.py",
    "abd_acceptance/open_source_reuse.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S02/P01_test.py",
    "tests/S02/P02_test.py",
    "tests/S02/P03_test.py",
}
SUCCESSOR_EVOLVED_TEST_HASHES = {
    "tests/S02/P01_test.py": "28868c63503b7e98f0c9761cdc92c70cb1053e2c957d196925f8d577abffce00",
    "tests/S02/P02_test.py": "dcafa1f4120415cf0d191f69654c58392bece7dcfb86e8e698d436ae1f2f68bd",
    "tests/S02/P03_test.py": "3e0bd2ec5eb089a09c6c311ecaca8dd757f3ba9a2dd96f3574434630a2d7d8ae",
}

P02_EVIDENCE_SHA256 = "0fc89eaba4a1afa7630f92ad79cecbb073ba5303bca6ea2f534f2267b4bb5623"
P02_ROLLBACK_SHA256 = "873ad2b164ef3280f5f5e7ef6ce0ce68d3bf64ea0cdf8c2ca43901088dbd7feb"

PINNED_PHASE_HASHES = {
    REUSE_MATRIX_PATH.as_posix(): "e5d049c5e4049195f537cce7b27cc8713269d211f55ce4840c10fdf67feac0e8",
    LICENSE_INVENTORY_PATH.as_posix(): "b09ce2ae8e60ba91d3c436f4116b032c772a19902cfebdcc9f37027c53393379",
    FIXTURE_PATH.as_posix(): "8fa4c75b2863cd34a08921b6ea2022be6469c95cf0a7edd9ebf60ddc4c68afde",
    TEST_PATH.as_posix(): "0face2a74e38ed22cb0dccfdfe8fe192631ef12466f1f57f11191f31fd76e5b6",
}

PINNED_BASELINE_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/sources.json": "387df5c4cf54fcad59072c46ee7bbcd67f13e66adf2f5ccf9b115b71182784d8",
    "machine/facts/research_reuse_matrix.json": "4e96ec569250ebe7a964035528f4030e83230a00bd13cdc5cf5dc2be9ecfa041",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "tests/S02/P01_test.py": "786acde040d037909f9e1c3fd4f9fa3b83ef5a0024b7fd08526cc06a6b41242a",
    "tests/S02/P02_test.py": "28090181af5286b5ed0b9d84f973623056b3f96b53e14e539d2ad42dab452eb4",
    "abd_acceptance/model_risk_research.py": "a4b97554f0d3473c10248571916475309a6ef70e6041190c483dc84621c874b9",
    "abd_acceptance/__init__.py": "7c25e8941528cb2f816df3272ce2951143212c1f858a2869345b049b0a62280a",
    "abd_acceptance/__main__.py": "842f4575ccbdfe634b6c5aea5035694cdb99cb5f27e94a937814affeef2d6110",
    P02_EVIDENCE_PATH.as_posix(): P02_EVIDENCE_SHA256,
    P02_ROLLBACK_PATH.as_posix(): P02_ROLLBACK_SHA256,
}

PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

ALLOWED_DECISIONS = {
    "ADAPT_DESIGN_ONLY",
    "ADAPT_RESEARCH_REFERENCE",
    "ADAPT_PARSER_TEST_PATTERNS_ONLY",
    "REJECT_CODE_REUSE_RESEARCH_ONLY",
    "RESEARCH_ONLY_NO_MODEL_REUSE",
    "ADAPT_MOCKS_AND_SCHEMA_ONLY",
}
ALLOWED_LICENSES = {"MIT", "Apache-2.0", "NOASSERTION"}
ALLOWED_REUSE_MODES = {
    "DESIGN_PATTERN",
    "ALGORITHM_REFERENCE",
    "PARSER_TEST_PATTERN",
    "PUBLIC_METADATA_RESEARCH",
    "MOCK_SCHEMA_REFERENCE",
    "COPY_CODE",
    "ADD_RUNTIME_DEPENDENCY",
    "LIVE_SOURCE",
}
ALLOWED_SOURCE_CONTRACTS = {"NOT_APPLICABLE", "VERIFIED", "UNVERIFIED", "REJECTED"}
ALLOWED_NUMERIC_DELTAS = {Decimal("-0.0001"), Decimal("0"), Decimal("0.0001")}
ALLOWED_NUMERIC_DELTA_STRINGS = {"-0.0001", "0", "0.0001"}
RESEARCH_ONLY_MODES = {
    "DESIGN_PATTERN",
    "ALGORITHM_REFERENCE",
    "PARSER_TEST_PATTERN",
    "MOCK_SCHEMA_REFERENCE",
}
RUNTIME_MODES = {"COPY_CODE", "ADD_RUNTIME_DEPENDENCY", "LIVE_SOURCE"}


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
    matches = [row for row in rows if row.get("id") == item_id]
    if len(matches) != 1:
        return {}
    return matches[0]


def _is_sha(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _is_https_github_url(value: Any, hosts: Sequence[str] = ("github.com",)) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and parsed.hostname in set(hosts) and not parsed.username and not parsed.password


def resolve_reuse_admission(
    *,
    license_class: str,
    reuse_mode: str,
    source_contract: str,
    contains_order_capability: bool,
    requires_live_account: bool,
    requires_incremental_cash: bool,
    numeric_delta: str,
) -> str:
    if license_class not in ALLOWED_LICENSES:
        raise ValueError("unsupported license_class")
    if reuse_mode not in ALLOWED_REUSE_MODES:
        raise ValueError("unsupported reuse_mode")
    if source_contract not in ALLOWED_SOURCE_CONTRACTS:
        raise ValueError("unsupported source_contract")
    for value in (contains_order_capability, requires_live_account, requires_incremental_cash):
        if type(value) is not bool:
            raise TypeError("reuse admission flags must be booleans")
    if not isinstance(numeric_delta, str):
        raise TypeError("numeric_delta must be a decimal string")
    if numeric_delta not in ALLOWED_NUMERIC_DELTA_STRINGS:
        raise ValueError("numeric_delta must use an exact frozen decimal representation")
    try:
        parsed_delta = Decimal(numeric_delta)
    except InvalidOperation as exc:
        raise ValueError("invalid numeric_delta") from exc
    if parsed_delta not in ALLOWED_NUMERIC_DELTAS:
        raise ValueError("numeric_delta is outside the frozen boundary set")

    if requires_incremental_cash:
        return "REJECT_INCREMENTAL_CASH"
    if contains_order_capability:
        return "REJECT_ORDER_CAPABILITY"
    if requires_live_account:
        return "REJECT_ACCOUNT_OR_API_ACCESS"
    if license_class == "NOASSERTION" and reuse_mode != "PUBLIC_METADATA_RESEARCH":
        return "REJECT_NO_LICENSE"
    if source_contract == "REJECTED":
        return "REJECT_SOURCE_CONTRACT"
    if reuse_mode == "PUBLIC_METADATA_RESEARCH":
        return "ALLOW_PUBLIC_METADATA_RESEARCH_ONLY"
    if reuse_mode == "LIVE_SOURCE" and source_contract != "VERIFIED":
        return "REJECT_UNVERIFIED_SOURCE_CONTRACT"
    if reuse_mode in RUNTIME_MODES:
        return "REJECT_P03_RUNTIME_SCOPE"
    if reuse_mode in RESEARCH_ONLY_MODES:
        return "ALLOW_PINNED_RESEARCH_ADAPTATION"
    raise ValueError("unreachable reuse admission state")


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
        check_id = "S02P03-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
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
        check_id = "S02P03-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
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
    phases = [row for row in stage.get("phases", []) if isinstance(row, dict) and row.get("id") == "P03"]
    expected_phase = {
        "id": "P03",
        "title": "开源项目复用审计",
        "objective": "审计flumine、penaltyblog、OddsHarvester及相关只读项目。",
        "outputs": [REUSE_MATRIX_PATH.as_posix(), LICENSE_INVENTORY_PATH.as_posix()],
        "pass_gate": "每个项目有采用/适配/拒绝和许可证裁定。",
        "hours": {"low": 3, "likely": 4, "high": 6},
    }
    _add(
        checks,
        "S02P03-ROADMAP-EXACT",
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
        "phase_id": "P03",
        "title": "开源项目复用审计",
        "problem": "若未完成“开源项目复用审计”，只研究与ABD直接相关的官方文档、论文和开源项目，明确采用、适配、拒绝和许可证。将缺少可执行、可验收或可恢复的基础。",
        "user": "单一账户持有人及自动开发/运维代理",
        "value": "审计flumine、penaltyblog、OddsHarvester及相关只读项目。",
        "scope": [REUSE_MATRIX_PATH.as_posix(), LICENSE_INVENTORY_PATH.as_posix()],
        "non_goals": [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ],
        "baseline": "未实现或旧包存在冲突/缺口",
        "target": "每个项目有采用/适配/拒绝和许可证裁定。",
        "measurement": "由 AC-S02-P03 的机器验收判定器执行固定输入、阈值和证据检查。",
        "observation_period": "开发期每次提交；上线后持续",
        "primary_acceptance_criteria_id": CONTRACT_ID,
        "priority": "P1",
        "owner_input_required_during_development": False,
    }
    _add(checks, "S02P03-REQUIREMENT-EXACT", requirement == expected_requirement, requirement)

    contract = _row(acceptance, CONTRACT_ID)
    contract_ok = (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("title") == "开源项目复用审计唯一主验收"
        and contract.get("oracle")
        == {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S02-P03 --evidence machine/evidence",
            "rule": "每个项目有采用/适配/拒绝和许可证裁定。",
        }
        and contract.get("threshold") == "每个项目有采用/适配/拒绝和许可证裁定。"
        and contract.get("pass_gate") == "每个项目有采用/适配/拒绝和许可证裁定。"
        and contract.get("evidence_requirements", [None])[0] == EVIDENCE_PATH.as_posix()
        and [row.get("id") for row in contract.get("tests", [])]
        == ["TEST-S02-P03", "TEST-S02-P03-BOUNDARY", "TEST-S02-P03-REPLAY"]
        and "固定时钟" in contract.get("environment", [])
        and "无外部网络的确定性测试模式" in contract.get("environment", [])
    )
    _add(checks, "S02P03-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [_row(task_graph.get("tasks", []), "T-S02-P03-%02d" % index) for index in range(1, 4)]
    task_ok = (
        tasks[0].get("depends_on") == ["T-S02-P02-03"]
        and tasks[0].get("outputs") == [REUSE_MATRIX_PATH.as_posix(), LICENSE_INVENTORY_PATH.as_posix()]
        and tasks[1].get("depends_on") == ["T-S02-P03-01"]
        and tasks[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
        and tasks[2].get("depends_on") == ["T-S02-P03-02"]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
        and all(row.get("stage_id") == "S02" and row.get("phase_id") == "P03" for row in tasks)
        and all(row.get("requirement_ids") == [REQUIREMENT_ID] for row in tasks)
        and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks)
        and all(row.get("oracle", {}).get("mode") == "DETERMINISTIC_FAIL_CLOSED" for row in tasks)
        and all(row.get("pass_gate") == "每个项目有采用/适配/拒绝和许可证裁定。" for row in tasks)
        and all(row.get("owner_input_required") is False and row.get("auto_advance_on_pass") is True for row in tasks)
    )
    _add(checks, "S02P03-TASK-CHAIN-EXACT", task_ok, [row.get("id") for row in tasks])

    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    expected_trace = {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S02-P03-01", "T-S02-P03-02", "T-S02-P03-03"],
        "test_ids": ["TEST-S02-P03", "TEST-S02-P03-BOUNDARY", "TEST-S02-P03-REPLAY"],
        "evidence_id": "EVD-S02-P03",
        "artifact_ids": ["ART-S02-P03-01", "ART-S02-P03-02"],
        "stage_id": "S02",
        "phase_id": "P03",
    }
    _add(checks, "S02P03-TRACEABILITY-EXACT", len(trace) == 1 and trace[0] == expected_trace, trace)


def _check_reuse_matrix(
    matrix: Mapping[str, Any],
    fixture: Mapping[str, Any],
    baseline_matrix: Mapping[str, Any],
    baseline_sources: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> Dict[str, Mapping[str, Any]]:
    shape_ok = (
        matrix.get("schema_version") == "1.0.0"
        and matrix.get("version") == VERSION
        and matrix.get("stage_id") == "S02"
        and matrix.get("phase_id") == "P03"
        and matrix.get("as_of") == "2026-07-20"
        and matrix.get("status") == "FROZEN_RESEARCH_ONLY_NO_RUNTIME_ADOPTION"
        and matrix.get("next_on_acceptance_pass") == "S02/P04_READY_NOT_STARTED"
    )
    _add(checks, "S02P03-MATRIX-SHAPE", shape_ok, matrix.get("status"))

    projects = matrix.get("projects", [])
    ids = [row.get("source_id") for row in projects if isinstance(row, dict)]
    expected_ids = fixture.get("expected_project_source_ids", [])
    _add(checks, "S02P03-MATRIX-PROJECT-COVERAGE", ids == expected_ids and not _duplicates(ids), ids)
    project_map = {row.get("source_id"): row for row in projects if isinstance(row, dict)}

    required_fields = set(fixture.get("required_project_fields", []))
    fields_ok = all(required_fields.issubset(row) for row in projects if isinstance(row, dict))
    _add(checks, "S02P03-MATRIX-REQUIRED-FIELDS", fields_ok, sorted(required_fields))

    repositories_ok = {item_id: project_map.get(item_id, {}).get("repository") for item_id in expected_ids} == fixture.get(
        "expected_repositories"
    )
    _add(checks, "S02P03-MATRIX-REPOSITORIES-EXACT", repositories_ok, fixture.get("expected_repositories"))

    commits_ok = {item_id: project_map.get(item_id, {}).get("pinned_commit") for item_id in expected_ids} == fixture.get(
        "expected_pinned_commits"
    ) and all(_is_sha(project_map.get(item_id, {}).get("pinned_commit"), 40) for item_id in expected_ids)
    _add(checks, "S02P03-MATRIX-COMMITS-EXACT", commits_ok, fixture.get("expected_pinned_commits"))

    readmes_ok = all(
        project_map.get(item_id, {}).get("readme", {}).get("sha256") == fixture.get("expected_readme_sha256", {}).get(item_id)
        and _is_sha(project_map.get(item_id, {}).get("readme", {}).get("sha256"), 64)
        and _is_sha(project_map.get(item_id, {}).get("readme", {}).get("git_blob_sha1"), 40)
        and project_map.get(item_id, {}).get("pinned_commit") in project_map.get(item_id, {}).get("readme", {}).get("url", "")
        and _is_https_github_url(project_map.get(item_id, {}).get("readme", {}).get("url"))
        for item_id in expected_ids
    )
    _add(checks, "S02P03-MATRIX-README-PINS-EXACT", readmes_ok, fixture.get("expected_readme_sha256"))

    decisions = {item_id: project_map.get(item_id, {}).get("decision") for item_id in expected_ids}
    decisions_ok = decisions == fixture.get("expected_decisions") and set(decisions.values()) == ALLOWED_DECISIONS
    _add(checks, "S02P03-MATRIX-DECISIONS-EXACT", decisions_ok, decisions)

    lists_ok = True
    list_errors = []
    for row in projects:
        for field in ("adopt", "adapt", "reject", "unverified"):
            values = row.get(field)
            if not isinstance(values, list) or not values or _duplicates(values) or not all(isinstance(item, str) and item for item in values):
                lists_ok = False
                list_errors.append({"source_id": row.get("source_id"), "field": field})
        if set(row.get("adopt", [])) & set(row.get("reject", [])):
            lists_ok = False
            list_errors.append({"source_id": row.get("source_id"), "field": "adopt_reject_overlap"})
    _add(checks, "S02P03-MATRIX-ADOPT-ADAPT-REJECT-COMPLETE", lists_ok, list_errors or len(projects))

    url_ok = all(
        _is_https_github_url(row.get("repository"))
        and _is_https_github_url(row.get("repository_api"), ("api.github.com",))
        and _is_https_github_url(row.get("commit_url"))
        and row.get("pinned_commit") in row.get("commit_url", "")
        and row.get("repository_archived_at_retrieval") is False
        for row in projects
    )
    _add(checks, "S02P03-MATRIX-OFFICIAL-PINNED-URLS", url_ok, ids)

    controls = matrix.get("global_controls", {})
    controls_ok = (
        controls.get("snapshot_basis") == "PINNED_GITHUB_COMMIT_AND_CONTENT_SHA256"
        and controls.get("project_count") == 6
        and controls.get("expected_source_ids") == expected_ids
        and controls.get("code_copied") is False
        and controls.get("dependency_added") is False
        and controls.get("repository_cloned") is False
        and controls.get("package_installed") is False
        and controls.get("live_service_called") is False
        and controls.get("account_or_api_key_used") is False
        and controls.get("external_terms_accepted") is False
        and controls.get("runtime_adoption_requires_future_acceptance") is True
        and controls.get("license_does_not_authorize_source_access") is True
        and controls.get("public_visibility_does_not_equal_reuse_permission") is True
        and controls.get("no_order_capability_may_enter_abd") is True
        and controls.get("a_zero_incremental_cash_preserved") is True
    )
    _add(checks, "S02P03-MATRIX-GLOBAL-CONTROLS", controls_ok, controls)

    coverage = matrix.get("coverage", {})
    coverage_ok = (
        coverage.get("all_taskpack_projects_present") is True
        and coverage.get("all_projects_have_adopt_adapt_reject") is True
        and coverage.get("all_projects_have_pinned_commit_and_readme_hash") is True
        and coverage.get("all_projects_have_license_evidence") is True
        and coverage.get("all_runtime_dependencies_rejected_or_deferred") is True
        and coverage.get("silent_project_omissions") == 0
    )
    _add(checks, "S02P03-MATRIX-COVERAGE-NO-SILENT-OMISSION", coverage_ok, coverage)

    effects = matrix.get("external_effect_boundary", {})
    _add(
        checks,
        "S02P03-MATRIX-NO-EXTERNAL-EFFECT",
        effects == fixture.get("expected_external_effect_boundary"),
        effects,
    )

    baseline_projects = {row.get("source_id"): row for row in baseline_matrix.get("projects", []) if isinstance(row, dict)}
    source_projects = {row.get("id"): row for row in baseline_sources if isinstance(row, dict)}
    baseline_errors = []
    for item_id in expected_ids:
        current = project_map.get(item_id, {})
        legacy = baseline_projects.get(item_id, {})
        source = source_projects.get(item_id, {})
        known_names = {current.get("name"), current.get("legacy_name_alias")}
        if legacy.get("name") not in known_names or source.get("title") not in known_names or current.get("repository") != source.get("url"):
            baseline_errors.append({"source_id": item_id, "reason": "identity"})
        if not set(legacy.get("adopt", [])).issubset(set(current.get("adopt", []))):
            baseline_errors.append({"source_id": item_id, "reason": "adopt"})
        if not set(legacy.get("reject", [])).issubset(set(current.get("reject", []))):
            baseline_errors.append({"source_id": item_id, "reason": "reject"})
        if current.get("license_evidence_id") != "LIC-%s" % item_id:
            baseline_errors.append({"source_id": item_id, "reason": "license_link"})
    _add(checks, "S02P03-MATRIX-BASELINE-CONTINUITY", not baseline_errors, baseline_errors or expected_ids)

    flumine = project_map.get("SRC-013", {})
    flumine_ok = "任何 place、cancel、update、replace 订单能力" in flumine.get("reject", []) and any(
        "真实订单" in item for item in flumine.get("observed_capabilities", [])
    )
    _add(checks, "S02P03-FLUMINE-ORDER-CAPABILITY-REJECTED", flumine_ok, flumine.get("adoption_status"))

    penaltyblog = project_map.get("SRC-014", {})
    penaltyblog_ok = (
        "未经独立时间验证直接用于建议" in penaltyblog.get("reject", [])
        and "UNVERIFIED" in penaltyblog.get("source_contract_status", "")
        and "NO_RUNTIME_DEPENDENCY" in penaltyblog.get("adoption_status", "")
    )
    _add(checks, "S02P03-PENALTYBLOG-RESEARCH-ONLY", penaltyblog_ok, penaltyblog.get("decision"))

    harvester = project_map.get("SRC-015", {})
    harvester_ok = (
        any("代理轮换" in item for item in harvester.get("reject", []))
        and any("条款" in item for item in harvester.get("reject", []))
        and "BLOCKS_ALL_LIVE_ODDSPORTAL_ACCESS" in harvester.get("source_contract_status", "")
    )
    _add(checks, "S02P03-ODDSHARVESTER-NO-BYPASS-OR-LIVE-SOURCE", harvester_ok, harvester.get("decision"))

    unlicensed = project_map.get("SRC-016", {})
    unlicensed_ok = (
        unlicensed.get("decision") == "REJECT_CODE_REUSE_RESEARCH_ONLY"
        and "CODE_REUSE_REJECTED" in unlicensed.get("adoption_status", "")
        and any("复制、修改、打包或分发" in item for item in unlicensed.get("reject", []))
        and any("VPN" in item for item in unlicensed.get("reject", []))
    )
    _add(checks, "S02P03-UNLICENSED-CODE-REUSE-REJECTED", unlicensed_ok, unlicensed.get("decision"))

    ml_demo = project_map.get("SRC-017", {})
    ml_ok = (
        ml_demo.get("decision") == "RESEARCH_ONLY_NO_MODEL_REUSE"
        and any("5.2%" in item for item in ml_demo.get("reject", []))
        and any("受限凯利" in item for item in ml_demo.get("adapt", []))
        and any("demo/synthetic" in item for item in ml_demo.get("adapt", []))
    )
    _add(checks, "S02P03-ML-DEMO-NO-MODEL-OR-RETURN-EVIDENCE", ml_ok, ml_demo.get("decision"))

    odds_api = project_map.get("SRC-018", {})
    odds_api_ok = (
        odds_api.get("decision") == "ADAPT_MOCKS_AND_SCHEMA_ONLY"
        and any("代码 Apache-2.0" in item for item in odds_api.get("reject", []))
        and any("API key" in item for item in odds_api.get("reject", []))
        and "SERVICE_TERMS" in odds_api.get("source_contract_status", "")
    )
    _add(checks, "S02P03-ODDS-API-CODE-SERVICE-SEPARATION", odds_api_ok, odds_api.get("decision"))

    return project_map


def _check_license_inventory(
    inventory: Mapping[str, Any],
    matrix_projects: Mapping[str, Mapping[str, Any]],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    shape_ok = (
        inventory.get("schema_version") == "1.0.0"
        and inventory.get("version") == VERSION
        and inventory.get("stage_id") == "S02"
        and inventory.get("phase_id") == "P03"
        and inventory.get("as_of") == "2026-07-20"
        and inventory.get("status") == "FROZEN_ENGINEERING_LICENSE_AUDIT_NOT_LEGAL_ADVICE"
        and inventory.get("next_on_acceptance_pass") == "S02/P04_READY_NOT_STARTED"
    )
    _add(checks, "S02P03-LICENSE-SHAPE", shape_ok, inventory.get("status"))

    policy = inventory.get("policy", {})
    policy_ok = (
        policy.get("legal_advice") is False
        and _is_https_github_url(policy.get("repository_license_detection_source"), ("docs.github.com",))
        and _is_https_github_url(policy.get("no_license_rule_source"), ("docs.github.com",))
        and "传递依赖" in policy.get("github_detection_boundary", "")
        and "不授权复制" in policy.get("no_license_default", "")
        and policy.get("code_license_separate_from_service_terms") is True
        and policy.get("future_reuse_requires_exact_version_recheck") is True
        and policy.get("p03_code_copy_or_dependency_addition") is False
    )
    _add(checks, "S02P03-LICENSE-POLICY-FAIL-CLOSED", policy_ok, policy)

    classes = inventory.get("license_classes", {})
    class_ok = set(classes) == ALLOWED_LICENSES and all(
        isinstance(classes[name].get("required_controls"), list) and classes[name].get("required_controls")
        for name in ALLOWED_LICENSES
    )
    _add(checks, "S02P03-LICENSE-CLASS-CONTROLS", class_ok, sorted(classes))

    entries = inventory.get("entries", [])
    ids = [row.get("id") for row in entries if isinstance(row, dict)]
    source_ids = [row.get("source_id") for row in entries if isinstance(row, dict)]
    expected_ids = fixture.get("expected_project_source_ids", [])
    coverage_ok = source_ids == expected_ids and ids == ["LIC-%s" % item_id for item_id in expected_ids] and not _duplicates(ids)
    _add(checks, "S02P03-LICENSE-ENTRY-COVERAGE", coverage_ok, ids)

    required_fields = set(fixture.get("required_license_fields", []))
    fields_ok = all(required_fields.issubset(row) for row in entries if isinstance(row, dict))
    _add(checks, "S02P03-LICENSE-REQUIRED-FIELDS", fields_ok, sorted(required_fields))

    entry_map = {row.get("source_id"): row for row in entries if isinstance(row, dict)}
    exact_errors = []
    for item_id, expected in fixture.get("expected_license_records", {}).items():
        row = entry_map.get(item_id, {})
        actual = {
            "id": row.get("id"),
            "spdx": row.get("detected_spdx"),
            "path": row.get("license_path"),
            "git_blob_sha1": row.get("license_git_blob_sha1"),
            "sha256": row.get("license_sha256"),
        }
        if actual != expected:
            exact_errors.append({"source_id": item_id, "expected": expected, "actual": actual})
        matrix = matrix_projects.get(item_id, {})
        if row.get("repository") != matrix.get("repository") or row.get("pinned_commit") != matrix.get("pinned_commit"):
            exact_errors.append({"source_id": item_id, "reason": "matrix_binding"})
        if row.get("id") != matrix.get("license_evidence_id"):
            exact_errors.append({"source_id": item_id, "reason": "license_id_binding"})
    _add(checks, "S02P03-LICENSE-PINS-EXACT", not exact_errors, exact_errors or expected_ids)

    hash_ok = all(
        (
            row.get("detected_spdx") == "NOASSERTION"
            and row.get("license_path") is None
            and row.get("license_git_blob_sha1") is None
            and row.get("license_sha256") is None
        )
        or (
            row.get("detected_spdx") in {"MIT", "Apache-2.0"}
            and _is_sha(row.get("license_git_blob_sha1"), 40)
            and _is_sha(row.get("license_sha256"), 64)
            and row.get("pinned_commit") in row.get("license_url", "")
        )
        for row in entries
    )
    _add(checks, "S02P03-LICENSE-CONTENT-HASHES-OR-NOASSERTION", hash_ok, source_ids)

    counts = {name: sum(1 for row in entries if row.get("detected_spdx") == name) for name in ALLOWED_LICENSES}
    _add(checks, "S02P03-LICENSE-COUNTS-EXACT", counts == fixture.get("expected_license_counts"), counts)

    noassertion = entry_map.get("SRC-016", {})
    noassertion_ok = (
        noassertion.get("license_api_result") == "NOT_FOUND_AT_RETRIEVAL"
        and noassertion.get("p03_disposition") == "REJECT_ALL_CODE_REUSE_PUBLIC_METADATA_RESEARCH_ONLY"
        and noassertion.get("future_reuse").startswith("BLOCKED_UNLESS_RIGHTSHOLDER")
        and "没有许可证" in noassertion.get("code_license_scope", "")
    )
    _add(checks, "S02P03-LICENSE-NOASSERTION-REJECTS-COPY", noassertion_ok, noassertion.get("p03_disposition"))

    apache = entry_map.get("SRC-018", {})
    apache_ok = (
        apache.get("detected_spdx") == "Apache-2.0"
        and apache.get("notice_file_at_repository_root") is False
        and "API 与数据使用" in apache.get("code_license_scope", "")
        and "SERVICE_TERMS" in apache.get("future_reuse", "")
        and any("NOTICE" in item for item in classes.get("Apache-2.0", {}).get("required_controls", []))
    )
    _add(checks, "S02P03-LICENSE-APACHE-CODE-SERVICE-BOUNDARY", apache_ok, apache.get("p03_disposition"))

    mit_ok = all(
        row.get("copyright_notice")
        and row.get("p03_disposition").endswith(("NO_COPY_NO_DEPENDENCY", "NO_MODEL_OR_CODE_REUSE"))
        for row in entries
        if row.get("detected_spdx") == "MIT"
    ) and any("版权声明" in item for item in classes.get("MIT", {}).get("required_controls", []))
    _add(checks, "S02P03-LICENSE-MIT-NOTICE-AND-NO-P03-COPY", mit_ok, counts.get("MIT"))

    summary = inventory.get("summary", {})
    expected_summary = {
        "projects": 6,
        "MIT": 4,
        "Apache-2.0": 1,
        "NOASSERTION": 1,
        "p03_code_copies": 0,
        "p03_dependencies_added": 0,
        "license_decisions_missing": 0,
        "service_terms_treated_as_code_license": 0,
        "legal_clearance_claimed": False,
    }
    _add(checks, "S02P03-LICENSE-SUMMARY-EXACT", summary == expected_summary, summary)

    effects = inventory.get("external_effect_boundary", {})
    effects_ok = (
        effects.get("repository_cloned") is False
        and effects.get("package_installed") is False
        and effects.get("provider_api_called") is False
        and effects.get("account_or_api_key_used") is False
        and effects.get("incremental_cash_spent_aud") == "0.00"
        and effects.get("production_or_legal_approval_claimed") is False
        and effects.get("s02_p04_started") is False
    )
    _add(checks, "S02P03-LICENSE-NO-EXTERNAL-EFFECT", effects_ok, effects)


def _check_fixture_vectors(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    decision_errors = []
    for vector in fixture.get("decision_vectors", []):
        try:
            actual = resolve_reuse_admission(
                license_class=vector["license_class"],
                reuse_mode=vector["reuse_mode"],
                source_contract=vector["source_contract"],
                contains_order_capability=vector["contains_order_capability"],
                requires_live_account=vector["requires_live_account"],
                requires_incremental_cash=vector["requires_incremental_cash"],
                numeric_delta=vector["numeric_delta"],
            )
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
        if actual != vector.get("expected"):
            decision_errors.append({"id": vector.get("id"), "expected": vector.get("expected"), "actual": actual})
    _add(checks, "S02P03-FIXTURE-DECISION-VECTORS", not decision_errors, decision_errors or len(fixture.get("decision_vectors", [])))

    boundary_errors = []
    deltas = fixture.get("numeric_boundary_deltas", [])
    for vector in fixture.get("boundary_cases", []):
        outcomes = set()
        for delta in deltas:
            try:
                outcomes.add(
                    resolve_reuse_admission(
                        license_class=vector["license_class"],
                        reuse_mode=vector["reuse_mode"],
                        source_contract=vector["source_contract"],
                        contains_order_capability=vector["contains_order_capability"],
                        requires_live_account=vector["requires_live_account"],
                        requires_incremental_cash=vector["requires_incremental_cash"],
                        numeric_delta=delta,
                    )
                )
            except Exception as exc:
                outcomes.add("%s: %s" % (type(exc).__name__, exc))
        if outcomes != {vector.get("expected")}:
            boundary_errors.append({"id": vector.get("id"), "expected": vector.get("expected"), "actual": sorted(outcomes)})
    boundary_ok = deltas == ["-0.0001", "0", "0.0001"] and not boundary_errors
    _add(checks, "S02P03-FIXTURE-NUMERIC-BOUNDARY-INVARIANCE", boundary_ok, boundary_errors or deltas)

    mutation_ids = fixture.get("fault_mutations", [])
    mutation_ok = len(mutation_ids) == 19 and len(set(mutation_ids)) == 19
    _add(checks, "S02P03-FIXTURE-FAULT-MUTATIONS", mutation_ok, mutation_ids)

    task_ids_ok = fixture.get("expected_task_ids") == ["T-S02-P03-01", "T-S02-P03-02", "T-S02-P03-03"]
    _add(checks, "S02P03-FIXTURE-TASK-IDS", task_ids_ok, fixture.get("expected_task_ids"))
    test_ids_ok = fixture.get("expected_test_ids") == ["TEST-S02-P03", "TEST-S02-P03-BOUNDARY", "TEST-S02-P03-REPLAY"]
    _add(checks, "S02P03-FIXTURE-TEST-IDS", test_ids_ok, fixture.get("expected_test_ids"))
    artifact_ids_ok = fixture.get("expected_artifact_ids") == ["ART-S02-P03-01", "ART-S02-P03-02"]
    _add(checks, "S02P03-FIXTURE-ARTIFACT-IDS", artifact_ids_ok, fixture.get("expected_artifact_ids"))


def _check_baseline_safety(
    canonical: Mapping[str, Any],
    costs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    matrix: Mapping[str, Any],
    inventory: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    no_order_ok = (
        canonical.get("scope", {}).get("product_role") == "ANALYSIS_AND_ADVICE_ONLY"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and "real_order_capability_present" in json.dumps(matrix, ensure_ascii=False, sort_keys=True)
        and matrix.get("external_effect_boundary", {}).get("real_order_capability_present") is False
    )
    _add(checks, "S02P03-BASELINE-NO-ORDER", no_order_ok, "analysis and advice only")

    costs_ok = (
        set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
        and costs.get("incremental_cash_gate", {}).get("maximum_aud") == "0.00"
        and matrix.get("external_effect_boundary", {}).get("incremental_cash_spent_aud") == "0.00"
        and inventory.get("external_effect_boundary", {}).get("incremental_cash_spent_aud") == "0.00"
    )
    _add(checks, "S02P03-BASELINE-A-ZERO", costs_ok, costs.get("incremental_cash_budget"))

    numeric = parameters.get("numeric_determinism", {})
    numeric_ok = (
        numeric.get("boundary_perturbation_absolute_probability") == "0.0001"
        and numeric.get("boundary_perturbation_absolute_threshold") == "0.0001"
        and numeric.get("boundary_perturbation_friction_up") == "0.0001"
        and "分类门" in str(fixture.get("numeric_boundary_semantics", ""))
    )
    _add(checks, "S02P03-BASELINE-NUMERIC-GATE-NOT-LICENSE-SCORE", numeric_ok, numeric)

    target_ok = "30%" not in json.dumps(inventory.get("entries", []), ensure_ascii=False) and matrix.get(
        "external_effect_boundary", {}
    ).get("return_or_guarantee_claimed") is False
    _add(checks, "S02P03-NO-RETURN-OR-LICENSE-GUARANTEE", target_ok, "no upstream claim becomes ABD evidence")


def _check_p02_prerequisite(root: Path, checks: List[Dict[str, Any]], verify_git_history: bool) -> None:
    try:
        result = verify_s02_p02_evidence(
            root,
            verify_git_history=verify_git_history,
            verify_p01_prerequisite=True,
            verify_successor_state=False,
        )
        passed = (
            result.get("status") == "PASS"
            and result.get("decision") == "S02_P02_EVIDENCE_VERIFIED"
            and result.get("evidence_sha256") == P02_EVIDENCE_SHA256
            and result.get("rollback_sha256") == P02_ROLLBACK_SHA256
            and result.get("next") == "S02/P03_READY_NOT_STARTED"
        )
        detail = result.get("summary")
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P03-P02-IMMUTABLE-PREREQUISITE", passed, detail)


def _check_s02_p04_not_started(
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
        p04 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P04"]
        forbidden_paths = [
            root / "research_gaps.json",
            root / "counterevidence.json",
            root / "review_schedule.json",
            root / "tests/S02/P04_test.py",
            root / "machine/tests/fixtures/S02_P04.json",
            root / "machine/evidence/EVD-S02-P04.json",
            root / "machine/evidence/EVD-S02-P04_rollback.json",
        ]
        existing = [path.relative_to(root).as_posix() for path in forbidden_paths if path.exists()]
        not_started = (
            len(p04) == 1
            and p04[0].get("status") == "PLANNED"
            and "actual_artifact" not in p04[0]
            and not existing
        )
        if not_started:
            passed = True
            detail = {"state": "P04_NOT_STARTED", "index": p04, "forbidden_existing": existing}
        elif (
            len(p04) == 1
            and p04[0].get("status") == "PLANNED"
            and "actual_artifact" not in p04[0]
            and existing
            == [
                "research_gaps.json",
                "counterevidence.json",
                "review_schedule.json",
                "tests/S02/P04_test.py",
                "machine/tests/fixtures/S02_P04.json",
            ]
        ):
            try:
                from .research_gap_audit import evaluate_contract as evaluate_p04_candidate

                candidate = evaluate_p04_candidate(
                    root,
                    require_external_reports=False,
                    _verify_git_history=verify_git_history,
                )
                passed = candidate.get("status") == "PASS" and candidate.get("next") == "S02/STAGE_REVIEW_READY_NOT_STARTED"
                detail = {
                    "state": "P04_IN_PROGRESS_VALIDATED_NOT_ACCEPTED" if passed else "INVALID_P04_CANDIDATE",
                    "candidate_summary": candidate.get("summary"),
                    "index": p04,
                    "existing": existing,
                }
            except Exception as exc:
                passed = False
                detail = {
                    "state": "INVALID_P04_CANDIDATE",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "index": p04,
                    "existing": existing,
                }
        else:
            try:
                from .research_gap_audit import verify_existing_phase_evidence as verify_p04_evidence

                successor = verify_p04_evidence(
                    root,
                    verify_git_history=verify_git_history,
                    verify_p03_prerequisite=False,
                )
                passed = (
                    successor.get("status") == "PASS"
                    and successor.get("decision") == "S02_P04_EVIDENCE_VERIFIED"
                    and successor.get("next") == "S02/STAGE_REVIEW_READY_NOT_STARTED"
                )
                detail = {
                    "state": "P04_VERIFIED_SUCCESSOR" if passed else "INVALID_OR_PARTIAL_P04_SUCCESSOR",
                    "successor_summary": successor.get("summary"),
                    "index": p04,
                    "existing": existing,
                }
            except Exception as exc:
                passed = False
                detail = {
                    "state": "INVALID_OR_PARTIAL_P04_SUCCESSOR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "index": p04,
                    "existing": existing,
                }
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P03-P04-NOT-STARTED", passed, detail)


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
        ("S02P03-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S02P03-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
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

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S02P03-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S02P03-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
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
        _add(checks, "S02P03-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S02P03-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P03",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "OPEN_SOURCE_REUSE_AND_LICENSE_DECISIONS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
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
        "reuse_status": "RESEARCH_ONLY_NO_CODE_COPIED_OR_DEPENDENCY_ADDED",
        "license_status": "ENGINEERING_AUDIT_NOT_LEGAL_CLEARANCE",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "phase_status": "S02_P03_PASS" if status == "PASS" else "S02_P03_FAILED",
        "next": "S02/P04_READY_NOT_STARTED" if status == "PASS" else "S02/P03_REMEDIATION_REQUIRED",
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

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S02P03-FIXTURE-STRICT-JSON")
    matrix = _safe_load(root / REUSE_MATRIX_PATH, checks, "S02P03-MATRIX-STRICT-JSON")
    inventory = _safe_load(root / LICENSE_INVENTORY_PATH, checks, "S02P03-LICENSE-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S02P03-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S02P03-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S02P03-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S02P03-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S02P03-TRACEABILITY-STRICT-JSON")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "S02P03-CANONICAL-STRICT-JSON")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "S02P03-COSTS-STRICT-JSON")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S02P03-PARAMETERS-STRICT-JSON")
    baseline_matrix = _safe_load(
        root / "machine/facts/research_reuse_matrix.json", checks, "S02P03-BASELINE-REUSE-STRICT-JSON"
    )
    baseline_sources = _safe_load(root / "machine/facts/sources.json", checks, "S02P03-BASELINE-SOURCES-STRICT-JSON")

    _check_pinned_hashes(root, checks, hashes, _verify_git_history)
    import_markers = [
        Path("tests/__init__.py"),
        Path("tests/S00/__init__.py"),
        Path("tests/S01/__init__.py"),
        Path("tests/S02/__init__.py"),
    ]
    _add(
        checks,
        "S02P03-PYTEST-IMPORT-ISOLATION",
        all((root / path).is_file() for path in import_markers),
        [path.as_posix() for path in import_markers],
    )

    dictionaries = [fixture, matrix, inventory, roadmap, task_graph, canonical, costs, parameters, baseline_matrix]
    arrays = [requirements, acceptance, traceability, baseline_sources]
    if not all(isinstance(value, dict) for value in dictionaries) or not all(isinstance(value, list) for value in arrays):
        _add(checks, "S02P03-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S02P03-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S02P03-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        project_map = _check_reuse_matrix(matrix, fixture, baseline_matrix, baseline_sources, checks)
    except Exception as exc:
        project_map = {}
        _add(checks, "S02P03-MATRIX-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_license_inventory(inventory, project_map, fixture, checks)
    except Exception as exc:
        _add(checks, "S02P03-LICENSE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_fixture_vectors(fixture, checks)
    except Exception as exc:
        _add(checks, "S02P03-FIXTURE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_baseline_safety(canonical, costs, parameters, matrix, inventory, fixture, checks)
    except Exception as exc:
        _add(checks, "S02P03-BASELINE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    _add(
        checks,
        "S02P03-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS",
        not any(_contains_float(value) for value in [fixture, matrix, inventory]),
        "categorical decisions and hashes remain exact strings or integers",
    )
    _check_p02_prerequisite(root, checks, _verify_git_history)
    _check_s02_p04_not_started(root, checks, _verify_git_history)
    if require_external_reports:
        _check_runtime_reports(root, fixture, checks, hashes)
    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0))
    if result["summary"]["checks"] < minimum:
        _add(checks, "S02P03-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
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
        (REUSE_MATRIX_PATH.as_posix(), root / REUSE_MATRIX_PATH),
        (LICENSE_INVENTORY_PATH.as_posix(), root / LICENSE_INVENTORY_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (P02_EVIDENCE_PATH.as_posix(), root / P02_EVIDENCE_PATH),
        (P02_ROLLBACK_PATH.as_posix(), root / P02_ROLLBACK_PATH),
        ("machine/facts/research_reuse_matrix.json", root / "machine/facts/research_reuse_matrix.json"),
        ("machine/facts/sources.json", root / "machine/facts/sources.json"),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s02-p03-rollback-") as directory:
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
        "evidence_id": "EVD-S02-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_OPEN_SOURCE_REUSE_AUDIT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        REUSE_MATRIX_PATH,
        LICENSE_INVENTORY_PATH,
        FIXTURE_PATH,
        *[Path(relative) for relative in PINNED_BASELINE_HASHES],
        TEST_PATH,
        Path("tests/S02/P02_test.py"),
        Path("tests/S02/P01_test.py"),
        Path("tests/S02/__init__.py"),
        Path("abd_acceptance/open_source_reuse.py"),
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
            "evidence_id": "EVD-S02-P03-ROLLBACK",
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
        result["phase_status"] = "S02_P03_FAILED"
        result["next"] = "S02/P03_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S02-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P03",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S02-P03-01": REUSE_MATRIX_PATH.as_posix(),
            "ART-S02-P03-02": LICENSE_INVENTORY_PATH.as_posix(),
        },
        "p02_prerequisite": {
            "evidence": P02_EVIDENCE_PATH.as_posix(),
            "evidence_sha256": P02_EVIDENCE_SHA256,
            "rollback": P02_ROLLBACK_PATH.as_posix(),
            "rollback_sha256": P02_ROLLBACK_SHA256,
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S02/P03 freezes repository reuse and license evidence only; it installs no package and executes no model, strategy, provider interaction, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S02/P03_test.py --junitxml=machine/evidence/S02/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S02-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": dict(strict_json_load(root / FIXTURE_PATH)["expected_external_effect_boundary"]),
        "explicit_unknowns": [
            "GitHub license detection is an engineering input, not legal clearance or a complete dependency license audit.",
            "No transitive dependency, package build, runtime behavior, vulnerability or compatibility was evaluated because no candidate was installed.",
            "A repository code license does not authorize external API, website, account, data access, scraping, redistribution or paid service use.",
            "OddsPortal, The Odds API and odds-api.net service terms, data rights, current price, quota and Australian availability remain unverified.",
            "The unlicensed sportsbook-odds-scraper repository remains prohibited for code reuse unless a future verifiable license and new audit pass.",
            "No candidate proves all-observable-market coverage, source reliability, model quality, execution capacity, production readiness or actual return.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; no reuse decision may relax evidence or risk gates.",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S02-P03"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S02-P03 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S02/P04_READY_NOT_STARTED" if status == "PASS" else "S02/P03_REMEDIATION_REQUIRED"
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
    verify_p02_prerequisite: bool = True,
    verify_successor_state: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S02P03-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S02P03-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"

    if isinstance(evidence, dict):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S02-P03"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S02"
            and evidence.get("phase_id") == "P03"
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "OPEN_SOURCE_REUSE_AND_LICENSE_DECISIONS_FROZEN"
            and evidence.get("phase_status") == "S02_P03_PASS"
            and evidence.get("next") == "S02/P04_READY_NOT_STARTED"
            and evidence.get("artifacts")
            == {
                "ART-S02-P03-01": REUSE_MATRIX_PATH.as_posix(),
                "ART-S02-P03-02": LICENSE_INVENTORY_PATH.as_posix(),
            }
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S02P03-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            validation.get("status") == "PASS"
            and validation.get("decision") == "OPEN_SOURCE_REUSE_AND_LICENSE_DECISIONS_FROZEN"
            and validation.get("summary", {}).get("failed") == 0
            and validation.get("next") == "S02/P04_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S02P03-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        effects = evidence.get("external_effect_boundary", {})
        effects_ok = (
            effects.get("github_upload_performed") is False
            and effects.get("repository_cloned") is False
            and effects.get("package_installed") is False
            and effects.get("provider_or_cloud_account_accessed") is False
            and effects.get("provider_api_called") is False
            and effects.get("api_key_requested_or_used") is False
            and effects.get("incremental_cash_spent_aud") == "0.00"
            and effects.get("production_deployment_claimed") is False
            and effects.get("real_order_capability_present") is False
            and effects.get("model_or_strategy_executed") is False
            and effects.get("return_or_guarantee_claimed") is False
            and effects.get("s02_p04_started") is False
        )
        _add(checks, "S02P03-RECEIPT-NO-EXTERNAL-EFFECT", effects_ok, effects)

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
            "S02P03-RECEIPT-SIGNED-INPUTS-CURRENT",
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
        _add(checks, "S02P03-RECEIPT-REPORT-HASHES-CURRENT", not report_errors, report_errors or "all reports match")

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
            "S02P03-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_actual, "historical_phase_commit": historical_code},
        )
        rollback_binding = evidence.get("hashes", {}).get("rollback_evidence")
        _add(
            checks,
            "S02P03-RECEIPT-ROLLBACK-HASH-BINDING",
            rollback_binding == rollback_hash,
            {"expected": rollback_binding, "actual": rollback_hash},
        )
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        _add(
            checks,
            "S02P03-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
            str(root) not in rendered and ("/" + "Users/") not in rendered and ("/private/" + "var/") not in rendered,
            "portable evidence",
        )
    else:
        for check_id in [
            "S02P03-RECEIPT-EVIDENCE-INTEGRITY",
            "S02P03-RECEIPT-VALIDATION-ALL-PASS",
            "S02P03-RECEIPT-NO-EXTERNAL-EFFECT",
            "S02P03-RECEIPT-SIGNED-INPUTS-CURRENT",
            "S02P03-RECEIPT-REPORT-HASHES-CURRENT",
            "S02P03-RECEIPT-CODE-HASH-CURRENT",
            "S02P03-RECEIPT-ROLLBACK-HASH-BINDING",
            "S02P03-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
        ]:
            _add(checks, check_id, False, "evidence unavailable")

    if isinstance(rollback, dict):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S02-P03-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("fixed_clock") == FIXED_CLOCK
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and len(rollback.get("artifacts", {})) == 8
            and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
        )
        _add(checks, "S02P03-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S02P03-RECEIPT-ROLLBACK-INTEGRITY", False, "rollback unavailable")

    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p03 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P03"]
        index_ok = (
            len(p03) == 1
            and p03[0].get("status") == "PASS"
            and p03[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and p03[0].get("artifact_sha256") == evidence_hash
            and p03[0].get("next") == "S02/P04_READY_NOT_STARTED"
        )
        _add(checks, "S02P03-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, p03)
    except Exception as exc:
        _add(checks, "S02P03-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    if verify_p02_prerequisite:
        _check_p02_prerequisite(root, checks, verify_git_history)
    if verify_successor_state:
        _check_s02_p04_not_started(root, checks, verify_git_history)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S02-P03",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S02_P03_EVIDENCE_VERIFIED" if not failed else "S02_P03_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for row in checks if row["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S02/P04_READY_NOT_STARTED" if not failed else "S02/P03_REMEDIATION_REQUIRED",
    }
