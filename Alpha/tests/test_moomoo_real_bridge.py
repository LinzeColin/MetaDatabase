"""真机桥 RealOpenDClient:假 SDK 注入验映射(端到端验证以部署机探针留痕为准)。"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from backend.app.adapters.brokers.moomoo_real import RealOpenDClient

RET_OK, RET_ERROR = 0, -1


class FakeQuoteCtx:
    def __init__(self, logined=True, snapshot_ok=True):
        self.logined = logined
        self.snapshot_ok = snapshot_ok

    def get_global_state(self):
        return RET_OK, {"qot_logined": self.logined, "trd_logined": True}

    def get_market_snapshot(self, codes):
        if self.snapshot_ok:
            return RET_OK, pd.DataFrame([{"code": codes[0], "last_price": 500.0}])
        return RET_ERROR, "no quote right"

    def close(self):
        pass


class FakeTradeCtx:
    def __init__(self):
        self.acc_df = pd.DataFrame([
            {"acc_id": 281756, "trd_env": "REAL", "acc_type": "CASH",
             "trdmarket_auth": ["US"], "acc_status": "ACTIVE"},
            {"acc_id": 555001, "trd_env": "SIMULATE", "acc_type": "CASH",
             "trdmarket_auth": ["US"]},
        ])

    def get_acc_list(self):
        return RET_OK, self.acc_df

    def accinfo_query(self, trd_env, acc_id, **kw):
        assert trd_env in ("REAL", "SIMULATE")
        return RET_OK, pd.DataFrame([{"cash": 1980.5, "power": 1980.5,
                                      "total_assets": 2100.0}])

    def position_list_query(self, trd_env, acc_id):
        return RET_OK, pd.DataFrame([
            {"code": "US.SPY", "qty": 2, "cost_price": 500.1, "market_val": 1010.0},
        ])

    def order_list_query(self, trd_env, acc_id):
        return RET_OK, pd.DataFrame([
            {"order_id": "77", "code": "US.SPY", "trd_side": "BUY", "qty": 1,
             "dealt_qty": 0, "price": 499.0, "order_status": "SUBMITTED",
             "create_time": "2026-07-20 09:31:00"},
            {"order_id": "78", "code": "US.QQQ", "trd_side": "BUY", "qty": 1,
             "dealt_qty": 1, "price": 400.0, "order_status": "FILLED_ALL",
             "create_time": "2026-07-20 09:32:00"},
        ])

    def deal_list_query(self, trd_env, acc_id):
        return RET_OK, pd.DataFrame([
            {"deal_id": "D1", "order_id": "78", "code": "US.QQQ", "trd_side": "BUY",
             "qty": 1, "price": 400.0, "create_time": "2026-07-20 09:32:01"},
        ])

    def close(self):
        pass


class FakeSDK:
    RET_OK = RET_OK

    class TrdMarket:
        US = "US"

    class SecurityFirm:
        FUTUAU = "FUTUAU"
        FUTUINC = "FUTUINC"

    def __init__(self, quote=None, trade=None):
        self._q = quote or FakeQuoteCtx()
        self._t = trade or FakeTradeCtx()

    def OpenQuoteContext(self, host, port):
        return self._q

    def OpenSecTradeContext(self, filter_trdmarket, host, port, security_firm):
        assert filter_trdmarket == "US" and security_firm == "FUTUAU"
        return self._t


def client(**kw):
    return RealOpenDClient(FakeSDK(**kw))


def test_ping_and_quote_connected():
    c = client()
    assert c.ping() is True
    assert c.quote_connected() is True
    assert c.trade_unlocked() is False   # 只读桥永不解锁


def test_acc_list_mapping_and_status():
    c = client()
    rows = c.get_acc_list()
    assert rows[0]["acc_id"] == "281756" and rows[0]["status"] == "ACTIVE"
    assert rows[1]["trd_env"] == "SIMULATE" and rows[1]["status"] == "UNKNOWN"
    # 无 acc_status 列的账户:资金可查询 => 运营定义 NORMAL(真实功能探测)
    assert c.get_account_status("555001") == "NORMAL"
    assert c.get_account_status("281756") == "ACTIVE"


def test_funds_positions_orders_fills():
    c = client()
    f = c.get_funds("555001")
    assert f["buying_power"] == 1980.5 and f["currency"] == "USD"
    p = c.get_positions("555001")
    assert p[0]["symbol"] == "SPY" and p[0]["quantity"] == 2
    o = c.get_open_orders("555001")
    assert len(o) == 1 and o[0]["broker_order_id"] == "77"  # 终态 FILLED_ALL 被滤掉
    fills = c.get_fills("555001", datetime(2026, 7, 20, tzinfo=timezone.utc))
    assert fills[0]["broker_execution_id"] == "D1" and fills[0]["symbol"] == "QQQ"


def test_trd_permissions_us_mapping():
    c = client()
    assert c.get_trd_permissions("281756") == ["US_STOCK"]


def test_quote_permissions_functional_probe():
    ok = client()
    assert ok.get_quote_permissions() == [{"market": "US", "level": "SNAPSHOT", "ok": True}]
    bad = client(quote=FakeQuoteCtx(snapshot_ok=False))
    assert bad.get_quote_permissions()[0]["ok"] is False


def test_non_ok_raises_fail_closed():
    class BadTrade(FakeTradeCtx):
        def get_acc_list(self):
            return RET_ERROR, "session expired"

    c = RealOpenDClient(FakeSDK(trade=BadTrade()))
    with pytest.raises(RuntimeError):
        c.get_acc_list()
