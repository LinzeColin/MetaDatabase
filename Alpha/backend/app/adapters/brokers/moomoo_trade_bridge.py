"""SIMULATE 专用交易桥(ALPHA-LIVE-070):实现网关 TradingClient 形状。

硬红线(结构性,不靠自觉):
- 构造即锁定 trd_env=SIMULATE + 模拟账户 acc_id;place_order 收到任何非
  SIMULATE 环境一律抛错拒绝——REAL 桥接是 080 的另一个类、另一次联调、另受十一门禁;
- unlock() 为显式空操作:SIMULATE 下单无需解锁,本进程亦永不解锁 REAL;
- 只支持 LIMIT 单(生产策略执行口径);其它类型如实拒绝;
- SDK 注入构造,测试用假件;RET_OK 协议,非 OK 抛错(上层失败关闭)。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from backend.app.adapters.brokers.moomoo_real import _f, _s

_INCOMPLETE = {"WAITING_SUBMIT", "SUBMITTING", "SUBMITTED", "FILLED_PART"}


class SimulateTradingClient:
    """moomoo SIMULATE 环境下单/改撤/查询门面(070 Paper 专用)。"""

    def __init__(self, sdk: Any, *, acc_id: str, host: str = "127.0.0.1",
                 port: int = 11111, security_firm: str = "FUTUAU") -> None:
        self._sdk = sdk
        self._acc_id = int(acc_id)
        self._host = host
        self._port = port
        self._firm_name = security_firm
        self._ctx: Optional[Any] = None

    def _trade(self) -> Any:
        if self._ctx is None:
            firm = getattr(self._sdk.SecurityFirm, self._firm_name)
            self._ctx = self._sdk.OpenSecTradeContext(
                filter_trdmarket=self._sdk.TrdMarket.US,
                host=self._host, port=self._port, security_firm=firm)
        return self._ctx

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    def _ok(self, api: str, ret_data: tuple) -> Any:
        ret, data = ret_data
        if ret != self._sdk.RET_OK:
            raise RuntimeError(f"{api} 非OK: {data}")
        return data

    # ---- TradingClient 形状 ----

    def place_order(self, *, symbol: str, side: str, quantity: int, order_type: str,
                    limit_price: Optional[Decimal], trd_env: str, remark: str) -> dict:
        if trd_env != "SIMULATE":
            raise PermissionError(f"本桥只允许 SIMULATE,收到 {trd_env}(REAL 属 080 另一联调)")
        if order_type != "LIMIT" or limit_price is None:
            raise ValueError(f"仅支持带价 LIMIT 单,收到 {order_type}/{limit_price}")
        side_map = {"BUY": self._sdk.TrdSide.BUY, "SELL": self._sdk.TrdSide.SELL}
        if side not in side_map:
            raise ValueError(f"未知方向 {side}")
        df = self._ok("place_order", self._trade().place_order(
            price=float(limit_price), qty=int(quantity), code=f"US.{symbol}",
            trd_side=side_map[side], order_type=self._sdk.OrderType.NORMAL,
            trd_env=self._sdk.TrdEnv.SIMULATE, acc_id=self._acc_id, remark=remark))
        row = df.to_dict("records")[0]
        return {"broker_order_id": _s(row.get("order_id"))}

    def modify_order(self, broker_order_id: str, *, quantity: int,
                     limit_price: Optional[Decimal]) -> dict:
        df = self._ok("modify_order", self._trade().modify_order(
            modify_order_op=self._sdk.ModifyOrderOp.NORMAL, order_id=broker_order_id,
            qty=int(quantity), price=float(limit_price or 0),
            trd_env=self._sdk.TrdEnv.SIMULATE, acc_id=self._acc_id))
        row = df.to_dict("records")[0]
        return {"broker_order_id": _s(row.get("order_id"))}

    def cancel_order(self, broker_order_id: str) -> dict:
        df = self._ok("cancel_order", self._trade().modify_order(
            modify_order_op=self._sdk.ModifyOrderOp.CANCEL, order_id=broker_order_id,
            qty=0, price=0, trd_env=self._sdk.TrdEnv.SIMULATE, acc_id=self._acc_id))
        row = df.to_dict("records")[0]
        return {"broker_order_id": _s(row.get("order_id"))}

    def unlock(self) -> None:
        """显式空操作:SIMULATE 无需解锁;本进程永不解锁 REAL(080 门禁后另议)。"""
        return None

    def healthy(self) -> bool:
        try:
            self._ok("get_acc_list", self._trade().get_acc_list())
            return True
        except Exception:
            return False

    def open_orders_by_remark(self) -> dict[str, str]:
        df = self._ok("order_list_query", self._trade().order_list_query(
            trd_env=self._sdk.TrdEnv.SIMULATE, acc_id=self._acc_id))
        out: dict[str, str] = {}
        for r in df.to_dict("records"):
            if _s(r.get("order_status")) in _INCOMPLETE and _s(r.get("remark")):
                out[_s(r.get("remark"))] = _s(r.get("order_id"))
        return out

    # ---- 轮询回补(070 无推送回调时的事实来源) ----

    def poll_orders(self) -> list[dict]:
        """全量订单行(remark/status/时间),供循环把券商事实回灌网关状态机。"""
        df = self._ok("order_list_query", self._trade().order_list_query(
            trd_env=self._sdk.TrdEnv.SIMULATE, acc_id=self._acc_id))
        return [
            {"remark": _s(r.get("remark")), "broker_order_id": _s(r.get("order_id")),
             "status": _s(r.get("order_status")),
             "dealt_qty": int(_f(r.get("dealt_qty"))),
             "dealt_avg_price": _f(r.get("dealt_avg_price")),
             "updated": _s(r.get("updated_time")) or _s(r.get("create_time"))}
            for r in df.to_dict("records")
        ]

    def poll_deals(self) -> list[dict]:
        """当日成交(order_id 关联),供循环回灌 on_fill。"""
        df = self._ok("deal_list_query", self._trade().deal_list_query(
            trd_env=self._sdk.TrdEnv.SIMULATE, acc_id=self._acc_id))
        return [
            {"broker_execution_id": _s(r.get("deal_id")),
             "broker_order_id": _s(r.get("order_id")),
             "quantity": int(_f(r.get("qty"))), "price": _f(r.get("price")),
             "created": _s(r.get("create_time"))}
            for r in df.to_dict("records")
        ]


def build_simulate_trading_client(*, acc_id: str, host: str = "127.0.0.1",
                                  port: int = 11111,
                                  security_firm: str = "FUTUAU") -> SimulateTradingClient:
    """真机工厂:惰性导入 SDK,缺失如实抛错(与只读桥同一纪律)。"""
    try:  # pragma: no cover - 真机路径
        import moomoo as sdk  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("moomoo SDK 未安装:交易桥只能在部署主机上构建") from exc
    return SimulateTradingClient(sdk, acc_id=acc_id, host=host, port=port,
                                 security_firm=security_firm)


class RealTradingClient(SimulateTradingClient):
    """REAL 环境交易桥(080)。与模拟桥同形,红线相反:只认 REAL、拒绝一切非 REAL。

    - 本类仅由网关在**十一门禁全过**后驱动;门禁不齐时代码路径根本走不到这里
      (MODE_TO_TRD_ENV 非 REAL、授权文件缺失、实盘总开关为 0 任一即封死);
    - unlock():交易解锁只在网关 _ensure_unlocked(门禁后)调用;解锁密码从环境
      现读现算 MD5,不落盘不留存;
    - 轮询接口继承(REAL 环境成交明细接口可用,自动走明细路)。
    """

    _ENV = "REAL"

    def place_order(self, *, symbol: str, side: str, quantity: int, order_type: str,
                    limit_price, trd_env: str, remark: str) -> dict:
        if trd_env != "REAL":
            raise PermissionError(f"真实桥只认 REAL,收到 {trd_env}")
        if order_type != "LIMIT" or limit_price is None:
            raise ValueError(f"仅支持带价 LIMIT 单,收到 {order_type}/{limit_price}")
        side_map = {"BUY": self._sdk.TrdSide.BUY, "SELL": self._sdk.TrdSide.SELL}
        if side not in side_map:
            raise ValueError(f"未知方向 {side}")
        df = self._ok("place_order", self._trade().place_order(
            price=float(limit_price), qty=int(quantity), code=f"US.{symbol}",
            trd_side=side_map[side], order_type=self._sdk.OrderType.NORMAL,
            trd_env=self._sdk.TrdEnv.REAL, acc_id=self._acc_id, remark=remark))
        row = df.to_dict("records")[0]
        return {"broker_order_id": _s(row.get("order_id"))}

    def unlock(self) -> None:
        """门禁后解锁交易。密码环境现读,MD5 现算,函数返回即丢弃。"""
        import hashlib
        import os

        pw = os.environ.get("MOOMOO_UNLOCK_PASSWORD", "")
        if not pw or pw.startswith("<"):
            raise PermissionError("解锁密码未配置(失败关闭)")
        self._ok("unlock_trade", self._trade().unlock_trade(
            password_md5=hashlib.md5(pw.encode()).hexdigest()))

    def _sim_env(self):  # pragma: no cover - 防御:继承的模拟方法一律替换环境
        return self._sdk.TrdEnv.REAL

    def modify_order(self, broker_order_id: str, *, quantity: int, limit_price) -> dict:
        df = self._ok("modify_order", self._trade().modify_order(
            modify_order_op=self._sdk.ModifyOrderOp.NORMAL, order_id=broker_order_id,
            qty=int(quantity), price=float(limit_price or 0),
            trd_env=self._sdk.TrdEnv.REAL, acc_id=self._acc_id))
        return {"broker_order_id": _s(df.to_dict("records")[0].get("order_id"))}

    def cancel_order(self, broker_order_id: str) -> dict:
        df = self._ok("cancel_order", self._trade().modify_order(
            modify_order_op=self._sdk.ModifyOrderOp.CANCEL, order_id=broker_order_id,
            qty=0, price=0, trd_env=self._sdk.TrdEnv.REAL, acc_id=self._acc_id))
        return {"broker_order_id": _s(df.to_dict("records")[0].get("order_id"))}

    def open_orders_by_remark(self) -> dict[str, str]:
        df = self._ok("order_list_query", self._trade().order_list_query(
            trd_env=self._sdk.TrdEnv.REAL, acc_id=self._acc_id))
        out: dict[str, str] = {}
        for r in df.to_dict("records"):
            if _s(r.get("order_status")) in _INCOMPLETE and _s(r.get("remark")):
                out[_s(r.get("remark"))] = _s(r.get("order_id"))
        return out

    def poll_orders(self) -> list[dict]:
        df = self._ok("order_list_query", self._trade().order_list_query(
            trd_env=self._sdk.TrdEnv.REAL, acc_id=self._acc_id))
        return [
            {"remark": _s(r.get("remark")), "broker_order_id": _s(r.get("order_id")),
             "status": _s(r.get("order_status")),
             "dealt_qty": int(_f(r.get("dealt_qty"))),
             "dealt_avg_price": _f(r.get("dealt_avg_price")),
             "updated": _s(r.get("updated_time")) or _s(r.get("create_time"))}
            for r in df.to_dict("records")
        ]

    def poll_deals(self) -> list[dict]:
        df = self._ok("deal_list_query", self._trade().deal_list_query(
            trd_env=self._sdk.TrdEnv.REAL, acc_id=self._acc_id))
        return [
            {"broker_execution_id": _s(r.get("deal_id")),
             "broker_order_id": _s(r.get("order_id")),
             "quantity": int(_f(r.get("qty"))), "price": _f(r.get("price")),
             "created": _s(r.get("create_time"))}
            for r in df.to_dict("records")
        ]


def build_real_trading_client(*, acc_id: str, host: str = "127.0.0.1",
                              port: int = 11111,
                              security_firm: str = "FUTUAU") -> RealTradingClient:
    """REAL 工厂(080):仅部署主机;调用方(build_live_cycle)已验模式与授权。"""
    try:  # pragma: no cover - 真机路径
        import moomoo as sdk  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("moomoo SDK 未安装:交易桥只能在部署主机上构建") from exc
    return RealTradingClient(sdk, acc_id=acc_id, host=host, port=port,
                             security_firm=security_firm)
