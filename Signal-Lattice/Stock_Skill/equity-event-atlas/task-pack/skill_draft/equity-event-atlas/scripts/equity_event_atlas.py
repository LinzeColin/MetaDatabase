#!/usr/bin/env python3
"""股票事件航图：确定性合同校验、能力门和可视化渲染器。

本脚本只处理调用方显式提供的结构化输入与本地证据，不联网、不连接券商、
不执行订单，也不把模型语言当作事实。Python 3.9+ 标准库即可运行。
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

VERSION = "0.0.0.1"
REQUEST_SCHEMA = "equity-event-atlas/request-v1"
BUNDLE_SCHEMA = "equity-event-atlas/analysis-bundle-v1"
CAPABILITY_SCHEMA = "equity-event-atlas/market-capabilities-v1"

EVENT_TYPES = {
    "IPO_LOCKUP",
    "EARNINGS_GUIDANCE",
    "FINANCING_DILUTION",
    "INSIDER_OWNERSHIP",
    "MNA_RESTRUCTURING",
    "INDEX_REBALANCE",
    "CORPORATE_ACTION",
    "REGULATORY_LEGAL",
    "PRODUCT_OPERATIONAL",
    "LIQUIDITY_POSITIONING",
}
EVENT_STATES = {
    "RUMORED", "ESTIMATED", "SCHEDULED", "CONDITIONAL", "CONFIRMED",
    "AMENDED", "COMPLETED", "CANCELLED", "DISPUTED", "UNKNOWN",
}
RELATION_TYPES = {
    "TRIGGERS", "DEPENDS_ON", "AMENDS", "PRECEDES", "OVERLAPS",
    "COMPOUNDS", "OFFSETS", "CONFLICTS_WITH",
}
CLAIM_LAYERS = {"FACT", "INFERENCE", "FORECAST", "ACTION"}
EVIDENCE_TIERS = {"T0", "T1", "T2", "T3", "T4"}
COVERAGE_TIERS = {"DEEP", "STANDARD", "GENERIC"}
RUN_CAPABILITIES = {"FULL", "SUPPORTED_WITH_HOST_DATA", "RESEARCH_ONLY", "BLOCKED"}
GATE_STATES = {"PASS", "RESEARCH_ONLY", "BLOCK"}
SCENARIOS = {"BEAR", "BASE", "BULL"}
ACTIONS = {
    "WATCH", "AVOID", "HOLD", "REDUCE", "ACCUMULATE", "HEDGE",
    "EXIT", "NO_ACTION", "RESEARCH_ONLY",
}
PASSIVE_ACTIONS = {"WATCH", "NO_ACTION", "RESEARCH_ONLY"}
ACTIONABLE_ACTIONS = ACTIONS - PASSIVE_ACTIONS
IMPACT_MECHANISMS = {
    "SUPPLY", "DEMAND", "FUNDAMENTALS", "EXPECTATIONS", "LIQUIDITY",
    "POSITIONING", "REGULATORY",
}

MARKET_REGISTRY: Dict[str, Dict[str, Any]] = {
    "XNAS": {"market": "美国", "coverage_tier": "DEEP", "calendar": "America/New_York", "currency": "USD"},
    "XNYS": {"market": "美国", "coverage_tier": "DEEP", "calendar": "America/New_York", "currency": "USD"},
    "XASE": {"market": "美国", "coverage_tier": "DEEP", "calendar": "America/New_York", "currency": "USD"},
    "ARCX": {"market": "美国", "coverage_tier": "DEEP", "calendar": "America/New_York", "currency": "USD"},
    "BATS": {"market": "美国", "coverage_tier": "DEEP", "calendar": "America/New_York", "currency": "USD"},
    "XASX": {"market": "澳大利亚", "coverage_tier": "DEEP", "calendar": "Australia/Sydney", "currency": "AUD"},
    "XTSE": {"market": "加拿大", "coverage_tier": "GENERIC", "calendar": "America/Toronto", "currency": "CAD"},
    "XTSX": {"market": "加拿大", "coverage_tier": "GENERIC", "calendar": "America/Toronto", "currency": "CAD"},
    "XLON": {"market": "英国", "coverage_tier": "GENERIC", "calendar": "Europe/London", "currency": "GBP"},
    "XHKG": {"market": "中国香港", "coverage_tier": "GENERIC", "calendar": "Asia/Hong_Kong", "currency": "HKD"},
    "XSHG": {"market": "中国大陆", "coverage_tier": "GENERIC", "calendar": "Asia/Shanghai", "currency": "CNY"},
    "XSHE": {"market": "中国大陆", "coverage_tier": "GENERIC", "calendar": "Asia/Shanghai", "currency": "CNY"},
    "XTKS": {"market": "日本", "coverage_tier": "GENERIC", "calendar": "Asia/Tokyo", "currency": "JPY"},
    "XKRX": {"market": "韩国", "coverage_tier": "GENERIC", "calendar": "Asia/Seoul", "currency": "KRW"},
    "XSES": {"market": "新加坡", "coverage_tier": "GENERIC", "calendar": "Asia/Singapore", "currency": "SGD"},
    "XETR": {"market": "德国", "coverage_tier": "GENERIC", "calendar": "Europe/Berlin", "currency": "EUR"},
    "XPAR": {"market": "法国", "coverage_tier": "GENERIC", "calendar": "Europe/Paris", "currency": "EUR"},
    "XAMS": {"market": "荷兰", "coverage_tier": "GENERIC", "calendar": "Europe/Amsterdam", "currency": "EUR"},
}

FORBIDDEN_KEYS = {
    "broker", "broker_account", "account_id", "order", "order_type",
    "execute", "execution", "quantity", "api_key", "access_token",
    "refresh_token", "password", "private_key", "cookie",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


class ValidationFailure(Exception):
    def __init__(self, issues: Sequence[Issue]):
        super().__init__("validation failed")
        self.issues = list(issues)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationFailure([Issue("FILE_NOT_FOUND", str(path), "文件不存在")]) from exc
    except json.JSONDecodeError as exc:
        raise ValidationFailure([
            Issue("JSON_INVALID", str(path), f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列")
        ]) from exc


def parse_time(value: Any, path: str, issues: List[Issue]) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        issues.append(Issue("TIME_REQUIRED", path, "必须提供带时区的 ISO 8601 时间"))
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        issues.append(Issue("TIME_INVALID", path, "时间不是有效 ISO 8601 格式"))
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        issues.append(Issue("TIMEZONE_REQUIRED", path, "时间必须包含 UTC 偏移或 Z"))
        return None
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def walk_values(value: Any, path: str = "$") -> Iterable[Tuple[str, Optional[str], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from walk_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield child_path, None, child
            yield from walk_values(child, child_path)


def common_safety_checks(value: Any, issues: List[Issue]) -> None:
    for path, key, child in walk_values(value):
        if key and key.lower() in FORBIDDEN_KEYS:
            issues.append(Issue("FORBIDDEN_EXECUTION_FIELD", path, "研究型 Skill 禁止券商、账户、订单或凭据字段"))
        if isinstance(child, str):
            for pattern in SECRET_PATTERNS:
                if pattern.search(child):
                    issues.append(Issue("SECRET_DETECTED", path, "检测到疑似真实凭据或私钥"))
                    break


def required_string(obj: Mapping[str, Any], key: str, path: str, issues: List[Issue]) -> Optional[str]:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        issues.append(Issue("FIELD_REQUIRED", f"{path}.{key}", "必须为非空字符串"))
        return None
    return value.strip()


def require_enum(value: Any, allowed: set, path: str, issues: List[Issue]) -> None:
    if value not in allowed:
        issues.append(Issue("ENUM_INVALID", path, f"允许值：{', '.join(sorted(allowed))}"))


def validate_request(value: Any) -> List[Issue]:
    issues: List[Issue] = []
    if not isinstance(value, dict):
        return [Issue("ROOT_OBJECT_REQUIRED", "$", "请求根必须是对象")]
    common_safety_checks(value, issues)
    if value.get("schema") != REQUEST_SCHEMA:
        issues.append(Issue("SCHEMA_MISMATCH", "$.schema", f"必须为 {REQUEST_SCHEMA}"))
    locale = value.get("locale")
    if not isinstance(locale, str) or not locale.lower().startswith("zh"):
        issues.append(Issue("CHINESE_OUTPUT_REQUIRED", "$.locale", "当前版本输出必须为中文 locale"))
    parse_time(value.get("as_of"), "$.as_of", issues)
    security = value.get("security")
    if not isinstance(security, dict):
        issues.append(Issue("SECURITY_REQUIRED", "$.security", "必须提供证券身份对象"))
    else:
        required_string(security, "name", "$.security", issues)
        required_string(security, "ticker", "$.security", issues)
        mic = required_string(security, "mic", "$.security", issues)
        required_string(security, "instrument_type", "$.security", issues)
        required_string(security, "currency", "$.security", issues)
        if mic and not re.fullmatch(r"[A-Z0-9]{4}", mic):
            issues.append(Issue("MIC_INVALID", "$.security.mic", "MIC 必须是四位大写字母或数字"))
    horizon = value.get("horizon_trading_days")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or not 1 <= horizon <= 756:
        issues.append(Issue("HORIZON_INVALID", "$.horizon_trading_days", "交易日范围必须是 1–756 的整数"))
    mode = value.get("requested_mode")
    require_enum(mode, {"SCAN", "DEEP_DIVE", "COMPARE", "REFRESH", "REVIEW", "SIMULATE"}, "$.requested_mode", issues)
    objective = value.get("objective")
    require_enum(objective, {"RESEARCH", "RISK_ADJUSTED_DECISION_SUPPORT"}, "$.objective", issues)
    if objective == "RISK_ADJUSTED_DECISION_SUPPORT":
        context = value.get("user_context")
        if not isinstance(context, dict):
            issues.append(Issue("USER_CONTEXT_REQUIRED", "$.user_context", "动作支持必须提供用户约束"))
        else:
            required_string(context, "position_status", "$.user_context", issues)
            required_string(context, "risk_budget", "$.user_context", issues)
            required_string(context, "max_event_exposure", "$.user_context", issues)
    return issues


def market_capability(
    mic: str,
    *,
    official_sources_verified: bool,
    calendar_verified: bool,
    market_data_verified: bool,
) -> Dict[str, Any]:
    normalized = (mic or "").upper()
    base = MARKET_REGISTRY.get(normalized)
    if base is None:
        tier = "GENERIC"
        market = "未登记市场"
        calendar = None
        currency = None
    else:
        tier = base["coverage_tier"]
        market = base["market"]
        calendar = base["calendar"]
        currency = base["currency"]
    reasons: List[str] = []
    if not official_sources_verified:
        reasons.append("未验证本次运行使用的官方披露来源")
    if not calendar_verified:
        reasons.append("未验证本次运行对应的交易日历与时区")
    if not market_data_verified:
        reasons.append("未验证本次运行的时点行情数据")
    if not official_sources_verified:
        run = "BLOCKED"
    elif tier == "DEEP" and calendar_verified and market_data_verified:
        run = "FULL"
    elif calendar_verified and market_data_verified:
        run = "SUPPORTED_WITH_HOST_DATA"
    else:
        run = "RESEARCH_ONLY"
    return {
        "schema": CAPABILITY_SCHEMA,
        "mic": normalized,
        "market": market,
        "coverage_tier": tier,
        "run_capability": run,
        "official_sources_verified": bool(official_sources_verified),
        "calendar_verified": bool(calendar_verified),
        "market_data_verified": bool(market_data_verified),
        "calendar_timezone": calendar,
        "default_currency": currency,
        "reasons": reasons,
    }


def validate_url(value: Any, path: str, issues: List[Issue]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        issues.append(Issue("URL_INVALID", path, "URL 必须是字符串"))
        return
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        issues.append(Issue("HTTPS_REQUIRED", path, "外部来源必须使用真实 HTTPS URL"))
        return
    host = parsed.hostname or ""
    reserved_suffix = "." + "example"
    reserved_host = "example" + ".com"
    if host.endswith(reserved_suffix) or host == reserved_host:
        issues.append(Issue("NON_REAL_URL", path, "不得使用示例域名冒充来源"))


def ids_by_key(items: Any, key: str, path: str, issues: List[Issue]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    if not isinstance(items, list):
        issues.append(Issue("ARRAY_REQUIRED", path, "必须为数组"))
        return result
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue("OBJECT_REQUIRED", item_path, "数组成员必须为对象"))
            continue
        identifier = required_string(item, key, item_path, issues)
        if identifier:
            if identifier in result:
                issues.append(Issue("ID_DUPLICATE", f"{item_path}.{key}", "标识符重复"))
            else:
                result[identifier] = item
    return result


def validate_bundle(value: Any, base_dir: Path) -> List[Issue]:
    issues: List[Issue] = []
    if not isinstance(value, dict):
        return [Issue("ROOT_OBJECT_REQUIRED", "$", "分析包根必须是对象")]
    common_safety_checks(value, issues)
    if value.get("schema") != BUNDLE_SCHEMA:
        issues.append(Issue("SCHEMA_MISMATCH", "$.schema", f"必须为 {BUNDLE_SCHEMA}"))
    locale = value.get("locale")
    if not isinstance(locale, str) or not locale.lower().startswith("zh"):
        issues.append(Issue("CHINESE_OUTPUT_REQUIRED", "$.locale", "当前版本报告必须为中文"))
    as_of = parse_time(value.get("as_of"), "$.as_of", issues)
    generated_at = parse_time(value.get("generated_at"), "$.generated_at", issues)
    if as_of and generated_at and generated_at < as_of:
        issues.append(Issue("GENERATED_BEFORE_AS_OF", "$.generated_at", "生成时间不能早于分析时点"))

    security = value.get("security")
    if not isinstance(security, dict):
        issues.append(Issue("SECURITY_REQUIRED", "$.security", "必须提供证券身份"))
    else:
        for key in ("name", "ticker", "mic", "instrument_type", "currency"):
            required_string(security, key, "$.security", issues)

    capability = value.get("market_capability")
    run_capability = None
    if not isinstance(capability, dict):
        issues.append(Issue("CAPABILITY_REQUIRED", "$.market_capability", "必须提供本次运行能力判定"))
    else:
        require_enum(capability.get("coverage_tier"), COVERAGE_TIERS, "$.market_capability.coverage_tier", issues)
        run_capability = capability.get("run_capability")
        require_enum(run_capability, RUN_CAPABILITIES, "$.market_capability.run_capability", issues)
        if capability.get("official_sources_verified") is not True and run_capability in {"FULL", "SUPPORTED_WITH_HOST_DATA"}:
            issues.append(Issue("OFFICIAL_SOURCE_GATE", "$.market_capability", "未验证官方来源时不能开放完整能力"))
        if run_capability == "FULL" and (
            capability.get("calendar_verified") is not True or capability.get("market_data_verified") is not True
        ):
            issues.append(Issue("FULL_CAPABILITY_UNSUPPORTED", "$.market_capability", "FULL 需要官方来源、日历和行情全部验证"))

    gates = value.get("gates")
    gate_identity = gate_evidence = gate_forecast = gate_action = None
    if not isinstance(gates, dict):
        issues.append(Issue("GATES_REQUIRED", "$.gates", "必须提供四项运行门"))
    else:
        for key in ("identity", "evidence", "forecast", "action"):
            require_enum(gates.get(key), GATE_STATES, f"$.gates.{key}", issues)
        gate_identity = gates.get("identity")
        gate_evidence = gates.get("evidence")
        gate_forecast = gates.get("forecast")
        gate_action = gates.get("action")
        if gate_identity != "PASS" and gate_forecast == "PASS":
            issues.append(Issue("FORECAST_WITHOUT_IDENTITY", "$.gates", "身份未通过时不得开放预测"))
        if gate_evidence != "PASS" and gate_forecast == "PASS":
            issues.append(Issue("FORECAST_WITHOUT_EVIDENCE", "$.gates", "证据未通过时不得开放预测"))

    evidence_map = ids_by_key(value.get("evidence"), "evidence_id", "$.evidence", issues)
    for evidence_id, item in evidence_map.items():
        index_path = f"$.evidence[{list(evidence_map).index(evidence_id)}]"
        require_enum(item.get("tier"), EVIDENCE_TIERS, f"{index_path}.tier", issues)
        source_type = required_string(item, "source_type", index_path, issues)
        published = parse_time(item.get("published_at"), f"{index_path}.published_at", issues)
        observed = parse_time(item.get("observed_at"), f"{index_path}.observed_at", issues)
        if published and observed and observed < published:
            issues.append(Issue("OBSERVED_BEFORE_PUBLISHED", f"{index_path}.observed_at", "观察时间不能早于发布时间"))
        if as_of and observed and observed > as_of:
            issues.append(Issue("POINT_IN_TIME_LEAK", f"{index_path}.observed_at", "证据在分析时点之后才被观察，构成前视污染"))
        validate_url(item.get("url"), f"{index_path}.url", issues)
        locator = item.get("locator")
        declared_hash = item.get("sha256")
        if source_type == "SYNTHETIC_FIXTURE":
            if not isinstance(locator, str) or not locator:
                issues.append(Issue("FIXTURE_LOCATOR_REQUIRED", f"{index_path}.locator", "合成证据必须指向本地文件"))
            else:
                rel = Path(locator)
                if rel.is_absolute() or ".." in rel.parts:
                    issues.append(Issue("FIXTURE_LOCATOR_UNSAFE", f"{index_path}.locator", "合成证据路径必须是包内安全相对路径"))
                else:
                    target = (base_dir / rel).resolve()
                    try:
                        target.relative_to(base_dir.resolve())
                    except ValueError:
                        issues.append(Issue("FIXTURE_LOCATOR_ESCAPE", f"{index_path}.locator", "合成证据路径逃逸分析包目录"))
                    else:
                        if not target.is_file():
                            issues.append(Issue("FIXTURE_MISSING", f"{index_path}.locator", "合成证据文件不存在"))
                        elif not isinstance(declared_hash, str) or declared_hash != sha256_file(target):
                            issues.append(Issue("EVIDENCE_HASH_MISMATCH", f"{index_path}.sha256", "合成证据哈希不匹配"))
        elif not isinstance(item.get("url"), str):
            issues.append(Issue("SOURCE_URL_REQUIRED", f"{index_path}.url", "非合成证据必须提供真实 HTTPS URL"))

    claims_map = ids_by_key(value.get("claims"), "claim_id", "$.claims", issues)
    for claim_id, item in claims_map.items():
        item_path = f"$.claims[{list(claims_map).index(claim_id)}]"
        layer = item.get("layer")
        require_enum(layer, CLAIM_LAYERS, f"{item_path}.layer", issues)
        required_string(item, "text", item_path, issues)
        refs = item.get("evidence_ids", [])
        if not isinstance(refs, list):
            issues.append(Issue("ARRAY_REQUIRED", f"{item_path}.evidence_ids", "证据引用必须为数组"))
            refs = []
        for ref in refs:
            if ref not in evidence_map:
                issues.append(Issue("EVIDENCE_REF_MISSING", f"{item_path}.evidence_ids", f"不存在证据 {ref}"))
        if layer == "FACT" and not refs:
            issues.append(Issue("FACT_WITHOUT_EVIDENCE", item_path, "FACT 必须至少绑定一项证据"))
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            issues.append(Issue("CONFIDENCE_INVALID", f"{item_path}.confidence", "置信度必须在 0–1 之间"))

    events_map = ids_by_key(value.get("events"), "event_id", "$.events", issues)
    for event_id, item in events_map.items():
        item_path = f"$.events[{list(events_map).index(event_id)}]"
        require_enum(item.get("event_type"), EVENT_TYPES, f"{item_path}.event_type", issues)
        require_enum(item.get("status"), EVENT_STATES, f"{item_path}.status", issues)
        required_string(item, "title", item_path, issues)
        parse_time(item.get("effective_at"), f"{item_path}.effective_at", issues)
        required_string(item, "timezone", item_path, issues)
        refs = item.get("claim_ids", [])
        if not isinstance(refs, list) or not refs:
            issues.append(Issue("EVENT_CLAIM_REQUIRED", f"{item_path}.claim_ids", "事件必须引用至少一条声明"))
            refs = []
        for ref in refs:
            if ref not in claims_map:
                issues.append(Issue("CLAIM_REF_MISSING", f"{item_path}.claim_ids", f"不存在声明 {ref}"))
        mechanisms = item.get("impact_mechanisms", [])
        if not isinstance(mechanisms, list) or not mechanisms:
            issues.append(Issue("IMPACT_REQUIRED", f"{item_path}.impact_mechanisms", "事件必须声明至少一种影响机制"))
        else:
            for mechanism in mechanisms:
                require_enum(mechanism, IMPACT_MECHANISMS, f"{item_path}.impact_mechanisms", issues)
        relationships = item.get("relationships", [])
        if not isinstance(relationships, list):
            issues.append(Issue("ARRAY_REQUIRED", f"{item_path}.relationships", "事件关系必须为数组"))
            relationships = []
        for rel_index, relation in enumerate(relationships):
            rel_path = f"{item_path}.relationships[{rel_index}]"
            if not isinstance(relation, dict):
                issues.append(Issue("OBJECT_REQUIRED", rel_path, "关系必须为对象"))
                continue
            require_enum(relation.get("type"), RELATION_TYPES, f"{rel_path}.type", issues)
            target = relation.get("target_event_id")
            if target not in events_map:
                issues.append(Issue("EVENT_REF_MISSING", f"{rel_path}.target_event_id", f"不存在事件 {target}"))
            if target == event_id:
                issues.append(Issue("SELF_RELATION", rel_path, "事件不得引用自身"))

    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list):
        issues.append(Issue("ARRAY_REQUIRED", "$.scenarios", "情景必须为数组"))
        scenarios = []
    if gate_forecast == "PASS":
        names = {item.get("scenario") for item in scenarios if isinstance(item, dict)}
        if names != SCENARIOS or len(scenarios) != 3:
            issues.append(Issue("SCENARIO_SET_INVALID", "$.scenarios", "预测开放时必须且只能提供 BEAR、BASE、BULL 三个情景"))
    probability_sum = 0.0
    for index, scenario in enumerate(scenarios):
        path = f"$.scenarios[{index}]"
        if not isinstance(scenario, dict):
            issues.append(Issue("OBJECT_REQUIRED", path, "情景必须为对象"))
            continue
        require_enum(scenario.get("scenario"), SCENARIOS, f"{path}.scenario", issues)
        probability = scenario.get("probability")
        if not isinstance(probability, (int, float)) or isinstance(probability, bool) or not 0 <= float(probability) <= 1:
            issues.append(Issue("PROBABILITY_INVALID", f"{path}.probability", "概率必须在 0–1 之间"))
        else:
            probability_sum += float(probability)
        horizon = scenario.get("horizon_trading_days")
        if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
            issues.append(Issue("HORIZON_INVALID", f"{path}.horizon_trading_days", "情景期限必须是正整数"))
        sample_size = scenario.get("sample_size")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 0:
            issues.append(Issue("SAMPLE_SIZE_INVALID", f"{path}.sample_size", "样本数必须是非负整数"))
        required_string(scenario, "method", path, issues)
        invalidators = scenario.get("invalidators")
        if not isinstance(invalidators, list) or not invalidators or not all(isinstance(x, str) and x.strip() for x in invalidators):
            issues.append(Issue("INVALIDATOR_REQUIRED", f"{path}.invalidators", "每个情景必须有非空失效条件"))
        price_path = scenario.get("price_path")
        if not isinstance(price_path, list) or len(price_path) < 2:
            issues.append(Issue("PRICE_PATH_REQUIRED", f"{path}.price_path", "价格路径至少需要两个时点"))
            continue
        previous_day = -1
        for point_index, point in enumerate(price_path):
            point_path = f"{path}.price_path[{point_index}]"
            if not isinstance(point, dict):
                issues.append(Issue("OBJECT_REQUIRED", point_path, "路径点必须为对象"))
                continue
            day = point.get("day")
            low = point.get("low")
            mid = point.get("mid")
            high = point.get("high")
            if not isinstance(day, int) or isinstance(day, bool) or day <= previous_day:
                issues.append(Issue("DAY_ORDER_INVALID", f"{point_path}.day", "交易日必须为严格递增整数"))
            else:
                previous_day = day
            values = (low, mid, high)
            if any(not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(float(number)) for number in values):
                issues.append(Issue("PRICE_INVALID", point_path, "low、mid、high 必须为有限数值"))
            elif not (0 < float(low) <= float(mid) <= float(high)):
                issues.append(Issue("PRICE_BAND_INVALID", point_path, "必须满足 0 < low ≤ mid ≤ high"))
    if scenarios and abs(probability_sum - 1.0) > 1e-6:
        issues.append(Issue("PROBABILITY_SUM_INVALID", "$.scenarios", f"情景概率之和必须为 1，当前为 {probability_sum:.8f}"))

    context = value.get("user_context")
    context_sufficient = isinstance(context, dict) and context.get("sufficient_for_action") is True
    actions = value.get("actions")
    if not isinstance(actions, list):
        issues.append(Issue("ARRAY_REQUIRED", "$.actions", "动作必须为数组"))
        actions = []
    for index, action in enumerate(actions):
        path = f"$.actions[{index}]"
        if not isinstance(action, dict):
            issues.append(Issue("OBJECT_REQUIRED", path, "动作必须为对象"))
            continue
        verb = action.get("action")
        require_enum(verb, ACTIONS, f"{path}.action", issues)
        if run_capability in {"RESEARCH_ONLY", "BLOCKED"} and verb not in PASSIVE_ACTIONS:
            issues.append(Issue("ACTION_BLOCKED_BY_MARKET", path, "当前市场能力只允许观察、无动作或仅研究"))
        if gate_action != "PASS" and verb not in PASSIVE_ACTIONS:
            issues.append(Issue("ACTION_GATE_BLOCKED", path, "动作门未通过时不得给出主动动作"))
        if verb in ACTIONABLE_ACTIONS:
            if not context_sufficient:
                issues.append(Issue("USER_CONTEXT_INSUFFICIENT", path, "主动动作需要充分用户约束"))
            if gate_forecast != "PASS":
                issues.append(Issue("ACTION_WITHOUT_FORECAST", path, "主动动作需要预测门通过"))
            for key in ("trigger", "risk_limit"):
                required_string(action, key, path, issues)
            size = action.get("size")
            if not isinstance(size, dict) or size.get("unit") not in {"PERCENT_CURRENT_POSITION", "PERCENT_PLANNED_POSITION"}:
                issues.append(Issue("ACTION_SIZE_INVALID", f"{path}.size", "动作规模必须使用计划仓位或当前仓位百分比"))
            elif not isinstance(size.get("value"), (int, float)) or isinstance(size.get("value"), bool) or not 0 < float(size.get("value")) <= 100:
                issues.append(Issue("ACTION_SIZE_INVALID", f"{path}.size.value", "动作百分比必须在 0–100 之间"))
            invalidators = action.get("invalidators")
            if not isinstance(invalidators, list) or not invalidators:
                issues.append(Issue("ACTION_INVALIDATOR_REQUIRED", f"{path}.invalidators", "主动动作必须有失效条件"))
        refs = action.get("rationale_claim_ids", [])
        if not isinstance(refs, list):
            issues.append(Issue("ARRAY_REQUIRED", f"{path}.rationale_claim_ids", "动作依据必须为声明引用数组"))
        else:
            for ref in refs:
                if ref not in claims_map:
                    issues.append(Issue("CLAIM_REF_MISSING", f"{path}.rationale_claim_ids", f"不存在声明 {ref}"))

    if run_capability == "BLOCKED" and gate_evidence == "PASS":
        issues.append(Issue("EVIDENCE_GATE_CONFLICT", "$.gates.evidence", "市场能力已阻断时证据门不能标记 PASS"))
    return issues


def fail_if_issues(issues: Sequence[Issue]) -> None:
    if issues:
        raise ValidationFailure(issues)


def escape_mermaid(text: Any) -> str:
    return str(text).replace('"', "'").replace("[", "(").replace("]", ")").replace("\n", " ")


def format_time(value: Any) -> str:
    if not isinstance(value, str):
        return "UNKNOWN"
    return value.replace("T", " ")


def render_report(bundle: Mapping[str, Any]) -> str:
    security = bundle["security"]
    capability = bundle["market_capability"]
    gates = bundle["gates"]
    lines = [
        f"# 股票事件航图：{security['name']}（{security['ticker']}）",
        "",
        "> 本报告是事件驱动研究与风险约束下的决策支持，不是收益承诺，不连接券商，也不执行订单。",
        "",
        "## 结论与当前能力",
        "",
        f"- 分析时点：`{bundle['as_of']}`",
        f"- 市场：`{capability.get('market', 'UNKNOWN')}` / MIC `{security['mic']}`",
        f"- 覆盖层级：`{capability['coverage_tier']}`",
        f"- 本次运行能力：`{capability['run_capability']}`",
        f"- 身份 / 证据 / 预测 / 动作门：`{gates['identity']}` / `{gates['evidence']}` / `{gates['forecast']}` / `{gates['action']}`",
        "",
    ]
    reasons = capability.get("reasons") or []
    if reasons:
        lines += ["### 能力限制", ""] + [f"- {item}" for item in reasons] + [""]
    lines += ["## 事件时间线", "", "| 时间 | 状态 | 类型 | 事件 | 影响机制 |", "|---|---|---|---|---|"]
    for event in sorted(bundle.get("events", []), key=lambda item: item.get("effective_at", "")):
        lines.append(
            f"| {format_time(event.get('effective_at'))} | `{event.get('status')}` | `{event.get('event_type')}` | "
            f"{event.get('title')} | {', '.join(event.get('impact_mechanisms', []))} |"
        )
    lines += ["", "## Bull / Base / Bear 概率路径", "", "| 情景 | 概率 | 期限 | 末端区间 | 样本数 | 置信度 |", "|---|---:|---:|---:|---:|---|"]
    for scenario in sorted(bundle.get("scenarios", []), key=lambda item: ("BEAR", "BASE", "BULL").index(item.get("scenario")) if item.get("scenario") in SCENARIOS else 9):
        path = scenario.get("price_path") or []
        endpoint = path[-1] if path else {}
        lines.append(
            f"| `{scenario.get('scenario')}` | {float(scenario.get('probability', 0)):.1%} | "
            f"{scenario.get('horizon_trading_days')} 个交易日 | "
            f"{endpoint.get('low', '—')}–{endpoint.get('high', '—')} | {scenario.get('sample_size', '—')} | "
            f"{scenario.get('confidence', 'UNKNOWN')} |"
        )
    lines += ["", "### 情景失效条件", ""]
    for scenario in bundle.get("scenarios", []):
        lines.append(f"- **{scenario.get('scenario')}**：" + "；".join(scenario.get("invalidators", [])))
    lines += ["", "## 条件动作", ""]
    actions = bundle.get("actions", [])
    if not actions:
        lines.append("- `NO_ACTION`：当前分析包未开放动作输出。")
    for action in actions:
        size = action.get("size") or {}
        size_text = f"{size.get('value')}% {size.get('unit')}" if size else "不适用"
        lines += [
            f"### `{action.get('action')}`",
            "",
            f"- 规模：{size_text}",
            f"- 触发：{action.get('trigger', '不适用')}",
            f"- 风险上限：{action.get('risk_limit', '不适用')}",
            f"- 失效：{'；'.join(action.get('invalidators', [])) or '不适用'}",
            "",
        ]
    lines += ["## 声明分层", "", "| 层级 | 声明 | 置信度 | 证据 |", "|---|---|---:|---|"]
    for claim in bundle.get("claims", []):
        lines.append(
            f"| `{claim.get('layer')}` | {claim.get('text')} | {float(claim.get('confidence', 0)):.0%} | "
            f"{', '.join(claim.get('evidence_ids', [])) or '—'} |"
        )
    lines += ["", "## 证据账本", "", "| ID | 等级 | 来源类型 | 发布时间 | 观察时间 | 定位 |", "|---|---|---|---|---|---|"]
    for evidence in bundle.get("evidence", []):
        locator = evidence.get("url") or evidence.get("locator") or "—"
        lines.append(
            f"| `{evidence.get('evidence_id')}` | `{evidence.get('tier')}` | `{evidence.get('source_type')}` | "
            f"{format_time(evidence.get('published_at'))} | {format_time(evidence.get('observed_at'))} | `{locator}` |"
        )
    disclosures = bundle.get("disclosures") or []
    if disclosures:
        lines += ["", "## 限制与披露", ""] + [f"- {item}" for item in disclosures]
    lines += ["", "---", "", f"生成器：Equity Event Atlas v{VERSION}", ""]
    return "\n".join(lines)


def render_timeline(bundle: Mapping[str, Any]) -> str:
    lines = ["timeline", f"    title {escape_mermaid(bundle['security']['name'])} 股票事件航线"]
    events = sorted(bundle.get("events", []), key=lambda item: item.get("effective_at", ""))
    for event in events:
        date = str(event.get("effective_at", "UNKNOWN"))[:10]
        lines.append(f"    {date} : {escape_mermaid(event.get('status'))} : {escape_mermaid(event.get('title'))}")
    return "\n".join(lines) + "\n"


def render_graph(bundle: Mapping[str, Any]) -> str:
    lines = ["flowchart LR"]
    events = bundle.get("events", [])
    for event in events:
        node = re.sub(r"[^A-Za-z0-9_]", "_", str(event.get("event_id")))
        label = escape_mermaid(f"{event.get('title')} | {event.get('status')}")
        lines.append(f'    {node}["{label}"]')
    for event in events:
        source = re.sub(r"[^A-Za-z0-9_]", "_", str(event.get("event_id")))
        for relation in event.get("relationships", []):
            target = re.sub(r"[^A-Za-z0-9_]", "_", str(relation.get("target_event_id")))
            lines.append(f"    {source} -->|{escape_mermaid(relation.get('type'))}| {target}")
    return "\n".join(lines) + "\n"


def svg_text(x: float, y: float, text: Any, *, size: int = 14, anchor: str = "start", weight: str = "normal") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{html.escape(str(text))}</text>'


def scale(value: float, low: float, high: float, start: float, end: float) -> float:
    if high <= low:
        return (start + end) / 2
    return start + (value - low) * (end - start) / (high - low)


def render_scenario_svg(bundle: Mapping[str, Any]) -> str:
    width, height = 1100, 660
    left, right, top, bottom = 90, 1040, 80, 570
    scenarios = bundle.get("scenarios", [])
    points = [point for scenario in scenarios for point in scenario.get("price_path", [])]
    if not points:
        raise ValueError("没有可渲染的价格路径")
    all_days = [float(point["day"]) for point in points]
    all_prices = [float(point[key]) for point in points for key in ("low", "mid", "high")]
    day_min, day_max = min(all_days), max(all_days)
    price_min, price_max = min(all_prices), max(all_prices)
    margin = max((price_max - price_min) * 0.08, 1.0)
    price_min = max(0.0, price_min - margin)
    price_max += margin
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{html.escape(bundle["security"]["name"])} 概率价格路径</title>',
        '<desc id="desc">Bull、Base、Bear 三情景的价格区间与中位路径，不构成收益承诺。</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 34, f'{bundle["security"]["name"]}：Bull / Base / Bear 概率路径', size=22, anchor="middle", weight="bold"),
        svg_text(width / 2, 58, f'分析时点 {bundle["as_of"]}；区间不是单点目标价', size=13, anchor="middle"),
    ]
    for tick in range(6):
        value = price_min + (price_max - price_min) * tick / 5
        y = scale(value, price_min, price_max, bottom, top)
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#d9d9d9" stroke-width="1"/>')
        svg.append(svg_text(left - 12, y + 5, f'{value:.2f}', anchor="end", size=12))
    for tick in range(6):
        day = day_min + (day_max - day_min) * tick / 5
        x = scale(day, day_min, day_max, left, right)
        svg.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="#eeeeee" stroke-width="1"/>')
        svg.append(svg_text(x, bottom + 25, f'{day:.0f}', anchor="middle", size=12))
    styles = {
        "BEAR": ("#9b2c2c", "#f9d6d5"),
        "BASE": ("#2b6cb0", "#d7e9f8"),
        "BULL": ("#2f855a", "#d8f3e5"),
    }
    legend_y = 95
    for scenario in sorted(scenarios, key=lambda item: ("BEAR", "BASE", "BULL").index(item["scenario"])):
        name = scenario["scenario"]
        line_color, fill_color = styles[name]
        path = scenario["price_path"]
        upper = [(scale(float(point["day"]), day_min, day_max, left, right), scale(float(point["high"]), price_min, price_max, bottom, top)) for point in path]
        lower = [(scale(float(point["day"]), day_min, day_max, left, right), scale(float(point["low"]), price_min, price_max, bottom, top)) for point in reversed(path)]
        polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in upper + lower)
        mid = [(scale(float(point["day"]), day_min, day_max, left, right), scale(float(point["mid"]), price_min, price_max, bottom, top)) for point in path]
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in mid)
        svg.append(f'<polygon points="{polygon}" fill="{fill_color}" fill-opacity="0.55" stroke="none"/>')
        svg.append(f'<polyline points="{polyline}" fill="none" stroke="{line_color}" stroke-width="3"/>')
        svg.append(f'<line x1="{right - 250}" y1="{legend_y - 5}" x2="{right - 215}" y2="{legend_y - 5}" stroke="{line_color}" stroke-width="4"/>')
        svg.append(svg_text(right - 205, legend_y, f'{name} {float(scenario["probability"]):.0%}', size=13))
        legend_y += 25
    svg += [
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333333" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333333" stroke-width="1.5"/>',
        svg_text((left + right) / 2, height - 35, "交易日", anchor="middle", size=14),
        f'<g transform="translate(24 {(top + bottom) / 2}) rotate(-90)">{svg_text(0, 0, security_currency(bundle), anchor="middle", size=14)}</g>',
        svg_text(width / 2, height - 10, "仅用于展示已提供情景；真实结果可能超出区间。", anchor="middle", size=12),
        '</svg>',
    ]
    return "\n".join(svg) + "\n"


def security_currency(bundle: Mapping[str, Any]) -> str:
    return f"价格（{bundle.get('security', {}).get('currency', 'UNKNOWN')}）"


def render_supply_svg(bundle: Mapping[str, Any]) -> str:
    width, height = 1100, 620
    left, right, top, bottom = 110, 1040, 90, 520
    items = bundle.get("supply_waterfall", [])
    if not isinstance(items, list) or not items:
        items = [{"label": "未提供供应变化", "delta": 0.0}]
    deltas = [float(item.get("delta", 0.0)) for item in items]
    cumulative = []
    running = 0.0
    for delta in deltas:
        start = running
        running += delta
        cumulative.append((start, running))
    values = [0.0] + [value for pair in cumulative for value in pair]
    y_min, y_max = min(values), max(values)
    margin = max((y_max - y_min) * 0.1, 1.0)
    y_min -= margin
    y_max += margin
    column = (right - left) / max(len(items), 1)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{html.escape(bundle["security"]["name"])} 股份供应瀑布</title>',
        '<desc id="desc">展示分析包中明确提供的潜在供应增减，不把可出售股份等同于实际出售。</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 34, f'{bundle["security"]["name"]}：潜在供应变化瀑布图', size=22, anchor="middle", weight="bold"),
        svg_text(width / 2, 58, "可出售 ≠ 实际出售 ≠ 净新增市场供给", size=13, anchor="middle"),
    ]
    zero_y = scale(0, y_min, y_max, bottom, top)
    svg.append(f'<line x1="{left}" y1="{zero_y:.1f}" x2="{right}" y2="{zero_y:.1f}" stroke="#333333" stroke-width="1.5"/>')
    for index, (item, pair) in enumerate(zip(items, cumulative)):
        start, end = pair
        x = left + index * column + column * 0.18
        bar_width = column * 0.64
        y1 = scale(start, y_min, y_max, bottom, top)
        y2 = scale(end, y_min, y_max, bottom, top)
        y = min(y1, y2)
        h = max(abs(y2 - y1), 2.0)
        fill = "#2f855a" if end >= start else "#9b2c2c"
        svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{h:.1f}" fill="{fill}" fill-opacity="0.78"/>')
        svg.append(svg_text(x + bar_width / 2, y - 8, f'{float(item.get("delta", 0)):+.2f}', anchor="middle", size=13, weight="bold"))
        label = str(item.get("label", ""))
        if len(label) > 12:
            label = label[:12] + "…"
        svg.append(svg_text(x + bar_width / 2, bottom + 28, label, anchor="middle", size=12))
        if index < len(items) - 1:
            next_x = left + (index + 1) * column + column * 0.18
            svg.append(f'<line x1="{x + bar_width:.1f}" y1="{y2:.1f}" x2="{next_x:.1f}" y2="{y2:.1f}" stroke="#777777" stroke-dasharray="4 3"/>')
    svg += [
        svg_text(28, (top + bottom) / 2, "供应单位（由输入定义）", anchor="middle", size=14),
        svg_text(width / 2, height - 24, "图表只渲染输入事实与假设；没有证据时不得自动补值。", anchor="middle", size=12),
        '</svg>',
    ]
    return "\n".join(svg) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.replace(temporary, path)


def render_bundle(bundle_path: Path, output_dir: Path) -> Dict[str, str]:
    bundle = load_json(bundle_path)
    fail_if_issues(validate_bundle(bundle, bundle_path.parent))
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: Dict[str, str] = {
        "REPORT.md": render_report(bundle),
        "event_timeline.mmd": render_timeline(bundle),
        "event_graph.mmd": render_graph(bundle),
        "scenario_fan.svg": render_scenario_svg(bundle),
        "supply_waterfall.svg": render_supply_svg(bundle),
    }
    status = {
        "schema": "equity-event-atlas/status-fragment-v1",
        "skill": "equity-event-atlas",
        "version": VERSION,
        "as_of": bundle["as_of"],
        "security": bundle["security"],
        "market_capability": bundle["market_capability"],
        "gates": bundle["gates"],
        "service_required": False,
        "runtime_state": "STATELESS_OUTPUT_RENDERED",
    }
    rendered["STATUS_FRAGMENT.json"] = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    for name, content in rendered.items():
        atomic_write(output_dir / name, content)
    manifest = {
        "schema": "equity-event-atlas/render-manifest-v1",
        "files": [
            {
                "path": name,
                "bytes": (output_dir / name).stat().st_size,
                "sha256": sha256_file(output_dir / name),
            }
            for name in sorted(rendered)
        ],
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write(output_dir / "render_manifest.json", manifest_text)
    return {item["path"]: item["sha256"] for item in manifest["files"]}


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        rel = path.relative_to(directory).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def self_test(fixtures: Path, repeat: int) -> Dict[str, Any]:
    valid_request = fixtures / "valid_request_us.json"
    valid_bundle = fixtures / "valid_bundle_synthetic.json"
    invalid_dir = fixtures / "invalid"
    results: Dict[str, Any] = {"request": None, "bundle": None, "invalid": {}, "deterministic": None}
    request_issues = validate_request(load_json(valid_request))
    fail_if_issues(request_issues)
    results["request"] = "PASS"
    bundle_value = load_json(valid_bundle)
    bundle_issues = validate_bundle(bundle_value, valid_bundle.parent)
    fail_if_issues(bundle_issues)
    results["bundle"] = "PASS"
    invalid_files = sorted(invalid_dir.glob("*.json"))
    if not invalid_files:
        raise RuntimeError("缺少负向 Fixture")
    for path in invalid_files:
        issues = validate_bundle(load_json(path), path.parent)
        if not issues:
            raise RuntimeError(f"负向 Fixture 未被拒绝：{path.name}")
        results["invalid"][path.name] = sorted({issue.code for issue in issues})
    digests = []
    for _ in range(max(2, repeat)):
        with tempfile.TemporaryDirectory(prefix="eea-self-test-") as temp:
            target = Path(temp) / "rendered"
            render_bundle(valid_bundle, target)
            digests.append(tree_digest(target))
    if len(set(digests)) != 1:
        raise RuntimeError("重复渲染结果不确定")
    results["deterministic"] = {"status": "PASS", "sha256": digests[0], "repeat": len(digests)}
    results["status"] = "PASS"
    return results


def print_validation(issues: Sequence[Issue], json_output: bool) -> int:
    status = "PASS" if not issues else "FAIL"
    payload = {"status": status, "issue_count": len(issues), "issues": [issue.as_dict() for issue in issues]}
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"validation: {status}")
        for issue in issues:
            print(f"- [{issue.code}] {issue.path}: {issue.message}")
    return 0 if not issues else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="equity-event-atlas", description="股票事件航图确定性工具")
    sub = parser.add_subparsers(dest="command", required=True)
    request = sub.add_parser("validate-request", help="校验宿主请求")
    request.add_argument("file", type=Path)
    request.add_argument("--json", action="store_true")
    bundle = sub.add_parser("validate-bundle", help="校验分析包")
    bundle.add_argument("file", type=Path)
    bundle.add_argument("--json", action="store_true")
    render = sub.add_parser("render", help="渲染 Markdown、Mermaid、SVG 与状态片段")
    render.add_argument("file", type=Path)
    render.add_argument("--output", required=True, type=Path)
    capability = sub.add_parser("capability", help="计算本次市场能力门")
    capability.add_argument("mic")
    capability.add_argument("--official-sources-verified", action="store_true")
    capability.add_argument("--calendar-verified", action="store_true")
    capability.add_argument("--market-data-verified", action="store_true")
    test = sub.add_parser("self-test", help="运行离线即时自检")
    test.add_argument("--fixtures", required=True, type=Path)
    test.add_argument("--repeat", type=int, default=2)
    sub.add_parser("version", help="输出版本")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-request":
            value = load_json(args.file)
            return print_validation(validate_request(value), args.json)
        if args.command == "validate-bundle":
            value = load_json(args.file)
            return print_validation(validate_bundle(value, args.file.parent), args.json)
        if args.command == "render":
            hashes = render_bundle(args.file, args.output)
            print(json.dumps({"status": "PASS", "output": str(args.output), "files": hashes}, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "capability":
            result = market_capability(
                args.mic,
                official_sources_verified=args.official_sources_verified,
                calendar_verified=args.calendar_verified,
                market_data_verified=args.market_data_verified,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "self-test":
            print(json.dumps(self_test(args.fixtures, args.repeat), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "version":
            print(VERSION)
            return 0
    except ValidationFailure as exc:
        print_validation(exc.issues, True)
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
