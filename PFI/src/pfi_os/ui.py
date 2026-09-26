"""PFI 本地界面：streamlit run src/pfi_os/ui.py（数据目录取 PFI_DATA_DIR）。"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from pfi_os.classify import classify_all, load_user_rules
from pfi_os.importers import load_data_dir
from pfi_os.report import monthly_summary

st.set_page_config(page_title="PFI 个人收支", layout="wide")
st.title("PFI 个人收支")

data_dir = st.sidebar.text_input("数据目录（PFI_DATA_DIR）", os.environ.get("PFI_DATA_DIR", ""))
if not data_dir:
    st.info("请设置环境变量 PFI_DATA_DIR，或在左侧填入存放支付宝/CBA 账单的目录。")
    st.stop()
if not Path(data_dir).expanduser().is_dir():
    st.error(f"数据目录不存在：{data_dir}")
    st.stop()

loaded = load_data_dir(Path(data_dir))
rows = classify_all(loaded.transactions, load_user_rules(Path(data_dir).expanduser()))
st.caption(
    f"{len(loaded.files)} 个文件，入账 {len(rows)} 条，跨文件去重 {loaded.duplicates_dropped} 条，"
    f"需复核 {sum(r.needs_review for r in rows)} 条"
    + (f"；跳过无法识别：{', '.join(loaded.skipped_files)}" if loaded.skipped_files else "")
)
if not rows:
    st.warning("没有读到任何流水。")
    st.stop()

summaries = monthly_summary(rows)
for currency in sorted({s.currency for s in summaries}):
    st.header(currency)
    table = pd.DataFrame(
        [
            {"月份": s.month, "收入": float(s.income), "支出": float(s.expense), "退款": float(s.refund),
             "净支出": float(s.net_expense), "结余": float(s.net), "投资净流": float(s.investment_net), "笔数": s.transactions}
            for s in summaries if s.currency == currency
        ]
    ).set_index("月份")
    st.bar_chart(table[["收入", "净支出"]])
    st.dataframe(table, use_container_width=True)
    months = list(table.index)
    month = st.selectbox(f"{currency} 类别明细月份", months, index=len(months) - 1, key=f"month-{currency}")
    chosen = next(s for s in summaries if s.currency == currency and s.month == month)
    categories = pd.Series({k: float(v) for k, v in chosen.categories.items()}, name="支出").sort_values(ascending=False)
    st.bar_chart(categories)

st.header("流水明细")
ledger = pd.DataFrame(
    [
        {"时间": r.tx.occurred_at, "来源": r.tx.source, "币种": r.tx.currency, "金额": float(r.tx.amount),
         "性质": r.kind, "类别": r.category, "需复核": r.needs_review, "对方": r.tx.counterparty,
         "说明": r.tx.description, "依据": r.reason}
        for r in rows
    ]
)
only_review = st.checkbox("只看需复核")
st.dataframe(ledger[ledger["需复核"]] if only_review else ledger, use_container_width=True)
