from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationPack, CandidateProfile, Experience, Job, Resume, json_dumps
from app.services.analyzer import AnalysisResult, build_application_drafts


def create_or_refresh_pack(
    db: Session,
    *,
    user_id: int,
    profile: CandidateProfile,
    job: Job,
    result: AnalysisResult,
) -> ApplicationPack:
    experiences = list(
        db.scalars(
            select(Experience).where(
                Experience.user_id == user_id,
                Experience.id.in_(result.selected_experience_ids or [-1]),
            )
        )
    )
    order = {item_id: index for index, item_id in enumerate(result.selected_experience_ids)}
    experiences.sort(key=lambda item: order.get(item.id, 999))
    drafts = build_application_drafts(
        profile=profile,
        job=job,
        result=result,
        selected_experiences=experiences,
    )

    pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job.id))
    if not pack:
        pack = ApplicationPack(user_id=user_id, job_id=job.id)
    pack.resume_id = result.selected_resume_id
    pack.experience_ids_json = json_dumps(result.selected_experience_ids)
    pack.fit_summary = drafts.fit_summary
    pack.why_role_draft = drafts.why_role
    pack.why_company_draft = drafts.why_company
    pack.work_authorization_answer = drafts.work_authorization
    pack.sponsorship_answer = drafts.sponsorship
    pack.salary_answer = drafts.salary
    pack.checklist_json = json_dumps(drafts.checklist)
    pack.user_reviewed = False
    db.add(pack)
    db.flush()
    return pack


def pack_as_markdown(
    *,
    job: Job,
    pack: ApplicationPack,
    resume: Resume | None,
    experiences: list[Experience],
) -> str:
    experience_lines = "\n".join(
        f"- {item.title} — {item.organization}: {item.description[:500]}" for item in experiences
    ) or "- 尚未选择经历"
    checklist_lines = "\n".join(f"- [ ] {item}" for item in pack.checklist)
    return f"""# {job.company} — {job.title} 申请包

## 决策摘要

{pack.fit_summary}

- 岗位链接：{job.url or '未提供'}
- 推荐：{job.recommendation}
- 匹配：{job.fit_label}
- 资格：{job.eligibility_status}
- 简历版本：{resume.label if resume else '尚未选择'}

## 建议重点经历

{experience_lines}

## Why this role（草稿，提交前复核）

{pack.why_role_draft}

## Why this company（草稿，提交前补充官网事实）

{pack.why_company_draft}

## 工作权利

{pack.work_authorization_answer}

## Sponsorship

{pack.sponsorship_answer}

## 薪资回答策略

{pack.salary_answer}

## 提交前检查

{checklist_lines}

## 记录规则

只有在官方页面看到明确成功信息、确认页面或申请编号后，才将状态改为 Applied。收藏、保存、填完表单或点击按钮但没有成功证据，都不算已提交。
"""
