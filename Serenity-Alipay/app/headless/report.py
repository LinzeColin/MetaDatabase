"""云端无人值守的正式报告：Markdown（GitHub Release 正文/资产）+ 自包含 HTML。

只依赖一次运行的结果字典和数据健康度字典，因此发布失败后可以不重算直接重发。
没有真实持仓快照时如实写「持仓快照：暂无」，不出“当前 vs 目标”偏离与增减配动作。
"""

from __future__ import annotations

import html
import re
from datetime import datetime

from app.core.reporting import _zh_compare_type, _zh_reason

WINDOW_LABELS = (("1m", "近1月"), ("3m", "近3月"), ("12m", "近1年"), ("10d", "近10交易日"))
GRADE_ZH = {"Action-Ready": "可执行", "Watch": "观察", "Manual Review": "人工复核", "Block": "阻断"}
DATA_ZH = {"pass": "通过", "degraded": "降级", "manual_review": "人工复核", "block": "阻断"}
_CJK = re.compile(r"[一-鿿]")


def pct(value: object, signed: bool = False) -> str:
    if value is None:
        return "缺失"
    number = float(value)  # type: ignore[arg-type]
    return f"{number:+.2%}" if signed else f"{number:.2%}"


def _cell(value: object) -> str:
    return str(value).replace("|", "／").replace("\n", " ")


def reason_zh(text: object) -> str:
    raw = str(text or "")
    return raw if _CJK.search(raw) else _zh_reason(raw)


def _slot_label(result: dict[str, object], slot: str) -> str:
    stamp = datetime.fromisoformat(str(result["run_time_bj"]))
    return f"{stamp:%Y-%m-%d} {slot} 档（{stamp:%H:%M} 北京时间）"


def _wins(returns: dict[str, float | None], bench: dict[str, float | None]) -> str:
    total = 0
    won = 0
    for key, _ in WINDOWS_ORDER:
        value, base = returns.get(key), bench.get(key)
        if value is None or base is None:
            continue
        total += 1
        won += int(value > base)
    return f"{won}/{total}" if total else "缺失"


WINDOWS_ORDER = WINDOW_LABELS


def _screening_summary(screening: list[dict[str, object]]) -> tuple[dict[str, int], list[dict[str, object]]]:
    buckets = {
        "回撤 ≥ 40%": 0,
        "回撤修复 ≥ 365 天": 0,
        "净值不足 24 个月": 0,
        "风险指标纪律剔除（连续多日指标负项过多）": 0,
        "保守类/已排除": 0,
        "评分或证据不足": 0,
        "通过硬规则": 0,
    }
    blocked: list[dict[str, object]] = []
    for row in screening:
        reason = str(row.get("hard_block_reason") or "")
        if row.get("grade") != "Block" and not reason.startswith(("max_drawdown", "recovery_time_days")):
            buckets["通过硬规则"] += 1
            continue
        trigger = str(row.get("trigger_reason") or "")
        if reason.startswith("max_drawdown"):
            buckets["回撤 ≥ 40%"] += 1
        elif reason.startswith("recovery_time_days"):
            buckets["回撤修复 ≥ 365 天"] += 1
        elif reason.startswith("nav_history_span_days"):
            buckets["净值不足 24 个月"] += 1
        elif "指标负项" in reason or "指标负项" in trigger:
            buckets["风险指标纪律剔除（连续多日指标负项过多）"] += 1
        elif "conservative" in reason or "excluded" in reason:
            buckets["保守类/已排除"] += 1
        else:
            buckets["评分或证据不足"] += 1
        blocked.append(row)
    return buckets, blocked


def render_report(result: dict[str, object], health: dict[str, object], *, slot: str) -> str:
    recs: list[dict[str, object]] = list(result["recommendations"])  # type: ignore[arg-type]
    top5 = [r for r in recs if int(r["rank"]) <= 5]  # type: ignore[call-overload]
    bench: dict[str, dict[str, float | None]] = result["benchmark_returns"]  # type: ignore[assignment]
    sh, sp = bench.get("Shanghai Composite", {}), bench.get("S&P 500", {})
    degraded = health.get("status") != "ok" or result.get("data_quality_status") == "degraded"
    first_round = result.get("reference_mode") == "zero_start_first_baseline"
    lines: list[str] = [
        f"# Serenity 每日分析 · {_slot_label(result, slot)}",
        "",
        "> 研究用途：只输出候选筛选、目标权重和纪律标签，**不自动买卖、不提交申购赎回**；不承诺未来跑赢沪指或标普 500。",
        "",
        "## 一句话结论",
        "",
    ]
    if top5:
        names = "、".join(f"{r['asset_name']}（{r['asset_code']}）" for r in top5)
        lines.append(f"- 本轮 Top5：{names}。")
    else:
        lines.append("- 本轮没有通过硬规则的候选，Top5 为空。")
    if degraded:
        lines.append("- **数据状态：降级**。下面的结论只作参考，请先看「数据来源与新鲜度」里的原因。")
    else:
        lines.append("- 数据状态：正常（基金净值、上证综指、标普 500 本轮均已刷新）。")
    lines.extend(
        [
            "- 持仓快照：**暂无**。没有真实持仓，所以本报告不含「当前持仓与目标的偏离」和增配/减配动作；只给候选池与目标权重。",
            f"- 运行时间：{datetime.fromisoformat(str(result['run_time_bj'])):%Y-%m-%d %H:%M} 北京 / {datetime.fromisoformat(str(result['run_time_au'])):%Y-%m-%d %H:%M} 悉尼；运行编号 `{result['run_id']}`。",
            "",
            "## Top5 候选池与目标权重",
            "",
            "| 排名 | 基金 | 等级 | 评分 | 目标权重 | 较上轮 | 近1月 | 近3月 | 近1年 | 最大回撤 | 净值日期 | 说明 |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in top5:
        metrics = row.get("metrics") or {}
        returns = metrics.get("returns") or {}
        delta = "首轮" if first_round else pct(float(row["target_weight"]) - float(row["current_weight"]), signed=True)  # type: ignore[arg-type]
        lines.append(
            "| {rank} | {name}（{code}） | {grade} | {score:.1f} | {target} | {delta} | {m1} | {m3} | {y1} | {mdd} | {nav} | {why} |".format(
                rank=row["rank"],
                name=_cell(row["asset_name"]),
                code=row["asset_code"],
                grade=GRADE_ZH.get(str(row["grade"]), str(row["grade"])),
                score=float(row["score"]),  # type: ignore[arg-type]
                target=pct(row["target_weight"]),
                delta=delta,
                m1=pct(returns.get("1m")),
                m3=pct(returns.get("3m")),
                y1=pct(returns.get("12m")),
                mdd=pct(metrics.get("max_drawdown")),
                nav=metrics.get("nav_date") or "缺失",
                why=_cell(reason_zh(row.get("trigger_reason"))),
            )
        )
    if not top5:
        lines.append("| - | 本轮无候选 | - | - | - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "怎么读：排名先看 Serenity 候选主表的优先级，再用评分微调；单只目标权重上限 30%；官方来源不足 2 个、净值不足 24 个月、回撤触发硬规则的基金不会进「可执行」。",
            "",
            "## 与上证综指、标普 500 对比",
            "",
            "| 对象 | 近1月 | 近3月 | 近1年 | 近10交易日 | 跑赢沪指窗口 | 跑赢标普窗口 |",
            "|---|---:|---:|---:|---:|---:|---:|",
            "| 上证综指 | {} | {} | {} | {} | - | - |".format(*[pct(sh.get(k)) for k, _ in WINDOW_LABELS]),
            "| 标普 500 | {} | {} | {} | {} | - | - |".format(*[pct(sp.get(k)) for k, _ in WINDOW_LABELS]),
        ]
    )
    for row in top5:
        returns = (row.get("metrics") or {}).get("returns") or {}
        lines.append(
            "| {name}（{code}） | {} | {} | {} | {} | {} | {} |".format(
                *[pct(returns.get(k)) for k, _ in WINDOW_LABELS],
                _wins(returns, sh),
                _wins(returns, sp),
                name=_cell(row["asset_name"]),
                code=row["asset_code"],
            )
        )
    buckets, blocked = _screening_summary(result["screening"])  # type: ignore[arg-type]
    lines.extend(
        [
            "",
            "## 硬规则筛选",
            "",
            f"候选共 {result['candidate_count']} 只（含自动扩容 {result.get('universe_added', 0)} 只）。规则：最大回撤 ≥ 40.00% 拦截；回撤修复 ≥ 365 天降级；净值历史必须 ≥ 24 个月。",
            "",
            "| 结果 | 数量 |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| {name} | {count} |" for name, count in buckets.items())
    if blocked:
        lines.extend(["", "被拦截/降级的基金（最多列 15 只）：", "", "| 基金 | 最大回撤 | 修复天数 | 净值跨度(天) | 原因 |", "|---|---:|---:|---:|---|"])
        for row in blocked[:15]:
            lines.append(
                "| {name}（{code}） | {mdd} | {rec} | {span} | {why} |".format(
                    name=_cell(row["asset_name"]),
                    code=row["asset_code"],
                    mdd=pct(row.get("max_drawdown")),
                    rec="缺失" if row.get("recovery_time_days") is None else row["recovery_time_days"],
                    span="缺失" if row.get("history_span_days") is None else row["history_span_days"],
                    why=_cell(reason_zh(row.get("hard_block_reason") or row.get("trigger_reason"))),
                )
            )
    lines.extend(["", "## 与上一轮、前一日、前一周、前一月的变化", "", "| 对比口径 | 对比运行 | 上轮 Top5 | 本轮 Top5 | 变动率 | 新增 | 替换 |", "|---|---|---|---|---:|---:|---:|"])
    for item in result["comparison_summaries"]:  # type: ignore[union-attr]
        lines.append(
            "| {kind} | {base} | {old} | {new} | {rate} | {added} | {replaced} |".format(
                kind=_zh_compare_type(item["compare_type"]),
                base=f"`{item['base_run_id']}`" if item.get("base_run_id") else "无（没有可比的通过运行）",
                old=", ".join(item.get("old_top5") or []) or "无",
                new=", ".join(item.get("new_top5") or []) or "无",
                rate=pct(item.get("top5_change_rate")),
                added=item.get("new_count", 0),
                replaced=item.get("replacement_count", 0),
            )
        )
    events = [reason_zh(e) for e in result.get("rebalance_events") or []]
    lines.extend(["", "Top5 变化提示：" + ("；".join(dict.fromkeys(events)) if events else "未触发变化阈值。")])
    lines.extend(["", "## 数据来源与新鲜度", "", "| 来源 | 本轮抓取 | 最新数据日期 | 说明 |", "|---|---|---|---|"])
    for source in health.get("sources") or []:  # type: ignore[union-attr]
        state = "成功" if source["ok"] else ("失败（沿用旧数据）" if source.get("used_cache") else "失败")
        lines.append(f"| {_cell(source['label'])} | {state} | {source.get('latest_date') or '无'} | {_cell(source['detail'])} |")
    notes = health.get("notes") or []
    if notes:
        lines.extend(["", "需要留意："])
        lines.extend(f"- {_cell(note)}" for note in notes)
    changes = health.get("status_changes") or []
    if changes:
        lines.extend(["", "申赎状态变化："])
        lines.extend(f"- {_cell(change)}" for change in changes)
    lines.extend(
        [
            "",
            "## 边界与口径",
            "",
            "- 数据全部来自免费、允许自动访问的公开来源；抓取失败会如实标注，不用旧数据冒充本轮数据。",
            "- 基金净值用单位净值，未做分红复权；分红较多的基金回撤可能被高估。",
            "- 费率、限额、确认日等规则来自候选主表的官方页快照，申赎状态每轮按天天基金公开状态刷新；真要操作前仍以支付宝或基金公司官方页为准。",
            f"- 数据质量：{DATA_ZH.get(str(result.get('data_quality_status')), result.get('data_quality_status'))}"
            + ("（数据本身正常，是 Top5 里有候选需要人工复核证据）" if result.get("data_quality_status") == "manual_review" and not degraded else "")
            + "；数据不通过时一律不建议新增。",
            "",
        ]
    )
    return "\n".join(lines)


def render_release_body(result: dict[str, object], health: dict[str, object], *, slot: str, run_count: int) -> str:
    """GitHub Release 页面正文：最新一轮的摘要（完整报告在资产里）。"""
    recs = [r for r in result["recommendations"] if int(r["rank"]) <= 5]  # type: ignore[index, call-overload]
    lines = [
        f"Serenity 每日分析 · 最新一轮：{_slot_label(result, slot)}（今日第 {run_count} 轮）",
        "",
        f"- 数据状态：{'降级' if health.get('status') != 'ok' else '正常'}；持仓快照：暂无；只做研究，不自动买卖。",
        "",
        "| 排名 | 基金 | 等级 | 目标权重 |",
        "|---:|---|---|---:|",
    ]
    for row in recs:
        lines.append(f"| {row['rank']} | {_cell(row['asset_name'])}（{row['asset_code']}） | {GRADE_ZH.get(str(row['grade']), row['grade'])} | {pct(row['target_weight'])} |")
    if not recs:
        lines.append("| - | 本轮无候选 | - | - |")
    lines.extend(["", "完整报告见本 Release 的资产（每轮一份 .md 与 .html）。"])
    return "\n".join(lines)


# ---------------------------------------------------------------- HTML

def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)


def markdown_to_html(markdown: str, title: str) -> str:
    body: list[str] = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("|"):
            table: list[str] = []
            while index < len(lines) and lines[index].startswith("|"):
                table.append(lines[index])
                index += 1
            head = [c.strip() for c in table[0].strip("|").split("|")]
            align = [c.strip() for c in table[1].strip("|").split("|")]
            body.append("<div class=\"wrap\"><table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
            for raw in table[2:]:
                cells = [c.strip() for c in raw.strip("|").split("|")]
                body.append("<tr>" + "".join(
                    f"<td class=\"{'num' if i < len(align) and align[i].endswith(':') else ''}\">{_inline(c)}</td>" for i, c in enumerate(cells)
                ) + "</tr>")
            body.append("</tbody></table></div>")
            continue
        if line.startswith("# "):
            body.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("> "):
            body.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            items: list[str] = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(f"<li>{_inline(lines[index][2:])}</li>")
                index += 1
            body.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif line.strip():
            body.append(f"<p>{_inline(line)}</p>")
        index += 1
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#f6f7f5; --card:#fff; --ink:#15211f; --muted:#5d6b68; --line:#d9e0dc; --accent:#0b6f6a; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#101615; --card:#182120; --ink:#e6efec; --muted:#9db0ac; --line:#2a3836; --accent:#5fd3c6; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 56px; }}
h1 {{ font-size:24px; margin:0 0 12px; }} h2 {{ font-size:18px; margin:28px 0 10px; padding-bottom:6px; border-bottom:2px solid var(--line); }}
blockquote {{ margin:0 0 16px; padding:10px 14px; background:var(--card); border-left:4px solid var(--accent); color:var(--muted); }}
.wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; margin:8px 0 12px; }}
table {{ border-collapse:collapse; width:100%; min-width:640px; font-size:13.5px; }}
th,td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ background:rgba(11,111,106,.08); }} td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
code {{ font-family:ui-monospace,Menlo,monospace; font-size:12.5px; overflow-wrap:anywhere; }}
ul {{ padding-left:20px; }} li {{ margin:4px 0; }}
</style>
</head>
<body><main>
{chr(10).join(body)}
</main></body>
</html>
"""
