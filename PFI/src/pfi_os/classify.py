"""自动分类：给每笔流水定 kind（收支性质）和 category（消费/收入类别）。

kind 取值：
- expense    真实消费（计入月度支出）
- income     真实收入（计入月度收入）
- refund     退款（冲减当月支出）
- transfer   自有账户搬运 / 信用卡、花呗还款（不计收支，避免重复计消费）
- investment 基金、余额宝、黄金等投资资金流（单列，不计生活收支）
- excluded   交易关闭/失败，或方向无法识别（不计收支；方向无法识别的会标 needs_review）

规则按顺序命中即停。Owner 可在数据目录放 rules.json 覆盖（优先于内置规则）：
[{"match": "WOOLWORTHS", "kind": "expense", "category": "日用超市"}, ...]
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pfi_os.importers import Transaction

KINDS = ("expense", "income", "refund", "transfer", "investment", "excluded")

CLOSED_STATUS = ("关闭", "失败", "撤销")
REPAYMENT = ("信用卡还款", "花呗还款", "借呗还款", "credit card repayment", "card repayment", "还款")
INVESTMENT = (
    "基金", "余额宝", "理财", "黄金", "白银", "bullion", "moomoo", "commsec", "stake", "券商", "证券",
)
OWN_TRANSFER = (
    "转出到银行卡", "提现", "充值", "余额转入", "转入到余额", "银证转账", "transfer to", "transfer from",
    "own account", "netbank transfer",
)
REFUND = ("退款", "refund")

# CBA 描述没有分类列，用关键词映射到与支付宝“交易分类”同一套中文类别。
CBA_CATEGORIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("woolworths", "coles", "aldi", "iga ", "costco"), "日用百货"),
    (("uber eats", "doordash", "menulog", "mcdonald", "kfc", "cafe", "coffee", "restaurant", "sushi", "pizza"), "餐饮美食"),
    (("uber", "opal", "transport", "didi", "7-eleven fuel", "ampol", "bp ", "shell", "caltex", "parking", "linkt"), "交通出行"),
    (("rent", "strata", "real estate"), "住房物业"),
    (("agl", "origin energy", "energyaustralia", "telstra", "optus", "vodafone", "aussie broadband", "water"), "生活缴费"),
    (("netflix", "spotify", "apple.com", "google", "youtube", "disney", "chatgpt", "openai", "anthropic"), "数码订阅"),
    (("amazon", "jb hi-fi", "kmart", "target", "big w", "officeworks", "ikea", "ebay"), "网购电器"),
    (("chemist", "pharmacy", "medical", "dental", "medicare", "bupa", "hospital"), "医疗健康"),
    (("salary", "payroll", "wage", "pay from"), "工资"),
    (("interest",), "利息"),
)


@dataclass(frozen=True)
class Classified:
    tx: Transaction
    kind: str
    category: str
    reason: str
    needs_review: bool


def load_user_rules(data_dir: Path | None) -> list[dict[str, str]]:
    if data_dir is None:
        return []
    path = Path(data_dir) / "rules.json"
    if not path.is_file():
        return []
    rules = json.loads(path.read_text(encoding="utf-8"))
    for index, rule in enumerate(rules):
        if not rule.get("match") or rule.get("kind") not in KINDS:
            raise ValueError(f"{path} 第 {index + 1} 条规则无效：需要非空 match，kind 必须是 {KINDS} 之一")
    return rules


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _cba_category(text: str, fallback: str) -> str:
    for words, category in CBA_CATEGORIES:
        if _has(text, words):
            return category
    return fallback


def classify(tx: Transaction, user_rules: list[dict[str, str]] | None = None) -> Classified:
    text = " ".join((tx.source_category, tx.counterparty, tx.description)).lower()

    for rule in user_rules or ():
        if rule["match"].lower() in text:
            return Classified(tx, rule["kind"], rule.get("category") or tx.source_category or "未分类", f"rules.json: {rule['match']}", False)

    if _has(tx.status, CLOSED_STATUS):
        return Classified(tx, "excluded", "交易关闭", f"交易状态“{tx.status}”没有实际资金流", False)
    if _has(text, REPAYMENT) or tx.source_category == "信用借还":
        return Classified(tx, "transfer", "还款", "信用卡/花呗还款：消费已在刷卡时计入，不重复计", False)
    # 支付宝“不计收支”的退款行只是原路退回的记账镜像，不再冲减支出。
    if _has(text, REFUND) and tx.amount > 0 and tx.direction != "不计收支":
        return Classified(tx, "refund", tx.source_category or "退款", "退款冲减支出", False)
    if tx.source_category == "投资理财" or _has(text, INVESTMENT):
        return Classified(tx, "investment", "投资理财", "基金/余额宝/券商/贵金属资金流单列", False)
    if _has(text, OWN_TRANSFER) or tx.direction == "不计收支":
        return Classified(tx, "transfer", "账户搬运", "自有账户间移动或支付宝“不计收支”", False)

    if tx.source == "alipay" and tx.direction not in ("支出", "收入"):
        return Classified(tx, "excluded", "方向未知", f"支付宝“收/支”列为“{tx.direction}”，无法判断方向", True)

    if tx.amount < 0:
        category = tx.source_category or _cba_category(text, "未分类")
        return Classified(tx, "expense", category, "流出", category == "未分类")
    category = tx.source_category or _cba_category(text, "其他收入")
    return Classified(tx, "income", category, "流入", False)


def classify_all(transactions: list[Transaction], user_rules: list[dict[str, str]] | None = None) -> list[Classified]:
    return [classify(tx, user_rules) for tx in transactions]
