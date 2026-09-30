"""前向记分簿：只追加的 SQLite。每个美股交易日收盘后记一行，20/60 个交易日后自动结算。

原则
- 只追加：表上有触发器，任何 UPDATE / DELETE 都会被数据库自己拒绝；亏损照样留存。
- 从上线日起算：不回填、不补记、不修正历史（没有记上的交易日就是没有记上，摘要里会数出「缺几天」）。
- 每天记：当日决策（建议或 NO_ACTION）、观察名单、建议股收盘价、IWM 收盘价、「同市值档随机对照」一只。
  随机对照按「日期 + 市值档」做种子从同档候选池里抽，同一天同一候选池重算得到同一只（可复现）。
  NO_ACTION 的日子没有建议股，也就没有要对照的市值档：只记 IWM 收盘价。
- 结算：建议股收盘价起算，持有 20 / 60 个交易日（交易日历取自 IWM 日线），算相对 IWM 超额、相对随机对照超额、
  是否命中（超额 > 0）、Brier（只有当时的建议带上涨概率才算，目前股势前瞻整分支 ABSTAIN，所以为空）。
- 样本不足（已结算 < 8）时，公开摘要不含任何收益数字，只写「样本不足，暂不下结论」。
  这条是构造出来的（摘要里根本没有数字），不靠调用方记得去隐藏。
- 影子候选（B4.5）：规则自证门没开时，中枢照常算出「如果发布会选谁」，每个交易日收盘后以 shadow 记一行，
  存在单独的两张表（shadow_record / shadow_settlement），与正式建议分开：不进分支权重，不进正式命中率，
  同样只追加、同样 20/60 日结算并带随机对照。影子候选样本 < 8 同样不含任何收益数字。
  前向证据（规则自证门的 (b)）= 已结算的影子候选 + 正式建议合并统计——它们是同一条规则的同一类输出，
  这样门打开后正式建议亏损也会把门重新关上。
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
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ---- 记录 ---------------------------------------------------------------------------
    def has_day(self, trading_day: str) -> bool:
        return self.db.execute("SELECT 1 FROM daily_record WHERE trading_day = ?", (trading_day,)).fetchone() is not None

    def record_day(self, trading_day: str, decision: Mapping[str, Any], *, close_price: Optional[float], iwm_close: float,
                   control: Optional[Mapping[str, Any]] = None, control_close: Optional[float] = None,
                   now: Optional[datetime] = None, probability: Optional[float] = None) -> bool:
        """追加一行；这一天已经记过就什么也不做（不覆盖）。返回是否新增。"""
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
                    "control_tier, control_seed, control_pool_size, control_pool_sha) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trading_day, (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(), decision["state"],
                     decision.get("primary_symbol"), decision.get("primary_name"), decision.get("market_cap_usd"),
                     json.dumps(_decision_public(decision), ensure_ascii=False, sort_keys=True),
                     json.dumps(decision.get("watchlist") or [], ensure_ascii=False, sort_keys=True),
                     json.dumps(supporters, ensure_ascii=False), probability,
                     (decision.get("data_chain") or {}).get("snapshot_sha256"), close_price, iwm_close,
                     (control or {}).get("symbol"), control_close, (control or {}).get("tier"), (control or {}).get("seed"),
                     (control or {}).get("pool_size"), (control or {}).get("pool_sha")))
        except sqlite3.IntegrityError:
            return False
        return True

    # ---- 影子候选 ------------------------------------------------------------------------
    def has_shadow_day(self, trading_day: str) -> bool:
        return self.db.execute("SELECT 1 FROM shadow_record WHERE trading_day = ?", (trading_day,)).fetchone() is not None

    def record_shadow(self, trading_day: str, decision: Mapping[str, Any], *, close_price: float, iwm_close: float,
                      control: Optional[Mapping[str, Any]] = None, control_close: Optional[float] = None,
                      now: Optional[datetime] = None) -> bool:
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
                    "close_price, iwm_close, control_symbol, control_close, control_tier, control_seed, control_pool_size, control_pool_sha) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trading_day, (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(), shadow["symbol"], shadow.get("name"),
                     shadow.get("market_cap_usd"), json.dumps(public, ensure_ascii=False, sort_keys=True), json.dumps(supporters, ensure_ascii=False),
                     (decision.get("data_chain") or {}).get("snapshot_sha256"), close_price, iwm_close, (control or {}).get("symbol"), control_close,
                     (control or {}).get("tier"), (control or {}).get("seed"), (control or {}).get("pool_size"), (control or {}).get("pool_sha")))
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
        """结算所有已满 20/60 个交易日、还没结算的建议。取不到收盘价的这轮跳过，下一轮再试（不用估计值凑）。"""
        return self._settle_due("formal", bars_fn, iwm_bars, now)

    def settle_shadow_due(self, bars_fn: BarsFn, iwm_bars: Bars, now: Optional[datetime] = None) -> List[dict]:
        """同上，结算影子候选。"""
        return self._settle_due("shadow", bars_fn, iwm_bars, now)

    def _settle_due(self, kind: str, bars_fn: BarsFn, iwm_bars: Bars, now: Optional[datetime]) -> List[dict]:
        settlements = "settlement" if kind == "formal" else "shadow_settlement"
        done: List[dict] = []
        for horizon, record in self._unsettled(kind):
            exit_day = trading_days_after(iwm_bars, record["trading_day"], horizon)
            if exit_day is None:
                continue
            stock_bars = bars_fn(record["symbol"])
            exit_close, iwm_exit = _close_on(stock_bars, exit_day), _close_on(iwm_bars, exit_day)
            if exit_close is None or iwm_exit is None or not record["close_price"] or not record["iwm_close"]:
                continue
            stock_return = exit_close / record["close_price"] - 1.0
            iwm_return = iwm_exit / record["iwm_close"] - 1.0
            control_exit = control_return = excess_control = None
            if record["control_symbol"] and record["control_close"]:
                control_exit = _close_on(bars_fn(record["control_symbol"]), exit_day)
                if control_exit is not None:
                    control_return = control_exit / record["control_close"] - 1.0
                    excess_control = stock_return - control_return
            excess = stock_return - iwm_return
            brier = None
            if kind == "formal" and record["probability"] is not None:
                brier = (float(record["probability"]) - (1.0 if excess > 0 else 0.0)) ** 2
            try:
                with self.db:
                    self.db.execute(
                        "INSERT INTO %s (record_id, horizon, exit_day, settled_at, exit_close, iwm_exit_close, control_exit_close, "
                        "stock_return, iwm_return, control_return, excess_vs_iwm, excess_vs_control, hit, brier) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)" % settlements,
                        (record["id"], horizon, exit_day, (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
                         exit_close, iwm_exit, control_exit, stock_return, iwm_return, control_return, excess, excess_control,
                         1 if excess > 0 else 0, brier))
            except sqlite3.IntegrityError:
                continue
            item = {"trading_day": record["trading_day"], "symbol": record["symbol"], "horizon": horizon, "exit_day": exit_day}
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

    def forward_evidence(self, horizon: int = 20) -> Dict[str, Any]:
        """规则自证门 (b) 的原料：已结算（20 日）的影子候选 + 正式建议，合并统计。只给中枢内部用，不直接公开。"""
        counts: Dict[str, Any] = {"shadow_settled": 0, "formal_settled": 0, "hits": 0}
        excess: List[float] = []
        for key, table in (("shadow_settled", "shadow_settlement"), ("formal_settled", "settlement")):
            for row in self.db.execute("SELECT excess_vs_iwm, hit FROM %s WHERE horizon = ?" % table, (horizon,)):
                counts[key] += 1
                counts["hits"] += int(row["hit"])
                excess.append(row["excess_vs_iwm"])
        counts["settled"] = counts["shadow_settled"] + counts["formal_settled"]
        counts["mean_excess"] = statistics.fmean(excess) if excess else None
        return counts

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
