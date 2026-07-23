"""Versioned sender registry and deterministic two-phase verification."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.headerregistry import AddressHeader
from email.parser import Parser
from enum import StrEnum
from typing import cast

from .gmail_discovery import HeaderSnapshot, MinimalMessage

_SCHEMA_VERSION = "moomooau.sender-registry.v1"
_VERSION = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_ENTRY_ID = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
_LOCAL_PART = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}$")
_DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_HEADER_NAME = re.compile(r"^[!-9;-~]{1,64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AUTH_METHOD = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*([A-Za-z0-9_-]+)(.*)$")
_AUTH_PROPERTY = re.compile(r"\b([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\s*=\s*(?:\"([^\"]*)\"|([^\s;]+))")
_AUTHSERV_ID = re.compile(r"^[A-Za-z0-9._-]{1,253}$")
_OPAQUE_GMAIL_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_PERMIT_SENTINEL = object()
_VERIFICATION_SENTINEL = object()


class SenderRegistryError(RuntimeError):
    """Registry or verification input failed a public-safe gate."""


class RegistryActivation(StrEnum):
    ACTIVE = "ACTIVE"
    EMPTY_PROTECTED_EVIDENCE_REQUIRED = "EMPTY_PROTECTED_EVIDENCE_REQUIRED"


class EvidenceSource(StrEnum):
    PUBLIC_PRIMARY = "PUBLIC_PRIMARY"
    PROTECTED_OWNER = "PROTECTED_OWNER"


class SenderStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class VerificationPhase(StrEnum):
    PRE_RAW = "PRE_RAW"
    PRE_M3 = "PRE_M3"


class SenderDecision(StrEnum):
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticationPolicy:
    trusted_authserv_ids: tuple[str, ...]
    dkim_domains: tuple[str, ...]
    spf_mail_from_domains: tuple[str, ...]
    dmarc_from_domains: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.trusted_authserv_ids or any(
            _AUTHSERV_ID.fullmatch(value) is None for value in self.trusted_authserv_ids
        ):
            raise SenderRegistryError("trusted authentication service IDs are invalid")
        for values in (
            self.dkim_domains,
            self.spf_mail_from_domains,
            self.dmarc_from_domains,
        ):
            if not values or any(_DOMAIN.fullmatch(value) is None for value in values):
                raise SenderRegistryError("authentication alignment domain is invalid")

    def __repr__(self) -> str:
        return "AuthenticationPolicy(<redacted exact alignment policy>)"


@dataclass(frozen=True, slots=True, repr=False)
class BusinessFingerprint:
    subject_prefixes: tuple[str, ...]
    required_headers: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.subject_prefixes and not self.required_headers:
            raise SenderRegistryError("business fingerprint has no deterministic signal")
        if len(self.subject_prefixes) > 32 or len(self.required_headers) > 16:
            raise SenderRegistryError("business fingerprint exceeds the safe limit")
        for prefix in self.subject_prefixes:
            if (
                not prefix
                or len(prefix) > 512
                or _normalize_text(prefix) != prefix
                or _has_control(prefix)
            ):
                raise SenderRegistryError("business subject prefix is invalid")
        names: set[str] = set()
        for name, value in self.required_headers:
            folded = name.casefold()
            if (
                _HEADER_NAME.fullmatch(name) is None
                or folded in names
                or not value
                or len(value) > 2048
                or _normalize_text(value) != value
                or _has_control(value)
            ):
                raise SenderRegistryError("business fingerprint header is invalid")
            names.add(folded)

    def __repr__(self) -> str:
        return "BusinessFingerprint(<redacted deterministic rules>)"

    @property
    def requested_header_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.required_headers)


@dataclass(frozen=True, slots=True, repr=False)
class SenderRegistryEntry:
    entry_id: str
    exact_address: str
    header_from_domain: str
    authentication: AuthenticationPolicy
    fingerprint: BusinessFingerprint
    evidence_source: EvidenceSource
    evidence_digest: str
    first_verified_at_utc: datetime
    last_verified_at_utc: datetime
    status: SenderStatus
    third_party: bool
    replaces_entry_id: str | None

    def __post_init__(self) -> None:
        if _ENTRY_ID.fullmatch(self.entry_id) is None:
            raise SenderRegistryError("sender registry entry ID is invalid")
        canonical_address, domain = _canonical_address(self.exact_address)
        if canonical_address != self.exact_address or domain != self.header_from_domain:
            raise SenderRegistryError("sender registry exact address is not canonical")
        if domain not in self.authentication.dmarc_from_domains:
            raise SenderRegistryError("sender domain is absent from DMARC alignment policy")
        if _SHA256.fullmatch(self.evidence_digest) is None:
            raise SenderRegistryError("sender evidence digest is invalid")
        first_offset = self.first_verified_at_utc.utcoffset()
        last_offset = self.last_verified_at_utc.utcoffset()
        if (
            self.first_verified_at_utc.tzinfo is None
            or self.last_verified_at_utc.tzinfo is None
            or first_offset is None
            or last_offset is None
            or first_offset.total_seconds() != 0
            or last_offset.total_seconds() != 0
            or self.first_verified_at_utc.astimezone(UTC)
            > self.last_verified_at_utc.astimezone(UTC)
        ):
            raise SenderRegistryError("sender verification timestamps are invalid")
        if self.third_party and not self.fingerprint.required_headers:
            raise SenderRegistryError("third-party sender requires an exact business header")
        if (
            self.replaces_entry_id is not None
            and _ENTRY_ID.fullmatch(self.replaces_entry_id) is None
        ):
            raise SenderRegistryError("replacement entry ID is invalid")

    def __repr__(self) -> str:
        return (
            "SenderRegistryEntry(entry_id=<redacted>, exact_address=<redacted>, "
            f"status={self.status.value!r}, third_party={self.third_party})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class SenderRegistry:
    registry_version: str
    issued_at_utc: datetime
    activation: RegistryActivation
    entries: tuple[SenderRegistryEntry, ...]
    digest: str

    def __post_init__(self) -> None:
        if (
            _VERSION.fullmatch(self.registry_version) is None
            or _SHA256.fullmatch(self.digest) is None
        ):
            raise SenderRegistryError("sender registry identity is invalid")
        issued_offset = self.issued_at_utc.utcoffset()
        if (
            self.issued_at_utc.tzinfo is None
            or issued_offset is None
            or issued_offset.total_seconds() != 0
        ):
            raise SenderRegistryError("sender registry timestamp is invalid")
        entry_ids = [entry.entry_id for entry in self.entries]
        addresses = [entry.exact_address for entry in self.entries]
        if entry_ids != sorted(entry_ids) or len(entry_ids) != len(set(entry_ids)):
            raise SenderRegistryError("sender registry entries must be sorted and unique")
        if len(addresses) != len(set(addresses)):
            raise SenderRegistryError("sender registry exact addresses must be unique")
        if self.activation is RegistryActivation.ACTIVE and not any(
            entry.status is SenderStatus.ACTIVE for entry in self.entries
        ):
            raise SenderRegistryError("active sender registry has no active entry")
        if self.activation is RegistryActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED and self.entries:
            raise SenderRegistryError("empty registry activation cannot contain entries")

    def __repr__(self) -> str:
        return (
            f"SenderRegistry(version={self.registry_version!r}, "
            f"activation={self.activation.value!r}, "
            f"entry_count={len(self.entries)}, digest=<redacted>)"
        )

    @classmethod
    def from_json(cls, payload: bytes) -> SenderRegistry:
        if len(payload) > 2 * 1024 * 1024:
            raise SenderRegistryError("sender registry exceeds the safe limit")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SenderRegistryError("sender registry is not valid JSON") from exc
        if not isinstance(value, dict):
            raise SenderRegistryError("sender registry must be an object")
        required = {
            "schema_version",
            "registry_version",
            "issued_at_utc",
            "activation_state",
            "entries",
        }
        if set(value) != required or value.get("schema_version") != _SCHEMA_VERSION:
            raise SenderRegistryError("sender registry schema is invalid")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list):
            raise SenderRegistryError("sender registry entries are invalid")
        try:
            return cls(
                registry_version=_require_string(value, "registry_version"),
                issued_at_utc=_parse_utc(_require_string(value, "issued_at_utc")),
                activation=RegistryActivation(_require_string(value, "activation_state")),
                entries=tuple(_parse_entry(item) for item in raw_entries),
                digest=hashlib.sha256(_canonical_json(value)).hexdigest(),
            )
        except ValueError as exc:
            raise SenderRegistryError("sender registry enum value is invalid") from exc

    @property
    def requested_header_names(self) -> tuple[str, ...]:
        names = {"From", "Subject", "Authentication-Results"}
        for entry in self.entries:
            names.update(entry.fingerprint.requested_header_names)
        return tuple(sorted(names, key=str.casefold))

    def active_entry_for(self, exact_address: str) -> SenderRegistryEntry | None:
        return next(
            (
                entry
                for entry in self.entries
                if entry.status is SenderStatus.ACTIVE and entry.exact_address == exact_address
            ),
            None,
        )


@dataclass(frozen=True, slots=True, repr=False)
class HeaderVerification:
    decision: SenderDecision
    entry_id: str | None
    reason_code: str
    verification_digest: str | None

    def __repr__(self) -> str:
        return (
            f"HeaderVerification(decision={self.decision.value!r}, entry_id=<redacted>, "
            f"reason_code={self.reason_code!r}, verification_digest=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class RawFetchPermit:
    message_id: str
    registry_version: str
    registry_digest: str
    entry_id: str
    verification_digest: str
    internal_date_ms: int
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._sentinel is not _PERMIT_SENTINEL
            or _OPAQUE_GMAIL_ID.fullmatch(self.message_id) is None
            or _VERSION.fullmatch(self.registry_version) is None
            or _SHA256.fullmatch(self.registry_digest) is None
            or _ENTRY_ID.fullmatch(self.entry_id) is None
            or _SHA256.fullmatch(self.verification_digest) is None
            or type(self.internal_date_ms) is not int
            or self.internal_date_ms < 0
        ):
            raise SenderRegistryError("raw fetch permit was not issued by the verifier")

    def __repr__(self) -> str:
        return (
            "RawFetchPermit(message_id=<redacted>, registry_version="
            f"{self.registry_version!r}, entry_id=<redacted>, "
            "verification_digest=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class MessageVerification:
    message_id: str
    internal_date_ms: int
    phase: VerificationPhase
    decision: SenderDecision
    entry_id: str | None
    reason_code: str
    registry_version: str
    registry_digest: str
    verification_digest: str | None
    raw_fetch_permit: RawFetchPermit | None
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        verified = self.decision is SenderDecision.VERIFIED
        permit_expected = self.phase is VerificationPhase.PRE_RAW and verified
        if (
            self._sentinel is not _VERIFICATION_SENTINEL
            or _OPAQUE_GMAIL_ID.fullmatch(self.message_id) is None
            or type(self.internal_date_ms) is not int
            or self.internal_date_ms < 0
            or _VERSION.fullmatch(self.registry_version) is None
            or _SHA256.fullmatch(self.registry_digest) is None
            or (self.entry_id is not None and _ENTRY_ID.fullmatch(self.entry_id) is None)
            or verified != (self.entry_id is not None and self.verification_digest is not None)
            or (
                self.verification_digest is not None
                and _SHA256.fullmatch(self.verification_digest) is None
            )
            or permit_expected != (self.raw_fetch_permit is not None)
        ):
            raise SenderRegistryError("message verification was not issued by the verifier")
        if self.raw_fetch_permit is not None and (
            self.raw_fetch_permit.message_id != self.message_id
            or self.raw_fetch_permit.internal_date_ms != self.internal_date_ms
            or self.raw_fetch_permit.registry_version != self.registry_version
            or self.raw_fetch_permit.registry_digest != self.registry_digest
            or self.raw_fetch_permit.entry_id != self.entry_id
            or self.raw_fetch_permit.verification_digest != self.verification_digest
        ):
            raise SenderRegistryError("message verification permit identity is inconsistent")

    def __repr__(self) -> str:
        return (
            "MessageVerification(message_id=<redacted>, "
            f"internal_date_ms=<redacted>, phase={self.phase.value!r}, "
            f"decision={self.decision.value!r}, "
            f"entry_id=<redacted>, reason_code={self.reason_code!r}, "
            f"registry_version={self.registry_version!r}, verification_digest=<redacted>, "
            f"raw_fetch_permit={self.raw_fetch_permit is not None})"
        )


class SenderVerifier:
    verifier_version = "sender-verifier-v1"

    def verify_headers(
        self,
        headers: HeaderSnapshot,
        registry: SenderRegistry,
    ) -> HeaderVerification:
        raw_from = headers.one("From")
        if raw_from is None:
            return HeaderVerification(
                SenderDecision.QUARANTINED, None, "FROM_NOT_EXACTLY_ONE", None
            )
        try:
            exact_address, _ = _address_from_header(raw_from)
        except SenderRegistryError:
            return HeaderVerification(SenderDecision.QUARANTINED, None, "FROM_INVALID", None)
        entry = registry.active_entry_for(exact_address)
        if entry is None:
            return HeaderVerification(SenderDecision.UNKNOWN, None, "SENDER_NOT_REGISTERED", None)
        authentication_headers = headers.all("Authentication-Results")
        if not authentication_headers:
            return HeaderVerification(
                SenderDecision.QUARANTINED,
                entry.entry_id,
                "AUTHENTICATION_RESULTS_MISSING",
                None,
            )
        try:
            authentication = _parse_authentication_results(authentication_headers)
        except SenderRegistryError:
            return HeaderVerification(
                SenderDecision.QUARANTINED,
                entry.entry_id,
                "AUTHENTICATION_RESULTS_INVALID",
                None,
            )
        if not _authentication_aligned(authentication, entry.authentication):
            return HeaderVerification(
                SenderDecision.REJECTED,
                entry.entry_id,
                "AUTHENTICATION_ALIGNMENT_FAILED",
                None,
            )
        fingerprint = _match_fingerprint(headers, entry.fingerprint)
        if fingerprint is None:
            return HeaderVerification(
                SenderDecision.REJECTED,
                entry.entry_id,
                "BUSINESS_FINGERPRINT_FAILED",
                None,
            )
        verification_digest = hashlib.sha256(
            _canonical_json(
                {
                    "entry_id": entry.entry_id,
                    "exact_address": exact_address,
                    "registry_digest": registry.digest,
                    "authentication": authentication,
                    "fingerprint": fingerprint,
                    "verifier_version": self.verifier_version,
                }
            )
        ).hexdigest()
        return HeaderVerification(
            SenderDecision.VERIFIED,
            entry.entry_id,
            "THREE_CONDITION_CONJUNCTION_PASSED",
            verification_digest,
        )

    def verify_message(
        self,
        message: MinimalMessage,
        registry: SenderRegistry,
        *,
        phase: VerificationPhase,
    ) -> MessageVerification:
        if "SENT" in message.label_ids or "DRAFT" in message.label_ids:
            header_result = HeaderVerification(
                SenderDecision.REJECTED,
                None,
                "OUTBOUND_MESSAGE_PROHIBITED",
                None,
            )
        else:
            header_result = self.verify_headers(message.headers, registry)
        permit: RawFetchPermit | None = None
        if (
            phase is VerificationPhase.PRE_RAW
            and header_result.decision is SenderDecision.VERIFIED
            and header_result.entry_id is not None
            and header_result.verification_digest is not None
        ):
            permit = RawFetchPermit(
                message_id=message.ref.message_id,
                registry_version=registry.registry_version,
                registry_digest=registry.digest,
                entry_id=header_result.entry_id,
                verification_digest=header_result.verification_digest,
                internal_date_ms=message.internal_date_ms,
                _sentinel=_PERMIT_SENTINEL,
            )
        return MessageVerification(
            message_id=message.ref.message_id,
            internal_date_ms=message.internal_date_ms,
            phase=phase,
            decision=header_result.decision,
            entry_id=header_result.entry_id,
            reason_code=header_result.reason_code,
            registry_version=registry.registry_version,
            registry_digest=registry.digest,
            verification_digest=header_result.verification_digest,
            raw_fetch_permit=permit,
            _sentinel=_VERIFICATION_SENTINEL,
        )


def double_verification_matches(
    first: MessageVerification,
    second: MessageVerification,
) -> bool:
    return (
        first.phase is VerificationPhase.PRE_RAW
        and second.phase is VerificationPhase.PRE_M3
        and first.decision is SenderDecision.VERIFIED
        and second.decision is SenderDecision.VERIFIED
        and first.raw_fetch_permit is not None
        and second.raw_fetch_permit is None
        and first.message_id == second.message_id
        and first.internal_date_ms == second.internal_date_ms
        and first.registry_version == second.registry_version
        and first.registry_digest == second.registry_digest
        and first.entry_id == second.entry_id
        and first.verification_digest == second.verification_digest
    )


def _parse_entry(value: object) -> SenderRegistryEntry:
    if not isinstance(value, dict):
        raise SenderRegistryError("sender registry entry must be an object")
    expected = {
        "entry_id",
        "exact_address",
        "header_from_domain",
        "authentication",
        "fingerprint",
        "evidence",
        "first_verified_at_utc",
        "last_verified_at_utc",
        "status",
        "third_party",
        "replaces_entry_id",
    }
    if set(value) != expected:
        raise SenderRegistryError("sender registry entry schema is invalid")
    authentication = _require_object(value, "authentication")
    fingerprint = _require_object(value, "fingerprint")
    evidence = _require_object(value, "evidence")
    if set(authentication) != {
        "trusted_authserv_ids",
        "dkim_domains",
        "spf_mail_from_domains",
        "dmarc_from_domains",
    }:
        raise SenderRegistryError("authentication policy schema is invalid")
    if set(fingerprint) != {"subject_prefixes", "required_headers"}:
        raise SenderRegistryError("business fingerprint schema is invalid")
    if set(evidence) != {"source_type", "source_digest"}:
        raise SenderRegistryError("sender evidence schema is invalid")
    raw_headers = fingerprint.get("required_headers")
    if not isinstance(raw_headers, list):
        raise SenderRegistryError("fingerprint headers are invalid")
    headers: list[tuple[str, str]] = []
    for header in raw_headers:
        if not isinstance(header, dict) or set(header) != {"name", "value"}:
            raise SenderRegistryError("fingerprint header entry is invalid")
        headers.append((_require_string(header, "name"), _require_string(header, "value")))
    third_party = value.get("third_party")
    replacement = value.get("replaces_entry_id")
    if type(third_party) is not bool or (
        replacement is not None and not isinstance(replacement, str)
    ):
        raise SenderRegistryError("sender registry flags are invalid")
    return SenderRegistryEntry(
        entry_id=_require_string(value, "entry_id"),
        exact_address=_require_string(value, "exact_address"),
        header_from_domain=_require_string(value, "header_from_domain"),
        authentication=AuthenticationPolicy(
            trusted_authserv_ids=_string_tuple(authentication, "trusted_authserv_ids"),
            dkim_domains=_domain_tuple(authentication, "dkim_domains"),
            spf_mail_from_domains=_domain_tuple(authentication, "spf_mail_from_domains"),
            dmarc_from_domains=_domain_tuple(authentication, "dmarc_from_domains"),
        ),
        fingerprint=BusinessFingerprint(
            subject_prefixes=_string_tuple(fingerprint, "subject_prefixes"),
            required_headers=tuple(headers),
        ),
        evidence_source=EvidenceSource(_require_string(evidence, "source_type")),
        evidence_digest=_require_string(evidence, "source_digest"),
        first_verified_at_utc=_parse_utc(_require_string(value, "first_verified_at_utc")),
        last_verified_at_utc=_parse_utc(_require_string(value, "last_verified_at_utc")),
        status=SenderStatus(_require_string(value, "status")),
        third_party=third_party,
        replaces_entry_id=replacement,
    )


def _address_from_header(value: str) -> tuple[str, str]:
    if "\r" in value or "\n" in value:
        raise SenderRegistryError("From header contains a line break")
    parsed = Parser(policy=policy.default).parsestr("From: " + value + "\n\n")
    header = parsed["From"]
    if (
        not isinstance(header, AddressHeader)
        or parsed.defects
        or getattr(header, "defects", False)
        or len(header.addresses) != 1
    ):
        raise SenderRegistryError("From header is not exactly one valid mailbox")
    return _canonical_address(header.addresses[0].addr_spec)


def _canonical_address(value: str) -> tuple[str, str]:
    if not value.isascii() or value.count("@") != 1 or "*" in value:
        raise SenderRegistryError("exact sender address is invalid")
    local, domain = value.rsplit("@", 1)
    canonical_domain = domain.casefold().rstrip(".")
    canonical_local = local.casefold()
    if (
        local != canonical_local
        or _LOCAL_PART.fullmatch(local) is None
        or _DOMAIN.fullmatch(canonical_domain) is None
    ):
        raise SenderRegistryError("exact sender address is invalid")
    return canonical_local + "@" + canonical_domain, canonical_domain


def _parse_authentication_results(values: tuple[str, ...]) -> list[dict[str, object]]:
    parsed: list[dict[str, object]] = []
    for value in values:
        clean = _remove_comments(value)
        segments = _split_semicolons(clean)
        if len(segments) < 2:
            raise SenderRegistryError("Authentication-Results has no result")
        authserv_tokens = segments[0].strip().split()
        if not authserv_tokens or _AUTHSERV_ID.fullmatch(authserv_tokens[0]) is None:
            raise SenderRegistryError("Authentication-Results authserv-id is invalid")
        authserv_id = authserv_tokens[0].casefold()
        for segment in segments[1:]:
            match = _AUTH_METHOD.fullmatch(segment)
            if match is None:
                raise SenderRegistryError("Authentication-Results method is invalid")
            properties: dict[str, str] = {}
            for prop in _AUTH_PROPERTY.finditer(match.group(3)):
                key = prop.group(1).casefold()
                raw_value = prop.group(2) if prop.group(2) is not None else prop.group(3)
                if raw_value is None or key in properties:
                    raise SenderRegistryError("Authentication-Results property is invalid")
                properties[key] = raw_value.casefold().rstrip(".")
            parsed.append(
                {
                    "authserv_id": authserv_id,
                    "method": match.group(1).casefold(),
                    "result": match.group(2).casefold(),
                    "properties": properties,
                }
            )
    return sorted(parsed, key=lambda item: _canonical_json(item))


def _authentication_aligned(
    results: list[dict[str, object]],
    expected: AuthenticationPolicy,
) -> bool:
    trusted = {value.casefold() for value in expected.trusted_authserv_ids}
    relevant = [item for item in results if item["authserv_id"] in trusted]
    if not relevant:
        return False
    expected_values = {
        "dkim": ("header.d", set(expected.dkim_domains)),
        "spf": ("smtp.mailfrom", set(expected.spf_mail_from_domains)),
        "dmarc": ("header.from", set(expected.dmarc_from_domains)),
    }
    for method, (property_name, domains) in expected_values.items():
        method_results = [item for item in relevant if item["method"] == method]
        if not method_results:
            return False
        for item in method_results:
            if item["result"] != "pass":
                return False
            properties = item["properties"]
            if not isinstance(properties, dict):
                return False
            identity = properties.get(property_name)
            if not isinstance(identity, str) or _identity_domain(identity) not in domains:
                return False
    return True


def _identity_domain(value: str) -> str:
    candidate = value.rsplit("@", 1)[-1].casefold().rstrip(".")
    return candidate if _DOMAIN.fullmatch(candidate) is not None else ""


def _match_fingerprint(
    headers: HeaderSnapshot,
    fingerprint: BusinessFingerprint,
) -> dict[str, object] | None:
    subject = headers.one("Subject")
    normalized_subject = _normalize_text(subject) if subject is not None else ""
    if fingerprint.subject_prefixes and not any(
        normalized_subject.casefold().startswith(prefix.casefold())
        for prefix in fingerprint.subject_prefixes
    ):
        return None
    matched_headers: list[tuple[str, str]] = []
    for name, expected in fingerprint.required_headers:
        observed = headers.one(name)
        if observed is None or _normalize_text(observed) != expected:
            return None
        matched_headers.append((name.casefold(), expected))
    return {
        "subject": normalized_subject,
        "required_headers": matched_headers,
    }


def _remove_comments(value: str) -> str:
    output: list[str] = []
    depth = 0
    quote = False
    escaped = False
    for character in value:
        if escaped:
            if depth == 0:
                output.append(character)
            escaped = False
            continue
        if character == "\\":
            escaped = True
            if depth == 0:
                output.append(character)
            continue
        if character == '"' and depth == 0:
            quote = not quote
            output.append(character)
            continue
        if not quote and character == "(":
            depth += 1
            if depth > 8:
                raise SenderRegistryError("Authentication-Results comments are too deep")
            continue
        if not quote and character == ")":
            if depth == 0:
                raise SenderRegistryError("Authentication-Results comment is unbalanced")
            depth -= 1
            continue
        if depth == 0:
            output.append(character)
    if depth or quote or escaped:
        raise SenderRegistryError("Authentication-Results syntax is unbalanced")
    return "".join(output)


def _split_semicolons(value: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    quote = False
    escaped = False
    for character in value:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\" and quote:
            current.append(character)
            escaped = True
            continue
        if character == '"':
            quote = not quote
            current.append(character)
            continue
        if character == ";" and not quote:
            segments.append("".join(current))
            current = []
        else:
            current.append(character)
    if quote or escaped:
        raise SenderRegistryError("Authentication-Results quoting is invalid")
    segments.append("".join(current))
    return segments


def _domain_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    values = _string_tuple(value, key)
    canonical = tuple(item.casefold().rstrip(".") for item in values)
    if (
        values != canonical
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise SenderRegistryError("registry domains must be canonical exact values")
    return canonical


def _string_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    raw = value.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise SenderRegistryError(f"registry {key} must be a string list")
    result = tuple(cast(list[str], raw))
    if len(result) != len(set(result)):
        raise SenderRegistryError(f"registry {key} contains duplicates")
    return result


def _require_object(value: dict[str, object], key: str) -> dict[str, object]:
    raw = value.get(key)
    if not isinstance(raw, dict):
        raise SenderRegistryError(f"registry {key} must be an object")
    return cast(dict[str, object], raw)


def _require_string(value: dict[str, object], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise SenderRegistryError(f"registry {key} must be a string")
    return raw


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SenderRegistryError("registry timestamp is invalid") from exc
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise SenderRegistryError("registry timestamp must be UTC")
    return parsed.astimezone(UTC)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
