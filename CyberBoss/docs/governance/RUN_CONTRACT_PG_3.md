# Run Contract — PG-3 Stage 3 Exit Gate

## 1. 目标

独立关闭 Stage 3 exit gate `PG-3`：

> Canonical adapter, Timeline, status, resource guard and R2/OCI adapters pass
> with explicit activation truth.

本 Run 只聚合 `CB-300`、`CB-310`、`CB-320`、`CB-330` 与 `CB-340` 已关闭的
Subject、evidence tree、implementation tree 和当前可复跑回归。只有
`FA-AC-008`、`FA-AC-009`、`FA-AC-010`、`FA-AC-011`、`FA-AC-012`、
`FA-AC-013`、`FA-AC-014`、`FA-AC-029`、`FA-AC-032` 全部在同一精确 Stage 3
Subject 上通过，才将 `PG-3` 标为 `passed`。

产品版本固定为 `v0.0.0.5`，设计基线固定为 `v0.0.0.4`，TaskPack 固定为
`v0.0.0.7`（ZIP SHA-256：
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`）。

## 2. Router 与执行边界

在本 Run 起点已运行本包 Skill Router：`task_id=PG-3`、
`mode=DETERMINISTIC_TEST_ONLY`、`selected_skill=null`、
`max_skill_body_loads=0`。因此本 Gate **不加载任何 Skill**，不调用 Verifier、
Teleiosis、Persona、SubAgent、第二模型或动态研究。

本 Run 最多关闭一个原生 phase；完成后下一边界只能是 `P4.1 / CB-400`。不得
顺带开始 software pipeline、模型试验、供应链、真实激活、Canary 或回滚部署。

## 3. 冻结输入与必做检查

- CB-340 closure `c132ee648ab2ad0f5f66c0dc3ee923c11cabfa42` 及其包含的
  Stage 3 evidence trees；
- 五个任务的 implementation commit/tree：CB-300、CB-310、CB-320、CB-330、
  CB-340；任一历史 evidence 变更即 fail closed；
- `machine/facts/task_state.json` 中五个 Stage 3 task 都必须为 `passed`，
  `PG-3` 在封口前必须为 `not_started`；
- 当前 Timeline、Status、Access、backup/restore 和 operations resource
  focused suites，以及它们 root CLI contract suites；完整 App regression；
  frozen Access/resource/external-adapter fixtures、identity scope、config、DAG、
  traceability、no-wait、TaskPack 和两个 manifest；
- adapter truth-state review：Private-Database、R2、Cloudflare Access/DNS/
  Analytics、OCI、Timeline/Status publication、self-heal/timer 真实状态仍是
  `activation_pending` 或 `hazard_blocked`；所有 real operation 与 LLM counter
  都是 `0`；local simulator/plan 不能被称为真实 activation。

## 4. 非目标与永久不变量

- 不修改 `CyberBoss/app/**`、任何已关闭 CB evidence、设计基线或 TaskPack；
- 不创建仓库、平行事实源、submodule、Git URL dependency、Private-Database clone
  或长期运行平面；
- 不依赖 Mac/macOS `launchd`，不安装/启用 systemd unit/timer，不执行 sleep、Soak、
  观察期、凭据等待、无限重试或真实时间等待；
- 不执行真实 Private-Database、R2、OCI、Cloudflare、WeChat、Codex、OVH、
  service restart、backup delete 或 GitHub 操作；不读取、打印或持久化 credential/
  secret value；
- 控制面和运维模型调用永久为 `0`；不 push、不创建 PR/tag/release，也不变更产品版本；
- rollback drill 只复核 CB-300 last-good、CB-310 atomic snapshot、CB-320 deny,
  CB-330 isolated restore 和 CB-340 zero-action/retention contracts，不对真实系统
  执行回滚。

## 5. 允许修改

实施阶段仅允许：

- `CyberBoss/docs/governance/RUN_CONTRACT_PG_3.md`
- `CyberBoss/scripts/validate_pg3.py`

封口阶段仅允许 `CHANGELOG.md`、`README.md`、`HANDOFF.md`、
`machine/facts/task_state.json` 与 `docs/evidence/PG-3/{summary,subject}.json`。
失败时只保留最小复验闭包；本 Gate 不产生外部对象。

## 6. 验收与停止条件

验证器必须在去除 credential 名称环境变量的临时测试目录实际运行：

1. Stage 3 App focused suites（Timeline、Status、Access、online backup、
   operations policy）和五个 root CLI contract suites；
2. frozen Access policy、resource profile、external adapter fixture；
3. App check 与完整 App regression；
4. identity scope、placeholder config、DAG、traceability、no-wait 与 TaskPack；
5. Stage 3 aggregate digest、immutable commit/tree/evidence topology、truth-state
   review 与 rollback-contract review。

立即停止并保持 `PG-3` 非 passed 的条件：任一核心安全/数据/恢复项为 UNKNOWN、
NOT_RUN 或失败；任一 Stage 3 evidence 被改写；Timeline 写回 canonical、Status
伪绿、Access/origin bypass、remote 未验证标绿、self-heal 调用 Agent/LLM、无界
action/delete/retry、secret/完整私聊泄漏，或任何检查需要真实外部凭据/写入才能通过。

`PG-3=passed` 只表示本地确定性 Gate 已闭合，不等于真实全云激活或
`FORMAL_FINAL_ACCEPTANCE`。closure evidence 必须包含 Stage 3 aggregate digest、
两个 manifest digest、`activation_pending` deployment pointer 和 0 次真实
operation/模型调用的 Subject。
