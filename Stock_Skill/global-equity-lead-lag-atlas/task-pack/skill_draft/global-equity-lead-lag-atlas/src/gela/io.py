from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import AnalysisConfig, MarketSession

REQUIRED_COLUMNS = (
    "market_id",
    "country_iso3",
    "country_name_zh",
    "index_name",
    "instrument_type",
    "return_type",
    "currency",
    "timezone",
    "latitude",
    "longitude",
    "session_date",
    "open_ts_utc",
    "close_ts_utc",
    "close",
    "source",
    "source_symbol",
    "source_retrieved_at",
)

ANALYSIS_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_DATA_USAGE_MODES = {"user_provided", "licensed_provider", "synthetic_fixture"}
ALLOWED_RETURN_TYPES = {"price", "total_return", "net_total_return"}


def parse_utc(value: str, field_name: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} 不是有效 ISO-8601 时间: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field_name} 必须显式为 UTC: {value}")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> AnalysisConfig:
    config_path = path.resolve()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("配置根节点必须是 JSON object")
    base = config_path.parent
    allowed = {
        "analysis_id", "input_csv", "output_dir", "horizons", "source_lags", "alpha",
        "min_raw_n", "min_effective_n", "min_abs_effect", "min_stability",
        "min_oos_improvement", "bootstrap_repetitions", "bootstrap_block",
        "rolling_windows", "max_base_staleness_hours", "random_seed", "fdr_scope",
        "currency_mode", "causal_claims", "data_usage_mode",
        "license_acknowledgement", "generated_at",
    }
    unknown = sorted(set(data).difference(allowed))
    if unknown:
        raise ValueError("配置包含未知字段: " + ", ".join(unknown))
    required = ("analysis_id", "input_csv", "output_dir", "license_acknowledgement")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"配置缺少字段: {', '.join(missing)}")

    analysis_id = str(data["analysis_id"]).strip()
    if not ANALYSIS_ID_PATTERN.fullmatch(analysis_id):
        raise ValueError("analysis_id 必须为 1–128 位字母、数字、点、下划线或连字符，且以字母或数字开头")
    input_value = str(data["input_csv"]).strip()
    output_value = str(data["output_dir"]).strip()
    if not input_value or not output_value:
        raise ValueError("input_csv 与 output_dir 不得为空")
    input_csv = (base / input_value).resolve()
    output_dir = (base / output_value).resolve()
    if output_dir.parent == output_dir:
        raise ValueError("output_dir 不得是文件系统根目录")
    if output_dir == input_csv or output_dir in input_csv.parents:
        raise ValueError("output_dir 必须是独立目录，不得等于输入文件或其父目录")

    try:
        horizons = tuple(int(v) for v in data.get("horizons", [1, 5, 10, 15, 21, 63, 126]))
        lags = tuple(int(v) for v in data.get("source_lags", [0, 1, 2, 3, 5]))
    except (TypeError, ValueError) as exc:
        raise ValueError("horizons 与 source_lags 必须是整数数组") from exc
    if not horizons or any(v <= 0 for v in horizons):
        raise ValueError("horizons 必须是非空正整数列表")
    if not lags or any(v < 0 for v in lags):
        raise ValueError("source_lags 必须是非空非负整数列表")
    if len(horizons) > 32 or len(set(horizons)) != len(horizons) or tuple(sorted(horizons)) != horizons:
        raise ValueError("horizons 必须唯一、严格升序且最多 32 项")
    if len(lags) > 32 or len(set(lags)) != len(lags) or tuple(sorted(lags)) != lags:
        raise ValueError("source_lags 必须唯一、严格升序且最多 32 项")
    if max(horizons) > 5040 or max(lags) > 2520:
        raise ValueError("horizon 或 source_lag 超出有界运行上限")
    if data.get("causal_claims", False):
        raise ValueError("v0.0.0.1 禁止 causal_claims=true")
    if data["license_acknowledgement"] is not True:
        raise ValueError("必须确认数据使用权：license_acknowledgement=true")

    alpha = float(data.get("alpha", 0.05))
    min_raw_n = int(data.get("min_raw_n", 80))
    min_effective_n = int(data.get("min_effective_n", 20))
    min_abs_effect = float(data.get("min_abs_effect", 0.15))
    min_stability = float(data.get("min_stability", 0.67))
    min_oos_improvement = float(data.get("min_oos_improvement", 0.0))
    bootstrap_repetitions = int(data.get("bootstrap_repetitions", 300))
    bootstrap_block = int(data.get("bootstrap_block", 10))
    rolling_windows = int(data.get("rolling_windows", 4))
    max_base_staleness_hours = float(data.get("max_base_staleness_hours", 96.0))
    fdr_scope = str(data.get("fdr_scope", "global"))
    currency_mode = str(data.get("currency_mode", "local"))
    data_usage_mode = str(data.get("data_usage_mode", "user_provided"))
    generated_at = data.get("generated_at")

    if not 0 < alpha < 1:
        raise ValueError("alpha 必须位于 0 与 1 之间")
    if min_raw_n < 8 or min_effective_n < 3 or min_effective_n > min_raw_n:
        raise ValueError("样本阈值不安全：min_raw_n>=8 且 3<=min_effective_n<=min_raw_n")
    if not 0 <= min_abs_effect <= 1:
        raise ValueError("min_abs_effect 必须位于 0 与 1 之间")
    if not 0 <= min_stability <= 1:
        raise ValueError("min_stability 必须位于 0 与 1 之间")
    if not -1 <= min_oos_improvement <= 1:
        raise ValueError("min_oos_improvement 必须位于 -1 与 1 之间")
    if not 20 <= bootstrap_repetitions <= 10000:
        raise ValueError("bootstrap_repetitions 必须位于 20 与 10000 之间")
    if not 1 <= bootstrap_block <= 5040 or not 2 <= rolling_windows <= 100:
        raise ValueError("Bootstrap block 或 rolling_windows 超出有界运行范围")
    if not 0 < max_base_staleness_hours <= 744:
        raise ValueError("max_base_staleness_hours 必须大于 0 且不超过 744")
    if fdr_scope != "global":
        raise ValueError("v0.0.0.1 仅支持 fdr_scope=global")
    if currency_mode not in {"local", "usd"}:
        raise ValueError("currency_mode 仅支持 local 或 usd")
    if data_usage_mode not in ALLOWED_DATA_USAGE_MODES:
        raise ValueError("data_usage_mode 仅支持 user_provided、licensed_provider 或 synthetic_fixture")
    if generated_at is not None:
        generated_at = _utc_text(parse_utc(str(generated_at), "generated_at"))

    return AnalysisConfig(
        analysis_id=analysis_id,
        input_csv=input_csv,
        output_dir=output_dir,
        horizons=horizons,
        source_lags=lags,
        alpha=alpha,
        min_raw_n=min_raw_n,
        min_effective_n=min_effective_n,
        min_abs_effect=min_abs_effect,
        min_stability=min_stability,
        min_oos_improvement=min_oos_improvement,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_block=bootstrap_block,
        rolling_windows=rolling_windows,
        max_base_staleness_hours=max_base_staleness_hours,
        random_seed=int(data.get("random_seed", 20260726)),
        fdr_scope=fdr_scope,
        currency_mode=currency_mode,
        causal_claims=False,
        data_usage_mode=data_usage_mode,
        license_acknowledgement=True,
        generated_at=generated_at,
    )


def load_sessions(path: Path) -> tuple[dict[str, list[MarketSession]], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(f"输入 CSV 不存在: {path}")
    warnings: list[str] = []
    warned_timezones: set[str] = set()
    markets: dict[str, list[MarketSession]] = {}
    identities: dict[str, tuple[Any, ...]] = {}
    seen: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        extra = [column for column in headers if column not in REQUIRED_COLUMNS]
        if missing:
            raise ValueError(f"CSV 缺少列: {', '.join(missing)}")
        if extra:
            raise ValueError(f"CSV 包含未声明列: {', '.join(extra)}")
        for row_number, row in enumerate(reader, start=2):
            market_id = row["market_id"].strip()
            if not market_id:
                raise ValueError(f"第 {row_number} 行 market_id 为空")
            session_date = row["session_date"].strip()
            try:
                date.fromisoformat(session_date)
            except ValueError as exc:
                raise ValueError(f"第 {row_number} 行 session_date 必须为 YYYY-MM-DD") from exc
            key = (market_id, session_date)
            if key in seen:
                raise ValueError(f"重复市场会话: {market_id} / {key[1]}")
            seen.add(key)

            open_ts = parse_utc(row["open_ts_utc"], "open_ts_utc")
            close_ts = parse_utc(row["close_ts_utc"], "close_ts_utc")
            retrieved_ts = parse_utc(row["source_retrieved_at"], "source_retrieved_at")
            if not open_ts < close_ts:
                raise ValueError(f"第 {row_number} 行必须 open_ts_utc < close_ts_utc")
            if retrieved_ts < close_ts:
                raise ValueError(f"第 {row_number} 行 source_retrieved_at 不得早于 close_ts_utc")

            close = float(row["close"])
            if not math_is_finite_positive(close):
                raise ValueError(f"第 {row_number} 行 close 必须为有限正数")
            country_iso3 = row["country_iso3"].strip().upper()
            currency = row["currency"].strip().upper()
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            instrument_type = row["instrument_type"].strip().lower()
            return_type = row["return_type"].strip().lower()
            timezone_name = row["timezone"].strip()

            if len(country_iso3) != 3 or not country_iso3.isalpha():
                raise ValueError(f"第 {row_number} 行 country_iso3 必须为三位字母")
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError(f"第 {row_number} 行 currency 必须为三位字母")
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError(f"第 {row_number} 行经纬度超出范围")
            if instrument_type != "cash_index":
                raise ValueError(f"第 {row_number} 行 instrument_type 必须为 cash_index；不得以 ETF 代替本地现金指数")
            if return_type not in ALLOWED_RETURN_TYPES:
                raise ValueError(f"第 {row_number} 行 return_type 不受支持")
            if not row["country_name_zh"].strip() or not row["index_name"].strip():
                raise ValueError(f"第 {row_number} 行市场名称或指数名称为空")
            if not timezone_name or not row["source"].strip() or not row["source_symbol"].strip():
                raise ValueError(f"第 {row_number} 行时区、来源或来源代码为空")

            try:
                local_close_date = close_ts.astimezone(ZoneInfo(timezone_name)).date().isoformat()
            except ZoneInfoNotFoundError:
                if timezone_name not in warned_timezones:
                    warnings.append(f"{market_id}: 当前主机无法核验 IANA timezone={timezone_name}；UTC 时序仍已验证")
                    warned_timezones.add(timezone_name)
            else:
                if local_close_date != session_date:
                    raise ValueError(
                        f"第 {row_number} 行 session_date={session_date} 与 {timezone_name} 本地收盘日期 {local_close_date} 不一致"
                    )

            session = MarketSession(
                market_id=market_id,
                country_iso3=country_iso3,
                country_name_zh=row["country_name_zh"].strip(),
                index_name=row["index_name"].strip(),
                instrument_type=instrument_type,
                return_type=return_type,
                currency=currency,
                timezone=timezone_name,
                latitude=latitude,
                longitude=longitude,
                session_date=session_date,
                open_ts_utc=open_ts,
                close_ts_utc=close_ts,
                close=close,
                source=row["source"].strip(),
                source_symbol=row["source_symbol"].strip(),
                source_retrieved_at=_utc_text(retrieved_ts),
            )
            identity = (
                session.country_iso3,
                session.country_name_zh,
                session.index_name,
                session.instrument_type,
                session.return_type,
                session.currency,
                session.timezone,
                session.latitude,
                session.longitude,
                session.source,
                session.source_symbol,
            )
            if market_id in identities and identities[market_id] != identity:
                raise ValueError(f"市场 {market_id} 的身份字段在不同会话中发生变化")
            identities[market_id] = identity
            markets.setdefault(market_id, []).append(session)

    if len(markets) < 2:
        raise ValueError("至少需要两个市场")
    return_types = {sessions[0].return_type for sessions in markets.values()}
    if len(return_types) != 1:
        raise ValueError("同一次分析不得混用 price、total_return 与 net_total_return 指数口径")
    for market_id, sessions in markets.items():
        sessions.sort(key=lambda value: value.close_ts_utc)
        if len(sessions) < 3:
            warnings.append(f"{market_id}: 会话数少于 3")
        for prior, current in zip(sessions, sessions[1:]):
            if not prior.close_ts_utc < current.close_ts_utc:
                raise ValueError(f"{market_id}: 收盘时间不是严格递增")
    return markets, warnings


def math_is_finite_positive(value: float) -> bool:
    return value > 0 and value != float("inf") and value != float("-inf") and value == value


def config_to_public_dict(config: AnalysisConfig) -> dict[str, Any]:
    return {
        "analysis_id": config.analysis_id,
        "horizons": list(config.horizons),
        "source_lags": list(config.source_lags),
        "alpha": config.alpha,
        "min_raw_n": config.min_raw_n,
        "min_effective_n": config.min_effective_n,
        "min_abs_effect": config.min_abs_effect,
        "min_stability": config.min_stability,
        "min_oos_improvement": config.min_oos_improvement,
        "bootstrap_repetitions": config.bootstrap_repetitions,
        "bootstrap_block": config.bootstrap_block,
        "rolling_windows": config.rolling_windows,
        "max_base_staleness_hours": config.max_base_staleness_hours,
        "random_seed": config.random_seed,
        "fdr_scope": config.fdr_scope,
        "currency_mode": config.currency_mode,
        "causal_claims": False,
        "data_usage_mode": config.data_usage_mode,
        "license_acknowledgement": True,
    }
