from __future__ import annotations

import bisect
import hashlib
import math
from datetime import datetime, timezone
from statistics import median
from typing import Any

from . import __version__
from .models import AnalysisConfig, CoMovement, Hypothesis, MarketSession
from .stats import (
    benjamini_hochberg,
    circular_block_bootstrap_ci,
    conservative_effective_n,
    fisher_two_sided_p,
    out_of_sample_mse_improvement,
    pearson,
    rolling_sign_stability,
    spearman,
)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return prefix + hashlib.sha256(raw).hexdigest()[:16]


def _hypothesis_id(source: str, target: str, horizon: int, lag: int) -> str:
    return _stable_id("H-", source, target, horizon, lag)


def _pair_id(market_a: str, market_b: str, horizon: int) -> str:
    return _stable_id("C-", market_a, market_b, horizon)


def _trailing_returns(sessions: list[MarketSession], horizon: int) -> list[float | None]:
    values: list[float | None] = [None] * len(sessions)
    for index in range(horizon, len(sessions)):
        values[index] = math.log(sessions[index].close / sessions[index - horizon].close)
    return values


def _forward_returns(sessions: list[MarketSession], horizon: int) -> list[float | None]:
    values: list[float | None] = [None] * len(sessions)
    for index in range(1, len(sessions)):
        end = index + horizon - 1
        if end < len(sessions):
            values[index] = math.log(sessions[end].close / sessions[index - 1].close)
    return values


def _same_session_date_values(
    market_a_sessions: list[MarketSession],
    market_b_sessions: list[MarketSession],
    returns_a: list[float | None],
    returns_b: list[float | None],
) -> tuple[list[float], list[float]]:
    """Pair trailing returns on the same declared local session_date.

    This symmetric co-movement view is intentionally separate from directional
    information-set alignment. It must not be used to infer which market led.
    """
    by_date_a = {
        session.session_date: value
        for session, value in zip(market_a_sessions, returns_a)
        if value is not None
    }
    by_date_b = {
        session.session_date: value
        for session, value in zip(market_b_sessions, returns_b)
        if value is not None
    }
    common_dates = sorted(set(by_date_a).intersection(by_date_b))
    return [by_date_a[value] for value in common_dates], [by_date_b[value] for value in common_dates]


def _paired_lead_lag_values(
    source_sessions: list[MarketSession],
    target_sessions: list[MarketSession],
    source_returns: list[float | None],
    target_returns: list[float | None],
    source_closes: list[datetime],
    source_lag: int,
    max_base_staleness_hours: float,
) -> tuple[list[float], list[float], list[float]]:
    x: list[float] = []
    y: list[float] = []
    lead_hours: list[float] = []
    for target_index, target in enumerate(target_sessions):
        target_value = target_returns[target_index]
        if target_value is None:
            continue
        base_source_index = bisect.bisect_left(source_closes, target.open_ts_utc) - 1
        if base_source_index < 0:
            continue
        base_staleness_hours = (
            target.open_ts_utc - source_sessions[base_source_index].close_ts_utc
        ).total_seconds() / 3600.0
        if base_staleness_hours > max_base_staleness_hours:
            continue
        source_index = base_source_index - source_lag
        if source_index < 0:
            continue
        source_value = source_returns[source_index]
        if source_value is None:
            continue
        if not source_sessions[source_index].close_ts_utc < target.open_ts_utc:
            raise AssertionError("检测到信息集前视")
        x.append(source_value)
        y.append(target_value)
        lead_hours.append(
            (target.open_ts_utc - source_sessions[source_index].close_ts_utc).total_seconds() / 3600.0
        )
    return x, y, lead_hours


def _market_public_summary(sessions: list[MarketSession]) -> dict[str, Any]:
    first = sessions[0]
    return {
        "market_id": first.market_id,
        "country_iso3": first.country_iso3,
        "country_name_zh": first.country_name_zh,
        "index_name": first.index_name,
        "instrument_type": first.instrument_type,
        "return_type": first.return_type,
        "currency": first.currency,
        "timezone": first.timezone,
        "latitude": first.latitude,
        "longitude": first.longitude,
        "source": first.source,
        "source_symbol": first.source_symbol,
        "session_count": len(sessions),
        "first_session": sessions[0].session_date,
        "last_session": sessions[-1].session_date,
    }


def _screen_common(
    n_raw: int,
    n_effective: int,
    effect: float | None,
    config: AnalysisConfig,
) -> list[str]:
    reasons: list[str] = []
    if n_raw < config.min_raw_n:
        reasons.append("RAW_SAMPLE_BELOW_THRESHOLD")
    if n_effective < config.min_effective_n:
        reasons.append("EFFECTIVE_SAMPLE_BELOW_THRESHOLD")
    if effect is None:
        reasons.append("CORRELATION_UNAVAILABLE")
    return reasons


def _analyze_co_movement(
    markets: dict[str, list[MarketSession]],
    config: AnalysisConfig,
    trailing_cache: dict[tuple[str, int], list[float | None]],
) -> tuple[list[CoMovement], list[CoMovement]]:
    market_ids = sorted(markets)
    results: list[CoMovement] = []
    for a_index, market_a in enumerate(market_ids):
        for market_b in market_ids[a_index + 1 :]:
            for horizon in config.horizons:
                x, y = _same_session_date_values(
                    markets[market_a],
                    markets[market_b],
                    trailing_cache[(market_a, horizon)],
                    trailing_cache[(market_b, horizon)],
                )
                pair_id = _pair_id(market_a, market_b, horizon)
                n_raw = len(x)
                n_effective = conservative_effective_n(n_raw, horizon)
                r = pearson(x, y)
                results.append(
                    CoMovement(
                        pair_id=pair_id,
                        market_a=market_a,
                        market_b=market_b,
                        horizon=horizon,
                        alignment="same_session_date_trailing_return",
                        n_raw=n_raw,
                        n_effective=n_effective,
                        pearson_r=r,
                        spearman_r=spearman(x, y),
                        p_value=fisher_two_sided_p(r, n_effective),
                        failure_reasons=_screen_common(n_raw, n_effective, r, config),
                    )
                )
    q_values = benjamini_hochberg([item.p_value for item in results])
    confirmed: list[CoMovement] = []
    for item, q_value in zip(results, q_values):
        item.q_value = q_value
        if item.failure_reasons:
            item.status = "INSUFFICIENT_OR_INVALID"
            continue
        if item.pearson_r is None or abs(item.pearson_r) < config.min_abs_effect:
            item.failure_reasons.append("EFFECT_BELOW_THRESHOLD")
        if q_value is None or q_value > config.alpha:
            item.failure_reasons.append("FDR_THRESHOLD_NOT_MET")
        if item.failure_reasons:
            item.status = "SCREEN_REJECTED"
            continue
        x, y = _same_session_date_values(
            markets[item.market_a],
            markets[item.market_b],
            trailing_cache[(item.market_a, item.horizon)],
            trailing_cache[(item.market_b, item.horizon)],
        )
        seed = config.random_seed + int(item.pair_id[-8:], 16)
        item.ci_low, item.ci_high = circular_block_bootstrap_ci(
            x,
            y,
            repetitions=config.bootstrap_repetitions,
            block_size=max(config.bootstrap_block, item.horizon),
            seed=seed,
        )
        item.rolling_sign_stability = rolling_sign_stability(
            x, y, config.rolling_windows, item.pearson_r
        )
        if item.ci_low is None or item.ci_high is None or item.ci_low <= 0 <= item.ci_high:
            item.failure_reasons.append("BOOTSTRAP_CI_INCLUDES_ZERO_OR_UNAVAILABLE")
        if item.rolling_sign_stability is None or item.rolling_sign_stability < config.min_stability:
            item.failure_reasons.append("ROLLING_STABILITY_BELOW_THRESHOLD")
        item.status = "CONFIRMED" if not item.failure_reasons else "CONFIRMATION_REJECTED"
        if item.status == "CONFIRMED":
            confirmed.append(item)
    return results, confirmed


def _analyze_lead_lag(
    markets: dict[str, list[MarketSession]],
    config: AnalysisConfig,
    trailing_cache: dict[tuple[str, int], list[float | None]],
    forward_cache: dict[tuple[str, int], list[float | None]],
    close_cache: dict[str, list[datetime]],
) -> tuple[list[Hypothesis], list[Hypothesis], list[Hypothesis]]:
    hypotheses: list[Hypothesis] = []
    market_ids = sorted(markets)
    for source in market_ids:
        for target in market_ids:
            if source == target:
                continue
            for horizon in config.horizons:
                for lag in config.source_lags:
                    x, y, hours = _paired_lead_lag_values(
                        markets[source],
                        markets[target],
                        trailing_cache[(source, horizon)],
                        forward_cache[(target, horizon)],
                        close_cache[source],
                        lag,
                        config.max_base_staleness_hours,
                    )
                    hypothesis_id = _hypothesis_id(source, target, horizon, lag)
                    n_raw = len(x)
                    n_effective = conservative_effective_n(n_raw, horizon)
                    r = pearson(x, y)
                    hypotheses.append(
                        Hypothesis(
                            hypothesis_id=hypothesis_id,
                            source_market=source,
                            target_market=target,
                            horizon=horizon,
                            source_lag=lag,
                            n_raw=n_raw,
                            n_effective=n_effective,
                            median_wall_clock_lead_hours=round(median(hours), 6) if hours else None,
                            pearson_r=r,
                            spearman_r=spearman(x, y),
                            p_value=fisher_two_sided_p(r, n_effective),
                            failure_reasons=_screen_common(n_raw, n_effective, r, config),
                        )
                    )
    q_values = benjamini_hochberg([item.p_value for item in hypotheses])
    for item, q_value in zip(hypotheses, q_values):
        item.q_value = q_value
        if item.failure_reasons:
            item.status = "INSUFFICIENT_OR_INVALID"
            continue
        if item.pearson_r is None or abs(item.pearson_r) < config.min_abs_effect:
            item.failure_reasons.append("EFFECT_BELOW_THRESHOLD")
        if q_value is None or q_value > config.alpha:
            item.failure_reasons.append("FDR_THRESHOLD_NOT_MET")
        if item.failure_reasons:
            item.status = "SCREEN_REJECTED"
            continue
        x, y, _ = _paired_lead_lag_values(
            markets[item.source_market],
            markets[item.target_market],
            trailing_cache[(item.source_market, item.horizon)],
            forward_cache[(item.target_market, item.horizon)],
            close_cache[item.source_market],
            item.source_lag,
            config.max_base_staleness_hours,
        )
        seed = config.random_seed + int(item.hypothesis_id[-8:], 16)
        item.ci_low, item.ci_high = circular_block_bootstrap_ci(
            x,
            y,
            repetitions=config.bootstrap_repetitions,
            block_size=max(config.bootstrap_block, item.horizon),
            seed=seed,
        )
        item.rolling_sign_stability = rolling_sign_stability(
            x, y, config.rolling_windows, item.pearson_r
        )
        item.oos_mse_improvement = out_of_sample_mse_improvement(x, y)
        if item.ci_low is None or item.ci_high is None or item.ci_low <= 0 <= item.ci_high:
            item.failure_reasons.append("BOOTSTRAP_CI_INCLUDES_ZERO_OR_UNAVAILABLE")
        if item.rolling_sign_stability is None or item.rolling_sign_stability < config.min_stability:
            item.failure_reasons.append("ROLLING_STABILITY_BELOW_THRESHOLD")
        if item.oos_mse_improvement is None or item.oos_mse_improvement <= config.min_oos_improvement:
            item.failure_reasons.append("OUT_OF_SAMPLE_IMPROVEMENT_NOT_MET")
        item.status = "CONFIRMED" if not item.failure_reasons else "CONFIRMATION_REJECTED"

    grouped: dict[tuple[str, str, int], list[Hypothesis]] = {}
    for item in hypotheses:
        grouped.setdefault((item.source_market, item.target_market, item.horizon), []).append(item)
    best_candidates: list[Hypothesis] = []
    confirmed_edges: list[Hypothesis] = []
    for key in sorted(grouped):
        candidates = grouped[key]
        best = max(
            candidates,
            key=lambda value: (
                1 if value.status == "CONFIRMED" else 0,
                abs(value.pearson_r or 0.0),
                value.rolling_sign_stability or 0.0,
                value.oos_mse_improvement or -999.0,
                -value.source_lag,
            ),
        )
        best_candidates.append(best)
        if best.status == "CONFIRMED":
            confirmed_edges.append(best)
    return hypotheses, best_candidates, confirmed_edges


def analyze(
    markets: dict[str, list[MarketSession]], config: AnalysisConfig
) -> dict[str, Any]:
    if config.currency_mode == "usd":
        non_usd = sorted({sessions[0].currency for sessions in markets.values() if sessions[0].currency != "USD"})
        if non_usd:
            raise ValueError("currency_mode=usd 要求宿主输入已统一换算为 USD；发现: " + ", ".join(non_usd))
    market_ids = sorted(markets)
    trailing_cache = {
        (market_id, horizon): _trailing_returns(markets[market_id], horizon)
        for market_id in market_ids
        for horizon in config.horizons
    }
    forward_cache = {
        (market_id, horizon): _forward_returns(markets[market_id], horizon)
        for market_id in market_ids
        for horizon in config.horizons
    }
    close_cache = {
        market_id: [session.close_ts_utc for session in markets[market_id]]
        for market_id in market_ids
    }
    co_movement, confirmed_co_movements = _analyze_co_movement(markets, config, trailing_cache)
    hypotheses, best_candidates, confirmed_edges = _analyze_lead_lag(
        markets, config, trailing_cache, forward_cache, close_cache
    )
    generated_at = config.generated_at
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "skill": {
            "name": "global-equity-lead-lag-atlas",
            "version": __version__,
            "display_name_zh": "全球股市时序联动图谱",
        },
        "analysis_id": config.analysis_id,
        "generated_at": generated_at,
        "claim_boundary": {
            "causal_claims": False,
            "allowed_claims": [
                "同会话日期收益相关",
                "会话感知预测领先",
                "未发现可靠关系证据",
            ],
            "co_movement_alignment": "same_session_date_trailing_return",
            "co_movement_warning": "同期相关按双方声明的 session_date 对齐，只描述共同变动，不用于判断先后。",
            "disclaimer": "统计相关或领先不等于现实因果，也不构成投资建议。",
        },
        "markets": [_market_public_summary(markets[market_id]) for market_id in market_ids],
        "co_movement": [item.to_dict() for item in co_movement],
        "confirmed_co_movements": [item.to_dict() for item in confirmed_co_movements],
        "hypotheses": [item.to_dict() for item in hypotheses],
        "best_candidates": [item.to_dict() for item in best_candidates],
        "confirmed_edges": [item.to_dict() for item in confirmed_edges],
        "counts": {
            "markets": len(market_ids),
            "co_movement_hypotheses": len(co_movement),
            "confirmed_co_movements": len(confirmed_co_movements),
            "hypotheses": len(hypotheses),
            "lead_lag_hypotheses": len(hypotheses),
            "confirmed_edges": len(confirmed_edges),
            "confirmed_lead_lag_edges": len(confirmed_edges),
        },
    }
