"""双层频控(ALPHA-LIVE-035,契约第 4.2 条)。

- 业务层:任意滚动 60 分钟 ≤ 5 笔——从订单事件表计数,重启不失忆。
- 券商层:15 次/30 秒 + 相邻请求间隔 ≥ 0.02 秒——进程内令牌桶。
触顶即拒绝并由网关落审计;时钟可注入,测试确定性。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from backend.app.store.orders import OrderStore


class RateLimitExceededError(Exception):
    def __init__(self, layer: str, detail: str) -> None:
        self.layer = layer
        super().__init__(f"[{layer}] {detail}")


class BusinessRateLimiter:
    """滚动 60 分钟 ≤ max_orders,以事件表为准。"""

    def __init__(
        self,
        store: OrderStore,
        *,
        max_orders: int = 5,
        window_minutes: int = 60,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._max = max_orders
        self._window = timedelta(minutes=window_minutes)
        self._now = now_fn

    def check(self) -> int:
        """返回窗口内已用笔数;触顶抛错。"""
        used = self._store.count_submissions_since(self._now() - self._window)
        if used >= self._max:
            raise RateLimitExceededError(
                "business", f"滚动 {self._window} 内已提交 {used} 笔,上限 {self._max}"
            )
        return used


class BrokerRateLimiter:
    """官方频控:窗口计数 + 最小间隔。"""

    def __init__(
        self,
        *,
        max_requests: int = 15,
        window_seconds: float = 30.0,
        min_interval_seconds: float = 0.02,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._max = max_requests
        self._window = timedelta(seconds=window_seconds)
        self._min_interval = timedelta(seconds=min_interval_seconds)
        self._now = now_fn
        self._recent: list[datetime] = []

    def acquire(self) -> None:
        now = self._now()
        cutoff = now - self._window
        self._recent = [t for t in self._recent if t > cutoff]
        if len(self._recent) >= self._max:
            raise RateLimitExceededError(
                "broker", f"{self._window.total_seconds():.0f} 秒内已 {len(self._recent)} 次,上限 {self._max}"
            )
        if self._recent and now - self._recent[-1] < self._min_interval:
            raise RateLimitExceededError("broker", "相邻请求间隔不足 0.02 秒")
        self._recent.append(now)
