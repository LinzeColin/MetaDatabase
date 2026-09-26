from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from pfi_os.classify import classify, load_user_rules
from pfi_os.importers import Transaction


def tx(amount: str, *, direction: str = "支出", category: str = "", description: str = "", status: str = "交易成功",
       source: str = "alipay", counterparty: str = "") -> Transaction:
    return Transaction(source, datetime(2026, 6, 1), Decimal(amount), "CNY" if source == "alipay" else "AUD",
                       direction, counterparty, description, category, status, "", "t.csv")


@pytest.mark.parametrize(
    ("item", "kind", "category"),
    [
        (tx("-12.5", category="餐饮美食", description="早餐"), "expense", "餐饮美食"),
        (tx("20", direction="收入", category="退款", description="订单退款"), "refund", "退款"),
        (tx("3000", direction="收入", category="收入", description="工资"), "income", "收入"),
        (tx("-25", category="餐饮美食", status="交易关闭"), "excluded", "交易关闭"),
        (tx("300", direction="不计收支", category="信用借还", description="花呗主动还款"), "transfer", "还款"),
        (tx("500", direction="不计收支", category="投资理财", description="余额宝-单次转入"), "investment", "投资理财"),
        (tx("-1000", category="投资理财", description="基金申购"), "investment", "投资理财"),
        (tx("88", direction="不计收支", category="其他", description="转出到银行卡"), "transfer", "账户搬运"),
        (tx("-200", category="转账红包", description="转账"), "expense", "转账红包"),
        (tx("-85.4", direction="支出", source="cba", description="WOOLWORTHS 1234"), "expense", "日用百货"),
        (tx("-1200", direction="支出", source="cba", description="Credit Card Repayment"), "transfer", "还款"),
        (tx("-2000", direction="支出", source="cba", description="Transfer to Moomoo"), "investment", "投资理财"),
        (tx("4500", direction="收入", source="cba", description="Salary Pay From Example"), "income", "工资"),
    ],
)
def test_classification_rules(item: Transaction, kind: str, category: str) -> None:
    result = classify(item)
    assert (result.kind, result.category) == (kind, category)


def test_not_counted_refund_mirror_does_not_reduce_spending() -> None:
    assert classify(tx("20", direction="不计收支", description="退款")).kind == "transfer"


def test_unknown_direction_and_uncategorised_spend_need_review() -> None:
    unknown = classify(tx("8", direction="", category="其他"))
    assert (unknown.kind, unknown.needs_review) == ("excluded", True)
    assert "无法判断方向" in unknown.reason
    assert classify(tx("-30", source="cba", description="UNKNOWN 99")).needs_review


def test_user_rules_override_builtin_rules(tmp_path: Path) -> None:
    (tmp_path / "rules.json").write_text(
        json.dumps([{"match": "transfer to landlord", "kind": "expense", "category": "住房物业"}]), encoding="utf-8"
    )
    rules = load_user_rules(tmp_path)
    result = classify(tx("-650", source="cba", description="Transfer To Landlord NetBank"), rules)
    assert (result.kind, result.category) == ("expense", "住房物业")


def test_invalid_user_rule_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "rules.json").write_text(json.dumps([{"match": "x", "kind": "spend"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="第 1 条规则无效"):
        load_user_rules(tmp_path)
