"""ALPHA-LIVE-020:Moomoo 只读适配器契约测试(假 OpenD,不连真机)。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.adapters.brokers.base import (
    AccountMismatchError,
    BrokerError,
    BrokerErrorKind,
    MODE_TO_TRD_ENV,
    ProbeEvidence,
    QuotePermission,
    SystemMode,
    TrdEnv,
)
from backend.app.adapters.brokers.moomoo import ERROR_CODE_MAP, MoomooReadOnlyAdapter, map_error
from backend.app.adapters.brokers.probe import evaluate, run_probe_and_persist
from backend.app.adapters.market_data.moomoo import MoomooMarketData
from backend.app.domain.models import JurisdictionCapability
from backend.app.store.db import create_session_factory, init_engine

UTC = timezone.utc
NOW = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)


class FakeOpenD:
    """假 OpenD:契约门面的确定性实现。"""

    def __init__(self, acc_id="281756", fail_with: Exception | None = None):
        self.acc_id = acc_id
        self.fail_with = fail_with
        self.account_status = "ACTIVE"
        self.trd_permissions = ["US_STOCK", "US_ETF"]
        self.quote_permissions = [{"market": "US", "level": "LV1", "ok": True}]

    def ping(self):
        return True

    def quote_connected(self):
        return True

    def trade_unlocked(self):
        return False  # 只读适配器永不解锁

    def get_acc_list(self):
        return [{"acc_id": self.acc_id, "currency": "AUD", "status": "ACTIVE", "trd_env": "REAL", "acc_type": "CASH"}]

    def _maybe_fail(self):
        if self.fail_with is not None:
            raise self.fail_with

    def get_funds(self, acc_id):
        self._maybe_fail()
        assert acc_id == self.acc_id
        return {"currency": "AUD", "cash": "3000.00", "buying_power": "3000.00", "total_assets": "3000.00", "as_of": NOW}

    def get_positions(self, acc_id):
        self._maybe_fail()
        return [{"symbol": "SPY", "quantity": 2, "cost_price": "500.10", "market_value": "1001.00", "currency": "USD", "as_of": NOW}]

    def get_open_orders(self, acc_id):
        self._maybe_fail()
        return [{
            "broker_order_id": "MM001", "symbol": "QQQ", "side": "BUY", "quantity": 3,
            "filled_quantity": 1, "price": "400.00", "status": "SUBMITTED",
            "submitted_at": NOW, "remark": "idem-abc123",
        }]

    def get_fills(self, acc_id, since):
        self._maybe_fail()
        return [{
            "broker_execution_id": "E9", "broker_order_id": "MM001", "symbol": "QQQ",
            "side": "BUY", "quantity": 1, "price": "399.98", "executed_at": NOW,
        }]

    def get_account_status(self, acc_id):
        return self.account_status

    def get_trd_permissions(self, acc_id):
        return self.trd_permissions

    def get_quote_permissions(self):
        return self.quote_permissions


class FakeQuoteClient:
    def __init__(self, ok=True):
        self.ok = ok

    def subscribe(self, symbols):
        return self.ok

    def get_snapshot(self, symbols):
        return [{
            "symbol": s, "last_price": "500.00", "bid": "499.99", "ask": "500.01",
            "exchange_ts": NOW, "received_ts": NOW + timedelta(milliseconds=120),
        } for s in symbols]


def make_adapter(**kw):
    fake = FakeOpenD(**kw)
    adapter = MoomooReadOnlyAdapter(fake, expected_acc_id=fake.acc_id)
    return adapter, fake


# ---- acc_id 规则(契约第 1 节) ----

def test_connect_asserts_acc_id_match():
    adapter, _ = make_adapter()
    health = adapter.connect()
    assert health.opend_connected and health.quote_connected
    assert health.trade_unlocked is False  # 只读会话永不解锁


def test_connect_rejects_acc_id_mismatch():
    fake = FakeOpenD(acc_id="999999")
    adapter = MoomooReadOnlyAdapter(fake, expected_acc_id="281756")
    with pytest.raises(AccountMismatchError):
        adapter.connect()


def test_empty_expected_acc_id_rejected():
    with pytest.raises(AccountMismatchError):
        MoomooReadOnlyAdapter(FakeOpenD(), expected_acc_id="")


def test_queries_require_connect_first():
    adapter, _ = make_adapter()
    with pytest.raises(BrokerError) as ei:
        adapter.get_funds()
    assert ei.value.kind is BrokerErrorKind.RETRYABLE_NETWORK


# ---- 只读查询字段映射 ----

def test_read_only_surfaces_map_fields():
    adapter, _ = make_adapter()
    adapter.connect()
    account = adapter.get_account()
    assert (account.acc_id, account.currency, account.status) == ("281756", "AUD", "ACTIVE")
    funds = adapter.get_funds()
    assert funds.cash == Decimal("3000.00") and funds.currency == "AUD"
    positions = adapter.get_positions()
    assert positions[0].symbol == "SPY" and positions[0].market_value == Decimal("1001.00")
    orders = adapter.get_open_orders()
    assert orders[0].broker_order_id == "MM001" and orders[0].remark == "idem-abc123"
    fills = adapter.get_recent_fills(NOW - timedelta(days=1))
    assert fills[0].broker_execution_id == "E9" and fills[0].price == Decimal("399.98")


def test_read_only_adapter_has_no_order_methods():
    """验收红线:只读适配器不含任何下单调用——类型层面不存在这些方法。"""
    for forbidden in ("place_order", "modify_order", "cancel_order", "unlock_trade"):
        assert not hasattr(MoomooReadOnlyAdapter, forbidden)


# ---- 错误映射(契约第 4.3 条) ----

@pytest.mark.parametrize(
    "raw,kind",
    [
        ("NET_TIMEOUT", BrokerErrorKind.RETRYABLE_NETWORK),
        ("NET_DISCONNECT", BrokerErrorKind.RETRYABLE_NETWORK),
        ("ORDER_REJECTED", BrokerErrorKind.REJECTED_BY_BROKER),
        ("INSUFFICIENT_FUNDS", BrokerErrorKind.REJECTED_BY_BROKER),
        ("SESSION_EXPIRED", BrokerErrorKind.AUTH_EXPIRED),
        ("UNLOCK_REQUIRED", BrokerErrorKind.AUTH_EXPIRED),
        ("RATE_LIMIT", BrokerErrorKind.RATE_LIMITED),
        ("FREQUENCY_LIMIT", BrokerErrorKind.RATE_LIMITED),
        ("SOMETHING_NEW", BrokerErrorKind.UNKNOWN),
    ],
)
def test_error_code_mapping(raw, kind):
    assert map_error(raw).kind is kind


def test_unexpected_sdk_exception_maps_unknown_fail_closed():
    adapter, fake = make_adapter()
    adapter.connect()
    fake.fail_with = RuntimeError("SDK 未知炸裂")
    with pytest.raises(BrokerError) as ei:
        adapter.get_funds()
    assert ei.value.kind is BrokerErrorKind.UNKNOWN


def test_error_map_covers_only_known_codes():
    assert set(ERROR_CODE_MAP) == {
        "NET_TIMEOUT", "NET_DISCONNECT", "ORDER_REJECTED", "INSUFFICIENT_FUNDS",
        "SESSION_EXPIRED", "UNLOCK_REQUIRED", "RATE_LIMIT", "FREQUENCY_LIMIT",
    }


# ---- 模式映射(契约第 3 节) ----

def test_mode_to_trd_env_table():
    assert MODE_TO_TRD_ENV[SystemMode.DISABLED] == (TrdEnv.NONE, False)
    assert MODE_TO_TRD_ENV[SystemMode.PAPER] == (TrdEnv.SIMULATE, True)
    assert MODE_TO_TRD_ENV[SystemMode.SHADOW] == (TrdEnv.NONE, False)
    assert MODE_TO_TRD_ENV[SystemMode.MICRO_LIVE] == (TrdEnv.REAL, True)
    assert MODE_TO_TRD_ENV[SystemMode.HALTED] == (TrdEnv.NONE, False)


# ---- 行情只读 ----

def test_market_data_snapshot_carries_both_timestamps():
    md = MoomooMarketData(FakeQuoteClient())
    md.subscribe(["SPY", "QQQ"])
    assert md.subscribed == frozenset({"SPY", "QQQ"})
    quotes = md.snapshot(["SPY"])
    assert quotes[0].exchange_ts == NOW
    assert quotes[0].received_ts > quotes[0].exchange_ts


def test_market_data_subscribe_failure_raises():
    md = MoomooMarketData(FakeQuoteClient(ok=False))
    with pytest.raises(BrokerError):
        md.subscribe(["SPY"])


# ---- 辖区探针(契约第 4.5 条) ----

def probe_evidence(status="ACTIVE", trd=("US_STOCK",), quote_ok=True):
    return ProbeEvidence(
        acc_id="281756",
        account_status=status,
        trd_permissions=list(trd),
        quote_permissions=[QuotePermission(market="US", level="LV1", ok=quote_ok)],
        probed_at=NOW,
    )


def test_probe_allow_requires_all_three_green():
    assert evaluate(probe_evidence())["verdict"] == "ALLOW"
    assert evaluate(probe_evidence(status="RESTRICTED"))["verdict"] == "DENY"
    assert evaluate(probe_evidence(trd=("HK_STOCK",)))["verdict"] == "DENY"
    assert evaluate(probe_evidence(quote_ok=False))["verdict"] == "DENY"


def test_probe_persists_capability_record(tmp_path):
    engine = init_engine(f"sqlite:///{tmp_path / 'probe.sqlite'}")
    factory = create_session_factory(engine)
    adapter, _ = make_adapter()
    adapter.connect()
    evidence = adapter.collect_probe_evidence()
    result = run_probe_and_persist(evidence, factory, account_principal="owner_au", location="AU")
    assert result["verdict"] == "ALLOW"
    with factory() as session:
        row = session.query(JurisdictionCapability).one()
        assert row.verdict == "ALLOW" and row.buy_permission is True
        assert "US_STOCK" in row.evidence_source  # 证据 JSON 落库


def test_probe_deny_persists_no_buy_permission(tmp_path):
    engine = init_engine(f"sqlite:///{tmp_path / 'probe2.sqlite'}")
    factory = create_session_factory(engine)
    result = run_probe_and_persist(
        probe_evidence(trd=("HK_STOCK",)), factory, account_principal="owner_au", location="AU"
    )
    assert result["verdict"] == "DENY"
    with factory() as session:
        row = session.query(JurisdictionCapability).one()
        assert row.buy_permission is False
