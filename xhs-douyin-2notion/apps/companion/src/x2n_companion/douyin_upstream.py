"""Strict boundary for an owner-managed, pinned Douyin sidecar.

The audited upstream CLI/REST API is deliberately not called directly.  A private
sidecar must first remove URLs, paths, credentials, raw metadata and upstream
storage identities, then attest the exact approved source/build.  This module only
accepts that small protocol and never retries or follows pagination automatically.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import selectors
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from x2n_contracts import ErrorCode

from .runtime import X2NRuntimeError


TASK_ID = "TSK.x2n.adapters.004"
UPSTREAM_REPOSITORY = "jiji262/douyin-downloader"
UPSTREAM_COMMIT = "ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7"
UPSTREAM_TREE = "ff7774b618f269fcdc750e17dc63612f159b6b46"
UPSTREAM_VERSION = "2.0.0"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_ENTRYPOINT = "douyin-dl=cli.main:main"
PROTOCOL_VERSION = "1.0.0"
HEALTH_SCHEMA = "x2n-douyin-sidecar-health-1.0"
REQUEST_SCHEMA = "x2n-douyin-sidecar-request-1.0"
BATCH_SCHEMA = "x2n-douyin-sidecar-batch-1.0"
ENVELOPE_SCHEMA = "x2n-douyin-sidecar-envelope-1.0"
INTEGRATION_LOCK_ID = "LOCK.X2N.DOUYIN-DOWNLOADER.001"
MAX_BATCH_ITEMS = 20
MAX_RESPONSE_BYTES = 256 * 1024
MAX_STDERR_BYTES = 16 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
COLLECTION_KEY = re.compile(r"^x2ncol_[0-9a-f]{32}$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
LOCAL_PATH = re.compile(r"(?:^|[\s\"'])(?:/(?:Users|home|private|var|tmp)/|[A-Za-z]:[\\/])")
URL_LIKE = re.compile(r"(?:https?|file|ftp|data)://", flags=re.IGNORECASE)
FORBIDDEN_KEYS = frozenset(
    {
        "aweme_id",
        "credential",
        "database_id",
        "download_addr",
        "file",
        "file_path",
        "headers",
        "metadata",
        "path",
        "play_addr",
        "primary_key",
        "raw",
        "sec_uid",
        "token",
        "uri",
        "url",
    }
)

Mode = Literal["favorites", "likes"]
BatchStatus = Literal[
    "ready",
    "partial",
    "auth_required",
    "empty_unverified",
    "platform_changed",
    "rate_limited",
    "upstream_error",
]
CompletionSignal = Literal["bounded_limit_reached", "more_available", "unknown"]
AttestationScope = Literal["ci_synthetic", "owner_private_build"]

SIDECAR_ERROR_MAP: dict[str, ErrorCode] = {
    "AUTH_EXPIRED": ErrorCode.ADAPTER_AUTH_EXPIRED,
    "DEPENDENCY_MISSING": ErrorCode.DEPENDENCY_MISSING,
    "EMPTY_UNVERIFIED": ErrorCode.PROVENANCE_INCOMPLETE,
    "NETWORK_FAILED": ErrorCode.NETWORK_FAILED,
    "PARTIAL_ITEM": ErrorCode.PROVENANCE_INCOMPLETE,
    "PLATFORM_CHANGED": ErrorCode.PLATFORM_CHANGED,
    "RATE_LIMITED": ErrorCode.RATE_LIMITED,
    "UNKNOWN_FAILURE": ErrorCode.UNKNOWN_FAILURE,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


INTEGRATION_CONTRACT_BASIS = {
    "batch_schema": BATCH_SCHEMA,
    "commit": UPSTREAM_COMMIT,
    "envelope_schema": ENVELOPE_SCHEMA,
    "health_schema": HEALTH_SCHEMA,
    "lock_id": INTEGRATION_LOCK_ID,
    "protocol_version": PROTOCOL_VERSION,
    "repository": UPSTREAM_REPOSITORY,
    "tree": UPSTREAM_TREE,
    "version": UPSTREAM_VERSION,
}
INTEGRATION_CONTRACT_SHA256 = _sha256_text(_canonical_json(INTEGRATION_CONTRACT_BASIS))


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Douyin synthetic attestation fixture is missing") from None


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SYNTHETIC_FIXTURE_ROOT = _PROJECT_ROOT / "packages/test-fixtures/adapters/v1/douyin_upstream"


def _synthetic_attestation_digests() -> dict[str, str]:
    """Read CI-only fixture evidence only when a synthetic sidecar is requested.

    Importing the adapter is also needed by the private Native Host's typed
    capability registry.  That registry must be able to verify the adapter
    class without requiring a test-only fixture to be installed beside the
    production runtime bundle.
    """

    return {
        "executable_sha256": _file_sha256(_PROJECT_ROOT / "scripts/douyin_sidecar_fixture_worker.py"),
        "resolved_lock_sha256": _file_sha256(_SYNTHETIC_FIXTURE_ROOT / "resolved-lock.json"),
        "sbom_sha256": _file_sha256(_SYNTHETIC_FIXTURE_ROOT / "sbom.cdx.json"),
        "transitive_license_report_sha256": _file_sha256(_SYNTHETIC_FIXTURE_ROOT / "transitive-licenses.json"),
    }


def _strict_object(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, f"Douyin {label} shape is invalid")
    return value


def _strict_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Douyin {label} must be an array")
    return value


def _safe_text(value: Any, *, label: str, optional: bool = False, maximum: int = 500) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or CONTROL.search(value)
        or URL_LIKE.search(value)
        or LOCAL_PATH.search(value)
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"Douyin {label} contains unsafe text")
    return value


def _safe_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Douyin {label} is invalid")
    return value


def _digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, f"Douyin {label} digest is invalid")
    return value


def _reject_forbidden_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Douyin response key is invalid")
            lowered = key.lower()
            if lowered in FORBIDDEN_KEYS or lowered.endswith("_url") or lowered.endswith("_path"):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin response contains a forbidden field")
            _reject_forbidden_tree(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden_tree(item)
    elif isinstance(value, str) and (URL_LIKE.search(value) or LOCAL_PATH.search(value) or CONTROL.search(value)):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin response contains a forbidden value")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Douyin response contains a duplicate field")
        result[key] = value
    return result


def decode_response(payload: bytes) -> Mapping[str, Any]:
    if len(payload) > MAX_RESPONSE_BYTES:
        raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Douyin sidecar response is too large")
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
        )
    except X2NRuntimeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sidecar returned invalid JSON") from None
    if not isinstance(value, Mapping):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sidecar response root is invalid")
    _reject_forbidden_tree(value)
    return value


@dataclass(frozen=True)
class SidecarBuildAttestation:
    scope: AttestationScope
    executable_sha256: str
    resolved_lock_sha256: str
    transitive_license_report_sha256: str
    sbom_sha256: str

    def __post_init__(self) -> None:
        if self.scope not in {"ci_synthetic", "owner_private_build"}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar attestation scope is invalid")
        for label in (
            "executable_sha256",
            "resolved_lock_sha256",
            "transitive_license_report_sha256",
            "sbom_sha256",
        ):
            _digest(getattr(self, label), label=label)

    def safe_dict(self) -> dict[str, str]:
        return {
            "executable_sha256": self.executable_sha256,
            "resolved_lock_sha256": self.resolved_lock_sha256,
            "sbom_sha256": self.sbom_sha256,
            "scope": self.scope,
            "transitive_license_report_sha256": self.transitive_license_report_sha256,
        }


def synthetic_attestation() -> SidecarBuildAttestation:
    return SidecarBuildAttestation(scope="ci_synthetic", **_synthetic_attestation_digests())


@dataclass(frozen=True)
class DouyinHealth:
    build: SidecarBuildAttestation

    def safe_dict(self) -> dict[str, Any]:
        return {
            "build": self.build.safe_dict(),
            "integration_contract_sha256": INTEGRATION_CONTRACT_SHA256,
            "integration_lock_id": INTEGRATION_LOCK_ID,
            "persistence_writes": 0,
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": HEALTH_SCHEMA,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_tree": UPSTREAM_TREE,
            "upstream_version": UPSTREAM_VERSION,
        }


@dataclass(frozen=True)
class DouyinBatchRequest:
    mode: Mode
    sequence: int
    max_items: int = MAX_BATCH_ITEMS
    explicit_owner_action: Literal[True] = True
    automatic_pagination: Literal[False] = False
    change_account_state: Literal[False] = False

    def __post_init__(self) -> None:
        if self.mode not in {"favorites", "likes"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin mode is invalid")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sequence is invalid")
        if (
            not isinstance(self.max_items, int)
            or isinstance(self.max_items, bool)
            or not 1 <= self.max_items <= MAX_BATCH_ITEMS
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin batch size exceeds the Owner boundary")
        if (
            self.explicit_owner_action is not True
            or self.automatic_pagination is not False
            or self.change_account_state is not False
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin batch requires an explicit bounded action")

    def wire(self) -> dict[str, Any]:
        return {
            "action": "batch",
            "automatic_pagination": self.automatic_pagination,
            "change_account_state": self.change_account_state,
            "explicit_owner_action": self.explicit_owner_action,
            "max_items": self.max_items,
            "mode": self.mode,
            "schema_version": REQUEST_SCHEMA,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class DouyinCollection:
    key: str
    name_private: str

    def __post_init__(self) -> None:
        if COLLECTION_KEY.fullmatch(self.key) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin collection key is not an x2n stable hash")
        _safe_text(self.name_private, label="collection name")

    def facts(self) -> dict[str, str]:
        return {"key": self.key, "name_private": self.name_private}


@dataclass(frozen=True)
class DouyinItem:
    content_id: str
    content_type: Literal["image_gallery", "unknown", "video"]
    title: str | None
    collection: DouyinCollection | None

    def __post_init__(self) -> None:
        _safe_id(self.content_id, label="content identity")
        if self.content_type not in {"image_gallery", "unknown", "video"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin content type is invalid")
        _safe_text(self.title, label="title", optional=True)

    def facts(self) -> dict[str, Any]:
        return {
            "collection": None if self.collection is None else self.collection.facts(),
            "content_id": self.content_id,
            "content_type": self.content_type,
            "title": self.title,
        }


@dataclass(frozen=True)
class DouyinBatch:
    mode: Mode
    sequence: int
    status: BatchStatus
    completion_signal: CompletionSignal
    items: tuple[DouyinItem, ...]
    error_codes: tuple[ErrorCode, ...]
    upstream_error_count: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "automatic_pagination": False,
            "completion_signal": self.completion_signal,
            "error_codes": [item.value for item in self.error_codes],
            "item_count": len(self.items),
            "mode": self.mode,
            "sequence": self.sequence,
            "status": self.status,
            "upstream_error_count": self.upstream_error_count,
        }


class DouyinTransport(Protocol):
    def exchange(self, request: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]: ...


class SubprocessDouyinTransport:
    """One JSON request/response per no-shell child process with bounded pipes."""

    def __init__(self, command: Sequence[str], *, working_directory: Path | None = None) -> None:
        if (
            not isinstance(command, Sequence)
            or isinstance(command, (str, bytes))
            or not command
            or any(
                not isinstance(part, str) or not part or "\x00" in part or "\n" in part or "\r" in part
                for part in command
            )
        ):
            raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Douyin sidecar command is invalid")
        if working_directory is not None and (not working_directory.is_absolute() or working_directory.is_symlink()):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar working directory is invalid")
        self._command = tuple(command)
        self._working_directory = working_directory

    def exchange(self, request: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]:
        if not 0 < timeout_seconds <= 60:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar timeout is invalid")
        payload = (_canonical_json(dict(request)) + "\n").encode("utf-8")
        if len(payload) > 16 * 1024:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sidecar request is too large")
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            process = subprocess.Popen(
                self._command,
                cwd=self._working_directory,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
        except OSError:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Douyin sidecar process is unavailable") from None
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        try:
            process.stdin.write(payload)
            process.stdin.close()
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            streams = {"stdout": bytearray(), "stderr": bytearray()}
            deadline = time.monotonic() + timeout_seconds
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(self._command[0], timeout_seconds)
                events = selector.select(timeout=remaining)
                if not events:
                    raise subprocess.TimeoutExpired(self._command[0], timeout_seconds)
                for key, _mask in events:
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    target = streams[str(key.data)]
                    target.extend(chunk)
                    limit = MAX_RESPONSE_BYTES if key.data == "stdout" else MAX_STDERR_BYTES
                    if len(target) > limit:
                        raise X2NRuntimeError(
                            ErrorCode.SECURITY_INJECTION_BLOCKED,
                            "Douyin sidecar output exceeded its safe boundary",
                        )
            return_code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise X2NRuntimeError(ErrorCode.NETWORK_FAILED, "Douyin sidecar request timed out") from None
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
            process.stderr.close()
        if return_code != 0:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FAILURE, "Douyin sidecar exited with a failure")
        return decode_response(bytes(streams["stdout"]))


class LoopbackRestDouyinTransport:
    """POST-only protocol transport restricted to numeric loopback and fixed paths."""

    def __init__(self, port: int) -> None:
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65_535:
            raise X2NRuntimeError(ErrorCode.URL_REJECTED, "Douyin loopback port is invalid")
        self._port = port

    def exchange(self, request: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]:
        if not 0 < timeout_seconds <= 60:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar timeout is invalid")
        action = request.get("action")
        path = "/x2n/v1/health" if action == "health" else "/x2n/v1/batch" if action == "batch" else None
        if path is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sidecar action is invalid")
        body = _canonical_json(dict(request)).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self._port, timeout=timeout_seconds)
        try:
            connection.request(
                "POST",
                path,
                body=body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    parsed_length = int(length)
                except ValueError:
                    raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sidecar length is invalid") from None
                if parsed_length < 0 or parsed_length > MAX_RESPONSE_BYTES:
                    raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Douyin sidecar response is too large")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Douyin sidecar response is too large")
            if response.status != 200:
                code = {
                    401: ErrorCode.ADAPTER_AUTH_EXPIRED,
                    429: ErrorCode.RATE_LIMITED,
                    502: ErrorCode.NETWORK_FAILED,
                    503: ErrorCode.NETWORK_FAILED,
                    504: ErrorCode.NETWORK_FAILED,
                }.get(response.status, ErrorCode.UNKNOWN_FAILURE)
                raise X2NRuntimeError(code, "Douyin sidecar REST request failed")
            if (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/json":
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin sidecar content type is invalid")
            return decode_response(payload)
        except (TimeoutError, ConnectionError, OSError, http.client.HTTPException):
            raise X2NRuntimeError(ErrorCode.NETWORK_FAILED, "Douyin sidecar REST transport failed") from None
        finally:
            connection.close()


def health_request() -> dict[str, str]:
    return {"action": "health", "schema_version": REQUEST_SCHEMA}


def parse_health(
    value: Any,
    *,
    expected_build: SidecarBuildAttestation,
    allow_synthetic: bool,
) -> DouyinHealth:
    health = _strict_object(
        value,
        {
            "build",
            "capabilities",
            "execution",
            "integration_contract_sha256",
            "integration_lock_id",
            "protocol_version",
            "schema_version",
            "storage",
            "upstream",
        },
        "health",
    )
    if health["schema_version"] != HEALTH_SCHEMA or health["protocol_version"] != PROTOCOL_VERSION:
        raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Douyin sidecar protocol version mismatch")
    if health["integration_lock_id"] != INTEGRATION_LOCK_ID:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin integration lock mismatch")
    if health["integration_contract_sha256"] != INTEGRATION_CONTRACT_SHA256:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin integration contract digest mismatch")
    upstream = _strict_object(
        health["upstream"], {"commit", "entrypoint", "license", "repository", "tree", "version"}, "upstream pin"
    )
    if upstream != {
        "commit": UPSTREAM_COMMIT,
        "entrypoint": UPSTREAM_ENTRYPOINT,
        "license": UPSTREAM_LICENSE,
        "repository": UPSTREAM_REPOSITORY,
        "tree": UPSTREAM_TREE,
        "version": UPSTREAM_VERSION,
    }:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin upstream pin or license mismatch")
    capabilities = _strict_object(
        health["capabilities"], {"collections", "favorites", "likes", "max_items_per_action"}, "capabilities"
    )
    if capabilities != {"collections": True, "favorites": True, "likes": True, "max_items_per_action": 20}:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar capability boundary mismatch")
    storage = _strict_object(
        health["storage"], {"cookies", "database", "json", "manifest", "media", "paths"}, "storage"
    )
    if any(storage.values()) or any(not isinstance(item, bool) for item in storage.values()):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar persistence is not disabled")
    execution = _strict_object(
        health["execution"],
        {"account_state_change", "automatic_pagination", "automatic_retry", "owner_action_only"},
        "execution",
    )
    if execution != {
        "account_state_change": False,
        "automatic_pagination": False,
        "automatic_retry": False,
        "owner_action_only": True,
    }:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar execution boundary mismatch")
    build_value = _strict_object(
        health["build"],
        {"executable_sha256", "resolved_lock_sha256", "sbom_sha256", "scope", "transitive_license_report_sha256"},
        "build attestation",
    )
    build = SidecarBuildAttestation(
        scope=build_value["scope"],
        executable_sha256=_digest(build_value["executable_sha256"], label="executable"),
        resolved_lock_sha256=_digest(build_value["resolved_lock_sha256"], label="resolved lock"),
        transitive_license_report_sha256=_digest(
            build_value["transitive_license_report_sha256"], label="transitive license report"
        ),
        sbom_sha256=_digest(build_value["sbom_sha256"], label="SBOM"),
    )
    if build != expected_build:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin sidecar build attestation mismatch")
    if build.scope == "ci_synthetic" and not allow_synthetic:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic Douyin sidecar cannot run in Owner scope")
    return DouyinHealth(build=build)


def _parse_item(value: Any, *, mode: Mode) -> DouyinItem:
    row = _strict_object(value, {"collection", "content_id", "content_type", "title"}, "item")
    collection_value = row["collection"]
    collection: DouyinCollection | None
    if collection_value is None:
        collection = None
    else:
        collection_row = _strict_object(collection_value, {"key", "name_private"}, "collection")
        collection = DouyinCollection(
            key=_safe_id(collection_row["key"], label="collection key"),
            name_private=_safe_text(collection_row["name_private"], label="collection name") or "",
        )
    if mode == "likes" and collection is not None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin likes cannot carry a collection")
    return DouyinItem(
        content_id=_safe_id(row["content_id"], label="content identity"),
        content_type=row["content_type"],
        title=_safe_text(row["title"], label="title", optional=True),
        collection=collection,
    )


def parse_batch(value: Any, *, request: DouyinBatchRequest) -> DouyinBatch:
    batch = _strict_object(
        value,
        {
            "automatic_pagination",
            "completion_signal",
            "errors",
            "items",
            "max_items",
            "mode",
            "schema_version",
            "sequence",
            "status",
        },
        "batch",
    )
    if batch["schema_version"] != BATCH_SCHEMA:
        raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Douyin batch Schema mismatch")
    if (
        not isinstance(batch["sequence"], int)
        or isinstance(batch["sequence"], bool)
        or not isinstance(batch["max_items"], int)
        or isinstance(batch["max_items"], bool)
    ):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin batch numeric fields are invalid")
    if (
        batch["mode"] != request.mode
        or batch["sequence"] != request.sequence
        or batch["max_items"] != request.max_items
        or batch["automatic_pagination"] is not False
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin batch request binding mismatch")
    status = batch["status"]
    completion = batch["completion_signal"]
    if status not in {
        "ready",
        "partial",
        "auth_required",
        "empty_unverified",
        "platform_changed",
        "rate_limited",
        "upstream_error",
    }:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin batch status is invalid")
    if completion not in {"bounded_limit_reached", "more_available", "unknown"}:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin completion signal is invalid")
    items = tuple(_parse_item(item, mode=request.mode) for item in _strict_sequence(batch["items"], "items"))
    errors: list[ErrorCode] = []
    for value in _strict_sequence(batch["errors"], "errors"):
        row = _strict_object(value, {"code"}, "error")
        code = row["code"]
        if not isinstance(code, str) or code not in SIDECAR_ERROR_MAP:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FAILURE, "Douyin sidecar error is unknown")
        errors.append(SIDECAR_ERROR_MAP[code])
    if len(items) > request.max_items or len({item.content_id for item in items}) != len(items):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin batch item boundary is invalid")
    if status == "ready":
        if not items or errors or completion == "unknown":
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin ready batch is incomplete")
    elif status == "partial":
        if not items or not errors or completion != "unknown":
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin partial batch lacks evidence")
    elif items or not errors or completion != "unknown":
        raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin blocked batch is inconsistent")
    return DouyinBatch(
        mode=request.mode,
        sequence=request.sequence,
        status=status,
        completion_signal=completion,
        items=items,
        error_codes=tuple(errors),
        upstream_error_count=len(errors),
    )


class PinnedDouyinClient:
    """Validate the exact pin/build and return one sanitized bounded batch."""

    def __init__(
        self,
        transport: DouyinTransport,
        *,
        expected_build: SidecarBuildAttestation,
        allow_synthetic: bool = False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if expected_build.scope == "ci_synthetic" and not allow_synthetic:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic Douyin build requires explicit CI scope")
        self._transport = transport
        self._expected_build = expected_build
        self._allow_synthetic = allow_synthetic
        self._timeout_seconds = timeout_seconds

    def health(self) -> DouyinHealth:
        value = self._transport.exchange(health_request(), timeout_seconds=self._timeout_seconds)
        return parse_health(value, expected_build=self._expected_build, allow_synthetic=self._allow_synthetic)

    def fetch_owner_batch(self, request: DouyinBatchRequest) -> tuple[DouyinHealth, DouyinBatch]:
        value = self._transport.exchange(request.wire(), timeout_seconds=self._timeout_seconds)
        envelope = _strict_object(value, {"batch", "health", "schema_version"}, "envelope")
        if envelope["schema_version"] != ENVELOPE_SCHEMA:
            raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Douyin envelope Schema mismatch")
        health = parse_health(
            envelope["health"], expected_build=self._expected_build, allow_synthetic=self._allow_synthetic
        )
        batch = parse_batch(envelope["batch"], request=request)
        return health, batch


@dataclass(frozen=True)
class ShadowDecision:
    status: Literal["BLOCKED_SHADOW", "PASS_PIN_UNCHANGED"]
    reasons: tuple[str, ...]

    def safe_dict(self) -> dict[str, Any]:
        return {"promotion": False, "reason_codes": list(self.reasons), "status": self.status}


def evaluate_shadow_candidate(value: Mapping[str, Any]) -> ShadowDecision:
    candidate = _strict_object(
        value,
        {
            "commit",
            "critical_files_match",
            "license",
            "protocol_version",
            "resolved_lock_sha256",
            "sbom_sha256",
            "transitive_licenses_compatible",
            "tree",
            "version",
        },
        "shadow candidate",
    )
    _digest(candidate["resolved_lock_sha256"], label="shadow resolved lock")
    _digest(candidate["sbom_sha256"], label="shadow SBOM")
    reasons: list[str] = []
    for field, expected, reason in (
        ("commit", UPSTREAM_COMMIT, "commit_changed"),
        ("tree", UPSTREAM_TREE, "tree_changed"),
        ("version", UPSTREAM_VERSION, "version_changed"),
        ("license", UPSTREAM_LICENSE, "license_changed"),
        ("protocol_version", PROTOCOL_VERSION, "protocol_changed"),
    ):
        if candidate[field] != expected:
            reasons.append(reason)
    if candidate["critical_files_match"] is not True:
        reasons.append("critical_files_changed_or_unknown")
    if candidate["transitive_licenses_compatible"] is not True:
        reasons.append("transitive_license_unknown_or_incompatible")
    if reasons:
        return ShadowDecision("BLOCKED_SHADOW", tuple(reasons))
    return ShadowDecision("PASS_PIN_UNCHANGED", ())
