#!/usr/bin/env python3
"""Build the MooMooAU fact adapter consumed by the pinned shared Governance.

This is project-specific mapping code, not a copy of the shared renderer or its
gates. ``--check`` is read-only; ``--write`` updates only derived fact files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def build_facts(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    canonical = _load(root / "machine/facts/canonical_facts.json")
    graph = _load(root / "machine/contracts/task_graph.json")
    delivery = _load(root / "machine/status/latest.json")
    if (
        delivery.get("schema_version") != "moomooau.delivery-status.v1"
        or delivery.get("package_version")
        not in {
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
            "1.0.13",
            "1.0.14",
        }
        or delivery.get("authority", {}).get("path") != "machine/status/latest.json"
    ):
        raise ValueError("delivery status authority identity mismatch")
    closed = delivery["package_version"] in {
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
        "1.0.14",
    }
    dependency_auth_ready = delivery["package_version"] in {
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
        "1.0.14",
    }
    t0703_entrypoint_ready = delivery["package_version"] in {
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
        "1.0.14",
    }
    t0703_authorized = delivery["package_version"] in {
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
        "1.0.14",
    }
    t0703_repair_authorized = delivery["package_version"] in {
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
        "1.0.14",
    }
    t0703_app_recovery_authorized = delivery["package_version"] in {
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
        "1.0.14",
    }
    t0703_response_scope_recovery_authorized = delivery["package_version"] in {
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }
    t0703_safe_deferred_aggregate_recovery_authorized = delivery["package_version"] == "1.0.12"
    t0703_zero_mutation_reconciliation_authorized = delivery["package_version"] in {
        "1.0.13",
        "1.0.14",
    }
    t0703_historical_label_reconciliation_authorized = delivery["package_version"] == "1.0.14"
    protected_beta_failed = (
        not t0703_repair_authorized
        and delivery.get("dimensions", {}).get("protected_oracles", {}).get("status") == "FAILED"
    )
    protected_beta_passed = (
        delivery.get("dimensions", {}).get("protected_oracles", {}).get("status") == "PARTIAL"
        and delivery.get("dimensions", {}).get("protected_oracles", {}).get("executed") == 2
        and delivery.get("dimensions", {}).get("protected_oracles", {}).get("passed") == 2
        and delivery.get("dimensions", {}).get("protected_oracles", {}).get("failed") == 0
    )
    findings = delivery.get("resolved_review_findings", [])
    blockers = delivery.get("blockers", [])
    if closed:
        if "REV-P1-006" not in findings or "RMD-06_PROTECTED_ACCEPTANCE_PENDING" not in blockers:
            raise ValueError("closed RMD-05 status is not coupled to its finding and blocker")
    elif "REV-P1-006" in findings or "RMD-05_ASSURANCE_PROVENANCE_PENDING" not in blockers:
        raise ValueError("pre-closure RMD-05 status is not coupled to its finding and blocker")

    stage_sources = {item["stage_id"]: item for item in delivery["stage_summary"]}
    stage_status = {
        "S0": "基线完成",
        "S1": "本地机制有证据；正式任务未完成",
        "S2": "本地机制有证据；正式任务未完成",
        "S3": "本地机制有证据；正式任务未完成",
        "S4": "本地机制有证据；正式任务未完成",
        "S5": "本地机制有证据；正式任务未完成",
        "S6": "本地机制有证据；正式任务未完成",
        "S7": (
            "T0702 已通过；T0703 第六次在 PROCESSED_PLAN 零副作用失败，"
            "历史 label 重放修复候选已授权"
            if t0703_historical_label_reconciliation_authorized
            else "T0702 已通过；T0703 第五次出现未知 mutation 结果，"
            "零新增写入 reconciliation 已授权"
            if t0703_zero_mutation_reconciliation_authorized
            else "T0702 已通过；T0703 四次执行均零观察副作用失败，SAFE_DEFERRED 聚合恢复候选已授权"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "T0702 已通过；T0703 三次执行均零观察副作用失败，可选 token 回显恢复候选已授权"
            if t0703_response_scope_recovery_authorized
            else "T0702 已通过；T0703 两次执行均零观察副作用失败，App 安装恢复候选已授权"
            if t0703_repair_authorized
            else "T0702 受保护 Beta 已通过；T0703 单件预算已授权并待首次执行"
            if t0703_authorized
            else "本地预检与已交付安全诊断有证据；最新 Beta 因 GitHub App 零安装失败"
            if protected_beta_failed
            else "T0702 受保护 Beta 已通过；当前范围停在 M3 前"
            if protected_beta_passed
            else "本地预检有证据；受保护门阻塞"
        ),
    }
    if set(stage_sources) != set(stage_status) or any(
        item["evidence_validation_status"] != "PASS" for item in stage_sources.values()
    ):
        raise ValueError("delivery stage summary is incomplete or invalid")
    stage_display_names = {
        "S0": "产品契约与开发入口冻结",
        "S1": "可运行骨架与公共代码骨架",
        "S2": "身份、加密与供应链",
        "S3": "邮箱发现、验证与标准原始邮件数据",
        "S4": "处理后数据产品与公开契约",
        "S5": "消息变更门与最新时间线",
        "S6": "安全、模型、压力与混沌保证",
        "S7": "安全发布、运维与交接",
    }
    stage_gates = {
        "S0": "七个局部验收全绿、只读包校验全绿、不变量无冲突",
        "S1": "合成原始邮件字节往返完整、公开敏感值为零",
        "S2": "禁止端点调用为零、密钥不进入公开面、跨仓最小权限",
        "S3": "非目标完整读取为零、候选差异为零、原始邮件往返完整",
        "S4": "血缘完整、错误密码不产出错误数据、公开敏感值为零",
        "S5": "消息级变更零误伤、失败不变更、最新图稳态唯一且可修复",
        "S6": "强制混沌与恢复场景全部通过、真实数据不进入模型",
        "S7": (
            "按前序执行确定性受保护证据门；零误伤、零泄漏、恢复完整后才能正式启用；无固定日历等待"
        ),
    }
    roadmap = {
        "stages": [
            {
                "id": stage["id"],
                "name": stage_display_names[stage["id"]],
                "gate": stage_gates[stage["id"]],
                "status": stage_status[stage["id"]],
            }
            for stage in graph["stages"]
        ]
    }

    blocker_content = {
        "FORMAL_TASKS_INCOMPLETE": "正式任务仅完成 7/58，51 项仍受最终验收门约束",
        "PROTECTED_ORACLES_NOT_RUN": "受保护验证尚未运行",
        "PROTECTED_BETA_FAILED": (
            "六次精确主分支 T0702 attempt 1 均未通过；最新固定诊断为 GitHub App 零安装"
        ),
        "STAGE7_POST_BETA_PHASES_NOT_AUTHORIZED": (
            "T0702 已通过并满足 M3 前序，但当前 Owner 范围明确停在 M3 前"
        ),
        "T0703_PROTECTED_FIRST_ATTEMPT_PENDING": (
            "T0703 单件预算已授权；精确 main 交付、两项安全延后注册表和首次受保护执行待完成"
        ),
        "T0703_REPAIR_CANDIDATE_PENDING": (
            "T0703 第六次零写入 reconciliation 在 Raw 恢复后停止于 PROCESSED_PLAN；"
            "私有仓与 Gmail 均无新效果。六个失败头均禁止 rerun/redispatch；仅允许一个"
            "从既有加密 Processed envelope 恢复历史 label state 的零写入 attempt 1"
            if t0703_historical_label_reconciliation_authorized
            else "T0703 第五次在 Raw 与 Processed 恢复后公开 MUTATION_FAILED；Processed 当前指针"
            "从零变一且 Gmail Trash 聚合增加一，但精确来源归因仍未声称。五个失败头均禁止 "
            "rerun/redispatch；仅允许一个零 Gmail/私有仓写入 reconciliation attempt 1"
            if t0703_zero_mutation_reconciliation_authorized
            else "T0703 四次受保护执行均零观察副作用失败；第四次仅公开 AGGREGATE_GATE，"
            "不据聚合输出声称精确线上根因；禁止任何失败头 rerun/redispatch，"
            "SAFE_DEFERRED 顺序与封闭聚合诊断恢复候选待交付并仅执行一次"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "T0703 三次受保护执行均零观察副作用失败；第三次仅公开 "
            "RESPONSE_SCOPE_REJECTED；禁止任何失败头 rerun/redispatch，"
            "可选 token 回显恢复候选待交付并仅执行一次"
            if t0703_response_scope_recovery_authorized
            else (
                "T0703 两次受保护执行均零观察副作用失败；禁止 rerun/redispatch，"
                "Owner 已确认 App 安装与私有仓链接，精确恢复候选待交付并仅执行一次"
            )
        ),
        "FINAL_ACCEPTANCE_BLOCKED": "最终验收 0/34，通过数为零",
        "PRODUCTION_WORKFLOW_NOT_RUN": "生产工作流运行数为零",
        "RMD-05_ASSURANCE_PROVENANCE_PENDING": "独立保证来源链尚未补齐",
        "RMD-06_PROTECTED_ACCEPTANCE_PENDING": "后续受保护验收与确定性运行尚未执行",
        "SECOND_BETA_DELIVERY_AND_RERUN_WITHHELD": (
            "历史暂缓已由 Owner 的 Stage 7 完工授权解除；仍禁止 GitHub rerun"
        ),
        "FINAL_CLEAN_SNAPSHOT_AND_PUBLICATION_WITHHELD": "按 Owner 顺序，最终干净快照与发布暂缓",
    }
    open_blockers = [
        {
            "id": blocker_id,
            "内容": blocker_content[blocker_id],
            "owner_only": False,
            "owner": "Codex 开发线程",
            "首次登记": "2026-07-22",
        }
        for blocker_id in delivery["blockers"]
    ]
    dimensions = delivery["dimensions"]
    status = {
        "version": delivery["package_version"],
        "stage": (
            "RMD-06 T0703 第六次 PROCESSED_PLAN 零副作用失败，历史 label 重放候选已授权"
            if t0703_historical_label_reconciliation_authorized
            else "RMD-06 T0703 第五次未知 mutation 结果，零新增写入 reconciliation 已授权"
            if t0703_zero_mutation_reconciliation_authorized
            else "RMD-06 T0703 四次零观察副作用失败，SAFE_DEFERRED 聚合恢复候选已授权"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "RMD-06 T0703 三次零观察副作用失败，可选 token 回显恢复候选已授权"
            if t0703_response_scope_recovery_authorized
            else "RMD-06 T0703 两次零观察副作用失败，App 安装恢复候选已授权"
            if t0703_repair_authorized
            else "RMD-06 T0703 单件预算已授权，首次受保护执行待完成"
            if t0703_authorized
            else "RMD-06 T0702 已通过，范围停在 M3 前"
            if protected_beta_passed
            else "RMD-06 T0702 已授权复验"
            if protected_beta_failed
            else "RMD-06 受保护验收准备"
        ),
        "phase": (
            "T0702/S7AC-002 已通过；T0703 第六次完成 Raw 恢复后停止于 PROCESSED_PLAN，"
            "远端与 Gmail 零新效果；仅授权一个从加密 Processed lineage 恢复历史 label "
            "state 的零新增写入 reconciliation 候选"
            if t0703_historical_label_reconciliation_authorized
            else "T0702/S7AC-002 已通过；T0703 第五次完成 Raw/Processed 恢复后返回 "
            "MUTATION_FAILED；独立聚合变化不单独证明精确来源，仅授权一个零新增写入 "
            "reconciliation 候选"
            if t0703_zero_mutation_reconciliation_authorized
            else "T0702/S7AC-002 已通过；T0703 四次执行均在任何已观察远端效果前失败；"
            "第四次仅公开 AGGREGATE_GATE，不声称聚合输出未证明的精确线上根因；"
            "仅授权一个 SAFE_DEFERRED 聚合恢复候选"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "T0702/S7AC-002 已通过；T0703 三次执行均在任何已观察远端效果前失败；"
            "第三次仅公开 RESPONSE_SCOPE_REJECTED，仅授权一个可选 token 回显恢复候选"
            if t0703_response_scope_recovery_authorized
            else "T0702/S7AC-002 已通过；T0703 两次执行均在任何已观察远端效果前失败；"
            "App 安装与私有仓链接已由 Owner 确认，仅授权一个新恢复候选"
            if t0703_repair_authorized
            else "T0702/S7AC-002 已通过；T0703 仅授权一次 Raw+Processed 恢复后精确 Trash，尚未执行"
            if t0703_authorized
            else "T0702/S7AC-002 已通过；Raw 远端恢复 100%，Gmail 变更为零；当前范围禁止进入 M3"
            if protected_beta_passed
            else "T0702 安全诊断已交付；最新 Beta 固定诊断为 GitHub App 零安装；禁止进入 M3"
            if protected_beta_failed
            else "T0702 入口本地就绪，真实 Beta 阻塞"
        ),
        "task": (
            "交付历史 label state 零新增写入 reconciliation 并执行一次 attempt 1；"
            "禁止六个失败头 rerun/redispatch，禁止 Gmail 与私有仓写入"
            if t0703_historical_label_reconciliation_authorized
            else "交付精确零新增写入 reconciliation 并执行一次 attempt 1；"
            "禁止五个失败头 rerun/redispatch，禁止 Gmail 与私有仓写入"
            if t0703_zero_mutation_reconciliation_authorized
            else "交付精确 SAFE_DEFERRED 聚合恢复候选并执行一次新候选 Budget-1 M3；"
            "禁止任何失败头 rerun/redispatch"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "交付精确可选 token 回显恢复候选并执行一次新候选 Budget-1 M3；"
            "禁止任何失败头 rerun/redispatch"
            if t0703_response_scope_recovery_authorized
            else (
                "交付精确 App 安装恢复候选并执行一次新候选 Budget-1 M3；"
                "禁止两个失败头 rerun/redispatch"
            )
            if t0703_repair_authorized
            else "交付精确 T0703 候选、配置两项安全延后注册表并执行唯一一次 Budget-1 M3"
            if t0703_authorized
            else "关闭 T0702 证据与派生状态；不触发 M3 或后续受保护阶段"
            if protected_beta_passed
            else "将现有最小权限 GitHub App 仅安装到唯一私有数据仓，再执行新 SHA attempt 1"
            if protected_beta_failed
            else "T0702 Raw-only 入口本地就绪；顺序与 protected prerequisites 待解决"
            if dependency_auth_ready
            else (
                "RMD-05 保证来源链已关闭；下一项 RMD-06"
                if closed
                else "RMD-05 保证来源链闭包进行中"
            )
        ),
        "real_progress": (
            "证据完整 58/58；本地机制证据 58/58；正式任务 7/58；"
            f"受保护验证 {dimensions['protected_oracles']['executed']}/"
            f"{dimensions['protected_oracles']['declared']}（通过 "
            f"{dimensions['protected_oracles']['passed']}、失败 "
            f"{dimensions['protected_oracles']['failed']}）；最终验收 0/34；生产阻塞"
        ),
        "report_grade": "机器证据",
        "business_verdict": "本地机制有证据；最终验收与生产就绪均未通过",
        "evidence_status": dimensions["evidence_integrity"]["status"],
        "rendered_at": delivery["status_as_of_utc"].split("T", 1)[0],
    }
    product = {
        "goal": (
            "建设一套零附带损害、纯云端、确定性的 MooMooAU 归档系统："
            "以悉尼时区每日 04:30 为调度目标，把每一封经确定性验证的 Moomoo 相关入站邮件，"
            "以 age 加密的原始数据和处理后数据归档到唯一私有数据仓；"
            "只保留一个加密最新时间线；远端恢复验证成功后，只把对应源消息移入垃圾箱；"
            "调度延迟或丢弃由后续运行自动补偿；系统可完全通过 Codex 开发线程维护，"
            "不依赖本地持久化、特殊自动化行为或例行人工操作。"
        ),
        "users": [
            {
                "who": "邮箱与数据所有者",
                "want": "只通过 Codex 开发线程维护一套零例行人工操作的确定性云端归档系统",
            }
        ],
        "non_goals": [
            "不访问 Moomoo 券商网页端，不调用交易接口，不下单",
            "不处理已发送或草稿邮件，不永久删除，不执行会话级移入垃圾箱",
            "不在用户电脑或自建服务器运行生产数据面",
            "不创建第二私有数据仓，不保存历史 Timeline 图片",
            "不让真实邮件、附件、密码、令牌或私钥进入模型上下文",
            "不让 Codex 自动化成为生产控制平面关键路径",
        ],
    }
    features = [
        {
            "id": "F-001",
            "name": "确定性 Gmail 候选发现与双重验证",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-002",
            "name": "完整 Raw 邮件 age 加密归档",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-003",
            "name": "版本化 Processed 数据与血缘",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-004",
            "name": "远端恢复后精确 Message Trash",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-005",
            "name": "唯一最新 Timeline 串行发布与修复",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-006",
            "name": "悉尼四点半调度与周日全量对账",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-007",
            "name": "脱敏公开 Evidence 与恢复状态",
            "status": "reconstructed",
            "evidence": "extracted",
        },
        {
            "id": "F-008",
            "name": "Codex 开发线程维护入口",
            "status": "reconstructed",
            "evidence": "extracted",
        },
    ]
    config = {
        "parameters": {
            "悉尼运行时间": {
                "value": "悉尼时区每日 04:30",
                "intent": "保持本地调度目标固定并覆盖夏令时；平台延迟或丢弃由后续运行补偿",
                "where": "机器事实中的运行时间契约",
            },
            "私有仓数量": {
                "value": 1,
                "intent": "避免第二数据面和额外故障域",
                "where": "机器事实中的仓库契约",
            },
            "最新图资产上限": {
                "value": 1,
                "intent": "健康稳态唯一且不保存历史图片",
                "where": "机器契约中的时间线发布协议",
            },
            "生产功能开关": {
                "value": "全部关闭",
                "intent": "最终验收和受保护验证未通过前禁止生产启用",
                "where": "发布契约中的功能开关",
            },
        }
    }
    data_contract = {
        "data_flow": (
            "只读候选元数据 → 首次确定性验证 → 完整 RFC EML → age Raw 密文 → "
            "唯一私有远端恢复 → age Processed 密文与远端恢复 → 第二次确定性验证 → "
            "exact Message Trash → 私有快照与唯一最新 Timeline → 脱敏公开 Evidence。"
        ),
        "entities": [
            {
                "entity": "原始数据",
                "keys": ["内容标识", "消息标识摘要", "密文摘要"],
                "pk": "内容标识",
            },
            {
                "entity": "处理后数据",
                "keys": ["内容标识", "结构版本", "解析器版本"],
                "pk": "内容标识、结构版本和解析器版本",
            },
            {"entity": "公开证据", "keys": ["运行状态", "不透明证据根"], "pk": "不透明证据根"},
            {"entity": "时间线", "keys": ["快照根", "密文摘要"], "pk": "快照根"},
        ],
    }
    glossary = {
        "numbers": [
            {
                "item": "生产运行时间",
                "rule": "Australia/Sydney 每日 04:30 调度目标；不承诺精确启动，后续运行自动补偿",
                "status": "frozen",
            },
            {"item": "私有仓数量", "rule": "恰好 1", "status": "frozen"},
            {
                "item": "Timeline 资产数量",
                "rule": "健康稳态恰好 1，任何时刻最多 1，修复态为 0",
                "status": "frozen",
            },
            {"item": "非目标邮件误伤", "rule": "0", "status": "frozen"},
        ],
        "data_shapes": [
            {
                "source": "Gmail",
                "shape": "入站消息元数据与通过验证后的 RFC EML",
                "status": "本地机制已取证；生产未验收",
            },
            {
                "source": "GitHub",
                "shape": "age 密文、固定 Release Asset 与脱敏 Evidence",
                "status": "本地机制已取证；生产未验收",
            },
        ],
        "invariants": [
            {
                "rule": item,
                "note": f"v1.0.1 产品契约，由 v{delivery['package_version']} 原样继承",
            }
            for item in canonical["invariants"]
        ],
        "terms": [
            {"en": "MooMooAU", "zh": "澳洲券商邮件归档产品", "note": "本项目名称"},
            {"en": "MooMoo", "zh": "券商品牌", "note": "本项目只处理澳洲相关入站消息"},
            {"en": "Gmail", "zh": "谷歌邮箱", "note": "受端点守卫限制的来源"},
            {"en": "Raw", "zh": "原始数据", "note": "完整 RFC EML 与附件"},
            {"en": "RFC", "zh": "邮件格式标准", "note": "原始邮件字节格式"},
            {"en": "EML", "zh": "邮件文件", "note": "原始邮件封装"},
            {"en": "Processed", "zh": "处理后数据", "note": "版本化结构化数据"},
            {"en": "Timeline", "zh": "时间线", "note": "唯一最新加密图"},
            {"en": "Evidence", "zh": "证据", "note": "公开面只允许脱敏字段"},
            {"en": "Message", "zh": "单封消息", "note": "变更粒度"},
            {"en": "Trash", "zh": "垃圾箱", "note": "唯一允许的 Gmail 变更"},
            {"en": "Snapshot", "zh": "事实快照", "note": "Timeline 确定性输入"},
            {"en": "Asset", "zh": "发布资产", "note": "固定名称加密文件"},
            {"en": "Repository", "zh": "代码仓库", "note": "私有身份只由受保护编号定位"},
            {"en": "Stage", "zh": "阶段", "note": "每次开发运行最多处理一个"},
            {"en": "Codex", "zh": "开发线程", "note": "用户唯一维护入口"},
            {"en": "age", "zh": "文件加密工具", "note": "所有敏感持久化数据的加密边界"},
            {"en": "Beta", "zh": "小规模真实只存原始数据阶段", "note": "T0702 受保护发布阶段"},
            {
                "en": "Raw-only",
                "zh": "仅原始数据",
                "note": "禁止解析、消息变更和时间线操作的 Beta 边界",
            },
            {
                "en": "main-only",
                "zh": "仅主分支",
                "note": "受保护入口只允许精确主分支提交",
            },
            {"en": "main", "zh": "主分支", "note": "远端唯一受控交付分支"},
            {
                "en": "Environment",
                "zh": "受保护环境",
                "note": "GitHub Actions 的受保护配置与机密边界",
            },
            {"en": "Budget-", "zh": "单件预算", "note": "受保护执行效果上限为一"},
            {
                "en": "SAFE_DEFERRED",
                "zh": "安全延后",
                "note": "缺少受保护处理证据时的显式非猜测 Processed 状态",
            },
            {
                "en": "moomooau-beta",
                "zh": "受保护测试环境名称",
                "note": "T0702 已验证且由 T0703 复用的 GitHub Environment",
            },
            {
                "en": "protected",
                "zh": "受保护",
                "note": "需要受保护环境、来源和确定性运行证据的执行范围",
            },
            {
                "en": "quarantine",
                "zh": "隔离",
                "note": "逐消息内容安全 metadata 不可验证时跳过该消息且不扩大读取或变更",
            },
            {
                "en": "parity",
                "zh": "行为对齐",
                "note": "M3 与已验证 T0702 metadata 隔离语义保持一致",
            },
            {
                "en": "diagnostics",
                "zh": "诊断信息",
                "note": "只允许固定枚举阶段，不包含异常文本或受保护值",
            },
            {
                "en": "mutation",
                "zh": "变更操作",
                "note": "可能改变 Gmail 来源消息状态的受预算操作",
            },
            {
                "en": "processed-current",
                "zh": "当前处理后数据指针",
                "note": "绑定不透明来源标识与最新加密 Processed lineage 的私有指针",
            },
            {
                "en": "public-safe",
                "zh": "公开安全",
                "note": "可进入公开日志且不含邮箱、机密或 private 仓标识",
            },
            {
                "en": "GITHUB_APP_TOKEN",
                "zh": "GitHub 应用安装令牌阶段",
                "note": "只表示封闭操作边界，不公开应用、安装或仓库标识",
            },
            {
                "en": "InstallationTokenFailureClass",
                "zh": "安装令牌失败分类",
                "note": "封闭公开安全枚举，不包含动态异常文本或受保护标识",
            },
            {
                "en": "RESPONSE_SCOPE_REJECTED",
                "zh": "令牌响应范围拒绝",
                "note": "仅表示响应或精确仓库探测未证明目标范围，不公开受保护标识",
            },
            {
                "en": "Date",
                "zh": "服务端日期响应头",
                "note": "用于有界校验安装令牌有效期的 GitHub HTTPS 响应时间",
            },
            {
                "en": "TTL",
                "zh": "有效期",
                "note": "安装令牌从可信参考时间起最长一小时",
            },
            {
                "en": "prerequisites",
                "zh": "前置条件",
                "note": "执行前必须全部确定满足的受保护输入和配置",
            },
            {"en": "exact", "zh": "精确", "note": "限定为单封消息的精确操作"},
            {
                "en": "fail-closed",
                "zh": "失败时保持关闭或阻塞",
                "note": "任何未知、漂移或未通过都不得授予后续权限",
            },
            {
                "en": "cumulative-final",
                "zh": "累计最终树验证模式",
                "note": "只允许后续阶段路径存在，不放宽生产与外部效果门",
            },
            {"en": "Deploy", "zh": "部署", "note": "把受控版本交给远端执行环境"},
            {"en": "Key", "zh": "密钥", "note": "本版本仅涉及单仓只读依赖认证密钥"},
            {"en": "PR", "zh": "拉取请求", "note": "代码变更审查入口"},
            {
                "en": "Secret",
                "zh": "受保护机密",
                "note": "依赖凭据与生产机密必须按契约分离",
            },
            {
                "en": "expression",
                "zh": "工作流表达式",
                "note": "GitHub Actions 在不同阶段解析的条件或变量表达式",
            },
            {
                "en": "fork",
                "zh": "派生仓库",
                "note": "外部派生仓库的拉取请求不得取得受保护依赖凭据",
            },
            {
                "en": "workflow",
                "zh": "工作流",
                "note": "GitHub-hosted 验证或生产编排定义",
            },
            {"en": "Run", "zh": "执行轮次", "note": "一次受契约约束的开发或受保护执行"},
            {"en": "dispatch", "zh": "手动触发", "note": "显式触发一次受保护工作流"},
            {"en": "rerun", "zh": "重新运行", "note": "对既有远端工作流再次执行"},
            {"en": "intake", "zh": "导入审计", "note": "早期只读接收记录标识"},
            {"en": "RMD-", "zh": "复审修复组", "note": "整体复审后的顺序修复单元"},
            {
                "en": "FORMAL_TASKS_INCOMPLETE",
                "zh": "正式任务未完成",
                "note": "唯一状态模型的稳定阻塞编号",
            },
            {
                "en": "PROTECTED_ORACLES_NOT_RUN",
                "zh": "受保护验证未运行",
                "note": "唯一状态模型的稳定阻塞编号",
            },
            {
                "en": "PROTECTED_BETA_FAILED",
                "zh": "受保护测试阶段失败",
                "note": "T0702 串行 attempt 1 尚未满足验收门；最新固定诊断为 App 零安装",
            },
            {
                "en": "STAGE7_POST_BETA_PHASES_NOT_AUTHORIZED",
                "zh": "测试阶段后的第七阶段步骤未授权",
                "note": "T0702 已通过；当前 Owner 范围停在 M3 前",
            },
            {
                "en": "PROTECTED_FIRST_ATTEMPT_PENDING",
                "zh": "受保护首次执行待完成",
                "note": "T0703 已授权但尚无真实受保护回执",
            },
            {
                "en": "T0703_REPAIR_CANDIDATE_PENDING",
                "zh": "T0703 修复候选待执行",
                "note": (
                    "第六次 M3 reconciliation 在 Raw 恢复后停止于 PROCESSED_PLAN；"
                    "远端与 Gmail 零新效果；六个失败头不可 rerun/redispatch，仅允许一个"
                    "从加密 Processed envelope 恢复历史 label state 的零写入 attempt 1"
                    if t0703_historical_label_reconciliation_authorized
                    else "第五次 M3 在完整恢复后返回 MUTATION_FAILED；聚合效果未单独证明精确"
                    "来源；五个失败头不可 rerun/redispatch，仅允许一个零新增写入 "
                    "reconciliation attempt 1"
                    if t0703_zero_mutation_reconciliation_authorized
                    else "四次 M3 均零观察副作用失败；第四次只公开 AGGREGATE_GATE；"
                    "任何失败头不可 rerun/redispatch，仅允许一个 SAFE_DEFERRED "
                    "聚合恢复候选 attempt 1"
                    if t0703_safe_deferred_aggregate_recovery_authorized
                    else "三次 M3 均零观察副作用失败；任何失败头不可 rerun/redispatch，"
                    "仅允许一个可选 token 回显恢复候选 attempt 1"
                    if t0703_response_scope_recovery_authorized
                    else (
                        "两次 M3 均零观察副作用失败；两个失败头不可 rerun/redispatch，"
                        "仅允许一个 App 安装恢复候选 attempt 1"
                    )
                ),
            },
            {
                "en": "FINAL_ACCEPTANCE_BLOCKED",
                "zh": "最终验收阻塞",
                "note": "唯一状态模型的稳定阻塞编号",
            },
            {
                "en": "PRODUCTION_WORKFLOW_NOT_RUN",
                "zh": "生产工作流未运行",
                "note": "唯一状态模型的稳定阻塞编号",
            },
            {
                "en": "CUMULATIVE_FINAL",
                "zh": "累计最终树入口",
                "note": "允许后续阶段路径存在但不放宽生产权限的显式验证模式",
            },
            {
                "en": "RMD-04_PRODUCTION_COMPOSITION_PENDING",
                "zh": "生产组合入口待实现（已关闭）",
                "note": "由 RMD-04 本地合成闭环关闭的历史阻塞编号",
            },
            {
                "en": "RMD-05_ASSURANCE_PROVENANCE_PENDING",
                "zh": "保证来源链待补齐",
                "note": "复审修复队列的稳定阻塞编号",
            },
            {
                "en": "RMD-06_PROTECTED_ACCEPTANCE_PENDING",
                "zh": "后续受保护验收与确定性运行待执行",
                "note": "RMD-05 关闭后下一组的稳定阻塞编号",
            },
            {
                "en": "SECOND_BETA_DELIVERY_AND_RERUN_WITHHELD",
                "zh": "历史第二次测试交付暂缓（已解除）",
                "note": "Owner 已授权 serial new first-attempt；GitHub rerun 仍禁止",
            },
            {
                "en": "FINAL_CLEAN_SNAPSHOT_AND_PUBLICATION_WITHHELD",
                "zh": "最终干净快照与发布暂缓",
                "note": "发布顺序的稳定阻塞编号",
            },
        ],
    }
    flows = {
        "main": [
            {
                "step": 1,
                "who": "云端托管工作流",
                "do": "按最小元数据发现候选",
                "out": "候选消息编号",
            },
            {
                "step": 2,
                "who": "确定性验证器",
                "do": "验证精确发件人、认证对齐和业务指纹",
                "out": "已验证候选",
            },
            {
                "step": 3,
                "who": "归档器",
                "do": "获取完整 RFC EML 并计算摘要",
                "out": "标准原始数据",
            },
            {"step": 4, "who": "加密器", "do": "在持久化前 age 加密", "out": "Raw 密文"},
            {
                "step": 5,
                "who": "远端恢复门",
                "do": "写入唯一私有仓并重取解密校验",
                "out": "可恢复证明",
            },
            {
                "step": 6,
                "who": "数据产品",
                "do": "生成版本化 Processed、age 加密并从唯一私有远端恢复校验",
                "out": "可恢复的 Processed 密文",
            },
            {
                "step": 7,
                "who": "消息变更器",
                "do": "第二次验证后精确调用单封消息移入垃圾箱",
                "out": "单封消息进入垃圾箱",
            },
            {
                "step": 8,
                "who": "时间线发布器",
                "do": "从已恢复数据快照确定性替换唯一最新 Timeline",
                "out": "恰好一个加密最新 Timeline",
            },
            {"step": 9, "who": "证据渲染器", "do": "发布桶化脱敏状态", "out": "公开证据"},
        ]
    }
    plan = {
        "stage": (
            "RMD-06 T0703 第六次 PROCESSED_PLAN 零副作用失败，历史 label 重放候选已授权"
            if t0703_historical_label_reconciliation_authorized
            else "RMD-06 T0703 第五次未知 mutation 结果，零新增写入 reconciliation 已授权"
            if t0703_zero_mutation_reconciliation_authorized
            else "RMD-06 T0703 四次零观察副作用失败，SAFE_DEFERRED 聚合恢复候选已授权"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "RMD-06 T0703 三次零观察副作用失败，可选 token 回显恢复候选已授权"
            if t0703_response_scope_recovery_authorized
            else "RMD-06 T0703 两次零观察副作用失败，App 安装恢复候选已授权"
            if t0703_repair_authorized
            else "RMD-06 T0703 单件预算已授权，首次受保护执行待完成"
            if t0703_authorized
            else "RMD-06 T0702 已通过，范围停在 M3 前"
            if protected_beta_passed
            else "RMD-06 T0702 已授权复验"
            if protected_beta_failed
            else "RMD-06 受保护验收准备"
        ),
        "phase": (
            "T0703 历史 label state 零新增写入 reconciliation 执行准备"
            if t0703_historical_label_reconciliation_authorized
            else "T0703 零新增写入未知 mutation reconciliation 执行准备"
            if t0703_zero_mutation_reconciliation_authorized
            else "T0703 SAFE_DEFERRED 聚合恢复候选 Budget-1 新候选执行准备"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "T0703 可选 token 回显恢复候选 Budget-1 新候选执行准备"
            if t0703_response_scope_recovery_authorized
            else "T0703 App 安装恢复候选 Budget-1 新候选执行准备"
            if t0703_repair_authorized
            else "T0703 Budget-1 受保护首次执行准备"
            if t0703_authorized
            else "T0702 证据闭环；M3 前停止"
            if protected_beta_passed
            else "诊断修复已交付；最新 Beta 因 GitHub App 零安装失败"
            if protected_beta_failed
            else "RMD-06 受保护验收准备"
            if dependency_auth_ready
            else "RMD-05 保证来源链闭包"
        ),
        "task": (
            "交付从加密 Processed envelope 恢复历史 label state 的零写入 reconciliation；"
            "六个失败头不可 rerun/redispatch，新候选仅执行一次"
            if t0703_historical_label_reconciliation_authorized
            else "交付唯一 processed-current 与 Trash 来源绑定的零写入 reconciliation；"
            "五个失败头不可 rerun/redispatch，新候选仅执行一次"
            if t0703_zero_mutation_reconciliation_authorized
            else "交付空注册表 SAFE_DEFERRED 顺序修复与封闭聚合失败分类；"
            "四个失败头不可 rerun/redispatch，新候选仅执行一次"
            if t0703_safe_deferred_aggregate_recovery_authorized
            else "交付可选 token 回显、精确仓库范围探测与 GitHub Date TTL 修复；"
            "三个失败头不可 rerun/redispatch，新候选仅执行一次"
            if t0703_response_scope_recovery_authorized
            else "交付 App 安装恢复与封闭 token 失败分类；两个失败头不可 rerun/redispatch，"
            "新候选仅执行一次"
            if t0703_repair_authorized
            else "复用既有受保护 Environment；Raw 与 Processed 恢复后只 Trash 精确源消息"
            if t0703_authorized
            else "同步 T0702 通过证据并停止；当前范围不授权 M3"
            if protected_beta_passed
            else "仅安装现有最小权限 GitHub App 到唯一私有数据仓；Beta 通过前不进入 M3"
            if protected_beta_failed
            else "T0702 入口仅本地就绪；先解决顺序与 protected prerequisites，不进入 M3"
            if dependency_auth_ready
            else ("RMD-05 已关闭；下一轮仅进入 RMD-06" if closed else "仅完成 RMD-05")
        ),
        "owner": "Codex 开发线程",
    }
    acceptance = {
        "items": [
            {
                "id": "`证据完整性`",
                "criteria": "58/58 任务证据按真实阶段契约验证",
                "status": "通过",
            },
            {
                "id": "`本地机制`",
                "criteria": "58/58 本地或合成机制有证据；不提升受保护结果",
                "status": "通过（限本地范围）",
            },
            {
                "id": "`正式任务`",
                "criteria": "冻结任务图仍为完成 7、计划中 51",
                "status": "未完成",
            },
            {
                "id": "`受保护验证`",
                "criteria": (
                    f"已声明 {dimensions['protected_oracles']['declared']}、"
                    f"已执行 {dimensions['protected_oracles']['executed']}、"
                    f"通过 {dimensions['protected_oracles']['passed']}、"
                    f"失败 {dimensions['protected_oracles']['failed']}"
                ),
                "status": (
                    "阻塞（T0702 通过；T0703 第六次 PROCESSED_PLAN 零副作用失败，"
                    "历史 label 重放 reconciliation 待运行）"
                    if t0703_historical_label_reconciliation_authorized
                    else "阻塞（T0702 通过；T0703 第五次未知 mutation 结果，"
                    "零新增写入 reconciliation 待运行）"
                    if t0703_zero_mutation_reconciliation_authorized
                    else "阻塞（T0702 通过；T0703 四次零观察副作用失败，"
                    "SAFE_DEFERRED 聚合恢复候选待运行）"
                    if t0703_safe_deferred_aggregate_recovery_authorized
                    else "阻塞（T0702 通过；T0703 三次零观察副作用失败，"
                    "可选 token 回显恢复候选待运行）"
                    if t0703_response_scope_recovery_authorized
                    else "阻塞（T0702 通过；T0703 两次零观察副作用失败，App 安装恢复候选待运行）"
                    if t0703_repair_authorized
                    else "部分通过（T0702；T0703 已授权待运行）"
                    if t0703_authorized
                    else "部分通过（T0702；后续未运行）"
                    if protected_beta_passed
                    else "阻塞（Beta 失败）"
                    if protected_beta_failed
                    else "阻塞"
                ),
            },
            {
                "id": "`最终验收`",
                "criteria": "34 个精确验收均需通过",
                "status": "阻塞（0/34）",
            },
            {
                "id": "`生产就绪`",
                "criteria": "正式任务、受保护验证、最终验收与生产运行全部通过",
                "status": "阻塞",
            },
            {
                "id": "`发布`",
                "criteria": "最终复审修复后才创建干净快照并一次性上传",
                "status": "本地，未发布",
            },
        ]
    }
    ops = {
        "troubleshooting": [
            {
                "symptom": "四点半后仍无新鲜证据",
                "cause": "托管调度排队延迟、事件丢弃或工作流停用",
                "fix": "保留水位并由下一次运行幂等补偿；周日执行全量对账，异常保持可见",
            },
            {
                "symptom": "禁止 Gmail 端点被请求",
                "cause": "端点守卫或调用边界漂移",
                "fix": "停止生产、撤销凭证、修复后重跑安全验收",
            },
            {
                "symptom": "远端恢复摘要不一致",
                "cause": "密文或密钥链异常",
                "fix": "保留 Gmail 原件、禁止 M3、从标准原始数据重建",
            },
            {
                "symptom": "时间线固定资产为零",
                "cause": "串行替换在删除后失败",
                "fix": "从同一处理后数据快照确定性重建并验证",
            },
        ]
    }
    changelog = [
        {
            "version": "1.0.4",
            "date": "2026-07-22",
            "summary": (
                "增加唯一 fail-closed 生产组合入口与本地合成端到端闭环；"
                "真实生产、受保护验证和发布仍关闭。"
            ),
        },
        {
            "version": "1.0.3",
            "date": "2026-07-22",
            "summary": "增加显式累计最终树入口与离线命令矩阵；历史 fail-closed 默认语义不变。",
        },
        {
            "version": "1.0.2",
            "date": "2026-07-22",
            "summary": "建立分阶段证据验证和唯一跨维度状态权威；产品契约与安全边界不变。",
        },
        {
            "version": "1.0.1",
            "date": "2026-07-20",
            "summary": "修复阶段局部门、只读包清单、时间线协议、共享治理绑定和公开定位。",
        },
    ]
    if closed:
        changelog.insert(
            0,
            {
                "version": "1.0.5",
                "date": "2026-07-22",
                "summary": (
                    "以候选绑定执行回执、十八次不可变尝试链和两个模型家族的独立通过"
                    "关闭 RMD-05；受保护验证、生产与发布仍关闭。"
                ),
            },
        )
    if dependency_auth_ready:
        changelog.insert(
            0,
            {
                "version": "1.0.6",
                "date": "2026-07-23",
                "summary": (
                    "为私有 Governance 增加单仓只读 Deploy Key 依赖认证、"
                    "fork PR fail-closed 与 workflow expression 修复，完成 9/9 云端非生产预检，"
                    "T0702 串行 first-attempt 账本区分一次 secret 前拒绝与十一次 protected 执行；"
                    "最新执行通过 Alpha、Raw-only Beta 与身份清理，Raw 远端恢复 100%，"
                    "Gmail 变更为零；当前范围停在 M3 前，生产与最终发布仍关闭。"
                ),
            },
        )
    if t0703_entrypoint_ready:
        changelog.insert(
            0,
            {
                "version": "1.0.7",
                "date": "2026-07-24",
                "summary": (
                    "新增独立受保护 M3 单件预算装配与仅主分支工作流，"
                    "绑定 T0702 通过回执和当前运行契约；M3 授权标志为假，"
                    "继续在读取密钥前关闭，真实 M3、处理后数据、Gmail 消息变更与发布均未运行。"
                ),
            },
        )
    if t0703_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.8",
                "date": "2026-07-24",
                "summary": (
                    "T0702 真实通过后建立唯一 T0703 Budget-1 Run Contract，复用已验证的 "
                    "moomooau-beta 受保护基础设施；缺少受保护分类或解析证据时只生成加密 "
                    "SAFE_DEFERRED Processed，远端恢复 Raw 与 Processed 后才允许精确消息 Trash。"
                ),
            },
        )
    if t0703_repair_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.9",
                "date": "2026-07-24",
                "summary": (
                    "固化 T0703 首次 protected M3 的零副作用失败账本，禁止失败头 rerun；"
                    "将内容安全的逐消息 metadata 不可验证与 T0702 对齐为 quarantine，并增加"
                    "封闭 public-safe M3 phase diagnostics。仅授权一个新精确候选 attempt 1。"
                ),
            },
        )
    if t0703_app_recovery_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.10",
                "date": "2026-07-24",
                "summary": (
                    "固化 T0703 第二次 protected M3 的零观察副作用失败和 GITHUB_APP_TOKEN "
                    "边界；Owner 随后确认 GitHub App 已安装并链接唯一 private 数据仓。"
                    "M3 现与 T0702 一样只公开封闭 InstallationTokenFailureClass；两个失败头"
                    "均禁止 rerun/redispatch，仅授权一个新精确候选 attempt 1。"
                ),
            },
        )
    if t0703_response_scope_recovery_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.11",
                "date": "2026-07-24",
                "summary": (
                    "固化 T0703 第三次 protected M3 的 RESPONSE_SCOPE_REJECTED 零副作用失败。"
                    "按 GitHub 固定 OpenAPI 将 repositories/permissions 视为可选回显；缺少"
                    "仓库回显时用 installation token 做最多两个结果的精确仓库范围探测，"
                    "并按有界 GitHub Date 校验一小时 TTL。三个失败头均禁止 rerun/redispatch。"
                ),
            },
        )
    if t0703_safe_deferred_aggregate_recovery_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.12",
                "date": "2026-07-24",
                "summary": (
                    "固化 T0703 第四次 protected M3 在 AGGREGATE_GATE 的零观察副作用失败；"
                    "不据聚合输出声称精确线上根因。静态契约验证并修复空分类/解析注册表下"
                    "隔离附件可能错误产生 BLOCKED 的顺序冲突，并增加封闭聚合失败分类。"
                    "四个失败头均禁止 rerun/redispatch，仅授权一个新候选 attempt 1。"
                ),
            },
        )
    if t0703_zero_mutation_reconciliation_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.13",
                "date": "2026-07-24",
                "summary": (
                    "固化 T0703 第五次 protected M3 在完整 Raw/Processed 恢复后的 "
                    "MUTATION_FAILED；独立聚合观察到 processed-current 从零变一与 Gmail "
                    "Trash 加一，但不据此声称精确来源归因或 mutation 子原因。新增唯一 "
                    "processed-current/Trash 来源选择、二次验证和零 Gmail/私有仓写入 "
                    "reconciliation；五个失败头均禁止 rerun/redispatch。"
                ),
            },
        )
    if t0703_historical_label_reconciliation_authorized:
        changelog.insert(
            0,
            {
                "version": "1.0.14",
                "date": "2026-07-24",
                "summary": (
                    "固化 T0703 第六次 protected M3 在 Raw 恢复后于 PROCESSED_PLAN "
                    "零副作用失败；独立确认私有仓 head/tree、Raw、Processed、current pointer "
                    "与 Gmail Trash 均未变化。修复 Gmail Trash 后 live label state 与既有 "
                    "Processed snapshot 的历史 label state 重放冲突；仅从加密 Processed "
                    "envelope 恢复规范 label，六个失败头均禁止 rerun/redispatch。"
                ),
            },
        )
    return {
        "status.json": status,
        "blockers.json": open_blockers,
        "roadmap.json": roadmap,
        "product.json": product,
        "features.json": features,
        "config.yaml": config,
        "data_contract.yaml": data_contract,
        "glossary.json": glossary,
        "flows.json": flows,
        "plan.json": plan,
        "acceptance.json": acceptance,
        "ops.json": ops,
        "changelog.json": changelog,
    }


def write_or_check(root: Path, *, write: bool) -> list[str]:
    expected = build_facts(root)
    facts_dir = root.resolve() / "machine/facts"
    mismatches = []
    for name, value in expected.items():
        path = facts_dir / name
        rendered = _dump(value)
        if write:
            path.write_text(rendered, encoding="utf-8")
        elif not path.is_file() or path.read_text(encoding="utf-8") != rendered:
            mismatches.append(name)
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches = write_or_check(args.root, write=args.write)
    result = {
        "status": "PASS" if not mismatches else "FAIL",
        "mode": "write" if args.write else "check",
        "derived_files": len(build_facts(args.root)),
        "mismatches": mismatches,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
