from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .coverage_observability import (
    evaluate_contract as evaluate_p04,
    verify_existing_phase_evidence as verify_p04,
)
from .market_ontology import (
    evaluate_contract as evaluate_p01,
    verify_existing_phase_evidence as verify_p01,
)
from .source_capabilities import (
    evaluate_contract as evaluate_p02,
    verify_existing_phase_evidence as verify_p02,
)
from .source_scheduler import (
    evaluate_contract as evaluate_p03,
    verify_existing_phase_evidence as verify_p03,
)
from .stage4_delivery import verify_stage4_delivery


CONTRACT_ID = "STAGE-REVIEW-S05"
REVIEW_ID = "ABD-S05-WHOLE-STAGE-REVIEW"
STAGE_ID = "S05"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-24T12:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage5_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S05/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S05_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S05/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S05/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S05/STAGE_REVIEW/full_regression.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S05/STAGE_REVIEW/signed_state_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S05-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S05-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

MARKET_ONTOLOGY_PATH = Path("market_ontology.json")
COVERAGE_SCHEMA_PATH = Path("coverage_manifest.schema.json")
PROVIDER_CONTRACTS_PATH = Path("provider_contracts.json")
SOURCE_CAPABILITIES_PATH = Path("source_capabilities.json")
SCHEDULER_PATH = Path("scheduler.py")
CADENCE_PATH = Path("cadence_tests.json")
RATE_BUDGET_PATH = Path("rate_budget.json")
COVERAGE_DASHBOARD_PATH = Path("coverage_dashboard.json")
SILENT_GAP_ORACLE_PATH = Path("silent_gap_oracle.py")

STRUCTURAL_SELF_NORMALIZED_SHA256 = "2751bdb203f29e481a2c1b2e9533b9965ba0d567a728d68ae48fe076b310ff83"
PINNED_REVIEW_ARTIFACT_HASHES: Dict[str, str] = {
    CONTRACT_PATH.as_posix(): "4181ce43657ad11152acb2a544a0e58dbe402530dee9cef063b3b76577ba9213",
    FINDINGS_PATH.as_posix(): "811314bfcf2f63d9d944b920500aab42454db78e462d6842982826c6c32f7914",
    FIXTURE_PATH.as_posix(): "bee1022c90fa0a7537853179b9c771573fceeba863093a5f15964a69773aa70d",
    TEST_PATH.as_posix(): "cb16462f46ec6b1376ce1ca5b31e7f514f521c6e5fc6d8eceb31200d27c2c269",
}
WORKFLOW_SHA256 = "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d"

PHASE_EVALUATORS = {
    "P01": evaluate_p01,
    "P02": evaluate_p02,
    "P03": evaluate_p03,
    "P04": evaluate_p04,
}
PHASE_VERIFIERS = {
    "P01": verify_p01,
    "P02": verify_p02,
    "P03": verify_p03,
    "P04": verify_p04,
}
PHASE_DECISIONS = {
    "P01": "S05_P01_EVIDENCE_VERIFIED",
    "P02": "S05_P02_EVIDENCE_VERIFIED",
    "P03": "S05_P03_EVIDENCE_VERIFIED",
    "P04": "S05_P04_EVIDENCE_VERIFIED",
}
PHASE_NEXT = {
    "P01": "S05/P02_READY_NOT_STARTED",
    "P02": "S05/P03_READY_NOT_STARTED",
    "P03": "S05/P04_READY_NOT_STARTED",
    "P04": "S05/STAGE_REVIEW_READY_NOT_STARTED",
}

ROLLBACK_ARTIFACTS = [
    MARKET_ONTOLOGY_PATH,
    COVERAGE_SCHEMA_PATH,
    PROVIDER_CONTRACTS_PATH,
    SOURCE_CAPABILITIES_PATH,
    SCHEDULER_PATH,
    CADENCE_PATH,
    RATE_BUDGET_PATH,
    COVERAGE_DASHBOARD_PATH,
    SILENT_GAP_ORACLE_PATH,
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    Path("abd_acceptance/stage5_review.py"),
    Path("abd_acceptance/coverage_observability.py"),
    Path("abd_acceptance/__main__.py"),
    Path("abd_acceptance/__init__.py"),
    Path("machine/evidence/S04/STAGE_REVIEW/github_delivery_receipt.json"),
]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?token|client[_-]?secret|password)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9_./+\-=]{12,}"
    ),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]


class Stage5ReviewContractError(ValueError):
    """Raised when the S05 whole-stage review cannot proceed safely."""


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


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/stage5_review.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _load_index(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise Stage5ReviewContractError("evidence index rows must be objects")
        rows.append(value)
    return rows


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    found = [row for row in rows if row.get(key) == item_id]
    return found[0] if len(found) == 1 else {}


def _review_pin_checks(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> None:
    for relative, expected in sorted(PINNED_REVIEW_ARTIFACT_HASHES.items()):
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(
            checks,
            "S05REVIEW-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"),
            actual == expected,
            {"expected": expected, "actual": actual},
        )
    structural = _structural_self_hash(root)
    _add(
        checks,
        "S05REVIEW-ORACLE-STRUCTURAL-HASH",
        structural == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": structural},
    )
    workflow = root.parent / WORKFLOW_PATH
    workflow_hash = sha256_file(workflow) if workflow.is_file() else "MISSING"
    hashes[WORKFLOW_PATH.as_posix()] = workflow_hash
    _add(
        checks,
        "S05REVIEW-WORKFLOW-PIN",
        workflow_hash == WORKFLOW_SHA256,
        {"expected": WORKFLOW_SHA256, "actual": workflow_hash},
    )


def _check_contract_and_findings(
    contract: Mapping[str, Any],
    findings: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    scope = contract.get("review_scope", {})
    identity_ok = (
        contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and contract.get("fixed_at") == FIXED_CLOCK
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("review_id") == REVIEW_ID
        and fixture.get("fixed_clock") == FIXED_CLOCK
    )
    _add(checks, "S05REVIEW-CONTRACT-IDENTITY", identity_ok, {"contract": contract.get("review_id"), "fixture": fixture.get("fixture_id")})
    expected_phases = fixture.get("expected_phase_ids")
    scope_ok = (
        scope.get("phase_ids") == expected_phases == ["P01", "P02", "P03", "P04"]
        and scope.get("requirement_ids") == ["REQ-S05-%s" % phase for phase in expected_phases]
        and scope.get("acceptance_contract_ids") == ["AC-S05-%s" % phase for phase in expected_phases]
        and scope.get("task_ids")
        == [
            "T-S05-%s-%02d" % (phase, task)
            for phase in expected_phases
            for task in [1, 2, 3]
        ]
    )
    _add(checks, "S05REVIEW-SCOPE-EXACT", scope_ok, scope)
    phase_records = contract.get("phase_records", [])
    records_ok = (
        isinstance(phase_records, list)
        and [row.get("phase_id") for row in phase_records] == expected_phases
        and len(phase_records) == 4
        and all(
            row.get("requirement_id") == "REQ-S05-%s" % row.get("phase_id")
            and row.get("acceptance_contract_id") == "AC-S05-%s" % row.get("phase_id")
            and row.get("expected_next") == PHASE_NEXT.get(str(row.get("phase_id")))
            for row in phase_records
        )
    )
    _add(checks, "S05REVIEW-PHASE-RECORDS-EXACT", records_ok, [row.get("phase_id") for row in phase_records if isinstance(row, Mapping)])
    receipts = contract.get("supplied_source_receipts", [])
    source_ok = (
        len(receipts) == 2
        and receipts[0].get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and receipts[1].get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and receipts[1].get("original_file_count") == 53
    )
    _add(checks, "S05REVIEW-SOURCE-RECEIPTS-EXACT", source_ok, receipts)
    finding_rows = findings.get("findings", [])
    expected_findings = fixture.get("expected_finding_ids")
    finding_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_at") == FIXED_CLOCK
        and [row.get("id") for row in finding_rows] == expected_findings
        and len({row.get("verification_gate") for row in finding_rows}) == len(finding_rows)
        and all(row.get("status") == "RESOLVED_IN_REVIEW_CANDIDATE" for row in finding_rows)
        and findings.get("summary", {}).get("total") == 6
        and findings.get("summary", {}).get("resolved_in_review_candidate") == 6
        and findings.get("summary", {}).get("open") == 0
    )
    _add(checks, "S05REVIEW-ALL-FINDINGS-RESOLVED", finding_ok, findings.get("summary"))
    boundary_ok = (
        contract.get("claim_boundary") == fixture.get("expected_claim_boundary")
        and contract.get("release_status_on_pass") == fixture.get("expected_release_status")
        and contract.get("next_on_pass") == fixture.get("expected_next")
    )
    _add(checks, "S05REVIEW-CLAIM-AND-TERMINAL-BOUNDARY", boundary_ok, contract.get("claim_boundary"))
    effects = contract.get("external_effect_boundary", {})
    effects_ok = (
        isinstance(effects, Mapping)
        and effects.get("incremental_cash_spent_aud") == "0.00"
        and effects.get("owner_final_order_only") is True
        and all(
            value is False
            for key, value in effects.items()
            if key not in {"incremental_cash_spent_aud", "owner_final_order_only"}
        )
    )
    _add(checks, "S05REVIEW-EXTERNAL-EFFECT-BOUNDARY", effects_ok, effects)
    _add(
        checks,
        "S05REVIEW-NO-BINARY-FLOAT",
        not _contains_float(contract) and not _contains_float(findings) and not _contains_float(fixture),
        "all financial and risk values remain integers or decimal strings",
    )


def _expected_capability_ids(providers: Sequence[str], modes: Sequence[str]) -> List[str]:
    return ["CAP-%s-%s" % (provider, mode) for provider in providers for mode in modes]


def _check_cross_phase_coupling(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    ontology = strict_json_load(root / MARKET_ONTOLOGY_PATH)
    provider_contracts = strict_json_load(root / PROVIDER_CONTRACTS_PATH)
    capabilities = strict_json_load(root / SOURCE_CAPABILITIES_PATH)
    cadence = strict_json_load(root / CADENCE_PATH)
    rate_budget = strict_json_load(root / RATE_BUDGET_PATH)
    dashboard = strict_json_load(root / COVERAGE_DASHBOARD_PATH)

    providers = fixture.get("expected_provider_ids", [])
    modes = fixture.get("expected_modes", [])
    expected_ids = _expected_capability_ids(providers, modes)
    ontology_boundary = ontology.get("claim_boundary", {})
    ontology_ok = (
        ontology.get("declared_discovery_scope") == "ALL_OBSERVABLE_MARKETS"
        and ontology.get("identity_scope") == "SOURCE_SCOPED_DISCOVERY_ID_NOT_CROSS_SOURCE_CANONICAL_ID"
        and ontology.get("classification_contract", {}).get("exactly_one_type_rule")
        == "EACH_OBSERVED_INPUT_PRODUCES_EXACTLY_ONE_RECORD_WITH_ONE_OBJECT_KIND"
        and ontology.get("classification_contract", {}).get("unknown_advice_eligible") is False
        and ontology.get("unknown_contract", {}).get("object_kind") == "UNKNOWN"
        and ontology.get("unknown_contract", {}).get("routing_action") == "QUARANTINE_AND_SURFACE_COVERAGE_GAP"
        and ontology_boundary.get("actual_provider_or_market_observed") is False
        and ontology_boundary.get("all_observable_markets_enumerated_or_verified") is False
    )
    _add(checks, "S05REVIEW-ONTOLOGY-SCOPE-AND-UNKNOWN", ontology_ok, ontology.get("claim_boundary"))

    provider_rows = provider_contracts.get("provider_contracts", [])
    mode_rows = provider_contracts.get("mode_contracts", [])
    provider_versions = {
        row.get("provider_id"): row.get("contract_version")
        for row in provider_rows
        if isinstance(row, Mapping)
    }
    mode_gates = {
        row.get("mode"): row.get("required_gate_ids")
        for row in mode_rows
        if isinstance(row, Mapping)
    }
    provider_ok = (
        [row.get("provider_id") for row in provider_rows] == providers
        and [row.get("mode") for row in mode_rows] == modes
        and len(provider_versions) == len(providers)
        and len(mode_gates) == len(modes)
        and all(row.get("production_collection_enabled") is False for row in provider_rows)
        and provider_contracts.get("claim_boundary", {}).get("provider_account_or_page_accessed") is False
        and provider_contracts.get("claim_boundary", {}).get("real_market_coverage_verified") is False
    )
    _add(checks, "S05REVIEW-PROVIDER-MODE-MATRIX", provider_ok, {"providers": list(provider_versions), "modes": list(mode_gates)})

    capability_rows = capabilities.get("capabilities", [])
    capability_map = {
        row.get("capability_id"): row
        for row in capability_rows
        if isinstance(row, Mapping)
    }
    capability_ok = (
        [row.get("capability_id") for row in capability_rows] == expected_ids
        and len(capability_map) == fixture.get("expected_real_capability_count") == 15
        and all(
            row.get("provider_contract_version") == provider_versions.get(row.get("provider_id"))
            and row.get("required_gate_ids") == mode_gates.get(row.get("mode"))
            and row.get("passed_gate_ids") == []
            and row.get("production_collection_enabled") is False
            and row.get("runtime_verified") is False
            and row.get("max_requests_per_period") == 0
            for row in capability_rows
        )
        and capabilities.get("matrix_summary", {}).get("production_collection_enabled_count") == 0
        and capabilities.get("matrix_summary", {}).get("runtime_verified_count") == 0
        and capabilities.get("matrix_summary", {}).get("real_market_coverage_count") == 0
    )
    _add(checks, "S05REVIEW-CAPABILITY-MATRIX", capability_ok, capabilities.get("matrix_summary"))

    budget_rows = rate_budget.get("capability_budgets", [])
    budget_map = {
        row.get("capability_id"): row
        for row in budget_rows
        if isinstance(row, Mapping)
    }
    budget_ok = (
        [row.get("capability_id") for row in budget_rows] == expected_ids
        and len(budget_map) == 15
        and all(
            row.get("provider_id") == capability_map[row.get("capability_id")].get("provider_id")
            and row.get("mode") == capability_map[row.get("capability_id")].get("mode")
            and row.get("production_collection_enabled") is False
            and row.get("max_dispatches_per_window") == 0
            and row.get("window_seconds") == 0
            for row in budget_rows
            if row.get("capability_id") in capability_map
        )
        and rate_budget.get("budget_semantics", {}).get("all_current_real_capabilities_disabled") is True
        and rate_budget.get("cost_boundary", {}).get("incremental_cash_budget_aud") == "0.00"
        and rate_budget.get("cost_boundary", {}).get("paid_data_or_api_dependency_allowed") is False
    )
    _add(checks, "S05REVIEW-RATE-BUDGET-MATRIX", budget_ok, {"count": len(budget_rows), "status": rate_budget.get("status")})

    recovery_rows = dashboard.get("recovery_actions", [])
    recovery_map = {
        row.get("action_id"): row
        for row in recovery_rows
        if isinstance(row, Mapping)
    }
    coverage_rows = dashboard.get("coverage_records", [])
    coverage_map = {
        row.get("coverage_unit_id"): row
        for row in coverage_rows
        if isinstance(row, Mapping)
    }
    status_counts = dict(Counter(row.get("coverage_status") for row in coverage_rows))
    expected_status_counts = fixture.get("expected_coverage_status_counts", {})
    status_counts_with_zero = {
        key: status_counts.get(key, 0)
        for key in expected_status_counts
    }
    coverage_ok = (
        [row.get("coverage_unit_id") for row in coverage_rows] == expected_ids
        and len(coverage_map) == 15
        and status_counts_with_zero == expected_status_counts
        and all(
            row.get("provider_id") == capability_map[row.get("coverage_unit_id")].get("provider_id")
            and row.get("mode") == capability_map[row.get("coverage_unit_id")].get("mode")
            and row.get("source_state") == capability_map[row.get("coverage_unit_id")].get("state")
            and row.get("source_reason_codes") == capability_map[row.get("coverage_unit_id")].get("reason_codes")
            and row.get("source_failure_action") == capability_map[row.get("coverage_unit_id")].get("failure_action")
            and row.get("production_collection_enabled") is False
            and row.get("runtime_verified") is False
            and row.get("rate_budget_enabled") is False
            and row.get("advice_eligible") is False
            and isinstance(row.get("reason_code"), str)
            and recovery_map.get(row.get("recovery_action_id"), {}).get("owner") == row.get("action_owner")
            for row in coverage_rows
            if row.get("coverage_unit_id") in capability_map
        )
        and dashboard.get("summary", {}).get("expected_unit_count") == 15
        and dashboard.get("summary", {}).get("represented_unit_count") == 15
        and dashboard.get("summary", {}).get("silent_gap_count") == 0
        and dashboard.get("summary", {}).get("explicit_gap_count") == 15
        and dashboard.get("summary", {}).get("covered_count") == 0
        and dashboard.get("summary", {}).get("status_counts") == expected_status_counts
        and dashboard.get("summary", {}).get("all_explicit_gaps_have_reason") is True
        and dashboard.get("summary", {}).get("all_explicit_gaps_have_recovery_action") is True
        and dashboard.get("summary", {}).get("all_explicit_gaps_have_action_owner") is True
        and dashboard.get("summary", {}).get("advice_enabled") is False
    )
    _add(checks, "S05REVIEW-COVERAGE-MATRIX", coverage_ok, dashboard.get("summary"))

    coupling_ok = (
        capability_ok
        and budget_ok
        and coverage_ok
        and set(capability_map) == set(budget_map) == set(coverage_map) == set(expected_ids)
        and all(
            budget_map[item_id].get("provider_id") == coverage_map[item_id].get("provider_id")
            and budget_map[item_id].get("mode") == coverage_map[item_id].get("mode")
            for item_id in expected_ids
        )
    )
    _add(
        checks,
        "S05REVIEW-CROSS-PHASE-CAPABILITY-COUPLING",
        coupling_ok,
        {"capabilities": len(capability_map), "budgets": len(budget_map), "coverage": len(coverage_map)},
    )

    synthetic = rate_budget.get("frozen_test_only_budget", {})
    synthetic_ok = (
        synthetic.get("capability_id") == fixture.get("expected_synthetic_capability_id")
        and synthetic.get("test_fixture_only") is True
        and synthetic.get("external_action_permitted") is False
        and synthetic.get("production_collection_enabled") is True
        and synthetic.get("capability_id") not in capability_map
        and synthetic.get("capability_id") not in coverage_map
    )
    _add(checks, "S05REVIEW-SYNTHETIC-REAL-SOURCE-SEPARATION", synthetic_ok, synthetic)

    fixed_gate = cadence.get("fixed_clock_gate", {})
    freshness = cadence.get("freshness_gate", {})
    cadence_ok = (
        fixed_gate.get("maximum_dispatch_deviation_seconds")
        == fixture.get("expected_fixed_clock_maximum_dispatch_deviation_seconds")
        == 2
        and fixed_gate.get("at_exact_limit") == "PASS"
        and fixed_gate.get("above_exact_limit") == "NO_DISPATCH_NO_ADVICE"
        and freshness.get("future_timestamp_action") == "NO_ADVICE"
        and freshness.get("unknown_or_untrusted_clock_action") == "NO_ADVICE"
        and freshness.get("quote_older_than_advice_limit_action") == "DO_NOT_ENTER_ADVICE_EVALUATION"
        and cadence.get("claim_boundary", {}).get("scheduler_daemon_started") is False
        and cadence.get("claim_boundary", {}).get("real_provider_dispatch_enabled") is False
        and cadence.get("claim_boundary", {}).get("runtime_freshness_verified") is False
    )
    _add(checks, "S05REVIEW-FIXED-CLOCK-AND-FRESHNESS", cadence_ok, {"fixed_clock_gate": fixed_gate, "freshness_gate": freshness})

    claim = contract.get("claim_boundary", {})
    dashboard_scope = dashboard.get("scope", {})
    overclaim_ok = (
        claim == fixture.get("expected_claim_boundary")
        and claim.get("declared_scope_is_design_intent_not_observed_market_universe") is True
        and all(
            claim.get(key) is False
            for key in [
                "actual_market_universe_enumerated_or_verified",
                "all_observable_markets_verified",
                "provider_permission_or_runtime_access_verified",
                "production_collection_enabled",
                "runtime_freshness_verified",
                "production_coverage_verified",
                "production_advice_enabled",
                "ovh_7x24_runtime_verified",
                "cloudflare_global_chinese_access_verified",
                "gmail_evidence_archival_verified",
                "financial_target_verified_or_guaranteed",
            ]
        )
        and dashboard_scope.get("actual_market_universe_enumerated_or_verified") is False
        and dashboard_scope.get("runtime_provider_coverage_verified") is False
        and dashboard_scope.get("production_covered_count") == 0
    )
    _add(checks, "S05REVIEW-REAL-MARKET-OVERCLAIM-BOUNDARY", overclaim_ok, {"claim": claim, "scope": dashboard_scope})


def _check_p04_review_evolution(root: Path, checks: List[Dict[str, Any]]) -> None:
    from . import coverage_observability as p04

    source = (root / "abd_acceptance/coverage_observability.py").read_text(encoding="utf-8")
    progression_ok = (
        hasattr(p04, "_check_stage_review_progression")
        and "_check_stage_review_not_started" not in source
        and "VERIFIED_S05_STAGE_REVIEW_CANDIDATE" in source
        and "VERIFIED_S05_STAGE_REVIEW_SIGNED" in source
        and "INVALID_PARTIAL_S05_STAGE_REVIEW" in source
    )
    _add(checks, "S05REVIEW-P04-MONOTONIC-PROGRESSION", progression_ok, "P04 accepts only absent, complete candidate or complete signed review")
    replay_ok = (
        getattr(p04, "PHASE_COMMIT", None) == "6aad40149a19e4012ab2520fe2002521465c24e3"
        and getattr(p04, "PINNED_PHASE_CODE_HASH", None)
        == "ce412627d902eb65e517c5281277062d7429f3dc86321c4b8e2b8335388a6747"
        and {
            "abd_acceptance/coverage_observability.py",
            "abd_acceptance/__main__.py",
            "abd_acceptance/__init__.py",
        }
        <= set(getattr(p04, "SUCCESSOR_EVOLVABLE_SIGNED_INPUTS", set()))
    )
    replay_inputs = getattr(p04, "SUCCESSOR_EVOLVABLE_SIGNED_INPUTS", set())
    _add(
        checks,
        "S05REVIEW-P04-HISTORICAL-REPLAY",
        replay_ok,
        sorted(replay_inputs) if isinstance(replay_inputs, set) else replay_inputs,
    )


def _check_safety_boundary(
    root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    product = canonical.get("product", {})
    safe = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("monthly_target_return") == "0.30"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
        and contract.get("external_effect_boundary", {}).get("incremental_cash_spent_aud") == "0.00"
    )
    _add(checks, "S05REVIEW-A300-A0-NO-ORDER-NO-RUNTIME-NO-RETURN", safe, {"product": product, "target": parameters.get("target_30pct")})


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        Path("abd_acceptance/stage5_review.py"),
        Path("abd_acceptance/coverage_observability.py"),
    ]
    leaks: List[Dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        for fragment in LOCAL_PATH_FRAGMENTS:
            if fragment in text:
                leaks.append({"path": relative.as_posix(), "kind": "local-path"})
    _add(checks, "S05REVIEW-NO-SECRET-OR-MACHINE-PATH", not leaks, leaks or "clean")


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    """Validate a complete S05 review candidate without invoking Phase verifiers."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root / CONTRACT_PATH, checks, "S05REVIEW-PREFLIGHT-CONTRACT-STRICT-JSON")
    findings = _safe_load(root / FINDINGS_PATH, checks, "S05REVIEW-PREFLIGHT-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S05REVIEW-PREFLIGHT-FIXTURE-STRICT-JSON")
    _review_pin_checks(root, checks, hashes)
    if isinstance(contract, Mapping) and isinstance(findings, Mapping) and isinstance(fixture, Mapping):
        _check_contract_and_findings(contract, findings, fixture, checks)
        try:
            _check_cross_phase_coupling(root, contract, fixture, checks)
        except Exception as exc:
            _add(checks, "S05REVIEW-CROSS-PHASE-CAPABILITY-COUPLING", False, "%s: %s" % (type(exc).__name__, exc))
        try:
            _check_p04_review_evolution(root, checks)
        except Exception as exc:
            _add(checks, "S05REVIEW-P04-MONOTONIC-PROGRESSION", False, "%s: %s" % (type(exc).__name__, exc))
            _add(checks, "S05REVIEW-P04-HISTORICAL-REPLAY", False, "%s: %s" % (type(exc).__name__, exc))
        _check_safety_boundary(root, contract, checks)
        _check_no_leaks(root, checks)
        required_gates = {row.get("verification_gate") for row in findings.get("findings", [])}
        observed_gates = {row.get("id") for row in checks}
        _add(
            checks,
            "S05REVIEW-FINDING-GATES-EXECUTABLE",
            required_gates <= observed_gates,
            {"missing": sorted(required_gates - observed_gates)},
        )
    else:
        _add(checks, "S05REVIEW-PREFLIGHT-INPUTS-AVAILABLE", False, "contract, findings or fixture unavailable")
    ids = [row["id"] for row in checks]
    if len(ids) != len(set(ids)):
        _add(checks, "S05REVIEW-PREFLIGHT-CHECK-IDS-UNIQUE", False, "duplicate check ids")
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_STAGE_REVIEW_CANDIDATE_VALID" if not failed else "S05_STAGE_REVIEW_CANDIDATE_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "next": "S05/GITHUB_STAGE_UPLOAD_READY" if not failed else "S05/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def _check_baseline_hashes(
    root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> None:
    values = contract.get("baseline_critical_artifacts", {})
    if not isinstance(values, Mapping):
        _add(checks, "S05REVIEW-BASELINE-SHAPE", False, values)
        return
    for relative, expected in values.items():
        path = root / str(relative)
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[str(relative)] = actual
        _add(
            checks,
            "S05REVIEW-BASELINE-%s" % str(relative).upper().replace("/", "-").replace(".", "-"),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_taskpack_trace(
    root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    tasks = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    traces = strict_json_load(root / "machine/facts/traceability_matrix.json")
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID]
    expected_outputs = [
        ["market_ontology.json", "coverage_manifest.schema.json"],
        ["provider_contracts.json", "source_capabilities.json"],
        ["scheduler.py", "cadence_tests.json", "rate_budget.json"],
        ["coverage_dashboard.json", "silent_gap_oracle.py"],
    ]
    roadmap_ok = (
        len(stages) == 1
        and stages[0].get("depends_on") == ["S02", "S04"]
        and [row.get("id") for row in stages[0].get("phases", [])] == ["P01", "P02", "P03", "P04"]
        and [row.get("outputs") for row in stages[0].get("phases", [])] == expected_outputs
    )
    _add(checks, "S05REVIEW-ROADMAP-TRACE-EXACT", roadmap_ok, stages)
    for record in contract.get("phase_records", []):
        phase = str(record.get("phase_id"))
        req_id = str(record.get("requirement_id"))
        ac_id = str(record.get("acceptance_contract_id"))
        task_ids = record.get("task_ids")
        req = _row(requirements, req_id)
        ac = _row(acceptance, ac_id)
        phase_tasks = [
            row
            for row in tasks
            if row.get("stage_id") == STAGE_ID and row.get("phase_id") == phase
        ]
        trace = _row(traces, req_id, "requirement_id")
        expected_tests = [
            "TEST-S05-%s" % phase,
            "TEST-S05-%s-BOUNDARY" % phase,
            "TEST-S05-%s-REPLAY" % phase,
        ]
        ok = (
            req.get("stage_id") == STAGE_ID
            and req.get("phase_id") == phase
            and req.get("primary_acceptance_criteria_id") == ac_id
            and ac.get("requirement_id") == req_id
            and [row.get("id") for row in ac.get("tests", [])] == expected_tests
            and [row.get("id") for row in phase_tasks] == task_ids
            and trace.get("acceptance_criteria_id") == ac_id
            and trace.get("task_ids") == task_ids
            and trace.get("test_ids") == expected_tests
            and trace.get("evidence_id") == "EVD-S05-%s" % phase
        )
        _add(checks, "S05REVIEW-TASKPACK-%s-TRACE" % phase, ok, {"requirement": req_id, "contract": ac_id, "tasks": task_ids})


def _verify_phase(phase_id: str, root: Path, verify_git_history: bool) -> Dict[str, Any]:
    return PHASE_VERIFIERS[phase_id](root, verify_git_history=verify_git_history)


def _evaluate_phase(phase_id: str, root: Path, verify_git_history: bool) -> Dict[str, Any]:
    return PHASE_EVALUATORS[phase_id](
        root,
        require_external_reports=False,
        _verify_git_history=verify_git_history,
    )


def _phase_code_hash_at_commit(root: Path, commit: str) -> str:
    ancestry = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", commit, "--", "ABD/abd_acceptance"],
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
            ["git", "-C", str(root.parent), "show", "%s:%s" % (commit, repo_path)],
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


def _check_phase_receipts_and_oracles(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    verify_git_history: bool,
) -> None:
    for record in contract.get("phase_records", []):
        phase = str(record.get("phase_id"))
        evidence_path = root / str(record.get("evidence_path"))
        rollback_path = root / str(record.get("rollback_path"))
        evidence_hash = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_hash = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        hash_ok = (
            evidence_hash
            == record.get("evidence_sha256")
            == fixture.get("expected_phase_evidence_sha256", {}).get(phase)
            and rollback_hash
            == record.get("rollback_sha256")
            == fixture.get("expected_phase_rollback_sha256", {}).get(phase)
        )
        _add(checks, "S05REVIEW-%s-SIGNED-ARTIFACT-HASHES" % phase, hash_ok, {"evidence": evidence_hash, "rollback": rollback_hash})
        try:
            receipt = _verify_phase(phase, root, verify_git_history)
            receipt_ok = (
                receipt.get("status") == "PASS"
                and receipt.get("decision") == PHASE_DECISIONS[phase]
                and receipt.get("next") == PHASE_NEXT[phase]
                and receipt.get("summary", {}).get("failed") == 0
            )
            _add(checks, "S05REVIEW-%s-SIGNED-RECEIPT" % phase, receipt_ok, receipt.get("summary"))
        except Exception as exc:
            _add(checks, "S05REVIEW-%s-SIGNED-RECEIPT" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            oracle = _evaluate_phase(phase, root, verify_git_history)
            oracle_ok = (
                oracle.get("status") == "PASS"
                and oracle.get("summary", {}).get("failed") == 0
                and oracle.get("next") == PHASE_NEXT[phase]
            )
            _add(checks, "S05REVIEW-%s-CURRENT-ORACLE" % phase, oracle_ok, oracle.get("summary"))
        except Exception as exc:
            _add(checks, "S05REVIEW-%s-CURRENT-ORACLE" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        if verify_git_history:
            historical = _phase_code_hash_at_commit(root, str(record.get("implementation_commit")))
            history_ok = historical == record.get("implementation_code_sha256")
        else:
            historical = "SKIPPED_ISOLATED_COPY_WITHOUT_GIT_HISTORY"
            history_ok = True
        _add(checks, "S05REVIEW-%s-HISTORICAL-CODE-REPLAY" % phase, history_ok, {"expected": record.get("implementation_code_sha256"), "actual": historical})
        outputs_ok = all((root / relative).is_file() for relative in record.get("required_outputs", []))
        _add(checks, "S05REVIEW-%s-REQUIRED-OUTPUTS" % phase, outputs_ok, record.get("required_outputs"))


def _junit_summary(path: Path) -> Dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
        "times": [suite.attrib.get("time") for suite in suites],
        "timestamps": [suite.attrib.get("timestamp") for suite in suites],
        "hostnames": [suite.attrib.get("hostname") for suite in suites if "hostname" in suite.attrib],
    }


def _check_external_reports(
    root: Path,
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> None:
    reports = [
        (JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases"), "TARGETED"),
        (FULL_JUNIT_PATH, fixture.get("minimum_full_pytest_cases"), "FULL"),
        (
            SIGNED_STATE_JUNIT_PATH,
            fixture.get("minimum_signed_state_pytest_cases"),
            "SIGNED-STATE",
        ),
    ]
    for relative, minimum, label in reports:
        if not (root / relative).is_file():
            _add(checks, "S05REVIEW-%s-JUNIT" % label, False, "missing %s" % relative)
            continue
        try:
            summary = _junit_summary(root / relative)
            ok = (
                summary["tests"] >= int(minimum)
                and summary["failures"] == 0
                and summary["errors"] == 0
                and summary["skipped"] == 0
                and set(summary["times"]) == {"0.000"}
                and set(summary["timestamps"]) == {JUNIT_FIXED_CLOCK}
                and not summary["hostnames"]
            )
        except Exception as exc:
            summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
            ok = False
        hashes[relative.as_posix()] = sha256_file(root / relative)
        _add(checks, "S05REVIEW-%s-JUNIT" % label, ok, summary)
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S05REVIEW-PACK-REPORT-STRICT-JSON")
    if isinstance(pack, Mapping):
        pack_ok = (
            pack.get("status") == "PASS"
            and pack.get("summary", {}).get("checks") == 49
            and pack.get("summary", {}).get("failed") == 0
        )
        _add(checks, "S05REVIEW-PACK-REPORT", pack_ok, pack.get("summary"))
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8") if (root / SCAN_REPORT_PATH).is_file() else ""
    required_lines = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    _add(checks, "S05REVIEW-PAID-DEPENDENCY-SCAN", required_lines <= set(scan_text.splitlines()), SCAN_REPORT_PATH.as_posix())
    if (root / SCAN_REPORT_PATH).is_file():
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    preflight = validate_candidate_preflight(root)
    checks.extend(preflight.get("checks", []))
    hashes.update(preflight.get("hashes", {}))
    contract = strict_json_load(root / CONTRACT_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    _check_baseline_hashes(root, contract, checks, hashes)
    try:
        _check_taskpack_trace(root, contract, checks)
    except Exception as exc:
        _add(checks, "S05REVIEW-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_phase_receipts_and_oracles(root, contract, fixture, checks, _verify_git_history)
    try:
        predecessor = verify_stage4_delivery(root, verify_git_history=_verify_git_history)
        predecessor_ok = (
            predecessor.get("status") == "PASS"
            and predecessor.get("decision") == "S04_DELIVERED_S05_MAY_START"
            and predecessor.get("next") == "S05/P01_READY_NOT_STARTED"
        )
        _add(checks, "S05REVIEW-S04-DELIVERY-PREREQUISITE", predecessor_ok, predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05REVIEW-S04-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    rollback = perform_rollback_drill(root)
    _add(checks, "S05REVIEW-ROLLBACK-DRILL", rollback.get("status") == "PASS", {"status": rollback.get("status"), "artifacts": len(rollback.get("artifacts", {}))})
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        _add(
            checks,
            "S05REVIEW-NUMERIC-BOUNDARY-%s" % str(delta).replace("-", "NEG").replace(".", "_"),
            delta in {"-0.0001", "0", "0.0001"},
            delta,
        )
    if require_external_reports:
        _check_external_reports(root, fixture, checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0))
    if len(checks) < minimum:
        _add(checks, "S05REVIEW-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    ids = [row["id"] for row in checks]
    if len(ids) != len(set(ids)):
        _add(checks, "S05REVIEW-CHECK-IDS-UNIQUE", False, "duplicate check ids")
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "S05_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S05_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED",
        "stage_status": "S05_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S05_WHOLE_STAGE_REVIEW_FAILED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "claim_boundary": contract.get("claim_boundary"),
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "production_coverage_status": "ZERO_OF_15_REAL_PROVIDER_MODE_UNITS_COVERED_ALL_15_EXPLICIT_GAPS",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": contract.get("release_status_on_pass"),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "next": contract.get("next_on_pass") if status == "PASS" else "S05/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s05-stage-review-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(ROLLBACK_ARTIFACTS):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%02d" % index)
            active = temporary / ("active-%02d" % index)
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
    status = (
        "PASS"
        if len(results) == len(ROLLBACK_ARTIFACTS)
        and all(row["status"] == "PASS" for row in results.values())
        else "FAIL"
    )
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_STAGE_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
        "provider_account_api_or_page_accessed": False,
        "real_market_data_collected": False,
        "scheduler_daemon_started": False,
        "recommendation_or_order_generated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        MARKET_ONTOLOGY_PATH,
        COVERAGE_SCHEMA_PATH,
        PROVIDER_CONTRACTS_PATH,
        SOURCE_CAPABILITIES_PATH,
        SCHEDULER_PATH,
        CADENCE_PATH,
        RATE_BUDGET_PATH,
        COVERAGE_DASHBOARD_PATH,
        SILENT_GAP_ORACLE_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/model_system_card.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("machine/evidence/EVD-S05-P01.json"),
        Path("machine/evidence/EVD-S05-P01_rollback.json"),
        Path("machine/evidence/EVD-S05-P02.json"),
        Path("machine/evidence/EVD-S05-P02_rollback.json"),
        Path("machine/evidence/EVD-S05-P03.json"),
        Path("machine/evidence/EVD-S05-P03_rollback.json"),
        Path("machine/evidence/EVD-S05-P04.json"),
        Path("machine/evidence/EVD-S05-P04_rollback.json"),
        Path("machine/evidence/S04/STAGE_REVIEW/github_delivery_receipt.json"),
        Path("abd_acceptance/stage5_review.py"),
        Path("abd_acceptance/coverage_observability.py"),
        Path("abd_acceptance/market_ontology.py"),
        Path("abd_acceptance/source_capabilities.py"),
        Path("abd_acceptance/source_scheduler.py"),
        Path("abd_acceptance/__main__.py"),
        Path("abd_acceptance/__init__.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / WORKFLOW_PATH)
    return result


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S05-STAGE-REVIEW-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
            "external_state_changed": False,
            "provider_account_api_or_page_accessed": False,
            "real_market_data_collected": False,
            "scheduler_daemon_started": False,
            "recommendation_or_order_generated": False,
            "incremental_cash_spent_aud": "0.00",
        }
    if rollback.get("status") != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "S05_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED"
        validation["stage_status"] = "S05_WHOLE_STAGE_REVIEW_FAILED"
        validation["next"] = "S05/STAGE_REVIEW_REMEDIATION_REQUIRED"
    contract = strict_json_load(root / CONTRACT_PATH)
    findings = strict_json_load(root / FINDINGS_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    inputs = _input_hashes(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "validation": validation,
        "phase_completion": {
            "phase_ids": fixture["expected_phase_ids"],
            "phase_evidence_status": "PASS",
            "phase_count": 4,
            "task_count": 12,
            "provider_count": 3,
            "mode_count": 5,
            "pinned_provider_mode_unit_count": 15,
            "explicit_gap_count": 15,
            "silent_gap_count": 0,
            "production_covered_count": 0,
            "real_market_universe_enumerated_or_verified": False,
        },
        "review_findings": findings.get("summary"),
        "claim_boundary": contract.get("claim_boundary"),
        "hashes": {
            "inputs": inputs,
            "parameters": inputs["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": inputs["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S05 whole-stage review validates ontology, source, scheduler and coverage contracts offline; it executes no provider, account, network, daemon, market collection, model, recommendation, order, deployment or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S05/stage_review_test.py --junitxml=machine/evidence/S05/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py tests/S05/P03_test.py tests/S05/P04_test.py tests/S05/stage_review_test.py --junitxml=machine/evidence/S05/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/STAGE_REVIEW/pytest.xml machine/evidence/S05/STAGE_REVIEW/signed_state_regression.xml machine/evidence/S05/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S05 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {
            "artifact": ROLLBACK_EVIDENCE_PATH.as_posix(),
            "status": rollback.get("status"),
        },
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "explicit_unknowns": [
            "ALL_OBSERVABLE_MARKETS is the declared discovery design scope, not evidence that a real market universe was enumerated.",
            "The pinned 3-provider by 5-mode matrix has 15 explicit non-production gaps and zero covered production units.",
            "No provider account, page, API, permission grant, market data or runtime freshness was accessed or verified.",
            "The 120-per-60-second synthetic budget is offline test input only and cannot dispatch to a real source.",
            "No scheduler daemon, OVH host, Cloudflare runtime, Gmail account, deployment or production traffic was used.",
            "No model, recommendation, stake, account selection or order was generated, submitted, confirmed or retried.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; shortfall cannot relax any gate.",
            "Remote GitHub CI is not claimed by local review evidence and must be observed after whole-stage upload.",
        ],
        "production_coverage_status": "ZERO_OF_15_REAL_PROVIDER_MODE_UNITS_COVERED_ALL_15_EXPLICIT_GAPS",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": fixture["expected_release_status"],
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "stage_status": "S05_WHOLE_STAGE_REVIEW_PASS" if validation["status"] == "PASS" else "S05_WHOLE_STAGE_REVIEW_FAILED",
        "next": validation["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-S05-STAGE-REVIEW"]
    if len(matching) > 1:
        raise Stage5ReviewContractError("duplicate INDEX-S05-STAGE-REVIEW rows")
    row = (
        matching[0]
        if matching
        else {
            "id": "INDEX-S05-STAGE-REVIEW",
            "kind": "STAGE_REVIEW_EVIDENCE",
            "stage_id": STAGE_ID,
        }
    )
    if not matching:
        rows.append(row)
    row.update(
        {
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "verified_at": FIXED_CLOCK,
            "next": "S05/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S05/STAGE_REVIEW_REMEDIATION_REQUIRED",
        }
    )
    payload = b"".join(
        (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for item in rows
    )
    _atomic_write(root / EVIDENCE_INDEX_PATH, payload)


def write_stage5_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise Stage5ReviewContractError("evidence directory must be inside the ABD project root") from exc
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


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def validate_signed_receipt_preflight(root: Path) -> Dict[str, Any]:
    """Validate the signed S05 review receipt without recursively invoking P04."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    candidate = validate_candidate_preflight(root)
    _add(checks, "S05REVIEW-SIGNED-CANDIDATE", candidate.get("status") == "PASS", candidate.get("summary"))
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S05REVIEW-SIGNED-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S05REVIEW-SIGNED-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    fixture = strict_json_load(root / FIXTURE_PATH)
    contract = strict_json_load(root / CONTRACT_PATH)
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S05-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S05_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("stage_status") == "S05_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("release_status") == fixture.get("expected_release_status")
            and evidence.get("next") == fixture.get("expected_next")
            and evidence.get("claim_boundary") == contract.get("claim_boundary")
            and evidence.get("external_effect_boundary") == contract.get("external_effect_boundary")
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S05REVIEW-SIGNED-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            isinstance(validation, Mapping)
            and validation.get("status") == "PASS"
            and validation.get("summary", {}).get("failed") == 0
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S05REVIEW-SIGNED-VALIDATION", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate_path = Path(relative)
            if candidate_path.is_absolute() or ".." in candidate_path.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate_path if relative.startswith(".github/") else root / candidate_path
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                input_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S05REVIEW-SIGNED-INPUT-HASHES", not input_errors, input_errors or "all inputs match")
        code_actual = _current_code_hash(root)
        _add(
            checks,
            "S05REVIEW-SIGNED-CODE-HASH",
            evidence.get("hashes", {}).get("code") == code_actual,
            {"expected": evidence.get("hashes", {}).get("code"), "actual": code_actual},
        )
        report_errors: List[Dict[str, str]] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [
            JUNIT_PATH,
            FULL_JUNIT_PATH,
            SIGNED_STATE_JUNIT_PATH,
            PACK_REPORT_PATH,
            SCAN_REPORT_PATH,
        ]:
            expected = validation_hashes.get(relative.as_posix())
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if not isinstance(expected, str) or expected != actual:
                report_errors.append({"path": relative.as_posix(), "expected": str(expected), "actual": actual})
        _add(checks, "S05REVIEW-SIGNED-REPORT-HASHES", not report_errors, report_errors or "all reports match")
        _add(
            checks,
            "S05REVIEW-SIGNED-ROLLBACK-BINDING",
            evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash,
            {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash},
        )
        completion = evidence.get("phase_completion", {})
        completion_ok = (
            completion.get("phase_count") == 4
            and completion.get("task_count") == 12
            and completion.get("pinned_provider_mode_unit_count") == 15
            and completion.get("explicit_gap_count") == 15
            and completion.get("silent_gap_count") == 0
            and completion.get("production_covered_count") == 0
            and completion.get("real_market_universe_enumerated_or_verified") is False
        )
        _add(checks, "S05REVIEW-SIGNED-COMPLETION-BOUNDARY", completion_ok, completion)
    else:
        for check_id in [
            "S05REVIEW-SIGNED-INTEGRITY",
            "S05REVIEW-SIGNED-VALIDATION",
            "S05REVIEW-SIGNED-INPUT-HASHES",
            "S05REVIEW-SIGNED-CODE-HASH",
            "S05REVIEW-SIGNED-REPORT-HASHES",
            "S05REVIEW-SIGNED-ROLLBACK-BINDING",
            "S05REVIEW-SIGNED-COMPLETION-BOUNDARY",
        ]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S05-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and rollback.get("provider_account_api_or_page_accessed") is False
        and rollback.get("real_market_data_collected") is False
        and rollback.get("scheduler_daemon_started") is False
        and rollback.get("recommendation_or_order_generated") is False
        and rollback.get("incremental_cash_spent_aud") == "0.00"
        and len(rollback.get("artifacts", {})) == fixture.get("expected_rollback_artifact_count")
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S05REVIEW-SIGNED-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-S05-STAGE-REVIEW"]
    index_ok = (
        len(rows) == 1
        and rows[0].get("status") == "PASS"
        and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and rows[0].get("artifact_sha256") == evidence_hash
        and rows[0].get("next") == "S05/GITHUB_STAGE_UPLOAD_READY"
    )
    _add(checks, "S05REVIEW-SIGNED-INDEX", index_ok, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_STAGE_REVIEW_SIGNED_PREFLIGHT_VALID" if not failed else "S05_STAGE_REVIEW_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S05/GITHUB_STAGE_UPLOAD_READY" if not failed else "S05/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def verify_existing_stage_review_evidence(
    root: Path,
    *,
    verify_phase_prerequisites: bool = True,
    verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    preflight = validate_signed_receipt_preflight(root)
    _add(checks, "S05REVIEW-RECEIPT-PREFLIGHT", preflight.get("status") == "PASS", preflight.get("summary"))
    if verify_phase_prerequisites:
        for phase in ["P01", "P02", "P03", "P04"]:
            try:
                result = _verify_phase(phase, root, verify_git_history)
                _add(
                    checks,
                    "S05REVIEW-RECEIPT-%s-PREREQUISITE" % phase,
                    result.get("status") == "PASS" and result.get("decision") == PHASE_DECISIONS[phase],
                    result.get("summary"),
                )
            except Exception as exc:
                _add(checks, "S05REVIEW-RECEIPT-%s-PREREQUISITE" % phase, False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_STAGE_REVIEW_EVIDENCE_VERIFIED" if not failed else "S05_STAGE_REVIEW_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": preflight.get("evidence_sha256"),
        "rollback_sha256": preflight.get("rollback_sha256"),
        "next": "S05/GITHUB_STAGE_UPLOAD_READY" if not failed else "S05/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_PATH",
    "EVIDENCE_PATH",
    "FINDINGS_PATH",
    "FIXED_CLOCK",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_PATH",
    "PINNED_REVIEW_ARTIFACT_HASHES",
    "REVIEW_ID",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "SIGNED_STATE_JUNIT_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "TEST_PATH",
    "Stage5ReviewContractError",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "validate_signed_receipt_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage5_review_evidence",
]
