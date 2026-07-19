from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .delivery import verify_stage0_delivery


CONTRACT_ID = "AC-S01-P03"
REQUIREMENT_ID = "REQ-S01-P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

REQUIREMENTS_PATH = Path("requirements.json")
SCOPE_PATH = Path("scope_boundary.json")
FLOWS_PATH = Path("business_flows.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S01_P03.json")
JUNIT_PATH = Path("machine/evidence/S01/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S01/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S01-P02_rollback.json")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

P02_COMMIT = "214232879e068c9703695ab098e92e010ac2db7f"
P02_EVIDENCE_SHA256 = "7d9471a303c23c34e567e9eee394be2f01bc7025a7ad74915aad6f21e5427ac5"
P02_ROLLBACK_SHA256 = "6608dd6bb06e11319d39b5c4757d68eccb7834717dd9a4139b2811c9b8f398df"

PINNED_SOURCE_HASHES = {
    "assumption_register.json": "b51e164e16fcf4c3cbd0708565583f91f7b5bf08f6a325d65a288872b03d9426",
    "customer_faq.md": "c004e375b0924564e1453885da5e7c286e15cc1924103524097fc4c58af22cb3",
    "customer_outcomes.json": "54ea272e26be24f88dc7344b4b2ea9d3268a488622214bc1790fe229d791b28d",
    P02_EVIDENCE_PATH.as_posix(): P02_EVIDENCE_SHA256,
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/authorization_matrix.json": "f7cf34a3d60e37365c3090fac75f40e0b390ec211976393e7148d597a2f4affe",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/decision_prerequisites.json": "e9b54b985aff11faceaa7a2d6e6db42e070c96c0a8286a348ff767bc62921ccc",
    "machine/facts/degraded_mode_contract.json": "823a92ee03a468aaa1df6a4706aa0f1af3472b7f9c96c530877578f2f072d02f",
    "machine/facts/email_ingestion.json": "7d40a142a482b5179aa6bb11fa0694fa5576a770f0b2a5af751615da3dea53cd",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/provider_contracts.json": "a9d0fd864fad7ac4c14ec6a324d447abbc8497b256a232f9ca04b3115b15364a",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/risk_register.json": "6f50e159f000ac4a1c714d08cff239e524a58c679cd77c05d7b4944a7b602888",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/security_assurance.json": "03543d4356f3718047293329d6b4e7cc3c14735b521e47f03079ff101f3205dd",
    "machine/facts/strategy_spec.json": "d77f047219632145a71f0f2932149654ae24205bbdc291fa604b93bfcff5117d",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}

PINNED_PHASE_HASHES = {
    REQUIREMENTS_PATH.as_posix(): "ec1d098d5855b5835fbef315e276852454a7a43d66accd5a4ea5a193cd99f68d",
    SCOPE_PATH.as_posix(): "b1efc644928df96357a0eb65583c1ff100fcdc35239fde1b07e170411528a383",
    FLOWS_PATH.as_posix(): "5b5da6955582f383980186a6f69ff089139ae71b919e09bb2ade9b39d3026648",
    FIXTURE_PATH.as_posix(): "cc077019262accae8982f4892f9b7752c88926db675b433ef47f14d173d94761",
}

PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

P02_SIGNED_ARTIFACT_HASHES = {
    "customer_faq.md": "c004e375b0924564e1453885da5e7c286e15cc1924103524097fc4c58af22cb3",
    "assumption_register.json": "b51e164e16fcf4c3cbd0708565583f91f7b5bf08f6a325d65a288872b03d9426",
    "machine/tests/fixtures/S01_P02.json": "f9f1183b9635c86c862e88f4f6fd26ac33dade5a10dd5c907cfc7a48fece9ccb",
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


def resolve_trace_default(**gates: bool) -> str:
    expected = {
        "unique_id",
        "source_pointers_resolve",
        "module_route_unique",
        "acceptance_route_valid",
        "business_flow_route_present",
    }
    if set(gates) != expected or any(type(gates.get(name)) is not bool for name in expected):
        return "BLOCK_MALFORMED_TRACE_GATE_SET"
    return "TRACEABLE" if all(gates.values()) else "BLOCK_UNTRACEABLE_REQUIREMENT"


def resolve_stability_default(actions: Sequence[str]) -> str:
    if isinstance(actions, (str, bytes)) or len(actions) != 4:
        return "NO_RECOMMENDATION_MALFORMED_STABILITY_VECTOR"
    if any(action not in {"RECOMMENDATION", "NO_RECOMMENDATION"} for action in actions):
        return "NO_RECOMMENDATION_MALFORMED_STABILITY_VECTOR"
    if len(set(actions)) != 1:
        return "NO_RECOMMENDATION_UNSTABLE"
    if actions[0] == "RECOMMENDATION":
        return "STABLE_RECOMMENDATION"
    return "STABLE_NO_RECOMMENDATION"


def _single_source_check(root: Path, relative: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(relative.name)
        if not {".git", ".venv", ".pytest_cache", "__pycache__"}.intersection(path.parts)
    )
    expected = [relative.as_posix()]
    if relative == REQUIREMENTS_PATH:
        expected = ["machine/facts/requirements.json", REQUIREMENTS_PATH.as_posix()]
    _add(checks, "S01P03-SINGLE-%s" % relative.stem.upper(), candidates == expected, candidates)


def _check_id_suffix(relative: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", relative.upper()).strip("-")


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in {**PINNED_SOURCE_HASHES, **PINNED_PHASE_HASHES}.items():
        check_id = "S01P03-HASH-%s" % _check_id_suffix(relative)
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                check_id,
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, check_id, False, str(exc))
    for relative, expected in PINNED_REPO_HASHES.items():
        check_id = "S01P03-HASH-%s" % _check_id_suffix(relative)
        try:
            actual = sha256_file(root.parent / relative)
            hashes[relative] = actual
            _add(
                checks,
                check_id,
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, check_id, False, str(exc))


def _check_continuous_workflow(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        text = (root.parent / CONTINUOUS_WORKFLOW_PATH).read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S01P03-CONTINUOUS-CI", False, str(exc))
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
    _add(checks, "S01P03-CONTINUOUS-CI", passed, refs)


def _check_taskpack_contract(
    roadmap: Mapping[str, Any],
    source_requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        stage = [row for row in roadmap.get("stages", []) if row.get("id") == "S01"]
        phases = [row for row in stage[0].get("phases", []) if row.get("id") == "P03"] if len(stage) == 1 else []
        phase = phases[0] if len(phases) == 1 else {}
        roadmap_ok = (
            phase.get("title") == "需求与边界"
            and phase.get("objective") == "建立业务线、功能模块、范围、非目标和错误路径。"
            and phase.get("outputs") == [REQUIREMENTS_PATH.as_posix(), SCOPE_PATH.as_posix(), FLOWS_PATH.as_posix()]
            and phase.get("pass_gate") == "每条需求唯一且可追踪。"
            and phase.get("hours") == {"low": 3, "likely": 4, "high": 6}
        )
    except Exception as exc:
        phase = {"error": "%s: %s" % (type(exc).__name__, exc)}
        roadmap_ok = False
    _add(checks, "S01P03-ROADMAP-EXACT", roadmap_ok, phase)

    requirement = _find_by_id(list(source_requirements), REQUIREMENT_ID)
    requirement_ok = isinstance(requirement, dict) and (
        requirement.get("stage_id") == "S01"
        and requirement.get("phase_id") == "P03"
        and requirement.get("value") == "建立业务线、功能模块、范围、非目标和错误路径。"
        and requirement.get("scope") == [REQUIREMENTS_PATH.as_posix(), SCOPE_PATH.as_posix(), FLOWS_PATH.as_posix()]
        and requirement.get("non_goals") == NON_GOALS
        and requirement.get("target") == "每条需求唯一且可追踪。"
        and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        and requirement.get("owner_input_required_during_development") is False
    )
    _add(checks, "S01P03-REQUIREMENT-EXACT", requirement_ok, requirement)

    contract = _find_by_id(list(acceptance), CONTRACT_ID)
    contract_ok = isinstance(contract, dict) and (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("oracle", {}).get("type") == "EXECUTABLE"
        and contract.get("oracle", {}).get("command")
        == "python -m abd_acceptance --contract AC-S01-P03 --evidence machine/evidence"
        and contract.get("oracle", {}).get("rule") == "每条需求唯一且可追踪。"
        and contract.get("pass_gate") == "每条需求唯一且可追踪。"
        and [row.get("id") for row in contract.get("tests", [])]
        == ["TEST-S01-P03", "TEST-S01-P03-BOUNDARY", "TEST-S01-P03-REPLAY"]
        and "新增现金支出将超过A$0" in contract.get("stop_condition", [])
    )
    _add(checks, "S01P03-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [
        row
        for row in task_graph.get("tasks", [])
        if isinstance(row, dict) and str(row.get("id", "")).startswith("T-S01-P03-")
    ]
    expected_ids = ["T-S01-P03-01", "T-S01-P03-02", "T-S01-P03-03"]
    tasks_ok = (
        [row.get("id") for row in tasks] == expected_ids
        and [row.get("depends_on") for row in tasks]
        == [["T-S01-P02-03"], ["T-S01-P03-01"], ["T-S01-P03-02"]]
        and all(row.get("auto_advance_on_pass") is True for row in tasks)
        and all(row.get("owner_input_required") is False for row in tasks)
        and tasks[0].get("outputs") == [REQUIREMENTS_PATH.as_posix(), SCOPE_PATH.as_posix(), FLOWS_PATH.as_posix()]
        and tasks[1].get("outputs") == ["tests/S01/P03_test.py", FIXTURE_PATH.as_posix()]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
    )
    _add(checks, "S01P03-TASK-CHAIN-EXACT", tasks_ok, [row.get("id") for row in tasks])

    trace = next(
        (row for row in traceability if isinstance(row, dict) and row.get("requirement_id") == REQUIREMENT_ID),
        None,
    )
    trace_ok = isinstance(trace, dict) and (
        trace.get("acceptance_criteria_id") == CONTRACT_ID
        and trace.get("task_ids") == expected_ids
        and trace.get("test_ids") == ["TEST-S01-P03", "TEST-S01-P03-BOUNDARY", "TEST-S01-P03-REPLAY"]
        and trace.get("evidence_id") == "EVD-S01-P03"
        and trace.get("artifact_ids") == ["ART-S01-P03-01", "ART-S01-P03-02", "ART-S01-P03-03"]
    )
    _add(checks, "S01P03-TRACEABILITY-EXACT", trace_ok, trace)


def _check_requirements_artifact(
    root: Path,
    artifact: Mapping[str, Any],
    fixture: Mapping[str, Any],
    acceptance: Sequence[Mapping[str, Any]],
    source_documents: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        artifact.get("schema_version") == "1.0.0"
        and artifact.get("artifact_id") == "ART-S01-P03-01"
        and artifact.get("requirement_id") == REQUIREMENT_ID
        and artifact.get("acceptance_contract_id") == CONTRACT_ID
        and artifact.get("product_version") == VERSION
        and artifact.get("fixed_at") == FIXED_CLOCK
        and artifact.get("status") == "PRODUCT_REQUIREMENTS_CONTRACT_NOT_IMPLEMENTATION_PROOF"
        and artifact.get("next_on_acceptance_pass") == "S01/P04_READY_NOT_STARTED"
        and artifact.get("non_goals") == NON_GOALS
    )
    _add(checks, "S01P03-REQUIREMENTS-TOP-LEVEL", top_ok, artifact.get("status"))

    try:
        actual = {relative: sha256_file(root / relative) for relative in PINNED_SOURCE_HASHES}
        bindings_ok = artifact.get("source_bindings") == PINNED_SOURCE_HASHES and actual == PINNED_SOURCE_HASHES
    except Exception as exc:
        bindings_ok = False
        actual = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(
        checks,
        "S01P03-REQUIREMENTS-SOURCE-BINDINGS",
        bindings_ok,
        {"declared": artifact.get("source_bindings"), "actual": actual},
    )

    rows = artifact.get("requirements", [])
    rows_ok = isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
    ids = [row.get("id") for row in rows] if rows_ok else []
    expected_ids = fixture.get("expected_requirement_ids", [])
    id_ok = (
        rows_ok
        and ids == expected_ids
        and not _duplicates(ids)
        and all(isinstance(item, str) and re.fullmatch(r"ABD-PRD-REQ-[0-9]{3}", item) for item in ids)
        and artifact.get("traceability_contract", {}).get("requirement_count") == len(expected_ids)
        and artifact.get("traceability_contract", {}).get("orphan_requirements_allowed") == 0
        and artifact.get("traceability_contract", {}).get("duplicate_requirements_allowed") == 0
    )
    _add(checks, "S01P03-REQUIREMENT-IDS-UNIQUE-EXACT", id_ok, ids)

    routes = [
        [row.get("id"), row.get("business_line_id"), row.get("module_id"), row.get("primary_acceptance_contract_id")]
        for row in rows
    ] if rows_ok else []
    primary_ids = [row[3] for row in routes]
    route_ok = routes == fixture.get("expected_requirement_routes") and not _duplicates(primary_ids)
    _add(checks, "S01P03-REQUIREMENT-ROUTES-UNIQUE-EXACT", route_ok, routes)

    accepted_ids = {row.get("id") for row in acceptance if isinstance(row, dict)}
    row_shape_ok = rows_ok
    acceptance_ok = rows_ok
    pointer_ok = rows_ok
    pointer_detail: Dict[str, Any] = {}
    for row in rows if rows_ok else []:
        required_strings = [
            "id",
            "title",
            "business_line_id",
            "module_id",
            "type",
            "priority",
            "statement",
            "user_value",
            "failure_default",
            "current_evidence_status",
            "primary_acceptance_contract_id",
        ]
        row_shape_ok = row_shape_ok and all(isinstance(row.get(key), str) and row.get(key) for key in required_strings)
        supports = row.get("supporting_acceptance_contract_ids")
        row_acceptance_ids = [row.get("primary_acceptance_contract_id"), *(supports if isinstance(supports, list) else [])]
        acceptance_ok = (
            acceptance_ok
            and isinstance(supports, list)
            and bool(supports)
            and not _duplicates(row_acceptance_ids)
            and all(item in accepted_ids for item in row_acceptance_ids)
        )
        evidence = row.get("source_evidence")
        row_pointer_ok = isinstance(evidence, list) and bool(evidence) and all(isinstance(item, dict) for item in evidence)
        failures: List[str] = []
        for item in evidence if isinstance(evidence, list) else []:
            path = item.get("path")
            pointers = item.get("pointers")
            if path not in PINNED_SOURCE_HASHES or not isinstance(pointers, list) or not pointers:
                failures.append("invalid-source-metadata:%r" % path)
                continue
            document = source_documents.get(path)
            if document is None:
                failures.append("source-not-json-or-unavailable:%s" % path)
                continue
            for pointer in pointers:
                try:
                    _json_pointer(document, pointer)
                except Exception as exc:
                    failures.append("%s%s:%s" % (path, pointer, type(exc).__name__))
        row_pointer_ok = row_pointer_ok and not failures
        pointer_ok = pointer_ok and row_pointer_ok
        pointer_detail[str(row.get("id"))] = failures
    _add(checks, "S01P03-REQUIREMENT-ROWS-COMPLETE", row_shape_ok, len(rows) if rows_ok else "malformed")
    _add(checks, "S01P03-ACCEPTANCE-ROUTES-VALID-UNIQUE", acceptance_ok, sorted(accepted_ids))
    _add(checks, "S01P03-SOURCE-POINTERS-RESOLVE", pointer_ok, pointer_detail)

    claim = artifact.get("claim_boundaries", {})
    claim_ok = (
        claim.get("requirements_are_implementation_proof") is False
        and claim.get("production_deployment_claimed") is False
        and claim.get("all_market_coverage_claimed") is False
        and claim.get("external_account_or_api_accessed") is False
        and claim.get("gmail_connected_claimed") is False
        and claim.get("real_order_or_return_claimed") is False
        and claim.get("return_guaranteed") is False
        and claim.get("incremental_cash_spent_aud") == "0.00"
    )
    _add(checks, "S01P03-REQUIREMENTS-NO-FALSE-CURRENT-CLAIMS", claim_ok, claim)

    text_by_id = {row.get("id"): json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows if isinstance(row, dict)}
    required_terms = {
        "ABD-PRD-REQ-001": ["Australia/Sydney", "中文", "不建议"],
        "ABD-PRD-REQ-002": ["禁止沉默失败", "安全下一步"],
        "ABD-PRD-REQ-003": ["不得包含提交、确认或重试真实订单", "用户"],
        "ABD-PRD-REQ-004": ["OVH Singapore VPS-1", "Cloudflare Access", "单主机不得宣称物理零中断"],
        "ABD-PRD-REQ-005": ["A$0", "A$300", "不得新增"],
        "ABD-PRD-REQ-006": ["全部可观察市场", "不得被误写为全部市场可建议"],
        "ABD-PRD-REQ-007": ["版本化来源合同", "A$0"],
        "ABD-PRD-REQ-008": ["gmail.modify", "state/PKCE", "未授权只关闭邮件模块"],
        "ABD-PRD-REQ-009": [".eml", "SHA-256", "永久删除能力必须不存在"],
        "ABD-PRD-REQ-010": ["未来信息容忍度为0", "模型版本"],
        "ABD-PRD-REQ-011": ["建议账本", "实际资金账本", "不得替代真实资金收益"],
        "ABD-PRD-REQ-012": ["四种去水", "市场共识", "强先验"],
        "ABD-PRD-REQ-013": ["残差", "时间外增量", "权重必须归零"],
        "ABD-PRD-REQ-014": ["第10百分位", "校准", "置信下界"],
        "ABD-PRD-REQ-015": ["万分之一", "赔率任一不利扰动", "不建议"],
        "ABD-PRD-REQ-016": ["证据层", "最低赔率", "唯一平台"],
        "ABD-PRD-REQ-017": ["受限凯利", "追损", "暴露"],
        "ABD-PRD-REQ-018": ["A$300×1.3^n", "6月", "12个完整月", "UNVERIFIED"],
        "ABD-PRD-REQ-019": ["不可信数据", "秘密", "最小权限"],
        "ABD-PRD-REQ-020": ["软件", "模型", "独立通过"],
        "ABD-PRD-REQ-021": ["功能开关", "自动回滚", "正式可用声明"],
    }
    missing_terms = {
        item_id: [term for term in terms if term not in text_by_id.get(item_id, "")]
        for item_id, terms in required_terms.items()
    }
    missing_terms = {item_id: terms for item_id, terms in missing_terms.items() if terms}
    _add(checks, "S01P03-REQUIRED-SEMANTICS-PRESENT", not missing_terms, missing_terms or "all present")


def _check_scope_artifact(
    scope: Mapping[str, Any],
    fixture: Mapping[str, Any],
    requirement_ids: Sequence[str],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        scope.get("schema_version") == "1.0.0"
        and scope.get("artifact_id") == "ART-S01-P03-02"
        and scope.get("requirement_id") == REQUIREMENT_ID
        and scope.get("acceptance_contract_id") == CONTRACT_ID
        and scope.get("product_version") == VERSION
        and scope.get("fixed_at") == FIXED_CLOCK
        and scope.get("status") == "SCOPE_BOUNDARY_CONTRACT_NOT_CAPABILITY_PROOF"
        and scope.get("requirements_artifact") == REQUIREMENTS_PATH.as_posix()
        and scope.get("next_on_acceptance_pass") == "S01/P04_READY_NOT_STARTED"
    )
    _add(checks, "S01P03-SCOPE-TOP-LEVEL", top_ok, scope.get("status"))

    lines = scope.get("business_lines", [])
    modules = scope.get("functional_modules", [])
    lines_ok = isinstance(lines, list) and all(isinstance(row, dict) for row in lines)
    modules_ok = isinstance(modules, list) and all(isinstance(row, dict) for row in modules)
    line_ids = [row.get("id") for row in lines] if lines_ok else []
    module_ids = [row.get("id") for row in modules] if modules_ok else []
    shape_ok = (
        lines_ok
        and modules_ok
        and line_ids == fixture.get("expected_business_line_ids")
        and module_ids == fixture.get("expected_module_ids")
        and not _duplicates(line_ids)
        and not _duplicates(module_ids)
        and all(row.get("name_zh") and row.get("objective") and isinstance(row.get("module_ids"), list) for row in lines)
        and all(
            row.get("business_line_id") in line_ids
            and row.get("name_zh")
            and row.get("scope_class")
            and row.get("current_status")
            and isinstance(row.get("requirement_ids"), list)
            and row.get("requirement_ids")
            for row in modules
        )
    )
    _add(checks, "S01P03-BUSINESS-LINES-MODULES-EXACT", shape_ok, {"lines": line_ids, "modules": module_ids})

    line_modules = {row.get("id"): row.get("module_ids") for row in lines if isinstance(row, dict)}
    actual_by_line = {
        line_id: [row.get("id") for row in modules if row.get("business_line_id") == line_id]
        for line_id in line_ids
    }
    hierarchy_ok = line_modules == actual_by_line
    _add(checks, "S01P03-BUSINESS-LINE-MODULE-HIERARCHY", hierarchy_ok, actual_by_line)

    assigned = [item for row in modules for item in row.get("requirement_ids", [])] if modules_ok else []
    coverage_ok = assigned == list(requirement_ids) and not _duplicates(assigned)
    _add(checks, "S01P03-EACH-REQUIREMENT-EXACTLY-ONE-MODULE", coverage_ok, assigned)

    invariants = scope.get("hard_invariants", [])
    out = scope.get("explicit_out_of_scope", [])
    conditional = scope.get("conditional_capabilities", [])
    expected = fixture.get("expected_counts", {})
    boundary_rows_ok = (
        isinstance(invariants, list)
        and len(invariants) == expected.get("hard_invariants")
        and [row.get("id") for row in invariants] == ["BOUNDARY-INV-%03d" % number for number in range(1, 11)]
        and all(row.get("rule") and row.get("requirement_ids") for row in invariants)
        and all(set(row.get("requirement_ids", [])).issubset(set(requirement_ids)) for row in invariants)
        and isinstance(out, list)
        and len(out) == expected.get("out_of_scope")
        and [row.get("id") for row in out] == ["OUT-%03d" % number for number in range(1, 9)]
        and all(row.get("capability") and row.get("reason") and row.get("default") for row in out)
        and isinstance(conditional, list)
        and len(conditional) == expected.get("conditional_capabilities")
        and [row.get("id") for row in conditional] == ["COND-%03d" % number for number in range(1, 7)]
        and all(row.get("capability") and row.get("current_status") and row.get("activation") and row.get("unknown_default") for row in conditional)
    )
    _add(checks, "S01P03-INVARIANTS-OUTSCOPE-CONDITIONAL-EXACT", boundary_rows_ok, expected)

    out_text = json.dumps(out, ensure_ascii=False, sort_keys=True)
    prohibited_ok = all(
        term in out_text
        for term in ["自动提交、确认或重试真实订单", "保证收益", "付费赔率接口", "Gmail永久删除", "LLM", "真实收益"]
    )
    _add(checks, "S01P03-EXPLICIT-NON-GOALS-FAIL-CLOSED", prohibited_ok, out_text)

    execution = scope.get("s01_p03_execution_boundary", {})
    execution_ok = (
        execution.get("requirements_only") is True
        and execution.get("runtime_code_implemented") is False
        and execution.get("external_account_or_api_accessed") is False
        and execution.get("production_deployed") is False
        and execution.get("real_order_capability_present") is False
        and execution.get("gmail_connected") is False
        and execution.get("incremental_cash_spent_aud") == "0.00"
        and execution.get("return_or_guarantee_claimed") is False
        and execution.get("p04_artifacts_created") is False
    )
    _add(checks, "S01P03-SCOPE-NO-EXTERNAL-EFFECTS", execution_ok, execution)


def _check_flows_artifact(
    flows_artifact: Mapping[str, Any],
    fixture: Mapping[str, Any],
    requirement_ids: Sequence[str],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        flows_artifact.get("schema_version") == "1.0.0"
        and flows_artifact.get("artifact_id") == "ART-S01-P03-03"
        and flows_artifact.get("requirement_id") == REQUIREMENT_ID
        and flows_artifact.get("acceptance_contract_id") == CONTRACT_ID
        and flows_artifact.get("product_version") == VERSION
        and flows_artifact.get("fixed_at") == FIXED_CLOCK
        and flows_artifact.get("status") == "BUSINESS_FLOW_CONTRACT_NOT_RUNTIME_PROOF"
        and flows_artifact.get("requirements_artifact") == REQUIREMENTS_PATH.as_posix()
        and flows_artifact.get("scope_artifact") == SCOPE_PATH.as_posix()
        and flows_artifact.get("next_on_acceptance_pass") == "S01/P04_READY_NOT_STARTED"
    )
    _add(checks, "S01P03-FLOWS-TOP-LEVEL", top_ok, flows_artifact.get("status"))

    flows = flows_artifact.get("flows", [])
    errors = flows_artifact.get("error_paths", [])
    rows_ok = isinstance(flows, list) and all(isinstance(row, dict) for row in flows)
    errors_ok = isinstance(errors, list) and all(isinstance(row, dict) for row in errors)
    flow_ids = [row.get("id") for row in flows] if rows_ok else []
    error_ids = [row.get("id") for row in errors] if errors_ok else []
    expected = fixture.get("expected_counts", {})
    identity_ok = (
        rows_ok
        and errors_ok
        and flow_ids == fixture.get("expected_flow_ids")
        and error_ids == fixture.get("expected_error_path_ids")
        and not _duplicates(flow_ids)
        and not _duplicates(error_ids)
        and len(flows) == expected.get("flows")
        and len(errors) == expected.get("error_paths")
    )
    _add(checks, "S01P03-FLOW-ERROR-IDS-UNIQUE-EXACT", identity_ok, {"flows": flow_ids, "errors": error_ids})

    allowed = flows_artifact.get("allowed_terminal_states", [])
    step_ids: List[str] = []
    flow_requirement_refs: List[str] = []
    flow_shape_ok = rows_ok and isinstance(allowed, list) and not _duplicates(allowed)
    for flow in flows if rows_ok else []:
        steps = flow.get("steps", [])
        flow_shape_ok = (
            flow_shape_ok
            and bool(flow.get("name_zh"))
            and bool(flow.get("trigger"))
            and isinstance(flow.get("preconditions"), list)
            and bool(flow.get("preconditions"))
            and isinstance(steps, list)
            and bool(steps)
            and flow.get("success_terminal") in allowed
            and flow.get("failure_terminal") in allowed
            and flow.get("external_effect_in_s01_p03") is False
        )
        for step in steps if isinstance(steps, list) else []:
            step_ids.append(step.get("id"))
            refs = step.get("requirement_ids", [])
            flow_requirement_refs.extend(refs if isinstance(refs, list) else [])
            flow_shape_ok = (
                flow_shape_ok
                and isinstance(step, dict)
                and bool(step.get("id"))
                and bool(step.get("actor"))
                and bool(step.get("action"))
                and bool(step.get("on_failure"))
                and isinstance(refs, list)
                and bool(refs)
                and set(refs).issubset(set(requirement_ids))
            )
    flow_shape_ok = (
        flow_shape_ok
        and len(step_ids) == expected.get("flow_steps")
        and not _duplicates(step_ids)
        and set(flow_requirement_refs) == set(requirement_ids)
    )
    _add(checks, "S01P03-FLOW-STEPS-TRACE-ALL-REQUIREMENTS", flow_shape_ok, {"steps": step_ids, "covered": sorted(set(flow_requirement_refs))})

    error_flow_refs: List[str] = []
    error_requirement_refs: List[str] = []
    error_shape_ok = errors_ok
    for row in errors if errors_ok else []:
        affected = row.get("affected_flow_ids", [])
        refs = row.get("requirement_ids", [])
        error_flow_refs.extend(affected if isinstance(affected, list) else [])
        error_requirement_refs.extend(refs if isinstance(refs, list) else [])
        error_shape_ok = (
            error_shape_ok
            and bool(row.get("trigger"))
            and isinstance(affected, list)
            and bool(affected)
            and set(affected).issubset(set(flow_ids))
            and isinstance(refs, list)
            and bool(refs)
            and set(refs).issubset(set(requirement_ids))
            and bool(row.get("safe_action"))
            and bool(row.get("forbidden_action"))
            and row.get("safe_action") != row.get("forbidden_action")
        )
    error_shape_ok = error_shape_ok and set(error_flow_refs) == set(flow_ids)
    _add(checks, "S01P03-EVERY-FLOW-HAS-SAFE-ERROR-PATH", error_shape_ok, sorted(set(error_flow_refs)))

    summary = flows_artifact.get("traceability_summary", {})
    summary_ok = (
        summary.get("requirement_count") == expected.get("requirements")
        and summary.get("flow_count") == expected.get("flows")
        and summary.get("error_path_count") == expected.get("error_paths")
        and summary.get("orphan_requirements_allowed") == 0
        and summary.get("duplicate_step_ids_allowed") == 0
        and summary.get("unknown_terminal_states_allowed") == 0
    )
    _add(checks, "S01P03-FLOW-TRACEABILITY-SUMMARY-EXACT", summary_ok, summary)

    boundary = flows_artifact.get("s01_p03_execution_boundary", {})
    boundary_ok = (
        boundary.get("runtime_flow_executed") is False
        and boundary.get("external_account_or_api_accessed") is False
        and boundary.get("production_deployed") is False
        and boundary.get("real_order_submitted") is False
        and boundary.get("gmail_message_read_or_moved") is False
        and boundary.get("incremental_cash_spent_aud") == "0.00"
        and boundary.get("return_or_guarantee_claimed") is False
        and boundary.get("p04_artifacts_created") is False
    )
    _add(checks, "S01P03-FLOWS-NO-RUNTIME-OR-EXTERNAL-EFFECT", boundary_ok, boundary)


def _check_cross_artifact_traceability(
    requirements_artifact: Mapping[str, Any],
    scope: Mapping[str, Any],
    flows: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    requirements = requirements_artifact.get("requirements", [])
    modules = scope.get("functional_modules", [])
    flow_rows = flows.get("flows", [])
    if not all(isinstance(value, list) for value in (requirements, modules, flow_rows)):
        _add(checks, "S01P03-CROSS-ARTIFACT-TRACEABILITY", False, "malformed arrays")
        return
    module_routes = {
        requirement_id: (module.get("business_line_id"), module.get("id"))
        for module in modules
        if isinstance(module, dict)
        for requirement_id in module.get("requirement_ids", [])
    }
    flow_routes = {
        requirement_id
        for flow in flow_rows
        if isinstance(flow, dict)
        for step in flow.get("steps", [])
        if isinstance(step, dict)
        for requirement_id in step.get("requirement_ids", [])
    }
    result = {}
    passed = True
    for row in requirements:
        item_id = row.get("id")
        expected_route = (row.get("business_line_id"), row.get("module_id"))
        gates = {
            "unique_id": sum(1 for item in requirements if item.get("id") == item_id) == 1,
            "source_pointers_resolve": bool(row.get("source_evidence")),
            "module_route_unique": module_routes.get(item_id) == expected_route,
            "acceptance_route_valid": bool(row.get("primary_acceptance_contract_id")),
            "business_flow_route_present": item_id in flow_routes,
        }
        decision = resolve_trace_default(**gates)
        result[str(item_id)] = decision
        passed = passed and decision == "TRACEABLE"
    _add(checks, "S01P03-CROSS-ARTIFACT-TRACEABILITY", passed, result)


def _verify_p02_prerequisite(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    verify_git_history: bool,
) -> None:
    evidence = _safe_load(root / P02_EVIDENCE_PATH, checks, "S01P03-P02-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / P02_ROLLBACK_PATH, checks, "S01P03-P02-ROLLBACK-STRICT-JSON")
    if not isinstance(evidence, dict) or not isinstance(rollback, dict):
        _add(checks, "S01P03-P02-IMMUTABLE-RECEIPT", False, "receipt unavailable")
        return
    try:
        evidence_hash = sha256_file(root / P02_EVIDENCE_PATH)
        rollback_hash = sha256_file(root / P02_ROLLBACK_PATH)
        hashes[P02_EVIDENCE_PATH.as_posix()] = evidence_hash
        hashes[P02_ROLLBACK_PATH.as_posix()] = rollback_hash
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        integrity_ok = decision_hash == _sha256_bytes(_json_bytes(unsigned))
        receipt_ok = (
            evidence_hash == P02_EVIDENCE_SHA256
            and rollback_hash == P02_ROLLBACK_SHA256
            and evidence.get("evidence_id") == "EVD-S01-P02"
            and evidence.get("contract_id") == "AC-S01-P02"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "FAQ_AND_ASSUMPTIONS_FROZEN"
            and evidence.get("phase_status") == "S01_P02_PASS"
            and evidence.get("next") == "S01/P03_READY_NOT_STARTED"
            and evidence.get("artifacts")
            == {"ART-S01-P02-01": "customer_faq.md", "ART-S01-P02-02": "assumption_register.json"}
            and evidence.get("hashes", {}).get("rollback_evidence") == P02_ROLLBACK_SHA256
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
        _add(checks, "S01P03-P02-RECEIPT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _add(
        checks,
        "S01P03-P02-IMMUTABLE-RECEIPT",
        receipt_ok,
        {"evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "decision_integrity": integrity_ok},
    )

    signed_inputs = evidence.get("hashes", {}).get("inputs", {})
    artifact_ok = isinstance(signed_inputs, dict)
    artifact_detail = {}
    for relative, expected in P02_SIGNED_ARTIFACT_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
        signed = signed_inputs.get(relative) if isinstance(signed_inputs, dict) else None
        row_ok = actual == expected and signed == expected
        artifact_detail[relative] = {"expected": expected, "signed": signed, "actual": actual}
        artifact_ok = artifact_ok and row_ok
    _add(checks, "S01P03-P02-SIGNED-ARTIFACTS", artifact_ok, artifact_detail)

    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p02_rows = [row for row in rows if row.get("id") == "INDEX-AC-S01-P02"]
        index_ok = (
            len(p02_rows) == 1
            and p02_rows[0].get("status") == "PASS"
            and p02_rows[0].get("artifact_sha256") == P02_EVIDENCE_SHA256
            and p02_rows[0].get("actual_artifact") == P02_EVIDENCE_PATH.as_posix()
            and p02_rows[0].get("next") == "S01/P03_READY_NOT_STARTED"
        )
    except Exception as exc:
        p02_rows = []
        index_ok = False
        _add(checks, "S01P03-P02-INDEX-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _add(checks, "S01P03-P02-EVIDENCE-INDEX", index_ok, p02_rows)

    stage0 = verify_stage0_delivery(root, verify_git_history=verify_git_history)
    _add(
        checks,
        "S01P03-STAGE0-DELIVERY-CHAIN",
        stage0.get("status") == "PASS" and stage0.get("next") == "S01/P01_READY_NOT_STARTED",
        stage0.get("summary"),
    )
    hashes.update(stage0.get("hashes", {}))

    if verify_git_history:
        try:
            resolved = subprocess.run(
                ["git", "-C", str(root.parent), "rev-parse", "%s^{commit}" % P02_COMMIT],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            ancestor = subprocess.run(
                ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", P02_COMMIT, "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            git_ok = resolved.returncode == 0 and resolved.stdout.strip() == P02_COMMIT and ancestor.returncode == 0
            detail = {"resolved": resolved.stdout.strip(), "ancestor_exit": ancestor.returncode}
        except Exception as exc:
            git_ok = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S01P03-P02-GIT-ANCESTRY", git_ok, detail)
    else:
        _add(checks, "S01P03-TEST-ONLY-GIT-PROFILE", True, "Git ancestry skipped only for isolated mutation clone")


def _check_frozen_semantics(
    canonical: Mapping[str, Any],
    parameters: Mapping[str, Any],
    costs: Mapping[str, Any],
    degraded: Mapping[str, Any],
    strategy: Mapping[str, Any],
    model_card: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
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
        and runtime.get("single_host_zero_downtime_guaranteed") is False
        and truth.get("advice_ledger_separate_from_actual_ledger") is True
        and truth.get("actual_return_requires_verified_execution_evidence") is True
        and truth.get("silent_coverage_gap_target") == 0
    )
    _add(checks, "S01P03-CANONICAL-BOUNDARIES-FROZEN", canonical_ok, "canonical role, budget, runtime and evidence")

    risk = parameters.get("risk", {})
    target = parameters.get("target_30pct", {})
    parameter_ok = (
        risk.get("kelly_fraction_alpha") == "0.00"
        and risk.get("kelly_fraction_beta") == "0.20"
        and risk.get("kelly_fraction_ga") == "0.25"
        and risk.get("chase_loss_prohibited") is True
        and risk.get("target_shortfall_may_relax_gate") is False
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and target.get("shadow_min_days") == 90
        and target.get("shadow_min_independent_equivalent_signals") == 1000
        and len(target.get("falsification_gate", [])) == 3
        and len(target.get("verification_gate", [])) == 4
    )
    _add(checks, "S01P03-RISK-TARGET-BOUNDARIES-FROZEN", parameter_ok, "Kelly and target discipline")

    cash_gate = costs.get("incremental_cash_gate", {})
    cost_ok = (
        costs.get("cost_semantics", {}).get("total_system_cost_is_zero") is False
        and costs.get("incremental_cash_budget") == {"low": "0.00", "likely": "0.00", "high": "0.00"}
        and cash_gate.get("maximum_aud") == "0.00"
        and cash_gate.get("positive_boundary_aud") == "0.0001"
        and cash_gate.get("automatic_purchase_allowed") is False
        and cash_gate.get("automatic_paid_upgrade_allowed") is False
        and cash_gate.get("automatic_overage_billing_allowed") is False
    )
    _add(checks, "S01P03-ZERO-INCREMENTAL-CASH-FROZEN", cost_ok, cash_gate)

    degraded_boundary = degraded.get("s00_p04_execution_boundary", {})
    gmail_ok = (
        degraded.get("current_state") == "CONSENT_NOT_REQUESTED"
        and degraded_boundary.get("external_product_or_account_network_access") is False
        and degraded_boundary.get("token_received_or_stored") is False
        and degraded_boundary.get("gmail_api_called") is False
        and degraded_boundary.get("email_moved_or_deleted") is False
    )
    _add(checks, "S01P03-GMAIL-REMAINS-DISABLED", gmail_ok, degraded_boundary)

    strategy_text = json.dumps(strategy, ensure_ascii=False, sort_keys=True)
    model_text = json.dumps(model_card, ensure_ascii=False, sort_keys=True)
    model_ok = all(
        term in strategy_text + model_text
        for term in ["市场锚定残差", "市场权重至少50%", "第10百分位", "万分之一", "受限凯利", "NO_BET", "自动提交、确认或重试真实订单"]
    )
    _add(checks, "S01P03-MODEL-RISK-SEMANTICS-FROZEN", model_ok, "market prior, residual, calibration, stability and Kelly")


def _check_p04_not_started(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p04 = [row for row in rows if row.get("id") == "INDEX-AC-S01-P04"]
        evidence = sorted((root / "machine/evidence").glob("EVD-S01-P04*.json"))
        outputs = [root / "metrics.json", root / "economics.json", root / "kill_criteria.json"]
        passed = (
            len(p04) == 1
            and p04[0].get("status") == "PLANNED"
            and not evidence
            and not any(path.exists() for path in outputs)
        )
        detail = {
            "p04_status": p04[0].get("status") if len(p04) == 1 else "INVALID",
            "evidence": [path.name for path in evidence],
            "outputs": [path.name for path in outputs if path.exists()],
        }
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01P03-P04-NOT-STARTED", passed, detail)


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
        ("S01P03-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("targeted_test_minimum", 0))),
        ("S01P03-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("full_regression_test_minimum", 0))),
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

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S01P03-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S01P03-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
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
        _add(checks, "S01P03-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S01P03-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P03",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "REQUIREMENTS_SCOPE_AND_FLOWS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
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
        "phase_status": "S01_P03_PASS" if status == "PASS" else "S01_P03_FAILED",
        "next": "S01/P04_READY_NOT_STARTED" if status == "PASS" else "S01/P03_REMEDIATION_REQUIRED",
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

    for path in (REQUIREMENTS_PATH, SCOPE_PATH, FLOWS_PATH, FIXTURE_PATH):
        _single_source_check(root, path, checks)

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S01P03-FIXTURE-STRICT-JSON")
    requirements_artifact = _safe_load(root / REQUIREMENTS_PATH, checks, "S01P03-PRODUCT-REQUIREMENTS-STRICT-JSON")
    scope = _safe_load(root / SCOPE_PATH, checks, "S01P03-SCOPE-STRICT-JSON")
    flows = _safe_load(root / FLOWS_PATH, checks, "S01P03-FLOWS-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S01P03-ROADMAP-STRICT-JSON")
    source_requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S01P03-TASKPACK-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S01P03-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S01P03-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S01P03-TRACEABILITY-STRICT-JSON")
    source_documents = {
        relative: _safe_load(root / relative, checks, "S01P03-SOURCE-%s-STRICT-JSON" % Path(relative).stem.upper())
        for relative in PINNED_SOURCE_HASHES
        if relative.endswith(".json")
    }

    _check_pinned_hashes(root, checks, hashes)
    _check_continuous_workflow(root, checks)
    import_isolation_ok = all(
        (root / path).is_file()
        for path in [Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py")]
    )
    _add(checks, "S01P03-PYTEST-IMPORT-ISOLATION", import_isolation_ok, "package markers")

    dictionaries = [fixture, requirements_artifact, scope, flows, roadmap, task_graph]
    arrays = [source_requirements, acceptance, traceability]
    if (
        not all(isinstance(value, dict) for value in dictionaries)
        or not all(isinstance(value, list) for value in arrays)
        or not all(value is not None for value in source_documents.values())
    ):
        _add(checks, "S01P03-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S01P03-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, source_requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S01P03-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_requirements_artifact(root, requirements_artifact, fixture, acceptance, source_documents, checks)
    except Exception as exc:
        _add(checks, "S01P03-REQUIREMENTS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    requirement_rows = requirements_artifact.get("requirements", [])
    requirement_ids = [row.get("id") for row in requirement_rows if isinstance(row, dict)] if isinstance(requirement_rows, list) else []
    try:
        _check_scope_artifact(scope, fixture, requirement_ids, checks)
    except Exception as exc:
        _add(checks, "S01P03-SCOPE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_flows_artifact(flows, fixture, requirement_ids, checks)
    except Exception as exc:
        _add(checks, "S01P03-FLOWS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_cross_artifact_traceability(requirements_artifact, scope, flows, checks)
    except Exception as exc:
        _add(checks, "S01P03-CROSS-ARTIFACT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    _verify_p02_prerequisite(root, checks, hashes, _verify_git_history)

    try:
        _check_frozen_semantics(
            source_documents["machine/facts/canonical_facts.json"],
            source_documents["machine/facts/parameters.json"],
            source_documents["machine/facts/costs.json"],
            source_documents["machine/facts/degraded_mode_contract.json"],
            source_documents["machine/facts/strategy_spec.json"],
            source_documents["machine/facts/model_system_card.json"],
            checks,
        )
    except Exception as exc:
        _add(checks, "S01P03-FROZEN-SEMANTICS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _check_p04_not_started(root, checks)
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
        (REQUIREMENTS_PATH.as_posix(), root / REQUIREMENTS_PATH),
        (SCOPE_PATH.as_posix(), root / SCOPE_PATH),
        (FLOWS_PATH.as_posix(), root / FLOWS_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (P02_EVIDENCE_PATH.as_posix(), root / P02_EVIDENCE_PATH),
        (P02_ROLLBACK_PATH.as_posix(), root / P02_ROLLBACK_PATH),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s01-p03-rollback-") as directory:
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
        "evidence_id": "EVD-S01-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_REQUIREMENTS_SCOPE_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        REQUIREMENTS_PATH,
        SCOPE_PATH,
        FLOWS_PATH,
        FIXTURE_PATH,
        P02_EVIDENCE_PATH,
        P02_ROLLBACK_PATH,
        *[Path(relative) for relative in PINNED_SOURCE_HASHES if relative != P02_EVIDENCE_PATH.as_posix()],
        Path("tests/S01/P03_test.py"),
        Path("abd_acceptance/requirements_scope.py"),
        Path("abd_acceptance/customer_faq.py"),
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


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S01-P03-ROLLBACK",
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
        result["phase_status"] = "S01_P03_FAILED"
        result["next"] = "S01/P03_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P03",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S01-P03-01": REQUIREMENTS_PATH.as_posix(),
            "ART-S01-P03-02": SCOPE_PATH.as_posix(),
            "ART-S01-P03-03": FLOWS_PATH.as_posix(),
        },
        "p02_prerequisite": {
            "evidence": P02_EVIDENCE_PATH.as_posix(),
            "sha256": P02_EVIDENCE_SHA256,
            "commit": P02_COMMIT,
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S01/P03 traces model requirements but implements or evaluates no prediction model.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing STAGE-REVIEW-S00",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S01/P03_test.py --junitxml=machine/evidence/S01/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S01/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S01-P03 --evidence machine/evidence",
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
            "p04_artifacts_created": False,
        },
        "explicit_unknowns": [
            "The 30% monthly target remains unverified and is not guaranteed.",
            "OVH, Cloudflare, Gmail, betting accounts, source freshness and all-market production coverage remain unverified.",
            "The three S01/P03 artifacts are requirements contracts, not runtime, deployment, model-performance or actual-return evidence.",
            "No external account, secret, real email, order, deployment or actual return was observed in this phase.",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S01-P03"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S01-P03 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S01/P04_READY_NOT_STARTED" if status == "PASS" else "S01/P03_REMEDIATION_REQUIRED"
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
