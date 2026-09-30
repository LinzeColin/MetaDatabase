"""前向记分簿：只追加的 SQLite。每个美股交易日收盘后记一行，20/60 个交易日后自动结算。

原则
- 只追加：表上有触发器，任何 UPDATE / DELETE 都会被数据库自己拒绝；亏损照样留存。
- 从上线日起算：不回填、不补记、不修正历史（没有记上的交易日就是没有记上，摘要里会数出「缺几天」）。
- 每天记：当日决策（建议或 NO_ACTION）、观察名单、建议股收盘价、IWM 收盘价、「同市值档随机对照」一只。
  随机对照按「日期 + 市值档」做种子从同档候选池里抽，同一天同一候选池重算得到同一只（可复现）。
  NO_ACTION 的日子没有建议股，也就没有要对照的市值档：只记 IWM 收盘价。
- 结算：口径与回测（backtest/hub_backtest.py）对齐——决策日 d 收盘后出结论，d 的下一个交易日收盘价入场，持有 20 / 60 个交易日后收盘价出场
  （交易日历取自 IWM 日线），每条腿（建议股、IWM、随机对照）都扣同一份成本模型（costs.py），
  算相对 IWM 的净超额、相对随机对照的净超额、是否命中（净超额 > 0）、Brier（只有当时的建议带上涨概率才算，目前股势前瞻整分支 ABSTAIN，所以为空）。
  只结算「已收盘」的日子：出场日必须已经收盘（盘中那一根不算），日线也只用已收盘的。
- 样本不足（已结算 < 8）时，公开摘要不含任何收益数字，只写「样本不足，暂不下结论」。
  这条是构造出来的（摘要里根本没有数字），不靠调用方记得去隐藏。
- 影子候选（B4.5）：规则自证门没开时，中枢照常算出「如果发布会选谁」，每个交易日收盘后以 shadow 记一行，
  存在单独的两张表（shadow_record / shadow_settlement），与正式建议分开：不进分支权重，不进正式命中率，
  同样只追加、同样 20/60 日结算并带随机对照。影子候选样本 < 8 同样不含任何收益数字。
  前向证据（规则自证门的 (b)）= 已结算的影子候选 + 正式建议合并统计——它们是同一条规则的同一类输出，
  这样门打开后正式建议亏损也会把门重新关上。合并后只数「独立样本」：同一只股只算一次，且 20 日持有窗口互不重叠；
  同一只股连续几天的影子记录、或窗口叠在一起的记录，共用同一段行情，算多条就是把一次运气重复数。
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import nyse_calendar
from .costs import BENCHMARK_DOLLAR_VOLUME, round_trip_cost

HORIZONS = (20, 60)
MIN_SETTLED_FOR_CONCLUSION = 8
INSUFFICIENT_TEXT = "样本不足，暂不下结论"
SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day     TEXT    NOT NULL UNIQUE,
    recorded_at     TEXT    NOT NULL,
    decision_state  TEXT    NOT NULL,
    symbol          TEXT,
    name            TEXT,
    market_cap_usd  REAL,
    decision_json   TEXT    NOT NULL,
    watchlist_json  TEXT    NOT NULL,
    supporters_json TEXT    NOT NULL,
    probability     REAL,
    snapshot_sha256 TEXT,
    close_price     REAL,
    iwm_close       REAL    NOT NULL,
    control_symbol  TEXT,
    control_close   REAL,
    control_tier    TEXT,
    control_seed    TEXT,
    control_pool_size INTEGER,
    control_pool_sha  TEXT
);
CREATE TABLE IF NOT EXISTS settlement (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id         INTEGER NOT NULL REFERENCES daily_record(id),
    horizon           INTEGER NOT NULL,
    exit_day          TEXT    NOT NULL,
    settled_at        TEXT    NOT NULL,
    exit_close        REAL    NOT NULL,
    iwm_exit_close    REAL    NOT NULL,
    control_exit_close REAL,
    stock_return      REAL    NOT NULL,
    iwm_return        REAL    NOT NULL,
    control_return    REAL,
    excess_vs_iwm     REAL    NOT NULL,
    excess_vs_control REAL,
    hit               INTEGER NOT NULL,
    brier             REAL,
    UNIQUE (record_id, horizon)
);
CREATE TABLE IF NOT EXISTS shadow_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day     TEXT    NOT NULL UNIQUE,
    recorded_at     TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    name            TEXT,
    market_cap_usd  REAL,
    decision_json   TEXT    NOT NULL,
    supporters_json TEXT    NOT NULL,
    snapshot_sha256 TEXT,
    close_price     REAL    NOT NULL,
    iwm_close       REAL    NOT NULL,
    control_symbol  TEXT,
    control_close   REAL,
    control_tier    TEXT,
    control_seed    TEXT,
    control_pool_size INTEGER,
    control_pool_sha  TEXT
);
CREATE TABLE IF NOT EXISTS shadow_settlement (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id         INTEGER NOT NULL REFERENCES shadow_record(id),
    horizon           INTEGER NOT NULL,
    exit_day          TEXT    NOT NULL,
    settled_at        TEXT    NOT NULL,
    exit_close        REAL    NOT NULL,
    iwm_exit_close    REAL    NOT NULL,
    control_exit_close REAL,
    stock_return      REAL    NOT NULL,
    iwm_return        REAL    NOT NULL,
    control_return    REAL,
    excess_vs_iwm     REAL    NOT NULL,
    excess_vs_control REAL,
    hit               INTEGER NOT NULL,
    brier             REAL,
    UNIQUE (record_id, horizon)
);
CREATE TRIGGER IF NOT EXISTS shadow_record_no_update BEFORE UPDATE ON shadow_record BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS shadow_record_no_delete BEFORE DELETE ON shadow_record BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS shadow_settlement_no_update BEFORE UPDATE ON shadow_settlement BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS shadow_settlement_no_delete BEFORE DELETE ON shadow_settlement BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS daily_record_no_update BEFORE UPDATE ON daily_record BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS daily_record_no_delete BEFORE DELETE ON daily_record BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS settlement_no_update BEFORE UPDATE ON settlement BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
CREATE TRIGGER IF NOT EXISTS settlement_no_delete BEFORE DELETE ON settlement BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END;
"""

# 后加的列：新库和旧库都走同一条迁移（ALTER TABLE ADD COLUMN 不触碰只追加触发器）。
_ADDED_COLUMNS = {
    "daily_record": (("cost_dollar_volume", "REAL"), ("control_dollar_volume", "REAL")),
    "shadow_record": (("cost_dollar_volume", "REAL"), ("control_dollar_volume", "REAL")),
    "settlement": (("entry_day", "TEXT"), ("entry_close", "REAL"), ("iwm_entry_close", "REAL"), ("control_entry_close", "REAL"),
                   ("stock_cost", "REAL"), ("iwm_cost", "REAL"), ("control_cost", "REAL")),
    "shadow_settlement": (("entry_day", "TEXT"), ("entry_close", "REAL"), ("iwm_entry_close", "REAL"), ("control_entry_close", "REAL"),
                          ("stock_cost", "REAL"), ("iwm_cost", "REAL"), ("control_cost", "REAL")),
}

CAP_TIERS = ((3e8, 1e9, "3-10亿美元"), (1e9, 2e9, "10-20亿美元"), (2e9, 5e9 + 1.0, "20-50亿美元"))

Bars = Sequence[Tuple[str, float]]          # [(YYYY-MM-DD, 收盘价)]，升序
BarsFn = Callable[[str], Optional[Bars]]


def cap_tier(market_cap_usd: Optional[float]) -> Optional[str]:
    if market_cap_usd is None:
        return None
    for low, high, name in CAP_TIERS:
        if low <= market_cap_usd < high:
            return name
    return None


def control_order(trading_day: str, tier: str, symbols: Sequence[str]) -> Tuple[List[str], str]:
    """同档候选的可复现随机顺序：种子 = sha256(日期|市值档)。返回（顺序, 种子）。"""
    seed = hashlib.sha256(("%s|%s" % (trading_day, tier)).encode("utf-8")).hexdigest()
    ordered = sorted(symbols)
    random.Random(int(seed, 16)).shuffle(ordered)
    return ordered, seed


def draw_control(trading_day: str, symbol: str, market_cap_usd: Optional[float], pool: Sequence[Mapping[str, Any]],
                 has_close: Optional[Callable[[str], bool]] = None) -> Optional[dict]:
    """从同市值档的候选池里抽一只随机对照（不含建议股本身）。has_close：取不到收盘价的顺延到下一只。"""
    tier = cap_tier(market_cap_usd)
    if tier is None:
        return None
    same_tier = [e["symbol"] for e in pool if e["symbol"] != symbol and cap_tier(e.get("market_cap_usd")) == tier]
    if not same_tier:
        return None
    ordered, seed = control_order(trading_day, tier, same_tier)
    pool_sha = hashlib.sha256("\n".join(sorted(same_tier)).encode("utf-8")).hexdigest()[:16]
    for attempt, candidate in enumerate(ordered):
        if has_close is None or has_close(candidate):
            return {"symbol": candidate, "tier": tier, "seed": seed[:16], "pool_size": len(same_tier), "pool_sha": pool_sha,
                    "attempt": attempt}
    return None


def _close_on(bars: Optional[Bars], day: str) -> Optional[float]:
    if not bars:
        return None
    for d, close in bars:
        if d == day:
            return float(close)
    return None


def trading_days_after(iwm_bars: Bars, day: str, horizon: int) -> Optional[str]:
    """交易日历取自 IWM 日线：day 之后第 horizon 个交易日；还没到（或 day 不在日历里）返回 None。"""
    days = [d for d, _ in iwm_bars]
    if day not in days:
        return None
    index = days.index(day) + horizon
    return days[index] if index < len(days) else None


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for table, columns in _ADDED_COLUMNS.items():
            existing = {row["name"] for row in self.db.execute("PRAGMA table_info(%s)" % table)}
            for name, kind in columns:
                if name not in existing:
                    self.db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, kind))
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ---- 记录 ---------------------------------------------------------------------------
    def has_day(self, trading_day: str) -> bool:
        return self.db.execute("SELECT 1 FROM daily_record WHERE trading_day = ?", (trading_day,)).fetchone() is not None

    def record_day(self, trading_day: str, decision: Mapping[str, Any], *, close_price: Optional[float], iwm_close: float,
                   control: Optional[Mapping[str, Any]] = None, control_close: Optional[float] = None,
                   now: Optional[datetime] = None, probability: Optional[float] = None,
                   dollar_volume: Optional[float] = None, control_dollar_volume: Optional[float] = None) -> bool:
        """追加一行；这一天已经记过就什么也不做（不覆盖）。返回是否新增。
        dollar_volume / control_dollar_volume：建议股与随机对照当时的 20 日成交额中位数，结算时按它套成本分档（缺失按最差一档）。"""
        if decision["state"] not in ("RECOMMENDATION", "NO_ACTION"):
            raise ValueError("只记录建议或 NO_ACTION，不记录 %s" % decision["state"])
        if decision["state"] == "RECOMMENDATION" and close_price is None:
            raise ValueError("建议当天必须有收盘价")
        supporters = [{"branch_id": b["branch_id"], "kind": b["kind"], "weighted": b["weighted"]}
                      for b in (decision.get("support") or {}).get("branches", [])]
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO daily_record (trading_day, recorded_at, decision_state, symbol, name, market_cap_usd, decision_json, "
                    "watchlist_json, supporters_json, probability, snapshot_sha256, close_price, iwm_close, control_symbol, control_close, "
                    "control_tier, control_seed, control_pool_size, control_pool_sha, cost_dollar_volume, control_dollar_volume) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trading_day, (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(), decision["state"],
                     decision.get("primary_symbol"), decision.get("primary_name"), decision.get("market_cap_usd"),
                     json.dumps(_decision_public(decision), ensure_ascii=False, sort_keys=True),
                     json.dumps(decision.get("watchlist") or [], ensure_ascii=False, sort_keys=True),
                     json.dumps(supporters, ensure_ascii=False), probability,
                     (decision.get("data_chain") or {}).get("snapshot_sha256"), close_price, iwm_close,
                     (control or {}).get("symbol"), control_close, (control or {}).get("tier"), (control or {}).get("seed"),
                     (control or {}).get("pool_size"), (control or {}).get("pool_sha"), dollar_volume, control_dollar_volume))
        except sqlite3.IntegrityError:
            return False
        return True

    # ---- 影子候选 ------------------------------------------------------------------------
    def has_shadow_day(self, trading_day: str) -> bool:
        return self.db.execute("SELECT 1 FROM shadow_record WHERE trading_day = ?", (trading_day,)).fetchone() is not None

    def record_shadow(self, trading_day: str, decision: Mapping[str, Any], *, close_price: float, iwm_close: float,
                      control: Optional[Mapping[str, Any]] = None, control_close: Optional[float] = None,
                      now: Optional[datetime] = None, dollar_volume: Optional[float] = None,
                      control_dollar_volume: Optional[float] = None) -> bool:
        """追加一行影子候选（规则自证门没开时「如果发布会选谁」）；这一天已经记过就什么也不做。"""
        shadow = decision.get("shadow_candidate")
        if decision.get("state") != "NO_ACTION" or not shadow:
            raise ValueError("影子候选只在 NO_ACTION 且有影子候选时记录")
        if close_price is None:
            raise ValueError("影子候选当天必须有收盘价")
        supporters = [{"branch_id": b["branch_id"], "kind": b["kind"], "weighted": b["weighted"]} for b in shadow.get("support_branches", [])]
        public = {key: shadow[key] for key in ("symbol", "name", "market_cap_usd", "price", "support_total", "support_branches", "reasons", "sources", "sentence")
                  if key in shadow}
        public["proof_gate"] = {"state": (decision.get("proof_gate") or {}).get("state"), "line": (decision.get("proof_gate") or {}).get("line")}
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO shadow_record (trading_day, recorded_at, symbol, name, market_cap_usd, decision_json, supporters_json, snapshot_sha256, "
                    "close_price, iwm_close, control_symbol, control_close, control_tier, control_seed, control_pool_size, control_pool_sha, "
                    "cost_dollar_volume, control_dollar_volume) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trading_day, (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(), shadow["symbol"], shadow.get("name"),
                     shadow.get("market_cap_usd"), json.dumps(public, ensure_ascii=False, sort_keys=True), json.dumps(supporters, ensure_ascii=False),
                     (decision.get("data_chain") or {}).get("snapshot_sha256"), close_price, iwm_close, (control or {}).get("symbol"), control_close,
                     (control or {}).get("tier"), (control or {}).get("seed"), (control or {}).get("pool_size"), (control or {}).get("pool_sha"),
                     dollar_volume, control_dollar_volume))
        except sqlite3.IntegrityError:
            return False
        return True

    # ---- 结算 ---------------------------------------------------------------------------
    def _unsettled(self, kind: str) -> List[Tuple[int, sqlite3.Row]]:
        records, settlements, where = (("daily_record", "settlement", "decision_state = 'RECOMMENDATION' AND ") if kind == "formal"
                                       else ("shadow_record", "shadow_settlement", ""))
        rows: List[Tuple[int, sqlite3.Row]] = []
        for horizon in HORIZONS:
            rows += [(horizon, r) for r in self.db.execute(
                "SELECT * FROM %s WHERE %sid NOT IN (SELECT record_id FROM %s WHERE horizon = ?) ORDER BY trading_day" % (records, where, settlements),
                (horizon,))]
        return rows

    def unsettled(self) -> List[sqlite3.Row]:
        return self._unsettled("formal")

    def unsettled_shadow(self) -> List[Tuple[int, sqlite3.Row]]:
        return self._unsettled("shadow")

    def settle_due(self, bars_fn: BarsFn, iwm_bars: Bars, now: Optional[datetime] = None) -> List[dict]:
        """结算所有已满 20/60 个交易日、还没结算的建议。取不到收盘价的这轮跳过，下一轮再试（不用估计值凑）。
        出场日必须已经收盘（相对 now）：盘中那一根日线只含到此刻的半天，不能当收盘价结算。"""
        return self._settle_due("formal", bars_fn, iwm_bars, now)

    def settle_shadow_due(self, bars_fn: BarsFn, iwm_bars: Bars, now: Optional[datetime] = None) -> List[dict]:
        """同上，结算影子候选。"""
        return self._settle_due("shadow", bars_fn, iwm_bars, now)

    def _settle_due(self, kind: str, bars_fn: BarsFn, iwm_bars: Bars, now: Optional[datetime]) -> List[dict]:
        settlements = "settlement" if kind == "formal" else "shadow_settlement"
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        closed_through = nyse_calendar.last_closed_session_day(moment).isoformat()
        done: List[dict] = []
        for horizon, record in self._unsettled(kind):
            entry_day = trading_days_after(iwm_bars, record["trading_day"], 1)
            exit_day = trading_days_after(iwm_bars, record["trading_day"], 1 + horizon)
            if entry_day is None or exit_day is None or exit_day > closed_through:
                continue                                    # 还没到，或出场日还没收盘
            stock_bars = bars_fn(record["symbol"])
            entry_close, exit_close = _close_on(stock_bars, entry_day), _close_on(stock_bars, exit_day)
            iwm_entry, iwm_exit = _close_on(iwm_bars, entry_day), _close_on(iwm_bars, exit_day)
            if None in (entry_close, exit_close, iwm_entry, iwm_exit) or not entry_close or not iwm_entry:
                continue
            stock_return = exit_close / entry_close - 1.0
            iwm_return = iwm_exit / iwm_entry - 1.0
            stock_cost = round_trip_cost(record["cost_dollar_volume"], entry_close)
            iwm_cost = round_trip_cost(BENCHMARK_DOLLAR_VOLUME, iwm_entry)
            control_entry = control_exit = control_return = control_cost = excess_control = None
            if record["control_symbol"]:
                control_bars = bars_fn(record["control_symbol"])
                control_entry, control_exit = _close_on(control_bars, entry_day), _close_on(control_bars, exit_day)
                if control_entry and control_exit is not None:
                    control_return = control_exit / control_entry - 1.0
                    control_cost = round_trip_cost(record["control_dollar_volume"], control_entry)
                    excess_control = (stock_return - stock_cost) - (control_return - control_cost)
            excess = (stock_return - stock_cost) - (iwm_return - iwm_cost)
            brier = None
            if kind == "formal" and record["probability"] is not None:
                brier = (float(record["probability"]) - (1.0 if excess > 0 else 0.0)) ** 2
            try:
                with self.db:
                    self.db.execute(
                        "INSERT INTO %s (record_id, horizon, exit_day, settled_at, exit_close, iwm_exit_close, control_exit_close, "
                        "stock_return, iwm_return, control_return, excess_vs_iwm, excess_vs_control, hit, brier, entry_day, entry_close, "
                        "iwm_entry_close, control_entry_close, stock_cost, iwm_cost, control_cost) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)" % settlements,
                        (record["id"], horizon, exit_day, moment.isoformat(), exit_close, iwm_exit, control_exit, stock_return, iwm_return,
                         control_return, excess, excess_control, 1 if excess > 0 else 0, brier, entry_day, entry_close, iwm_entry,
                         control_entry, stock_cost, iwm_cost, control_cost))
            except sqlite3.IntegrityError:
                continue
            item = {"trading_day": record["trading_day"], "symbol": record["symbol"], "horizon": horizon, "entry_day": entry_day, "exit_day": exit_day}
            done.append(item if kind == "formal" else {**item, "kind": "shadow"})
        return done

    # ---- 统计 ---------------------------------------------------------------------------
    def branch_hit_stats(self, horizon: int = 20) -> Dict[str, Dict[str, int]]:
        """每个分支：它给出支持的、已结算的建议共几条、其中几条命中。中枢用它算分支权重。"""
        stats: Dict[str, Dict[str, int]] = {}
        for row in self.db.execute(
                "SELECT d.supporters_json AS sup, s.hit AS hit FROM settlement s JOIN daily_record d ON d.id = s.record_id WHERE s.horizon = ?",
                (horizon,)):
            for supporter in json.loads(row["sup"]):
                item = stats.setdefault(supporter["branch_id"], {"n": 0, "hits": 0})
                item["n"] += 1
                item["hits"] += int(row["hit"])
        return stats

    def _forward_rows(self, horizon: int) -> List[Dict[str, Any]]:
        """已结算（horizon 日）、按新口径（下一交易日收盘入场 + 扣成本）结算的影子候选与正式建议。
        旧口径的行（没有 entry_day）不进前向证据：口径不同的数字不能混着数。"""
        rows: List[Dict[str, Any]] = []
        for kind, records, table in (("formal", "daily_record", "settlement"), ("shadow", "shadow_record", "shadow_settlement")):
            for row in self.db.execute(
                    "SELECT r.symbol AS symbol, r.trading_day AS decision_day, s.entry_day AS entry_day, s.exit_day AS exit_day, "
                    "s.excess_vs_iwm AS excess, s.hit AS hit FROM %s s JOIN %s r ON r.id = s.record_id "
                    "WHERE s.horizon = ? AND s.entry_day IS NOT NULL" % (table, records), (horizon,)):
                rows.append({"kind": kind, **dict(row)})
        rows.sort(key=lambda r: (r["entry_day"], 0 if r["kind"] == "formal" else 1, r["symbol"] or ""))
        return rows

    @staticmethod
    def _independent(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """独立样本：不同标的，且持有窗口 [入场日, 出场日] 与已选样本的窗口互不重叠。
        窗口长度相同，按入场日先后贪心就是能选出的最多条数。"""
        picked: List[Dict[str, Any]] = []
        symbols: set = set()
        last_exit = ""
        for row in rows:
            if row["symbol"] in symbols or (last_exit and row["entry_day"] <= last_exit):
                continue
            picked.append(row)
            symbols.add(row["symbol"])
            last_exit = row["exit_day"]
        return picked

    def forward_evidence(self, horizon: int = 20) -> Dict[str, Any]:
        """规则自证门 (b) 的原料：已结算（20 日）的影子候选 + 正式建议，合并后只数独立样本
        （不同标的、20 日窗口不重叠；口径 = 下一交易日收盘入场、扣回测同一份成本）。只给中枢内部用，不直接公开。"""
        picked = self._independent(self._forward_rows(horizon))
        counts: Dict[str, Any] = {"shadow_settled": sum(r["kind"] == "shadow" for r in picked),
                                  "formal_settled": sum(r["kind"] == "formal" for r in picked), "hits": sum(int(r["hit"]) for r in picked)}
        counts["settled"] = counts["shadow_settled"] + counts["formal_settled"]
        counts["mean_excess"] = statistics.fmean(r["excess"] for r in picked) if picked else None
        return counts

    def forward_evidence_overlap(self, horizon: int = 20) -> Dict[str, Any]:
        """前向证据里被「非独立」规则挡掉的记录数：门的说明里要能看到「已结算 N 条，其中独立 M 条」。"""
        rows = self._forward_rows(horizon)
        independent = len(self._independent(rows))
        return {"raw_settled": len(rows), "independent_settled": independent, "excluded_not_independent": len(rows) - independent}

    def shadow_summary(self, *, recent: int = 10) -> dict:
        """影子候选的公开摘要：结构与正式记分簿一致；已结算 < 8 的周期不含任何收益数字（构造出来的）。"""
        counts = self.db.execute("SELECT COUNT(*) AS n, MIN(trading_day) AS first, MAX(trading_day) AS last FROM shadow_record").fetchone()
        settled = {h: self.db.execute("SELECT COUNT(*) FROM shadow_settlement WHERE horizon = ?", (h,)).fetchone()[0] for h in HORIZONS}
        sufficient = {h: settled[h] >= MIN_SETTLED_FOR_CONCLUSION for h in HORIZONS}
        out: Dict[str, Any] = {
            "inception_day": counts["first"], "last_recorded_day": counts["last"], "recorded_days": counts["n"] or 0,
            "settled": {str(h): settled[h] for h in HORIZONS}, "min_settled_for_conclusion": MIN_SETTLED_FOR_CONCLUSION,
            "sample_status": "SUFFICIENT" if sufficient[20] else "SAMPLE_INSUFFICIENT",
            "message": "影子候选已结算 %d 条（20 日）/ %d 条（60 日）；" % (settled[20], settled[60]) + (
                "样本已够，下列为全部已结算影子候选（含亏损）的汇总" if sufficient[20] else INSUFFICIENT_TEXT),
            "note": "影子候选 = 规则自证门没开时「如果发布会选谁」，只记录、不发布；从上线日起算，不回填。",
        }
        horizons: Dict[str, Any] = {}
        for horizon in HORIZONS:
            if not sufficient[horizon]:
                horizons[str(horizon)] = {"settled": settled[horizon], "status": "SAMPLE_INSUFFICIENT", "message": INSUFFICIENT_TEXT}
                continue
            rows = self.db.execute("SELECT * FROM shadow_settlement WHERE horizon = ?", (horizon,)).fetchall()
            values = [r["excess_vs_iwm"] for r in rows]
            control = [r["excess_vs_control"] for r in rows if r["excess_vs_control"] is not None]
            horizons[str(horizon)] = {
                "settled": len(rows), "status": "SUFFICIENT", "hit_rate": sum(r["hit"] for r in rows) / len(rows),
                "mean_excess_vs_iwm": statistics.fmean(values), "median_excess_vs_iwm": statistics.median(values),
                "control_samples": len(control), "mean_excess_vs_control": statistics.fmean(control) if control else None,
                "worst_excess_vs_iwm": min(values)}
        out["horizons"] = horizons
        items = []
        for record in self.db.execute("SELECT * FROM shadow_record ORDER BY trading_day DESC LIMIT ?", (recent,)).fetchall():
            item = {"trading_day": record["trading_day"], "symbol": record["symbol"], "name": record["name"], "settled_20": False, "settled_60": False}
            for horizon in HORIZONS:
                row = self.db.execute("SELECT * FROM shadow_settlement WHERE record_id = ? AND horizon = ?", (record["id"], horizon)).fetchone()
                item["settled_%d" % horizon] = row is not None
                if row is not None and sufficient[horizon]:
                    item["excess_vs_iwm_%d" % horizon] = row["excess_vs_iwm"]
            items.append(item)
        out["recent"] = items
        return out

    def summary(self, *, recent: int = 10) -> dict:
        """公开摘要。已结算样本不足 8 条的周期：只给样本数，不含任何收益/命中率数字。"""
        counts = self.db.execute(
            "SELECT COUNT(*) AS n, SUM(decision_state='RECOMMENDATION') AS rec, MIN(trading_day) AS first, MAX(trading_day) AS last FROM daily_record").fetchone()
        settled = {h: self.db.execute("SELECT COUNT(*) FROM settlement WHERE horizon = ?", (h,)).fetchone()[0] for h in HORIZONS}
        sufficient = {h: settled[h] >= MIN_SETTLED_FOR_CONCLUSION for h in HORIZONS}
        out: Dict[str, Any] = {
            "inception_day": counts["first"], "last_recorded_day": counts["last"], "recorded_days": counts["n"] or 0,
            "recommendation_days": int(counts["rec"] or 0), "no_action_days": (counts["n"] or 0) - int(counts["rec"] or 0),
            "settled": {str(h): settled[h] for h in HORIZONS}, "min_settled_for_conclusion": MIN_SETTLED_FOR_CONCLUSION,
            "sample_status": "SUFFICIENT" if sufficient[20] else "SAMPLE_INSUFFICIENT",
            "message": "已结算 %d 条（20 日）/ %d 条（60 日）；" % (settled[20], settled[60]) + (
                "样本已够，下列为全部已结算建议（含亏损）的汇总" if sufficient[20] else INSUFFICIENT_TEXT),
            "append_only": True, "backfilled": False,
            "note": "从上线日起算，不回填；没有建议的交易日只记 IWM 收盘价。",
        }
        horizons: Dict[str, Any] = {}
        for horizon in HORIZONS:
            if not sufficient[horizon]:
                horizons[str(horizon)] = {"settled": settled[horizon], "status": "SAMPLE_INSUFFICIENT", "message": INSUFFICIENT_TEXT}
                continue
            rows = self.db.execute("SELECT * FROM settlement WHERE horizon = ?", (horizon,)).fetchall()
            excess = [r["excess_vs_iwm"] for r in rows]
            control = [r["excess_vs_control"] for r in rows if r["excess_vs_control"] is not None]
            briers = [r["brier"] for r in rows if r["brier"] is not None]
            horizons[str(horizon)] = {
                "settled": len(rows), "status": "SUFFICIENT", "hit_rate": sum(r["hit"] for r in rows) / len(rows),
                "mean_excess_vs_iwm": statistics.fmean(excess), "median_excess_vs_iwm": statistics.median(excess),
                "control_samples": len(control), "mean_excess_vs_control": statistics.fmean(control) if control else None,
                "brier_mean": statistics.fmean(briers) if briers else None, "brier_samples": len(briers),
                "worst_excess_vs_iwm": min(excess),
            }
        out["horizons"] = horizons
        recent_rows = self.db.execute("SELECT * FROM daily_record ORDER BY trading_day DESC LIMIT ?", (recent,)).fetchall()
        items = []
        for record in recent_rows:
            item = {"trading_day": record["trading_day"], "state": record["decision_state"], "symbol": record["symbol"], "name": record["name"],
                    "settled_20": False, "settled_60": False}
            for horizon in HORIZONS:
                row = self.db.execute("SELECT * FROM settlement WHERE record_id = ? AND horizon = ?", (record["id"], horizon)).fetchone()
                item["settled_%d" % horizon] = row is not None
                if row is not None and sufficient[horizon]:
                    item["excess_vs_iwm_%d" % horizon] = row["excess_vs_iwm"]
            items.append(item)
        out["recent"] = items
        out["shadow"] = self.shadow_summary(recent=recent)
        return out


def _decision_public(decision: Mapping[str, Any]) -> dict:
    keep = ("state", "action", "action_code", "primary_symbol", "primary_name", "market_cap_usd", "price", "support", "rationale",
            "reasons", "sources", "conflicts", "invalidation", "published_at", "blocked_reason")
    return {key: decision[key] for key in keep if key in decision}
