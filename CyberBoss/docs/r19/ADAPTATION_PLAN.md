# R19 适配计划（Build Agent 第一动作产物）

任务包：`CyberBoss_v0.0.0.8_SEALED_TASKPACK_FINAL_R19_SHARED_BOT_DEEPSEEK_V4_PRO_20260728`
本文由两个只读探针的输出生成，不是推断。

## 探针结果（真实运行，非自述）

| 探针 | 命令 | 结果 |
|---|---|---|
| Current Truth | `scripts/current_truth_probe.sh .` | 退出码 0，`consensus.status = consistent` |
| Target Compatibility | `scripts/target_compatibility_probe.py --repo . --map machine/overlay_map.json` | 退出码 0，`status = mapped` |

- Subject：`b555aece63143dfb05171bd609cd9afc2542078a`，分支 `claude/cyberboss-v0-0-0-8-taskpack-fc4d1f`，工作树干净
- 三个来源（machine_task_state / README / HANDOFF）一致声明高水位 `CB-840`，45 个任务有证据
- `mutation_policy = allow_normal_execution`，`next_action = continue_frozen_task_dag`
- 目标树扫描 4989 个文件，`ambiguous_required_domains = 0`
- **main 的 HEAD 是 `c85bfb1e`，落后本分支今日全部修复提交**；「不覆盖 main 中更好的实现」在本轮不构成约束，因为本分支严格领先

## 七个域的分类

| 域 | 探针状态 | 分类 | 依据 |
|---|---|---|---|
| database_migration | EXACT_PATH_PRESENT | **adapt** | `app/migrations/` 已存在且有 001..00N 序列，按 `<next>_multiuser_v8.sql` 续写，不新建目录 |
| public_scan_entry | **NEW_MODULE_REQUIRED** | **apply** | 唯一真正缺失的模块。`app/src/services/public-entry/` 与 `app/public/` 均无匹配（candidate_count = 0） |
| identity_isolation | EXACT_PATH_PRESENT | **adapt** | weixin/users/inbox/outbox 四个目录都在；改的是语义：`user_id = f(shared_bot_account_id, sender_id)` |
| deepseek_runtime | EXACT_PATH_PRESENT | **adapt + obsolete** | 目录在，但四 Provider BYOK 路由被 R19 判为过时（见下） |
| historical_imports | EXACT_PATH_PRESENT | **satisfied** | 四平台解析器、上传策略、幂等台账已建成并有测试 |
| profile_companion | EXACT_PATH_PRESENT | **satisfied** | profile / timeline / reminder / analytics 均已建成 |
| data_backup_status_ops | EXACT_PATH_PRESENT | **satisfied（部分 blocked）** | canonical / status / scripts 齐备；R2 侧凭据 403，见 blocked |

## 明确判为 obsolete 的既有实现

R19 `00_READ_FIRST` 要求「mark any per-user-Bot/public-login implementation obsolete」。据此：

| 既有实现 | 判定 | 理由 |
|---|---|---|
| 四 Provider Router + Credential Vault（BYOK） | **obsolete** | R19：统一 Owner 额度的 DeepSeek 官方 API，固定 `deepseek-v4-pro`，无 BYOK、无模型选择 |
| 每用户模型预算与配额（个人日/月/次数） | **obsolete** | R19：无个人限额，仅 UTC 每日 1,000,000,000 total tokens 全局熔断 |
| 主人认领码 + 10 分钟绑定窗口 | **obsolete** | R19：Owner 只在受保护的 `/ops/wechat` 扫 iLink 授权二维码。本轮自创的这两条是在没有任务包指引下的权宜之计，应由 `/ops/wechat` 取代 |
| 设置页面的用户填 API Key 流程 | **obsolete** | 同上，无 BYOK。设置链接保留，但用途改为导入/资料/导出/删除 |

**保留不动**：多用户加密隔离、导出与可验证删除、双副本备份、Status 业务矩阵、不可变发布与指针回滚、durable inbox/outbox/job scheduler。这些 R19 未取代，且已有证据。

## blocked（无真实凭据，不得标记完成）

| 项 | 状态 | 缺什么 |
|---|---|---|
| DeepSeek V4 Pro | blocked | `DEEPSEEK_API_KEY` 未提供 |
| R2 备份 | blocked | 现有密钥 403 AccessDenied（SigV4 已验证正确，是权限问题） |
| 共享 Bot 公开扫码 | blocked | 需要 Owner 在 `/ops/wechat` 完成一次真实 iLink 授权 |

## 本轮必须先解决的既有缺陷（先于 DAG 1）

**非主人消息无法在建 job 之前分流。** `JobScheduler` 要求 `dispatchRuntime` 返回真实的 `threadId`/`turnId`，因此普通用户/入门回复/状态三条路必须在 `DurableInboxCoordinator` 建 job **之前**分流；`app/src/services/inbox/durable-inbox.js` 目前没有这个钩子。

这一条直接卡住 R19 的席位语义（第六人要在 DeepSeek 调用前被拒绝）——不先修，DAG 2 和 DAG 4 都无法闭环。

## 铁律（本仓反复踩中）

任何改动在标记完成前，必须确认它在**真实链路**上可达：

```
bin/cyberboss.js → app/scripts/cloud-supervisor.js → durable inbox → job scheduler → dispatchDurableRuntimeJob
```

本轮已四次出现「测试全绿、真实链路上那段代码从未被执行」。模块测试通过不构成证据。
