"""有界 Cookie 托管（v0.0.0.7 / T05）。

守两条不变量：

  · INV-DOMESTIC-COOKIE-STAYS —— 国内平台的 Cookie 一步都不离开 Owner 的浏览器
  · INV-NO-PASSWORD —— 任何地方都不出现平台账号密码；这里连 Cookie 明文也不落库

判据分三层，因为「应用层记得拦」和「不可能存在」是两件事：
应用层拒绝、表上的 CHECK、以及事后的全仓明文扫描。三层都单独测。
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from social_archive.credentials import (
    CUSTODIAL_PLATFORMS,
    DOMESTIC_PLATFORMS,
    CredentialRejected,
    CredentialStore,
    CredentialUnavailable,
    CredentialVault,
    assert_custodial_platform,
    count_cookies,
)
from social_archive.db import RuntimeStore

ROOT = Path(__file__).resolve().parents[2]

COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".x.com\tTRUE\t/\tTRUE\t0\tauth_token\tzz9plural1zalphaOmega77\n"
    "#HttpOnly_.x.com\tTRUE\t/\tTRUE\t0\tct0\tmagratgarlick42heaven\n"
)
# 上面这两个值是编的，但**形态**和真的一样——判据要能在真形态上工作，
# 用 "REDACTED" 当夹具会让脱敏扫描器永远测不出来。


@pytest.fixture
def vault(tmp_path: Path) -> CredentialVault:
    if not shutil.which("age") or not shutil.which("age-keygen"):
        pytest.skip("本机没有 age，跳过需要真实加解密的判据")
    identity = tmp_path / "identity.txt"
    completed = subprocess.run(
        ["age-keygen", "-o", str(identity)], capture_output=True, text=True, check=True
    )
    identity.chmod(0o600)
    recipient = ""
    for token in (completed.stderr + completed.stdout).split():
        if token.startswith("age1"):
            recipient = token.strip()
            break
    assert recipient, "没能从 age-keygen 输出里取到收件人公钥"
    return CredentialVault(recipient=recipient, identity_file=str(identity))


@pytest.fixture
def store_and_credentials(tmp_path: Path, vault: CredentialVault):
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    with store.connection() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(id,display_name,created_at,is_owner) VALUES(?,?,?,1)",
            ("usr_a", "甲", "2026-01-01T00:00:00Z"),
        )
        con.execute(
            "INSERT OR IGNORE INTO users(id,display_name,created_at,is_owner) VALUES(?,?,?,0)",
            ("usr_b", "乙", "2026-01-01T00:00:00Z"),
        )
    return store, CredentialStore(store, vault)


# ── 第一层：应用层拒绝 ────────────────────────────────────────────────


@pytest.mark.parametrize("platform", sorted(DOMESTIC_PLATFORMS))
def test_credential_store_rejects_domestic_platforms(platform: str, store_and_credentials) -> None:
    """任务包点名的判据。四个国内平台逐个试，不许有一个能写进去。"""
    _store, credentials = store_and_credentials
    with pytest.raises(CredentialRejected) as caught:
        credentials.put(user_id="usr_a", platform=platform, cookies_txt=COOKIES)
    # 拒绝理由要说清楚"为什么不需要"，不是笼统的"不支持"——
    # 用户看到"不支持"会以为是缺功能，然后去别处找绕过的办法。
    assert "不会离开你的浏览器" in str(caught.value)


def test_reddit_is_rejected_because_it_uses_oauth_not_because_it_was_forgotten(
    store_and_credentials,
) -> None:
    _store, credentials = store_and_credentials
    with pytest.raises(CredentialRejected) as caught:
        credentials.put(user_id="usr_a", platform="reddit", cookies_txt=COOKIES)
    assert "授权登录" in str(caught.value)


def test_only_the_three_western_sources_are_custodial() -> None:
    assert CUSTODIAL_PLATFORMS == {"x", "instagram", "youtube"}
    assert not (CUSTODIAL_PLATFORMS & DOMESTIC_PLATFORMS)
    assert assert_custodial_platform("  X  ") == "x"


def test_empty_cookies_are_rejected_instead_of_silently_connecting(store_and_credentials) -> None:
    """空串当成功会让「已连接」变成假的，之后取数永远是 0 且没人知道为什么。"""
    _store, credentials = store_and_credentials
    for empty in ("", "   ", "# 只有注释\n"):
        with pytest.raises(CredentialRejected):
            credentials.put(user_id="usr_a", platform="x", cookies_txt=empty)


# ── 第二层：库层不可能存在 ────────────────────────────────────────────


def test_database_check_constraint_blocks_domestic_even_if_app_layer_is_bypassed(
    store_and_credentials,
) -> None:
    """绕过应用层直接写库也要被 CHECK 拦住。

    这一条不是多余的：应用层的拒绝是一行 if，将来加个新入口忘了调用就没了；
    表上的约束是不变量本身。
    """
    store, _credentials = store_and_credentials
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection() as con:
            con.execute(
                """INSERT INTO platform_credential(
                       id,user_id,platform,recipient_fingerprint,cipher,
                       cipher_sha256,cipher_byte_size,created_at,updated_at)
                   VALUES('c','usr_a','xiaohongshu','fp',X'00','sha',1,'t','t')""",
            )


# ── 加密、隔离、撤销 ─────────────────────────────────────────────────


def test_stored_credential_is_ciphertext_and_plaintext_never_touches_the_database(
    store_and_credentials,
) -> None:
    store, credentials = store_and_credentials
    credentials.put(user_id="usr_a", platform="x", cookies_txt=COOKIES)
    with store.connection() as con:
        row = con.execute("SELECT * FROM platform_credential WHERE user_id='usr_a'").fetchone()
    assert row["algorithm"] == "age-x25519"
    assert bytes(row["cipher"]).startswith(b"age-encryption.org/v1")
    assert row["cookie_count"] == 2

    # 整个库文件里都不许出现明文里的任何一个值
    db_bytes = Path(_database_path(store)).read_bytes()
    for secret in (b"zz9plural1zalphaOmega77", b"magratgarlick42heaven"):
        assert secret not in db_bytes, "明文出现在了 SQLite 文件里"


def _database_path(store: RuntimeStore) -> str:
    """RuntimeStore 的库文件路径。不同版本属性名不同，取到哪个用哪个。"""
    for attr in ("path", "database", "db_path", "_path"):
        value = getattr(store, attr, None)
        if value:
            return str(value)
    raise AssertionError("找不到 RuntimeStore 的库文件路径——判据无法验证明文是否落盘")


def test_credentials_are_isolated_per_user(store_and_credentials) -> None:
    _store, credentials = store_and_credentials
    credentials.put(user_id="usr_a", platform="x", cookies_txt=COOKIES)
    assert [s.platform for s in credentials.status("usr_a") if s.connected] == ["x"]
    assert [s.platform for s in credentials.status("usr_b") if s.connected] == []
    with pytest.raises(CredentialUnavailable):
        with credentials.materialize(user_id="usr_b", platform="x"):
            pass


def test_revoke_leaves_no_row_and_no_ciphertext(store_and_credentials) -> None:
    store, credentials = store_and_credentials
    credentials.put(user_id="usr_a", platform="x", cookies_txt=COOKIES)
    assert credentials.revoke(user_id="usr_a", platform="x") == 1
    with store.connection() as con:
        rows = con.execute(
            "SELECT COUNT(*) AS n FROM platform_credential WHERE user_id='usr_a'"
        ).fetchone()["n"]
    assert rows == 0
    # 再撤一次是 0 不是报错——一键撤销要幂等
    assert credentials.revoke(user_id="usr_a", platform="x") == 0


def test_materialized_file_is_0600_and_disappears_afterwards(store_and_credentials) -> None:
    _store, credentials = store_and_credentials
    credentials.put(user_id="usr_a", platform="x", cookies_txt=COOKIES)
    seen: Path | None = None
    with credentials.materialize(user_id="usr_a", platform="x") as path:
        seen = path
        assert path.is_file()
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.read_text(encoding="utf-8") == COOKIES
        # 明文绝不能落在 data_root 里——那是要被三副本备份出去的
        assert "runtime.sqlite3" not in str(path)
    assert seen is not None and not seen.exists(), "临时明文文件没有被删掉"


def test_materialize_fails_loudly_when_nothing_is_stored(store_and_credentials) -> None:
    _store, credentials = store_and_credentials
    with pytest.raises(CredentialUnavailable):
        with credentials.materialize(user_id="usr_a", platform="instagram"):
            pass


def test_cookie_count_includes_httponly_lines_and_ignores_comments() -> None:
    assert count_cookies(COOKIES) == 2
    assert count_cookies("# 全是注释\n# 再来一行\n") == 0
    assert count_cookies("") == 0


# ── 第三层：脱敏扫描器自身 ───────────────────────────────────────────


def test_redaction_scanner_actually_catches_a_planted_cookie(tmp_path: Path) -> None:
    """判据自己的自检：扫描器必须在阳性对照上报红。

    只跑阴性扫描然后说「干净」是没有意义的——扫不到和没问题长得一样。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib

    scanner = importlib.import_module("scan_plaintext_credentials")
    planted = (
        ".x.com\tTRUE\t/\tTRUE\t0\tauth_token\t9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d\n"
    )
    hits = scanner.scan_text("planted.txt", planted)
    assert hits, "扫描器抓不到一条标准的 Netscape cookie 行"
    assert {h["kind"] for h in hits} >= {"netscape_cookie_line"}

    # 占位值不该被报成泄漏，否则真出事时没人看告警
    assert not scanner.scan_text(
        "fixture.txt", ".x.com\tTRUE\t/\tTRUE\t0\tauth_token\tREDACTED\n"
    )


def test_repository_has_no_plaintext_credentials() -> None:
    """全仓扫描。T05 的 Stop Condition：命中即停整个 S2。"""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_plaintext_credentials.py"), "--all"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, (
        f"全仓扫描发现明文凭据，按 T05 的 Stop Condition 必须停止整个 S2：\n"
        f"{completed.stderr}"
    )
    assert "扫了" in completed.stdout and "0 处命中" in completed.stdout


def test_revoke_leaves_no_ciphertext_bytes_in_the_database_file(store_and_credentials) -> None:
    """「撤销后库中无残留」按**字面**做到，不是「SELECT 查不到就算了」。

    实测过：不开 PRAGMA secure_delete 的话，撤销后 SELECT 确实返回 0 行，
    但密文原样躺在已释放的页里，grep 库文件就能找到。存的是密文（没有 age
    身份读不出内容），可要求写的是「无残留」而不是「读不出来」。
    """
    store, credentials = store_and_credentials
    credentials.put(user_id="usr_a", platform="x", cookies_txt=COOKIES)
    with store.connection() as con:
        cipher = bytes(
            con.execute("SELECT cipher FROM platform_credential WHERE user_id='usr_a'")
            .fetchone()["cipher"]
        )
    assert len(cipher) > 48

    def db_bytes() -> bytes:
        base = Path(_database_path(store))
        blob = b""
        for suffix in ("", "-wal"):
            candidate = Path(str(base) + suffix)
            if candidate.exists():
                blob += candidate.read_bytes()
        return blob

    assert cipher[:48] in db_bytes(), "撤销前都找不到密文，这条判据在空转"
    credentials.revoke(user_id="usr_a", platform="x")
    assert cipher[:48] not in db_bytes(), (
        "撤销之后密文仍然留在库文件里——PRAGMA secure_delete 没有生效"
    )
