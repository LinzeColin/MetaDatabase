"""账本模式戳:一本账、一个运行目录只属于一个运行模式(R4 混账的模式版)。

影子盘的模拟成交与将来券商模拟盘/微实盘的真实成交,在库里长得一模一样(同一批表)。
若 owner 把 ALPHA_MODE 改成 PAPER/MICRO_LIVE 却沿用旧库与旧运行目录,调仓会把影子持仓当成
券商持仓,微实盘还会对真实账户发出卖出影子持仓的真单。所以:

- 装配时给"库"和"运行目录"各盖一个模式戳(库里 ledger_meta.ledger_mode、运行目录 LEDGER_MODE.txt);
- 戳与当前模式不一致 -> 拒绝装配(失败关闭),提示换全新的 ALPHA_DATABASE_URL 与 ALPHA_RUNTIME_DIR;
- 没有戳的旧账本按内容判归属:含 sim_orders = 影子盘的;含订单或运行状态文件 = 券商类的;
  什么都没有 = 空账本,谁都能认领。影子盘只认领影子盘或空账本,券商模式只认领券商类或空账本。
模式升级只能由 owner 触发(改环境文件),本模块只负责让升级必须换新账。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import func, select

from backend.app.adapters.brokers.base import SystemMode
from backend.app.domain.models import BrokerOrder, LedgerMeta, SimOrder

STAMP_KEY = "ledger_mode"
RUNTIME_STAMP_FILE = "LEDGER_MODE.txt"
#: 运行目录里"这个模式已经在此记过账"的状态文件(无戳旧目录据此判非空)
#: (净值快照任何模式都会写 equity_history.json,不是归属线索,不列入)
_RUNTIME_STATE_FILES = ("LIVE_START_CAPITAL.json", "last_s1_eval.txt", "last_eval_result.json")
_UPGRADE_HINT = ("升级模式必须换全新的账本与运行目录:新的 ALPHA_DATABASE_URL 与 ALPHA_RUNTIME_DIR;"
                 "旧账本留档不动,绝不与新模式共用")


def _belongs(mode: SystemMode) -> str:
    return "SHADOW" if mode is SystemMode.SHADOW else "BROKER"


def _judge(stamp: Optional[str], legacy: str, mode: SystemMode, where: str) -> None:
    """stamp=已盖的戳;legacy=无戳时按内容判的归属("SHADOW"/"BROKER"/"EMPTY")。"""
    if stamp is not None:
        if stamp != mode.value:
            raise RuntimeError(f"{where}属于 {stamp} 模式,当前是 {mode.value},拒绝装配(失败关闭)。"
                               f"{_UPGRADE_HINT}")
        return
    if legacy != "EMPTY" and legacy != _belongs(mode):
        raise RuntimeError(f"{where}没有模式戳,内容显示属于{'影子盘' if legacy == 'SHADOW' else '券商类模式'},"
                           f"与当前模式 {mode.value} 不符,拒绝装配(失败关闭)。{_UPGRADE_HINT}")


def claim_ledger(factory, mode: SystemMode, runtime_dir: Path) -> None:
    """认领账本与运行目录:戳不符即抛错;通过则补盖两个戳。装配时调用一次(影子盘与券商路径各一次)。"""
    runtime_dir = Path(runtime_dir)
    with factory() as s:
        row = s.get(LedgerMeta, STAMP_KEY)
        db_stamp = row.value if row is not None else None
        has_sim = bool(s.scalar(select(func.count()).select_from(SimOrder)))
        has_orders = bool(s.scalar(select(func.count()).select_from(BrokerOrder)))
    db_legacy = "SHADOW" if has_sim else ("BROKER" if has_orders else "EMPTY")
    _judge(db_stamp, db_legacy, mode, "账本数据库")

    stamp_file = runtime_dir / RUNTIME_STAMP_FILE
    rt_stamp = stamp_file.read_text().strip() if stamp_file.exists() else None
    rt_legacy = "EMPTY"
    if any((runtime_dir / f).exists() for f in _RUNTIME_STATE_FILES):
        # 运行目录自身没有影子/券商的内容线索:以库的归属为准;库是空的就按"券商类"保守认定
        rt_legacy = db_legacy if db_stamp is None else _belongs(SystemMode(db_stamp))
        if rt_legacy == "EMPTY":
            rt_legacy = "BROKER"
    _judge(rt_stamp, rt_legacy, mode, f"运行目录 {runtime_dir}")

    if db_stamp is None:
        with factory() as s, s.begin():
            s.add(LedgerMeta(key=STAMP_KEY, value=mode.value))
    if rt_stamp is None:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        stamp_file.write_text(mode.value)
