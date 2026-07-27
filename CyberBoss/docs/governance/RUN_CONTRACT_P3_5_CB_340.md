# Run Contract — P3.5 / CB-340

## 1. 目标

在 Owner 锁定产品版本 `v0.0.0.5`、设计基线 `v0.0.0.4`、现有
ResourceReadinessGate 与 CB-330 backup closure 均不变的前提下，完成一个本地
确定性的资源闸门、自愈行动选择、滞回、有限预算与 retention report 薄层。

该层只接受显式 resource snapshot、冻结 `cyberboss.retention.v2` policy、无秘密
inventory、fake clock 与 prior receipt；输出 action plan 或在调用方显式注入
simulator executor 时执行**恰好一个**有界动作。没有 executor 时严格返回
`activation_pending`。它不调用 `systemctl`、不安装/启用 timer、不删除 spool、
不发起 R2/OCI/Private-Database/Cloudflare 请求，也不调用模型。

上游锚点是已关闭的 CB-330 closure
`69012f32ae99ea35960c3dc08db059905a4f29ec`。本 Run 只处理 P3.5 / CB-340；
下一原生节点为 PG-3。

## 2. TaskPack 与 Skill Router

- TaskPack：`v0.0.0.7`；ZIP SHA-256：
  `77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`。
- Task boundary Router 选择 `output-skill`，模式
  `NATIVE_IF_PRESENT_ELSE_EMBEDDED`，最多一个轻量 Skill body。
- 本机有该轻量 Skill，因此只加载一次其正文；若缺失仅允许冻结
  `machine/skill_microplaybooks.json` fallback，网络获取为 `false`；实际 Skill body load 为 `1`，
  不递归加载其它 Skill。
- 不加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究；没有真实
  时间等待。

## 3. 最小范围、状态与激活边界

- 复用 `ResourceReadinessGate` 的既有 resource threshold；新增层只将其输出来
  归一为 `recover` / `warn` / `protect`。previous `protect` 在普通 warning 中保持
  `protect`，只有全部 recover predicates 才解除，避免压力边界抖动。
- allowlist action 仅为 `refresh_status`、`try_restart_single_service`、
  `reclaim_explicit_cache`、`pause_intake`、`trigger_local_backup` 与 `none`。每个
  plan 的 `max_invocations` 为 0 或 1；restart 由显式 receipt 限制为 120 秒
  cooldown、10 分钟窗口最多 3 次，不包含 sleep、poll loop 或无界 retry。
- retention policy 仅消费 TaskPack 已冻结的 `cyberboss.retention.v2` values：7 日
  runtime logs、30 日 diagnostics、保留最新 2 个 `local_verified` backup、
  `current`/`previous` immutable release slots 与 512 MiB build cache cap。它只报告
  backup/log/diagnostic candidate、failed-object isolation 与 explicit cache reclaim；
  自动删除 backup/log/spool 一律为 false，spool 和 private content 保持保护。
- systemd timer 只以 `timer_contract.installed=false`、
  `activation_pending` 的 future contract 出现；没有 macOS `launchd` 依赖。真实
  service/backup/Provider/Private-Database/global Status 操作均为 0。
- 所有 plan/receipt/CLI 输出扫描 private key、Bearer、GitHub/OpenAI/WeChat shaped
  secret 与绝对运行路径。控制面、运维和 self-heal 模型调用计数永久为 0。

## 4. 验收、输出与验证

映射 critical Oracle 为 `FA-AC-010`、`FA-AC-014`、`FA-AC-027`：

1. **FA-AC-010**：每个 plan/receipt/CLI 输出都有 control-plane 与 operations
   LLM counter=`0`；不读取 prompt、不改代码、不调用 Codex/Claude/LLM。
2. **FA-AC-014**：fake resource matrix 将 runtime/poll、memory/disk/inode/load/
   queue、warning/recover 映射为 allowlisted 单一 bounded action；注入 executor
   最多调用一次，missing executor 只能是 `activation_pending`；cooldown 与 budget
   exhaustion 均拒绝 restart。
3. **FA-AC-027**：fake clock 证明滞回与 10 分钟 budget；没有 real-time wait、
   timer installation、retry loop 或无界删除。retention cap 只生成 review/isolation
   candidate，spool 永不删除。
4. 在 credential-name-scrubbed 临时环境运行模块/CLI 测试、syntax、既有 resource
   profile 与 external-adapter fixture、`npm run check`、完整 App regression、identity/
   config、DAG、traceability、no-wait 与 TaskPack validation。

实施输出是 resource profile plan、自愈 action/timer contract 与 retention report；
它们都是 local deterministic facts，不折算任何真实云端激活。

## 5. 允许修改与封口边界

实施阶段仅允许：

- `CyberBoss/app/src/services/operations/canonical-operations-policy.js`
- `CyberBoss/app/scripts/canonical-operations-plan.js`
- `CyberBoss/app/test/canonical-operations-policy.test.js`
- `CyberBoss/tests/canonical-operations-plan.test.js`
- 本 Run Contract 与 `CyberBoss/scripts/validate_cb340.py`

封口阶段仅允许 `CHANGELOG.md`、`README.md`、`HANDOFF.md`、
`machine/facts/task_state.json` 与
`docs/evidence/CB-340/{summary,subject}.json`。不变更产品、设计或 TaskPack
版本，不新建仓库、子模块或平行事实源。

## 6. 风险、回滚与停止条件

- 未来真实 timer/service action 需要 Owner 授权、明确 allowlisted service、真实
  target receipt 与独立 activation task；本 Run 不安装 timer、不改 unit、不执行
  restart。回滚为禁用未来 timer、恢复 prior policy，且不删除 spool 或最后好快照。
- 出现 self-heal 调用 Agent/LLM、非 allowlist action、单次超过一个动作、无界 retry/
  删除、危害其它服务、secret/PII、真实 Provider mutation、Private-Database clone、
  macOS `launchd` 或任何非零模型计数，即停止并拒绝封口。
