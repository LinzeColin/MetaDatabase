"""事件航图测试共用的 Form 4 XML 构造器与内存库。"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from signal_lattice.evidence.eventstore import EventStore


def txn(code="P", date="2026-08-10", shares=1000, price=25.0, ad="A", footnote=None, ownership="D"):
    note = '<footnoteId id="%s"/>' % footnote if footnote else ""
    return """
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>%s</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>%s</transactionCode>%s</transactionCoding>
      <transactionAmounts>
        <transactionShares><value>%s</value></transactionShares>
        <transactionPricePerShare><value>%s</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>%s</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>%s</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>""" % (date, code, note, shares, "" if price is None else price, ad, ownership)


def form4_xml(transactions: Sequence[str], issuer_cik=1234567, symbol="TEST", owners=((900001, "Doe Jane", "CEO"),),
              aff10b5one: Optional[str] = None, footnotes: Optional[dict] = None):
    owner_xml = "".join("""
    <reportingOwner>
      <reportingOwnerId><rptOwnerCik>%010d</rptOwnerCik><rptOwnerName>%s</rptOwnerName></reportingOwnerId>
      <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>%s</isOfficer><isTenPercentOwner>0</isTenPercentOwner>
        <officerTitle>%s</officerTitle></reportingOwnerRelationship>
    </reportingOwner>""" % (cik, name, "1" if title else "0", title) for cik, name, title in owners)
    flag = "<aff10b5One>%s</aff10b5One>" % aff10b5one if aff10b5one is not None else ""
    notes = "".join('<footnote id="%s">%s</footnote>' % item for item in (footnotes or {}).items())
    return """<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0508</schemaVersion><documentType>4</documentType><periodOfReport>2026-08-10</periodOfReport>
  %s
  <issuer><issuerCik>%010d</issuerCik><issuerName>Test Corp</issuerName><issuerTradingSymbol>%s</issuerTradingSymbol></issuer>
  %s
  <nonDerivativeTable>%s</nonDerivativeTable>
  <footnotes>%s</footnotes>
</ownershipDocument>""" % (flag, issuer_cik, symbol, owner_xml, "".join(transactions), notes)


def wrap_submission(xml: str, accepted="20260811093015"):
    return ("<SEC-DOCUMENT>x\n<SEC-HEADER>\n<ACCEPTANCE-DATETIME>%s\nACCESSION NUMBER: 0000000000-26-000001\n</SEC-HEADER>\n"
            "<DOCUMENT>\n<TYPE>4\n<XML>\n%s\n</XML>\n</DOCUMENT>\n</SEC-DOCUMENT>" % (accepted, xml))


def add_p_history(store: EventStore, owner: int, months: Iterable[tuple], issuer=555, filed_lag_days=3):
    """给内部人写入 P 买入历史：months=[(年, 月), ...]，每月 15 日成交。"""
    rows = []
    for index, (year, month) in enumerate(months):
        trade = "%04d-%02d-15" % (year, month)
        filed = "%04d-%02d-%02d" % (year, month, 15 + filed_lag_days)
        rows.append(("H-%d-%d-%d" % (owner, year, month), owner, issuer, trade, filed, 100.0 + index, 10.0))
    store.add_insider_p(rows, "test")
    store.commit()


def add_buy(store: EventStore, accession: str, owner: int, issuer=1234567, filed="2026-08-12", first_trade="2026-08-10",
            amount=50_000.0, plan=0, name="Doe Jane", role="CEO", symbol="TEST"):
    store.add_buy({
        "accession": accession, "owner_cik": owner, "issuer_cik": issuer, "symbol": symbol, "owner_name": name,
        "role": role, "filed": filed, "accepted_at": filed + "T13:00:00Z", "first_trade": first_trade,
        "last_trade": first_trade, "shares": amount / 10.0, "amount_usd": amount, "plan_10b5_1": plan, "indirect": 0})
    store.commit()
