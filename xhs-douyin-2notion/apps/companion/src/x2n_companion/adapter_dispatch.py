"""Strict, CI-synthetic-only routing for the eight approved relation scopes.

This module deliberately does not contain a browser reader, HTTP transport, or
adapter batch payload.  It verifies the binding to each completed Adapter and
produces a deterministic dispatch receipt only.  A future task may supply an
already-sanitized batch to the corresponding Adapter; it must not widen this
Native Messaging boundary.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from x2n_contracts import canonical_json_sha256
from x2n_contracts.models import (
    CapabilityFeatureFlag,
    CapabilityManifest,
    CapabilityReasonCode,
    CapabilityTerminal,
    Platform,
    RelationType,
    SyncScopeId,
)

from .runtime import X2NRuntimeError
from x2n_contracts import ErrorCode


CAPABILITY_CONTRACT_VERSION = "1.0"
DISPATCH_EXECUTION = "ci_synthetic_dispatch"
_DIGEST_KEYS = ("adapter_registry", "feature_registry", "policy_registry", "scope_registry")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ScopeBinding:
    scope_id: SyncScopeId
    platform: Platform
    relation: RelationType
    module_name: str
    adapter_class_name: str
    adapter_name: str
    run_kind: str
    selected_collection: bool = False
    adapter_mode: str | None = None

    def resolve_adapter(self) -> tuple[str, str, str]:
        """Load and verify the completed Adapter binding without running it."""

        try:
            module = importlib.import_module(self.module_name)
            adapter = getattr(module, self.adapter_class_name)
            adapter_name = getattr(module, "ADAPTER_NAME")
            adapter_version = getattr(module, "ADAPTER_VERSION")
            run_kind = getattr(module, "RUN_KIND")
        except (AttributeError, ImportError, TypeError, ValueError) as error:
            raise X2NRuntimeError(
                ErrorCode.CAPABILITY_TECHNICAL_BLOCKED,
                "Adapter binding cannot be verified",
            ) from error
        if (
            not callable(adapter)
            or adapter_name != self.adapter_name
            or run_kind != self.run_kind
            or not isinstance(adapter_version, str)
            or not adapter_version
        ):
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Adapter binding drifted")
        return adapter_name, adapter_version, run_kind

    def source_registry_digests(self, inputs: "CapabilityGateInputs") -> dict[str, str]:
        adapter_name, adapter_version, run_kind = self.resolve_adapter()
        values = {
            "adapter_registry": canonical_json_sha256(
                {
                    "adapter_class": self.adapter_class_name,
                    "adapter_module": self.module_name,
                    "adapter_name": adapter_name,
                    "adapter_version": adapter_version,
                    "adapter_mode": self.adapter_mode,
                    "run_kind": run_kind,
                }
            ),
            "feature_registry": canonical_json_sha256({"feature_flag": inputs.feature_flag.value}),
            "policy_registry": canonical_json_sha256(inputs.safe_dict()),
            "scope_registry": canonical_json_sha256(
                {
                    "platform": self.platform.value,
                    "relation": self.relation.value,
                    "scope_id": self.scope_id.value,
                    "selected_collection": self.selected_collection,
                }
            ),
        }
        if tuple(values) != _DIGEST_KEYS:
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability digest registry drifted")
        return values


SCOPE_BINDINGS: tuple[ScopeBinding, ...] = (
    ScopeBinding(
        SyncScopeId.XIAOHONGSHU_FAVORITES,
        Platform.XIAOHONGSHU,
        RelationType.FAVORITED,
        "x2n_companion.xiaohongshu_favorites",
        "XhsFavoritesAdapter",
        "xhs_favorites",
        "xhs_favorites_scan_v1",
    ),
    ScopeBinding(
        SyncScopeId.XIAOHONGSHU_LIKES,
        Platform.XIAOHONGSHU,
        RelationType.LIKED,
        "x2n_companion.xiaohongshu_likes",
        "XhsLikesAdapter",
        "xhs_likes",
        "xhs_likes_scan_v1",
    ),
    ScopeBinding(
        SyncScopeId.DOUYIN_FAVORITES,
        Platform.DOUYIN,
        RelationType.FAVORITED,
        "x2n_companion.douyin_adapter",
        "DouyinAdapter",
        "douyin_upstream",
        "douyin_owner_bounded_scan_v1",
        adapter_mode="favorites",
    ),
    ScopeBinding(
        SyncScopeId.DOUYIN_LIKES,
        Platform.DOUYIN,
        RelationType.LIKED,
        "x2n_companion.douyin_adapter",
        "DouyinAdapter",
        "douyin_upstream",
        "douyin_owner_bounded_scan_v1",
        adapter_mode="likes",
    ),
    ScopeBinding(
        SyncScopeId.BILIBILI_SELECTED_COLLECTION,
        Platform.BILIBILI,
        RelationType.SAVED_CURRENT,
        "x2n_companion.bilibili_selected",
        "BilibiliSelectedAdapter",
        "bilibili_selected_collection",
        "bilibili_owner_selection_v1",
        selected_collection=True,
    ),
    ScopeBinding(
        SyncScopeId.KUAISHOU_SELECTED_COLLECTION,
        Platform.KUAISHOU,
        RelationType.SAVED_CURRENT,
        "x2n_companion.kuaishou_selected",
        "KuaishouSelectedAdapter",
        "kuaishou_selected_collection",
        "kuaishou_owner_selection_v1",
        selected_collection=True,
    ),
    ScopeBinding(
        SyncScopeId.WEIBO_SELECTED_COLLECTION,
        Platform.WEIBO,
        RelationType.FAVORITED,
        "x2n_companion.weibo_selected",
        "WeiboSelectedAdapter",
        "weibo_selected_collection",
        "weibo_owner_selection_v1",
        selected_collection=True,
    ),
    ScopeBinding(
        SyncScopeId.TAOBAO_SELECTED_COLLECTION,
        Platform.TAOBAO,
        RelationType.SAVED_CURRENT,
        "x2n_companion.taobao_selected",
        "TaobaoSelectedAdapter",
        "taobao_selected_collection",
        "taobao_owner_selection_v1",
        selected_collection=True,
    ),
)
_BINDING_BY_SCOPE = {binding.scope_id: binding for binding in SCOPE_BINDINGS}

if tuple(binding.scope_id for binding in SCOPE_BINDINGS) != tuple(SyncScopeId):
    raise RuntimeError("eight-scope dispatch registry is incomplete or out of order")


@dataclass(frozen=True)
class CapabilityGateInputs:
    """Versioned input facts. They never serve a runtime authorization directly."""

    technical_blocked: bool = False
    unknown_disabled: bool = False
    blocked_policy: bool = False
    blocked_auth: bool = False
    blocked_budget: bool = False
    blocked_capability: bool = False
    feature_flag: CapabilityFeatureFlag = CapabilityFeatureFlag.CI_SYNTHETIC_ONLY

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool
            for value in (
                self.technical_blocked,
                self.unknown_disabled,
                self.blocked_policy,
                self.blocked_auth,
                self.blocked_budget,
                self.blocked_capability,
            )
        ):
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability gate input is invalid")

    def safe_dict(self) -> dict[str, Any]:
        return {
            "blocked_auth": self.blocked_auth,
            "blocked_budget": self.blocked_budget,
            "blocked_capability": self.blocked_capability,
            "blocked_policy": self.blocked_policy,
            "technical_blocked": self.technical_blocked,
            "unknown_disabled": self.unknown_disabled,
        }


@dataclass(frozen=True)
class AdapterDispatchReceipt:
    scope_id: SyncScopeId
    adapter_name: str
    adapter_version: str
    run_kind: str
    receipt_hash: str
    platform_calls: int = 0


class AdapterDispatchFailure(RuntimeError):
    """Test-injectable, sanitized execution failure after durable job creation."""


class CapabilityRegistry:
    """Evaluate only versioned inputs; callers persist the resulting snapshot."""

    def __init__(self, inputs: Mapping[SyncScopeId, CapabilityGateInputs] | None = None) -> None:
        actual = dict(inputs) if inputs is not None else {scope: CapabilityGateInputs() for scope in SyncScopeId}
        if set(actual) != set(SyncScopeId):
            raise X2NRuntimeError(
                ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability scope input registry is incomplete"
            )
        if any(not isinstance(value, CapabilityGateInputs) for value in actual.values()):
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability input registry is invalid")
        self._inputs = actual

    def with_override(self, scope_id: SyncScopeId, **changes: Any) -> "CapabilityRegistry":
        if scope_id not in self._inputs:
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability scope is unknown")
        revised = dict(self._inputs)
        revised[scope_id] = replace(revised[scope_id], **changes)
        return CapabilityRegistry(revised)

    def technical_scope_ids(self) -> tuple[SyncScopeId, ...]:
        return tuple(scope_id for scope_id in SyncScopeId if self._inputs[scope_id].technical_blocked)

    @staticmethod
    def _external_reason(inputs: CapabilityGateInputs) -> CapabilityReasonCode:
        # The order is contractual; never use an unordered collection here.
        if inputs.unknown_disabled:
            return CapabilityReasonCode.UNKNOWN_DISABLED
        if inputs.blocked_policy:
            return CapabilityReasonCode.BLOCKED_POLICY
        if inputs.blocked_auth:
            return CapabilityReasonCode.BLOCKED_AUTH
        if inputs.blocked_budget:
            return CapabilityReasonCode.BLOCKED_BUDGET
        if inputs.blocked_capability:
            return CapabilityReasonCode.BLOCKED_CAPABILITY
        return CapabilityReasonCode.CI_SYNTH_READY

    def evaluate(self, *, evaluated_at: str | None = None) -> CapabilityManifest:
        technical = self.technical_scope_ids()
        if technical:
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability technical veto is active")
        stamp = evaluated_at or _now()
        outcomes: list[dict[str, Any]] = []
        for binding in SCOPE_BINDINGS:
            inputs = self._inputs[binding.scope_id]
            reason = self._external_reason(inputs)
            ready = reason is CapabilityReasonCode.CI_SYNTH_READY
            terminal = (
                CapabilityTerminal.READY_FOR_MVP_ACTIVATION if ready else CapabilityTerminal.DISABLED_EXTERNAL_GATE
            )
            feature_flag = inputs.feature_flag if ready else CapabilityFeatureFlag.DISABLED
            digests = binding.source_registry_digests(inputs)
            evidence_hash = canonical_json_sha256(
                {
                    "feature_flag": feature_flag.value,
                    "reason_code": reason.value,
                    "scope_id": binding.scope_id.value,
                    "source_registry_digests": digests,
                    "terminal": terminal.value,
                }
            )
            outcomes.append(
                {
                    "scope_id": binding.scope_id.value,
                    "platform": binding.platform.value,
                    "relation": binding.relation.value,
                    "terminal": terminal.value,
                    "reason_code": reason.value,
                    "source_registry_digests": digests,
                    "feature_flag": feature_flag.value,
                    "evidence_hash": evidence_hash,
                    "evaluated_at": stamp,
                }
            )
        return CapabilityManifest.model_validate_json(
            json.dumps(
                {"capability_contract_version": CAPABILITY_CONTRACT_VERSION, "outcomes": outcomes},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )


class AdapterDispatcher:
    """Performs the only Task010 execution: verified, zero-network synthetic dispatch."""

    def __init__(self, *, failure_predicate: Callable[[ScopeBinding], bool] | None = None) -> None:
        self._failure_predicate = failure_predicate

    @staticmethod
    def binding_for(scope_id: SyncScopeId, *, platform: Platform, relation: RelationType) -> ScopeBinding:
        binding = _BINDING_BY_SCOPE.get(scope_id)
        if binding is None or binding.platform is not platform or binding.relation is not relation:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Dispatch scope cross-product is not allowlisted")
        return binding

    @staticmethod
    def expected_receipt_hash(binding: ScopeBinding, *, payload_hash: str) -> str:
        adapter_name, adapter_version, run_kind = binding.resolve_adapter()
        return canonical_json_sha256(
            {
                "adapter_name": adapter_name,
                "adapter_version": adapter_version,
                "execution": DISPATCH_EXECUTION,
                "payload_hash": payload_hash,
                "platform_calls": 0,
                "run_kind": run_kind,
                "scope_id": binding.scope_id.value,
            }
        )

    def execute_synthetic(self, binding: ScopeBinding, *, payload_hash: str) -> AdapterDispatchReceipt:
        if self._failure_predicate is not None and self._failure_predicate(binding):
            raise AdapterDispatchFailure("synthetic adapter execution failed")
        adapter_name, adapter_version, run_kind = binding.resolve_adapter()
        receipt_hash = self.expected_receipt_hash(binding, payload_hash=payload_hash)
        return AdapterDispatchReceipt(
            scope_id=binding.scope_id,
            adapter_name=adapter_name,
            adapter_version=adapter_version,
            run_kind=run_kind,
            receipt_hash=receipt_hash,
        )
