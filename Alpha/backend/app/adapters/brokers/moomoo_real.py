"""真机 OpenD 只读桥(ALPHA-LIVE-070 联调;实现 OpenDClient 形状)。

设计约束(与只读适配器同一红线):
- 本类**不存在**任何下单/改单/撤单/解锁调用——类型层面就无法触单;
- 全部查询走 moomoo SDK 的 RET_OK 协议,非 OK 一律抛错(上层适配器失败关闭);
- SDK 以构造参数注入:测试注入假件验映射,真机由 build_real_opend_client 注入
  已导入的 moomoo 模块——本文件不做"没有真机也装作可用"的事;
- 若干字段官方接口无直查(账户状态/行情等级),用**真实功能性探测**作运营定义并
  在字段值中自明(如 level="SNAPSHOT"),绝不空造 "ACTIVE"/"LV1" 字样。
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

#: 未完成订单状态集合(moomoo OrderStatus 字符串;完成态/终态不在其列)
_INCOMPLETE_ORDER_STATUSES = {
    "WAITING_SUBMIT", "SUBMITTING", "SUBMITTED", "FILLED_PART",
}


def _f(value: Any, default: float = 0.0) -> float:
    """SDK 数值容错:N/A、NaN、None 一律回退 default(只读展示口径)。"""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(out) else out


def _s(value: Any) -> str:
    """SDK 字符串容错:None 与 pandas NaN(str 后是 'nan')一律视为缺失返回空串。"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def _parse_time(value: Any) -> datetime:
    """SDK 时间字符串尽力解析;解析不动如实用当前 UTC(仅只读展示口径)。"""
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("/", "-")[:26])
    except ValueError:
        return datetime.now(timezone.utc)


class RealOpenDClient:
    """moomoo SDK 只读门面。契约:仅回环;永不 unlock;永不下单。"""

    def __init__(self, sdk: Any, *, host: str = "127.0.0.1", port: int = 11111,
                 security_firm: str = "FUTUAU") -> None:
        self._sdk = sdk
        self._host = host
        self._port = port
        self._firm_name = security_firm
        self._quote_ctx: Optional[Any] = None
        self._trade_ctx: Optional[Any] = None
        self._acc_env: dict[str, Any] = {}      # acc_id -> SDK trd_env 枚举值
        self._acc_rows: dict[str, dict] = {}    # acc_id -> 原始行(状态/权限来源)

    # ---- 上下文(惰性;失败如实抛错) ----

    def _quote(self) -> Any:
        if self._quote_ctx is None:
            self._quote_ctx = self._sdk.OpenQuoteContext(host=self._host, port=self._port)
        return self._quote_ctx

    def _trade(self) -> Any:
        if self._trade_ctx is None:
            firm = getattr(self._sdk.SecurityFirm, self._firm_name)
            self._trade_ctx = self._sdk.OpenSecTradeContext(
                filter_trdmarket=self._sdk.TrdMarket.US,
                host=self._host, port=self._port, security_firm=firm)
        return self._trade_ctx

    def close(self) -> None:
        for ctx in (self._quote_ctx, self._trade_ctx):
            if ctx is not None:
                ctx.close()
        self._quote_ctx = self._trade_ctx = None

    def _ok(self, api: str, ret_data: tuple) -> Any:
        ret, data = ret_data
        if ret != self._sdk.RET_OK:
            raise RuntimeError(f"{api} 非OK: {data}")  # 上层 _call 归为 UNKNOWN 失败关闭
        return data

    # ---- OpenDClient 形状 ----

    def ping(self) -> bool:
        try:
            self._ok("get_global_state", self._quote().get_global_state())
            return True
        except Exception:
            return False

    def quote_connected(self) -> bool:
        try:
            state = self._ok("get_global_state", self._quote().get_global_state())
            return bool(state.get("qot_logined"))
        except Exception:
            return False

    def trade_unlocked(self) -> bool:
        return False  # 只读进程从不解锁;如实报 False(SIMULATE 下单不需解锁)

    def get_acc_list(self) -> list[dict]:
        df = self._ok("get_acc_list", self._trade().get_acc_list())
        rows: list[dict] = []
        for r in df.to_dict("records"):
            acc_id = str(int(r["acc_id"]))
            self._acc_env[acc_id] = r.get("trd_env")
            self._acc_rows[acc_id] = r
            rows.append({
                "acc_id": acc_id,
                "trd_env": _s(r.get("trd_env")),
                "acc_type": _s(r.get("acc_type")),
                "currency": _s(r.get("currency")),
                "status": _s(r.get("acc_status")) or "UNKNOWN",
            })
        return rows

    def _env_for(self, acc_id: str) -> Any:
        if acc_id not in self._acc_env:
            self.get_acc_list()
        if acc_id not in self._acc_env:
            raise RuntimeError(f"acc_id {acc_id} 不在账户列表")
        return self._acc_env[acc_id]

    def get_funds(self, acc_id: str) -> dict:
        kwargs: dict[str, Any] = {}
        if hasattr(self._sdk, "Currency"):
            kwargs["currency"] = self._sdk.Currency.USD
        df = self._ok("accinfo_query", self._trade().accinfo_query(
            trd_env=self._env_for(acc_id), acc_id=int(acc_id), **kwargs))
        row = df.to_dict("records")[0]
        return {
            "currency": "USD",
            "cash": _f(row.get("cash")),
            "buying_power": _f(row.get("power")),
            "total_assets": _f(row.get("total_assets")),
            "as_of": datetime.now(timezone.utc),
        }

    def get_positions(self, acc_id: str) -> list[dict]:
        df = self._ok("position_list_query", self._trade().position_list_query(
            trd_env=self._env_for(acc_id), acc_id=int(acc_id)))
        out = []
        for r in df.to_dict("records"):
            code = str(r.get("code", ""))
            out.append({
                "symbol": code.split(".", 1)[1] if "." in code else code,
                "quantity": int(_f(r.get("qty"))),
                "cost_price": _f(r.get("cost_price")),
                "market_value": _f(r.get("market_val")),
                "currency": "USD",
            })
        return out

    def get_open_orders(self, acc_id: str) -> list[dict]:
        df = self._ok("order_list_query", self._trade().order_list_query(
            trd_env=self._env_for(acc_id), acc_id=int(acc_id)))
        out = []
        for r in df.to_dict("records"):
            status = str(r.get("order_status", ""))
            if status not in _INCOMPLETE_ORDER_STATUSES:
                continue
            code = str(r.get("code", ""))
            out.append({
                "broker_order_id": str(r.get("order_id", "")),
                "symbol": code.split(".", 1)[1] if "." in code else code,
                "side": str(r.get("trd_side", "")),
                "quantity": int(_f(r.get("qty"))),
                "filled_quantity": int(_f(r.get("dealt_qty"))),
                "price": _f(r.get("price")) or None,
                "status": status,
                "submitted_at": _parse_time(r.get("create_time")),
                "remark": str(r.get("remark", "")),
            })
        return out

    def get_fills(self, acc_id: str, since: datetime) -> list[dict]:
        df = self._ok("deal_list_query", self._trade().deal_list_query(
            trd_env=self._env_for(acc_id), acc_id=int(acc_id)))
        out = []
        for r in df.to_dict("records"):
            executed_at = _parse_time(r.get("create_time"))
            naive_since = since.replace(tzinfo=None) if since.tzinfo else since
            naive_exec = executed_at.replace(tzinfo=None) if executed_at.tzinfo else executed_at
            if naive_exec < naive_since:
                continue
            code = str(r.get("code", ""))
            out.append({
                "broker_execution_id": str(r.get("deal_id", "")),
                "broker_order_id": str(r.get("order_id", "")),
                "symbol": code.split(".", 1)[1] if "." in code else code,
                "side": str(r.get("trd_side", "")),
                "quantity": int(_f(r.get("qty"))),
                "price": _f(r.get("price")),
                "executed_at": executed_at,
            })
        return out

    def get_account_status(self, acc_id: str) -> str:
        row = self._acc_rows.get(acc_id) or {}
        if acc_id not in self._acc_rows:
            self.get_acc_list()
            row = self._acc_rows.get(acc_id) or {}
        raw = _s(row.get("acc_status")).strip()
        if raw:
            return raw
        # 官方无直查字段时的运营定义:资金可查询 = 账户正常运作(真实功能探测,非空造)
        try:
            self.get_funds(acc_id)
            return "NORMAL"
        except Exception:
            return "UNKNOWN"

    def get_trd_permissions(self, acc_id: str) -> list[str]:
        row = self._acc_rows.get(acc_id) or {}
        if acc_id not in self._acc_rows:
            self.get_acc_list()
            row = self._acc_rows.get(acc_id) or {}
        auth = row.get("trdmarket_auth") or []
        perms = []
        for m in list(auth):
            if "US" in str(m).upper():
                perms.append("US_STOCK")   # 契约口径:美股交易权限
            else:
                perms.append(str(m))
        return perms

    def get_daily_bars(self, symbol: str, start: str, end: str) -> list[dict]:
        """日 K 历史(前复权),供 070 实盘评估喂策略。返回 dict 行,调用方转 Bar。

        注意:request_history_kline 返回三元组 (ret, data, page_req_key)。
        """
        ret_data = self._quote().request_history_kline(
            f"US.{symbol}", start=start, end=end,
            ktype=self._sdk.KLType.K_DAY, autype=self._sdk.AuType.QFQ,
            max_count=1000)
        ret, data = ret_data[0], ret_data[1]
        if ret != self._sdk.RET_OK:
            raise RuntimeError(f"request_history_kline({symbol}) 非OK: {data}")
        out = []
        for r in data.to_dict("records"):
            out.append({"day": _s(r.get("time_key"))[:10],
                        "open": _f(r.get("open")), "high": _f(r.get("high")),
                        "low": _f(r.get("low")), "close": _f(r.get("close"))})
        return out

    def get_snapshot(self, symbols: list[str]) -> dict[str, dict]:
        """快照:symbol -> {price, update_time}(070 定价与鲜度判定)。"""
        codes = [f"US.{s}" for s in symbols]
        df = self._ok("get_market_snapshot", self._quote().get_market_snapshot(codes))
        out: dict[str, dict] = {}
        for r in df.to_dict("records"):
            code = _s(r.get("code"))
            sym = code.split(".", 1)[1] if "." in code else code
            out[sym] = {"price": _f(r.get("last_price")),
                        "update_time": _s(r.get("update_time"))}
        return out

    def get_quote_permissions(self) -> list[dict]:
        # 真实功能探测:能取到 US.SPY 快照即证明美股行情可用;level 自明为 SNAPSHOT
        try:
            self._ok("get_market_snapshot", self._quote().get_market_snapshot(["US.SPY"]))
            return [{"market": "US", "level": "SNAPSHOT", "ok": True}]
        except Exception:
            return [{"market": "US", "level": "NONE", "ok": False}]
