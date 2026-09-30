"""中枢：把四个选股分支各自的结论汇成「唯一建议 / NO_ACTION / SYSTEM_BLOCKED」。

这个模块只做确定性的规则计算，不联网、不读文件、不落盘：输入是研究层产物（ResearchView）、
实时层的行情状态、前向记分簿给出的分支命中率、上一轮的失效条件状态；输出是决策、候选比较表和新的状态。
回测（backtest/hub_backtest.py）调用的是同一批函数，所以「回测复现的规则」和「线上跑的规则」是同一份代码。

规则（Owner 已定，不因结果难看而改动）
------------------------------------
候选   = 研究层 shortlist（<= 60 只）。
硬门   = ① 在候选池内；② 实时报价按交易时间口径新鲜；③ 流动性（价格、20 日成交额中位数、市值上限）；
         ④ 没有生效的失效条件（事件航图 FAILED：近 90 天增发/ATM 或股数大增；以及此前发布过、之后已失效的建议）。
         ④ 是一票否决，列入「冲突」。（内部人净卖出、瓶颈 kill switch 暂未接入：研究层没有这两项的数据来源，
         所以它们不是硬门，页面上如实写「暂未接入」，不假装生效。）
支持度 = 每个选股分支对该股：PASS = 1.0；未 PASS 但该分支分数在全池前 10%（且不是 FAILED）= 0.3（排序支持）；否则 0。
         没有 SEC 一手原文链接的论点不计分。
独立性 = 两个分支若引用的申报（accession）全部落在已计分分支引用过的申报里，只算一次。
权重   = 前向记分簿里该分支已结算建议的命中率；该分支已结算样本 < 8 用等权（1.0）。
         权重只会把支持度往下调（上限 1.0），不会让门槛变低。
发布   = 加权支持度合计 >= 1.3（至少一个分支 PASS 且至少另一个独立分支排序支持）且全部硬门通过；取合计最高者，
         平局按支持它的事件的新近程度。否则 NO_ACTION，并给观察名单前 5。
自证门 = 规则自证门（B4.5）：发布唯一建议前，规则必须先自己证明有信息量。
         (a) 回测证据：样本外窗口 >= 6，且唯一建议 20 日净超额均值相对 IWM > 0、相对同档随机 > 0，且安慰剂均值 < 正式结果均值，
             安慰剂本身要有 >= 6 个有效窗口且与正式窗口的月份对齐；回测报告必须绑定当前规则版本与各分支参数 sha256（报告里记录、读取时核对，
             对不上就当没有回测证据），并且没过 35 天有效期（过期同样当没有回测证据）；
         (b) 前向证据：记分簿里已结算的候选（影子候选 + 正式建议）里「独立样本」>= 8 条（不同标的、20 日窗口不重叠），
             命中率 >= 55%，平均超额 > 0（下一交易日收盘入场、扣与回测同一份成本）。
         开门 = (a) 或 (b) 达标，且前向证据没有否决——前向证据一旦够样本下限而不达标（命中率 < 55% 或平均超额 <= 0），一票否决，无论回测如何。
         门没开：决策一律 NO_ACTION（原因写人话），照常算出「如果发布会选谁」记为影子候选，只记录、不发布，并给观察名单前 5。
         证据不足（回测窗口 < 6、前向独立样本 < 8）时，门的判定里不含任何收益数字。
阻断   = 研究快照过期（> 36 小时没确认）、分支收据不全或有分支运行失败、行情源全断 -> SYSTEM_BLOCKED。
动作只写「研究跟进（看多）」，不写「买入」；系统不下单。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import nyse_calendar
from .research_view import BRANCH_LABELS, ENVIRONMENT_BRANCH, RANK_TOP_FRACTION, STOCK_BRANCHES, ResearchView

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

# ---- 规则自证门（B4.5）：Owner 定的门槛，不许为了让门打开而改 ---------------------------------
PROOF_MIN_OOS_WINDOWS = 6
PROOF_FORWARD_MIN_SETTLED = 8
PROOF_FORWARD_MIN_HIT_RATE = 0.55
PROOF_BACKTEST_MAX_AGE_DAYS = 35
PROOF_GATE_SCHEMA = "signal-lattice-proof-gate/2"
HUB_RULE_VERSION = "hub-rule/3"
# 回测重放的分支（股势前瞻线上整分支 ABSTAIN，回测不重放，它的参数变化不影响回测结论）
BACKTEST_BOUND_BRANCHES = ("bottleneck-serenity-skill", "equity-event-atlas", "stock-commercial-opportunities")
PROOF_MIN_PLACEBO_WINDOWS = 6
PROOF_GATE_RULE = ("规则自证门：满足任一才允许发布唯一建议。(a) 回测：样本外窗口 >= %d，唯一建议 20 日净超额均值相对 IWM > 0、相对同档随机 > 0，"
                   "且安慰剂（事件日期后移 60 个交易日，有效窗口 >= %d 且月份与正式对齐）均值低于正式结果；回测报告必须绑定当前规则版本与参数 sha256，"
                   "且在 %d 天有效期内，否则当没有回测证据；(b) 前向：记分簿里已结算的候选（影子候选 + 正式建议）中独立样本（不同标的、20 日窗口不重叠）>= %d 条，"
                   "命中率（相对 IWM 净超额 > 0）>= %d%%，平均超额 > 0。前向证据够样本而不达标时一票否决，无论回测如何。证据不足时不显示任何收益数字。"
                   % (PROOF_MIN_OOS_WINDOWS, PROOF_MIN_PLACEBO_WINDOWS, PROOF_BACKTEST_MAX_AGE_DAYS, PROOF_FORWARD_MIN_SETTLED,
                      int(PROOF_FORWARD_MIN_HIT_RATE * 100)))

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


# 暂未接入的否决项：研究层没有这两项的数据来源，所以它们不在硬门里、也不会生效。页面如实写「暂未接入」，不假装在拦。
NOT_WIRED_VETOES = [
    {"id": "INSIDER_NET_SELL", "text": "内部人公开市场净卖出", "status": "NOT_WIRED",
     "reason": "研究层只采集 Form 4 的公开市场买入（代码 P），没有采集卖出（代码 S），没有数据来源，暂未接入"},
    {"id": "BOTTLENECK_KILL_SWITCH", "text": "瓶颈分支 kill switch", "status": "NOT_WIRED",
     "reason": "瓶颈分支目前不输出 kill switch 结论，没有数据来源，暂未接入"},
]

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


def research_age_hours(research: ResearchView, now: datetime) -> Optional[float]:
    """研究快照多久没确认（小时），扣掉之间整天休市的周末与美股假日：那些天没有新申报，快照不会因此变旧。
    休市当天与交易日的时间照常按墙钟计，所以行为只在长周末/假日里比纯墙钟宽——上限仍是 36 小时。"""
    age, fresh = research.age_hours(now), research.fresh_at
    if age is None or fresh is None:
        return age
    return max(0.0, age - 24.0 * nyse_calendar.closed_full_days_between(fresh, now))


def data_chain(research: ResearchView, now: datetime) -> dict:
    age = research.age_hours(now)
    trading_age = research_age_hours(research, now)
    return {"research_as_of": research.as_of or None, "snapshot_sha256": research.snapshot_sha256 or None,
            "snapshot_generated_at": research.generated_at.isoformat() if research.generated_at else None,
            "research_checked_at": research.checked_at.isoformat() if research.checked_at else None,
            "research_age_hours": None if age is None else round(age, 2), "research_max_age_hours": RESEARCH_MAX_AGE_HOURS,
            "research_age_trading_hours": None if trading_age is None else round(trading_age, 2),
            "problems": list(research.problems)}


def system_block(research: ResearchView, now: datetime, *, quotes_available: bool = True) -> Optional[dict]:
    """数据链不完整：返回阻断决策；完整返回 None。"""
    chain = data_chain(research, now)
    if research.problems:
        message = "数据链不完整：" + humanize_problems(research.problems) + "。本轮不出结论。"
        return blocked_decision("RESEARCH_CHAIN_INCOMPLETE", message, details=chain)
    age = research_age_hours(research, now)
    if age is None or age > RESEARCH_MAX_AGE_HOURS:
        message = "研究快照已经 %s 小时没有更新（上限 %d 小时，周末与美股假日不计），不拿旧的研究结果出结论。" % (
            "未知" if age is None else "%.0f" % age, int(RESEARCH_MAX_AGE_HOURS))
        return blocked_decision("RESEARCH_SNAPSHOT_STALE", message, details=chain)
    if not quotes_available:
        return blocked_decision("MARKET_DATA_UNAVAILABLE", "行情源全部取不到数据，本轮不出结论。", details=chain)
    return None


# ---- 规则自证门 ---------------------------------------------------------------------------
def _finite(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def signed_pct(value: float) -> str:
    """+2.4% / −3.9%（负号用真正的减号，和正号一样宽，一眼分得出方向）。"""
    return "%s%.1f%%" % ("+" if value >= 0 else "\u2212", abs(value) * 100)


# ---- 回测报告与当前规则的绑定 + 有效期 ------------------------------------------------------
def _canonical_sha(body: Mapping) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def rule_fingerprint() -> dict:
    """中枢规则本体：全部 Owner 定的门槛与权重公式。任何一个数字变了，指纹就变，旧回测就不再算这套规则的证据。"""
    body = {
        "version": HUB_RULE_VERSION,
        "support": {"pass": SUPPORT_PASS, "rank": SUPPORT_RANK, "publish_threshold": PUBLISH_THRESHOLD, "rank_top_fraction": RANK_TOP_FRACTION},
        "weights": {"min_samples": WEIGHT_MIN_SAMPLES, "neutral_hit_rate": WEIGHT_NEUTRAL_HIT_RATE},
        "hard_gates": {"min_price_usd": MIN_PRICE_USD, "min_median_dollar_volume_usd": MIN_MEDIAN_DOLLAR_VOLUME_USD,
                       "max_market_cap_usd": MAX_MARKET_CAP_USD, "vetoes": ["EVENT_ATLAS_FAILED", "PREVIOUSLY_INVALIDATED"]},
        "proof": {"min_oos_windows": PROOF_MIN_OOS_WINDOWS, "min_placebo_windows": PROOF_MIN_PLACEBO_WINDOWS,
                  "forward_min_settled": PROOF_FORWARD_MIN_SETTLED, "forward_min_hit_rate": PROOF_FORWARD_MIN_HIT_RATE,
                  "backtest_max_age_days": PROOF_BACKTEST_MAX_AGE_DAYS},
        "bound_branches": list(BACKTEST_BOUND_BRANCHES),
    }
    return {"hub_rule_version": HUB_RULE_VERSION, "hub_rule_sha256": _canonical_sha(body)}


def rule_binding(branch_params: Mapping[str, Mapping[str, Any]]) -> dict:
    """回测报告与线上必须一致的东西：中枢规则版本 + 指纹，加上回测重放的各分支「参数版本 + 参数 sha256」。
    branch_params：{分支: {"params_version", "params_sha256"}}（研究层收据里就有这两项）。"""
    body = {"schema": "signal-lattice-rule-binding/1", **rule_fingerprint(),
            "branch_params": {b: {"params_version": (branch_params.get(b) or {}).get("params_version"),
                                  "params_sha256": (branch_params.get(b) or {}).get("params_sha256")} for b in BACKTEST_BOUND_BRANCHES}}
    return {**body, "sha256": _canonical_sha(body)}


def binding_from_receipts(receipts: Mapping[str, Mapping[str, Any]]) -> dict:
    return rule_binding({b: receipts.get(b) or {} for b in BACKTEST_BOUND_BRANCHES})


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _binding_mismatches(recorded: Mapping, expected: Mapping) -> List[str]:
    found: List[str] = []
    body = {k: v for k, v in recorded.items() if k != "sha256"}
    if recorded.get("sha256") != _canonical_sha(body):
        found.append("绑定记录自身的校验值对不上（报告被改过）")
    if recorded.get("hub_rule_version") != expected.get("hub_rule_version"):
        found.append("中枢规则版本：回测时 %s，现在 %s" % (recorded.get("hub_rule_version"), expected.get("hub_rule_version")))
    elif recorded.get("hub_rule_sha256") != expected.get("hub_rule_sha256"):
        found.append("中枢规则的门槛/权重内容变了（版本号没变）")
    for branch in BACKTEST_BOUND_BRANCHES:
        old = (recorded.get("branch_params") or {}).get(branch) or {}
        new = (expected.get("branch_params") or {}).get(branch) or {}
        if old.get("params_sha256") != new.get("params_sha256") or old.get("params_version") != new.get("params_version"):
            found.append("%s 的参数：回测时 %s（%s），现在 %s（%s）" % (BRANCH_LABELS.get(branch, branch), old.get("params_version") or "-",
                                                                     (old.get("params_sha256") or "-")[:8], new.get("params_version") or "-",
                                                                     (new.get("params_sha256") or "-")[:8]))
    return found


def backtest_validity(report: Mapping, expected_binding: Optional[Mapping], now: Optional[datetime]) -> dict:
    """回测报告能不能当「当前规则」的证据：(1) 报告里记录的绑定要与当前规则版本 + 参数 sha256 逐项一致；(2) 生成后不超过 35 天。
    核对不了（没给当前绑定/没给当前时间/报告没写生成时间）一律当作不成立——不因为漏传参数而放行。"""
    generated = _parse_time(report.get("generated_at"))
    recorded = report.get("binding") if isinstance(report.get("binding"), Mapping) else None
    valid_until = None if generated is None else generated + timedelta(days=PROOF_BACKTEST_MAX_AGE_DAYS)
    info: Dict[str, Any] = {
        "generated_at": report.get("generated_at"), "valid_days": PROOF_BACKTEST_MAX_AGE_DAYS,
        "valid_until": None if valid_until is None else valid_until.isoformat(),
        "age_days": None if generated is None or now is None else round((now - generated).total_seconds() / 86400.0, 2),
        "expired": None if valid_until is None or now is None else now > valid_until,
        "binding_recorded": recorded is not None, "binding_matches": None, "mismatches": [],
        "report_binding_sha256": None if recorded is None else recorded.get("sha256"),
        "current_binding_sha256": None if expected_binding is None else expected_binding.get("sha256"),
        "rule_version": None if recorded is None else recorded.get("hub_rule_version"),
    }
    if recorded is None:
        info["binding_matches"], info["mismatches"] = False, ["报告里没有记录它对应的规则版本与参数 sha256"]
    elif expected_binding is None:
        info["mismatches"] = ["没有拿到当前规则版本与参数 sha256，无法核对"]
    else:
        info["mismatches"] = _binding_mismatches(recorded, expected_binding)
        info["binding_matches"] = not info["mismatches"]
    info["usable"] = info["binding_matches"] is True and info["expired"] is False
    if info["usable"]:
        info["status"] = "VALID"
    elif info["expired"] is True:
        info["status"] = "EXPIRED"
    elif info["binding_matches"] is not True:
        info["status"] = "UNBOUND" if info["binding_matches"] is False else "UNVERIFIABLE"
    else:
        info["status"] = "UNVERIFIABLE"
    return info


def _month_excess(block: Any) -> Optional[float]:
    outcome = (((block or {}).get("pick") or {}).get("outcomes") or {}).get("20") if isinstance(block, Mapping) else None
    return _finite((outcome or {}).get("excess_vs_iwm")) if isinstance(outcome, Mapping) else None


def placebo_alignment(report: Mapping) -> dict:
    """安慰剂与正式结果必须在「同样的月份」上比：两边都有已成熟 20 日结果的月份才是对齐的窗口，均值也只在这些月份上算。"""
    formal: Dict[str, float] = {}
    placebo: Dict[str, float] = {}
    for month in report.get("months") or []:
        if not isinstance(month, Mapping) or not isinstance(month.get("as_of"), str):
            continue
        for target, name in ((formal, "actual"), (placebo, "placebo")):
            value = _month_excess(month.get(name))
            if value is not None:
                target[month["as_of"]] = value
    aligned = sorted(set(formal) & set(placebo))
    out: Dict[str, Any] = {"formal_months": len(formal), "placebo_months": len(placebo), "aligned_months": len(aligned),
                           "min_windows": PROOF_MIN_PLACEBO_WINDOWS, "sufficient": len(aligned) >= PROOF_MIN_PLACEBO_WINDOWS}
    if out["sufficient"]:
        out["formal_mean_on_aligned"] = statistics.fmean(formal[m] for m in aligned)
        out["placebo_mean_on_aligned"] = statistics.fmean(placebo[m] for m in aligned)
    return out


def backtest_proof(report: Optional[Mapping], expected_binding: Optional[Mapping] = None, now: Optional[datetime] = None) -> dict:
    """(a) 回测证据。report = 私有完整回测报告（hub-backtest.json）；没有或读不懂就当没有证据。
    报告必须绑定当前规则版本与参数 sha256、且在 35 天有效期内，否则同样当没有回测证据（不含任何收益数字）。
    收益数字只在报告有效且样本外窗口 >= 6 时才写进结果：证据不足的数字在这里就不存在，不靠调用方去隐藏。"""
    out: Dict[str, Any] = {"available": False, "min_windows": PROOF_MIN_OOS_WINDOWS, "windows": None, "sufficient": False, "passed": False,
                           "usable": False, "checks": {"windows_ok": False, "beats_iwm": None, "beats_control": None, "beats_placebo": None,
                                                       "placebo_evidence_ok": None}, "generated_at": None, "validity": None, "placebo": None}
    if not isinstance(report, Mapping):
        return out
    try:
        actual = report["summary"]["actual"]["pick_20"]
        placebo = (report["summary"].get("placebo") or {}).get("pick_20") or {}
        windows = int(report.get("oos_windows", actual.get("windows", 0)) or 0)
    except (KeyError, TypeError, ValueError, AttributeError):
        return out
    validity = backtest_validity(report, expected_binding, now)
    out.update({"available": True, "windows": windows, "generated_at": report.get("generated_at"), "validity": validity,
                "usable": validity["usable"]})
    if not validity["usable"]:
        return out                                     # 过期 / 没绑定当前规则：视为没有回测证据，数字也不出
    out["sufficient"] = out["checks"]["windows_ok"] = windows >= PROOF_MIN_OOS_WINDOWS
    if not out["sufficient"]:
        return out
    formal_iwm = _finite((actual.get("excess_vs_iwm") or {}).get("mean"))
    formal_control = _finite((actual.get("excess_vs_control") or {}).get("mean"))
    summary_placebo = _finite((placebo.get("excess_vs_iwm") or {}).get("mean"))
    alignment = placebo_alignment(report)
    out["placebo"] = alignment
    out["formal_20d_vs_iwm"], out["formal_20d_vs_control"] = formal_iwm, formal_control
    out["placebo_20d_vs_iwm"] = alignment.get("placebo_mean_on_aligned") if alignment["sufficient"] else None
    out["hit_rate_20d"] = _finite((actual.get("excess_vs_iwm") or {}).get("hit_rate"))
    checks = out["checks"]
    checks["beats_iwm"] = formal_iwm is not None and formal_iwm > 0
    checks["beats_control"] = formal_control is not None and formal_control > 0
    checks["placebo_evidence_ok"] = alignment["sufficient"] and summary_placebo is not None
    checks["beats_placebo"] = bool(checks["placebo_evidence_ok"] and alignment["placebo_mean_on_aligned"] < alignment["formal_mean_on_aligned"])
    out["passed"] = all(checks[k] is True for k in ("windows_ok", "beats_iwm", "beats_control", "placebo_evidence_ok", "beats_placebo"))
    return out


def forward_proof(stats: Optional[Mapping]) -> dict:
    """(b) 前向证据。stats 来自记分簿：{settled, shadow_settled, formal_settled, hits, mean_excess}（20 日已结算的独立样本，影子 + 正式）；
    可带 raw_settled / independent_settled（说明有多少条因为不独立被挡掉）。
    样本够了（>= 8）而不达标 = 否决（vetoes_gate）：这时无论回测如何都不开门。"""
    stats = stats or {}
    settled = int(stats.get("settled") or 0)
    out: Dict[str, Any] = {"settled": settled, "shadow_settled": int(stats.get("shadow_settled") or 0), "formal_settled": int(stats.get("formal_settled") or 0),
                           "raw_settled": stats.get("raw_settled"), "excluded_not_independent": stats.get("excluded_not_independent"),
                           "min_settled": PROOF_FORWARD_MIN_SETTLED, "min_hit_rate": PROOF_FORWARD_MIN_HIT_RATE,
                           "sufficient": settled >= PROOF_FORWARD_MIN_SETTLED, "passed": False, "vetoes_gate": False,
                           "checks": {"enough_samples": settled >= PROOF_FORWARD_MIN_SETTLED, "hit_rate_ok": None, "mean_excess_positive": None}}
    if not out["sufficient"]:
        return out
    hit_rate = int(stats.get("hits") or 0) / settled
    mean_excess = _finite(stats.get("mean_excess"))
    out["hit_rate"], out["mean_excess_vs_iwm"] = hit_rate, mean_excess
    out["checks"]["hit_rate_ok"] = hit_rate >= PROOF_FORWARD_MIN_HIT_RATE - 1e-12
    out["checks"]["mean_excess_positive"] = mean_excess is not None and mean_excess > 0
    out["passed"] = all(out["checks"].values())
    out["vetoes_gate"] = not out["passed"]
    return out


def _validity_tail(validity: Optional[Mapping]) -> str:
    if not validity:
        return ""
    until = (validity.get("valid_until") or "")[:10]
    return "；报告 %s 生成、有效至 %s、已绑定当前规则版本与参数" % ((validity.get("generated_at") or "")[:10], until)


def _backtest_piece(bt: Mapping) -> str:
    if not bt["available"]:
        return "回测：还没有产出"
    validity = bt.get("validity") or {}
    if not bt["usable"]:
        why = {"EXPIRED": "报告已过期（%s 生成，有效期 %d 天）" % ((validity.get("generated_at") or "")[:10], PROOF_BACKTEST_MAX_AGE_DAYS),
               "UNBOUND": "报告对应的不是当前规则版本与参数（%s）" % "；".join(validity.get("mismatches") or []),
               }.get(validity.get("status"), "无法核对报告是否对应当前规则版本与参数")
        return "回测：%s，视为没有回测证据，不显示收益数字" % why
    if not bt["sufficient"]:
        return "回测：样本外窗口 %d/%d，样本不足，不显示收益数字" % (bt["windows"], bt["min_windows"])
    text = "回测：过去 %d 个月，20 日净超额相对 IWM %s" % (bt["windows"], signed_pct(bt["formal_20d_vs_iwm"]) if bt["formal_20d_vs_iwm"] is not None else "—")
    if bt["formal_20d_vs_control"] is not None:
        text += "、相对同档随机 %s" % signed_pct(bt["formal_20d_vs_control"])
    if bt["placebo_20d_vs_iwm"] is not None:
        text += "，安慰剂 %s" % signed_pct(bt["placebo_20d_vs_iwm"])
    elif bt.get("placebo") is not None:
        text += "，安慰剂证据不足（与正式月份对齐的有效窗口 %d/%d）" % (bt["placebo"]["aligned_months"], bt["placebo"]["min_windows"])
    return text + ("（通过" if bt["passed"] else "（未通过") + _validity_tail(validity) + "）"


def _forward_piece(fw: Mapping) -> str:
    extra = ""
    if fw.get("raw_settled") is not None and fw.get("excluded_not_independent"):
        extra = "（记分簿共已结算 %d 条，其中 %d 条与别的记录同一只股票或窗口重叠，不算独立样本）" % (fw["raw_settled"], fw["excluded_not_independent"])
    if not fw["sufficient"]:
        return "前向：已结算的独立样本 %d/%d 条，样本不足，不显示收益数字%s" % (fw["settled"], fw["min_settled"], extra)
    text = "前向：已结算独立样本 %d 条，命中率 %.0f%%" % (fw["settled"], fw["hit_rate"] * 100)
    if fw["mean_excess_vs_iwm"] is not None:
        text += "、平均超额 %s" % signed_pct(fw["mean_excess_vs_iwm"])
    return text + ("（通过）" if fw["passed"] else "（未通过，一票否决）") + extra


def _closed_headline(bt: Mapping, fw: Optional[Mapping] = None) -> str:
    tail = "在它证明自己之前不给建议。"
    if fw is not None and fw.get("vetoes_gate"):
        return ("这套选股规则上线后的前向成绩不达标：已结算 %d 个独立样本，命中率 %.0f%%、平均超额 %s（要求命中率 >= %d%% 且平均超额为正），"
                "前向成绩一票否决，无论回测怎样，%s" % (fw["settled"], fw["hit_rate"] * 100,
                                                  "—" if fw["mean_excess_vs_iwm"] is None else signed_pct(fw["mean_excess_vs_iwm"]),
                                                  int(PROOF_FORWARD_MIN_HIT_RATE * 100), tail))
    if bt["available"] and not bt["usable"]:
        status = (bt.get("validity") or {}).get("status")
        if status == "EXPIRED":
            return "这套选股规则的回测报告已经过了 %d 天有效期，不能再当证据，也还没有前向成绩，%s" % (PROOF_BACKTEST_MAX_AGE_DAYS, tail)
        return "这套选股规则现在的版本或参数，和当初跑回测时的不一致（或无法核对），旧回测不算证据，也还没有前向成绩，%s" % tail
    if bt["sufficient"]:
        n, iwm = bt["windows"], bt["formal_20d_vs_iwm"]
        if not bt["checks"]["beats_iwm"]:
            verb = "平均跑输" if (iwm is not None and iwm < 0) else "平均没有跑赢"
            return "这套选股规则在过去 %d 个月的回测里%s小盘基准 IWM（20 日 %s），%s" % (n, verb, "—" if iwm is None else signed_pct(iwm), tail)
        if not bt["checks"]["beats_control"]:
            ctrl = bt["formal_20d_vs_control"]
            return "这套选股规则在过去 %d 个月的回测里虽然平均跑赢了 IWM（20 日 %s），但没有跑赢同市值档的随机抽样（%s），%s" % (
                n, signed_pct(iwm), "—" if ctrl is None else signed_pct(ctrl), tail)
        if not bt["checks"]["placebo_evidence_ok"]:
            aligned = (bt.get("placebo") or {}).get("aligned_months", 0)
            return "这套选股规则在过去 %d 个月的回测里（20 日 %s）虽然跑赢了基准，但安慰剂对照只有 %d 个与正式月份对齐的有效窗口（至少要 %d 个），安慰剂证据不足，%s" % (
                n, signed_pct(iwm), aligned, PROOF_MIN_PLACEBO_WINDOWS, tail)
        placebo = bt["placebo_20d_vs_iwm"]
        return "这套选股规则在过去 %d 个月的回测里（20 日 %s）并不比把事件日期后移 60 个交易日的安慰剂（%s）更好，成绩不像来自规则本身，%s" % (
            n, signed_pct(iwm), "—" if placebo is None else signed_pct(placebo), tail)
    if bt["available"]:
        return "这套选股规则的回测只有 %d 个样本外月份（至少要 %d 个才算数），还没有被证明，%s" % (bt["windows"], bt["min_windows"], tail)
    return "这套选股规则还没有可用的回测，也没有前向成绩，还没有被证明，" + tail


def proof_gate(backtest_report: Optional[Mapping] = None, forward_stats: Optional[Mapping] = None, *,
               expected_binding: Optional[Mapping] = None, now: Optional[datetime] = None) -> dict:
    """规则自证门：(a) 回测证据 或 (b) 前向证据 满足任一即开；但前向证据够样本而不达标时一票否决。纯函数。

    expected_binding：线上当前的规则绑定（rule_binding()）；now：当前时间（判有效期）。不给就核对不了，回测证据一律不成立。"""
    now = now.astimezone(timezone.utc) if now is not None else None
    bt, fw = backtest_proof(backtest_report, expected_binding, now), forward_proof(forward_stats)
    veto = bool(fw["vetoes_gate"])
    opened_by = [] if veto else [name for name, part in (("BACKTEST", bt), ("FORWARD", fw)) if part["passed"]]
    is_open = bool(opened_by)
    pieces = "；".join((_backtest_piece(bt), _forward_piece(fw)))
    reasons: List[str] = []
    if veto:
        reasons.append("前向成绩一票否决：已结算的独立样本 %d 条，命中率 %.0f%%（要求 >= %d%%），平均超额 %s（要求为正）。无论回测怎样都不开门。" % (
            fw["settled"], fw["hit_rate"] * 100, int(PROOF_FORWARD_MIN_HIT_RATE * 100),
            "—" if fw["mean_excess_vs_iwm"] is None else signed_pct(fw["mean_excess_vs_iwm"])))
    if not bt["passed"]:
        validity = bt.get("validity") or {}
        if not bt["available"]:
            reasons.append("回测还没有产出。")
        elif not bt["usable"]:
            for line in validity.get("mismatches") or []:
                reasons.append("回测报告与当前规则不一致：%s。" % line)
            if validity.get("expired") is True:
                reasons.append("回测报告生成于 %s，已超过 %d 天有效期，视为没有回测证据。" % ((validity.get("generated_at") or "")[:10], PROOF_BACKTEST_MAX_AGE_DAYS))
            elif validity.get("expired") is None:
                reasons.append("回测报告的生成时间读不出或没有当前时间，无法核对有效期。")
        elif not bt["sufficient"]:
            reasons.append("回测样本外窗口只有 %d 个，少于 %d 个，不足以证明规则有信息量。" % (bt["windows"], bt["min_windows"]))
        else:
            checks = bt["checks"]
            if not checks["beats_iwm"]:
                reasons.append("正式结果相对 IWM 没有正超额（20 日 %s）。" % ("—" if bt["formal_20d_vs_iwm"] is None else signed_pct(bt["formal_20d_vs_iwm"])))
            if not checks["beats_control"]:
                reasons.append("正式结果没有跑赢同档随机抽样（%s）。" % ("—" if bt["formal_20d_vs_control"] is None else signed_pct(bt["formal_20d_vs_control"])))
            if not checks["placebo_evidence_ok"]:
                reasons.append("安慰剂证据不足：与正式月份对齐的有效窗口只有 %d 个，少于 %d 个。" % ((bt.get("placebo") or {}).get("aligned_months", 0), PROOF_MIN_PLACEBO_WINDOWS))
            elif not checks["beats_placebo"]:
                reasons.append("安慰剂（事件后移 60 个交易日）%s，不低于正式结果，说明成绩不像来自规则本身。" % (
                    "—" if bt["placebo_20d_vs_iwm"] is None else signed_pct(bt["placebo_20d_vs_iwm"])))
    if not fw["passed"] and not veto:
        reasons.append("前向影子候选已结算的独立样本 %d 条，少于 %d 条，样本不足。" % (fw["settled"], fw["min_settled"]))
    return {
        "schema": PROOF_GATE_SCHEMA, "open": is_open, "opened_by": opened_by, "state": "OPEN" if is_open else "CLOSED", "rule": PROOF_GATE_RULE,
        "vetoed_by": ["FORWARD"] if veto else [], "backtest": bt, "forward": fw, "reasons": [] if is_open else reasons,
        "headline": None if is_open else _closed_headline(bt, fw), "evidence": pieces,
        "line": ("规则自证门：开。依据（%s）。" if is_open else "规则自证门：关。%s。") % (
            "、".join({"BACKTEST": "回测", "FORWARD": "前向"}[x] for x in opened_by) + "达标：" + pieces if is_open else pieces),
    }


def missing_proof_gate() -> dict:
    """调用方没有给证据：按证据不足处理，门关着（不因为没传参数而放行）。"""
    return proof_gate(None, None)


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
    order = (("veto", "一票否决"), ("support", "支持度"), ("quote", "实时报价"), ("liquidity", "流动性"), ("pool", "候选池"), ("proof", "规则自证门"))
    for key, name in order:
        gate = row["gates"].get(key)
        if gate is not None and gate["ok"] is False:
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


CANDIDATE_GATES = ("pool", "quote", "liquidity", "veto", "support")


def decide(research: ResearchView, market: Mapping[str, Mapping[str, Any]], *, now: datetime,
           liquidity_fn: Optional[Liquidity] = None, weights: Optional[Mapping[str, Any]] = None,
           state: Optional[Mapping] = None, quotes_available: bool = True, proof: Optional[Mapping] = None) -> dict:
    """返回 {decision, candidates, state, weights}。纯函数：同样的输入得到同样的输出。

    proof：规则自证门（proof_gate() 的结果）。不传等于「没有证据」，门关着——不会因为漏传参数而放行建议。"""
    now = now.astimezone(timezone.utc)
    weights = dict(weights or branch_weights(None))
    proof = dict(proof) if proof is not None else missing_proof_gate()
    blocked = system_block(research, now, quotes_available=quotes_available)
    if blocked is not None:
        return {"decision": blocked, "candidates": [], "state": deepcopy(dict(state or {})), "weights": weights}

    new_state = refresh_state(state, research, now)
    invalidated = {s: r for s, r in new_state.get("published", {}).items() if r.get("status") == "INVALIDATED"}
    chain = data_chain(research, now)
    environment = {"regime": research.environment.get("regime"), "note": research.environment.get("note"),
                   "role": "MARKET_ENVIRONMENT_INPUT_NOT_STOCK_PICKING"}

    rows, summaries, winner = rank_candidates(research, market, weights, invalidated, liquidity_fn)

    # 第六道门：规则自证门。它不属于逐股的门（回测重放的是逐股规则本身），只在这里、在发布这一步拦。
    proof_detail = proof["line"] if proof["open"] else "规则还没证明自己有信息量，暂不发布（依据见首屏「规则自证门」）"
    for row in rows:
        row["gates"]["proof"] = {"ok": bool(proof["open"]), "detail": proof_detail}
    candidates = [_candidate_view(research, summaries[row["symbol"]], row, market) for row in rows]
    for rank, view in enumerate(candidates, 1):
        view["rank"] = rank

    gate_closed = not proof["open"]
    # 门关着：唯一建议不发布，观察名单就是候选前 5（含「如果发布会选谁」那一只）；门开着：名单不含被选中的那一只。
    watch_source = candidates if gate_closed else [c for c in candidates if not (winner is not None and c["symbol"] == winner["symbol"])]
    watchlist = [_watch_view(c, shadow=gate_closed and winner is not None and c["symbol"] == winner["symbol"]) for c in watch_source[:WATCHLIST_SIZE]]
    qualifying = sum(1 for c in candidates if c["passes_candidate_gates"])
    common = {"qualifying_candidates": qualifying, "weights_mode": weights["mode"], "data_chain": chain, "market_environment": environment, "support_rule": SUPPORT_RULE,
              "weight_formula": WEIGHT_FORMULA, "publish_threshold": PUBLISH_THRESHOLD, "proof_gate": proof,
              "not_wired_vetoes": deepcopy(NOT_WIRED_VETOES),
              "invalidated_recommendations": [_published_view(s, r) for s, r in sorted(invalidated.items())]}

    if winner is None or gate_closed:
        best = candidates[0] if candidates else None
        why = ("候选 %d 只，没有一只同时满足「支持度合计 >= %.1f」和全部硬门。" % (len(candidates), PUBLISH_THRESHOLD)
               + ("离发布最近的是 %s（%s）。" % (best["symbol"], best["gate_summary"]) if best else ""))
        shadow = None
        if gate_closed and winner is not None:
            shadow = _shadow_view(research, summaries[winner["symbol"]], next(c for c in candidates if c["symbol"] == winner["symbol"]), market, proof)
        decision = {"state": "NO_ACTION", "action": None, "action_code": ACTION_CODES["NO_ACTION"], "primary_symbol": None,
                    "no_action_cause": "PROOF_GATE_CLOSED" if gate_closed else "NO_QUALIFYING_CANDIDATE",
                    "rationale": proof["headline"] if gate_closed else why, "candidate_note": why,
                    "reasons": [], "sources": [], "conflicts": [], "invalidation": None,
                    "watchlist": watchlist, "candidates_evaluated": len(candidates), "shadow_candidate": shadow,
                    "shadow_note": None if shadow else ("今天没有候选同时满足发布条件，所以今天没有影子候选。" if gate_closed else None), **common}
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
        "passes_candidate_gates": all(row["gates"][k]["ok"] for k in CANDIDATE_GATES),
        "branch_kinds": {i["branch_id"]: i["kind"] for i in summary["all"]},
        "failed_gate": failed_name, "gate_summary": ("差在【%s】：%s%s" % (failed_name, failed_detail, "；这只股本身的其余门都过了" if failed_name == "规则自证门" else "")) if failed_name else "全部门通过（与唯一建议同分，平局按事件新近度排在后面）",
        "links": [x["url"] for i in summary["counted"] for x in i["links"][:1]] or _any_sec_link(research, symbol),
        "latest_event_date": summary["latest_event_date"],
    }


def _any_sec_link(research: ResearchView, symbol: str) -> List[str]:
    """没有分支给出可计分的支持时，观察名单仍要给一条 SEC 原文：取任一分支对这只股引用的第一条。"""
    for branch in STOCK_BRANCHES:
        record = research.verdict(branch, symbol)
        for link in (record or {}).get("links") or []:
            if is_sec_link(link):
                return [link["url"]]
    return []


def _watch_view(candidate: Mapping, *, shadow: bool = False) -> dict:
    """观察名单一行：支持它的分支、差在哪一道门、一条 SEC 原文。shadow = 这一只是「如果发布会选它」的影子候选。"""
    return {"symbol": candidate["symbol"], "name": candidate["name"], "market_cap_usd": candidate.get("market_cap_usd"),
            "support_total": candidate["support_total"], "failed_gate": candidate["failed_gate"], "sentence": candidate["gate_summary"],
            "links": candidate["links"][:2], "scores": candidate["scores"], "price": candidate["price"],
            "support_branches": [{"branch_id": b["branch_id"], "label": b["label"], "kind": b["kind"]} for b in candidate["support_branches"]],
            "is_shadow_candidate": shadow}


def _shadow_view(research: ResearchView, summary: Mapping, candidate: Mapping, market: Mapping[str, Mapping], proof: Mapping) -> dict:
    """影子候选：规则自证门关着时，「如果发布，会选谁」。只记录、不发布。"""
    symbol = candidate["symbol"]
    entry = research.pool.get(symbol) or {}
    reasons = [{"branch_id": i["branch_id"], "label": i["label"], "kind": i["kind"], "sentence": i["sentence"],
                "link": i["links"][0]["url"] if i["links"] else None} for i in summary["counted"]]
    sources: List[dict] = []
    for item in summary["counted"]:
        for link in item["links"][:2]:
            if link["url"] not in {x["url"] for x in sources}:
                sources.append({"url": link["url"], "branch_id": item["branch_id"], "summary": link.get("summary") or link.get("label"),
                                "published_date": link.get("published_date") or link.get("filed")})
    return {"symbol": symbol, "name": entry.get("name") or candidate.get("name"), "market_cap_usd": candidate.get("market_cap_usd"),
            "price": (market.get(symbol) or {}).get("price"), "support_total": summary["total"],
            "support_branches": [{"branch_id": i["branch_id"], "label": i["label"], "kind": i["kind"], "raw": i["raw"], "weight": i["weight"],
                                  "weighted": i["weighted"]} for i in summary["counted"]],
            "reasons": reasons, "sources": sources,
            "sentence": "今天如果发布，会是 %s（%s）：%s。" % (symbol, entry.get("name") or candidate.get("name") or "", "；".join(r["sentence"] for r in reasons)),
            "why_not_published": "规则自证门没开，只记录、不发布：" + (proof.get("headline") or ""), "publishable_if_gate_opens": True,
            "gates": candidate["gates"]}
