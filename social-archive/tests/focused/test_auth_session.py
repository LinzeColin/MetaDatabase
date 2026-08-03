"""登录会话与身份（v0.0.0.7 / T02）。

范围说明（重要）：这些测试覆盖 T02 中**不依赖真实 OAuth 凭据**的那一半——
会话生命周期、登出失效、身份主键语义、未配置时的可读失败。

**它们不构成 T02 的 Acceptance。** T02 的 Acceptance 是「Owner 在真实浏览器用
两个 provider 各登录成功一次」，那需要真实 client_id/secret，当前状态见
evidence/T02/CREDENTIAL_BLOCKED_RECEIPT.json。这里通过不等于 T02 通过——
任务包把「pytest 全绿」明确列在『不能拿来当 PASS 的证据』里。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from social_archive.auth import PROVIDERS, SESSION_COOKIE, provider_configured
from social_archive.db import RuntimeStore


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStore:
    db = RuntimeStore(tmp_path / "runtime.sqlite3")
    db.initialize()
    return db


# ── 身份 ──────────────────────────────────────────────────────────


def test_same_subject_is_the_same_person(store: RuntimeStore) -> None:
    first = store.upsert_oauth_identity(provider="github", subject="12345", display_name="Linze")
    again = store.upsert_oauth_identity(provider="github", subject="12345", display_name="Linze")
    assert first == again, "同一个 subject 第二次登录变成了另一个人"


def test_both_providers_land_on_the_same_owner(store: RuntimeStore) -> None:
    """本版本站点在 Cloudflare Access 后面，只有 Owner 进得来。
    用 Google 登录一次、GitHub 登录一次，必须是同一个人——否则 Owner 会
    因为换了个按钮就看不到自己的数据。"""
    via_google = store.upsert_oauth_identity(provider="google", subject="g-1", display_name="Linze")
    via_github = store.upsert_oauth_identity(provider="github", subject="h-1", display_name="Linze")
    assert via_google == via_github
    with store.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM oauth_identity").fetchone()[0] == 2


def test_identity_binds_to_owner_row_created_by_migration(store: RuntimeStore) -> None:
    """T01 的迁移会先建一个 is_owner=1 的行。第一次登录必须认领它，
    而不是另建一个用户——否则 Owner 登录后看到的是空库。"""
    store.capture.__self__  # noqa: B018 - 只是明确 store 可用
    with store.connection() as con:
        con.execute(
            "INSERT INTO users(id,display_name,created_at,is_owner) VALUES(?,?,?,1)",
            ("usr_from_migration", "Owner", "2026-08-03T00:00:00Z"),
        )
    user_id = store.upsert_oauth_identity(provider="google", subject="g-2", display_name="Linze")
    assert user_id == "usr_from_migration"


def test_subject_is_required(store: RuntimeStore) -> None:
    """provider 没给 subject 时必须拒绝建身份，而不是拿空串当主键——
    那样所有人会合并成同一个『空 subject』用户。"""
    with pytest.raises(ValueError):
        store.upsert_oauth_identity(provider="google", subject="", display_name="x")


def test_unknown_provider_rejected(store: RuntimeStore) -> None:
    with pytest.raises(ValueError):
        store.upsert_oauth_identity(provider="weibo", subject="1", display_name="x")


# ── 会话 ──────────────────────────────────────────────────────────


def test_session_resolves_then_stops_after_logout(store: RuntimeStore) -> None:
    """T02 Acceptance 的可测部分：登出后受保护入口必须拒绝。"""
    user_id = store.upsert_oauth_identity(provider="github", subject="1", display_name="Linze")
    session_id = store.create_session(user_id=user_id)

    assert store.resolve_session(session_id) == user_id
    assert store.revoke_session(session_id) is True
    assert store.resolve_session(session_id) is None, "登出后会话仍然有效"


def test_revoking_twice_is_harmless(store: RuntimeStore) -> None:
    """登出必须幂等——让用户『登出失败』是没有意义的失败。"""
    user_id = store.upsert_oauth_identity(provider="github", subject="1", display_name="x")
    session_id = store.create_session(user_id=user_id)
    assert store.revoke_session(session_id) is True
    assert store.revoke_session(session_id) is False
    assert store.resolve_session(session_id) is None


def test_expired_session_is_rejected(store: RuntimeStore) -> None:
    user_id = store.upsert_oauth_identity(provider="github", subject="1", display_name="x")
    session_id = store.create_session(user_id=user_id, ttl_seconds=1)
    with store.connection() as con:
        con.execute(
            "UPDATE session SET expires_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(hours=1)).isoformat(), session_id),
        )
    assert store.resolve_session(session_id) is None, "过期会话仍然被接受"


def test_unknown_and_empty_session_ids_are_rejected(store: RuntimeStore) -> None:
    assert store.resolve_session("") is None
    assert store.resolve_session("nope") is None


def test_session_ids_are_unguessable_and_unique(store: RuntimeStore) -> None:
    """Cookie 里放的就是这个值，可猜等于可冒充。"""
    user_id = store.upsert_oauth_identity(provider="github", subject="1", display_name="x")
    ids = {store.create_session(user_id=user_id) for _ in range(50)}
    assert len(ids) == 50, "签发出了重复的会话 id"
    assert all(len(i) >= 32 for i in ids)


def test_revoke_all_sessions(store: RuntimeStore) -> None:
    user_id = store.upsert_oauth_identity(provider="github", subject="1", display_name="x")
    sessions = [store.create_session(user_id=user_id) for _ in range(3)]
    assert store.revoke_all_sessions(user_id) == 3
    assert all(store.resolve_session(s) is None for s in sessions)


def test_session_maps_to_tenant_scope(store: RuntimeStore) -> None:
    """会话的用处就是拿到 user_id 去开租户视图——这条把 T01 和 T02 缝在一起。"""
    user_id = store.upsert_oauth_identity(provider="github", subject="1", display_name="x")
    session_id = store.create_session(user_id=user_id)
    resolved = store.resolve_session(session_id)
    assert resolved is not None
    assert store.for_user(resolved).user_id == user_id


# ── 配置缺失时的行为 ──────────────────────────────────────────────


def test_provider_reported_unconfigured_without_credentials(tmp_path: Path) -> None:
    """没配凭据时必须**说得出**没配，而不是让用户点一个必然报错的按钮。"""

    class _S:
        google_client_id = None
        google_client_secret_file = None
        github_client_id = "abc"
        github_client_secret_file = None  # 有 id 没 secret 也算没配好

    assert provider_configured(_S(), "google") is False
    assert provider_configured(_S(), "github") is False


def test_provider_table_matches_taskpack_scope() -> None:
    """本版本 scope 冻结为 Google + GitHub 两个。多一个少一个都是范围变动。"""
    assert set(PROVIDERS) == {"google", "github"}


def test_subject_field_is_never_email() -> None:
    """邮箱可以改，改了就变成另一个人，历史数据全部失联。
    这条把『用 subject 不用邮箱』钉住。"""
    for provider in PROVIDERS.values():
        assert "mail" not in provider.subject_field.lower()


def test_session_cookie_name_is_stable() -> None:
    """扩展与 PWA 都按这个名字取会话，改名等于让所有人掉线。"""
    assert SESSION_COOKIE == "sa_session"


# ── 端点行为 ──────────────────────────────────────────────────────
#
# 判据故意是"端点响应什么"，不是"app.routes 里有没有这几条路径"。
# 后者试过一次，是错的：FastAPI 0.141 会把带 prefix 的 router 挂成 Mount，
# 路由藏在 Mount 内部，app.routes 里根本看不到——照那个判据会得出
# "路由没挂上"的结论，而实际请求是通的。判据要打在可观察行为上。


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(tmp_path / "data"))
    import importlib

    import social_archive.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app), api_module


def test_providers_endpoint_reports_configuration_honestly(client) -> None:
    c, _ = client
    body = c.get("/v1/auth/providers").json()
    names = {p["name"]: p["configured"] for p in body["providers"]}
    assert names == {"google": False, "github": False}, (
        "没配凭据却报告已配置——那会让用户点到一个必然报错的按钮"
    )


def test_protected_endpoint_rejects_without_session(client) -> None:
    """T02 Acceptance 的可测部分：没有有效会话时受保护入口返回 401。"""
    c, _ = client
    response = c.get("/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "还没有登录。"


def test_me_returns_user_after_session_cookie_is_set(client) -> None:
    c, api_module = client
    user_id = api_module.store.upsert_oauth_identity(
        provider="github", subject="99", display_name="Linze"
    )
    session_id = api_module.store.create_session(user_id=user_id)
    c.cookies.set(SESSION_COOKIE, session_id)
    body = c.get("/v1/auth/me").json()
    assert body["user_id"] == user_id
    assert body["is_owner"] is True


def test_logout_invalidates_the_session_for_real(client) -> None:
    """登出不能只是删 Cookie——服务端会话必须真的失效，
    否则拿到旧 Cookie 的人还能进来。"""
    c, api_module = client
    user_id = api_module.store.upsert_oauth_identity(
        provider="github", subject="98", display_name="Linze"
    )
    session_id = api_module.store.create_session(user_id=user_id)
    c.cookies.set(SESSION_COOKIE, session_id)
    assert c.get("/v1/auth/me").status_code == 200

    assert c.post("/v1/auth/logout").status_code == 200
    # 即使把 Cookie 原样塞回去也不该再认
    c.cookies.set(SESSION_COOKIE, session_id)
    assert c.get("/v1/auth/me").status_code == 401


def test_start_is_unavailable_not_broken_when_unconfigured(client) -> None:
    """没配凭据时是 503 + 中文，不是 500 + 堆栈。
    说不出为什么的失败是缺陷（INV-NO-SILENT-ZERO 的同一条精神）。"""
    c, _ = client
    response = c.get("/v1/auth/github/start")
    assert response.status_code == 503
    assert "配置" in response.json()["detail"]


def test_unknown_provider_is_404(client) -> None:
    c, _ = client
    assert c.get("/v1/auth/weibo/start").status_code == 404


def test_callback_rejects_missing_or_mismatched_state(client) -> None:
    """state 是 CSRF 防线。缺失或对不上一律拒绝，不能"宽容处理"。"""
    c, _ = client
    assert c.get("/v1/auth/github/callback?code=x&state=y").status_code == 400
    c.cookies.set("sa_oauth_state", "real-state")
    assert c.get("/v1/auth/github/callback?code=x&state=wrong").status_code == 400
    assert c.get("/v1/auth/github/callback?state=real-state").status_code == 400
