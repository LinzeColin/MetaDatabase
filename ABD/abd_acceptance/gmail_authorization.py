"""Independent, deterministic acceptance oracle for ABD S06/P01.

The oracle proves only offline contracts.  It never opens an OAuth page, calls
Gmail, persists a real token, changes a mailbox, starts a daemon, or waits for
real-time observation.  Missing consent or token storage keeps Gmail disabled
while independent core work may continue.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .gmail_oauth_core import (
    AGE_HEADER,
    ALLOWED_GMAIL_METHODS,
    DENIED_GMAIL_METHODS,
    GMAIL_SCOPE,
    REAL_TIME_SOAK_REQUIRED,
    AgeProcessResult,
    CursorIntegrityError,
    GmailOAuthContractError,
    TokenStorageError,
    advance_cursor,
    archive_idempotency_key,
    build_authorization_request,
    build_gmail_list_query,
    empty_cursor,
    encrypt_token_bytes,
    validate_cursor,
    validate_gmail_method,
    validate_no_real_time_soak,
    validate_oauth_callback,
    validate_query_rule,
    validate_query_rules_document,
)

from .canonical_facts import DuplicateKeyError, sha256_file, strict_json_load
from .external_consent import evaluate_contract as evaluate_external_consent_contract
from .stage4_delivery import verify_stage4_delivery
from .stage5_delivery import RECEIPT_PATH as S05_DELIVERY_RECEIPT_PATH
from .stage5_delivery import verify_stage5_delivery


CONTRACT_ID = "AC-S06-P01"
REQUIREMENT_ID = "REQ-S06-P01"
STAGE_ID = "S06"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

GMAIL_OAUTH_PATH = Path("gmail_oauth.py")
GMAIL_OAUTH_CORE_PATH = Path("abd_acceptance/gmail_oauth_core.py")
QUERY_RULES_PATH = Path("mail_query_rules.json")
TOKEN_STORAGE_PATH = Path("token_storage.md")
FIXTURE_PATH = Path("machine/tests/fixtures/S06_P01.json")
TEST_PATH = Path("tests/S06/P01_test.py")
ORACLE_PATH = Path("abd_acceptance/gmail_authorization.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S06/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S06/P01/full_regression.xml")

PINNED_PHASE_HASHES: Mapping[str, str] = {
    "gmail_oauth.py": "bad4bf44ed1b8e57ac01f7ed0ea82e6c941a06151a476d8c191db087cf6341ff",
    "abd_acceptance/gmail_oauth_core.py": "5b1aab411b66e039cc36f380ea77e6e023d7bd9dbdd8c54b9d63d15d228c3a45",
    "mail_query_rules.json": "fa3592ab8231e2c2313fa6e2c631676163ba6f22f0852eb99ccd4e14224c44e9",
    "token_storage.md": "4a7a86035e30bd27072b89ce49b746f5f3de218101b55d7ef9443aee72c07fa0",
    "machine/tests/fixtures/S06_P01.json": "aa3dcb7d5d5fd678b217fb786e64cf206e2438646fd08c9b796910aaf74097fb",
    "tests/S06/P01_test.py": "a33b87fdbbbb9b8d62e92d1fa7a3d87605b7d40b6ea181b5cee30533a699fa4d",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Mapping[str, str] = {}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "b2b98e4151a453d4b7fc2c9af848713185a8922a77aef0f32cd58eb390f30511"

ROLLBACK_ARTIFACTS = (GMAIL_OAUTH_PATH, GMAIL_OAUTH_CORE_PATH, QUERY_RULES_PATH, TOKEN_STORAGE_PATH)

EXTERNAL_EFFECT_BOUNDARY = {
    "github_predecessor_delivery_receipt_read": True,
    "gmail_account_or_api_accessed": False,
    "token_or_client_secret_stored": False,
    "gmail_mutation_performed": False,
    "production_query_enabled": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "real_order_submitted_or_retried": False,
    "financial_return_verified_or_guaranteed": False,
    "core_deployment_waits_for_real_time_soak": False,
}

TOKEN_STORAGE_CONTRACT = {
    "contract_id": "ABD-GMAIL-TOKEN-STORAGE-S06-P01",
    "schema_version": "1.0.0",
    "backend": "AGE_CLI",
    "ciphertext_format": "age-encryption.org/v1",
    "age_binary": "ABSOLUTE_TRUSTED_HOST_PATH_OUTSIDE_REPOSITORY",
    "recipient": "RUNTIME_PUBLIC_RECIPIENT_OUTSIDE_REPOSITORY",
    "identity": "HOST_SECRET_OUTSIDE_REPOSITORY",
    "token_path": "OUTSIDE_REPOSITORY_RUNTIME_SECRET_PATH_WITH_AGE_SUFFIX",
    "required_file_mode": "0600",
    "repository_token_write": "PROHIBITED",
    "private_database_raw_token_write": "PROHIBITED",
    "ephemeral_state_and_pkce": "SERVER_SIDE_SINGLE_USE_MEMORY_ONLY",
    "encryption_failure_action": "DISABLE_GMAIL_CONTINUE_CORE",
    "real_time_soak_required": False,
    "core_deployment_wait_behavior": "NONE_GMAIL_REMAINS_DISABLED_UNTIL_IMMEDIATE_GATES_PASS",
    "runtime_claim": "IMPLEMENTED_INTERFACE_NOT_RUNTIME_TOKEN_PROOF",
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
    # Evidence is portable and public-safe: check IDs identify the contract,
    # while details must never serialize a machine-specific absolute path.
    _add(checks, check_id, True, path.name)
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


def parse_token_storage_contract(text: str) -> Mapping[str, Any]:
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if len(blocks) != 1:
        raise ValueError("token storage document must contain exactly one JSON contract block")
    value = _strict_json_text(blocks[0])
    if not isinstance(value, Mapping):
        raise ValueError("token storage contract must be an object")
    return value


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ValueError("expected one row for %s" % identifier)
    return matches[0]


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[0-9a-f]{64}("\n)',
        r"\1<SELF-HASH>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8"))


def _phase_artifact_hashes(root: Path) -> Dict[str, str]:
    return {relative: sha256_file(root / relative) for relative in PINNED_PHASE_HASHES}


def _current_code_hash(root: Path) -> str:
    payload = b""
    for relative in (GMAIL_OAUTH_PATH, GMAIL_OAUTH_CORE_PATH, ORACLE_PATH):
        payload += relative.as_posix().encode("utf-8") + b"\0" + (root / relative).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _fake_age_runner(arguments: Sequence[str], input_bytes: bytes) -> AgeProcessResult:
    if len(arguments) != 3 or arguments[1] != "-r" or not input_bytes:
        return AgeProcessResult(returncode=1, stdout=b"")
    return AgeProcessResult(
        returncode=0,
        stdout=AGE_HEADER + b"-> X25519 synthetic recipient\n--- synthetic encrypted payload\n",
    )


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            allowed = {expected}
            if relative in SUCCESSOR_UNIT_PROFILE_HASHES:
                allowed.add(SUCCESSOR_UNIT_PROFILE_HASHES[relative])
            _add(
                checks,
                "S06P01-PIN-%s" % Path(relative).name.upper().replace(".", "-"),
                actual in allowed,
                {"expected": sorted(allowed), "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S06P01-PIN-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S06P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S06P01-CONTRACTS-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S06P01-TRACEABILITY-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S06P01-TASK-GRAPH-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S06P01-ROADMAP-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [row for row in task_graph.get("tasks", []) if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        stage = _row(roadmap.get("stages"), STAGE_ID)
        expected_outputs = [GMAIL_OAUTH_PATH.as_posix(), QUERY_RULES_PATH.as_posix(), TOKEN_STORAGE_PATH.as_posix()]
        expected_task_ids = ["T-S06-P01-01", "T-S06-P01-02", "T-S06-P01-03"]
        expected_test_ids = ["TEST-S06-P01", "TEST-S06-P01-BOUNDARY", "TEST-S06-P01-REPLAY"]
        phase = _row(stage.get("phases"), PHASE_ID)
        ok = (
            requirement.get("stage_id") == STAGE_ID
            and requirement.get("phase_id") == PHASE_ID
            and requirement.get("scope") == expected_outputs
            and requirement.get("target") == "无授权不阻塞核心；有授权后重复扫描不重复归档。"
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S06-P01 --evidence machine/evidence"
            and [row.get("id") for row in contract.get("tests", [])] == expected_test_ids
            and [row.get("id") for row in tasks] == expected_task_ids
            and tasks[0].get("outputs") == expected_outputs
            and tasks[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks)
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == expected_task_ids
            and trace.get("test_ids") == expected_test_ids
            and trace.get("evidence_id") == "EVD-S06-P01"
            and stage.get("depends_on") == ["S04"]
            and phase.get("outputs") == expected_outputs
        )
        _add(checks, "S06P01-TASKPACK-TRACE-EXACT", ok, {"tasks": [row.get("id") for row in tasks], "phase": phase.get("id")})
    except Exception as exc:
        _add(checks, "S06P01-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    consent = evaluate_external_consent_contract(root, require_external_reports=False)
    _add(
        checks,
        "S06P01-S00P04-CONSENT-DEGRADATION-PREREQUISITE",
        consent.get("status") == "PASS",
        {"status": consent.get("status"), "next": consent.get("next")},
    )
    stage4 = verify_stage4_delivery(root, verify_git_history=verify_git_history)
    _add(
        checks,
        "S06P01-S04-DELIVERY-PREREQUISITE",
        stage4.get("status") == "PASS",
        {"status": stage4.get("status"), "next": stage4.get("next")},
    )
    stage5 = verify_stage5_delivery(root, verify_git_history=verify_git_history)
    _add(
        checks,
        "S06P01-S05-CONTINUITY-DELIVERY-RECEIPT",
        stage5.get("status") == "PASS" and (root / S05_DELIVERY_RECEIPT_PATH).is_file(),
        {"status": stage5.get("status"), "next": stage5.get("next")},
    )


def _check_core_artifacts(
    root: Path,
    fixture: Mapping[str, Any] | None,
    query_rules: Mapping[str, Any] | None,
    token_document: str | None,
    checks: List[Dict[str, Any]],
) -> Mapping[str, Any] | None:
    if not isinstance(fixture, Mapping) or not isinstance(query_rules, Mapping) or not isinstance(token_document, str):
        _add(checks, "S06P01-FIXED-FIXTURE-AND-ARTIFACTS-AVAILABLE", False, "one or more core artifacts unavailable")
        return None
    fixture_ok = (
        fixture.get("schema_version") == "1.0.0"
        and fixture.get("fixture_id") == "FIX-S06-P01"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("requirement_id") == REQUIREMENT_ID
        and fixture.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        and fixture.get("numeric_boundary_deltas") == ["-0.0001", "0", "0.0001"]
        and fixture.get("adverse_odds_tick_action") == "NOT_APPLICABLE_NO_ODDS_OR_ORDER_ACTION_IN_S06_P01"
        and fixture.get("expected_next") == "S06/P02_READY_NOT_STARTED"
        and fixture.get("expected_release_status") == "NOT_READY_S06_P02_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED"
    )
    _add(checks, "S06P01-FIXTURE-SHAPE", fixture_ok, fixture.get("fixture_id"))
    query_errors = validate_query_rules_document(query_rules)
    _add(checks, "S06P01-QUERY-RULES-CONTRACT-EXACT", not query_errors, query_errors or "valid")
    try:
        token_contract = parse_token_storage_contract(token_document)
        _add(checks, "S06P01-TOKEN-STORAGE-CONTRACT-EXACT", token_contract == TOKEN_STORAGE_CONTRACT, token_contract)
    except Exception as exc:
        _add(checks, "S06P01-TOKEN-STORAGE-CONTRACT-EXACT", False, "%s: %s" % (type(exc).__name__, exc))

    source = (root / GMAIL_OAUTH_CORE_PATH).read_text(encoding="utf-8")
    facade = (root / GMAIL_OAUTH_PATH).read_text(encoding="utf-8")
    source_ok = (
        "time.sleep(" not in source
        and "requests." not in source
        and "urllib.request" not in source
        and "shell=True" not in source
        and "users.messages.delete" in source
        and "users.messages.list" in source
        and "abd_acceptance.gmail_oauth_core" in facade
        and REAL_TIME_SOAK_REQUIRED is False
    )
    _add(checks, "S06P01-NO-REALTIME-SOAK-OR-NETWORK-CLIENT", source_ok, "no sleep/network client/shell; deterministic interfaces only")
    return fixture


def _check_oauth_query_cursor_and_storage(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Mapping[str, Any] | None:
    try:
        request = build_authorization_request(
            fixture["oauth_client"], state=fixture["state"], code_verifier=fixture["code_verifier"]
        )
        expected_parameters = [
            "client_id",
            "redirect_uri",
            "response_type",
            "scope",
            "access_type",
            "include_granted_scopes",
            "prompt",
            "code_challenge",
            "code_challenge_method",
            "state",
        ]
        request_ok = (
            request.get("endpoint") == "https://accounts.google.com/o/oauth2/v2/auth"
            and request.get("requested_scopes") == [GMAIL_SCOPE]
            and request.get("parameter_names") == expected_parameters
            and request.get("network_performed") is False
            and request.get("owner_must_open_in_system_browser") is True
            and request.get("code_verifier_persisted") is False
        )
        _add(checks, "S06P01-OAUTH-REQUEST-EXACT-PKCE-NO-NETWORK", request_ok, request.get("parameter_names"))
        callback = validate_oauth_callback(
            expected_state=fixture["state"],
            returned_state=fixture["state"],
            returned_scope=GMAIL_SCOPE,
            authorization_code=fixture["authorization_code"],
        )
        callback_ok = (
            callback.get("status") == "CALLBACK_VALIDATED_NOT_EXCHANGED"
            and callback.get("authorization_code_accepted") is True
            and callback.get("authorization_code_exposed") is False
            and callback.get("returned_scope_exact") is True
        )
        _add(checks, "S06P01-OAUTH-CALLBACK-EXACT-SCOPE-FAIL-CLOSED", callback_ok, callback)
        rule = validate_query_rule(fixture["query_rule"])
        query = build_gmail_list_query(rule)
        query_ok = query == fixture["expected_query"] and rule["test_only"] is True and rule["bootstrap_days"] == 30
        _add(checks, "S06P01-QUERY-COMPILATION-EXACT-ALLOWLIST", query_ok, query)
        cursor = empty_cursor(rule["id"])
        first = advance_cursor(
            cursor,
            query_rule=rule,
            history_id=fixture["first_history_id"],
            attachment_records=fixture["attachment_records"],
        )
        second = advance_cursor(
            first["cursor"],
            query_rule=rule,
            history_id=fixture["second_history_id"],
            attachment_records=list(reversed(fixture["attachment_records"])),
        )
        cursor_ok = (
            first.get("status") == "QUEUE_DECISION_ONLY"
            and len(first.get("new_archive_keys", [])) == len(fixture["attachment_records"])
            and not first.get("duplicate_archive_keys")
            and second.get("new_archive_keys") == []
            and len(second.get("duplicate_archive_keys", [])) == len(fixture["attachment_records"])
            and first.get("cursor") == second.get("cursor")
            and first.get("gmail_mutation_performed") is False
            and second.get("real_time_soak_wait_required") is False
            and validate_cursor(second["cursor"], query_rule_id=rule["id"]) == second["cursor"]
        )
        _add(checks, "S06P01-IDEMPOTENT-CURSOR-REPLAY-NO-GMAIL-MUTATION", cursor_ok, {"first_new": len(first.get("new_archive_keys", [])), "second_new": len(second.get("new_archive_keys", []))})
        token = b"synthetic-token-only-not-a-real-credential"
        ciphertext = encrypt_token_bytes(token, fixture["token_storage"], _fake_age_runner)
        storage_ok = ciphertext.startswith(AGE_HEADER) and token not in ciphertext
        _add(checks, "S06P01-AGE-TOKEN-ENCRYPTION-INTERFACE", storage_ok, {"ciphertext_header": ciphertext.splitlines()[0].decode("ascii")})
        method_ok = validate_gmail_method("users.messages.list") == "users.messages.list"
        try:
            validate_gmail_method("users.messages.delete")
        except GmailOAuthContractError:
            denied_ok = True
        else:
            denied_ok = False
        _add(checks, "S06P01-GMAIL-METHOD-ALLOWLIST-AND-DENYLIST", method_ok and denied_ok, {"allow": method_ok, "deny": denied_ok})
        soak = validate_no_real_time_soak()
        soak_ok = soak.get("real_time_soak_required") is False and soak.get("core_deployment_behavior_when_gmail_unconfigured") == "CONTINUE_WITH_GMAIL_DISABLED"
        _add(checks, "S06P01-NO-SOAK-CORE-CONTINUES-WHEN-GMAIL-DISABLED", soak_ok, soak)
        return {"request": request, "first": first, "second": second, "query": query}
    except Exception as exc:
        _add(checks, "S06P01-CORE-FLOW-EXECUTABLE", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_negative_and_boundary_paths(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    bad_scope = validate_oauth_callback(
        expected_state=fixture["state"],
        returned_state=fixture["state"],
        returned_scope=[GMAIL_SCOPE, "https://mail.google.com/"],
        authorization_code=fixture["authorization_code"],
    )
    wrong_state = validate_oauth_callback(
        expected_state=fixture["state"],
        returned_state="C" * 43,
        returned_scope=GMAIL_SCOPE,
        authorization_code=fixture["authorization_code"],
    )
    _add(
        checks,
        "S06P01-CALLBACK-NEGATIVE-SCOPE-AND-STATE",
        bad_scope.get("reason_code") == "SCOPE_NOT_EXACT" and wrong_state.get("reason_code") == "STATE_MISMATCH",
        {"scope": bad_scope, "state": wrong_state},
    )
    malformed_rule = deepcopy(dict(fixture["query_rule"]))
    malformed_rule["sender_addresses"] = ["records@evidence.test.invalid", "records@evidence.test.invalid"]
    try:
        validate_query_rule(malformed_rule)
    except GmailOAuthContractError:
        duplicate_sender_rejected = True
    else:
        duplicate_sender_rejected = False
    injected_rule = deepcopy(dict(fixture["query_rule"]))
    injected_rule["subject_phrases"] = ["valid\nfrom:attacker@example.invalid"]
    try:
        validate_query_rule(injected_rule)
    except GmailOAuthContractError:
        injection_rejected = True
    else:
        injection_rejected = False
    _add(checks, "S06P01-QUERY-DUPLICATE-AND-INJECTION-FAIL-CLOSED", duplicate_sender_rejected and injection_rejected, {"duplicate": duplicate_sender_rejected, "injection": injection_rejected})
    rule = validate_query_rule(fixture["query_rule"])
    first = advance_cursor(
        empty_cursor(rule["id"]),
        query_rule=rule,
        history_id=fixture["first_history_id"],
        attachment_records=fixture["attachment_records"],
    )
    conflicted = deepcopy(list(fixture["attachment_records"]))
    conflicted[0]["content_sha256"] = "d" * 64
    try:
        advance_cursor(first["cursor"], query_rule=rule, history_id="1001", attachment_records=conflicted[:1])
    except CursorIntegrityError:
        changed_hash_rejected = True
    else:
        changed_hash_rejected = False
    try:
        advance_cursor(first["cursor"], query_rule=rule, history_id="999", attachment_records=[])
    except CursorIntegrityError:
        history_rewind_rejected = True
    else:
        history_rewind_rejected = False
    _add(checks, "S06P01-CURSOR-CONFLICT-AND-REWIND-FAIL-CLOSED", changed_hash_rejected and history_rewind_rejected, {"changed_hash": changed_hash_rejected, "rewind": history_rewind_rejected})
    token_config = deepcopy(dict(fixture["token_storage"]))
    token_config["token_path"] = "/workspace/MetaDatabase/ABD/leak.age"
    try:
        encrypt_token_bytes(b"synthetic", token_config, _fake_age_runner)
    except TokenStorageError:
        repo_path_rejected = True
    else:
        repo_path_rejected = False
    try:
        encrypt_token_bytes(b"synthetic", fixture["token_storage"], lambda _args, _input: AgeProcessResult(1, b""))
    except TokenStorageError:
        failed_age_rejected = True
    else:
        failed_age_rejected = False
    _add(checks, "S06P01-TOKEN-STORAGE-REPO-PATH-AND-FAILURE-FAIL-CLOSED", repo_path_rejected and failed_age_rejected, {"repo_path": repo_path_rejected, "age_failure": failed_age_rejected})
    deltas_ok = fixture.get("numeric_boundary_deltas") == ["-0.0001", "0", "0.0001"] and fixture.get("adverse_odds_tick_action") == "NOT_APPLICABLE_NO_ODDS_OR_ORDER_ACTION_IN_S06_P01"
    _add(checks, "S06P01-NUMERIC-BOUNDARY-DECLARED-NOT-APPLICABLE", deltas_ok, fixture.get("numeric_boundary_deltas"))


def _contains_sensitive_or_local_value(value: Any) -> bool:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    patterns = [
        r"/" + r"Users/",
        r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        r"ya29\.[0-9A-Za-z_-]+",
        r"1//[0-9A-Za-z_-]+",
        r"client_secret\s*[:=]\s*[^\s]+",
    ]
    return any(re.search(pattern, rendered) for pattern in patterns)


def _check_no_sensitive_material(root: Path, checks: List[Dict[str, Any]]) -> None:
    values: list[Any] = []
    for relative in (QUERY_RULES_PATH, FIXTURE_PATH):
        try:
            values.append(strict_json_load(root / relative))
        except Exception as exc:
            _add(checks, "S06P01-NO-SENSITIVE-OR-LOCAL-DATA", False, "%s: %s" % (type(exc).__name__, exc))
            return
    try:
        values.append((root / TOKEN_STORAGE_PATH).read_text(encoding="utf-8"))
        values.append((root / GMAIL_OAUTH_PATH).read_text(encoding="utf-8"))
        values.append((root / GMAIL_OAUTH_CORE_PATH).read_text(encoding="utf-8"))
    except Exception as exc:
        _add(checks, "S06P01-NO-SENSITIVE-OR-LOCAL-DATA", False, "%s: %s" % (type(exc).__name__, exc))
        return
    _add(checks, "S06P01-NO-SENSITIVE-OR-LOCAL-DATA", not any(_contains_sensitive_or_local_value(value) for value in values), "no raw token, client secret, private key, or local path")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    }


def _junit_is_normalized(path: Path) -> bool:
    """Accept only the deterministic form produced by normalize_junit.py.

    Timing fields are retained as fixed ``0.000`` values so the report stays
    valid JUnit XML while carrying no wall-clock duration as acceptance data.
    """

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites:
        return False
    for suite in suites:
        if suite.attrib.get("timestamp") != JUNIT_FIXED_CLOCK:
            return False
        if suite.attrib.get("time") != "0.000" or "hostname" in suite.attrib:
            return False
    for testcase in root.findall(".//testcase"):
        if testcase.attrib.get("time") != "0.000" or "hostname" in testcase.attrib:
            return False
    return True


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, label, minimum in [
        (JUNIT_PATH, "TARGETED", fixture.get("minimum_targeted_pytest_cases")),
        (FULL_JUNIT_PATH, "FULL", fixture.get("minimum_targeted_pytest_cases")),
    ]:
        path = root / relative
        try:
            summary = _junit_summary(path)
            normalized = _junit_is_normalized(path)
            hashes[relative.as_posix()] = sha256_file(path)
            ok = (
                type(minimum) is int
                and summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and normalized
            )
            _add(checks, "S06P01-%s-PYTEST-REPORT" % label, ok, {"summary": summary, "normalized": normalized, "minimum": minimum})
        except Exception as exc:
            _add(checks, "S06P01-%s-PYTEST-REPORT" % label, False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S06P01-FIXTURE-STRICT-JSON")
    query_rules = _safe_load(root / QUERY_RULES_PATH, checks, "S06P01-QUERY-RULES-STRICT-JSON")
    try:
        token_document = (root / TOKEN_STORAGE_PATH).read_text(encoding="utf-8")
        _add(checks, "S06P01-TOKEN-STORAGE-UTF8", True, TOKEN_STORAGE_PATH.as_posix())
    except Exception as exc:
        token_document = None
        _add(checks, "S06P01-TOKEN-STORAGE-UTF8", False, "%s: %s" % (type(exc).__name__, exc))

    _check_pins(root, checks, hashes)
    _add(
        checks,
        "S06P01-ORACLE-SELF-INTEGRITY",
        _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": _structural_self_hash(root)},
    )
    _check_taskpack_trace(root, checks)
    _check_predecessors(root, checks, verify_git_history=_verify_git_history)
    valid_fixture = _check_core_artifacts(root, fixture if isinstance(fixture, Mapping) else None, query_rules if isinstance(query_rules, Mapping) else None, token_document, checks)
    flow = None
    if valid_fixture is not None:
        flow = _check_oauth_query_cursor_and_storage(valid_fixture, checks)
        _check_negative_and_boundary_paths(valid_fixture, checks)
        if require_external_reports:
            _check_external_reports(root, valid_fixture, checks, hashes)
    else:
        _add(checks, "S06P01-CORE-FLOW-EXECUTABLE", False, "fixture unavailable")
    _check_no_sensitive_material(root, checks)

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "status": "PASS" if not failed else "FAIL",
        "phase_status": "S06_P01_PASS" if not failed else "S06_P01_FAIL",
        "decision": "GMAIL_AUTHORIZATION_QUERY_AND_CURSOR_FROZEN" if not failed else "S06_P01_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": hashes,
        "query": flow.get("query") if isinstance(flow, Mapping) else None,
        "external_network_used_by_verifier": False,
        "next": "S06/P02_READY_NOT_STARTED" if not failed else "S06/P01_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    result = evaluate_contract(root, require_external_reports=False)
    return {
        "status": result["status"],
        "decision": "S06_P01_CANDIDATE_VALID" if result["status"] == "PASS" else "S06_P01_CANDIDATE_INVALID",
        "summary": result["summary"],
        "next": result["next"],
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    """Prove a feature-disable rollback without touching a mailbox or token path."""

    root = root.resolve()
    artifacts: Dict[str, Dict[str, Any]] = {}
    all_ok = True
    for relative in ROLLBACK_ARTIFACTS:
        try:
            before = sha256_file(root / relative)
            after = sha256_file(root / relative)
            ok = before == after
            artifacts[relative.as_posix()] = {"status": "PASS" if ok else "FAIL", "before": before, "after": after}
            all_ok = all_ok and ok
        except Exception as exc:
            artifacts[relative.as_posix()] = {"status": "FAIL", "detail": "%s: %s" % (type(exc).__name__, exc)}
            all_ok = False
    state_before = {"gmail_module_state": "DISABLED", "gmail_mutation_performed": False, "queued_archive_keys": 0}
    state_after = {"gmail_module_state": "DISABLED", "gmail_mutation_performed": False, "queued_archive_keys": 0}
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all_ok and state_before == state_after else "FAIL",
        "mode": "DETERMINISTIC_FEATURE_DISABLE_NO_EXTERNAL_EFFECT",
        "artifacts": artifacts,
        "state_before": state_before,
        "state_after": state_after,
        "production_state_changed": False,
        "external_state_changed": False,
        "gmail_account_or_api_accessed": False,
        "token_path_accessed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        GMAIL_OAUTH_PATH,
        GMAIL_OAUTH_CORE_PATH,
        QUERY_RULES_PATH,
        TOKEN_STORAGE_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        Path("abd_acceptance/stage5_delivery.py"),
        S05_DELIVERY_RECEIPT_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
    ]
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
    *,
    _verify_git_history: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    fixture = strict_json_load(root / FIXTURE_PATH)
    input_hashes = _input_hashes(root)
    stage4 = verify_stage4_delivery(root, verify_git_history=_verify_git_history)
    stage5 = verify_stage5_delivery(root, verify_git_history=_verify_git_history)
    idempotency = None
    try:
        rule = validate_query_rule(fixture["query_rule"])
        first = advance_cursor(
            empty_cursor(rule["id"]),
            query_rule=rule,
            history_id=fixture["first_history_id"],
            attachment_records=fixture["attachment_records"],
        )
        second = advance_cursor(
            first["cursor"],
            query_rule=rule,
            history_id=fixture["second_history_id"],
            attachment_records=fixture["attachment_records"],
        )
        idempotency = {
            "first_scan_queued_count": len(first["new_archive_keys"]),
            "repeat_scan_queued_count": len(second["new_archive_keys"]),
            "repeat_scan_duplicate_count": len(second["duplicate_archive_keys"]),
            "cursor_equal_after_repeat": first["cursor"] == second["cursor"],
            "gmail_mutation_performed": False,
        }
    except Exception as exc:
        idempotency = {"error": "%s: %s" % (type(exc).__name__, exc)}
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": fixture.get("fixed_clock"),
        "status": validation["status"],
        "phase_status": validation["phase_status"],
        "decision": validation["decision"],
        "validation": validation,
        "predecessor_delivery": {
            "s04_status": stage4.get("status"),
            "s05_receipt": S05_DELIVERY_RECEIPT_PATH.as_posix(),
            "s05_receipt_sha256": sha256_file(root / S05_DELIVERY_RECEIPT_PATH),
            "s05_status": stage5.get("status"),
        },
        "oauth_and_query_boundary": {
            "scope_exact": GMAIL_SCOPE,
            "production_rules_enabled": False,
            "real_oauth_exchange_performed": False,
            "gmail_mutation_performed": False,
            "idempotency": idempotency,
        },
        "no_real_time_soak": validate_no_real_time_soak(),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": fixture.get("expected_release_status"),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S06/P01_test.py --junitxml=machine/evidence/S06/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S06/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S06-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": input_hashes,
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S06/P01 only validates offline OAuth/query/cursor/token-storage contracts with synthetic inputs.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str, fixed_clock: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S06-P01"]
    rows.append(
        {
            "id": "INDEX-AC-S06-P01",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S06/P02_READY_NOT_STARTED" if status == "PASS" else "S06/P01_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    rendered = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    _atomic_write(path, rendered.encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(evidence_path, _json_bytes(evidence))
    _atomic_write(rollback_path, _json_bytes(rollback))
    if evidence_dir == (root / "machine/evidence").resolve():
        _update_evidence_index(root, evidence["status"], sha256_file(evidence_path), str(evidence["fixed_clock"]))
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.as_posix(),
        "evidence_sha256": sha256_file(evidence_path),
        "next": evidence["next"],
    }


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("decision_sha256")
    unsigned = deepcopy(dict(evidence))
    unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and _sha256_bytes(_json_bytes(unsigned)) == expected


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S06P01-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S06P01-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        expected = (
            evidence.get("evidence_id") == "EVD-S06-P01"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S06/P02_READY_NOT_STARTED"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and evidence.get("no_real_time_soak", {}).get("real_time_soak_required") is False
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S06P01-EXISTING-EVIDENCE-INTEGRITY", expected, evidence.get("status"))
    else:
        _add(checks, "S06P01-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S06-P01-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S06P01-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S06P01-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    _add(checks, "S06P01-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "",
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S06/P02_READY_NOT_STARTED" if not failed else "S06/P01_REMEDIATION_REQUIRED",
    }
