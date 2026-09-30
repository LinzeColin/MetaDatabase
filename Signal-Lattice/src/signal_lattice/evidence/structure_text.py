"""10-K / 10-Q 正文里的「结构性证据」确定性抽取器（标准库正则，零模型）。

抽五类（外加两类辅助），每条都保留原句、所在段落、所在章节，以及申报的 accession 与原文链接：

  lead_time              交期："lead times of N weeks/months"、"N-week lead time"
  sole_source            单一/唯一来源、唯一供应商（不带数字，只作定性）
  purchase_share         "accounted for N% of purchases"、某个单一供应商占采购的百分比（永远是上游依赖）
  customer_concentration 客户集中度："one customer accounted for N% of revenue"、"Customer A 23%"
  qualification          认证/资格周期："qualification ... N months/years"
  capacity_constraint    产能受限、产能利用率 N%、满负荷
  backlog                "backlog of $N"

方向（direction）——这是本模块最重要的一道判别，因为同一句「sole source」有两个相反的含义：
  OWNER      公司自己是瓶颈拥有者（"we are the sole source ..."、客户的积压订单、客户换供应商要认证 N 个月）
  UPSTREAM   公司依赖上游单一来源/长交期/上游产能受限（"we rely on a sole source supplier ..."）——这是风险，不是加分
  AMBIGUOUS  两边都说得通，或判不出主语——不计入加分，也不计入风险打分（只留在证据里给人看）
  RISK       客户集中度本身就是风险方向，没有方向之争

方向判别只看句子里的显式主语线索（"we are the ..." 对 "we rely on ... our suppliers ..."），线索不足一律 AMBIGUOUS；
宁可漏判，不把上游风险冒充成瓶颈优势。

只做抽取与分类，不打分——打分在 branches/bottleneck.py，按 scoring_model.md 的 0-5 锚点接入。
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

EXTRACTOR_VERSION = "structure-text/2"

OWNER = "OWNER"
UPSTREAM = "UPSTREAM"
AMBIGUOUS = "AMBIGUOUS"
RISK = "RISK"

KINDS = ("lead_time", "sole_source", "purchase_share", "customer_concentration", "qualification",
         "capacity_constraint", "backlog")

MAX_SENTENCE_CHARS = 420
MAX_PARAGRAPH_CHARS = 900
MAX_ITEMS_PER_KIND = 6          # 每类每个方向只留最有信息量的几条，缓存文件不膨胀

_WEEKS_TO_MONTHS = 12.0 / 52.0
_DAYS_TO_MONTHS = 1.0 / 30.4

# ---- 基础零件 -----------------------------------------------------------------------
_NUM = r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
_DURATION = re.compile(
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:(?:to|-|–|—|and|or)\s*(?P<b>\d+(?:\.\d+)?)\s*)?[- ]?(?P<u>weeks?|months?|days?|years?)\b", re.I)
_SECTION_HEAD = re.compile(r"^\s*item\s+(\d{1,2}[abc]?)\b\.?\s*(.{0,60})", re.I)
_SENTENCE_START = re.compile(r"(?<=[.!?;])\s+(?=[A-Z(“\"])")
_ABBREV_END = re.compile(r"(?:\bInc|\bCorp|\bCo|\bLtd|\bNo|\bU\.S|\bSt|\bvs|\bapprox|\be\.g|\bi\.e|\bDr|\bMr|\bMs)\.$")

_MONEY_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "mm": 1e6, "billion": 1e9, "b": 1e9, "bn": 1e9}


def _months(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("week"):
        return value * _WEEKS_TO_MONTHS
    if unit.startswith("day"):
        return value * _DAYS_TO_MONTHS
    if unit.startswith("year"):
        return value * 12.0
    return value


def duration_months(text: str) -> Optional[Tuple[float, float, str]]:
    """句内第一个持续时间表达 -> (低端月数, 高端月数, 原文)。区间取两端。"""
    match = _DURATION.search(text)
    if not match:
        return None
    unit = match.group("u")
    low = _months(float(match.group("a")), unit)
    high = _months(float(match.group("b")), unit) if match.group("b") else low
    if high < low:
        low, high = high, low
    return low, high, match.group(0)


# ---- 句子/段落 -----------------------------------------------------------------------
def sentence_around(paragraph: str, start: int, end: int) -> str:
    """包含 [start, end) 的那一句（按 .!?; 加大写字母起头切；缩写不算句末）。"""
    boundaries = [0]
    for match in _SENTENCE_START.finditer(paragraph):
        cut = match.start()
        if _ABBREV_END.search(paragraph[max(0, cut - 8):cut + 1]):
            continue
        boundaries.append(match.end())
    boundaries.append(len(paragraph) + 1)
    lo = max(b for b in boundaries if b <= start)
    hi = min(b for b in boundaries if b >= end)
    sentence = paragraph[lo:hi].strip()
    if len(sentence) > MAX_SENTENCE_CHARS:
        centre = start - lo
        left = max(0, centre - MAX_SENTENCE_CHARS // 2)
        sentence = sentence[left:left + MAX_SENTENCE_CHARS].strip()
    return sentence


def _trim_paragraph(paragraph: str, start: int) -> str:
    if len(paragraph) <= MAX_PARAGRAPH_CHARS:
        return paragraph
    left = max(0, start - MAX_PARAGRAPH_CHARS // 2)
    return paragraph[left:left + MAX_PARAGRAPH_CHARS].strip()


# ---- 方向判别 -----------------------------------------------------------------------
# 上游线索：公司在「买」「依赖」「被供货」
_UPSTREAM_STRONG = tuple(re.compile(p, re.I) for p in (
    r"\bwe\s+(?:currently\s+)?(?:rely|depend|purchase|source|obtain|procure|buy|outsource)\b",
    r"\b(?:the\s+)?company\s+(?:relies|depends|purchases|sources|obtains|procures|buys)\b",
    r"\b(?:dependent|reliant|reliance)\s+(?:up)?on\b",
    r"\bour\s+(?:(?:contract|third[- ]party|key|primary|principal|main|current)\s+){0,2}"
    r"(?:suppliers?|vendors?|manufacturers?|foundr(?:y|ies)|subcontractors?|supply\s+chain|component\s+suppliers?|CMOs?|CDMOs?|CROs?)\b",
    r"\b(?:suppliers?|vendors?)['’]?\s+(?:lead|capacity|shortages?|delays?|allocation)",
    r"\bfrom\s+(?:a\s+|an\s+|one\s+|our\s+|the\s+|third[- ]party\s+|these\s+|such\s+)?(?:sole|single|limited|few|suppliers?|vendors?)",
    r"\bqualif\w*\s+(?:a\s+|an\s+|any\s+)?(?:new|alternative|additional|second)\s+(?:suppliers?|vendors?|sources?|manufacturers?)",
    r"\b(?:CMOs?|CDMOs?)\b",
))
# 弱线索：只是名词（component/equipment/supplies...），不足以单独判上游
_UPSTREAM_WEAK = tuple(re.compile(p, re.I) for p in (
    r"\b(?:components?|raw\s+materials?|parts|wafers|substrates?|ingredients|supplies|equipment|materials?)\b",
))
# 拥有者线索：公司是被别人依赖的那一方
_OWNER_CUES = tuple(re.compile(p, re.I) for p in (
    r"\bwe\s+(?:are|were|have\s+been|remain)\s+(?:currently\s+)?(?:the|a|an|one\s+of)\s+(?:only|sole|single|few|limited|leading|two|three)\b",
    r"\bour\s+(?:customers?|orders?|backlog|products?|manufacturing|production|facilit\w+|plants?|capacity|deliver\w+|"
    r"(?:manufacturing|production|delivery|product)\s+lead)\b",
    r"\bto\s+(?:our\s+)?customers?\b",
    r"\bcustomers?['’]?\s+(?:orders?|requirements?|demand|switch\w*|qualif\w+)",
    r"\bdemand\s+(?:for|from)\b",
    r"\bcompetitors?\b|\bnew\s+entrants?\b|\bswitching\b|\bdisplac\w+|\bbarriers?\s+to\s+entry\b",
    r"\bwe\s+(?:sell|ship|deliver|supply|produce|manufacture|build)\b",
))
_OWNER_SOLE = re.compile(
    r"\bwe\s+(?:are|were|remain|have\s+been)\s+(?:currently\s+)?(?:the\s+|a\s+|an\s+)?(?:sole|single|only)(?:[- ]|\s+qualified\s+|\s+approved\s+)"
    r"(?:source|supplier|provider|manufacturer|vendor|producer|commercial\s+source)"
    r"|\bwe\s+are\s+(?:currently\s+)?the\s+only\s+(?:company|manufacturer|supplier|provider|producer)\b"
    r"|\bwe\s+are\s+one\s+of\s+(?:only\s+|just\s+)?(?:two|three|a\s+(?:very\s+)?(?:few|limited\s+number\s+of))\s+"
    r"(?:qualified\s+|approved\s+|certified\s+)?(?:suppliers|manufacturers|providers|vendors|sources|producers|companies)\b"
    r"|\b(?:sole|single|only)[- ]source\s+(?:supplier|provider)\s+(?:to|for|of)\s+(?:our\s+)?customers?\b", re.I)


def _cue_score(sentence: str, cues: Sequence["re.Pattern"]) -> int:
    return sum(1 for cue in cues if cue.search(sentence))


def classify_direction(sentence: str, *, strict_owner: bool = False) -> str:
    """句子里显式线索多的一方赢；持平或都没有 -> AMBIGUOUS。
    strict_owner（sole_source 用）：拥有者必须有显式的自称句式；上游必须有强线索（rely/depend/our suppliers...），
    光有 component/equipment 这类名词不够。"""
    strong = _cue_score(sentence, _UPSTREAM_STRONG)
    weak = _cue_score(sentence, _UPSTREAM_WEAK)
    up = strong * 2 + weak
    own = _cue_score(sentence, _OWNER_CUES)
    if strict_owner:
        if _OWNER_SOLE.search(sentence):
            return OWNER
        return UPSTREAM if strong > 0 and own <= strong else AMBIGUOUS
    if up > own:
        return UPSTREAM
    if own > up:
        return OWNER
    return AMBIGUOUS


# ---- 数据结构 -------------------------------------------------------------------------
@dataclass(frozen=True)
class Extraction:
    kind: str
    direction: str
    sentence: str
    paragraph: str
    section: Optional[str]
    value: Optional[float] = None       # lead_time/qualification：高端月数；*_share：百分比；backlog：美元；capacity：利用率%
    value_low: Optional[float] = None   # 区间低端 / backlog 的对比期数值
    unit: Optional[str] = None          # months | percent | usd
    detail: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "direction": self.direction, "sentence": self.sentence, "paragraph": self.paragraph,
                "section": self.section, "value": self.value, "value_low": self.value_low, "unit": self.unit,
                "detail": dict(self.detail)}

    @staticmethod
    def from_dict(payload: Mapping) -> "Extraction":
        return Extraction(payload["kind"], payload["direction"], payload["sentence"], payload["paragraph"],
                          payload.get("section"), payload.get("value"), payload.get("value_low"), payload.get("unit"),
                          dict(payload.get("detail") or {}))


@dataclass(frozen=True)
class FilingExtraction:
    cik: int
    accession: str
    form: str
    filed: str
    period_end: Optional[str]
    url: str
    chars: int
    version: str
    items: Tuple[Extraction, ...]

    def of(self, kind: str, direction: Optional[str] = None) -> List[Extraction]:
        return [i for i in self.items if i.kind == kind and (direction is None or i.direction == direction)]

    def counts(self) -> Dict[str, Dict[str, int]]:
        table: Dict[str, Dict[str, int]] = {}
        for item in self.items:
            table.setdefault(item.kind, {}).setdefault(item.direction, 0)
            table[item.kind][item.direction] += 1
        return table

    def to_dict(self) -> dict:
        return {"cik": self.cik, "accession": self.accession, "form": self.form, "filed": self.filed,
                "period_end": self.period_end, "url": self.url, "chars": self.chars, "version": self.version,
                "items": [i.to_dict() for i in self.items]}

    @staticmethod
    def from_dict(payload: Mapping) -> "FilingExtraction":
        return FilingExtraction(int(payload["cik"]), payload["accession"], payload["form"], payload["filed"],
                                payload.get("period_end"), payload["url"], int(payload["chars"]), payload["version"],
                                tuple(Extraction.from_dict(i) for i in payload["items"]))


# ---- 各类抽取 -------------------------------------------------------------------------
_LEAD_AFTER = re.compile(r"\blead[- ]times?\b[^.;]{0,90}?" + _DURATION.pattern, re.I)
_LEAD_BEFORE = re.compile(r"(?P<a>\d+(?:\.\d+)?)\s*(?:(?:to|-|–|—|and|or)\s*(?P<b>\d+(?:\.\d+)?)\s*)?[- ]?(?P<u>weeks?|months?|days?)\b[- ]?"
                          r"(?:long\s+)?(?:manufacturing\s+|production\s+|delivery\s+|procurement\s+)?lead[- ]times?\b", re.I)

_SOLE_NOT_SUPPLY = re.compile(r"\bsole\s+source\s+of\s+(?:gain|return|income|revenues?|liquidity|funds?|funding|cash|capital|payments?|"
                              r"recovery|remedy|profits?|earnings|support|repayment|distributions?|dividends?)\b", re.I)
_SOLE = re.compile(
    r"\b(?:sole|single)[- ]sourced?\b|\bsole[- ]sourc(?:e|es|ed|ing)\b|\b(?:sole|single|only)[- ](?:supplier|provider|vendor|manufacturer|source)s?\b|"
    r"\bonly\s+(?:one|a\s+single)\s+(?:qualified\s+|approved\s+)?(?:supplier|source|vendor|manufacturer|provider)\b|"
    r"\bone\s+of\s+(?:only\s+|just\s+)?(?:two|three)\s+(?:qualified\s+|approved\s+)?(?:suppliers|manufacturers|providers|sources)\b", re.I)

_PURCHASE_SHARE = tuple(re.compile(p, re.I) for p in (
    r"accounted\s+for\s+(?:approximately\s+|about\s+|over\s+|more\s+than\s+|nearly\s+)?(?P<p>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s+of\s+"
    r"(?:our\s+|the\s+company['’]s\s+|total\s+|aggregate\s+)*(?:inventory\s+|raw\s+material\s+|component\s+|material\s+|product\s+)?purchases",
    r"(?P<p>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(?:our\s+|the\s+company['’]s\s+|total\s+|aggregate\s+)*"
    r"(?:inventory\s+|raw\s+material\s+|component\s+|material\s+|product\s+)?purchases",
    r"(?:sole|single|largest|principal|primary|one|two|three|top\s+\w+)\s+(?:supplier|vendor|manufacturer|source|contract\s+manufacturer)s?\b[^.]{0,160}?"
    r"(?:accounted\s+for|represented|supplied|provided|was|were|comprised)[^.%]{0,60}?(?P<p>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)",
))

_CUSTOMER_WORD = r"(?:customers?|distributors?|resellers?|clients?|OEMs?|channel\s+partners?|retailers?|wholesalers?)"
_REV_OBJECT = (r"(?:revenues?|net\s+sales|sales)")
_CUSTOMER_PCT = tuple(re.compile(p, re.I) for p in (
    # "one customer accounted for 23% of revenue" / "our largest customer represented 34% of net sales" / "top ten customers ... 81%"
    r"\b(?:one|two|three|four|five|a\s+single|single|our\s+(?:largest|top|largest\s+single)|the\s+(?:largest|top)|largest|top\s+(?:five|ten|\d+)|\d+\s+largest|\d+)\b"
    r"[^.%]{0,60}?" + _CUSTOMER_WORD + r"\b[^.%]{0,200}?"
    r"(?P<p>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(?:our\s+|the\s+company['’]s\s+|total\s+|consolidated\s+|net\s+|gross\s+)*" + _REV_OBJECT,
    # "23% of our revenue was from one customer"
    r"(?P<p>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(?:our\s+|the\s+company['’]s\s+|total\s+|consolidated\s+|net\s+)*" + _REV_OBJECT +
    r"[^.]{0,120}?\b(?:from|to|by|with)\s+(?:a\s+|one\s+|our\s+|two\s+|three\s+)?(?:single\s+|largest\s+|major\s+|top\s+)?" + _CUSTOMER_WORD + r"\b",
    # 表格行："Customer A 23 % 19 %"
    r"\bcustomer\s+(?P<who>[A-Z0-9])\b[^\n%]{0,30}?(?P<p>\d{1,3}(?:\.\d+)?)\s*%",
))
_NO_CUSTOMER = re.compile(
    r"\bno\s+(?:single\s+|individual\s+|one\s+)?(?:end[- ])?customers?[^.]{0,120}?(?:accounted\s+for|represented|exceed\w*|in\s+excess\s+of|more\s+than|greater\s+than|over)[^.]{0,60}?10\s*(?:%|percent)"
    r"[^.]{0,40}?\b(?:revenues?|net\s+sales|sales)\b", re.I)
_NOT_CUSTOMER_SCOPE = re.compile(r"outside\s+(?:of\s+)?(?:the\s+)?(?:United\s+States|U\.S\.)|international|foreign|domestic|geograph|"
                                 r"located\s+(?:in|outside)|based\s+in|end\s+markets?|segments?\b|product\s+lines?|receivables?|region|"
                                 r"countr(?:y|ies)|territor|\b(?:China|Asia|Europe|Americas|EMEA|APAC|Japan|Canada|Mexico|India)\b", re.I)
_NEGATED = re.compile(r"\b(?:no|none|not|neither|nor)\b|less\s+than|fewer\s+than|below|under\s+\d", re.I)
_SINGULAR_CUSTOMER = re.compile(r"\b(?:one|a\s+single|single|our\s+largest|the\s+largest|largest|top|major|significant)\s+(?:end[- ])?"
                                r"(?:customer|distributor|reseller|client|OEM|retailer|channel\s+partner)\b(?!s)|\bcustomer\s+[A-Z0-9]\b", re.I)
_LOWER_BOUND = re.compile(r"(?:more|greater)\s+than\s*$|in\s+excess\s+of\s*$|exceed\w*\s*$|over\s*$|at\s+least\s*$|each\s+(?:regularly\s+)?(?:exceeding|over)\s*$", re.I)
_TOP_N = re.compile(r"\btop\s+(?:five|ten|\d+)\s+customers?\b|\b(?:five|ten|\d+)\s+largest\s+customers?\b", re.I)

_QUAL = re.compile(r"\bqualification\s+(?:process|period|cycle|time|timeline|lead\s+time|requirements?|and\s+(?:certification|validation))\b|"
                   r"\b(?:qualify|qualifying|qualified)\s+(?:a\s+|an\s+|any\s+|our\s+|the\s+|new\s+|alternative\s+|additional\s+|second\s+)*"
                   r"(?:suppliers?|vendors?|sources?|manufacturers?|products?|components?|parts?|designs?|materials?|foundr\w+|facilit\w+|processes)\b|"
                   r"\b(?:design[- ]in|design[- ]win|qualification)\b", re.I)
_QUAL_DURATION = re.compile(r"(?P<a>\d+(?:\.\d+)?)\s*(?:(?:to|-|–|—|and|or)\s*(?P<b>\d+(?:\.\d+)?)\s*)?[- ]?(?P<u>weeks?|months?|years?)\b", re.I)
_QUAL_NOT = re.compile(r"exclusivity|\bBLA\b|\bFDA\b|patent|\bREIT\b|tax[- ]qualified|qualified\s+(?:opportunity|zone|dividend|plan|retirement|purchaser|institutional)|"
                       r"purchased\s+seasoned|qualif\w+\s+as\s+a\b|orphan|breakthrough|fast\s+track|clinical", re.I)
_QUAL_MOAT = re.compile(r"\bswitch\w*|\breplac\w+|\bdisplac\w+|\bcompetitors?\b|\bnew\s+entrants?\b|\bbarriers?\b|\bincumbent|\bsticky|"
                        r"\bdifficult\s+for\s+(?:competitors|others)|\bentry\b", re.I)
_QUAL_UPSTREAM = re.compile(r"\bqualif\w*\s+(?:a\s+|an\s+|any\s+)?(?:new|alternative|additional|second|replacement|other)\s+"
                            r"(?:suppliers?|vendors?|sources?|manufacturers?|foundr\w+)|\b(?:suppliers?|vendors?|sources?)\b[^.]{0,80}\bqualif|"
                            r"\bqualif\w*\b[^.]{0,80}\b(?:our\s+suppliers?|alternative\s+(?:suppliers?|sources?)|second\s+source)", re.I)
_QUAL_CUSTOMER_BARRIER = re.compile(r"\b(?:our\s+)?customers?\b[^.]{0,100}\bqualif\w*[^.]{0,60}\b(?:new|alternative|another|different)\s+(?:suppliers?|vendors?)", re.I)

_CAP_OWNER = tuple(re.compile(p, re.I) for p in (
    r"\bwe\s+(?:are|were|have\s+been|remain|continue\s+to\s+be)\s+(?:currently\s+|presently\s+)?(?:operating\s+)?(?:capacity|supply|production)[- ]constrained\b",
    r"\boperat\w+\s+(?:at|near)\s+(?:or\s+near\s+)?(?:full|maximum|peak|our)\s+(?:production\s+|manufacturing\s+)?capacity\b",
    r"\bdemand\s+(?:for\s+our\s+[\w\s,-]{0,60}?)?(?:has\s+)?(?:exceed\w*|outpac\w+|outstrip\w*)\s+(?:our\s+)?(?:current\s+|existing\s+)?(?:production\s+|manufacturing\s+)?(?:capacity|supply)\b",
    r"\bunable\s+to\s+(?:fully\s+)?(?:meet|fulfill|satisfy)\s+(?:all\s+)?(?:customer\s+)?(?:demand|orders)\b[^.]{0,80}?\b(?:capacity|constraint)",
    r"\b(?:our|the)\s+(?:manufacturing\s+|production\s+)?(?:facilit\w+|plants?|factor\w+|lines?)\s+(?:is|are|was|were)\s+(?:currently\s+)?(?:operating\s+)?(?:at|near)\s+(?:full\s+)?capacity\b",
    r"\bcapacity\s+utili[sz]ation\b[^.]{0,80}?(?P<p>\d{2,3}(?:\.\d+)?)\s*(?:%|percent)",
    r"(?P<p>\d{2,3}(?:\.\d+)?)\s*(?:%|percent)\s+(?:capacity\s+)?utili[sz]ation",
    r"\butili[sz]ation\s+(?:rate\s+)?(?:of|was|were|at|reached)\s+(?:approximately\s+|about\s+)?(?P<p>\d{2,3}(?:\.\d+)?)\s*(?:%|percent)",
))
_CAP_GENERIC = re.compile(r"\bcapacity[- ]constrain\w*|\bsupply[- ]constrain\w*|\bconstrained\s+(?:by\s+)?(?:supply|capacity)\b|"
                          r"\bcapacity\s+(?:constraints?|limitations?|shortages?)\b|\bsupply\s+(?:constraints?|shortages?|disruptions?)\b|"
                          r"\bcomponent\s+shortages?\b", re.I)
_CAP_UPSTREAM = re.compile(r"\b(?:suppliers?|vendors?|foundr\w+|manufacturers?)\b[^.]{0,60}(?:capacity|constrain|shortage|utili)", re.I)

_BACKLOG = re.compile(
    r"\bbacklog\b[^.]{0,120}?\$\s?(?P<n>%s)\s*(?P<u>thousand|million|billion|K|M|B|MM|bn)?\b|"
    r"\$\s?(?P<n2>%s)\s*(?P<u2>thousand|million|billion|K|M|B|MM|bn)?\s+(?:of|in)\s+(?:(?:total\s+|firm\s+|order\s+|customer\s+|contracted\s+)*)backlog\b" % (_NUM, _NUM), re.I)
_BACKLOG_PRIOR = re.compile(r"(?:compared\s+(?:to|with)|from|versus|vs\.?)[^.$]{0,60}?\$\s?(?P<n>%s)\s*(?P<u>thousand|million|billion|K|M|B|MM|bn)?\b" % _NUM, re.I)


def _add(items: List[Extraction], seen: set, extraction: Extraction) -> None:
    key = (extraction.kind, extraction.sentence[:160])
    if key in seen:
        return
    seen.add(key)
    items.append(extraction)


def _money(value: str, unit: Optional[str]) -> float:
    return float(value.replace(",", "")) * _MONEY_MULT.get((unit or "").lower(), 1.0)


def _scan_paragraph(paragraph: str, section: Optional[str], out: List[Extraction], seen: set) -> None:
    low = paragraph.lower()

    def para(start: int) -> str:
        return _trim_paragraph(paragraph, start)

    if "lead" in low:
        for pattern in (_LEAD_AFTER, _LEAD_BEFORE):
            for match in pattern.finditer(paragraph):
                unit = match.group("u")
                low_m = _months(float(match.group("a")), unit)
                high_m = _months(float(match.group("b")), unit) if match.group("b") else low_m
                if high_m < low_m:
                    low_m, high_m = high_m, low_m
                sentence = sentence_around(paragraph, match.start(), match.end())
                _add(out, seen, Extraction("lead_time", classify_direction(sentence), sentence, para(match.start()), section,
                                           value=round(high_m, 3), value_low=round(low_m, 3), unit="months",
                                           detail={"expression": match.group(0)[:160]}))
    if "sole" in low or "single" in low or "only one" in low or "one of only" in low or "one of two" in low or "one of three" in low:
        for match in _SOLE.finditer(paragraph):
            sentence = sentence_around(paragraph, match.start(), match.end())
            if _SOLE_NOT_SUPPLY.search(sentence) or re.search(r"\bno\s+(?:single|sole)\s+(?:supplier|vendor|source|manufacturer)", sentence, re.I):
                continue
            _add(out, seen, Extraction("sole_source", classify_direction(sentence, strict_owner=True), sentence,
                                       para(match.start()), section, detail={"expression": match.group(0)}))
    if "purchase" in low or "supplier" in low or "vendor" in low or "manufacturer" in low:
        for pattern in _PURCHASE_SHARE:
            for match in pattern.finditer(paragraph):
                share = float(match.group("p"))
                if share <= 0 or share > 100:
                    continue
                sentence = sentence_around(paragraph, match.start(), match.end())
                if re.search(r"\bno\s+(?:single\s+|one\s+)?(?:supplier|vendor|manufacturer|source)|\bnone\s+of\s+our\s+(?:suppliers|vendors)|"
                             r"accounts?\s+payable|\bpayables?\b", sentence, re.I) \
                        or not re.search(r"suppliers?|vendors?|manufacturers?|sources?", sentence, re.I) \
                        or not re.search(r"purchases|cost\s+of\s+(?:goods|sales|revenue)|supply\s+of|inventory", sentence, re.I):
                    continue
                before = paragraph[max(0, match.start("p") - 40):match.start("p")]
                floor = bool(re.search(r"(?:greater|more)\s+than\s*$|in\s+excess\s+of\s*$|exceed\w*\s*$|over\s*$|at\s+least\s*$", before, re.I))
                _add(out, seen, Extraction("purchase_share", UPSTREAM, sentence, para(match.start()), section,
                                           value=share, unit="percent", detail={"expression": match.group(0)[:200], "lower_bound": floor}))
    if "customer" in low or "distributor" in low or "reseller" in low:
        for pattern in _CUSTOMER_PCT:
            for match in pattern.finditer(paragraph):
                share = float(match.group("p"))
                if share <= 0 or share > 100:
                    continue
                sentence = sentence_around(paragraph, match.start(), match.end())
                head = match.group(0)[:match.start("p") - match.start()]
                lead_in = paragraph[max(0, match.start() - 80):match.start()]
                tail = paragraph[match.end():match.end() + 70]
                if (_NOT_CUSTOMER_SCOPE.search(match.group(0) + " " + tail) or re.search(r"receivables?|payables?", sentence, re.I)
                        or _NEGATED.search(head) or _NEGATED.search(lead_in.rsplit(".", 1)[-1])):
                    continue
                if "who" in pattern.groupindex:
                    scope = "single"
                elif _TOP_N.search(match.group(0)) or not _SINGULAR_CUSTOMER.search(match.group(0)):
                    scope = "multi"
                else:
                    scope = "single"
                lower = bool(_LOWER_BOUND.search(paragraph[max(0, match.start("p") - 40):match.start("p")]))
                _add(out, seen, Extraction("customer_concentration", RISK, sentence, para(match.start()), section,
                                           value=share, unit="percent",
                                           detail={"scope": scope, "lower_bound": lower, "expression": match.group(0)[:200]}))
        for match in _NO_CUSTOMER.finditer(paragraph):
            sentence = sentence_around(paragraph, match.start(), match.end())
            _add(out, seen, Extraction("customer_concentration", RISK, sentence, para(match.start()), section,
                                       value=0.0, unit="percent", detail={"scope": "none_over_10pct", "expression": match.group(0)[:200]}))
    if "qualif" in low:
        for match in _QUAL.finditer(paragraph):
            sentence = sentence_around(paragraph, match.start(), match.end())
            if _QUAL_NOT.search(sentence):
                continue
            anchor = sentence.lower().find(match.group(0).lower())
            window = sentence[max(0, anchor - 60):][:260]
            dm = _QUAL_DURATION.search(window)
            if not dm:
                continue
            low_m = _months(float(dm.group("a")), dm.group("u"))
            high_m = _months(float(dm.group("b")), dm.group("u")) if dm.group("b") else low_m
            if high_m < low_m:
                low_m, high_m = high_m, low_m
            if not 1.0 <= high_m <= 60.0:
                continue
            expression = dm.group(0)
            if _QUAL_CUSTOMER_BARRIER.search(sentence):
                direction = OWNER               # 客户给别的供应商做认证要 N 个月 = 公司作为在位者的壁垒
            elif _QUAL_UPSTREAM.search(sentence):
                direction = UPSTREAM
            elif _QUAL_MOAT.search(sentence):
                direction = OWNER
            else:
                direction = AMBIGUOUS
            _add(out, seen, Extraction("qualification", direction, sentence, para(match.start()), section,
                                       value=round(high_m, 3), value_low=round(low_m, 3), unit="months",
                                       detail={"expression": expression}))
    if "capacity" in low or "constrain" in low or "shortage" in low or "utili" in low:
        matched_spans: List[Tuple[int, int]] = []
        for pattern in _CAP_OWNER:
            for match in pattern.finditer(paragraph):
                sentence = sentence_around(paragraph, match.start(), match.end())
                utilization = None
                if "p" in pattern.groupindex and match.group("p"):
                    utilization = float(match.group("p"))
                    if utilization > 100:
                        continue
                if not re.search(r"manufactur|production|plants?\b|factor(?:y|ies)|\bfabs?\b|foundr|mills?\b|refiner|smelter|throughput|units|"
                                 r"backlog|orders|customer\s+demand|capacity\s+to\s+(?:produce|manufacture|build|ship)", sentence, re.I):
                    continue        # 「100% utilization rate」（保险）、「same-store 满负荷」（景区）、「循环授信利用率」都不是产能
                # 「our suppliers are operating at full capacity」：主语是供应商，不是公司
                direction = UPSTREAM if _CAP_UPSTREAM.search(sentence) else OWNER
                matched_spans.append((match.start(), match.end()))
                _add(out, seen, Extraction("capacity_constraint", direction, sentence, para(match.start()), section,
                                           value=utilization, unit="percent" if utilization is not None else None,
                                           detail={"expression": match.group(0)[:200]}))
        for match in _CAP_GENERIC.finditer(paragraph):
            if any(s <= match.start() < e for s, e in matched_spans):
                continue
            sentence = sentence_around(paragraph, match.start(), match.end())
            upstream = bool(re.search(r"\b(?:our\s+)?(?:suppliers?|vendors?|foundr\w+|contract\s+manufacturers?|manufacturers?|supply\s+chain)\b", sentence, re.I)) \
                or bool(re.search(r"\bcomponent\s+shortages?\b|\bshortages?\s+of\s+(?:components?|materials?|parts)\b", sentence, re.I))
            if upstream:
                direction = UPSTREAM
            elif re.search(r"\bwe\s+(?:are|were|have\s+been|remain)\b[^.]{0,40}\bconstrain", sentence, re.I):
                direction = OWNER
            else:
                direction = AMBIGUOUS
            _add(out, seen, Extraction("capacity_constraint", direction, sentence, para(match.start()), section,
                                       detail={"expression": match.group(0)[:200], "generic": True}))
    if "backlog" in low:
        for match in _BACKLOG.finditer(paragraph):
            if match.group("n"):
                value = _money(match.group("n"), match.group("u"))
            elif match.group("n2"):
                value = _money(match.group("n2"), match.group("u2"))
            else:
                continue
            unit_word = (match.group("u") or match.group("u2") or "") if match.groupdict().get("u2") is not None or match.groupdict().get("u") is not None else ""
            if not unit_word and value < 1_000_000:     # 「$61,199」没写 thousand/million：表格单位不明，宁可不采
                continue
            between = paragraph[match.start(): match.start("n") if match.group("n") else match.start("n2")]
            if re.search(r"(?:increas|decreas|declin|grew|grow|rose|fell|reduc|dropp|up|down)\w*\s+(?:by\s+|of\s+)?(?:approximately\s+|about\s+)?\$?\s*$", between, re.I):
                continue                                # 「积压增加了 $1.4 百万」是变化量不是余额
            if re.search(r"beginning\s+balance|ending\s+balance|acquired|adjust|potential|expected|includ", between, re.I) \
                    or re.search(r"(?:potential|expected|estimated|projected)\s+(?:\d+[- ]years?\s+)?(?:revenue\s+)?$", paragraph[max(0, match.start() - 40):match.start()], re.I):
                continue
            sentence = sentence_around(paragraph, match.start(), match.end())
            prior = None
            pm = _BACKLOG_PRIOR.search(paragraph[match.end():match.end() + 220])
            if pm:
                prior = _money(pm.group("n"), pm.group("u"))
            _add(out, seen, Extraction("backlog", OWNER, sentence, para(match.start()), section,
                                       value=value, value_low=prior, unit="usd", detail={"expression": match.group(0)[:200]}))


def extract_structure(text: str) -> List[Extraction]:
    """text 是 html_to_text 的输出（一段一行）。返回按信息量截断后的抽取列表。"""
    items: List[Extraction] = []
    seen: set = set()
    section: Optional[str] = None
    for line in text.split("\n"):
        head = _SECTION_HEAD.match(line)
        if head and len(line) < 140:
            section = ("Item %s %s" % (head.group(1).upper(), head.group(2).strip()))[:80]
            continue
        if len(line) < 40:
            continue
        _scan_paragraph(line, section, items, seen)
    return _truncate(items)


def _strength(item: Extraction) -> Tuple:
    """同类里保留哪几条：有数字的优先，方向明确的优先，数值大的优先。"""
    return (item.value is not None, item.direction in (OWNER, UPSTREAM, RISK), item.value or 0.0)


def _truncate(items: Sequence[Extraction]) -> List[Extraction]:
    kept: List[Extraction] = []
    for kind in KINDS:
        by_direction: Dict[str, List[Extraction]] = {}
        for item in items:
            if item.kind == kind:
                by_direction.setdefault(item.direction, []).append(item)
        for members in by_direction.values():
            kept += sorted(members, key=_strength, reverse=True)[:MAX_ITEMS_PER_KIND]
    return kept


def build_filing_extraction(text: str, *, cik: int, accession: str, form: str, filed: str,
                            period_end: Optional[str], url: str) -> FilingExtraction:
    return FilingExtraction(int(cik), accession, form, filed, period_end, url, len(text), EXTRACTOR_VERSION,
                            tuple(extract_structure(text)))


# ---- 缓存（每份申报一个小 JSON，不存原文）-------------------------------------------------
class ExtractionCache:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, accession: str) -> Path:
        return self.directory / (accession + ".json.gz")

    def get(self, accession: str) -> Optional[FilingExtraction]:
        try:
            payload = json.loads(gzip.decompress(self.path(accession).read_bytes()).decode("utf-8"))
        except (OSError, EOFError, ValueError):
            return None
        if payload.get("version") != EXTRACTOR_VERSION:
            return None          # 抽取器升级后旧缓存自动作废
        try:
            return FilingExtraction.from_dict(payload)
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, extraction: FilingExtraction) -> None:
        target = self.path(extraction.accession)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(json.dumps(extraction.to_dict(), ensure_ascii=False).encode("utf-8"), 6))
        temporary.replace(target)
