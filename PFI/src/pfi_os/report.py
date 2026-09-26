"""月度收支汇总与报告渲染。不同币种（CNY / AUD）分开统计，不做汇率换算。"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from pfi_os.classify import Classified
from pfi_os.importers import LoadResult

ZERO = Decimal("0")


@dataclass
class MonthSummary:
    month: str
    currency: str
    income: Decimal = ZERO
    expense: Decimal = ZERO  # 毛支出，正数
    refund: Decimal = ZERO  # 退款，正数
    investment_net: Decimal = ZERO  # 投资资金净流入（负数=净买入）
    transactions: int = 0
    needs_review: int = 0
    categories: dict[str, Decimal] = field(default_factory=dict)

    @property
    def net_expense(self) -> Decimal:
        return self.expense - self.refund

    @property
    def net(self) -> Decimal:
        return self.income - self.net_expense


def monthly_summary(rows: list[Classified]) -> list[MonthSummary]:
    table: dict[tuple[str, str], MonthSummary] = {}
    for row in rows:
        key = (row.tx.month, row.tx.currency)
        summary = table.setdefault(key, MonthSummary(*key))
        summary.transactions += 1
        summary.needs_review += int(row.needs_review)
        amount = row.tx.amount
        if row.kind == "expense":
            summary.expense += -amount
            summary.categories[row.category] = summary.categories.get(row.category, ZERO) + (-amount)
        elif row.kind == "income":
            summary.income += amount
        elif row.kind == "refund":
            summary.refund += amount
        elif row.kind == "investment" and row.tx.direction != "不计收支":
            summary.investment_net += amount
    return [table[key] for key in sorted(table)]


def _fmt(value: Decimal) -> str:
    return f"{value:,.2f}"


def render_markdown(summaries: list[MonthSummary], loaded: LoadResult, rows: list[Classified], top: int = 5) -> str:
    kinds: dict[str, int] = defaultdict(int)
    for row in rows:
        kinds[row.kind] += 1
    out = [
        "# PFI 月度收支报告",
        "",
        f"- 读取文件：{len(loaded.files)} 个；跳过无法识别：{len(loaded.skipped_files)} 个"
        + (f"（{', '.join(loaded.skipped_files)}）" if loaded.skipped_files else ""),
        f"- 流水：{len(loaded.transactions) + loaded.duplicates_dropped} 条原始，跨文件去重 {loaded.duplicates_dropped} 条，入账 {len(rows)} 条",
        "- 分类：" + "，".join(f"{kind} {kinds[kind]}" for kind in sorted(kinds)),
        f"- 需复核：{sum(int(r.needs_review) for r in rows)} 条（方向未知或未分类支出）",
        "- 口径：净支出 = 支出 − 退款；结余 = 收入 − 净支出；转账/还款/投资不计入收支。",
        "",
    ]
    for currency in sorted({s.currency for s in summaries}):
        items = [s for s in summaries if s.currency == currency]
        out += [
            f"## {currency}",
            "",
            "| 月份 | 收入 | 支出 | 退款 | 净支出 | 结余 | 净支出环比 | 投资净流 | 笔数 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        previous: MonthSummary | None = None
        for s in items:
            change = "—"
            if previous is not None and previous.net_expense:
                change = f"{(s.net_expense - previous.net_expense) / previous.net_expense * 100:+.1f}%"
            out.append(
                f"| {s.month} | {_fmt(s.income)} | {_fmt(s.expense)} | {_fmt(s.refund)} | {_fmt(s.net_expense)} "
                f"| {_fmt(s.net)} | {change} | {_fmt(s.investment_net)} | {s.transactions} |"
            )
            previous = s
        total_income = sum((s.income for s in items), ZERO)
        total_net_expense = sum((s.net_expense for s in items), ZERO)
        out += [
            "",
            f"合计：收入 {_fmt(total_income)}，净支出 {_fmt(total_net_expense)}，结余 {_fmt(total_income - total_net_expense)}；"
            f"月均净支出 {_fmt(total_net_expense / len(items))}（{len(items)} 个月）",
            "",
            f"### {currency} 每月支出前 {top} 类",
            "",
        ]
        for s in items:
            ranked = sorted(s.categories.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
            out.append(f"- {s.month}：" + ("，".join(f"{name} {_fmt(v)}" for name, v in ranked) or "无支出"))
        out.append("")
    return "\n".join(out)


LEDGER_COLUMNS = (
    "occurred_at", "month", "source", "currency", "amount", "kind", "category", "needs_review",
    "direction", "counterparty", "description", "source_category", "status", "order_id", "source_file", "reason",
)


def write_ledger_csv(rows: list[Classified], path: Path) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(LEDGER_COLUMNS)
        for r in rows:
            t = r.tx
            writer.writerow([
                t.occurred_at.isoformat(sep=" "), t.month, t.source, t.currency, f"{t.amount:.2f}", r.kind, r.category,
                int(r.needs_review), t.direction, t.counterparty, t.description, t.source_category, t.status,
                t.order_id, t.source_file, r.reason,
            ])
