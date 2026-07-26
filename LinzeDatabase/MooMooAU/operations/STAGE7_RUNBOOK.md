# Stage 7 受保护发布与运维手册

## 当前状态

交付状态为 `PROTECTED_GA_SECOND_ATTEMPT_FAILED_METADATA_REPAIR_AUTHORIZED`，Stage 7
验收覆盖状态为
`T0705_TWO_FAILED_HEADS_FROZEN_METADATA_REPAIR_AUTHORIZED_PENDING`。T0701–T0708
的本地机制已经覆盖发布控制、Beta protected bootstrap、Beta Raw-only、M3 Canary、
Blue-Green/单 Timeline、GA 全流程、Codex Auto、Recovery Drill，以及只读 Patch Lifecycle/
Operations 决策；所有机制在缺前序、预算、registry、容量、age 绑定、供应链保证或受保护证据时
fail closed。T0702 账本区分 1 次 Secret 前 context 拒绝与 11 次 protected first attempt；最终
Raw-only Beta PASS。T0703 的六个失败 exact-main head 保持不可变且从未 rerun：第五次留下一个
可恢复 Processed lineage 与未精确归因的 Gmail Trash 聚合变化，第六次在 `PROCESSED_PLAN`
零新增效果停止。第七个不同 exact-main head 的 attempt 1 已通过 authority、历史 label 零写入
reconciliation 与 identity cleanup；Raw+Processed 远端恢复 100%，当前运行 Gmail mutation、
private write、collateral mutation 与 Timeline write 均为 0。独立前后核验确认 private
head/tree/path counts 与 Gmail Trash 聚合不变。T0703/S7AC-003 因此 PASS。

T0704 首次 exact-main attempt 1 已通过 authority 与 identity cleanup，并远端恢复 candidate
Processed shadow 和 Timeline snapshot；`processed-current` 路径及 blob 身份保持不变。随后固定
Release Asset 恢复失败，清理后 live Asset 为 0，并留下一个加密修复状态。该失败 head 已冻结，
rerun 与 redispatch 均为 0。唯一新 exact-main 修复 head 的 attempt 1 已通过 authority、
Blue-Green 与 identity cleanup：复用并恢复既有 candidate/snapshot，跟随一个限定在 GitHub
release-assets CDN 的 302 且不转发 Authorization，最终恢复并验证恰好一个非空 age 加密
Timeline。受保护 repair 的 Gmail mutation、processed-current、candidate/snapshot 新写入均为 0；
独立聚合核验只确认一个 encrypted Timeline state commit，未解密或公开私有定位。
T0704/S7AC-004 因此 PASS，但不等于 Stage 7、最终 Acceptance 或生产 PASS。

T0705 两个不同 exact-main protected head 均只执行 attempt 1。首次 run `30182491342` 与第二次
run `30184702520` 的 authority 和 identity cleanup 均 PASS，protected GA 均 FAILED，live
schedule hold 均未启用。第二次独立聚合核验确认新增 private commit 0、checkpoint 未创建、
唯一 encrypted latest Timeline 仍为 1；一次性 authority 与 production enablement 已清除。
两个失败 head 均已冻结，rerun 与 redispatch 为 0。

protected 输出没有披露第二次 exact runtime exception。不可变 T0703 同邮箱回执证明存在
metadata quarantine bucket；静态路径证明 GA pre-Raw candidate loop 没有捕获 typed
`MessageMetadataUnverifiable`，而 Beta/M3 已隔离。因此当前只声明 high-confidence defect，
不伪造线上精确 root cause。

当前精确 successor Run Contract 的总 delivery 预算为 4，两个 launch 已消耗 2；总 rehearsal
dispatch 预算为 3，两个失败 attempt 已消耗 2。只剩一次 pre-Raw metadata quarantine repair
delivery、一个新 exact-main attempt-1 protected `SCHEDULE_REHEARSAL`（rerun 0）和一次
receipt/schedule-closure delivery。它复用现有 `moomooau-beta` Environment 的八个精确 Secret
名称，不复制 Secret 值；受保护修复运行通过后才启用已提交的 04:30 Australia/Sydney schedule。
rehearsal 必须明确记录 `platform_schedule_event_observed=false`，不能伪称 GitHub schedule
event。T0706、Recovery Drill、Patch Lifecycle protected execution、最终 Acceptance 与最终
发布均未授权。

## Beta protected bootstrap 契约

`ProtectedBetaBootstrap` 只接受调用方显式注入的 Secret source、OAuth/Gmail/GitHub HTTPS transports 和 approved tmpfs root；不得自行枚举环境或读取其他 Secret。固定名称为 `MOOMOOAU_BETA_CONFIG`、`MOOMOOAU_SENDER_REGISTRY`、`MOOMOOAU_GITHUB_APP_PRIVATE_KEY`、`MOOMOOAU_OPAQUE_ID_KEY`、`MOOMOOAU_AGE_IDENTITY` 与 `MOOMOOAU_GMAIL_OAUTH`。

`MOOMOOAU_BETA_CONFIG` 必须声明 phase=`BETA_RAW_ONLY`、正整数消息预算、Key Epoch、age Recipient、GitHub App/Installation/Repository ID，以及不超过 24 小时的容量快照和 owner-provisioned LFS limits。Bootstrap 在任何 Gmail/GitHub 生产调用前验证 Alpha 前序、ACTIVE sender registry、RSA private key、容量写权限和 age Recipient/Identity 加解密绑定；生产默认只接受 `/dev/shm` 且必须由 Linux mountinfo 证明为 tmpfs，Runtime 单次执行后立即归零并删除 Identity、Token 和 opaque key。非 tmpfs override 只存在于合成测试装配中。

若配置中的 GitHub App Installation ID 返回 404，Bootstrap 只允许一次
`GET /app/installations?per_page=2` 有界校准；仅当 App 恰有一个未挂起、`selected` 且权限精确为
`contents:write`/`metadata:read` 的 Installation 时才可继续。随后生成的 Token 若回显
repository/permission/selection，回显值必须精确匹配配置中的唯一 Repository ID 与同一最小权限。
GitHub 合法省略 repository 回显时，Bootstrap 必须用该 token 执行
`GET /installation/repositories?per_page=2`，并证明 `total_count=1` 且唯一 Repository ID 精确
匹配；最多两个结果之外不枚举。token 最长一小时有效期以同一响应的有界 GitHub `Date` 为参考。
任何 Date 漂移、零个/多个仓、全仓选择、挂起、权限漂移或探测失败均销毁 token 并失败关闭。

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
T0702/S7AC-002 已关闭；其历史回执与账本继续作为 T0703 的不可变前序。

## Blue-Green 与单一 Timeline 本地机制

`BlueGreenTimelineRunner` 只接受已经通过远端恢复门的 Raw proof，并在调用注入的 current/store/Timeline remote 前验证 Alpha、Beta、M3 前序和写容量。incumbent 与 candidate 使用同一个 `CanonicalRaw`、同一个 `DocumentEnvelope` 和同一次有界 extraction；candidate 只写版本化不可变 Processed 对象并再次远端恢复。写入前后均重新解密解析 `processed-current`，必须完全相等。同次运行语义一致即可报告确定性证据完整，但 T0704 绝不生成或写入 candidate current pointer；业务输出有差异时保持 incumbent 并要求独立受保护审批。

Timeline 聚合将每个 current Processed pointer 与同 source 的 canonical `TimelineEvent` 绑定。逻辑 `processed_snapshot_root` 只由排序后的 source ID、current pointer plaintext digest 和 Timeline Event plaintext digest 推导，不依赖 age 随机密文。Event 与 manifest 均以 append-only `.age` 对象写入同一个私有数据库命名空间，随后从 store 重新取回、解密、解析并重算 root。`SingleLatestTimelinePublisher` 只接收该恢复 proof 的 root 与 incumbent facts；健康状态必须始终恰好一个固定 live Asset，修复状态只能为零。

当前机制已由 T0704 exact-main protected PASS 验证。paired empty protected
classification/parser registries 明确产生 SAFE_DEFERRED incumbent/candidate，未虚构解析事实。
T0704 不把超过 24 小时的 config snapshot 当作写授权：GitHub App token 只先用于读取
Repository-ID 绑定的 metadata、完整 default-branch tree 和固定 live Release；保守重算
repository/largest-object/LFS-continuity/live-asset capacity 后才交换 Gmail credential。
tree truncated、出现无法证明零新增 LFS 的 `.gitattributes`、Release 非单资产或容量非可写，
均在 Gmail 读取和仓库写入前 fail closed。
首次 T0704 run 已失败并冻结；唯一 redirect-recovery attempt 1 随后 PASS，两个 head 均不得再次
运行。成功修复的 candidate 与 snapshot 新写入均为 0，Timeline state 新写入为 1。Release Asset
下载只接受 200，或一个 HTTPS
`release-assets.githubusercontent.com/github-production-release-asset` 跳转；第二跳不得携带
Authorization，也不得继续跳转。T0704/S7AC-004 的 PASS 只来自精确受保护回执；未提升
current pointer，未单独提升仍受最终 Acceptance 约束的 AC，也未进入 T0705。不设自然日等待。

Owner 已授权 v1.0.2 successor baseline。`machine/tools/validate_evidence.py` 现在按任务的真实
Stage schema 路由，并同时核对 task graph、stage-local acceptance、final Acceptance 绑定和禁止项
计数。验证 PASS 只证明证据完整；T0701–T0704 protected Oracle PASS 不会提升其余 protected
Oracle `NOT_RUN`、final Acceptance 0/34、Stage 7 或生产 `BLOCKED`。

## GA 全流程本地机制

`GAFullPipelineRunner` 没有环境发现、Secret 读取或可执行生产入口；Gmail、单一私有仓、age、Timeline Release 与所有 registry 均由受保护装配层显式注入。首次远端读取前必须同时满足 Alpha→Beta→M3→Blue-Green 的 protected evidence、当前 Parser、owner 明确配置的正整数 stable Mutation Budget、容量写授权和全部 GA Feature Flag。任何一项缺失时远端调用为 0。

日常运行从同一私有仓恢复 `MooMooAU/State/gmail-sync-current.json.age`。周日或手动 Full Reconciliation 必须先由有效 History 水位计算增量候选，再独立全量扫描；只有两者实际相等才可记录 difference=0。首次导入或 History 404 没有独立候选时明确记为 `NOT_COMPARABLE`，不得伪装为零差异。非零差异在 Raw Fetch、M3 和 Timeline 前停止。

每个候选仍执行 metadata-first 验证；只有 `VERIFIED` 才可 Full Fetch。Raw age 提交与远端恢复、current Parser 的 Processed age 提交与远端恢复全部成功后，才进行第二次验证并从显式 stable Budget 中消费一次精确 `users.messages.trash`。Budget 用尽的已恢复消息保持 `ELIGIBLE` 并由下次 checkpoint 重放；已在 Trash 的同一消息只确认、不重复消费 mutation call。pending 消息若从新 Gmail 真值集合消失或 thread identity 改变，整次运行 fail closed 且不前移 checkpoint，不得静默丢弃已验证待办。任何不确定 Trash 结果立即停止且不前移 checkpoint。

Timeline 只聚合远端恢复且仍匹配 current Processed pointer 的 facts；snapshot 再次 age 提交/恢复后才调用单 Asset publisher。健康结果必须为恰好一个 live Asset。最后一步才 strict-CAS Gmail checkpoint，并重新读取、解密和逐字段比较；CAS 或恢复失败时整次运行不完成，下次按旧水位幂等补偿。公开结果只含 bucket/零差异状态，不含 Gmail ID、仓库定位或金融值，也明确 `production_health_claimed=false`。

`ProtectedGAEntrypoint` 已把 T0702、T0703、T0704 精确 PASS 回执、当前 Run Contract、同树 gate
digest、owner/exact-main/workflow ref、one-shot exact-head authority 与 attempt 1/rerun 0 绑定。
它只在 Secret 前 context gate 通过后，使用现有八个 protected input 在内存中派生 GA config；
GitHub App 先刷新真实私有仓容量，再允许 Gmail credential exchange。`workflow_dispatch` 只调用
与 04:30 生产运行相同的 `RunTrigger.SCHEDULE` planner path，并公开标记为
`SCHEDULE_REHEARSAL`。

首次 protected rehearsal 的 paired-empty SAFE_DEFERRED 修复候选在第二个 exact-main head
仍然 FAILED，不能计为 PASS；两个 head 都已冻结。第二次 protected 输出没有披露 exact
exception。唯一新修复只在 GA 首次 pre-Raw metadata read 捕获 typed
`MessageMetadataUnverifiable`：该 candidate 计入 quarantine 后跳过，不得 Full Fetch、写入、
Trash 或从既有 pending replay 集合消失。Raw/Processed 恢复后的 second verification 继续
fail closed；ACTIVE registry 与 paired-empty SAFE_DEFERRED 行为保持不变。新入口明确拒绝两个
失败 head，并把 authority job 验证后的 exact head 通过 job output 绑定给 protected
Environment job。当前新 repair rehearsal 尚未运行，因此 T0705 与其 AC 仍为
`BLOCKED/PARTIAL/FAILED`；本地修复候选不能替代精确 protected receipt。

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
5. **GA**：必须显式配置经实时容量证据支持的正整数 Mutation Budget；一次 exact-main protected
   `workflow_dispatch` 可调用与生产调度相同的 SCHEDULE planner path，无需等待墙钟到达
   04:30。该次运行必须如实称为 `SCHEDULE_REHEARSAL`，证明真实 Processed、Timeline 发布、
   checkpoint-last 与 Full Reconciliation，并保持 platform schedule event 计数为 0；PASS 回执
   绑定后才启用已提交的 04:30 Australia/Sydney schedule。不得使用代码默认值或假造 schedule
   event。
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
