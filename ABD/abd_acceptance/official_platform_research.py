from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .canonical_facts import sha256_file, strict_json_load
from .stage1_delivery import (
    PINNED_RECEIPT_SHA256 as STAGE1_DELIVERY_RECEIPT_SHA256,
    PINNED_STAGE_EVIDENCE_SHA256 as STAGE1_REVIEW_EVIDENCE_SHA256,
    PINNED_STAGE_ROLLBACK_SHA256 as STAGE1_REVIEW_ROLLBACK_SHA256,
    RECEIPT_PATH as STAGE1_DELIVERY_RECEIPT_PATH,
    STAGE_EVIDENCE_PATH as STAGE1_REVIEW_EVIDENCE_PATH,
    STAGE_ROLLBACK_PATH as STAGE1_REVIEW_ROLLBACK_PATH,
    verify_stage1_delivery,
)


CONTRACT_ID = "AC-S02-P01"
REQUIREMENT_ID = "REQ-S02-P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SOURCES_PATH = Path("sources.json")
PROVIDER_FACTS_PATH = Path("provider_facts_snapshot.json")
REGULATORY_MATRIX_PATH = Path("regulatory_matrix.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S02_P01.json")
JUNIT_PATH = Path("machine/evidence/S02/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S02/P01/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")
PHASE_COMMIT = "51598c991eb97f51b3c533dd88e438188094ec60"
PINNED_PHASE_CODE_HASH = "b020d07833ab97f297f81402c07e83be4fe6d9113ff1aec7df50698daf7076be"

SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "abd_acceptance/official_platform_research.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S02/P01_test.py",
}
SUCCESSOR_EVOLVED_TEST_HASHES = {
    "tests/S02/P01_test.py": "bc800d7bd6ac82ba5bf8b709013a0e16287750b635d838f6cd4ac885c7364377",
}

PINNED_PHASE_HASHES = {
    SOURCES_PATH.as_posix(): "a00d0bf733c2fb6c14ef0f5d56012a4d632bab982f9d5744fbea5b3eef487966",
    PROVIDER_FACTS_PATH.as_posix(): "a76b514469243d7b0a5c7c4ed3e2b388452d5fd5ded7fdc42aad48d5ebb17b06",
    REGULATORY_MATRIX_PATH.as_posix(): "5022031f18d910d040221d4e526b87c1b05b118bed4c1da9e655bc7b9d08227f",
    FIXTURE_PATH.as_posix(): "68bf2b7c97d31d5f9ac3d722e1f03f55e55c92b0d19f3c05e383d6780fc71faa",
}

PINNED_BASELINE_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/provider_contracts.json": "a9d0fd864fad7ac4c14ec6a324d447abbc8497b256a232f9ca04b3115b15364a",
    "machine/facts/authorization_matrix.json": "f7cf34a3d60e37365c3090fac75f40e0b390ec211976393e7148d597a2f4affe",
    "machine/facts/email_ingestion.json": "7d40a142a482b5179aa6bb11fa0694fa5576a770f0b2a5af751615da3dea53cd",
    "machine/facts/sources.json": "387df5c4cf54fcad59072c46ee7bbcd67f13e66adf2f5ccf9b115b71182784d8",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    STAGE1_DELIVERY_RECEIPT_PATH.as_posix(): STAGE1_DELIVERY_RECEIPT_SHA256,
    STAGE1_REVIEW_EVIDENCE_PATH.as_posix(): STAGE1_REVIEW_EVIDENCE_SHA256,
    STAGE1_REVIEW_ROLLBACK_PATH.as_posix(): STAGE1_REVIEW_ROLLBACK_SHA256,
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


def _absolute_local_paths(value: Any) -> List[str]:
    """Return absolute filesystem paths embedded as JSON scalar values.

    Evidence is portable across macOS, Linux, and Windows.  URLs and JSON
    pointers are not filesystem paths, while POSIX paths, Windows drive/UNC
    paths, and file URIs are always rejected regardless of the verifier host.
    """

    result: List[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for item in node.values():
                visit(item)
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, str) or not node:
            return
        lowered = node.lower()
        if (
            lowered.startswith("file://")
            or PurePosixPath(node).is_absolute()
            or PureWindowsPath(node).is_absolute()
        ):
            result.append(node)

    visit(value)
    return sorted(set(result))


def _row(rows: Sequence[Mapping[str, Any]], item_id: str) -> Mapping[str, Any]:
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == item_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s row, found %d" % (item_id, len(matches)))
    return matches[0]


def _fact_rows(provider_facts: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    result: List[Mapping[str, Any]] = []
    for provider in provider_facts.get("providers", []):
        if isinstance(provider, dict):
            result.extend(row for row in provider.get("facts", []) if isinstance(row, dict))
    return result


def _fact(provider_facts: Mapping[str, Any], fact_id: str) -> Mapping[str, Any]:
    matches = [row for row in _fact_rows(provider_facts) if row.get("fact_id") == fact_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s fact, found %d" % (fact_id, len(matches)))
    return matches[0]


def _rule(regulatory: Mapping[str, Any], rule_id: str) -> Mapping[str, Any]:
    matches = [row for row in regulatory.get("rules", []) if isinstance(row, dict) and row.get("rule_id") == rule_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s rule, found %d" % (rule_id, len(matches)))
    return matches[0]


def resolve_incremental_cost_gate(value: Any) -> str:
    if value is None:
        return "FAIL_UNKNOWN_INCREMENTAL_CASH"
    if not isinstance(value, str) or not value or value.strip() != value:
        return "FAIL_INVALID_INCREMENTAL_CASH"
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return "FAIL_INVALID_INCREMENTAL_CASH"
    if not parsed.is_finite():
        return "FAIL_INVALID_INCREMENTAL_CASH"
    if parsed < Decimal("0"):
        return "FAIL_INVALID_NEGATIVE_INCREMENTAL_CASH"
    if parsed == Decimal("0"):
        return "PASS_ZERO_INCREMENTAL_CASH"
    return "FAIL_POSITIVE_INCREMENTAL_CASH"


def resolve_source_freshness(retrieved_on: Any, review_by: Any, as_of: Any) -> str:
    if not all(isinstance(value, str) for value in [retrieved_on, review_by, as_of]):
        return "INVALID_SOURCE_DATES"
    try:
        retrieved = date.fromisoformat(retrieved_on)
        review = date.fromisoformat(review_by)
        current = date.fromisoformat(as_of)
    except ValueError:
        return "INVALID_SOURCE_DATES"
    if retrieved > review or current < retrieved:
        return "INVALID_SOURCE_DATES"
    if current > review:
        return "STALE_FAIL_CLOSED"
    return "CURRENT_FOR_FROZEN_SNAPSHOT"


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in {**PINNED_PHASE_HASHES, **PINNED_BASELINE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S02P01-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        check_id = "S02P01-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
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
    phases = [row for row in stage.get("phases", []) if isinstance(row, dict) and row.get("id") == "P01"]
    phase = phases[0] if len(phases) == 1 else {}
    expected_phase = {
        "id": "P01",
        "title": "官方平台与监管调研",
        "objective": "固化TAB、Sportsbet、Gmail、Cloudflare、OVH及监管事实。",
        "outputs": ["sources.json", "provider_facts_snapshot.json", "regulatory_matrix.json"],
        "pass_gate": "每个事实有URL、检索日期和来源等级。",
        "hours": {"low": 3, "likely": 4, "high": 6},
    }
    stage_ok = (
        len(stages) == 1
        and len(phases) == 1
        and stage.get("title") == "公开网络与 GitHub 调研复用"
        and stage.get("depends_on") == ["S00"]
        and phase == expected_phase
    )
    _add(checks, "S02P01-ROADMAP-EXACT", stage_ok, phase)

    req_rows = [row for row in requirements if isinstance(row, dict) and row.get("id") == REQUIREMENT_ID]
    requirement = req_rows[0] if len(req_rows) == 1 else {}
    requirement_ok = (
        len(req_rows) == 1
        and requirement.get("stage_id") == "S02"
        and requirement.get("phase_id") == "P01"
        and requirement.get("title") == "官方平台与监管调研"
        and requirement.get("value") == "固化TAB、Sportsbet、Gmail、Cloudflare、OVH及监管事实。"
        and requirement.get("scope") == expected_phase["outputs"]
        and requirement.get("non_goals")
        == [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
        and requirement.get("target") == expected_phase["pass_gate"]
        and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        and requirement.get("owner_input_required_during_development") is False
    )
    _add(checks, "S02P01-REQUIREMENT-EXACT", requirement_ok, requirement)

    ac_rows = [row for row in acceptance if isinstance(row, dict) and row.get("id") == CONTRACT_ID]
    contract = ac_rows[0] if len(ac_rows) == 1 else {}
    test_ids = [row.get("id") for row in contract.get("tests", []) if isinstance(row, dict)]
    contract_ok = (
        len(ac_rows) == 1
        and contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("oracle")
        == {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S02-P01 --evidence machine/evidence",
            "rule": expected_phase["pass_gate"],
        }
        and contract.get("threshold") == expected_phase["pass_gate"]
        and test_ids == ["TEST-S02-P01", "TEST-S02-P01-BOUNDARY", "TEST-S02-P01-REPLAY"]
        and contract.get("pass_gate") == expected_phase["pass_gate"]
        and contract.get("evidence_requirements", [None])[0] == "machine/evidence/EVD-S02-P01.json"
    )
    _add(checks, "S02P01-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [
        row
        for row in task_graph.get("tasks", [])
        if isinstance(row, dict) and str(row.get("id", "")).startswith("T-S02-P01-")
    ]
    task_ids = [row.get("id") for row in tasks]
    expected_outputs = {
        "T-S02-P01-01": expected_phase["outputs"],
        "T-S02-P01-02": ["tests/S02/P01_test.py", "machine/tests/fixtures/S02_P01.json"],
        "T-S02-P01-03": ["machine/evidence/EVD-S02-P01.json", "machine/evidence/EVD-S02-P01_rollback.json"],
    }
    expected_dependencies = {
        "T-S02-P01-01": ["T-S00-P04-03"],
        "T-S02-P01-02": ["T-S02-P01-01"],
        "T-S02-P01-03": ["T-S02-P01-02"],
    }
    task_ok = task_ids == ["T-S02-P01-01", "T-S02-P01-02", "T-S02-P01-03"]
    for task in tasks:
        task_id = str(task.get("id"))
        task_ok = task_ok and (
            task.get("stage_id") == "S02"
            and task.get("phase_id") == "P01"
            and task.get("outputs") == expected_outputs.get(task_id)
            and task.get("depends_on") == expected_dependencies.get(task_id)
            and task.get("requirement_ids") == [REQUIREMENT_ID]
            and task.get("acceptance_criteria_ids") == [CONTRACT_ID]
            and task.get("owner_input_required") is False
            and task.get("auto_advance_on_pass") is True
            and task.get("pass_gate") == expected_phase["pass_gate"]
            and task.get("oracle", {}).get("mode") == "DETERMINISTIC_FAIL_CLOSED"
        )
    _add(checks, "S02P01-TASK-CHAIN-EXACT", task_ok, {"ids": task_ids, "dependencies": expected_dependencies})

    trace_rows = [row for row in traceability if isinstance(row, dict) and row.get("requirement_id") == REQUIREMENT_ID]
    expected_trace = {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S02-P01-01", "T-S02-P01-02", "T-S02-P01-03"],
        "test_ids": ["TEST-S02-P01", "TEST-S02-P01-BOUNDARY", "TEST-S02-P01-REPLAY"],
        "evidence_id": "EVD-S02-P01",
        "artifact_ids": ["ART-S02-P01-01", "ART-S02-P01-02", "ART-S02-P01-03"],
        "stage_id": "S02",
        "phase_id": "P01",
    }
    _add(
        checks,
        "S02P01-TRACEABILITY-EXACT",
        len(trace_rows) == 1 and trace_rows[0] == expected_trace,
        trace_rows,
    )


def _check_source_catalog(
    sources: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> Dict[str, Mapping[str, Any]]:
    boundary = sources.get("s02_p01_execution_boundary", {})
    top_ok = (
        sources.get("schema_version") == "1.0.0"
        and sources.get("artifact_id") == "ART-S02-P01-01"
        and sources.get("requirement_id") == REQUIREMENT_ID
        and sources.get("acceptance_contract_id") == CONTRACT_ID
        and sources.get("product_version") == VERSION
        and sources.get("fixed_at") == FIXED_CLOCK
        and sources.get("status") == "OFFICIAL_SOURCE_SET_FROZEN_CAPABILITIES_NOT_ENABLED"
        and sources.get("next_on_acceptance_pass") == "S02/P02_READY_NOT_STARTED"
    )
    _add(checks, "S02P01-SOURCES-TOP-LEVEL", top_ok, sources.get("status"))

    mode = sources.get("research_mode", {})
    mode_ok = mode == {
        "network_mode": "READ_ONLY_PUBLIC_WEB",
        "official_primary_sources_only": True,
        "account_login_performed": False,
        "provider_api_called": False,
        "content_archived": False,
        "legal_advice_provided": False,
        "scope_is_exhaustive_of_internet": False,
    }
    _add(checks, "S02P01-READ-ONLY-NONEXHAUSTIVE-RESEARCH-MODE", mode_ok, mode)

    expected_levels = fixture.get("expected_source_levels")
    _add(
        checks,
        "S02P01-SOURCE-LEVEL-DEFINITIONS-EXACT",
        list(sources.get("source_level_definitions", {}).keys()) == expected_levels
        and sources.get("admission_policy", {}).get("allowed_source_levels") == expected_levels
        and sources.get("admission_policy", {}).get("missing_or_unreachable_source") == "UNKNOWN_FAIL_CLOSED"
        and sources.get("admission_policy", {}).get("terms_or_price_drift") == "REVALIDATE_BEFORE_CAPABILITY_ENABLEMENT"
        and sources.get("admission_policy", {}).get("absence_from_scoped_source_set")
        == "NOT_AUTHORIZED_BY_EVIDENCE_NOT_UNIVERSAL_ABSENCE",
        sources.get("admission_policy"),
    )

    rows = sources.get("sources", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    _add(
        checks,
        "S02P01-SOURCE-IDS-EXACT-UNIQUE",
        ids == fixture.get("expected_source_ids") and not _duplicates(ids),
        ids,
    )

    allowed_hosts = set(fixture.get("official_host_allowlist", []))
    allowed_levels = set(expected_levels or [])
    exact_keys = {
        "id",
        "publisher",
        "title",
        "url",
        "retrieved_on",
        "source_level",
        "jurisdiction",
        "time_varying",
        "last_updated_or_effective_on",
        "review_by",
        "claim_ids",
    }
    metadata_ok = True
    url_ok = True
    freshness_ok = True
    claims_ok = True
    detail: Dict[str, Any] = {}
    source_map: Dict[str, Mapping[str, Any]] = {}
    urls: List[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            metadata_ok = url_ok = freshness_ok = claims_ok = False
            continue
        source_id = str(row.get("id", ""))
        source_map[source_id] = row
        url = row.get("url")
        parts = urlsplit(url) if isinstance(url, str) else None
        row_url_ok = bool(
            parts
            and parts.scheme == "https"
            and parts.hostname in allowed_hosts
            and parts.username is None
            and parts.password is None
            and not parts.fragment
        )
        url_ok = url_ok and row_url_ok
        if isinstance(url, str):
            urls.append(url)
        row_metadata_ok = (
            set(row) == exact_keys
            and all(isinstance(row.get(key), str) and row.get(key) for key in ["id", "publisher", "title", "url", "jurisdiction"])
            and row.get("source_level") in allowed_levels
            and row.get("retrieved_on") == "2026-07-20"
            and row.get("review_by") == "2026-08-20"
            and row.get("time_varying") is True
            and (row.get("last_updated_or_effective_on") is None or isinstance(row.get("last_updated_or_effective_on"), str))
        )
        metadata_ok = metadata_ok and row_metadata_ok
        row_freshness = resolve_source_freshness(row.get("retrieved_on"), row.get("review_by"), "2026-07-20")
        freshness_ok = freshness_ok and row_freshness == "CURRENT_FOR_FROZEN_SNAPSHOT"
        claim_ids = row.get("claim_ids")
        row_claims_ok = isinstance(claim_ids, list) and bool(claim_ids) and not _duplicates(claim_ids)
        claims_ok = claims_ok and row_claims_ok
        detail[source_id] = {
            "host": parts.hostname if parts else None,
            "source_level": row.get("source_level"),
            "freshness": row_freshness,
            "claims": len(claim_ids) if isinstance(claim_ids, list) else 0,
        }
    _add(checks, "S02P01-SOURCE-METADATA-COMPLETE", metadata_ok, detail)
    _add(checks, "S02P01-SOURCE-URLS-OFFICIAL-HTTPS", url_ok and not _duplicates(urls), urls)
    _add(checks, "S02P01-SOURCE-RETRIEVAL-DATES-CURRENT", freshness_ok, detail)
    _add(checks, "S02P01-SOURCE-CLAIM-MAPPINGS-NONEMPTY", claims_ok, detail)

    expected_boundary = {
        "external_account_accessed": False,
        "provider_api_called": False,
        "credential_or_token_created": False,
        "cloud_deployment_performed": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
        "production_readiness_claimed": False,
        "return_or_roi_verified": False,
        "s02_p02_started": False,
    }
    _add(checks, "S02P01-SOURCES-NO-EXTERNAL-EFFECT", boundary == expected_boundary, boundary)
    limitations = sources.get("limitations", [])
    limitations_ok = (
        isinstance(limitations, list)
        and len(limitations) == 4
        and any("not legal advice" in str(item) for item in limitations)
        and any("must be revalidated" in str(item) for item in limitations)
        and any("No source proves" in str(item) for item in limitations)
    )
    _add(checks, "S02P01-SOURCE-LIMITATIONS-EXPLICIT", limitations_ok, limitations)
    return source_map


def _citation_matches_source(
    citation: Mapping[str, Any],
    source: Mapping[str, Any],
    claim_id: str,
) -> bool:
    return (
        set(citation) == {"source_id", "url", "retrieved_on", "source_level"}
        and citation.get("source_id") == source.get("id")
        and citation.get("url") == source.get("url")
        and citation.get("retrieved_on") == source.get("retrieved_on")
        and citation.get("source_level") == source.get("source_level")
        and claim_id in source.get("claim_ids", [])
    )


def _check_provider_facts(
    provider_facts: Mapping[str, Any],
    fixture: Mapping[str, Any],
    source_map: Mapping[str, Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        provider_facts.get("schema_version") == "1.0.0"
        and provider_facts.get("artifact_id") == "ART-S02-P01-02"
        and provider_facts.get("requirement_id") == REQUIREMENT_ID
        and provider_facts.get("acceptance_contract_id") == CONTRACT_ID
        and provider_facts.get("product_version") == VERSION
        and provider_facts.get("fixed_at") == FIXED_CLOCK
        and provider_facts.get("status") == "PROVIDER_FACTS_FROZEN_CAPABILITIES_FAIL_CLOSED"
        and provider_facts.get("next_on_acceptance_pass") == "S02/P02_READY_NOT_STARTED"
    )
    _add(checks, "S02P01-PROVIDER-TOP-LEVEL", top_ok, provider_facts.get("status"))

    semantics = provider_facts.get("fact_semantics", {})
    semantics_ok = (
        semantics.get("official_document_is_runtime_proof") is False
        and semantics.get("missing_permission_is_authorization") is False
        and semantics.get("absence_from_scoped_sources_is_universal_prohibition") is False
        and semantics.get("terms_prices_limits_and_registers_require_live_revalidation") is True
    )
    _add(checks, "S02P01-FACT-SEMANTICS-FAIL-CLOSED", semantics_ok, semantics)

    providers = provider_facts.get("providers", [])
    provider_ids = [row.get("provider_id") for row in providers if isinstance(row, dict)] if isinstance(providers, list) else []
    _add(
        checks,
        "S02P01-PROVIDER-IDS-EXACT-UNIQUE",
        provider_ids == fixture.get("expected_provider_ids") and not _duplicates(provider_ids),
        provider_ids,
    )
    providers_complete = all(
        isinstance(row.get("provider_role"), str)
        and bool(row.get("provider_role"))
        and isinstance(row.get("current_abd_capability"), str)
        and any(term in row.get("current_abd_capability", "") for term in ["NOT_", "UNKNOWN", "UNVERIFIED"])
        and isinstance(row.get("facts"), list)
        and bool(row.get("facts"))
        for row in providers
        if isinstance(row, dict)
    )
    _add(checks, "S02P01-PROVIDER-CAPABILITIES-NOT-FABRICATED", providers_complete, provider_ids)

    facts = _fact_rows(provider_facts)
    fact_ids = [row.get("fact_id") for row in facts]
    _add(
        checks,
        "S02P01-PROVIDER-FACT-IDS-EXACT-UNIQUE",
        fact_ids == fixture.get("expected_provider_fact_ids") and not _duplicates(fact_ids),
        fact_ids,
    )
    complete = True
    citations_ok = True
    decisions_safe = True
    details: Dict[str, Any] = {}
    for row in facts:
        fact_id = str(row.get("fact_id", ""))
        complete = complete and set(row) == {
            "fact_id",
            "statement",
            "fact_status",
            "applicability",
            "operational_decision",
            "citations",
        }
        complete = complete and all(
            isinstance(row.get(key), str) and bool(row.get(key))
            for key in ["fact_id", "statement", "fact_status", "applicability", "operational_decision"]
        )
        citations = row.get("citations")
        row_citations_ok = isinstance(citations, list) and bool(citations)
        for citation in citations if isinstance(citations, list) else []:
            source = source_map.get(citation.get("source_id")) if isinstance(citation, dict) else None
            row_citations_ok = row_citations_ok and bool(
                isinstance(citation, dict)
                and isinstance(source, dict)
                and _citation_matches_source(citation, source, fact_id)
            )
        citations_ok = citations_ok and row_citations_ok
        decision = str(row.get("operational_decision", ""))
        decisions_safe = decisions_safe and not any(
            token in decision
            for token in ["SUBMIT_ORDER", "CONFIRM_ORDER", "RETRY_ORDER", "AUTO_PURCHASE", "AUTO_UPGRADE_TO_PAID"]
        )
        details[fact_id] = {"citations": len(citations) if isinstance(citations, list) else 0, "decision": decision}
    _add(checks, "S02P01-PROVIDER-FACT-ROWS-COMPLETE", complete, details)
    _add(checks, "S02P01-PROVIDER-FACT-CITATIONS-RESOLVE", citations_ok, details)
    _add(checks, "S02P01-PROVIDER-DECISIONS-NO-ORDER-OR-SPEND", decisions_safe, details)

    critical = provider_facts.get("critical_safe_defaults", {})
    _add(
        checks,
        "S02P01-CRITICAL-SAFE-DEFAULTS-EXACT",
        critical == fixture.get("expected_critical_defaults"),
        critical,
    )
    tab_ok = (
        _fact(provider_facts, "PF-TAB-003").get("operational_decision")
        == "PROHIBIT_SCREEN_SCRAPING_CREDENTIAL_SHARING_AND_THIRD_PARTY_ACCOUNT_CONTROL"
        and _fact(provider_facts, "PF-TAB-004").get("operational_decision")
        == "NOT_AUTHORIZED_UNLESS_SEPARATE_ACCESS_GRANT_METHOD_AND_USE_CONTRACT_ARE_VERIFIED"
        and "UNKNOWN_FAIL_CLOSED" in str(_fact(provider_facts, "PF-TAB-005").get("fact_status"))
    )
    _add(checks, "S02P01-TAB-ACCESS-CONTRACT-FAIL-CLOSED", tab_ok, "screen scrape, web services and Studio")
    sportsbet_ok = (
        _fact(provider_facts, "PF-SPORTSBET-003").get("fact_status") == "UNKNOWN_FAIL_CLOSED"
        and _fact(provider_facts, "PF-SPORTSBET-003").get("operational_decision")
        == "NO_SCRAPING_AUTOMATION_OR_API_USE_WITHOUT_SEPARATE_OFFICIAL_PERMISSION_EVIDENCE"
        and "not a claim" in str(_fact(provider_facts, "PF-SPORTSBET-003").get("statement"))
    )
    _add(checks, "S02P01-SPORTSBET-AUTOMATION-NOT-INVENTED", sportsbet_ok, _fact(provider_facts, "PF-SPORTSBET-003"))
    gmail_ok = (
        "restricted OAuth scopes" in str(_fact(provider_facts, "PF-GMAIL-001").get("statement"))
        and _fact(provider_facts, "PF-GMAIL-002").get("operational_decision")
        == "ALLOW_ONLY_LIST_GET_ATTACHMENT_GET_TRASH_AND_UNTRASH_AFTER_CONSENT_AND_POLICY_GATES"
        and _fact(provider_facts, "PF-GMAIL-005").get("fact_status")
        == "UNKNOWN_REQUIRES_GOOGLE_POLICY_CONFIRMATION_BEFORE_ENABLEMENT"
    )
    _add(checks, "S02P01-GMAIL-RESTRICTED-SCOPE-POLICY-GATE", gmail_ok, "scope, methods and assessment")
    cloudflare_ok = (
        _fact(provider_facts, "PF-CLOUDFLARE-002").get("operational_decision")
        == "REJECT_PAID_PLAN_AND_AUTOMATIC_UPGRADE_UNDER_AUD_ZERO_INCREMENTAL_CASH_GATE"
        and _fact(provider_facts, "PF-CLOUDFLARE-004").get("operational_decision")
        == "REJECT_CHINA_NETWORK_FROM_VERSION_0_0_0_1_AUD_ZERO_INCREMENTAL_CASH_SCOPE"
        and _fact(provider_facts, "PF-CLOUDFLARE-005").get("operational_decision")
        == "DO_NOT_USE_PAGES_AS_EVIDENCE_OF_MAINLAND_CHINA_AVAILABILITY"
        and _fact(provider_facts, "PF-CLOUDFLARE-006").get("fact_status")
        == "UNKNOWN_FAIL_CLOSED_FOR_MAINLAND_CHINA_SERVICE_CLAIM"
    )
    _add(checks, "S02P01-CLOUDFLARE-CHINA-AND-ZERO-CASH-GATE", cloudflare_ok, "paid China Network rejected; no mainland claim")
    ovh_ok = (
        "not evidence" in str(_fact(provider_facts, "PF-OVH-001").get("statement"))
        and _fact(provider_facts, "PF-OVH-002").get("operational_decision")
        == "PROHIBIT_NEW_PURCHASE_UPGRADE_OR_PAID_ADD_ON_UNDER_AUD_ZERO_INCREMENTAL_CASH_GATE"
        and _fact(provider_facts, "PF-OVH-003").get("fact_status") == "UNKNOWN_FAIL_CLOSED"
    )
    _add(checks, "S02P01-OVH-SLA-NOT-RUNTIME-PROOF", ovh_ok, "SLA and existing-instance state remain distinct")

    boundary = provider_facts.get("s02_p01_execution_boundary", {})
    expected_boundary = {
        "provider_accounts_accessed": False,
        "provider_permissions_obtained": False,
        "provider_api_called": False,
        "email_read_or_modified": False,
        "cloud_deployment_performed": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
        "availability_verified": False,
        "market_coverage_verified": False,
        "return_or_roi_verified": False,
        "s02_p02_started": False,
    }
    _add(checks, "S02P01-PROVIDER-NO-EXTERNAL-OR-PERFORMANCE-EFFECT", boundary == expected_boundary, boundary)


def _check_regulatory_matrix(
    regulatory: Mapping[str, Any],
    fixture: Mapping[str, Any],
    source_map: Mapping[str, Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        regulatory.get("schema_version") == "1.0.0"
        and regulatory.get("artifact_id") == "ART-S02-P01-03"
        and regulatory.get("requirement_id") == REQUIREMENT_ID
        and regulatory.get("acceptance_contract_id") == CONTRACT_ID
        and regulatory.get("product_version") == VERSION
        and regulatory.get("fixed_at") == FIXED_CLOCK
        and regulatory.get("status") == "REGULATORY_BASELINE_FROZEN_CAPABILITIES_FAIL_CLOSED"
        and regulatory.get("next_on_acceptance_pass") == "S02/P02_READY_NOT_STARTED"
    )
    _add(checks, "S02P01-REGULATORY-TOP-LEVEL", top_ok, regulatory.get("status"))
    scope = regulatory.get("scope", {})
    scope_ok = (
        scope.get("jurisdiction") == "AUSTRALIA"
        and scope.get("legal_advice") is False
        and scope.get("legal_opinion_or_full_compliance_assessment") is False
        and scope.get("licensed_counsel_review_performed") is False
        and scope.get("owner_account_or_identity_status_inspected") is False
        and scope.get("regulatory_scope_exhaustive") is False
    )
    _add(checks, "S02P01-REGULATORY-NO-LEGAL-ADVICE-OR-CERTIFICATION", scope_ok, scope)

    rules = regulatory.get("rules", [])
    rule_ids = [row.get("rule_id") for row in rules if isinstance(row, dict)] if isinstance(rules, list) else []
    _add(
        checks,
        "S02P01-REGULATORY-RULE-IDS-EXACT-UNIQUE",
        rule_ids == fixture.get("expected_regulatory_rule_ids") and not _duplicates(rule_ids),
        rule_ids,
    )
    expected_keys = {
        "rule_id",
        "authority",
        "jurisdiction",
        "subject",
        "statement",
        "status",
        "applicability_to_abd",
        "operational_control",
        "unknown_or_conflict_action",
        "citations",
    }
    complete = True
    citations_ok = True
    controls_ok = True
    expected_controls = fixture.get("expected_regulatory_controls", {})
    details: Dict[str, Any] = {}
    for row in rules if isinstance(rules, list) else []:
        if not isinstance(row, dict):
            complete = citations_ok = controls_ok = False
            continue
        rule_id = str(row.get("rule_id", ""))
        complete = complete and set(row) == expected_keys and all(
            isinstance(row.get(key), str) and bool(row.get(key))
            for key in expected_keys - {"citations"}
        )
        controls_ok = controls_ok and row.get("operational_control") == expected_controls.get(rule_id)
        citations = row.get("citations")
        row_citations_ok = isinstance(citations, list) and bool(citations)
        for citation in citations if isinstance(citations, list) else []:
            source = source_map.get(citation.get("source_id")) if isinstance(citation, dict) else None
            row_citations_ok = row_citations_ok and bool(
                isinstance(citation, dict)
                and isinstance(source, dict)
                and _citation_matches_source(citation, source, rule_id)
            )
        citations_ok = citations_ok and row_citations_ok
        details[rule_id] = {"control": row.get("operational_control"), "citations": len(citations) if isinstance(citations, list) else 0}
    _add(checks, "S02P01-REGULATORY-RULES-COMPLETE", complete, details)
    _add(checks, "S02P01-REGULATORY-CITATIONS-RESOLVE", citations_ok, details)
    _add(checks, "S02P01-REGULATORY-CONTROLS-EXACT", controls_ok, details)

    critical_ok = (
        _rule(regulatory, "REG-001").get("status") == "HARD_PROHIBITION_CONTROL"
        and _rule(regulatory, "REG-001").get("operational_control")
        == "BLOCK_ONLINE_IN_PLAY_MARKETS_AND_EMIT_NO_RECOMMENDATION"
        and _rule(regulatory, "REG-003").get("status") == "HARD_PAYMENT_METHOD_PROHIBITION_CONTROL"
        and _rule(regulatory, "REG-004").get("operational_control")
        == "SELF_EXCLUDED_OR_STATUS_UNKNOWN_EMITS_NO_RECOMMENDATION_AND_NO_PROVIDER_INTERACTION"
        and _rule(regulatory, "REG-007").get("status")
        == "SAFE_DESIGN_BASELINE_FORMAL_LEGAL_APPLICABILITY_UNKNOWN"
        and _rule(regulatory, "REG-008").get("operational_control")
        == "NO_SCREEN_SCRAPING_NO_CREDENTIAL_CAPTURE_NO_ACCOUNT_CONTROL_NO_ORDER_SUBMISSION"
    )
    _add(checks, "S02P01-REGULATORY-CRITICAL-FAIL-CLOSED-BEHAVIOR", critical_ok, "in-play, payments, BetStop, privacy, TAB")

    runtime = regulatory.get("runtime_prerequisite_state", {})
    expected_runtime = {
        "owner_jurisdiction_verified": False,
        "licensed_provider_match_verified": False,
        "owner_age_residency_and_kyc_verified": False,
        "betstop_or_other_self_exclusion_status_verified": False,
        "provider_terms_acceptance_verified": False,
        "TAB_web_services_or_studio_permission_verified": False,
        "Sportsbet_automation_permission_verified": False,
        "default": "NO_PROVIDER_INTERACTION_NO_RECOMMENDATION",
    }
    _add(checks, "S02P01-REGULATORY-RUNTIME-PREREQUISITES-UNVERIFIED", runtime == expected_runtime, runtime)
    conflict = regulatory.get("conflict_assessment", {})
    conflict_ok = (
        conflict.get("irreconcilable_legal_or_source_contract_conflict_found") is False
        and conflict.get("unresolved_legal_questions_exist") is True
        and conflict.get("unresolved_question_action") == "KEEP_AFFECTED_CAPABILITY_DISABLED_AND_REVALIDATE_PRIMARY_SOURCES"
        and "does not certify legal compliance" in str(conflict.get("reason"))
    )
    _add(checks, "S02P01-REGULATORY-CONFLICTS-HAVE-SAFE-DEFAULT", conflict_ok, conflict)
    boundary = regulatory.get("s02_p01_execution_boundary", {})
    expected_boundary = {
        "legal_advice_provided": False,
        "regulatory_compliance_certified": False,
        "owner_identity_or_account_state_inspected": False,
        "provider_account_accessed": False,
        "provider_api_called": False,
        "production_deployed": False,
        "real_order_submitted": False,
        "incremental_cash_spent_aud": "0.00",
        "return_or_roi_verified": False,
        "s02_p02_started": False,
    }
    _add(checks, "S02P01-REGULATORY-NO-EXTERNAL-EFFECT", boundary == expected_boundary, boundary)


def _check_cross_artifact_claims(
    sources: Mapping[str, Any],
    provider_facts: Mapping[str, Any],
    regulatory: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    source_rows = [row for row in sources.get("sources", []) if isinstance(row, dict)]
    source_claims: Dict[str, List[str]] = {
        str(row.get("id")): list(row.get("claim_ids", [])) for row in source_rows
    }
    fact_ids = [str(row.get("fact_id")) for row in _fact_rows(provider_facts)]
    rule_ids = [str(row.get("rule_id")) for row in regulatory.get("rules", []) if isinstance(row, dict)]
    expected_claims = set(fact_ids + rule_ids)
    declared_claims = {claim for claims in source_claims.values() for claim in claims}
    _add(
        checks,
        "S02P01-ALL-CLAIMS-HAVE-OFFICIAL-SOURCE",
        declared_claims == expected_claims,
        {"missing": sorted(expected_claims - declared_claims), "orphan": sorted(declared_claims - expected_claims)},
    )

    cited_sources = set()
    for row in [*_fact_rows(provider_facts), *[item for item in regulatory.get("rules", []) if isinstance(item, dict)]]:
        for citation in row.get("citations", []):
            if isinstance(citation, dict):
                cited_sources.add(citation.get("source_id"))
    source_ids = set(source_claims)
    _add(
        checks,
        "S02P01-NO-UNUSED-OFFICIAL-SOURCES",
        cited_sources == source_ids,
        {"unused": sorted(source_ids - cited_sources), "unknown": sorted(cited_sources - source_ids)},
    )


def _check_canonical_alignment(
    canonical: Mapping[str, Any],
    costs: Mapping[str, Any],
    provider_contracts: Sequence[Mapping[str, Any]],
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
        and truth.get("actual_return_requires_verified_execution_evidence") is True
    )
    _add(checks, "S02P01-CANONICAL-BOUNDARIES-FROZEN", canonical_ok, "bankroll, zero cash, advice-only, runtime target")
    cost_gate = costs.get("incremental_cash_gate", {})
    costs_ok = (
        costs.get("incremental_cash_budget") == {"low": "0.00", "likely": "0.00", "high": "0.00"}
        and cost_gate.get("maximum_aud") == "0.00"
        and cost_gate.get("positive_boundary_aud") == "0.0001"
        and cost_gate.get("negative_boundary_aud") == "-0.0001"
        and cost_gate.get("automatic_purchase_allowed") is False
        and cost_gate.get("automatic_paid_upgrade_allowed") is False
        and cost_gate.get("automatic_overage_billing_allowed") is False
    )
    _add(checks, "S02P01-ZERO-INCREMENTAL-CASH-BASELINE", costs_ok, cost_gate)
    providers_ok = (
        [row.get("id") for row in provider_contracts] == ["TAB", "SPORTSBET", "OTHER_OBSERVABLE_PROVIDER"]
        and all(row.get("order_submission") == "NOT_PRESENT" for row in provider_contracts)
        and all(row.get("background_public_page_collection") == "SOURCE_CONTRACT_DEPENDENT" for row in provider_contracts)
    )
    _add(checks, "S02P01-PROVIDER-CONTRACTS-REMAIN-SOURCE-DEPENDENT", providers_ok, provider_contracts)


def _check_s02_p02_not_started(
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
        p02 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P02"]
        forbidden_paths = [
            root / "research_evidence_matrix.json",
            root / "model_claims.json",
            root / "tests/S02/P02_test.py",
            root / "machine/tests/fixtures/S02_P02.json",
            root / "machine/evidence/EVD-S02-P02.json",
            root / "machine/evidence/EVD-S02-P02_rollback.json",
        ]
        existing = [path.relative_to(root).as_posix() for path in forbidden_paths if path.exists()]
        not_started = (
            len(p02) == 1
            and p02[0].get("status") == "PLANNED"
            and "actual_artifact" not in p02[0]
            and not existing
        )
        if not_started:
            passed = True
            detail = {"state": "P02_NOT_STARTED", "index": p02, "forbidden_existing": existing}
        elif (
            len(p02) == 1
            and p02[0].get("status") == "PLANNED"
            and "actual_artifact" not in p02[0]
            and existing
            == [
                "research_evidence_matrix.json",
                "model_claims.json",
                "tests/S02/P02_test.py",
                "machine/tests/fixtures/S02_P02.json",
            ]
        ):
            try:
                from .model_risk_research import evaluate_contract as evaluate_p02_candidate

                candidate = evaluate_p02_candidate(
                    root,
                    require_external_reports=False,
                    _verify_git_history=verify_git_history,
                )
                passed = candidate.get("status") == "PASS" and candidate.get("next") == "S02/P03_READY_NOT_STARTED"
                detail = {
                    "state": "P02_IN_PROGRESS_VALIDATED_NOT_ACCEPTED" if passed else "INVALID_P02_CANDIDATE",
                    "candidate_summary": candidate.get("summary"),
                    "index": p02,
                    "existing": existing,
                }
            except Exception as exc:
                passed = False
                detail = {
                    "state": "INVALID_P02_CANDIDATE",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "index": p02,
                    "existing": existing,
                }
        else:
            try:
                from .model_risk_research import verify_existing_phase_evidence as verify_p02_evidence

                successor = verify_p02_evidence(
                    root,
                    verify_git_history=verify_git_history,
                    verify_p01_prerequisite=False,
                )
                passed = (
                    successor.get("status") == "PASS"
                    and successor.get("decision") == "S02_P02_EVIDENCE_VERIFIED"
                    and successor.get("next") == "S02/P03_READY_NOT_STARTED"
                )
                detail = {
                    "state": "P02_VERIFIED_SUCCESSOR" if passed else "INVALID_OR_PARTIAL_P02_SUCCESSOR",
                    "successor_summary": successor.get("summary"),
                    "index": p02,
                    "existing": existing,
                }
            except Exception as exc:
                passed = False
                detail = {
                    "state": "INVALID_OR_PARTIAL_P02_SUCCESSOR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "index": p02,
                    "existing": existing,
                }
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02P01-P02-NOT-STARTED", passed, detail)


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
        ("S02P01-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S02P01-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
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

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S02P01-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S02P01-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
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
        _add(checks, "S02P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S02P01-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P01",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "OFFICIAL_PLATFORM_AND_REGULATORY_FACTS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
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
        "provider_capability_status": "NOT_CONNECTED_OR_NOT_AUTHORIZED",
        "legal_status": "RESEARCH_BASELINE_NOT_LEGAL_ADVICE_OR_COMPLIANCE_CERTIFICATION",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "phase_status": "S02_P01_PASS" if status == "PASS" else "S02_P01_FAILED",
        "next": "S02/P02_READY_NOT_STARTED" if status == "PASS" else "S02/P01_REMEDIATION_REQUIRED",
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


def verify_existing_phase_evidence(
    root: Path,
    *,
    verify_git_history: bool = True,
    verify_successor_state: bool = True,
) -> Dict[str, Any]:
    """Verify the completed P01 receipt for safe historical-stage replay.

    This verifier trusts neither the evidence self-report nor the evidence index:
    it rehashes every signed input, the normalized reports, current acceptance
    code, rollback receipt, and the Stage 1 delivery prerequisite.
    """

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S02P01-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S02P01-RECEIPT-ROLLBACK-STRICT-JSON")

    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, dict):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S02-P01"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S02"
            and evidence.get("phase_id") == "P01"
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "OFFICIAL_PLATFORM_AND_REGULATORY_FACTS_FROZEN"
            and evidence.get("phase_status") == "S02_P01_PASS"
            and evidence.get("next") == "S02/P02_READY_NOT_STARTED"
            and evidence.get("artifacts")
            == {
                "ART-S02-P01-01": SOURCES_PATH.as_posix(),
                "ART-S02-P01-02": PROVIDER_FACTS_PATH.as_posix(),
                "ART-S02-P01-03": REGULATORY_MATRIX_PATH.as_posix(),
            }
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S02P01-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            validation.get("status") == "PASS"
            and validation.get("decision") == "OFFICIAL_PLATFORM_AND_REGULATORY_FACTS_FROZEN"
            and validation.get("summary", {}).get("failed") == 0
            and validation.get("next") == "S02/P02_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S02P01-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        effects = evidence.get("external_effect_boundary", {})
        effects_ok = (
            effects.get("github_upload_performed") is False
            and effects.get("wagering_provider_account_accessed") is False
            and effects.get("gmail_account_accessed") is False
            and effects.get("hosting_or_cdn_account_accessed") is False
            and effects.get("provider_api_called") is False
            and effects.get("incremental_cash_spent_aud") == "0.00"
            and effects.get("production_deployment_claimed") is False
            and effects.get("mainland_china_availability_claimed") is False
            and effects.get("real_order_capability_present") is False
            and effects.get("return_or_guarantee_claimed") is False
            and effects.get("s02_p02_started") is False
        )
        _add(checks, "S02P01-RECEIPT-NO-EXTERNAL-EFFECT", effects_ok, effects)

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
            "S02P01-RECEIPT-SIGNED-INPUTS-CURRENT",
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
        _add(checks, "S02P01-RECEIPT-REPORT-HASHES-CURRENT", not report_errors, report_errors or "all reports match")

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
            "S02P01-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_actual, "historical_phase_commit": historical_code},
        )
        rollback_binding = evidence.get("hashes", {}).get("rollback_evidence")
        _add(
            checks,
            "S02P01-RECEIPT-ROLLBACK-HASH-BINDING",
            rollback_binding == rollback_hash,
            {"expected": rollback_binding, "actual": rollback_hash},
        )
        absolute_local_paths = _absolute_local_paths(evidence)
        _add(
            checks,
            "S02P01-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
            not absolute_local_paths,
            absolute_local_paths or "portable evidence",
        )
    else:
        for check_id in [
            "S02P01-RECEIPT-EVIDENCE-INTEGRITY",
            "S02P01-RECEIPT-VALIDATION-ALL-PASS",
            "S02P01-RECEIPT-NO-EXTERNAL-EFFECT",
            "S02P01-RECEIPT-SIGNED-INPUTS-CURRENT",
            "S02P01-RECEIPT-REPORT-HASHES-CURRENT",
            "S02P01-RECEIPT-CODE-HASH-CURRENT",
            "S02P01-RECEIPT-ROLLBACK-HASH-BINDING",
            "S02P01-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
        ]:
            _add(checks, check_id, False, "evidence unavailable")

    if isinstance(rollback, dict):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S02-P01-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("fixed_clock") == FIXED_CLOCK
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and len(rollback.get("artifacts", {})) == 7
            and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
        )
        _add(checks, "S02P01-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S02P01-RECEIPT-ROLLBACK-INTEGRITY", False, "rollback unavailable")

    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p01 = [row for row in rows if row.get("id") == "INDEX-AC-S02-P01"]
        index_ok = (
            len(p01) == 1
            and p01[0].get("status") == "PASS"
            and p01[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and p01[0].get("artifact_sha256") == evidence_hash
            and p01[0].get("next") == "S02/P02_READY_NOT_STARTED"
        )
        _add(checks, "S02P01-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, p01)
    except Exception as exc:
        _add(checks, "S02P01-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))

    delivery = verify_stage1_delivery(root, verify_git_history=verify_git_history)
    _add(
        checks,
        "S02P01-RECEIPT-STAGE1-DELIVERY-CHAIN",
        delivery.get("status") == "PASS" and delivery.get("next") == "S02/P01_READY_NOT_STARTED",
        delivery.get("summary"),
    )
    if verify_successor_state:
        _check_s02_p02_not_started(root, checks, verify_git_history)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S02-P01",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S02_P01_EVIDENCE_VERIFIED" if not failed else "S02_P01_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for row in checks if row["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S02/P02_READY_NOT_STARTED" if not failed else "S02/P01_REMEDIATION_REQUIRED",
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

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S02P01-FIXTURE-STRICT-JSON")
    sources = _safe_load(root / SOURCES_PATH, checks, "S02P01-SOURCES-STRICT-JSON")
    provider_facts = _safe_load(root / PROVIDER_FACTS_PATH, checks, "S02P01-PROVIDER-FACTS-STRICT-JSON")
    regulatory = _safe_load(root / REGULATORY_MATRIX_PATH, checks, "S02P01-REGULATORY-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S02P01-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S02P01-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S02P01-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S02P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S02P01-TRACEABILITY-STRICT-JSON")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "S02P01-CANONICAL-STRICT-JSON")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "S02P01-COSTS-STRICT-JSON")
    provider_contracts = _safe_load(root / "machine/facts/provider_contracts.json", checks, "S02P01-PROVIDER-CONTRACTS-STRICT-JSON")

    _check_pinned_hashes(root, checks, hashes)
    import_markers = [Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py"), Path("tests/S02/__init__.py")]
    _add(
        checks,
        "S02P01-PYTEST-IMPORT-ISOLATION",
        all((root / path).is_file() for path in import_markers),
        [path.as_posix() for path in import_markers],
    )

    dictionaries = [fixture, sources, provider_facts, regulatory, roadmap, task_graph, canonical, costs, provider_contracts]
    arrays = [requirements, acceptance, traceability]
    if not all(isinstance(value, dict) for value in dictionaries) or not all(isinstance(value, list) for value in arrays):
        _add(checks, "S02P01-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S02P01-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S02P01-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        source_map = _check_source_catalog(sources, fixture, checks)
    except Exception as exc:
        source_map = {}
        _add(checks, "S02P01-SOURCE-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_provider_facts(provider_facts, fixture, source_map, checks)
    except Exception as exc:
        _add(checks, "S02P01-PROVIDER-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_regulatory_matrix(regulatory, fixture, source_map, checks)
    except Exception as exc:
        _add(checks, "S02P01-REGULATORY-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_cross_artifact_claims(sources, provider_facts, regulatory, checks)
    except Exception as exc:
        _add(checks, "S02P01-CROSS-ARTIFACT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_canonical_alignment(canonical, costs, provider_contracts.get("providers", []), checks)
    except Exception as exc:
        _add(checks, "S02P01-CANONICAL-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    no_float = not any(_contains_float(value) for value in [fixture, sources, provider_facts, regulatory])
    _add(checks, "S02P01-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS", no_float, "decimal facts remain strings")

    delivery = verify_stage1_delivery(root, verify_git_history=_verify_git_history)
    _add(
        checks,
        "S02P01-STAGE1-DELIVERY-CHAIN",
        delivery.get("status") == "PASS"
        and delivery.get("decision") == "S01_DELIVERED_S02_MAY_START"
        and delivery.get("next") == "S02/P01_READY_NOT_STARTED",
        delivery.get("summary"),
    )
    hashes.update(delivery.get("hashes", {}))
    _check_s02_p02_not_started(root, checks, _verify_git_history)
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
        (SOURCES_PATH.as_posix(), root / SOURCES_PATH),
        (PROVIDER_FACTS_PATH.as_posix(), root / PROVIDER_FACTS_PATH),
        (REGULATORY_MATRIX_PATH.as_posix(), root / REGULATORY_MATRIX_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (STAGE1_DELIVERY_RECEIPT_PATH.as_posix(), root / STAGE1_DELIVERY_RECEIPT_PATH),
        (STAGE1_REVIEW_EVIDENCE_PATH.as_posix(), root / STAGE1_REVIEW_EVIDENCE_PATH),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s02-p01-rollback-") as directory:
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
        "evidence_id": "EVD-S02-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_OFFICIAL_RESEARCH_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        SOURCES_PATH,
        PROVIDER_FACTS_PATH,
        REGULATORY_MATRIX_PATH,
        FIXTURE_PATH,
        *[Path(relative) for relative in PINNED_BASELINE_HASHES],
        Path("tests/S02/P01_test.py"),
        Path("tests/S02/__init__.py"),
        Path("abd_acceptance/official_platform_research.py"),
        Path("abd_acceptance/stage1_delivery.py"),
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
            "evidence_id": "EVD-S02-P01-ROLLBACK",
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
        result["phase_status"] = "S02_P01_FAILED"
        result["next"] = "S02/P01_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S02-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S02",
        "phase_id": "P01",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S02-P01-01": SOURCES_PATH.as_posix(),
            "ART-S02-P01-02": PROVIDER_FACTS_PATH.as_posix(),
            "ART-S02-P01-03": REGULATORY_MATRIX_PATH.as_posix(),
        },
        "stage1_delivery_prerequisite": {
            "receipt": STAGE1_DELIVERY_RECEIPT_PATH.as_posix(),
            "sha256": STAGE1_DELIVERY_RECEIPT_SHA256,
            "stage_review_evidence_sha256": STAGE1_REVIEW_EVIDENCE_SHA256,
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S02/P01 freezes official platform and regulatory research; it executes no prediction model, strategy, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing STAGE-REVIEW-S01",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S02/P01_test.py --junitxml=machine/evidence/S02/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S02-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": {
            "github_upload_performed": False,
            "wagering_provider_account_accessed": False,
            "gmail_account_accessed": False,
            "hosting_or_cdn_account_accessed": False,
            "provider_api_called": False,
            "secret_provisioned": False,
            "incremental_cash_spent_aud": "0.00",
            "production_deployment_claimed": False,
            "mainland_china_availability_claimed": False,
            "all_market_coverage_claimed": False,
            "real_order_capability_present": False,
            "return_or_guarantee_claimed": False,
            "s02_p02_started": False,
        },
        "explicit_unknowns": [
            "TAB Web Services and TAB Studio access are not granted or authorized by this research.",
            "Sportsbet automation or API permission was not established by the scoped official source set.",
            "Gmail consent, OAuth verification, restricted-data policy and security-assessment readiness remain unresolved; Gmail is not connected.",
            "Cloudflare account, free-plan headroom and deployment are unverified; mainland-China in-country delivery is outside the A$0 scope and is not claimed.",
            "The owner-declared existing OVH VPS was not inspected; 7x24 runtime, capacity, billing and availability remain unverified.",
            "Owner jurisdiction, KYC, provider eligibility, self-exclusion status and provider terms acceptance remain unverified.",
            "The 30% monthly target, all-market coverage, actual return and ROI remain unverified and are not guaranteed.",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S02-P01"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S02-P01 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S02/P02_READY_NOT_STARTED" if status == "PASS" else "S02/P01_REMEDIATION_REQUIRED"
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
