"""实时层读研究层产物的唯一入口（只读）。

研究层每天/盘中增量跑一轮，落盘 <out_dir>/<as_of>/{latest.json, cycle-*.json, shortlist-*.json, hubinputs-*.json,
branches/<分支>/{receipt,verdicts}-*.json}。这里把它们读成一个 ResearchView：
  - receipts：五个分支的收据（快照 hash、参数版本、PASS/ABSTAIN/FAILED 计数）；
  - verdicts：分支 → 标的 → 精简结论（结论、分数、原文链接、原因、失效条件）；
  - ranks：分支 → 全池排名（「全池前 10%」按这个算，分母是该分支给出结论的全部标的）；
  - shortlist / pool / fundamentals：候选、候选池全表、营收同比与最新定期报告。
读不全、hash 对不上、快照过期都不在这里「修」，而是记进 problems，由中枢发布 SYSTEM_BLOCKED 并说人话原因。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import branch_notes
from .names import pretty_name

STOCK_BRANCHES = ("equity-event-atlas", "bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-foresight-signal")
ENVIRONMENT_BRANCH = "global-equity-lead-lag-atlas"
ALL_BRANCHES = STOCK_BRANCHES + (ENVIRONMENT_BRANCH,)
BRANCH_LABELS = {
    "equity-event-atlas": "事件航图",
    "bottleneck-serenity-skill": "瓶颈",
    "stock-commercial-opportunities": "商业机会",
    "equity-foresight-signal": "股势前瞻",
    "global-equity-lead-lag-atlas": "全球联动",
}
RANK_TOP_FRACTION = 0.10
FAILURE_FILE = "research-failure.json"      # 研究层拒绝产出快照（候选池缩水）时写在 out_dir 根目录的失败标记


@dataclass
class ResearchView:
    directory: Path
    as_of: str = ""
    snapshot_sha256: str = ""
    generated_at: Optional[datetime] = None
    checked_at: Optional[datetime] = None
    receipts: Dict[str, dict] = field(default_factory=dict)
    verdicts: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    ranks: Dict[str, dict] = field(default_factory=dict)
    shortlist: List[dict] = field(default_factory=list)
    pool: Dict[str, dict] = field(default_factory=dict)
    fundamentals: Dict[str, dict] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    notes: Dict[str, str] = field(default_factory=dict)          # 分支 -> 一句话说明（取自收据与逐股结论，见 branch_notes）
    universe_count: int = 0
    problems: List[str] = field(default_factory=list)

    @property
    def fresh_at(self) -> Optional[datetime]:
        """研究层「数据是当前的」这一结论最后成立的时刻：快照生成，或研究层最后一次确认快照仍是当前数据。"""
        points = [p for p in (self.generated_at, self.checked_at) if p is not None]
        return max(points) if points else None

    def age_hours(self, now: datetime) -> Optional[float]:
        fresh = self.fresh_at
        return None if fresh is None else (now - fresh).total_seconds() / 3600.0

    def verdict(self, branch_id: str, symbol: str) -> Optional[dict]:
        return self.verdicts.get(branch_id, {}).get(symbol)

    def branch_status(self, branch_id: str) -> str:
        return (self.receipts.get(branch_id) or {}).get("status", "MISSING")


def _parse(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _read(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def latest_day_dir(out_dir: Path) -> Optional[Path]:
    days = sorted(p for p in Path(out_dir).glob("*") if p.is_dir() and (p / "latest.json").is_file())
    return days[-1] if days else None


def _slim(record: Mapping) -> dict:
    evidence = record.get("evidence") or {}
    keep = {}
    for key in ("invalidation_risk", "invalidation_conditions", "hard_flags", "falsifiers", "maturity_code", "status",
               "insider_window", "positive_events"):
        if key in evidence:
            keep[key] = evidence[key]
    return {"verdict": record["verdict"], "label": record.get("label"), "score": record.get("score"),
            "rank_key": record.get("rank_key"), "reasons": list(record.get("reasons") or []),
            "links": [dict(x) for x in (record.get("links") or [])], "name": pretty_name(record.get("name")),
            "market_cap_usd": record.get("market_cap_usd"), "evidence": keep}


def _rank_table(records: Mapping[str, Mapping]) -> dict:
    """「全池前 10%」：分母 = 该分支给出结论的全部标的；k = ceil(10% × N)；分数不小于第 k 名（并列一并算入）。"""
    scored = sorted(((r.get("score") if isinstance(r.get("score"), (int, float)) and math.isfinite(r["score"]) else None, s)
                     for s, r in records.items()), key=lambda item: (-(item[0] if item[0] is not None else -1e18), item[1]))
    pool = len(scored)
    if pool == 0:
        return {"pool": 0, "k": 0, "cutoff": None, "rank": {}}
    k = max(1, math.ceil(RANK_TOP_FRACTION * pool))
    cutoff = scored[k - 1][0]
    rank: Dict[str, int] = {}
    previous_score, previous_rank = None, 0
    for position, (score, symbol) in enumerate(scored, 1):
        if score != previous_score:
            previous_rank, previous_score = position, score
        rank[symbol] = previous_rank
    return {"pool": pool, "k": k, "cutoff": cutoff, "rank": rank}


def load_research(out_dir: Path) -> ResearchView:
    view = ResearchView(directory=Path(out_dir))
    failure = Path(out_dir) / FAILURE_FILE
    if failure.is_file():
        try:
            count = int(_read(failure).get("count"))
        except (OSError, ValueError, TypeError, AttributeError):
            count = -1
        view.problems.append("UNIVERSE_INCOMPLETE:%s" % ("未知" if count < 0 else count))
    day = latest_day_dir(Path(out_dir))
    if day is None:
        view.problems.append("RESEARCH_MISSING:研究层还没有产出任何结果")
        return view
    try:
        latest = _read(day / "latest.json")
        cycle = _read(day / latest["cycle"])
        shortlist_doc = _read(day / latest["shortlist"])
    except (OSError, ValueError, KeyError) as exc:
        view.problems.append("RESEARCH_UNREADABLE:%s" % type(exc).__name__)
        return view
    view.as_of = latest.get("as_of") or cycle.get("as_of") or ""
    view.snapshot_sha256 = latest.get("snapshot_sha256") or ""
    view.generated_at = _parse(shortlist_doc.get("generated_at"))
    view.checked_at = _parse(latest.get("checked_at"))
    view.shortlist = [{**item, "name": pretty_name(item.get("name"))} for item in shortlist_doc.get("entries") or []]
    view.universe_count = int(cycle.get("universe_count") or 0)
    if shortlist_doc.get("snapshot_sha256") != view.snapshot_sha256:
        view.problems.append("SNAPSHOT_MISMATCH:shortlist 与 latest 指向的快照不是同一份")
    for receipt in cycle.get("receipts") or []:
        view.receipts[receipt["branch_id"]] = receipt
    for branch_id in ALL_BRANCHES:
        receipt = view.receipts.get(branch_id)
        if receipt is None:
            view.problems.append("BRANCH_RECEIPT_MISSING:%s" % branch_id)
            continue
        if receipt.get("snapshot_hash") != view.snapshot_sha256:
            view.problems.append("BRANCH_SNAPSHOT_MISMATCH:%s" % branch_id)
        if receipt.get("status") == "FAILED":
            view.problems.append("BRANCH_FAILED:%s:%s" % (branch_id, receipt.get("reason")))
        path = receipt.get("verdicts_file")
        candidate = Path(path) if path else None
        if candidate is not None and not candidate.is_file():
            # 产物目录被整体搬走时，收据里的绝对路径失效：按目录结构再找一次
            candidate = day / "branches" / branch_id / Path(path).name
        if candidate is None or not candidate.is_file():
            if receipt.get("status") != "FAILED":
                view.problems.append("VERDICTS_MISSING:%s" % branch_id)
            continue
        try:
            document = _read(candidate)
        except (OSError, ValueError):
            view.problems.append("VERDICTS_UNREADABLE:%s" % branch_id)
            continue
        records = {r["symbol"]: r for r in document.get("verdicts", [])}
        view.verdicts[branch_id] = {symbol: _slim(r) for symbol, r in records.items()}
        if branch_id in STOCK_BRANCHES:
            view.ranks[branch_id] = _rank_table(records)
        if branch_id == ENVIRONMENT_BRANCH:
            view.environment = dict(document.get("meta") or {})
        view.notes[branch_id] = branch_notes.describe(branch_id, receipt, view.verdicts[branch_id], document.get("meta") or {})
    hub_file = latest.get("hubinputs")
    if hub_file and (day / hub_file).is_file():
        try:
            inputs = _read(day / hub_file)
            if inputs.get("snapshot_sha256") == view.snapshot_sha256:
                view.pool = {row["symbol"]: {**row, "name": pretty_name(row.get("name"))} for row in inputs.get("pool", [])}
                view.fundamentals = dict(inputs.get("fundamentals") or {})
            else:
                view.problems.append("HUBINPUTS_MISMATCH:中枢输入与快照不是同一份")
        except (OSError, ValueError, KeyError):
            view.problems.append("HUBINPUTS_UNREADABLE")
    else:
        view.problems.append("HUBINPUTS_MISSING:研究产物里没有中枢输入文件（hubinputs）")
    return view
