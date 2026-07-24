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
CJK_BENCHMARK_COMPARISON = re.compile(
    r"(?:与|以|对照|相较于)[ \t]*"
    r"(?P<name>[\u3400-\u9fff]{2,24}"
    r"(?:[0-9]{1,6}[\u3400-\u9fff]{0,12})?(?:指数|基准))"
    r"[ \t]*(?:进行[ \t]*)?(?:比较|对比|衡量|为参照|为基准)"
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
        "candidate",
        "can",
        "cited",
        "could",
        "committed",
        "compatible",
        "considered",
        "constrained",
        "contracted",
        "contract",
        "current",
        "currently",
        "data",
        "entity",
        "eventual",
        "fragile",
        "filing",
        "formal",
        "chosen",
        "funded",
        "future",
        "generic",
        "hyperscale",
        "identified",
        "identity",
        "in",
        "industry",
        "interim",
        "liquid",
        "later",
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
        "content",
        "transformer",
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
        "security",
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
        "has",
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
        "enrich",
        "enriches",
        "favor",
        "favors",
        "favour",
        "favours",
        "identify",
        "identifies",
        "prefer",
        "preferred",
        "prefers",
        "reference",
        "referenced",
        "references",
        "select",
        "selects",
        "underwrite",
        "underwrites",
    }
)
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
    "settle": frozenset({"at", "with"}),
    "settled": frozenset({"at", "with"}),
    "settles": frozenset({"at", "with"}),
    "track": frozenset({"against", "to", "with"}),
    "tracked": frozenset({"against", "to", "with"}),
    "tracks": frozenset({"against", "to", "with"}),
    "transfer": frozenset({"into", "through", "to"}),
    "transferred": frozenset({"into", "through", "to"}),
    "transfers": frozenset({"into", "through", "to"}),
}
SEMANTIC_WORD = re.compile(r"[^\W_](?:[^\W_]|[&'’.-])*|[:;,—–]")
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
ROLE_NEUTRAL_CANDIDATE_PREFIX = re.compile(
    r"^(?:"
    r"(?:a|an|the)[ \t]+(?:broad|generic|liquid)\b|"
    r"(?:a|an)[ \t]+independently[ \t]+(?:opened|verified)\b|"
    r"(?:broad|generic|liquid)(?:[ \t]+(?:and|or)[ \t]+"
    r"(?:broad|generic|global|liquid))*\b|"
    r"(?:whichever|whoever|whatever)\b|"
    r"(?:will[ \t]+|would[ \t]+|may[ \t]+|might[ \t]+)?"
    r"(?:be[ \t]+)?(?:assigned|chosen|determined|identified|introduced|"
    r"named|selected|verified)\b|"
    r"(?:intentionally[ \t]+)?blank\b|"
    r"(?:nominally[ \t]+unknown|null[ \t]+for[ \t]+now|"
    r"shown[ \t]+here|under[ \t]+review|undecided|unspecified)\b|"
    r"required\b|"
    r"identity[ \t]+withheld\b|"
    r"(?:currently[ \t]+)?known\b|"
    r"(?:nevertheless[ \t]+)?null\b|"
    r"not(?:[ \t]+yet)?[ \t]+(?:assigned|determined|identified|known|"
    r"named|selected)\b|"
    r"(?:still[ \t]+)?(?:unknown|uncertain|undetermined|unidentified|"
    r"unnamed|unassigned)\b|"
    r"outside\b|one[ \t]+of\b|subject[ \t]+to\b"
    r")"
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
    if re.match(r"^(?:A|An|The)[ \t]+[a-z]", raw):
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


def _semantic_entity_slots(text: str) -> Iterable[str]:
    """Yield names occupying selection, role, and rent-capture semantic slots."""

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
                candidate = _candidate_from_tokens(tokens, copula_index + 1)
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
                    clause_start = (
                        max(
                            (
                                boundary_index
                                for boundary_index in range(index)
                                if lowered[boundary_index]
                                in CLAUSE_BOUNDARY_TOKENS
                            ),
                            default=-1,
                        )
                        + 1
                    )
                    candidate = _candidate_from_tokens(
                        tokens, clause_start, index
                    )
                    if _is_entity_candidate(candidate):
                        yield candidate
            if token in DIRECT_OBJECT_VERBS:
                candidate = _candidate_from_tokens(tokens, index + 1)
                if _is_entity_candidate(candidate):
                    yield candidate
            required_prepositions = PREPOSITIONAL_OBJECT_VERBS.get(token)
            if required_prepositions is None:
                continue
            for prep_index in range(index + 1, min(index + 6, len(tokens))):
                if lowered[prep_index] in required_prepositions:
                    candidate = _candidate_from_tokens(tokens, prep_index + 1)
                    if _is_entity_candidate(candidate):
                        yield candidate
                    break

        if ":" in tokens:
            colon_index = tokens.index(":")
            label_words = set(lowered[:colon_index])
            if label_words & SEMANTIC_ROLE_HEADS:
                candidate = _candidate_from_tokens(tokens, colon_index + 1)
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
