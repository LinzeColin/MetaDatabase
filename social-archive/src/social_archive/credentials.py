"""有界 Cookie 托管（v0.0.0.7 / T05）。

## 边界在哪

只有**西方三源**（X / Instagram / YouTube）的会话会被托管到服务端，
因为它们的取数是在服务端跑 gallery-dl / yt-dlp，工具需要一份 cookies.txt。

**国内平台一步都不进来。** 小红书、抖音、B站、快手的 Cookie 永远留在 Owner 的
浏览器里（INV-DOMESTIC-COOKIE-STAYS）——它们的取数路是在浏览器内拦截平台
自身的 API 响应，服务端从头到尾不需要、也不接受它们的凭据。

Reddit 也不在这里：它走 OAuth，不是 Cookie。

拒绝写在三层上，因为"应用层记得拦"和"不可能存在"是两件事：

  1. `assert_custodial_platform()` —— 写入路径显式拒绝，给用户一句中文
  2. 表上的 `CHECK(platform IN ('x','instagram','youtube'))` —— 绕过第 1 层也进不去
  3. `scripts/scan_plaintext_credentials.py` —— 事后扫描，明文一旦外泄立刻可见

## 明文的生命周期

明文只在两个瞬间存在，两次都不落持久盘：

  · 写入：HTTP body → 进程内存 → age 子进程 stdin → 密文入库
  · 使用：密文 → age -d → **0600 临时文件** → 子进程读 → 立即 unlink

临时文件放在系统临时目录（容器里挂 tmpfs），绝不放 data_root：
data_root 是要被三副本备份出去的，明文进了那里就等于上传了。
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .utils import sha256_bytes, stable_id

# 托管范围。改这里之前先读 INV-DOMESTIC-COOKIE-STAYS。
CUSTODIAL_PLATFORMS = frozenset({"x", "instagram", "youtube"})

# 明确点名的国内平台——不是"不在白名单里"，是**明确禁止**，
# 好让拒绝理由能对用户说清楚，而不是笼统的"不支持"。
DOMESTIC_PLATFORMS = frozenset({"xiaohongshu", "douyin", "bilibili", "kuaishou"})

# Reddit 不是漏掉的：它走 OAuth，没有 Cookie 要托管。
OAUTH_PLATFORMS = frozenset({"reddit"})


class CredentialRejected(Exception):
    """写入被拒。message 是给用户看的中文，会原样出现在 400 响应里。"""


class CredentialUnavailable(Exception):
    """要用凭据但库里没有，或解密不可用。"""


@dataclass(frozen=True)
class CredentialStatus:
    platform: str
    connected: bool
    cookie_count: int = 0
    updated_at: str | None = None
    last_used_at: str | None = None


def assert_custodial_platform(platform: str) -> str:
    """写入路径的第一道门。返回规范化后的平台名，或抛 CredentialRejected。"""
    name = str(platform or "").strip().lower()
    if name in DOMESTIC_PLATFORMS:
        raise CredentialRejected(
            f"{name} 的登录信息不会离开你的浏览器，本产品不接收它。"
            "这个平台的内容是在你自己的浏览器里读取的，服务端不需要你的账号凭据。"
        )
    if name in OAUTH_PLATFORMS:
        raise CredentialRejected(f"{name} 使用授权登录，不需要上传浏览器会话。")
    if name not in CUSTODIAL_PLATFORMS:
        raise CredentialRejected("不支持托管这个平台的登录信息。")
    return name


def count_cookies(cookies_txt: str) -> int:
    """数 Netscape cookies.txt 里的有效行。

    只用于界面显示"已连接、N 条"。**不解析也不留下任何名或值。**
    `#HttpOnly_` 是注释形态但确实是一条 cookie，要算进去；
    其余 `#` 开头的是真注释。
    """
    count = 0
    for line in str(cookies_txt or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and not stripped.startswith("#HttpOnly_"):
            continue
        if stripped.count("\t") >= 6:
            count += 1
    return count


class CredentialVault:
    """age 加解密。加密只要收件人公钥，解密才要私钥。

    与 `encryption.AgeEncryptor` 分开的原因：那个是给内容制品用的，
    只加密不解密（三副本只需要公钥）。凭据必须能解回来给子进程用，
    是不同的信任面，混在一起会让"备份通道只有公钥"这条性质悄悄失效。
    """

    def __init__(self, *, recipient: str | None, identity_file: str | None, binary: str = "age"):
        self.recipient = (recipient or "").strip()
        self.identity_file = (identity_file or "").strip()
        self.binary = binary

    @property
    def recipient_fingerprint(self) -> str:
        return sha256_bytes(self.recipient.encode("utf-8"))[:24]

    def _age(self) -> str:
        resolved = shutil.which(self.binary)
        if not resolved:
            raise CredentialUnavailable("服务器缺少 age 命令，不能安全保存登录信息。")
        return resolved

    def encrypt(self, plaintext: str) -> bytes:
        if not self.recipient:
            raise CredentialUnavailable("服务器未配置加密收件人，暂时不能保存登录信息。")
        completed = subprocess.run(
            [self._age(), "-r", self.recipient, "-o", "-"],
            input=plaintext.encode("utf-8"), capture_output=True, check=False,
        )
        if completed.returncode or not completed.stdout:
            # stderr 里不会有明文（age 不回显输入），但仍然只取尾部并截断。
            raise CredentialUnavailable((completed.stderr.decode("utf-8", "replace") or "加密失败")[-300:])
        return completed.stdout

    def decrypt_to_bytes(self, cipher: bytes) -> bytes:
        if not self.identity_file:
            raise CredentialUnavailable("服务器未配置解密身份，不能使用已保存的登录信息。")
        identity = Path(self.identity_file)
        if not identity.is_file():
            raise CredentialUnavailable("解密身份文件不存在。")
        completed = subprocess.run(
            [self._age(), "-d", "-i", str(identity)],
            input=cipher, capture_output=True, check=False,
        )
        if completed.returncode:
            raise CredentialUnavailable((completed.stderr.decode("utf-8", "replace") or "解密失败")[-300:])
        return completed.stdout


class CredentialStore:
    """凭据的读写与撤销。所有方法都按 user_id + platform 隔离。"""

    def __init__(self, runtime_store, vault: CredentialVault):
        self._store = runtime_store
        self._vault = vault

    def put(self, *, user_id: str, platform: str, cookies_txt: str) -> CredentialStatus:
        name = assert_custodial_platform(platform)
        text = str(cookies_txt or "")
        count = count_cookies(text)
        if count <= 0:
            # 空字符串当成功会让"已连接"变成假的，之后取数永远是 0 且没人知道为什么。
            raise CredentialRejected("没有读到这个平台的登录信息，请先在浏览器里登录该平台。")
        cipher = self._vault.encrypt(text)
        now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        row_id = stable_id("cred", user_id, name)
        with self._store.connection() as con:
            con.execute(
                """INSERT INTO platform_credential(
                       id,user_id,platform,algorithm,recipient_fingerprint,cipher,
                       cipher_sha256,cipher_byte_size,cookie_count,created_at,updated_at)
                   VALUES(?,?,?,'age-x25519',?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,platform) DO UPDATE SET
                       cipher=excluded.cipher, cipher_sha256=excluded.cipher_sha256,
                       cipher_byte_size=excluded.cipher_byte_size, cookie_count=excluded.cookie_count,
                       recipient_fingerprint=excluded.recipient_fingerprint, updated_at=excluded.updated_at""",
                (row_id, user_id, name, self._vault.recipient_fingerprint, cipher,
                 sha256_bytes(cipher), len(cipher), count, now, now),
            )
        return CredentialStatus(platform=name, connected=True, cookie_count=count, updated_at=now)

    def status(self, user_id: str) -> list[CredentialStatus]:
        """给界面用。只回形态，绝不回密文或明文。"""
        with self._store.connection() as con:
            rows = {
                row["platform"]: row
                for row in con.execute(
                    "SELECT platform,cookie_count,updated_at,last_used_at "
                    "FROM platform_credential WHERE user_id=?", (user_id,)
                )
            }
        return [
            CredentialStatus(
                platform=name,
                connected=name in rows,
                cookie_count=int(rows[name]["cookie_count"]) if name in rows else 0,
                updated_at=rows[name]["updated_at"] if name in rows else None,
                last_used_at=rows[name]["last_used_at"] if name in rows else None,
            )
            for name in sorted(CUSTODIAL_PLATFORMS)
        ]

    @staticmethod
    def _secure_delete(con) -> None:
        """让 DELETE 真的把字节抹掉，而不是只把页标成空闲。

        实测过：不开这个的话，撤销之后 `SELECT` 确实返回 0 行，但密文原样
        躺在已释放的页里，用 grep 就能在库文件中找到——「撤销后库中无残留」
        按字面讲是不成立的。存的是密文（没有 age 身份读不出内容），
        但要求写的是「无残留」，不是「读不出来」，所以照字面做到。

        secure_delete 是连接级 PRAGMA，必须在这次 DELETE 之前设。
        """
        con.execute("PRAGMA secure_delete=ON")

    def revoke(self, *, user_id: str, platform: str) -> int:
        """撤销 = 删行。密文是 BLOB，行没了密文就没了，不留指向磁盘的残骸。"""
        name = str(platform or "").strip().lower()
        with self._store.connection() as con:
            self._secure_delete(con)
            cursor = con.execute(
                "DELETE FROM platform_credential WHERE user_id=? AND platform=?", (user_id, name)
            )
            return int(cursor.rowcount or 0)

    def revoke_all(self, *, user_id: str) -> int:
        with self._store.connection() as con:
            self._secure_delete(con)
            return int(con.execute(
                "DELETE FROM platform_credential WHERE user_id=?", (user_id,)
            ).rowcount or 0)

    @contextlib.contextmanager
    def materialize(self, *, user_id: str, platform: str) -> Iterator[Path]:
        """把凭据解密成一个 0600 临时文件，交给子进程用，退出即删。

        为什么必须是临时文件而不是管道：gallery-dl / yt-dlp 的 `--cookies` 只收路径。
        为什么必须在系统临时目录：data_root 会被三副本备份出去，
        明文写进那里等于把它上传了。
        """
        name = assert_custodial_platform(platform)
        with self._store.connection() as con:
            row = con.execute(
                "SELECT cipher FROM platform_credential WHERE user_id=? AND platform=?",
                (user_id, name),
            ).fetchone()
        if row is None:
            raise CredentialUnavailable(f"还没有连接 {name}，请先在浏览器里登录并点连接。")
        plaintext = self._vault.decrypt_to_bytes(row["cipher"])

        handle, raw_path = tempfile.mkstemp(prefix="sa-cookies-", suffix=".txt")
        path = Path(raw_path)
        try:
            os.fchmod(handle, 0o600)
            with os.fdopen(handle, "wb") as stream:
                stream.write(plaintext)
            now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            with self._store.connection() as con:
                con.execute(
                    "UPDATE platform_credential SET last_used_at=? WHERE user_id=? AND platform=?",
                    (now, user_id, name),
                )
            yield path
        finally:
            # 先覆写再删：删除只摘目录项，块还在盘上。覆写不是万无一失（COW/SSD
            # 有磨损均衡），但比什么都不做强，成本也只有几 KB。
            try:
                size = path.stat().st_size
                with open(path, "r+b") as stream:
                    stream.write(b"\0" * size)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                pass
            path.unlink(missing_ok=True)
