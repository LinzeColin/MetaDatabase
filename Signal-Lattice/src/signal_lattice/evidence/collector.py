"""对单个 CIK 采集 submissions + companyfacts 并入账。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .factstore import FactStore
from .sec_client import SecClient


def collect_company(client: SecClient, store: FactStore, cik: int, today: Optional[date] = None) -> dict:
    """返回本次新增行数；同一家重复采集是幂等的（已入账的行忽略）。"""
    today = today or date.today()
    submissions = client.submissions(cik)
    filings_added = store.ingest_submissions(cik, submissions, today)
    facts_added = store.ingest_companyfacts(cik, client.companyfacts(cik), today)
    return {
        "cik": int(cik),
        "name": submissions.get("name"),
        "tickers": submissions.get("tickers"),
        "filings_added": filings_added,
        "facts_added": facts_added,
        "facts_total": store.count("facts", cik),
    }
