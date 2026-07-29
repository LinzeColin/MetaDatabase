"""Task005 direct-MVP activation state and bounded execution helpers.

This module is intentionally local-first and default-deny.  It accepts only
owner-authored, owner-only private input; it never stores credentials, browser
state, arbitrary paths, platform media addresses, raw DOM or raw media.  It
does not implement a prerelease/soak/observation stage: the only states are a
bounded in-task activation, direct active MVP, and rollback/disabled.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from x2n_contracts import ErrorCode, canonical_json_sha256
from x2n_contracts.models import CapabilityFeatureFlag, CapabilityReasonCode, CapabilityTerminal, SyncScopeId

from .adapter_dispatch import CapabilityGateInputs, CapabilityRegistry, ScopeBinding
from .adapter_guard import AdapterExecutionGate
from .canonical_store import CanonicalStore
from .douyin_adapter import DouyinAdapter, DouyinBatchCoordinator
from .douyin_visible_sidecar import (
    OwnerPrivateVisibleSidecarClient,
    VisibleBatchRequest,
    clean_room_sidecar_build,
)
from .douyin_upstream import (
    DouyinBatch,
    SidecarBuildAttestation,
)
from .lifecycle import LifecycleService, PrivateDbTransport
from .markdown_sink import MARKDOWN_RENDERER_VERSION, MarkdownSink
from .runtime import RuntimePaths, X2NRuntimeError, _atomic_private_json
from .sink_projection import build_sink_projection
from .xiaohongshu_favorites import XhsFavoritesAdapter, XhsFavoritesBatch, XhsFavoritesBatchCoordinator
from .xiaohongshu_likes import XhsLikesAdapter, XhsLikesBatch, XhsLikesBatchCoordinator


TASK_ID = "TSK.x2n.assurance.005"
RELEASE_VERSION = "v0.0.0.1"
INPUT_SCHEMA_VERSION = "1.0"
STATE_SCHEMA_VERSION = "1.1"
ARM_CONFIRMATION = "ARM_X2N_OWNER_MVP_ACTIVATION"
MATERIALIZE_CONFIRMATION = "MATERIALIZE_X2N_OWNER_MVP_KNOWLEDGE_ASSETS"
SIGNOFF_CONFIRMATION = "SIGN_OFF_X2N_OWNER_MVP"
ROLLBACK_CONFIRMATION = "ROLLBACK_X2N_OWNER_MVP"
OWNER_INPUT_CONTRACT = Path(__file__).resolve().parents[4] / "docs/governance/OWNER_INPUT_CONTRACT.md"
# The Native Host is installed from the staged package tree, not from this
# repository.  It therefore cannot safely read the public Markdown contract at
# runtime.  The source lane verifies this literal against that Markdown before
# arming/tagging; the installed Host verifies only the non-secret stable digest.
OWNER_INPUT_CONTRACT_SHA256 = "b585b32349af9bf9b719fcd2e9302beb50f0bac289c1ed738772945e25b4e222"
SUPPORTED_BROWSERS = frozenset({"chrome", "chrome-for-testing", "chromium"})

MVP_SCOPE_IDS = (
    SyncScopeId.XIAOHONGSHU_FAVORITES,
    SyncScopeId.XIAOHONGSHU_LIKES,
    SyncScopeId.DOUYIN_FAVORITES,
    SyncScopeId.DOUYIN_LIKES,
)
EXTERNAL_SCOPE_IDS = (
    SyncScopeId.BILIBILI_SELECTED_COLLECTION,
    SyncScopeId.KUAISHOU_SELECTED_COLLECTION,
    SyncScopeId.WEIBO_SELECTED_COLLECTION,
    SyncScopeId.TAOBAO_SELECTED_COLLECTION,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_FORBIDDEN_KEY_PARTS = ("credential", "cookie", "header", "password", "secret", "token", "url", "path")
_FORBIDDEN_VALUE = re.compile(r"(?:https?://|file://|(?:^|[\s\"'])/(?:Users|home|private|var|tmp)/)", re.IGNORECASE)
_SIDECAR_BUNDLE_DIRECTORY_PARTS = ("runtime", "sidecars", "douyin", "current")
_SIDECAR_BUNDLE_FILES = (
    ("executable_sha256", "sidecar", 0o700, 512 * 1024 * 1024),
    ("resolved_lock_sha256", "resolved-lock.json", 0o600, 16 * 1024 * 1024),
    ("sbom_sha256", "sbom.cdx.json", 0o600, 64 * 1024 * 1024),
    ("transitive_license_report_sha256", "transitive-licenses.json", 0o600, 64 * 1024 * 1024),
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Owner input contract source is unavailable") from error


def owner_input_contract_sha256(*, verify_source: bool = False) -> str:
    """Return the packaged Owner-contract binding without requiring repo files at Host runtime."""

    if verify_source and _sha256_file(OWNER_INPUT_CONTRACT) != OWNER_INPUT_CONTRACT_SHA256:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner input contract source binding drifted")
    return OWNER_INPUT_CONTRACT_SHA256


def _strict_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, f"{label} must be an object")
    return value


def _read_owner_private_json(path: Path, *, label: str) -> dict[str, Any]:
    """Read one private JSON file without exposing its path or content."""

    if not path.exists() or path.is_symlink() or not path.is_file():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} is unavailable")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_size > 256 * 1024
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} must be owner-only")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            chunks.append(chunk)
        return _strict_json_object(b"".join(chunks), label=label)
    except OSError as error:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} cannot be read") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _owner_private_file_sha256(path: Path, *, expected_mode: int, maximum_bytes: int, label: str) -> str:
    """Hash one fixed Owner-private artifact without returning its bytes or path."""

    if not path.exists() or path.is_symlink() or not path.is_file():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} is unavailable")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != expected_mode
            or metadata.st_uid != os.getuid()
            or metadata.st_size < 1
            or metadata.st_size > maximum_bytes
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} must be an owner-only regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} cannot be read") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _require_owner_private_directory(path: Path, *, label: str) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} is unavailable")
    try:
        metadata = path.stat()
    except OSError as error:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} cannot be read") from error
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} must be owner-only")


def verify_owner_private_douyin_sidecar_bundle(
    paths: RuntimePaths,
    expected_build: SidecarBuildAttestation,
) -> dict[str, Any]:
    """Prove fixed Owner-private artifacts still match the input attestation.

    This verifies only local metadata and byte digests. It does not start a
    process, inspect a Browser Profile, contact a platform, or emit artifact
    names, paths, contents, or digests.
    """

    if expected_build.scope != "owner_private_build":
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin Sidecar bundle is not Owner-private")
    current = paths.data_root
    for part in _SIDECAR_BUNDLE_DIRECTORY_PARTS:
        current = current / part
        _require_owner_private_directory(current, label="Douyin Sidecar bundle directory")
    if current != paths.douyin_sidecar_bundle_directory:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin Sidecar bundle location drifted")
    observed: dict[str, str] = {}
    for digest_field, filename, expected_mode, maximum_bytes in _SIDECAR_BUNDLE_FILES:
        observed[digest_field] = _owner_private_file_sha256(
            current / filename,
            expected_mode=expected_mode,
            maximum_bytes=maximum_bytes,
            label="Douyin Sidecar artifact",
        )
    actual = SidecarBuildAttestation(scope="owner_private_build", **observed)
    if actual != clean_room_sidecar_build():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin Sidecar bundle is not the approved clean-room build")
    if actual != expected_build:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin Sidecar bundle attestation mismatch")
    return {"artifact_count": len(_SIDECAR_BUNDLE_FILES), "paths_emitted": False, "status": "VERIFIED"}


def _require_exact_mapping(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} shape is invalid")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} digest is invalid")
    return value


def _require_uuid(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except ValueError as error:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid") from error
    return value


def _reject_private_leak_surface(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or any(part in key.lower() for part in _FORBIDDEN_KEY_PARTS):
                raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Owner release input contains a forbidden field")
            _reject_private_leak_surface(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_leak_surface(item)
    elif isinstance(value, str) and _FORBIDDEN_VALUE.search(value):
        raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Owner release input contains an unsafe value")


@dataclass(frozen=True)
class OwnerMvpReleaseInput:
    """Strict private facts needed to open the fixed four-scope MVP boundary."""

    input_sha256: str
    douyin_port: int
    douyin_build: SidecarBuildAttestation
    external_reasons: Mapping[SyncScopeId, CapabilityReasonCode]
    model_mode: Literal["disabled", "suggestion_only"]
    scope_manifest_hashes: Mapping[SyncScopeId, frozenset[str]]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OwnerMvpReleaseInput":
        _reject_private_leak_surface(value)
        root = _require_exact_mapping(
            value,
            {
                "disabled_external_scopes",
                "douyin_sidecar",
                "enabled_scopes",
                "model_mode",
                "owner_authorization",
                "owner_input_contract_sha256",
                "owner_private_manifests",
                "project",
                "release_version",
                "rollback_target",
                "schema_version",
            },
            label="Owner MVP release input",
        )
        if (
            root["schema_version"] != INPUT_SCHEMA_VERSION
            or root["project"] != "xhs-douyin-2notion"
            or root["release_version"] != RELEASE_VERSION
            or root["owner_authorization"] != "owner_authorized_direct_mvp"
            or root["rollback_target"] != "previous_stable_or_disable"
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP release input identity is invalid")
        if _require_sha256(root["owner_input_contract_sha256"], label="Owner input contract") != owner_input_contract_sha256():
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner input contract binding drifted")
        if root["model_mode"] not in {"disabled", "suggestion_only"}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Model capability must stay disabled or suggestion-only")

        enabled = root["enabled_scopes"]
        if not isinstance(enabled, list) or len(enabled) != len(MVP_SCOPE_IDS):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Owner MVP enabled scope set is invalid")
        enabled_by_scope: dict[SyncScopeId, Mapping[str, Any]] = {}
        expected_transports = {
            SyncScopeId.XIAOHONGSHU_FAVORITES: "chrome_visible_dom",
            SyncScopeId.XIAOHONGSHU_LIKES: "chrome_visible_dom",
            SyncScopeId.DOUYIN_FAVORITES: "owner_private_loopback_sidecar",
            SyncScopeId.DOUYIN_LIKES: "owner_private_loopback_sidecar",
        }
        for row in enabled:
            item = _require_exact_mapping(row, {"max_items", "scope_id", "transport"}, label="enabled MVP scope")
            try:
                scope_id = SyncScopeId(item["scope_id"])
            except (TypeError, ValueError) as error:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Enabled MVP scope is unknown") from error
            if (
                scope_id not in expected_transports
                or type(item["max_items"]) is not int
                or item["max_items"] != 20
                or item["transport"] != expected_transports[scope_id]
                or scope_id in enabled_by_scope
            ):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Enabled MVP scope exceeds the fixed bounded contract")
            enabled_by_scope[scope_id] = item
        if tuple(enabled_by_scope) != MVP_SCOPE_IDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Enabled MVP scopes must be the fixed ordered baseline")

        private_manifests = root["owner_private_manifests"]
        if not isinstance(private_manifests, list) or len(private_manifests) != len(MVP_SCOPE_IDS):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Owner MVP private manifest set is invalid")
        scope_manifest_hashes: dict[SyncScopeId, frozenset[str]] = {}
        for row in private_manifests:
            item = _require_exact_mapping(
                row,
                {"content_id_sha256", "scope_id"},
                label="Owner MVP private manifest",
            )
            try:
                scope_id = SyncScopeId(item["scope_id"])
            except (TypeError, ValueError) as error:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Owner MVP private manifest scope is unknown") from error
            item_hashes = item["content_id_sha256"]
            if (
                scope_id not in MVP_SCOPE_IDS
                or scope_id in scope_manifest_hashes
                or not isinstance(item_hashes, list)
                or len(item_hashes) != 20
            ):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP private manifest exceeds its fixed boundary")
            normalized = frozenset(_require_sha256(value, label="Owner MVP manifest content ID") for value in item_hashes)
            if len(normalized) != 20:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP private manifest contains duplicate content IDs")
            scope_manifest_hashes[scope_id] = normalized
        if tuple(scope_manifest_hashes) != MVP_SCOPE_IDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP private manifests must match the fixed baseline")

        disabled = root["disabled_external_scopes"]
        if not isinstance(disabled, list) or len(disabled) != len(EXTERNAL_SCOPE_IDS):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "External-gate scope set is invalid")
        external_reasons: dict[SyncScopeId, CapabilityReasonCode] = {}
        allowed_reasons = {
            CapabilityReasonCode.UNKNOWN_DISABLED,
            CapabilityReasonCode.BLOCKED_POLICY,
            CapabilityReasonCode.BLOCKED_AUTH,
            CapabilityReasonCode.BLOCKED_BUDGET,
            CapabilityReasonCode.BLOCKED_CAPABILITY,
        }
        for row in disabled:
            item = _require_exact_mapping(
                row,
                {"flag_off", "live_support_claim", "platform_calls", "reason_code", "scope_id"},
                label="external-gate scope",
            )
            try:
                scope_id = SyncScopeId(item["scope_id"])
                reason = CapabilityReasonCode(item["reason_code"])
            except (TypeError, ValueError) as error:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "External-gate scope is invalid") from error
            if (
                scope_id not in EXTERNAL_SCOPE_IDS
                or scope_id in external_reasons
                or reason not in allowed_reasons
                or item["flag_off"] is not True
                or item["live_support_claim"] is not False
                or type(item["platform_calls"]) is not int
                or item["platform_calls"] != 0
            ):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "External-gate settlement is invalid")
            external_reasons[scope_id] = reason
        if tuple(external_reasons) != EXTERNAL_SCOPE_IDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "External-gate scope ordering is invalid")

        sidecar = _require_exact_mapping(root["douyin_sidecar"], {"attestation", "port"}, label="Douyin sidecar")
        if type(sidecar["port"]) is not int or not 1 <= sidecar["port"] <= 65_535:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin loopback port is invalid")
        attestation = _require_exact_mapping(
            sidecar["attestation"],
            {
                "executable_sha256",
                "resolved_lock_sha256",
                "sbom_sha256",
                "scope",
                "transitive_license_report_sha256",
            },
            label="Douyin sidecar attestation",
        )
        build = SidecarBuildAttestation(
            scope=attestation["scope"],
            executable_sha256=attestation["executable_sha256"],
            resolved_lock_sha256=attestation["resolved_lock_sha256"],
            sbom_sha256=attestation["sbom_sha256"],
            transitive_license_report_sha256=attestation["transitive_license_report_sha256"],
        )
        if build.scope != "owner_private_build":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin sidecar must be owner-private")
        return cls(
            input_sha256=canonical_json_sha256(dict(root)),
            douyin_port=sidecar["port"],
            douyin_build=build,
            external_reasons=external_reasons,
            model_mode=root["model_mode"],
            scope_manifest_hashes=scope_manifest_hashes,
        )

    def safe_summary(self) -> dict[str, Any]:
        return {
            "enabled_scope_count": len(MVP_SCOPE_IDS),
            "external_disabled_scope_count": len(EXTERNAL_SCOPE_IDS),
            "input_sha256": self.input_sha256,
            "model_mode": self.model_mode,
            "paths_emitted": False,
            "private_manifest_item_count": sum(len(items) for items in self.scope_manifest_hashes.values()),
            "private_manifest_scope_count": len(self.scope_manifest_hashes),
            "private_sidecar_attested": True,
            "release_version": RELEASE_VERSION,
        }


def load_owner_mvp_release_input(paths: RuntimePaths) -> OwnerMvpReleaseInput:
    """Load and validate the private Task005 input without arming execution."""

    return OwnerMvpReleaseInput.from_mapping(
        _read_owner_private_json(paths.owner_mvp_release_input, label="Owner MVP release input")
    )


def _validate_owner_input_contract(paths: RuntimePaths) -> None:
    """Check only the fixed non-secret gates from the Owner input contract."""

    raw = _read_owner_private_json(paths.data_root / "runtime/owner_input_contract.local.json", label="Owner input")
    root = _require_exact_mapping(
        raw,
        {
            "data_scale",
            "environment",
            "first_sync",
            "gold_set",
            "input_state",
            "media_retention",
            "models",
            "notion",
            "platforms",
            "project",
            "schema_version",
            "taxonomy",
        },
        label="Owner input",
    )
    if root["schema_version"] != "1.0" or root["project"] != "x2n" or root["input_state"] != "owner_confirmed":
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner input confirmation is missing")
    if root["first_sync"] != "owner_authorized_direct_mvp":
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner direct-MVP authorization is missing")
    platforms = _require_exact_mapping(
        root["platforms"],
        {"bilibili", "douyin", "kuaishou", "taobao", "weibo", "xiaohongshu"},
        label="Owner platform input",
    )
    for platform in ("xiaohongshu", "douyin"):
        value = _require_exact_mapping(platforms[platform], {"login_state", "real_execution_authorized"}, label="Owner platform")
        if value["login_state"] != "owner_managed_profile" or value["real_execution_authorized"] is not True:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner platform execution authorization is missing")
    for platform in ("bilibili", "kuaishou", "weibo", "taobao"):
        value = _require_exact_mapping(platforms[platform], {"login_state", "real_execution_authorized"}, label="Owner platform")
        if value["real_execution_authorized"] is not False:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "External-gate platform cannot be concurrently enabled")
    media = _require_exact_mapping(
        root["media_retention"],
        {"failure_max_hours", "persist_platform_cdn_urls", "persist_raw_media", "success"},
        label="Owner media retention",
    )
    if (
        media["success"] != "delete_immediately"
        or media["persist_platform_cdn_urls"] is not False
        or media["persist_raw_media"] is not False
        or type(media["failure_max_hours"]) is not int
        or not 0 <= media["failure_max_hours"] <= 24
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner media-retention boundary is invalid")
    taxonomy = _require_exact_mapping(root["taxonomy"], {"ai_may_create_top_level", "top_level_categories"}, label="Owner taxonomy")
    if taxonomy["ai_may_create_top_level"] is not False or not isinstance(taxonomy["top_level_categories"], list):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner taxonomy boundary is invalid")
    notion = _require_exact_mapping(root["notion"], {"credential_reference", "enabled", "parent_reference"}, label="Owner Notion")
    models = _require_exact_mapping(root["models"], {"cloud_enabled", "currency", "monthly_budget"}, label="Owner models")
    if (
        notion["enabled"] is not False
        or notion["credential_reference"] != "unset"
        or notion["parent_reference"] != "unset"
        or models["cloud_enabled"] is not False
        or models["currency"] != "AUD"
        or type(models["monthly_budget"]) not in {int, float}
        or models["monthly_budget"] != 0
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner external model or Notion boundary is invalid")


def _initial_knowledge_assets() -> dict[str, Any]:
    """Return the fail-closed post-baseline asset state.

    The direct MVP creates deterministic Markdown before a release switch.  A
    live Notion transport remains explicitly disabled until a separately
    authorized Owner configuration exists; Markdown and Canonical durability
    therefore never depend on it.
    """

    return {
        "markdown_content_count": 0,
        "markdown_library_sha256": None,
        "markdown_renderer_version": None,
        "materialized": False,
        "notion_mode": "DISABLED_OWNER_INPUT",
        "notion_platform_calls": 0,
        "private_durability_manifest_sha256": None,
    }


def _validate_knowledge_assets(value: Any) -> dict[str, Any]:
    assets = _require_exact_mapping(
        value,
        {
            "markdown_content_count",
            "markdown_library_sha256",
            "markdown_renderer_version",
            "materialized",
            "notion_mode",
            "notion_platform_calls",
            "private_durability_manifest_sha256",
        },
        label="Owner MVP knowledge assets",
    )
    materialized = assets["materialized"]
    if (
        type(materialized) is not bool
        or assets["notion_mode"] != "DISABLED_OWNER_INPUT"
        or type(assets["notion_platform_calls"]) is not int
        or assets["notion_platform_calls"] != 0
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP knowledge-asset boundary is invalid")
    if materialized:
        if (
            type(assets["markdown_content_count"]) is not int
            or assets["markdown_content_count"] < 1
            or _SHA256.fullmatch(str(assets["markdown_library_sha256"])) is None
            or assets["markdown_renderer_version"] != MARKDOWN_RENDERER_VERSION
            or _SHA256.fullmatch(str(assets["private_durability_manifest_sha256"])) is None
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP knowledge-asset proof is invalid")
    elif dict(assets) != _initial_knowledge_assets():
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP knowledge assets are partially materialized")
    return dict(assets)


def _initial_state(*, release_input: OwnerMvpReleaseInput, backup: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "baseline": {"baseline_hash": None, "passed": False, "total_relations": 0},
        "deployment": {"artifact_sha256": None, "browser": None, "online_smoke": False, "state": "not_deployed"},
        "input_sha256": release_input.input_sha256,
        "knowledge_assets": _initial_knowledge_assets(),
        "owner_signoff": False,
        "phase": "activation_armed",
        "project": "xhs-douyin-2notion",
        "release_version": RELEASE_VERSION,
        "rollback": {
            "backup_id": backup["backup_id"],
            "backup_sha256": backup["database_sha256"],
            "rehearsed": False,
        },
        "schema_version": STATE_SCHEMA_VERSION,
        "scope_jobs": {},
        "scope_receipts": {},
        "task_id": TASK_ID,
    }


def _validate_state(value: Mapping[str, Any], *, release_input: OwnerMvpReleaseInput) -> dict[str, Any]:
    state = _require_exact_mapping(
        value,
        {
            "baseline",
            "deployment",
            "input_sha256",
            "knowledge_assets",
            "owner_signoff",
            "phase",
            "project",
            "release_version",
            "rollback",
            "schema_version",
            "scope_jobs",
            "scope_receipts",
            "task_id",
        },
        label="Owner MVP release state",
    )
    if (
        state["schema_version"] != STATE_SCHEMA_VERSION
        or state["project"] != "xhs-douyin-2notion"
        or state["release_version"] != RELEASE_VERSION
        or state["task_id"] != TASK_ID
        or state["input_sha256"] != release_input.input_sha256
        or state["phase"] not in {"activation_armed", "pre_switch_ready", "active", "rolled_back"}
        or type(state["owner_signoff"]) is not bool
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP release state identity is invalid")
    baseline = _require_exact_mapping(state["baseline"], {"baseline_hash", "passed", "total_relations"}, label="baseline")
    if (
        baseline["baseline_hash"] is not None and _SHA256.fullmatch(str(baseline["baseline_hash"])) is None
    ) or type(baseline["passed"]) is not bool or type(baseline["total_relations"]) is not int:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP baseline state is invalid")
    if baseline["passed"] is True and (baseline["baseline_hash"] is None or baseline["total_relations"] != 80):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP baseline is not the exact 80-item release gate")
    knowledge_assets = _validate_knowledge_assets(state["knowledge_assets"])
    deployment = _require_exact_mapping(
        state["deployment"],
        {"artifact_sha256", "browser", "online_smoke", "state"},
        label="deployment",
    )
    if (
        deployment["state"] not in {"not_deployed", "deployed", "rolled_back"}
        or type(deployment["online_smoke"]) is not bool
        or (deployment["artifact_sha256"] is not None and _SHA256.fullmatch(str(deployment["artifact_sha256"])) is None)
        or (deployment["browser"] is not None and deployment["browser"] not in SUPPORTED_BROWSERS)
        or (deployment["state"] == "deployed" and (deployment["browser"] is None or deployment["artifact_sha256"] is None))
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP deployment state is invalid")
    rollback = _require_exact_mapping(state["rollback"], {"backup_id", "backup_sha256", "rehearsed"}, label="rollback")
    if (
        not isinstance(rollback["backup_id"], str)
        or _SAFE_TOKEN.fullmatch(rollback["backup_id"]) is None
        or _SHA256.fullmatch(str(rollback["backup_sha256"])) is None
        or type(rollback["rehearsed"]) is not bool
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP rollback state is invalid")
    for key in ("scope_jobs", "scope_receipts"):
        rows = state[key]
        if not isinstance(rows, Mapping) or any(scope not in {item.value for item in MVP_SCOPE_IDS} for scope in rows):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP scope state is invalid")
    for scope, job_id in state["scope_jobs"].items():
        _require_uuid(job_id, label=f"Owner MVP scope job {scope}")
    for scope, digest in state["scope_receipts"].items():
        _require_sha256(digest, label=f"Owner MVP scope receipt {scope}")
    if set(state["scope_jobs"]) != set(state["scope_receipts"]):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP scope receipt mapping diverged")
    if state["phase"] in {"pre_switch_ready", "active"} and (
        baseline["passed"] is not True
        or knowledge_assets["materialized"] is not True
        or rollback["rehearsed"] is not True
        or state["owner_signoff"] is not True
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP release bypassed a pre-switch gate")
    if state["phase"] == "active" and (deployment["state"] != "deployed" or deployment["online_smoke"] is not True):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP active state lacks deployment proof")
    return dict(state)


@dataclass
class MvpReleaseController:
    """Own the private state transition for the one direct owner-MVP release."""

    paths: RuntimePaths
    release_input: OwnerMvpReleaseInput
    state: dict[str, Any]

    @classmethod
    def load(cls, paths: RuntimePaths, *, require_state: bool = True) -> "MvpReleaseController | None":
        input_exists = paths.owner_mvp_release_input.exists() or paths.owner_mvp_release_input.is_symlink()
        state_exists = paths.owner_mvp_release_state.exists() or paths.owner_mvp_release_state.is_symlink()
        if not input_exists and not state_exists and not require_state:
            return None
        if not input_exists:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP release input is unavailable")
        release_input = load_owner_mvp_release_input(paths)
        if not state_exists:
            if require_state:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP release has not been armed")
            return None
        state = _validate_state(
            _read_owner_private_json(paths.owner_mvp_release_state, label="Owner MVP release state"),
            release_input=release_input,
        )
        marker = paths._validate_marker()
        expected_marker = {
            "activation_armed": (True, "stage_6_mvp_activation_armed"),
            "pre_switch_ready": (True, "stage_6_mvp_activation_armed"),
            "active": (True, "stage_6_mvp_active"),
            "rolled_back": (False, "stage_6_mvp_rollback_or_disabled"),
        }[state["phase"]]
        if (
            marker["product_execution_authorized"] is not expected_marker[0]
            or marker["real_data_state"] != expected_marker[1]
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP marker and release state diverged")
        return cls(paths=paths, release_input=release_input, state=state)

    @classmethod
    def arm(cls, paths: RuntimePaths, store: CanonicalStore, *, confirmation: str) -> "MvpReleaseController":
        if confirmation != ARM_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP activation confirmation is missing")
        owner_input_contract_sha256(verify_source=True)
        paths.ensure_private_directory("runtime/release")
        if paths.owner_mvp_release_state.exists() or paths.owner_mvp_release_state.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP activation is already armed")
        _validate_owner_input_contract(paths)
        release_input = load_owner_mvp_release_input(paths)
        verify_owner_private_douyin_sidecar_bundle(paths, release_input.douyin_build)
        backup = store.backup(label="mvp_pre_switch").safe_dict()
        state = _initial_state(release_input=release_input, backup=backup)
        _atomic_private_json(paths.owner_mvp_release_state, state)
        paths.set_mvp_execution_authorized(enabled=True, active=False)
        return cls(paths=paths, release_input=release_input, state=state)

    def _persist(self) -> None:
        _validate_state(self.state, release_input=self.release_input)
        _read_owner_private_json(self.paths.owner_mvp_release_state, label="Owner MVP release state")
        _atomic_private_json(self.paths.owner_mvp_release_state, self.state)

    def capability_registry(self) -> CapabilityRegistry:
        if self.state["phase"] not in {"activation_armed", "pre_switch_ready", "active"}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release is not active")
        inputs: dict[SyncScopeId, CapabilityGateInputs] = {}
        for scope_id in MVP_SCOPE_IDS:
            inputs[scope_id] = CapabilityGateInputs(feature_flag=CapabilityFeatureFlag.MVP_ACTIVATION_CANDIDATE)
        reason_to_kwargs = {
            CapabilityReasonCode.UNKNOWN_DISABLED: {"unknown_disabled": True},
            CapabilityReasonCode.BLOCKED_POLICY: {"blocked_policy": True},
            CapabilityReasonCode.BLOCKED_AUTH: {"blocked_auth": True},
            CapabilityReasonCode.BLOCKED_BUDGET: {"blocked_budget": True},
            CapabilityReasonCode.BLOCKED_CAPABILITY: {"blocked_capability": True},
        }
        for scope_id in EXTERNAL_SCOPE_IDS:
            inputs[scope_id] = CapabilityGateInputs(**reason_to_kwargs[self.release_input.external_reasons[scope_id]])
        return CapabilityRegistry(inputs)

    def external_gate_settlements(self, *, store: CanonicalStore | None = None) -> list[dict[str, Any]]:
        """Prove every non-enabled platform remains legally disabled.

        This is not a count-only assertion: the release checks each typed
        capability result, its permitted external reason, disabled feature
        flag, zero calls, and absent live-support claim before Owner sign-off
        and again when go-live evidence is emitted.
        """

        manifest = self.capability_registry().evaluate()
        outcomes = {outcome.scope_id: outcome for outcome in manifest.outcomes}
        if set(outcomes) != set(SyncScopeId):
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability gate snapshot is incomplete")
        persisted = None
        if store is not None:
            persisted = {outcome.scope_id: outcome for outcome in store.capability_snapshot().outcomes}
            if set(persisted) != set(SyncScopeId):
                raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Persisted capability snapshot is incomplete")
        settlements: list[dict[str, Any]] = []
        for scope_id in EXTERNAL_SCOPE_IDS:
            outcome = outcomes[scope_id]
            expected_reason = self.release_input.external_reasons[scope_id]
            if (
                outcome.terminal is not CapabilityTerminal.DISABLED_EXTERNAL_GATE
                or outcome.feature_flag is not CapabilityFeatureFlag.DISABLED
                or outcome.reason_code is not expected_reason
            ):
                raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "External-gate settlement drifted")
            if persisted is not None:
                persisted_outcome = persisted[scope_id]
                if (
                    persisted_outcome.terminal is not outcome.terminal
                    or persisted_outcome.feature_flag is not outcome.feature_flag
                    or persisted_outcome.reason_code is not outcome.reason_code
                    or persisted_outcome.evidence_hash != outcome.evidence_hash
                ):
                    raise X2NRuntimeError(
                        ErrorCode.CAPABILITY_TECHNICAL_BLOCKED,
                        "Persisted external-gate settlement drifted",
                    )
            settlements.append(
                {
                    "feature_flag": CapabilityFeatureFlag.DISABLED.value,
                    "live_support_claim": False,
                    "platform_calls": 0,
                    "reason_code": expected_reason.value,
                    "scope_id": scope_id.value,
                    "status": "PASS_DISABLED_EXTERNAL_GATE",
                }
            )
        return settlements

    def require_scope(self, scope_id: SyncScopeId) -> None:
        if self.state["phase"] not in {"activation_armed", "pre_switch_ready", "active"} or scope_id not in MVP_SCOPE_IDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP scope is not enabled")

    def scope_scan_id(self, scope_id: SyncScopeId) -> str:
        """Return the release-scoped scan identity used for idempotent writes.

        It is derived solely from the private release-input digest and fixed
        scope identifier.  It is never emitted as a public identifier and it
        lets a retried Native request replay the same adapter checkpoint rather
        than creating a second 20-item scan.
        """

        self.require_scope(scope_id)
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"x2n-owner-mvp-scan:{self.release_input.input_sha256}:{scope_id.value}",
            )
        )

    def owner_account_ref_hash(self) -> str:
        """Create one opaque release-scoped account reference without profile data."""

        return canonical_json_sha256(
            {
                "account_binding": "owner_mvp_release",
                "input_sha256": self.release_input.input_sha256,
                "task_id": TASK_ID,
            }
        )

    def ensure_scope_job(self, *, scope_id: SyncScopeId, job_id: str) -> None:
        """Reject a second logical action before it reaches an adapter."""

        self.require_scope(scope_id)
        job_id = _require_uuid(job_id, label="Owner MVP job")
        existing_job = self.state["scope_jobs"].get(scope_id.value)
        if existing_job is not None and existing_job != job_id:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP scope already completed its bounded action")

    def require_manifest_match(self, *, scope_id: SyncScopeId, content_ids: Sequence[str]) -> None:
        """Block writes unless the Owner-private 20-item manifest matches exactly."""

        self.require_scope(scope_id)
        if len(content_ids) != 20 or any(not isinstance(content_id, str) or not content_id for content_id in content_ids):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Owner MVP manifest item set is incomplete")
        observed = frozenset(hashlib.sha256(content_id.encode("utf-8")).hexdigest() for content_id in content_ids)
        if len(observed) != 20 or observed != self.release_input.scope_manifest_hashes[scope_id]:
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Owner MVP action does not match its private manifest")

    def record_scope_receipt(self, *, scope_id: SyncScopeId, job_id: str, receipt_hash: str) -> None:
        self.require_scope(scope_id)
        job_id = _require_uuid(job_id, label="Owner MVP job")
        receipt_hash = _require_sha256(receipt_hash, label="Owner MVP receipt")
        scope = scope_id.value
        existing_job = self.state["scope_jobs"].get(scope)
        existing_receipt = self.state["scope_receipts"].get(scope)
        if (existing_job, existing_receipt) not in {(None, None), (job_id, receipt_hash)}:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP scope receipt conflicts with its first action")
        self.state["scope_jobs"][scope] = job_id
        self.state["scope_receipts"][scope] = receipt_hash
        self._persist()

    def verify_baseline(self, store: CanonicalStore) -> dict[str, Any]:
        if self.state["phase"] != "activation_armed":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP baseline is not in its activation window")
        if set(self.state["scope_jobs"]) != {scope.value for scope in MVP_SCOPE_IDS}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP baseline requires all four bounded scope actions")
        scans = {scope: self.scope_scan_id(scope) for scope in MVP_SCOPE_IDS}
        snapshot = store.owner_mvp_baseline_snapshot(scope_scan_ids=scans)
        self.state["baseline"] = {
            "baseline_hash": snapshot["baseline_hash"],
            "passed": snapshot["exact_four_scope_baseline"],
            "total_relations": snapshot["total_relations"],
        }
        self._persist()
        return snapshot

    def verify_knowledge_assets(self, store: CanonicalStore) -> dict[str, Any]:
        """Re-read the post-baseline Markdown and durability proof without side effects."""

        assets = _validate_knowledge_assets(self.state["knowledge_assets"])
        if assets["materialized"] is not True:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP knowledge assets are not materialized")
        sink = MarkdownSink(store)
        manifest = sink.library_manifest()
        checked_links = sink.validate_category_links()
        canonical_content_count = len(store.projection_snapshots())
        lifecycle = store.lifecycle_state()
        if (
            manifest.content_count != canonical_content_count
            or manifest.content_count != assets["markdown_content_count"]
            or manifest.library_sha256 != assets["markdown_library_sha256"]
            or manifest.renderer_version != assets["markdown_renderer_version"]
            or checked_links != manifest.content_count
            or lifecycle.durability_state != "durability_verified"
            or lifecycle.latest_manifest_sha256 != assets["private_durability_manifest_sha256"]
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP knowledge-asset evidence drifted")
        return {
            "markdown_content_count": manifest.content_count,
            "markdown_library_sha256": manifest.library_sha256,
            "markdown_renderer_version": manifest.renderer_version,
            "notion_mode": "DISABLED_OWNER_INPUT",
            "notion_platform_calls": 0,
            "private_durability_manifest_sha256": lifecycle.latest_manifest_sha256,
        }

    def materialize_knowledge_assets(
        self,
        store: CanonicalStore,
        *,
        confirmation: str,
        private_client: PrivateDbTransport | None,
    ) -> dict[str, Any]:
        """Build Markdown and verify Private-MetaDatabase durability before sign-off.

        The Owner input contract keeps Notion explicitly disabled here, so this
        bounded release action never initiates a Notion request or treats a
        missing configuration as a successful Notion synchronization.
        """

        if confirmation != MATERIALIZE_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP knowledge-asset confirmation is missing")
        if self.state["phase"] != "activation_armed" or self.state["baseline"]["passed"] is not True:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Knowledge assets require a passing bounded MVP baseline")
        existing = _validate_knowledge_assets(self.state["knowledge_assets"])
        if existing["materialized"] is True:
            return self.verify_knowledge_assets(store)
        if private_client is None:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Approved Private-MetaDatabase client is unavailable")
        self.verify_baseline_snapshot(store)
        sink = MarkdownSink(store)
        first = sink.rebuild_from_canonical(build_sink_projection)
        second = sink.rebuild_from_canonical(build_sink_projection)
        if (
            first.manifest.content_count < 1
            or first.checked_links != first.manifest.content_count
            or second.manifest != first.manifest
            or (
                second.content_writes,
                second.category_index_writes,
                second.removed_content_files,
                second.removed_category_indexes,
            )
            != (0, 0, 0, 0)
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown rebuild is not deterministic")
        durable = LifecycleService(store).export_and_verify(private_client)
        durability = durable.get("durability")
        execution = durable.get("execution")
        attestation = durable.get("attestation")
        if (
            not isinstance(durability, Mapping)
            or durability.get("durability_state") != "durability_verified"
            or _SHA256.fullmatch(str(durability.get("latest_manifest_sha256"))) is None
            or not isinstance(execution, Mapping)
            or execution.get("platform_calls") != 0
            or execution.get("real_notion_calls") != 0
            or execution.get("token_value_contact") != 0
            or not isinstance(attestation, Mapping)
            or attestation.get("auth_mutations") != 0
            or attestation.get("client_digest_verified") is not True
            or attestation.get("token_value_contact") != 0
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private-MetaDatabase durability proof is invalid")
        self.state["knowledge_assets"] = {
            "markdown_content_count": first.manifest.content_count,
            "markdown_library_sha256": first.manifest.library_sha256,
            "markdown_renderer_version": first.manifest.renderer_version,
            "materialized": True,
            "notion_mode": "DISABLED_OWNER_INPUT",
            "notion_platform_calls": 0,
            "private_durability_manifest_sha256": durability["latest_manifest_sha256"],
        }
        self._persist()
        return self.verify_knowledge_assets(store)

    def rehearse_rollback(self, store: CanonicalStore) -> dict[str, Any]:
        if self.state["baseline"]["passed"] is not True:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Rollback rehearsal requires a passing MVP baseline")
        self.verify_knowledge_assets(store)
        receipt = store.rehearse_backup_restore(
            backup_id=self.state["rollback"]["backup_id"],
            expected_sha256=self.state["rollback"]["backup_sha256"],
        )
        self.state["rollback"]["rehearsed"] = True
        self._persist()
        return receipt

    def owner_signoff(self, store: CanonicalStore, *, confirmation: str) -> None:
        if confirmation != SIGNOFF_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP signoff confirmation is missing")
        if self.state["baseline"]["passed"] is not True or self.state["rollback"]["rehearsed"] is not True:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP pre-switch checks are incomplete")
        self.verify_knowledge_assets(store)
        self.external_gate_settlements(store=store)
        self.state["owner_signoff"] = True
        self.state["phase"] = "pre_switch_ready"
        self._persist()

    def _remove_browser_handshake(self) -> None:
        handshake = self.paths.owner_mvp_browser_handshake
        if handshake.exists() or handshake.is_symlink():
            if handshake.is_symlink() or not handshake.is_file() or stat.S_IMODE(handshake.stat().st_mode) != 0o600:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner MVP browser handshake is unsafe")
            handshake.unlink()

    def mark_deployed(self, *, artifact_sha256: str, browser: str) -> None:
        if self.state["phase"] != "pre_switch_ready":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP deployment pre-switch checks are incomplete")
        if browser not in SUPPORTED_BROWSERS:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "MVP deployment browser is unsupported")
        self._remove_browser_handshake()
        self.state["deployment"] = {
            "artifact_sha256": _require_sha256(artifact_sha256, label="release artifact"),
            "browser": browser,
            "online_smoke": False,
            "state": "deployed",
        }
        self._persist()

    def record_browser_handshake(self, *, artifact_sha256: str) -> bool:
        """Persist a no-content, staged-artifact-bound Side Panel handshake after deploy."""

        deployment = self.state["deployment"]
        if self.state["phase"] not in {"pre_switch_ready", "active"} or deployment["state"] != "deployed":
            return False
        expected_artifact_sha256 = _require_sha256(deployment["artifact_sha256"], label="release artifact")
        observed_artifact_sha256 = _require_sha256(artifact_sha256, label="Side Panel release artifact")
        if observed_artifact_sha256 != expected_artifact_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Side Panel release artifact does not match deployment")
        handshake = self.paths.owner_mvp_browser_handshake
        if handshake.exists() or handshake.is_symlink():
            self.verify_browser_handshake()
            return True
        _atomic_private_json(
            handshake,
            {
                "artifact_sha256": expected_artifact_sha256,
                "handshake_kind": "sidepanel_native_health",
                "release_version": RELEASE_VERSION,
                "schema_version": "1.0",
            },
        )
        return True

    def verify_browser_handshake(self) -> dict[str, Any]:
        deployment = self.state["deployment"]
        if self.state["phase"] not in {"pre_switch_ready", "active"} or deployment["state"] != "deployed":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP browser handshake is not eligible")
        value = _read_owner_private_json(self.paths.owner_mvp_browser_handshake, label="Owner MVP browser handshake")
        expected = {
            "artifact_sha256",
            "handshake_kind",
            "release_version",
            "schema_version",
        }
        if (
            set(value) != expected
            or value["schema_version"] != "1.0"
            or value["release_version"] != RELEASE_VERSION
            or value["handshake_kind"] != "sidepanel_native_health"
            or value["artifact_sha256"] != deployment["artifact_sha256"]
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP browser handshake is invalid")
        return {
            "browser_sidepanel_handshake": "PASS",
            "paths_emitted": False,
            "release_version": RELEASE_VERSION,
        }

    def verify_baseline_snapshot(self, store: CanonicalStore) -> dict[str, Any]:
        """Re-read the aggregate-only 80-item proof without reopening activation."""

        scans = {scope: self.scope_scan_id(scope) for scope in MVP_SCOPE_IDS}
        snapshot = store.owner_mvp_baseline_snapshot(scope_scan_ids=scans)
        baseline = self.state["baseline"]
        if (
            snapshot["exact_four_scope_baseline"] is not True
            or snapshot["total_relations"] != 80
            or baseline["passed"] is not True
            or snapshot["baseline_hash"] != baseline["baseline_hash"]
            or snapshot["total_relations"] != baseline["total_relations"]
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner MVP baseline evidence drifted")
        return snapshot

    def verify_go_live(self, store: CanonicalStore) -> dict[str, Any]:
        """Return only safe aggregate facts for the final owner-operated receipt."""

        deployment = self.state["deployment"]
        if (
            self.state["phase"] != "active"
            or deployment["state"] != "deployed"
            or deployment["online_smoke"] is not True
            or self.state["owner_signoff"] is not True
            or self.state["rollback"]["rehearsed"] is not True
            or set(self.state["scope_jobs"]) != {scope.value for scope in MVP_SCOPE_IDS}
            or set(self.state["scope_receipts"]) != {scope.value for scope in MVP_SCOPE_IDS}
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP go-live verification is incomplete")
        baseline = self.verify_baseline_snapshot(store)
        knowledge_assets = self.verify_knowledge_assets(store)
        external_gates = self.external_gate_settlements(store=store)
        return {
            "baseline_hash": baseline["baseline_hash"],
            "external_disabled_scope_count": len(external_gates),
            "external_gates": external_gates,
            "knowledge_assets": knowledge_assets,
            "model_mode": self.release_input.model_mode,
            "owner_mvp_baseline_relations": baseline["total_relations"],
            "paths_emitted": False,
            "private_manifest_item_count": sum(len(items) for items in self.release_input.scope_manifest_hashes.values()),
            "private_manifest_scope_count": len(self.release_input.scope_manifest_hashes),
            "rollback_rehearsed": True,
            "sidepanel": self.verify_browser_handshake(),
        }

    def mark_online_smoke(self) -> None:
        if self.state["deployment"]["state"] != "deployed":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP runtime is not deployed")
        self.verify_browser_handshake()
        self.state["deployment"]["online_smoke"] = True
        self.state["phase"] = "active"
        self._persist()
        self.paths.set_mvp_execution_authorized(enabled=True, active=True)

    def rollback_disable(self, *, confirmation: str) -> None:
        if confirmation != ROLLBACK_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP rollback confirmation is missing")
        self._remove_browser_handshake()
        self.state["deployment"] = {
            "artifact_sha256": None,
            "browser": self.state["deployment"]["browser"],
            "online_smoke": False,
            "state": "rolled_back",
        }
        self.state["phase"] = "rolled_back"
        self._persist()
        self.paths.set_mvp_execution_authorized(enabled=False)

    def safe_status(self) -> dict[str, Any]:
        return {
            "baseline": {
                "passed": self.state["baseline"]["passed"],
                "total_relations": self.state["baseline"]["total_relations"],
            },
            "deployment": dict(self.state["deployment"]),
            "external_disabled_scope_count": len(EXTERNAL_SCOPE_IDS),
            "knowledge_assets": {
                "markdown_content_count": self.state["knowledge_assets"]["markdown_content_count"],
                "materialized": self.state["knowledge_assets"]["materialized"],
                "notion_mode": self.state["knowledge_assets"]["notion_mode"],
                "private_durability_verified": self.state["knowledge_assets"]["private_durability_manifest_sha256"]
                is not None,
            },
            "model_mode": self.release_input.model_mode,
            "owner_signoff": self.state["owner_signoff"],
            "phase": self.state["phase"],
            "private_manifest_item_count": sum(len(items) for items in self.release_input.scope_manifest_hashes.values()),
            "private_manifest_scope_count": len(self.release_input.scope_manifest_hashes),
            "release_version": RELEASE_VERSION,
            "rollback_rehearsed": self.state["rollback"]["rehearsed"],
            "scope_action_count": len(self.state["scope_jobs"]),
        }


class MvpActivationExecutor:
    """Execute precisely one owner-selected Task005 scope action."""

    def __init__(self, controller: MvpReleaseController, store: CanonicalStore) -> None:
        self.controller = controller
        self.store = store

    @staticmethod
    def _clock() -> tuple[datetime, float]:
        return datetime.now(timezone.utc).replace(microsecond=0), time.time()

    @staticmethod
    def _require_exact_batch(batch: XhsFavoritesBatch | XhsLikesBatch | DouyinBatch) -> None:
        if (
            batch.status != "ready"
            or len(batch.items) != 20
            or batch.completion_signal != "bounded_limit_reached"
        ):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Owner MVP action did not produce exactly 20 verified items")

    def _execute_xhs(self, *, binding: ScopeBinding, payload: Any, scan_id: str) -> dict[str, Any]:
        if payload.max_items != 20 or payload.visible_batch is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "XHS MVP action requires one visible 20-item batch")
        observed_at, monotonic_time = self._clock()
        raw_batch = payload.visible_batch.model_dump(mode="json", by_alias=True)
        gate = AdapterExecutionGate(self.controller.paths)
        account_ref_hash = self.controller.owner_account_ref_hash()
        if binding.scope_id is SyncScopeId.XIAOHONGSHU_FAVORITES:
            batch = XhsFavoritesBatch.from_extension_result(raw_batch, sequence=0, observed_at=observed_at)
            self._require_exact_batch(batch)
            self.controller.require_manifest_match(
                scope_id=binding.scope_id,
                content_ids=[item.content_id for item in batch.items],
            )
            adapter = XhsFavoritesAdapter(self.store)
            adapter.begin_scan(
                scan_id,
                account_ref_hash=account_ref_hash,
                scope_mode="owner_mvp_20",
                started_at=observed_at,
            )
            receipt = XhsFavoritesBatchCoordinator(adapter, gate).apply_owner_action(
                scan_id,
                batch,
                monotonic_batch_time=monotonic_time,
                monotonic_observation_time=monotonic_time,
            )
        elif binding.scope_id is SyncScopeId.XIAOHONGSHU_LIKES:
            batch = XhsLikesBatch.from_extension_result(raw_batch, sequence=0, observed_at=observed_at)
            self._require_exact_batch(batch)
            self.controller.require_manifest_match(
                scope_id=binding.scope_id,
                content_ids=[item.content_id for item in batch.items],
            )
            adapter = XhsLikesAdapter(self.store)
            adapter.begin_scan(
                scan_id,
                account_ref_hash=account_ref_hash,
                scope_mode="owner_mvp_20",
                started_at=observed_at,
            )
            receipt = XhsLikesBatchCoordinator(adapter, gate).apply_owner_action(
                scan_id,
                batch,
                monotonic_batch_time=monotonic_time,
                monotonic_observation_time=monotonic_time,
            )
        else:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "XHS dispatch binding is invalid")
        safe = receipt.safe_dict()
        if safe["relations"] != 20 or safe["observations"] != 20 or safe["automatic_scrolls"] != 0:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "XHS MVP receipt is incomplete")
        return {"execution": "chrome_visible_dom", "receipt": safe, "sidecar_batch_requests": 0}

    def _execute_douyin(self, *, binding: ScopeBinding, payload: Any, scan_id: str) -> dict[str, Any]:
        if payload.max_items != 20 or binding.adapter_mode not in {"favorites", "likes"}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin MVP action exceeds the fixed boundary")
        if getattr(payload, "source_collection_id", None) is not None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin MVP action cannot infer a collection from page state")
        verify_owner_private_douyin_sidecar_bundle(self.controller.paths, self.controller.release_input.douyin_build)
        if payload.visible_batch is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin MVP action requires one visible 20-item batch")
        observed_at, monotonic_time = self._clock()
        client = OwnerPrivateVisibleSidecarClient(
            self.controller.paths,
            expected_build=self.controller.release_input.douyin_build,
            port=self.controller.release_input.douyin_port,
        )
        adapter = DouyinAdapter(self.store)
        coordinator = DouyinBatchCoordinator(adapter, client, AdapterExecutionGate(self.controller.paths))
        request = VisibleBatchRequest(
            mode=binding.adapter_mode,
            sequence=0,
            visible_batch=payload.visible_batch.model_dump(mode="json", by_alias=True),
            max_items=20,
        )

        def validate_batch(batch: DouyinBatch) -> None:
            self._require_exact_batch(batch)
            self.controller.require_manifest_match(
                scope_id=binding.scope_id,
                content_ids=[item.content_id for item in batch.items],
            )
            adapter.begin_scan(
                scan_id,
                account_ref_hash=self.controller.owner_account_ref_hash(),
                mode=binding.adapter_mode,
                scope_mode="owner_mvp_20",
                started_at=observed_at,
            )

        receipt = coordinator.apply_owner_action(
            scan_id,
            request,
            observed_at=observed_at,
            monotonic_batch_time=monotonic_time,
            monotonic_observation_time=monotonic_time,
            batch_validator=validate_batch,
        )
        safe = receipt.safe_dict()
        if (
            safe["relations"] != 20
            or safe["observations"] != 20
            or safe["automatic_pagination"] != 0
            or safe["mode"] != binding.adapter_mode
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin MVP receipt is incomplete")
        return {
            "execution": "owner_private_loopback_sidecar",
            "receipt": safe,
            "sidecar_batch_requests": 1,
        }

    def execute(self, *, binding: ScopeBinding, payload: Any, job_id: str, payload_hash: str) -> str:
        self.controller.require_scope(binding.scope_id)
        self.controller.ensure_scope_job(scope_id=binding.scope_id, job_id=job_id)
        scan_id = self.controller.scope_scan_id(binding.scope_id)
        if binding.scope_id in {
            SyncScopeId.XIAOHONGSHU_FAVORITES,
            SyncScopeId.XIAOHONGSHU_LIKES,
        }:
            result = self._execute_xhs(binding=binding, payload=payload, scan_id=scan_id)
        elif binding.scope_id in {SyncScopeId.DOUYIN_FAVORITES, SyncScopeId.DOUYIN_LIKES}:
            result = self._execute_douyin(binding=binding, payload=payload, scan_id=scan_id)
        else:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "External-gate scope cannot execute in the MVP")
        execution_receipt_hash = canonical_json_sha256(
            {
                "execution": result["execution"],
                "input_sha256": self.controller.release_input.input_sha256,
                "payload_hash": payload_hash,
                "receipt": result["receipt"],
                "scope_id": binding.scope_id.value,
                "sidecar_batch_requests": result["sidecar_batch_requests"],
            }
        )
        self.controller.record_scope_receipt(
            scope_id=binding.scope_id,
            job_id=job_id,
            receipt_hash=execution_receipt_hash,
        )
        return expected_mvp_receipt_hash(
            binding=binding,
            payload_hash=payload_hash,
            input_sha256=self.controller.release_input.input_sha256,
        )


def expected_mvp_receipt_hash(*, binding: ScopeBinding, payload_hash: str, input_sha256: str) -> str:
    """Give the Native Store an idempotent, content-free expected receipt key."""

    return canonical_json_sha256(
        {
            "execution": "owner_mvp_bounded_activation",
            "input_sha256": input_sha256,
            "payload_hash": payload_hash,
            "scope_id": binding.scope_id.value,
            "task_id": TASK_ID,
        }
    )
