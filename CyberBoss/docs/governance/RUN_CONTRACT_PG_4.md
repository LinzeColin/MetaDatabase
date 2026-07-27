# Run Contract — PG-4 Stage 4 双流水线与 Safe Release Gate

## 1. 目标与范围

本 Run 独立关闭 Stage 4 exit gate PG-4，只聚合已关闭的 CB-400、CB-410、CB-420、
CB-430 与 CB-440 的精确 Subject、evidence tree、implementation tree 和当前可复跑
本地回归。它映射 FA-AC-015、FA-AC-016、FA-AC-017、FA-AC-018、FA-AC-019 与
FA-AC-029；只有所有 critical Oracle 都有精确 Subject 绑定的证据，且没有未接受的
P0/P1，才可标记 PG-4 为 passed。

产品版本固定为 v0.0.0.5，设计基线固定为 v0.0.0.4，TaskPack 固定为 v0.0.0.7，
ZIP SHA-256 固定为
77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a。

本 Gate 的冻结锚点是 CB-440 closure
5ac84f31e6889dc416cad405011dda572a463d38（tree
70913b5a040bed7929e01de9d3492b0b7187dce9）。它不是产品 promotion，也不改变
candidate/current/previous 的本地 fixture 语义。

## 2. Router 与永久边界

本包 Skill Router 已在本任务边界返回 PG-4 的
DETERMINISTIC_TEST_ONLY 结果：selected_skill=null、max_skill_body_loads=0、
network_fetch=false。故本 Gate 不加载任何 Skill，也不调用 Verifier、Teleiosis、
Persona、SubAgent、第二模型或动态研究。

本 Run 最多关闭一个原生节点。完成后下一边界只能是 P5.1 / CB-500，且 CB-500
必须重新运行它自己的 Router。不得顺带执行 dress rehearsal、真实全云激活、Canary、
rollback、Private-Database 日频/重大事件同步、R2/OCI 备份、Cloudflare Access/DNS、
Status 发布、服务操作或 GitHub 操作。

控制面与运维模型调用永久为 0。禁止 macOS launchd、真实时间等待、sleep、soak、
凭据等待、无限重试、Private-Database clone、新仓库、submodule、远端制品或平行事实源。
不得读取、输出或持久化 credential、token、cookie、完整私聊、原始 prompt 或模型响应。
所有真实外部状态保持原样：R2 为 hazard_blocked，其余未授权 provider/data/service
activation 均为 activation_pending。

## 3. 双流水线复核

PG-4 的 deterministic aggregate 必须同时确认：

1. 软件正确性流水线：CB-400 的十个 frozen core slices、predeploy receipt、migration
   compatibility 与 rollback discrimination 都为 passed，deployment mutations 为 0；
2. 模型安全流水线：CB-410 的六个 redacted fixture 仅验证 artifact/test oracle，
   secret exfiltration、未授权不可逆动作、false-success release 和 real model calls
   均为 0；真实 Codex trial 与 budget/latency 仍为 activation_pending；
3. 安全、隐私、供应链：CB-420 的 secret/P0/P1/unresolved license 均为 0，Access/
   analytics privacy contract 继续 fail closed，真实 Analytics/source distribution 保持
   activation_pending；
4. 故障与恢复：CB-430 的 lost messages、duplicate execution、duplicate side effects
   与 unbounded retries 均为 0，rollback/restore contract 有效；
5. Safe release seal：CB-440 的 immutable candidate、operator contract、8 条
   request-count predicate 与 P0 immediate pointer restore 都可本地复验。candidate
   installation、current switch、live request-count Canary 与 live rollback 仍是
   activation_pending，不能记为真实通过。

允许的 implementation 路径严格为：

~~~
CyberBoss/docs/governance/RUN_CONTRACT_PG_4.md
CyberBoss/docs/governance/STAGE4_SAFE_RELEASE_GATE_PG4.md
CyberBoss/scripts/validate_pg4.py
~~~

封口阶段仅允许修改 CyberBoss/CHANGELOG.md、CyberBoss/README.md、
CyberBoss/HANDOFF.md、CyberBoss/machine/facts/task_state.json 与
CyberBoss/docs/evidence/PG-4/{summary,subject}.json。

## 4. 验证、停止条件与回滚

验证器在 credential-scrubbed 临时环境重跑五条 Stage 4 focused App/root suites、各
deterministic CLI、Cloud/runtime/access 安全边界、secret scan、App check/full regression、
identity/config/DAG/traceability/no-wait/TaskPack 与两个冻结 manifest。它还验证
CB-400 至 CB-440 evidence 没有在冻结锚点后被改写，逐一复核 Subject SHA-256、
implementation tree、acceptance、零操作/零模型计数、external truth-state，并计算
Stage 4 evidence digest。

立即停止并保持 PG-4 非 passed 的条件是：任一 P0/P1 未接受；任一 Subject/evidence/
implementation tree 漂移；软件或模型流水线出现 UNKNOWN、NOT_RUN 或失败；secret、
privacy、license、Access/origin bypass、fault/restore、candidate immutability、Canary
predicate 或 rollback contract 异常；或者任何 pending 外部项目被伪绿。

PG-4=passed 只表示本地 deterministic safe-release gate 已闭合，明确不等于
FORMAL_FINAL_ACCEPTANCE、真实全云激活或生产 deployment。失败时只返回最小整改闭包；
不修改产品或真实 current，回滚仅保留现有 accepted baseline 与 activation_pending
truth-state。
