"""Form 4 原始 XML 解析：只认公开市场买入（交易代码 P），剔除 10b5-1 计划与小额。

不依赖任何第三方库。输入既可以是纯 XML，也可以是 EDGAR 的完整提交文本（accession.txt，
里面嵌着 <ownershipDocument>，头部有 <ACCEPTANCE-DATETIME>）。

判定规则（写死在这里，由 tests/test_event_atlas_form4.py 钉住）：
  1. 只看非衍生品表（nonDerivativeTransaction）里 transactionCode == "P" 的行；
     A 授予、M 行权、F 扣税、S 卖出、G 赠与、J 其他……一律不算。
  2. 10b5-1 计划交易剔除：整份表的 <aff10b5One> 勾选为 true/1，或该交易行引用的脚注提到 10b5-1。
  3. 金额 = 股数 × 单价，同一份申报里同一内部人的 P 行合计后与门槛（默认 2.5 万美元）比较；
     没有单价的行金额记 0（不猜价）。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, Union

_PLAN_10B5_1 = re.compile(r"10b5[\s\-‐-―]*1", re.I)
_ACCEPTANCE = re.compile(r"<ACCEPTANCE-DATETIME>\s*(\d{14})")
_DOCUMENT = re.compile(r"<ownershipDocument\b.*?</ownershipDocument>", re.S)


class Form4ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Owner:
    cik: int
    name: str
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    officer_title: str

    @property
    def role(self) -> str:
        parts = []
        if self.is_officer:
            parts.append(self.officer_title or "Officer")
        if self.is_director:
            parts.append("Director")
        if self.is_ten_percent_owner:
            parts.append("10% Owner")
        return ", ".join(parts) or "Other"


@dataclass(frozen=True)
class Transaction:
    code: str
    date: str                      # YYYY-MM-DD（交易日，不是申报日）
    shares: float
    price: Optional[float]
    acquired_disposed: str         # A / D
    security_title: str
    ownership: str                 # D 直接 / I 间接
    is_10b5_1: bool

    @property
    def amount_usd(self) -> float:
        return self.shares * self.price if self.price else 0.0


@dataclass(frozen=True)
class Form4Doc:
    issuer_cik: int
    issuer_name: str
    symbol: str
    period_of_report: Optional[str]
    aff10b5_one: bool
    owners: tuple
    transactions: tuple
    accepted_at: Optional[str] = None      # ACCEPTANCE-DATETIME（EDGAR 收到的时刻，UTC 数字串格式化）
    footnotes: dict = field(default_factory=dict)


def _text(node: Optional[ET.Element], path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "y", "yes"}


def _number(value: str) -> Optional[float]:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def extract_xml(payload: Union[str, bytes]) -> tuple[str, Optional[str]]:
    """从纯 XML 或完整提交文本里切出 <ownershipDocument>，并读出受理时刻。"""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    accepted = None
    match = _ACCEPTANCE.search(text)
    if match:
        raw = match.group(1)
        accepted = "%s-%s-%sT%s:%s:%sZ" % (raw[:4], raw[4:6], raw[6:8], raw[8:10], raw[10:12], raw[12:14])
    document = _DOCUMENT.search(text)
    if document is None:
        raise Form4ParseError("NO_OWNERSHIP_DOCUMENT")
    return document.group(0), accepted


def parse_form4(payload: Union[str, bytes]) -> Form4Doc:
    xml_text, accepted = extract_xml(payload)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise Form4ParseError("XML_INVALID:%s" % exc) from exc
    footnotes = {
        (node.get("id") or ""): " ".join((node.text or "").split())
        for node in root.iter("footnote")
    }
    issuer = root.find("issuer")
    try:
        issuer_cik = int(_text(issuer, "issuerCik"))
    except ValueError as exc:
        raise Form4ParseError("ISSUER_CIK_MISSING") from exc
    owners = []
    for node in root.findall("reportingOwner"):
        try:
            owner_cik = int(_text(node, "reportingOwnerId/rptOwnerCik"))
        except ValueError:
            continue
        relation = node.find("reportingOwnerRelationship")
        owners.append(Owner(
            cik=owner_cik,
            name=_text(node, "reportingOwnerId/rptOwnerName"),
            is_director=_flag(_text(relation, "isDirector")),
            is_officer=_flag(_text(relation, "isOfficer")),
            is_ten_percent_owner=_flag(_text(relation, "isTenPercentOwner")),
            officer_title=_text(relation, "officerTitle"),
        ))
    aff = _flag(_text(root, "aff10b5One"))
    transactions = []
    for node in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        note_ids = {ref.get("id") or "" for ref in node.iter("footnoteId")}
        plan = aff or any(_PLAN_10B5_1.search(footnotes.get(note_id, "")) for note_id in note_ids)
        shares = _number(_text(node, "transactionAmounts/transactionShares/value"))
        if shares is None:
            continue
        transactions.append(Transaction(
            code=_text(node, "transactionCoding/transactionCode").upper(),
            date=_text(node, "transactionDate/value")[:10],
            shares=shares,
            price=_number(_text(node, "transactionAmounts/transactionPricePerShare/value")),
            acquired_disposed=_text(node, "transactionAmounts/transactionAcquiredDisposedCode/value").upper(),
            security_title=_text(node, "securityTitle/value"),
            ownership=_text(node, "ownershipNature/directOrIndirectOwnership/value").upper() or "D",
            is_10b5_1=plan,
        ))
    return Form4Doc(
        issuer_cik=issuer_cik,
        issuer_name=_text(issuer, "issuerName"),
        symbol=_text(issuer, "issuerTradingSymbol").upper(),
        period_of_report=_text(root, "periodOfReport") or None,
        aff10b5_one=aff,
        owners=tuple(owners),
        transactions=tuple(transactions),
        accepted_at=accepted,
        footnotes=footnotes,
    )


def open_market_purchases(doc: Form4Doc) -> list[Transaction]:
    """交易代码 P 且方向为买入（A）的非衍生品交易；是否 10b5-1 由调用方看 is_10b5_1。"""
    return [t for t in doc.transactions if t.code == "P" and t.acquired_disposed in ("A", "")]
