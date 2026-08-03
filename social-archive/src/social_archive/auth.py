"""Google / GitHub 登录（v0.0.0.7 / T02）。

## 为什么不用 Authlib

任务包的 suggested_path 提了 Authlib，但那是 L2 建议不是约束。授权码流本身
只有三步（跳转 → 换 token → 取 userinfo），用已经在依赖里的 httpx 写完不到
一百行；引入 Authlib 会带进一串传递依赖，而 forbidden_dependencies 明确在意
稳定性。少一个依赖少一份维护面。

## 硬边界

· 永不接受、存储或代填任何平台账号密码（INV-NO-PASSWORD）。本模块只处理
  provider 回调带回来的 code，Owner 的密码全程在 provider 那边。
· client_secret 只从 systemd credential 文件读，不进仓、不进 .env、不进日志。
· 会话是服务端 session 表 + HttpOnly Cookie，不是 JWT —— 撤销只要 UPDATE 一行。
· 身份主键用 provider 的 subject 而不是邮箱：邮箱可以改，改了就变成另一个人。

## 状态参数（CSRF）

state 存进 HttpOnly Cookie，回调时逐字节比对后立刻删除。不另建表：state 的生命
周期就是一次跳转往返，放 Cookie 里比放数据库更贴合它的寿命，也不会留垃圾行。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from .config import Settings
from .db import RuntimeStore
from .utils import read_secret

SESSION_COOKIE = "sa_session"
STATE_COOKIE = "sa_oauth_state"
#: state 只需要活过一次跳转往返。给 10 分钟，够慢网络用，又不会让一个被偷看的
#: state 长期可用。
STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    #: userinfo 响应里哪个字段是稳定唯一 ID。**不是邮箱。**
    subject_field: str
    name_field: str


PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email profile",
        subject_field="sub",
        name_field="name",
    ),
    "github": Provider(
        name="github",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scope="read:user",
        subject_field="id",
        name_field="name",
    ),
}


class AuthNotConfigured(Exception):
    """凭据还没配好。

    这是**环境状态**，不是代码缺陷，所以它有自己的类型：路由据此返回 503 +
    可读中文，而不是 500 + 堆栈。INV-NO-SILENT-ZERO 的同一条精神——说不出
    为什么的失败是缺陷。
    """


def _client_id(settings: Settings, provider: str) -> str | None:
    return getattr(settings, f"{provider}_client_id", None) or None


def _client_secret(settings: Settings, provider: str) -> str | None:
    return read_secret(getattr(settings, f"{provider}_client_secret_file", None))


def provider_configured(settings: Settings, provider: str) -> bool:
    return bool(_client_id(settings, provider) and _client_secret(settings, provider))


def _require_provider(name: str) -> Provider:
    provider = PROVIDERS.get(name)
    if provider is None:
        raise HTTPException(404, f"不支持的登录方式：{name}")
    return provider


def _redirect_uri(settings: Settings, provider: str) -> str:
    # 与 OWNER_OAUTH_SETUP.md 里登记的回调地址必须逐字符一致，
    # 差一个字符就是 redirect_uri_mismatch。结尾没有斜杠。
    return f"{settings.public_base_url.rstrip('/')}/v1/auth/{provider}/callback"


async def _exchange_code(
    settings: Settings, provider: Provider, code: str
) -> str:
    client_id = _client_id(settings, provider.name)
    client_secret = _client_secret(settings, provider.name)
    if not client_id or not client_secret:
        raise AuthNotConfigured(provider.name)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            provider.token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _redirect_uri(settings, provider.name),
            },
            # GitHub 默认回 form-urlencoded，要显式要 JSON
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        # 绝不把响应正文原样带出去——它可能含 client_secret 的回显。
        raise HTTPException(502, "登录服务暂时不可用，请稍后再试。")
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(502, "登录服务没有返回访问凭据，请重试。")
    return str(token)


async def _fetch_identity(provider: Provider, access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            provider.userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
    if response.status_code != 200:
        raise HTTPException(502, "拿不到你的账号信息，请重试。")
    return dict(response.json())


def build_router(settings: Settings, store: RuntimeStore) -> APIRouter:
    router = APIRouter(prefix="/v1/auth", tags=["auth"])
    secure_cookie = settings.public_base_url.startswith("https://")

    @router.get("/providers")
    def providers() -> dict[str, Any]:
        """第 1 屏据此决定显示哪些登录按钮。

        没配好的 provider 不显示——比显示一个点了就报错的按钮好。
        """
        return {
            "providers": [
                {"name": name, "configured": provider_configured(settings, name)}
                for name in PROVIDERS
            ]
        }

    @router.get("/{provider_name}/start")
    def start(provider_name: str, response: Response) -> dict[str, str]:
        provider = _require_provider(provider_name)
        client_id = _client_id(settings, provider.name)
        if not client_id or not _client_secret(settings, provider.name):
            raise HTTPException(503, f"{provider.name} 登录还没配置好，请联系管理员。")
        state = secrets.token_urlsafe(32)
        response.set_cookie(
            STATE_COOKIE,
            state,
            max_age=STATE_TTL_SECONDS,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            path="/v1/auth",
        )
        query = httpx.QueryParams(
            {
                "client_id": client_id,
                "redirect_uri": _redirect_uri(settings, provider.name),
                "response_type": "code",
                "scope": provider.scope,
                "state": state,
            }
        )
        return {"authorize_url": f"{provider.authorize_url}?{query}"}

    @router.get("/{provider_name}/callback")
    async def callback(
        provider_name: str,
        request: Request,
        response: Response,
        code: str = Query(default=""),
        state: str = Query(default=""),
    ) -> dict[str, Any]:
        provider = _require_provider(provider_name)
        expected_state = request.cookies.get(STATE_COOKIE) or ""
        # compare_digest 而不是 ==：state 比对是安全判断，不给计时侧信道。
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            raise HTTPException(400, "登录链接已失效，请回到首页重新登录。")
        if not code:
            raise HTTPException(400, "登录没有完成，请重试。")

        try:
            access_token = await _exchange_code(settings, provider, code)
        except AuthNotConfigured:
            raise HTTPException(503, f"{provider.name} 登录还没配置好，请联系管理员。")
        identity = await _fetch_identity(provider, access_token)

        subject = identity.get(provider.subject_field)
        if subject in (None, ""):
            raise HTTPException(502, "登录服务没有返回账号标识，请重试。")

        user_id = store.upsert_oauth_identity(
            provider=provider.name,
            subject=str(subject),
            display_name=identity.get(provider.name_field) or identity.get("login"),
        )
        session_id = store.create_session(user_id=user_id)

        response.delete_cookie(STATE_COOKIE, path="/v1/auth")
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            path="/",
        )
        # 绝不回显 session_id 或任何 token——Cookie 已经带上了，正文里再出现
        # 一次只会多一个泄漏面（日志、Referer、截图）。
        return {"ok": True, "provider": provider.name}

    @router.post("/logout")
    def logout(request: Request, response: Response) -> dict[str, bool]:
        session_id = request.cookies.get(SESSION_COOKIE) or ""
        revoked = store.revoke_session(session_id) if session_id else False
        response.delete_cookie(SESSION_COOKIE, path="/")
        # 无论有没有撤销成功都清 Cookie 并回 ok：登出必须是幂等的，
        # 让用户"登出失败"是没有意义的失败。
        return {"ok": True, "revoked": revoked}

    @router.get("/me")
    def me(request: Request) -> dict[str, Any]:
        user_id = store.resolve_session(request.cookies.get(SESSION_COOKIE) or "")
        if not user_id:
            raise HTTPException(401, "还没有登录。")
        with store.connection() as con:
            row = con.execute(
                "SELECT id,display_name,is_owner FROM users WHERE id=?", (user_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(401, "还没有登录。")
        return {"user_id": row["id"], "display_name": row["display_name"], "is_owner": bool(row["is_owner"])}

    return router


def session_user_id(request: Request, store: RuntimeStore) -> str | None:
    """给其他路由用的会话解析。返回 None 表示未登录。"""
    return store.resolve_session(request.cookies.get(SESSION_COOKIE) or "")
