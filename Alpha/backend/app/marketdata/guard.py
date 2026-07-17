"""行情新鲜度守卫(ALPHA-LIVE-030)。

口径(machine/facts/config.yaml):阈值默认 5 秒,待 G3 实测校准;
判老化用交易所时间戳(比接收时间戳更保守——传输延迟也算老化)。
陈旧行情:stale_data_blocks_new_orders = true,风控引擎据此拒单。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEFAULT_FRESHNESS_THRESHOLD_SECONDS = 5.0


@dataclass(frozen=True)
class FreshnessVerdict:
    symbol: str
    age_seconds: float
    threshold_seconds: float
    fresh: bool


class FreshnessGuard:
    def __init__(self, threshold_seconds: float = DEFAULT_FRESHNESS_THRESHOLD_SECONDS) -> None:
        if threshold_seconds <= 0:
            raise ValueError("新鲜度阈值必须为正")
        self._threshold = float(threshold_seconds)

    def check(self, *, symbol: str, exchange_ts: datetime, now: datetime) -> FreshnessVerdict:
        age = (now - exchange_ts).total_seconds()
        # 时钟漂移出现"未来行情"同样不可信:一律按不新鲜处理(失败关闭)。
        fresh = 0.0 <= age <= self._threshold
        return FreshnessVerdict(
            symbol=symbol, age_seconds=age, threshold_seconds=self._threshold, fresh=fresh
        )
