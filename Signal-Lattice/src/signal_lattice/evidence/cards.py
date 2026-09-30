"""产业瓶颈证据卡：给瓶颈分支「结构性约束」里申报拿不到的因子提供可审计的一手证据。

一张卡 = 一个产业瓶颈（src/signal_lattice/evidence_cards/<id>.yaml）。开发期由人去查一手来源、逐个打开链接、
抄原文摘录，随代码发布；运行期只读卡片，零联网、零模型。

读卡规则（任何一条不满足，这个因子回到 NO_EVIDENCE，不填中值、不记 0 分）：
- 卡片结构校验不过 → 整张卡作废；
- as_of 早于检索日（时点正确，回测不能用未来才查到的证据）或晚于有效期 → 失效；
- 评分的每一条来源必须是一手来源（政府/监管/SEC 申报/学术/行业协会的官方统计），并带 verification.json 里的
  核验印章（状态码 200、原文摘录在页面里找得到、印章与当前的链接+摘录一一对应——改了摘录就要重新核验）；
- 一手来源数量不足（评分 ≥1 要 1 条；≥4 要带数字的摘录；5 要两家不同发布方）→ 该因子不成立。

这里的数字（有效期上限、评分与来源数量的对应）是「怎样才算有证据」的校验口径，不是瓶颈分支的门槛；门槛在 bottleneck.py 的
DEFAULT_PARAMS，本模块不碰。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

CARD_SCHEMA = "signal-lattice-evidence-card/1"
VERIFICATION_SCHEMA = "signal-lattice-card-verification/1"
CARDS_DIR = Path(__file__).resolve().parents[1] / "evidence_cards"
VERIFICATION_FILE = "verification.json"

# 证据卡只负责这八个「结构性约束」因子
CARD_FACTORS: Tuple[str, ...] = (
    "funded_demand", "current_tightness", "supplier_concentration", "qualification_barrier",
    "substitution_difficulty", "expansion_lead_time", "policy_resilience", "architectural_necessity",
)
SOURCE_KINDS = ("regulator", "government_statistics", "company_filing", "industry_association", "academic_paper")
# 一手来源的域名：政府/监管/军方/高校、SEC、学术出版与预印本、国际机构。新闻、博客、券商观点不在其中。
PRIMARY_HOST_SUFFIXES: Tuple[str, ...] = (
    ".gov", ".mil", ".edu", "sec.gov", "arxiv.org", "doi.org", "europa.eu", "iea.org", "oecd-nea.org", "iaea.org",
    "nea.org", "nature.com", "science.org", "ieee.org", "osti.gov", "nrel.gov", "worldbank.org", "imf.org",
    "semi.org", "nema.org", "sia-online.org", "ussc.gov", "gao.gov", "cbo.gov",
)
SEC_FILING_PREFIX = "https://www.sec.gov/Archives/edgar/data/"
MAX_CARD_DAYS = 366                              # 卡片整体有效期上限（检索日起算）
MAX_FAST_FACTOR_DAYS = 190                       # 随时间变化快的因子（紧张度、在手需求）有效期更短
FAST_FACTORS = ("current_tightness", "funded_demand")
POOL_MIN_CAP_USD = 300_000_000                   # 候选池市值区间（universe.py 的 MIN/MAX_MARKET_CAP_USD）：卡片登记的公司必须落在其中
POOL_MAX_CAP_USD = 5_000_000_000
MAX_EXCERPT_SENTENCES = 2
MAX_EXCERPT_CHARS = 600

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SENTENCE_END = re.compile(r"[.!?。！？](?:\s|$)")


class CardParseError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# 极小 YAML 子集解析器（运行期零依赖：安装包是离线构建的，不带 PyYAML）。
# 支持：块映射、块列表（"- 标量" 或 "- key: value" 起头的映射）、双引号字符串（JSON 转义）、整数/小数/true/false/null、
# 不含 ": " 与 " #" 的裸字符串、[] 与 {}、整行与行尾（引号外）注释。其它写法一律报错，不猜。
# ---------------------------------------------------------------------------------------------
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?: +(.*))?$")


def _strip_comment(line: str) -> str:
    in_quote, escaped = False, False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
        elif ch == "\\" and in_quote:
            escaped = True
        elif ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(text: str, lineno: int) -> Any:
    text = text.strip()
    if text == "":
        return None
    if text[0] == '"':
        try:
            value = json.loads(text)
        except ValueError as exc:
            raise CardParseError("第 %d 行：双引号字符串不合法（%s）" % (lineno, exc)) from None
        if not isinstance(value, str):
            raise CardParseError("第 %d 行：引号内容必须是字符串" % lineno)
        return value
    if text[0] in "'[{&*!|>%@`" and text not in ("[]", "{}"):
        raise CardParseError("第 %d 行：不支持的写法 %r（字符串请用双引号）" % (lineno, text[:20]))
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    if ": " in text or text.endswith(":"):
        raise CardParseError("第 %d 行：裸字符串里不能含冒号（请加双引号）：%r" % (lineno, text[:30]))
    return text


def parse_simple_yaml(text: str) -> Any:
    rows: List[Tuple[int, str, int]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if raw.startswith("\t") or re.match(r" *\t", raw):
            raise CardParseError("第 %d 行：不允许制表符缩进" % lineno)
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        rows.append((len(body) - len(body.lstrip(" ")), body.strip(), lineno))
    if not rows:
        raise CardParseError("空文件")
    value, pos = _parse_block(rows, 0, rows[0][0])
    if pos != len(rows):
        raise CardParseError("第 %d 行：缩进不对，无法归入上文" % rows[pos][2])
    return value


def _is_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _parse_block(rows: List[Tuple[int, str, int]], pos: int, indent: int) -> Tuple[Any, int]:
    return _parse_list(rows, pos, indent) if _is_item(rows[pos][1]) else _parse_map(rows, pos, indent)


def _parse_map(rows: List[Tuple[int, str, int]], pos: int, indent: int) -> Tuple[dict, int]:
    out: dict = {}
    i = pos
    while i < len(rows):
        ind, content, lineno = rows[i]
        if ind < indent or _is_item(content) and ind == indent:
            break
        if ind > indent:
            raise CardParseError("第 %d 行：缩进多了" % lineno)
        match = _KEY.match(content)
        if not match:
            raise CardParseError("第 %d 行：不是「键: 值」：%r" % (lineno, content[:40]))
        key, rest = match.group(1), match.group(2)
        if key in out:
            raise CardParseError("第 %d 行：键重复 %s" % (lineno, key))
        i += 1
        if rest is not None and rest.strip() != "":
            out[key] = _scalar(rest, lineno)
        elif i < len(rows) and (rows[i][0] > indent or (rows[i][0] == indent and _is_item(rows[i][1]))):
            out[key], i = _parse_block(rows, i, rows[i][0])
        else:
            out[key] = None
    return out, i


def _parse_list(rows: List[Tuple[int, str, int]], pos: int, indent: int) -> Tuple[list, int]:
    out: list = []
    i = pos
    while i < len(rows):
        ind, content, lineno = rows[i]
        if ind < indent or not _is_item(content) and ind == indent:
            break
        if ind > indent:
            raise CardParseError("第 %d 行：缩进多了" % lineno)
        rest = "" if content == "-" else content[2:].strip()
        if rest == "":
            i += 1
            if i < len(rows) and rows[i][0] > indent:
                item, i = _parse_block(rows, i, rows[i][0])
                out.append(item)
            else:
                out.append(None)
        elif rest[0] != '"' and _KEY.match(rest):
            # 「- 键: 值」：把这一行改写成缩进 +2 的普通键行，其余键同缩进，按映射解析
            rows[i] = (indent + 2, rest, lineno)
            item, i = _parse_map(rows, i, indent + 2)
            out.append(item)
        else:
            out.append(_scalar(rest, lineno))
            i += 1
    return out, i


# ---------------------------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------------------------
def normalize_excerpt(text: str) -> str:
    """核验与印章共用的摘录规范化：NFKC、统一引号/连字符、连字符断行接回、空白折叠、小写。"""
    text = unicodedata.normalize("NFKC", text)
    text = (text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
            .replace("–", "-").replace("—", "-").replace("­", ""))
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def stamp_key(url: str, excerpt: str) -> str:
    return hashlib.sha256((url.strip() + "\n" + normalize_excerpt(excerpt)).encode("utf-8")).hexdigest()[:32]


def primary_host(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return any(host == s.lstrip(".") or host.endswith("." + s.lstrip(".")) for s in PRIMARY_HOST_SUFFIXES)


@dataclass(frozen=True)
class CardSource:
    url: str
    kind: str
    publisher: str
    title: str
    excerpt: str

    @property
    def key(self) -> str:
        return stamp_key(self.url, self.excerpt)

    def to_dict(self) -> dict:
        return {"url": self.url, "kind": self.kind, "publisher": self.publisher, "title": self.title, "excerpt": self.excerpt}


@dataclass(frozen=True)
class CardFactor:
    name: str
    rating: int
    basis: str
    valid_until: str
    sources: Tuple[CardSource, ...]


@dataclass(frozen=True)
class CardCompany:
    cik: int
    symbol: str
    name: str
    exposure: str
    source: CardSource
    market_cap_usd: float
    market_cap_as_of: str


@dataclass(frozen=True)
class EvidenceCard:
    id: str
    bottleneck: str
    retrieved: str
    valid_until: str
    factors: Mapping[str, CardFactor]
    companies: Tuple[CardCompany, ...]
    contradictions: Tuple[Mapping[str, str], ...]
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False)


def _is_date(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def excerpt_problems(excerpt: Any) -> List[str]:
    if not isinstance(excerpt, str) or not excerpt.strip():
        return ["摘录为空"]
    problems = []
    if len(excerpt) > MAX_EXCERPT_CHARS:
        problems.append("摘录超过 %d 字" % MAX_EXCERPT_CHARS)
    sentences = len([s for s in _SENTENCE_END.split(excerpt.strip()) if s.strip()])
    if sentences > MAX_EXCERPT_SENTENCES:
        problems.append("摘录超过 %d 句" % MAX_EXCERPT_SENTENCES)
    return problems


def _source_from(raw: Any, where: str, problems: List[str], sec_only: bool = False) -> Optional[CardSource]:
    if not isinstance(raw, dict):
        problems.append("%s：来源必须是对象" % where)
        return None
    extra = set(raw) - {"url", "kind", "publisher", "title", "excerpt"}
    missing = {"url", "kind", "publisher", "title", "excerpt"} - set(raw)
    if extra or missing:
        problems.append("%s：来源键不齐（缺 %s，多 %s）" % (where, sorted(missing), sorted(extra)))
        return None
    before = len(problems)
    url, kind = raw["url"], raw["kind"]
    if not isinstance(url, str) or not primary_host(url):
        problems.append("%s：链接不是一手来源域名（只认政府/监管/SEC/学术/国际机构/行业协会官方）：%r" % (where, url))
    if kind not in SOURCE_KINDS:
        problems.append("%s：来源类别 %r 不在 %s" % (where, kind, list(SOURCE_KINDS)))
    if kind == "company_filing" and not (isinstance(url, str) and url.startswith(SEC_FILING_PREFIX)):
        problems.append("%s：公司申报必须是 SEC Archives 原文链接" % where)
    if sec_only and not (isinstance(url, str) and url.startswith(SEC_FILING_PREFIX)):
        problems.append("%s：公司与瓶颈的关系必须由公司自己的 SEC 申报原文支撑" % where)
    for key in ("publisher", "title"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            problems.append("%s：%s 不能为空" % (where, key))
    problems.extend("%s：%s" % (where, p) for p in excerpt_problems(raw["excerpt"]))
    if len(problems) > before:
        return None
    return CardSource(url.strip(), kind, raw["publisher"].strip(), raw["title"].strip(), raw["excerpt"].strip())


def parse_card(raw: Any, expected_id: Optional[str] = None) -> Tuple[Optional[EvidenceCard], List[str]]:
    """结构校验：返回 (卡片或 None, 问题清单)。有任何问题卡片整张作废。"""
    problems: List[str] = []
    if not isinstance(raw, dict):
        return None, ["顶层必须是对象"]
    need = {"schema", "id", "bottleneck", "retrieved", "valid_until", "factors", "companies", "contradictions"}
    if need - set(raw) or set(raw) - need:
        return None, ["顶层键不齐（缺 %s，多 %s）" % (sorted(need - set(raw)), sorted(set(raw) - need))]
    if raw["schema"] != CARD_SCHEMA:
        problems.append("schema 必须是 %s" % CARD_SCHEMA)
    if not isinstance(raw["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", raw["id"]):
        problems.append("id 必须是小写英文/数字/连字符")
    elif expected_id is not None and raw["id"] != expected_id:
        problems.append("id %r 与文件名 %r 不一致" % (raw["id"], expected_id))
    if not isinstance(raw["bottleneck"], str) or len(raw["bottleneck"].strip()) < 10:
        problems.append("bottleneck（瓶颈描述）不能为空或过短")
    for key in ("retrieved", "valid_until"):
        if not _is_date(raw[key]):
            problems.append("%s 必须是 YYYY-MM-DD" % key)
    if problems:
        return None, problems
    if raw["valid_until"] <= raw["retrieved"]:
        problems.append("valid_until 必须晚于 retrieved")
    elif _days(raw["retrieved"], raw["valid_until"]) > MAX_CARD_DAYS:
        problems.append("有效期超过 %d 天上限" % MAX_CARD_DAYS)

    factors: Dict[str, CardFactor] = {}
    if not isinstance(raw["factors"], dict) or not raw["factors"]:
        problems.append("factors 必须是非空对象")
    else:
        for name, body in raw["factors"].items():
            where = "factors.%s" % name
            if name not in CARD_FACTORS:
                problems.append("%s：不是证据卡负责的因子（%s）" % (where, ", ".join(CARD_FACTORS)))
                continue
            if not isinstance(body, dict) or set(body) - {"rating", "basis", "valid_until", "sources"} or \
                    {"rating", "basis", "sources"} - set(body):
                problems.append("%s：键必须是 rating、basis、sources（可选 valid_until）" % where)
                continue
            rating = body["rating"]
            if isinstance(rating, bool) or not isinstance(rating, int) or not 0 <= rating <= 5:
                problems.append("%s：rating 必须是 0-5 的整数" % where)
                continue
            if not isinstance(body["basis"], str) or len(body["basis"].strip()) < 10:
                problems.append("%s：basis（为什么是这个分）不能为空" % where)
                continue
            until = body.get("valid_until", raw["valid_until"])
            if not _is_date(until) or until > raw["valid_until"] or until <= raw["retrieved"]:
                problems.append("%s：valid_until 必须是晚于检索日、不晚于卡片有效期的日期" % where)
                continue
            if name in FAST_FACTORS and _days(raw["retrieved"], until) > MAX_FAST_FACTOR_DAYS:
                problems.append("%s：随时间变化快的因子有效期不得超过 %d 天" % (where, MAX_FAST_FACTOR_DAYS))
                continue
            if not isinstance(body["sources"], list) or not body["sources"]:
                problems.append("%s：至少一条一手来源" % where)
                continue
            sources = []
            for idx, item in enumerate(body["sources"]):
                src = _source_from(item, "%s.sources[%d]" % (where, idx), problems)
                if src is not None:
                    sources.append(src)
            if len(sources) != len(body["sources"]):
                continue
            if len({s.key for s in sources}) != len(sources):
                problems.append("%s：来源重复" % where)
                continue
            if rating >= 4 and not any(re.search(r"\d", s.excerpt) for s in sources):
                problems.append("%s：评分 ≥4 必须有带数字的原文摘录" % where)
                continue
            if rating == 5 and len({s.publisher.lower() for s in sources}) < 2:
                problems.append("%s：评分 5 需要两家不同发布方各自的一手来源" % where)
                continue
            factors[name] = CardFactor(name, rating, body["basis"].strip(), until, tuple(sources))

    companies: List[CardCompany] = []
    if not isinstance(raw["companies"], list) or not raw["companies"]:
        problems.append("companies 必须是非空列表")
    else:
        seen = set()
        for idx, item in enumerate(raw["companies"]):
            where = "companies[%d]" % idx
            keys = {"cik", "symbol", "name", "exposure", "source", "market_cap_usd", "market_cap_as_of"}
            if not isinstance(item, dict) or set(item) != keys:
                problems.append("%s：键必须是 %s" % (where, sorted(keys)))
                continue
            if isinstance(item["cik"], bool) or not isinstance(item["cik"], int) or item["cik"] <= 0:
                problems.append("%s：cik 必须是正整数（SEC CIK）" % where)
                continue
            if item["cik"] in seen:
                problems.append("%s：cik %d 重复" % (where, item["cik"]))
                continue
            seen.add(item["cik"])
            if not all(isinstance(item[k], str) and item[k].strip() for k in ("symbol", "name", "exposure")):
                problems.append("%s：symbol、name、exposure 不能为空" % where)
                continue
            cap, cap_day = item["market_cap_usd"], item["market_cap_as_of"]
            if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not POOL_MIN_CAP_USD <= cap <= POOL_MAX_CAP_USD:
                problems.append("%s：market_cap_usd 必须落在候选池区间 %d–%d 美元（取自候选池快照）" % (where, POOL_MIN_CAP_USD, POOL_MAX_CAP_USD))
                continue
            if not _is_date(cap_day) or cap_day > raw["retrieved"]:
                problems.append("%s：market_cap_as_of 必须是不晚于检索日的 YYYY-MM-DD" % where)
                continue
            src = _source_from(item["source"], where + ".source", problems, sec_only=True)
            if src is not None:
                companies.append(CardCompany(item["cik"], item["symbol"].strip(), item["name"].strip(),
                                             item["exposure"].strip(), src, float(cap), cap_day))

    contradictions: List[Mapping[str, str]] = []
    if not isinstance(raw["contradictions"], list) or not raw["contradictions"]:
        problems.append("contradictions（反证记录）必须是非空列表：写清查过什么、结果如何")
    else:
        for idx, item in enumerate(raw["contradictions"]):
            where = "contradictions[%d]" % idx
            if not isinstance(item, dict) or set(item) - {"searched", "found", "effect", "url"} or \
                    {"searched", "found", "effect"} - set(item):
                problems.append("%s：键必须是 searched、found、effect（可选 url）" % where)
                continue
            if not all(isinstance(item[k], str) and item[k].strip() for k in ("searched", "found", "effect")):
                problems.append("%s：searched、found、effect 不能为空" % where)
                continue
            if "url" in item and not (isinstance(item["url"], str) and primary_host(item["url"])):
                problems.append("%s：url 必须是一手来源域名" % where)
                continue
            contradictions.append({k: str(v).strip() for k, v in item.items()})

    if problems:
        return None, problems
    card = EvidenceCard(raw["id"], raw["bottleneck"].strip(), raw["retrieved"], raw["valid_until"], factors,
                        tuple(companies), tuple(contradictions), raw)
    return card, []


# ---------------------------------------------------------------------------------------------
# 核验印章：verification.json 由 scripts/verify_evidence_cards.py 逐个打开链接后写入
# ---------------------------------------------------------------------------------------------
def source_verified(source: CardSource, stamps: Mapping[str, Any], retrieved: str, as_of: str) -> Tuple[bool, str]:
    stamp = stamps.get(source.key)
    if not isinstance(stamp, dict):
        return False, "无核验印章（链接或摘录改过，或从没核验过）"
    if stamp.get("url") != source.url:
        return False, "印章的链接与卡片不一致"
    if stamp.get("status") != 200:
        return False, "链接核验状态码 %s，不是 200" % stamp.get("status")
    if stamp.get("excerpt_found") is not True:
        return False, "原文摘录没有在页面里找到"
    checked = stamp.get("checked")
    if not _is_date(checked):
        return False, "印章缺核验日期"
    if checked > as_of:
        return False, "核验日 %s 晚于 as_of %s" % (checked, as_of)
    return True, ""


@dataclass(frozen=True)
class ActiveFactor:
    """某只股票在 as_of 这天、从证据卡得到的一个因子。"""
    name: str
    rating: int
    basis: str
    card_ids: Tuple[str, ...]
    sources: Tuple[CardSource, ...]
    valid_until: str


class CardBook:
    """随快照一起钉住的全部证据卡 + 核验印章。"""

    def __init__(self, cards: Sequence[EvidenceCard], stamps: Mapping[str, Any], invalid: Mapping[str, Sequence[str]]) -> None:
        self.cards: Tuple[EvidenceCard, ...] = tuple(cards)
        self.stamps: Mapping[str, Any] = dict(stamps)
        self.invalid: Dict[str, List[str]] = {k: list(v) for k, v in invalid.items()}

    # ---- 从磁盘 / 从快照 ---------------------------------------------------------------
    @classmethod
    def from_payload(cls, payload: Optional[Mapping[str, Any]]) -> "CardBook":
        payload = payload or {}
        cards, invalid = [], {}
        for card_id, raw in sorted((payload.get("cards") or {}).items()):
            card, problems = parse_card(raw, expected_id=card_id)
            if card is None:
                invalid[card_id] = problems
            else:
                cards.append(card)
        for card_id, problems in (payload.get("unreadable") or {}).items():
            invalid[card_id] = list(problems)
        return cls(cards, payload.get("stamps") or {}, invalid)

    @classmethod
    def load_dir(cls, directory: Path = CARDS_DIR) -> "CardBook":
        return cls.from_payload(load_payload(directory))

    # ---- 查询 -------------------------------------------------------------------------
    def for_company(self, cik: int, as_of: str) -> Tuple[Dict[str, ActiveFactor], List[dict]]:
        """返回 (因子名 → 生效的证据, 被拒绝的原因清单)。多张卡给同一个因子时取最低分（保守），来源合并。"""
        per_factor: Dict[str, List[Tuple[EvidenceCard, CardFactor, Tuple[CardSource, ...]]]] = {}
        rejected: List[dict] = []
        for card_id, problems in self.invalid.items():
            rejected.append({"card": card_id, "factor": None, "reason": "CARD_INVALID", "detail": "; ".join(problems)[:300]})
        for card in self.cards:
            member = next((c for c in card.companies if c.cik == cik), None)
            if member is None:
                continue
            if as_of < card.retrieved:
                rejected.append({"card": card.id, "factor": None, "reason": "CARD_NOT_YET_RETRIEVED",
                                 "detail": "检索日 %s 晚于 as_of %s" % (card.retrieved, as_of)})
                continue
            ok, why = source_verified(member.source, self.stamps, card.retrieved, as_of)
            if not ok:
                rejected.append({"card": card.id, "factor": None, "reason": "COMPANY_EXPOSURE_UNVERIFIED", "detail": why})
                continue
            for name, factor in card.factors.items():
                if as_of > factor.valid_until:
                    rejected.append({"card": card.id, "factor": name, "reason": "CARD_EXPIRED",
                                     "detail": "有效期到 %s，as_of %s" % (factor.valid_until, as_of)})
                    continue
                good = []
                for src in factor.sources:
                    verified, why = source_verified(src, self.stamps, card.retrieved, as_of)
                    if verified:
                        good.append(src)
                    else:
                        rejected.append({"card": card.id, "factor": name, "reason": "SOURCE_UNVERIFIED",
                                         "detail": "%s：%s" % (src.url, why)})
                if not good or not _support_ok(factor.rating, good):
                    if good:
                        rejected.append({"card": card.id, "factor": name, "reason": "SUPPORT_TOO_THIN",
                                         "detail": "通过核验的来源不足以支撑评分 %d" % factor.rating})
                    continue
                per_factor.setdefault(name, []).append((card, factor, tuple(good)))
        active: Dict[str, ActiveFactor] = {}
        for name, items in per_factor.items():
            low = min(items, key=lambda it: (it[1].rating, it[0].id))
            sources: List[CardSource] = []
            for _, _, srcs in items:
                for s in srcs:
                    if s.url not in {x.url for x in sources}:
                        sources.append(s)
            basis = "证据卡 %s（行业层面，非该公司自述）：%s" % (",".join(sorted(it[0].id for it in items)), low[1].basis)
            active[name] = ActiveFactor(name, low[1].rating, basis, tuple(sorted(it[0].id for it in items)), tuple(sources),
                                        min(it[1].valid_until for it in items))
        return active, rejected

    def summary(self) -> dict:
        return {"cards": [{"id": c.id, "retrieved": c.retrieved, "valid_until": c.valid_until,
                           "factors": sorted(c.factors), "companies": len(c.companies)} for c in self.cards],
                "invalid": self.invalid}


def _support_ok(rating: int, good_sources: Sequence[CardSource]) -> bool:
    """通过核验的来源是否仍满足评分对来源的要求（结构校验时是按全部来源判的，核验后要再判一次）。"""
    if rating == 0:
        return len(good_sources) >= 1
    if rating >= 4 and not any(re.search(r"\d", s.excerpt) for s in good_sources):
        return False
    if rating == 5 and len({s.publisher.lower() for s in good_sources}) < 2:
        return False
    return len(good_sources) >= 1


def load_payload(directory: Path = CARDS_DIR) -> dict:
    """读目录里全部卡片与印章，得到可直接 json 化、钉进快照的载荷。读不了的卡记进 unreadable，不抛错。"""
    directory = Path(directory)
    cards: Dict[str, Any] = {}
    unreadable: Dict[str, List[str]] = {}
    stamps: Dict[str, Any] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.yaml")):
            try:
                cards[path.stem] = parse_simple_yaml(path.read_text("utf-8"))
            except (CardParseError, OSError, UnicodeDecodeError) as exc:
                unreadable[path.stem] = ["读不了：%s" % exc]
        stamp_path = directory / VERIFICATION_FILE
        if stamp_path.is_file():
            try:
                doc = json.loads(stamp_path.read_text("utf-8"))
                if doc.get("schema") == VERIFICATION_SCHEMA and isinstance(doc.get("entries"), dict):
                    stamps = doc["entries"]
            except (OSError, ValueError):
                stamps = {}
    payload = {"schema": "signal-lattice-card-payload/1", "cards": cards, "unreadable": unreadable, "stamps": stamps}
    payload["content_sha256"] = hashlib.sha256(
        json.dumps({k: payload[k] for k in ("cards", "unreadable", "stamps")}, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    return payload
