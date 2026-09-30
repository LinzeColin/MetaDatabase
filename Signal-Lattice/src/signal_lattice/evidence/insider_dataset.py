"""SEC 官方「内部人交易数据集」（DERA insider-transactions-data-sets，免 key，按季度 zip）。

用途只有两个，都是「批量筛」而不是最终证据：
  1. 找出哪些 Form 4 含代码 P 的买入——只有这些才去抓原文 XML（全池一季 1.5 万份 Form 4，
     其中约 5% 有 P；不筛就要多抓 20 倍）。最终事件与金额、10b5-1 判定一律以原文 XML 为准。
  2. 给「例行买入者」判定提供全市场内部人的 P 买入历史与首次出现日。
最新一季数据集有滞后（约季末后 3 天发布，到那天为止）；数据集之后的申报走每日索引 + 原文。
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime, timezone
from typing import Callable, Iterable, Optional

from .eventstore import EventStore
from .sec_client import SecClient

LANDING_URL = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
_LINK = re.compile(r'href="(/files/[^"]*?/(\d{4})q([1-4])_form345\.zip)"')
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def dera_date(text: str) -> Optional[str]:
    """'30-JUN-2026' -> '2026-06-30'"""
    try:
        day, month, year = text.strip().split("-")
        return "%04d-%02d-%02d" % (int(year), _MONTHS[month.upper()], int(day))
    except (ValueError, KeyError):
        return None


def list_dataset_urls(client: SecClient) -> dict:
    """{'2026q2': url, ...}；从官方登记页读链接，不手拼（不同年份放在不同目录）。"""
    page = client.get_bytes(LANDING_URL, cache=False).decode("utf-8", errors="replace")
    return {"%sq%s" % (m.group(2), m.group(3)): "https://www.sec.gov" + m.group(1) for m in _LINK.finditer(page)}


def _tsv(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""), delimiter="\t")
        for row in reader:
            yield row


def load_dataset_zip(store: EventStore, payload: bytes, label: str,
                     pool_ciks: Optional[Iterable[int]] = None) -> dict:
    """把一个季度 zip 读进库。返回统计。zip 只在内存里过，不落盘。"""
    csv.field_size_limit(10 ** 9)
    pool = None if pool_ciks is None else frozenset(int(c) for c in pool_ciks)
    archive = zipfile.ZipFile(io.BytesIO(payload))
    submissions = {}
    for row in _tsv(archive, "SUBMISSION.tsv"):
        filed = dera_date(row.get("FILING_DATE", ""))
        try:
            issuer = int(row["ISSUERCIK"])
        except (KeyError, ValueError):
            continue
        if filed:
            submissions[row["ACCESSION_NUMBER"]] = (issuer, filed, row.get("DOCUMENT_TYPE", ""))
    owners: dict = {}
    first_seen: dict = {}
    for row in _tsv(archive, "REPORTINGOWNER.tsv"):
        info = submissions.get(row["ACCESSION_NUMBER"])
        if info is None:
            continue
        try:
            owner = int(row["RPTOWNERCIK"])
        except ValueError:
            continue
        owners.setdefault(row["ACCESSION_NUMBER"], []).append(owner)
        if info[1] < first_seen.get(owner, "9999"):
            first_seen[owner] = info[1]
    store.touch_owner_first(first_seen.items(), "dera:" + label)

    def number(text: str) -> Optional[float]:
        try:
            return float(text)
        except ValueError:
            return None

    p_rows = []
    for row in _tsv(archive, "NONDERIV_TRANS.tsv"):
        if row.get("TRANS_CODE") != "P" or row.get("TRANS_ACQUIRED_DISP_CD", "A") not in ("A", ""):
            continue
        accession = row["ACCESSION_NUMBER"]
        info = submissions.get(accession)
        trade_date = dera_date(row.get("TRANS_DATE", ""))
        if info is None or trade_date is None or info[2] != "4":
            continue  # 4/A 修订件与 Form 5 不入买入历史（避免同一笔重复计数）
        for owner in owners.get(accession, []):
            p_rows.append((accession, owner, info[0], trade_date, info[1],
                           number(row.get("TRANS_SHARES", "")), number(row.get("TRANS_PRICEPERSHARE", ""))))
    added = store.add_insider_p(p_rows, "dera:" + label)
    pool_p_accessions = {r[0] for r in p_rows if pool is not None and r[2] in pool}
    store.mark_dataset(label, len(p_rows), datetime.now(timezone.utc).isoformat())
    store.commit()
    return {
        "label": label,
        "submissions": len(submissions),
        "p_rows": len(p_rows),
        "p_rows_added": added,
        "owners_seen": len(first_seen),
        "pool_p_accessions": len(pool_p_accessions),
        "latest_filing": max((v[1] for v in submissions.values()), default=None),
    }


def pool_p_candidates(store: EventStore, pool_ciks: Iterable[int], since: str, until: str,
                      min_amount_usd: float) -> list[tuple]:
    """库里（DERA 来源）候选 Form 4：发行人在池内、申报日在区间内、同一内部人同一份申报里 P 金额合计 >= 门槛。
    返回 [(accession, issuer_cik), ...]。金额只是筛，不是判定：单价缺失的行不猜价，直接放行去看原文。"""
    pool = sorted({int(c) for c in pool_ciks})
    result = {}
    for start in range(0, len(pool), 500):
        chunk = pool[start:start + 500]
        rows = store.db.execute(
            "SELECT accession, issuer_cik, owner_cik, SUM(COALESCE(shares,0)*COALESCE(price,0)) AS amount, "
            "SUM(price IS NULL OR price = 0) AS missing FROM insider_p "
            "WHERE issuer_cik IN (%s) AND filed >= ? AND filed <= ? AND source LIKE 'dera:%%' "
            "GROUP BY accession, issuer_cik, owner_cik" % ",".join("?" * len(chunk)),
            chunk + [since, until])
        for accession, issuer, _owner, amount, missing in rows:
            if amount >= min_amount_usd or missing:
                result[accession] = issuer
    return sorted(result.items())
