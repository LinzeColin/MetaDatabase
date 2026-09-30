"""公司名显示：SEC 登记名常是全大写（「KENNAMETAL INC」），页面上读起来像在喊。
规则取自 EEI 的 prettyName（EEI/apps/universe/app.js）：只改「字母全是大写、且至少 3 个字母」的名字，
已经是正常大小写的名字（「Evolv Technologies Holdings, Inc.」）原样保留；转换时首字母大写，
介词/连词（of、and、de……）保持小写，LLC / NV / LP / PLC 等公司类型缩写和常见首字母缩写保持全大写。
"""

from __future__ import annotations

import re
from typing import Any, Optional

KEEP_UPPER = frozenset({"LLC", "LP", "LLP", "PLC", "AG", "SA", "NV", "BV", "AB", "AS", "SE", "KK", "USA", "US", "UK", "EU", "II", "III", "IV",
                        "AI", "TSMC", "ASML", "IBM", "HK", "SAS", "SRL", "SPA", "GK", "PTE", "LTDA", "CV", "SARL", "OY", "ULC", "SLU",
                        "ETF", "REIT", "CEO", "CFO", "ADR", "SPAC", "IT", "TV", "PC", "HQ", "NA", "FSB"})
SMALL_WORDS = frozenset({"of", "and", "de", "du", "la", "le", "the", "für", "und", "for", "in", "on", "at", "to", "by"})
_TOKEN = re.compile(r"[a-z][a-z'.&]*")
_INITIALS_WITH_AMPERSAND = re.compile(r"^[a-z]{1,2}&[a-z]{1,2}$")         # AT&T、S&P、H&R


def pretty_name(raw: Any) -> Any:
    """全大写的公司名转成正常大小写；其它输入原样返回（None、空串、已经是正常大小写的名字）。"""
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    letters = re.sub(r"[^A-Za-z]", "", text)
    if not letters or letters != letters.upper() or len(letters) < 3:
        return text if text else raw

    def fix(match: "re.Match[str]") -> str:
        word = match.group(0)
        bare = re.sub(r"[.']", "", word).upper()
        if bare in KEEP_UPPER or _INITIALS_WITH_AMPERSAND.match(word):
            return word.upper()
        if word in SMALL_WORDS:
            return word
        return word[0].upper() + word[1:]

    converted = _TOKEN.sub(fix, text.lower())
    return converted[0].upper() + converted[1:]


def pretty_optional(value: Optional[str]) -> Optional[str]:
    return pretty_name(value) if isinstance(value, str) else value
