"""事件航图分支（equity-event-atlas）：把 SEC 一手申报变成带状态机的事件，算历史基准概率，给出 PASS/ABSTAIN/FAILED。

数据流：events.sqlite（申报索引、Form 4 买入、submissions、股数）→ 事件（家族/状态/机制/三个时间）
        → 全池事件研究（20/60 日相对 IWM 超额收益的三分位概率）→ 逐公司结论。
所有入口都接收 as_of，只使用申报日 <= as_of 的申报（时点正确）。参数在
Stock_Skill/equity-event-atlas/runtime/params.json，不在代码里写死阈值。

只输出研究结论，不下单、不给仓位。verdict 含义：
  PASS     有正向事件（机会型内部人买入 / 13D）且没有近期稀释，且至少带一条 SEC 原文链接；
  FAILED   稀释失效条件已触发（近期增发/ATM/招股，或股数同比明显增加）；
  ABSTAIN  证据不足（没有正向事件，或只有信息性事件）。
近 90 天有 ATM/增发的，无论结论如何，一律带失效风险标记。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from ..evidence.eventstore import EventStore, iso
from ..evidence.factstore import filing_index_url
from ..evidence.history_prices import BENCHMARK, BarStore
from ..evidence.insiders import (OPPORTUNISTIC, ROUTINE, UNCLASSIFIABLE, classify_buy, collapse_joint_filers,
                                 opportunistic_summary)
from ..evidence.prospectus import ATM, EQUITY_OFFERING, OTHER, UNVERIFIED, document_url
from . import event_study
from .param_floors import enforce_not_looser

DEFAULT_PARAMS_PATH = (Path(__file__).resolve().parents[3] / "Stock_Skill" / "equity-event-atlas" / "runtime" / "params.json")
PARAMS_SCHEMA = "equity-event-atlas/params-v1"

# ---- 本体：事件家族 / 状态 / 机制（枚举取自 references/event_ontology.md）----------
INSIDER_OWNERSHIP = "INSIDER_OWNERSHIP"
FINANCING_DILUTION = "FINANCING_DILUTION"
EARNINGS_GUIDANCE = "EARNINGS_GUIDANCE"
PRODUCT_OPERATIONAL = "PRODUCT_OPERATIONAL"

KIND_SPEC: Dict[str, tuple] = {
    # kind: (家族, 状态, 机制, 先验方向——只是事件性质的标注，不是预测)
    "INSIDER_BUY_OPPORTUNISTIC": (INSIDER_OWNERSHIP, "COMPLETED", ("EXPECTATIONS", "DEMAND"), "POSITIVE"),
    "INSIDER_BUY_ROUTINE": (INSIDER_OWNERSHIP, "COMPLETED", ("DEMAND",), "NEUTRAL"),
    "INSIDER_BUY_UNCLASSIFIABLE": (INSIDER_OWNERSHIP, "COMPLETED", ("DEMAND",), "NEUTRAL"),
    "INSIDER_CLUSTER": (INSIDER_OWNERSHIP, "COMPLETED", ("EXPECTATIONS", "DEMAND"), "POSITIVE"),
    "ACTIVIST_13D": (INSIDER_OWNERSHIP, "CONFIRMED", ("DEMAND", "POSITIONING"), "POSITIVE"),
    "DILUTION_SHELF": (FINANCING_DILUTION, "CONDITIONAL", ("SUPPLY",), "NEGATIVE"),
    "DILUTION_S1": (FINANCING_DILUTION, "CONDITIONAL", ("SUPPLY",), "NEGATIVE"),
    "DILUTION_OFFERING": (FINANCING_DILUTION, "CONFIRMED", ("SUPPLY",), "NEGATIVE"),
    "DILUTION_ATM": (FINANCING_DILUTION, "CONFIRMED", ("SUPPLY", "LIQUIDITY"), "NEGATIVE"),
    "SHARE_COUNT_GROWTH": (FINANCING_DILUTION, "COMPLETED", ("SUPPLY",), "NEGATIVE"),
    "SHARE_COUNT_JUMP_UNEXPLAINED": (FINANCING_DILUTION, "UNKNOWN", ("SUPPLY",), "NEUTRAL"),
    "PROSPECTUS_OTHER": (FINANCING_DILUTION, "CONFIRMED", ("SUPPLY",), "NEUTRAL"),
    "MATERIAL_AGREEMENT": (PRODUCT_OPERATIONAL, "CONFIRMED", ("FUNDAMENTALS",), "NEUTRAL"),
    "EARNINGS_RESULTS": (EARNINGS_GUIDANCE, "COMPLETED", ("FUNDAMENTALS", "EXPECTATIONS"), "NEUTRAL"),
    "EXEC_CHANGE": (PRODUCT_OPERATIONAL, "CONFIRMED", ("FUNDAMENTALS",), "NEUTRAL"),
}
OFFERING_KINDS = {"DILUTION_OFFERING", "DILUTION_ATM", "DILUTION_S1"}
DILUTION_RISK_KINDS = OFFERING_KINDS | {"DILUTION_SHELF"}
_SENIOR = re.compile(r"chief executive|\bceo\b|chief financial|\bcfo\b|president|chair", re.I)


# ---- 参数 -------------------------------------------------------------------
class ParamsError(ValueError):
    pass


# 远端参数只许收紧、不许放宽：下面是仓库内 Stock_Skill/equity-event-atlas/runtime/params.json 的门槛（写死在代码里，
# 远端文件改不了它；tests 里有一条核对它与仓库参数文件一致）。
FLOORS = {
    "insider.min_purchase_usd": ("min", 25000), "insider.pass_min_opportunistic_insiders": ("min", 1),
    "insider.pass_min_total_usd": ("min", 25000), "insider.cluster_min_insiders": ("min", 2),
    "insider.offering_like_min_buyers": ("max", 4),       # 同日买家 >= 这个数按增发参与处理：数越小越严
    "insider.window_days": ("max", 90),                    # 买入落在窗口内才算正向事件：窗口越短越严
    "dilution.lookback_days": ("min", 90),                 # 增发回看越长越严
    "dilution.share_growth_yoy_threshold": ("max", 0.10),  # 股数同比阈值越低越严
    "study.min_sample": ("min", 30), "study.entry_lag_trading_days": ("min", 1),
    "verdict.positive_kinds": ("subset", ["INSIDER_BUY_OPPORTUNISTIC"]),
}


def validate_params(params: Mapping) -> Mapping:
    """简单 schema 校验：必需字段、类型、取值范围，再核对关键门槛不比仓库默认宽松。不合格就抛 ParamsError，调用方沿用上一份好参数。"""
    def need(block: Mapping, key: str, kind, where: str):
        if key not in block or not isinstance(block[key], kind) or isinstance(block[key], bool) and kind is not bool:
            raise ParamsError("%s.%s 缺失或类型不对" % (where, key))
        return block[key]

    if params.get("schema") != PARAMS_SCHEMA:
        raise ParamsError("schema 必须是 %s" % PARAMS_SCHEMA)
    if params.get("skill_id") != "equity-event-atlas":
        raise ParamsError("skill_id 不匹配")
    need(params, "params_version", str, "root")
    for section in ("insider", "dilution", "filings", "study", "verdict"):
        need(params, section, dict, "root")
    insider, dilution, filings, study, verdict = (params[k] for k in ("insider", "dilution", "filings", "study", "verdict"))
    if need(insider, "min_purchase_usd", (int, float), "insider") < 0:
        raise ParamsError("insider.min_purchase_usd 不能为负")
    if not 1 <= need(insider, "window_days", int, "insider") <= 365:
        raise ParamsError("insider.window_days 需在 1..365")
    if need(insider, "routine_history_years", int, "insider") != 3:
        raise ParamsError("insider.routine_history_years 目前只支持 3（Cohen-Malloy-Pomorski 定义）")
    for key in ("pass_min_opportunistic_insiders", "cluster_min_insiders"):
        if need(insider, key, int, "insider") < 1:
            raise ParamsError("insider.%s 需 >= 1" % key)
    need(insider, "pass_min_total_usd", (int, float), "insider")
    if need(insider, "offering_like_min_buyers", int, "insider") < 2:
        raise ParamsError("insider.offering_like_min_buyers 需 >= 2")
    if not 1 <= need(dilution, "lookback_days", int, "dilution") <= 365:
        raise ParamsError("dilution.lookback_days 需在 1..365")
    for key in ("offering_forms", "shelf_forms", "atm_terms"):
        if not need(dilution, key, list, "dilution") or not all(isinstance(x, str) for x in dilution[key]):
            raise ParamsError("dilution.%s 需为非空字符串列表" % key)
    growth = need(dilution, "share_growth_yoy_threshold", (int, float), "dilution")
    cap = need(dilution, "share_growth_split_cap", (int, float), "dilution")
    if not 0 < growth < cap:
        raise ParamsError("dilution 股数同比阈值需满足 0 < 阈值 < 拆股上限")
    if not need(filings, "eight_k_items", dict, "filings") or not need(filings, "activist_forms", list, "filings"):
        raise ParamsError("filings 配置为空")
    horizons = need(study, "horizons_trading_days", list, "study")
    if not horizons or not all(isinstance(h, int) and 1 <= h <= 250 for h in horizons):
        raise ParamsError("study.horizons_trading_days 需为 1..250 的整数列表")
    if need(study, "min_sample", int, "study") < 2:
        raise ParamsError("study.min_sample 需 >= 2")
    if not (study["min_sample"] <= need(study, "medium_confidence_sample", int, "study")
            <= need(study, "high_confidence_sample", int, "study")):
        raise ParamsError("study 样本阈值需满足 min <= medium <= high")
    if not 0.5 < need(study, "interval_confidence", (int, float), "study") < 1:
        raise ParamsError("study.interval_confidence 需在 (0.5, 1)")
    for key in ("entry_lag_trading_days", "dedupe_trading_days", "control_samples", "control_seed"):
        if need(study, key, int, "study") < 0:
            raise ParamsError("study.%s 不能为负" % key)
    if study["entry_lag_trading_days"] < 1:
        raise ParamsError("study.entry_lag_trading_days 需 >= 1（不能用申报当日收盘价入场）")
    unknown = set(need(verdict, "positive_kinds", list, "verdict")) - set(KIND_SPEC)
    if unknown:
        raise ParamsError("verdict.positive_kinds 含未知事件类：%s" % sorted(unknown))
    need(verdict, "score", dict, "verdict")
    if need(verdict, "top_n", int, "verdict") < 1:
        raise ParamsError("verdict.top_n 需 >= 1")
    enforce_not_looser(params, FLOORS, ParamsError, "equity-event-atlas")
    return params


def load_params(path: Optional[Path] = None) -> Mapping:
    target = Path(path) if path is not None else DEFAULT_PARAMS_PATH
    try:
        payload = json.loads(target.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ParamsError("参数文件读不了：%s" % exc) from exc
    return validate_params(payload)


# ---- 事件 -------------------------------------------------------------------
@dataclass(frozen=True)
class Event:
    event_id: str
    cik: int
    symbol: str
    family: str
    kind: str
    state: str
    mechanisms: tuple
    direction_prior: str
    published_at: str            # 公开时刻：EDGAR 受理时刻，缺则用申报日
    observed_at: str             # 回放口径 = 公开时刻；实时运行由采集时钟覆盖
    effective_at: Optional[str]  # 事件发生/生效日
    published_date: str          # 申报日，时点闸门用它
    accession: str
    source_url: str              # SEC 真实页面（申报索引页）
    summary: str
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        record = asdict(self)
        record["mechanisms"] = list(self.mechanisms)
        return record


def _event(kind: str, entry: Mapping, accession: str, published_date: str, published_at: Optional[str],
           effective_at: Optional[str], summary: str, details: dict, suffix: str = "") -> Event:
    family, state, mechanisms, prior = KIND_SPEC[kind]
    published = published_at or published_date
    return Event(
        event_id="%s:%s%s" % (kind, accession, suffix), cik=int(entry["cik"]), symbol=entry["symbol"], family=family,
        kind=kind, state=state, mechanisms=mechanisms, direction_prior=prior, published_at=published,
        observed_at=published, effective_at=effective_at, published_date=published_date, accession=accession,
        source_url=filing_index_url(int(entry["cik"]), accession), summary=summary, details=details)


def _usd(value: float) -> str:
    return "$%.2fM" % (value / 1e6) if value >= 1e6 else "$%.0fK" % (value / 1e3)


def insider_events(store: EventStore, entries: Mapping[int, Mapping], as_of, params: Mapping, since=None) -> List[Event]:
    min_usd = float(params["insider"]["min_purchase_usd"])
    window = int(params["insider"]["window_days"])
    cluster_min = int(params["insider"]["cluster_min_insiders"])
    offering_like = store.offering_like_accessions(as_of, int(params["insider"]["offering_like_min_buyers"]))
    events: List[Event] = []
    opportunistic_by_issuer: Dict[int, List[Event]] = defaultdict(list)
    for row in collapse_joint_filers(store.all_buys_as_of(as_of, since)):
        entry = entries.get(row["issuer_cik"])
        if entry is None or row["plan_10b5_1"] or row["amount_usd"] < min_usd or row["accession"] in offering_like:
            continue
        # 例行/机会型按「这份申报公开那天」能看到的历史判定，不用后来才知道的信息
        label = classify_buy(store, row["owner_cik"], row["first_trade"], row["filed"])
        kind = {OPPORTUNISTIC: "INSIDER_BUY_OPPORTUNISTIC", ROUTINE: "INSIDER_BUY_ROUTINE",
                UNCLASSIFIABLE: "INSIDER_BUY_UNCLASSIFIABLE"}[label]
        text = {"INSIDER_BUY_OPPORTUNISTIC": "机会型", "INSIDER_BUY_ROUTINE": "例行型（过去3年每年同月都买）",
                "INSIDER_BUY_UNCLASSIFIABLE": "历史不足3年、无法分类"}[kind]
        event = _event(kind, entry, row["accession"], row["filed"], row["accepted_at"], row["first_trade"],
                       "%s（%s）公开市场买入 %s，均价约 $%.2f，%s" % (
                           row["owner_name"], row["role"], _usd(row["amount_usd"]),
                           row["amount_usd"] / row["shares"] if row["shares"] else 0.0, text),
                       {"owner_cik": row["owner_cik"], "owner_name": row["owner_name"], "role": row["role"],
                        "shares": row["shares"], "amount_usd": row["amount_usd"], "first_trade": row["first_trade"],
                        "last_trade": row["last_trade"], "classification": label, "indirect": bool(row["indirect"])},
                       suffix=":%d" % row["owner_cik"])
        events.append(event)
        if kind == "INSIDER_BUY_OPPORTUNISTIC":
            opportunistic_by_issuer[row["issuer_cik"]].append(event)
    # 集群：90 天内 >= cluster_min 位不同的机会型内部人，在凑够那份申报公开时记一条
    for cik, items in opportunistic_by_issuer.items():
        items.sort(key=lambda e: (e.published_date, e.event_id))
        last_cluster: Optional[str] = None
        for index, event in enumerate(items):
            floor = (date.fromisoformat(event.published_date) - timedelta(days=window)).isoformat()
            recent = [e for e in items[:index + 1] if e.published_date >= floor]
            owners = {e.details["owner_cik"] for e in recent}
            if len(owners) >= cluster_min and (last_cluster is None or last_cluster < floor):
                total = {}
                for e in recent:
                    total[e.accession] = max(total.get(e.accession, 0.0), e.details["amount_usd"])
                last_cluster = event.published_date
                events.append(_event(
                    "INSIDER_CLUSTER", entries[cik], event.accession, event.published_date, event.published_at,
                    event.effective_at, "%d 天内 %d 位机会型内部人先后买入，合计 %s" % (window, len(owners), _usd(sum(total.values()))),
                    {"insiders": len(owners), "amount_usd": sum(total.values()), "accessions": sorted(total)},
                    suffix=":cluster"))
    return events


def dilution_events(store: EventStore, entries: Mapping[int, Mapping], as_of, params: Mapping, since=None) -> List[Event]:
    cfg = params["dilution"]
    events: List[Event] = []
    forms = list(cfg["shelf_forms"]) + list(cfg["offering_forms"])
    meta = {r["accession"]: dict(r) for r in store.db.execute("SELECT * FROM filing_meta WHERE form IN (%s)" % ",".join("?" * len(forms)), forms)}
    labels = {r[0]: r[1] for r in store.db.execute("SELECT accession, label FROM prospectus_class")}
    for row in store.filings_as_of(forms, as_of, since):
        entry = entries.get(row["cik"])
        if entry is None:
            continue
        accession, filed, form = row["accession"], row["filed"], row["form"]
        details = {"form": form}
        primary = (meta.get(accession) or {}).get("primary_document")
        if primary:
            details["document_url"] = document_url(row["cik"], accession, primary)
        if form in cfg["shelf_forms"]:
            kind, text = "DILUTION_SHELF", "%s 货架注册：登记了未来可增发的额度，尚未证明已发行" % form
        elif form == "S-1":
            kind, text = "DILUTION_S1", "S-1 注册声明：拟发行股票，需 SEC 宣布生效后才能发售"
        else:  # 424B5
            label = labels.get(accession, UNVERIFIED)
            details["prospectus_label"] = label
            if label == ATM:
                kind, text = "DILUTION_ATM", "424B5：ATM（按市价分批增发）项目，可随时向市场卖新股"
            elif label == OTHER:
                kind, text = "PROSPECTUS_OTHER", "424B5：债券等其他发行，非普通股增发"
            else:
                kind = "DILUTION_OFFERING"
                text = "424B5：普通股增发招股说明书补充" + ("（正文未能核实类型，按增发保守处理）" if label == UNVERIFIED else "")
        events.append(_event(kind, entry, accession, filed, (meta.get(accession) or {}).get("accepted_at"),
                             filed, text, details))
    # 股数同比：封面流通股 vs 约一年前的封面流通股
    growth_cap = float(cfg["share_growth_split_cap"])
    threshold = float(cfg["share_growth_yoy_threshold"])
    filed_of = {r["accession"]: r["filed"] for r in store.db.execute(
        "SELECT accession, filed FROM filings WHERE form IN ('10-K','10-Q') UNION SELECT accession, filed FROM filing_meta WHERE form IN ('10-K','10-Q')")}
    by_cik: Dict[int, list] = defaultdict(list)
    for r in store.db.execute("SELECT cik, cover_end, shares, accession FROM shares_obs ORDER BY cik, cover_end"):
        by_cik[r["cik"]].append(r)
    for cik, observations in by_cik.items():
        entry = entries.get(cik)
        if entry is None:
            continue
        for current in observations:
            published = filed_of.get(current["accession"])
            if published is None or published > iso(as_of) or (since is not None and published < iso(since)):
                continue
            target = date.fromisoformat(current["cover_end"]) - timedelta(days=365)
            prior = min((o for o in observations if o is not current and abs((date.fromisoformat(o["cover_end"]) - target).days) <= 45),
                        key=lambda o: abs((date.fromisoformat(o["cover_end"]) - target).days), default=None)
            if prior is None or prior["shares"] <= 0:
                continue
            growth = current["shares"] / prior["shares"] - 1
            if growth < threshold:
                continue
            kind = "SHARE_COUNT_JUMP_UNEXPLAINED" if growth > growth_cap else "SHARE_COUNT_GROWTH"
            text = ("封面流通股同比 %+.1f%%（%.1f 百万 → %.1f 百万）" % (growth * 100, prior["shares"] / 1e6, current["shares"] / 1e6)
                    + ("；涨幅过大，可能是拆股/并购，不计入稀释" if kind == "SHARE_COUNT_JUMP_UNEXPLAINED" else ""))
            events.append(_event(kind, entry, current["accession"], published, None, current["cover_end"], text,
                                 {"growth_yoy": growth, "shares": current["shares"], "prior_shares": prior["shares"],
                                  "prior_cover_end": prior["cover_end"]}))
    return events


def filing_events(store: EventStore, entries: Mapping[int, Mapping], as_of, params: Mapping, since=None) -> List[Event]:
    items_cfg: Mapping[str, str] = params["filings"]["eight_k_items"]
    events: List[Event] = []
    sql = "SELECT * FROM filing_meta WHERE form = '8-K' AND filed <= ? AND items IS NOT NULL"
    args: list = [iso(as_of)]
    if since is not None:
        sql += " AND filed >= ?"
        args.append(iso(since))
    for row in store.db.execute(sql, args):
        entry = entries.get(row["cik"])
        if entry is None:
            continue
        present = [i.strip() for i in row["items"].split(",")]
        for item, kind in items_cfg.items():
            if item not in present:
                continue
            label = {"MATERIAL_AGREEMENT": "8-K Item 1.01 重大合同", "EARNINGS_RESULTS": "8-K Item 2.02 业绩公告",
                     "EXEC_CHANGE": "8-K Item 5.02 董事/高管变动"}[kind]
            details = {"items": present, "report_date": row["report_date"]}
            if row["primary_document"]:
                details["document_url"] = document_url(row["cik"], row["accession"], row["primary_document"])
            events.append(_event(kind, entry, row["accession"], row["filed"], row["accepted_at"],
                                 row["report_date"] or row["filed"], label, details))
    for row in store.filings_as_of(list(params["filings"]["activist_forms"]), as_of, since):
        entry = entries.get(row["cik"])
        if entry is not None:
            events.append(_event("ACTIVIST_13D", entry, row["accession"], row["filed"], None, row["filed"],
                                 "Schedule 13D：持股超 5% 且披露了投资意图（未区分激进/控股/被动转入）", {"form": row["form"]}))
    return events


def build_events(store: EventStore, entries: Sequence[Mapping], as_of, params: Mapping, since=None) -> List[Event]:
    by_cik = {int(e["cik"]): e for e in entries}
    events = (insider_events(store, by_cik, as_of, params, since) + dilution_events(store, by_cik, as_of, params, since)
              + filing_events(store, by_cik, as_of, params, since))
    return sorted(events, key=lambda e: (e.published_date, e.event_id))


# ---- 逐公司结论 -----------------------------------------------------------------
def _horizon_summary(stats: Optional[Mapping]) -> dict:
    if not stats:
        return {"status": event_study.INSUFFICIENT, "note": "该类事件在研究窗口内没有样本"}
    return {"n_events": stats["n_events"], "n_after_dedupe": stats["n_after_dedupe"], "horizons": stats["horizons"]}


def evaluate_company(entry: Mapping, events: Sequence[Event], store: EventStore, as_of, params: Mapping,
                     study_stats: Mapping[str, dict]) -> dict:
    cfg_i, cfg_d, cfg_v = params["insider"], params["dilution"], params["verdict"]
    as_of_text = iso(as_of)
    lookback = (date.fromisoformat(as_of_text) - timedelta(days=int(cfg_d["lookback_days"]))).isoformat()
    summary = opportunistic_summary(store, int(entry["cik"]), as_of, int(cfg_i["window_days"]),
                                    float(entry["market_cap_usd"]), float(cfg_i["min_purchase_usd"]),
                                    int(cfg_i["offering_like_min_buyers"]))
    recent = [e for e in events if e.published_date >= lookback]
    offerings = [e for e in recent if e.kind in OFFERING_KINDS]
    shelves = [e for e in recent if e.kind == "DILUTION_SHELF"]
    growth = [e for e in events if e.kind == "SHARE_COUNT_GROWTH"]
    latest_growth = max(growth, key=lambda e: e.published_date, default=None)
    share_growth_active = latest_growth is not None and latest_growth.published_date >= (
        date.fromisoformat(as_of_text) - timedelta(days=200)).isoformat()
    positives: List[Event] = []
    opp_events = [e for e in recent if e.kind == "INSIDER_BUY_OPPORTUNISTIC"]
    opp_total = summary["opportunistic_amount_usd"]
    if ("INSIDER_BUY_OPPORTUNISTIC" in cfg_v["positive_kinds"] and summary["opportunistic_insiders"] >= int(cfg_i["pass_min_opportunistic_insiders"])
            and opp_total >= float(cfg_i["pass_min_total_usd"])):
        positives += opp_events
    if "ACTIVIST_13D" in cfg_v["positive_kinds"]:
        positives += [e for e in recent if e.kind == "ACTIVIST_13D"]
    dilution_flags = sorted({e.kind for e in offerings} | ({"SHARE_COUNT_GROWTH"} if share_growth_active else set()))
    risk_flags = sorted({e.kind for e in offerings + shelves} | ({"SHARE_COUNT_GROWTH"} if share_growth_active else set()))
    evidence = [{"kind": e.kind, "url": e.source_url, "published_date": e.published_date, "summary": e.summary}
                for e in positives]
    if offerings or share_growth_active:
        verdict = "FAILED"
        reason = "稀释失效条件已触发：" + "、".join(
            [e.summary for e in offerings[:2]] + ([latest_growth.summary] if share_growth_active else []))
        if positives:
            reason = "有正向事件但被稀释否决。" + reason
        evidence += [{"kind": e.kind, "url": e.source_url, "published_date": e.published_date, "summary": e.summary}
                     for e in offerings[:3]] + ([{"kind": latest_growth.kind, "url": latest_growth.source_url,
                                                  "published_date": latest_growth.published_date, "summary": latest_growth.summary}]
                                               if share_growth_active else [])
    elif positives and evidence:
        verdict, reason = "PASS", "有正向事件且近 %d 天无增发/ATM/招股" % int(cfg_d["lookback_days"])
    else:
        verdict, reason = "ABSTAIN", "近 %d 天没有满足门槛的正向事件" % int(cfg_i["window_days"])
    senior = any(_SENIOR.search(b["role"] or "") for b in summary["buys"])
    score_cfg = cfg_v["score"]
    bps = (summary["pct_of_market_cap"] or 0) * 1e4
    score = 0.0
    if verdict == "PASS":
        score = (score_cfg["per_insider"] * min(summary["opportunistic_insiders"], score_cfg["max_insiders"])
                 + min(bps, score_cfg["bps_of_cap_cap"]) + (score_cfg["senior_buyer_bonus"] if senior else 0)
                 + (score_cfg["activist_bonus"] if any(e.kind == "ACTIVIST_13D" for e in positives) else 0))
    return {
        "symbol": entry["symbol"], "cik": int(entry["cik"]), "name": entry["name"],
        "market_cap_usd": entry["market_cap_usd"], "verdict": verdict, "reason": reason,
        "score": round(score, 2), "invalidation_risk": risk_flags,
        "invalidation_conditions": ["近 %d 天内出现 424B5/S-1（含 ATM）增发或招股" % int(cfg_d["lookback_days"]),
                                    "封面流通股同比增幅 >= %.0f%%" % (float(cfg_d["share_growth_yoy_threshold"]) * 100)],
        "insider_window": {k: summary[k] for k in ("window_days", "opportunistic_insiders", "opportunistic_amount_usd",
                                                    "pct_of_market_cap", "counts", "excluded")},
        "evidence": evidence,
        "events_recent": [{"kind": e.kind, "state": e.state, "published_date": e.published_date, "url": e.source_url}
                          for e in recent if e.kind not in ("INSIDER_BUY_ROUTINE",)][:12],
        "baseline": {kind: _horizon_summary(study_stats.get(kind)) for kind in sorted({e.kind for e in positives})},
    }


# ---- 全流程 ---------------------------------------------------------------------
def _load_bars(bar_store: BarStore, symbols: Iterable[str]) -> Dict[str, event_study.Bars]:
    result = {}
    for symbol in symbols:
        rows = bar_store.load(symbol)
        if rows:
            result[symbol] = ([r[0] for r in rows], [float(r[1]) for r in rows])
    return result


def run(store: EventStore, entries: Sequence[Mapping], bar_store: BarStore, as_of, params: Mapping,
        event_start: str) -> dict:
    as_of_text = iso(as_of)
    events = build_events(store, entries, as_of_text, params, since=event_start)
    symbols = [e["symbol"] for e in entries]
    bars = _load_bars(bar_store, symbols)
    benchmark = _load_bars(bar_store, [BENCHMARK[0]]).get(BENCHMARK[0])
    study_stats: Dict[str, dict] = {}
    if benchmark is not None:
        rows = [{"event_id": e.event_id, "cik": e.cik, "symbol": e.symbol, "kind": e.kind,
                 "published_date": e.published_date} for e in events]
        study_stats = event_study.study(rows, bars, benchmark, params, (event_start, as_of_text))
    by_cik: Dict[int, List[Event]] = defaultdict(list)
    for event in events:
        by_cik[event.cik].append(event)
    verdicts = [evaluate_company(e, by_cik.get(int(e["cik"]), []), store, as_of_text, params, study_stats) for e in entries]
    return {"as_of": as_of_text, "event_start": event_start, "params_version": params["params_version"],
            "events": events, "study": study_stats, "verdicts": verdicts,
            "benchmark_available": benchmark is not None, "bars_loaded": len(bars)}


def counts_by_family(events: Iterable[Event], since: str) -> dict:
    family_counts: Counter = Counter()
    kind_counts: Counter = Counter()
    for event in events:
        if event.published_date >= since:
            family_counts[event.family] += 1
            kind_counts[event.kind] += 1
    return {"by_family": dict(sorted(family_counts.items())), "by_kind": dict(sorted(kind_counts.items()))}


def main(argv: Optional[Sequence[str]] = None) -> int:
    from ..evidence.event_collect import load_pool

    parser = argparse.ArgumentParser(prog="signal_lattice.branches.event_atlas")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--event-start", default="2024-10-01")
    parser.add_argument("--max-cap", type=float, default=5e9)
    parser.add_argument("--params", type=Path, default=None)
    parser.add_argument("--db", default="events.sqlite")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    params = load_params(args.params)
    entries, _meta = load_pool(args.universe, max_cap_usd=args.max_cap)
    store = EventStore(args.run_dir / args.db)
    result = run(store, entries, BarStore(args.run_dir / "ev-bars"), args.as_of, params, args.event_start)
    out = args.out or (args.run_dir / ("event-atlas-%s.json" % args.as_of))
    payload = {**result, "events": [e.as_dict() for e in result["events"]]}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
