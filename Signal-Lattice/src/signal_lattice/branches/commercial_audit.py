"""商业机会分支覆盖率审计（只读研究层产物，不联网、不改任何判定）。

用法（verdicts 文件是研究层落盘的 <out_dir>/<as_of>/stock-commercial-opportunities/verdicts-<hash>.json）：
  python -m signal_lattice.branches.commercial_audit VERDICTS.json [--before OLD_VERDICTS.json]

输出：PASS/ABSTAIN/FAILED 计数、状态分布、decision_score 分布（分位与最高分离 65 差多少）、
18 个因子各自的 NO_EVIDENCE 占比（读分支 meta.factor_no_evidence；旧版产物没有这项会明说）、前 10 名的卡点。
给了 --before 时并排给出前后对比。本工具不重算任何分数。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

WATCHLIST_BELOW = 65.0      # 仅用于「离门槛差多少」的展示；判定以分支自己的 params 为准


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def summarize(doc: dict) -> dict:
    verdicts: List[dict] = doc["verdicts"]
    scores = [v["score"] for v in verdicts if v.get("score") is not None]
    quantiles = [round(x, 1) for x in statistics.quantiles(scores, n=10)] if len(scores) >= 2 else []
    top = sorted(verdicts, key=lambda v: -(v.get("rank_key") or 0))[:10]
    return {
        "universe": len(verdicts),
        "verdict": dict(Counter(v["verdict"] for v in verdicts)),
        "label": dict(Counter(v["label"] for v in verdicts)),
        "score_deciles": quantiles,
        "score_max": round(max(scores), 2) if scores else None,
        "pass": [{"symbol": v["symbol"], "score": v["score"], "links": [x["url"] for x in v.get("links", [])]}
                 for v in verdicts if v["verdict"] == "PASS"],
        "top10": [{"symbol": v["symbol"], "score": v["score"], "label": v["label"],
                   "blockers": [r for r in v.get("reasons", []) if r.split(":")[0] in (
                       "DECISION_SCORE_BELOW_DILIGENCE", "DECISION_SCORE_BELOW_SCREEN_FLAG", "CONFIDENCE_BELOW_MIN",
                       "BASE_COVERAGE_BELOW_FLOOR", "BASE_REQUIRED_DIMENSION_NO_EVIDENCE")]} for v in top],
        "factor_no_evidence": (doc.get("meta") or {}).get("factor_no_evidence"),
        "fundamentals_profile": (doc.get("meta") or {}).get("fundamentals_profile"),
    }


def render(summary: dict, before: Optional[dict] = None) -> str:
    out: List[str] = []
    add = out.append
    add("候选池 %d 只；口径 %s" % (summary["universe"], summary["fundamentals_profile"] or "旧版产物（无 profile 标记）"))
    add("结论：%s" % json.dumps(summary["verdict"], ensure_ascii=False))
    if before:
        add("  修改前：%s" % json.dumps(before["verdict"], ensure_ascii=False))
    add("状态：%s" % json.dumps(summary["label"], ensure_ascii=False))
    add("decision_score 十分位：%s；最高 %s（门槛 %.0f，差 %s）" % (
        summary["score_deciles"], summary["score_max"], WATCHLIST_BELOW,
        "n/a" if summary["score_max"] is None else round(WATCHLIST_BELOW - summary["score_max"], 1)))
    if before:
        add("  修改前十分位：%s；最高 %s" % (before["score_deciles"], before["score_max"]))
    table = summary["factor_no_evidence"]
    if table is None:
        add("因子 NO_EVIDENCE 占比：这份产物没有 meta.factor_no_evidence（旧版研究层产物）")
    else:
        old = (before or {}).get("factor_no_evidence") or {}
        for group in ("base", "risk"):
            add("因子 NO_EVIDENCE 占比（%s）：" % ("基础分 10 维" if group == "base" else "风险扣分 8 项"))
            for name, ratio in table[group].items():
                prev = old.get(group, {}).get(name)
                add("  %-30s %5.1f%%%s" % (name, ratio * 100, "" if prev is None else "   (修改前 %.1f%%)" % (prev * 100)))
    add("PASS %d 只%s" % (len(summary["pass"]), "：" if summary["pass"] else "（照实：0 只通过）"))
    for item in summary["pass"]:
        add("  %s score=%s %s" % (item["symbol"], item["score"], " ".join(item["links"][:3])))
    add("前 10 名与卡点：")
    for item in summary["top10"]:
        add("  %-6s %-10s %s  %s" % (item["symbol"], item["label"], item["score"], ",".join(item["blockers"]) or "-"))
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("verdicts", type=Path)
    parser.add_argument("--before", type=Path, default=None, help="修改前的 verdicts 文件，用于并排对比")
    args = parser.parse_args(argv)
    print(render(summarize(load(args.verdicts)), summarize(load(args.before)) if args.before else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
