# Stage 7 受保护发布与运维手册

## 当前状态

`BLOCKED_T0702_PASS_SCOPE_STOP`，本地实现状态为 `LOCAL_MECHANISMS_READY`。T0701–T0708
的本地机制已经覆盖发布控制、Beta protected bootstrap、Beta Raw-only、M3 Canary、
Blue-Green/单 Timeline、GA 全流程、Codex Auto、Recovery Drill，以及只读 Patch Lifecycle/
Operations 决策；所有机制在缺前序、预算、registry、容量、age 绑定、供应链保证或受保护证据时
fail closed。账本区分 1 次 Secret 前 context 拒绝与 11 次 protected first attempt；最新
exact-main attempt 的 Alpha、Raw-only Beta 与 identity cleanup 均 PASS，Raw 远端恢复 100%，
Gmail mutation、M3、Processed 与 Timeline mutation 均为 0，GitHub rerun 为 0。T0702/S7AC-002
已通过；实际 M3、GA、Automation、Recovery Drill、Patch Canary、Patch apply 与 rollback 均未运行。
禁止把 T0702 PASS 或 `--preflight` 的退出码 0 解释为 Stage 7、最终 Acceptance 或生产 PASS。

历史 completion Run Contract 允许过 T0702 repair 的串行 first attempt，GitHub rerun 始终禁止。
该权限已经完成 T0702；当前 Owner 范围只允许收口 T0702 证据并明确停在 M3 前，因此不得新增
protected dispatch、受控交付或进入任何 post-Beta 阶段。

## Beta protected bootstrap 契约

`ProtectedBetaBootstrap` 只接受调用方显式注入的 Secret source、OAuth/Gmail/GitHub HTTPS transports 和 approved tmpfs root；不得自行枚举环境或读取其他 Secret。固定名称为 `MOOMOOAU_BETA_CONFIG`、`MOOMOOAU_SENDER_REGISTRY`、`MOOMOOAU_GITHUB_APP_PRIVATE_KEY`、`MOOMOOAU_OPAQUE_ID_KEY`、`MOOMOOAU_AGE_IDENTITY` 与 `MOOMOOAU_GMAIL_OAUTH`。

`MOOMOOAU_BETA_CONFIG` 必须声明 phase=`BETA_RAW_ONLY`、正整数消息预算、Key Epoch、age Recipient、GitHub App/Installation/Repository ID，以及不超过 24 小时的容量快照和 owner-provisioned LFS limits。Bootstrap 在任何 Gmail/GitHub 生产调用前验证 Alpha 前序、ACTIVE sender registry、RSA private key、容量写权限和 age Recipient/Identity 加解密绑定；生产默认只接受 `/dev/shm` 且必须由 Linux mountinfo 证明为 tmpfs，Runtime 单次执行后立即归零并删除 Identity、Token 和 opaque key。非 tmpfs override 只存在于合成测试装配中。

若配置中的 GitHub App Installation ID 返回 404，Bootstrap 只允许一次
`GET /app/installations?per_page=2` 有界校准；仅当 App 恰有一个未挂起、`selected` 且权限精确为
`contents:write`/`metadata:read` 的 Installation 时才可继续。随后生成的 Token 仍必须只包含配置中的
唯一 Repository ID 与同一最小权限，否则失败关闭；零个、多个、全仓选择、挂起或权限漂移均不得自愈。

此入口只能产生 Raw-only runner；不得装配 Parser、M3、Timeline 或 Release Asset 权限。
`.github/workflows/moomooau-beta.yml` 是唯一受保护 Beta 入口，仅允许 owner 在 `main` 上手动
`workflow_dispatch` 的首次尝试，并逐项绑定控制仓/owner/actor 数字 ID、expected commit、Workflow
ref、GitHub-hosted runner、`moomooau-beta` Environment 与同树 Alpha gate。两个 job 均在 checkout
或 Secret 注入前拒绝非 GitHub-hosted runner；Alpha job 不接触 Beta Secret，Beta 执行步只引用上述
六个精确名称。控制仓权限为 `contents: read`，禁止 rerun、schedule、artifact/cache、`git push`
和生产入口。
成功结果只输出既有 bucket、零值计数和 gate 布尔值，不公开精确预算或精确邮箱/恢复计数，并明确 M3、
生产健康与最终验收均未执行或宣称；失败输出固定 reason code，不回显异常或受保护值。postflight 必须
确认 `/dev/shm/moomooau-protected-beta-*` 已清空。

完整账本保留首次 aggregate-only 失败、GitHub App 分类修复、response-scope 修复与 metadata
verification 修复的全部公开安全历史。1 次 context 拒绝发生在 Secret 读取前；11 次 protected
执行均为 workflow attempt 1，Alpha 与 identity cleanup 均 PASS，前 10 次 Beta fail closed，
最后一次 Beta PASS，rerun 0。最终修复对单封无法取得可验证 metadata 的旧消息使用 typed、
per-message、bounded quarantine；404/结构不完整可隔离继续，任何 raw/snippet 泄漏、ID mismatch、
未请求 header 或权限/服务错误仍整次 fail closed。PASS 结果只公开 `TEN_PLUS` discovery/
verification bucket、`ONE` recovery bucket、Raw recovery 100% 和零 Gmail mutation/M3/Processed/
Timeline mutation；private namespace 只公开为非零 age ciphertext，不公开精确对象数量或仓标识。
T0702/S7AC-002 已关闭，但当前范围不得进入 M3。

## Blue-Green 与单一 Timeline 本地机制

`BlueGreenTimelineRunner` 只接受已经通过远端恢复门的 Raw proof，并在调用注入的 current/store/Timeline remote 前验证 Alpha、Beta、M3 前序和写容量。incumbent 与 candidate 使用同一个 `CanonicalRaw`、同一个 `DocumentEnvelope` 和同一次有界 extraction；candidate 只写版本化不可变 Processed 对象并再次远端恢复。写入前后均重新解密解析 `processed-current`，必须完全相等。同次运行语义一致即可报告确定性证据完整，但 T0704 绝不生成或写入 candidate current pointer；业务输出有差异时保持 incumbent 并要求独立受保护审批。

Timeline 聚合将每个 current Processed pointer 与同 source 的 canonical `TimelineEvent` 绑定。逻辑 `processed_snapshot_root` 只由排序后的 source ID、current pointer plaintext digest 和 Timeline Event plaintext digest 推导，不依赖 age 随机密文。Event 与 manifest 均以 append-only `.age` 对象写入同一个私有数据库命名空间，随后从 store 重新取回、解密、解析并重算 root。`SingleLatestTimelinePublisher` 只接收该恢复 proof 的 root 与 incumbent facts；健康状态必须始终恰好一个固定 live Asset，修复状态只能为零。

当前这些保证只在本地合成内存 remote 上验证。未配置 protected classification/parser registries，M3 尚未完成，受保护 Blue-Green 确定性证据运行尚未执行；因此不得宣称 T0704、AC-015、AC-028、AC-029 或 AC-030 已通过，也不得在此机制中提升 current pointer。不设自然日等待。

Owner 已授权 v1.0.2 successor baseline。`machine/tools/validate_evidence.py` 现在按任务的真实
Stage schema 路由，并同时核对 task graph、stage-local acceptance、final Acceptance 绑定和禁止项
计数。验证 PASS 只证明证据完整；T0701/T0702 protected Oracle PASS 不会提升其余 protected Oracle
`NOT_RUN`、final Acceptance 0/34、Stage 7 或生产 `BLOCKED`。

## GA 全流程本地机制

`GAFullPipelineRunner` 没有环境发现、Secret 读取或可执行生产入口；Gmail、单一私有仓、age、Timeline Release 与所有 registry 均由受保护装配层显式注入。首次远端读取前必须同时满足 Alpha→Beta→M3→Blue-Green 的 protected evidence、当前 Parser、owner 明确配置的正整数 stable Mutation Budget、容量写授权和全部 GA Feature Flag。任何一项缺失时远端调用为 0。

日常运行从同一私有仓恢复 `MooMooAU/State/gmail-sync-current.json.age`。周日或手动 Full Reconciliation 必须先由有效 History 水位计算增量候选，再独立全量扫描；只有两者实际相等才可记录 difference=0。首次导入或 History 404 没有独立候选时明确记为 `NOT_COMPARABLE`，不得伪装为零差异。非零差异在 Raw Fetch、M3 和 Timeline 前停止。

每个候选仍执行 metadata-first 验证；只有 `VERIFIED` 才可 Full Fetch。Raw age 提交与远端恢复、current Parser 的 Processed age 提交与远端恢复全部成功后，才进行第二次验证并从显式 stable Budget 中消费一次精确 `users.messages.trash`。Budget 用尽的已恢复消息保持 `ELIGIBLE` 并由下次 checkpoint 重放；已在 Trash 的同一消息只确认、不重复消费 mutation call。pending 消息若从新 Gmail 真值集合消失或 thread identity 改变，整次运行 fail closed 且不前移 checkpoint，不得静默丢弃已验证待办。任何不确定 Trash 结果立即停止且不前移 checkpoint。

Timeline 只聚合远端恢复且仍匹配 current Processed pointer 的 facts；snapshot 再次 age 提交/恢复后才调用单 Asset publisher。健康结果必须为恰好一个 live Asset。最后一步才 strict-CAS Gmail checkpoint，并重新读取、解密和逐字段比较；CAS 或恢复失败时整次运行不完成，下次按旧水位幂等补偿。公开结果只含 bucket/零差异状态，不含 Gmail ID、仓库定位或金融值，也明确 `production_health_claimed=false`。

上述机制仅由合成 ciphertext-only remote 验证。生产 Workflow 仍保持 Stage 5 fail-closed hold；Blue-Green 未完成、GA 容量与 Mutation Budget 未配置、真实 04:30 运行未观察，因此 T0705 与其 AC 仍为 `BLOCKED/PARTIAL/NOT_RUN`，绝不能因本地 runner 存在而启用 GA。

## Codex Automation 本地策略

`PassiveCodexAutoContract` 固定唯一普通 Automation 名称 `MooMooAU passive health check`、每日 `04:30 Australia/Sydney` 目标、公开仓 `LinzeColin/MetaDatabase`、唯一公开路径 `LinzeDatabase/MooMooAU/evidence/ops/latest.json`、48 小时最大证据年龄、`moomooau-ops` label 和每次最多一次 Issue 更新。Gmail、私有仓、Secret、加密对象、Workflow Dispatch、代码写入、既有对话 continuation 与数据平面依赖全部固定为 `false`，不能通过调用参数提升。

`CodexAutoMonitor` 只接受一个由 `StrictPublicInventoryPublisher` 产生的 bucket-only 文档，以及该唯一公开文件的 UTC commit 时间。健康且不超过 48 小时输出 `NONE`；超过 48 小时或状态异常只生成一条指向该公开路径的 `UPDATE_SINGLE_OPS_ISSUE` 指令。未来 commit 时间、任何非唯一 latest 路径或不一致文档直接 fail closed。重复输入得到同一计划；禁用时输出零 Issue，确定性数据平面不读取也不依赖 Automation。

这只是可执行本地 policy，不是实际 connector 或 owner-created Automation 证据。T0705 protected GA、冻结 validator 与上传顺序问题未解决前，禁止创建、修改、启用或运行 Automation，也不得写真实 Issue；T0706 与 AC-024 保持 `BLOCKED/PARTIAL/NOT_RUN`。

## Recovery Drill 本地机制

`RecoveryDrillRunContract` 固定依赖 T0706、每个角色最多一个样本、合计三个样本、私有仓只读，以及 Gmail、私有写入、Workflow Dispatch、M3 mutation、Identity 输出和明文持久化全部为零。未来 protected run 必须声明 Identity 来源为 owner 持有的 `MooMooAU-Recovery-Key.agekey`；仅使用 operational Environment Secret 不能满足 Recovery Key Oracle。

`RecoveryDrillRunner` 以一次 32-byte cryptographic nonce 为 Raw、Processed、Timeline 派生三个不同选择 nonce。注入的只读 source 必须分别用 Raw Manifest、Processed Manifest、Timeline private state 提供密文/明文摘要绑定和 opaque sample ID。密文经 official age 从 `/dev/shm/MooMooAU-Recovery-Key.agekey` 流入有界 SHA-256 sink；读取第一个样本前和解密时均验证路径、symlink、文件类型与私密权限。Runner 不返回明文，也不把路径、私有摘要、密文或 Identity 放入结果；未来 protected workflow 必须在 `finally` 中删除 tmpfs Identity，并由 postflight safety audit 验证无 Identity/明文残留。公开结果只含 Run/Code/Container 版本、角色计数、opaque selection root、耗时、安全计数与零权限计数。

任何角色选择、age 解密、密文摘要、明文摘要或 before/after log-and-artifact safety audit 失败，都在第一个失败角色停止，触发 KILL-005，并把 M3/new writes 关闭；不得继续读取后续角色。成功的 Local Synthetic 结果仍被 `RecoveryDrillGate` 标为 `PROTECTED_RECOVERY_DRILL_NOT_RUN`。T0706、owner key、read-only protected adapters、真实三角色密文和受保护日志扫描均未就绪，因此 T0707、AC-012、AC-032 仍为 `BLOCKED/NOT_RUN/PARTIAL`。

## 发布顺序与停止条件

每次只改变一个阶段，前一阶段的受保护 Evidence 必须先由 `Stage7ReleaseGate` 判为 `READY`：

1. **Alpha**：只运行合成数据；所有生产 Flag 为 `false`，Mutation Budget 为 0。
2. **Beta Raw-only**：先给出明确正整数 Beta message budget；只允许 Discovery、Raw、Public Evidence 和 Full Reconcile。Parser、M3、Timeline 关闭。
3. **M3 Canary**：Processing 必须先启用并产生 `COMPLETE` 或显式 safe-deferred Processed；Mutation Budget 固定为 1；在一次有界受保护运行中，每封消息必须先远端恢复，再调用精确 `messages.trash` 并确认；Timeline 仍关闭。不设自然日等待。
4. **Blue-Green**：在一次有界受保护运行中，对相同恢复 Raw 并行比较 incumbent/candidate；必须观测真实 Processed、Parser 比较、Timeline 发布和 Full Reconciliation；live Timeline 的最小和最大 Asset 数都必须为 1。不设自然日等待。
5. **GA**：必须显式配置经容量证据支持的正整数 Mutation Budget；至少观察一次真实 04:30 Australia/Sydney 全流程，且真实 Processed、Timeline 发布和 Full Reconciliation 均至少一次。不得使用代码默认值猜测。
6. **Codex Automation**：只在 GA 后创建；只读上一份公开健康证据。健康不动作；异常最多更新一个 Ops Issue。不得拥有 Gmail、私有仓、Secret、Workflow Dispatch 或代码写权限。
7. **Recovery Drill**：从私有密文各随机选一个 Raw、Processed、Timeline；owner Recovery Key 只能在 `/dev/shm`，恢复明文只进入 hash sink，不能进入普通 `runner.temp`、Artifact 或 Cache；公开输出只含聚合。
8. **Operations / Patch Lifecycle**：只有 T0707 受保护 Recovery Drill 通过后，才可装配不可变 Patch Candidate；供应链、恢复、容量、Kill、Reconcile、单 Timeline、成本与 scope 门全部通过后仍只进入 owner-approved promotion，不能自动关闭 Stage 7。

任一阶段出现下列情况立即停止提升：误伤大于 0、公开敏感发现大于 0、逻辑重复大于 0、Full Reconcile 差异大于 0、恢复率低于 100%、live Timeline Asset 超过 1、未知容量、Secret/Identity 泄漏、禁止端点尝试，或证据缺失/过期。

## 自动降级

- 误伤、禁止端点或公开泄漏：所有生产 Flag 关闭，Mutation Budget 设为 0，触发 Kill Gate。
- 私有提交或恢复失败：M3 关闭；Gmail 原件保留；仅在容量与恢复重新通过后恢复 Raw。
- Full Reconcile 差异：M3 关闭且 Budget 为 0；不得自动“修正”Gmail。
- Parser 失败：候选隔离，current 指针不变；Raw 不删除。
- Timeline 上传/删除/响应不确定：保持上一已验证 Asset，运行单 Asset 修复；不得建立历史图片仓。
- Codex Automation 失败：禁用 Automation；数据平面不受影响。
- Recovery Drill 任一角色、摘要、Identity 或 safety scan 失败：触发 KILL-005，M3 与新写入保持关闭，不读取后续角色。
- Patch Lifecycle 任一 assurance、受保护前序或运维门失败：冻结候选并保持精确的上一验证 commit；不得自动 apply 或执行 rollback。

## 恢复与回滚

1. 关闭受影响 Flag；M3 先归零。
2. 保留已提交且可验证的不可变 Raw；禁止覆盖或删除它。
3. 回退到机读 Patch Candidate 中精确的 40 位 `rollback_commit`，不使用漂移分支名。
4. Processed current 指针回到上一验证版本；失败候选保留隔离。
5. Timeline 由上一验证 Processed Snapshot 重绘并执行单 Asset 替换协议。
6. Gmail 仅在有精确 source Message ID 和受保护授权时调用 `messages.untrash`；不得 Thread Untrash，不得永久删除。
7. 重跑累计本地门、受影响 protected canary 和 Recovery Drill；全部通过前不得恢复更高阶段。

## 补丁生命周期

`PatchChangeSet` 只接受排序、去重、仓库相对的公开路径集合；输出只公开路径数量、确定性 `opaque_change_root`、归一化 surface 与 impact，不公开精确路径。分类规则只承认根目录 `moomooau-*` Workflow 与 `LinzeDatabase/MooMooAU/` 项目边界；边界外路径一律产生 `PATCH_PATH_OUTSIDE_MOOMOOAU_SCOPE`。是否需要 protected canary 完全由 impact 派生，调用方不能自行降级。

`PatchLifecycleRunContract` 将候选 commit、上一验证 commit、容器 digest、T0707 前序、候选 assurance 和运维快照绑定。`rollback_commit` 必须逐字符等于上一验证的 40 位 commit；candidate 与 rollback commit、不可变 pin、hash lock、可复现 SBOM、build provenance、全量测试、dependency audit、High/Critical=0、Secret/scope finding=0、冻结基线和合成恢复均须验证。受影响 impact 的 protected canary、T0707 protected Recovery、容量、Kill、公开证据新鲜度、Full Reconciliation、收益高于成本、恰好一个 live Timeline Asset 与公开证据零私有值也必须同时通过。

任一门失败只返回 `FREEZE_KEEP_LAST_VERIFIED` 及确定性修复动作，例如停止 backfill、保持 Kill/M3/new writes、暂停 Processed/Timeline、重建公开证据、修复单 Timeline 或移除 scope drift。全部门通过也只返回 `READY_FOR_OWNER_APPROVED_PROMOTION`；输入中的 `PROTECTED_GITHUB_ACTIONS` provenance 不是平台签名，结果始终声明 `patch_applied=false`、`production_health_claimed=false`、`stage7_completion_claimed=false`，且所有 GitHub 写入、私有仓、Gmail、Secret、Dispatch、deploy、rollback、Feature Flag 与 M3 effect 都为 0。

`.github/workflows/moomooau-patch-lifecycle.yml` 是 `contents: read`、无 Secret 的累计 policy preflight：验证固定 Action、hash lock、测试、Governance、dependency audit、可复现 SBOM 和 Secret scan。它允许的手动 `workflow_dispatch` 只重跑公开 policy，不能成为 protected candidate/canary 证明，也不能 apply、deploy、rollback 或提升发布阶段。真实 Patch Candidate、protected canary、owner approval 与 rollback 执行必须在任务包顺序冲突解决后由独立受保护入口提供；当前全部为 `NOT_RUN`。

## 验证入口

本地/无 Secret 实现前置：

```bash
PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/tmp/moomooau-stage7-hypothesis python -m pytest -q tests/tasks/test_t07*.py
python machine/stages/S7/tools/validate_stage7.py --governance-root /path/to/pinned/Governance --preflight
```

最终 Stage 7 验证不带 `--preflight`；在所有 protected Evidence 尚未完成前，它必须以非零退出并报告当前受保护阻塞状态，不能把本地机制验证提升为最终 PASS。
