"""研究层给中枢的补充输入：全候选池的市值档位表 + shortlist 的营收同比与最新定期报告。

为什么要单独一份文件：实时层（每 60 秒）只读研究产物，不碰 1.7GB 事实库，也不读证据快照。
中枢需要三样研究快照里才有的东西：
  1. 候选池全表（同市值档随机对照要从「同档候选」里抽；流动性门要成交额与流通股）；
  2. shortlist 各股最新一份 10-K/10-Q 是哪一份、营收同比多少（失效条件「下一份 10-Q 营收同比转负」的基线与核对）；
  3. 快照 hash，证明它和分支收据是同一份快照。
文件名 hubinputs-<快照hash前12位>.json，与 shortlist 同目录；内容只由快照与 shortlist 决定，重算得到同样的文件。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .branches.fundamentals import MarketInput, compute_fundamentals
from .evidence_snapshot import EvidenceSnapshot

SCHEMA = "signal-lattice-hubinputs/1"
POOL_FIELDS = ("symbol", "cik", "name", "exchange", "market_cap_usd", "price_usd", "shares_outstanding",
               "median_dollar_volume_20d_usd", "last_bar_day")


def _value(metric: Any) -> Any:
    return metric.value if getattr(metric, "ok", False) else None


def build(snapshot: EvidenceSnapshot, shortlist: Sequence[Mapping[str, Any]]) -> dict:
    entries = {e["symbol"]: e for e in snapshot.entries}
    facts, bar_store = snapshot.facts(), snapshot.bar_store()
    fundamentals: Dict[str, dict] = {}
    try:
        for item in shortlist:
            entry = entries.get(item["symbol"])
            if entry is None:
                continue
            rows = bar_store.load(entry["symbol"]) or []
            history = [(row[0], float(row[1])) for row in rows if row[0] <= snapshot.as_of]
            f = compute_fundamentals(facts, MarketInput.from_entry(entry, history), snapshot.as_of)
            latest = f.latest_periodic
            fundamentals[item["symbol"]] = {
                "revenue_ttm": _value(f.revenue_ttm), "revenue_yoy": _value(f.revenue_yoy), "revenue_q_yoy": _value(f.revenue_q_yoy),
                "share_change_yoy": _value(f.share_change_yoy),
                "latest_periodic": None if latest is None else {
                    "form": latest["form"], "accession": latest["accession"], "filed": latest["filed"],
                    "period_end": latest.get("report_date"),
                },
            }
    finally:
        facts.close()
    return {
        "schema": SCHEMA, "as_of": snapshot.as_of, "snapshot_sha256": snapshot.sha256,
        "pool": [{key: e.get(key) for key in POOL_FIELDS} for e in snapshot.entries],
        "fundamentals": fundamentals,
    }


def write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    temporary.replace(path)
