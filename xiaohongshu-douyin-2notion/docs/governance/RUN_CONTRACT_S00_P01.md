# Run Contract — Stage 0 / Phase 0.1

## 目标

建立唯一仓库/项目身份、Phase 0.1 Task/Acceptance 注册，以及可机器验证的 Public Artifact / Private Runtime 路径契约。

## 最小范围

- `TSK.x2n.discovery.001`：只读仓库基线与 changed-scope map。
- `TSK.x2n.discovery.002`：项目、ID 和人类可读记录注册。
- `TSK.x2n.discovery.003`：Public Artifact / Private Runtime Policy。

Owner 本轮明确将执行单元设为“最多一个 Phase”，因此本 Run 可按依赖顺序完成 Phase 0.1 的三个 Task；该授权不扩展到 Phase 0.2。

## 输入

- MetaDatabase 根/项目 Agent Contract。
- v0.0.0.1 Roadmap 与 Product Design Task Pack。
- Owner 对母仓库、子项目和统一数据根的修正。
- `LinzeColin/Governance` 只消费原则。

## 允许写入

- `xiaohongshu-douyin-2notion/` 项目目录。
- MetaDatabase 根 `README.md` 的单一项目索引行。
- 仓库外 Owner 私有数据根的空目录、marker 和保护属性。

## 禁止写入或副作用

- MetaDatabase 主工作树和其他子项目。
- 任何旧数据目录、旧项目、其他 worktree。
- 真实账号、浏览器 Profile、SQLite、媒体、Markdown 私人正文、Notion、模型或 VPS。
- 远端 push、PR 或 Release。

## 验证

1. Task Pack YAML、Stage 0–6、35 个 Task、依赖无环、Acceptance 引用完整。
2. 仓库/项目身份唯一，旧路由字符串命中为 0。
3. Git 中本机绝对路径、私有扩展名和 Runtime 目录命中为 0。
4. 私有根在仓库外、basename 正确、权限为 Owner-only、marker 一致。
5. Phase 0.1 三个 Task 的适用范围证据完整；下游/Release Gate 保持 NOT_RUN。

## 风险与回滚

- 风险：把 Public Artifact 扫描设计误报为产品 Release 验收通过。
- 控制：证据区分 `PHASE_PASS` 与 `DOWNSTREAM_NOT_RUN`。
- 回滚：删除本 worktree/分支及新建空私有根；不触碰旧目录或主树。

## 停止条件

- 唯一母仓/项目身份冲突。
- 私有根会落入 Git 或要求泄露本机绝对路径。
- 需要迁移/删除旧数据、访问真实账号或进入 Phase 0.2+。
- Task/Acceptance ID 冲突、DAG 有环、证据无法独立复核。
