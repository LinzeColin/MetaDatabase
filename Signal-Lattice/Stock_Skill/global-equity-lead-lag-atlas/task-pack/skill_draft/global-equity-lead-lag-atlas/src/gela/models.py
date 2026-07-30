from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MarketSession:
    market_id: str
    country_iso3: str
    country_name_zh: str
    index_name: str
    instrument_type: str
    return_type: str
    currency: str
    timezone: str
    latitude: float
    longitude: float
    session_date: str
    open_ts_utc: datetime
    close_ts_utc: datetime
    close: float
    source: str
    source_symbol: str
    source_retrieved_at: str


@dataclass(frozen=True)
class AnalysisConfig:
    analysis_id: str
    input_csv: Path
    output_dir: Path
    horizons: tuple[int, ...] = (1, 5, 10, 15, 21, 63, 126)
    source_lags: tuple[int, ...] = (0, 1, 2, 3, 5)
    alpha: float = 0.05
    min_raw_n: int = 80
    min_effective_n: int = 20
    min_abs_effect: float = 0.15
    min_stability: float = 0.67
    min_oos_improvement: float = 0.0
    bootstrap_repetitions: int = 300
    bootstrap_block: int = 10
    rolling_windows: int = 4
    max_base_staleness_hours: float = 96.0
    random_seed: int = 20260726
    fdr_scope: str = "global"
    currency_mode: str = "local"
    causal_claims: bool = False
    data_usage_mode: str = "user_provided"
    license_acknowledgement: bool = False
    generated_at: str | None = None


@dataclass
class CoMovement:
    pair_id: str
    market_a: str
    market_b: str
    horizon: int
    alignment: str
    n_raw: int
    n_effective: int
    pearson_r: float | None
    spearman_r: float | None
    p_value: float | None
    q_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    rolling_sign_stability: float | None = None
    status: str = "SCREENED"
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    hypothesis_id: str
    source_market: str
    target_market: str
    horizon: int
    source_lag: int
    n_raw: int
    n_effective: int
    median_wall_clock_lead_hours: float | None
    pearson_r: float | None
    spearman_r: float | None
    p_value: float | None
    q_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    rolling_sign_stability: float | None = None
    oos_mse_improvement: float | None = None
    status: str = "SCREENED"
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
