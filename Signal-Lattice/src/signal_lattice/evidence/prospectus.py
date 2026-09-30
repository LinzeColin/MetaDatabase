"""424B5 招股说明书补充文件：只看主文档头部（约 8 万字节），判断是 ATM、普通增发，还是债券等其他发行。

只用于给「稀释」事件定性；抓不到或读不出来的记 UNVERIFIED，风险口径上按增发处理（宁可多标失效风险）。
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional, Sequence

from .eventstore import EventStore
from .sec_client import SecClient, SecFetchError

HEAD_BYTES = 80_000
ATM = "ATM"
EQUITY_OFFERING = "EQUITY_OFFERING"
OTHER = "OTHER_PROSPECTUS"
UNVERIFIED = "UNVERIFIED"

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_DEBT = re.compile(r"\b(?:senior|subordinated|convertible|unsecured|secured|floating rate|fixed rate)?\s*(?:notes|debentures|bonds)\b"
                   r"[^.]{0,40}\bdue\s+\d{4}|\baggregate principal amount\b", re.I)
_EQUITY = re.compile(r"\b(?:shares? of (?:our )?(?:class [a-z] )?common stock|ordinary shares|common shares|"
                     r"shares of common stock)\b", re.I)


def plain_text(payload: bytes) -> str:
    text = html.unescape(_TAGS.sub(" ", payload.decode("utf-8", errors="replace"))).replace("\xa0", " ")
    return _SPACES.sub(" ", text).strip()


def classify_prospectus(text: str, atm_terms: Sequence[str]) -> str:
    lowered = text.lower()
    if any(term.lower() in lowered for term in atm_terms):
        return ATM
    cover = text[:6000]
    if _DEBT.search(cover) and not _EQUITY.search(cover):
        return OTHER
    return EQUITY_OFFERING if _EQUITY.search(text) else UNVERIFIED


def document_url(cik: int, accession: str, primary_document: str) -> str:
    return "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (int(cik), accession.replace("-", ""), primary_document)


def label_424b5(client: SecClient, store: EventStore, rows: Iterable[tuple], atm_terms: Sequence[str],
                log: Callable[[str], None] = print, limit: Optional[int] = None) -> dict:
    """rows: [(accession, cik, primary_document)]。已标过的跳过。"""
    done = {r[0] for r in store.db.execute("SELECT accession FROM prospectus_class")}
    counts: dict = {}
    todo = [r for r in rows if r[0] not in done]
    if limit:
        todo = todo[:limit]
    for index, (accession, cik, primary) in enumerate(todo, 1):
        label = UNVERIFIED
        if primary:
            try:
                # SEC 不支持 Range，只能整份取回；只留头部判断，原文不落盘
                payload = client.get_bytes(document_url(cik, accession, primary), cache=False)
                label = classify_prospectus(plain_text(payload[:HEAD_BYTES]), atm_terms)
            except SecFetchError:
                label = UNVERIFIED
        store.db.execute("INSERT OR REPLACE INTO prospectus_class (accession, label, checked_at) VALUES (?,?,?)",
                         (accession, label, datetime.now(timezone.utc).isoformat()))
        counts[label] = counts.get(label, 0) + 1
        if index % 200 == 0:
            store.commit()
            log("prospectus labelled %d/%d %s" % (index, len(todo), counts))
    store.commit()
    return counts
