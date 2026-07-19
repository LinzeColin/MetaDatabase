# Codex 起点

本任务包包含未安装的 Codex Skill 源码：`stock-commercial-opportunities`，中文名“股票商业机会拆解”。它把产业/政策/技术/价值链商业机会转成可追溯的上市证券研究队列，不生成个人买卖建议。

## 最小读取顺序

1. `AGENTS.md`
2. `CODEX_MASTER_TASK.md`
3. `DECISIONS_AND_DEFAULTS.md`
4. `skill_draft/stock-commercial-opportunities/SKILL.md`

按需读取：

| 阶段 | 文件 | 退出条件 |
|---|---|---|
| 定位/研究 | `USER_REQUIREMENTS.md`, `RESEARCH_REPORT.md`, `REFERENCE_PROJECT_MATRIX.md` | 类似系统和差异有公开证据 |
| 设计/实现 | `TARGET_ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md` | 一个 Run Contract 范围确定 |
| 验证 | `ACCEPTANCE_CHECKLIST.md`, Skill 内 `references/evaluation.md` | 阻断检查有同次结果 |
| 恢复/交付 | `VALIDATION_REPORT.md`, `PACKAGE_CONTENTS.md`, `BLIND_SPOTS_AND_SURPRISES.md` | 哈希、未运行项和恢复步骤明确 |

## 当前状态

| Gate | 状态 |
|---|---|
| v1/v2 原始谱系归档 | COMPLETE |
| v3 股票版研究、架构、脚本和 fixtures | COMPLETE |
| 本地确定性验证 | 见 `VALIDATION_REPORT.md`；以同次命令为准 |
| 新鲜任务隐式触发与无/有 Skill A/B | NOT_RUN |
| 用户级安装 | NOT_RUN / 当前明确禁止 |
| 真实股票研究结论 | NOT_RUN；fixtures 全为 synthetic |

## 默认动作

先验证源码、manifest 和 release ZIP。若未来需要使用，用户应单独决定“临时加载/仓库级引用/安装”方案；当前任务不得写入任何全局 Skill 根。
