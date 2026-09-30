"""SEC 申报原文里的「瓶颈证据标记」（关键词计数），只做标记，不承诺收益。

调研（02_调研依据.md）没有找到「单一来源 / 产能受限 / 交期」类措辞对应收益的实证，
所以这里只产出：哪几类措辞出现了几次、原文链接、一两句摘录。打分时它们只能
- 给瓶颈「结构性约束」的少数因子提供评分上限很低的佐证；
- 提高证据质量维度的一手原文覆盖；
它们绝不进入「股东能分到钱」「错误定价」两个与收益相关的维度。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from ..evidence.factstore import FactStore
from ..evidence.sec_client import ARCHIVE_URL, SecClient, SecFetchError
from .scoring_support import KIND_TEXT, EvidenceRef

# 六类措辞（Owner 给定：sole source / single source / capacity constrained / lead times / backlog / allocation）
MARKER_PATTERNS: Mapping[str, re.Pattern] = {
    "sole_source": re.compile(r"\b(?:sole|single)[- ]sources?(?:d)?\b|\bsole[- ]supplier\b|\bsingle[- ]supplier\b|"
                              r"\bonly (?:one )?(?:qualified )?(?:supplier|source)\b", re.I),
    "capacity_constrained": re.compile(r"\bcapacity[- ]constrain|\bsupply[- ]constrain|\bconstrained (?:by )?(?:supply|capacity)\b|"
                                       r"\bcapacity (?:constraints?|limitations?)\b|\bsupply (?:constraints?|shortages?)\b", re.I),
    "lead_times": re.compile(r"\b(?:extended|longer|long|increased|lengthening|elevated)?\s*lead[- ]times?\b", re.I),
    "backlog": re.compile(r"\bbacklog\b|\bremaining performance obligations?\b", re.I),
    "allocation": re.compile(r"\b(?:product|supply|capacity|component|wafer|material)s? allocations?\b|\ballocat(?:ed|ion) (?:of )?(?:supply|capacity|product)\b|"
                             r"\bon allocation\b|\bsupplier allocations?\b", re.I),
}
MARKER_MIN_COUNT = 2   # 单次提及多是风险提示模板话，出现 ≥2 次才记为「有标记」


@dataclass(frozen=True)
class TextMarkers:
    cik: int
    accession: str
    form: str
    filed: str
    period_end: Optional[str]
    url: str
    chars: int
    counts: Mapping[str, int]
    snippets: Mapping[str, Tuple[str, ...]]

    def present(self, group: str) -> bool:
        return self.counts.get(group, 0) >= MARKER_MIN_COUNT

    def groups_present(self) -> Tuple[str, ...]:
        return tuple(g for g in MARKER_PATTERNS if self.present(g))

    def ref(self, group: str) -> EvidenceRef:
        return EvidenceRef(
            kind=KIND_TEXT, label="text marker %s x%d in %s %s" % (group, self.counts.get(group, 0), self.form, self.filed),
            value=float(self.counts.get(group, 0)), accession=self.accession, form=self.form, filed=self.filed,
            period_end=self.period_end, url=self.url)

    def all_refs(self) -> Tuple[EvidenceRef, ...]:
        return tuple(self.ref(g) for g in self.groups_present())

    def to_dict(self) -> dict:
        return {"cik": self.cik, "accession": self.accession, "form": self.form, "filed": self.filed,
                "period_end": self.period_end, "url": self.url, "chars": self.chars,
                "counts": dict(self.counts), "snippets": {k: list(v) for k, v in self.snippets.items()}}

    @staticmethod
    def from_dict(payload: Mapping) -> "TextMarkers":
        return TextMarkers(payload["cik"], payload["accession"], payload["form"], payload["filed"], payload.get("period_end"),
                           payload["url"], payload["chars"], dict(payload["counts"]),
                           {k: tuple(v) for k, v in payload.get("snippets", {}).items()})


_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_SPACE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    text = _SCRIPT.sub(" ", raw)
    text = _TAG.sub(" ", text)
    return _SPACE.sub(" ", html.unescape(text)).strip()


def scan_text(text: str, snippet_chars: int = 160, snippets_per_group: int = 1) -> Tuple[Dict[str, int], Dict[str, Tuple[str, ...]]]:
    counts: Dict[str, int] = {}
    snippets: Dict[str, Tuple[str, ...]] = {}
    for group, pattern in MARKER_PATTERNS.items():
        matches = list(pattern.finditer(text))
        counts[group] = len(matches)
        if matches:
            picked: List[str] = []
            for match in matches[:snippets_per_group]:
                start = max(0, match.start() - snippet_chars // 2)
                picked.append(text[start:start + snippet_chars].strip())
            snippets[group] = tuple(picked)
    return counts, snippets


def latest_periodic_with_document(store: FactStore, cik: int, as_of: str) -> Optional[dict]:
    """as_of 之前已申报的最近一份带主文档的 10-K（优先）或 10-Q。"""
    rows = [r for r in store.filings_as_of(cik, as_of, ("10-K", "10-KT", "10-Q", "10-QT"))
            if r.get("primary_document") and "/" not in r["primary_document"]]
    if not rows:
        return None
    annual = [r for r in rows if r["form"] in ("10-K", "10-KT")]
    newest_any = max(rows, key=lambda r: (r["filed"], r["accession"]))
    newest_annual = max(annual, key=lambda r: (r["filed"], r["accession"])) if annual else None
    # 年报措辞最完整；但若年报已是一年前、季报更新很多，就用较新的季报
    if newest_annual and (date.fromisoformat(newest_any["filed"]) - date.fromisoformat(newest_annual["filed"])).days <= 200:
        return newest_annual
    return newest_any


def fetch_markers_for_row(client: SecClient, cik: int, row: dict, max_bytes: int = 12_000_000) -> Optional[TextMarkers]:
    """只做网络与文本扫描（不碰 SQLite），可以放进线程池；row 由主线程用 latest_periodic_with_document 取好。"""
    url = ARCHIVE_URL.format(cik=int(cik), accession_nodash=row["accession"].replace("-", ""), name=row["primary_document"])
    try:
        body = client.get_bytes(url)
    except SecFetchError:
        return None
    if len(body) > max_bytes:
        body = body[:max_bytes]
    text = html_to_text(body.decode("utf-8", errors="replace"))
    counts, snippets = scan_text(text)
    return TextMarkers(int(cik), row["accession"], row["form"], row["filed"], row.get("report_date"), url, len(text),
                       counts, snippets)


def fetch_markers(client: SecClient, store: FactStore, cik: int, as_of: str) -> Optional[TextMarkers]:
    row = latest_periodic_with_document(store, cik, as_of)
    return None if row is None else fetch_markers_for_row(client, cik, row)
