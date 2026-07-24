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
        "process",
        "span",
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
        "payload",
        "payloads",
        "record",
        "records",
        "trail",
        "trails",
        "wrapper",
        "wrappers",
    }
)
PRIVATE_VALUE_MARKER = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:chat|conversation|dialog|interaction|"
    r"sess(?:ion)?|thread|turn)"
    r"(?:[_:-](?:id|live|prod|session|synthetic|[a-z0-9]{8,}))"
)
PRIVATE_UUID_CONTEXT_KEYS = FORBIDDEN_PRIVATE_METADATA_KEYS | frozenset(
    {
        "receipt",
        "runreceipt",
    }
)
PRIVATE_TEXT_IDENTIFIER = re.compile(
    rb"""(?ix)
    \b(?:
        session(?:[_\x20-]?(?:id|identifier|info|metadata|state))?
        | execution[_\x20-]?session(?:[_\x20-]?metadata)?
        | model[_\x20-]?session
        | run[_\x20-]?session
        | conversation[_\x20-]?id
        | thread[_\x20-]?id
        | chat[_\x20-]?id
        | turn[_\x20-]?id
        | executor[_\x20-]?receipt
        | execution[_\x20-]?(?:context|receipt|record)
        | agent[_\x20-]?run
    )
    [\x20\t]*[:=][\x20\t]*["']?
    [0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-
    [89ab][0-9a-f]{3}-[0-9a-f]{12}
    \b
    """
)


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


def is_stable_public_request_reference(
    tokens: frozenset[str],
    value: object,
) -> bool:
    """Allow an explicitly public request reference, never a private receipt."""

    return (
        {"public", "request"} <= tokens
        and bool(tokens & {"ref", "reference"})
        and not (
            tokens
            & (
                COMMUNICATION_TOKENS
                | RUNTIME_TOKENS
                | OPAQUE_RUNTIME_ACTIVITY_TOKENS
                | (PRIVATE_DETAIL_TOKENS - {"ref", "reference"})
            )
        )
        and is_stable_public_logical_identifier(value)
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
    if (
        tokens & {"byte", "bytes", "code", "count"}
        and isinstance(child, (int, float))
        and not isinstance(child, bool)
    ):
        return None
    if is_stable_public_request_reference(tokens, child):
        return None
    if compact in FORBIDDEN_PRIVATE_METADATA_KEYS:
        return "explicit private metadata key"
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
    if is_stable_public_request_reference(combined, child):
        return None
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
                if root_tokens:
                    next_ancestor_tokens = ancestor_tokens | root_tokens
                elif is_neutral_context_container(key, child):
                    next_ancestor_tokens = ancestor_tokens
                else:
                    next_ancestor_tokens = frozenset()
                walk(
                    child,
                    f"{location}.{key}",
                    private_identifier_context
                    or key_implies_private_identifier_context(key),
                    next_ancestor_tokens,
                )
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(
                    child,
                    f"{location}[{index}]",
                    private_identifier_context,
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
    if PRIVATE_TEXT_IDENTIFIER.search(data):
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
    stock_root = repo_root / "Stock_Skill"
    scope = [repo_root / "AGENTS.md", repo_root / "README.md"]
    if stock_root.is_symlink() or not stock_root.is_dir():
        state.errors.append("Stock_Skill: root must be a non-symlink directory")
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


def main() -> int:
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
