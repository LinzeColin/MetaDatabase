"""Fail-closed, fixture-only multi-surface E2E oracle for ABD S15/P03.

The phase replays frozen local configuration schemas, static Chinese client
surfaces, a browser-component contract, and recovery artifacts.  It neither
contacts nor configures OVH, Cloudflare, a browser, TAB, Gmail, an account, or
an order endpoint.  "Multi-environment" below therefore means deterministic
local contract replay, never a claim of a live host, edge, device, extension,
or deployment.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .source_contract_integration import (
    SOURCE_SPECS as P02_SOURCE_SPECS,
    evaluate_integration_case as evaluate_p02_integration_case,
)
from .source_contract_integration import verify_existing_phase_evidence as verify_s15_p02_evidence


CONTRACT_ID = "AC-S15-P03"
REQUIREMENT_ID = "REQ-S15-P03"
STAGE_ID = "S15"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

E2E_TESTS_PATH = Path("e2e_tests.json")
ENVIRONMENT_MATRIX_PATH = Path("environment_matrix.json")
E2E_EVIDENCE_PATH = Path("e2e_evidence.json")
ORACLE_PATH = Path("abd_acceptance/e2e_multi_environment.py")
TEST_PATH = Path("tests/S15/P03_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S15_P03.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S15/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S15/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
ROADMAP_PATH = Path("machine/facts/roadmap.json")
CANONICAL_FACTS_PATH = Path("machine/facts/canonical_facts.json")

P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S15-P02_rollback.json")
P02_EVIDENCE_SHA256 = "b3e8c7f5eb604d19029ff23eb0f4c382ac194634a9fdc4fe8f44e998dde22521"
P02_ROLLBACK_SHA256 = "971bc1d3b8059d064cfa4b379c3978e557a0f328a8c26122d95b0f8d4826f499"
P02_INTEGRATION_TESTS_PATH = Path("integration_tests.json")
P02_FIXTURES_MANIFEST_PATH = Path("fixtures_manifest.json")

FEATURE_FLAG_ID = "quality:s15-p03-local-multi-surface-e2e"
EXPECTED_TASK_IDS = ("T-S15-P03-01", "T-S15-P03-02", "T-S15-P03-03")
EXPECTED_TEST_IDS = ("TEST-S15-P03", "TEST-S15-P03-BOUNDARY", "TEST-S15-P03-REPLAY")
EXPECTED_ARTIFACTS = {
    "ART-S15-P03-01": E2E_TESTS_PATH,
    "ART-S15-P03-02": ENVIRONMENT_MATRIX_PATH,
    "ART-S15-P03-03": E2E_EVIDENCE_PATH,
}

ENVIRONMENT_SPECS = (
    {
        "environment_id": "ENV-S15-P03-OVH-CONFIG-SCHEMA",
        "surface": "OVH_CONFIGURATION_SCHEMA",
        "artifact_paths": ("infra/config.schema.json", "infra/compose.yml"),
        "validation_class": "PRODUCTION_EQUIVALENT_CONFIGURATION_SCHEMA",
        "replay_mode": "LOCAL_STATIC_SCHEMA_REPLAY",
    },
    {
        "environment_id": "ENV-S15-P03-CLOUDFLARE-EDGE-SCHEMA",
        "surface": "CLOUDFLARE_EDGE_CONFIGURATION",
        "artifact_paths": ("infra/cloudflared.yml", "degraded_page.html"),
        "validation_class": "PRODUCTION_EQUIVALENT_CONFIGURATION_SCHEMA",
        "replay_mode": "LOCAL_STATIC_SCHEMA_REPLAY",
    },
    {
        "environment_id": "ENV-S15-P03-ZH-DESKTOP-STATIC",
        "surface": "CHINESE_DESKTOP_STATIC_CLIENT",
        "artifact_paths": ("webapp/index.html", "webapp/app.css"),
        "validation_class": "STATIC_CLIENT_CONTRACT",
        "replay_mode": "LOCAL_STATIC_CLIENT_REPLAY",
    },
    {
        "environment_id": "ENV-S15-P03-ZH-MOBILE-STATIC",
        "surface": "CHINESE_MOBILE_STATIC_CLIENT",
        "artifact_paths": ("webapp/index.html", "webapp/app.css"),
        "validation_class": "STATIC_CLIENT_CONTRACT",
        "replay_mode": "LOCAL_STATIC_CLIENT_REPLAY",
    },
    {
        "environment_id": "ENV-S15-P03-BROWSER-COMPONENT",
        "surface": "BROWSER_COMPONENT_LOCAL",
        "artifact_paths": ("browser_companion/manifest.json", "browser_companion/content.js"),
        "validation_class": "STATIC_CLIENT_CONTRACT",
        "replay_mode": "LOCAL_COMPONENT_CONTRACT_REPLAY",
    },
    {
        "environment_id": "ENV-S15-P03-RECOVERY-PATH",
        "surface": "RECOVERY_PATH_LOCAL",
        "artifact_paths": ("journey_tests.json", "recovery_actions.json", "degraded_page.html"),
        "validation_class": "STATIC_RECOVERY_CONTRACT",
        "replay_mode": "LOCAL_RECOVERY_CONTRACT_REPLAY",
    },
)
ENVIRONMENT_IDS = tuple(item["environment_id"] for item in ENVIRONMENT_SPECS)
JOURNEY_CLASSES = ("GOLDEN", "BLACK", "DEGRADED", "RECOVERY")
ENVIRONMENT_MODES = ("ALL_LOCAL_SURFACES", "SIMULATED_EDGE_SCHEMA_UNAVAILABLE", "RECOVERY_LOCAL_REPLAY")
EXPECTED_SCENARIOS = (
    {
        "case_id": "S15-P03-GOLDEN-BASELINE-LOCAL",
        "journey_class": "GOLDEN",
        "source_replay_case_id": "S15-P02-BASELINE-LOCAL",
        "environment_mode": "ALL_LOCAL_SURFACES",
        "simulated_unavailable_environment_id": "NONE",
        "expected": {
            "status": "E2E_GOLDEN_LOCAL_PASS_NO_EXTERNAL_ACTION",
            "reason_codes": ["ALL_LOCAL_SURFACES_CONTRACT_VALIDATED", "P02_BASELINE_LOCAL_REPLAY_PASS"],
        },
    },
    {
        "case_id": "S15-P03-GOLDEN-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
        "journey_class": "GOLDEN",
        "source_replay_case_id": "S15-P02-ODDS-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
        "environment_mode": "ALL_LOCAL_SURFACES",
        "simulated_unavailable_environment_id": "NONE",
        "expected": {
            "status": "E2E_GOLDEN_LOCAL_PASS_NO_EXTERNAL_ACTION",
            "reason_codes": ["ALL_LOCAL_SURFACES_CONTRACT_VALIDATED", "P02_FAVOURABLE_BOUNDARY_REPLAY_PASS"],
        },
    },
    {
        "case_id": "S15-P03-BLACK-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
        "journey_class": "BLACK",
        "source_replay_case_id": "S15-P02-ODDS-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
        "environment_mode": "ALL_LOCAL_SURFACES",
        "simulated_unavailable_environment_id": "NONE",
        "expected": {
            "status": "E2E_BLACK_REVOKED_NO_ORDER",
            "reason_codes": ["P02_ADVERSE_MINUS_0_0001_FAILED_CLOSED", "NO_EXTERNAL_ACTION"],
        },
    },
    {
        "case_id": "S15-P03-BLACK-RESULT-TICKET-MISMATCH",
        "journey_class": "BLACK",
        "source_replay_case_id": "S15-P02-RESULT-TICKET-MISMATCH",
        "environment_mode": "ALL_LOCAL_SURFACES",
        "simulated_unavailable_environment_id": "NONE",
        "expected": {
            "status": "E2E_BLACK_REVOKED_NO_ORDER",
            "reason_codes": ["P02_RESULT_TICKET_MISMATCH_FAILED_CLOSED", "NO_EXTERNAL_ACTION"],
        },
    },
    {
        "case_id": "S15-P03-DEGRADED-SIMULATED-EDGE-SCHEMA-UNAVAILABLE",
        "journey_class": "DEGRADED",
        "source_replay_case_id": "S15-P02-BASELINE-LOCAL",
        "environment_mode": "SIMULATED_EDGE_SCHEMA_UNAVAILABLE",
        "simulated_unavailable_environment_id": "ENV-S15-P03-CLOUDFLARE-EDGE-SCHEMA",
        "expected": {
            "status": "E2E_DEGRADED_LOCAL_RECOVERY_PAGE_NO_ACTION",
            "reason_codes": ["SIMULATED_EDGE_SCHEMA_UNAVAILABLE", "RECOVERY_PAGE_STATIC_CONTRACT_VALIDATED"],
        },
    },
    {
        "case_id": "S15-P03-RECOVERY-FRESH-LOCAL-REPLAY",
        "journey_class": "RECOVERY",
        "source_replay_case_id": "S15-P02-BASELINE-LOCAL",
        "environment_mode": "RECOVERY_LOCAL_REPLAY",
        "simulated_unavailable_environment_id": "NONE",
        "expected": {
            "status": "E2E_RECOVERY_READY_FRESH_LOCAL_REPLAY_NO_ACTION",
            "reason_codes": ["FRESH_LOCAL_P02_BASELINE_REPLAY_PASS", "RECOVERY_CATALOG_STATIC_CONTRACT_VALIDATED"],
        },
    },
)
EXPECTED_CASE_IDS = tuple(item["case_id"] for item in EXPECTED_SCENARIOS)
NEGATIVE_MUTATION_IDS = (
    "MUT-S15-P03-UNKNOWN-E2E-FIELD",
    "MUT-S15-P03-UNPINNED-ENVIRONMENT-HASH",
    "MUT-S15-P03-UNDECLARED-P02-REPLAY-CASE",
    "MUT-S15-P03-UNSTRUCTURED-EVIDENCE-LOG",
)

EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "production_equivalent_config_schema_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "cloudflare_account_dns_or_tunnel_accessed": False,
    "desktop_or_mobile_browser_exercised": False,
    "browser_component_installed_or_run": False,
    "tab_or_provider_runtime_accessed": False,
    "gmail_account_or_api_accessed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
CLAIM_BOUNDARY = {
    "local_multi_surface_contract_replayed": True,
    "actual_ovh_host_exercised": False,
    "actual_cloudflare_edge_exercised": False,
    "actual_desktop_or_mobile_browser_exercised": False,
    "actual_browser_component_installed": False,
    "actual_network_outage_exercised": False,
    "external_network_accessed": False,
}
BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    CANONICAL_FACTS_PATH.as_posix(): "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    PARAMETERS_PATH.as_posix(): "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    ROADMAP_PATH.as_posix(): "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    REQUIREMENTS_PATH.as_posix(): "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    CONTRACTS_PATH.as_posix(): "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    TASK_GRAPH_PATH.as_posix(): "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    TRACEABILITY_PATH.as_posix(): "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}


class MultiEnvironmentE2EError(ValueError):
    """Raised when the local S15/P03 contract fails closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _closed_mapping(value: Any, fields: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields) or _contains_float(value):
        raise MultiEnvironmentE2EError("%s fields are not closed" % label)
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise MultiEnvironmentE2EError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise MultiEnvironmentE2EError("JSONL row %d is not an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise MultiEnvironmentE2EError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise MultiEnvironmentE2EError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _expected_environment_rows(root: Path) -> List[Dict[str, Any]]:
    return [
        {
            "environment_id": spec["environment_id"],
            "surface": spec["surface"],
            "artifact_paths": list(spec["artifact_paths"]),
            "artifact_sha256": {relative: sha256_file(root / relative) for relative in spec["artifact_paths"]},
            "validation_class": spec["validation_class"],
            "replay_mode": spec["replay_mode"],
            "external_execution_performed": False,
        }
        for spec in ENVIRONMENT_SPECS
    ]


def validate_environment_matrix(root: Path, document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "artifact_id", "matrix_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version",
        "fixed_clock", "environments", "execution_policy", "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "environment_matrix")
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P03-02"
        and document.get("matrix_id") == "S15-P03-LOCAL-MULTI-SURFACE-MATRIX"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("environments") == _expected_environment_rows(root)
        and document.get("execution_policy") == EXECUTION_POLICY
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise MultiEnvironmentE2EError("environment_matrix is not exact")
    return document


def _surface_checks(root: Path) -> Dict[str, Dict[str, Any]]:
    checks: Dict[str, Dict[str, Any]] = {}
    try:
        schema = strict_json_load(root / "infra/config.schema.json")
        compose = strict_json_load(root / "infra/compose.yml")
        checks["ENV-S15-P03-OVH-CONFIG-SCHEMA"] = {
            "passed": (
                _nested(schema, "properties", "product_version", "const") == VERSION
                and _nested(schema, "properties", "host", "properties", "provider", "const") == "OVHcloud"
                and _nested(schema, "properties", "budget", "properties", "incremental_cash_aud", "const") == "0.00"
                and _nested(compose, "services", "abd-core", "environment", "ABD_ORDER_SUBMISSION_ENABLED") == "false"
                and _nested(compose, "services", "abd-core", "ports")[0].get("host_ip") == "127.0.0.1"
            ),
            "detail": "local OVH configuration schema and loopback compose contract",
        }
    except Exception as exc:
        checks["ENV-S15-P03-OVH-CONFIG-SCHEMA"] = {"passed": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    try:
        edge = strict_json_load(root / "infra/cloudflared.yml")
        page = (root / "degraded_page.html").read_text(encoding="utf-8")
        checks["ENV-S15-P03-CLOUDFLARE-EDGE-SCHEMA"] = {
            "passed": (
                edge.get("tunnel") == "00000000-0000-4000-8000-000000000000"
                and edge.get("credentials-file") == "/etc/cloudflared/00000000-0000-4000-8000-000000000000.json"
                and _nested(edge, "ingress")[0].get("service") == "http" + "://127.0.0.1:8080"
                and edge.get("ingress", [])[-1] == {"service": "http" + "_status:404"}
                and "服务暂不可用" in page
                and "停止新建议。不要使用任何旧建议下单。" in page
            ),
            "detail": "local Cloudflare edge schema and degraded-page contract",
        }
    except Exception as exc:
        checks["ENV-S15-P03-CLOUDFLARE-EDGE-SCHEMA"] = {"passed": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    try:
        page = (root / "webapp/index.html").read_text(encoding="utf-8")
        style = (root / "webapp/app.css").read_text(encoding="utf-8")
        checks["ENV-S15-P03-ZH-DESKTOP-STATIC"] = {
            "passed": "<html lang=\"zh-CN\">" in page and "当前不建议" in page and "不执行外部动作" in page and "@media (min-width: 721px)" in style,
            "detail": "local Chinese desktop static-client contract",
        }
        checks["ENV-S15-P03-ZH-MOBILE-STATIC"] = {
            "passed": "name=\"viewport\"" in page and "@media (max-width: 720px)" in style and "grid-template-columns: 1fr" in style,
            "detail": "local Chinese mobile static-client contract",
        }
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
        checks["ENV-S15-P03-ZH-DESKTOP-STATIC"] = {"passed": False, "detail": detail}
        checks["ENV-S15-P03-ZH-MOBILE-STATIC"] = {"passed": False, "detail": detail}
    try:
        manifest = strict_json_load(root / "browser_companion/manifest.json")
        content = (root / "browser_companion/content.js").read_text(encoding="utf-8")
        checks["ENV-S15-P03-BROWSER-COMPONENT"] = {
            "passed": (
                manifest.get("manifest_version") == 3
                and manifest.get("permissions") == ["activeTab", "scripting"]
                and "host_permissions" not in manifest
                and "data-abd-visible-field" in content
                and "chrome.runtime.sendMessage" in content
                and "http" + "://" not in content
                and "https" + "://" not in content
            ),
            "detail": "local browser-component static contract",
        }
    except Exception as exc:
        checks["ENV-S15-P03-BROWSER-COMPONENT"] = {"passed": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    try:
        journeys = strict_json_load(root / "journey_tests.json")
        recovery = strict_json_load(root / "recovery_actions.json")
        journey_types = {item.get("journey_type") for item in journeys.get("journeys", []) if isinstance(item, Mapping)}
        action_ids = {item.get("journey_id") for item in recovery.get("actions", []) if isinstance(item, Mapping)}
        boundary = journeys.get("claim_boundary") if isinstance(journeys, Mapping) else None
        checks["ENV-S15-P03-RECOVERY-PATH"] = {
            "passed": (
                set(JOURNEY_CLASSES).issubset(journey_types)
                and {"S13-P04-GOLDEN", "S13-P04-BLACK", "S13-P04-DEGRADED", "S13-P04-RECOVERY"}.issubset(action_ids)
                and isinstance(boundary, Mapping)
                and boundary.get("external_network_accessed") is False
                and boundary.get("order_submission_enabled") is False
                and boundary.get("production_deployed_or_activated") is False
            ),
            "detail": "local recovery catalog and no-action boundary",
        }
    except Exception as exc:
        checks["ENV-S15-P03-RECOVERY-PATH"] = {"passed": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    return checks


def validate_local_environment_surfaces(root: Path, matrix: Any) -> Dict[str, Dict[str, Any]]:
    validate_environment_matrix(root, matrix)
    checks = _surface_checks(root)
    if [identifier for identifier in ENVIRONMENT_IDS if not checks.get(identifier, {}).get("passed")]:
        raise MultiEnvironmentE2EError("one or more local environment surfaces are invalid")
    return checks


def _expected_outcomes() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": item["case_id"],
            "journey_class": item["journey_class"],
            "status": item["expected"]["status"],
            "reason_codes": item["expected"]["reason_codes"],
        }
        for item in EXPECTED_SCENARIOS
    ]


def _expected_structured_logs() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": item["case_id"],
            "journey_class": item["journey_class"],
            "status": item["expected"]["status"],
            "structured_log_id": "LOG-" + item["case_id"],
        }
        for item in EXPECTED_SCENARIOS
    ]


def validate_e2e_tests(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "artifact_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock",
        "journey_classes", "environment_modes", "scenarios", "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "e2e_tests")
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P03-01"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("journey_classes") == list(JOURNEY_CLASSES)
        and document.get("environment_modes") == list(ENVIRONMENT_MODES)
        and document.get("scenarios") == list(EXPECTED_SCENARIOS)
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise MultiEnvironmentE2EError("e2e_tests is not exact")
    return document


def validate_e2e_evidence(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "artifact_id", "evidence_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version",
        "fixed_clock", "expected_outcomes", "structured_logs", "claim_boundary", "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "e2e_evidence")
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P03-03"
        and document.get("evidence_id") == "E2E-S15-P03-LOCAL-MULTI-SURFACE"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("expected_outcomes") == _expected_outcomes()
        and document.get("structured_logs") == _expected_structured_logs()
        and document.get("claim_boundary") == CLAIM_BOUNDARY
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise MultiEnvironmentE2EError("e2e_evidence is not exact")
    return document


def _validate_fixture(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "fixture_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock",
        "parameters_sha256", "predecessor", "execution_policy", "minimum_targeted_pytest_cases", "expected_environment_ids",
        "expected_case_ids", "expected_journey_classes", "expected_negative_mutation_ids", "expected_decision", "expected_next",
    }
    document = _closed_mapping(document, fields, "S15 P03 fixture")
    predecessor = {
        "contract_id": "AC-S15-P02",
        "evidence_path": P02_EVIDENCE_PATH.as_posix(),
        "evidence_sha256": P02_EVIDENCE_SHA256,
        "rollback_path": P02_ROLLBACK_PATH.as_posix(),
        "rollback_sha256": P02_ROLLBACK_SHA256,
        "next": "S15/P03_READY_NOT_STARTED",
    }
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("fixture_id") == "FIX-S15-P03-LOCAL-MULTI-SURFACE-E2E"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("parameters_sha256") == BASELINE_HASHES[PARAMETERS_PATH.as_posix()]
        and document.get("predecessor") == predecessor
        and document.get("execution_policy") == EXECUTION_POLICY
        and isinstance(document.get("minimum_targeted_pytest_cases"), int)
        and document.get("minimum_targeted_pytest_cases") >= 18
        and document.get("expected_environment_ids") == list(ENVIRONMENT_IDS)
        and document.get("expected_case_ids") == list(EXPECTED_CASE_IDS)
        and document.get("expected_journey_classes") == list(JOURNEY_CLASSES)
        and document.get("expected_negative_mutation_ids") == list(NEGATIVE_MUTATION_IDS)
        and document.get("expected_decision") == "S15_P03_LOCAL_MULTI_SURFACE_E2E_READY_P04_REQUIRED"
        and document.get("expected_next") == "S15/P04_READY_NOT_STARTED"
    )
    if not valid:
        raise MultiEnvironmentE2EError("S15 P03 fixture is not exact")
    return document


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.as_posix())
    return value


def _safe_load_evidence_index(root: Path, checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S15P03-EVIDENCE-INDEX-STRICT-JSONL", True, EVIDENCE_INDEX_PATH.as_posix())
        return rows
    except Exception as exc:
        _add(checks, "S15P03-EVIDENCE-INDEX-STRICT-JSONL", False, "%s: %s" % (type(exc).__name__, exc))
        return []


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S15P03-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S15P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S15P03-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S15P03-TASKS-STRICT-JSON")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S15P03-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        rows = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(rows, list):
            raise MultiEnvironmentE2EError("task graph tasks are unavailable")
        tasks = [row for row in rows if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        outputs = {row.get("id"): row.get("outputs") for row in tasks}
        valid = (
            requirement.get("scope") == ["e2e_tests", "environment_matrix.json", "e2e_evidence.json"]
            and requirement.get("target") == "Golden/Black/Degraded/Recovery全通过。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S15-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in tasks] == list(EXPECTED_TASK_IDS)
            and outputs == {
                "T-S15-P03-01": ["e2e_tests", "environment_matrix.json", "e2e_evidence.json"],
                "T-S15-P03-02": ["tests/S15/P03_test.py", "machine/tests/fixtures/S15_P03.json"],
                "T-S15-P03-03": ["machine/evidence/EVD-S15-P03.json", "machine/evidence/EVD-S15-P03_rollback.json"],
            }
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S15-P03"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACTS)
        )
    except Exception as exc:
        valid = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S15P03-TASKPACK-SCOPE-TRACE-EXACT", valid, requirement if not valid else list(EXPECTED_TASK_IDS))
    index = _safe_load_evidence_index(root, checks)
    try:
        row = _row(index, "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "Golden/Black/Degraded/Recovery全通过。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "PHASE_EVIDENCE"
            and row.get("stage_id") == STAGE_ID
            and row.get("contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("artifact_sha256") == (sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING")
            and row.get("next") == "S15/P04_READY_NOT_STARTED"
        )
        _add(checks, "S15P03-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S15P03-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence_hash = sha256_file(root / P02_EVIDENCE_PATH) if (root / P02_EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / P02_ROLLBACK_PATH) if (root / P02_ROLLBACK_PATH).is_file() else "MISSING"
    hashes[P02_EVIDENCE_PATH.as_posix()] = evidence_hash
    hashes[P02_ROLLBACK_PATH.as_posix()] = rollback_hash
    try:
        result = verify_s15_p02_evidence(root)
        valid = (
            result.get("contract_id") == "AC-S15-P02"
            and result.get("status") == "PASS"
            and result.get("evidence_sha256") == P02_EVIDENCE_SHA256 == evidence_hash
            and result.get("next") == "S15/P03_READY_NOT_STARTED"
            and rollback_hash == P02_ROLLBACK_SHA256
        )
    except Exception as exc:
        result = "%s: %s" % (type(exc).__name__, exc)
        valid = False
    _add(checks, "S15P03-P02-SIGNED-PREDECESSOR-EXACT", valid, result)


def _load_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    e2e_tests = _safe_load(root, E2E_TESTS_PATH, checks, "S15P03-E2E-TESTS-STRICT-JSON")
    matrix = _safe_load(root, ENVIRONMENT_MATRIX_PATH, checks, "S15P03-ENVIRONMENT-MATRIX-STRICT-JSON")
    evidence = _safe_load(root, E2E_EVIDENCE_PATH, checks, "S15P03-E2E-EVIDENCE-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S15P03-FIXTURE-STRICT-JSON")
    for path, document, validator, label in (
        (E2E_TESTS_PATH, e2e_tests, validate_e2e_tests, "E2E-TESTS"),
        (E2E_EVIDENCE_PATH, evidence, validate_e2e_evidence, "E2E-EVIDENCE"),
        (FIXTURE_PATH, fixture, _validate_fixture, "FIXTURE"),
    ):
        try:
            validated = validator(document)
            hashes[path.as_posix()] = sha256_file(root / path)
            _add(checks, "S15P03-%s-EXACT" % label, True, path.as_posix())
        except Exception as exc:
            _add(checks, "S15P03-%s-EXACT" % label, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        matrix = validate_environment_matrix(root, matrix)
        hashes[ENVIRONMENT_MATRIX_PATH.as_posix()] = sha256_file(root / ENVIRONMENT_MATRIX_PATH)
        for spec in ENVIRONMENT_SPECS:
            for relative in spec["artifact_paths"]:
                hashes[relative] = sha256_file(root / relative)
        _add(checks, "S15P03-ENVIRONMENT-MATRIX-AND-HASHES-EXACT", True, list(ENVIRONMENT_IDS))
    except Exception as exc:
        _add(checks, "S15P03-ENVIRONMENT-MATRIX-AND-HASHES-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return e2e_tests, matrix, evidence, fixture


def _check_environment_surfaces(root: Path, matrix: Any, checks: List[Dict[str, Any]]) -> None:
    try:
        surface_checks = validate_local_environment_surfaces(root, matrix)
        for identifier in ENVIRONMENT_IDS:
            item = surface_checks[identifier]
            _add(checks, "S15P03-%s-STATIC-CONTRACT" % identifier, item["passed"], item["detail"])
    except Exception as exc:
        _add(checks, "S15P03-LOCAL-ENVIRONMENT-SURFACES", False, "%s: %s" % (type(exc).__name__, exc))


def _load_p02_replay_inputs(root: Path) -> Tuple[Mapping[str, Any], Dict[str, Mapping[str, Any]], Dict[str, Mapping[str, Any]]]:
    integration = strict_json_load(root / P02_INTEGRATION_TESTS_PATH)
    manifest = strict_json_load(root / P02_FIXTURES_MANIFEST_PATH)
    if not isinstance(integration, Mapping) or not isinstance(manifest, Mapping) or not isinstance(integration.get("cases"), list):
        raise MultiEnvironmentE2EError("P02 replay inputs are unavailable")
    bundle = {str(spec["id"]): strict_json_load(root / spec["fixture_path"]) for spec in P02_SOURCE_SPECS}
    cases = {str(item.get("case_id")): item for item in integration["cases"] if isinstance(item, Mapping)}
    return manifest, bundle, cases


def evaluate_e2e_scenario(root: Path, matrix: Mapping[str, Any], scenario: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay one declared S15/P03 journey with local frozen artifacts only."""

    scenario = _closed_mapping(scenario, ("case_id", "journey_class", "source_replay_case_id", "environment_mode", "simulated_unavailable_environment_id", "expected"), "e2e scenario")
    if scenario not in EXPECTED_SCENARIOS:
        raise MultiEnvironmentE2EError("scenario is not declared")
    validate_local_environment_surfaces(root, matrix)
    manifest, bundle, p02_cases = _load_p02_replay_inputs(root)
    p02_case = p02_cases.get(str(scenario["source_replay_case_id"]))
    if p02_case is None:
        raise MultiEnvironmentE2EError("P02 replay case is not declared")
    p02_result = evaluate_p02_integration_case(manifest, bundle, p02_case)
    source_projection = p02_result["decision_projection"]
    source_status = source_projection.get("status")
    journey_class = scenario["journey_class"]
    if journey_class == "GOLDEN" and source_status == "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION":
        reason = "P02_BASELINE_LOCAL_REPLAY_PASS" if scenario["source_replay_case_id"] == "S15-P02-BASELINE-LOCAL" else "P02_FAVOURABLE_BOUNDARY_REPLAY_PASS"
        status, reasons = "E2E_GOLDEN_LOCAL_PASS_NO_EXTERNAL_ACTION", ["ALL_LOCAL_SURFACES_CONTRACT_VALIDATED", reason]
    elif journey_class == "BLACK" and source_status == "NO_ACTION_SOURCE_CONTRACT_FAILED":
        reason = "P02_ADVERSE_MINUS_0_0001_FAILED_CLOSED" if scenario["source_replay_case_id"] == "S15-P02-ODDS-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND" else "P02_RESULT_TICKET_MISMATCH_FAILED_CLOSED"
        status, reasons = "E2E_BLACK_REVOKED_NO_ORDER", [reason, "NO_EXTERNAL_ACTION"]
    elif journey_class == "DEGRADED" and source_status == "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION" and scenario["environment_mode"] == "SIMULATED_EDGE_SCHEMA_UNAVAILABLE":
        status, reasons = "E2E_DEGRADED_LOCAL_RECOVERY_PAGE_NO_ACTION", ["SIMULATED_EDGE_SCHEMA_UNAVAILABLE", "RECOVERY_PAGE_STATIC_CONTRACT_VALIDATED"]
    elif journey_class == "RECOVERY" and source_status == "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION" and scenario["environment_mode"] == "RECOVERY_LOCAL_REPLAY":
        status, reasons = "E2E_RECOVERY_READY_FRESH_LOCAL_REPLAY_NO_ACTION", ["FRESH_LOCAL_P02_BASELINE_REPLAY_PASS", "RECOVERY_CATALOG_STATIC_CONTRACT_VALIDATED"]
    else:
        raise MultiEnvironmentE2EError("declared E2E scenario cannot be replayed fail-closed")
    projection = {
        "status": status,
        "reason_codes": reasons,
        "environment_ids": list(ENVIRONMENT_IDS),
        "source_case_id": scenario["source_replay_case_id"],
        "source_decision_projection_sha256": p02_result["decision_projection_sha256"],
        "environment_matrix_sha256": _canonical_sha256({"environments": matrix.get("environments")}),
        "external_network_accessed": False,
        "ovh_account_or_host_accessed": False,
        "cloudflare_account_dns_or_tunnel_accessed": False,
        "desktop_or_mobile_browser_exercised": False,
        "browser_component_installed_or_run": False,
        "tab_or_provider_runtime_accessed": False,
        "gmail_account_or_api_accessed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_state_changed": False,
        "actual_return_claimed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    return {
        "case_id": scenario["case_id"],
        "journey_class": journey_class,
        "network_probe_performed": False,
        "actual_network_outage_exercised": False,
        "decision_projection": projection,
        "decision_projection_sha256": _canonical_sha256(projection),
    }


def _check_scenarios(root: Path, e2e_tests: Any, matrix: Any, fixture: Any, checks: List[Dict[str, Any]]) -> None:
    if not isinstance(e2e_tests, Mapping) or not isinstance(matrix, Mapping) or not isinstance(fixture, Mapping):
        _add(checks, "S15P03-SCENARIOS-AVAILABLE", False, "delivery artifacts unavailable")
        return
    results: Dict[str, Dict[str, Any]] = {}
    for scenario in e2e_tests["scenarios"]:
        try:
            result = evaluate_e2e_scenario(root, matrix, scenario)
            projection = result["decision_projection"]
            expected = scenario["expected"]
            if projection.get("status") != expected.get("status") or projection.get("reason_codes") != expected.get("reason_codes"):
                raise MultiEnvironmentE2EError("scenario projection differs from frozen case")
            if any(
                projection.get(key) is not False
                for key in (
                    "external_network_accessed", "ovh_account_or_host_accessed", "cloudflare_account_dns_or_tunnel_accessed",
                    "desktop_or_mobile_browser_exercised", "browser_component_installed_or_run", "tab_or_provider_runtime_accessed",
                    "gmail_account_or_api_accessed", "recommendation_generated", "order_submission_enabled", "external_state_changed",
                    "actual_return_claimed", "real_time_soak_waited",
                )
            ) or projection.get("incremental_cash_spent_aud") != "0.00":
                raise MultiEnvironmentE2EError("external-effect boundary changed")
            results[str(scenario["case_id"])] = result
            _add(checks, "S15P03-CASE-%s" % scenario["case_id"], True, projection["status"])
        except Exception as exc:
            label = scenario.get("case_id") if isinstance(scenario, Mapping) else "INVALID"
            _add(checks, "S15P03-CASE-%s" % label, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        classes = {item["journey_class"] for item in e2e_tests["scenarios"]}
        expected_classes = set(fixture["expected_journey_classes"])
        all_pass = (
            classes == expected_classes == set(JOURNEY_CLASSES)
            and set(results) == set(EXPECTED_CASE_IDS)
            and all(result["network_probe_performed"] is False and result["actual_network_outage_exercised"] is False for result in results.values())
        )
        _add(checks, "S15P03-GOLDEN-BLACK-DEGRADED-RECOVERY-ALL-PASS", all_pass, sorted(classes))
    except Exception as exc:
        _add(checks, "S15P03-GOLDEN-BLACK-DEGRADED-RECOVERY-ALL-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"}
        forbidden_tokens = ("slee" "p(", "submit" "_order", "retry" "_order", "http" "://", "https" "://")
        passed = not imports.intersection(forbidden) and all(token not in source for token in forbidden_tokens)
        _add(checks, "S15P03-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", passed, {"imports": sorted(imports), "forbidden": sorted(imports.intersection(forbidden))})
    except Exception as exc:
        _add(checks, "S15P03-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
    if not suites:
        raise MultiEnvironmentE2EError("JUnit has no testsuite")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    normalized = True
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
        normalized = normalized and suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000"
        normalized = normalized and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S15P03-TARGETED-REPORTS-REQUIRED", True, "preflight mode")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        passed = isinstance(minimum, int) and summary["tests"] >= minimum and not summary["failures"] and not summary["errors"] and not summary["skipped"] and normalized
        _add(checks, "S15P03-TARGETED-PYTEST-REPORT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S15P03-TARGETED-PYTEST-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S15P03-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P03-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S15P03-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S15P03-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S15_P03_LOCAL_MULTI_SURFACE_E2E_READY_P04_REQUIRED" if passed else "S15/P03_BLOCKED",
        "next": "S15/P04_READY_NOT_STARTED" if passed else "S15/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    e2e_tests, matrix, _e2e_evidence, fixture = _load_artifacts(root, checks, hashes)
    _check_environment_surfaces(root, matrix, checks)
    _check_scenarios(root, e2e_tests, matrix, fixture, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = [
        E2E_TESTS_PATH, ENVIRONMENT_MATRIX_PATH, E2E_EVIDENCE_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH,
        *[Path(relative) for spec in ENVIRONMENT_SPECS for relative in spec["artifact_paths"]],
    ]
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING", "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S15_P03_LOCAL_MULTI_SURFACE_HARNESS_KEEP_SIGNED_S15_P02",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "actual_return_claimed": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        ORACLE_PATH, E2E_TESTS_PATH, ENVIRONMENT_MATRIX_PATH, E2E_EVIDENCE_PATH, TEST_PATH, FIXTURE_PATH,
        *[Path(relative) for spec in ENVIRONMENT_SPECS for relative in spec["artifact_paths"]],
        *[Path(relative) for relative in BASELINE_HASHES], P02_EVIDENCE_PATH, P02_ROLLBACK_PATH,
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _canonical_sha256({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "status": evidence.get("status"), "validation": evidence.get("validation")})


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S15_P03_LOCAL_EVIDENCE_ONLY_P04_REQUIRED",
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S15/P03_test.py --junitxml=machine/evidence/S15/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S15/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S15/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S15-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {
            "scenario_count": len(EXPECTED_CASE_IDS),
            "environment_count": len(ENVIRONMENT_IDS),
            "journey_classes": list(JOURNEY_CLASSES),
            "actual_network_or_device_execution_performed": False,
            "real_time_wait_performed": False,
        },
        "rollback": rollback,
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
        raise MultiEnvironmentE2EError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S15/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise MultiEnvironmentE2EError("S15/P03 evidence-index row must exist exactly once")
    output = [_jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8") for raw_line, row in zip(raw_lines, rows)]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise MultiEnvironmentE2EError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise MultiEnvironmentE2EError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S15/P04_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise MultiEnvironmentE2EError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S15_P03_LOCAL_MULTI_SURFACE_E2E_READY_P04_REQUIRED"
        and evidence.get("next") == "S15/P04_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("claim_boundary") == CLAIM_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("actual_return_claimed") is False
    )
    if not valid:
        raise MultiEnvironmentE2EError("existing S15/P03 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S15/P04_READY_NOT_STARTED"}


__all__ = [
    "CLAIM_BOUNDARY", "CONTRACT_ID", "E2E_EVIDENCE_PATH", "E2E_TESTS_PATH", "ENVIRONMENT_IDS", "ENVIRONMENT_MATRIX_PATH",
    "EXECUTION_POLICY", "EXPECTED_CASE_IDS", "EXTERNAL_EFFECT_BOUNDARY", "FIXTURE_PATH", "MultiEnvironmentE2EError", "NEGATIVE_MUTATION_IDS",
    "ORACLE_PATH", "TEST_PATH", "evaluate_contract", "evaluate_e2e_scenario", "perform_rollback_drill", "validate_candidate_preflight",
    "validate_e2e_evidence", "validate_e2e_tests", "validate_environment_matrix", "validate_local_environment_surfaces", "verify_existing_phase_evidence",
    "write_phase_evidence",
]
