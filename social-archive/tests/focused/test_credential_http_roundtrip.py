"""凭据托管的 **HTTP 层**往返（v0.0.0.7 / T06）。

T05 的 15 条判据打在 CredentialStore 上（库层）。这一组打在**接口**上：
状态码、中文提示、以及"永不回值"这条。

为什么要分开：库层再对，端点接错了照样出事——比如把 bearer 令牌
也当成合法身份（凭据必须只认会话）、或者未配密钥时静默成功。

已在真实实例上手工跑通一次（evidence/T06/CUSTODY_ROUNDTRIP_LIVE.json，
含真 age 密钥、真 SQLite、撤销后逐字节查残留）。这组判据是把那次
手工验证钉住，免得回归。
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 上传的全是合成值，**不是任何真实账号的会话**。
SYNTHETIC = (
    "# Netscape HTTP Cookie File\n"
    ".x.com\tTRUE\t/\tTRUE\t0\tauth_token\tSYNTHETIC-NOT-A-REAL-SESSION\n"
    ".x.com\tTRUE\t/\tTRUE\t2000000000\tct0\tSYNTHETIC-CSRF\n"
)


def _client(tmp_path, monkeypatch, *, with_age_key: bool) -> tuple[TestClient, object]:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": str(root),
        "SOCIAL_ARCHIVE_RUNTIME_DB": str(root / "db.sqlite"),
        "SOCIAL_ARCHIVE_STAGING_ROOT": str(root / "staging"),
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": str(root / "private"),
        "SOCIAL_ARCHIVE_WATCH_ROOT": str(root / "import"),
        "SOCIAL_ARCHIVE_PWA_ROOT": str(pwa),
        "SOCIAL_ARCHIVE_PAIRING_REQUIRED": "false",
    }.items():
        monkeypatch.setenv(key, value)

    if with_age_key:
        keys = tmp_path / "keys"
        keys.mkdir()
        identity = keys / "cred.txt"
        proc = subprocess.run(["age-keygen", "-o", str(identity)],
                              capture_output=True, text=True, check=True)
        recipient = ""
        for token in (proc.stderr + proc.stdout).split():
            if token.startswith("age1"):
                recipient = token
                break
        assert recipient, "没能从 age-keygen 拿到收件人"
        identity.chmod(0o600)
        monkeypatch.setenv("SOCIAL_ARCHIVE_CREDENTIAL_AGE_RECIPIENT", recipient)
        monkeypatch.setenv("SOCIAL_ARCHIVE_CREDENTIAL_AGE_IDENTITY_FILE", str(identity))
    else:
        monkeypatch.delenv("SOCIAL_ARCHIVE_CREDENTIAL_AGE_RECIPIENT", raising=False)
        monkeypatch.delenv("SOCIAL_ARCHIVE_CREDENTIAL_AGE_IDENTITY_FILE", raising=False)

    import social_archive.api as api

    api = importlib.reload(api)
    return TestClient(api.app), api


def _login(api) -> dict[str, str]:
    """建一个会话，等同于 OAuth 回调成功后那一步。"""
    user_id = api.store.upsert_oauth_identity(
        provider="github", subject="synthetic-owner", display_name="Owner"
    )
    return {"sa_session": api.store.create_session(user_id=user_id)}


pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "age-keygen"], capture_output=True).returncode != 0,
    reason="本机没有 age-keygen",
)


def test_credentials_require_a_session_not_a_bearer_token(tmp_path, monkeypatch) -> None:
    """凭据只认会话。共享 bearer 是给扩展做业务上行的，不该能写凭据。"""
    client, _ = _client(tmp_path, monkeypatch, with_age_key=True)
    assert client.get("/v1/credentials").status_code == 401
    anon = client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC})
    assert anon.status_code == 401
    assert "登录" in anon.json()["detail"]


def test_put_then_get_never_returns_the_value(tmp_path, monkeypatch) -> None:
    """存进去之后，**任何**读接口都不许把 cookie 值吐回来。"""
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)

    put = client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC}, cookies=cookies)
    assert put.status_code == 200, put.text
    assert put.json()["cookie_count"] == 2
    assert put.json()["connected"] is True

    got = client.get("/v1/credentials", cookies=cookies)
    assert got.status_code == 200
    body = got.text
    assert "SYNTHETIC-NOT-A-REAL-SESSION" not in body, "读接口把 cookie 值吐回来了"
    assert "auth_token" not in body
    entry = next(i for i in got.json()["items"] if i["platform"] == "x")
    assert entry["connected"] is True and entry["cookie_count"] == 2


def test_stored_bytes_are_ciphertext_not_the_cookie(tmp_path, monkeypatch) -> None:
    """落到库文件里的必须是 age 密文，明文一个字节都不许出现。"""
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)
    client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC}, cookies=cookies)

    raw = Path(api.settings.runtime_db).read_bytes()
    assert b"SYNTHETIC-NOT-A-REAL-SESSION" not in raw, "明文 cookie 落进了库文件"
    assert b"age-encryption.org" in raw, "存的不是 age 密文"


def test_revoke_is_idempotent_and_says_two_different_things(tmp_path, monkeypatch) -> None:
    """删两次都成功，但**措辞不同**——第二次不许假装删掉了什么。"""
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)
    client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC}, cookies=cookies)

    first = client.delete("/v1/credentials/x", cookies=cookies).json()
    second = client.delete("/v1/credentials/x", cookies=cookies).json()
    assert first["revoked"] == 1 and second["revoked"] == 0
    assert first["message_zh"] != second["message_zh"], "两次删除说了同一句话"

    raw = Path(api.settings.runtime_db).read_bytes()
    assert b"SYNTHETIC-NOT-A-REAL-SESSION" not in raw
    assert b"age-encryption.org" not in raw, "撤销之后库文件里还留着密文"


def test_unconfigured_vault_fails_loudly_instead_of_silently(tmp_path, monkeypatch) -> None:
    """没配加密收件人时必须 503 + 中文，不能静默成功也不能存明文。"""
    client, api = _client(tmp_path, monkeypatch, with_age_key=False)
    cookies = _login(api)
    resp = client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC}, cookies=cookies)
    assert resp.status_code == 503, resp.text
    assert "未配置" in resp.json()["detail"]
    assert Path(api.settings.runtime_db).read_bytes().count(b"SYNTHETIC") == 0


@pytest.mark.parametrize("platform", ["xiaohongshu", "douyin", "bilibili", "kuaishou"])
def test_domestic_platforms_are_refused_at_the_endpoint(platform, tmp_path, monkeypatch) -> None:
    """INV-DOMESTIC-COOKIE-STAYS：国内平台的登录态一个字节都不收。"""
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)
    resp = client.put(f"/v1/credentials/{platform}", json={"cookies_txt": SYNTHETIC}, cookies=cookies)
    # 400 而不是 422：这不是格式问题，是产品明确不接收
    assert resp.status_code == 400, resp.text
    assert "不会离开你的浏览器" in resp.json()["detail"]


def test_reddit_is_refused_for_its_own_reason(tmp_path, monkeypatch) -> None:
    """Reddit 被拒是因为它走 OAuth，不是因为它是国内平台。

    两种拒绝说的是两件事，混成一句话用户就不知道下一步该干嘛。
    """
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)
    detail = client.put("/v1/credentials/reddit",
                        json={"cookies_txt": SYNTHETIC}, cookies=cookies).json()["detail"]
    assert "授权登录" in detail
    assert "不会离开你的浏览器" not in detail, "把 Reddit 并进了国内平台那条理由"


def test_storing_is_refused_when_we_could_not_read_it_back(tmp_path, monkeypatch) -> None:
    """收件人配了、私钥没配 —— 这时**不许**报「已加密保存」。

    加密只要公钥，解密要私钥，两者分开配。所以完全可能出现
    「存得进、读不回」：PUT 成功、界面说存好了，而这份凭据永远取不出来，
    直到某次真的要用时才炸。

    生产上这个前提是实测到的：credential_age_identity 文件根本不存在，
    而 install.sh 建的是空占位。
    """
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)

    # 只把**私钥**拿掉，收件人保留 —— 精确复现那个配置
    api.credential_vault = type(api.credential_vault)(
        recipient=api.settings.credential_age_recipient, identity_file=None
    )
    api.credential_store = type(api.credential_store)(api.store, api.credential_vault)

    resp = client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC}, cookies=cookies)
    assert resp.status_code == 503, f"缺私钥却报了成功：{resp.status_code} {resp.text}"
    assert "解密" in resp.json()["detail"] or "自检" in resp.json()["detail"]

    # 而且**什么都不许留下**——半存不存比不存更糟
    listed = client.get("/v1/credentials", cookies=cookies).json()["items"]
    assert all(not i["connected"] for i in listed), "自检失败了却把密文留在库里"
    assert b"age-encryption.org" not in Path(api.settings.runtime_db).read_bytes()


def test_a_corrupt_identity_is_caught_at_write_time_not_at_read_time(tmp_path, monkeypatch) -> None:
    """私钥文件存在但是空的（install.sh 建的正是空占位）——同样要当场拒绝。"""
    client, api = _client(tmp_path, monkeypatch, with_age_key=True)
    cookies = _login(api)

    empty = tmp_path / "empty_identity.txt"
    empty.write_text("", encoding="utf-8")
    api.credential_vault = type(api.credential_vault)(
        recipient=api.settings.credential_age_recipient, identity_file=str(empty)
    )
    api.credential_store = type(api.credential_store)(api.store, api.credential_vault)

    resp = client.put("/v1/credentials/x", json={"cookies_txt": SYNTHETIC}, cookies=cookies)
    assert resp.status_code == 503, f"空私钥却报了成功：{resp.status_code} {resp.text}"
    assert b"age-encryption.org" not in Path(api.settings.runtime_db).read_bytes()
