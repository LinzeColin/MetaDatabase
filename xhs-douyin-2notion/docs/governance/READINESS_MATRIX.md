# Pre-development Readiness Matrix

此矩阵只做路由，不提前执行 Phase 0.5+。状态含义：`RESOLVED` 已有本轮证据；`NOT_RUN` 未验收；`DEFAULTED` 有可逆默认但不等于通过；`BLOCKS_G0` 在进入 Stage 1 前必须完成。

| 主题 | 当前状态 | 已知默认/边界 | 唯一后续路由 | 是否阻断当前 Phase |
|---|---|---|---|---|
| 母仓库/子项目 | RESOLVED | MetaDatabase / `xhs-douyin-2notion/` | 本 Phase 证据 | 否 |
| 原始 taskpack 下载绝对路径 | RESOLVED_GAP | 原始输入未指定；不得伪造来源 | Owner Change Event + Source Manifest | 否 |
| Runtime/下载根 | RESOLVED | `${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion` 统一命名空间，仓库外、Owner-only | 本 Phase 证据 | 否 |
| 下载目的地既有条目 | PRESERVED | 仅聚合数量/元数据指纹审计且不回显名称；不读取内容、不导入、不链接、不修改、不删除 | 独立迁移 Run（仅 Owner 新授权） | 否；跨命名空间立即阻断 |
| MetaDatabase 长期并行开发 | RESOLVED_CURRENT_RUN | 独立 x2n worktree；显式 override；外部 dirty path 只计数；x2n overlap 必须为 0 | 本 Phase 隔离证据；Stage Review 对 `origin/main` 重新同步核验 | 否；重叠或越界立即阻断 |
| Task/Acceptance/DAG | RESOLVED | Stage 0–6、43 Task、61 Acceptance、无环 | Phase 0.5 证据 | 否 |
| 上游 Commit/Schema/License | RESOLVED / CURRENT_ARTIFACT_SCOPE | 三仓 exact pin；xhs clean-room only；douyin disabled pending lock/contract；MediaCrawler 仅历史审计参考、零 Runtime | Phase 0.2 历史证据；Phase 0.5 restricted-research boundary | 否；任何未来变化需新 Change Event |
| Chrome/CWS 当前政策 | RESOLVED_DESIGN / RECHECK_REQUIRED | 用户手势、最小权限、无 Remote Hosted Code、无自动滚动 | 每个实现/发布 Phase 重新核验一手政策 | 否；G0 Review 仍未运行 |
| 六平台账号与访问边界 | RESOLVED_DESIGN / ALL_DISABLED | 不改变账号状态、不绕过限制；独立 Policy/Auth/Technical Gate | 各平台 Phase 开始时重新核验 | 否；真实执行未授权 |
| Owner OS/硬件/数据量 | DEFAULTED | 自动检测；规模未知；只用合成数据 | 私有 Owner Contract；Stage 1/Canary 再确认 | 否 |
| 一级分类 | DEFAULTED | 仅 `Unclassified`，AI 不得新增 | Owner 后续明确输入 | 否；自动分类保持关闭 |
| Notion | DEFAULTED | Disabled；无 Secret、无外部写入 | Stage 2/5 对应 Gate | 否 |
| AI Provider/预算 | DEFAULTED | Cloud Off、预算 0 | Stage 4 对应 Gate | 否 |
| Threat Model/ADR | RESOLVED_DESIGN | ADR-001–010、10 Trust Boundaries、STRIDE、20 Stop/Kill | Phase 0.5 证据；G0 全 Stage Review | 否；G0 Review 仍未运行 |
| ShilongLee/Crawler | RESOLVED / EXCLUDED | 自定义非商业 License；0 copy/vendor/runtime dependency；clean-room ideas only | Phase 0.5 竞品登记 | 否 |
| 临时源码 remote 凭据形态 | CONTAINED / BLOCKS_G0 | 临时副本删除；项目/私有根文件扫描 0；凭据生命周期未知 | `INC-X2N-S00-P05-001`；Owner 轮换/重新认证或过期证明 | 不阻断本 Phase；阻断 G0 PASS |
| Stage 0 Gate / 上传 | NOT_RUN | Phase 中间禁止 push | Stage 0 全 Phase 后 Review/Fix/Re-test | 否；阻断上传 |

Phase 0.5 完成后只能进入独立的 Stage 0 全 Stage Review/Fix/Re-acceptance Run；在 G0 通过前不能跳到 Stage 1、启用任何平台、读取真实账号或上传中间 Phase。
