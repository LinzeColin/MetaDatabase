#!/usr/bin/env python3
"""Deterministically build ADP v1.2 historical traceability from locked inputs."""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path


FIELDS = [
    "source_family",
    "source_id",
    "source_title",
    "source_status",
    "disposition",
    "disposition_reason",
    "current_evidence",
    "v1_2_task_ids",
    "v1_2_acceptance_ids",
    "source_ref",
]
ALLOWED = {
    "INHERITED_PROVEN",
    "V1_2_ACTIVE",
    "SUPERSEDED_WITH_REASON",
    "OUT_OF_SCOPE_OWNER_DECISION",
    "UNKNOWN_BLOCKED",
}


def add(rows, family, source_id, title, source_status, disposition, reason,
        evidence, tasks, acceptances, source_ref):
    if disposition not in ALLOWED:
        raise ValueError(f"invalid disposition: {disposition}")
    rows.append({
        "source_family": family,
        "source_id": source_id,
        "source_title": title,
        "source_status": source_status,
        "disposition": disposition,
        "disposition_reason": reason,
        "current_evidence": evidence,
        "v1_2_task_ids": tasks,
        "v1_2_acceptance_ids": acceptances,
        "source_ref": source_ref,
    })


def old_task_mapping(task_id: str, stage: str):
    active = {
        "ADP-S1-P02-T012": ("ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-005;ACC-V12-S2-001;ACC-V12-S3-001"),
        "ADP-S1-P02-T013": ("ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-005;ACC-V12-S2-002;ACC-V12-S3-001"),
        "ADP-S1-P02-T014": ("ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-005;ACC-V12-S2-001;ACC-V12-S3-001"),
        "ADP-S1-P02-T015": ("ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-005;ACC-V12-S2-001;ACC-V12-S3-001"),
        "ADP-S1-P03-T016": ("ADP-V12-S4-T001", "ACC-V12-S4-001"),
        "ADP-S1-P03-T017": ("ADP-V12-S4-T001", "ACC-V12-S4-001"),
        "ADP-S1-P03-T018": ("ADP-V12-S4-T001", "ACC-V12-S4-001;ACC-V12-S4-002"),
        "ADP-S1-P03-T019": ("ADP-V12-S4-T001", "ACC-V12-S4-002"),
        "ADP-S1-P03-T020": ("ADP-V12-S4-T001", "ACC-V12-S4-001;ACC-V12-S4-002"),
        "ADP-S3-P01-T031": ("ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-001;ACC-V12-S2-001;ACC-V12-S3-001"),
        "ADP-S3-P01-T032": ("ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-001;ACC-V12-S2-001;ACC-V12-S3-002"),
        "ADP-S3-P02-T035": ("ADP-V12-S2-T001", "ACC-V12-S2-001;ACC-V12-S2-002"),
        "ADP-S3-P03-T038": ("ADP-V12-S1-T001", "ACC-V12-S1-001;ACC-V12-S1-004"),
        "ADP-S5-P03-T063": ("ADP-V12-S3-T001", "ACC-V12-S3-001;ACC-V12-S3-002"),
        "ADP-S7-P01-T077": ("ADP-V12-S4-T003", "ACC-V12-S4-004;ACC-V12-S4-005"),
        "ADP-S7-P01-T078": ("ADP-V12-S4-T003", "ACC-V12-S4-005"),
        "ADP-S7-P02-T079": ("ADP-V12-S4-T002", "ACC-V12-S4-003"),
        "ADP-S7-P02-T080": ("ADP-V12-S4-T002;ADP-V12-S4-T003", "ACC-V12-S4-003;ACC-V12-S4-006"),
        "ADP-S7-P03-T081": ("ADP-V12-S5-T002", "ACC-V12-S5-002"),
        "ADP-S7-P03-T082": ("ADP-V12-S4-T003", "ACC-V12-S4-004;ACC-V12-S4-006"),
        "ADP-S7-P03-T083": ("ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-004;ACC-V12-S6-001"),
        "ADP-S7-P04-T084": ("ADP-V12-S4-T001;ADP-V12-S4-T003", "ACC-V12-S4-001;ACC-V12-S4-006"),
        "ADP-S8-P01-T085": ("ADP-V12-S6-T001", "ACC-V12-S6-001;ACC-V12-S6-002"),
        "ADP-S8-P01-T086": ("ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-003;ACC-V12-S6-002"),
        "ADP-S8-P01-T087": ("ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-004;ACC-V12-S6-003"),
        "ADP-S8-P02-T088": ("ADP-V12-S6-T001", "ACC-V12-S6-002;ACC-V12-S6-003"),
        "ADP-S8-P02-T089": ("ADP-V12-S6-T001", "ACC-V12-S6-005"),
        "ADP-S8-P03-T090": ("ADP-V12-S6-T001", "ACC-V12-S6-001;ACC-V12-S6-006"),
    }
    inherited = {
        "ADP-S0-P02-T004", "ADP-S0-P02-T005", "ADP-S0-P02-T006",
        "ADP-S0-P02-T007", "ADP-S1-P01-T009", "ADP-S1-P01-T010",
        "ADP-S1-P01-T011",
    }
    governance_superseded = {
        "ADP-S0-P01-T001", "ADP-S0-P01-T002", "ADP-S0-P01-T003",
        "ADP-S0-P03-T008",
    }
    if task_id in active:
        tasks, acceptances = active[task_id]
        return (
            "V1_2_ACTIVE",
            "该历史能力仍影响 v1.2，但以更小、可验证的当前 Task 和 Oracle 重述。",
            "arxiv-daily-push/docs/pursuing_goal/v1_2/TECHNICAL_DESIGN.md",
            tasks,
            acceptances,
        )
    if task_id in inherited:
        return (
            "INHERITED_PROVEN",
            "迁移闭合验收已证明当前仓位、live/build、治理或机器事实；v1.2 只做回归保护。",
            "arxiv-daily-push/docs/HANDOFF.md;arxiv-daily-push/docs/archive/taskpacks/2026-07-20/ADP_META_MIGRATION_e1af471c_2026-07-20_acceptance_review_taskpack.zip",
            "ADP-V12-S0-T001;ADP-V12-S6-T001",
            "ACC-V12-S0-004;ACC-V12-S6-001",
        )
    if task_id in governance_superseded:
        return (
            "SUPERSEDED_WITH_REASON",
            "旧任务是 v0.1 包装/治理实施步骤；由 v1.2 七角色合同、追溯和 verifier 双摘要替代。",
            "arxiv-daily-push/docs/pursuing_goal/v1_2/README.md",
            "ADP-V12-S0-T001",
            "ACC-V12-S0-001;ACC-V12-S0-003",
        )
    if stage == "S6" or task_id in {
        "ADP-S4-P02-T045", "ADP-S4-P02-T046", "ADP-S4-P02-T047",
        "ADP-S4-P02-T048", "ADP-S4-P03-T049", "ADP-S4-P03-T050",
        "ADP-S4-P03-T051", "ADP-S4-P03-T052", "ADP-S4-P04-T053",
        "ADP-S4-P04-T054", "ADP-S4-P04-T055",
    }:
        return (
            "OUT_OF_SCOPE_OWNER_DECISION",
            "v1.2 是来源救援、内容/UI 和运行可靠性增量版；预测或大规模 A0/A1/A2 扩张不在本版本执行范围。",
            "arxiv-daily-push/docs/pursuing_goal/v1_2/PRD.md#4-非目标",
            "ADP-V12-S0-T001",
            "ACC-V12-S0-003",
        )
    return (
        "SUPERSEDED_WITH_REASON",
        "该历史实施步骤保留在 v0.1 谱系，但 v1.2 不重新声明其完成；既有行为只受当前回归门保护。",
        "arxiv-daily-push/docs/pursuing_goal/v1_2/PRD.md;arxiv-daily-push/docs/pursuing_goal/v1_2/ACCEPTANCE_CONTRACT.yaml",
        "ADP-V12-S0-T001;ADP-V12-S6-T001",
        "ACC-V12-S0-003;ACC-V12-S6-001",
    )


REQ_MAP = {
    "REQ-001": ("V1_2_ACTIVE", "增量开发与 canary/rollback 继续禁止 big-bang。", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-005;ACC-V12-S6-002"),
    "REQ-002": ("SUPERSEDED_WITH_REASON", "Owner 已把来源救援、移动端、视觉和运维纳入 v1.2，旧的仅问题 2/3 范围不再当前。", "ADP-V12-S0-T001", "ACC-V12-S0-003"),
    "REQ-003": ("V1_2_ACTIVE", "中国官方来源等级和原文证据边界继续适用，stats/source 变更需回归。", "ADP-V12-S2-T001;ADP-V12-S6-T001", "ACC-V12-S2-002;ACC-V12-S6-001"),
    "REQ-004": ("SUPERSEDED_WITH_REASON", "v1.2 不新做 2016+ 批量回填；现有历史不可倒退，未来扩张另开版本。", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-003;ACC-V12-S6-001"),
    "REQ-005": ("V1_2_ACTIVE", "现有 D1/R2 原始证据不改，发布/恢复门必须保护数据不变量。", "ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-003;ACC-V12-S6-002"),
    "REQ-006": ("V1_2_ACTIVE", "7fd finding F-005 直接进入中文人话版闭合。", "ADP-V12-S4-T001", "ACC-V12-S4-001;ACC-V12-S4-002"),
    "REQ-007": ("V1_2_ACTIVE", "版本、来源、cron 和 build 身份在 v1.2 对齐并回归。", "ADP-V12-S1-T001;ADP-V12-S5-T001;ADP-V12-S5-T002", "ACC-V12-S1-005;ACC-V12-S5-001;ACC-V12-S5-004"),
    "REQ-008": ("SUPERSEDED_WITH_REASON", "v1.2 保留现有板块，不新增知识图谱/全面性声明。", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-003;ACC-V12-S6-001"),
    "REQ-009": ("OUT_OF_SCOPE_OWNER_DECISION", "预测与回测不在 v1.2 关键路径，本版本不新增或放行预测能力。", "ADP-V12-S0-T001", "ACC-V12-S0-003"),
    "REQ-010": ("V1_2_ACTIVE", "前端 v1.1 与 7fd finding F-006/F-007 纳入六主题、导航和视觉门。", "ADP-V12-S4-T002;ADP-V12-S4-T003", "ACC-V12-S4-003;ACC-V12-S4-004;ACC-V12-S4-005;ACC-V12-S4-006"),
    "REQ-011": ("OUT_OF_SCOPE_OWNER_DECISION", "竞品 131 项扩张不在 v1.2，禁止为 parity 扩大入口。", "ADP-V12-S0-T001", "ACC-V12-S0-003"),
    "REQ-012": ("V1_2_ACTIVE", "免费档容量、SLO 与升级提案构成当前 Value-Cost Gate。", "ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-004;ACC-V12-S6-003"),
    "REQ-013": ("V1_2_ACTIVE", "UNKNOWN/缺证据失败关闭适用于全部任务和部署。", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-003;ACC-V12-S6-003"),
    "REQ-014": ("V1_2_ACTIVE", "WIP=1、回滚和独立 verifier 是永久执行门。", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-001;ACC-V12-S6-006"),
    "REQ-015": ("INHERITED_PROVEN", "现有 realtime 优先边界不在 S0 修改，发布阶段按 full-suite/运行门保护。", "ADP-V12-S6-T001", "ACC-V12-S6-001"),
    "REQ-016": ("V1_2_ACTIVE", "v1.2 明确 RTO/RPO、恢复演练和自动回滚。", "ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-003;ACC-V12-S6-002"),
    "REQ-017": ("V1_2_ACTIVE", "Google/stats 来源仍必须给出 provenance 和来源同步证据。", "ADP-V12-S1-T001;ADP-V12-S2-T001", "ACC-V12-S1-005;ACC-V12-S2-002"),
    "REQ-018": ("SUPERSEDED_WITH_REASON", "v1.2 不新增 as-of/版本视图；既有行为只做发布回归，不声称完成旧扩张任务。", "ADP-V12-S6-T001", "ACC-V12-S6-001"),
    "REQ-019": ("V1_2_ACTIVE", "不加新服务，Google/Stats/PubMed 均采用最小 adapter 与免费边界。", "ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-005;ACC-V12-S2-003;ACC-V12-S3-003"),
    "REQ-020": ("V1_2_ACTIVE", "SLO、探针覆盖、capacity 和 14 日 soak 都要求原始测量。", "ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-002;ACC-V12-S5-004;ACC-V12-S6-005"),
}


FRONTEND_ROWS = [
    ("FE-V11-001", "六主题必须具有独立视觉语言", "ADP-V12-S4-T003", "ACC-V12-S4-004"),
    ("FE-V11-002", "简约专注、炫技、森林三个视频主题真实 autoplay/muted/loop", "ADP-V12-S4-T003", "ACC-V12-S4-004"),
    ("FE-V11-003", "prefers-reduced-motion 停止视频和装饰动效但保留功能", "ADP-V12-S4-T003", "ACC-V12-S4-006"),
    ("FE-V11-004", "小于 780px 统一今天/队列/雷达/系统四标签", "ADP-V12-S4-T002", "ACC-V12-S4-003"),
    ("FE-V11-005", "冷加载 console error 为零", "ADP-V12-S4-T003", "ACC-V12-S4-006"),
    ("FE-V11-006", "桌面 sidebar/topbar/dock 导航结构保持", "ADP-V12-S4-T002", "ACC-V12-S4-003"),
    ("FE-V11-007", "不得用新框架或统一换肤替换六主题结构", "ADP-V12-S4-T003", "ACC-V12-S4-004"),
    ("FE-V11-008", "生产视频资产身份和可用性可验证，不依赖无证据占位 URL", "ADP-V12-S4-T003;ADP-V12-S6-T001", "ACC-V12-S4-004;ACC-V12-S6-004"),
    ("FE-V11-009", "宇宙仪表盘读数与当日真实数据一致", "ADP-V12-S4-T003;ADP-V12-S6-T001", "ACC-V12-S4-005;ACC-V12-S6-004"),
]


OLD_FINDINGS = [
    ("F-001", "任务包 Pursuing Goal 角色名不被 verifier 识别", "INHERITED_PROVEN", "e1af 后 v1.2 使用 PURSUING_GOAL.md 和七角色 ingest。", "ADP-V12-S0-T001", "ACC-V12-S0-001"),
    ("F-002", "权威合同优先级冲突", "INHERITED_PROVEN", "迁移 HANDOFF 已建立唯一当前路由，v1.2 显式 authority_order。", "ADP-V12-S0-T001", "ACC-V12-S0-004"),
    ("F-003", "MetaDatabase 根契约仍称 ADP 未迁移", "INHERITED_PROVEN", "e1af 迁移闭合验收 PASS，根 AGENTS 已路由 canonical ADP。", "ADP-V12-S0-T001", "ACC-V12-S0-004"),
    ("F-004", "迁移导致治理/full-suite 扩大失败", "INHERITED_PROVEN", "e1af 证明 65/65、14/14 且 candidate-only failure/error 为零。", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-004;ACC-V12-S6-001"),
    ("F-005", "人话版仍是英文摘要", "V1_2_ACTIVE", "保留为 v1.2 阻断 UX 缺陷。", "ADP-V12-S4-T001", "ACC-V12-S4-001;ACC-V12-S4-002"),
    ("F-006", "移动端未实现 Owner 四标签底栏", "V1_2_ACTIVE", "保留为六主题移动端阻断缺陷。", "ADP-V12-S4-T002", "ACC-V12-S4-003"),
    ("F-007", "强制视觉门在 canonical worker 上 BLOCK 且 pixel 未 enforce", "V1_2_ACTIVE", "重建可承重视觉/负控门。", "ADP-V12-S4-T003", "ACC-V12-S4-005"),
    ("F-008", "Python 版本元数据与源码不一致", "V1_2_ACTIVE", "在版本/运行时任务对齐 >=3.12 和最低版本矩阵。", "ADP-V12-S5-T001", "ACC-V12-S5-001"),
]


E1AF_ROWS = [
    ("E1AF-001", "MetaDatabase governance 65/65 PASS"),
    ("E1AF-002", "security boundary 14/14 PASS"),
    ("E1AF-003", "dual-plane、V7.2、root compatibility PASS"),
    ("E1AF-004", "candidate-only failure/error test-name set 为 0"),
    ("E1AF-005", "Worker build c2ccc1fd01ec 未修改未部署"),
    ("E1AF-006", "30 bundles、424 manifests、frontend ZIP hash 未漂移"),
    ("E1AF-007", "developer_check PASS 不授权当时部署或 runtime enablement"),
]


HANDOFF_ROWS = [
    ("HO-001", "MetaDatabase/arxiv-daily-push 是唯一 canonical 源", "INHERITED_PROVEN", "ADP-V12-S0-T001", "ACC-V12-S0-004"),
    ("HO-002", "CodexProject 已删除旧源不得恢复", "V1_2_ACTIVE", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-005;ACC-V12-S6-001"),
    ("HO-003", "Cloudflare 保持 canonical live，不迁 OVH/Coolify", "V1_2_ACTIVE", "ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-004;ACC-V12-S6-002"),
    ("HO-004", "来源顺序 Google News→stats-gov→Science Advances/PubMed", "V1_2_ACTIVE", "ADP-V12-S1-T001;ADP-V12-S2-T001;ADP-V12-S3-T001", "ACC-V12-S1-001;ACC-V12-S2-001;ACC-V12-S3-001"),
    ("HO-005", "v0.1 TASK_INDEX.csv.status 是死配置且不修", "V1_2_ACTIVE", "ADP-V12-S0-T001", "ACC-V12-S0-003"),
    ("HO-006", "三个 dormant Cloudflare 资源已删除且不得重建", "INHERITED_PROVEN", "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-005;ACC-V12-S6-002"),
    ("HO-007", "当前 live build c2ccc1fd01ec、3/5 cron 是锁定基线", "INHERITED_PROVEN", "ADP-V12-S0-T001;ADP-V12-S5-T002", "ACC-V12-S0-005;ACC-V12-S5-004"),
    ("HO-008", "Owner 新授权仅在全部门通过后部署，Free 优先且不自动付费", "V1_2_ACTIVE", "ADP-V12-S5-T002;ADP-V12-S6-T001", "ACC-V12-S5-004;ACC-V12-S6-003"),
]


def build(pack_root: Path) -> str:
    docs = pack_root.parents[1]
    v01_zip = docs / "archive/taskpacks/2026-07-15/ADP_V0.1_FINAL_EXECUTION_TASK_PACKAGE_2026-07-15.zip"
    rows = []
    with zipfile.ZipFile(v01_zip) as archive:
        task_member = next(n for n in archive.namelist() if n.endswith("/06_TASK_INDEX.csv"))
        req_member = next(n for n in archive.namelist() if n.endswith("/08_REQUIREMENT_TRACEABILITY_MATRIX.csv"))
        tasks = list(csv.DictReader(io.StringIO(archive.read(task_member).decode("utf-8-sig"))))
        reqs = list(csv.DictReader(io.StringIO(archive.read(req_member).decode("utf-8-sig"))))

    for row in tasks:
        disposition, reason, evidence, current_tasks, acceptances = old_task_mapping(row["task_id"], row["stage_id"])
        add(rows, "V0_1_TASK", row["task_id"], row["title"], "NOT_STARTED_DEAD_CONFIG_PRESERVED", disposition,
            reason, evidence, current_tasks, acceptances,
            f"INPUT-V01!{task_member}#task_id={row['task_id']}")

    for row in reqs:
        disposition, reason, current_tasks, acceptances = REQ_MAP[row["requirement_id"]]
        add(rows, "V0_1_REQUIREMENT", row["requirement_id"], row["requirement"], "MAPPED_NOT_IMPLEMENTED_HISTORICAL", disposition,
            reason,
            "arxiv-daily-push/docs/pursuing_goal/v1_2/PRD.md;arxiv-daily-push/docs/pursuing_goal/v1_2/ACCEPTANCE_CONTRACT.yaml",
            current_tasks, acceptances,
            f"INPUT-V01!{req_member}#requirement_id={row['requirement_id']}")

    for source_id, title, tasks, acceptances in FRONTEND_ROWS:
        add(rows, "FRONTEND_V1_1", source_id, title, "OWNER_CONTRACT", "V1_2_ACTIVE",
            "前端 v1.1 是六主题与导航的直接验收输入。",
            "arxiv-daily-push/docs/design/前端呈现基线_v1/_原始存档/ADP主题动效v1.1.zip",
            tasks, acceptances, "INPUT-FRONTEND-V11")

    for source_id, title, disposition, reason, tasks, acceptances in OLD_FINDINGS:
        add(rows, "ACCEPTANCE_7FD", source_id, title, "CONFIRMED", disposition, reason,
            "arxiv-daily-push/docs/archive/taskpacks/2026-07-20/ADP_7fd07680_acceptance_review_taskpack.zip",
            tasks, acceptances, "INPUT-ACCEPTANCE-7FD!DEFECT_REPORT.md")

    for source_id, title in E1AF_ROWS:
        add(rows, "ACCEPTANCE_E1AF", source_id, title, "PASS", "INHERITED_PROVEN",
            "e1af 独立 verifier sealed evidence 已闭合迁移 developer_check；v1.2 将其作为回归基线而非新部署授权。",
            "arxiv-daily-push/docs/archive/taskpacks/2026-07-20/ADP_META_MIGRATION_e1af471c_2026-07-20_acceptance_review_taskpack.zip",
            "ADP-V12-S0-T001;ADP-V12-S6-T001", "ACC-V12-S0-004;ACC-V12-S6-001",
            "INPUT-ACCEPTANCE-E1AF!VERDICT.md")

    for source_id, title, disposition, tasks, acceptances in HANDOFF_ROWS:
        add(rows, "HANDOFF_DECISION", source_id, title, "OWNER_DECIDED", disposition,
            "canonical HANDOFF 与 Owner v1.2 指令共同构成当前执行边界。",
            "arxiv-daily-push/docs/HANDOFF.md", tasks, acceptances,
            "arxiv-daily-push/docs/HANDOFF.md")

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pack_root = Path(__file__).resolve().parents[1]
    target = pack_root / "HISTORICAL_TRACEABILITY.csv"
    rendered = build(pack_root)
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            print("FAIL: HISTORICAL_TRACEABILITY.csv is missing or stale")
            return 1
        print("PASS: HISTORICAL_TRACEABILITY.csv is deterministic")
        return 0
    target.write_text(rendered, encoding="utf-8")
    print(f"WROTE {target} rows={rendered.count(chr(10)) - 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
