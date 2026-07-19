# Stage 0 / Phase 0.1 Baseline Inventory

## 已核验事实

| 项目 | 事实 |
|---|---|
| 母仓库 | `LinzeColin/MetaDatabase`，默认分支 `main`，GitHub 可见性 Public，许可为专有/All Rights Reserved |
| 主树 | 开工前位于 `main` 且 clean；本 Run 未在主树写入 |
| 开发隔离 | 专用 worktree 和 `codex/` 分支，稀疏范围仅目标子项目 |
| 子项目 | `xiaohongshu-douyin-2notion/`；开工前不存在 |
| 产品设计 | `v0.0.0.1`；7 个 Stage（0–6）、35 个唯一 Task，依赖无缺失且无环 |
| 输入 Roadmap | SHA-256 `66f949b2109ffe2701d7b74099430e862f4027bb4a429c56e84e13716c0bc906` |
| 输入 Task Pack ZIP | SHA-256 `b32993f465888d9352d745b353c3b923c38406c941a8f357ddf1a64e2bba5a58`；7 个成员；CRC 通过 |
| Roadmap 一致性 | 独立 Roadmap 与 ZIP 内 `02_ROADMAP.md` 原始内容哈希一致 |
| 统一数据根 | 开工前不存在；本 Run 只建立空目录/marker/保护属性，不创建真实 Runtime 数据 |
| 旧目录 | 保持不变；不迁移、不链接、不删除、不作为新项目输入或输出 |

## Changed-scope Allowlist

- Git：`xiaohongshu-douyin-2notion/**`，以及根 `README.md` 的单一项目索引行。
- 本地私有：仅 `X2N_DATA_ROOT` 新根的空骨架和 marker。
- 工具：只读 Git/GitHub 状态、YAML/Markdown/JSON 校验、权限与备份排除状态检查。

## Forbidden Scope

- MetaDatabase 其他项目与主工作树。
- Stage 0 / Phase 0.2 及以后任务。
- 产品功能实现、真实平台交互、Notion/AI/VPS、旧数据迁移和远端发布。

## 已显式消除的歧义

- Stage 工时 `288–600h` 是组合层规划包络；Task `high` 是单任务孤立风险上界，不能直接相加。机器 Task Pack 已记录口径，工时不是 Acceptance。
- 第三方上游与许可证绑定到 Phase 0.2；平台/Chrome Web Store 政策、Owner Input、Threat Model 与 ADR 绑定到 Phase 0.5。原 Roadmap 的 0.3/0.4 明确为 0.5 准备域，不是独立 Run。
- Phase 0.1 的策略扫描通过不代表 DB、媒体、Markdown、Notion、Build、Release 或真实账号 Acceptance 通过。
- 后续任务若没有更窄的 Task-specific Scope，默认 Git 写入范围仍只能是本子项目；任何仓库外写入必须在该 Run Contract 中逐项列出。

## 指令读取回执

- 已读取 GithubProject 工作间 README 六条铁律。
- 已读取 MetaDatabase 根 `AGENTS.md`。
- 已读取本项目 `AGENTS.md`。
- 已读取 v0.0.0.1 PRD、Architecture/System Card、Acceptance 与 Phase 0.1 Task DAG。
- 已读取 Codex Dev Orchestrator 的 Controlled Run / Run Contract 指令。
