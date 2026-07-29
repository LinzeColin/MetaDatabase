"""Fail-closed Gmail OAuth, query, cursor, and token-storage primitives for ABD S06/P01.

This module deliberately performs no HTTP request and no Gmail mutation.  It
prepares an owner-only OAuth request, validates a callback supplied by a
runtime adapter, compiles an exact allowlisted Gmail search query, and keeps a
deterministic cursor for later archival stages.  The caller must provide a
separately provisioned, outside-repository ``age`` binary and secret paths
before any real token is encrypted or read.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode, urlparse


VERSION = "0.0.0.1"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_SCOPE_SHORT_NAME = "gmail.modify"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_RESPONSE_TYPE = "code"
OAUTH_ACCESS_TYPE = "offline"
OAUTH_PROMPT = "consent"
PKCE_METHOD = "S256"
CURSOR_SCHEMA_VERSION = "1.0.0"
AGE_HEADER = b"age-encryption.org/v1\n"
TOKEN_FILE_MODE = 0o600
MAX_TOKEN_BYTES = 16_384
AGE_PROCESS_TIMEOUT_SECONDS = 5
REAL_TIME_SOAK_REQUIRED = False

ALLOWED_GMAIL_METHODS = (
    "users.getProfile",
    "users.history.list",
    "users.messages.list",
    "users.messages.get",
    "users.messages.attachments.get",
    "users.messages.trash",
    "users.messages.untrash",
)
DENIED_GMAIL_METHODS = (
    "users.drafts.create",
    "users.drafts.send",
    "users.messages.batchDelete",
    "users.messages.delete",
    "users.messages.import",
    "users.messages.insert",
    "users.messages.send",
    "users.settings.*",
    "users.threads.delete",
)

_CLIENT_ID_RE = re.compile(r"\A[0-9]{6,}-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com\Z")
_STATE_RE = re.compile(r"\A[A-Za-z0-9_-]{43,128}\Z")
_PKCE_VERIFIER_RE = re.compile(r"\A[A-Za-z0-9._~-]{43,128}\Z")
_EMAIL_RE = re.compile(r"\A[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\Z")
_RULE_ID_RE = re.compile(r"\A[A-Z][A-Z0-9_-]{3,80}\Z")
_EXTENSION_RE = re.compile(r"\A[a-z0-9]{1,12}\Z")
_MESSAGE_OR_ATTACHMENT_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_HISTORY_ID_RE = re.compile(r"\A(?:0|[1-9][0-9]{0,38})\Z")
_AGE_RECIPIENT_RE = re.compile(r"\Aage1[ac-hj-np-z02-9]{20,}\Z")


class GmailOAuthContractError(ValueError):
    """Raised for a contract or input violation before any external action."""


class OAuthCallbackError(GmailOAuthContractError):
    """Raised when an OAuth callback cannot be safely accepted."""


class CursorIntegrityError(GmailOAuthContractError):
    """Raised when a scan would make the archive cursor ambiguous."""


class TokenStorageError(GmailOAuthContractError):
    """Raised without echoing token, command stderr, or secret file paths."""


@dataclass(frozen=True)
class AgeProcessResult:
    """Small process result surface that intentionally excludes command logs."""

    returncode: int
    stdout: bytes


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_string(value: Any, field: str, *, minimum: int = 1, maximum: int = 512) -> str:
    if not isinstance(value, str) or isinstance(value, bool):
        raise GmailOAuthContractError("%s must be a string" % field)
    if not minimum <= len(value) <= maximum:
        raise GmailOAuthContractError("%s length is outside the permitted range" % field)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise GmailOAuthContractError("%s contains a control character" % field)
    return value


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _require_random_bytes(random_bytes: Callable[[int], bytes], length: int, field: str) -> bytes:
    value = random_bytes(length)
    if not isinstance(value, bytes) or len(value) != length:
        raise GmailOAuthContractError("%s random source did not return exactly %d bytes" % (field, length))
    return value


def create_ephemeral_oauth_material(random_bytes: Callable[[int], bytes] = os.urandom) -> Mapping[str, str]:
    """Create memory-only state and PKCE verifier material.

    The caller owns the one-time server-side session.  This function neither
    persists nor logs either value, so it can safely be exercised with a fixed
    random source in deterministic tests.
    """

    state = _base64url(_require_random_bytes(random_bytes, 32, "state"))
    verifier = _base64url(_require_random_bytes(random_bytes, 64, "code_verifier"))
    validate_state(state)
    validate_pkce_verifier(verifier)
    return {"state": state, "code_verifier": verifier}


def validate_state(value: Any) -> str:
    state = _require_string(value, "state", minimum=43, maximum=128)
    if not _STATE_RE.fullmatch(state):
        raise GmailOAuthContractError("state must be an RFC 7636-safe base64url value")
    return state


def validate_pkce_verifier(value: Any) -> str:
    verifier = _require_string(value, "code_verifier", minimum=43, maximum=128)
    if not _PKCE_VERIFIER_RE.fullmatch(verifier):
        raise GmailOAuthContractError("code_verifier must be an RFC 7636 unreserved value")
    return verifier


def pkce_s256_challenge(code_verifier: Any) -> str:
    verifier = validate_pkce_verifier(code_verifier)
    return _base64url(hashlib.sha256(verifier.encode("ascii")).digest())


def validate_exact_gmail_scope(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        scopes: list[Any] = value.split()
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        scopes = list(value)
    else:
        raise GmailOAuthContractError("scope must be a string or sequence")
    if any(not isinstance(scope, str) for scope in scopes):
        raise GmailOAuthContractError("scope contains a non-string value")
    if tuple(scopes) != (GMAIL_SCOPE,):
        raise GmailOAuthContractError("scope must be exactly gmail.modify")
    return (GMAIL_SCOPE,)


def validate_client_id(value: Any) -> str:
    client_id = _require_string(value, "client_id", maximum=256)
    if not _CLIENT_ID_RE.fullmatch(client_id):
        raise GmailOAuthContractError("client_id is not a Google web OAuth client identifier")
    return client_id


def validate_redirect_uri(value: Any) -> str:
    uri = _require_string(value, "redirect_uri", maximum=512)
    parsed = urlparse(uri)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "*" in parsed.hostname
        or parsed.hostname.lower() == "localhost"
    ):
        raise GmailOAuthContractError("redirect_uri must be one exact owner-controlled HTTPS URI")
    return uri


def build_authorization_request(
    oauth_client: Mapping[str, Any],
    *,
    state: Any,
    code_verifier: Any,
) -> Mapping[str, Any]:
    """Build, but never open, an owner-only Google authorization request."""

    if not isinstance(oauth_client, Mapping):
        raise GmailOAuthContractError("oauth_client must be a mapping")
    if set(oauth_client) != {"client_id", "redirect_uri"}:
        raise GmailOAuthContractError("oauth_client fields must be exactly client_id and redirect_uri")
    client_id = validate_client_id(oauth_client["client_id"])
    redirect_uri = validate_redirect_uri(oauth_client["redirect_uri"])
    state_value = validate_state(state)
    challenge = pkce_s256_challenge(code_verifier)
    parameters = (
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("response_type", OAUTH_RESPONSE_TYPE),
        ("scope", GMAIL_SCOPE),
        ("access_type", OAUTH_ACCESS_TYPE),
        ("include_granted_scopes", "false"),
        ("prompt", OAUTH_PROMPT),
        ("code_challenge", challenge),
        ("code_challenge_method", PKCE_METHOD),
        ("state", state_value),
    )
    return {
        "authorization_url": "%s?%s" % (GOOGLE_AUTHORIZATION_ENDPOINT, urlencode(parameters)),
        "endpoint": GOOGLE_AUTHORIZATION_ENDPOINT,
        "requested_scopes": [GMAIL_SCOPE],
        "parameter_names": [name for name, _ in parameters],
        "network_performed": False,
        "owner_must_open_in_system_browser": True,
        "code_verifier_persisted": False,
    }


def validate_oauth_callback(
    *,
    expected_state: Any,
    returned_state: Any,
    returned_scope: Any,
    authorization_code: Any,
    error: Any = None,
) -> Mapping[str, Any]:
    """Validate callback facts without returning the authorization code."""

    expected = validate_state(expected_state)
    returned = _require_string(returned_state, "returned_state", minimum=43, maximum=128)
    if error not in (None, ""):
        return {"status": "DISABLED", "reason_code": "OAUTH_ERROR_RETURNED", "authorization_code_accepted": False}
    if not hmac.compare_digest(expected, returned):
        return {"status": "DISABLED", "reason_code": "STATE_MISMATCH", "authorization_code_accepted": False}
    try:
        validate_exact_gmail_scope(returned_scope)
    except GmailOAuthContractError:
        return {"status": "DISABLED", "reason_code": "SCOPE_NOT_EXACT", "authorization_code_accepted": False}
    code = _require_string(authorization_code, "authorization_code", minimum=8, maximum=4096)
    if any(char.isspace() for char in code):
        return {"status": "DISABLED", "reason_code": "AUTHORIZATION_CODE_MALFORMED", "authorization_code_accepted": False}
    return {
        "status": "CALLBACK_VALIDATED_NOT_EXCHANGED",
        "reason_code": "EXTERNAL_TOKEN_EXCHANGE_REQUIRES_SEPARATE_RUNTIME_GATE",
        "authorization_code_accepted": True,
        "returned_scope_exact": True,
        "authorization_code_exposed": False,
    }


def validate_gmail_method(method: Any) -> str:
    method_name = _require_string(method, "gmail_method", maximum=128)
    if method_name not in ALLOWED_GMAIL_METHODS:
        raise GmailOAuthContractError("gmail method is not allowlisted")
    return method_name


def _strict_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise GmailOAuthContractError("%s fields are not exact" % name)


def _normalize_unique_strings(values: Any, field: str, validator: Callable[[Any], str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise GmailOAuthContractError("%s must be a non-empty sequence" % field)
    normalized = tuple(sorted(validator(value) for value in values))
    if len(set(normalized)) != len(normalized):
        raise GmailOAuthContractError("%s contains duplicates" % field)
    return normalized


def _validate_sender_address(value: Any) -> str:
    address = _require_string(value, "sender_address", maximum=254).lower()
    if not _EMAIL_RE.fullmatch(address):
        raise GmailOAuthContractError("sender_address must be one exact email address")
    return address


def _validate_subject_phrase(value: Any) -> str:
    phrase = _require_string(value, "subject_phrase", maximum=120)
    if '"' in phrase or "\\" in phrase:
        raise GmailOAuthContractError("subject_phrase cannot contain quoting control characters")
    return phrase


def _validate_attachment_extension(value: Any) -> str:
    extension = _require_string(value, "attachment_extension", maximum=12).lower()
    if not _EXTENSION_RE.fullmatch(extension):
        raise GmailOAuthContractError("attachment_extension must be a simple extension without a dot")
    return extension


def validate_query_rule(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GmailOAuthContractError("query rule must be a mapping")
    _strict_keys(
        value,
        {
            "id",
            "sender_addresses",
            "subject_phrases",
            "attachment_extensions",
            "bootstrap_days",
            "source_contract_id",
            "test_only",
        },
        "query rule",
    )
    rule_id = _require_string(value["id"], "rule id", maximum=80)
    source_contract_id = _require_string(value["source_contract_id"], "source_contract_id", maximum=80)
    if not _RULE_ID_RE.fullmatch(rule_id) or not _RULE_ID_RE.fullmatch(source_contract_id):
        raise GmailOAuthContractError("query rule identifiers must be uppercase contract identifiers")
    bootstrap_days = value["bootstrap_days"]
    if type(bootstrap_days) is not int or not 1 <= bootstrap_days <= 90:
        raise GmailOAuthContractError("bootstrap_days must be an integer from 1 to 90")
    if type(value["test_only"]) is not bool:
        raise GmailOAuthContractError("test_only must be a boolean")
    return {
        "id": rule_id,
        "sender_addresses": _normalize_unique_strings(value["sender_addresses"], "sender_addresses", _validate_sender_address),
        "subject_phrases": _normalize_unique_strings(value["subject_phrases"], "subject_phrases", _validate_subject_phrase),
        "attachment_extensions": _normalize_unique_strings(
            value["attachment_extensions"], "attachment_extensions", _validate_attachment_extension
        ),
        "bootstrap_days": bootstrap_days,
        "source_contract_id": source_contract_id,
        "test_only": value["test_only"],
    }


def _or_group(terms: Sequence[str]) -> str:
    return terms[0] if len(terms) == 1 else "{" + " ".join(terms) + "}"


def build_gmail_list_query(value: Any) -> str:
    """Compile a deterministic, narrow Gmail ``users.messages.list`` query."""

    rule = validate_query_rule(value)
    sender_clause = _or_group(["from:%s" % address for address in rule["sender_addresses"]])
    subject_clause = _or_group(['subject:"%s"' % phrase for phrase in rule["subject_phrases"]])
    extension_clause = _or_group(["filename:%s" % extension for extension in rule["attachment_extensions"]])
    return " ".join(
        (
            sender_clause,
            subject_clause,
            "has:attachment",
            extension_clause,
            "newer_than:%dd" % rule["bootstrap_days"],
            "-in:trash",
        )
    )


def validate_query_rules_document(value: Any) -> list[str]:
    """Return errors rather than raising so the independent oracle can report all faults."""

    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["document_not_mapping"]
    expected = {
        "schema_version",
        "artifact_id",
        "requirement_id",
        "acceptance_contract_id",
        "product_version",
        "status",
        "authorization_contract",
        "query_contract",
        "method_policy",
        "claim_boundary",
    }
    if set(value) != expected:
        errors.append("document_fields_not_exact")
    if value.get("schema_version") != "1.0.0":
        errors.append("schema_version_invalid")
    if value.get("artifact_id") != "ART-S06-P01-02":
        errors.append("artifact_id_invalid")
    if value.get("requirement_id") != "REQ-S06-P01":
        errors.append("requirement_id_invalid")
    if value.get("acceptance_contract_id") != "AC-S06-P01":
        errors.append("acceptance_contract_id_invalid")
    if value.get("product_version") != VERSION:
        errors.append("product_version_invalid")
    if value.get("status") != "FROZEN_NO_PRODUCTION_SENDER_RULES":
        errors.append("status_invalid")
    authorization = value.get("authorization_contract")
    expected_authorization = {
        "scope_uri": GMAIL_SCOPE,
        "scope_short_name": GMAIL_SCOPE_SHORT_NAME,
        "one_time_human_consent_required": True,
        "missing_consent_action": "DISABLE_GMAIL_CONTINUE_CORE",
        "authorization_endpoint": GOOGLE_AUTHORIZATION_ENDPOINT,
        "response_type": OAUTH_RESPONSE_TYPE,
        "access_type": OAUTH_ACCESS_TYPE,
        "include_granted_scopes": False,
        "pkce_method": PKCE_METHOD,
        "state_storage": "SERVER_SIDE_SINGLE_USE_EPHEMERAL",
    }
    if authorization != expected_authorization:
        errors.append("authorization_contract_invalid")
    query = value.get("query_contract")
    expected_query = {
        "gmail_method": "users.messages.list",
        "bootstrap_lookback_days": 30,
        "production_rules": [],
        "production_enablement": "DISABLED_UNTIL_VERIFIED_SENDER_SUBJECT_ATTACHMENT_CONTRACT",
        "required_rule_fields": [
            "id",
            "sender_addresses",
            "subject_phrases",
            "attachment_extensions",
            "bootstrap_days",
            "source_contract_id",
            "test_only",
        ],
        "attachment_type_enforcement_stage": "S06_P03_AFTER_FETCH",
        "cursor_type": "GMAIL_HISTORY_ID_AND_ARCHIVE_KEY_SET",
        "idempotency_material": "gmail_message_id + attachment_id + sha256",
        "same_attachment_identity_changed_hash_action": "QUARANTINE_AND_DO_NOT_TRASH",
        "unknown_sender_action": "QUARANTINE_AND_DO_NOT_TRASH",
        "gmail_mutation_in_p01": "PROHIBITED_QUEUE_DECISION_ONLY",
        "real_time_soak_gate": "NONE",
    }
    if query != expected_query:
        errors.append("query_contract_invalid")
    method_policy = value.get("method_policy")
    if method_policy != {"allowed_methods": list(ALLOWED_GMAIL_METHODS), "denied_methods": list(DENIED_GMAIL_METHODS)}:
        errors.append("method_policy_invalid")
    expected_boundary = {
        "gmail_account_or_api_accessed": False,
        "token_or_client_secret_stored_in_repository": False,
        "gmail_mutation_performed": False,
        "production_query_enabled": False,
        "core_deployment_waits_for_real_time_soak": False,
        "real_order_submitted_or_retried": False,
        "financial_return_verified_or_guaranteed": False,
    }
    if value.get("claim_boundary") != expected_boundary:
        errors.append("claim_boundary_invalid")
    return errors


def _validate_identifier(value: Any, field: str) -> str:
    identifier = _require_string(value, field, maximum=128)
    if not _MESSAGE_OR_ATTACHMENT_ID_RE.fullmatch(identifier):
        raise CursorIntegrityError("%s is malformed" % field)
    return identifier


def _validate_sha256(value: Any, field: str) -> str:
    digest = _require_string(value, field, minimum=64, maximum=64)
    if not _SHA256_RE.fullmatch(digest):
        raise CursorIntegrityError("%s must be a lowercase SHA-256" % field)
    return digest


def normalize_attachment_record(value: Any) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise CursorIntegrityError("attachment record must be a mapping")
    _strict_keys(value, {"gmail_message_id", "attachment_id", "content_sha256"}, "attachment record")
    return {
        "gmail_message_id": _validate_identifier(value["gmail_message_id"], "gmail_message_id"),
        "attachment_id": _validate_identifier(value["attachment_id"], "attachment_id"),
        "content_sha256": _validate_sha256(value["content_sha256"], "content_sha256"),
    }


def attachment_identity(value: Mapping[str, Any]) -> str:
    normalized = normalize_attachment_record(value)
    return "%s/%s" % (normalized["gmail_message_id"], normalized["attachment_id"])


def archive_idempotency_key(value: Mapping[str, Any]) -> str:
    normalized = normalize_attachment_record(value)
    return _sha256(_json_bytes(normalized))


def empty_cursor(query_rule_id: Any) -> Mapping[str, Any]:
    rule_id = _require_string(query_rule_id, "query_rule_id", maximum=80)
    if not _RULE_ID_RE.fullmatch(rule_id):
        raise CursorIntegrityError("query_rule_id is malformed")
    return {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "query_rule_id": rule_id,
        "history_id": None,
        "processed_archive_keys": [],
        "attachment_hashes": {},
    }


def _validate_history_id(value: Any) -> str:
    history_id = _require_string(value, "history_id", maximum=39)
    if not _HISTORY_ID_RE.fullmatch(history_id):
        raise CursorIntegrityError("history_id must be a non-negative decimal identifier")
    return history_id


def validate_cursor(value: Any, *, query_rule_id: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CursorIntegrityError("cursor must be a mapping")
    expected_rule_id = _require_string(query_rule_id, "query_rule_id", maximum=80)
    _strict_keys(
        value,
        {"schema_version", "query_rule_id", "history_id", "processed_archive_keys", "attachment_hashes"},
        "cursor",
    )
    if value["schema_version"] != CURSOR_SCHEMA_VERSION or value["query_rule_id"] != expected_rule_id:
        raise CursorIntegrityError("cursor schema or rule binding is invalid")
    history_id = value["history_id"]
    if history_id is not None:
        history_id = _validate_history_id(history_id)
    keys = value["processed_archive_keys"]
    if not isinstance(keys, list) or any(not isinstance(key, str) or not _SHA256_RE.fullmatch(key) for key in keys):
        raise CursorIntegrityError("processed_archive_keys is invalid")
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        raise CursorIntegrityError("processed_archive_keys must be sorted and unique")
    hashes = value["attachment_hashes"]
    if not isinstance(hashes, Mapping):
        raise CursorIntegrityError("attachment_hashes is invalid")
    normalized_hashes: dict[str, str] = {}
    for identity, digest in hashes.items():
        if not isinstance(identity, str) or identity.count("/") != 1:
            raise CursorIntegrityError("attachment identity is invalid")
        message_id, attachment_id = identity.split("/", 1)
        record = {
            "gmail_message_id": _validate_identifier(message_id, "gmail_message_id"),
            "attachment_id": _validate_identifier(attachment_id, "attachment_id"),
            "content_sha256": _validate_sha256(digest, "content_sha256"),
        }
        if archive_idempotency_key(record) not in keys:
            raise CursorIntegrityError("attachment_hashes has no matching processed archive key")
        normalized_hashes[identity] = record["content_sha256"]
    if list(hashes) != sorted(hashes):
        raise CursorIntegrityError("attachment_hashes must be in deterministic key order")
    return {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "query_rule_id": expected_rule_id,
        "history_id": history_id,
        "processed_archive_keys": list(keys),
        "attachment_hashes": normalized_hashes,
    }


def advance_cursor(
    cursor: Any,
    *,
    query_rule: Any,
    history_id: Any,
    attachment_records: Any,
) -> Mapping[str, Any]:
    """Classify one scan without persisting data or mutating Gmail.

    A repeated identical scan returns no new archive key.  A changed hash for a
    stable Gmail message/attachment identity is suspicious and fails closed.
    """

    rule = validate_query_rule(query_rule)
    current = validate_cursor(cursor, query_rule_id=rule["id"])
    incoming_history_id = _validate_history_id(history_id)
    if current["history_id"] is not None and int(incoming_history_id) < int(current["history_id"]):
        raise CursorIntegrityError("history_id moved backwards")
    if not isinstance(attachment_records, list):
        raise CursorIntegrityError("attachment_records must be a list")
    records = sorted(
        (normalize_attachment_record(row) for row in attachment_records),
        key=lambda row: (row["gmail_message_id"], row["attachment_id"], row["content_sha256"]),
    )
    processed = set(current["processed_archive_keys"])
    attachment_hashes = dict(current["attachment_hashes"])
    new_keys: list[str] = []
    duplicate_keys: list[str] = []
    for record in records:
        identity = attachment_identity(record)
        old_hash = attachment_hashes.get(identity)
        if old_hash is not None and old_hash != record["content_sha256"]:
            raise CursorIntegrityError("attachment identity changed content hash")
        key = archive_idempotency_key(record)
        if key in processed:
            duplicate_keys.append(key)
            continue
        processed.add(key)
        attachment_hashes[identity] = record["content_sha256"]
        new_keys.append(key)
    next_history_id = incoming_history_id
    if current["history_id"] is not None:
        next_history_id = str(max(int(incoming_history_id), int(current["history_id"])))
    next_cursor = {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "query_rule_id": rule["id"],
        "history_id": next_history_id,
        "processed_archive_keys": sorted(processed),
        "attachment_hashes": {key: attachment_hashes[key] for key in sorted(attachment_hashes)},
    }
    validate_cursor(next_cursor, query_rule_id=rule["id"])
    return {
        "status": "QUEUE_DECISION_ONLY",
        "new_archive_keys": sorted(new_keys),
        "duplicate_archive_keys": sorted(duplicate_keys),
        "cursor": next_cursor,
        "gmail_mutation_performed": False,
        "real_time_soak_wait_required": False,
    }


def validate_token_storage_config(value: Any) -> Mapping[str, Path | str]:
    if not isinstance(value, Mapping):
        raise TokenStorageError("token storage config must be a mapping")
    _strict_keys(value, {"age_binary", "recipient", "token_path", "repository_root"}, "token storage config")
    age_binary = _require_string(value["age_binary"], "age_binary", maximum=1024)
    recipient = _require_string(value["recipient"], "recipient", maximum=256)
    token_path = _require_string(value["token_path"], "token_path", maximum=4096)
    repository_root = _require_string(value["repository_root"], "repository_root", maximum=4096)
    if not Path(age_binary).is_absolute():
        raise TokenStorageError("age_binary must be an absolute trusted host path")
    if not _AGE_RECIPIENT_RE.fullmatch(recipient):
        raise TokenStorageError("recipient must be an age public recipient")
    resolved_token_path = Path(token_path).expanduser().resolve()
    resolved_repository_root = Path(repository_root).expanduser().resolve()
    if not resolved_token_path.is_absolute() or not resolved_repository_root.is_absolute():
        raise TokenStorageError("secret paths must be absolute")
    if resolved_token_path.suffix != ".age":
        raise TokenStorageError("encrypted token path must use the .age suffix")
    try:
        resolved_token_path.relative_to(resolved_repository_root)
    except ValueError:
        pass
    else:
        raise TokenStorageError("token storage inside the repository is prohibited")
    return {
        "age_binary": Path(age_binary),
        "recipient": recipient,
        "token_path": resolved_token_path,
        "repository_root": resolved_repository_root,
    }


def _default_age_runner(arguments: Sequence[str], input_bytes: bytes) -> AgeProcessResult:
    try:
        result = subprocess.run(
            list(arguments),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=AGE_PROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return AgeProcessResult(returncode=1, stdout=b"")
    return AgeProcessResult(returncode=result.returncode, stdout=result.stdout)


AgeRunner = Callable[[Sequence[str], bytes], AgeProcessResult]


def encrypt_token_bytes(value: Any, token_storage: Any, runner: AgeRunner = _default_age_runner) -> bytes:
    if not isinstance(value, bytes) or not value or len(value) > MAX_TOKEN_BYTES:
        raise TokenStorageError("token plaintext is absent or outside the permitted size")
    config = validate_token_storage_config(token_storage)
    result = runner((str(config["age_binary"]), "-r", str(config["recipient"])), value)
    if not isinstance(result, AgeProcessResult) or result.returncode != 0:
        raise TokenStorageError("token encryption failed")
    if not result.stdout.startswith(AGE_HEADER) or value in result.stdout:
        raise TokenStorageError("encrypted token payload is invalid")
    return bytes(result.stdout)


def _atomic_write_secret(path: Path, ciphertext: bytes) -> None:
    if not ciphertext.startswith(AGE_HEADER):
        raise TokenStorageError("refusing to store a non-age payload")
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=".abd-gmail-token-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, TOKEN_FILE_MODE)
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(ciphertext)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, TOKEN_FILE_MODE)
    except Exception as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise TokenStorageError("encrypted token write failed") from exc


def store_encrypted_token(value: Any, token_storage: Any, runner: AgeRunner = _default_age_runner) -> Mapping[str, Any]:
    """Encrypt and atomically store token bytes without returning their path or contents."""

    config = validate_token_storage_config(token_storage)
    ciphertext = encrypt_token_bytes(value, token_storage, runner)
    _atomic_write_secret(config["token_path"], ciphertext)
    mode = os.stat(config["token_path"]).st_mode & 0o777
    if mode != TOKEN_FILE_MODE:
        raise TokenStorageError("encrypted token permissions are not 0600")
    return {
        "status": "VERIFIED_ENCRYPTED",
        "ciphertext_sha256": _sha256(ciphertext),
        "file_mode": "0600",
        "token_or_path_exposed": False,
        "repository_written": False,
    }


def validate_no_real_time_soak() -> Mapping[str, Any]:
    """Expose the release invariant without treating observation time as proof."""

    return {
        "real_time_soak_required": REAL_TIME_SOAK_REQUIRED,
        "core_deployment_behavior_when_gmail_unconfigured": "CONTINUE_WITH_GMAIL_DISABLED",
        "immediate_gates": [
            "EXACT_SCOPE",
            "PKCE_AND_STATE",
            "OUTSIDE_REPOSITORY_ENCRYPTION",
            "QUERY_ALLOWLIST",
            "CURSOR_INTEGRITY",
        ],
    }
