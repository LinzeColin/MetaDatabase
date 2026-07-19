# Owner Change Event — CE-X2N-20260719-S00-P01

> 执行粒度条款已被 `CE-X2N-20260720-S00-REVIEW` 取代：未来普通 Run 只能执行一个 DAG Task。本文件保留为历史路由证据，不再授权“一 Run 一个 Phase”。

## 原因

原始 v0.0.0.1 Product Design 输入中的仓库路由不再符合 Owner 的唯一目标，且原始 roadmap/taskpack 没有指定本机下载绝对路径。Owner 明确要求在 pre Stage 00 先完成只读核验，并将后续实施统一到 MetaDatabase 的唯一子项目与指定下载目的地内的隔离私有数据根。

## Owner 已定修正

1. 唯一母仓库为 `LinzeColin/MetaDatabase`。
2. 唯一子项目路径为 `xhs-douyin-2notion/`。
3. Owner 指定下载目的地为逻辑 `X2N_DOWNLOAD_DESTINATION`；`X2N_DATA_ROOT` 解析为其中的 `xhs-douyin-2notion/` 隔离命名空间，Runtime 与所有 Adapter 下载共用该根；本机绝对解析值不得进入 Git。
4. 下载目的地现有同级条目只允许不回显名称的聚合数量/元数据指纹审计；不读取内容、不迁移、不链接、不修改、不删除。
5. v0.0.0.1 DAG 的有效范围只有 Stage 0–6。
6. 每个 Run 最多一个 Phase；每个 Stage 完成后 Review → Fix → Re-acceptance → 整 Stage 上传。
7. Stage `288–600h` 保留为组合层规划包络；Task `high` 仅表示单任务孤立风险上界，不做算术累加，也不作为验收阈值。
8. Stage 0 的机器可执行顺序为 Phase 0.1 → 0.2 → 0.5；Roadmap 0.3/0.4 是 `TSK.x2n.discovery.005` 的非独立准备域，不增加或改号 Task。

## 版本处理

本 Change Event 不修改产品功能需求、验收阈值或 Stage 0–6 DAG，只修正实施路由、数据位置和执行单元。Owner 要求继续使用 `v0.0.0.1`；原始输入哈希保留在 Source Manifest 和 Baseline Inventory，修订不伪装成原始 ZIP 内容。

## 影响与回滚

- 影响：全部七份 Product Design 文档的仓库/路径引用、Phase 0.1 注册和本地空目录骨架。
- 不影响：产品代码、真实数据、账号、第三方依赖 Pin、后续 Acceptance 阈值。
- 回滚：删除本 worktree/分支与仍为空的新私有根；旧目录和 MetaDatabase 主树不变。
