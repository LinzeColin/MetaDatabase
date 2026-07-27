# Run Contract — P3.2 / CB-310 Atomic redacted Status

## 1. Goal

关闭原生任务 `CB-310`：从既有 runtime/canonical 事实构建原子、脱敏、可验证的
`cyberboss.status.v2` snapshot，并生成可由既有 `status.linzezhang.com` 项目行
契约消费的兼容 row。它不是新 Status 产品、数据库、HTTP 服务或第二事实源。

产品版本固定为 `v0.0.0.5`，设计基线固定为 `v0.0.0.4`，TaskPack 固定为
`v0.0.0.7`（zip SHA-256：
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`）。
前置 CB-300 已在 closure commit
`e8243ea81b5ecf239a8ec2df44189259c661adfa` 精确关闭。

## 2. Router and execution boundary

在本 Run 起点已经运行本包 Skill Router：`task_id=CB-310`、
`selected_skill=webapp-testing`、`mode=NATIVE_IF_PRESENT_ELSE_EMBEDDED`、
`max_skill_body_loads=1`。当前环境不存在该 Skill，因此按 TaskPack 冻结 fallback
只使用 `machine/skill_microplaybooks.json` 的 existing HTTP/DOM/unit fixture；
实际 Skill body load 为 `0`，不安装、不替换、不联网寻找其它 Skill。

不调用 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究。本 Run 最多
关闭一个 phase；完成后下一边界只能是 `P3.3 / CB-320`。

## 3. Implementation contract

- snapshot schema 固定为 `cyberboss.status.v2`；只允许 schema、generation、
  source commit、overall、固定 component 集、固定 metrics、固定 adapter 集和
  release 集，未知字段或不合法类型 fail closed；
- 组件至少覆盖 process、poll、send、Runtime、E2E、queue、canonical、Timeline、
  R2、OCI、resources、self-heal；overall 按 failed/degraded/unknown/
  activation_pending/healthy 确定性聚合，`unknown`、`activation_pending` 和
  `disabled` 绝不成为 healthy；
- `generated_at` 必须由调用方显式注入；generation ID 使用时间前缀和内容 hash，
  写入时严格递增。没有 timer、sleep、真实时间等待或观察期；
- snapshot 和 row 都经 temp file、fsync、atomic rename、directory fsync 写出；
  before-rename 保留上一有效 JSON，after-rename 故障仍只能留下完整 JSON；
- 禁止 prompt、result、微信/线程/账户 ID、token、credential、绝对路径和私人文件名。
  reason code 仅稳定 allowlist 形式；控制面 LLM 与 self-heal agent counters 必须恒为
  `0`；
- 直接复用锁定的现有 `global-status-adapter.js` 的 `buildRow`，只喂入由 v2
  snapshot 投影出的安全兼容输入；不调用其远程 fetch path，不写线上 Status，项目行
  generation ID 必须等于 source snapshot，`agent` 和 `notify` 固定为中文“无”。

映射 acceptance：

- `FA-AC-009`：原子、脱敏、组件化 snapshot，未知状态不假绿；
- `FA-AC-010`：所有控制面与运维模型/agent 计数为零；
- `FA-AC-028`：snapshot、row、CLI 输出与 evidence 无 secret/隐私；
- `FA-AC-031`：新增用户可见项目字段使用中文，既有项目名/URL 只保留兼容契约。

## 4. Non-goals and invariants

- 不修改产品版本、设计基线、TaskPack、锁定 existing Status collector、Timeline
  source、既有 CB/PG evidence；不创建仓库、submodule、Git URL dependency、Status
  服务、数据库或平行事实源；
- 不启动 HTTP/static 服务、systemd timer、Cloudflare Access、隧道、浏览器或真实
  collector；不执行真实 Private-Database、R2、OCI、Cloudflare、WeChat、Codex、OVH
  或 GitHub 操作，不读取、打印或持久化 credential value；
- 不依赖 Mac/macOS `launchd`、Keychain、本机 Runner 或常驻浏览器；
- 控制面与运维模型调用永久为 `0`；不使用 sleep、Soak、无限重试、凭据等待或其它
  真实时间等待；
- Private-Database、R2、OCI、Cloudflare Access、Timeline 静态发布与 global Status
  在线写入仍为 `activation_pending`（R2 继续 `hazard_blocked`），不得伪绿；不
  push、PR、tag 或 release。

## 5. Allowed modifications and rollback

实现提交只允许变更：

- `CyberBoss/app/src/services/status/canonical-status-export.js`
- `CyberBoss/app/scripts/canonical-status-export.js`
- `CyberBoss/app/test/canonical-status-export.test.js`
- `CyberBoss/tests/canonical-status.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P3_2_CB_310.md`
- `CyberBoss/scripts/validate_cb310.py`

closure 提交仅允许变更 `README.md`、`HANDOFF.md`、`CHANGELOG.md`、
`machine/facts/task_state.json` 和 `docs/evidence/CB-310/{summary,subject}.json`。
回滚为禁用新 exporter/adapter 并保留上一有效 snapshot/row；必要时只可 `git revert`
本地 CB-310 closure commit。部分 JSON、generation 回退、UNKNOWN 假绿、任何敏感
字段、第二 Status 平台、非零模型/agent 计数或外部写入都立即停止。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_cb310.py --prepare
python3 CyberBoss/scripts/validate_cb310.py
git diff --check
```

验证器在移除 credential 名称环境变量的临时目录中实际运行：snapshot/row unit
fixture、component fault matrix、atomic crash cuts、DLP/schema/zero-agent、root
CLI fixture、Node syntax、完整 App check/regression，以及 identity/config/DAG/
traceability/no-wait/TaskPack checks。浏览器能力降级只可使用已有 fixture，不得
安装依赖或建立常驻服务。
