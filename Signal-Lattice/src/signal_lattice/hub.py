"""中枢：把四个选股分支各自的结论汇成「唯一建议 / NO_ACTION / SYSTEM_BLOCKED」。

这个模块只做确定性的规则计算，不联网、不读文件、不落盘：输入是研究层产物（ResearchView）、
实时层的行情状态、前向记分簿给出的分支命中率、上一轮的失效条件状态；输出是决策、候选比较表和新的状态。
回测（backtest/hub_backtest.py）调用的是同一批函数，所以「回测复现的规则」和「线上跑的规则」是同一份代码。

规则（Owner 已定，不因结果难看而改动）
------------------------------------
候选   = 研究层 shortlist（<= 60 只）。
硬门   = ① 在候选池内；② 实时报价按交易时间口径新鲜；③ 流动性（价格、20 日成交额中位数、市值上限）；
         ④ 没有生效的失效条件（事件航图 FAILED：近 90 天增发/ATM 或股数大增；内部人净卖出；瓶颈 kill switch；
         以及此前发布过、之后已失效的建议）。④ 是一票否决，列入「冲突」。
支持度 = 每个选股分支对该股：PASS = 1.0；未 PASS 但该分支分数在全池前 10%（且不是 FAILED）= 0.3（排序支持）；否则 0。
         没有 SEC 一手原文链接的论点不计分。
独立性 = 两个分支若引用的申报（accession）全部落在已计分分支引用过的申报里，只算一次。
权重   = 前向记分簿里该分支已结算建议的命中率；该分支已结算样本 < 8 用等权（1.0）。
         权重只会把支持度往下调（上限 1.0），不会让门槛变低。
发布   = 加权支持度合计 >= 1.3（至少一个分支 PASS 且至少另一个独立分支排序支持）且全部硬门通过；取合计最高者，
         平局按支持它的事件的新近程度。否则 NO_ACTION，并给观察名单前 5。
阻断   = 研究快照过期（> 36 小时没确认）、分支收据不全或有分支运行失败、行情源全断 -> SYSTEM_BLOCKED。
动作只写「研究跟进（看多）」，不写「买入」；系统不下单。
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .research_view import BRANCH_LABELS, ENVIRONMENT_BRANCH, STOCK_BRANCHES, ResearchView

# ---- 常量（Owner 定的门槛，不许为了凑出建议而改） -------------------------------------------
SUPPORT_PASS = 1.0
SUPPORT_RANK = 0.3
PUBLISH_THRESHOLD = 1.3
WEIGHT_MIN_SAMPLES = 8
WEIGHT_NEUTRAL_HIT_RATE = 0.5
RESEARCH_MAX_AGE_HOURS = 36.0
WATCHLIST_SIZE = 5
MIN_PRICE_USD = 3.0
MIN_MEDIAN_DOLLAR_VOLUME_USD = 3_000_000.0
MAX_MARKET_CAP_USD = 5_000_000_000.0
PUBLISHED_TTL_DAYS = 60

ACTION_FOLLOW = "研究跟进（看多）"
# 展示层按这个机器码上色；颜色只绑机器码，不绑中文文案（改文案不会让颜色静默失效）。
ACTION_CODES: Dict[str, str] = {
    "RECOMMENDATION": "RESEARCH_FOLLOW_LONG",
    "NO_ACTION": "NO_ACTION",
    "SYSTEM_BLOCKED": "SYSTEM_BLOCKED",
}

WEIGHT_FORMULA = ("权重(分支) = 1.0，若该分支已结算的建议样本 < %d；否则 min(1.0, 命中率 / %.1f)。"
                  "命中率 = 已结算 20 日建议里相对 IWM 超额 > 0 的占比；只统计该分支给出支持的建议。"
                  "权重上限 1.0：权重只会抬高门槛，不会降低门槛。" % (WEIGHT_MIN_SAMPLES, WEIGHT_NEUTRAL_HIT_RATE))
SUPPORT_RULE = ("支持度：分支 PASS = %.1f；未 PASS 但分数进入全池前 10%% 且不是 FAILED = %.1f（排序支持）；其余 0。"
                "合计 >= %.1f（至少一个 PASS + 至少一个独立分支的排序支持）且硬门全过才发布。" % (SUPPORT_PASS, SUPPORT_RANK, PUBLISH_THRESHOLD))

_ACCESSION_URL = re.compile(r"/data/\d+/(\d{18})(?:/|$)")
_ACCESSION_DASHED = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def resolve_action_code(state: str) -> str:
    try:
        return ACTION_CODES[state]
    except KeyError:
        raise ValueError("UNKNOWN_DECISION_STATE:%s" % state) from None


# ---- 原文链接与证据根 ---------------------------------------------------------------------
def is_sec_link(link: Mapping) -> bool:
    url = link.get("url") or ""
    return url.startswith("https://www.sec.gov/") or url.startswith("https://data.sec.gov/")


def accession_of(link: Mapping) -> Optional[str]:
    accession = link.get("accession")
    if isinstance(accession, str) and _ACCESSION_DASHED.match(accession):
        return accession
    matched = _ACCESSION_URL.search(link.get("url") or "")
    if matched:
        digits = matched.group(1)
        return "%s-%s-%s" % (digits[:10], digits[10:12], digits[12:])
    return None


def evidence_roots(links: Sequence[Mapping]) -> Tuple[List[dict], List[str]]:
    """一个分支论点的一手原文与「证据根」（accession 集合）。

    只用来说明「新鲜度」的申报（supports == freshness）不算证据根，除非该分支只有这一条链接。
    """
    sec = [dict(x) for x in links if is_sec_link(x)]
    evidential = [x for x in sec if x.get("supports") != "freshness"] or sec
    roots = sorted({a for a in (accession_of(x) for x in evidential) if a})
    if not roots:                                   # 链接指向的不是申报页：用 URL 自身当根，仍能去重
        roots = sorted({x["url"] for x in evidential})
    return sec, roots


def _latest_date(links: Sequence[Mapping]) -> str:
    return max((str(x.get("published_date") or x.get("filed") or "") for x in links), default="")


# ---- 分支权重 ---------------------------------------------------------------------------
def branch_weights(stats: Optional[Mapping[str, Mapping[str, Any]]] = None) -> dict:
    """stats: {分支: {"n": 已结算样本数, "hits": 命中数}}（来自前向记分簿）。"""
    stats = stats or {}
    branches: Dict[str, dict] = {}
    for branch in STOCK_BRANCHES:
        item = stats.get(branch) or {}
        n, hits = int(item.get("n") or 0), int(item.get("hits") or 0)
        if n < WEIGHT_MIN_SAMPLES:
            branches[branch] = {"weight": 1.0, "mode": "EQUAL_COLD_START", "settled_samples": n,
                                "note": "已结算样本 %d < %d，等权" % (n, WEIGHT_MIN_SAMPLES)}
        else:
            rate = hits / n
            branches[branch] = {"weight": round(min(1.0, rate / WEIGHT_NEUTRAL_HIT_RATE), 6), "mode": "HIT_RATE",
                                "settled_samples": n, "hit_rate": round(rate, 6),
                                "note": "命中率 %.1f%%（%d/%d）" % (rate * 100, hits, n)}
    modes = {b["mode"] for b in branches.values()}
    return {"mode": "COLD_START_EQUAL" if modes == {"EQUAL_COLD_START"} else "HIT_RATE_WEIGHTED",
            "min_samples": WEIGHT_MIN_SAMPLES, "formula": WEIGHT_FORMULA, "branches": branches}


# ---- 支持度 -----------------------------------------------------------------------------
def _score(record: Mapping) -> Optional[float]:
    value = record.get("score")
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _rank_percentile(research: ResearchView, branch: str, symbol: str) -> Optional[float]:
    table = research.ranks.get(branch) or {}
    rank = (table.get("rank") or {}).get(symbol)
    pool = table.get("pool") or 0
    return None if rank is None or not pool else 1.0 - (rank - 1) / pool


def branch_support(research: ResearchView, branch: str, symbol: str) -> dict:
    """一个分支对一只股的原始支持：PASS 1.0 / 排序支持 0.3 / 0，附一句话理由与原文。"""
    label = BRANCH_LABELS[branch]
    status = research.branch_status(branch)
    record = research.verdict(branch, symbol)
    item: Dict[str, Any] = {"branch_id": branch, "label": label, "kind": "NONE", "raw": 0.0, "score": None, "rank": None,
                            "verdict": None, "sentence": "", "links": [], "roots": []}
    if record is not None:
        item["verdict"], item["score"] = record["verdict"], _score(record)
        item["rank"] = ((research.ranks.get(branch) or {}).get("rank") or {}).get(symbol)
    if status != "PASS":
        item["sentence"] = "%s：分支整体未出结论（%s），不给支持" % (label, (research.receipts.get(branch) or {}).get("reason") or status)
        return item
    if record is None:
        item["sentence"] = "%s：本轮没有这只股的结论" % label
        return item
    table = research.ranks.get(branch) or {}
    if record["verdict"] == "PASS":
        item["kind"], item["raw"] = "PASS", SUPPORT_PASS
        headline = (record["links"][0].get("summary") if record["links"] and record["links"][0].get("summary") else None) or \
                   (record["reasons"][0] if record["reasons"] else record.get("label"))
        item["sentence"] = "%s PASS：%s" % (label, headline)
    elif record["verdict"] == "FAILED":
        item["kind"] = "FAILED"
        item["sentence"] = "%s FAILED（%s）：%s" % (label, record.get("label"), (record["reasons"] or [""])[0])
    else:
        score, cutoff = item["score"], table.get("cutoff")
        if score is not None and score > 0 and cutoff is not None and score >= cutoff:
            item["kind"], item["raw"] = "RANK", SUPPORT_RANK
            item["sentence"] = "%s 排序支持：分数 %.1f，全池第 %s/%s（前 10%% 线 %.1f），结论 %s 未达 PASS" % (
                label, score, item["rank"], table.get("pool"), cutoff, record.get("label"))
        else:
            item["sentence"] = "%s：结论 %s，分数 %s，未进全池前 10%%" % (label, record.get("label"), "-" if score is None else "%.1f" % score)
    if item["raw"] > 0:
        sec, roots = evidence_roots(record["links"])
        if not sec:
            item["kind"], item["raw"] = "NO_PRIMARY_SOURCE", 0.0
            item["sentence"] += "；但没有 SEC 一手原文，不计分"
        else:
            item["links"], item["roots"] = sec, roots
    return item


def dedupe_supports(items: Sequence[dict], weights: Mapping[str, Any]) -> Tuple[List[dict], List[dict]]:
    """按证据根去重：一个分支的全部证据根都已被更强（或同强按分支顺序在前）的已计分分支引用过，只算一次。"""
    order = {b: i for i, b in enumerate(STOCK_BRANCHES)}
    counted: List[dict] = []
    duplicates: List[dict] = []
    seen: set = set()
    for item in sorted((i for i in items if i["raw"] > 0), key=lambda i: (-i["raw"], order[i["branch_id"]])):
        roots = set(item["roots"])
        if roots and roots <= seen:
            duplicates.append({**item, "duplicate_of_roots": sorted(roots)})
            continue
        seen |= roots
        weight = float((weights.get("branches", {}).get(item["branch_id"]) or {}).get("weight", 1.0))
        counted.append({**item, "weight": weight, "weighted": round(item["raw"] * weight, 6)})
    return counted, duplicates


def support_summary(research: ResearchView, symbol: str, weights: Mapping[str, Any]) -> dict:
    items = [branch_support(research, branch, symbol) for branch in STOCK_BRANCHES]
    counted, duplicates = dedupe_supports(items, weights)
    total = round(sum(i["weighted"] for i in counted), 6)
    raw_total = round(sum(i["raw"] for i in counted), 6)
    n_pass = sum(1 for i in counted if i["kind"] == "PASS")
    n_rank = sum(1 for i in counted if i["kind"] == "RANK")
    pct = sum(p for p in (_rank_percentile(research, i["branch_id"], symbol) for i in items
                          if i["verdict"] not in (None, "FAILED") and (i["score"] or 0) > 0) if p is not None)
    links = [x for i in counted for x in i["links"]]
    return {"symbol": symbol, "total": total, "raw_total": raw_total, "n_pass": n_pass, "n_rank": n_rank, "counted": counted,
            "duplicates": duplicates, "all": items, "rank_percentile_sum": round(pct, 4), "latest_event_date": _latest_date(links),
            "meets_threshold": n_pass >= 1 and (n_pass + n_rank) >= 2 and total >= PUBLISH_THRESHOLD - 1e-9}


# ---- 一票否决 / 冲突 --------------------------------------------------------------------
def vetoes_for(research: ResearchView, symbol: str, invalidated: Optional[Mapping[str, dict]] = None) -> List[dict]:
    found: List[dict] = []
    event = research.verdict("equity-event-atlas", symbol)
    if event is not None and event["verdict"] == "FAILED":
        found.append({"id": "EVENT_ATLAS_FAILED", "branch_id": "equity-event-atlas", "label": event.get("label"),
                      "text": "事件航图：%s" % ((event["reasons"] or [event.get("label")])[0]), "links": [x for x in event["links"] if is_sec_link(x)][:4]})
    if event is not None and (event.get("evidence") or {}).get("insider_net_sell"):
        found.append({"id": "INSIDER_NET_SELL", "branch_id": "equity-event-atlas", "label": "INSIDER_NET_SELL",
                      "text": "近期内部人公开市场净卖出", "links": []})
    bottleneck = research.verdict("bottleneck-serenity-skill", symbol)
    if bottleneck is not None and ((bottleneck.get("evidence") or {}).get("hard_flags") or {}).get("kill_switch_triggered") is True:
        found.append({"id": "BOTTLENECK_KILL_SWITCH", "branch_id": "bottleneck-serenity-skill", "label": "KILL_SWITCH",
                      "text": "瓶颈：kill switch 已触发", "links": []})
    previous = (invalidated or {}).get(symbol)
    if previous is not None:
        found.append({"id": "PREVIOUSLY_INVALIDATED", "branch_id": None, "label": "INVALIDATED",
                      "text": "此前发布的建议已失效（%s）：%s" % (previous.get("invalidated_at", "")[:16],
                                                          "；".join(t["text"] for t in previous.get("triggered", [])) or "已触发"),
                      "links": []})
    return found


def conflicts_for(research: ResearchView, symbol: str, vetoes: Sequence[dict]) -> List[dict]:
    """保留正反冲突：否决项，加上其它分支给出 FAILED 的原因（不否决，但要让人看到）。"""
    result = [{"kind": "VETO", "text": v["text"], "branch_id": v.get("branch_id"), "links": v.get("links", [])} for v in vetoes]
    veto_branches = {v.get("branch_id") for v in vetoes}
    for branch in STOCK_BRANCHES:
        record = research.verdict(branch, symbol)
        if record is not None and record["verdict"] == "FAILED" and branch not in veto_branches and research.branch_status(branch) == "PASS":
            result.append({"kind": "OPPOSING_BRANCH", "branch_id": branch, "links": [],
                           "text": "%s：%s（%s）" % (BRANCH_LABELS[branch], record.get("label"), (record["reasons"] or [""])[0][:120])})
    return result


# ---- 失效条件：发布时写死，之后每轮核对 ---------------------------------------------------
NOT_MONITORED = [{"id": "INSIDER_SELL", "text": "内部人公开市场卖出",
                  "reason": "研究层目前只采集 Form 4 的公开市场买入（代码 P），没有采集卖出（代码 S），暂时无法自动核对"}]


def freeze_conditions(research: ResearchView, symbol: str, supporters: Sequence[Mapping], now: datetime) -> dict:
    event = research.verdict("equity-event-atlas", symbol)
    dilution_text = ((event or {}).get("evidence") or {}).get("invalidation_conditions") or [
        "近 90 天内出现 424B5/S-1（含 ATM）增发或招股", "封面流通股同比增幅 >= 10%"]
    latest = (research.fundamentals.get(symbol) or {}).get("latest_periodic")
    return {
        "symbol": symbol, "published_at": now.astimezone(timezone.utc).isoformat(), "as_of": research.as_of,
        "snapshot_sha256": research.snapshot_sha256, "status": "ACTIVE", "triggered": [], "invalidated_at": None,
        "supporters": [{"branch_id": s["branch_id"], "kind": s["kind"]} for s in supporters],
        "baseline_periodic": latest,
        "conditions": [
            {"id": "DILUTION", "text": "发布后出现增发 / ATM / 招股：" + "；".join(dilution_text)},
            {"id": "SUPPORT_REVOKED", "text": "支持它的分支结论被撤销（PASS 变为非 PASS，或排序支持者被判 FAILED）"},
            {"id": "REVENUE_TURNS_NEGATIVE", "text": "下一份 10-Q/10-K 营收同比转负"
             + ("（当前基线：%s %s 申报于 %s）" % (latest["form"], latest["period_end"], latest["filed"]) if latest else "（研究层未取到基线，暂无法核对）")},
        ],
        "not_monitored": deepcopy(NOT_MONITORED),
    }


def check_conditions(frozen: Mapping, research: ResearchView) -> List[dict]:
    """逐条核对。返回 [{id, text, status: OK|TRIGGERED|NOT_CHECKABLE, detail}]。"""
    symbol = frozen["symbol"]
    results: List[dict] = []
    text = {c["id"]: c["text"] for c in frozen["conditions"]}

    event = research.verdict("equity-event-atlas", symbol)
    if research.branch_status("equity-event-atlas") != "PASS" or event is None:
        results.append({"id": "DILUTION", "text": text["DILUTION"], "status": "NOT_CHECKABLE", "detail": "最新研究快照里没有这只股的事件航图结论"})
    elif event["verdict"] == "FAILED":
        results.append({"id": "DILUTION", "text": text["DILUTION"], "status": "TRIGGERED",
                        "detail": (event["reasons"] or [event.get("label")])[0], "links": [x for x in event["links"] if is_sec_link(x)][:3]})
    else:
        results.append({"id": "DILUTION", "text": text["DILUTION"], "status": "OK", "detail": "最新快照没有触发稀释失效条件"})

    revoked = []
    for supporter in frozen["supporters"]:
        branch, kind = supporter["branch_id"], supporter["kind"]
        record = research.verdict(branch, symbol)
        status = research.branch_status(branch)
        if kind == "PASS" and (status != "PASS" or record is None or record["verdict"] != "PASS"):
            revoked.append("%s 的 PASS 已变为 %s" % (BRANCH_LABELS[branch], "无结论" if record is None or status != "PASS" else record["verdict"]))
        elif kind == "RANK" and (status == "PASS" and record is not None and record["verdict"] == "FAILED"):
            revoked.append("%s 已判 FAILED（%s）" % (BRANCH_LABELS[branch], record.get("label")))
    results.append({"id": "SUPPORT_REVOKED", "text": text["SUPPORT_REVOKED"], "status": "TRIGGERED" if revoked else "OK",
                    "detail": "；".join(revoked) if revoked else "支持它的分支结论仍然成立"})

    current = (research.fundamentals.get(symbol) or {})
    baseline = frozen.get("baseline_periodic")
    latest = current.get("latest_periodic")
    if baseline is None or not current:
        results.append({"id": "REVENUE_TURNS_NEGATIVE", "text": text["REVENUE_TURNS_NEGATIVE"], "status": "NOT_CHECKABLE",
                        "detail": "没有发布时的定期报告基线或最新营收数据"})
    elif latest is None or latest["accession"] == baseline["accession"]:
        results.append({"id": "REVENUE_TURNS_NEGATIVE", "text": text["REVENUE_TURNS_NEGATIVE"], "status": "OK",
                        "detail": "尚无新的 10-Q/10-K（最新仍是 %s，申报于 %s）" % (baseline["form"], baseline["filed"])})
    else:
        q, ttm = current.get("revenue_q_yoy"), current.get("revenue_yoy")
        negative = (q is not None and q < 0) or (q is None and ttm is not None and ttm < 0)
        if q is None and ttm is None:
            results.append({"id": "REVENUE_TURNS_NEGATIVE", "text": text["REVENUE_TURNS_NEGATIVE"], "status": "NOT_CHECKABLE",
                            "detail": "新的 %s 已申报，但取不到营收同比" % latest["form"]})
        else:
            results.append({"id": "REVENUE_TURNS_NEGATIVE", "text": text["REVENUE_TURNS_NEGATIVE"], "status": "TRIGGERED" if negative else "OK",
                            "detail": "新的 %s（%s 申报）单季营收同比 %s，TTM 同比 %s" % (
                                latest["form"], latest["filed"], "-" if q is None else "%+.1f%%" % (q * 100),
                                "-" if ttm is None else "%+.1f%%" % (ttm * 100))})
    return results


def refresh_state(state: Optional[Mapping], research: ResearchView, now: datetime) -> dict:
    """每轮核对所有仍生效的已发布建议；触发即标 INVALIDATED，超过 PUBLISHED_TTL_DAYS 标 EXPIRED。"""
    new = deepcopy(dict(state or {}))
    published = new.setdefault("published", {})
    for symbol, record in published.items():
        if record.get("status") != "ACTIVE":
            continue
        age = now - datetime.fromisoformat(record["published_at"])
        if age > timedelta(days=PUBLISHED_TTL_DAYS):
            record["status"] = "EXPIRED"
            continue
        checks = check_conditions(record, research)
        record["last_checked_at"] = now.astimezone(timezone.utc).isoformat()
        record["last_checks"] = checks
        triggered = [c for c in checks if c["status"] == "TRIGGERED"]
        if triggered:
            record["status"] = "INVALIDATED"
            record["triggered"] = triggered
            record["invalidated_at"] = now.astimezone(timezone.utc).isoformat()
    return new


# ---- 硬门 ---------------------------------------------------------------------------------
Liquidity = Callable[[str], Optional[Mapping[str, Any]]]


def gate_quote(market: Mapping[str, Any]) -> dict:
    status = market.get("quote_status") if market else None
    price = market.get("price") if market else None
    ok = status == "FRESH" and isinstance(price, (int, float)) and math.isfinite(price) and price > 0
    return {"ok": ok, "detail": "报价新鲜" if ok else "报价不通过：%s" % (status or "没有取到报价"), "status": status}


def gate_liquidity(entry: Mapping, market: Mapping, liquidity: Optional[Mapping[str, Any]]) -> dict:
    price = (market or {}).get("price")
    problems: List[str] = []
    if price is None or price < MIN_PRICE_USD:
        problems.append("价格 %s < %.0f 美元" % ("-" if price is None else "%.2f" % price, MIN_PRICE_USD))
    shares = (entry or {}).get("shares_outstanding")
    cap = price * shares if price and shares else None
    if cap is not None and cap > MAX_MARKET_CAP_USD:
        problems.append("按最新价算市值 %.1f 亿美元 > 50 亿" % (cap / 1e8))
    dollar_volume = (liquidity or {}).get("median_dollar_volume_20d_usd")
    source = (liquidity or {}).get("source", "research_snapshot")
    if dollar_volume is None:
        dollar_volume = (entry or {}).get("median_dollar_volume_20d_usd")
        source = "research_snapshot"
    if dollar_volume is None or dollar_volume < MIN_MEDIAN_DOLLAR_VOLUME_USD:
        problems.append("20 日成交额中位数 %s < %.0f 万美元" % ("-" if dollar_volume is None else "%.0f 万" % (dollar_volume / 1e4),
                                                            MIN_MEDIAN_DOLLAR_VOLUME_USD / 1e4))
    return {"ok": not problems, "detail": "；".join(problems) if problems else "流动性通过（20 日成交额中位数 %.0f 万美元，%s）" % (
        dollar_volume / 1e4, "实时日线" if source == "live_daily_bars" else "研究快照"), "median_dollar_volume_20d_usd": dollar_volume,
        "source": source, "market_cap_usd": cap}


# ---- 阻断 ---------------------------------------------------------------------------------
_PROBLEM_TEXT = {
    "RESEARCH_MISSING": "研究层还没有产出任何结果",
    "RESEARCH_UNREADABLE": "研究层产物读不出来",
    "SNAPSHOT_MISMATCH": "研究产物之间指向的不是同一份快照",
    "BRANCH_RECEIPT_MISSING": "有分支没有交收据",
    "BRANCH_SNAPSHOT_MISMATCH": "有分支读的不是本轮同一份快照",
    "BRANCH_FAILED": "有分支运行失败",
    "VERDICTS_MISSING": "有分支的逐股结论文件缺失",
    "VERDICTS_UNREADABLE": "有分支的逐股结论文件读不出来",
    "HUBINPUTS_MISSING": "研究产物缺少中枢输入文件",
    "HUBINPUTS_MISMATCH": "中枢输入与快照不是同一份",
    "HUBINPUTS_UNREADABLE": "中枢输入文件读不出来",
}


def humanize_problems(problems: Sequence[str]) -> str:
    parts = []
    for problem in problems:
        code, _, rest = problem.partition(":")
        text = _PROBLEM_TEXT.get(code, code)
        parts.append("%s（%s）" % (text, rest) if rest else text)
    return "；".join(parts)


def blocked_decision(reason: str, message: str, *, details: Optional[Mapping] = None) -> dict:
    return {
        "state": "SYSTEM_BLOCKED", "action": None, "action_code": ACTION_CODES["SYSTEM_BLOCKED"], "primary_symbol": None,
        "blocked_reason": reason, "rationale": message, "message": message,
        "invalidation": None, "reasons": [], "sources": [], "conflicts": [], "watchlist": [],
        "details": dict(details or {}),
    }


def data_chain(research: ResearchView, now: datetime) -> dict:
    age = research.age_hours(now)
    return {"research_as_of": research.as_of or None, "snapshot_sha256": research.snapshot_sha256 or None,
            "snapshot_generated_at": research.generated_at.isoformat() if research.generated_at else None,
            "research_checked_at": research.checked_at.isoformat() if research.checked_at else None,
            "research_age_hours": None if age is None else round(age, 2), "research_max_age_hours": RESEARCH_MAX_AGE_HOURS,
            "problems": list(research.problems)}


def system_block(research: ResearchView, now: datetime, *, quotes_available: bool = True) -> Optional[dict]:
    """数据链不完整：返回阻断决策；完整返回 None。"""
    chain = data_chain(research, now)
    if research.problems:
        message = "数据链不完整：" + humanize_problems(research.problems) + "。本轮不出结论。"
        return blocked_decision("RESEARCH_CHAIN_INCOMPLETE", message, details=chain)
    age = research.age_hours(now)
    if age is None or age > RESEARCH_MAX_AGE_HOURS:
        message = "研究快照已经 %s 小时没有更新（上限 %d 小时），不拿旧的研究结果出结论。" % (
            "未知" if age is None else "%.0f" % age, int(RESEARCH_MAX_AGE_HOURS))
        return blocked_decision("RESEARCH_SNAPSHOT_STALE", message, details=chain)
    if not quotes_available:
        return blocked_decision("MARKET_DATA_UNAVAILABLE", "行情源全部取不到数据，本轮不出结论。", details=chain)
    return None


# ---- 主入口 -------------------------------------------------------------------------------
def _gate_row(symbol: str, research: ResearchView, summary: dict, market: Mapping[str, Mapping], vetoes: Sequence[dict],
              liquidity_fn: Optional[Liquidity], evaluate_liquidity: bool) -> dict:
    entry = research.pool.get(symbol) or {}
    quote = gate_quote(market.get(symbol) or {})
    row = {"symbol": symbol, "gates": {
        "pool": {"ok": symbol in research.pool, "detail": "在候选池内" if symbol in research.pool else "不在候选池内"},
        "quote": quote,
        "liquidity": {"ok": None, "detail": "未评估（前面的门没过）"},
        "veto": {"ok": not vetoes, "detail": "没有生效的失效条件" if not vetoes else "；".join(v["text"] for v in vetoes)},
        "support": {"ok": summary["meets_threshold"],
                    "detail": "加权支持度 %.2f >= %.1f（%d 个 PASS + %d 个排序支持）" % (summary["total"], PUBLISH_THRESHOLD, summary["n_pass"], summary["n_rank"])
                    if summary["meets_threshold"] else _support_shortfall(summary)},
    }}
    if evaluate_liquidity:
        liquidity = liquidity_fn(symbol) if liquidity_fn else None
        row["gates"]["liquidity"] = gate_liquidity(entry, market.get(symbol) or {}, liquidity)
    return row


def _support_shortfall(summary: dict) -> str:
    counted = summary["counted"]
    if not counted:
        return "没有任何分支给出支持（合计 0，需要 %.1f）" % PUBLISH_THRESHOLD
    parts = "、".join("%s %s %.1f" % (i["label"], "PASS" if i["kind"] == "PASS" else "排序支持", i["weighted"]) for i in counted)
    dup = "；另有 %s 与已计分分支引用同一份申报，只算一次" % "、".join(i["label"] for i in summary["duplicates"]) if summary["duplicates"] else ""
    if summary["n_pass"] == 0:
        return "没有分支 PASS（只有%s，合计 %.2f < %.1f）%s" % (parts, summary["total"], PUBLISH_THRESHOLD, dup)
    if summary["n_pass"] + summary["n_rank"] < 2:
        return "只有 %s，没有另一个独立分支排序支持（合计 %.2f < %.1f）%s" % (parts, summary["total"], PUBLISH_THRESHOLD, dup)
    return "支持度合计 %.2f < %.1f（%s；权重把它压低了）%s" % (summary["total"], PUBLISH_THRESHOLD, parts, dup)


def _first_failed_gate(row: dict) -> Tuple[str, str]:
    order = (("veto", "一票否决"), ("support", "支持度"), ("quote", "实时报价"), ("liquidity", "流动性"), ("pool", "候选池"))
    for key, name in order:
        gate = row["gates"][key]
        if gate["ok"] is False:
            return name, gate["detail"]
    return "", ""


def rank_candidates(research: ResearchView, market: Mapping[str, Mapping[str, Any]], weights: Mapping[str, Any],
                    invalidated: Optional[Mapping[str, dict]] = None, liquidity_fn: Optional[Liquidity] = None,
                    symbols: Optional[Sequence[str]] = None) -> Tuple[List[dict], Dict[str, dict], Optional[dict]]:
    """候选排序 + 逐门评估 + 选出唯一建议。线上（decide）和回测（backtest/hub_backtest.py）共用这一个函数。
    返回（按发布优先级排好的逐门结果, {代码: 支持度}, 第一个全部门通过的候选或 None）。"""
    summaries = {symbol: support_summary(research, symbol, weights) for symbol in (symbols or [i["symbol"] for i in research.shortlist])}
    winner: Optional[dict] = None
    rows: List[dict] = []
    for summary in candidate_order(summaries.values()):
        symbol = summary["symbol"]
        vetoes = vetoes_for(research, symbol, invalidated)
        cheap = _gate_row(symbol, research, summary, market, vetoes, liquidity_fn, evaluate_liquidity=False)
        others_ok = all(cheap["gates"][k]["ok"] for k in ("pool", "quote", "veto", "support"))
        row = _gate_row(symbol, research, summary, market, vetoes, liquidity_fn, evaluate_liquidity=True) if others_ok else cheap
        row["vetoes"] = vetoes
        rows.append(row)
        if winner is None and all(row["gates"][k]["ok"] for k in ("pool", "quote", "liquidity", "veto", "support")):
            winner = row
    return rows, summaries, winner


def decide(research: ResearchView, market: Mapping[str, Mapping[str, Any]], *, now: datetime,
           liquidity_fn: Optional[Liquidity] = None, weights: Optional[Mapping[str, Any]] = None,
           state: Optional[Mapping] = None, quotes_available: bool = True) -> dict:
    """返回 {decision, candidates, state, weights}。纯函数：同样的输入得到同样的输出。"""
    now = now.astimezone(timezone.utc)
    weights = dict(weights or branch_weights(None))
    blocked = system_block(research, now, quotes_available=quotes_available)
    if blocked is not None:
        return {"decision": blocked, "candidates": [], "state": deepcopy(dict(state or {})), "weights": weights}

    new_state = refresh_state(state, research, now)
    invalidated = {s: r for s, r in new_state.get("published", {}).items() if r.get("status") == "INVALIDATED"}
    chain = data_chain(research, now)
    environment = {"regime": research.environment.get("regime"), "note": research.environment.get("note"),
                   "role": "MARKET_ENVIRONMENT_INPUT_NOT_STOCK_PICKING"}

    rows, summaries, winner = rank_candidates(research, market, weights, invalidated, liquidity_fn)

    candidates = [_candidate_view(research, summaries[row["symbol"]], row, market) for row in rows]
    for rank, view in enumerate(candidates, 1):
        view["rank"] = rank

    watch_source = [c for c in candidates if not (winner is not None and c["symbol"] == winner["symbol"])]
    watchlist = [_watch_view(c) for c in watch_source[:WATCHLIST_SIZE]]
    qualifying = sum(1 for c in candidates if c["passes_all_gates"])
    common = {"qualifying_candidates": qualifying, "weights_mode": weights["mode"], "data_chain": chain, "market_environment": environment, "support_rule": SUPPORT_RULE,
              "weight_formula": WEIGHT_FORMULA, "publish_threshold": PUBLISH_THRESHOLD,
              "invalidated_recommendations": [_published_view(s, r) for s, r in sorted(invalidated.items())]}

    if winner is None:
        best = candidates[0] if candidates else None
        why = ("候选 %d 只，没有一只同时满足「支持度合计 >= %.1f」和全部硬门。" % (len(candidates), PUBLISH_THRESHOLD)
               + ("离发布最近的是 %s（%s）。" % (best["symbol"], best["gate_summary"]) if best else ""))
        decision = {"state": "NO_ACTION", "action": None, "action_code": ACTION_CODES["NO_ACTION"], "primary_symbol": None,
                    "rationale": why, "reasons": [], "sources": [], "conflicts": [], "invalidation": None,
                    "watchlist": watchlist, "candidates_evaluated": len(candidates), **common}
        return {"decision": decision, "candidates": candidates, "state": new_state, "weights": weights}

    symbol = winner["symbol"]
    summary = summaries[symbol]
    frozen = new_state["published"].get(symbol)
    if frozen is None or frozen.get("status") != "ACTIVE":
        frozen = freeze_conditions(research, symbol, summary["counted"], now)
        frozen["last_checks"] = check_conditions(frozen, research)
        frozen["last_checked_at"] = now.isoformat()
        new_state["published"][symbol] = frozen
    entry = research.pool.get(symbol) or {}
    record = next((c for c in candidates if c["symbol"] == symbol), {})
    sources, reasons = [], []
    for item in summary["counted"]:
        reasons.append({"branch_id": item["branch_id"], "label": item["label"], "kind": item["kind"], "weight": item["weight"],
                        "support": item["weighted"], "sentence": item["sentence"],
                        "link": item["links"][0]["url"] if item["links"] else None})
        for link in item["links"][:3]:
            if link["url"] not in {s["url"] for s in sources}:
                sources.append({"url": link["url"], "branch_id": item["branch_id"], "summary": link.get("summary") or link.get("label"),
                                "published_date": link.get("published_date") or link.get("filed")})
    decision = {
        "state": "RECOMMENDATION", "action": ACTION_FOLLOW, "action_code": ACTION_CODES["RECOMMENDATION"], "primary_symbol": symbol,
        "primary_name": entry.get("name") or record.get("name"), "market_cap_usd": record.get("market_cap_usd"),
        "price": (market.get(symbol) or {}).get("price"), "quote_source_time": (market.get(symbol) or {}).get("source_time"),
        "support": {"total": summary["total"], "threshold": PUBLISH_THRESHOLD, "raw_total": summary["raw_total"],
                    "branches": [{"branch_id": i["branch_id"], "label": i["label"], "kind": i["kind"], "raw": i["raw"], "weight": i["weight"],
                                  "weighted": i["weighted"], "roots": i["roots"]} for i in summary["counted"]],
                    "deduplicated": [{"branch_id": i["branch_id"], "label": i["label"], "roots": i["duplicate_of_roots"]} for i in summary["duplicates"]]},
        "rationale": "%s（%s）加权支持度 %.2f >= %.1f：%s。" % (symbol, entry.get("name", ""), summary["total"], PUBLISH_THRESHOLD,
                                                    "；".join(r["sentence"] for r in reasons)),
        "reasons": reasons, "sources": sources, "conflicts": conflicts_for(research, symbol, []),
        "invalidation": _published_view(symbol, frozen), "watchlist": watchlist, "candidates_evaluated": len(candidates),
        "gates": winner["gates"], "published_at": frozen["published_at"], **common,
    }
    return {"decision": decision, "candidates": candidates, "state": new_state, "weights": weights}


def candidate_order(summaries: Sequence[dict]) -> List[dict]:
    """支持度合计高者在前；平局：支持它的事件更新的在前，再看各分支名次分位之和，最后按代码。（稳定多轮排序）"""
    ordered = sorted(summaries, key=lambda s: s["symbol"])
    ordered.sort(key=lambda s: -s["rank_percentile_sum"])
    ordered.sort(key=lambda s: s["latest_event_date"], reverse=True)
    ordered.sort(key=lambda s: -s["total"])
    return ordered


def _published_view(symbol: str, record: Mapping) -> dict:
    return {"symbol": symbol, "status": record["status"], "status_text": {"ACTIVE": "生效中", "INVALIDATED": "已失效", "EXPIRED": "已过期"}.get(record["status"], record["status"]),
            "published_at": record["published_at"], "as_of": record.get("as_of"), "invalidated_at": record.get("invalidated_at"),
            "conditions": record.get("last_checks") or [{"id": c["id"], "text": c["text"], "status": "NOT_CHECKED"} for c in record["conditions"]],
            "triggered": record.get("triggered", []), "not_monitored": record.get("not_monitored", []),
            "last_checked_at": record.get("last_checked_at")}


def _candidate_view(research: ResearchView, summary: dict, row: dict, market: Mapping[str, Mapping]) -> dict:
    symbol = summary["symbol"]
    item = next((x for x in research.shortlist if x["symbol"] == symbol), {})
    failed_name, failed_detail = _first_failed_gate(row)
    quote = market.get(symbol) or {}
    return {
        "symbol": symbol, "name": item.get("name"), "cik": item.get("cik"), "market_cap_usd": item.get("market_cap_usd"),
        "price": quote.get("price"), "quote_status": quote.get("quote_status"),
        "support_total": summary["total"], "n_pass": summary["n_pass"], "n_rank": summary["n_rank"],
        "support_branches": [{"branch_id": i["branch_id"], "label": i["label"], "kind": i["kind"], "weighted": i["weighted"]} for i in summary["counted"]],
        "deduplicated": [i["label"] for i in summary["duplicates"]],
        "scores": {i["branch_id"]: i["score"] for i in summary["all"] if i["score"] is not None},
        "gates": row["gates"], "vetoes": row.get("vetoes", []),
        "passes_all_gates": all(g["ok"] for g in row["gates"].values()),
        "failed_gate": failed_name, "gate_summary": ("差在【%s】：%s" % (failed_name, failed_detail)) if failed_name else "全部门通过（与唯一建议同分，平局按事件新近度排在后面）",
        "links": [x["url"] for i in summary["counted"] for x in i["links"][:1]],
        "latest_event_date": summary["latest_event_date"],
    }


def _watch_view(candidate: Mapping) -> dict:
    return {"symbol": candidate["symbol"], "name": candidate["name"], "support_total": candidate["support_total"],
            "failed_gate": candidate["failed_gate"], "sentence": candidate["gate_summary"], "links": candidate["links"][:2],
            "scores": candidate["scores"], "price": candidate["price"]}
