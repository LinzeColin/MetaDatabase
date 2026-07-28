# Stage 3 Review Resume — Direct MVP Contract

## 结论

`STG.X2N.3.REVIEW.RESUME` 已把 Owner 的最新约束版本化，但没有执行第十个 Adapter Task，也没有把
旧 Review 的合成证据重写成真实能力。当前真实状态为：

> `CONTRACT_VERSIONED / G3_BLOCKED_TECHNICAL / STAGE_3_UPLOAD_FORBIDDEN / STAGE_4_UNAUTHORIZED`

原五个 blocker 中，三个合同/Owner 归属问题已经闭合：

| 已闭合项 | 版本化结论 |
|---|---|
| `CANARY-TERMINALS` | 合法终态仅 `READY_FOR_MVP_ACTIVATION` / `DISABLED_EXTERNAL_GATE`；后者必须关闭 flag、0 平台调用、0 live support claim |
| `ACCEPTANCE-SCOPE` | Stage 3 只贡献 `PASS_CI_SYNTH_CONTRIBUTION`；完整 `ACC.x2n.rel.006` 只在 Stage 6 判定 |
| `OWNER-CANARIES` | 真实账号激活与私有 Manifest 属于 Stage 6，不是 G3 条件，当前仍 `NOT_RUN` |

两个技术 blocker 合并由下一任务 `TSK.x2n.adapters.010 / PH.X2N.3.10` 闭合：

1. 8 scope 严格 Extension → Native → Adapter dispatch；
   `START_SYNC` 必须新增严格 `scope_id` 判别合同，精确表达 Bilibili/Kuaishou/Taobao
   selected-collection 的 `saved_current`（并绑定 Owner manifest/source/`max_items`），不得伪装成
   liked/favorited；`CAPTURE_CURRENT` 仍是独立单条动作，非法交叉组合全部拒绝；
2. typed `GET_CAPABILITIES` 必须只在完整有效评估后返回恰好八个终态；SQLite
   `capability_gate_outcome` 每 scope 最多一行，完整有效 snapshot 才恰好八行，按固定 reason
   优先级从 versioned registries 派生，是唯一 restart-safe runtime snapshot；
   `BLOCKED_TECHNICAL` 是先于所有外部 reason 的 global veto，会阻止完整 snapshot、使受影响旧
   READY row 失效/移除并令 `GET_CAPABILITIES` Fail Closed，组合时也不能被外部门原因遮蔽；
3. SQLite `run_record.failed`＋脱敏 `run_failure` 为耐久真相；Side Panel 只从
   `fallback_eligible` 派生 `FALLBACK_AVAILABLE`，失败 `GET_JOB` 保留 `job_id`，且第二次独立
   Owner 动作才可用新 `request_id`＋`fallback_from_job_id` 创建 current-page request。该任务必须
   同步 versioned migration、Pydantic/JSON Schema/generated TypeScript 与 Extension consumer。

因此 G3 是 `BLOCKED_TECHNICAL`，不是 PASS；Stage 3 不上传，Stage 4 不开始。
Task DAG 还把 `multimodal.001` 显式依赖到 task010，并要求跨 Stage 前上一 Gate 为 PASS；task010
完成本身不能替代独立 G3 Review，`assurance.005` 的传递依赖闭包覆盖其余全部 43 个 Task。

## Release policy

v0.0.0.1 不设置预发布阶段、固定 30 日健康观察或 soak。`G0–G5`、前四个 Assurance、UXOps005
与最终任务精确自有 Acceptance 集合之外的 Blocking Acceptance 通过后启动该任务；任务内完成
80 条 XHS/Douyin Owner MVP 基线，并对每个额外实际启用能力执行独立、不超过 20 条的激活检查；
外部门禁能力只能以 flag off、0 调用、0 live claim 的合法禁用结算，技术阻断不能结算。随后完成
安全门硬通过、模型能力通过或明确关闭/降级为仅建议模式、回滚、签字、部署、运行与在线 smoke，
安全未知或失败不能降级结算；全部成功后才签发 `G6 PASS`
并直接上线唯一 tag `v0.0.0.1`。任务内 Oracle 与 `G6 PASS` 都不是任务启动条件；上线后监控
不会形成等待门，只能触发修复、降级或回滚。

这不是降低门槛：安全、隐私、幂等、证据、恢复和回滚任一未知仍 Fail Closed。

## Data contract

`X2N_DATA_ROOT` 继续解析到 Owner 指定下载父目录下的 `xhs-douyin-2notion` 子目录，但角色被明确为
本机易失的下载/执行/活跃 SQLite working copy。活跃 SQLite 是逻辑真相源；耐久快照、导出和 runtime
receipt 统一进入：

`LinzeColin/Private-Database` 的 area `Private-MetaDatabase`，manifest
`domain=xhs-douyin-2notion`

唯一允许的访问面是
`KMOS/KMDatabase/machine/tools/private_db_client.py ingest|get|list|verify`。禁止 clone、直接 Git
写入或在验证 receipt 前声称耐久。客户端拒绝直接 `.sqlite/.db` 且单对象上限 95 MiB，因此实际
实现必须把一致性 SQLite 快照封装为非运行时归档、按 ≤90 MiB 分片，用 restore manifest 过滤
domain、校验 SHA-256、重组并运行 SQLite integrity；不得靠改名绕过红线。该实现由计划中的
`TSK.x2n.uxops.005` 完成，本 Review Resume 没有写入任何运行数据。
目标是整个 `X2N_DATA_ROOT` 排除于 Time Machine；只读实测当前根仍是历史逐子目录状态，尚未实现
whole-root exclusion。本 Resume 不调用 `tmutil`；`TSK.x2n.uxops.005` 必须经 Owner 明确授权记录
pre-state、执行整根排除并验证所有子路径，非 macOS 或任一 included 子路径 Fail Closed。本地 backup
始终只是易失回滚缓存，不能成为第二耐久目的地或满足 durability/Release Gate。

只读客户端审计还发现两项必须由 wrapper 补足的语义：全局 manifest 只按 SHA 幂等而非按 domain，
且 `verify` 是 area-global、发现缺对象时不会自动返回非零，还可能列出其他项目路径。Task005 已要求
domain-bound chunk envelope、精确 domain 行逐对象 get/hash/重组/恢复、opaque name、临时文件清理，
以及隔离的 Owner-authorized ephemeral auth；全 area verify 只允许做零路径披露的 redacted advisory，
其他 domain 缺失不阻断 x2n，x2n domain 缺失必须 Fail Closed。禁止 `put/delete`；未来显式授权
Task 可仅经 `private_db_client.py` 使用现有 Owner-authorized authenticated session，但不得接触
Token 值或修改/删除/撤销/轮换认证。
因此本项目删除语义是 active SQLite/派生 Sink 删除＋单调 deletion epoch/tombstone 防恢复复活；durable
hard erase 需要独立 Owner Private-Database 治理。本轮“没有调用 `gh api` 或写外部数据”属于过程声明，
不是离线 verifier 的独立观测。

## Historical integrity and isolation

- 原 Review final commit：`6b3f5464d1ed645d31c3650b9b51998c9e4fe1ab`。
- 原 `machine/facts/stage_3_gate_state.json` SHA-256：
  `0243a478273de9bda16803e7311ef56c7e461c2bc3b8c871c5d2c1c87cdd6772`，保持字节不变。
- 本地离线 Git 重验只保留一个 x2n worktree、一个 x2n local branch、其他项目零变更；0 open x2n PR
  是此前只读检查，本轮离线 verifier 未重新访问远端。
- 本 Resume authenticated session/Token 值/auth mutation 均零接触，真实账号/平台/真实
  Notion/模型/媒体处理为 0 / `NOT_RUN` 均是过程声明，
  明确标记为未被离线 verifier 独立观测。

## Local verification

- Resume schema/history/DAG/release/data/client-audit/isolation：全部 PASS。
- Focused Resume＋旧 Review：27/27 tests PASS（20 Resume＋7 历史 Review）。
- Phase 0.1 / Phase 0.5 当前 DAG 与治理回归：PASS。
- source-freeze 后的锁定 Python 3.12.13 fresh fast lane 是提交前强制门；权威结果只写入
  `machine/evidence/stage_3/review_resume_mvp/verification.json`，旧报告不得复用。
- 本轮不运行 full-release 的两次重复，因为没有产品实现或 release candidate 变更；fast lane 是
  有界 Blocking 验证，不是固定观察或 soak。

## Next run

下一独立 Run 只执行 `TSK.x2n.adapters.010` 与其 Acceptance。完成后必须再运行一次 Review Resume
重验 G3；只有 G3 真正 PASS 后才可上传 Stage 3 并开始 Stage 4。
