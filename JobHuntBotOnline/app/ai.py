from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import AIUsage, PlatformState, User, utcnow
from .security import redact_for_provider


class AIUnavailable(RuntimeError):
    pass


def _state(db: Session, key: str) -> PlatformState:
    row = db.get(PlatformState, key)
    if not row:
        row = PlatformState(key=key, value="")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _usage(db: Session, user_id: int | None) -> AIUsage:
    day = utcnow().date().isoformat()
    scope = "platform" if user_id is None else f"user:{user_id}"
    row = db.scalar(select(AIUsage).where(AIUsage.scope_key == scope, AIUsage.day_key == day))
    if not row:
        row = AIUsage(scope_key=scope, user_id=user_id, day_key=day, requests=0, tokens=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def platform_status(db: Session, settings: Settings) -> dict:
    breaker = _state(db, "deepseek_breaker")
    return {
        "configured": bool(settings.deepseek_api_key),
        "model": settings.deepseek_model,
        "breaker": breaker.value or "closed",
        "platform_daily_request_limit": settings.deepseek_daily_platform_request_limit,
        "default_user_daily_request_limit": settings.deepseek_default_user_request_limit,
    }


def generate(
    db: Session,
    settings: Settings,
    user: User,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1500,
) -> str:
    if not settings.deepseek_api_key:
        raise AIUnavailable("平台 AI 尚未配置，已使用确定性规则继续完成核心流程。")

    breaker = _state(db, "deepseek_breaker")
    if breaker.value:
        try:
            payload = json.loads(breaker.value)
            until = datetime.fromisoformat(payload.get("open_until", ""))
            if until > utcnow():
                raise AIUnavailable("平台 AI 暂时熔断，已使用确定性规则。")
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    user_usage = _usage(db, user.id)
    platform_usage = _usage(db, None)
    user_limit = user.daily_ai_request_limit or settings.deepseek_default_user_request_limit
    if user_usage.requests >= user_limit:
        raise AIUnavailable("你今天的 AI 增强额度已用完，核心功能仍可使用。")
    if platform_usage.requests >= settings.deepseek_daily_platform_request_limit:
        raise AIUnavailable("平台今天的 AI 请求额度已用完，核心功能仍可使用。")
    if platform_usage.tokens >= settings.deepseek_daily_platform_token_limit:
        raise AIUnavailable("平台今天的 AI Token 预算已用完，核心功能仍可使用。")

    body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": redact_for_provider(user_prompt)},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=settings.deepseek_request_timeout_seconds) as client:
            response = client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json=body,
            )
        if response.status_code in {401, 402, 429}:
            raise AIUnavailable(f"平台 AI 暂不可用（{response.status_code}），已退回确定性规则。")
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or 0)
        user_usage.requests += 1
        user_usage.tokens += tokens
        platform_usage.requests += 1
        platform_usage.tokens += tokens
        breaker.value = ""
        db.commit()
        return text
    except AIUnavailable:
        raise
    except Exception as exc:
        failure = _state(db, "deepseek_failures")
        try:
            count = int(failure.value or "0") + 1
        except ValueError:
            count = 1
        failure.value = str(count)
        if count >= settings.deepseek_circuit_breaker_failures:
            breaker.value = json.dumps({
                "open_until": (utcnow() + timedelta(minutes=settings.deepseek_circuit_breaker_minutes)).isoformat(),
                "reason": type(exc).__name__,
            })
            failure.value = "0"
        db.commit()
        raise AIUnavailable("平台 AI 请求失败，已使用确定性规则继续。") from exc
