from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple
from urllib.parse import urlparse

from .canonical_facts import DuplicateKeyError, sha256_file, strict_json_load


CONTRACT_ID = "AC-S00-P04"
REQUIREMENT_ID = "REQ-S00-P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

PREREQUISITES_PATH = Path("machine/facts/decision_prerequisites.json")
DEGRADED_PATH = Path("machine/facts/degraded_mode_contract.json")
RUNBOOK_PATH = Path("machine/runbooks/gmail_oauth_bootstrap.md")
FIXTURE_PATH = Path("machine/tests/fixtures/S00_P04.json")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S00-P03.json")
JUNIT_PATH = Path("machine/evidence/S00/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S00/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
FORBIDDEN_MAIL_SCOPE = "https://mail.google.com/"

PINNED_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/authorization_matrix.json": "f7cf34a3d60e37365c3090fac75f40e0b390ec211976393e7148d597a2f4affe",
    "machine/facts/default_decisions.json": "1315982e4f0d3a62c50cc11e716645b7951fc86dde53e7f1e356cae62920d20f",
    P03_EVIDENCE_PATH.as_posix(): "ad9ee08e80f60dcadfa86b84a646c4fcfdbcebbb5217fcf03699ec7fbef62870",
    PREREQUISITES_PATH.as_posix(): "e9b54b985aff11faceaa7a2d6e6db42e070c96c0a8286a348ff767bc62921ccc",
    DEGRADED_PATH.as_posix(): "823a92ee03a468aaa1df6a4706aa0f1af3472b7f9c96c530877578f2f072d02f",
    RUNBOOK_PATH.as_posix(): "5588ed4e484349c96609258c37e526e1cd606c84f78ae89d3eb6cbe6bb618ae2",
    FIXTURE_PATH.as_posix(): "8c1ffb0a1d4670501fb79f5e10aaa7030c408f4b8e828ede8aae778d77ee9742",
}

OFFICIAL_HOSTS = {
    "developers.google.com",
    "support.google.com",
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


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


def _strict_json_text(value: str) -> Any:
    def no_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise DuplicateKeyError("duplicate JSON key: %s" % key)
            result[key] = item
        return result

    return json.loads(value, object_pairs_hook=no_duplicates)


def parse_runbook_contract(text: str) -> Mapping[str, Any]:
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if len(blocks) != 1:
        raise ValueError("runbook must contain exactly one JSON contract block")
    value = _strict_json_text(blocks[0])
    if not isinstance(value, dict):
        raise ValueError("runbook contract must be a JSON object")
    return value


def _single_source_check(root: Path, expected: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(expected.name)
        if not {".git", ".venv", "__pycache__"}.intersection(path.parts)
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


def _check_p03_prerequisite(root: Path, checks: List[Dict[str, Any]]) -> None:
    p03 = _safe_load(root / P03_EVIDENCE_PATH, checks, "PREREQ-P03-EVIDENCE-PARSE")
    if not isinstance(p03, dict):
        _add(checks, "PREREQ-P03-PASS", False, "P03 evidence unavailable")
        return
    try:
        rows = _load_evidence_index(root)
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S00-P03"]
        actual_hash = sha256_file(root / P03_EVIDENCE_PATH)
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == actual_hash
        )
    except Exception as exc:
        _add(checks, "PREREQ-P03-PASS", False, "evidence index: %s: %s" % (type(exc).__name__, exc))
        return
    ok = (
        p03.get("status") == "PASS"
        and p03.get("contract_id") == "AC-S00-P03"
        and p03.get("next") == "S00/P04_READY_NOT_STARTED"
        and actual_hash == PINNED_HASHES[P03_EVIDENCE_PATH.as_posix()]
        and index_ok
    )
    _add(
        checks,
        "PREREQ-P03-PASS",
        ok,
        {
            "status": p03.get("status"),
            "next": p03.get("next"),
            "artifact_hash_matches": actual_hash == PINNED_HASHES[P03_EVIDENCE_PATH.as_posix()],
            "index_hash_matches": index_ok,
        },
    )


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
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


def resolve_consent_event(
    contract: Mapping[str, Any],
    event: str,
    proven_gate_ids: Iterable[str],
) -> Dict[str, Any]:
    resolutions = {
        row.get("event"): row.get("state")
        for row in contract.get("event_resolution", [])
        if isinstance(row, dict)
    }
    state_id = resolutions.get(event, resolutions.get("UNKNOWN_EVENT", "CONSENT_NOT_REQUESTED"))
    required_gates = {
        gate.get("id")
        for gate in contract.get("activation_gates", [])
        if isinstance(gate, dict) and gate.get("id")
    }
    provided = set(proven_gate_ids)
    if state_id == "ACTIVE" and provided != required_gates:
        state_id = "CONSENT_GRANTED_UNVERIFIED"
    states = {
        row.get("id"): row
        for row in contract.get("states", [])
        if isinstance(row, dict) and row.get("id")
    }
    state = states.get(state_id) or states.get("CONSENT_NOT_REQUESTED")
    if not isinstance(state, dict):
        return {
            "id": "CONSENT_NOT_REQUESTED",
            "gmail_enabled": False,
            "gmail_external_calls_allowed": False,
            "core_task_graph": "CONTINUE_SUBJECT_TO_INDEPENDENT_GATES",
            "owner_prompt": "NONE",
            "evidence_status": "GMAIL_NOT_CONNECTED",
        }
    return dict(state)


def validate_consent_receipt(contract: Mapping[str, Any], receipt: Mapping[str, Any]) -> List[str]:
    receipt_contract = contract.get("consent_receipt_contract", {})
    required = set(receipt_contract.get("required_fields", []))
    forbidden = set(receipt_contract.get("forbidden_fields", []))
    errors = []
    missing = sorted(required - set(receipt))
    present_forbidden = sorted(forbidden.intersection(receipt))
    if missing:
        errors.append("missing:%s" % ",".join(missing))
    if present_forbidden:
        errors.append("forbidden:%s" % ",".join(present_forbidden))
    if receipt.get("secret_material_present") is not False:
        errors.append("secret_material_present")
    authorization_status = receipt.get("authorization_status")
    if authorization_status not in {"NOT_REQUESTED", "PENDING", "DENIED", "GRANTED"}:
        errors.append("authorization_status_invalid")
    scopes = receipt.get("granted_scopes")
    if not isinstance(scopes, list):
        errors.append("granted_scopes_not_array")
    elif scopes and scopes != [GMAIL_SCOPE]:
        errors.append("scope_not_exact")
    elif scopes and authorization_status != "GRANTED":
        errors.append("scope_without_grant")
    for field in ("state_validated", "pkce_validated", "redirect_uri_validated", "external_capability_verified"):
        if not isinstance(receipt.get(field), bool):
            errors.append("%s_not_boolean" % field)
    if receipt.get("external_capability_verified") is True and authorization_status != "GRANTED":
        errors.append("capability_without_grant")
    module_state = receipt.get("gmail_module_state")
    if module_state not in {"DISABLED", "ACTIVE"}:
        errors.append("gmail_module_state_invalid")
    if module_state == "ACTIVE":
        active_requirements = (
            receipt.get("external_capability_verified") is True,
            authorization_status == "GRANTED",
            scopes == [GMAIL_SCOPE],
            receipt.get("state_validated") is True,
            receipt.get("pkce_validated") is True,
            receipt.get("redirect_uri_validated") is True,
            receipt.get("token_storage_status") == "VERIFIED_ENCRYPTED",
            str(receipt.get("oauth_app_status", "")).startswith("VERIFIED"),
        )
        if not all(active_requirements):
            errors.append("active_without_all_receipt_gates")
    rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    sensitive_patterns = [
        r"/" + r"Users/",
        r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        r"ya29\.[0-9A-Za-z_-]+",
        r"1//[0-9A-Za-z_-]+",
    ]
    if any(re.search(pattern, rendered) for pattern in sensitive_patterns):
        errors.append("sensitive_value_pattern")
    return errors


def _check_canonical_and_p02(
    canonical: Mapping[str, Any],
    authorization: Mapping[str, Any],
    defaults: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        email = canonical["email"]
        canonical_ok = (
            email["gmail_scope_required"] == "gmail.modify"
            and email["one_time_human_consent_required"] is True
            and email["one_time_consent_blocks_core_product"] is False
            and email["permanent_delete"] is False
        )
        _add(checks, "CONSENT-CANONICAL-ALIGNMENT", canonical_ok, email)
    except (KeyError, TypeError) as exc:
        _add(checks, "CONSENT-CANONICAL-ALIGNMENT", False, "%s: %s" % (type(exc).__name__, exc))

    actions = authorization.get("actions", [])
    gmail_actions = [row for row in actions if isinstance(row, dict) and row.get("id") == "GMAIL_OAUTH_CONSENT"]
    gmail = gmail_actions[0] if len(gmail_actions) == 1 else {}
    auth_ok = (
        len(gmail_actions) == 1
        and gmail.get("authorization") == "OPTIONAL_OWNER_CONSENT"
        and gmail.get("capability_status") == "UNVERIFIED_UNTIL_OWNER_CONSENTS"
        and gmail.get("cash_cost_aud") == "0.00"
        and gmail.get("on_precondition_failure") == "DISABLE_GMAIL_MODULE_CONTINUE_CORE"
        and gmail.get("auto_advance_after_success") is False
        and set(gmail.get("evidence_required", []))
        == {"CONSENT_RESULT_WITHOUT_TOKEN", "SCOPE", "REVOCATION_TEST"}
    )
    _add(checks, "CONSENT-P02-AUTHORIZATION-ALIGNMENT", auth_ok, gmail)

    rows = defaults.get("defaults", [])
    gmail_defaults = [
        row for row in rows if isinstance(row, dict) and row.get("condition_code") == "OPTIONAL_GMAIL_CONSENT_MISSING"
    ]
    default = gmail_defaults[0] if len(gmail_defaults) == 1 else {}
    default_ok = (
        len(gmail_defaults) == 1
        and default.get("decision") == "DISABLE_GMAIL_MODULE_CONTINUE_CORE"
        and default.get("blocks_task_graph") is False
        and default.get("owner_input_required") is False
        and default.get("auto_continue_independent_ready_tasks") is True
    )
    _add(checks, "CONSENT-P02-DEFAULT-ALIGNMENT", default_ok, default)


def _check_prerequisites(
    prerequisites: Mapping[str, Any],
    degraded: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    semantics = prerequisites.get("semantics", {})
    observation = prerequisites.get("current_phase_observation", {})
    semantics_ok = (
        semantics.get("authorization_is_not_capability") is True
        and semantics.get("capability_is_not_readiness") is True
        and semantics.get("consent_receipt_is_not_token") is True
        and semantics.get("phase_acceptance_is_not_external_consent") is True
        and semantics.get("one_time_means_normal_owner_action_not_permanent_token_validity") is True
        and semantics.get("current_owner_action_required") is False
    )
    observation_ok = (
        observation.get("gmail_authorization_status") == "NOT_REQUESTED"
        and observation.get("gmail_capability_status") == "UNVERIFIED"
        and observation.get("gmail_readiness_status") == "NOT_READY"
        and observation.get("gmail_module_enabled") is False
        and observation.get("gmail_external_api_call_performed") is False
        and observation.get("oauth_link_generated") is False
        and observation.get("token_received_or_stored") is False
        and observation.get("owner_consent_claimed") is False
    )
    _add(checks, "CONSENT-SEMANTICS-AND-CURRENT-OBSERVATION", semantics_ok and observation_ok, {"semantics": semantics, "observation": observation})

    items = prerequisites.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        _add(checks, "CONSENT-PREREQUISITES-STRUCTURE", False, "items must be an array of objects")
        return
    ids = [item.get("id") for item in items]
    expected_ids = fixture.get("required_decision_prerequisite_ids", [])
    structure_ok = len(ids) == len(set(ids)) and sorted(ids) == sorted(expected_ids)
    _add(checks, "CONSENT-PREREQUISITES-STRUCTURE", structure_ok, {"actual": ids, "expected": expected_ids})

    by_id = {item["id"]: item for item in items if item.get("id")}
    gmail = by_id.get("DP-004", {})
    gmail_ok = (
        gmail.get("authorization_status") == "NOT_REQUESTED_OPTIONAL_OWNER_CONSENT"
        and gmail.get("capability_status") == "UNVERIFIED"
        and gmail.get("readiness_status") == "NOT_READY"
        and gmail.get("module_enabled") is False
        and gmail.get("blocking_for_current_core_task_graph") is False
        and gmail.get("current_human_action") == "NONE"
        and gmail.get("requested_scope_exact") == GMAIL_SCOPE
        and gmail.get("forbidden_scope") == FORBIDDEN_MAIL_SCOPE
        and gmail.get("incremental_cash_cost_aud") == "0.00"
        and gmail.get("fallback") == "DISABLE_GMAIL_MODULE_CONTINUE_CORE"
        and str(gmail.get("owner_reprompt_policy", "")).startswith("NEVER_AUTOMATIC")
    )
    _add(checks, "CONSENT-GMAIL-PREREQUISITE-FAIL-CLOSED", gmail_ok, gmail)

    capability_errors = []
    for item in items:
        capability = str(item.get("capability_status", ""))
        if capability.startswith("VERIFIED") or item.get("current_human_action") != "NONE":
            capability_errors.append(item.get("id"))
    _add(checks, "CONSENT-NO-EXTERNAL-CAPABILITY-OR-ACTION-CLAIM", not capability_errors, capability_errors or "none")

    impact = prerequisites.get("gmail_missing_consent_impact", {})
    components = degraded.get("components", {})
    impact_ok = (
        impact.get("core_task_graph") == "CONTINUE_SUBJECT_TO_INDEPENDENT_GATES"
        and impact.get("owner_prompt_policy") == "NO_PROMPT_UNTIL_GMAIL_MODULE_AND_SECURE_TOKEN_STORAGE_ARE_READY"
        and impact.get("release_claim") == "GMAIL_NOT_CONNECTED"
        and impact.get("disabled_components") == components.get("gmail_only")
        and impact.get("unaffected_components") == components.get("safe_core")
        and "STAGE_REVIEW" in (impact.get("unaffected_components") or [])
    )
    _add(checks, "CONSENT-DEGRADED-IMPACT-CROSS-SOURCE", impact_ok, impact)


def _check_degraded_contract(
    degraded: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    invariants = degraded.get("invariants", {})
    required_invariants = {
        "gmail_enabled_only_in_active_state",
        "ordinary_missing_or_invalid_consent_disables_only_gmail",
        "ordinary_degraded_state_never_blocks_core_task_graph",
        "unexpected_scope_never_expands_authority",
        "unknown_state_fails_to_gmail_disabled",
        "no_automatic_owner_reprompt",
        "no_permanent_delete_capability_requested",
        "security_incident_uses_p02_explicit_pause_contract",
    }
    invariant_ok = required_invariants.issubset(invariants) and all(invariants[key] is True for key in required_invariants)
    _add(checks, "DEGRADED-INVARIANTS", invariant_ok, invariants)

    scope = degraded.get("scope_policy", {})
    methods = degraded.get("method_policy", {})
    allowed = methods.get("allowed_when_active", [])
    denied = methods.get("always_denied", [])
    method_ok = (
        scope.get("requested_scopes_exact") == [GMAIL_SCOPE]
        and scope.get("forbidden_scopes") == [FORBIDDEN_MAIL_SCOPE]
        and scope.get("returned_scope_rule") == "EXACT_SET_MATCH_ONLY"
        and scope.get("scope_classification") == "RESTRICTED"
        and "users.messages.trash" in allowed
        and "users.messages.untrash" in allowed
        and "users.messages.delete" in denied
        and "users.messages.send" in denied
        and "users.messages.batchDelete" in denied
        and not set(allowed).intersection(denied)
        and str(methods.get("unknown_method_action", "")).startswith("DENY_")
    )
    _add(checks, "DEGRADED-SCOPE-AND-METHOD-BOUNDARY", method_ok, {"scope": scope, "methods": methods})

    gates = degraded.get("activation_gates", [])
    if not isinstance(gates, list):
        gates = []
    gate_ids = [gate.get("id") for gate in gates if isinstance(gate, dict)]
    gate_ok = (
        len(gates) == 9
        and len(gate_ids) == len(set(gate_ids))
        and all(gate.get("current_status") != "PROVEN" for gate in gates if isinstance(gate, dict))
    )
    _add(checks, "DEGRADED-ACTIVATION-GATES-CURRENTLY-UNPROVEN", gate_ok, {"gate_ids": gate_ids, "statuses": [gate.get("current_status") for gate in gates if isinstance(gate, dict)]})

    states = degraded.get("states")
    if not isinstance(states, list) or not all(isinstance(state, dict) for state in states):
        _add(checks, "DEGRADED-STATES-STRUCTURE", False, "states must be an array of objects")
        return
    state_ids = [state.get("id") for state in states]
    states_by_id = {state["id"]: state for state in states if state.get("id")}
    expected_state_ids = set(fixture.get("required_ordinary_degraded_states", [])) | {"ACTIVE", "SECURITY_ISOLATED"}
    structure_ok = (
        len(state_ids) == len(set(state_ids))
        and set(state_ids) == expected_state_ids
        and degraded.get("current_state") == "CONSENT_NOT_REQUESTED"
        and degraded.get("current_state") in states_by_id
    )
    _add(checks, "DEGRADED-STATES-STRUCTURE", structure_ok, state_ids)

    ordinary = degraded.get("ordinary_degraded_states", [])
    expected_ordinary = fixture.get("required_ordinary_degraded_states", [])
    ordinary_errors = []
    if ordinary != expected_ordinary:
        ordinary_errors.append({"actual": ordinary, "expected": expected_ordinary})
    for state_id in ordinary:
        state = states_by_id.get(state_id, {})
        if (
            state.get("gmail_enabled") is not False
            or state.get("gmail_external_calls_allowed") is not False
            or state.get("core_task_graph") != "CONTINUE_SUBJECT_TO_INDEPENDENT_GATES"
        ):
            ordinary_errors.append(state_id)
    _add(checks, "DEGRADED-ORDINARY-STATES-DISABLE-ONLY-GMAIL", not ordinary_errors, ordinary_errors or ordinary)

    active = states_by_id.get("ACTIVE", {})
    security = states_by_id.get("SECURITY_ISOLATED", {})
    special_ok = (
        active.get("gmail_enabled") is True
        and active.get("gmail_external_calls_allowed") is True
        and active.get("evidence_status") == "ALL_ACTIVATION_GATES_PROVEN"
        and security.get("gmail_enabled") is False
        and security.get("core_task_graph") == "PAUSE_AFFECTED_SCOPE_PER_P02_SECURITY_OR_SUPPLY_CHAIN_INCIDENT"
    )
    _add(checks, "DEGRADED-ACTIVE-AND-SECURITY-EXCEPTION", special_ok, {"active": active, "security": security})

    activation = degraded.get("activation_rule", {})
    activation_ok = (
        activation.get("all_activation_gates_must_be_proven") is True
        and activation.get("receipt_alone_never_activates") is True
        and activation.get("active_without_all_gates_action")
        == "FORCE_CONSENT_GRANTED_UNVERIFIED_DISABLE_GMAIL"
        and activation.get("testing_refresh_token_expiry_must_be_handled") is True
        and activation.get("revocation_event_disables_before_next_gmail_operation") is True
    )
    _add(checks, "DEGRADED-ACTIVATION-RULE", activation_ok, activation)

    receipt_contract = degraded.get("consent_receipt_contract", {})
    required_receipt_fields = {
        "schema_version",
        "receipt_id",
        "observed_at",
        "authorization_status",
        "granted_scopes",
        "state_validated",
        "pkce_validated",
        "redirect_uri_validated",
        "token_storage_status",
        "oauth_app_status",
        "secret_material_present",
        "external_capability_verified",
        "gmail_module_state",
    }
    forbidden_receipt_fields = {
        "authorization_code",
        "access_token",
        "refresh_token",
        "client_secret",
        "token_value",
        "email_address",
        "account_id",
        "authorization_url",
    }
    receipt_contract_ok = (
        set(receipt_contract.get("required_fields", [])) == required_receipt_fields
        and set(receipt_contract.get("forbidden_fields", [])) == forbidden_receipt_fields
        and receipt_contract.get("secret_material_present_must_equal") is False
        and receipt_contract.get("granted_scopes_rule")
        == "EMPTY_UNLESS_OBSERVED_THEN_EXACT_GMAIL_MODIFY_ONLY"
        and receipt_contract.get("receipt_is_capability_proof_only_after_live_verification") is True
    )
    _add(checks, "DEGRADED-RECEIPT-CONTRACT", receipt_contract_ok, receipt_contract)

    events = degraded.get("event_resolution", [])
    event_names = [row.get("event") for row in events if isinstance(row, dict)]
    event_states = [row.get("state") for row in events if isinstance(row, dict)]
    events_ok = (
        len(events) == len(event_names) == len(set(event_names))
        and "UNKNOWN_EVENT" in event_names
        and all(state in states_by_id for state in event_states)
    )
    _add(checks, "DEGRADED-EVENT-RESOLUTION", events_ok, event_names)

    scenario_errors = []
    for case in fixture.get("scenario_cases", []):
        state = resolve_consent_event(degraded, case.get("event", ""), case.get("proven_gate_ids", []))
        if (
            state.get("id") != case.get("expected_state")
            or state.get("gmail_enabled") is not case.get("expected_gmail_enabled")
            or state.get("core_task_graph") != case.get("expected_core_task_graph")
        ):
            scenario_errors.append({"id": case.get("id"), "actual": state})
    _add(checks, "DEGRADED-SCENARIO-ORACLE", not scenario_errors, scenario_errors or {"cases": len(fixture.get("scenario_cases", []))})

    transitions = degraded.get("allowed_transitions", [])
    if not isinstance(transitions, list) or not all(isinstance(item, str) for item in transitions):
        transitions = []
    transition_ok = (
        len(transitions) == len(set(transitions))
        and "CONSENT_PENDING->ACTIVE" not in transitions
        and "CONSENT_GRANTED_UNVERIFIED->ACTIVE" in transitions
        and "ACTIVE->TOKEN_INVALID_OR_REVOKED" in transitions
    )
    _add(checks, "DEGRADED-TRANSITIONS-NO-DIRECT-ACTIVATION", transition_ok, transitions)

    execution = degraded.get("s00_p04_execution_boundary", {})
    execution_ok = (
        all(execution.get(key) is False for key in (
            "external_product_or_account_network_access",
            "oauth_link_generated",
            "owner_consent_requested",
            "token_received_or_stored",
            "gmail_api_called",
            "email_moved_or_deleted",
        ))
        and execution.get("current_result") == "CONTRACT_PROVEN_GMAIL_REMAINS_DISABLED"
    )
    _add(checks, "DEGRADED-NO-EXTERNAL-EFFECT-IN-P04", execution_ok, execution)

    receipt = fixture.get("valid_nonsecret_receipt", {})
    receipt_errors = validate_consent_receipt(degraded, receipt) if isinstance(receipt, dict) else ["fixture_not_object"]
    _add(checks, "DEGRADED-CONSENT-RECEIPT-NONSECRET", not receipt_errors, receipt_errors or "valid")


def _check_runbook(
    text: str,
    degraded: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        contract = parse_runbook_contract(text)
    except Exception as exc:
        _add(checks, "RUNBOOK-MACHINE-CONTRACT-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    _add(checks, "RUNBOOK-MACHINE-CONTRACT-PARSE", True, RUNBOOK_PATH.as_posix())

    scope = degraded.get("scope_policy", {})
    methods = degraded.get("method_policy", {})
    cross_ok = (
        contract.get("runbook_contract_id") == "ABD-GMAIL-OAUTH-BOOTSTRAP-S00-P04"
        and contract.get("current_state") == degraded.get("current_state")
        and contract.get("requested_scopes_exact") == scope.get("requested_scopes_exact")
        and contract.get("forbidden_scopes") == scope.get("forbidden_scopes")
        and contract.get("allowed_methods") == methods.get("allowed_when_active")
        and contract.get("always_denied_methods") == methods.get("always_denied")
        and contract.get("degraded_action") == "DISABLE_GMAIL_MODULE_CONTINUE_CORE"
        and contract.get("secret_material_in_runbook") is False
        and contract.get("external_action_performed_in_s00_p04") is False
    )
    _add(checks, "RUNBOOK-CROSS-SOURCE-CONTRACT", cross_ok, contract)

    params = contract.get("request_parameters", {})
    params_ok = (
        params.get("access_type") == "offline"
        and params.get("include_granted_scopes") is False
        and params.get("prompt") == "CONSENT_ONLY_FOR_INITIAL_OR_OWNER_EXPLICIT_REENABLE"
        and params.get("response_type") == "code"
        and params.get("state") == "REQUIRED_SINGLE_USE_SERVER_SIDE"
        and params.get("pkce") == "S256_REQUIRED"
        and params.get("redirect_uri") == "EXACT_HTTPS_OWNER_CONTROLLED_URI"
    )
    _add(checks, "RUNBOOK-OAUTH-REQUEST-SAFETY", params_ok, params)

    content_requirements = {
        "scope_risk": "可读取、撰写和发送" in text,
        "testing_expiry": "7 天失效" in text,
        "system_browser": "不得使用内嵌浏览器" in text,
        "no_real_link": "未生成授权链接" in text,
        "stage_review_next": "下一步是 Stage 0 整体复审" in text,
        "revoke_delay": "传播延迟" in text,
    }
    missing = sorted(key for key, value in content_requirements.items() if not value)
    _add(checks, "RUNBOOK-RISK-AND-STOP-DISCLOSURE", not missing, missing or sorted(content_requirements))


def _check_official_sources(
    prerequisites: Mapping[str, Any],
    degraded: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    rows = list(prerequisites.get("official_source_snapshot", [])) + list(degraded.get("official_source_snapshot", []))
    errors = []
    if not rows:
        errors.append("no sources")
    for row in rows:
        if not isinstance(row, dict):
            errors.append("non-object source")
            continue
        host = urlparse(str(row.get("url", ""))).hostname
        if host not in OFFICIAL_HOSTS:
            errors.append({"url": row.get("url"), "host": host})
        if row.get("retrieved_at") != "2026-07-19":
            errors.append({"url": row.get("url"), "reason": "retrieval_date"})
    _add(checks, "CONSENT-OFFICIAL-SOURCE-SNAPSHOT", not errors, errors or {"rows": len(rows)})


def _check_no_sensitive_or_local_data(artifacts: Sequence[Any], checks: List[Dict[str, Any]]) -> None:
    rendered = json.dumps(list(artifacts), ensure_ascii=False, sort_keys=True)
    patterns = {
        "absolute_user_path": r"/" + r"Users/",
        "private_key": r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        "access_token": r"ya29\.[0-9A-Za-z_-]+",
        "refresh_token": r"1//[0-9A-Za-z_-]+",
        "github_token": r"ghp_[0-9A-Za-z]{20,}",
        "google_api_key": r"AIza[0-9A-Za-z_-]{20,}",
    }
    matches = [name for name, pattern in patterns.items() if re.search(pattern, rendered)]
    _add(checks, "SECURITY-NO-SECRET-OR-LOCAL-PATH", not matches, matches or "none")


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


def _check_runtime_reports(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for check_id, path, minimum in [
        ("TEST-P04-JUNIT-PASS", JUNIT_PATH, 30),
        ("TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, 100),
    ]:
        try:
            summary = _junit_summary(root / path)
            normalized = _junit_is_normalized(root / path)
            ok = (
                summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and normalized
            )
            _add(checks, check_id, ok, {**summary, "normalized": normalized, "minimum": minimum})
            hashes[path.as_posix()] = sha256_file(root / path)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    report = _safe_load(root / PACK_REPORT_PATH, checks, "PACK-REPORT-PARSE")
    report_ok = isinstance(report, dict) and report.get("status") == "PASS"
    _add(checks, "PACK-VALIDATION-PASS", report_ok, report.get("status") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)


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
        "decision": "OPTIONAL_EXTERNAL_CONSENT_DEGRADED_MODE_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "gmail_connection_status": "NOT_CONNECTED",
        "external_capability_status": "UNVERIFIED",
        "release_status": "NOT_READY",
        "stage_status": "S00_PHASES_COMPLETE_REVIEW_PENDING" if status == "PASS" else "S00_IN_PROGRESS_BLOCKED",
        "next": "S00/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S00/STAGE_REVIEW_BLOCKED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}

    _check_p03_prerequisite(root, checks)
    for expected in (PREREQUISITES_PATH, DEGRADED_PATH, RUNBOOK_PATH):
        _single_source_check(root, expected, checks)

    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "INPUT-CANONICAL-PARSE")
    authorization = _safe_load(root / "machine/facts/authorization_matrix.json", checks, "INPUT-AUTHORIZATION-PARSE")
    defaults = _safe_load(root / "machine/facts/default_decisions.json", checks, "INPUT-DEFAULTS-PARSE")
    prerequisites = _safe_load(root / PREREQUISITES_PATH, checks, "INPUT-PREREQUISITES-PARSE")
    degraded = _safe_load(root / DEGRADED_PATH, checks, "INPUT-DEGRADED-PARSE")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "INPUT-FIXTURE-PARSE")
    try:
        runbook_text = (root / RUNBOOK_PATH).read_text(encoding="utf-8")
        _add(checks, "INPUT-RUNBOOK-READ", True, RUNBOOK_PATH.as_posix())
    except Exception as exc:
        runbook_text = ""
        _add(checks, "INPUT-RUNBOOK-READ", False, "%s: %s" % (type(exc).__name__, exc))
    _check_pinned_hashes(root, checks, hashes)

    objects = (canonical, authorization, defaults, prerequisites, degraded, fixture)
    if not all(isinstance(value, dict) for value in objects):
        _add(checks, "INPUTS-ALL-OBJECTS", False, "one or more required JSON inputs are unavailable")
        return _build_result(checks, hashes)
    _add(checks, "INPUTS-ALL-OBJECTS", True, "all parsed")

    version_ok = (
        prerequisites.get("version") == VERSION
        and prerequisites.get("phase") == "S00/P04"
        and degraded.get("product_version") == VERSION
        and degraded.get("acceptance_contract_id") == CONTRACT_ID
        and fixture.get("contract_id") == CONTRACT_ID
    )
    _add(checks, "CONSENT-VERSION-AND-PHASE", version_ok, {"prerequisites": prerequisites.get("version"), "degraded": degraded.get("product_version")})

    _check_canonical_and_p02(canonical, authorization, defaults, checks)
    _check_prerequisites(prerequisites, degraded, fixture, checks)
    _check_degraded_contract(degraded, fixture, checks)
    _check_runbook(runbook_text, degraded, checks)
    _check_official_sources(prerequisites, degraded, checks)
    _check_no_sensitive_or_local_data([prerequisites, degraded, fixture, runbook_text], checks)
    if require_external_reports:
        _check_runtime_reports(root, checks, hashes)
    return _build_result(checks, hashes)


def _code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    artifacts = (PREREQUISITES_PATH, DEGRADED_PATH, RUNBOOK_PATH)
    results: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s00-p04-rollback-") as directory:
        directory_path = Path(directory)
        for index, relative in enumerate(artifacts):
            source = root / relative
            expected_hash = sha256_file(source)
            signed = directory_path / ("signed-%d" % index)
            active = directory_path / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted_hash = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored_hash = sha256_file(active)
            item_status = "PASS" if corrupted_hash != expected_hash and restored_hash == expected_hash else "FAIL"
            results[relative.as_posix()] = {
                "status": item_status,
                "signed_sha256": expected_hash,
                "corrupted_sha256": corrupted_hash,
                "restored_sha256": restored_hash,
            }
    status = "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_EXTERNAL_CONSENT_CONTRACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/authorization_matrix.json"),
        Path("machine/facts/default_decisions.json"),
        P03_EVIDENCE_PATH,
        PREREQUISITES_PATH,
        DEGRADED_PATH,
        RUNBOOK_PATH,
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
            "evidence_id": "EVD-S00-P04-ROLLBACK",
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
        result["stage_status"] = "S00_IN_PROGRESS_BLOCKED"
        result["next"] = "S00/STAGE_REVIEW_BLOCKED"

    rollback_bytes = _json_bytes(rollback)
    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "task_ids": ["T-S00-P04-01", "T-S00-P04-02", "T-S00-P04-03"],
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "pass_gate": "未授权时仅邮件自动化关闭，其他任务全部继续。",
        "validation": result,
        "gmail_boundary": {
            "authorization_status": "NOT_REQUESTED",
            "capability_status": "UNVERIFIED",
            "readiness_status": "NOT_READY",
            "module_enabled": False,
            "core_task_graph": "CONTINUE_SUBJECT_TO_INDEPENDENT_GATES",
            "owner_action_performed": False,
            "oauth_link_generated": False,
            "token_received_or_stored": False,
            "gmail_api_called": False,
            "email_moved_or_deleted": False,
        },
        "stage_phase_completion": {
            "completed_phase_ids": ["P01", "P02", "P03", "P04"],
            "phase_count": 4,
            "stage_review_status": "NOT_STARTED",
            "stage_upload_status": "NOT_STARTED",
            "stage_pass_claimed": False,
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes.get("machine/facts/parameters.json", "MISSING"),
            "code": _code_hash(root),
            "model": None,
            "model_not_applicable_reason": "S00/P04 freezes external consent and degraded-mode contracts and has no model artifact.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
                "result_source": PACK_REPORT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q tests/S00/P04_test.py --junitxml=machine/evidence/S00/P04/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P04/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S00/P04/full_regression.xml",
                "result_source": FULL_JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P04/full_regression.xml",
                "result_source": FULL_JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S00-P04 --evidence machine/evidence",
                "exit_code": 0 if result["status"] == "PASS" else 1,
            },
        ],
        "rollback": {
            "artifact": "machine/evidence/EVD-S00-P04_rollback.json",
            "status": rollback.get("status"),
        },
        "non_guarantee": "A$300*1.3^n remains an unverified falsifiable target, never a random-return guarantee.",
        "explicit_unknowns": [
            "No Google Cloud project, OAuth client, consent screen, audience, publishing status, verification or administrator policy was inspected.",
            "No Gmail authorization link was generated and no owner consent was requested or claimed.",
            "No authorization code, access token, refresh token, client credential, email address or account identifier entered evidence.",
            "The Gmail module remains unimplemented or inactive and all external Gmail capability is unverified.",
            "All S00 phases have phase evidence, but the required whole-stage review, remediation and GitHub upload remain unrun.",
        ],
        "release_status": "NOT_READY",
        "stage_status": result["stage_status"],
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
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    matches = 0
    for row in rows:
        if row.get("id") == "INDEX-AC-S00-P04":
            matches += 1
            row["status"] = status
            row["actual_artifact"] = "machine/evidence/EVD-S00-P04.json"
            row["artifact_sha256"] = evidence_hash
            row["verified_at"] = FIXED_CLOCK
            row["next"] = "S00/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S00/STAGE_REVIEW_BLOCKED"
    if matches != 1:
        raise ValueError("expected exactly one INDEX-AC-S00-P04 row, found %d" % matches)
    data = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
    )
    _atomic_write(path, data)


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence directory must be inside the ABD project root") from exc

    evidence, rollback = build_evidence(root, require_external_reports=True)
    rollback_path = evidence_dir / "EVD-S00-P04_rollback.json"
    evidence_path = evidence_dir / "EVD-S00-P04.json"
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
