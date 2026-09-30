"""EDGAR 申报索引：每日索引（当季未结束部分）与季度全量索引（已结束季度），批量发现申报。

daily-index/YYYY/QTRn/form.YYYYMMDD.idx  —— 一天一个文件，当季用它；
full-index/YYYY/QTRn/form.gz             —— 一整季一个文件，已结束季度用它（同一格式，只是日期写法不同）。
索引只告诉我们「哪家公司在哪天交了什么表、accession 是多少」，不含表内内容；
表内内容（Form 4 交易、8-K 事项）再按需取原文。
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Iterator, Optional

from .sec_client import SecClient, SecNotFound

DAILY_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/form.{ymd}.idx"
FULL_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/form.gz"
ARCHIVE_ACCESSION_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"

_ROW = re.compile(
    r"^(?P<form>\S.*?)\s{2,}(?P<company>.+?)\s+(?P<cik>\d{1,10})\s+"
    r"(?P<filed>\d{8}|\d{4}-\d{2}-\d{2})\s+(?P<file>edgar/\S+)\s*$"
)
_ACCESSION = re.compile(r"(\d{10}-\d{2}-\d{6})\.txt$")


@dataclass(frozen=True)
class IndexRow:
    form: str
    company: str
    cik: int
    filed: str          # YYYY-MM-DD
    accession: str      # 0001234567-26-000123
    file_name: str      # edgar/data/<cik>/<accession>.txt

    @property
    def txt_url(self) -> str:
        return "https://www.sec.gov/" + self.file_name

    @property
    def index_url(self) -> str:
        """人能点开的申报索引页（真实 SEC 页面）。"""
        return "https://www.sec.gov/Archives/edgar/data/%d/%s/%s-index.htm" % (
            self.cik, self.accession.replace("-", ""), self.accession)


def _iso(text: str) -> str:
    return text if "-" in text else "%s-%s-%s" % (text[:4], text[4:6], text[6:8])


def parse_form_index(text: str, forms: Optional[Iterable[str]] = None,
                     ciks: Optional[Iterable[int]] = None) -> Iterator[IndexRow]:
    """解析 form.idx 文本；可按表格类型与 CIK 过滤（过滤在解析时做，避免为 35 万行建对象）。"""
    wanted_forms = None if forms is None else frozenset(forms)
    wanted_ciks = None if ciks is None else frozenset(int(c) for c in ciks)
    for line in text.splitlines():
        if len(line) < 60 or line.startswith(("Form Type", "---", "Description", "Last Data", "Comments", "Anonymous")):
            continue
        match = _ROW.match(line)
        if match is None:
            continue
        form = match.group("form").strip()
        if wanted_forms is not None and form not in wanted_forms:
            continue
        cik = int(match.group("cik"))
        if wanted_ciks is not None and cik not in wanted_ciks:
            continue
        accession = _ACCESSION.search(match.group("file"))
        if accession is None:
            continue
        yield IndexRow(form, match.group("company").strip(), cik, _iso(match.group("filed")),
                       accession.group(1), match.group("file"))


def quarter_of(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    start = date(year, 3 * quarter - 2, 1)
    end = date(year + 1, 1, 1) - timedelta(days=1) if quarter == 4 else date(year, 3 * quarter + 1, 1) - timedelta(days=1)
    return start, end


def _quarters_between(start: date, end: date) -> list[tuple[int, int]]:
    result, cursor = [], quarter_of(start)
    while cursor <= quarter_of(end):
        result.append(cursor)
        cursor = (cursor[0] + (cursor[1] == 4), cursor[1] % 4 + 1)
    return result


def fetch_full_index(client: SecClient, year: int, quarter: int, forms=None, ciks=None) -> list[IndexRow]:
    body = client.get_bytes(FULL_URL.format(year=year, quarter=quarter), immutable=True)
    text = gzip.decompress(body).decode("latin-1")
    return list(parse_form_index(text, forms, ciks))


DAILY_LISTING_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/"
_DAILY_NAME = re.compile(r"form\.(\d{8})\.idx")


def list_daily_days(client: SecClient, year: int, quarter: int) -> set:
    """该季度实际存在每日索引的日期。节假日没有文件，直接请求会得到 403（会被当成限流重试），
    所以先读目录页，只取列出来的日子。"""
    page = client.get_bytes(DAILY_LISTING_URL.format(year=year, quarter=quarter)).decode("latin-1")
    return {date(int(d[:4]), int(d[4:6]), int(d[6:8])) for d in _DAILY_NAME.findall(page)}


def fetch_daily_index(client: SecClient, day: date, forms=None, ciks=None) -> list[IndexRow]:
    """已收盘的日子内容不再变，命中缓存不再发请求；不存在的日子（404）返回空表。"""
    url = DAILY_URL.format(year=day.year, quarter=quarter_of(day)[1], ymd=day.strftime("%Y%m%d"))
    try:
        text = client.get_bytes(url, immutable=day < date.today()).decode("latin-1")
    except SecNotFound:
        return []
    return list(parse_form_index(text, forms, ciks))


def discover_filings(client: SecClient, start: date, end: date, forms=None, ciks=None,
                     as_of: Optional[date] = None) -> list[IndexRow]:
    """[start, end] 区间内的申报。整季已结束的用季度全量索引，其余按日取每日索引。
    as_of（默认等于 end）之后申报的一律丢弃——时点正确的第一道闸。"""
    limit = min(end, as_of) if as_of is not None else end
    rows: list[IndexRow] = []
    for year, quarter in _quarters_between(start, limit):
        q_start, q_end = quarter_bounds(year, quarter)
        if q_end < date.today() and q_end <= limit:
            found = fetch_full_index(client, year, quarter, forms, ciks)
        else:
            found = []
            for day in sorted(list_daily_days(client, year, quarter)):
                if max(start, q_start) <= day <= min(limit, q_end):
                    found.extend(fetch_daily_index(client, day, forms, ciks))
        rows.extend(row for row in found if start.isoformat() <= row.filed <= limit.isoformat())
    return rows
