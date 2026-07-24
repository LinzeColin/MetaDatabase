# MooMooAU S0–S7 整体复审

## 1. 结论

- 复审状态：`FAIL_REMEDIATION_REQUIRED`
- 被复审提交：`18011918884a24457183e3da1d1ba32f94846484`
- 当前控制包：`MMAU-ARCHIVE-TP-2026-07-22-V1.0.4`（RMD-04 基线保真控制继任版本）
- 历史 v1.0.1 Manifest SHA-256：`c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f`
- 复审时间：`2026-07-22T04:54:25Z`
- RMD-01 复核时间：`2026-07-22T05:27:29Z`
- RMD-02 继任包时间：`2026-07-22T07:09:44Z`
- RMD-03 累计 CI 复核时间：`2026-07-22T08:25:00Z`
- RMD-04 生产组合复核时间：`2026-07-22T09:19:42Z`
- 外部效果：真实 Gmail 调用 0、Gmail 修改 0、私有仓调用 0、Secret 读取 0、远端发布 0、生产运行 0、GitHub 上传 0

S0–S7 已形成大量 fail-closed 本地机制，task tests、静态检查、类型检查、冻结包校验、Governance、
依赖漏洞与可复现 SBOM 门均通过。原复审发现正式 34 个 Acceptance Contract 的指定测试和
evidence 全部不存在；RMD-01 已补齐这层控制面，并以确定性 schema、builder 和 validator 将冻结契约、
traceability、test entry、task evidence 与未来 Oracle observation 绑定。当前 34/34 record 结构有效，
但最终 Oracle 均未执行，关联 task final claim 也尚未全 PASS，因此最终结果仍是 0/34 PASS、34/34
BLOCKED。RMD-04 已在源码和 Workflow 中组装 Gmail → Raw → Processed → Recovery → exact M3 →
Timeline 全链路，并以合成 HTTP 端到端证明顺序与零附带损害边界；真实生产、受保护环境和远端
Workflow 仍未运行。

RMD-02 已消除 stage evidence validator 与状态真源冲突；RMD-03 已让 S3–S6 最终树 Workflow 入口
显式选择累计模式，并以无参数历史模式作为 fail-closed 负向控制；RMD-04 已关闭本地 production
composition 缺口，但没有解决 assurance provenance 或任何受保护门。唯一当前跨维度状态是
`machine/status/latest.json`：evidence
完整性 58/58 PASS，本地/合成机制证据 58/58，正式任务 7/58，受保护 Oracle 0/43，最终验收 0/34，
生产运行 0，整体状态 `LOCAL_MECHANISMS_EVIDENCED_FINAL_ACCEPTANCE_BLOCKED`。因此仍不可上线、
不可宣称 GA、不可整体上传。

## 2. 复审合同与证据边界

复审依据按以下优先级锁定：

1. 用户目标与原始 Roadmap；
2. 用户 ZIP 的来源哈希与 `taskpack/SOURCE_PROVENANCE.json`；
3. 冻结 v1.0.1 Task Pack、34 RQ、34 AC、58-task DAG 与 traceability matrix；
4. 当前实现、测试、evidence、Workflow、运维与安全资料；
5. 在干净临时环境中独立重跑的本地门禁。

原复审轮是只读复审。除了本报告和交接状态，不修复发现，不访问真实 Gmail、私有仓或 Secret，不运行
protected Oracle、Canary、Recovery Drill、生产 Workflow、部署或 rollback，不 push。

用户提供的两份原始输入与已记录来源完全一致：

| 输入 | SHA-256 | 结论 |
|---|---|---|
| Roadmap v1.0.0 | `36dc9546a77fdaa09bd7db19a6d53e02668505e85224bf79d33245fbd7cfaf71` | 与 provenance 一致 |
| Product Design Taskpack v1.0.0 ZIP | `c827b672388e4c2688c17f5cae9e7f73d578d8c73444e680ef6f177f24b80563` | 与 provenance 一致 |

## 3. 阻断发现

严重度定义：P0 表示正式交付或数据安全目标不能成立；P1 表示发布、CI 或证明完整性被阻断；P2 表示
状态真源或长期维护存在显著风险。

### REV-P0-001 — 34/34 最终 Acceptance 的执行与证据层缺失

状态：`REMEDIATED_CONTROL_PLANE / FINAL_ACCEPTANCE_BLOCKED`

**原复审证据（被复审提交 `18011918884a24457183e3da1d1ba32f94846484`）**

- `machine/contracts/acceptance_contract.json` 为 AC-001–AC-034 各指定一个
  `tests/acceptance/test_ac_NNN.py` 命令；34 个文件全部不存在，`tests/acceptance/` 目录不存在。
- 34 个 `evidence/acceptance/AC-*.json` 全部不存在，`evidence/acceptance/` 目录不存在。
- `python -m pytest -q tests/acceptance` 退出码为 4：目标目录不存在。
- `evidence/stage7/latest.json` 和 S7 task status 如实记录
  `final_acceptances_passed=0`。

**RMD-01 复核**

- 冻结指定的 34 个 `tests/acceptance/test_ac_NNN.py` 和 34 个精确
  `evidence/acceptance/AC-*.json` 已存在；`evidence/acceptance/latest.json` 绑定全部记录的 Merkle-like
  root hash。
- 结构 validator 报告 34 valid、0 invalid；默认模式只证明结构有效，`--require-pass` 在 0/34 PASS
  时以退出码 1 fail closed。
- 34 个冻结 pytest 命令均可收集并到达统一 Pass Gate；当前均因
  `FINAL_ORACLE_NOT_EXECUTED` 和关联 task final claim 的 `PARTIAL/NOT_RUN` 明确失败，而非 collection
  error。
- 34 份 evidence 均为 `scope=LOCAL_ACCEPTANCE_CONTROL_PLANE`、`oracle_status=NOT_RUN`、
  `acceptance_status=BLOCKED`、`pass_gate=false`；本轮禁止项计数和外部效果均为 0。
- Oracle observation schema 绑定冻结 environment/input/oracle/threshold/pass-gate、证据哈希、祖先提交和
  protected attestation；任何缺失或漂移都会拒绝 PASS。

**影响**

246 个 task tests 只能证明局部机制，不能替代冻结 AC 的端到端 Oracle、threshold 与 Pass Gate。
RMD-01 消除了“无执行入口/无 evidence”的控制面缺口，但没有执行最终 Oracle，也没有把局部绿色状态
升级为最终 PASS。Roadmap 的最终完成定义第 1 条和 PRD 的 GA 定义仍未满足。

**所需修复**

控制面修复已由 RMD-01 完成。剩余工作是在其他复审问题修复、明确授权和正确受保护环境就绪后，逐条
执行冻结最终 Oracle，关闭每个关联 task 的 `PARTIAL/NOT_RUN` final claim，并让生成器从可核验 observation
推导 PASS；在此之前必须保持 `NOT_RUN/BLOCKED`。

### REV-P0-002 — 04:30 Workflow 没有运行归档产品

状态：`REMEDIATED_BY_RMD_04_LOCAL_SYNTHETIC / PROTECTED_AND_PRODUCTION_NOT_RUN`

**原复审证据**

- `.github/workflows/moomooau-production.yml` 的调度配置是
  `30 4 * * *` + `Australia/Sydney`，并支持手动触发。GitHub 当前官方语法允许 schedule 使用 IANA
  `timezone`；这一配置本身有效，且官方也说明 scheduled run 可能延迟或丢弃：
  [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax?apiVersion=2022-11-28)。
- 该 Workflow 唯一业务命令是 `python -m moomooau_archive.run_schedule`，只输出调度计划；随后断言
  `MOOMOOAU_STAGE5_PROTECTED_ORACLE=NOT_RUN` 并结束。
- `pyproject.toml` 唯一产品脚本指向 `moomooau_archive.cli:main`；该 CLI 明确要求
  `--synthetic`，且 `process/timeline/m3/reconcile` 只返回 Stage 1 degraded 占位状态。
- `GAFullPipelineRunner` 包含有价值的库级全链路，但源代码中没有生产 composition root 将受保护配置、
  Gmail、私有 GitHub、age、checkpoint、Raw、Processed、recovery、exact M3、Timeline 与公开 evidence
  组装并交给 Workflow 运行。
- 多个生产注入边界仍只有 Protocol 或 test-support 实现，例如
  `FirstImportTimestampSource`、`RandomRecoverySampleSource`、`RecoveryDrillSafetyAudit`，以及只存在于
  `tests/stage7_support.py` 的 `OfficialAgeTimelineCrypto`。

**原影响**

即使开启 `MOOMOOAU_PRODUCTION_ENABLED`，当前 Workflow 也不会发现、归档、恢复验证或移动任何邮件，
更不会替换最新 Timeline。用户目标中的 cloud-only 每日系统并不存在可执行部署入口。

**原所需修复**

新增唯一生产 composition root 与 fail-closed 命令，补齐受保护 adapter/config 绑定，将调度 watermark 与
补偿状态接入 encrypted remote checkpoint，并让 Workflow 调用完整 runner。上线前必须通过 synthetic
E2E、protected canary、Recovery、M3、Timeline 和公开 evidence Oracle；本报告不授权这些操作。

**RMD-04 复核**

- 新增唯一 `moomooau_archive.production` composition root；CLI 只接受显式 `--contract-only` 或
  `--execute-protected`，缺少、未知或漂移配置均 fail closed。
- composition 在任何 OAuth/GitHub 凭证交换前验证八个精确 Secret、私有 Repository ID、age
  recipient/identity、容量快照、分类/解析注册表和 ALPHA → BETA → M3 → BLUE_GREEN 前序观察。
- 生产 Workflow 安装 hash-locked 依赖与本项目，固定官方 age 下载 SHA-256，只把八个精确 Secret
  传给完整 GA runner；默认开关关闭，未执行真实生产。
- 合成 Gmail/GitHub HTTP 端到端运行处理 1 封确定性验证消息，Raw 与 Processed 均 age 加密并从远端
  恢复后才执行一次 exact `users.messages.trash`；Timeline 资产最大值和最终值均为 1。
- 加密 checkpoint v2 记录最后成功 Sydney 日期并兼容读取 v1；远端恢复 Processed lineage 提供首次导入
  时间。阻塞的前序观察在任何 credential exchange 或远端调用前停止，临时密钥、令牌与 identity 被销毁。
- `machine/contracts/production_composition.json` 只记录 1 次本地合成全链路；真实 Gmail、私有仓、
  protected Oracle、生产 Workflow、外部写入和发布计数全部为 0，不声明生产健康。

因此 `REV-P0-002` 的本地 composition 缺口已关闭；protected canary、真实 Recovery/M3/Timeline、GA
观察和最终 AC 仍由后续授权门控制，不能据此上线。

### REV-P0-003 — 冻结 task verification 与 Stage 1–7 evidence schema 自相矛盾

状态：`REMEDIATED_BY_RMD_02`

**原复审证据**

- 冻结 `machine/contracts/task_graph.json` 的 58 个 task verification 都调用
  `machine/tools/validate_evidence.py evidence/tasks/Txxxx.json`。
- 该冻结 validator 明确只接受 `moomooau.stage0-evidence.v2`、`stage_id=S0`、S0 字段集合和
  S0 acceptance ID。
- 对 58 个 task evidence 运行该权威 validator：S0 为 7 PASS；S1–S7 为 51 FAIL。由于对应 task
  test 均通过，51 个冻结 task verification 的失败点就是其 evidence validator 部分。
- 冻结 task graph 同时仍记录 S0 7 个 `completed`，S1–S7 51 个 `planned`。

**原影响**

严格按照当前冻结 v1.0.1 不可能同时做到“Stage 1–7 使用各自 evidence schema”与“每个 task 的冻结
verification 通过”。这是任务包权威层冲突，不得靠修改 evidence 字段、冒充 S0 或跳过命令消除。

**RMD-02 复核**

- Owner 明确选择方案 1，授权建立不改变产品语义的 v1.0.2 基线保真继任版本；授权范围只覆盖
  stage-aware evidence validation 与唯一跨维度状态权威。
- `machine/tools/validate_evidence.py` 保留 S0 既有语义；S1–S7 根据 task graph 的 stage 选择对应 schema、
  stage-local acceptance contract，并精确绑定 task、final AC、禁止项和安全 evidence reference。
- 冻结 task graph、34 RQ、34 AC、追踪矩阵、Kill Criteria、Canonical Facts 与 v1.0.1 Manifest 本体均按
  固定 SHA-256 验证未变；58 个 task verification 路径本身无需改写。
- 58/58 task evidence 现均通过权威结构与绑定验证；这只证明 evidence 完整性和本地机制证据，validator
  同时输出正式 task status、final claim、protected Oracle 与 `production_ready=false`，不会提升状态。
- 负向测试证明错误 stage schema、错误局部/最终 AC 绑定、越界路径、禁止项非零和虚假 PASS 均 fail
  closed。

### REV-P1-004 — S3–S6 历史 CI 会在最终上传时确定性失败

状态：`REMEDIATED_BY_RMD_03_LOCAL_REPLAY / REMOTE_CI_NOT_RUN`

**证据**

- `moomooau-stage3-ci.yml` 至 `moomooau-stage6-ci.yml` 都监听
  `LinzeDatabase/MooMooAU/**`，所以任何最终快照都会触发全部历史 Workflow。
- 它们分别直接调用 `validate_stage3.py` 至 `validate_stage6.py` 的 CLI。
- 当前树上四个命令分别因
  `scope.no_stage4_or_production_authority`、`scope.no_stage5_or_production_authority`、
  `scope.no_stage6_or_production_execution`、`scope.no_stage7_or_production_execution` 退出 1。
- S7 cumulative preflight 能通过这些历史层，是因为 Python 内部调用显式传入 `allow_stageN=True`；旧
  Workflow CLI 没有对应参数。

**影响**

直接上传当前最终树会得到红色 S3–S6 CI，即使 S7 cumulative preflight 为绿；因此当前状态不满足可合并
与上线条件。

**所需修复**

让历史 Workflow 的入口具备确定性的 cumulative-final 模式，或将其触发范围限定为真正的历史层；新增
离线 Workflow command matrix，证明最终树上所有被触发命令均为绿，且不弱化各阶段的 fail-closed
语义。

**RMD-03 复核**

- S3–S6 validator CLI 新增显式 `--cumulative-final`，分别只把既有 `allow_stage4` 至 `allow_stage7`
  设为真；其他契约、安全、发布、evidence、只读和零外部效果检查原样执行。
- 四份历史 Workflow 均显式传入该参数，且各自 validator 反向要求 Workflow 必须保留该参数。
- `machine/contracts/workflow_command_matrix.json` 以精确 Workflow SHA-256、工作目录、命令、预期退出码
  和唯一历史 scope failure 绑定 S3–S6。
- 离线矩阵累计模式 4/4 退出 0 且 `PASS`；无参数历史默认模式 4/4 退出 1 且 `BLOCKED`，每项只保留
  原 later-stage scope failure；回放前后项目与四份 Workflow 的树摘要一致。
- 该结论只覆盖本地只读入口。远端 Workflow runs、protected Oracles、生产 runs、外部写入和发布均为
  0/NOT_RUN，不能据此声称远端 CI 或上线完成。

### REV-P1-005 — 当前分支历史永久禁止 push

**证据**

- 当前 HEAD 的祖先包含 taskpack 明确标记为永久禁止 push 的本地原始导入提交
  `67a324a95cb66e7a4e8b6081625300ae68fa6327`。
- 当前分支与 `origin/main` 的 merge-base 为
  `2f77723bf52f54e16f23958cc72e5bcfc3dcae71`，复审时 `origin/main` 已前进到
  `6777c8fcce75a36741b70c2858c8bc5fff17d440`。
- `taskpack/00_READ_ME_FIRST.v1.0.1.md` 要求所有阶段、复审和修复完成后，才从最新
  `origin/main` 创建干净快照历史并整体上传。

**影响**

当前分支只能作为本地开发与审计历史，不能成为最终 push 来源。

**所需修复**

所有发现闭环且重新复审通过后，从届时最新且干净的 `origin/main` 建立一次性 snapshot worktree，复制
经验证的最终树、重新运行全部门禁，仅上传干净 snapshot commit。不得 rebase 或直接 push 当前分支来
规避这一约束。

### REV-P1-006 — 两个“不同模型独立复审”的仓内证据不足以独立验证来源

**证据**

- 两个 S6 review JSON 声称分别来自 GPT-5.6-sol 与 GPT-5.6-terra，并要求“忠实持久化 actual reply”。
- 当前记录只有结构化摘要、自填 model family/task 名称和相同秒级时间；没有原始 reply、不可变 reply
  hash、可核验 task/thread 标识或外部 attestation。
- `moomooau-stage6-model-assurance.yml` 只运行本地 schema/distinct-string tests，不调用模型，也不能证明
  两次实际独立执行。

**影响**

仓库当前可证明“有两个结构不同的记录”，不能从现有制品独立证明“两个不同模型实际完成过独立复审”。
本复审将来源状态记为 `UNKNOWN`，不指控记录虚假，也不把它们计为最终 AC-033 的充分证明。

**所需修复**

重新执行两次明确隔离的只读复审，保留最小且不含敏感内容的可核验 provenance（例如不可变 reply hash
和平台 task 标识），并让 validator 验证 provenance 结构、不同执行与结论闭包；模型仍不得接触真实
邮件、Secret 或私有数据。

### REV-P2-007 — 冻结状态真源与实现 overlay 冲突

状态：`REMEDIATED_BY_RMD_02`

**原复审证据**

- 冻结 `README.md` 仍写明“Stage 1 尚未开始”。
- 冻结 task graph 仍将 S1–S7 的 51 个 task 标为 `planned`。
- 非冻结 S7 status/evidence overlay 同时写明 `LOCAL_MECHANISMS_READY`、0 个正式 completed task、0 个
  protected Oracle 和 0 个 final acceptance。
- `README.md` 与 task graph 都在 v1.0.1 Manifest 内，不能直接编辑而仍声称 manifest identity 未变。

**原影响**

不同入口会让维护者对“代码是否实现”“task 是否正式完成”“是否可生产”得到不同答案，增加误发布和
错误决策风险。

**RMD-02 复核**

- 新增 `machine/contracts/delivery_status_model.json`，裁定产品义务、正式 task graph、source records、
  派生 facts/docs 与唯一当前状态之间的优先级。
- `machine/status/latest.json` 是唯一当前跨维度状态；builder 从 58 份 task evidence、冻结 task graph、
  34 份最终 acceptance evidence 和禁止项计数确定性重建，validator 以 JSON Schema 和 byte-equivalent
  rebuild fail closed。
- 根 README、13 份 Governance facts 与七份人类文档均从或明确指向该状态，旧 v1.0.1 Manifest 只作为
  不可变历史本体保留，不再被解释为当前实现或生产状态。
- 状态明确分离 evidence integrity、local mechanism evidence、formal task completion、protected Oracles、
  final Acceptance、production readiness 与 publication；任何本地绿色均不能使生产状态通过。

## 4. 最终完成定义逐项判定

| Roadmap 最终条件 | 本地机制 | 正式判定 |
|---|---|---|
| 34 AC 有可执行 Oracle、证据、Pass Gate | 34 个入口、证据 schema/builder/validator 与 fail-closed Pass Gate 已存在 | **BLOCKED**：0/34 PASS；最终 Oracle 34/34 NOT_RUN |
| DAG 无环且 Stage/Phase 子项不超过 5 | 冻结 package validator 通过 | **PASS（静态任务包）** |
| 用户电脑/自建服务器零运行、持久化、缓存 | Workflow 设计为 GitHub-hosted，无 Artifact/Cache | **NOT_RUN（生产）** |
| 只处理双重验证 Moomoo 入站，其他误伤 0 | verifier/discovery/M3 synthetic tests 通过 | **NOT_RUN（protected Gmail）** |
| Raw/Processed 持久化前全部 age 加密 | 加密、远端恢复与 append-only 机制测试通过 | **NOT_RUN（私有数据面）** |
| 一个私有仓；Timeline 稳态恰好一个、任意时刻最多一个 | store/publisher/repair 机制测试通过 | **NOT_RUN（private Release）** |
| 远端恢复后才 exact `users.messages.trash` | double-check、recovery proof、exact-message M3 测试通过 | **NOT_RUN（protected Gmail）** |
| Codex thread 为用户入口；Auto 非关键 | development boundary/passive policy 测试通过 | **NOT_RUN（生产连续性）** |

除静态 DAG 条件外，机制级 PASS 都不能升级为生产 PASS。

## 5. 34 RQ/AC 覆盖审计

下表中的 task IDs 是冻结 traceability 指向的局部实现证据，不等于 AC 的最终 proof。RMD-01 已让每个
指定测试和 evidence 可执行、可验证；但最终 Oracle 均未执行，且关联 task final claim 尚未全 PASS，
所以所有行仍统一为 `BLOCKED`，不能宣称最终验收通过。

| RQ / AC | 需求 | 关联 tasks | 最终状态 |
|---|---|---|---|
| RQ-001 / AC-001 | 对象零误伤边界 | T0304, T0702 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-002 / AC-002 | 全部已验证邮件类型覆盖 | T0401, T0502, T0705 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-003 / AC-003 | 全邮箱位置覆盖 | T0003, T0301, T0607 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-004 / AC-004 | 发件人确定性双重验证 | T0303, T0304, T0702 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-005 / AC-005 | 新发件人安全默认 | T0303, T0304 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-006 / AC-006 | 消息级 M3 | T0002, T0202, T0502, T0703 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-007 / AC-007 | M3 远端恢复 Gate | T0501, T0602, T0702, T0703 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-008 / AC-008 | 单一公开代码位置 | T0001, T0005, T0006, T0101, T0106 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-009 / AC-009 | 单一私有数据仓 | T0001, T0002, T0101, T0203 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-010 / AC-010 | 云端临时执行 | T0102, T0205 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-011 / AC-011 | 全部敏感数据 age 加密 | T0104, T0205, T0307, T0506 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-012 / AC-012 | 恢复钥匙一次性交付 | T0007, T0206, T0707 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-013 / AC-013 | Canonical Raw 完整邮件 | T0103, T0104, T0305, T0601 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-014 / AC-014 | 附件 Magic Bytes 识别 | T0003, T0103, T0306, T0403, T0601 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-015 / AC-015 | Processed 版本化与血缘 | T0105, T0402, T0403, T0404, T0406, T0704 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-016 / AC-016 | 公开面严格脱敏 | T0407, T0601 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-017 / AC-017 | PDF 密码未知不阻塞 Raw/M3 | T0405, T0501 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-018 / AC-018 | 单一 Gmail OAuth 与端点守卫 | T0007, T0201, T0202, T0601, T0604 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-019 / AC-019 | 私有仓短时最小权限 | T0007, T0203, T0204, T0604 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-020 / AC-020 | 不可信内容隔离 | T0103, T0306, T0603 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-021 / AC-021 | 供应链可复现与治理 | T0107, T0207, T0604, T0701, T0708 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-022 / AC-022 | 明文零持久缓存 | T0201, T0205, T0506, T0604, T0607 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-023 / AC-023 | 04:30 悉尼时区运行 | T0002, T0302, T0507, T0705 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-024 / AC-024 | Codex 职责简单稳定 | T0605, T0706 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-025 / AC-025 | Gmail History 与全量补偿 | T0301, T0302, T0507, T0608 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-026 / AC-026 | 端到端幂等 | T0302, T0307, T0502, T0601, T0607, T0703 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-027 / AC-027 | 私有优先跨仓一致性 | T0104, T0204, T0307, T0501, T0602, T0608 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-028 / AC-028 | 单一最新 Timeline | T0002, T0505, T0506, T0602, T0704 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-029 / AC-029 | Timeline 时间语义正确 | T0105, T0402, T0403, T0503, T0504, T0505, T0704 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-030 / AC-030 | 不误报报表缺失 | T0503, T0504, T0704 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-031 / AC-031 | 公开持续证据 | T0003, T0004, T0006, T0104, T0105, T0407, T0607, T0705, T0708 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-032 / AC-032 | 主动恢复与混沌验证 | T0004, T0406, T0608, T0701, T0705, T0707, T0708 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-033 / AC-033 | 双 assurance 流水线 | T0107, T0207, T0605, T0606, T0701 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |
| RQ-034 / AC-034 | 严格范围与非目标 | T0001, T0004, T0102, T0106, T0202, T0404, T0708 | BLOCKED：最终 Oracle 未执行；关联 task final claim 未全 PASS |

## 6. 独立验证结果

| 检查 | 结果 |
|---|---|
| v1.0.4 successor package | PASS；497 个项目内文件；v1.0.3、v1.0.2 与 v1.0.1 Manifest 本体哈希保持不变 |
| 全量 task tests | PASS；246 passed |
| RMD-04 专项与负向测试 | PASS；7 passed；含完整合成 composition、CLI/前序 fail-closed、checkpoint 升级和 v1.0.4 包/状态门 |
| RMD-03 专项与负向测试 | PASS；6 passed；包含 8-command 实际回放 |
| RMD-02 专项与负向测试 | PASS；11 passed |
| RMD-04 production composition validator | PASS；1 次本地合成全链路；真实/受保护/生产/外部写入均为 0 |
| stage-aware task evidence validator | PASS；58/58；正式状态保持 7 completed / 51 planned |
| 唯一 delivery status | PASS；确定性重建一致；生产 `BLOCKED`、未发布 |
| acceptance evidence builder | PASS；34 份 deterministic exact-path records 与汇总均无漂移 |
| acceptance structural validator | PASS；34 valid、0 invalid；默认结构模式不把 BLOCKED 当 PASS |
| acceptance `--require-pass` | EXPECTED BLOCKED；0 PASS、34 BLOCKED、退出码 1 |
| 34 个冻结 acceptance test entry | EXPECTED BLOCKED；34 个均可收集并因显式 blocker 失败 |
| acceptance framework tests | PASS；7 passed |
| Ruff format/check | PASS；RMD-04 Stage 7 闭包 106 个文件格式一致，完整相关 lint 闭包全绿 |
| mypy strict | PASS；包含 RMD-04 production/control 代码在内的 70 source files |
| S1–S6 cumulative validators | PASS；S1/S2 scoped 与 S3–S6 cumulative-final 均退出 0 |
| S7 cumulative preflight | scoped 9/9 PASS；`LOCAL_MECHANISMS_READY`；正式状态仍 BLOCKED |
| S3 / S4 / S5 / S6 cumulative-final CLI | PASS；4/4 退出码 0；零外部效果信号 |
| S3 / S4 / S5 / S6 历史默认 CLI | EXPECTED BLOCKED；4/4 退出码 1；各只有一个 later-stage scope check |
| offline Workflow command matrix | PASS；4 个累计入口 + 4 个历史负向控制；树摘要不变 |
| pinned Governance | PASS；commit `ebc6c2e4884edc959118cfc56d0e18a86c49460f` |
| dependency audit | PASS；hash lock，0 known vulnerabilities |
| reproducible SBOM | PASS；重新生成并 sanitize 后与冻结 S6 SBOM byte-equal |
| publication safety | PASS；505 files，0 findings |
| scoped Stage 7 secret scan | PASS；0 findings；确定性 SHA-256 证据使用显式 digest 字段并由扫描策略识别 |
| GitHub Actions pins / runner / persistence | Action 均为 commit SHA；GitHub-hosted；未发现 Artifact/Cache/self-hosted |

补充安全说明：一次非规范的全项目 `detect-secrets --all-files` 探索扫描产生 5,657 个启发式结果，
其中 5,655 个为 hex high-entropy 类（主要覆盖 SBOM、lock、manifest 与 immutable pin），2 个为
Secret Keyword 类。该结果没有被记为 PASS，也不能单独证明存在凭证；规范 CI 使用受控范围并排除确定性
制品，publication validator 本次为 0 findings。修复后仍需重新运行规范 scoped scan，并对任何新增
结果 fail closed。

## 7. 修复顺序与停止条件

每个后续 run 最多处理一个修复 task group：

1. **RMD-01 最终 AC 执行层（已完成）**：已补齐 34 个测试、schema/validator 与
   synthetic/protected 状态边界；0 个 protected Oracle 被执行，0 个 PASS 被伪造。
2. **RMD-02 契约权威修复（已完成）**：Owner 已授权 v1.0.2 基线保真继任版本；58 份 task evidence
   按真实 stage 验证，唯一跨维度状态已建立，未提升正式或受保护状态。
3. **RMD-03 累计 CI 闭包（已完成）**：S3–S6 显式累计入口与离线 Workflow command matrix 已通过；
   历史默认 scope 语义仍 fail closed，远端 CI 未冒充执行。
4. **RMD-04 生产 composition（已完成）**：唯一生产入口、受保护 adapter/config 组装、加密 Sydney
   水位和 synthetic E2E 已通过；真实生产、受保护 Oracle 和远端 Workflow 未冒充执行。
5. **RMD-05 assurance provenance**：重新完成两个不同模型的独立复审并固化可验证、无敏感数据的来源。
6. **RMD-06 protected 验收与观察**：在明确授权、正确 Secret/私有仓/Gmail 环境中依次执行 Beta、
   M3 Canary、Timeline Blue-Green、GA、Recovery 与最终 AC；任何未知结果停止，不扩大权限。
7. **RMD-07 最终复审与干净上传**：所有 34 AC 和发布门全绿后，从届时最新 `origin/main` 建立干净
   snapshot，重新验证后一次性上传；当前分支永不 push。

任一 run 出现以下情况立即停止：需要改变冻结不变量但没有 Owner 授权；无法证明 exact source message；
远端 recovery 不一致；出现非 Moomoo 完整读取/下载/修改；发现明文持久化、第二数据仓、Timeline 多于
一个、Thread Trash 或永久删除；受保护操作结果未知；任何 AC/Security/Model/Chaos/Recovery Gate
不通过。
