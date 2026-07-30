"""Clean-room Owner-private loopback Sidecar for a visible Douyin batch.

This is deliberately not a wrapper for a downloader, crawler, browser profile,
or cookie source. The Chrome Side Panel supplies one already-sanitized,
currently-visible 20-item facts envelope after an explicit gesture. The private
Sidecar revalidates that envelope over one nonce-bound loopback exchange, emits
only the adapter's small sanitized batch shape, and exits. It makes no platform
request, does not page/scroll/retry, and has no persistent storage surface.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import select
import stat
import subprocess
import sys
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, Literal

from x2n_contracts import ErrorCode

from .douyin_upstream import DouyinBatch, DouyinItem, SidecarBuildAttestation
from .runtime import RuntimePaths, X2NRuntimeError


PROVISION_CONFIRMATION = "PROVISION_X2N_DOUYIN_VISIBLE_SIDECAR"
PROTOCOL_VERSION = "1.0.0"
HEALTH_SCHEMA = "x2n-douyin-visible-sidecar-health-1.0"
REQUEST_SCHEMA = "x2n-douyin-visible-sidecar-request-1.0"
ENVELOPE_SCHEMA = "x2n-douyin-visible-sidecar-envelope-1.0"
BATCH_SCHEMA = "x2n-douyin-visible-sidecar-batch-1.0"
IMPLEMENTATION = {"kind": "x2n_clean_room_visible_dom", "upstream_runtime": False}
MAX_BATCH_ITEMS = 20
MAX_REQUEST_BYTES = 128 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_STARTUP_SECONDS = 5.0
MAX_ACTION_SECONDS = 15.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FORBIDDEN_VALUE = re.compile(r"(?:https?|file|data)://|(?:^|[\s\"'])/(?:Users|home|private|var|tmp)/", re.I)
_FORBIDDEN_KEYS = frozenset({"cookie", "credential", "header", "raw", "token", "url", "path"})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_object(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Douyin visible Sidecar {label} shape is invalid")
    return value


def _safe_text(value: Any, *, label: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 500
        or value != " ".join(value.split())
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or _FORBIDDEN_VALUE.search(value)
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"Douyin visible Sidecar {label} is unsafe")
    return value


def _require_digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, f"Douyin visible Sidecar {label} digest is invalid")
    return value


def _reject_forbidden_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = key.lower() if isinstance(key, str) else ""
            if (
                not isinstance(key, str)
                or lowered in _FORBIDDEN_KEYS
                or lowered.endswith("_url")
                or lowered.endswith("_path")
            ):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar message has a forbidden field")
            _reject_forbidden_tree(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_tree(item)
    elif isinstance(value, str) and _FORBIDDEN_VALUE.search(value):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar message has an unsafe value")


def _decode_json(payload: bytes) -> Mapping[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    if len(payload) > MAX_RESPONSE_BYTES:
        raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Douyin visible Sidecar response is too large")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin visible Sidecar returned invalid JSON") from error
    if not isinstance(value, Mapping):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin visible Sidecar response root is invalid")
    _reject_forbidden_tree(value)
    return value


@dataclass(frozen=True)
class VisibleBatchRequest:
    mode: Literal["favorites", "likes"]
    sequence: int
    visible_batch: Mapping[str, Any]
    max_items: int = MAX_BATCH_ITEMS

    def __post_init__(self) -> None:
        if self.mode not in {"favorites", "likes"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin visible Sidecar mode is invalid")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence != 0:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar sequence is invalid")
        if self.max_items != MAX_BATCH_ITEMS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar batch limit is invalid")
        _validate_visible_batch(self.visible_batch)


def _validate_visible_batch(value: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    root = _strict_object(
        value,
        {"batch", "code", "errors", "items", "platform", "schema_version", "status"},
        label="visible batch",
    )
    if root["platform"] != "douyin" or root["schema_version"] != "1.0" or root["status"] != "ready":
        raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar batch is not ready")
    if root["code"] is not None or root["errors"] != []:
        raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar batch has error evidence")
    batch = _strict_object(
        root["batch"],
        {"automatic_scroll", "completion_signal", "explicit_owner_action", "visible_card_count"},
        label="visible batch boundary",
    )
    if batch != {
        "automatic_scroll": False,
        "completion_signal": "bounded_limit_reached",
        "explicit_owner_action": True,
        "visible_card_count": MAX_BATCH_ITEMS,
    }:
        raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar boundary is incomplete")
    if not isinstance(root["items"], list) or len(root["items"]) != MAX_BATCH_ITEMS:
        raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar item count is invalid")
    items: list[dict[str, Any]] = []
    identities: set[str] = set()
    for item in root["items"]:
        row = _strict_object(item, {"content_id", "content_type", "title"}, label="visible item")
        content_id = row["content_id"]
        if not isinstance(content_id, str) or _SAFE_ID.fullmatch(content_id) is None or content_id in identities:
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar item identity is invalid")
        if row["content_type"] not in {"image_gallery", "unknown", "video"}:
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar item type is invalid")
        title = _safe_text(row["title"], label="item title", optional=True)
        identities.add(content_id)
        items.append({"content_id": content_id, "content_type": row["content_type"], "title": title})
    return tuple(items)


def _health(build: SidecarBuildAttestation) -> dict[str, Any]:
    return {
        "build": build.safe_dict(),
        "capabilities": {
            "favorites": True,
            "likes": True,
            "max_items_per_action": MAX_BATCH_ITEMS,
            "visible_dom_input": True,
        },
        "execution": {
            "account_state_change": False,
            "automatic_pagination": False,
            "automatic_retry": False,
            "automatic_scroll": False,
            "owner_action_only": True,
            "platform_network": False,
        },
        "implementation": dict(IMPLEMENTATION),
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": HEALTH_SCHEMA,
        "storage": {"cookies": False, "database": False, "json": False, "media": False, "paths": False},
    }


def _parse_health(value: Any, *, expected_build: SidecarBuildAttestation) -> None:
    health = _strict_object(
        value,
        {"build", "capabilities", "execution", "implementation", "protocol_version", "schema_version", "storage"},
        label="health",
    )
    if health["schema_version"] != HEALTH_SCHEMA or health["protocol_version"] != PROTOCOL_VERSION:
        raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Douyin visible Sidecar protocol mismatch")
    if health["implementation"] != IMPLEMENTATION:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar implementation is not clean-room")
    if health["capabilities"] != {
        "favorites": True,
        "likes": True,
        "max_items_per_action": MAX_BATCH_ITEMS,
        "visible_dom_input": True,
    }:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar capability boundary mismatch")
    if health["storage"] != {"cookies": False, "database": False, "json": False, "media": False, "paths": False}:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar persistence boundary mismatch")
    if health["execution"] != {
        "account_state_change": False,
        "automatic_pagination": False,
        "automatic_retry": False,
        "automatic_scroll": False,
        "owner_action_only": True,
        "platform_network": False,
    }:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar execution boundary mismatch")
    build_value = _strict_object(
        health["build"],
        {"executable_sha256", "resolved_lock_sha256", "sbom_sha256", "scope", "transitive_license_report_sha256"},
        label="build attestation",
    )
    build = SidecarBuildAttestation(
        scope=build_value["scope"],
        executable_sha256=_require_digest(build_value["executable_sha256"], label="executable"),
        resolved_lock_sha256=_require_digest(build_value["resolved_lock_sha256"], label="resolved lock"),
        sbom_sha256=_require_digest(build_value["sbom_sha256"], label="SBOM"),
        transitive_license_report_sha256=_require_digest(
            build_value["transitive_license_report_sha256"], label="transitive license report"
        ),
    )
    if build.scope != "owner_private_build" or build != expected_build:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin visible Sidecar build attestation mismatch")


def _parse_envelope(
    value: Mapping[str, Any], *, request: VisibleBatchRequest, expected_build: SidecarBuildAttestation
) -> DouyinBatch:
    envelope = _strict_object(value, {"batch", "health", "schema_version"}, label="envelope")
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Douyin visible Sidecar envelope mismatch")
    _parse_health(envelope["health"], expected_build=expected_build)
    batch = _strict_object(
        envelope["batch"],
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
        label="batch",
    )
    if (
        batch["schema_version"] != BATCH_SCHEMA
        or batch["mode"] != request.mode
        or batch["sequence"] != request.sequence
        or batch["max_items"] != request.max_items
        or batch["automatic_pagination"] is not False
        or batch["completion_signal"] != "bounded_limit_reached"
        or batch["status"] != "ready"
        or batch["errors"] != []
        or not isinstance(batch["items"], list)
        or len(batch["items"]) != MAX_BATCH_ITEMS
    ):
        raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar batch is incomplete")
    source_items = _validate_visible_batch(request.visible_batch)
    expected_items = [
        {
            "collection": None,
            "content_id": item["content_id"],
            "content_type": item["content_type"],
            "title": item["title"],
        }
        for item in source_items
    ]
    if batch["items"] != expected_items:
        raise X2NRuntimeError(
            ErrorCode.DATA_INTEGRITY_FAILED, "Douyin visible Sidecar batch is not bound to the visible input"
        )
    items = tuple(
        DouyinItem(
            content_id=item["content_id"],
            content_type=item["content_type"],
            title=item["title"],
            collection=None,
        )
        for item in source_items
    )
    return DouyinBatch(
        mode=request.mode,
        sequence=request.sequence,
        status="ready",
        completion_signal="bounded_limit_reached",
        items=items,
        error_codes=(),
        upstream_error_count=0,
    )


def _sidecar_source() -> bytes:
    """Return the self-contained stdlib worker copied into the private bundle."""

    return (
        textwrap.dedent(
            r"""#!/usr/bin/env python3
import argparse
import json
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

MAX_ITEMS = 20
MAX_REQUEST_BYTES = 128 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FORBIDDEN = re.compile(r"(?:https?|file|data)://|(?:^|[\s\"'])/(?:Users|home|private|var|tmp)/", re.I)

def strict_object(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("shape")
    return value

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result

def parse_json(raw):
    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique_pairs,
                      parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("constant")))

def safe_title(value):
    if value is None:
        return None
    if (not isinstance(value, str) or not value or len(value) > 500
            or value != " ".join(value.split())
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or FORBIDDEN.search(value)):
        raise ValueError("title")
    return value

def visible_items(value):
    root = strict_object(value, {"batch", "code", "errors", "items", "platform", "schema_version", "status"})
    if root["platform"] != "douyin" or root["schema_version"] != "1.0" or root["status"] != "ready":
        raise ValueError("status")
    if root["code"] is not None or root["errors"] != []:
        raise ValueError("errors")
    if strict_object(root["batch"], {"automatic_scroll", "completion_signal", "explicit_owner_action", "visible_card_count"}) != {
        "automatic_scroll": False, "completion_signal": "bounded_limit_reached",
        "explicit_owner_action": True, "visible_card_count": MAX_ITEMS,
    }:
        raise ValueError("boundary")
    if not isinstance(root["items"], list) or len(root["items"]) != MAX_ITEMS:
        raise ValueError("items")
    seen = set()
    items = []
    for value in root["items"]:
        row = strict_object(value, {"content_id", "content_type", "title"})
        content_id = row["content_id"]
        if not isinstance(content_id, str) or not SAFE_ID.fullmatch(content_id) or content_id in seen:
            raise ValueError("identity")
        if row["content_type"] not in {"image_gallery", "unknown", "video"}:
            raise ValueError("type")
        seen.add(content_id)
        items.append({"collection": None, "content_id": content_id, "content_type": row["content_type"],
                      "title": safe_title(row["title"])})
    return items

def health(build):
    return {
        "build": build,
        "capabilities": {"favorites": True, "likes": True, "max_items_per_action": MAX_ITEMS, "visible_dom_input": True},
        "execution": {"account_state_change": False, "automatic_pagination": False, "automatic_retry": False,
                      "automatic_scroll": False, "owner_action_only": True, "platform_network": False},
        "implementation": {"kind": "x2n_clean_room_visible_dom", "upstream_runtime": False},
        "protocol_version": "1.0.0",
        "schema_version": "x2n-douyin-visible-sidecar-health-1.0",
        "storage": {"cookies": False, "database": False, "json": False, "media": False, "paths": False},
    }

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--ready-fd", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not isinstance(args.nonce, str) or len(args.nonce) < 32:
        return 2
    try:
        build = parse_json(args.build.encode("utf-8"))
        strict_object(build, {"executable_sha256", "resolved_lock_sha256", "sbom_sha256", "scope", "transitive_license_report_sha256"})
        if build["scope"] != "owner_private_build":
            return 2
    except Exception:
        return 2

    class Handler(BaseHTTPRequestHandler):
        server_version = ""
        sys_version = ""
        def log_message(self, *_args):
            return
        def _send(self, status, value):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            if self.client_address[0] != "127.0.0.1" or self.path != "/x2n/v1/batch":
                self._send(403, {"error": "blocked"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if length < 1 or length > MAX_REQUEST_BYTES:
                    raise ValueError("length")
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("content-type")
                request = parse_json(self.rfile.read(length))
                row = strict_object(request, {"action", "automatic_pagination", "automatic_scroll", "change_account_state",
                                              "explicit_owner_action", "max_items", "mode", "nonce", "schema_version",
                                              "sequence", "visible_batch"})
                if (row["action"] != "batch" or row["schema_version"] != "x2n-douyin-visible-sidecar-request-1.0"
                        or row["nonce"] != args.nonce or row["mode"] not in {"favorites", "likes"}
                        or row["sequence"] != 0 or row["max_items"] != MAX_ITEMS
                        or row["explicit_owner_action"] is not True or row["automatic_pagination"] is not False
                        or row["automatic_scroll"] is not False or row["change_account_state"] is not False):
                    raise ValueError("request")
                items = visible_items(row["visible_batch"])
                self._send(200, {
                    "batch": {"automatic_pagination": False, "completion_signal": "bounded_limit_reached", "errors": [],
                              "items": items, "max_items": MAX_ITEMS, "mode": row["mode"],
                              "schema_version": "x2n-douyin-visible-sidecar-batch-1.0", "sequence": 0, "status": "ready"},
                    "health": health(build), "schema_version": "x2n-douyin-visible-sidecar-envelope-1.0",
                })
                self.server.served = True
            except Exception:
                self._send(400, {"error": "invalid"})
    try:
        server = HTTPServer(("127.0.0.1", args.port), Handler)
        server.timeout = 0.25
        server.served = False
        os = __import__("os")
        os.write(args.ready_fd, b"1")
        os.close(args.ready_fd)
        deadline = __import__("time").monotonic() + 15.0
        while not server.served and __import__("time").monotonic() < deadline:
            server.handle_request()
        server.server_close()
        return 0 if server.served else 3
    except Exception:
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
"""
        )
        .lstrip()
        .encode("utf-8")
    )


def clean_room_sidecar_artifacts() -> dict[str, tuple[bytes, int]]:
    """Return the exact four files permitted in the private Sidecar bundle."""

    sidecar = _sidecar_source()
    executable_sha256 = _sha256_bytes(sidecar)
    resolved_lock = (
        _canonical_json(
            {
                "implementation": IMPLEMENTATION["kind"],
                "runtime_dependencies": ["python-stdlib"],
                "schema_version": "1.0",
                "sidecar_sha256": executable_sha256,
            }
        ).encode("utf-8")
        + b"\n"
    )
    sbom = (
        _canonical_json(
            {
                "bomFormat": "CycloneDX",
                "components": [
                    {
                        "hashes": [{"alg": "SHA-256", "content": executable_sha256}],
                        "name": "x2n-douyin-visible-sidecar",
                        "type": "application",
                        "version": PROTOCOL_VERSION,
                    },
                    {"licenses": [{"license": {"id": "PSF-2.0"}}], "name": "python-stdlib", "type": "framework"},
                ],
                "specVersion": "1.5",
            }
        ).encode("utf-8")
        + b"\n"
    )
    licenses = (
        _canonical_json(
            {
                "components": [
                    {"license": "Proprietary", "name": "x2n-douyin-visible-sidecar", "runtime_dependency": False},
                    {"license": "PSF-2.0", "name": "python-stdlib", "runtime_dependency": True},
                ],
                "schema_version": "1.0",
            }
        ).encode("utf-8")
        + b"\n"
    )
    return {
        "sidecar": (sidecar, 0o700),
        "resolved-lock.json": (resolved_lock, 0o600),
        "sbom.cdx.json": (sbom, 0o600),
        "transitive-licenses.json": (licenses, 0o600),
    }


def clean_room_sidecar_build() -> SidecarBuildAttestation:
    """Return the expected attestation for the only production Sidecar implementation."""

    artifacts = clean_room_sidecar_artifacts()
    return SidecarBuildAttestation(
        scope="owner_private_build",
        executable_sha256=_sha256_bytes(artifacts["sidecar"][0]),
        resolved_lock_sha256=_sha256_bytes(artifacts["resolved-lock.json"][0]),
        sbom_sha256=_sha256_bytes(artifacts["sbom.cdx.json"][0]),
        transitive_license_report_sha256=_sha256_bytes(artifacts["transitive-licenses.json"][0]),
    )


def _write_private_file(path: Path, content: bytes, *, mode: int) -> None:
    if path.exists() or path.is_symlink():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar destination already exists")
    temporary = path.with_name(f".{path.name}.x2n-{token_urlsafe(12)}")
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        os.write(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        path.chmod(mode)
    except OSError as error:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar bundle cannot be written") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def provision_owner_private_visible_sidecar(
    paths: RuntimePaths,
    *,
    confirmation: str,
) -> SidecarBuildAttestation:
    """Create the fixed owner-only clean-room bundle, never a crawler runtime."""

    if confirmation != PROVISION_CONFIRMATION:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar provisioning confirmation is missing")
    directory = paths.ensure_private_directory("runtime/sidecars/douyin/current")
    artifacts = clean_room_sidecar_artifacts()
    expected = tuple(artifacts)
    if any((directory / name).exists() or (directory / name).is_symlink() for name in expected):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar bundle already exists")
    if any(entry.name not in expected for entry in directory.iterdir()):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar bundle directory is not empty")
    for filename, (content, mode) in artifacts.items():
        _write_private_file(directory / filename, content, mode=mode)
    return clean_room_sidecar_build()


class OwnerPrivateVisibleSidecarClient:
    """Start one clean-room loopback process and exchange exactly one batch."""

    def __init__(self, paths: RuntimePaths, *, expected_build: SidecarBuildAttestation, port: int) -> None:
        if expected_build.scope != "owner_private_build":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar build is not Owner-private")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65_535:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin visible Sidecar loopback port is invalid")
        self._paths = paths
        self._expected_build = expected_build
        self._port = port

    def _start(self) -> tuple[subprocess.Popen[bytes], str]:
        sidecar = self._paths.douyin_sidecar_bundle_directory / "sidecar"
        if (
            sidecar.is_symlink()
            or not sidecar.is_file()
            or stat.S_IMODE(sidecar.stat().st_mode) != 0o700
            or sidecar.stat().st_uid != os.getuid()
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin visible Sidecar executable is unsafe")
        nonce = token_urlsafe(32)
        read_fd, write_fd = os.pipe()
        build_json = _canonical_json(self._expected_build.safe_dict())
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(sidecar),
                    "--port",
                    str(self._port),
                    "--nonce",
                    nonce,
                    "--build",
                    build_json,
                    "--ready-fd",
                    str(write_fd),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                },
                close_fds=True,
                pass_fds=(write_fd,),
                start_new_session=True,
            )
        except OSError as error:
            os.close(read_fd)
            os.close(write_fd)
            raise X2NRuntimeError(
                ErrorCode.DEPENDENCY_MISSING, "Douyin visible Sidecar process is unavailable"
            ) from error
        os.close(write_fd)
        try:
            ready, _, _ = select.select([read_fd], [], [], MAX_STARTUP_SECONDS)
            if not ready or os.read(read_fd, 1) != b"1":
                raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Douyin visible Sidecar did not become ready")
        except OSError as error:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Douyin visible Sidecar readiness failed") from error
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
        finally:
            os.close(read_fd)
        return process, nonce

    def _exchange(self, request: VisibleBatchRequest, *, nonce: str) -> Mapping[str, Any]:
        payload = _canonical_json(
            {
                "action": "batch",
                "automatic_pagination": False,
                "automatic_scroll": False,
                "change_account_state": False,
                "explicit_owner_action": True,
                "max_items": request.max_items,
                "mode": request.mode,
                "nonce": nonce,
                "schema_version": REQUEST_SCHEMA,
                "sequence": request.sequence,
                "visible_batch": dict(request.visible_batch),
            }
        ).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin visible Sidecar request is too large")
        connection = http.client.HTTPConnection("127.0.0.1", self._port, timeout=MAX_ACTION_SECONDS)
        try:
            connection.request(
                "POST",
                "/x2n/v1/batch",
                body=payload,
                headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
            )
            response = connection.getresponse()
            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise X2NRuntimeError(
                    ErrorCode.SECURITY_INJECTION_BLOCKED, "Douyin visible Sidecar response is too large"
                )
            if response.status != 200 or content_type != "application/json":
                raise X2NRuntimeError(
                    ErrorCode.PROVENANCE_INCOMPLETE, "Douyin visible Sidecar rejected the visible batch"
                )
            return _decode_json(body)
        except (TimeoutError, ConnectionError, OSError, http.client.HTTPException) as error:
            raise X2NRuntimeError(
                ErrorCode.NETWORK_FAILED, "Douyin visible Sidecar loopback exchange failed"
            ) from error
        finally:
            connection.close()

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        try:
            return_code = process.wait(timeout=MAX_STARTUP_SECONDS)
            if return_code != 0:
                raise X2NRuntimeError(ErrorCode.UNKNOWN_FAILURE, "Douyin visible Sidecar exited with a failure")
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise X2NRuntimeError(
                ErrorCode.NETWORK_FAILED, "Douyin visible Sidecar did not stop after one action"
            ) from None

    def fetch_owner_batch(self, request: VisibleBatchRequest) -> tuple[dict[str, str], DouyinBatch]:
        process, nonce = self._start()
        try:
            value = self._exchange(request, nonce=nonce)
            batch = _parse_envelope(value, request=request, expected_build=self._expected_build)
            self._stop(process)
            return {"implementation": IMPLEMENTATION["kind"]}, batch
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
