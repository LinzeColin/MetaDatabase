# Run Contract — PG-2 Stage 2 Exit Gate

## 1. Goal

独立关闭 Stage 2 exit gate `PG-2`：

> Durable inbox/outbox, cursor ordering, idempotency, singleton and crash-cut
> recovery pass count-based deterministic tests.

本 Run 只聚合 `CB-200`、`CB-210`、`CB-220`、`CB-230` 与 `CB-240` 的冻结
Stage 2 Subject、机器证据和当前可复跑回归。只有 `FA-AC-007`、`FA-AC-027` 与
`FA-AC-029` 都在同一精确 Subject 上通过，才把 `PG-2` 标为 `passed`。

产品版本固定为 `v0.0.0.5`，设计基线固定为 `v0.0.0.4`，TaskPack 固定为
`v0.0.0.7`（zip SHA-256：
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`）。

## 2. Router and execution boundary

在本 Run 起点已运行本包 Skill Router：`task_id=PG-2`、
`mode=DETERMINISTIC_TEST_ONLY`、`selected_skill=null`、
`max_skill_body_loads=0`。因此本 Gate **不加载任何 Skill**，不调用
Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究。

本 Run 最多关闭一个原生 phase；完成后下一边界只能是 `P3.1 / CB-300`，不得
顺带开始 Timeline、Status、Cloudflare Access、R2/OCI、确定性自愈或真实激活。

## 3. Frozen inputs and required checks

- `CB-240` closure commit `91e9c267a775b138e27b196f0cc96de552ba958b` 及其
  Stage 2 evidence trees；
- `machine/facts/task_state.json`，其五个 Stage 2 tasks 都必须为 `passed`；
- `docs/evidence/CB-200/**` 至 `docs/evidence/CB-240/**` 的 implementation
  commit、tree、结构化 crash/replay/resource/outbox/canonical evidence；
- `docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md`、
  `04_TASK_DAG_EXECUTION_PACK.yaml`、`implementation-kit/**`；
- 当前 App 与 root 的 Stage 2 focused regression、完整 App regression、
  DAG、traceability、no-wait、config、identity scope 与 TaskPack checks。

普通 canonical facts 的远端 dispatch 仍是 `03:20 UTC` 日频；
`release_completed`、`incident_declared`、`recovery_completed` 仍是唯一
material event 集合。PG-2 不重新解释或改变这些 CB-240 已封口的事实。

## 4. Non-goals and invariants

- 不修改 `CyberBoss/app/**`、`vendor/**`、产品设计基线、TaskPack 或任何既有
  CB evidence；
- 不创建仓库、平行事实源、submodule、Git URL dependency、克隆
  Private-Database 或长期运行平面；
- 不依赖 Mac/macOS `launchd`、Keychain、本机 Runner、隧道或本机 Codex；
- 不执行真实 Private-Database、R2、OCI、Cloudflare、WeChat、Codex、OVH 或
  GitHub 操作，不读取、打印或持久化 credential/secret value；
- 控制面与运维模型调用永久为 `0`；不使用 sleep、Soak、观察期、凭据等待、
  无限重试或真实时间等待；
- 真实外部 adapter/部署仍为 `activation_pending`（R2 维持
  `hazard_blocked` 直至精确 write-scope attestation），不得伪绿；
- 不 push，不创建 PR、tag、release 或新的产品版本。

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_PG_2.md`
- `CyberBoss/scripts/validate_pg2.py`
- `CyberBoss/docs/evidence/PG-2/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

除以上路径外不得修改。失败时只保留最小复验闭包，回滚只可 `git revert` 本地
PG-2 closure commit；本 Gate 不产生外部对象。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_pg2.py --prepare
python3 CyberBoss/scripts/validate_pg2.py
git diff --check
```

验证器必须在去除 credential 名称环境变量的临时测试目录中实际运行：

1. Stage 2 App focused suites（WAL/state、durable inbox/cursor、scheduler/
   workspace/resource、outbox/recovery、canonical sync）；
2. Stage 2 root contract suites；
3. App check 与完整 App regression；
4. identity scope、placeholder config、DAG、traceability、no-wait 与
   TaskPack checks；
5. clean-state replay 不得触发网络、真实 provider、真实数据操作或等待。

## 7. Stop conditions and acceptance

立即停止并保持 `PG-2` 非 passed 的条件：任一 Stage 2 task 不是 `passed`；
任一 P0 durable/inbox/cursor/lease/outbox/canonical Oracle 为 UNKNOWN、NOT_RUN
或失败；Stage 2 历史 evidence 被改写；重放可重复执行、消息丢失、same
ID/different hash 覆盖、非单例 Runtime lease、未知发送被确认、secret/完整私聊
泄漏，或任何检查需要真实外部凭据/写入才能通过。

`PG-2=passed` 只表示上述本地确定性 Gate 已闭合。它不等于真实云端激活，也不
等于 `FORMAL_FINAL_ACCEPTANCE`。closure evidence 必须包含不可变 source/tree、
Stage 2 evidence aggregate digest、两个 manifest digest、`activation_pending`
deployment pointer 与 0 次真实操作/模型调用的 Subject。
