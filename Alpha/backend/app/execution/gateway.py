"""唯一执行网关(ALPHA-LIVE-035)。

铁律:
- 先落库后提交:意图+幂等键+SUBMITTING 折叠先持久化,才允许触碰券商接口。
- 单写者:每次提交前验证租约仍在手;无租约=不提交。
- 双层频控:业务 5 笔/60 分钟(事件表计数)+ 券商 15 次/30 秒。
- REAL 路径存在但默认被十一门禁完全封锁;SIMULATE 用于 Paper 验证。
- 回调可能先于同步返回:成交/状态回调经 store 安全合并;晚到的同步回执
  只补录券商单号,绝不回退状态。
- 重启恢复:SUBMITTING 悬挂订单按幂等键向券商核对——找到即归位,
  找不到标记 SUBMIT_FAILED;恢复过程绝不重新提交。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional, Protocol

from backend.app.adapters.brokers.base import SystemMode, TrdEnv, MODE_TO_TRD_ENV
from backend.app.domain.state_machine import IllegalTransitionError, OrderState
from backend.app.execution.gates import (
    GateInputs,
    GateReport,
    evaluate_eleven_gates,
    validate_authorization,
)
from backend.app.execution.lease import LeaseManager
from backend.app.execution.ratelimit import (
    BrokerRateLimiter,
    BusinessRateLimiter,
    RateLimitExceededError,
)
from backend.app.risk.engine import RiskContext, RiskVerdict, evaluate as risk_evaluate
from backend.app.store.orders import OrderStore


class GateBlockedError(Exception):
    def __init__(self, report: GateReport) -> None:
        self.report = report
        super().__init__(f"REAL 路径被门禁封锁: {report.failures}")


class LeaseLostError(Exception):
    pass


class TradingClient(Protocol):
    """交易会话门面(SIMULATE 用假件/OpenD 模拟环境;REAL 桥接部署日联调)。"""

    def place_order(
        self, *, symbol: str, side: str, quantity: int, order_type: str,
        limit_price: Optional[Decimal], trd_env: str, remark: str,
    ) -> dict: ...
    def modify_order(self, broker_order_id: str, *, quantity: int, limit_price: Optional[Decimal]) -> dict: ...
    def cancel_order(self, broker_order_id: str) -> dict: ...
    def unlock(self) -> None: ...
    def healthy(self) -> bool: ...
    def open_orders_by_remark(self) -> dict[str, str]: ...  # remark(幂等键) -> broker_order_id


class ExecutionGateway:
    def __init__(
        self,
        *,
        store: OrderStore,
        client: TradingClient,
        lease: LeaseManager,
        mode: SystemMode,
        policy_path: str = "configs/trading_governor_policy.yaml",
        promotion_config_path: str = "configs/strategy_promotion.yaml",
        authorization_path: str = "runtime/LIVE_AUTHORIZATION.json",
        kill_switch_check: Callable[[], bool] = lambda: False,   # True=已触发
        env_reader: Callable[[str], Optional[str]] = os.environ.get,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        business_limiter: Optional[BusinessRateLimiter] = None,
        broker_limiter: Optional[BrokerRateLimiter] = None,
    ) -> None:
        self._store = store
        self._client = client
        self._lease = lease
        self._mode = mode
        self._policy_path = policy_path
        self._promotion_path = promotion_config_path
        self._auth_path = authorization_path
        self._kill_switch = kill_switch_check
        self._env = env_reader
        self._now = now_fn
        self._biz_limit = business_limiter or BusinessRateLimiter(store, now_fn=now_fn)
        self._broker_limit = broker_limiter or BrokerRateLimiter(now_fn=now_fn)
        self._unlocked = False

    # ---------- 提交 ----------

    def submit_intent(
        self,
        *,
        idempotency_key: str,
        symbol: str,
        side: str,
        quantity: int,
        currency: str,
        strategy_source: str,
        order_type: str = "LIMIT",
        limit_price: Optional[Decimal] = None,
        risk_ctx: RiskContext,
    ) -> str:
        """完整提交流程:落库 -> 风控 -> (REAL: 十一门禁) -> 频控 -> SUBMITTING -> 券商。

        返回 order_id。任何拒绝路径都已留审计并保持失败关闭。
        """
        trd_env, may_trade = MODE_TO_TRD_ENV[self._mode]
        if not may_trade:
            raise GateBlockedError(GateReport(passed=False, failures=("MODE_FORBIDS_TRADING",),
                                              detail={"mode": self._mode.value}))

        key_unused = self._store.idempotency_key_available(idempotency_key)
        order_id = self._store.create_intent(
            idempotency_key=idempotency_key, symbol=symbol, side=side, quantity=quantity,
            currency=currency, strategy_source=strategy_source,
            order_type=order_type, limit_price=limit_price,
        )

        verdict: RiskVerdict = risk_evaluate(risk_ctx)
        self._store.record_risk_decision(
            order_id, allowed=verdict.allowed,
            triggered_rules=list(verdict.triggered_rules), exposure_snapshot=verdict.snapshot,
        )
        if not verdict.allowed:
            return order_id  # RISK_REJECTED 终态,审计已全

        if trd_env is TrdEnv.REAL:
            report = self._evaluate_gates(verdict, key_unused)
            if not report.passed:
                self._store.annotate(order_id, event_type="GATE_BLOCKED_REAL",
                                     payload={"failures": list(report.failures), **report.detail})
                raise GateBlockedError(report)
            self._ensure_unlocked()

        if not self._lease.held():
            self._store.annotate(order_id, event_type="LEASE_NOT_HELD_BLOCKED")
            raise LeaseLostError("执行租约不在手,拒绝提交")

        try:
            self._biz_limit.check()
            self._broker_limit.acquire()
        except RateLimitExceededError as exc:
            self._store.annotate(order_id, event_type="RATE_LIMIT_BLOCKED",
                                 payload={"layer": exc.layer, "detail": str(exc)})
            raise

        # 先落库后提交
        self._store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT",
                                     payload={"trd_env": trd_env.value})
        try:
            ack = self._client.place_order(
                symbol=symbol, side=side, quantity=quantity, order_type=order_type,
                limit_price=limit_price, trd_env=trd_env.value, remark=idempotency_key,
            )
        except Exception as exc:
            self._store.apply_transition(order_id, OrderState.SUBMIT_FAILED,
                                         event_type="GATEWAY_SUBMIT_ERROR", payload={"error": str(exc)})
            raise

        self._merge_sync_ack(order_id, str(ack["broker_order_id"]))
        return order_id

    def _evaluate_gates(self, verdict: RiskVerdict, key_unused: bool) -> GateReport:
        auth_ok, auth_reasons = validate_authorization(
            self._auth_path, policy_path=self._policy_path,
            promotion_config_path=self._promotion_path, now=self._now(),
        )
        inputs = GateInputs(
            env_flag_live_trading=(self._env("LIVE_TRADING_ENABLED") == "1"),
            authorization_ok=auth_ok,
            authorization_reasons=tuple(auth_reasons),
            policy_hash_matches=auth_ok,  # 授权校验已含 policy hash 锚定;失败原因在 reasons
            broker_healthy=self._client.healthy(),
            jurisdiction_verdict=self._store.latest_jurisdiction_verdict(),
            reconciliation_clean=not self._store.halt_new_orders(),
            market_data_fresh=(
                verdict.snapshot.get("quote_age_seconds") is not None
                and "RULE_MARKET_DATA_STALE" not in verdict.triggered_rules
                and "RULE_MARKET_DATA_MISSING" not in verdict.triggered_rules
            ),
            risk_allowed=verdict.allowed,
            idempotency_key_unused=key_unused,
            kill_switch_clear=not self._kill_switch(),
            lease_held=self._lease.held(),
        )
        return evaluate_eleven_gates(inputs)

    def _ensure_unlocked(self) -> None:
        if not self._unlocked:
            self._client.unlock()  # 只在门禁全过后的 REAL 路径发生
            self._unlocked = True

    def _merge_sync_ack(self, order_id: str, broker_order_id: str) -> None:
        """同步回执合并:回调可能已把状态推得更远——晚到回执只补录单号。"""
        current = self._store.get_state(order_id)
        if current is OrderState.SUBMITTING:
            self._store.apply_transition(order_id, OrderState.SUBMITTED, event_type="BROKER_SYNC_ACK",
                                         broker_order_id=broker_order_id)
        else:
            self._store.annotate(order_id, event_type="BROKER_SYNC_ACK_LATE",
                                 payload={"state_at_ack": current.value},
                                 broker_order_id=broker_order_id)

    # ---------- 回调入口(订单推送/成交推送) ----------

    def on_order_event(self, *, idempotency_key: str, broker_order_id: str, status: str,
                       broker_timestamp: Optional[datetime] = None,
                       broker_sequence: Optional[int] = None) -> None:
        order_id = self._store.find_order_by_idempotency_key(idempotency_key)
        if order_id is None:
            return  # 未知订单:040 对账器处置;这里不猜
        mapping = {
            "SUBMITTED": OrderState.SUBMITTED,
            "ACCEPTED": OrderState.ACCEPTED,
            "REJECTED": OrderState.REJECTED,
            "CANCELLED": OrderState.CANCELLED,
            "EXPIRED": OrderState.EXPIRED,
        }
        target = mapping.get(status)
        if target is None:
            self._store.mark_unknown(order_id, reason=f"无法解释的券商状态: {status}")
            return
        current = self._store.get_state(order_id)
        if current is OrderState.SUBMITTING and target not in (OrderState.SUBMITTED,):
            # 回调先于同步返回:补写 SUBMITTED 中间态
            if target in (OrderState.ACCEPTED,):
                self._store.apply_transition(order_id, OrderState.SUBMITTED,
                                             event_type="BACKFILLED_INTERMEDIATE",
                                             broker_order_id=broker_order_id, backfilled=True)
        try:
            self._store.apply_transition(order_id, target, event_type=f"BROKER_{status}",
                                         broker_order_id=broker_order_id,
                                         broker_timestamp=broker_timestamp,
                                         broker_sequence=broker_sequence)
        except IllegalTransitionError:
            # store 已完成隔离(审计+UNKNOWN+开对账);网关不再扩散异常
            pass

    def on_fill(self, *, idempotency_key: str, quantity: int, price: Decimal,
                fees: Decimal = Decimal("0"), broker_execution_id: Optional[str] = None,
                broker_timestamp: Optional[datetime] = None,
                broker_sequence: Optional[int] = None) -> None:
        order_id = self._store.find_order_by_idempotency_key(idempotency_key)
        if order_id is None:
            return
        try:
            self._store.apply_fill_event(
                order_id, quantity=quantity, price=price, fees=fees,
                broker_execution_id=broker_execution_id,
                broker_timestamp=broker_timestamp, broker_sequence=broker_sequence,
            )
        except IllegalTransitionError:
            pass  # 已隔离

    # ---------- 改单 / 撤单 ----------

    def request_cancel(self, order_id: str) -> None:
        order = self._require_broker_order(order_id)
        self._store.apply_transition(order_id, OrderState.CANCEL_REQUESTED, event_type="GATEWAY_CANCEL")
        self._broker_limit.acquire()
        self._client.cancel_order(order)

    def request_modify(self, order_id: str, *, quantity: int, limit_price: Optional[Decimal]) -> None:
        order = self._require_broker_order(order_id)
        self._store.annotate(order_id, event_type="MODIFY_REQUESTED",
                             payload={"quantity": quantity, "limit_price": str(limit_price)})
        self._broker_limit.acquire()
        self._client.modify_order(order, quantity=quantity, limit_price=limit_price)

    def _require_broker_order(self, order_id: str) -> str:
        with self._store._sessions() as session:  # noqa: SLF001 - 网关与仓库同域
            from backend.app.domain.models import BrokerOrder

            row = session.get(BrokerOrder, order_id)
            if row is None or row.broker_order_id is None:
                raise KeyError(f"订单无券商单号,无法改撤: {order_id}")
            return row.broker_order_id

    # ---------- 重启恢复 ----------

    def recover_in_flight(self) -> dict:
        """恢复 SUBMITTING 悬挂订单:核对券商在途单,绝不重新提交。"""
        report = {"adopted": [], "submit_failed": []}
        hanging = self._store.list_orders_in_state(OrderState.SUBMITTING)
        if not hanging:
            return report
        broker_orders = self._client.open_orders_by_remark()
        for item in hanging:
            key = item["idempotency_key"]
            broker_id = broker_orders.get(key) or item["broker_order_id"]
            if broker_id:
                self._store.apply_transition(item["order_id"], OrderState.SUBMITTED,
                                             event_type="RECOVERY_ADOPTED", broker_order_id=str(broker_id))
                report["adopted"].append(item["order_id"])
            else:
                self._store.apply_transition(item["order_id"], OrderState.SUBMIT_FAILED,
                                             event_type="RECOVERY_SUBMIT_FAILED",
                                             payload={"reason": "券商侧无此幂等键在途单"})
                report["submit_failed"].append(item["order_id"])
        return report
