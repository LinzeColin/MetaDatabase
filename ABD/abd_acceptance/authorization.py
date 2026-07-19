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


CONTRACT_ID = "AC-S00-P02"
REQUIREMENT_ID = "REQ-S00-P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
PINNED_CANONICAL_SHA256 = "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385"
PINNED_GOAL_SHA256 = "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5"

AUTHORIZATION_PATH = Path("machine/facts/authorization_matrix.json")
DEFAULTS_PATH = Path("machine/facts/default_decisions.json")
PAUSE_SCHEMA_PATH = Path("machine/schemas/pause_receipt_schema.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S00-P01.json")
JUNIT_PATH = Path("machine/evidence/S00/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S00/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S00_P02.json")

PINNED_HASHES = {
    AUTHORIZATION_PATH.as_posix(): "f7cf34a3d60e37365c3090fac75f40e0b390ec211976393e7148d597a2f4affe",
    DEFAULTS_PATH.as_posix(): "1315982e4f0d3a62c50cc11e716645b7951fc86dde53e7f1e356cae62920d20f",
    PAUSE_SCHEMA_PATH.as_posix(): "c937d999977cceaa31ac2a44981b4a2f91df247fdc4c22d05ca15fbd4406e9cb",
}

PAUSE_CODES = (
    "LEGAL_REGULATORY_SOURCE_CONFLICT",
    "SECURITY_OR_SUPPLY_CHAIN_INCIDENT",
    "ACTUAL_LEDGER_RECONCILIATION_FAILURE",
    "IRREVERSIBLE_OPERATION",
    "INCREMENTAL_CASH_BUDGET_EXCEEDED",
    "OUT_OF_AUTHORIZED_SCOPE",
    "TERMINATION_CONDITION_TRIGGERED",
)

PROHIBITED_ACTIONS = {
    "REAL_ORDER_SUBMISSION",
    "REAL_ORDER_CONFIRMATION_OR_RETRY",
    "PERMANENT_EMAIL_DELETE",
    "PAID_DEPENDENCY_PURCHASE",
    "AUTHORIZATION_SCOPE_EXPANSION",
    "IMMUTABLE_FACT_OR_LEDGER_DELETE_OR_REWRITE",
}

REQUIRED_DEFAULT_CONDITIONS = {
    "AUTHORIZATION_UNKNOWN_OR_MISSING",
    "EXTERNAL_CAPABILITY_OR_CREDENTIAL_UNVERIFIED",
    "OPTIONAL_GMAIL_CONSENT_MISSING",
    "STAGE_REVIEW_INCOMPLETE_OR_FINDINGS_OPEN",
    "ODDS_THRESHOLD_TIME_OR_PROBABILITY_UNFAVORABLE_BY_0_0001",
    "MONTHLY_TARGET_SHORTFALL",
    "NORMAL_REVERSIBLE_ZERO_COST_TASK_READY",
}

ACTION_FIELDS = {
    "id",
    "name_zh",
    "effect",
    "external_state_change",
    "reversibility",
    "authorization",
    "capability_status",
    "cash_cost_aud",
    "preconditions",
    "evidence_required",
    "on_precondition_failure",
    "auto_advance_after_success",
}

DEFAULT_FIELDS = {
    "id",
    "condition_code",
    "decision",
    "blocks_task_graph",
    "owner_input_required",
    "auto_continue_independent_ready_tasks",
}


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _portable(path: Path) -> str:
    rendered = path.as_posix()
    for marker in ("/machine/", "/abd_acceptance/", "/tests/"):
        if marker in rendered:
            return marker.strip("/").split("/")[0] + "/" + rendered.split(marker, 1)[1]
    return path.name


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


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
            if element.attrib.get("timestamp") != FIXED_CLOCK:
                return False
            if element.attrib.get("time") != "0.000":
                return False
        if element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _single_source_check(root: Path, expected: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(expected.name)
        if ".git" not in path.parts and ".venv" not in path.parts and "__pycache__" not in path.parts
    )
    _add(checks, "SOURCE-SINGLE-%s" % expected.stem.upper(), candidates == [expected.as_posix()], candidates)


def _load_evidence_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / "machine/evidence/evidence_index.jsonl")
        .read_text(encoding="utf-8-sig")
        .splitlines()
        if line
    ]


def _check_p01_prerequisite(root: Path, checks: List[Dict[str, Any]]) -> None:
    p01 = _safe_load(root / P01_EVIDENCE_PATH, checks, "PREREQ-P01-EVIDENCE-PARSE")
    if not isinstance(p01, dict):
        _add(checks, "PREREQ-P01-PASS", False, "P01 evidence unavailable")
        return
    try:
        rows = _load_evidence_index(root)
    except Exception as exc:
        _add(checks, "PREREQ-P01-PASS", False, "evidence index: %s: %s" % (type(exc).__name__, exc))
        return
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S00-P01"]
    actual_hash = sha256_file(root / P01_EVIDENCE_PATH)
    index_ok = (
        len(matching) == 1
        and matching[0].get("status") == "PASS"
        and matching[0].get("artifact_sha256") == actual_hash
    )
    p01_ok = (
        p01.get("status") == "PASS"
        and p01.get("contract_id") == "AC-S00-P01"
        and p01.get("next") == "S00/P02_READY_NOT_STARTED"
        and index_ok
    )
    _add(
        checks,
        "PREREQ-P01-PASS",
        p01_ok,
        {
            "status": p01.get("status"),
            "next": p01.get("next"),
            "index_hash_matches": index_ok,
        },
    )


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, Any]) -> None:
    for relative, expected in PINNED_HASHES.items():
        path = root / relative
        try:
            actual = sha256_file(path)
        except Exception as exc:
            _add(checks, "HASH-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "HASH-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_pause_reasons(
    canonical: Mapping[str, Any], matrix: Mapping[str, Any], checks: List[Dict[str, Any]]
) -> None:
    try:
        reasons = matrix["global_pause_reasons"]
        codes = [reason["code"] for reason in reasons]
        texts = [reason["canonical_text"] for reason in reasons]
        canonical_texts = canonical["authorization"]["pause_only_on"]
        ok = (
            tuple(codes) == PAUSE_CODES
            and len(codes) == len(set(codes))
            and texts == canonical_texts
            and matrix["global_pause_reason_codes_apply_to_all_actions"] is True
        )
        _add(
            checks,
            "AUTH-PAUSE-REASONS-EXACT",
            ok,
            {"codes": codes, "canonical_text_match": texts == canonical_texts},
        )
    except (KeyError, TypeError) as exc:
        _add(checks, "AUTH-PAUSE-REASONS-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_actions(matrix: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    actions = matrix.get("actions")
    if not isinstance(actions, list):
        _add(checks, "AUTH-ACTIONS-STRUCTURE", False, "actions is not an array")
        return

    object_actions = [action for action in actions if isinstance(action, dict)]
    ids = [action.get("id") for action in object_actions]
    field_errors = [
        action.get("id", "UNKNOWN") for action in object_actions if not ACTION_FIELDS.issubset(action)
    ]
    structure_ok = len(object_actions) == len(actions) and len(ids) == len(set(ids)) and not field_errors
    _add(
        checks,
        "AUTH-ACTIONS-STRUCTURE",
        structure_ok,
        {"count": len(actions), "unique_ids": len(set(ids)), "field_errors": field_errors},
    )

    by_id = {action["id"]: action for action in object_actions if "id" in action}
    prohibited_errors = [
        action_id
        for action_id in sorted(PROHIBITED_ACTIONS)
        if action_id not in by_id
        or by_id[action_id].get("authorization") != "PROHIBITED"
        or by_id[action_id].get("auto_advance_after_success") is not False
    ]
    _add(checks, "AUTH-PROHIBITIONS", not prohibited_errors, prohibited_errors or sorted(PROHIBITED_ACTIONS))

    active_authorizations = {"PREAUTHORIZED", "CONDITIONALLY_PREAUTHORIZED", "OPTIONAL_OWNER_CONSENT"}
    allowed_authorizations = active_authorizations | {"PROHIBITED", "PAUSE_REQUIRED"}
    execution_errors: List[Dict[str, Any]] = []
    for action in object_actions:
        authorization = action.get("authorization")
        if authorization not in allowed_authorizations:
            execution_errors.append({"id": action.get("id"), "reason": "unknown_authorization"})
        if authorization in active_authorizations:
            if action.get("cash_cost_aud") != "0.00":
                execution_errors.append({"id": action.get("id"), "reason": "nonzero_or_unknown_cash"})
            if not action.get("evidence_required"):
                execution_errors.append({"id": action.get("id"), "reason": "missing_evidence"})
            if "EXECUTE" in str(action.get("on_precondition_failure", "")):
                execution_errors.append({"id": action.get("id"), "reason": "failure_executes"})
        if action.get("external_state_change") and authorization == "PREAUTHORIZED":
            execution_errors.append({"id": action.get("id"), "reason": "unconditional_external_write"})
        if str(action.get("capability_status", "")).startswith("VERIFIED"):
            execution_errors.append({"id": action.get("id"), "reason": "capability_claimed_verified"})
    _add(checks, "AUTH-ACTIVE-ACTIONS-SAFE", not execution_errors, execution_errors or "all safe")

    deployment_requirements = {
        "OVH_REVERSIBLE_DEPLOY": {
            "CAPABILITY_VERIFIED",
            "ACCEPTANCE_GATES_PASSED",
            "ROLLBACK_VERIFIED",
            "NO_INCREMENTAL_CASH_COST",
        },
        "CLOUDFLARE_REVERSIBLE_DEPLOY": {
            "CAPABILITY_VERIFIED",
            "ACCEPTANCE_GATES_PASSED",
            "ROLLBACK_VERIFIED",
            "NO_INCREMENTAL_CASH_COST",
        },
        "GITHUB_STAGE_UPLOAD": {
            "ALL_STAGE_PHASES_PASS",
            "WHOLE_STAGE_REVIEW_PASS",
            "ALL_REVIEW_FINDINGS_RESOLVED",
            "FULL_STAGE_REGRESSION_PASS",
            "SECRET_SCAN_PASS",
            "CLEAN_WORKTREE",
        },
    }
    deployment_errors = []
    for action_id, required in deployment_requirements.items():
        action = by_id.get(action_id, {})
        missing = sorted(required - set(action.get("preconditions", [])))
        if action.get("authorization") != "CONDITIONALLY_PREAUTHORIZED" or missing:
            deployment_errors.append({"id": action_id, "missing": missing})
    _add(checks, "AUTH-EXTERNAL-GATES", not deployment_errors, deployment_errors or "all required gates")

    gmail = by_id.get("GMAIL_OAUTH_CONSENT", {})
    gmail_ok = (
        gmail.get("authorization") == "OPTIONAL_OWNER_CONSENT"
        and gmail.get("auto_advance_after_success") is False
        and gmail.get("on_precondition_failure") == "DISABLE_GMAIL_MODULE_CONTINUE_CORE"
    )
    _add(checks, "AUTH-GMAIL-NONBLOCKING", gmail_ok, gmail)


def _check_defaults(defaults: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    rows = defaults.get("defaults")
    if not isinstance(rows, list):
        _add(checks, "DEFAULTS-STRUCTURE", False, "defaults is not an array")
        return
    object_rows = [row for row in rows if isinstance(row, dict)]
    ids = [row.get("id") for row in object_rows]
    conditions = [row.get("condition_code") for row in object_rows]
    field_errors = [row.get("id", "UNKNOWN") for row in object_rows if not DEFAULT_FIELDS.issubset(row)]
    structure_ok = (
        len(object_rows) == len(rows)
        and len(ids) == len(set(ids))
        and len(conditions) == len(set(conditions))
        and not field_errors
    )
    _add(
        checks,
        "DEFAULTS-STRUCTURE",
        structure_ok,
        {"count": len(rows), "unique_conditions": len(set(conditions)), "field_errors": field_errors},
    )

    coverage_missing = sorted(REQUIRED_DEFAULT_CONDITIONS - set(conditions))
    _add(checks, "DEFAULTS-REQUIRED-COVERAGE", not coverage_missing, coverage_missing or sorted(REQUIRED_DEFAULT_CONDITIONS))

    pause_errors = []
    execution_errors = []
    explicit_pause_codes = set()
    for row in object_rows:
        if row.get("blocks_task_graph"):
            code = row.get("pause_reason_code")
            source = row.get("pause_reason_source")
            if code in PAUSE_CODES:
                explicit_pause_codes.add(code)
            if code not in PAUSE_CODES and source != "authorization_matrix.global_pause_reasons":
                pause_errors.append(row.get("condition_code"))
            if row.get("owner_input_required") is not True:
                pause_errors.append(row.get("condition_code"))
        else:
            if row.get("owner_input_required") is not False:
                pause_errors.append(row.get("condition_code"))
        if "UNKNOWN" in str(row.get("condition_code")) and "EXECUTE" in str(row.get("decision")):
            execution_errors.append(row.get("condition_code"))
        if "EXECUTE" in str(row.get("decision")) and row.get("condition_code") != "NORMAL_REVERSIBLE_ZERO_COST_TASK_READY":
            execution_errors.append(row.get("condition_code"))
    missing_pause_defaults = sorted(set(PAUSE_CODES) - explicit_pause_codes)
    if missing_pause_defaults:
        pause_errors.append({"missing_pause_defaults": missing_pause_defaults})
    _add(checks, "DEFAULTS-ONLY-EXPLICIT-PAUSE-BLOCKS", not pause_errors, pause_errors or "all blocking rows mapped")
    _add(checks, "DEFAULTS-UNKNOWN-NEVER-EXECUTES", not execution_errors, execution_errors or "safe")

    by_condition = {row.get("condition_code"): row for row in object_rows}
    boundary_ok = by_condition.get(
        "ODDS_THRESHOLD_TIME_OR_PROBABILITY_UNFAVORABLE_BY_0_0001", {}
    ).get("decision") == "NO_RECOMMENDATION"
    target_ok = "WITHOUT_RELAXING_ANY_GATE" in by_condition.get("MONTHLY_TARGET_SHORTFALL", {}).get("decision", "")
    stage_ok = "KEEP_STAGE_COMMITS_LOCAL" in by_condition.get("STAGE_REVIEW_INCOMPLETE_OR_FINDINGS_OPEN", {}).get("decision", "")
    _add(
        checks,
        "DEFAULTS-HARD-BOUNDARIES",
        boundary_ok and target_ok and stage_ok,
        {"adverse_0_0001": boundary_ok, "target_no_relax": target_ok, "stage_local": stage_ok},
    )


def _check_pause_schema(
    schema: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]
) -> None:
    try:
        required = set(schema["required"])
        canonical_fields = {
            "minimal_decision_question",
            "evidence",
            "default_recommendation",
            "no_decision_consequence",
        }
        enum_codes = tuple(schema["properties"]["pause_reason_code"]["enum"])
        structural_ok = (
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
            and schema.get("type") == "object"
            and schema.get("additionalProperties") is False
            and canonical_fields.issubset(required)
            and enum_codes == PAUSE_CODES
            and schema["properties"]["incremental_cash_cost_aud"].get("const") == "0.00"
            and schema["properties"]["secret_material_present"].get("const") is False
        )
        _add(checks, "PAUSE-SCHEMA-STRUCTURE", structural_ok, {"required": sorted(required), "codes": list(enum_codes)})
    except (KeyError, TypeError) as exc:
        _add(checks, "PAUSE-SCHEMA-STRUCTURE", False, "%s: %s" % (type(exc).__name__, exc))
        return

    try:
        import jsonschema

        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        errors = sorted(validator.iter_errors(fixture["valid_pause_receipt"]), key=lambda error: list(error.path))
        _add(checks, "PAUSE-SCHEMA-VALID-FIXTURE", not errors, [error.message for error in errors] or "valid")
    except Exception as exc:
        _add(checks, "PAUSE-SCHEMA-VALID-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_no_sensitive_or_local_data(
    artifacts: Sequence[Mapping[str, Any]], checks: List[Dict[str, Any]]
) -> None:
    rendered = json.dumps(list(artifacts), ensure_ascii=False, sort_keys=True)
    patterns = {
        "absolute_user_path": r"/" + r"Users/",
        "private_key": r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        "github_token": r"ghp_[0-9A-Za-z]{20,}",
        "google_api_key": r"AIza[0-9A-Za-z_-]{20,}",
    }
    matches = [name for name, pattern in patterns.items() if re.search(pattern, rendered)]
    _add(checks, "SECURITY-NO-SECRET-OR-LOCAL-PATH", not matches, matches or "none")


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "AUTHORIZATION_AND_DEFAULTS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "release_status": "NOT_READY",
        "stage_status": "S00_IN_PROGRESS",
        "next": "S00/P03_READY_NOT_STARTED" if status == "PASS" else "S00/P03_BLOCKED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, Any] = {}

    _check_p01_prerequisite(root, checks)
    for expected in (AUTHORIZATION_PATH, DEFAULTS_PATH, PAUSE_SCHEMA_PATH):
        _single_source_check(root, expected, checks)

    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "INPUT-CANONICAL-PARSE")
    matrix = _safe_load(root / AUTHORIZATION_PATH, checks, "INPUT-AUTHORIZATION-PARSE")
    defaults = _safe_load(root / DEFAULTS_PATH, checks, "INPUT-DEFAULTS-PARSE")
    schema = _safe_load(root / PAUSE_SCHEMA_PATH, checks, "INPUT-PAUSE-SCHEMA-PARSE")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "INPUT-FIXTURE-PARSE")
    _check_pinned_hashes(root, checks, hashes)

    if not all(isinstance(value, dict) for value in (canonical, matrix, defaults, schema, fixture)):
        _add(checks, "INPUTS-ALL-OBJECTS", False, "one or more P02 inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "INPUTS-ALL-OBJECTS", True, "all parsed")

    version_ok = matrix.get("product_version") == defaults.get("product_version") == VERSION
    _add(checks, "AUTH-VERSION", version_ok, {"matrix": matrix.get("product_version"), "defaults": defaults.get("product_version")})

    semantics = matrix.get("semantics", {})
    semantics_ok = (
        semantics.get("authorization_is_not_capability") is True
        and semantics.get("authorization_is_not_release_readiness") is True
        and semantics.get("authorization_is_not_evidence_of_external_access") is True
        and semantics.get("unknown_authorization_default") == "DENY_OR_DEGRADE"
        and semantics.get("cash_budget_boundary_aud") == "0.00"
    )
    _add(checks, "AUTH-SEMANTICS", semantics_ok, semantics)

    try:
        canonical_hash = sha256_file(root / "machine/facts/canonical_facts.json")
        goal_hash = sha256_file(root / "PURSUE_GOAL_PROMPT.txt")
        sources = matrix["authority_sources"]
        source_hashes_ok = (
            canonical_hash == PINNED_CANONICAL_SHA256
            and sources.get("canonical_facts_sha256") == canonical_hash
            and goal_hash == PINNED_GOAL_SHA256
            and sources.get("current_user_goal_sha256") == goal_hash
        )
        _add(
            checks,
            "AUTH-AUTHORITY-SOURCE-HASHES",
            source_hashes_ok,
            {
                "canonical_expected": PINNED_CANONICAL_SHA256,
                "canonical_actual": canonical_hash,
                "goal_expected": PINNED_GOAL_SHA256,
                "goal_actual": goal_hash,
            },
        )
    except (KeyError, TypeError, OSError) as exc:
        _add(checks, "AUTH-AUTHORITY-SOURCE-HASHES", False, "%s: %s" % (type(exc).__name__, exc))

    _check_pause_reasons(canonical, matrix, checks)
    _check_actions(matrix, checks)
    _check_defaults(defaults, checks)
    _check_pause_schema(schema, fixture, checks)
    _check_no_sensitive_or_local_data((matrix, defaults, schema), checks)

    try:
        invariants_ok = (
            canonical["scope"]["order_submission_module_present"] is False
            and canonical["email"]["permanent_delete"] is False
            and matrix.get("invariants", {}).get("risk_evidence_numeric_source_gates_may_not_relax") is True
            and defaults.get("invariants", {}).get("only_explicit_pause_reasons_block") is True
        )
        _add(checks, "AUTH-CANONICAL-INVARIANTS", invariants_ok, "order/delete/risk/pause gates")
    except (KeyError, TypeError) as exc:
        _add(checks, "AUTH-CANONICAL-INVARIANTS", False, "%s: %s" % (type(exc).__name__, exc))

    if require_external_reports:
        for check_id, path, minimum in (
            ("TEST-P02-JUNIT-PASS", JUNIT_PATH, 18),
            ("TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, 30),
        ):
            try:
                summary = _junit_summary(root / path)
                normalized = _junit_is_normalized(root / path)
                ok = (
                    summary["tests"] >= minimum
                    and summary["failures"] == 0
                    and summary["errors"] == 0
                    and normalized
                )
                _add(checks, check_id, ok, {**summary, "normalized": normalized})
                hashes[path.as_posix()] = sha256_file(root / path)
            except Exception as exc:
                _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

        report = _safe_load(root / PACK_REPORT_PATH, checks, "PACK-REPORT-PARSE")
        report_ok = isinstance(report, dict) and report.get("status") == "PASS"
        _add(checks, "PACK-VALIDATION-PASS", report_ok, report.get("status") if isinstance(report, dict) else "unavailable")
        if (root / PACK_REPORT_PATH).is_file():
            hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)

    return _build_result(checks, hashes)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    restored: Dict[str, Dict[str, str]] = {}
    status = "PASS"
    with tempfile.TemporaryDirectory(prefix="abd-s00-p02-rollback-") as directory:
        temp = Path(directory)
        for relative in (AUTHORIZATION_PATH, DEFAULTS_PATH, PAUSE_SCHEMA_PATH):
            source = root / relative
            signed = temp / (relative.name + ".signed")
            active = temp / relative.name
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            expected = sha256_file(signed)
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored_hash = sha256_file(active)
            item_ok = corrupted != expected and restored_hash == expected
            if not item_ok:
                status = "FAIL"
            restored[relative.as_posix()] = {
                "signed_sha256": expected,
                "corrupted_sha256": corrupted,
                "restored_sha256": restored_hash,
                "status": "PASS" if item_ok else "FAIL",
            }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_POLICY_RESTORE",
        "status": status,
        "artifacts": restored,
        "production_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        P01_EVIDENCE_PATH,
        Path("machine/facts/canonical_facts.json"),
        AUTHORIZATION_PATH,
        DEFAULTS_PATH,
        PAUSE_SCHEMA_PATH,
        FIXTURE_PATH,
        Path("machine/facts/parameters.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
    ]
    return {
        path.as_posix(): sha256_file(root / path) if (root / path).is_file() else "MISSING"
        for path in paths
    }


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S00-P02-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
        }
    if rollback["status"] != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["next"] = "S00/P03_BLOCKED"

    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "task_ids": ["T-S00-P02-01", "T-S00-P02-02", "T-S00-P02-03"],
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "pass_gate": "只有明确暂停条件可以阻止自动推进。",
        "validation": result,
        "hashes": {
            "inputs": _input_hashes(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "code": _code_hash(root),
            "model": None,
            "model_not_applicable_reason": "S00/P02 freezes authorization and defaults and has no model artifact.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
                "result_source": PACK_REPORT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q tests/S00/P02_test.py --junitxml=machine/evidence/S00/P02/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P02/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S00/P02/full_regression.xml",
                "result_source": FULL_JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P02/full_regression.xml",
                "result_source": FULL_JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S00-P02 --evidence machine/evidence",
                "exit_code": 0 if result["status"] == "PASS" else 1,
            },
        ],
        "rollback": {
            "artifact": "machine/evidence/EVD-S00-P02_rollback.json",
            "status": rollback["status"],
        },
        "authorization_boundary": {
            "authorization_is_not_capability": True,
            "authorization_is_not_release_readiness": True,
            "external_capability_verified_in_this_phase": False,
            "external_write_performed_in_this_phase": False,
            "real_order_capability": "PROHIBITED",
        },
        "explicit_unknowns": [
            "OVH, Cloudflare, GitHub, Gmail and provider credentials or runtime capability were not inspected in S00/P02.",
            "No external deployment, account change, email action, real order or cash spend occurred.",
            "P03 zero-budget dependency proof and P04 external-consent degraded-mode implementation remain unrun."
        ],
        "release_status": "NOT_READY",
        "stage_status": "S00_IN_PROGRESS",
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
    path = root / "machine/evidence/evidence_index.jsonl"
    rows = _load_evidence_index(root)
    matches = 0
    for row in rows:
        if row.get("id") == "INDEX-AC-S00-P02":
            matches += 1
            row["status"] = status
            row["actual_artifact"] = "machine/evidence/EVD-S00-P02.json"
            row["artifact_sha256"] = evidence_hash
            row["verified_at"] = FIXED_CLOCK
            row["next"] = "S00/P03_READY_NOT_STARTED" if status == "PASS" else "S00/P03_BLOCKED"
    if matches != 1:
        raise ValueError("expected exactly one INDEX-AC-S00-P02 row, found %d" % matches)
    payload = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
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
    rollback_path = evidence_dir / "EVD-S00-P02_rollback.json"
    evidence_path = evidence_dir / "EVD-S00-P02.json"
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
