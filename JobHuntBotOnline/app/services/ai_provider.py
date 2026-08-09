from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AIApplicationEnhancement,
    AIProviderConfig,
    AIUsageRecord,
    ApplicationPack,
    CandidateProfile,
    Experience,
    Job,
    Resume,
    json_dumps,
)
from app.services.analyzer import AnalysisResult


settings = get_settings()
ALLOWED_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
ALLOWED_MODES = {"fast", "precision"}
OFFICIAL_BASE_URL = "https://api.deepseek.com"
PROMPT_VERSION = "job-analysis-v2"


class AIProviderError(RuntimeError):
    def __init__(self, code: str, user_message: str, *, retryable: bool = False):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retryable = retryable


@dataclass(frozen=True)
class UsageSummary:
    requests: int
    total_tokens: int


@dataclass(frozen=True)
class ProviderView:
    configured: bool
    enabled: bool
    ready: bool
    key_source: str
    masked_key: str
    base_url: str
    fast_model: str
    precision_model: str
    default_mode: str
    daily_request_limit: int
    daily_token_limit: int
    requests_today: int
    tokens_today: int
    last_tested_at: datetime | None
    last_success_at: datetime | None
    last_error: str
    circuit_open_until: datetime | None
    consent_to_external_processing: bool


@dataclass(frozen=True)
class EnhancementPayload:
    summary_zh: str
    reasons_zh: list[str]
    risks_zh: list[str]
    questions_for_user_zh: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    why_role_en: str
    why_company_en: str
    confidence: str
    suggested_action: str


@dataclass(frozen=True)
class EnhancementOutcome:
    status: str
    enhancement: AIApplicationEnhancement | None
    user_message: str


def get_or_create_config(db: Session, user_id: int) -> AIProviderConfig:
    config = db.scalar(select(AIProviderConfig).where(AIProviderConfig.user_id == user_id))
    if config:
        return config
    config = AIProviderConfig(
        user_id=user_id,
        provider="deepseek",
        base_url=OFFICIAL_BASE_URL,
        fast_model=settings.deepseek_fast_model,
        precision_model=settings.deepseek_precision_model,
        default_mode=settings.deepseek_default_mode,
        enabled=False,
        consent_to_external_processing=False,
        daily_request_limit=settings.deepseek_daily_request_limit,
        daily_token_limit=settings.deepseek_daily_token_limit,
        max_input_characters=settings.deepseek_max_input_characters,
        request_timeout_seconds=settings.deepseek_request_timeout_seconds,
    )
    db.add(config)
    db.flush()
    return config


def _read_key_file(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value


def effective_api_key(config: AIProviderConfig) -> tuple[str, str]:
    file_key = _read_key_file(settings.deepseek_api_key_file)
    if file_key:
        return file_key, "server_secret_file"
    if settings.deepseek_api_key:
        return settings.deepseek_api_key, "server_environment"
    if config.api_key:
        return config.api_key, "encrypted_database"
    return "", "not_configured"


def _mask_key(key: str) -> str:
    if not key:
        return "未设置"
    suffix = key[-4:] if len(key) >= 4 else "****"
    return f"••••••••{suffix}"


def usage_today(db: Session, user_id: int) -> UsageSummary:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    row = db.execute(
        select(
            func.count(AIUsageRecord.id),
            func.coalesce(func.sum(AIUsageRecord.total_tokens), 0),
        ).where(
            AIUsageRecord.user_id == user_id,
            AIUsageRecord.created_at >= start,
            AIUsageRecord.status.in_(["success", "failed"]),
        )
    ).one()
    return UsageSummary(requests=int(row[0] or 0), total_tokens=int(row[1] or 0))


def provider_view(db: Session, user_id: int) -> ProviderView:
    config = get_or_create_config(db, user_id)
    key, source = effective_api_key(config)
    usage = usage_today(db, user_id)
    circuit = _aware(config.circuit_open_until)
    now = datetime.now(timezone.utc)
    circuit_open = bool(circuit and circuit > now)
    ready = bool(
        key
        and config.enabled
        and config.consent_to_external_processing
        and config.last_success_at
        and not config.last_error
        and not circuit_open
    )
    return ProviderView(
        configured=bool(key),
        enabled=config.enabled,
        ready=ready,
        key_source=source,
        masked_key=_mask_key(key),
        base_url=config.base_url,
        fast_model=config.fast_model,
        precision_model=config.precision_model,
        default_mode=config.default_mode,
        daily_request_limit=config.daily_request_limit,
        daily_token_limit=config.daily_token_limit,
        requests_today=usage.requests,
        tokens_today=usage.total_tokens,
        last_tested_at=config.last_tested_at,
        last_success_at=config.last_success_at,
        last_error=config.last_error,
        circuit_open_until=config.circuit_open_until,
        consent_to_external_processing=config.consent_to_external_processing,
    )


def save_provider_config(
    db: Session,
    *,
    user_id: int,
    api_key: str,
    enabled: bool,
    consent: bool,
    default_mode: str,
    daily_request_limit: int,
    daily_token_limit: int,
) -> AIProviderConfig:
    config = get_or_create_config(db, user_id)
    key = api_key.strip()
    key_changed = bool(key and key != config.api_key)
    if key:
        if len(key) < 16 or len(key) > 512 or any(ch.isspace() for ch in key):
            raise ValueError("API Key 格式无效；请复制完整密钥，不要包含空格或换行。")
        config.api_key = key
        if key_changed:
            config.last_tested_at = None
            config.last_success_at = None
    if default_mode not in ALLOWED_MODES:
        raise ValueError("默认模式无效。")
    if not 1 <= daily_request_limit <= 500:
        raise ValueError("每日调用上限必须在 1–500 次之间。")
    if not 10_000 <= daily_token_limit <= 10_000_000:
        raise ValueError("每日 Token 上限必须在 10,000–10,000,000 之间。")
    effective_key, _ = effective_api_key(config)
    if enabled and not consent:
        raise ValueError("启用 DeepSeek 前必须确认数据发送边界。")
    if enabled and not effective_key:
        raise ValueError("启用 DeepSeek 前必须先填写 API Key。")

    config.base_url = OFFICIAL_BASE_URL
    config.fast_model = settings.deepseek_fast_model
    config.precision_model = settings.deepseek_precision_model
    config.default_mode = default_mode
    config.enabled = enabled
    config.consent_to_external_processing = consent
    config.daily_request_limit = daily_request_limit
    config.daily_token_limit = daily_token_limit
    config.last_error = ""
    config.circuit_open_until = None
    config.consecutive_failures = 0
    db.add(config)
    db.flush()
    return config


def revoke_database_key(db: Session, user_id: int) -> AIProviderConfig:
    config = get_or_create_config(db, user_id)
    config.api_key = ""
    config.enabled = False
    config.consent_to_external_processing = False
    config.last_error = ""
    config.last_tested_at = None
    config.last_success_at = None
    config.circuit_open_until = None
    config.consecutive_failures = 0
    db.add(config)
    db.flush()
    return config


async def verify_connection(
    db: Session,
    *,
    user_id: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderView:
    config = get_or_create_config(db, user_id)
    key, _ = effective_api_key(config)
    if not key:
        raise AIProviderError("missing_key", "尚未配置 DeepSeek API Key。")
    if not config.consent_to_external_processing:
        raise AIProviderError("consent_required", "请先确认数据发送边界。")

    config.last_tested_at = datetime.now(timezone.utc)
    try:
        response, duration_ms = await _request_json(
            api_key=key,
            model=config.fast_model,
            mode="fast",
            messages=[
                {
                    "role": "system",
                    "content": "Return one valid JSON object only. Do not include markdown.",
                },
                {
                    "role": "user",
                    "content": 'Return exactly this JSON object: {"status":"ok"}',
                },
            ],
            max_tokens=64,
            timeout_seconds=config.request_timeout_seconds,
            user_id=user_id,
            transport=transport,
        )
        content = _response_content(response)
        parsed = _parse_json_object(content)
        if parsed.get("status") != "ok":
            raise AIProviderError("unexpected_response", "DeepSeek 已响应，但验证内容不符合预期。")
        usage = _extract_usage(response)
        _record_usage(
            db,
            user_id=user_id,
            job_id=None,
            operation="connection_test",
            model=config.fast_model,
            mode="fast",
            status="success",
            duration_ms=duration_ms,
            **usage,
        )
        _mark_success(config)
    except AIProviderError as exc:
        _record_usage(
            db,
            user_id=user_id,
            job_id=None,
            operation="connection_test",
            model=config.fast_model,
            mode="fast",
            status="failed",
            error_code=exc.code,
        )
        _mark_failure(config, exc)
        db.add(config)
        db.flush()
        raise
    db.add(config)
    db.flush()
    return provider_view(db, user_id)


async def enhance_application(
    db: Session,
    *,
    user_id: int,
    profile: CandidateProfile,
    job: Job,
    rule_result: AnalysisResult,
    resume: Resume | None,
    experiences: list[Experience],
    application_pack: ApplicationPack,
    requested_mode: str | None = None,
    force: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EnhancementOutcome:
    config = get_or_create_config(db, user_id)
    key, _ = effective_api_key(config)
    if not config.enabled or not config.consent_to_external_processing or not key:
        return EnhancementOutcome(
            status="not_configured",
            enhancement=None,
            user_message="DeepSeek 尚未启用；已使用可解释规则完成分析。",
        )

    mode = requested_mode if requested_mode in ALLOWED_MODES else config.default_mode
    if mode not in ALLOWED_MODES:
        mode = "fast"
    model = config.precision_model if mode == "precision" else config.fast_model
    if model not in ALLOWED_MODELS:
        model = settings.deepseek_precision_model if mode == "precision" else settings.deepseek_fast_model

    existing = db.scalar(
        select(AIApplicationEnhancement).where(AIApplicationEnhancement.job_id == job.id)
    )
    if existing and existing.status == "success" and existing.mode == mode and not force:
        return EnhancementOutcome(status="cached", enhancement=existing, user_message="已使用现有 DeepSeek 分析。")

    try:
        _enforce_runtime_limits(db, config)
        response, duration_ms = await _request_json(
            api_key=key,
            model=model,
            mode=mode,
            messages=_build_messages(
                config=config,
                profile=profile,
                job=job,
                rule_result=rule_result,
                resume=resume,
                experiences=experiences,
            ),
            max_tokens=settings.deepseek_max_output_tokens,
            timeout_seconds=config.request_timeout_seconds,
            user_id=user_id,
            transport=transport,
        )
        payload = _validate_enhancement_payload(_parse_json_object(_response_content(response)))
        usage = _extract_usage(response)
        enhancement = existing or AIApplicationEnhancement(user_id=user_id, job_id=job.id)
        enhancement.provider = "deepseek"
        enhancement.model = model
        enhancement.mode = mode
        enhancement.status = "success"
        enhancement.prompt_version = PROMPT_VERSION
        enhancement.content_json = json_dumps(_payload_dict(payload))
        enhancement.usage_json = json_dumps({**usage, "duration_ms": duration_ms})
        enhancement.error_message = ""
        enhancement.generated_at = datetime.now(timezone.utc)
        db.add(enhancement)

        # The AI may improve prose, but cannot change hard eligibility or the rule-engine recommendation.
        if not application_pack.user_reviewed:
            application_pack.fit_summary = (
                f"规则结论：{rule_result.recommendation} / {rule_result.fit_label} / "
                f"{rule_result.eligibility_status}。\n\nDeepSeek 语义说明：{payload.summary_zh}"
            )
            application_pack.why_role_draft = payload.why_role_en
            application_pack.why_company_draft = payload.why_company_en
            db.add(application_pack)

        _record_usage(
            db,
            user_id=user_id,
            job_id=job.id,
            operation="job_enhancement",
            model=model,
            mode=mode,
            status="success",
            duration_ms=duration_ms,
            **usage,
        )
        _mark_success(config)
        db.add(config)
        db.flush()
        return EnhancementOutcome(
            status="success",
            enhancement=enhancement,
            user_message="DeepSeek 已完成语义增强；硬性资格结论仍由规则引擎控制。",
        )
    except AIProviderError as exc:
        has_previous = bool(
            existing
            and existing.status in {"success", "stale"}
            and existing.content_json
            and existing.content_json != "{}"
        )
        enhancement = existing or AIApplicationEnhancement(user_id=user_id, job_id=job.id)
        enhancement.provider = "deepseek"
        if has_previous:
            enhancement.status = "stale"
            enhancement.error_message = exc.user_message
        else:
            enhancement.model = model
            enhancement.mode = mode
            enhancement.status = "failed"
            enhancement.prompt_version = PROMPT_VERSION
            enhancement.error_message = exc.user_message
            enhancement.generated_at = datetime.now(timezone.utc)
        db.add(enhancement)
        _record_usage(
            db,
            user_id=user_id,
            job_id=job.id,
            operation="job_enhancement",
            model=model,
            mode=mode,
            status="failed",
            error_code=exc.code,
        )
        _mark_failure(config, exc)
        db.add(config)
        db.flush()
        retained = "上一次成功的 AI 结果也已保留。" if has_previous else ""
        return EnhancementOutcome(
            status="failed",
            enhancement=enhancement,
            user_message=f"{exc.user_message} 已保留规则分析和原申请包。{retained}",
        )


def get_job_enhancement(db: Session, user_id: int, job_id: int) -> AIApplicationEnhancement | None:
    return db.scalar(
        select(AIApplicationEnhancement).where(
            AIApplicationEnhancement.user_id == user_id,
            AIApplicationEnhancement.job_id == job_id,
        )
    )


def _enforce_runtime_limits(db: Session, config: AIProviderConfig) -> None:
    now = datetime.now(timezone.utc)
    circuit = _aware(config.circuit_open_until)
    if circuit and circuit > now:
        raise AIProviderError(
            "circuit_open",
            f"DeepSeek 已临时暂停到 {circuit.strftime('%H:%M UTC')}，规则分析仍可使用。",
        )
    usage = usage_today(db, config.user_id)
    if usage.requests >= config.daily_request_limit:
        raise AIProviderError(
            "daily_request_limit",
            "今天的 DeepSeek 调用次数已达到你设置的上限。",
        )
    if usage.total_tokens >= config.daily_token_limit:
        raise AIProviderError(
            "daily_token_limit",
            "今天的 DeepSeek Token 使用量已达到你设置的上限。",
        )


def _build_messages(
    *,
    config: AIProviderConfig,
    profile: CandidateProfile,
    job: Job,
    rule_result: AnalysisResult,
    resume: Resume | None,
    experiences: list[Experience],
) -> list[dict[str, str]]:
    limit = max(5_000, min(config.max_input_characters, settings.deepseek_max_input_characters))
    job_limit = max(4_000, int(limit * 0.55))
    resume_limit = max(2_000, int(limit * 0.25))
    experience_limit = max(800, int(limit * 0.05))

    def safe(value: Any, max_chars: int | None = None) -> str:
        clean = _redact_for_provider(str(value or ""), profile)
        return _truncate(clean, max_chars) if max_chars else clean

    def safe_list(values: list[str], max_items: int = 30) -> list[str]:
        return [safe(item) for item in values[:max_items] if safe(item).strip()]

    payload = {
        "privacy_note": (
            "Direct candidate identifiers, account credentials, raw file bytes and provider secrets "
            "have been removed before this request."
        ),
        "candidate_constraints": {
            "target_roles": safe(profile.target_roles),
            "secondary_roles": safe(profile.secondary_roles),
            "roles_to_avoid": safe(profile.roles_to_avoid),
            "target_locations": safe(profile.target_locations),
            "work_mode": safe(profile.work_mode),
            "target_level": safe(profile.target_level),
            "graduation_year": profile.graduation_year,
            "professional_experience_years": profile.professional_experience_years,
            "degree_summary": safe(profile.degree_summary, 1000),
            "work_authorization_country": safe(profile.work_authorization_country),
            # This is user-authored eligibility context, not identity evidence; it is still redacted and bounded.
            "work_authorization_text": safe(profile.work_authorization_text, 1000),
            "sponsorship_now": profile.sponsorship_now,
            "sponsorship_future": profile.sponsorship_future,
        },
        "deterministic_rule_result": {
            "recommendation": rule_result.recommendation,
            "fit_label": rule_result.fit_label,
            "eligibility_status": rule_result.eligibility_status,
            "freshness_status": rule_result.freshness_status,
            "application_effort": rule_result.application_effort,
            "reasons": safe_list(rule_result.reasons, 20),
            "risks": safe_list(rule_result.risks, 20),
            "unknowns": safe_list(rule_result.unknowns, 20),
            "matched_skills": safe_list(rule_result.matched_skills, 80),
            "missing_skills": safe_list(rule_result.missing_skills, 80),
        },
        "selected_resume": {
            "label": safe(resume.label if resume else ""),
            "role_family": safe(resume.role_family if resume else ""),
            "skills": safe_list(resume.skills[:80] if resume else [], 80),
            "text": safe(_resume_without_contact_header(resume.extracted_text if resume else ""), resume_limit),
        },
        "selected_experiences": [
            {
                "title": safe(item.title, 180),
                "organization": safe(item.organization, 180),
                "date_range": safe(item.date_range, 100),
                "description": safe(item.description, experience_limit),
                "tags": safe_list(item.tags, 30),
            }
            for item in experiences[:4]
        ],
        "job": {
            "company": safe(job.company, 300),
            "title": safe(job.title, 300),
            "location": safe(job.location, 300),
            "posted_date": safe(job.posted_date, 100),
            "source": safe(job.source, 100),
            "description": safe(job.description, job_limit),
        },
        "required_json_schema": {
            "summary_zh": "string",
            "reasons_zh": ["string"],
            "risks_zh": ["string"],
            "questions_for_user_zh": ["string"],
            "matched_skills": ["string"],
            "missing_skills": ["string"],
            "why_role_en": "string",
            "why_company_en": "string",
            "confidence": "high|medium|low",
            "suggested_action": "Apply|Review|Needs user|Skip",
        },
    }
    system_message = (
        "You are an evidence-constrained candidate-side job analyst. Use only supplied facts. "
        "Never invent or strengthen work authorization, sponsorship, dates, grades, metrics, employers, "
        "experience, skills, company facts or role facts. The deterministic rule result is authoritative for "
        "hard eligibility and cannot be overridden. If evidence is missing, put it in questions_for_user_zh. "
        "Generate Chinese analysis and English application drafts. why_company_en may only rely on the supplied "
        "job posting and must not pretend to know the employer website or culture. Return one valid JSON object "
        "matching required_json_schema, without markdown or extra keys."
    )
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]


async def _request_json(
    *,
    api_key: str,
    model: str,
    mode: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_seconds: int,
    user_id: int,
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[dict[str, Any], int]:
    if model not in ALLOWED_MODELS:
        raise AIProviderError("invalid_model", "DeepSeek 模型配置无效。")
    thinking_enabled = mode == "precision"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
        "max_tokens": max(64, min(int(max_tokens), 12_000)),
        "stream": False,
    }
    if thinking_enabled:
        payload["reasoning_effort"] = "high"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout = httpx.Timeout(connect=10, read=timeout_seconds, write=20, pool=10)
    retry_statuses = {429, 500, 503}
    started = time.monotonic()
    last_response: httpx.Response | None = None

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                transport=transport,
            ) as client:
                response = await client.post(
                    OFFICIAL_BASE_URL + "/chat/completions",
                    headers=headers,
                    json=payload,
                )
            last_response = response
        except httpx.TimeoutException as exc:
            if attempt == 0:
                await asyncio.sleep(0.25)
                continue
            raise AIProviderError("timeout", "DeepSeek 响应超时。", retryable=True) from exc
        except httpx.NetworkError as exc:
            if attempt == 0:
                await asyncio.sleep(0.25)
                continue
            raise AIProviderError("network_error", "无法连接 DeepSeek。", retryable=True) from exc
        if response.status_code in retry_statuses and attempt == 0:
            await asyncio.sleep(0.4)
            continue
        break

    duration_ms = int((time.monotonic() - started) * 1000)
    if last_response is None:
        raise AIProviderError("network_error", "无法连接 DeepSeek。", retryable=True)
    response = last_response
    if response.status_code == 400:
        raise AIProviderError("invalid_request", "DeepSeek 拒绝了请求格式；规则分析仍可使用。")
    if response.status_code == 401:
        raise AIProviderError("invalid_key", "DeepSeek API Key 无效或已失效。")
    if response.status_code == 402:
        raise AIProviderError("insufficient_balance", "DeepSeek 账户余额不足。")
    if response.status_code in {403, 422}:
        raise AIProviderError("account_or_parameter_error", "DeepSeek 账户权限或参数不允许本次调用。")
    if response.status_code == 429:
        raise AIProviderError("rate_limited", "DeepSeek 当前请求过多。", retryable=True)
    if response.status_code in {500, 503}:
        raise AIProviderError("provider_unavailable", "DeepSeek 服务暂时不可用。", retryable=True)
    if response.status_code >= 400:
        raise AIProviderError("request_failed", f"DeepSeek 请求失败（HTTP {response.status_code}）。")
    try:
        body = response.json()
    except ValueError as exc:
        raise AIProviderError("invalid_response", "DeepSeek 返回了无法读取的响应。") from exc
    if not isinstance(body, dict):
        raise AIProviderError("invalid_response", "DeepSeek 返回结构无效。")
    return body, duration_ms


def _response_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError("invalid_response", "DeepSeek 响应缺少有效内容。") from exc
    if not isinstance(content, str) or not content.strip():
        raise AIProviderError("empty_response", "DeepSeek 返回内容为空。")
    return content.strip()


def _parse_json_object(content: str) -> dict[str, Any]:
    clean = content.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        value = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise AIProviderError("invalid_json", "DeepSeek 返回内容不是有效 JSON。") from exc
    if not isinstance(value, dict):
        raise AIProviderError("invalid_json", "DeepSeek 返回内容不是 JSON object。")
    return value


def _validate_enhancement_payload(value: dict[str, Any]) -> EnhancementPayload:
    confidence = str(value.get("confidence", "medium")).strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    action = str(value.get("suggested_action", "Review")).strip()
    if action not in {"Apply", "Review", "Needs user", "Skip"}:
        action = "Review"
    return EnhancementPayload(
        summary_zh=_required_text(value.get("summary_zh"), 2000, "summary_zh"),
        reasons_zh=_string_list(value.get("reasons_zh"), 8, 800),
        risks_zh=_string_list(value.get("risks_zh"), 8, 800),
        questions_for_user_zh=_string_list(value.get("questions_for_user_zh"), 8, 800),
        matched_skills=_string_list(value.get("matched_skills"), 30, 120),
        missing_skills=_string_list(value.get("missing_skills"), 30, 120),
        why_role_en=_required_text(value.get("why_role_en"), 5000, "why_role_en"),
        why_company_en=_required_text(value.get("why_company_en"), 5000, "why_company_en"),
        confidence=confidence,
        suggested_action=action,
    )


def _payload_dict(payload: EnhancementPayload) -> dict[str, Any]:
    return {
        "summary_zh": payload.summary_zh,
        "reasons_zh": payload.reasons_zh,
        "risks_zh": payload.risks_zh,
        "questions_for_user_zh": payload.questions_for_user_zh,
        "matched_skills": payload.matched_skills,
        "missing_skills": payload.missing_skills,
        "why_role_en": payload.why_role_en,
        "why_company_en": payload.why_company_en,
        "confidence": payload.confidence,
        "suggested_action": payload.suggested_action,
    }


def _required_text(value: Any, limit: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AIProviderError("invalid_payload", f"DeepSeek 返回的 {field} 无效。")
    return value.strip()[:limit]


def _string_list(value: Any, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        clean = item.strip()[:max_chars]
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
        if len(result) >= max_items:
            break
    return result


def _extract_usage(response: dict[str, Any]) -> dict[str, int]:
    raw = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    prompt = _nonnegative_int(raw.get("prompt_tokens"))
    completion = _nonnegative_int(raw.get("completion_tokens"))
    total = _nonnegative_int(raw.get("total_tokens")) or prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _record_usage(
    db: Session,
    *,
    user_id: int,
    job_id: int | None,
    operation: str,
    model: str,
    mode: str,
    status: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
    error_code: str = "",
) -> None:
    db.add(
        AIUsageRecord(
            user_id=user_id,
            job_id=job_id,
            operation=operation[:80],
            provider="deepseek",
            model=model[:100],
            mode=mode,
            status=status,
            prompt_tokens=max(0, int(prompt_tokens)),
            completion_tokens=max(0, int(completion_tokens)),
            total_tokens=max(0, int(total_tokens)),
            duration_ms=max(0, int(duration_ms)),
            error_code=error_code[:80],
        )
    )


def _mark_success(config: AIProviderConfig) -> None:
    now = datetime.now(timezone.utc)
    config.last_success_at = now
    config.last_error = ""
    config.consecutive_failures = 0
    config.circuit_open_until = None


def _mark_failure(config: AIProviderConfig, error: AIProviderError) -> None:
    config.last_error = error.user_message
    config.consecutive_failures += 1
    threshold = max(1, settings.deepseek_circuit_breaker_failures)
    should_open = config.consecutive_failures >= threshold or error.code in {
        "invalid_key",
        "insufficient_balance",
    }
    if should_open:
        minutes = 30 if error.code in {"invalid_key", "insufficient_balance"} else max(
            1, settings.deepseek_circuit_breaker_minutes
        )
        config.circuit_open_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)


_RESUME_SECTION_RE = re.compile(
    r"^(?:experience|work experience|employment|projects?|education|skills?|certifications?|awards?|实习经历|工作经历|项目经历|教育经历|技能|证书)\s*:?$",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


def _resume_without_contact_header(text: str) -> str:
    """Drop the typical name/contact header before sending resume evidence externally."""
    lines = text.splitlines()
    for index, line in enumerate(lines[:40]):
        if _RESUME_SECTION_RE.match(line.strip()):
            return "\n".join(lines[index:]).strip()
    return text.strip()


def _redact_for_provider(text: str, profile: CandidateProfile) -> str:
    """Remove direct identifiers from model-bound text, including identifiers embedded in resumes."""
    clean = str(text or "")
    exact_values = {
        profile.preferred_name,
        profile.legal_name,
        profile.email,
        profile.phone,
        profile.current_location,
        profile.linkedin_url,
        profile.github_url,
        profile.portfolio_url,
    }
    for value in sorted((item.strip() for item in exact_values if item and item.strip()), key=len, reverse=True):
        clean = re.sub(re.escape(value), "[REDACTED]", clean, flags=re.IGNORECASE)
    clean = _EMAIL_RE.sub("[REDACTED_EMAIL]", clean)
    clean = _PHONE_RE.sub("[REDACTED_PHONE]", clean)
    clean = _URL_RE.sub("[REDACTED_URL]", clean)
    return clean


def _truncate(text: str, limit: int) -> str:
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    head = int(limit * 0.7)
    tail = limit - head
    return clean[:head] + "\n…[truncated]…\n" + clean[-tail:]


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
