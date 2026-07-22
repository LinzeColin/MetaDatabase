"""Stable error taxonomy and registry source of truth."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorClass(str, Enum):
    USER_ACTION_REQUIRED = "user_action_required"
    PLATFORM_CHANGED = "platform_changed"
    RATE_LIMITED = "rate_limited"
    NETWORK = "network"
    DEPENDENCY_MISSING = "dependency_missing"
    PROVIDER = "provider"
    INVALID_INPUT = "invalid_input"
    SECURITY_BLOCKED = "security_blocked"
    STORAGE = "storage"
    DATA_INTEGRITY = "data_integrity"
    POLICY = "policy"
    UNKNOWN = "unknown"


class ErrorCode(str, Enum):
    INVALID_SCHEMA_VERSION = "X2N_INVALID_SCHEMA_VERSION"
    UNKNOWN_FIELD = "X2N_UNKNOWN_FIELD"
    INVALID_INPUT = "X2N_INVALID_INPUT"
    NATIVE_ORIGIN_REJECTED = "X2N_NATIVE_ORIGIN_REJECTED"
    NATIVE_MESSAGE_TOO_LARGE = "X2N_NATIVE_MESSAGE_TOO_LARGE"
    NATIVE_ACTION_UNKNOWN = "X2N_NATIVE_ACTION_UNKNOWN"
    NATIVE_DUPLICATE_REQUEST = "X2N_NATIVE_DUPLICATE_REQUEST"
    CANONICAL_KEY_INVALID = "X2N_CANONICAL_KEY_INVALID"
    RELATION_KEY_INVALID = "X2N_RELATION_KEY_INVALID"
    ARTIFACT_VERSION_CONFLICT = "X2N_ARTIFACT_VERSION_CONFLICT"
    PROVENANCE_INCOMPLETE = "X2N_PROVENANCE_INCOMPLETE"
    CDN_PERSISTENCE_BLOCKED = "X2N_CDN_PERSISTENCE_BLOCKED"
    URL_REJECTED = "X2N_URL_REJECTED"
    SECURITY_INJECTION_BLOCKED = "X2N_SECURITY_INJECTION_BLOCKED"
    ADAPTER_AUTH_EXPIRED = "X2N_ADAPTER_AUTH_EXPIRED"
    PLATFORM_CHANGED = "X2N_PLATFORM_CHANGED"
    RATE_LIMITED = "X2N_RATE_LIMITED"
    NETWORK_FAILED = "X2N_NETWORK_FAILED"
    DEPENDENCY_MISSING = "X2N_DEPENDENCY_MISSING"
    PROVIDER_FAILED = "X2N_PROVIDER_FAILED"
    STORAGE_FAILED = "X2N_STORAGE_FAILED"
    DATA_INTEGRITY_FAILED = "X2N_DATA_INTEGRITY_FAILED"
    POLICY_BLOCKED = "X2N_POLICY_BLOCKED"
    UNKNOWN_FAILURE = "X2N_UNKNOWN_FAILURE"


class DataEffect(str, Enum):
    NONE = "none"
    CANONICAL_UNCHANGED = "canonical_unchanged"
    DERIVED_OUTPUT_MISSING = "derived_output_missing"
    UNKNOWN_FAIL_CLOSED = "unknown_fail_closed"


class NextAction(str, Enum):
    CORRECT_INPUT = "correct_input"
    REVIEW_SECURITY_EVENT = "review_security_event"
    USE_EXISTING_JOB = "use_existing_job"
    RESTORE_BACKUP = "restore_backup"
    REVIEW_POLICY = "review_policy"
    OPEN_LOGIN_PROFILE = "open_login_profile"
    INSPECT_PLATFORM_FIXTURE = "inspect_platform_fixture"
    WAIT_AND_RETRY = "wait_and_retry"
    RETRY = "retry"
    INSTALL_DEPENDENCY = "install_dependency"
    INSPECT_PROVIDER = "inspect_provider"
    FREE_DISK_SPACE = "free_disk_space"
    INSPECT_DIAGNOSTICS = "inspect_diagnostics"


@dataclass(frozen=True)
class ErrorSpec:
    error_class: ErrorClass
    retryable: bool
    data_effect: DataEffect
    next_action: NextAction
    default_safe_message: str


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_SCHEMA_VERSION: ErrorSpec(ErrorClass.INVALID_INPUT, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "消息版本不受支持"),
    ErrorCode.UNKNOWN_FIELD: ErrorSpec(ErrorClass.INVALID_INPUT, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "消息包含未声明字段"),
    ErrorCode.INVALID_INPUT: ErrorSpec(ErrorClass.INVALID_INPUT, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "输入未通过严格合同"),
    ErrorCode.NATIVE_ORIGIN_REJECTED: ErrorSpec(ErrorClass.SECURITY_BLOCKED, False, DataEffect.NONE, NextAction.REVIEW_SECURITY_EVENT, "调用来源未获允许"),
    ErrorCode.NATIVE_MESSAGE_TOO_LARGE: ErrorSpec(ErrorClass.SECURITY_BLOCKED, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "消息超过允许大小"),
    ErrorCode.NATIVE_ACTION_UNKNOWN: ErrorSpec(ErrorClass.INVALID_INPUT, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "消息动作不受支持"),
    ErrorCode.NATIVE_DUPLICATE_REQUEST: ErrorSpec(ErrorClass.DATA_INTEGRITY, False, DataEffect.NONE, NextAction.USE_EXISTING_JOB, "请求标识与既有请求冲突"),
    ErrorCode.CANONICAL_KEY_INVALID: ErrorSpec(ErrorClass.DATA_INTEGRITY, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "内容键不符合确定性规则"),
    ErrorCode.RELATION_KEY_INVALID: ErrorSpec(ErrorClass.DATA_INTEGRITY, False, DataEffect.NONE, NextAction.CORRECT_INPUT, "关系键不符合确定性规则"),
    ErrorCode.ARTIFACT_VERSION_CONFLICT: ErrorSpec(ErrorClass.DATA_INTEGRITY, False, DataEffect.CANONICAL_UNCHANGED, NextAction.RESTORE_BACKUP, "派生资产版本发生冲突"),
    ErrorCode.PROVENANCE_INCOMPLETE: ErrorSpec(ErrorClass.DATA_INTEGRITY, False, DataEffect.CANONICAL_UNCHANGED, NextAction.CORRECT_INPUT, "来源链不完整"),
    ErrorCode.CDN_PERSISTENCE_BLOCKED: ErrorSpec(ErrorClass.POLICY, False, DataEffect.NONE, NextAction.REVIEW_POLICY, "平台媒体地址不得持久化"),
    ErrorCode.URL_REJECTED: ErrorSpec(ErrorClass.SECURITY_BLOCKED, False, DataEffect.NONE, NextAction.REVIEW_SECURITY_EVENT, "地址不在允许范围"),
    ErrorCode.SECURITY_INJECTION_BLOCKED: ErrorSpec(ErrorClass.SECURITY_BLOCKED, False, DataEffect.NONE, NextAction.REVIEW_SECURITY_EVENT, "危险输入已阻断"),
    ErrorCode.ADAPTER_AUTH_EXPIRED: ErrorSpec(ErrorClass.USER_ACTION_REQUIRED, False, DataEffect.CANONICAL_UNCHANGED, NextAction.OPEN_LOGIN_PROFILE, "请在专用浏览器配置中重新登录"),
    ErrorCode.PLATFORM_CHANGED: ErrorSpec(ErrorClass.PLATFORM_CHANGED, False, DataEffect.CANONICAL_UNCHANGED, NextAction.INSPECT_PLATFORM_FIXTURE, "平台页面结构已变化"),
    ErrorCode.RATE_LIMITED: ErrorSpec(ErrorClass.RATE_LIMITED, True, DataEffect.CANONICAL_UNCHANGED, NextAction.WAIT_AND_RETRY, "请求受到速率限制"),
    ErrorCode.NETWORK_FAILED: ErrorSpec(ErrorClass.NETWORK, True, DataEffect.CANONICAL_UNCHANGED, NextAction.RETRY, "网络请求失败"),
    ErrorCode.DEPENDENCY_MISSING: ErrorSpec(ErrorClass.DEPENDENCY_MISSING, False, DataEffect.CANONICAL_UNCHANGED, NextAction.INSTALL_DEPENDENCY, "所需本地依赖不可用"),
    ErrorCode.PROVIDER_FAILED: ErrorSpec(ErrorClass.PROVIDER, True, DataEffect.DERIVED_OUTPUT_MISSING, NextAction.INSPECT_PROVIDER, "处理服务失败"),
    ErrorCode.STORAGE_FAILED: ErrorSpec(ErrorClass.STORAGE, True, DataEffect.UNKNOWN_FAIL_CLOSED, NextAction.FREE_DISK_SPACE, "本地存储操作失败"),
    ErrorCode.DATA_INTEGRITY_FAILED: ErrorSpec(ErrorClass.DATA_INTEGRITY, False, DataEffect.UNKNOWN_FAIL_CLOSED, NextAction.RESTORE_BACKUP, "数据完整性检查失败"),
    ErrorCode.POLICY_BLOCKED: ErrorSpec(ErrorClass.POLICY, False, DataEffect.NONE, NextAction.REVIEW_POLICY, "当前策略禁止此操作"),
    ErrorCode.UNKNOWN_FAILURE: ErrorSpec(ErrorClass.UNKNOWN, False, DataEffect.UNKNOWN_FAIL_CLOSED, NextAction.INSPECT_DIAGNOSTICS, "发生未知错误，系统已停止副作用"),
}
