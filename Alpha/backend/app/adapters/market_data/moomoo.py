"""Moomoo 行情只读适配器(ALPHA-LIVE-020)。

订阅与快照,均带交易所时间戳与本地接收时间戳——030 行情守卫据此判新鲜度。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Protocol

from backend.app.adapters.brokers.moomoo import map_error


@dataclass(frozen=True)
class Quote:
    symbol: str
    last_price: Decimal
    bid: Decimal
    ask: Decimal
    exchange_ts: datetime   # 交易所时间戳
    received_ts: datetime   # 本地接收时间戳


class QuoteClient(Protocol):
    def subscribe(self, symbols: list[str]) -> bool: ...
    def get_snapshot(self, symbols: list[str]) -> list[dict]: ...


class MoomooMarketData:
    def __init__(self, client: QuoteClient) -> None:
        self._client = client
        self._subscribed: set[str] = set()

    def subscribe(self, symbols: list[str]) -> None:
        if not self._client.subscribe(symbols):
            raise map_error("NET_DISCONNECT", f"行情订阅失败: {symbols}")
        self._subscribed.update(symbols)

    @property
    def subscribed(self) -> frozenset[str]:
        return frozenset(self._subscribed)

    def snapshot(self, symbols: list[str]) -> list[Quote]:
        rows = self._client.get_snapshot(symbols)
        now = datetime.now(timezone.utc)
        return [
            Quote(
                symbol=str(r["symbol"]),
                last_price=Decimal(str(r["last_price"])),
                bid=Decimal(str(r["bid"])),
                ask=Decimal(str(r["ask"])),
                exchange_ts=r["exchange_ts"],
                received_ts=r.get("received_ts") or now,
            )
            for r in rows
        ]


SnapshotFn = Callable[[list[str]], list[Quote]]
