from __future__ import annotations

from datetime import datetime
from typing import Any

from .clock import format_sydney


MATRIX_COLUMNS = (
    "技能", "适用状态", "运行方式", "弃权主原因", "方法家族",
    "原始权重", "家族内权重", "总体权重", "结论", "独立性",
)


def finalize_report(report: dict[str, Any], now: datetime, next_review: datetime) -> dict[str, Any]:
    report["运行时间"] = format_sydney(now)
    report["第一板块"]["下一正式复核"] = f"{format_sydney(next_review)}（悉尼时间）或重大事件"
    return report


def render_report(report: dict[str, Any]) -> str:
    first = report["第一板块"]
    second = report["第二板块"]
    lines = [
        f"运行时间：{report['运行时间']}",
        f"提示词版本：{report['提示词版本']}",
        f"运行状态：{report['运行状态']}",
        f"市场覆盖：{report['市场覆盖']}",
        f"数据截止：{report['数据截止']}",
        f"状态连续性：{report['状态连续性']}",
        f"裁决完整性：{report['裁决完整性']}",
        f"技能适用覆盖率：{report['技能适用覆盖率']}",
        "",
        "# 第一板块：唯一影子操作",
    ]
    for key in (
        "唯一操作", "唯一平台", "唯一标的", "代码", "唯一方向", "可观察回撤",
        "风险调整回撤", "剩余回撤预算", "预期研究窗口", "相对宽基", "相对现金",
        "现在怎么做", "核心依据", "最大反证", "失效条件", "下一正式复核",
    ):
        lines.append(f"{key}：{first[key]}")
    lines.extend([
        "",
        "# 第二板块：六技能能力与覆盖矩阵",
        "| " + " | ".join(MATRIX_COLUMNS) + " |",
        "|---|---|---|---|---|---:|---:|---:|---|---|",
    ])
    for row in second["矩阵"]:
        values = [str(row.get(column, "")) for column in MATRIX_COLUMNS]
        values = [value.replace("|", "／").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend([
        "",
        f"适用技能：{second['适用技能']}",
        f"实际参与：{second['实际参与']}",
        f"适用覆盖率：{second['适用覆盖率']}",
        f"原生参与：{second['原生参与']}",
        f"原生覆盖率：{second['原生覆盖率']}",
        f"中央定量审查：{second['中央定量审查']}",
        f"权重说明：{second['权重说明']}",
    ])
    return "\n".join(lines)


def public_asset_mentions(report: dict[str, Any]) -> tuple[str, str]:
    first = report["第一板块"]
    return str(first["唯一标的"]), str(first["代码"])
