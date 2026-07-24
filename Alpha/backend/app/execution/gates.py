"""真实下单前置门禁十一项(ALPHA-LIVE-035;AGENTS.md 第 3 节逐条对应)。

纯函数裁定:所有门全部评估(不短路),缺一即封锁,失败清单完整落审计。
预签授权文件按 specs/LIVE_AUTHORIZATION.schema.json 手工校验
(不引第三方 jsonschema 依赖;常量逐条比对,宽进严出=一律严出)。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def sha256_of_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


GATE_NAMES = (
    "GATE_01_ENV_FLAG",
    "GATE_02_PRESIGNED_AUTHORIZATION",
    "GATE_03_POLICY_HASH",
    "GATE_04_BROKER_HEALTH",
    "GATE_05_JURISDICTION_PROBE",
    "GATE_06_RECONCILIATION_CLEAN",
    "GATE_07_MARKET_DATA_FRESH",
    "GATE_08_RISK_PASS",
    "GATE_09_IDEMPOTENCY_UNUSED",
    "GATE_10_KILL_SWITCH_CLEAR",
    "GATE_11_EXECUTION_LEASE",
)


def validate_authorization(
    auth_path: str | Path,
    *,
    policy_path: str | Path,
    promotion_config_path: str | Path,
    now: datetime,
) -> tuple[bool, list[str]]:
    """预签授权文件校验(schema 常量逐条 + 有效窗 + 双哈希锚定)。"""
    reasons: list[str] = []
    p = Path(auth_path)
    if not p.exists():
        return False, [f"授权文件不存在: {p}"]
    try:
        auth = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return False, [f"授权文件不可读/非法 JSON: {exc}"]

    required = [
        "authorization_id", "owner", "mode", "capital", "markets",
        "promotion_conditions", "valid_from", "valid_until",
        "policy_hash", "owner_signature", "signed_at",
    ]
    for key in required:
        if key not in auth:
            reasons.append(f"缺必填字段: {key}")
    if reasons:
        return False, reasons

    if auth["owner"] != "Linze":
        reasons.append("owner 必须为 Linze")
    if auth["mode"] != "MICRO_LIVE":
        reasons.append("mode 必须为 MICRO_LIVE")
    cap = auth["capital"]
    if cap.get("currency") != "AUD":
        reasons.append("capital.currency 必须为 AUD")
    if cap.get("max_managed_gross_exposure") != 3000:
        reasons.append("capital.max_managed_gross_exposure 必须为 3000")
    if cap.get("fat_finger_max_single_order_ratio") != 0.9:
        reasons.append("capital.fat_finger_max_single_order_ratio 必须为 0.9")
    if cap.get("max_orders_per_hour") != 5:
        reasons.append("capital.max_orders_per_hour 必须为 5")
    if cap.get("max_open_positions", None) is not None:
        reasons.append("capital.max_open_positions 必须为 null")
    if not auth["markets"] or not set(auth["markets"]) <= {"US_STOCK", "US_ETF"}:
        reasons.append("markets 只能是 US_STOCK/US_ETF 且非空")
    promo = auth["promotion_conditions"]
    if promo.get("auto_activate_on_all_green") is not True:
        reasons.append("promotion_conditions.auto_activate_on_all_green 必须为 true")
    expected_promo_hash = sha256_of_file(promotion_config_path)
    if promo.get("strategy_promotion_config_hash") != expected_promo_hash:
        reasons.append("晋级判定配置哈希不匹配(判定标准被改动过,须 owner 重签)")
    expected_policy_hash = sha256_of_file(policy_path)
    if auth["policy_hash"] != expected_policy_hash:
        reasons.append("policy_hash 不匹配(风控政策被改动过,须 owner 重签)")
    if not str(auth.get("owner_signature", "")).strip():
        reasons.append("owner_signature 不得为空")
    try:
        valid_from = datetime.fromisoformat(auth["valid_from"].replace("Z", "+00:00"))
        valid_until = datetime.fromisoformat(auth["valid_until"].replace("Z", "+00:00"))
        if not (valid_from <= now <= valid_until):
            reasons.append(f"不在有效窗内: {auth['valid_from']} ~ {auth['valid_until']}")
    except (ValueError, AttributeError) as exc:
        reasons.append(f"有效期字段非法: {exc}")

    return (not reasons), reasons


@dataclass(frozen=True)
class GateInputs:
    """十一门禁的全部输入——由网关采集,这里只裁定。"""

    env_flag_live_trading: bool
    authorization_ok: bool
    authorization_reasons: tuple[str, ...]
    policy_hash_matches: bool
    broker_healthy: bool
    jurisdiction_verdict: Optional[str]     # ALLOW / DENY / None(从未探测)
    reconciliation_clean: bool
    market_data_fresh: bool
    risk_allowed: bool
    idempotency_key_unused: bool
    kill_switch_clear: bool
    lease_held: bool


@dataclass(frozen=True)
class GateReport:
    passed: bool
    failures: tuple[str, ...] = field(default_factory=tuple)
    detail: dict = field(default_factory=dict)


def evaluate_eleven_gates(inputs: GateInputs) -> GateReport:
    failures: list[str] = []
    if not inputs.env_flag_live_trading:
        failures.append("GATE_01_ENV_FLAG")
    if not inputs.authorization_ok:
        failures.append("GATE_02_PRESIGNED_AUTHORIZATION")
    if not inputs.policy_hash_matches:
        failures.append("GATE_03_POLICY_HASH")
    if not inputs.broker_healthy:
        failures.append("GATE_04_BROKER_HEALTH")
    if inputs.jurisdiction_verdict != "ALLOW":
        failures.append("GATE_05_JURISDICTION_PROBE")
    if not inputs.reconciliation_clean:
        failures.append("GATE_06_RECONCILIATION_CLEAN")
    if not inputs.market_data_fresh:
        failures.append("GATE_07_MARKET_DATA_FRESH")
    if not inputs.risk_allowed:
        failures.append("GATE_08_RISK_PASS")
    if not inputs.idempotency_key_unused:
        failures.append("GATE_09_IDEMPOTENCY_UNUSED")
    if not inputs.kill_switch_clear:
        failures.append("GATE_10_KILL_SWITCH_CLEAR")
    if not inputs.lease_held:
        failures.append("GATE_11_EXECUTION_LEASE")
    return GateReport(
        passed=not failures,
        failures=tuple(failures),
        detail={
            "authorization_reasons": list(inputs.authorization_reasons),
            "jurisdiction_verdict": inputs.jurisdiction_verdict,
        },
    )
