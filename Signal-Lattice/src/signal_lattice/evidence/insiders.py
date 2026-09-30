"""内部人买入：从 Form 4 原文入库、分类（机会型 / 例行 / 无法分类）、聚合。

分类（Cohen-Malloy-Pomorski 的定义，按 Owner 口径落成代码）：
  - 例行（ROUTINE）：该内部人在过去 3 个日历年里，每一年的同一个日历月都有 P 买入。
  - 无法分类（UNCLASSIFIABLE）：该内部人在「买入月份往前第 3 年的那个月」结束之前还没有出现在任何
    Form 3/4/5 上——历史不足 3 年，单独计数，不当机会型。
  - 机会型（OPPORTUNISTIC）：历史足够且不是例行。
「例行」的判断只看这位内部人在 as_of 前已申报的买入（时点正确）。
"""

from __future__ import annotations

import calendar
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Optional, Sequence

from .edgar_index import IndexRow
from .eventstore import EventStore, iso
from .form4 import Form4Doc, Form4ParseError, open_market_purchases, parse_form4
from .sec_client import SecClient, SecFetchError, SecNotFound

ROUTINE = "ROUTINE"
OPPORTUNISTIC = "OPPORTUNISTIC"
UNCLASSIFIABLE = "UNCLASSIFIABLE"
ARCHIVE_TXT = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"


def _month_end(year: int, month: int) -> str:
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def classify_buy(store: EventStore, owner_cik: int, trade_date: str, as_of) -> str:
    year, month = int(trade_date[:4]), int(trade_date[5:7])
    first = store.owner_first_filed(owner_cik)
    if first is None or first > _month_end(year - 3, month):
        return UNCLASSIFIABLE
    months = store.owner_p_months(owner_cik, as_of)
    if all((year - back, month) in months for back in (1, 2, 3)):
        return ROUTINE
    return OPPORTUNISTIC


def buys_from_doc(doc: Form4Doc, accession: str, filed: str) -> list[dict]:
    """一份 Form 4 → 每位内部人一行（他名下所有非 10b5-1 的 P 行合计）。没有 P 行返回空。"""
    purchases = open_market_purchases(doc)
    if not purchases:
        return []
    rows = []
    for owner in doc.owners:
        live = [t for t in purchases if not t.is_10b5_1]
        lines = live or purchases
        rows.append({
            "accession": accession, "owner_cik": owner.cik, "issuer_cik": doc.issuer_cik, "symbol": doc.symbol,
            "owner_name": owner.name, "role": owner.role, "filed": filed, "accepted_at": doc.accepted_at,
            "first_trade": min(t.date for t in lines), "last_trade": max(t.date for t in lines),
            "shares": sum(t.shares for t in lines), "amount_usd": sum(t.amount_usd for t in lines),
            "plan_10b5_1": 0 if live else 1,
            "indirect": int(any(t.ownership == "I" for t in lines)),
        })
    return rows


def ingest_form4_payload(store: EventStore, payload: bytes, accession: str, filed: str, fetched_at: str) -> str:
    """解析一份 Form 4 原文并入库；返回状态。同时把 P 行补进买入历史。"""
    try:
        doc = parse_form4(payload)
    except Form4ParseError:
        store.log_form4(accession, "PARSE_ERROR", fetched_at)
        return "PARSE_ERROR"
    rows = buys_from_doc(doc, accession, filed)
    if rows:
        store.save_form4_raw(accession, payload)
        for row in rows:
            store.add_buy(row)
        store.add_insider_p(
            [(accession, r["owner_cik"], r["issuer_cik"], t.date, filed, t.shares, t.price)
             for r in rows for t in open_market_purchases(doc)], "xml")
    store.log_form4(accession, "OK", fetched_at)
    return "OK"


def fetch_form4_batch(client: SecClient, store: EventStore, targets: Sequence[tuple],
                      workers: int = 4, limit: Optional[int] = None,
                      log: Callable[[str], None] = print) -> Counter:
    """targets: [(accession, issuer_cik, filed), ...]。已抓过的跳过；抓不到的记状态，下次不重试 NOT_FOUND。"""
    done = {row[0] for row in store.db.execute("SELECT accession FROM form4_fetch WHERE status IN ('OK','NOT_FOUND','PARSE_ERROR')")}
    pending = [t for t in targets if t[0] not in done]
    if limit is not None:
        pending = pending[:limit]
    stats: Counter = Counter()

    def fetch(target):
        accession, cik, _filed = target
        try:
            return target, client.get_bytes(ARCHIVE_TXT.format(cik=cik, accession=accession), cache=False), None
        except SecNotFound:
            return target, None, "NOT_FOUND"
        except SecFetchError:
            return target, None, "FETCH_ERROR"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (target, payload, error) in enumerate(pool.map(fetch, pending), 1):
            now = datetime.now(timezone.utc).isoformat()
            if payload is None:
                store.log_form4(target[0], error, now)
                stats[error] += 1
            else:
                stats[ingest_form4_payload(store, payload, target[0], target[2], now)] += 1
            if index % 500 == 0:
                store.commit()
                log("form4 fetched %d/%d %s requests=%d" % (index, len(pending), dict(stats), client.requests_sent))
    store.commit()
    return stats


def resolve_owner_history(client: SecClient, store: EventStore, owner_ciks: Iterable[int],
                          log: Callable[[str], None] = print, max_owners: Optional[int] = None) -> int:
    """数据集只覆盖 2021Q4 起；DERA 里首次出现较晚的内部人，去 submissions 查真正的首次申报日。
    返回新增确认的人数。查不到的保持原状（走无法分类）。"""
    checked = 0
    for owner in owner_ciks:
        if max_owners is not None and checked >= max_owners:
            break
        source_row = store.db.execute("SELECT source FROM owner_first WHERE owner_cik = ?", (int(owner),)).fetchone()
        if source_row is not None and source_row[0] == "submissions":
            continue
        try:
            payload = client.submissions(int(owner))
        except SecFetchError:
            continue
        checked += 1
        dates = list((payload.get("filings") or {}).get("recent", {}).get("filingDate") or [])
        for page in (payload.get("filings") or {}).get("files") or []:
            if page.get("filingFrom"):
                dates.append(page["filingFrom"])
        existing = store.owner_first_filed(int(owner))
        earliest = min(dates + ([existing] if existing else [])) if dates else existing
        if earliest:
            store.db.execute("INSERT OR REPLACE INTO owner_first (owner_cik, first_filed, source) VALUES (?,?,?)",
                             (int(owner), earliest, "submissions"))
        if checked % 200 == 0:
            store.commit()
            log("owner history checked %d" % checked)
    store.commit()
    return checked


def collapse_joint_filers(rows: Iterable) -> list:
    """联名申报（基金 + 管理人 + 个人一起报同一笔买入）只算一个买家：每份申报留 CIK 最小的那位。
    否则一笔买入会被算成好几位「内部人」、金额也会重复。"""
    chosen: dict = {}
    for row in rows:
        current = chosen.get(row["accession"])
        if current is None or row["owner_cik"] < current["owner_cik"]:
            chosen[row["accession"]] = row
    return sorted(chosen.values(), key=lambda r: (r["filed"], r["accession"]))


# ---- 聚合 ---------------------------------------------------------------------
def classified_buys(store: EventStore, as_of, since=None, issuer_cik: Optional[int] = None,
                    min_amount_usd: float = 25_000.0,
                    offering_like_min_buyers: Optional[int] = None) -> tuple[list[dict], Counter]:
    """返回 (合格买入行 + 分类, 剔除计数)。合格 = P、非 10b5-1、金额 >= 门槛。as_of 之后申报的看不到。"""
    rows = store.buys_as_of(issuer_cik, as_of, since) if issuer_cik is not None else store.all_buys_as_of(as_of, since)
    rows = collapse_joint_filers(rows)
    offering_like = store.offering_like_accessions(as_of, offering_like_min_buyers) if offering_like_min_buyers else set()
    excluded: Counter = Counter()
    kept = []
    for row in rows:
        if row["plan_10b5_1"]:
            excluded["PLAN_10B5_1"] += 1
        elif row["accession"] in offering_like:
            excluded["OFFERING_LIKE"] += 1
        elif row["amount_usd"] < min_amount_usd:
            excluded["BELOW_MIN_AMOUNT"] += 1
        else:
            entry = dict(row)
            entry["classification"] = classify_buy(store, row["owner_cik"], row["first_trade"], as_of)
            kept.append(entry)
    return kept, excluded


def opportunistic_summary(store: EventStore, issuer_cik: int, as_of, window_days: int = 90,
                          market_cap_usd: Optional[float] = None, min_amount_usd: float = 25_000.0,
                          offering_like_min_buyers: Optional[int] = None) -> dict:
    """as_of 之前 window_days 天内该公司的机会型买入：人数、金额、占市值比，附各类计数。"""
    as_of_text = iso(as_of)
    since = (date.fromisoformat(as_of_text) - timedelta(days=window_days)).isoformat()
    kept, excluded = classified_buys(store, as_of, since, issuer_cik, min_amount_usd, offering_like_min_buyers)
    buckets = Counter(entry["classification"] for entry in kept)
    opportunistic = [entry for entry in kept if entry["classification"] == OPPORTUNISTIC]
    per_accession: dict = {}
    for entry in opportunistic:
        per_accession[entry["accession"]] = max(per_accession.get(entry["accession"], 0.0), entry["amount_usd"])
    total = sum(per_accession.values())
    return {
        "as_of": as_of_text,
        "window_days": window_days,
        "opportunistic_insiders": len({entry["owner_cik"] for entry in opportunistic}),
        "opportunistic_amount_usd": round(total, 2),
        "pct_of_market_cap": (total / market_cap_usd) if market_cap_usd else None,
        "buys": opportunistic,
        "counts": {"opportunistic": buckets[OPPORTUNISTIC], "routine": buckets[ROUTINE],
                   "unclassifiable": buckets[UNCLASSIFIABLE]},
        "excluded": dict(excluded),
    }
