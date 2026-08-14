"""Fail-closed, local-only acceptance oracle for ABD S14/P02.

S14/P02 freezes a security pipeline contract and verifies its declared static
analysis, dependency-lock, secret-reference, container, and infrastructure
controls without contacting a vulnerability feed, CI provider, mailbox,
account, host, Cloudflare, OVH, or order endpoint.  A PASS is local control
evidence only; it is not a production security, deployment, or return claim.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S14-P02"
REQUIREMENT_ID = "REQ-S14-P02"
STAGE_ID = "S14"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

PIPELINE_PATH = Path("security_pipeline.yml")
SAST_POLICY_PATH = Path("sast_policy.json")
SECRET_POLICY_PATH = Path("secret_policy.json")
ORACLE_PATH = Path("abd_acceptance/security_analysis.py")
TEST_PATH = Path("tests/S14/P02_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S14_P02.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S14/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S14/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")

P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S14-P01_rollback.json")
P01_EVIDENCE_SHA256 = "91d353c7e3f850119cbc755936c4023537c6870ec3f1a384346bc1875aa90a8c"
P01_ROLLBACK_SHA256 = "feba53995af01741678c252fb0f2a2d58af4a3a37f5b558f70a94549354463c0"

BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
    "incremental_cash_spent_aud": "0.00",
}

CONTROL_PLANE_TARGETS = (
    "abd_acceptance/threat_model.py",
    "abd_acceptance/security_analysis.py",
    "security_pipeline.yml",
    "sast_policy.json",
    "secret_policy.json",
    "infra/compose.yml",
    "infra/config.schema.json",
    "infra/cloudflared.yml",
    "infra/rebuild.sh",
    "infra/systemd/abd.service",
    "infra/systemd/abd-cloudflared.service",
    "pyproject.toml",
    "uv.lock",
)
SAST_TARGETS = (
    "abd_acceptance/threat_model.py",
    "abd_acceptance/security_analysis.py",
    "security_pipeline.yml",
    "sast_policy.json",
    "secret_policy.json",
)
SECRET_TARGETS = CONTROL_PLANE_TARGETS
CONTAINER_INFRASTRUCTURE_TARGETS = (
    "infra/compose.yml",
    "infra/config.schema.json",
    "infra/cloudflared.yml",
    "infra/rebuild.sh",
    "infra/systemd/abd.service",
    "infra/systemd/abd-cloudflared.service",
)
PIPELINE_STAGE_IDS = (
    "CONFIG_TYPE_CHECK",
    "STATIC_APPLICATION_ANALYSIS",
    "DEPENDENCY_LOCK_ANALYSIS",
    "SECRET_REFERENCE_ANALYSIS",
    "CONTAINER_INFRASTRUCTURE_ANALYSIS",
)
SAST_RULE_IDS = (
    "SAST-IMPORT-CAPABILITY",
    "SAST-CALL-CAPABILITY",
    "SAST-ORDER-CAPABILITY",
    "SAST-FLOAT-NUMERIC-SAFETY",
    "SAST-PIPELINE-LOCAL-ONLY",
)
SECRET_RULE_IDS = (
    "SECRET-AWS-ACCESS-KEY",
    "SECRET-PRIVATE-KEY",
    "SECRET-GITHUB-PERSONAL-TOKEN",
    "SECRET-GENERIC-INLINE-ASSIGNMENT",
)
PIPELINE_FIELDS = {
    "schema_version",
    "pipeline_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "serialization",
    "execution_mode",
    "scope_boundary",
    "stages",
    "required_commands",
    "policy_paths",
    "findings_gate",
    "external_effect_boundary",
    "not_production_evidence",
}
SAST_FIELDS = {
    "schema_version",
    "policy_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "source_targets",
    "analysis_rules",
    "finding_gate",
    "waiver_policy",
    "external_effect_boundary",
    "not_production_evidence",
}
SECRET_FIELDS = {
    "schema_version",
    "policy_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "scan_targets",
    "detection_rules",
    "allowed_reference_tokens",
    "prohibited_repository_extensions",
    "finding_gate",
    "external_effect_boundary",
    "not_production_evidence",
}
FIXTURE_FIELDS = {
    "schema_version",
    "fixture_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "minimum_targeted_pytest_cases",
    "expected_pipeline_stage_ids",
    "expected_sast_rule_ids",
    "expected_secret_rule_ids",
    "expected_decision",
    "expected_next",
    "single_pass_case_count",
    "snapshot_cases",
}

PIPELINE_SCOPE_BOUNDARY = {
    "included_control_plane_targets": list(CONTROL_PLANE_TARGETS),
    "excluded_as_not_claimed": [
        "LIVE_CVE_DATABASE",
        "PRODUCTION_RUNTIME",
        "EXTERNAL_CI_EXECUTION",
        "REAL_ACCOUNT_OR_ORDER_ACTION",
    ],
    "production_security_verified": False,
}
PIPELINE_STAGES = [
    {
        "id": "CONFIG_TYPE_CHECK",
        "kind": "CONFIG_TYPE",
        "scope": ["security_pipeline.yml", "sast_policy.json", "secret_policy.json", "infra/config.schema.json"],
        "failure_action": "FAIL_CLOSED_NO_RELEASE",
        "network_accessed": False,
        "external_execution": False,
    },
    {
        "id": "STATIC_APPLICATION_ANALYSIS",
        "kind": "SAST",
        "scope": ["abd_acceptance/threat_model.py", "abd_acceptance/security_analysis.py"],
        "failure_action": "FAIL_CLOSED_NO_RELEASE",
        "network_accessed": False,
        "external_execution": False,
    },
    {
        "id": "DEPENDENCY_LOCK_ANALYSIS",
        "kind": "DEPENDENCY",
        "scope": ["pyproject.toml", "uv.lock"],
        "failure_action": "FAIL_CLOSED_NO_RELEASE",
        "network_accessed": False,
        "external_execution": False,
    },
    {
        "id": "SECRET_REFERENCE_ANALYSIS",
        "kind": "SECRET",
        "scope": [
            "abd_acceptance/threat_model.py",
            "abd_acceptance/security_analysis.py",
            "infra/compose.yml",
            "infra/config.schema.json",
            "infra/cloudflared.yml",
            "infra/rebuild.sh",
            "infra/systemd/abd.service",
            "infra/systemd/abd-cloudflared.service",
        ],
        "failure_action": "FAIL_CLOSED_NO_RELEASE",
        "network_accessed": False,
        "external_execution": False,
    },
    {
        "id": "CONTAINER_INFRASTRUCTURE_ANALYSIS",
        "kind": "CONTAINER_INFRASTRUCTURE",
        "scope": list(CONTAINER_INFRASTRUCTURE_TARGETS),
        "failure_action": "FAIL_CLOSED_NO_RELEASE",
        "network_accessed": False,
        "external_execution": False,
    },
]
REQUIRED_COMMANDS = [
    "uv run --frozen --python 3.12 python -m pytest -q tests/S14/P02_test.py --junitxml=machine/evidence/S14/P02/pytest.xml",
    "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S14/P02/pytest.xml",
    "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S14/P02/paid_dependency_scan.txt",
    "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
    "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S14-P02 --evidence machine/evidence",
    "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
]
SAST_RULES = [
    {"id": "SAST-IMPORT-CAPABILITY", "severity": "HIGH", "mode": "AST_IMPORT_DENYLIST"},
    {"id": "SAST-CALL-CAPABILITY", "severity": "HIGH", "mode": "AST_CALL_DENYLIST"},
    {"id": "SAST-ORDER-CAPABILITY", "severity": "CRITICAL", "mode": "AST_ORDER_ACTION_DENYLIST"},
    {"id": "SAST-FLOAT-NUMERIC-SAFETY", "severity": "HIGH", "mode": "AST_FLOAT_LITERAL_DENYLIST"},
    {"id": "SAST-PIPELINE-LOCAL-ONLY", "severity": "HIGH", "mode": "DECLARATIVE_COMMAND_DENYLIST"},
]
SECRET_RULES = [
    {"id": "SECRET-AWS-ACCESS-KEY", "severity": "CRITICAL", "mode": "LITERAL_VALUE_PATTERN"},
    {"id": "SECRET-PRIVATE-KEY", "severity": "CRITICAL", "mode": "LITERAL_VALUE_PATTERN"},
    {"id": "SECRET-GITHUB-PERSONAL-TOKEN", "severity": "HIGH", "mode": "LITERAL_VALUE_PATTERN"},
    {"id": "SECRET-GENERIC-INLINE-ASSIGNMENT", "severity": "HIGH", "mode": "LITERAL_VALUE_PATTERN"},
]
FINDINGS_GATE = {
    "unresolved_critical": 0,
    "unresolved_high": 0,
    "automatic_waiver_allowed": False,
}
PIPELINE_FINDINGS_GATE = {**FINDINGS_GATE, "release_on_failure": "BLOCK_LOCAL_RELEASE"}
WAIVER_POLICY = {
    "high_or_critical_waiver_allowed": False,
    "waiver_count": 0,
    "waiver_evidence_required": True,
}
ALLOWED_REFERENCE_TOKENS = ["ABD_RUNTIME_SECRET_FILE", "ABD_CONFIG_FILE", "credentials-file"]
PROHIBITED_REPOSITORY_EXTENSIONS = [".env", ".pem", ".key", ".p12"]

PROHIBITED_IMPORTS = {"socket", "subprocess", "requests", "urllib", "smtplib", "ftplib", "asyncio", "os"}
PROHIBITED_CALLS = {"sleep", "Popen", "run", "system", "popen"}
ORDER_CALLS = {"submit_order", "retry_order", "confirm_order", "cancel_order"}
PROHIBITED_COMMAND_FRAGMENTS = ("git push", "docker ", "systemctl", "curl ", "wget ", "gh ", "full_regression")
SECRET_PATTERNS = {
    "SECRET-AWS-ACCESS-KEY": ("CRITICAL", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    "SECRET-PRIVATE-KEY": ("CRITICAL", re.compile(r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----")),
    "SECRET-GITHUB-PERSONAL-TOKEN": ("HIGH", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    "SECRET-GENERIC-INLINE-ASSIGNMENT": (
        "HIGH",
        re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"),
    ),
}


class SecurityAnalysisError(ValueError):
    """Raised when S14/P02 cannot remain deterministic and fail closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _portable(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_portable(item) for item in value)
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return not normalized.startswith("/") and "/Users/" not in normalized and "file://" not in normalized
    return True


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise SecurityAnalysisError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise SecurityAnalysisError("evidence-index row %d is not an object" % number)
        rows.append(row)
    if not rows:
        raise SecurityAnalysisError("evidence index is empty")
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise SecurityAnalysisError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise SecurityAnalysisError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _coverage_decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"[01]\.\d{4}", value) is None:
        raise SecurityAnalysisError("coverage_score must be four-place decimal text")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise SecurityAnalysisError("coverage_score is not decimal") from exc


def _require_header(value: Mapping[str, Any], identifier: str) -> None:
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("execution_mode") != "FROZEN_LOCAL_DETERMINISTIC_NO_NETWORK"
    ):
        raise SecurityAnalysisError("%s header is not frozen" % identifier)


def validate_security_pipeline(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != PIPELINE_FIELDS or _contains_float(value):
        raise SecurityAnalysisError("security pipeline fields are not closed")
    _require_header(value, "security pipeline")
    if (
        value.get("pipeline_id") != "S14-P02-SECURITY-PIPELINE"
        or value.get("serialization") != "JSON_COMPATIBLE_YAML"
        or value.get("scope_boundary") != PIPELINE_SCOPE_BOUNDARY
        or value.get("stages") != PIPELINE_STAGES
        or value.get("required_commands") != REQUIRED_COMMANDS
        or value.get("policy_paths") != [SAST_POLICY_PATH.as_posix(), SECRET_POLICY_PATH.as_posix()]
        or value.get("findings_gate") != PIPELINE_FINDINGS_GATE
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("not_production_evidence") is not True
    ):
        raise SecurityAnalysisError("security pipeline contract is not exact")
    return dict(value)


def validate_sast_policy(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != SAST_FIELDS or _contains_float(value):
        raise SecurityAnalysisError("SAST policy fields are not closed")
    _require_header(value, "SAST policy")
    if (
        value.get("policy_id") != "S14-P02-SAST-POLICY"
        or value.get("source_targets") != list(SAST_TARGETS)
        or value.get("analysis_rules") != SAST_RULES
        or value.get("finding_gate") != FINDINGS_GATE
        or value.get("waiver_policy") != WAIVER_POLICY
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("not_production_evidence") is not True
    ):
        raise SecurityAnalysisError("SAST policy is not exact")
    return dict(value)


def validate_secret_policy(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != SECRET_FIELDS or _contains_float(value):
        raise SecurityAnalysisError("secret policy fields are not closed")
    _require_header(value, "secret policy")
    if (
        value.get("policy_id") != "S14-P02-SECRET-POLICY"
        or value.get("scan_targets") != list(SECRET_TARGETS)
        or value.get("detection_rules") != SECRET_RULES
        or value.get("allowed_reference_tokens") != ALLOWED_REFERENCE_TOKENS
        or value.get("prohibited_repository_extensions") != PROHIBITED_REPOSITORY_EXTENSIONS
        or value.get("finding_gate") != FINDINGS_GATE
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("not_production_evidence") is not True
    ):
        raise SecurityAnalysisError("secret policy is not exact")
    return dict(value)


def validate_security_fixture(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != FIXTURE_FIELDS or _contains_float(value):
        raise SecurityAnalysisError("security fixture fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("fixture_id") != "FIX-S14-P02-SECURITY-ANALYSIS"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("minimum_targeted_pytest_cases") != 24
        or value.get("expected_pipeline_stage_ids") != list(PIPELINE_STAGE_IDS)
        or value.get("expected_sast_rule_ids") != list(SAST_RULE_IDS)
        or value.get("expected_secret_rule_ids") != list(SECRET_RULE_IDS)
        or value.get("expected_decision") != "SECURITY_PIPELINE_READY_UNRESOLVED_CRITICAL_OR_HIGH_FINDINGS_ZERO_LOCAL_ONLY"
        or value.get("expected_next") != "S14/P03_READY_NOT_STARTED"
        or value.get("single_pass_case_count") != 12
    ):
        raise SecurityAnalysisError("security fixture header is not frozen")
    rows = value.get("snapshot_cases")
    if not isinstance(rows, list) or len(rows) != 12 or len({row.get("case_id") for row in rows if isinstance(row, Mapping)}) != 12:
        raise SecurityAnalysisError("security fixture snapshots are not exact")
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"case_id", "snapshot", "expected"}:
            raise SecurityAnalysisError("security fixture snapshot shape is invalid")
        if not isinstance(row.get("case_id"), str) or not row["case_id"]:
            raise SecurityAnalysisError("security fixture case id is invalid")
        evaluate_security_snapshot(row["snapshot"])
        expected = row.get("expected")
        if not isinstance(expected, Mapping) or set(expected) != {"status", "reason_codes"}:
            raise SecurityAnalysisError("security fixture expected result is invalid")
    return dict(value)


def evaluate_security_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one frozen P02 security snapshot without enabling actions."""

    required = {
        "p01_receipt_current",
        "pipeline_configuration_closed",
        "static_analysis_passed",
        "dependency_lock_analysis_passed",
        "secret_analysis_passed",
        "container_infrastructure_analysis_passed",
        "external_effect_boundary_preserved",
        "unresolved_critical_count",
        "unresolved_high_count",
        "coverage_score",
        "foreign_odds_input_present",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != required:
        raise SecurityAnalysisError("security snapshot shape is invalid")
    for field in required - {"unresolved_critical_count", "unresolved_high_count", "coverage_score"}:
        if type(snapshot.get(field)) is not bool:
            raise SecurityAnalysisError("%s must be boolean" % field)
    for field in ("unresolved_critical_count", "unresolved_high_count"):
        if type(snapshot.get(field)) is not int or snapshot[field] < 0:
            raise SecurityAnalysisError("%s must be a nonnegative integer" % field)
    coverage = _coverage_decimal(snapshot.get("coverage_score"))
    reason_map = (
        ("p01_receipt_current", "P01_RECEIPT_NOT_CURRENT"),
        ("pipeline_configuration_closed", "PIPELINE_CONFIGURATION_NOT_CLOSED"),
        ("static_analysis_passed", "STATIC_ANALYSIS_FAILED"),
        ("dependency_lock_analysis_passed", "DEPENDENCY_LOCK_ANALYSIS_FAILED"),
        ("secret_analysis_passed", "SECRET_ANALYSIS_FAILED"),
        ("container_infrastructure_analysis_passed", "CONTAINER_INFRASTRUCTURE_ANALYSIS_FAILED"),
        ("external_effect_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["unresolved_critical_count"] != 0:
        reasons.append("UNRESOLVED_CRITICAL_FINDINGS")
    if snapshot["unresolved_high_count"] != 0:
        reasons.append("UNRESOLVED_HIGH_FINDINGS")
    if coverage != Decimal("1.0000"):
        reasons.append("CONTROL_COVERAGE_NOT_EXACT")
    if snapshot["foreign_odds_input_present"] is True:
        reasons.append("FOREIGN_ODDS_INPUT_REJECTED")
    result: Dict[str, Any] = {
        "status": "S14P02_SECURITY_ANALYSIS_VERIFIED_NO_ACTION" if not reasons else "S14P02_SECURITY_ANALYSIS_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def _finding(rule_id: str, severity: str, location: str, detail: str) -> Dict[str, str]:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "status": "UNRESOLVED",
        "location": location,
        "detail": detail,
    }


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def scan_source_text(relative: str, text: str) -> List[Dict[str, str]]:
    """Return high/critical AST findings for one Python source text."""

    if not relative.endswith(".py"):
        return []
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return [_finding("SAST-PYTHON-SYNTAX", "HIGH", relative, "%s" % exc)]
    imports: set[str] = set()
    calls: set[str] = set()
    order_calls: set[str] = set()
    float_lines: List[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in PROHIBITED_CALLS:
                calls.add(name)
            if name in ORDER_CALLS:
                order_calls.add(name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            float_lines.append(getattr(node, "lineno", 0))
    findings: List[Dict[str, str]] = []
    if imports & PROHIBITED_IMPORTS:
        findings.append(_finding("SAST-IMPORT-CAPABILITY", "HIGH", relative, "denied imports: %s" % sorted(imports & PROHIBITED_IMPORTS)))
    if calls:
        findings.append(_finding("SAST-CALL-CAPABILITY", "HIGH", relative, "denied calls: %s" % sorted(calls)))
    if order_calls:
        findings.append(_finding("SAST-ORDER-CAPABILITY", "CRITICAL", relative, "denied order calls: %s" % sorted(order_calls)))
    if float_lines:
        findings.append(_finding("SAST-FLOAT-NUMERIC-SAFETY", "HIGH", relative, "float literals at lines: %s" % float_lines))
    return findings


def scan_secret_text(relative: str, text: str) -> List[Dict[str, str]]:
    """Return literal secret findings without reading or decoding any secret store."""

    findings: List[Dict[str, str]] = []
    for rule_id, (severity, pattern) in SECRET_PATTERNS.items():
        if pattern.search(text):
            findings.append(_finding(rule_id, severity, relative, "literal secret pattern matched"))
    return findings


def _check_dependency_lock(root: Path) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject.get("project")
        groups = pyproject.get("dependency-groups")
        expected_dev = ["jsonschema==4.25.1", "pytest==8.4.2"]
        valid_project = (
            isinstance(project, Mapping)
            and project.get("name") == "abd"
            and project.get("version") == VERSION
            and project.get("requires-python") == ">=3.12,<3.13"
            and project.get("dependencies") == []
            and isinstance(groups, Mapping)
            and groups.get("dev") == expected_dev
        )
        lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
        packages = lock.get("package")
        expected_names = {
            "abd",
            "attrs",
            "colorama",
            "iniconfig",
            "jsonschema",
            "jsonschema-specifications",
            "packaging",
            "pluggy",
            "pygments",
            "pytest",
            "referencing",
            "rpds-py",
            "typing-extensions",
        }
        package_names = {item.get("name") for item in packages if isinstance(item, Mapping)} if isinstance(packages, list) else set()
        lock_valid = (
            lock.get("version") == 1
            and lock.get("revision") == 3
            and lock.get("requires-python") == "==3.12.*"
            and package_names == expected_names
            and len(packages) == len(expected_names) if isinstance(packages, list) else False
        )
        if not valid_project or not lock_valid:
            findings.append(_finding("DEPENDENCY-LOCK-INTEGRITY", "HIGH", "pyproject.toml|uv.lock", "pinned dependency contract is not exact"))
    except Exception as exc:
        findings.append(_finding("DEPENDENCY-LOCK-PARSE", "HIGH", "pyproject.toml|uv.lock", "%s: %s" % (type(exc).__name__, exc)))
    return findings


def _check_container_infrastructure(root: Path) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    try:
        compose = strict_json_load(root / "infra/compose.yml")
        services = compose.get("services") if isinstance(compose, Mapping) else None
        for service_id in ("abd-core", "abd-shadow"):
            service = services.get(service_id) if isinstance(services, Mapping) else None
            valid = (
                isinstance(service, Mapping)
                and service.get("read_only") is True
                and service.get("cap_drop") == ["ALL"]
                and service.get("security_opt") == ["no-new-privileges:true"]
                and service.get("environment", {}).get("ABD_ORDER_SUBMISSION_ENABLED") == "false"
                and service.get("networks") == ["abd_internal"]
                and service.get("privileged") is not True
                and "network_mode" not in service
                and isinstance(service.get("image"), str)
                and "ABD_IMAGE" in service["image"]
                and service.get("pull_policy") == "never"
                and all(isinstance(port, Mapping) and port.get("host_ip") == "127.0.0.1" for port in service.get("ports", []))
            )
            if not valid:
                findings.append(_finding("CONTAINER-HARDENING", "HIGH", "infra/compose.yml:%s" % service_id, "container hardening contract is not exact"))
        schema = strict_json_load(root / "infra/config.schema.json")
        properties = schema.get("properties") if isinstance(schema, Mapping) else None
        secrets = properties.get("secrets", {}).get("properties", {}) if isinstance(properties, Mapping) else {}
        runtime = properties.get("runtime", {}).get("properties", {}) if isinstance(properties, Mapping) else {}
        budget = properties.get("budget", {}).get("properties", {}) if isinstance(properties, Mapping) else {}
        schema_valid = (
            isinstance(schema, Mapping)
            and schema.get("additionalProperties") is False
            and secrets.get("inline_secret_values_present", {}).get("const") is False
            and secrets.get("repository_secret_files", {}).get("maxItems") == 0
            and runtime.get("order_submission_enabled", {}).get("const") is False
            and runtime.get("no_new_privileges", {}).get("const") is True
            and budget.get("incremental_cash_aud", {}).get("const") == "0.00"
            and budget.get("paid_upgrade_allowed", {}).get("const") is False
        )
        if not schema_valid:
            findings.append(_finding("INFRA-CONFIG-SECURITY", "HIGH", "infra/config.schema.json", "schema security constraints are not exact"))
        cloudflared = strict_json_load(root / "infra/cloudflared.yml")
        ingress = cloudflared.get("ingress") if isinstance(cloudflared, Mapping) else None
        tunnel_valid = (
            isinstance(cloudflared, Mapping)
            and cloudflared.get("no-autoupdate") is True
            and isinstance(cloudflared.get("metrics"), str)
            and cloudflared["metrics"].startswith("127.0.0.1:")
            and isinstance(ingress, list)
            and len(ingress) == 2
            and isinstance(ingress[0], Mapping)
            and ingress[0].get("service") == "http://127.0.0.1:8080"
            and isinstance(ingress[1], Mapping)
            and ingress[1].get("service") == "http_status:404"
        )
        if not tunnel_valid:
            findings.append(_finding("INFRA-TUNNEL-LOOPBACK", "HIGH", "infra/cloudflared.yml", "tunnel contract is not local-only"))
        service_text = (root / "infra/systemd/abd.service").read_text(encoding="utf-8")
        cloudflared_service_text = (root / "infra/systemd/abd-cloudflared.service").read_text(encoding="utf-8")
        rebuild_text = (root / "infra/rebuild.sh").read_text(encoding="utf-8")
        main_required = ("EnvironmentFile=/etc/abd/runtime.env", "UMask=0077", "NoNewPrivileges=true", "config --quiet")
        connector_required = ("NoNewPrivileges=true", "PrivateDevices=true", "PrivateTmp=true", "ProtectHome=true", "ProtectSystem=strict", "MemoryDenyWriteExecute=true")
        if not all(token in service_text for token in main_required):
            findings.append(_finding("INFRA-SYSTEMD-MAIN", "HIGH", "infra/systemd/abd.service", "main unit hardening contract is incomplete"))
        if not all(token in cloudflared_service_text for token in connector_required):
            findings.append(_finding("INFRA-SYSTEMD-CONNECTOR", "HIGH", "infra/systemd/abd-cloudflared.service", "connector unit hardening contract is incomplete"))
        if "set -eu" not in rebuild_text or "exec python3 -m abd_acceptance.infrastructure_iac" not in rebuild_text:
            findings.append(_finding("INFRA-REBUILD-ENTRYPOINT", "HIGH", "infra/rebuild.sh", "rebuild entrypoint is not deterministic"))
    except Exception as exc:
        findings.append(_finding("CONTAINER-INFRA-PARSE", "HIGH", "infra", "%s: %s" % (type(exc).__name__, exc)))
    return findings


def _repository_extension_findings(root: Path) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        if path.name == ".env" or path.suffix in set(PROHIBITED_REPOSITORY_EXTENSIONS[1:]):
            findings.append(_finding("SECRET-PROHIBITED-REPOSITORY-FILE", "CRITICAL", path.relative_to(root).as_posix(), "prohibited secret-bearing file extension"))
    return findings


def run_security_analysis(root: Path, pipeline: Mapping[str, Any], sast_policy: Mapping[str, Any], secret_policy: Mapping[str, Any]) -> Dict[str, Any]:
    """Execute the declared local static analyses without external effects."""

    root = root.resolve()
    findings: List[Dict[str, str]] = []
    sast_findings: List[Dict[str, str]] = []
    secret_findings: List[Dict[str, str]] = []
    for relative in ("abd_acceptance/threat_model.py", "abd_acceptance/security_analysis.py"):
        try:
            sast_findings.extend(scan_source_text(relative, (root / relative).read_text(encoding="utf-8")))
        except Exception as exc:
            sast_findings.append(_finding("SAST-SOURCE-READ", "HIGH", relative, "%s: %s" % (type(exc).__name__, exc)))
    for command in pipeline["required_commands"]:
        if not isinstance(command, str) or any(fragment in command.lower() for fragment in PROHIBITED_COMMAND_FRAGMENTS):
            sast_findings.append(_finding("SAST-PIPELINE-LOCAL-ONLY", "HIGH", PIPELINE_PATH.as_posix(), "unsafe or non-phase-only command"))
    dependency_findings = _check_dependency_lock(root)
    for relative in secret_policy["scan_targets"]:
        try:
            secret_findings.extend(scan_secret_text(relative, (root / relative).read_text(encoding="utf-8")))
        except Exception as exc:
            secret_findings.append(_finding("SECRET-SOURCE-READ", "HIGH", relative, "%s: %s" % (type(exc).__name__, exc)))
    secret_findings.extend(_repository_extension_findings(root))
    infrastructure_findings = _check_container_infrastructure(root)
    findings.extend(sast_findings)
    findings.extend(dependency_findings)
    findings.extend(secret_findings)
    findings.extend(infrastructure_findings)
    unresolved_critical = sum(1 for finding in findings if finding["severity"] == "CRITICAL")
    unresolved_high = sum(1 for finding in findings if finding["severity"] == "HIGH")
    result = {
        "status": "PASS" if not findings else "FAIL",
        "scanned_target_count": len(secret_policy["scan_targets"]),
        "sast_passed": not sast_findings,
        "dependency_lock_passed": not dependency_findings,
        "secret_passed": not secret_findings,
        "container_infrastructure_passed": not infrastructure_findings,
        "unresolved_critical_count": unresolved_critical,
        "unresolved_high_count": unresolved_high,
        "findings": findings,
        "live_vulnerability_database_queried": False,
        "external_network_used": False,
        "external_account_or_runtime_used": False,
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    passed = True
    for relative, expected in BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            valid = actual == expected
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            valid = False
        _add(checks, "S14P02-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), valid, {"expected": expected, "actual": actual})
        passed = passed and valid
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S14P02-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S14P02-CONTRACTS-PARSE")
    graph_document = _safe_load(root, TASK_GRAPH_PATH, checks, "S14P02-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S14P02-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S14P02-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        index = []
        _add(checks, "S14P02-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
    tasks = graph_document.get("tasks") if isinstance(graph_document, Mapping) else None
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        task_rows = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        task_map = {row.get("id"): row for row in task_rows}
        index_row = _row(index, "INDEX-" + CONTRACT_ID)
        non_goals = [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
        test_ids = ["TEST-S14-P02", "TEST-S14-P02-BOUNDARY", "TEST-S14-P02-REPLAY"]
        task_ids = ["T-S14-P02-01", "T-S14-P02-02", "T-S14-P02-03"]
        planned_index = {
            "acceptance_contract_id": CONTRACT_ID,
            "expected_artifact": EVIDENCE_PATH.as_posix(),
            "id": "INDEX-" + CONTRACT_ID,
            "kind": "ACCEPTANCE_EVIDENCE",
            "pass_gate": "未处置严重/高危为0。",
            "requirement_id": REQUIREMENT_ID,
            "status": "PLANNED",
        }
        signed_index = (
            set(index_row) == {"id", "kind", "stage_id", "contract_id", "requirement_id", "status", "actual_artifact", "artifact_sha256", "next", "verified_at"}
            and index_row.get("id") == "INDEX-" + CONTRACT_ID
            and index_row.get("kind") == "PHASE_EVIDENCE"
            and index_row.get("stage_id") == STAGE_ID
            and index_row.get("contract_id") == CONTRACT_ID
            and index_row.get("requirement_id") == REQUIREMENT_ID
            and index_row.get("status") == "PASS"
            and index_row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and index_row.get("next") == "S14/P03_READY_NOT_STARTED"
            and index_row.get("verified_at") == FIXED_CLOCK
            and isinstance(index_row.get("artifact_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", index_row["artifact_sha256"]) is not None
        )
        exact = (
            requirement.get("stage_id") == STAGE_ID
            and requirement.get("phase_id") == PHASE_ID
            and requirement.get("scope") == [PIPELINE_PATH.as_posix(), SAST_POLICY_PATH.as_posix(), SECRET_POLICY_PATH.as_posix()]
            and requirement.get("target") == "未处置严重/高危为0。"
            and requirement.get("non_goals") == non_goals
            and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("pass_gate") == requirement.get("target")
            and contract.get("threshold") == requirement.get("target")
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % CONTRACT_ID
            and [item.get("id") for item in contract.get("tests", [])] == test_ids
            and [row.get("id") for row in task_rows] == task_ids
            and task_map[task_ids[0]].get("outputs") == [PIPELINE_PATH.as_posix(), SAST_POLICY_PATH.as_posix(), SECRET_POLICY_PATH.as_posix()]
            and task_map[task_ids[0]].get("depends_on") == ["T-S14-P01-03"]
            and task_map[task_ids[1]].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and task_map[task_ids[1]].get("depends_on") == [task_ids[0]]
            and task_map[task_ids[2]].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and task_map[task_ids[2]].get("depends_on") == [task_ids[1]]
            and all(row.get("requirement_ids") == [REQUIREMENT_ID] and row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in task_rows)
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == task_ids
            and trace.get("test_ids") == test_ids
            and trace.get("evidence_id") == "EVD-S14-P02"
            and trace.get("artifact_ids") == ["ART-S14-P02-01", "ART-S14-P02-02", "ART-S14-P02-03"]
            and (index_row == planned_index or signed_index)
        )
        detail: Any = {"task_ids": task_ids, "index_status": index_row.get("status")}
    except Exception as exc:
        exact = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P02-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", exact, detail)
    return exact


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    try:
        receipt = strict_json_load(root / P01_EVIDENCE_PATH)
        rollback = strict_json_load(root / P01_ROLLBACK_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-AC-S14-P01")
        receipt_ok = (
            isinstance(receipt, Mapping)
            and receipt.get("evidence_id") == "EVD-S14-P01"
            and receipt.get("contract_id") == "AC-S14-P01"
            and receipt.get("requirement_id") == "REQ-S14-P01"
            and receipt.get("status") == "PASS"
            and receipt.get("next") == "S14/P02_READY_NOT_STARTED"
            and receipt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and receipt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and sha256_file(root / P01_EVIDENCE_PATH) == P01_EVIDENCE_SHA256
        )
        rollback_ok = (
            isinstance(rollback, Mapping)
            and rollback.get("evidence_id") == "EVD-S14-P01-ROLLBACK"
            and rollback.get("contract_id") == "AC-S14-P01"
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and sha256_file(root / P01_ROLLBACK_PATH) == P01_ROLLBACK_SHA256
        )
        index_ok = (
            index.get("kind") == "PHASE_EVIDENCE"
            and index.get("contract_id") == "AC-S14-P01"
            and index.get("status") == "PASS"
            and index.get("actual_artifact") == P01_EVIDENCE_PATH.as_posix()
            and index.get("artifact_sha256") == P01_EVIDENCE_SHA256
            and index.get("next") == "S14/P02_READY_NOT_STARTED"
        )
        passed = receipt_ok and rollback_ok and index_ok
        detail: Any = {"receipt": receipt_ok, "rollback": rollback_ok, "index": index_ok}
        hashes[P01_EVIDENCE_PATH.as_posix()] = sha256_file(root / P01_EVIDENCE_PATH)
        hashes[P01_ROLLBACK_PATH.as_posix()] = sha256_file(root / P01_ROLLBACK_PATH)
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P02-P01-SIGNED-DEPENDENCY-EXACT", passed, detail)
    return passed


def _check_artifacts(pipeline: Any, sast_policy: Any, secret_policy: Any, fixture: Any, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    try:
        pipeline_value = validate_security_pipeline(pipeline)
        _add(checks, "S14P02-SECURITY-PIPELINE-EXACT", True, list(PIPELINE_STAGE_IDS))
    except Exception as exc:
        pipeline_value = None
        _add(checks, "S14P02-SECURITY-PIPELINE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        sast_value = validate_sast_policy(sast_policy)
        _add(checks, "S14P02-SAST-POLICY-EXACT", True, list(SAST_RULE_IDS))
    except Exception as exc:
        sast_value = None
        _add(checks, "S14P02-SAST-POLICY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        secret_value = validate_secret_policy(secret_policy)
        _add(checks, "S14P02-SECRET-POLICY-EXACT", True, list(SECRET_RULE_IDS))
    except Exception as exc:
        secret_value = None
        _add(checks, "S14P02-SECRET-POLICY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        fixture_value = validate_security_fixture(fixture)
        _add(checks, "S14P02-FIXTURE-EXACT", True, fixture_value["single_pass_case_count"])
    except Exception as exc:
        fixture_value = None
        _add(checks, "S14P02-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return {"pipeline": pipeline_value, "sast": sast_value, "secret": secret_value, "fixture": fixture_value}


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    rows = fixture.get("snapshot_cases") if isinstance(fixture, Mapping) else None
    if not isinstance(rows, list):
        _add(checks, "S14P02-SNAPSHOT-CASES", False, "cases unavailable")
        return False
    passed = True
    for row in rows:
        try:
            actual = evaluate_security_snapshot(row["snapshot"])
            expected = row["expected"]
            current = actual["status"] == expected["status"] and actual["reason_codes"] == expected["reason_codes"]
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            current = False
        case_id = row.get("case_id") if isinstance(row, Mapping) else "MALFORMED"
        _add(checks, "S14P02-CASE-%s" % case_id, current, actual)
        passed = passed and current
    return passed


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    try:
        document = ElementTree.parse(root / JUNIT_PATH).getroot()
        suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
        summary = {field: sum(int(suite.attrib.get(field, "0")) for suite in suites) for field in ("tests", "failures", "errors", "skipped")}
        junit_ok = (
            bool(suites)
            and summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and summary["failures"] == 0
            and summary["errors"] == 0
            and summary["skipped"] == 0
            and all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK for suite in suites)
        )
    except Exception as exc:
        summary = "%s: %s" % (type(exc).__name__, exc)
        junit_ok = False
    _add(checks, "S14P02-TARGETED-PYTEST-REPORT", junit_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(
            line in scan
            for line in (
                "STATUS: PASS",
                "MAX_INCREMENTAL_CASH_AUD: 0.00",
                "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
                "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
                "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
            )
        )
    except Exception as exc:
        scan = "%s: %s" % (type(exc).__name__, exc)
        scan_ok = False
    _add(checks, "S14P02-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary_value = report.get("summary") if isinstance(report, Mapping) else None
        pack_ok = (
            isinstance(report, Mapping)
            and report.get("status") == "PASS"
            and isinstance(summary_value, Mapping)
            and summary_value.get("failed") == 0
            and type(summary_value.get("checks")) is int
            and summary_value.get("passed") == summary_value.get("checks")
        )
    except Exception as exc:
        summary_value = "%s: %s" % (type(exc).__name__, exc)
        pack_ok = False
    _add(checks, "S14P02-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, summary_value)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any], analysis: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "SECURITY_PIPELINE_READY_UNRESOLVED_CRITICAL_OR_HIGH_FINDINGS_ZERO_LOCAL_ONLY" if passed else "SECURITY_PIPELINE_REMEDIATION_REQUIRED",
        "next": "S14/P03_READY_NOT_STARTED" if passed else "S14/P02_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "snapshot": dict(snapshot),
        "analysis": dict(analysis),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Check the frozen S14/P02 delivery state without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    pipeline = _safe_load(root, PIPELINE_PATH, checks, "S14P02-PIPELINE-PARSE")
    sast_policy = _safe_load(root, SAST_POLICY_PATH, checks, "S14P02-SAST-POLICY-PARSE")
    secret_policy = _safe_load(root, SECRET_POLICY_PATH, checks, "S14P02-SECRET-POLICY-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S14P02-FIXTURE-PARSE")
    _check_baseline(root, checks, hashes)
    taskpack_ok = _check_taskpack(root, checks)
    predecessor_ok = _check_predecessor(root, checks, hashes)
    artifacts = _check_artifacts(pipeline, sast_policy, secret_policy, fixture, checks)
    pipeline_value = artifacts["pipeline"]
    sast_value = artifacts["sast"]
    secret_value = artifacts["secret"]
    fixture_value = artifacts["fixture"]
    try:
        analysis = run_security_analysis(root, pipeline_value, sast_value, secret_value) if all(isinstance(value, Mapping) for value in (pipeline_value, sast_value, secret_value)) else {"status": "FAIL", "sast_passed": False, "dependency_lock_passed": False, "secret_passed": False, "container_infrastructure_passed": False, "unresolved_critical_count": 1, "unresolved_high_count": 0, "findings": [], "output_sha256": "UNAVAILABLE"}
    except Exception as exc:
        analysis = {"status": "FAIL", "sast_passed": False, "dependency_lock_passed": False, "secret_passed": False, "container_infrastructure_passed": False, "unresolved_critical_count": 1, "unresolved_high_count": 0, "findings": [{"rule_id": "ANALYSIS-EXCEPTION", "severity": "CRITICAL", "status": "UNRESOLVED", "location": ORACLE_PATH.as_posix(), "detail": "%s: %s" % (type(exc).__name__, exc)}], "output_sha256": "UNAVAILABLE"}
    analysis_ok = analysis.get("status") == "PASS" and analysis.get("unresolved_critical_count") == 0 and analysis.get("unresolved_high_count") == 0
    _add(checks, "S14P02-STATIC-ANALYSIS-UNRESOLVED-CRITICAL-HIGH-ZERO", analysis_ok, {"critical": analysis.get("unresolved_critical_count"), "high": analysis.get("unresolved_high_count"), "findings": analysis.get("findings")})
    boundary_ok = isinstance(pipeline_value, Mapping) and pipeline_value.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }
    _add(checks, "S14P02-NO-NETWORK-ACCOUNT-ORDER-DEPLOY-OR-SOAK-BOUNDARY", boundary_ok, EXECUTION_POLICY)
    portable = all(_portable(value) for value in (pipeline, sast_policy, secret_policy, fixture))
    _add(checks, "S14P02-ARTIFACTS-PORTABLE", portable, "portable" if portable else "local path detected")
    snapshot = {
        "p01_receipt_current": predecessor_ok,
        "pipeline_configuration_closed": taskpack_ok and all(isinstance(value, Mapping) for value in (pipeline_value, sast_value, secret_value, fixture_value)),
        "static_analysis_passed": analysis.get("sast_passed") is True,
        "dependency_lock_analysis_passed": analysis.get("dependency_lock_passed") is True,
        "secret_analysis_passed": analysis.get("secret_passed") is True,
        "container_infrastructure_analysis_passed": analysis.get("container_infrastructure_passed") is True,
        "external_effect_boundary_preserved": boundary_ok,
        "unresolved_critical_count": analysis.get("unresolved_critical_count") if type(analysis.get("unresolved_critical_count")) is int else 1,
        "unresolved_high_count": analysis.get("unresolved_high_count") if type(analysis.get("unresolved_high_count")) is int else 1,
        "coverage_score": "1.0000" if analysis_ok and portable else "0.9999",
        "foreign_odds_input_present": False,
    }
    snapshot_result = evaluate_security_snapshot(snapshot)
    _add(checks, "S14P02-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S14P02_SECURITY_ANALYSIS_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture_value, checks)
    reports_ok = _check_reports(root, fixture_value if isinstance(fixture_value, Mapping) else {}, checks, require_test_reports=require_test_reports)
    _add(checks, "S14P02-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
    _add(checks, "S14P02-PHASE-ONLY-NO-FULL-REGRESSION", EXECUTION_POLICY["full_regression_or_real_time_soak_allowed"] is False, EXECUTION_POLICY)
    return _result(checks, hashes, snapshot, analysis)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"status": "PASS" if (root / relative).is_file() else "FAIL", "sha256": sha256_file(root / relative) if (root / relative).is_file() else "MISSING"}
        for relative in (PIPELINE_PATH, SAST_POLICY_PATH, SECRET_POLICY_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S14_P02_LOCAL_SECURITY_PIPELINE_PRESERVE_P01_AND_SIGNED_EVIDENCE_NO_EXTERNAL_MUTATION",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = set(BASELINE_HASHES)
    paths.update(CONTROL_PLANE_TARGETS)
    paths.update({TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(), P01_EVIDENCE_PATH.as_posix(), P01_ROLLBACK_PATH.as_posix()})
    if require_test_reports:
        paths.update({JUNIT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix(), PACK_REPORT_PATH.as_posix()})
    return {relative: sha256_file(root / relative) for relative in sorted(paths)}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = dict(evidence)
    payload.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    snapshot_result = evaluate_security_snapshot(validation["snapshot"])
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S14_P02_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED" if validation["status"] == "PASS" else "S14_P02_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "execution_policy": dict(EXECUTION_POLICY),
        "commands": list(REQUIRED_COMMANDS),
        "deterministic_replay": {"pipeline_stage_count": len(PIPELINE_STAGE_IDS), "single_pass_snapshot_count": 12, "real_time_wait_performed": False},
        "stage_snapshot_summary": {"status": snapshot_result["status"], "reason_codes": snapshot_result["reason_codes"]},
        "hashes": {"code": sha256_file(root / ORACLE_PATH), "inputs": _input_hashes(root, require_test_reports=require_test_reports), "rollback_evidence": _sha256_bytes(_json_bytes(rollback))},
        "validation": validation,
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    if len(raw_lines) != len(rows):
        raise SecurityAnalysisError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-" + CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S14/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    positions = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) != 1:
        raise SecurityAnalysisError("S14/P02 evidence-index row must exist exactly once")
    planned = {
        "acceptance_contract_id": CONTRACT_ID,
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "id": replacement["id"],
        "kind": "ACCEPTANCE_EVIDENCE",
        "pass_gate": "未处置严重/高危为0。",
        "requirement_id": REQUIREMENT_ID,
        "status": "PLANNED",
    }
    existing = rows[positions[0]]
    if existing != planned and not (isinstance(existing, Mapping) and existing.get("kind") == "PHASE_EVIDENCE" and existing.get("contract_id") == CONTRACT_ID and existing.get("status") == "PASS"):
        raise SecurityAnalysisError("S14/P02 evidence-index row is not the planned or current phase record")
    output = [_jsonl_bytes(replacement) if number == positions[0] else (line + "\n").encode("utf-8") for number, line in enumerate(raw_lines)]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise SecurityAnalysisError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise SecurityAnalysisError("cannot write evidence for a failed S14/P02 phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/P03_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-" + CONTRACT_ID)
    except Exception as exc:
        raise SecurityAnalysisError("existing S14/P02 evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S14-P02"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("requirement_id") == REQUIREMENT_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("phase_id") == PHASE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "SECURITY_PIPELINE_READY_UNRESOLVED_CRITICAL_OR_HIGH_FINDINGS_ZERO_LOCAL_ONLY"
        and evidence.get("next") == "S14/P03_READY_NOT_STARTED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("hashes", {}).get("code") == sha256_file(root / ORACLE_PATH)
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("evidence_id") == "EVD-S14-P02-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and rollback.get("incremental_cash_spent_aud") == "0.00"
        and index.get("kind") == "PHASE_EVIDENCE"
        and index.get("contract_id") == CONTRACT_ID
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S14/P03_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
        and validation.get("analysis", {}).get("unresolved_critical_count") == 0
        and validation.get("analysis", {}).get("unresolved_high_count") == 0
    )
    if not valid:
        raise SecurityAnalysisError("existing S14/P02 evidence does not replay exactly")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/P03_READY_NOT_STARTED",
    }
