"""Fail-closed, local-only acceptance oracle for ABD S14/P03.

S14/P03 records the component metadata that is actually present in this
worktree.  It deliberately separates the one local application component from
unconfigured deployment prerequisites.  A passing result means the declared
production component has source, version, license, and governance ownership;
it does not assert that an image, cloudflared binary, host, account, CVE feed,
or production deployment exists or is safe.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .security_analysis import verify_existing_phase_evidence as verify_security_analysis_phase_evidence


CONTRACT_ID = "AC-S14-P03"
REQUIREMENT_ID = "REQ-S14-P03"
STAGE_ID = "S14"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SBOM_PATH = Path("sbom.json")
GOVERNANCE_PATH = Path("component_governance.json")
PATCH_SLA_PATH = Path("patch_sla.json")
ORACLE_PATH = Path("abd_acceptance/component_governance.py")
TEST_PATH = Path("tests/S14/P03_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S14_P03.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S14/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S14/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
DEPENDENCY_BUDGET_PATH = Path("machine/facts/dependency_budget.lock")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S14-P02_rollback.json")
REPOSITORY_LICENSE_PATH = Path("../LICENSE")

P02_EVIDENCE_SHA256 = "ef081da80f4b8d690dcc396cf762d5998d761136a95bd04dd5ece0c942d4fee9"
P02_ROLLBACK_SHA256 = "1000e28224fb747657065d500cc903560ed0bcc97ee7a8ebd8665b251c0f0d70"

BASELINE_HASHES = {
    "../LICENSE": "aac7f387d4714b270cc91576fdb4e96bb92e14cec27c104c0107bad4ebf6f7df",
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/dependency_budget.lock": "4904a86b7561456edef9f5e4c9da3e8fa5562a83892f224e58ea3a7511e66b06",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "pyproject.toml": "ed30542952d445085e1f7724872bda1b697898f90576bf9bd65fd3191719bb72",
    "uv.lock": "982a3044aabd62584d76cddcbd9dfcfe761482a5e60248ad5e299c18fd2ad9cf",
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
    "phase_test_only": True,
    "broad_suite_or_real_time_wait_allowed": False,
    "external_runtime_access_allowed": False,
    "incremental_cash_spent_aud": "0.00",
}

PRODUCTION_COMPONENT_FIELDS = (
    "bom_ref",
    "name",
    "version",
    "version_pin",
    "component_type",
    "scope",
    "source",
    "license",
    "governance_owner",
    "release_admission",
)
PRODUCTION_COMPONENT = {
    "bom_ref": "pkg:generic/abd@0.0.0.1",
    "name": "abd",
    "version": "0.0.0.1",
    "version_pin": "0.0.0.1",
    "component_type": "APPLICATION_SOURCE",
    "scope": "PRODUCTION",
    "source": {
        "kind": "LOCAL_VIRTUAL_PROJECT",
        "manifest": "pyproject.toml",
        "repository_remote": "git@github.com:LinzeColin/MetaDatabase.git",
        "subdirectory": "ABD",
    },
    "license": {
        "expression": "LicenseRef-LinzeZhang-Proprietary",
        "evidence_path": "../LICENSE",
        "verification": "LOCAL_REPOSITORY_ROOT_LICENSE_TEXT",
    },
    "governance_owner": "单一账户持有人",
    "release_admission": "P03_METADATA_COMPLETE_P04_PROVENANCE_AND_DEPLOYMENT_GATES_REMAIN",
}
SBOM_SCOPE_BOUNDARY = {
    "production_component_definition": "Only source components whose metadata is complete in this local worktree.",
    "runtime_direct_dependencies_from_pyproject": [],
    "production_component_count": 1,
    "declared_unadmitted_items_not_counted_as_production": [
        "UNADMITTED-ABD-IMAGE",
        "UNADMITTED-CLOUDFLARED-BINARY",
        "UNADMITTED-CLOUDFLARE-OVH-RUNTIME",
    ],
    "excluded_as_not_claimed": [
        "DEPLOYED_CONTAINER_IMAGE",
        "INSTALLED_CLOUDFLARED_BINARY",
        "OVH_HOST_CONFIGURATION",
        "CLOUDFLARE_ACCOUNT_CONFIGURATION",
        "REAL_CVE_OR_VENDOR_ADVISORY_STATUS",
    ],
}
UNADMITTED_RUNTIME_PREREQUISITES = [
    {
        "id": "UNADMITTED-ABD-IMAGE",
        "component_kind": "CONTAINER_IMAGE_SELECTOR",
        "declared_in": "infra/compose.yml",
        "scope": "PLANNED_RUNTIME_PREREQUISITE_NOT_PRODUCTION_COMPONENT",
        "source": "INFRA_TEMPLATE_ONLY",
        "version": "UNKNOWN_REQUIRED_AT_ACTUAL_RELEASE",
        "license": "UNKNOWN_REQUIRED_AT_ACTUAL_RELEASE",
        "governance_owner": "单一账户持有人",
        "release_admission": "BLOCKED",
        "block_reason": "ABD_IMAGE is required by digest, but this worktree contains no actual release image value.",
    },
    {
        "id": "UNADMITTED-CLOUDFLARED-BINARY",
        "component_kind": "TUNNEL_CLIENT_BINARY",
        "declared_in": "infra/cloudflared.yml",
        "scope": "PLANNED_RUNTIME_PREREQUISITE_NOT_PRODUCTION_COMPONENT",
        "source": "INFRA_TEMPLATE_ONLY",
        "version": "UNKNOWN_REQUIRED_AT_ACTUAL_RELEASE",
        "license": "UNKNOWN_REQUIRED_AT_ACTUAL_RELEASE",
        "governance_owner": "单一账户持有人",
        "release_admission": "BLOCKED",
        "block_reason": "The local tunnel configuration is a template and does not prove an installed cloudflared binary.",
    },
    {
        "id": "UNADMITTED-CLOUDFLARE-OVH-RUNTIME",
        "component_kind": "EXTERNAL_RUNTIME_CONFIGURATION",
        "declared_in": "machine/facts/canonical_facts.json",
        "scope": "PLANNED_RUNTIME_PREREQUISITE_NOT_PRODUCTION_COMPONENT",
        "source": "OWNER_DECLARED_PLANNED_RUNTIME",
        "version": "UNKNOWN_ACCOUNT_AND_HOST_SPECIFIC",
        "license": "NOT_A_LOCAL_SOFTWARE_COMPONENT",
        "governance_owner": "单一账户持有人",
        "release_admission": "BLOCKED",
        "block_reason": "No OVH host or Cloudflare account configuration was inspected or activated in this phase.",
    },
]

GOVERNANCE_REQUIRED_FIELDS = [
    "bom_ref",
    "name",
    "version",
    "version_pin",
    "source",
    "license",
    "governance_owner",
]
COMPONENT_SCOPE_RULE = {
    "production_scope_source": "sbom.json.production_components",
    "production_component_must_be_explicitly_scoped": True,
    "unadmitted_runtime_items_count_as_production": False,
    "unadmitted_runtime_release_action": "BLOCK_RELEASE",
}
ADMISSION_RULES = {
    "missing_source": "BLOCK_RELEASE",
    "missing_version": "BLOCK_RELEASE",
    "missing_license": "BLOCK_RELEASE",
    "missing_governance_owner": "BLOCK_RELEASE",
    "non_exact_version_pin": "BLOCK_RELEASE",
    "paid_or_unknown_cost_dependency": "BLOCK_ADMISSION_DO_NOT_PURCHASE",
    "new_external_component": "REQUIRE_SOURCE_LICENSE_COST_AND_S14_P02_REVIEW",
}
LICENSE_POLICY = {
    "first_party_expression": "LicenseRef-LinzeZhang-Proprietary",
    "development_allowlist_source": "machine/facts/dependency_budget.lock",
    "unknown_license_action": "BLOCK_RELEASE",
    "external_service_terms_are_not_code_license": True,
}
VERSION_PIN_POLICY = {
    "production_version_must_equal_version_pin": True,
    "version_prefix_v_allowed": False,
    "unknown_version_action": "BLOCK_RELEASE",
    "runtime_direct_dependencies_must_match_pyproject": True,
}
OWNERSHIP_POLICY = {
    "required_owner_field": "governance_owner",
    "default_governance_owner": "单一账户持有人",
    "upstream_copyright_not_inferred": True,
    "missing_owner_action": "BLOCK_RELEASE",
}
UNADMITTED_RUNTIME_POLICY = {
    "required_scope": "PLANNED_RUNTIME_PREREQUISITE_NOT_PRODUCTION_COMPONENT",
    "required_release_admission": "BLOCKED",
    "unknown_metadata_is_admitted": False,
    "actual_release_requires_new_component_record": True,
}

PATCH_SEVERITY_SLAS = [
    {
        "severity": "CRITICAL",
        "maximum_elapsed_hours": "24",
        "deadline_basis": "CONFIRMED_SEVERITY_TIMESTAMP",
        "required_action": "DISABLE_AFFECTED_COMPONENT_OR_BLOCK_RELEASE",
    },
    {
        "severity": "HIGH",
        "maximum_elapsed_hours": "168",
        "deadline_basis": "CONFIRMED_SEVERITY_TIMESTAMP",
        "required_action": "DISABLE_AFFECTED_COMPONENT_OR_BLOCK_RELEASE",
    },
    {
        "severity": "MEDIUM",
        "maximum_elapsed_hours": "720",
        "deadline_basis": "CONFIRMED_SEVERITY_TIMESTAMP",
        "required_action": "SCHEDULE_PATCH_OR_BLOCK_NEXT_RELEASE",
    },
]
PATCH_MAINTENANCE_CADENCE = [
    {
        "control": "CLAMAV_SIGNATURE_UPDATE",
        "cadence": "DAILY",
        "evidence_action": "RECORD_RESULT_OR_BLOCK_MAIL_INGESTION_IF_UNAVAILABLE",
    },
    {
        "control": "SOURCE_CONTRACT_REVALIDATION",
        "cadence": "WEEKLY",
        "evidence_action": "RECORD_RESULT_OR_MARK_SOURCE_NOT_RECOMMENDABLE",
    },
    {
        "control": "SECRET_ROTATION_DRILL",
        "cadence": "QUARTERLY",
        "evidence_action": "RECORD_DRILL_WITHOUT_STORING_SECRET_VALUE",
    },
    {
        "control": "RECOVERY_DRILL",
        "cadence": "MONTHLY",
        "evidence_action": "RECORD_LOCAL_RECOVERY_RESULT",
    },
]

SBOM_FIELDS = {
    "schema_version",
    "bom_format",
    "bom_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "inventory_status",
    "scope_boundary",
    "production_components",
    "development_components",
    "declared_unadmitted_runtime_prerequisites",
    "external_effect_boundary",
    "not_production_evidence",
}
GOVERNANCE_FIELDS = {
    "schema_version",
    "policy_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "production_component_required_fields",
    "component_scope_rule",
    "admission_rules",
    "license_policy",
    "version_pin_policy",
    "ownership_policy",
    "unadmitted_runtime_policy",
    "patch_sla_reference",
    "external_effect_boundary",
    "not_production_evidence",
}
PATCH_SLA_FIELDS = {
    "schema_version",
    "policy_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "scope",
    "severity_slas",
    "maintenance_cadence",
    "unknown_vulnerability_or_component_action",
    "rollback_rule",
    "clock_boundary",
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
    "expected_production_component_count",
    "expected_development_component_count",
    "expected_sla_hours",
    "expected_decision",
    "expected_next",
    "single_pass_case_count",
    "snapshot_cases",
}
SNAPSHOT_CASE_IDS = (
    "PASS",
    "P02_PREDECESSOR_FAIL",
    "SBOM_FAIL",
    "GOVERNANCE_FAIL",
    "PATCH_SLA_FAIL",
    "METADATA_FAIL",
    "VERSION_PIN_FAIL",
    "UNADMITTED_RUNTIME_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PRODUCTION_COUNT_LOW_FAIL",
    "PRODUCTION_COUNT_HIGH_FAIL",
    "POINT_0001_COVERAGE_FAIL",
    "POINT_0001_COVERAGE_OVERFAIL_AND_FOREIGN_ODDS",
)


class ComponentGovernanceError(ValueError):
    """Raised when S14/P03 cannot remain deterministic and fail closed."""


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
            raise ComponentGovernanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise ComponentGovernanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    if not rows:
        raise ComponentGovernanceError("evidence index is empty")
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ComponentGovernanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ComponentGovernanceError("expected exactly one %s=%s" % (key, identifier))
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
        raise ComponentGovernanceError("coverage_score must be four-place decimal text")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ComponentGovernanceError("coverage_score is not decimal") from exc


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
        raise ComponentGovernanceError("%s header is not frozen" % identifier)


def _expected_development_components(root: Path) -> List[Dict[str, Any]]:
    budget = strict_json_load(root / DEPENDENCY_BUDGET_PATH)
    environment = budget.get("python_environment") if isinstance(budget, Mapping) else None
    packages = environment.get("registry_packages") if isinstance(environment, Mapping) else None
    allowlist = environment.get("approved_license_expressions") if isinstance(environment, Mapping) else None
    if (
        not isinstance(packages, list)
        or not isinstance(allowlist, list)
        or environment.get("runtime_direct_dependencies") != []
        or environment.get("dev_direct_dependencies") != ["jsonschema==4.25.1", "pytest==8.4.2"]
    ):
        raise ComponentGovernanceError("dependency budget lock does not retain the frozen zero-runtime-dependency boundary")
    expected: List[Dict[str, Any]] = []
    for package in packages:
        if not isinstance(package, Mapping):
            raise ComponentGovernanceError("registry package is not an object")
        name = package.get("name")
        version = package.get("version")
        scope = package.get("scope")
        source = package.get("source")
        license_expression = package.get("license_spdx")
        if (
            not all(isinstance(item, str) and item for item in (name, version, scope, source, license_expression))
            or license_expression not in allowlist
        ):
            raise ComponentGovernanceError("registry package lacks a frozen source, version, or allowlisted license")
        expected.append(
            {
                "bom_ref": "pkg:pypi/%s@%s" % (name, version),
                "name": name,
                "version": version,
                "scope": scope,
                "source": {
                    "package_url": source,
                    "lock_path": DEPENDENCY_BUDGET_PATH.as_posix(),
                },
                "license": {
                    "expression": license_expression,
                    "evidence_path": DEPENDENCY_BUDGET_PATH.as_posix(),
                },
                "governance_owner": "单一账户持有人",
                "production_component": False,
                "release_admission": "DEVELOPMENT_ONLY_NOT_IN_PRODUCTION_COMPONENT_SCOPE",
            }
        )
    if len(expected) != 12 or len({item["bom_ref"] for item in expected}) != len(expected):
        raise ComponentGovernanceError("development component inventory is not exact")
    return expected


def _repository_license_is_expected(root: Path) -> bool:
    try:
        text = (root / REPOSITORY_LICENSE_PATH).read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        text.startswith("Copyright (c) 2026 LinzeZhang. All Rights Reserved.")
        and "proprietary" in text
        and "confidential" in text
        and "No license, express or implied" in text
    )


def validate_sbom(value: Any, root: Path) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != SBOM_FIELDS or _contains_float(value):
        raise ComponentGovernanceError("SBOM fields are not closed")
    _require_header(value, "SBOM")
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject.get("project")
    except Exception as exc:
        raise ComponentGovernanceError("pyproject cannot establish the runtime dependency boundary") from exc
    if (
        not isinstance(project, Mapping)
        or project.get("name") != "abd"
        or project.get("version") != VERSION
        or project.get("dependencies") != []
        or not _repository_license_is_expected(root)
    ):
        raise ComponentGovernanceError("local application provenance boundary is not exact")
    if (
        value.get("bom_format") != "ABD_LOCAL_COMPONENT_BOM"
        or value.get("bom_id") != "S14-P03-COMPONENT-INVENTORY"
        or value.get("inventory_status") != "FROZEN_LOCAL_PRE_RELEASE_NOT_A_DEPLOYED_SBOM"
        or value.get("scope_boundary") != SBOM_SCOPE_BOUNDARY
        or value.get("production_components") != [PRODUCTION_COMPONENT]
        or value.get("development_components") != _expected_development_components(root)
        or value.get("declared_unadmitted_runtime_prerequisites") != UNADMITTED_RUNTIME_PREREQUISITES
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("not_production_evidence") is not True
    ):
        raise ComponentGovernanceError("SBOM contract is not exact")
    return {
        "production_component_count": len(value["production_components"]),
        "development_component_count": len(value["development_components"]),
        "unadmitted_runtime_prerequisite_count": len(value["declared_unadmitted_runtime_prerequisites"]),
        "runtime_direct_dependency_count": 0,
    }


def validate_component_governance(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != GOVERNANCE_FIELDS or _contains_float(value):
        raise ComponentGovernanceError("component governance fields are not closed")
    _require_header(value, "component governance")
    if (
        value.get("policy_id") != "S14-P03-COMPONENT-GOVERNANCE"
        or value.get("production_component_required_fields") != GOVERNANCE_REQUIRED_FIELDS
        or value.get("component_scope_rule") != COMPONENT_SCOPE_RULE
        or value.get("admission_rules") != ADMISSION_RULES
        or value.get("license_policy") != LICENSE_POLICY
        or value.get("version_pin_policy") != VERSION_PIN_POLICY
        or value.get("ownership_policy") != OWNERSHIP_POLICY
        or value.get("unadmitted_runtime_policy") != UNADMITTED_RUNTIME_POLICY
        or value.get("patch_sla_reference") != PATCH_SLA_PATH.as_posix()
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("not_production_evidence") is not True
    ):
        raise ComponentGovernanceError("component governance contract is not exact")
    return dict(value)


def validate_patch_sla(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != PATCH_SLA_FIELDS or _contains_float(value):
        raise ComponentGovernanceError("patch SLA fields are not closed")
    _require_header(value, "patch SLA")
    if (
        value.get("policy_id") != "S14-P03-PATCH-SLA"
        or value.get("scope")
        != "Static lifecycle policy only; it does not measure live remediation elapsed time or query a CVE feed."
        or value.get("severity_slas") != PATCH_SEVERITY_SLAS
        or value.get("maintenance_cadence") != PATCH_MAINTENANCE_CADENCE
        or value.get("unknown_vulnerability_or_component_action")
        != "BLOCK_NEW_RELEASE_DISABLE_AFFECTED_COMPONENT_PRESERVE_EVIDENCE"
        or value.get("rollback_rule") != "DISABLE_AFFECTED_COMPONENT_RESTORE_LAST_SIGNED_ARTIFACT_PRESERVE_EVIDENCE"
        or value.get("clock_boundary")
        != {
            "real_time_measurement_performed": False,
            "real_time_soak_waited": False,
            "policy_deadlines_are_not_claimed_as_completed": True,
        }
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("not_production_evidence") is not True
    ):
        raise ComponentGovernanceError("patch SLA contract is not exact")
    return dict(value)


def evaluate_component_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one frozen component-governance snapshot without enabling actions."""

    required = {
        "p02_receipt_current",
        "sbom_closed",
        "governance_closed",
        "patch_sla_closed",
        "production_component_count",
        "production_metadata_complete",
        "version_pins_exact",
        "unadmitted_runtime_blocked",
        "external_effect_boundary_preserved",
        "coverage_score",
        "foreign_odds_input_present",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != required:
        raise ComponentGovernanceError("component snapshot shape is invalid")
    for field in required - {"production_component_count", "coverage_score"}:
        if type(snapshot.get(field)) is not bool:
            raise ComponentGovernanceError("%s must be boolean" % field)
    if type(snapshot.get("production_component_count")) is not int or snapshot["production_component_count"] < 0:
        raise ComponentGovernanceError("production_component_count must be a nonnegative integer")
    coverage = _coverage_decimal(snapshot.get("coverage_score"))
    reason_map = (
        ("p02_receipt_current", "P02_RECEIPT_NOT_CURRENT"),
        ("sbom_closed", "SBOM_NOT_CLOSED"),
        ("governance_closed", "COMPONENT_GOVERNANCE_NOT_CLOSED"),
        ("patch_sla_closed", "PATCH_SLA_NOT_CLOSED"),
        ("production_metadata_complete", "PRODUCTION_COMPONENT_METADATA_INCOMPLETE"),
        ("version_pins_exact", "VERSION_PIN_NOT_EXACT"),
        ("unadmitted_runtime_blocked", "UNADMITTED_RUNTIME_COMPONENT_NOT_BLOCKED"),
        ("external_effect_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["production_component_count"] != 1:
        reasons.append("PRODUCTION_COMPONENT_COUNT_NOT_EXACT")
    if coverage != Decimal("1.0000"):
        reasons.append("COMPONENT_METADATA_COVERAGE_NOT_EXACT")
    if snapshot["foreign_odds_input_present"] is True:
        reasons.append("FOREIGN_ODDS_INPUT_REJECTED")
    result: Dict[str, Any] = {
        "status": "S14P03_COMPONENT_GOVERNANCE_VERIFIED_NO_ACTION"
        if not reasons
        else "S14P03_COMPONENT_GOVERNANCE_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def validate_component_fixture(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != FIXTURE_FIELDS or _contains_float(value):
        raise ComponentGovernanceError("component fixture fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("fixture_id") != "FIX-S14-P03-COMPONENT-GOVERNANCE"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("minimum_targeted_pytest_cases") != 35
        or value.get("expected_production_component_count") != 1
        or value.get("expected_development_component_count") != 12
        or value.get("expected_sla_hours") != {"CRITICAL": "24", "HIGH": "168", "MEDIUM": "720"}
        or value.get("expected_decision") != "COMPONENT_METADATA_COMPLETE_LOCAL_ONLY_P04_PROVENANCE_REQUIRED"
        or value.get("expected_next") != "S14/P04_READY_NOT_STARTED"
        or value.get("single_pass_case_count") != len(SNAPSHOT_CASE_IDS)
    ):
        raise ComponentGovernanceError("component fixture header is not frozen")
    rows = value.get("snapshot_cases")
    if (
        not isinstance(rows, list)
        or [row.get("case_id") for row in rows if isinstance(row, Mapping)] != list(SNAPSHOT_CASE_IDS)
    ):
        raise ComponentGovernanceError("component fixture snapshots are not exact")
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"case_id", "snapshot", "expected"}:
            raise ComponentGovernanceError("component fixture snapshot shape is invalid")
        actual = evaluate_component_snapshot(row["snapshot"])
        expected = row.get("expected")
        if (
            not isinstance(expected, Mapping)
            or set(expected) != {"status", "reason_codes"}
            or actual["status"] != expected["status"]
            or actual["reason_codes"] != expected["reason_codes"]
        ):
            raise ComponentGovernanceError("component fixture expected result is invalid")
    return dict(value)


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
        identifier = "S14P03-BASELINE-%s" % relative.replace("../", "ROOT-").upper().replace("/", "-").replace(".", "-")
        _add(checks, identifier, valid, {"expected": expected, "actual": actual})
        passed = passed and valid
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S14P03-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S14P03-CONTRACTS-PARSE")
    graph_document = _safe_load(root, TASK_GRAPH_PATH, checks, "S14P03-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S14P03-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S14P03-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        index = []
        _add(checks, "S14P03-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
    tasks = graph_document.get("tasks") if isinstance(graph_document, Mapping) else None
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        task_rows = [
            row
            for row in tasks
            if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID
        ]
        task_map = {row.get("id"): row for row in task_rows}
        index_row = _row(index, "INDEX-" + CONTRACT_ID)
        task_ids = ["T-S14-P03-01", "T-S14-P03-02", "T-S14-P03-03"]
        test_ids = ["TEST-S14-P03", "TEST-S14-P03-BOUNDARY", "TEST-S14-P03-REPLAY"]
        non_goals = [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
        planned_index = {
            "acceptance_contract_id": CONTRACT_ID,
            "expected_artifact": EVIDENCE_PATH.as_posix(),
            "id": "INDEX-" + CONTRACT_ID,
            "kind": "ACCEPTANCE_EVIDENCE",
            "pass_gate": "每个生产组件有来源、版本、许可证和负责人。",
            "requirement_id": REQUIREMENT_ID,
            "status": "PLANNED",
        }
        signed_index = (
            set(index_row) == {
                "id",
                "kind",
                "stage_id",
                "contract_id",
                "requirement_id",
                "status",
                "actual_artifact",
                "artifact_sha256",
                "next",
                "verified_at",
            }
            and index_row.get("id") == "INDEX-" + CONTRACT_ID
            and index_row.get("kind") == "PHASE_EVIDENCE"
            and index_row.get("stage_id") == STAGE_ID
            and index_row.get("contract_id") == CONTRACT_ID
            and index_row.get("requirement_id") == REQUIREMENT_ID
            and index_row.get("status") == "PASS"
            and index_row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and index_row.get("next") == "S14/P04_READY_NOT_STARTED"
            and index_row.get("verified_at") == FIXED_CLOCK
            and isinstance(index_row.get("artifact_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", index_row["artifact_sha256"]) is not None
        )
        exact = (
            requirement.get("stage_id") == STAGE_ID
            and requirement.get("phase_id") == PHASE_ID
            and requirement.get("scope") == [SBOM_PATH.as_posix(), GOVERNANCE_PATH.as_posix(), PATCH_SLA_PATH.as_posix()]
            and requirement.get("target") == "每个生产组件有来源、版本、许可证和负责人。"
            and requirement.get("non_goals") == non_goals
            and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("pass_gate") == requirement.get("target")
            and contract.get("threshold") == requirement.get("target")
            and contract.get("oracle", {}).get("command")
            == "python -m abd_acceptance --contract %s --evidence machine/evidence" % CONTRACT_ID
            and [item.get("id") for item in contract.get("tests", [])] == test_ids
            and [row.get("id") for row in task_rows] == task_ids
            and task_map[task_ids[0]].get("outputs")
            == [SBOM_PATH.as_posix(), GOVERNANCE_PATH.as_posix(), PATCH_SLA_PATH.as_posix()]
            and task_map[task_ids[0]].get("depends_on") == ["T-S14-P02-03"]
            and task_map[task_ids[1]].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and task_map[task_ids[1]].get("depends_on") == [task_ids[0]]
            and task_map[task_ids[2]].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and task_map[task_ids[2]].get("depends_on") == [task_ids[1]]
            and all(
                row.get("requirement_ids") == [REQUIREMENT_ID]
                and row.get("acceptance_criteria_ids") == [CONTRACT_ID]
                for row in task_rows
            )
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == task_ids
            and trace.get("test_ids") == test_ids
            and trace.get("evidence_id") == "EVD-S14-P03"
            and trace.get("artifact_ids") == ["ART-S14-P03-01", "ART-S14-P03-02", "ART-S14-P03-03"]
            and (index_row == planned_index or signed_index)
        )
        detail: Any = {"task_ids": task_ids, "index_status": index_row.get("status")}
    except Exception as exc:
        exact = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P03-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", exact, detail)
    return exact


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    try:
        verified = verify_security_analysis_phase_evidence(root)
        receipt = strict_json_load(root / P02_EVIDENCE_PATH)
        rollback = strict_json_load(root / P02_ROLLBACK_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-AC-S14-P02")
        receipt_ok = (
            isinstance(receipt, Mapping)
            and receipt.get("status") == "PASS"
            and receipt.get("next") == "S14/P03_READY_NOT_STARTED"
            and receipt.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and sha256_file(root / P02_EVIDENCE_PATH) == P02_EVIDENCE_SHA256
        )
        rollback_ok = (
            isinstance(rollback, Mapping)
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and rollback.get("production_state_changed") is False
            and sha256_file(root / P02_ROLLBACK_PATH) == P02_ROLLBACK_SHA256
        )
        index_ok = (
            index.get("kind") == "PHASE_EVIDENCE"
            and index.get("contract_id") == "AC-S14-P02"
            and index.get("status") == "PASS"
            and index.get("actual_artifact") == P02_EVIDENCE_PATH.as_posix()
            and index.get("artifact_sha256") == P02_EVIDENCE_SHA256
            and index.get("next") == "S14/P03_READY_NOT_STARTED"
        )
        passed = verified.get("status") == "PASS" and receipt_ok and rollback_ok and index_ok
        detail: Any = {
            "predecessor_verifier": verified.get("status"),
            "receipt": receipt_ok,
            "rollback": rollback_ok,
            "index": index_ok,
        }
        hashes[P02_EVIDENCE_PATH.as_posix()] = sha256_file(root / P02_EVIDENCE_PATH)
        hashes[P02_ROLLBACK_PATH.as_posix()] = sha256_file(root / P02_ROLLBACK_PATH)
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P03-P02-SIGNED-DEPENDENCY-EXACT", passed, detail)
    return passed


def _check_artifacts(
    sbom: Any,
    governance: Any,
    patch_sla: Any,
    fixture: Any,
    root: Path,
    checks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        sbom_summary = validate_sbom(sbom, root)
        _add(checks, "S14P03-SBOM-EXACT", True, sbom_summary)
        sbom_ok = True
    except Exception as exc:
        sbom_summary = {
            "production_component_count": 0,
            "development_component_count": 0,
            "unadmitted_runtime_prerequisite_count": 0,
            "runtime_direct_dependency_count": 0,
        }
        _add(checks, "S14P03-SBOM-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        sbom_ok = False
    try:
        validate_component_governance(governance)
        _add(checks, "S14P03-COMPONENT-GOVERNANCE-EXACT", True, GOVERNANCE_REQUIRED_FIELDS)
        governance_ok = True
    except Exception as exc:
        _add(checks, "S14P03-COMPONENT-GOVERNANCE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        governance_ok = False
    try:
        validate_patch_sla(patch_sla)
        _add(checks, "S14P03-PATCH-SLA-EXACT", True, ["24", "168", "720"])
        patch_sla_ok = True
    except Exception as exc:
        _add(checks, "S14P03-PATCH-SLA-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        patch_sla_ok = False
    try:
        fixture_value = validate_component_fixture(fixture)
        _add(checks, "S14P03-FIXTURE-EXACT", True, fixture_value["single_pass_case_count"])
        fixture_ok = True
    except Exception as exc:
        _add(checks, "S14P03-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        fixture_ok = False
    return {
        "sbom_ok": sbom_ok,
        "governance_ok": governance_ok,
        "patch_sla_ok": patch_sla_ok,
        "fixture_ok": fixture_ok,
        "sbom_summary": sbom_summary,
    }


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    rows = fixture.get("snapshot_cases") if isinstance(fixture, Mapping) else None
    if not isinstance(rows, list):
        _add(checks, "S14P03-SNAPSHOT-CASES", False, "cases unavailable")
        return False
    passed = True
    for row in rows:
        try:
            actual = evaluate_component_snapshot(row["snapshot"])
            expected = row["expected"]
            current = actual["status"] == expected["status"] and actual["reason_codes"] == expected["reason_codes"]
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            current = False
        case_id = row.get("case_id") if isinstance(row, Mapping) else "MALFORMED"
        _add(checks, "S14P03-CASE-%s" % case_id, current, actual)
        passed = passed and current
    return passed


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    try:
        document = ElementTree.parse(root / JUNIT_PATH).getroot()
        suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
        summary = {
            field: sum(int(suite.attrib.get(field, "0")) for suite in suites)
            for field in ("tests", "failures", "errors", "skipped")
        }
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
    _add(checks, "S14P03-TARGETED-PYTEST-REPORT", junit_ok, summary)
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
    _add(checks, "S14P03-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
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
    _add(checks, "S14P03-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, summary_value)
    return junit_ok and scan_ok and pack_ok


def _result(
    checks: List[Dict[str, Any]],
    hashes: Mapping[str, str],
    snapshot: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "COMPONENT_METADATA_COMPLETE_LOCAL_ONLY_P04_PROVENANCE_REQUIRED"
        if passed
        else "COMPONENT_GOVERNANCE_REMEDIATION_REQUIRED",
        "next": "S14/P04_READY_NOT_STARTED" if passed else "S14/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_ids": failed},
        "checks": list(checks),
        "snapshot": dict(snapshot),
        "analysis": dict(analysis),
        "hashes": dict(sorted(hashes.items())),
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the local S14/P03 contract without contacting an external system."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    predecessor_ok = _check_predecessor(root, checks, hashes)
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    sbom = _safe_load(root, SBOM_PATH, checks, "S14P03-SBOM-PARSE")
    governance = _safe_load(root, GOVERNANCE_PATH, checks, "S14P03-COMPONENT-GOVERNANCE-PARSE")
    patch_sla = _safe_load(root, PATCH_SLA_PATH, checks, "S14P03-PATCH-SLA-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S14P03-FIXTURE-PARSE")
    artifact_result = _check_artifacts(sbom, governance, patch_sla, fixture, root, checks)
    snapshot_input = {
        "p02_receipt_current": predecessor_ok,
        "sbom_closed": artifact_result["sbom_ok"],
        "governance_closed": artifact_result["governance_ok"],
        "patch_sla_closed": artifact_result["patch_sla_ok"],
        "production_component_count": artifact_result["sbom_summary"]["production_component_count"],
        "production_metadata_complete": artifact_result["sbom_ok"],
        "version_pins_exact": artifact_result["sbom_ok"],
        "unadmitted_runtime_blocked": artifact_result["sbom_ok"],
        "external_effect_boundary_preserved": EXTERNAL_EFFECT_BOUNDARY
        == {
            "external_network_accessed": False,
            "gmail_account_or_api_accessed": False,
            "ovh_or_cloudflare_runtime_accessed": False,
            "real_account_balance_read_or_written": False,
            "recommendation_generated_or_enabled": False,
            "order_submitted_confirmed_or_retried": False,
            "production_deployed_or_activated": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        },
        "coverage_score": "1.0000" if artifact_result["sbom_ok"] else "0.0000",
        "foreign_odds_input_present": False,
    }
    snapshot = evaluate_component_snapshot(snapshot_input)
    _add(
        checks,
        "S14P03-ACTUAL-COMPONENT-SNAPSHOT-PASS",
        snapshot["status"] == "S14P03_COMPONENT_GOVERNANCE_VERIFIED_NO_ACTION",
        snapshot,
    )
    _check_snapshot_cases(fixture, checks)
    if isinstance(fixture, Mapping):
        _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    elif require_test_reports:
        _add(checks, "S14P03-TEST-REPORTS-UNAVAILABLE", False, "fixture unavailable")
    analysis = {
        **artifact_result["sbom_summary"],
        "production_components_complete": artifact_result["sbom_summary"]["production_component_count"]
        if artifact_result["sbom_ok"]
        else 0,
        "production_components_incomplete": 0 if artifact_result["sbom_ok"] else 1,
        "live_vulnerability_database_queried": False,
        "production_runtime_inventory_verified": False,
        "external_network_used": False,
        "external_account_or_runtime_used": False,
        "status": "PASS" if artifact_result["sbom_ok"] and artifact_result["governance_ok"] and artifact_result["patch_sla_ok"] else "FAIL",
    }
    return _result(checks, hashes, snapshot, analysis)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {
            "status": "PASS" if (root / relative).is_file() else "FAIL",
            "sha256": sha256_file(root / relative) if (root / relative).is_file() else "MISSING",
        }
        for relative in (SBOM_PATH, GOVERNANCE_PATH, PATCH_SLA_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S14_P03_COMPONENT_ADMISSION_PRESERVE_P02_AND_SIGNED_EVIDENCE_NO_EXTERNAL_MUTATION",
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
    paths.update(
        {
            SBOM_PATH.as_posix(),
            GOVERNANCE_PATH.as_posix(),
            PATCH_SLA_PATH.as_posix(),
            ORACLE_PATH.as_posix(),
            TEST_PATH.as_posix(),
            FIXTURE_PATH.as_posix(),
            P02_EVIDENCE_PATH.as_posix(),
            P02_ROLLBACK_PATH.as_posix(),
        }
    )
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
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S14_P03_LOCAL_EVIDENCE_ONLY_P04_AND_STAGE_REVIEW_REQUIRED"
        if validation["status"] == "PASS"
        else "S14_P03_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "execution_policy": dict(EXECUTION_POLICY),
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S14/P03_test.py --junitxml=machine/evidence/S14/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S14/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S14/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S14-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {
            "production_component_count": 1,
            "single_pass_snapshot_count": len(SNAPSHOT_CASE_IDS),
            "real_time_wait_performed": False,
        },
        "component_scope": {
            "runtime_direct_dependencies": [],
            "unadmitted_runtime_prerequisites": [item["id"] for item in UNADMITTED_RUNTIME_PREREQUISITES],
            "production_runtime_not_claimed": True,
        },
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
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
        raise ComponentGovernanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-" + CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S14/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    positions = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) != 1:
        raise ComponentGovernanceError("S14/P03 evidence-index row must exist exactly once")
    planned = {
        "acceptance_contract_id": CONTRACT_ID,
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "id": replacement["id"],
        "kind": "ACCEPTANCE_EVIDENCE",
        "pass_gate": "每个生产组件有来源、版本、许可证和负责人。",
        "requirement_id": REQUIREMENT_ID,
        "status": "PLANNED",
    }
    existing = rows[positions[0]]
    if existing != planned and not (
        isinstance(existing, Mapping) and existing.get("kind") == "PHASE_EVIDENCE" and existing.get("contract_id") == CONTRACT_ID and existing.get("status") == "PASS"
    ):
        raise ComponentGovernanceError("S14/P03 evidence-index row is not the planned or current phase record")
    output = [
        _jsonl_bytes(replacement) if number == positions[0] else (line + "\n").encode("utf-8")
        for number, line in enumerate(raw_lines)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ComponentGovernanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ComponentGovernanceError("cannot write evidence for a failed S14/P03 phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/P04_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-" + CONTRACT_ID)
    except Exception as exc:
        raise ComponentGovernanceError("existing S14/P03 evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S14-P03"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("requirement_id") == REQUIREMENT_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("phase_id") == PHASE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "COMPONENT_METADATA_COMPLETE_LOCAL_ONLY_P04_PROVENANCE_REQUIRED"
        and evidence.get("next") == "S14/P04_READY_NOT_STARTED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("hashes", {}).get("code") == sha256_file(root / ORACLE_PATH)
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("evidence_id") == "EVD-S14-P03-ROLLBACK"
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
        and index.get("next") == "S14/P04_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
        and validation.get("analysis", {}).get("production_component_count") == 1
        and validation.get("analysis", {}).get("production_components_incomplete") == 0
    )
    if not valid:
        raise ComponentGovernanceError("existing S14/P03 evidence does not replay exactly")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/P04_READY_NOT_STARTED",
    }
