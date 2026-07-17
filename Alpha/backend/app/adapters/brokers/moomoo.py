"""Moomoo OpenD 只读适配器(ALPHA-LIVE-020)。

刻意设计:本类**不存在** place_order / modify_order / cancel_order 方法——
只读适配器在类型层面就无法下单。交易能力由 035 的唯一执行网关另行实现并受十一门禁。

SDK 注入:构造时传入实现 `OpenDClient` 形状的对象。测试用 FakeOpenD;
真机用 `build_real_opend_client()`(惰性导入 moomoo/futu SDK,本机未装则如实报错,
不伪造任何真机行为——真机验证在部署日 BLK-005 完成)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Protocol

from backend.app.adapters.brokers.base import (
    Account,
    AccountMismatchError,
    BrokerError,
    BrokerErrorKind,
    FillInfo,
    Funds,
    Health,
    OpenOrderInfo,
    Position,
    ProbeEvidence,
    QuotePermission,
)

#: SDK 错误码 -> 错误分类(契约第 4.3 条)。UNKNOWN 一律失败关闭并触发对账。
ERROR_CODE_MAP: dict[str, BrokerErrorKind] = {
    "NET_TIMEOUT": BrokerErrorKind.RETRYABLE_NETWORK,
    "NET_DISCONNECT": BrokerErrorKind.RETRYABLE_NETWORK,
    "ORDER_REJECTED": BrokerErrorKind.REJECTED_BY_BROKER,
    "INSUFFICIENT_FUNDS": BrokerErrorKind.REJECTED_BY_BROKER,
    "SESSION_EXPIRED": BrokerErrorKind.AUTH_EXPIRED,
    "UNLOCK_REQUIRED": BrokerErrorKind.AUTH_EXPIRED,
    "RATE_LIMIT": BrokerErrorKind.RATE_LIMITED,
    "FREQUENCY_LIMIT": BrokerErrorKind.RATE_LIMITED,
}


def map_error(raw_code: str, message: str = "") -> BrokerError:
    kind = ERROR_CODE_MAP.get(raw_code, BrokerErrorKind.UNKNOWN)
    return BrokerError(kind, message or raw_code, raw_code=raw_code)


class OpenDClient(Protocol):
    """OpenD 会话门面:真机桥接与测试假件都实现这个形状(全部只读)。"""

    def ping(self) -> bool: ...
    def quote_connected(self) -> bool: ...
    def trade_unlocked(self) -> bool: ...
    def get_acc_list(self) -> list[dict]: ...
    def get_funds(self, acc_id: str) -> dict: ...
    def get_positions(self, acc_id: str) -> list[dict]: ...
    def get_open_orders(self, acc_id: str) -> list[dict]: ...
    def get_fills(self, acc_id: str, since: datetime) -> list[dict]: ...
    def get_account_status(self, acc_id: str) -> str: ...
    def get_trd_permissions(self, acc_id: str) -> list[str]: ...
    def get_quote_permissions(self) -> list[dict]: ...


class MoomooReadOnlyAdapter:
    """只读能力:连接、账户、资金、持仓、未完成订单、近期成交、探针证据。"""

    def __init__(self, client: OpenDClient, *, expected_acc_id: str) -> None:
        if not expected_acc_id:
            raise AccountMismatchError("expected_acc_id 不得为空(禁 acc_index 定位)")
        self._client = client
        self._expected_acc_id = str(expected_acc_id)
        self._connected = False

    # ---- 连接与健康 ----

    def connect(self) -> Health:
        """建立会话并断言 acc_id 匹配(契约第 1 节:账户定位只用 acc_id)。"""
        if not self._client.ping():
            raise map_error("NET_DISCONNECT", "OpenD 无法连通")
        acc_ids = [str(a.get("acc_id")) for a in self._client.get_acc_list()]
        if self._expected_acc_id not in acc_ids:
            raise AccountMismatchError(
                f"环境预期 acc_id 不在账户列表中(预期 {self._expected_acc_id},实际 {acc_ids})"
            )
        self._connected = True
        return self.health()

    def health(self) -> Health:
        return Health(
            opend_connected=self._client.ping(),
            quote_connected=self._client.quote_connected(),
            trade_unlocked=self._client.trade_unlocked(),
            checked_at=datetime.now(timezone.utc),
        )

    # ---- 只读查询 ----

    def get_account(self) -> Account:
        self._require_connected()
        for row in self._client.get_acc_list():
            if str(row.get("acc_id")) == self._expected_acc_id:
                return Account(
                    acc_id=str(row["acc_id"]),
                    currency=str(row.get("currency", "")),
                    status=str(row.get("status", "UNKNOWN")),
                    trd_env=str(row.get("trd_env", "")),
                    account_type=str(row.get("acc_type", "")),
                )
        raise AccountMismatchError(f"账户列表中已找不到 {self._expected_acc_id}")

    def get_funds(self) -> Funds:
        self._require_connected()
        raw = self._call(self._client.get_funds, self._expected_acc_id)
        return Funds(
            currency=str(raw["currency"]),
            cash=Decimal(str(raw["cash"])),
            buying_power=Decimal(str(raw["buying_power"])),
            total_assets=Decimal(str(raw["total_assets"])),
            as_of=raw.get("as_of") or datetime.now(timezone.utc),
        )

    def get_positions(self) -> list[Position]:
        self._require_connected()
        rows = self._call(self._client.get_positions, self._expected_acc_id)
        return [
            Position(
                symbol=str(r["symbol"]),
                quantity=int(r["quantity"]),
                cost_price=Decimal(str(r["cost_price"])),
                market_value=Decimal(str(r["market_value"])),
                currency=str(r.get("currency", "USD")),
                as_of=r.get("as_of") or datetime.now(timezone.utc),
            )
            for r in rows
        ]

    def get_open_orders(self) -> list[OpenOrderInfo]:
        self._require_connected()
        rows = self._call(self._client.get_open_orders, self._expected_acc_id)
        return [
            OpenOrderInfo(
                broker_order_id=str(r["broker_order_id"]),
                symbol=str(r["symbol"]),
                side=str(r["side"]),
                quantity=int(r["quantity"]),
                filled_quantity=int(r.get("filled_quantity", 0)),
                price=Decimal(str(r["price"])) if r.get("price") is not None else None,
                status=str(r["status"]),
                submitted_at=r["submitted_at"],
                remark=str(r.get("remark", "")),
            )
            for r in rows
        ]

    def get_recent_fills(self, since: datetime) -> list[FillInfo]:
        self._require_connected()
        rows = self._call(self._client.get_fills, self._expected_acc_id, since)
        return [
            FillInfo(
                broker_execution_id=str(r["broker_execution_id"]),
                broker_order_id=str(r["broker_order_id"]),
                symbol=str(r["symbol"]),
                side=str(r["side"]),
                quantity=int(r["quantity"]),
                price=Decimal(str(r["price"])),
                executed_at=r["executed_at"],
            )
            for r in rows
        ]

    def collect_probe_evidence(self) -> ProbeEvidence:
        """辖区探针原始证据(判定在 probe 模块)。"""
        self._require_connected()
        return ProbeEvidence(
            acc_id=self._expected_acc_id,
            account_status=self._call(self._client.get_account_status, self._expected_acc_id),
            trd_permissions=list(self._call(self._client.get_trd_permissions, self._expected_acc_id)),
            quote_permissions=[
                QuotePermission(market=str(q["market"]), level=str(q["level"]), ok=bool(q["ok"]))
                for q in self._call(self._client.get_quote_permissions)
            ],
            probed_at=datetime.now(timezone.utc),
        )

    # ---- 内部 ----

    def _require_connected(self) -> None:
        if not self._connected:
            raise map_error("NET_DISCONNECT", "尚未 connect() 或连接已断开")

    @staticmethod
    def _call(fn: Callable[..., Any], *args: Any) -> Any:
        try:
            return fn(*args)
        except BrokerError:
            raise
        except ConnectionError as exc:
            raise map_error("NET_DISCONNECT", str(exc)) from exc
        except TimeoutError as exc:
            raise map_error("NET_TIMEOUT", str(exc)) from exc
        except Exception as exc:  # 未知异常一律 UNKNOWN:失败关闭 + 触发对账
            raise BrokerError(BrokerErrorKind.UNKNOWN, str(exc)) from exc


def build_real_opend_client(*, host: str = "127.0.0.1", port: int = 11111) -> OpenDClient:
    """真机 OpenD 客户端工厂(部署日使用;本机无 SDK 则如实抛错,绝不伪造)。

    契约第 1 节:仅回环地址;RSA 加密由 OpenD 侧配置;解锁只在执行网关进程内发生,
    本只读客户端永不调用 unlock。
    """
    try:  # pragma: no cover - 真机路径,CI 不装 SDK
        import moomoo as sdk  # type: ignore
    except ImportError:  # pragma: no cover
        try:
            import futu as sdk  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "moomoo/futu SDK 未安装:真机探针只能在部署主机上运行(见 specs/DEPLOY_RUNBOOK_ORACLE.md);"
                "本地不伪造真机行为"
            ) from exc
    raise NotImplementedError(  # pragma: no cover
        "真机桥接在 ALPHA-LIVE-040 部署任务中与 OpenD 实机联调时完成并留痕;"
        "020 阶段如实标注:未与真机验证过的桥接代码不冒充可用"
    )
