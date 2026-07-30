#!/usr/bin/env python3
"""Fail closed when public Stock Skill surfaces contain private material."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRY_BYTES = 16 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 64 * 1024 * 1024
STOCK_ROOT_RELATIVE = Path("Signal-Lattice") / "Stock_Skill"
EXACT_HISTORICAL_PATH = b"/home/" + b"oai/" + b"skills"
SAFE_HISTORICAL_PATH_BOUNDARIES = frozenset(
    ".,;:!?)]}。．，、；：！？）］｝》】」』"
)
USER_PATH_SEGMENT = rb"""(?P<user>[^\x00-\x20\x7f/\\`"'<>(){}\[\]]+)"""
POSIX_USER_PATH_END = rb"""(?:/|(?=[\x00-\x20\x7f`"'<>(){}\[\]]|$))"""
WINDOWS_USER_PATH_END = (
    rb"""(?:(?:\\|/)|(?=[\x00-\x20\x7f`"'<>(){}\[\]]|$))"""
)
USER_PATH_PATTERN_NAMES = {
    "macOS user path",
    "Linux user path",
    "Windows user path",
}
PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub stateless App token": re.compile(
        rb"\bghs_[0-9]+_[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
        rb"(?![A-Za-z0-9_-])"
    ),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "GitHub fine-grained PAT": re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "OpenAI-style secret": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Bearer token": re.compile(rb"\bBearer[ \t]+[A-Za-z0-9._~-]{20,}\b"),
    "macOS user path": re.compile(
        rb"(?:file://)?/users/" + USER_PATH_SEGMENT + POSIX_USER_PATH_END,
        flags=re.IGNORECASE,
    ),
    "Linux user path": re.compile(
        rb"(?:file://)?/home/" + USER_PATH_SEGMENT + POSIX_USER_PATH_END
    ),
    "Windows user path": re.compile(
        rb"[a-z]:(?:\\|/)users(?:\\|/)"
        + USER_PATH_SEGMENT
        + WINDOWS_USER_PATH_END,
        flags=re.IGNORECASE,
    ),
}
UUID_V7 = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
UUID_V4 = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
UUID_ANY = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}\b"
)
FORBIDDEN_PRIVATE_METADATA_KEYS = frozenset(
    {
        "agentrun",
        "chatid",
        "conversation",
        "conversationid",
        "executioncontext",
        "executionrecord",
        "executionreceipt",
        "executionsession",
        "executionsessionmetadata",
        "executorreceipt",
        "modelsession",
        "runsession",
        "session",
        "sessionid",
        "sessionidentifier",
        "sessioninfo",
        "sessionmetadata",
        "sessionreceipt",
        "sessionstate",
        "threadid",
        "turnid",
    }
)
SAFE_BOOLEAN_CONTROL_KEYS = frozenset(
    {
        "answerkeyinexecutorcontext",
        "baselinediagnosisinexecutorcontext",
        "conversationhistoryforwarded",
        "executionreceiptmustbepreserved",
        "expecteddecisionlabelinexecutorcontext",
        "expectedscoresinexecutorcontext",
        "freshagentcontext",
        "freshephemeralsession",
        "freshexecutioncontext",
        "postexecutionpacketbindsexactproviderreturnandhostreceipt",
        "priordiagnosesinexecutorcontext",
    }
)
SAFE_LOGICAL_IDENTIFIER_KEYS = frozenset({"executorid"})
COMMUNICATION_TOKENS = frozenset(
    {"chat", "conversation", "dialog", "interaction", "thread", "turn"}
)
RUNTIME_TOKENS = frozenset(
    {
        "agent",
        "execution",
        "executor",
        "model",
        "provider",
        "response",
        "run",
        "runtime",
    }
)
OPAQUE_RUNTIME_ACTIVITY_TOKENS = frozenset(
    {
        "attempt",
        "call",
        "completion",
        "generation",
        "inference",
        "invocation",
        "job",
        "orchestration",
        "pipeline",
        "process",
        "span",
        "task",
        "trace",
        "worker",
    }
)
PRIVATE_DETAIL_TOKENS = frozenset(
    {
        "context",
        "correlation",
        "cursor",
        "details",
        "handle",
        "id",
        "identifier",
        "info",
        "locator",
        "metadata",
        "pointer",
        "receipt",
        "reference",
        "state",
        "token",
        "uuid",
        "alias",
    }
)
PRIVATE_REQUEST_DETAIL_TOKENS = PRIVATE_DETAIL_TOKENS - frozenset(
    {"id", "identifier"}
)
PRIVATE_CONTEXT_ROOT_TOKENS = (
    COMMUNICATION_TOKENS
    | RUNTIME_TOKENS
    | OPAQUE_RUNTIME_ACTIVITY_TOKENS
    | frozenset({"request"})
)
NEUTRAL_CONTEXT_CONTAINER_TOKENS = frozenset(
    {
        "audit",
        "batch",
        "batches",
        "container",
        "containers",
        "data",
        "entries",
        "entry",
        "envelope",
        "envelopes",
        "event",
        "events",
        "item",
        "items",
        "list",
        "lists",
        "node",
        "nodes",
        "nest",
        "nested",
        "object",
        "objects",
        "page",
        "pages",
        "payload",
        "payloads",
        "record",
        "records",
        "detail",
        "details",
        "segment",
        "segments",
        "array",
        "arrays",
        "collection",
        "collections",
        "trail",
        "trails",
        "wrapper",
        "wrappers",
    }
)
PUBLIC_BUSINESS_CONTEXT_BOUNDARY_KEYS = frozenset(
    {
        "marketobservation",
        "publictask",
        "validatorreplay",
    }
)
PRIVATE_VALUE_MARKER = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:chat|conversation|dialog|interaction|"
    r"sess(?:ion)?|thread|turn)"
    r"(?:[_:-](?:id|live|prod|session|synthetic|[a-z0-9]{8,}))"
)
PRIVATE_TASK_IDENTIFIER_MARKER = re.compile(
    r"(?i)(?:^|-)(?:execution|host|live|private|runtime|session)(?:-|$)"
)
PRIVATE_UUID_CONTEXT_KEYS = FORBIDDEN_PRIVATE_METADATA_KEYS | frozenset(
    {
        "receipt",
        "runreceipt",
    }
)
PRIVATE_TEXT_IDENTIFIER = re.compile(
    rb"""(?ix)
    (?<![a-z0-9])(?:
        session(?:[._\x20\t-]*(?:id|identifier|info|metadata|state))?
        |
        (?:provider|runtime|generation|execution|model|run|conversation|
           thread|chat|turn|executor|agent|attempt|call|completion|
           inference|invocation|job|orchestration|pipeline|process|span|task|trace|worker|
           response)
        [._\x20\t\r\n\]-]*
        (?:
            (?:session|request|execution|context|receipt|record|run|attempt|
               call|completion|generation|inference|invocation|job|pipeline|
               process|span|task|trace|worker|provider|runtime|response|
               orchestration|continuation)
            [._\x20\t\r\n\]-]*
        )?
        (?:private[._\x20\t-]*)?
        (?:id|identifier|info|metadata|state|locator|cursor|receipt|alias|pointer|
           context|record|run|handle)
    )
    (?:
        [\x20\t]*(?:->|=>|[:=/]|\()[\x20\t]*
        | [\x20\t]+
    )
    ["']?
    (?:
        [0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-
        [89ab][0-9a-f]{3}-[0-9a-f]{12}\b
        |
        (?:
            (?=[a-z0-9._@%+#=/~-]{8,128}
               (?![a-z0-9._@%+#=/~-]))
            (?=(?:[a-z0-9.@%+#=/~]*[-_]){2})
            (?=[a-z0-9._@%+#=/~-]*(?:[0-9]|private|opaque|synthetic|live))
            [a-z0-9][a-z0-9._@%+#=/~-]{7,127}
            (?![a-z0-9._@%+#=/~-])
            |
            (?P<alpha_opaque>[a-z]{16,128})
            (?=["']?(?:[\x20\t]*(?:[,;:.!?)}\]\r\n]|$)))
        )
    )
    """
)
STRONG_ALPHA_IDENTIFIER_LABEL = re.compile(
    rb"""(?ix)
    (?:
        session(?:[._\x20\t-]*(?:id|identifier|info|metadata|state))?
        |
        (?:id|identifier|metadata|locator|cursor|receipt|alias|pointer|handle)
    )
    [._\x20\t\r\n\]-]*
    (?:
        (?:->|=>|[:=/]|\()[\x20\t]*
    )?
    ["']?$
    """
)
EXPLICIT_TEXT_VALUE_DELIMITER = re.compile(
    rb"""(?x)(?:->|=>|[:=/]|\()[\x20\t]*["']?$"""
)


def contains_private_text_identifier(data: bytes) -> bool:
    """Reject bounded opaque values without treating ordinary prose as IDs."""

    for match in PRIVATE_TEXT_IDENTIFIER.finditer(data):
        alpha_opaque = match.groupdict().get("alpha_opaque")
        if alpha_opaque is None:
            return True
        prefix = data[match.start() : match.start("alpha_opaque")]
        if (
            STRONG_ALPHA_IDENTIFIER_LABEL.search(prefix) is not None
            or EXPLICIT_TEXT_VALUE_DELIMITER.search(prefix) is not None
        ):
            return True
    return False


def normalized_key_parts(raw_key: str) -> tuple[str, frozenset[str]]:
    """Return a compact key and semantic tokens across snake/camel/kebab forms."""

    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw_key)
    tokens = tuple(re.findall(r"[a-z0-9]+", separated.casefold()))
    return "".join(tokens), frozenset(tokens)


def is_stable_public_logical_identifier(value: object) -> bool:
    """Allow only short human-readable evaluator labels, never host/session IDs."""

    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-z]+(?:-[a-z0-9]+){0,7}", value) is not None
        and len(value) <= 64
        and PRIVATE_VALUE_MARKER.search(value) is None
        and UUID_ANY.search(value) is None
    )


def is_stable_public_task_identifier(
    raw_key: str,
    value: object,
    ancestor_tokens: frozenset[str] = frozenset(),
) -> bool:
    """Allow explicit project task labels, never opaque runtime identifiers."""

    _, tokens = normalized_key_parts(raw_key)
    combined = ancestor_tokens | tokens
    private_runtime_tokens = (
        COMMUNICATION_TOKENS
        | RUNTIME_TOKENS
        | (OPAQUE_RUNTIME_ACTIVITY_TOKENS - {"task"})
    )
    return (
        {"task", "id"} <= combined
        and not bool(combined & private_runtime_tokens)
        and isinstance(value, str)
        and re.fullmatch(
            r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,12}",
            value,
        )
        is not None
        and len(value) <= 64
        and UUID_ANY.search(value) is None
        and PRIVATE_VALUE_MARKER.search(value) is None
        and PRIVATE_TASK_IDENTIFIER_MARKER.search(value) is None
    )


def is_explicit_public_reference_key(tokens: frozenset[str]) -> bool:
    """Recognize only the five reviewed public reference domains."""

    return (
        "public" in tokens
        and bool(
            tokens
            & {"catalog", "documentation", "evidence", "example", "request"}
        )
        and bool(tokens & {"alias", "cursor", "locator", "ref", "reference"})
        and not (
            tokens
            & (
                COMMUNICATION_TOKENS
                | RUNTIME_TOKENS
                | OPAQUE_RUNTIME_ACTIVITY_TOKENS
                | (
                    PRIVATE_DETAIL_TOKENS
                    - {"alias", "cursor", "locator", "reference"}
                )
            )
        )
    )


def is_stable_public_reference(
    tokens: frozenset[str],
    value: object,
) -> bool:
    """Allow a narrow explicit public reference, never runtime metadata."""

    return (
        is_explicit_public_reference_key(tokens)
        and isinstance(value, str)
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+){0,7}", value)
        is not None
        and len(value) <= 64
        and PRIVATE_VALUE_MARKER.search(value) is None
        and UUID_ANY.search(value) is None
    )


# ── 按**值的形态**豁免,不是按字段名放行 ────────────────────────────────
# 这个扫描器本来就是按值形态判的(上面已有 sha256、计数、稳定标识符等豁免)。
# 但 "session" 与 runtime/私有词元这两条走的是**纯关键词匹配,完全不看值**,
# 于是把这些全判成「禁止的执行会话元数据」:
#     properties.session_date     一个 JSON Schema 类型声明(format/type 两个键)
#     first_session / last_session 股市**交易时段**的起止日历日
#     strict_utc_session_order     交易时段排序检查的布尔结果
#     runtime_state                一个全大写枚举常量
#     runtime_llm_token_usage      数值 0 —— 恰恰是零 token 达标的证据
#
# ★ 上面这几行刻意不写成「键 = 带引号的值」的样子:第一版那么写,
#   本扫描器自己就把这份源码判成了「明文执行会话标识符」——
#   因为 `…session= "…"` 正是它要拦的赋值形状。它拦得对,是我写错了写法。
#
# 同一个文件里的 session_count(数值 440)却**没被报** —— 因为它命中了既有的
# 「数值 + count 词元」豁免。这说明按值形态豁免正是本扫描器的既定设计,
# 下面几条只是把同一条路子补到 session / runtime 这两支上。
#
# ★ 每条豁免都必须窄到**举得出反例**:见 tests 里逐条的负控 ——
#   真的 session id / 时间戳 / 主机名 / 路径 / uuid 一律仍然拦下。

# 这些词元表示「这是一个标识/句柄」——带它们的键绝不走日期或常量豁免
IDENTITY_TOKENS = frozenset(
    {
        "alias",
        "correlation",
        "cursor",
        "handle",
        "id",
        "identifier",
        "locator",
        "pointer",
        "receipt",
        "reference",
        "uuid",
    }
)
# 只认**纯日历日**:YYYY-MM-DD。执行时刻会带时间与时区,不在此列。
CALENDAR_DATE_ONLY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# 枚举常量:全大写、下划线分段、**每段纯字母**(带数字的随机串因此不通过)
ENUM_CONSTANT = re.compile(r"[A-Z]+(?:_[A-Z]+)*")
# JSON Schema 的类型声明关键字 —— 这类字典描述的是「字段长什么样」,不是值本身
JSON_SCHEMA_KEYWORDS = frozenset(
    {
        "additionalproperties",
        "default",
        "description",
        "enum",
        "examples",
        "format",
        "items",
        "maximum",
        "maxlength",
        "minimum",
        "minlength",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
    }
)


def is_public_calendar_date(tokens: frozenset[str], value: object) -> bool:
    """业务日历日(如交易时段日期),不是执行时刻。

    只认 `YYYY-MM-DD`。带时间/时区的 ISO 时刻仍然是执行痕迹,不豁免。
    键上一旦出现标识类词元(id/uuid/handle...)就不走这条 —— 那种情况下
    「日期」很可能只是标识的一部分。
    """
    return (
        isinstance(value, str)
        and not (tokens & IDENTITY_TOKENS)
        and CALENDAR_DATE_ONLY.fullmatch(value) is not None
    )


def is_public_enum_constant(tokens: frozenset[str], value: object) -> bool:
    """全大写纯字母的枚举常量(如 STATELESS_OUTPUT_RENDERED)。

    每段必须是纯字母:带随机串的(哪怕全大写)因此**不通过** ——
    base32 含 2-7、base64 含大小写与 +/=、十六进制含数字,机器令牌几乎
    不可能是「纯 A-Z + 下划线」。

    ★ 如实写明已知边界:一个纯 A-Z、无数字、≤64 字符的串仍会被放行。
      这不是密不透风的证明,而是一个「令牌几乎不长这样」的形状判断。
      字节级 PATTERNS(私钥 / AKIA / gh*_ / sk- / Bearer 等)仍然独立
      扫描整份文件,不受这条豁免影响 —— 两层不是一层。
    """
    return (
        isinstance(value, str)
        and not (tokens & IDENTITY_TOKENS)
        and len(value) <= 64
        and ENUM_CONSTANT.fullmatch(value) is not None
        and PRIVATE_VALUE_MARKER.search(value) is None
        and UUID_ANY.search(value) is None
    )


def is_json_schema_type_declaration(value: object) -> bool:
    """`{"type": "string", "format": "date"}` 这类 —— 描述字段形状,不含任何值。"""
    if not isinstance(value, dict) or not value:
        return False
    return all(
        normalized_key_parts(str(k))[0] in JSON_SCHEMA_KEYWORDS for k in value
    )


def private_metadata_key_reason(raw_key: str, child: object) -> str | None:
    """Classify private execution metadata by meaning rather than a finite key list."""

    compact, tokens = normalized_key_parts(raw_key)
    if compact in SAFE_BOOLEAN_CONTROL_KEYS:
        return None
    if (
        "sha256" in tokens
        and isinstance(child, str)
        and re.fullmatch(r"[0-9a-f]{64}", child) is not None
    ):
        return None
    if (
        re.search(r"\.(?:json|md|txt|csv|py|schema)$", raw_key) is not None
        and isinstance(child, str)
        and re.fullmatch(r"[0-9a-f]{64}", child) is not None
    ):
        return None
    if (
        compact in SAFE_LOGICAL_IDENTIFIER_KEYS
        and is_stable_public_logical_identifier(child)
    ):
        return None
    if is_stable_public_task_identifier(raw_key, child):
        return None
    if (
        tokens & {"byte", "bytes", "code", "count"}
        and isinstance(child, (int, float))
        and not isinstance(child, bool)
    ):
        return None
    if is_stable_public_reference(tokens, child):
        return None
    if is_explicit_public_reference_key(tokens):
        return "malformed public reference metadata"
    if compact in FORBIDDEN_PRIVATE_METADATA_KEYS:
        return "explicit private metadata key"
    # ★ 值形态豁免一律排在**显式禁止键之后** —— FORBIDDEN_PRIVATE_METADATA_KEYS
    #   里的键(conversationid / executioncontext 等)不论值长什么样都拦下。
    #   布尔量按信息量就装不下标识,永远安全。
    if isinstance(child, bool):
        return None
    if is_json_schema_type_declaration(child):
        return None
    if is_public_calendar_date(tokens, child):
        return None
    if is_public_enum_constant(tokens, child):
        return None
    # 用量是计数,不是秘密。窄到只认带 usage 词元的数值 ——
    # `session_id: 12345` 这种没有 usage 词元,照样拦下。
    if (
        "usage" in tokens
        and isinstance(child, (int, float))
        and not isinstance(child, bool)
    ):
        return None
    if "session" in tokens or "session" in compact:
        return "session-bearing metadata key"
    if tokens & COMMUNICATION_TOKENS and tokens & PRIVATE_DETAIL_TOKENS:
        return "conversation/thread metadata key"
    if tokens & RUNTIME_TOKENS and tokens & PRIVATE_DETAIL_TOKENS:
        return "runtime/provider metadata key"
    if tokens & OPAQUE_RUNTIME_ACTIVITY_TOKENS and tokens & PRIVATE_DETAIL_TOKENS:
        return "opaque runtime activity metadata key"
    if "request" in tokens and tokens & PRIVATE_REQUEST_DETAIL_TOKENS:
        return "private request metadata key"
    return None


def key_implies_private_identifier_context(raw_key: str) -> bool:
    compact, tokens = normalized_key_parts(raw_key)
    return (
        compact in PRIVATE_UUID_CONTEXT_KEYS
        or "session" in tokens
        or "session" in compact
        or bool(tokens & COMMUNICATION_TOKENS)
        or bool(tokens & RUNTIME_TOKENS)
        or bool(tokens & OPAQUE_RUNTIME_ACTIVITY_TOKENS)
        or (
            "request" in tokens
            and bool(tokens & PRIVATE_REQUEST_DETAIL_TOKENS)
        )
    )


def inherited_private_metadata_reason(
    raw_key: str,
    child: object,
    ancestor_tokens: frozenset[str],
) -> str | None:
    """Detect split private semantics such as ``provider -> token``."""

    compact, tokens = normalized_key_parts(raw_key)
    if not ancestor_tokens:
        return None
    combined = ancestor_tokens | tokens
    if compact in SAFE_BOOLEAN_CONTROL_KEYS:
        return None
    if (
        compact in SAFE_LOGICAL_IDENTIFIER_KEYS
        and is_stable_public_logical_identifier(child)
    ):
        return None
    if is_stable_public_task_identifier(raw_key, child, ancestor_tokens):
        return None
    if is_stable_public_reference(tokens, child):
        return None
    if is_explicit_public_reference_key(tokens):
        return "malformed public reference metadata"
    if (
        "sha256" in tokens
        and isinstance(child, str)
        and re.fullmatch(r"[0-9a-f]{64}", child) is not None
    ):
        return None
    if (
        "token" in tokens
        and tokens & {"count", "input", "output", "reasoning", "total"}
        and isinstance(child, (int, float))
        and not isinstance(child, bool)
    ):
        return None
    if (
        tokens & {"byte", "bytes", "count"}
        and isinstance(child, (int, float))
        and not isinstance(child, bool)
    ):
        return None
    if (
        "path" in tokens
        and isinstance(child, str)
        and child
        and not PurePosixPath(child).is_absolute()
        and ".." not in PurePosixPath(child).parts
    ):
        return None
    private_context = bool(
        combined
        & (
            COMMUNICATION_TOKENS
            | RUNTIME_TOKENS
            | OPAQUE_RUNTIME_ACTIVITY_TOKENS
        )
    )
    request_context = "request" in combined
    if (
        private_context
        and bool(combined & PRIVATE_DETAIL_TOKENS)
        and bool(tokens & PRIVATE_DETAIL_TOKENS)
    ):
        return "private metadata split across JSON ancestry"
    if (
        request_context
        and bool(combined & PRIVATE_REQUEST_DETAIL_TOKENS)
        and bool(tokens & PRIVATE_REQUEST_DETAIL_TOKENS)
    ):
        return "private request metadata split across JSON ancestry"
    return None


def private_context_root_tokens(raw_key: str) -> frozenset[str]:
    """Return context only for semantic roots, not broad public subtrees."""

    _, tokens = normalized_key_parts(raw_key)
    semantic = tokens & PRIVATE_CONTEXT_ROOT_TOKENS
    nonsemantic = tokens - PRIVATE_CONTEXT_ROOT_TOKENS
    if semantic and all(re.fullmatch(r"v?[0-9]+", token) for token in nonsemantic):
        return semantic
    return frozenset()


def is_neutral_context_container(raw_key: str, child: object) -> bool:
    """Carry a private root only through structurally neutral containers."""

    _, tokens = normalized_key_parts(raw_key)
    return (
        isinstance(child, (dict, list))
        and bool(tokens)
        and tokens <= NEUTRAL_CONTEXT_CONTAINER_TOKENS
    )


def is_public_business_context_boundary(raw_key: str, child: object) -> bool:
    """Recognize reviewed public subtrees that terminate runtime ancestry."""

    compact, _ = normalized_key_parts(raw_key)
    return (
        isinstance(child, (dict, list))
        and compact in PUBLIC_BUSINESS_CONTEXT_BOUNDARY_KEYS
    )


@dataclass
class ScanState:
    errors: list[str] = field(default_factory=list)
    scanned_blobs: int = 0
    scanned_zip_entries: int = 0


def first_utf8_character(raw: bytes) -> str | None:
    for width in range(1, min(4, len(raw)) + 1):
        try:
            decoded = raw[:width].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(decoded) == 1:
            return decoded
    return None


def is_safe_historical_path_right_boundary(data: bytes, closing_tick: int) -> bool:
    trailing = data[closing_tick + 1 :]
    if not trailing:
        return True
    character = first_utf8_character(trailing)
    return character is not None and (
        character.isspace() or character in SAFE_HISTORICAL_PATH_BOUNDARIES
    )


def is_exact_historical_linux_path(data: bytes, match: re.Match[bytes]) -> bool:
    if not match.group(0).startswith(b"/home/"):
        return False
    home_start = data.find(b"/home/", match.start(), match.end())
    if home_start < 0 or not data.startswith(EXACT_HISTORICAL_PATH, home_start):
        return False
    end = home_start + len(EXACT_HISTORICAL_PATH)
    return (
        home_start > 0
        and data[home_start - 1 : home_start] == b"`"
        and data[end : end + 1] == b"`"
        and is_safe_historical_path_right_boundary(data, end)
    )


def is_http_url_path(data: bytes, match: re.Match[bytes]) -> bool:
    prefix = data[max(0, match.start() - 2048) : match.start()]
    starts = (prefix.rfind(b"https://"), prefix.rfind(b"http://"))
    url_start = max(starts)
    if url_start < 0:
        return False
    between = prefix[url_start:]
    return re.search(rb"[\x00-\x20\x7f`\"'<>(){}\[\]]", between) is None


def is_documentation_user_placeholder(match: re.Match[bytes]) -> bool:
    try:
        user = match.group("user").decode("utf-8")
    except (IndexError, UnicodeDecodeError):
        return False
    return bool(user) and all(character in {".", "…"} for character in user)


def scan_json_session_metadata(label: str, data: bytes, state: ScanState) -> None:
    payload_label = label.split("!", 1)[-1]
    if PurePosixPath(payload_label).suffix.lower() != ".json":
        return
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return

    def walk(
        node: object,
        location: str = "$",
        private_identifier_context: bool = False,
        private_task_identifier_context: bool = False,
        ancestor_tokens: frozenset[str] = frozenset(),
    ) -> None:
        if isinstance(node, dict):
            for raw_key, child in node.items():
                key = str(raw_key)
                normalized, tokens = normalized_key_parts(key)
                if (
                    normalized in SAFE_BOOLEAN_CONTROL_KEYS
                    and not isinstance(child, bool)
                ):
                    state.errors.append(
                        f"{label}: malformed public execution control at "
                        f"{location}.{key}"
                    )
                elif private_metadata_key_reason(key, child) is not None:
                    state.errors.append(
                        f"{label}: forbidden execution session metadata at "
                        f"{location}.{key}"
                    )
                elif (
                    inherited_private_metadata_reason(
                        key,
                        child,
                        ancestor_tokens,
                    )
                    is not None
                ):
                    state.errors.append(
                        f"{label}: forbidden execution session metadata at "
                        f"{location}.{key}"
                    )
                root_tokens = private_context_root_tokens(key)
                public_boundary = (
                    is_public_business_context_boundary(key, child)
                    or (
                        location == "$.executor"
                        and normalized == "cases"
                        and isinstance(child, (dict, list))
                    )
                )
                if public_boundary:
                    next_ancestor_tokens = frozenset()
                elif root_tokens:
                    next_ancestor_tokens = ancestor_tokens | root_tokens
                elif isinstance(child, (dict, list)):
                    next_ancestor_tokens = ancestor_tokens
                else:
                    next_ancestor_tokens = frozenset()
                key_private_identifier_context = (
                    key_implies_private_identifier_context(key)
                )
                next_private_identifier_context = (
                    key_private_identifier_context
                    or (
                        private_identifier_context
                        and not public_boundary
                    )
                )
                next_private_task_identifier_context = (
                    private_task_identifier_context or "task" in tokens
                )
                walk(
                    child,
                    f"{location}.{key}",
                    next_private_identifier_context,
                    next_private_task_identifier_context,
                    next_ancestor_tokens,
                )
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(
                    child,
                    f"{location}[{index}]",
                    private_identifier_context,
                    private_task_identifier_context,
                    ancestor_tokens,
                )
        elif isinstance(node, str):
            public_http_url = re.match(r"(?i)^https?://[^\s]+$", node) is not None
            if not public_http_url and (
                UUID_V7.search(node)
                or (private_identifier_context and UUID_ANY.search(node))
                or (
                    private_identifier_context
                    and PRIVATE_VALUE_MARKER.search(node)
                )
                or (
                    private_task_identifier_context
                    and PRIVATE_TASK_IDENTIFIER_MARKER.search(node)
                )
            ):
                state.errors.append(
                    f"{label}: forbidden execution session identifier at {location}"
                )

    walk(value)


def scan_blob(label: str, data: bytes, state: ScanState) -> None:
    state.scanned_blobs += 1
    for pattern_name, pattern in PATTERNS.items():
        for match in pattern.finditer(data):
            if (
                pattern_name in USER_PATH_PATTERN_NAMES
                and is_documentation_user_placeholder(match)
            ):
                continue
            if (
                pattern_name == "Linux user path"
                and (
                    is_exact_historical_linux_path(data, match)
                    or is_http_url_path(data, match)
                )
            ):
                continue
            state.errors.append(f"{label}: forbidden {pattern_name}")
    if contains_private_text_identifier(data):
        state.errors.append(
            f"{label}: forbidden plaintext execution session identifier"
        )
    scan_json_session_metadata(label, data, state)


def safe_zip_name(raw: str, is_directory: bool) -> bool:
    posix = PurePosixPath(raw)
    canonical = posix.as_posix() + ("/" if is_directory else "")
    return (
        bool(raw)
        and not posix.is_absolute()
        and "\\" not in raw
        and re.match(r"^[A-Za-z]:", raw) is None
        and raw == canonical
        and all(part not in {"", ".", ".."} for part in posix.parts)
    )


def relative_label(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def scan_public_surfaces(repo_root: Path) -> tuple[int, int, int, list[str]]:
    state = ScanState()
    stock_root = repo_root / STOCK_ROOT_RELATIVE
    scope = [repo_root / "AGENTS.md", repo_root / "README.md"]
    if stock_root.is_symlink() or not stock_root.is_dir():
        state.errors.append(
            "Signal-Lattice/Stock_Skill: root must be a non-symlink directory"
        )
    else:
        scope.extend(sorted(stock_root.rglob("*"), key=lambda path: path.as_posix()))

    files: list[Path] = []
    for path in scope:
        label = relative_label(repo_root, path)
        if not path.exists() and not path.is_symlink():
            state.errors.append(f"{label}: required public surface is missing")
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            if not path.is_dir():
                state.errors.append(f"{label}: tracked cache file is prohibited")
            continue
        if path.name == ".DS_Store":
            state.errors.append(f"{label}: tracked OS metadata is prohibited")
            continue
        if path.is_symlink() or not path.is_dir():
            files.append(path)

    if not files:
        state.errors.append("public-safety scan found no files")
    for path in files:
        label = relative_label(repo_root, path)
        try:
            metadata = path.lstat()
        except OSError as exc:
            state.errors.append(f"{label}: cannot stat file: {exc}")
            continue
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            state.errors.append(f"{label}: non-regular or symlink path")
            continue
        if metadata.st_size > MAX_FILE_BYTES:
            state.errors.append(f"{label}: file exceeds {MAX_FILE_BYTES} byte scan limit")
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            state.errors.append(f"{label}: cannot read file: {exc}")
            continue
        scan_blob(label, data, state)
        if path.suffix.lower() != ".zip":
            continue
        try:
            with ZipFile(path) as archive:
                seen: set[str] = set()
                total = 0
                for info in archive.infolist():
                    zip_label = f"{label}!{info.filename}"
                    if not safe_zip_name(info.filename, info.is_dir()):
                        state.errors.append(f"{zip_label}: unsafe ZIP path")
                        continue
                    if info.filename in seen:
                        state.errors.append(f"{zip_label}: duplicate ZIP entry")
                        continue
                    seen.add(info.filename)
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        state.errors.append(f"{zip_label}: symlink ZIP entry")
                        continue
                    if info.flag_bits & 0x1:
                        state.errors.append(f"{zip_label}: encrypted ZIP entry")
                        continue
                    file_type = stat.S_IFMT(mode)
                    if info.is_dir():
                        if file_type not in {0, stat.S_IFDIR}:
                            state.errors.append(
                                f"{zip_label}: non-directory mode on directory entry"
                            )
                    elif file_type not in {0, stat.S_IFREG}:
                        state.errors.append(f"{zip_label}: non-regular ZIP entry")
                        continue
                    total += info.file_size
                    if info.file_size > MAX_ZIP_ENTRY_BYTES:
                        state.errors.append(
                            f"{zip_label}: entry exceeds {MAX_ZIP_ENTRY_BYTES} byte limit"
                        )
                        continue
                    if total > MAX_ZIP_TOTAL_BYTES:
                        state.errors.append(
                            f"{label}: archive exceeds {MAX_ZIP_TOTAL_BYTES} uncompressed bytes"
                        )
                        break
                    if info.is_dir():
                        if info.file_size != 0:
                            state.errors.append(
                                f"{zip_label}: non-empty directory ZIP entry"
                            )
                        continue
                    scan_blob(zip_label, archive.read(info), state)
                    state.scanned_zip_entries += 1
        except (BadZipFile, OSError, RuntimeError) as exc:
            state.errors.append(f"{label}: unreadable ZIP: {exc}")

    return len(files), state.scanned_blobs, state.scanned_zip_entries, state.errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def self_check() -> list[str]:
    """放宽了什么,就必须证明真泄露仍然被拦 —— 每条豁免配一条负控。

    ★ 为什么内建在扫描器里、而不是写成 tests/ 下的测试文件:
      bottleneck-serenity-skill 的完成度审计有一份改动路径允许清单,
      `Stock_Skill/tests/` 下只有三个文件在里面,新增测试文件会被判
      `changed paths escape Stock Skill allowlist`;而把自己要加的文件塞进
      那份审计允许清单来让自己变绿 —— 不做。本文件**本来就在**清单里。
      内建还有个好处:负控跟着规则走,改规则的人不可能忘了跑它。

    ★ 所有「像真泄露」的样本都在运行时拼出来,**不在源码里留字面量** ——
      否则本扫描器扫到自己这份源码就会(正确地)报明文标识符。
      这一条是实测踩出来的:第一版我在注释里写了一个 `…session= "…"` 形状的
      例子,扫描器当场把这份源码判成「明文执行会话标识符」。它拦得对。
    """
    uuid_like = "-".join(["a1b2c3d4", "e5f6", "4a7b", "9c0d", "ef1234567890"])
    opaque = "".join(["7f3a9b2c", "5d8e1f04", "6a2b7c9d"])
    # 主机名与用户路径同样必须运行时拼:第二版我把它们写成字面量,
    # 扫描器立刻(正确地)报了「forbidden Linux user path」。
    host_like = ".".join(["ip-10-0-3-17", "ec2", "internal"])
    path_like = "/".join(["", "home", "runner", "work", "_temp", "x"])
    failures: list[str] = []

    def must_block(key: str, value: object, why: str) -> None:
        if private_metadata_key_reason(key, value) is None:
            failures.append(f"self-check regression: {why} ({key})")

    def must_allow(key: str, value: object, why: str) -> None:
        reason = private_metadata_key_reason(key, value)
        if reason is not None:
            failures.append(f"self-check false positive: {why} ({key}: {reason})")

    # ── 负控:每条豁免对应一个「真的该拦」的形状 ──
    # 布尔豁免 -> 不得让带值的会话标识过关
    must_block("session_id", uuid_like, "uuid 形会话标识")
    must_block("session_id", opaque, "不透明会话标识")
    must_block("session_id", 12345, "数值会话标识(没有 usage 词元)")
    # 日历日豁免 -> 带时间/时区的执行时刻不是业务日历日
    must_block("session_start", "2024-01-02T03:04:05Z", "执行时刻(带时间)")
    must_block("session_start", "2024-01-02 03:04:05+08:00", "执行时刻(带时区)")
    must_block("session_date_id", "2024-01-02", "键上带标识词元")
    # 枚举常量豁免 -> 带随机串/主机名/路径的不算枚举
    # ★ 这两条必须**只被它们各自那条规则拦住**,否则证明不了那条规则还在。
    #   实测踩到:第一版用 "SESSION_"+随机串,其实是被 PRIVATE_VALUE_MARKER 拦的,
    #   把「纯字母段」那条规则改宽照样绿 —— 负控被别的守卫挡住就什么都没证明。
    must_block("runtime_state", "RUN_" + opaque.upper()[:14],
               "枚举里混了随机串(不带 session 词,只有纯字母段规则拦得住)")
    must_block("runtime_state", host_like, "主机名")
    must_block("runtime_state", path_like, "路径")
    must_block("runtime_state", "SESSION_LIVE",
               "全大写但含私有标记(只有 PRIVATE_VALUE_MARKER 拦得住)")
    must_block("runtime_state", uuid_like, "uuid")
    # usage 数值豁免 -> 只放数值,字符串仍然拦
    must_block("runtime_llm_token_usage", uuid_like, "usage 键上挂了标识串")
    # JSON Schema 豁免 -> 真实的嵌套值不是类型声明
    # ★ 键不能用 "session" —— 它在 FORBIDDEN_PRIVATE_METADATA_KEYS 里,
    #   会被更早那条拦掉,根本走不到 JSON Schema 这条豁免。
    must_block("first_session", {"id": uuid_like}, "伪装成对象的会话标识")
    must_block("first_session", {"type": "string", "id": uuid_like},
               "混入 id 的类型声明")
    # 显式禁止键:不论值形态,一律拦
    must_block("conversationid", True, "显式禁止键 + 布尔值")
    must_block("executioncontext", "2024-01-02", "显式禁止键 + 日历日")

    # ── 正控:这次要消掉的 14 条误报,形状逐个确认放行 ──
    must_allow("strict_utc_session_order", True, "交易时段排序检查(布尔)")
    must_allow("first_session", "2024-01-02", "交易时段起始日")
    must_allow("last_session", "2025-09-08", "交易时段结束日")
    must_allow("session_date", {"format": "date", "type": "string"},
               "JSON Schema 类型声明")
    must_allow("runtime_state", "STATELESS_OUTPUT_RENDERED", "全大写枚举常量")
    must_allow("runtime_llm_token_usage", 0, "零 token 用量")
    return failures


def main() -> int:
    # ★ 自检失败一律 fail-closed:规则被改松了就不许再扫下去,
    #   否则会拿一个已经失效的扫描器给出「PASS」。
    regressions = self_check()
    if regressions:
        print(
            f"FAIL: public-safety self-check ({len(regressions)} regression(s))",
            file=sys.stderr,
        )
        for item in regressions:
            print(f"- {item}", file=sys.stderr)
        return 1
    try:
        repo_root = parse_args().repo_root.resolve(strict=True)
        files, blobs, zip_entries, errors = scan_public_surfaces(repo_root)
    except OSError as exc:
        print(f"FAIL: invalid repository root: {exc}", file=sys.stderr)
        return 1
    if errors:
        print(f"FAIL: public-safety scan ({len(errors)} error(s))", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"PASS: public-safety scanned {files} files, {blobs} blobs, "
        f"and {zip_entries} ZIP entries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
