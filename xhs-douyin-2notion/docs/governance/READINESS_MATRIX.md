# Pre-development Readiness Matrix

此矩阵只做路由，本 Resume Run 不执行 Stage 1。状态含义：`RESOLVED` 已有本轮证据；`NOT_RUN` 未验收；`DEFAULTED` 有可逆默认但不等于通过；`AUTHORIZED_NEXT_RUN` 只允许在后续独立 Run 开始。

| 主题 | 当前状态 | 已知默认/边界 | 唯一后续路由 | 是否阻断当前 Phase |
|---|---|---|---|---|
| 母仓库/子项目 | RESOLVED | MetaDatabase / `xhs-douyin-2notion/` | 本 Phase 证据 | 否 |
| 原始 taskpack 下载绝对路径 | RESOLVED_GAP | 原始输入未指定；不得伪造来源 | Owner Change Event + Source Manifest | 否 |
| Runtime/下载根 | RESOLVED | `${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion` 统一命名空间，仓库外、Owner-only | 本 Phase 证据 | 否 |
| 下载目的地既有条目 | PRESERVED | 仅聚合数量/元数据指纹审计且不回显名称；不读取内容、不导入、不链接、不修改、不删除 | 独立迁移 Run（仅 Owner 新授权） | 否；跨命名空间立即阻断 |
| MetaDatabase 长期并行开发 | RESOLVED_REVIEW_CUTOFF | 独立 x2n worktree；显式 override；外部 dirty path 只计数；x2n overlap 必须为 0；moving main 用明确 cutoff | Stage Review cutoff/evidence；cutoff 后只检查 x2n overlap | 否；重叠或越界立即阻断 |
| Task/Acceptance/DAG | RESOLVED | Stage 0–6、43 Task、61 Acceptance、无环；每普通 Run 一个 DAG Task | Stage 0 Review 证据 | 否 |
| 上游 Commit/Schema/License | RESOLVED / CURRENT_ARTIFACT_SCOPE | 三仓 exact pin；xhs clean-room only；douyin disabled pending lock/contract；MediaCrawler 仅历史审计参考、零 Runtime | Phase 0.2 历史证据；Phase 0.5 restricted-research boundary | 否；任何未来变化需新 Change Event |
| Chrome/CWS 当前政策 | REVALIDATED_DESIGN / RECHECK_REQUIRED | 用户手势、最小权限、无 Remote Hosted Code、无自动滚动 | 每个实现/发布 Phase 重新核验一手政策 | 否；不构成发布授权 |
| 六平台账号与访问边界 | RESOLVED_DESIGN / ALL_DISABLED | 不改变账号状态、不绕过限制；独立 Policy/Auth/Technical Gate | 各平台 Phase 开始时重新核验 | 否；真实执行未授权 |
| Owner OS/硬件/数据量 | DEFAULTED | 自动检测；规模未知；只用合成数据 | 私有 Owner Contract；Stage 1/Canary 再确认 | 否 |
| 一级分类 | DEFAULTED | 仅 `Unclassified`，AI 不得新增 | Owner 后续明确输入 | 否；自动分类保持关闭 |
| Notion | DEFAULTED | Disabled；无 Secret、无外部写入 | Stage 2/5 对应 Gate | 否 |
| AI Provider/预算 | DEFAULTED | Cloud Off、预算 0 | Stage 4 对应 Gate | 否 |
| Threat Model/ADR | REVIEWED_DESIGN | ADR-001–010、10 Trust Boundaries、STRIDE、20 Stop/Kill | Phase 0.5 + Stage 0 Review 证据 | 否；实现 Oracle 仍未运行 |
| ShilongLee/Crawler | REVALIDATED / EXCLUDED | 固定 Commit 仍为当前 HEAD；自定义非商业 License；0 copy/vendor/runtime dependency；clean-room ideas only | Stage 0 Review 外部复核 | 否 |
| 外部共享认证材料与临时源码事件 | RESOLVED_WITH_COMPENSATING_CONTROLS | 外部材料由 Owner 保留；x2n 零接触；当前树/历史/私有根/Local Remote 0 命中；Secret Presence 不可 waiver | `POLICY.X2N.AUTH-ISOLATION.001`；未来匿名公开源码 Snapshot；任一新命中 Fail Closed | 否；Resume 证据已关闭原 G0 follow-up |
| Stage 0 Gate / 上传 | G0_PASS / AUTHORIZED | 独立 Resume、Owner 闭合回执、完整复验与脱敏证据通过；首次 Blocked 证据保留 | 上传整个 Stage 0；后续独立 Run 从 `TSK.x2n.foundation.001` 开始 | 否；本 Run 不执行 Stage 1 |

Stage 0 Review Resume 已签发机器 `G0 PASS`。Stage 0 可整阶段上传；下一独立 Run 只允许 `TSK.x2n.foundation.001`。这不启用任何平台、不授权真实账号，也不代表产品或下游 Acceptance 已运行。
