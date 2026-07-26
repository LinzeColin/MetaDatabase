#!/usr/bin/env python3
"""Shared fail-closed checks for the roles-before-securities presentation gate."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


ENTITY_KEYS = frozenset(
    {
        "benchmark",
        "benchmark_name",
        "branded_operator",
        "company",
        "company_name",
        "exchange",
        "index",
        "issuer",
        "legal_entity",
        "listed_entity",
        "publisher",
        "security",
        "ticker",
    }
)
GENERIC_UPPERCASE = frozenset(
    {
        "AI",
        "CAGR",
        "EBITDA",
        "EHV",
        "E2E",
        "FCF",
        "GPU",
        "HVDC",
        "OEM",
        "P10",
        "P50",
        "P90",
        "RPO",
        "SEC",
        "TBA",
        "TBD",
        "URL",
        "U.S.",
        "USD",
    }
)
GENERIC_UPPERCASE_CANONICAL = frozenset(
    token.rstrip(".") for token in GENERIC_UPPERCASE
)
UPPERCASE_ENTITY = re.compile(
    r"(?<![A-Za-z0-9_])\$?[A-Z][A-Z0-9.:-]{1,11}(?![A-Za-z0-9_])"
)
EXCHANGE_TICKER = re.compile(
    r"(?<![A-Za-z0-9_])[A-Z]{2,12}:[A-Z0-9][A-Z0-9.-]{0,11}"
    r"(?![A-Za-z0-9_])"
)
NUMERIC_TICKER = re.compile(
    r"(?<![A-Za-z0-9_])(?:[0-9]{3,6}|[A-Z]{1,6})"
    r"\.(?:HK|L|T|TO|AX|SI|KS|KQ|TW)(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)
CORPORATE_NAME = re.compile(
    r"\b[A-Z][A-Za-z0-9&'’-]*(?:\s+[A-Z][A-Za-z0-9&'’-]*){0,4}\s+"
    r"(?i:Co(?:mpany)?|Corp(?:oration)?|Energy|Exchange|Group|Holdings?|"
    r"Inc(?:orporated)?|Ltd|Limited|PLC|S\.?A\.?|SE|Securities)\b"
)
LOWERCASE_CORPORATE_NAME = re.compile(
    r"\b[a-z][a-z0-9&'’-]{1,63}\s+"
    r"(?i:Co(?:mpany)?|Corp(?:oration)?|Energy|Exchange|Group|Holdings?|"
    r"Inc(?:orporated)?|Ltd|Limited|PLC|S\.?A\.?|SE|Securities)\b"
)
CAMELCASE_BRAND = re.compile(r"(?<![A-Za-z0-9_])[A-Z][a-z]+[A-Z][A-Za-z0-9]*")
CJK_CORPORATE = re.compile(
    r"[\u3400-\u9fff]{2,24}(?:公司|集团|控股|股份|证券|银行|能源)"
)
URI = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z][A-Za-z0-9+.-]{1,31}://|"
    r"(?:data|file|mailto|sftp|ssh|tel|urn):)",
    flags=re.IGNORECASE,
)
EMAIL = re.compile(
    r"(?<![A-Za-z0-9_.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{2,59})(?![A-Za-z0-9_-])",
    flags=re.IGNORECASE,
)
BARE_HOST = re.compile(
    r"(?<![A-Za-z0-9_@-])(?:www[0-9]*\.)?"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{2,59})"
    r"(?::[0-9]{1,5})?(?:/[^\s<>()]*)?",
    flags=re.IGNORECASE,
)
STANDALONE_NAME = re.compile(
    r"(?:\A|[.!?]\s+|\n[ \t]*\n[ \t]*)"
    r"([A-Za-z][A-Za-z0-9&'’.-]{1,63})"
    r"(?:[.!?](?=\s|\Z)|(?=[ \t]*(?:\n|\Z)))"
)
STANDALONE_TITLECASE_NAME = re.compile(
    r"(?:\A|[.!?]\s+|\n[ \t]*\n[ \t]*)"
    r"([A-Z][A-Za-z0-9&'’.-]{1,63}"
    r"(?:[ \t]+[A-Z][A-Za-z0-9&'’.-]{1,63}){1,4})"
    r"(?:[.!?](?=\s|\Z)|(?=[ \t]*(?:\n|\Z)))"
)
ENTITY_NAME_TOKEN = (
    r"[^\W\d_](?:(?:[^\W_]|[&'’.-]){0,62}[^\W_])?"
)
ENTITY_NAME_COMPONENT = rf"(?:{ENTITY_NAME_TOKEN}|[0-9]{{1,6}})"
ENTITY_NAME_PHRASE = (
    rf"{ENTITY_NAME_TOKEN}(?:[ \t]+{ENTITY_NAME_COMPONENT}){{0,3}}"
)
ENTITY_SUBJECT_NAME = (
    rf"{ENTITY_NAME_TOKEN}(?:[ \t]+{ENTITY_NAME_COMPONENT}){{0,3}}?"
)
ENTITY_FLEX_TOKEN = r"[^\W_](?:[^\W_]|[&'’.-]){0,63}"
ENTITY_FLEX_PHRASE = (
    rf"{ENTITY_FLEX_TOKEN}(?:[ \t]+{ENTITY_FLEX_TOKEN}){{0,5}}"
)
ENTITY_CLAUSE_START = (
    r"(?:\A|[.!?][\"')\]]*\s+|\n[ \t]*|"
    r"(?:[,;]|—|–)[ \t]*(?:(?:(?:although|because|but|though|whereas|while|yet)"
    r"|except[ \t]+that)[ \t]+)?)"
)
ENTITY_ROLE = (
    r"(?:absorber|benchmark|beneficiary|bottleneck[ \t]+owner|"
    r"benchmark[ \t]+brand|benchmark[ \t]+provider|"
    r"branded[ \t]+operator|company|exposure|fabricator|firm|issuer|index|"
    r"index[ \t]+brand|index[ \t]+provider|investment[ \t]+vehicle|"
    r"listed[ \t]+beneficiary|listed[ \t]+issuer|manufacturer|operator|"
    r"owner|pick|producer|provider|public[ \t]+beneficiary|"
    r"conduit|public[ \t]+proxy|publisher|recipient|security|"
    r"listed[ \t]+exposure|"
    r"security[ \t]+vehicle|substitute|supplier|source|tollbooth|"
    r"unlocker|vehicle|vendor|winner)"
)
ENTITY_ASSIGNMENT = re.compile(
    rf"\b(?:the|a|an|one|our|this|that)?[ \t]*"
    rf"(?:(?:candidate|chosen|constrained|critical|investable|key|leading|"
    rf"named|preferred|primary|qualified|selected|single)[ \t]+)*"
    rf"{ENTITY_ROLE}"
    rf"(?:[ \t]+(?:is|are|was|were|remains?|became|becomes)|"
    rf"[ \t]+(?:called|named)|[ \t]*:)[ \t]+`?"
    rf"(?P<name>{ENTITY_NAME_PHRASE})`?"
    r"(?=[ \t]*(?:[,.;:!?)]|\Z|\n))",
    flags=re.IGNORECASE,
)
ENTITY_APPOSITIVE = re.compile(
    rf"\b(?:a|an|one|the)[ \t]+"
    rf"(?:(?:benchmark|branded|candidate|chosen|comparison|contract|critical|"
    rf"designated|exposure|nominated|payment|preferred|primary|provisional|"
    rf"qualified|selected|single)[ \t]+)*"
    rf"{ENTITY_ROLE}"
    rf"[ \t]*,[ \t]*`?(?P<name>{ENTITY_NAME_PHRASE})`?[ \t]*,"
    r"(?=[ \t]*(?:absorbs?|anchors?|controls?|builds?|defines?|holds?|"
    r"receives?|settles?|supplies|provides|manufactures|has|"
    r"owns|operates|makes|may|might|can|could|will|would)\b)",
    flags=re.IGNORECASE,
)
ENTITY_RELATION = re.compile(
    rf"\b(?:belongs?[ \t]+to|controlled[ \t]+by|depends?[ \t]+on|"
    rf"demand[ \t]+from|relies[ \t]+on|routed[ \t]+through|supplied[ \t]+by)"
    rf"[ \t]+`?(?P<name>{ENTITY_NAME_PHRASE})`?"
    r"(?=[ \t]*(?:[,.;:!?)]|\n|\b(?:under|for|in|with|within|remains?|"
    r"controls?|builds?|supplies|provides|manufactures|owns|operates|"
    r"makes|may|might|can|could|will|would)\b))",
    flags=re.IGNORECASE,
)
ENTITY_SUBJECT = re.compile(
    rf"{ENTITY_CLAUSE_START}"
    rf"(?P<name>{ENTITY_SUBJECT_NAME})"
    r"(?=[ \t]+(?:(?:may|might|can|could|will|would)[ \t]+"
    r"(?:be[ \t]+)?(?:already[ \t]+|currently[ \t]+|nevertheless[ \t]+|"
    r"still[ \t]+)?|(?:already[ \t]+|currently[ \t]+|nevertheless[ \t]+|"
    r"still[ \t]+))?"
    r"(?:awarded|carr(?:y|ies)|collects?|holds?|receives?|makes?|builds?|"
    r"suppl(?:y|ies)|"
    r"provides|manufactures|offers|"
    r"sells|announces?|reports?|reported|disclosed|develops|owns|operates|"
    r"controls?)\b)",
    flags=re.IGNORECASE,
)
ENTITY_POSSESSIVE_SUBJECT = re.compile(
    rf"{ENTITY_CLAUSE_START}"
    rf"(?P<name>{ENTITY_SUBJECT_NAME})['’]s\b"
    r"[^.!?\n]{0,96}\b(?:absorbs?|controls?|builds?|supplies|provides|"
    r"manufactures|defines?|owns|operates|makes|reports?|discloses?|"
    r"cites?|cited)\b",
    flags=re.IGNORECASE,
)
ENTITY_POSSESSIVE_SOURCE = re.compile(
    rf"\b(?P<name>{ENTITY_SUBJECT_NAME})['’]s[ \t]+"
    r"(?:(?:(?:annual|earnings|investor|regulatory)[ \t]+)?"
    r"(?:filing|report|release|statement)|"
    r"(?:benchmark|index)[ \t]+(?:methodology|series))\b",
    flags=re.IGNORECASE,
)
ENTITY_REVERSE_ASSIGNMENT = re.compile(
    rf"{ENTITY_CLAUSE_START}"
    rf"(?P<name>{ENTITY_SUBJECT_NAME})[ \t]+"
    r"(?:(?:may|might|can|could|will|would)[ \t]+)?"
    r"(?:is|are|was|were|be|remain|remains|became|become|becomes)[ \t]+"
    r"(?:(?:appointed|chosen|designated|nominated|selected)[ \t]+as[ \t]+)?"
    r"(?:(?:the|a|an|our|this|that|contract|listed|only|payment|preferred|primary|"
    r"qualified|selected|single)"
    r"[ \t]+)*"
    rf"{ENTITY_ROLE}\b",
    flags=re.IGNORECASE,
)
ENTITY_SELECTION = re.compile(
    rf"\b(?:designated|named|nominated|selected|shortlisted)[ \t]+`?"
    rf"(?P<name>{ENTITY_NAME_PHRASE})`?[ \t]+"
    r"(?:as|for)[ \t]+(?:a|an|its|the|this|that)?[ \t]*"
    r"(?:(?:(?:framework|payment|settlement)[ \t]+)?"
    r"(?:conduit|intermediary|vendor)|beneficiary|candidate|company|issuer|"
    r"provider|recipient|role|security|source|supplier|vehicle|winner)\b",
    flags=re.IGNORECASE,
)
ENTITY_PASSIVE_SELECTION = re.compile(
    rf"{ENTITY_CLAUSE_START}(?P<name>{ENTITY_SUBJECT_NAME})[ \t]+"
    r"(?:is|are|was|were|has[ \t]+been|have[ \t]+been)[ \t]+"
    r"(?:appointed|chosen|designated|nominated|selected|shortlisted)"
    r"(?=[ \t]*(?:as[ \t]+(?:a|an|the)?[ \t]*"
    r"(?:beneficiary|candidate|company|conduit|intermediary|issuer|provider|"
    r"recipient|security|source|supplier|vehicle|vendor|winner))?"
    r"(?:[,.;:!?)]|\Z|\n))",
    flags=re.IGNORECASE,
)
ENTITY_RESULT_ROLE = re.compile(
    rf"\b(?:leaves?|left|makes?|made)[ \t]+`?"
    rf"(?P<name>{ENTITY_NAME_PHRASE})`?[ \t]+(?:as[ \t]+)?"
    r"(?:(?:the|a|an|only|primary|qualified|selected|single|sole)[ \t]+)*"
    rf"{ENTITY_ROLE}\b",
    flags=re.IGNORECASE,
)
ENTITY_SOURCE_ATTRIBUTION = re.compile(
    rf"\bsource[ \t]*:[ \t]*`?(?P<name>{ENTITY_NAME_TOKEN})`?"
    r"(?=[ \t]+(?:annual|earnings|filing|investor|press|research|report)\b|"
    r"[,.;:!?)]|\Z|\n)",
    flags=re.IGNORECASE,
)
ENTITY_CAPACITY_AT = re.compile(
    rf"\bcapacity[ \t]+at[ \t]+`?(?P<name>{ENTITY_SUBJECT_NAME})`?"
    r"(?=[ \t]+remains?[ \t]+(?:constrained|limited|scarce|tight)\b)",
    flags=re.IGNORECASE,
)
ENTITY_DASH_ASSIGNMENT = re.compile(
    rf"\b(?:(?:award|comparison|contract|equity|investable|public-market|"
    rf"scarcity|selected)[ \t]+)*"
    rf"{ENTITY_ROLE}(?:[ \t]+-[ \t]+|[ \t]*(?:—|–)[ \t]*)`?"
    rf"(?P<name>{ENTITY_NAME_PHRASE})`?"
    r"(?=[ \t]*(?:[,.;:!?)]|—|–|\Z|\n))",
    flags=re.IGNORECASE,
)
ENTITY_PARENTHETICAL_ROLE = re.compile(
    rf"\b(?:(?:candidate|chosen|designated|listed|nominated|preferred|primary|"
    rf"provisional|public|qualified|selected)[ \t]+)*"
    rf"{ENTITY_ROLE}[ \t]*\([ \t]*`?(?P<name>{ENTITY_NAME_PHRASE})`?"
    r"[ \t]*\)[ \t]+(?=(?:is|are|was|were|controls?|defines?|has|"
    r"anchors?|holds?|maintains?|owns|operates|supplies|provides|settles?|"
    r"may|might|can|could|"
    r"will|would)\b)",
    flags=re.IGNORECASE,
)
ENTITY_STANDOUT_ROLE = re.compile(
    rf"{ENTITY_CLAUSE_START}"
    rf"(?P<name>{ENTITY_SUBJECT_NAME})[ \t]+"
    r"(?:stands?[ \t]+out|is[ \t]+positioned)[ \t]+as[ \t]+"
    r"(?:(?:the|a|an|only|preferred|primary|qualified|selected)[ \t]+)*"
    rf"{ENTITY_ROLE}\b",
    flags=re.IGNORECASE,
)
ENTITY_POISED_OUTCOME = re.compile(
    rf"{ENTITY_CLAUSE_START}"
    rf"(?P<name>{ENTITY_SUBJECT_NAME})[ \t]+"
    r"(?:(?:is|remains?)[ \t]+)?poised[ \t]+to[ \t]+"
    r"(?:benefit|capture|receive|secure|take|win)\b",
    flags=re.IGNORECASE,
)
ENTITY_BENCHMARK_SUBJECT = re.compile(
    rf"{ENTITY_CLAUSE_START}(?P<name>{ENTITY_SUBJECT_NAME})[ \t]+"
    r"(?:is|are|was|were|remains?)[ \t]+"
    r"(?:(?:already|currently)[ \t]+)?(?:applied|used)[ \t]+"
    r"(?:as|for)[ \t]+(?:a[ \t]+|the[ \t]+)?"
    r"(?:benchmark|comparison|relative[ \t]+returns?)\b",
    flags=re.IGNORECASE,
)
ENTITY_ATTRIBUTION = re.compile(
    rf"\b(?:according[ \t]+to|as[ \t]+(?:cited|reported)[ \t]+by|per)"
    rf"[ \t]+`?(?P<name>{ENTITY_NAME_PHRASE})`?"
    r"(?=[ \t]*(?:[,.;:!?)]|\Z|\n))",
    flags=re.IGNORECASE,
)
ENTITY_CONTEXTUAL_SOURCE = re.compile(
    rf"\b(?:funding|supply)[ \t]+from[ \t]+(?:the[ \t]+)?"
    rf"(?:(?:listed|named|public|selected)[ \t]+)+{ENTITY_ROLE}[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]+(?:clears?|comes?|determines?|supports?|supplies)\b)",
    flags=re.IGNORECASE,
)
ENTITY_CONTEXTUAL_DEPENDENCY = re.compile(
    rf"\b(?:depends?|relies)[ \t]+(?:on|upon)[ \t]+(?:the[ \t]+)?"
    rf"(?:(?:listed|named|public|selected)[ \t]+)*{ENTITY_ROLE}[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]+(?:for|under|with|within)\b)",
    flags=re.IGNORECASE,
)
ENTITY_INDEX_NAMING = re.compile(
    rf"\b(?:benchmark|comparison)[ \t]+index[ \t]+"
    rf"(?:calls?|labels?|names?)[ \t]+(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]+as[ \t]+(?:a|an|the)?[ \t]*"
    r"(?:(?:leading|listed|named|public|selected)[ \t]+)*"
    r"(?:benchmark|company|issuer|provider|security|vehicle)\b)",
    flags=re.IGNORECASE,
)
ENTITY_NOMINAL_SELECTION = re.compile(
    rf"\b(?:choice|nomination|selection)[ \t]+of[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]+as[ \t]+(?:a|an|the)?[ \t]*"
    r"(?:(?:listed|public|selected)[ \t]+)*"
    rf"{ENTITY_ROLE}\b)",
    flags=re.IGNORECASE,
)
ENTITY_ROLE_FILL = re.compile(
    rf"\b(?:(?:constrained|critical|listed|public|selected)[ \t]+)*"
    rf"(?:role|{ENTITY_ROLE})[ \t]+(?:is|are|was|were)[ \t]+"
    rf"(?:filled|held|occupied)[ \t]+by[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]*(?:,[ \t]+(?:a|an|the)[ \t]+"
    r"(?:(?:listed|public)[ \t]+)*(?:company|issuer|security)\b|"
    r"[,.;:!?)]|\Z|\n))",
    flags=re.IGNORECASE,
)
ENTITY_CONTEXTUAL_RENT_ROUTE = re.compile(
    rf"\b(?:incremental|scarcity)?[ \t]*rent[ \t]+"
    rf"(?:accrues?|flows?)[ \t]+to[ \t]+(?:the[ \t]+)?"
    rf"(?:(?:listed|named|public|selected)[ \t]+)*{ENTITY_ROLE}[ \t]+"
    rf"(?:«|\"|')(?P<name>{ENTITY_FLEX_PHRASE})(?:»|\"|')",
    flags=re.IGNORECASE,
)
ENTITY_FRONTED_SOURCE = re.compile(
    rf"\bfrom[ \t]+(?:the[ \t]+)?"
    rf"(?:(?:listed|named|public|selected)[ \t]+)+{ENTITY_ROLE}[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]+comes?\b)",
    flags=re.IGNORECASE,
)
ENTITY_COMPANY_LABEL = re.compile(
    rf"\b(?:company|issuer|operator|provider|supplier)[ \t]+"
    rf"(?:called|labeled|labelled|named)[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]+(?:captures?|clears?|controls?|determines?|owns?|"
    r"receives?|supplies|supports?)\b)",
    flags=re.IGNORECASE,
)
ENTITY_CONTEXTUAL_POSSESSIVE = re.compile(
    rf"{ENTITY_CLAUSE_START}(?P<name>{ENTITY_FLEX_PHRASE})['’]s[ \t]+"
    r"(?:capacity|equipment|line|network|output|supply)[ \t]*,"
    r"[ \t]*(?:as|being)[ \t]+(?:a|an|the)?[ \t]*"
    r"(?:(?:listed|public|selected)[ \t]+)+"
    rf"{ENTITY_ROLE}\b",
    flags=re.IGNORECASE,
)
ENTITY_CONTEXTUAL_DASH = re.compile(
    rf"\b(?:(?:listed|named|public|selected)[ \t]+)+{ENTITY_ROLE}"
    rf"[ \t]*(?:—|–)[ \t]*(?P<name>{ENTITY_FLEX_PHRASE})"
    r"(?=[ \t]*(?:—|–))",
    flags=re.IGNORECASE,
)
ENTITY_CONTEXTUAL_PARENTHETICAL = re.compile(
    rf"\b{ENTITY_ROLE}[ \t]*\([ \t]*(?:the[ \t]+)?"
    rf"(?:(?:listed|named|public|selected)[ \t]+)+{ENTITY_ROLE}[ \t]+"
    rf"(?P<name>{ENTITY_FLEX_PHRASE})[ \t]*\)"
    r"(?=[ \t]+(?:captures?|clears?|controls?|defines?|determines?|"
    r"owns?|receives?|supplies|supports?)\b)",
    flags=re.IGNORECASE,
)
CJK_BENCHMARK_COMPARISON = re.compile(
    r"(?:与|以|对照|相较于)[ \t]*"
    r"(?P<name>[\u3400-\u9fff]{2,24}"
    r"(?:[0-9]{1,6}[\u3400-\u9fff]{0,12})?(?:指数|基准))"
    r"[ \t]*(?:进行[ \t]*)?(?:比较|对比|衡量|为参照|为基准)"
)
RAW_SEMANTIC_ENTITY_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
    for pattern in (
        # Preserve the exact source bytes for names that tokenization would split
        # at Unicode punctuation, symbols, legal-suffix dots, or mixed scripts.
        r"\b(?:who|which)[^?\n]{0,160}\?[ \t]*(?P<name>[^\n]{2,180}?)[ \t]+would\b",
        r"(?P<name>[^\n]{2,180}?)['’]s"
        r"[ \t]+(?:qualified[ \t]+)?(?:capacity|line|output|supply)\b",
        r"\b(?:asset[ \t]+)?(?:beneficiary|claimant|incumbent|operator|owner|"
        r"provider|supplier|vendor)[ \t]*,[ \t]*(?P<name>[^\n,]{2,180}?)[ \t]*,"
        r"[ \t]*(?:captures?|controls?|holds?|owns?|receives?|supplies)\b",
        r"\b(?:captured|controlled|held|operated|owned|remitted|supplied)"
        r"(?:[ \t]+legally)?[ \t]+by[ \t]+(?P<name>[^\n]{2,180}?)"
        r"(?=[ \t]+(?:after|before|for|in|on|under|with|within)\b|"
        r"[.!?](?=[ \t]*(?:\n|\Z))|\n|\Z)",
        r"\b(?:accrues?|flows?|goes?|remitted|routed|transferred)"
        r"[ \t]+(?:through|to)[ \t]+(?P<name>[^,;\n]{2,180}?)"
        r"(?=[ \t]+(?:after|before|for|in|on|under|with|within)\b|"
        r"[,;]|[.!?](?=[ \t]*(?:\n|\Z))|\n|\Z)",
        r"\bunlike[^\n,]{0,120},[ \t]+"
        r"(?P<name>[^\n,;]{2,180}?)[ \t]+"
        r"(?:captures?|controls?|owns?|receives?)\b",
        r"^[ \t]*[-*>]?[ \t]*(?:public-market[ \t]+)?"
        r"(?:beneficiary|claimant|exposure|holder|issuer|operator|owner|"
        r"proxy|security)[^:\n]{0,80}:[ \t]*(?P<name>[^;\n]{2,180}?)[ \t]*"
        r"(?=;|$)",
        r"\b(?:identified|named|selected|disclosed)[^.!?\n]{0,64}\bas[ \t]+"
        r"(?P<name>[^\n]{2,180}?)(?=[ \t]+(?:is|are|was|were|remains?)\b|"
        r"[.!?](?=\s|\Z)|\n|\Z)",
        r"^[ \t]*\|[^|\n]*(?:beneficiary|claimant|exposure|holder|issuer|"
        r"owner|security)[^|\n]*\|[ \t]*(?P<name>[^|\n]{2,180}?)[ \t]*\|",
        r"^#{1,6}[ \t]+[^\n]*(?:beneficiary|claimant|exposure|holder|issuer|"
        r"listed|owner|security)[^\n]*\n(?:[ \t]*\n)?"
        r"(?P<name>[^\n]{2,180}?)[ \t]*$",
        r"^\[\^[^\]\n]+\]:[ \t]*(?P<name>[^\n]{2,180}?)[ \t]*$",
        r"\b(?:held|operated|owned)[ \t]+by[ \t]+"
        r"(?P<name>[^)\n]{2,180}?)[ \t]*\)",
        r"\b(?:beneficiary|counterparty|holder|issuer|operator|owner|proxy|"
        r"security)[ \t]+(?:is|was|remains?)[ \t]+[`\"“«]"
        r"(?P<name>[^`\"”»\n]{2,180}?)[`\"”»]",
        r"\b(?:beneficiary|issuer|operator|owner|proxy|security)"
        r"[^.!?\n]{0,80}\b(?:called|described|identified|named)[ \t]+as[ \t]+"
        r"[`\"“«](?P<name>[^`\"”»\n]{2,180}?)[`\"”»]",
        r"\b(?:evidence[ \t]+)?source:[ \t]*(?P<name>[^\n]{2,180}?)[ \t]+"
        r"(?:annual|earnings|investor|regulatory)[ \t]+"
        r"(?:filing|report|release|statement)\b",
        r"\b(?:branded[ \t]+commercial[ \t]+)?"
        r"(?:beneficiary|operator|owner|provider|proxy|supplier|vendor)"
        r"[ \t]+(?:is|was)[ \t]+(?P<name>[^\n]{2,180}?)[ \t]+"
        r"(?:after|before|for|in|on|under|with|within)\b",
        r"\b(?:comparison[ \t]+)?(?:benchmark|index)[ \t]+(?:is|was)"
        r"[ \t]+(?:a|an|the)[ \t]+(?P<name>[^\n]{2,180}?)[ \t]+"
        r"(?:benchmark|index)[ \t]+(?:family|series)\b",
        r"^(?:bottleneck|constraint|public-market|security)[ \t]+"
        r"(?:beneficiary|claimant|exposure|holder|issuer|operator|owner|"
        r"proxy|security)[ \t]*/[^/\n]*/[ \t]*(?P<name>[^\n]{2,180}?)"
        r"[ \t]*[.!?]?$",
        r"\b(?:if|when)[^,;\n]{0,120},[ \t]*(?:then[ \t]+)?"
        r"(?P<name>[^\n,;]{2,180}?)[ \t]+"
        r"(?:captures?|controls?|owns?|receives?)\b",
        r"\b(?:do[ \t]+not|never)[ \t]+(?:choose|identify|name|select|"
        r"shortlist)[ \t]+(?P<name>[^;\n]{2,180}?)[ \t]*;",
        r"[\"“«](?P<name>[^\n\"”»]{2,180}?)[ \t]+(?:is|was|remains?)"
        r"[ \t]+(?:a|an|the)[ \t]+(?:only[ \t]+)?"
        r"(?:(?:listed|named|public)[ \t]+)*"
        r"(?:beneficiary|claimant|holder|issuer|operator|owner|security)"
        r"[.!?]?[\"”»]",
        r"\b(?:award|designation|nomination|selection)[^\n]{0,80}"
        r"[ \t]+(?:goes?|went|was[ \t]+awarded)[ \t]+to[ \t]+"
        r"(?P<name>[^\n]{2,180}?)(?=[.!?](?=\s|\Z)|\n|\Z)",
        r"\b(?:contracts?|procurement|records?)[ \t]+"
        r"(?:call|calls|name|named|names|select|selected|selects)[ \t]+"
        r"(?P<name>[^\n]{2,180}?)[ \t]+as[ \t]+"
        r"(?:a|an|the)[ \t]+(?:exclusive[ \t]+)?"
        r"(?:beneficiary|claimant|issuer|operator|owner|provider|supplier|vendor)\b",
        r"\b(?:beneficiary|claimant|issuer|operator|owner|provider|security|"
        r"supplier|vendor)[ \t]+(?:called|named)[ \t]+"
        r"(?P<name>[^\n]{2,180}?)[ \t]+(?:is|was|remains?)\b",
        r"\b(?:channels?|routes?|transfers?)[^.!?\n]{0,80}"
        r"[ \t]+(?:through|to|via)[ \t]+(?P<name>[^\n]{2,180}?)"
        r"(?=[.!?](?=[.!?]|\s|\Z))",
        r"\b(?:benchmark|beneficiary|candidate|claimant|exposure|holder|"
        r"issuer|operator|owner|provider|proxy|security|supplier|vendor)"
        r"\b(?:[ \t]+index)?[ \t]+(?:chosen|designated|named|selected)"
        r"(?:[ \t]+(?:as|for|under)[ \t]+[^.!?\n]{1,64}?)?"
        r"[ \t]+(?:is|was|remains?)[ \t]+"
        r"(?P<name>[^.!?\n]{2,180}?)(?=[.!?]+(?=\s|\Z))",
        r"\b(?:beneficiary|claimant|exposure|holder|issuer|operator|owner|"
        r"provider|proxy|security|supplier|vendor)[ \t]+that[ \t]+"
        r"[^.!?\n]{1,96}?[ \t]+(?:is|was|remains?)[ \t]+"
        r"(?P<name>[^.!?\n]{2,180}?)(?=[.!?]+(?=\s|\Z))",
        r"(?:\A|^[ \t>*-]*|(?<=[.!?])\s+)"
        r"(?P<name>[^\n]{2,180}?)[ \t]+"
        r"(?:fronts?|is[ \t]+where|sits?[ \t]+behind)\b",
        r"\b(?:source|supply|unit)[^\n]{0,96}[ \t]+from[ \t]+"
        r"(?P<name>[^\n]{2,180}?)(?=[ \t]+(?:is|are|was|were|remains?)\b|"
        r"[.!?](?=\s|\Z)|\n|\Z)",
        r"(?:稀缺租金|租金|经济利益)[^。！？\n]{0,40}(?:流向|归于|支付给)"
        r"(?P<name>[^。！？\n]{2,80})(?=[。！？]|\n|\Z)",
        r"(?:選定された|指名された)(?:供給者|会社|事業者)は"
        r"(?P<name>[^。！？\n]{2,80}?)(?:です|である)(?=[。！？]|\n|\Z)",
    )
)
ROLE_NEUTRAL_SUBJECTS = frozenset(
    {
        "a",
        "access",
        "absorber",
        "absorbers",
        "an",
        "analysis",
        "architecture",
        "architectures",
        "benchmark",
        "benchmarks",
        "beneficiaries",
        "beneficiary",
        "bottleneck",
        "cash",
        "capacity",
        "customer",
        "customers",
        "companies",
        "company",
        "constraint",
        "constraints",
        "demand",
        "duration",
        "equipment",
        "evidence",
        "expression",
        "fee",
        "fees",
        "framework",
        "it",
        "independent",
        "international",
        "issuer",
        "issuers",
        "index",
        "manufacturer",
        "manufacturers",
        "market",
        "markets",
        "operator",
        "operators",
        "order",
        "orders",
        "owner",
        "owners",
        "proxy",
        "proxies",
        "procurement",
        "production",
        "public",
        "publisher",
        "publishers",
        "rent",
        "rents",
        "recipient",
        "recipients",
        "research",
        "revenue",
        "role",
        "roles",
        "scarcity",
        "security",
        "source",
        "sources",
        "supplier",
        "suppliers",
        "supply",
        "system",
        "systems",
        "substitute",
        "substitutes",
        "that",
        "the",
        "these",
        "they",
        "this",
        "those",
        "ticker",
        "tickers",
        "tollbooth",
        "tollbooths",
        "unlocker",
        "unlockers",
        "vendor",
        "vendors",
        "we",
    }
)
ROLE_NEUTRAL_REFERENTS = ROLE_NEUTRAL_SUBJECTS | frozenset(
    {
        "all",
        "and",
        "annual",
        "any",
        "appear",
        "as",
        "at",
        "admitted",
        "assigned",
        "asset",
        "available",
        "before",
        "blank",
        "below",
        "candidate",
        "can",
        "cited",
        "could",
        "committed",
        "compatible",
        "comparison",
        "considered",
        "constrained",
        "conversion",
        "contracted",
        "contract",
        "current",
        "currently",
        "data",
        "deferred",
        "delayed",
        "downstream",
        "entity",
        "eventual",
        "for",
        "fragile",
        "filing",
        "formal",
        "chosen",
        "funded",
        "future",
        "generic",
        "hyperscale",
        "here",
        "identified",
        "identity",
        "in",
        "incremental",
        "industry",
        "interim",
        "labor",
        "liquid",
        "level",
        "later",
        "lead",
        "manufacturing",
        "mandatory",
        "may",
        "milestone",
        "might",
        "missing",
        "more",
        "must",
        "name",
        "named",
        "names",
        "neither",
        "nevertheless",
        "no",
        "none",
        "not",
        "null",
        "one",
        "only",
        "or",
        "payment",
        "payments",
        "pending",
        "placeholder",
        "placeholders",
        "primary",
        "private",
        "provisional",
        "provides",
        "purchase",
        "qualified",
        "qualification",
        "quality",
        "regulatory",
        "required",
        "reservation",
        "review",
        "securities",
        "selected",
        "single",
        "shorter",
        "spare",
        "stage",
        "still",
        "sole",
        "substitutable",
        "supports",
        "subject",
        "content",
        "tender",
        "transformer",
        "tooling",
        "times",
        "two",
        "unknown",
        "uncertain",
        "unresolved",
        "unassigned",
        "undetermined",
        "unidentified",
        "unnamed",
        "verification",
        "verified",
        "withheld",
        "will",
        "with",
        "would",
        "yet",
    }
)

SEMANTIC_ROLE_HEADS = frozenset(
    {
        "benchmark",
        "beneficiary",
        "candidate",
        "company",
        "expression",
        "exposure",
        "fabricator",
        "firm",
        "incumbent",
        "index",
        "issuer",
        "manufacturer",
        "name",
        "operator",
        "owner",
        "ownership",
        "pick",
        "producer",
        "provider",
        "proxy",
        "publisher",
        "recipient",
        "role",
        "security",
        "slot",
        "source",
        "supplier",
        "vendor",
        "vehicle",
        "winner",
    }
)
COPULA_TOKENS = frozenset(
    {
        "are",
        "be",
        "became",
        "become",
        "becomes",
        "is",
        "remain",
        "remains",
        "was",
        "were",
    }
)
SUBJECT_OUTCOME_VERBS = frozenset(
    {
        "accrue",
        "accrues",
        "benefit",
        "benefits",
        "capture",
        "captures",
        "captured",
        "dominate",
        "dominates",
        "embody",
        "embodies",
        "emerge",
        "emerges",
        "extract",
        "extracted",
        "extracts",
        "fill",
        "filled",
        "fills",
        "has",
        "owns",
        "receive",
        "received",
        "receives",
        "secure",
        "secured",
        "secures",
        "serve",
        "serves",
        "take",
        "takes",
        "took",
        "win",
        "wins",
        "won",
    }
)
DIRECT_OBJECT_VERBS = frozenset(
    {
        "choose",
        "chooses",
        "chose",
        "designate",
        "designated",
        "designates",
        "enrich",
        "enriches",
        "favor",
        "favors",
        "favour",
        "favours",
        "identify",
        "identifies",
        "named",
        "names",
        "nominate",
        "nominated",
        "nominates",
        "prefer",
        "preferred",
        "prefers",
        "reference",
        "referenced",
        "references",
        "select",
        "selected",
        "selects",
        "shortlist",
        "shortlisted",
        "shortlists",
        "underwrite",
        "underwrites",
    }
)
NOUN_SOURCE_PREPOSITIONS = {
    "demand": frozenset({"from"}),
    "funding": frozenset({"by", "from"}),
    "supply": frozenset({"from"}),
}
PREPOSITIONAL_OBJECT_VERBS = {
    "accrue": frozenset({"to"}),
    "accrues": frozenset({"to"}),
    "assign": frozenset({"to"}),
    "assigned": frozenset({"to"}),
    "assigns": frozenset({"to"}),
    "award": frozenset({"to"}),
    "awarded": frozenset({"to"}),
    "concentrate": frozenset({"at"}),
    "concentrates": frozenset({"at"}),
    "compare": frozenset({"against", "to", "with"}),
    "compared": frozenset({"against", "to", "with"}),
    "compares": frozenset({"against", "to", "with"}),
    "benchmark": frozenset({"against", "to", "with"}),
    "benchmarked": frozenset({"against", "to", "with"}),
    "benchmarks": frozenset({"against", "to", "with"}),
    "belong": frozenset({"to"}),
    "belonged": frozenset({"to"}),
    "belongs": frozenset({"to"}),
    "captured": frozenset({"by"}),
    "channel": frozenset({"through", "to", "via"}),
    "channeled": frozenset({"through", "to", "via"}),
    "channelled": frozenset({"through", "to", "via"}),
    "channels": frozenset({"through", "to", "via"}),
    "collect": frozenset({"by"}),
    "collected": frozenset({"by"}),
    "collects": frozenset({"by"}),
    "evaluate": frozenset({"against"}),
    "evaluated": frozenset({"against"}),
    "evaluates": frozenset({"against"}),
    "depend": frozenset({"on", "upon"}),
    "depended": frozenset({"on", "upon"}),
    "depends": frozenset({"on", "upon"}),
    "flow": frozenset({"through", "to", "via"}),
    "flows": frozenset({"through", "to", "via"}),
    "focus": frozenset({"on"}),
    "go": frozenset({"to"}),
    "goes": frozenset({"to"}),
    "hinge": frozenset({"on"}),
    "hinges": frozenset({"on"}),
    "land": frozenset({"with"}),
    "landed": frozenset({"with"}),
    "lands": frozenset({"with"}),
    "map": frozenset({"to"}),
    "maps": frozenset({"to"}),
    "migrate": frozenset({"to", "toward", "towards"}),
    "migrated": frozenset({"to", "toward", "towards"}),
    "migrates": frozenset({"to", "toward", "towards"}),
    "measure": frozenset({"against"}),
    "measured": frozenset({"against"}),
    "measures": frozenset({"against"}),
    "obtain": frozenset({"through"}),
    "obtained": frozenset({"through"}),
    "point": frozenset({"to", "toward", "towards"}),
    "pointed": frozenset({"to", "toward", "towards"}),
    "points": frozenset({"to", "toward", "towards"}),
    "pay": frozenset({"to"}),
    "paid": frozenset({"through", "to", "via"}),
    "pays": frozenset({"to"}),
    "route": frozenset({"through", "to"}),
    "routed": frozenset({"through", "to"}),
    "routes": frozenset({"through", "to"}),
    "remit": frozenset({"through", "to"}),
    "remitted": frozenset({"through", "to"}),
    "remits": frozenset({"through", "to"}),
    "receive": frozenset({"by"}),
    "received": frozenset({"by"}),
    "receives": frozenset({"by"}),
    "rely": frozenset({"on", "upon"}),
    "relied": frozenset({"on", "upon"}),
    "relies": frozenset({"on", "upon"}),
    "settle": frozenset({"at", "with"}),
    "settled": frozenset({"at", "with"}),
    "settles": frozenset({"at", "with"}),
    "supplied": frozenset({"by", "from"}),
    "track": frozenset({"against", "to", "with"}),
    "tracked": frozenset({"against", "to", "with"}),
    "tracks": frozenset({"against", "to", "with"}),
    "transfer": frozenset({"into", "through", "to"}),
    "transferred": frozenset({"into", "through", "to"}),
    "transfers": frozenset({"into", "through", "to"}),
}
SEMANTIC_PREPOSITION_BRIDGE = frozenset(
    {
        "already",
        "currently",
        "directly",
        "explicitly",
        "finally",
        "legally",
        "nominally",
        "ultimately",
    }
)
SEMANTIC_WORD = re.compile(r"[^\W_](?:[^\W_]|[&'’.-])*|[=:;,/()—–]")
SEMANTIC_PUNCTUATION = frozenset({"(", ")", ",", "/", ":", ";", "=", "—", "–"})
SEMANTIC_OBJECT_STOP_WORDS = frozenset(
    {
        "after",
        "as",
        "at",
        "because",
        "before",
        "but",
        "can",
        "could",
        "except",
        "filled",
        "for",
        "held",
        "if",
        "in",
        "is",
        "may",
        "might",
        "once",
        "occupied",
        "remain",
        "remains",
        "selected",
        "since",
        "so",
        "than",
        "that",
        "then",
        "though",
        "to",
        "unless",
        "until",
        "was",
        "were",
        "will",
        "when",
        "where",
        "whereas",
        "which",
        "while",
        "who",
        "whose",
        "with",
        "would",
        "yet",
    }
)
SEMANTIC_ROLE_PREFIX_MODIFIERS = frozenset(
    {
        "a",
        "an",
        "candidate",
        "chosen",
        "constrained",
        "critical",
        "designated",
        "ecosystem",
        "eventual",
        "incumbent",
        "investable",
        "key",
        "leading",
        "listed",
        "named",
        "operating",
        "preferred",
        "primary",
        "provisional",
        "public",
        "qualified",
        "selected",
        "single",
        "the",
        "unnamed",
    }
)
SEMANTIC_ROLE_COPULA_BRIDGE = frozenset(
    {
        "already",
        "apparently",
        "appears",
        "be",
        "been",
        "being",
        "can",
        "commercially",
        "could",
        "chosen",
        "currently",
        "deliberately",
        "eventually",
        "intentionally",
        "later",
        "legally",
        "likely",
        "may",
        "might",
        "must",
        "nominally",
        "not",
        "provisionally",
        "publicly",
        "selected",
        "seems",
        "shall",
        "should",
        "still",
        "tentatively",
        "to",
        "will",
        "would",
        "yet",
    }
)
CLAUSE_BOUNDARY_TOKENS = frozenset(
    {
        ";",
        "although",
        "because",
        "but",
        "following",
        "if",
        "once",
        "though",
        "unless",
        "until",
        "when",
        "where",
        "whereas",
        "which",
        "whichever",
        "while",
        "without",
        "who",
        "whoever",
        "whose",
        "whatever",
        "yet",
    }
)
SEMANTIC_CLAUSE_BOUNDARIES = CLAUSE_BOUNDARY_TOKENS | frozenset(
    {",", ";", ":", "—", "–"}
)
ROLE_NEUTRAL_CANDIDATE_PREFIX = re.compile(
    r"^(?:"
    r"(?:a|an|the)[ \t]+(?:broad|generic|liquid)\b|"
    r"(?:a|an)[ \t]+independently[ \t]+(?:opened|verified)\b|"
    r"(?:broad|generic|liquid)(?:[ \t]+(?:and|or)[ \t]+"
    r"(?:broad|generic|global|liquid))*\b|"
    r"(?:whichever|whoever|whatever)\b|"
    r"(?:will[ \t]+|would[ \t]+|may[ \t]+|might[ \t]+)?"
    r"(?:be[ \t]+)?(?:assigned|chosen|determined|identified|introduced|"
    r"deferred|evaluated|named|needed|postponed|reserved|selected|verified)\b|"
    r"(?:called[ \t]+(?:a[ \t]+)?(?:owner|role|supplier|operator))\b|"
    r"(?:category|functional|role)[ \t]+(?:description|descriptions|"
    r"label|labels|term|terms)\b|"
    r"no[ \t]+(?:beneficiary|candidate|company|entity|holder|issuer|name|"
    r"operator|owner|proxy|security|supplier|ticker|vendor)\b|"
    r"(?:deliberately|intentionally)[ \t]+(?:absent|unspecified|withheld)\b|"
    r"(?:intentionally[ \t]+)?blank\b|"
    r"(?:nominally[ \t]+unknown|null[ \t]+for[ \t]+now|"
    r"shown[ \t]+here|under[ \t]+review|undecided|unspecified)\b|"
    r"required\b|"
    r"identity[ \t]+withheld\b|"
    r"(?:currently[ \t]+)?known\b|"
    r"(?:nevertheless[ \t]+)?null\b|"
    r"not(?:[ \t]+yet)?[ \t]+(?:assigned|determined|identified|known|"
    r"named|necessary|needed|selected)\b|"
    r"(?:still[ \t]+)?(?:unknown|uncertain|undetermined|unidentified|"
    r"unnamed|unassigned)\b|"
    r"outside\b|one[ \t]+of\b|subject[ \t]+to\b"
    r")"
)
POSSESSIVE_ENTITY_CONNECTORS = frozenset(
    {
        "and",
        "de",
        "del",
        "der",
        "di",
        "et",
        "for",
        "la",
        "le",
        "of",
        "the",
        "und",
        "van",
        "von",
        "y",
    }
)
POSSESSIVE_LEGAL_SUFFIXES = frozenset(
    {
        "ab",
        "ag",
        "aps",
        "as",
        "asa",
        "bv",
        "co",
        "corp",
        "corporation",
        "gmbh",
        "hf",
        "inc",
        "limited",
        "llc",
        "llp",
        "lp",
        "ltd",
        "nv",
        "oyj",
        "plc",
        "pte",
        "sa",
        "sac",
        "se",
        "sl",
        "spa",
    }
)
POSSESSIVE_REPORTING_BOUNDARIES = frozenset(
    {
        "argue",
        "argues",
        "argued",
        "ask",
        "asks",
        "asked",
        "assume",
        "assumes",
        "assumed",
        "believe",
        "believes",
        "believed",
        "conclude",
        "concludes",
        "concluded",
        "confirm",
        "confirms",
        "confirmed",
        "establish",
        "establishes",
        "established",
        "estimate",
        "estimates",
        "estimated",
        "expect",
        "expects",
        "expected",
        "find",
        "finds",
        "found",
        "how",
        "if",
        "indicate",
        "indicates",
        "indicated",
        "infer",
        "infers",
        "inferred",
        "note",
        "notes",
        "noted",
        "observe",
        "observes",
        "observed",
        "propose",
        "proposes",
        "proposed",
        "report",
        "reports",
        "reported",
        "reveal",
        "reveals",
        "revealed",
        "say",
        "says",
        "said",
        "show",
        "shows",
        "showed",
        "state",
        "states",
        "stated",
        "suggest",
        "suggests",
        "suggested",
        "that",
        "whether",
        "why",
    }
)


def _walk_entities(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            if key in ENTITY_KEYS:
                if isinstance(child, str) and child.strip():
                    yield child.strip()
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, str) and item.strip():
                            yield item.strip()
            yield from _walk_entities(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_entities(child)


def _contains_named_entity(text: str, entity: str) -> bool:
    if len(entity) < 2:
        return False
    return (
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(entity)}(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _without_markdown_headings(text: str) -> str:
    """Mask headings so their required labels are not mistaken for names."""

    return "\n".join(
        "" if line.lstrip().startswith("#") else line
        for line in text.splitlines()
    )


def _is_entity_candidate(candidate: str) -> bool:
    """Distinguish an explicit name slot from ordinary role-neutral prose."""

    raw = candidate.strip(" `\"'’.,;:!?()[]{}")
    normalized = raw.casefold()
    if not normalized:
        return False
    if re.match(r"^(?:A|An|The|a|an|the)[ \t]+[a-z]", raw):
        return False
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.?", raw):
        return False
    if raw.rstrip(".") in GENERIC_UPPERCASE_CANONICAL:
        return False
    if re.match(r"(?i)^(?:n/?a|none|null|tba|tbd)\.(?:[ \t]|\Z)", raw):
        return False
    if re.fullmatch(
        r"(?:n/?a|none|null|tba|tbd|not[ \t_-]+(?:applicable|assigned|"
        r"available|determined|identified|known|named|selected))",
        normalized,
    ):
        return False
    if raw[:1].islower() and ROLE_NEUTRAL_CANDIDATE_PREFIX.match(normalized):
        return False
    words = re.findall(r"[^\W_]+", normalized)
    return bool(words) and not all(word in ROLE_NEUTRAL_REFERENTS for word in words)


def _candidate_from_tokens(
    tokens: list[str],
    start: int,
    stop: int | None = None,
) -> str:
    boundary = len(tokens) if stop is None else min(stop, len(tokens))
    words: list[str] = []
    for token in tokens[start:boundary]:
        if token in {":", ";", ",", "—", "–"}:
            break
        if words and token.casefold() in CLAUSE_BOUNDARY_TOKENS:
            break
        words.append(token)
        if len(words) == 5:
            break
    auxiliaries = {
        "already",
        "be",
        "been",
        "being",
        "can",
        "could",
        "currently",
        "eventually",
        "may",
        "might",
        "must",
        "nevertheless",
        "not",
        "shall",
        "should",
        "still",
        "will",
        "would",
    }
    while words and words[-1].casefold() in auxiliaries:
        words.pop()
    return " ".join(words).strip()


def _semantic_candidate_from_tokens(
    tokens: list[str],
    start: int,
    stop: int | None = None,
    *,
    stop_words: frozenset[str] = frozenset(),
    strip_role_prefix: bool = False,
) -> str:
    """Extract one bounded semantic slot while preserving the full name."""

    boundary = len(tokens) if stop is None else min(stop, len(tokens))
    words: list[str] = []
    for token in tokens[start:boundary]:
        normalized = token.casefold().rstrip(".")
        if token in SEMANTIC_PUNCTUATION:
            break
        if normalized in stop_words or (
            words and normalized in CLAUSE_BOUNDARY_TOKENS
        ):
            break
        words.append(token)
        if len(words) == 10:
            break

    auxiliaries = {
        "already",
        "be",
        "been",
        "being",
        "can",
        "could",
        "currently",
        "eventually",
        "may",
        "might",
        "must",
        "nevertheless",
        "not",
        "shall",
        "should",
        "still",
        "will",
        "would",
    }
    while words and words[-1].casefold().rstrip(".") in auxiliaries:
        words.pop()
    while words and words[0].casefold().rstrip(".") == "only":
        words.pop(0)

    if strip_role_prefix:
        lowered_words = [word.casefold().rstrip(".") for word in words]
        for role_index, word in enumerate(lowered_words[:6]):
            if word not in SEMANTIC_ROLE_HEADS:
                continue
            if role_index and all(
                prefix in SEMANTIC_ROLE_PREFIX_MODIFIERS
                for prefix in lowered_words[:role_index]
            ):
                words = words[role_index + 1 :]
            break

    return " ".join(words).strip(" `\"'’.,;:!?()[]{}")


def _nearest_possessive_noun_phrase(candidate: str) -> str:
    """Preserve the nearest named NP without parsing its reporting prefix."""

    tokens = list(re.finditer(r"\S+", candidate))
    if not tokens:
        return ""

    def normalized(token: str) -> str:
        return re.sub(
            r"[^\w]+",
            "",
            token.casefold(),
            flags=re.UNICODE,
        )

    def has_entity_signal(token: str) -> bool:
        return (
            any(character.isupper() or character.isdigit() for character in token)
            or any(ord(character) > 127 for character in token)
            or re.search(r"[&+@%#=/·־・‑_]", token) is not None
        )

    last_token = tokens[-1].group(0).strip(" `\"'’.,;:!?()[]{}")
    last_normalized = normalized(last_token)
    if (
        last_normalized in ROLE_NEUTRAL_REFERENTS
        and last_normalized not in POSSESSIVE_LEGAL_SUFFIXES
    ):
        return last_token

    start_index = len(tokens) - 1
    saw_entity_signal = False
    saw_legal_suffix = False
    for index in range(len(tokens) - 1, -1, -1):
        raw_token = tokens[index].group(0)
        token = raw_token.strip(" `\"'’.,;:!?()[]{}")
        token_normalized = normalized(token)
        if has_entity_signal(token):
            saw_entity_signal = True
            start_index = index
            continue
        if (
            token_normalized in POSSESSIVE_LEGAL_SUFFIXES
            and (
                saw_entity_signal
                or saw_legal_suffix
                or index == len(tokens) - 1
            )
        ):
            saw_legal_suffix = True
            start_index = index
            continue
        if saw_entity_signal and token_normalized in POSSESSIVE_ENTITY_CONNECTORS:
            start_index = index
            continue
        if saw_legal_suffix and not saw_entity_signal:
            if (
                token_normalized in POSSESSIVE_REPORTING_BOUNDARIES
                or raw_token.rstrip().endswith((",", ";", ":"))
            ):
                break
            if token_normalized:
                start_index = index
                continue
        break

    if saw_entity_signal or saw_legal_suffix:
        return candidate[tokens[start_index].start() :].strip(" `\"'’")
    return last_token


def _raw_semantic_entity_slots(text: str) -> Iterable[str]:
    """Yield exact bounded names before lossy semantic tokenization."""

    for pattern in RAW_SEMANTIC_ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group("name").strip(" \t`\"'“”‘’«»")
            if re.search(
                r"['’]s[ \t]+(?:qualified[ \t]+)?"
                r"(?:capacity|line|output|supply)\b",
                match.group(0),
                flags=re.IGNORECASE,
            ):
                candidate = _nearest_possessive_noun_phrase(candidate)
            if _is_entity_candidate(candidate):
                yield candidate


def _semantic_entity_slots(text: str) -> Iterable[str]:
    """Yield names occupying selection, role, and rent-capture semantic slots."""

    yield from _raw_semantic_entity_slots(text)
    for raw_clause in re.split(r"(?<=[.!?。！？])\s+|\n+", text):
        semantic_clause = re.sub(
            r"<[^>\n]{1,128}>|\{\{[^}\n]{1,128}\}\}|\[[^\]\n]{1,128}\]",
            " ",
            raw_clause.replace("`", ""),
        )
        tokens = SEMANTIC_WORD.findall(semantic_clause)
        lowered = [token.casefold().rstrip(".") for token in tokens]
        if not tokens:
            continue

        for index, token in enumerate(lowered):
            if token not in SEMANTIC_ROLE_HEADS:
                continue
            if {
                "neither",
                "no",
                "none",
                "not",
            } & set(lowered[max(0, index - 7) : index]):
                continue
            for copula_index in range(index + 1, min(index + 6, len(tokens))):
                if lowered[copula_index] in CLAUSE_BOUNDARY_TOKENS:
                    break
                if lowered[copula_index] not in COPULA_TOKENS:
                    continue
                if not all(
                    bridge_token in SEMANTIC_ROLE_COPULA_BRIDGE
                    for bridge_token in lowered[index + 1 : copula_index]
                ):
                    break
                candidate = _semantic_candidate_from_tokens(
                    tokens,
                    copula_index + 1,
                    stop_words=SEMANTIC_OBJECT_STOP_WORDS,
                )
                if _is_entity_candidate(candidate):
                    yield candidate
                break

        for index, token in enumerate(lowered):
            if token in SUBJECT_OUTCOME_VERBS:
                passive_subject = index and lowered[index - 1] in {
                    "are",
                    "be",
                    "been",
                    "being",
                    "is",
                    "was",
                    "were",
                }
                if not passive_subject:
                    candidate_stop = index
                    boundaries = [
                        boundary_index
                        for boundary_index in range(index)
                        if lowered[boundary_index]
                        in SEMANTIC_CLAUSE_BOUNDARIES
                    ]
                    clause_start = (boundaries[-1] if boundaries else -1) + 1
                    if index and tokens[index - 1] == ",":
                        earlier_commas = [
                            boundary_index
                            for boundary_index in range(index - 1)
                            if tokens[boundary_index] == ","
                        ]
                        if earlier_commas:
                            candidate_stop = earlier_commas[-1]
                            prior_boundaries = [
                                boundary_index
                                for boundary_index in boundaries
                                if boundary_index < candidate_stop
                                and tokens[boundary_index] != ","
                            ]
                            clause_start = (
                                prior_boundaries[-1]
                                if prior_boundaries
                                else -1
                            ) + 1
                    candidate = _semantic_candidate_from_tokens(
                        tokens, clause_start, candidate_stop
                    )
                    if _is_entity_candidate(candidate):
                        yield candidate
            if token in DIRECT_OBJECT_VERBS:
                if (
                    (index and lowered[index - 1] in COPULA_TOKENS)
                    or (
                        index + 1 < len(tokens)
                        and lowered[index + 1]
                        in (COPULA_TOKENS | SEMANTIC_ROLE_HEADS)
                    )
                    or (
                        index + 1 < len(tokens)
                        and lowered[index + 1] in {"neither", "no", "none", "not"}
                    )
                    or (
                        index + 1 < len(tokens)
                        and lowered[index + 1].endswith(("'s", "’s"))
                        and lowered[index + 1][:-2] in SEMANTIC_ROLE_HEADS
                    )
                ):
                    continue
                candidate = _semantic_candidate_from_tokens(
                    tokens,
                    index + 1,
                    stop_words=SEMANTIC_OBJECT_STOP_WORDS,
                )
                if _is_entity_candidate(candidate):
                    yield candidate
            required_prepositions = PREPOSITIONAL_OBJECT_VERBS.get(token)
            if required_prepositions is None:
                continue
            for prep_index in range(index + 1, min(index + 6, len(tokens))):
                if lowered[prep_index] in required_prepositions:
                    if not all(
                        bridge_token in SEMANTIC_PREPOSITION_BRIDGE
                        for bridge_token in lowered[index + 1 : prep_index]
                    ):
                        break
                    candidate = _semantic_candidate_from_tokens(
                        tokens,
                        prep_index + 1,
                        stop_words=SEMANTIC_OBJECT_STOP_WORDS,
                        strip_role_prefix=True,
                    )
                    if _is_entity_candidate(candidate):
                        yield candidate
                    break

        for index, token in enumerate(lowered):
            required_prepositions = NOUN_SOURCE_PREPOSITIONS.get(token)
            if required_prepositions is None:
                continue
            for prep_index in range(index + 1, min(index + 4, len(tokens))):
                if lowered[prep_index] not in required_prepositions:
                    continue
                predicate_index = next(
                    (
                        cursor
                        for cursor in range(prep_index + 1, len(tokens))
                        if lowered[cursor]
                        in (
                            COPULA_TOKENS
                            | frozenset({"has", "have", "had"})
                        )
                    ),
                    len(tokens),
                )
                candidate = _candidate_from_tokens(
                    tokens,
                    prep_index + 1,
                    predicate_index,
                )
                if _is_entity_candidate(candidate):
                    yield candidate
                break

        for index, token in enumerate(lowered):
            if token not in {"called", "named"}:
                continue
            preceding = lowered[max(0, index - 6) : index]
            if not any(word in SEMANTIC_ROLE_HEADS for word in preceding):
                continue
            predicate_index = next(
                (
                    cursor
                    for cursor in range(index + 1, len(tokens))
                    if lowered[cursor] in SUBJECT_OUTCOME_VERBS
                ),
                len(tokens),
            )
            if predicate_index == len(tokens):
                continue
            candidate = _candidate_from_tokens(
                tokens,
                index + 1,
                predicate_index,
            )
            if _is_entity_candidate(candidate):
                yield candidate

        paired_delimiters = {"(": ")", "/": "/", "—": "—", "–": "–"}
        for delimiter_index, delimiter in enumerate(tokens):
            if delimiter not in {"(", "/", ":", "=", "—", "–"}:
                continue
            label_words = set(lowered[max(0, delimiter_index - 10) : delimiter_index])
            if not label_words & SEMANTIC_ROLE_HEADS:
                continue
            paired = paired_delimiters.get(delimiter)
            if paired is not None:
                stop_index = next(
                    (
                        cursor
                        for cursor in range(delimiter_index + 1, len(tokens))
                        if tokens[cursor] == paired
                    ),
                    -1,
                )
                if stop_index < 0:
                    continue
            else:
                stop_index = next(
                    (
                        cursor
                        for cursor in range(delimiter_index + 1, len(tokens))
                        if tokens[cursor] in SEMANTIC_PUNCTUATION
                    ),
                    len(tokens),
                )
            candidate = _semantic_candidate_from_tokens(
                tokens,
                delimiter_index + 1,
                stop_index,
                stop_words=SEMANTIC_OBJECT_STOP_WORDS,
            )
            if _is_entity_candidate(candidate):
                yield candidate


def find_role_neutral_violations(
    memo: str,
    security_heading: str,
    entity_payloads: Iterable[Any] = (),
) -> list[str]:
    """Return deterministic issuer/security markers found before Security map."""

    if memo.count(security_heading) != 1:
        return ["Security map heading cardinality"]
    prefix = memo.split(security_heading, 1)[0]
    prose = _without_markdown_headings(prefix)
    violations: set[str] = set()
    for label, pattern in (
        ("URI", URI),
        ("email", EMAIL),
        ("domain", BARE_HOST),
    ):
        if pattern.search(prefix):
            violations.add(label)

    known_entities = {
        entity
        for payload in entity_payloads
        for entity in _walk_entities(payload)
    }
    for entity in known_entities:
        if _contains_named_entity(prefix, entity):
            violations.add(entity)
    violations.update(_raw_semantic_entity_slots(prefix))

    for match in UPPERCASE_ENTITY.finditer(prefix):
        token = match.group(0).lstrip("$")
        if (
            token.rstrip(".") not in GENERIC_UPPERCASE_CANONICAL
            and not token.startswith("C-")
        ):
            violations.add(match.group(0))
    for pattern in (
        EXCHANGE_TICKER,
        NUMERIC_TICKER,
        CAMELCASE_BRAND,
    ):
        violations.update(match.group(0) for match in pattern.finditer(prefix))
    violations.update(
        match.group(0)
        for match in CJK_CORPORATE.finditer(prefix)
        if not match.group(0).startswith(("任何", "任一"))
    )
    for pattern in (CORPORATE_NAME, LOWERCASE_CORPORATE_NAME):
        violations.update(
            match.group(0)
            for match in pattern.finditer(prose)
            if _is_entity_candidate(match.group(0))
        )
    violations.update(
        match.group(0).strip()
        for match in STANDALONE_NAME.finditer(prose)
        if match.group(1) not in GENERIC_UPPERCASE
        and _is_entity_candidate(match.group(1))
    )
    violations.update(
        match.group(1).strip()
        for match in STANDALONE_TITLECASE_NAME.finditer(prose)
        if _is_entity_candidate(match.group(1))
    )
    for pattern in (
        ENTITY_ASSIGNMENT,
        ENTITY_APPOSITIVE,
        ENTITY_RELATION,
        ENTITY_SUBJECT,
        ENTITY_POSSESSIVE_SUBJECT,
        ENTITY_POSSESSIVE_SOURCE,
        ENTITY_REVERSE_ASSIGNMENT,
        ENTITY_SELECTION,
        ENTITY_PASSIVE_SELECTION,
        ENTITY_RESULT_ROLE,
        ENTITY_SOURCE_ATTRIBUTION,
        ENTITY_CAPACITY_AT,
        ENTITY_DASH_ASSIGNMENT,
        ENTITY_PARENTHETICAL_ROLE,
        ENTITY_STANDOUT_ROLE,
        ENTITY_POISED_OUTCOME,
        ENTITY_BENCHMARK_SUBJECT,
        ENTITY_ATTRIBUTION,
        ENTITY_CONTEXTUAL_SOURCE,
        ENTITY_CONTEXTUAL_DEPENDENCY,
        ENTITY_INDEX_NAMING,
        ENTITY_NOMINAL_SELECTION,
        ENTITY_ROLE_FILL,
        ENTITY_CONTEXTUAL_RENT_ROUTE,
        ENTITY_FRONTED_SOURCE,
        ENTITY_COMPANY_LABEL,
        ENTITY_CONTEXTUAL_POSSESSIVE,
        ENTITY_CONTEXTUAL_DASH,
        ENTITY_CONTEXTUAL_PARENTHETICAL,
    ):
        violations.update(
            match.group("name").strip()
            for match in pattern.finditer(prose)
            if _is_entity_candidate(match.group("name"))
        )
    violations.update(_semantic_entity_slots(prose))
    violations.update(
        match.group("name").strip()
        for match in CJK_BENCHMARK_COMPARISON.finditer(prose)
    )

    return sorted(violations, key=str.casefold)
