"""把事件航图与文本比对的结果渲染成一份可核对的文字报告（计数、基准、结论、前 10、链接）。

    python -m signal_lattice.branches.event_atlas_report --run-dir DIR --as-of 2026-09-29
读取 event-atlas-<日期>.json、text-similarity-<日期>.json 与 events.sqlite，只做汇总，不重新判定。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

from ..evidence.eventstore import EventStore
from ..evidence.insiders import classified_buys


def _pct(value: float) -> str:
    return "%.0f%%" % (value * 100)


def _usd_m(value: float) -> str:
    return "$%.0fM" % (value / 1e6)


def insider_bucket_counts(store: EventStore, as_of: str, days: int, min_usd: float, offering_like: int) -> dict:
    since = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()
    kept, excluded = classified_buys(store, as_of, since, None, min_usd, offering_like)
    counts = Counter(row["classification"] for row in kept)
    return {"opportunistic": counts["OPPORTUNISTIC"], "routine": counts["ROUTINE"],
            "unclassifiable": counts["UNCLASSIFIABLE"], "excluded_10b5_1": excluded["PLAN_10B5_1"],
            "excluded_below_min": excluded["BELOW_MIN_AMOUNT"],
            "excluded_offering_like": excluded["OFFERING_LIKE"]}


def render(atlas: dict, store: EventStore, text: Optional[dict], min_usd: float = 25_000.0, top_n: int = 10,
           offering_like: int = 4) -> str:
    as_of = atlas["as_of"]
    since = (date.fromisoformat(as_of) - timedelta(days=365)).isoformat()
    lines: List[str] = ["事件航图  as_of=%s  参数版本=%s" % (as_of, atlas["params_version"]), ""]
    family_counts: Counter = Counter()
    kind_counts: Counter = Counter()
    for event in atlas["events"]:
        if event["published_date"] >= since:
            family_counts[event["family"]] += 1
            kind_counts[(event["family"], event["kind"])] += 1
    lines.append("一、近 12 个月（%s ~ %s）事件采集计数" % (since, as_of))
    for family, total in sorted(family_counts.items()):
        lines.append("  %-20s %6d" % (family, total))
        for (fam, kind), count in sorted(kind_counts.items()):
            if fam == family:
                lines.append("      %-30s %6d" % (kind, count))
    buckets = insider_bucket_counts(store, as_of, 365, min_usd, offering_like)
    lines += ["", "二、内部人买入分类（近 12 个月，代码 P、非 10b5-1、单人单份 >= $%d）" % min_usd,
              "  机会型 %(opportunistic)d | 例行型 %(routine)d | 无法分类（历史不足3年）%(unclassifiable)d"
              " | 另剔除：10b5-1 计划 %(excluded_10b5_1)d，小额 %(excluded_below_min)d，疑似发行认购 %(excluded_offering_like)d" % buckets]
    lines += ["", "三、各事件类历史基准（研究窗口 %s ~ %s；相对 IWM 超额收益；Bull/Base/Bear 分界=随机对照三分位）" % (
        atlas["event_start"], as_of)]
    if not atlas["benchmark_available"]:
        lines.append("  没有 IWM 日线，无法做事件研究")
    header = "  %-30s %-4s %5s %-8s %-30s %s"
    lines.append(header % ("事件类", "持有", "样本", "置信度", "Bull/Base/Bear（90%区间）", "超额收益 中位数 [p33, p67]"))
    for kind, entry in sorted(atlas["study"].items()):
        for horizon, block in sorted(entry["horizons"].items(), key=lambda item: int(item[0])):
            if block.get("status") != "OK":
                lines.append(header % (kind, horizon + "日", block["n"], "-", "样本不足，不出概率" if block.get("status") == "样本不足" else block.get("status"), ""))
                continue
            prob, interval = block["probability"], block["probability_interval"]
            cell = " / ".join("%s[%s-%s]" % (_pct(prob[k]), _pct(interval[k][0]), _pct(interval[k][1])) for k in ("bull", "base", "bear"))
            lines.append(header % (kind, horizon + "日", block["n"], block["confidence"], cell,
                                   "%+.1f%% [%+.1f%%, %+.1f%%]" % (block["median_excess"] * 100, block["excess_p33"] * 100, block["excess_p67"] * 100)))
    verdicts = atlas["verdicts"]
    counts = Counter(v["verdict"] for v in verdicts)
    flagged = sum(1 for v in verdicts if v["invalidation_risk"])
    lines += ["", "四、结论计数（候选池 %d 家）：PASS %d | ABSTAIN %d | FAILED %d；带失效风险标记 %d 家" % (
        len(verdicts), counts["PASS"], counts["ABSTAIN"], counts["FAILED"], flagged)]
    passes = sorted((v for v in verdicts if v["verdict"] == "PASS"), key=lambda v: (-v["score"], v["symbol"]))[:top_n]
    lines.append("  PASS 前 %d 名（按机会型买入强度）：" % top_n)
    for rank, verdict in enumerate(passes, 1):
        first = verdict["evidence"][0]
        window = verdict["insider_window"]
        lines.append("  %2d. %-6s %s | 市值 %s | 得分 %.1f" % (rank, verdict["symbol"], verdict["name"], _usd_m(verdict["market_cap_usd"]), verdict["score"]))
        lines.append("      事件：%s（近%d天机会型内部人 %d 位，合计 $%.0f，占市值 %.3f%%）%s" % (
            first["summary"], window["window_days"], window["opportunistic_insiders"], window["opportunistic_amount_usd"],
            (window["pct_of_market_cap"] or 0) * 100, "；失效风险：" + ",".join(verdict["invalidation_risk"]) if verdict["invalidation_risk"] else ""))
        lines.append("      SEC 原文：%s" % first["url"])
    if text is not None:
        cov = text["coverage"]
        records = text["records"]
        big = sorted((r for r in records if r["big_changer"]), key=lambda r: r["similarity"])
        lines += ["", "五、文本比对（Lazy Prices）覆盖：候选池 %d 家，抽样 %d 家，成功比对 %d 家（覆盖率 %.1f%%），跳过 %d 家（缺同类上期申报或正文取不到）" % (
            cov["pool"], cov["sampled"], cov["computed"], cov["computed"] / cov["pool"] * 100, cov["skipped"]),
            "  大改动者（同类申报相似度最低 20%%）共 %d 家；相似度最低的前 %d：" % (len(big), top_n)]
        for rank, record in enumerate(big[:top_n], 1):
            lines.append("  %2d. %-6s %s | %s | 相似度 %.3f（分位 %s）| 变化最大：%s" % (
                rank, record["symbol"], record["name"], record["form"], record["similarity"], _pct(record["percentile"]),
                record.get("largest_change_section") or "未定位到风险因素/法律诉讼段"))
            lines.append("      本期 %s  上期 %s" % (record["url"], record["prior_url"]))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_lattice.branches.event_atlas_report")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--db", default="events.sqlite")
    args = parser.parse_args(argv)
    atlas = json.loads((args.run_dir / ("event-atlas-%s.json" % args.as_of)).read_text("utf-8"))
    text_path = args.run_dir / ("text-similarity-%s.json" % args.as_of)
    text = json.loads(text_path.read_text("utf-8")) if text_path.is_file() else None
    from .event_atlas import load_params

    insider = load_params()["insider"]
    print(render(atlas, EventStore(args.run_dir / args.db), text, float(insider["min_purchase_usd"]),
                 offering_like=int(insider["offering_like_min_buyers"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
