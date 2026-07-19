# Pre-development Readiness Matrix

此矩阵只做路由，不提前执行 Phase 0.5+。状态含义：`RESOLVED` 已有本轮证据；`NOT_RUN` 未验收；`DEFAULTED` 有可逆默认但不等于通过；`BLOCKS_G0` 在进入 Stage 1 前必须完成。

| 主题 | 当前状态 | 已知默认/边界 | 唯一后续路由 | 是否阻断当前 Phase |
|---|---|---|---|---|
| 母仓库/子项目 | RESOLVED | MetaDatabase / `xiaohongshu-douyin-2notion/` | 本 Phase 证据 | 否 |
| Runtime/下载根 | RESOLVED | 同一 `X2N_DATA_ROOT`，仓库外、Owner-only | 本 Phase 证据 | 否 |
| 旧目录/数据 | RESOLVED | 不导入、不链接、不删除 | 独立迁移 Run（仅 Owner 新授权） | 否 |
| Task/Acceptance/DAG | RESOLVED | Stage 0–6、35 Task、无环 | 本 Phase 证据 | 否 |
| 上游 Commit/Schema/License | RESOLVED / CURRENT_ARTIFACT_SCOPE | 三仓 exact pin；xhs clean-room only；douyin disabled pending lock/contract；MediaCrawler external only | Phase 0.2 证据；Phase 0.5 收口 Notice/ADR | 否；未来启用仍需重验 |
| Chrome/CWS 当前政策 | NOT_RUN / BLOCKS_G0 | 账号安全、最小权限、无自动滚动 | Phase 0.5 / `TSK.x2n.discovery.005` 官方一手复核 | 否；阻断 G0 |
| 小红书/抖音账号与访问边界 | NOT_RUN / BLOCKS_G0 | 不改变账号状态、不绕过限制 | Phase 0.5 / `TSK.x2n.discovery.005` | 否；阻断 G0 |
| Owner OS/硬件/数据量 | DEFAULTED / NOT_RUN | 当前 Mac 优先；只用合成数据 | Phase 0.5 / `TSK.x2n.discovery.005` | 否；阻断 G0 完整输入 |
| 一级分类 | DEFAULTED / NOT_RUN | 仅 `Unclassified`，AI 不得新增 | Phase 0.5 / `TSK.x2n.discovery.005` | 否；阻断分类 Alpha |
| Notion | DEFAULTED / NOT_RUN | Disabled；无 Secret、无外部写入 | Phase 0.5 输入契约与 Stage 5 | 否 |
| AI Provider/预算 | DEFAULTED / NOT_RUN | Cloud Off、预算 0 | Phase 0.5 输入契约与 Stage 4 | 否 |
| Threat Model/ADR | NOT_RUN / BLOCKS_G0 | Fail Closed | Phase 0.5 / `TSK.x2n.discovery.005` | 否；阻断 G0 |
| Stage 0 Gate / 上传 | NOT_RUN | Phase 中间禁止 push | Stage 0 全 Phase 后 Review/Fix/Re-test | 否；阻断上传 |

因此，Phase 0.2 完成后，Stage 0 唯一剩余 Run 是 Phase 0.5；0.3/0.4 只作为其准备域。不能跳到 Stage 1、启用上游、读取真实账号或上传中间 Phase。
