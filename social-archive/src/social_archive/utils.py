from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import unicodedata
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 密钥脱敏。**这个正则改过一次，因为原来那版同时犯了两个方向相反的错。**
#
# 原版：r"(?i)(token|secret|password|cookie|authorization|session)[=: ]+[^\s,;]+"
#
#   1. **漏**。`Authorization: Bearer eyJhbGciOi….SIG` 里，关键词后面的第一段
#      是 `Bearer`——于是它把 "Bearer" 这个词遮住，**把真正的 JWT 原样留在日志里**。
#      实测：`Authorization=<已隐藏> eyJhbGciOiJIUzI1NiJ9.PAYLOAD.SIG`。
#      这个函数存在的全部理由就是防这个。
#   2. **过**。分隔符里有一个裸空格，于是中文里正常的
#      「Instagram Session 尚未配置」被吃成「Instagram Session=<已隐藏>」，
#      「缺少 Reddit OAuth token 或 username」被吃成
#      「缺少 Reddit OAuth token=<已隐藏> username」。
#      **用户最需要的那句解释，被脱敏器吃掉了。**
#      2026-08-04 生产实测就是这么发现的：修好 Instagram 的权限之后，
#      失败原因显示成 `Instagram Session=<已隐藏>`，什么也看不出来。
#
# 现在分两种写法处理：
#
#   · 显式赋值 `key=value` / `key: value` —— 一律遮到 `;` `,` 或行尾。
#     Authorization 那种「Bearer <token>」整段都在这个范围里，不会再漏。
#   · 只隔一个空格 `key value` —— **只在后面那段像密钥时才遮**：
#     长度 ≥12，或者字母数字混排。这样 `Session 尚未配置`、`token 或 username`、
#     `Authorization header missing` 都能留下，而 `password hunter2`、
#     `Authorization Bearer eyJ…` 照遮不误。
#
# 这一版在「漏」的方向上**严格强于**旧版；在「过」的方向上只放过明显是散文的部分。
_SECRET_KEY = r"(?i)(token|secret|password|passwd|cookie|authorization|session|api[_-]?key)"
_ASSIGNED = re.compile(_SECRET_KEY + r"\s*[=:]\s*[^;,\n]+")
_SPACED = re.compile(
    _SECRET_KEY + r"[ \t]+((?:bearer|basic|token)[ \t]+)?"
    r"(?=[!-~])(?:[A-Za-z0-9_.\-+/=]{12,}|[A-Za-z0-9_.\-+/=]*(?:[A-Za-z][0-9]|[0-9][A-Za-z])[A-Za-z0-9_.\-+/=]*)"
    r"[^;,\n ]*"
)
SHARED_HOST_SECRET_ROOT = Path("/opt/social-archive/runtime/secrets")
CORE_SECRET_UID_GID = 10001
SYSTEMD_CREDENTIALS_ROOT = Path("/run/credentials")


def utcnow() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:32]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonicalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅允许有效的 http/https URL")
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    query = [(k, v) for k, v in query if k.lower() not in tracking]
    clean = urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urllib.parse.urlencode(query, doseq=True), ""))
    return clean


def assert_public_http_url(value: str, resolve_dns: bool = False) -> str:
    clean = canonicalize_url(value)
    host = urllib.parse.urlsplit(clean).hostname or ""
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("拒绝本机或内网地址")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("拒绝本机或内网地址")
    except ValueError as exc:
        if "拒绝" in str(exc):
            raise
        if resolve_dns:
            for info in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(info[4][0])
                if not ip.is_global:
                    raise ValueError("DNS 解析到了本机或内网地址")
    return clean


# 单个文件名分量的字节上限。ext4/xfs/APFS 都是 255 **字节**，不是 255 个字符。
#
# 留出的余量：
#   · 调用方还要拼 `-{id 后 8 位}.md` = 12 字节
#   · atomic_write 用 mkstemp 建临时文件，名字是 `.{最终名}.{8 位随机}` ≈ +10 字节
# 180 字节给这两样留足了空间，还剩富余给别的调用方（Obsidian 路径、私有库路径）。
SLUG_BYTE_BUDGET = 180


def safe_slug(value: str, fallback: str = "item") -> str:
    """把任意标题变成一个能落地的文件名分量。

    ## 为什么按**字节**截，不按字符截

    原来是 `value[:120]`。一个 120 字的中文标题在 UTF-8 下是 **360 字节**，
    远超文件系统对单个名字分量的 255 字节上限。

    2026-08-03T17:23 生产上实测炸了：

        [Errno 36] File name too long:
        '/var/lib/social-archive/exports/markdown/douyin/.迈特威四…'

    而且后果不止丢一条：那次失败把**整个 markdown 目的地**降级成
    needs_user_action，之后每一条导出都被授权闸门挡下，界面显示的是
    「请先点击『检查连接』」——**一个太长的标题，让 79 条内容再也没导出过**，
    而给用户看的原因完全指错了方向。
    """
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-._")
    encoded = value.encode("utf-8")
    if len(encoded) > SLUG_BYTE_BUDGET:
        # 在字节边界上截，再用 errors="ignore" 丢掉被切成两半的那个字符。
        value = encoded[:SLUG_BYTE_BUDGET].decode("utf-8", errors="ignore").strip("-._")
    return (value or fallback).lower()


def atomic_write(path: Path, data: bytes, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def redact(value: str) -> str:
    value = _ASSIGNED.sub(lambda m: f"{m.group(1)}=<已隐藏>", value)
    return _SPACED.sub(lambda m: f"{m.group(1)}=<已隐藏>", value)


def approved_shared_host_secret(path: Path, *, mode: int, uid: int, gid: int) -> bool:
    """Allow only the documented non-root Docker/systemd Secret bridge.

    Docker Compose file-backed secrets preserve host ownership. Production uses
    uid/gid 10001 for the non-root Core and one dedicated host service group;
    this exception must never make arbitrary 0640 files acceptable.
    """
    try:
        under_runtime_secret_root = path.resolve().is_relative_to(SHARED_HOST_SECRET_ROOT)
    except OSError:
        return False
    return (
        under_runtime_secret_root
        and mode == 0o640
        and uid == CORE_SECRET_UID_GID
        and gid == CORE_SECRET_UID_GID
    )


def approved_systemd_credential(path: Path, *, mode: int, uid: int, gid: int) -> bool:
    """Accept only the per-unit credential directory created by systemd.

    ``LoadCredential=`` exposes a root-owned, group-readable file below the
    service's ``$CREDENTIALS_DIRECTORY``.  The enclosing /run/credentials
    namespace is isolated for the unit, so this is not equivalent to allowing
    arbitrary 0640 host files.
    """
    raw_directory = os.getenv("CREDENTIALS_DIRECTORY", "").strip()
    if not raw_directory:
        return False
    try:
        credential_directory = Path(raw_directory).resolve()
        resolved_path = path.resolve()
        under_systemd_credentials = credential_directory.is_relative_to(SYSTEMD_CREDENTIALS_ROOT)
        under_unit_directory = resolved_path.is_relative_to(credential_directory)
    except OSError:
        return False
    return (
        under_systemd_credentials
        and under_unit_directory
        and uid == 0
        and gid == 0
        and mode in {0o400, 0o440}
    )


def read_secret(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    metadata = path.stat()
    mode = metadata.st_mode & 0o777
    runtime_secret = str(path.resolve()).startswith("/run/secrets/")
    shared_host_secret = approved_shared_host_secret(
        path,
        mode=mode,
        uid=metadata.st_uid,
        gid=metadata.st_gid,
    )
    systemd_credential = approved_systemd_credential(
        path,
        mode=mode,
        uid=metadata.st_uid,
        gid=metadata.st_gid,
    )
    if mode & 0o022 or (not runtime_secret and mode & 0o077 and not shared_host_secret and not systemd_credential):
        raise PermissionError(
            f"宿主机秘密文件必须为 0600，或为已批准的 10001:10001 0640 运行时 Secret，"
            f"或为 systemd LoadCredential；"
            f"Docker secret 不得可被组/其他用户写入：{path}"
        )
    return path.read_text(encoding="utf-8").strip()

_DOUYIN_COUNT_PREFIX = re.compile(r"^\d+(?:\.\d+)?(?:万|w)?$")


def clean_display_title(title: str | None) -> str:
    r"""抖音那条取数路把「互动数 + 文案 + 文案」拼成了标题——显示前修掉。（2026-08-10）

    Owner 打开 Obsidian 看到的是这样：

        1029找卖萌办校园卡不后悔#校园卡找卖萌办校园卡不后悔#校园卡

    生产实测 86 条抖音：**54 条带互动数前缀，47 条文案整段重复两遍**。

    **只在能自证的那一档动手**：去掉纯数字前缀之后，剩下的部分左右两半
    完全相同——这既修了重复，也证明了那个数字是独立的一段。
    其余 39 条一个字都不碰。

    ★ **前缀不能用贪婪正则去猜。** 第一版写 `^\d+(?:\.\d+)?(?:万|w)?`，
    在 `9326岁 感谢命运…9326岁 感谢命运…` 上把 `9326` 一起吃了
    （真前缀是 `93`，文案以 `26岁` 开头），于是那一条漏掉。
    改成**先找重复点、再验前缀是不是纯数字**。
    这个 bug 是「先出提案后落盘」看出来的——提案里那条躺在「不改」那一列。

    **不动存下来的数据**，只在显示时修：改坏正文这个仓栽过两次。
    """
    text = str(title or "").strip()
    # **整个标题就是一个互动数——那说明文案根本没抓到。**（2026-08-10）
    # 他库里有 4 条这样的：646 / 186 / 6.6万 / 4.4万。
    # 返回空字符串，让调用方落到已有的那条兜底上（用链接尾巴认人：
    # `douyin.com/video/7669771030182253002`）——比给他看一个 646 强。
    if text and _DOUYIN_COUNT_PREFIX.match(text):
        return ""
    for index in range(0, min(len(text), 8) + 1):
        prefix, rest = text[:index], text[index:]
        if prefix and not _DOUYIN_COUNT_PREFIX.match(prefix):
            continue
        half = len(rest) // 2
        # **门槛是 3 不是 4。** 原来写 `half > 3`，于是 `503小黑丝小黑丝`
        # 这种六字的重复漏掉了。全库量过：放到 >= 3 只多修这一条，不误伤别的
        # （叠词都在 2 字以内：哈哈 / 加油加油 / 好好，half <= 2 碰不到）。
        if half >= 3 and rest[:half] == rest[half:]:
            return rest[:half].strip()
    return text
