from __future__ import annotations

import copy
import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from abd_acceptance.gmail_oauth_core import (
    AGE_HEADER,
    ALLOWED_GMAIL_METHODS,
    DENIED_GMAIL_METHODS,
    GMAIL_SCOPE,
    TOKEN_FILE_MODE,
    AgeProcessResult,
    CursorIntegrityError,
    GmailOAuthContractError,
    TokenStorageError,
    advance_cursor,
    archive_idempotency_key,
    build_authorization_request,
    build_gmail_list_query,
    create_ephemeral_oauth_material,
    empty_cursor,
    encrypt_token_bytes,
    normalize_attachment_record,
    store_encrypted_token,
    validate_cursor,
    validate_gmail_method,
    validate_no_real_time_soak,
    validate_oauth_callback,
    validate_query_rule,
    validate_query_rules_document,
)
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.gmail_authorization import (
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    GMAIL_OAUTH_PATH,
    JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    ORACLE_PATH,
    PINNED_PHASE_HASHES,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    TOKEN_STORAGE_CONTRACT,
    TOKEN_STORAGE_PATH,
    _structural_self_hash,
    _junit_is_normalized,
    build_evidence as _build_evidence,
    evaluate_contract as _evaluate_contract,
    parse_token_storage_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)
from abd_acceptance.stage4_delivery import verify_stage4_delivery
from abd_acceptance.stage5_delivery import RECEIPT_PATH as S05_RECEIPT_PATH
from abd_acceptance.stage5_delivery import verify_stage5_delivery


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
QUERY_RULES = strict_json_load(ROOT / "mail_query_rules.json")


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def build_evidence(root: Path, require_external_reports: bool = False):
    return _build_evidence(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def verify_existing_phase_evidence(root: Path):
    return _verify_existing_phase_evidence(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"))
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str | None = None) -> None:
    assert result["status"] == "FAIL", result
    if check_id is not None:
        assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _success_age_runner(arguments, input_bytes: bytes) -> AgeProcessResult:
    assert arguments[1] == "-r"
    assert input_bytes
    return AgeProcessResult(0, AGE_HEADER + b"-> X25519 fixture\n--- encrypted fixture only\n")


def test_candidate_preflight_passes_without_external_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S06_P01_CANDIDATE_VALID"
    assert result["next"] == FIXTURE["expected_next"]


def test_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "GMAIL_AUTHORIZATION_QUERY_AND_CURSOR_FROZEN"
    assert result["phase_status"] == "S06_P01_PASS"
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["external_network_used_by_verifier"] is False
    assert result["next"] == "S06/P02_READY_NOT_STARTED"
    assert len({check["id"] for check in result["checks"]}) == len(result["checks"])


def test_taskpack_identity_and_scope_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    row = next(item for item in requirements if item["id"] == "REQ-S06-P01")
    assert CONTRACT_ID == "AC-S06-P01"
    assert row["scope"] == ["gmail_oauth.py", "mail_query_rules.json", "token_storage.md"]
    assert row["target"] == "无授权不阻塞核心；有授权后重复扫描不重复归档。"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) in {
        PINNED_PHASE_HASHES[relative],
        SUCCESSOR_UNIT_PROFILE_HASHES.get(relative),
    }


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_junit_normalization_accepts_fixed_metadata_only(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        "<testsuites><testsuite tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\" "
        "timestamp=\"%s\" time=\"0.000\"><testcase name=\"offline\" time=\"0.000\" />"
        "</testsuite></testsuites>" % JUNIT_FIXED_CLOCK,
        encoding="utf-8",
    )
    assert _junit_is_normalized(report) is True
    report.write_text(report.read_text(encoding="utf-8").replace("time=\"0.000\"", "time=\"0.001\"", 1), encoding="utf-8")
    assert _junit_is_normalized(report) is False


def test_query_rule_document_is_exact_and_live_rules_remain_disabled() -> None:
    assert validate_query_rules_document(QUERY_RULES) == []
    assert QUERY_RULES["query_contract"]["production_rules"] == []
    assert QUERY_RULES["claim_boundary"]["production_query_enabled"] is False
    assert QUERY_RULES["query_contract"]["real_time_soak_gate"] == "NONE"


def test_token_storage_document_machine_contract_and_no_real_token() -> None:
    document = (ROOT / TOKEN_STORAGE_PATH).read_text(encoding="utf-8")
    assert parse_token_storage_contract(document) == TOKEN_STORAGE_CONTRACT
    assert "ya29." not in document
    assert "1//" not in document
    assert "real_time_soak_required\": false" in document


def test_oauth_request_is_exact_pkce_and_does_not_open_network() -> None:
    result = build_authorization_request(
        FIXTURE["oauth_client"], state=FIXTURE["state"], code_verifier=FIXTURE["code_verifier"]
    )
    assert result["endpoint"] == "https://accounts.google.com/o/oauth2/v2/auth"
    assert result["requested_scopes"] == [GMAIL_SCOPE]
    assert result["network_performed"] is False
    assert result["owner_must_open_in_system_browser"] is True
    assert result["code_verifier_persisted"] is False
    assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.modify" in result["authorization_url"]
    assert "include_granted_scopes=false" in result["authorization_url"]
    assert "code_challenge_method=S256" in result["authorization_url"]


@pytest.mark.parametrize(
    "client",
    [
        {"client_id": "bad", "redirect_uri": FIXTURE["oauth_client"]["redirect_uri"]},
        {"client_id": FIXTURE["oauth_client"]["client_id"], "redirect_uri": "http://abd-owner.invalid/callback"},
        {"client_id": FIXTURE["oauth_client"]["client_id"], "redirect_uri": "https://localhost/callback"},
        {"client_id": FIXTURE["oauth_client"]["client_id"], "redirect_uri": "https://abd-owner.invalid/callback?open=true"},
        {"client_id": FIXTURE["oauth_client"]["client_id"], "redirect_uri": "https://*.invalid/callback"},
    ],
)
def test_invalid_oauth_client_configuration_is_rejected(client: dict) -> None:
    with pytest.raises(GmailOAuthContractError):
        build_authorization_request(client, state=FIXTURE["state"], code_verifier=FIXTURE["code_verifier"])


@pytest.mark.parametrize(
    "returned_scope,expected_reason",
    [
        ([GMAIL_SCOPE, "https://mail.google.com/"], "SCOPE_NOT_EXACT"),
        ("https://mail.google.com/", "SCOPE_NOT_EXACT"),
        ([], "SCOPE_NOT_EXACT"),
        ([GMAIL_SCOPE, GMAIL_SCOPE], "SCOPE_NOT_EXACT"),
    ],
)
def test_scope_expansion_or_mismatch_disables_callback(returned_scope, expected_reason: str) -> None:
    result = validate_oauth_callback(
        expected_state=FIXTURE["state"],
        returned_state=FIXTURE["state"],
        returned_scope=returned_scope,
        authorization_code=FIXTURE["authorization_code"],
    )
    assert result["status"] == "DISABLED"
    assert result["reason_code"] == expected_reason
    assert result["authorization_code_accepted"] is False


@pytest.mark.parametrize(
    "returned_state,error,reason",
    [
        ("C" * 43, None, "STATE_MISMATCH"),
        (FIXTURE["state"], "access_denied", "OAUTH_ERROR_RETURNED"),
        (FIXTURE["state"], None, "AUTHORIZATION_CODE_MALFORMED"),
    ],
)
def test_callback_state_or_error_paths_fail_closed(returned_state: str, error: str | None, reason: str) -> None:
    code = "bad code" if reason == "AUTHORIZATION_CODE_MALFORMED" else FIXTURE["authorization_code"]
    result = validate_oauth_callback(
        expected_state=FIXTURE["state"],
        returned_state=returned_state,
        returned_scope=GMAIL_SCOPE,
        authorization_code=code,
        error=error,
    )
    assert result["status"] == "DISABLED"
    assert result["reason_code"] == reason


def test_ephemeral_material_has_valid_nonpersistent_shapes() -> None:
    material = create_ephemeral_oauth_material(lambda count: bytes(range(count)))
    assert len(material["state"]) == 43
    assert len(material["code_verifier"]) == 86
    request = build_authorization_request(FIXTURE["oauth_client"], **material)
    assert request["code_verifier_persisted"] is False


def test_query_compilation_is_exact_and_input_order_independent() -> None:
    baseline = build_gmail_list_query(FIXTURE["query_rule"])
    reordered = copy.deepcopy(FIXTURE["query_rule"])
    for field in ("sender_addresses", "subject_phrases", "attachment_extensions"):
        reordered[field] = list(reversed(reordered[field]))
    assert baseline == FIXTURE["expected_query"]
    assert build_gmail_list_query(reordered) == baseline


@pytest.mark.parametrize(
    "field,value",
    [
        ("sender_addresses", []),
        ("sender_addresses", ["records@evidence.test.invalid", "records@evidence.test.invalid"]),
        ("sender_addresses", ["records@evidence.test.invalid\nfrom:attacker@example.invalid"]),
        ("subject_phrases", ["injected\nfrom:attacker@example.invalid"]),
        ("subject_phrases", ['unterminated " quote']),
        ("attachment_extensions", [".pdf"]),
        ("attachment_extensions", ["pdf OR from:attacker"]),
        ("bootstrap_days", 30.0001),
    ],
)
def test_query_rule_malformed_or_injected_input_is_rejected(field: str, value) -> None:
    rule = copy.deepcopy(FIXTURE["query_rule"])
    rule[field] = value
    with pytest.raises(GmailOAuthContractError):
        validate_query_rule(rule)


def test_query_rule_requires_test_only_boolean_and_exact_fields() -> None:
    rule = copy.deepcopy(FIXTURE["query_rule"])
    rule["test_only"] = "true"
    with pytest.raises(GmailOAuthContractError):
        validate_query_rule(rule)
    rule = copy.deepcopy(FIXTURE["query_rule"])
    rule["untrusted_query"] = "in:anywhere"
    with pytest.raises(GmailOAuthContractError):
        validate_query_rule(rule)


def test_first_scan_queues_each_synthetic_attachment_once() -> None:
    rule = validate_query_rule(FIXTURE["query_rule"])
    result = advance_cursor(
        empty_cursor(rule["id"]),
        query_rule=rule,
        history_id=FIXTURE["first_history_id"],
        attachment_records=FIXTURE["attachment_records"],
    )
    assert result["status"] == "QUEUE_DECISION_ONLY"
    assert len(result["new_archive_keys"]) == 3
    assert result["duplicate_archive_keys"] == []
    assert result["gmail_mutation_performed"] is False
    assert result["real_time_soak_wait_required"] is False
    assert validate_cursor(result["cursor"], query_rule_id=rule["id"]) == result["cursor"]


def test_repeated_scan_is_idempotent_and_order_independent() -> None:
    rule = validate_query_rule(FIXTURE["query_rule"])
    first = advance_cursor(
        empty_cursor(rule["id"]),
        query_rule=rule,
        history_id="1000",
        attachment_records=FIXTURE["attachment_records"],
    )
    second = advance_cursor(
        first["cursor"],
        query_rule=rule,
        history_id="1000",
        attachment_records=list(reversed(FIXTURE["attachment_records"])),
    )
    assert second["new_archive_keys"] == []
    assert second["duplicate_archive_keys"] == sorted(first["new_archive_keys"])
    assert second["cursor"] == first["cursor"]


def test_archive_key_uses_message_attachment_and_hash() -> None:
    source = FIXTURE["attachment_records"][0]
    same = copy.deepcopy(source)
    changed = copy.deepcopy(source)
    changed["content_sha256"] = "f" * 64
    assert archive_idempotency_key(source) == archive_idempotency_key(same)
    assert archive_idempotency_key(source) != archive_idempotency_key(changed)
    assert normalize_attachment_record(source) == source


@pytest.mark.parametrize(
    "mutation",
    [
        "history_rewind",
        "content_hash_changed",
        "cursor_key_unsorted",
        "cursor_key_duplicate",
        "cursor_map_unbound",
        "malformed_message_id",
        "malformed_sha256",
    ],
)
def test_cursor_integrity_faults_fail_closed(mutation: str) -> None:
    rule = validate_query_rule(FIXTURE["query_rule"])
    first = advance_cursor(
        empty_cursor(rule["id"]),
        query_rule=rule,
        history_id="1000",
        attachment_records=FIXTURE["attachment_records"],
    )
    if mutation == "history_rewind":
        with pytest.raises(CursorIntegrityError):
            advance_cursor(first["cursor"], query_rule=rule, history_id="999", attachment_records=[])
    elif mutation == "content_hash_changed":
        changed = copy.deepcopy(FIXTURE["attachment_records"][:1])
        changed[0]["content_sha256"] = "d" * 64
        with pytest.raises(CursorIntegrityError):
            advance_cursor(first["cursor"], query_rule=rule, history_id="1001", attachment_records=changed)
    elif mutation == "cursor_key_unsorted":
        cursor = copy.deepcopy(first["cursor"])
        cursor["processed_archive_keys"] = list(reversed(cursor["processed_archive_keys"]))
        with pytest.raises(CursorIntegrityError):
            validate_cursor(cursor, query_rule_id=rule["id"])
    elif mutation == "cursor_key_duplicate":
        cursor = copy.deepcopy(first["cursor"])
        cursor["processed_archive_keys"].append(cursor["processed_archive_keys"][0])
        cursor["processed_archive_keys"].sort()
        with pytest.raises(CursorIntegrityError):
            validate_cursor(cursor, query_rule_id=rule["id"])
    elif mutation == "cursor_map_unbound":
        cursor = copy.deepcopy(first["cursor"])
        cursor["attachment_hashes"]["MSG0099/ATT0099"] = "f" * 64
        cursor["attachment_hashes"] = {key: cursor["attachment_hashes"][key] for key in sorted(cursor["attachment_hashes"])}
        with pytest.raises(CursorIntegrityError):
            validate_cursor(cursor, query_rule_id=rule["id"])
    elif mutation == "malformed_message_id":
        bad = copy.deepcopy(FIXTURE["attachment_records"][:1])
        bad[0]["gmail_message_id"] = "bad/id"
        with pytest.raises(CursorIntegrityError):
            advance_cursor(empty_cursor(rule["id"]), query_rule=rule, history_id="1", attachment_records=bad)
    else:
        bad = copy.deepcopy(FIXTURE["attachment_records"][:1])
        bad[0]["content_sha256"] = "A" * 64
        with pytest.raises(CursorIntegrityError):
            advance_cursor(empty_cursor(rule["id"]), query_rule=rule, history_id="1", attachment_records=bad)


def test_method_allowlist_is_exact_and_delete_is_denied() -> None:
    assert validate_gmail_method("users.messages.list") == "users.messages.list"
    assert len(ALLOWED_GMAIL_METHODS) == 7
    assert "users.messages.delete" in DENIED_GMAIL_METHODS
    with pytest.raises(GmailOAuthContractError):
        validate_gmail_method("users.messages.delete")


@pytest.mark.parametrize("method", DENIED_GMAIL_METHODS)
def test_all_disallowed_gmail_methods_are_rejected(method: str) -> None:
    with pytest.raises(GmailOAuthContractError):
        validate_gmail_method(method)


def test_token_encryptor_returns_only_age_ciphertext_and_not_plaintext() -> None:
    token = b"synthetic-token-not-a-real-credential"
    ciphertext = encrypt_token_bytes(token, FIXTURE["token_storage"], _success_age_runner)
    assert ciphertext.startswith(AGE_HEADER)
    assert token not in ciphertext


def test_encrypted_token_storage_writes_outside_repository_with_mode_0600(tmp_path: Path) -> None:
    config = copy.deepcopy(FIXTURE["token_storage"])
    config["repository_root"] = str(tmp_path / "repo")
    config["token_path"] = str(tmp_path / "runtime-secrets" / "gmail-refresh-token.age")
    token = b"synthetic-token-not-a-real-credential"
    result = store_encrypted_token(token, config, _success_age_runner)
    token_path = Path(config["token_path"])
    assert result["status"] == "VERIFIED_ENCRYPTED"
    assert result["token_or_path_exposed"] is False
    assert token not in token_path.read_bytes()
    assert stat.S_IMODE(os.stat(token_path).st_mode) == TOKEN_FILE_MODE


@pytest.mark.parametrize(
    "configuration,runner",
    [
        ({"token_path": "/workspace/MetaDatabase/ABD/leak.age"}, _success_age_runner),
        ({"recipient": "not-an-age-recipient"}, _success_age_runner),
        ({"age_binary": "relative/age"}, _success_age_runner),
        ({}, lambda _arguments, _input: AgeProcessResult(1, b"")),
    ],
)
def test_token_storage_bad_config_or_encrypt_failure_is_rejected(configuration: dict, runner) -> None:
    config = copy.deepcopy(FIXTURE["token_storage"])
    config.update(configuration)
    with pytest.raises(TokenStorageError):
        encrypt_token_bytes(b"synthetic-token", config, runner)


def test_no_real_time_soak_never_blocks_core_when_gmail_disabled() -> None:
    status = validate_no_real_time_soak()
    assert status["real_time_soak_required"] is False
    assert status["core_deployment_behavior_when_gmail_unconfigured"] == "CONTINUE_WITH_GMAIL_DISABLED"
    assert "EXACT_SCOPE" in status["immediate_gates"]


def test_stage4_and_stage5_delivery_receipts_pass() -> None:
    stage4 = verify_stage4_delivery(ROOT)
    stage5 = verify_stage5_delivery(ROOT)
    assert stage4["status"] == "PASS", stage4
    assert stage5["status"] == "PASS", stage5
    assert stage5["next"] == "S06/P01_READY_NOT_STARTED"


def test_stage5_receipt_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    receipt = strict_json_load(root / S05_RECEIPT_PATH)
    receipt["pull_request"]["merge_commit"] = "0" * 40
    _write_json(root / S05_RECEIPT_PATH, receipt)
    result = verify_stage5_delivery(root, verify_git_history=False)
    _failed(result, "S05DELIVERY-PR-IMMUTABLE-FACTS")


@pytest.mark.parametrize(
    "relative,mutation,check_id",
    [
        ("mail_query_rules.json", ("query_contract", "production_rules", [{"bad": True}]), "S06P01-QUERY-RULES-CONTRACT-EXACT"),
        ("machine/tests/fixtures/S06_P01.json", ("query_rule", "bootstrap_days", 31), "S06P01-QUERY-COMPILATION-EXACT-ALLOWLIST"),
    ],
)
def test_artifact_mutations_fail_closed(tmp_path: Path, relative: str, mutation: tuple, check_id: str) -> None:
    root = _clone_project(tmp_path)
    value = strict_json_load(root / relative)
    target = value
    for key in mutation[:-2]:
        target = target[key]
    target[mutation[-2]] = mutation[-1]
    _write_json(root / relative, value)
    result = evaluate_contract(root)
    _failed(result, check_id)


def test_sensitive_token_pattern_in_document_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / TOKEN_STORAGE_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\nexample ya29.synthetic-token\n", encoding="utf-8")
    result = evaluate_contract(root)
    _failed(result, "S06P01-NO-SENSITIVE-OR-LOCAL-DATA")


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["oauth_and_query_boundary"]["idempotency"]["repeat_scan_queued_count"] == 0
    assert first["no_real_time_soak"]["real_time_soak_required"] is False
    assert first["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert first["next"] == "S06/P02_READY_NOT_STARTED"
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered


def test_rollback_drill_preserves_every_phase_artifact_and_never_waits() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["real_time_soak_waited"] is False


def test_external_report_mode_fails_closed_without_reports(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S06P01-TARGETED-PYTEST-REPORT")


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
    else:
        assert result["status"] == "FAIL"
