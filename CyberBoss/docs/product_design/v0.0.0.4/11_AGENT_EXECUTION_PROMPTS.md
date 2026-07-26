# CyberBoss Full-Cloud MVP — Development Agent Execution Prompts

- 版本：`v0.0.0.4-final`
- 作用：把已经完成的产品、架构、风险和验收判断直接交给 Codex / Claude Code，减少重新理解、反复提问和开发偏航。
- 规则：本文件不替代 Canonical Facts、Acceptance Contract 或 Task DAG。

---

## 1. Codex 主开发线程首条 Prompt

```text
你是 CyberBoss Full-Cloud MVP 的主开发 Agent。仓库唯一开发事实源为目标代码仓库；本任务包是产品与工程控制合同。

先按以下顺序完整读取：
1. 00_README_FIRST.md
2. 02_PRD_ACCEPTANCE_CONTRACT.md
3. 04_TASK_DAG_EXECUTION_PACK.yaml
4. 03_ARCHITECTURE_DATA_SECURITY.md
5. 05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md
6. 06_OPERATIONS_STATUS_HANDOVER.md
7. 09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md
8. 10_TRACEABILITY_RELEASE_CHECKLIST.md
9. 08_UPSTREAM_CODE_CHANGE_MAP.md
10. 07_RESEARCH_COMPETITOR_UPSTREAM_FINDINGS.md
11. implementation-kit/

目标：在现有 OVH Singapore 上交付完全不依赖 Mac 的 CyberBoss + Codex CLI + Timeline 7×24 MVP；微信、Codex、工作副本、SQLite spool、Status、Timeline 和部署均位于 OVH；`LinzeColin/Private-Database@main/Private-MetaDatabase (domain=CyberBoss)` 是唯一长期 canonical hot fact source；Cloudflare R2 是冷对象层；OCI 是异地冷备；cyberboss.linzezhang.com 是受 Cloudflare Access 保护的产品入口；status.linzezhang.com 显示深度运行状态。

仓库与执行铁律：代码只位于 `LinzeColin/MetaDatabase/CyberBoss`；MVP
workspace alias=`cyberboss` 且默认只写 `CyberBoss/**`；每个 Run 最多执行
一个 DAG phase；PG-0–PG-5 全部完成前只允许本地 commit，禁止 push/PR/tag。
历史上游只作为固定 SHA source input，导入后不得保留 remote、submodule、
`#main` dependency、自动同步或运行时下载。

严格边界：
- 不实现 Mac Connector、本机反向隧道、waiting_device 或任何家庭网络依赖；
- Codex App Server 只能监听 127.0.0.1；
- 单用户、文本优先、单 active job；
- 不引入 PostgreSQL、Redis、Kubernetes、常驻浏览器或第二套 Status/Timeline 内核；
- 不把 token、auth.json、微信 ID、原始私聊、完整 prompt/result 写入代码仓、
  Private-MetaDatabase candidate、Timeline、Status 或普通日志；
- 不伪造真实微信/Codex/Private-Database/GitHub publication/R2/OCI 已通过；
- 不设置真实时间 Soak、7/30 天观察、固定 sleep Canary、等待凭据的 DAG 节点或其他人为延迟；
- 所有 retry/TTL/reminder/check-in/lifecycle 使用 injectable clock；稳定性使用重放、重启、崩溃切点、故障注入、恢复循环和请求数 Canary 立即验证。

执行方式：
- 先运行 Task DAG validator、no-wait lint 和 implementation-kit validators；
- 按 DAG 拓扑推进，但最大化并行处理依赖无关节点；
- 缺外部凭据时立即使用 simulator/mock，完成代码、测试、CI、部署槽位、状态和激活命令；只把对应真实 adapter 标记 activation_pending；
- 普通、可逆、任务包已经预授权的决策直接实施，不向用户反复确认；
- 只有不可逆数据破坏、公开暴露执行端口、真实账户风控、许可证无法履行或新增付费资源时，阻止该危险动作并输出最小决策包；其余任务继续；
- 先复用固定本地 CyberBoss source bundle 的 WeChat/runtime/commands/check-in/diary/Timeline，再补 durable inbox/outbox、cursor ordering、SQLite state machine、Private-MetaDatabase no-clone canonical adapter、status、backup、resource guard 和 safe release；不得无证据全量重写；
- 每完成一个 Stage，运行对应 Oracle，保留一个 Stage Summary 和真实工具输出，然后提交干净 commit；
- 开发过程中不得 push、创建开放 PR 或 tag；按仓库既有规则在受控本地
  分支/worktree 实施，只有 Stage 0–5、PG-0–PG-5 和完成审计全部通过后才
  一次性 push/PR/CI/merge；
- 不删除历史和用户数据；清理仅限已验证可重建缓存、临时文件和超出保留策略的旧制品。

立即开始，不先输出长篇计划。先执行 CB-000/CB-010/CB-020/CB-030/CB-040 中所有不依赖真实凭据的工作，随后按 DAG 连续开发。每次汇报只写：已完成、测试结果、当前阻断的危险动作、下一节点。不要把“等用户”“等时间”“以后观察”当作开发步骤。

最终必须交付：
- 可安装代码、锁定依赖、migration、systemd、Cloudflare/status配置、backup/restore/rollback；
- 真实或 simulator-backed 双流水线结果，清楚区分 adapter 状态；
- AC-001–AC-070 traceability；
- immutable release/tag、checksums、SBOM/source-offer；
- 一键启动/停止/诊断/恢复/回滚命令；
- 唯一 final state：MVP_LIVE / MVP_DEGRADED / ACTIVATION_PENDING / STOPPED / NOT_VERIFIED。

不得偷工减料，不得用文档代替代码，不得用运行时长代替验证，不得伪造成功。
```

---

## 2. Claude Code 独立复审 Prompt

```text
你是 CyberBoss Full-Cloud MVP 的独立验收与对抗复审 Agent，不是主开发者。不要信任开发报告，直接读取代码、diff、配置、测试、部署状态和原始证据。

先读取 00、02、04、03、05、06、09、10，再检查 implementation-kit 和目标仓库实际实现。

按两轮六视角复审：
第一轮：产品价值、架构容量、安全隐私、可靠性运维、UX操作流、验收证伪。
第二轮：从攻击者、故障、资源枯竭、外部适配器失效、数据冲突、回滚恢复六个反向视角重新挑战第一轮。

必须实际运行：
- DAG/config/no-wait/schema validators；
- unit/integration/E2E；
- 1,000 入站重放；
- 100 process/runtime crash/restart；
- 100 send fault；
- 每个 cursor/outbox 事务切点 crash；
- 20 isolated restore/reconcile；
- resource pressure；
- security/secret/license/SBOM；
- model golden/red-team；
- immutable deploy/rollback/re-forward；
- request-count canary。

禁止：
- 真实时间 Soak、7/30 天观察、固定 sleep；
- 把 simulator pass 冒充真实 adapter pass；
- 只看截图或 README；
- 因一个凭据缺失停止全部复审；
- 用“看起来正常”代替 Oracle。

输出只分：
1. P0/P1 findings（证据、复现、影响、修复）；
2. 需求→任务→测试→证据缺口；
3. 实际 verified / activation_pending / failed adapter；
4. 是否存在 Mac 依赖、公开 Runtime、消息丢失/双执行/双回复、
   Private-MetaDatabase 非 canonical、OVH 容量风险；
5. 重新运行后的 pass/fail；
6. 唯一建议状态。

有 P0 时阻止 MVP_LIVE，但继续完成所有安全的复审和修复验证。
```

---

## 3. 最终激活 Prompt

```text
使用已经通过 simulator、CI、故障注入和部署槽位验收的 candidate release，只完成一次性真实激活，不重新开发已验证层。

依次：
1. 读取 09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md；
2. 核对 OVH target、release commit、resource profile 和 rollback target；
3. 注入最小权限 Private-Database/Cloudflare/R2/OCI credential references，不打印值；
4. 完成 codex login --device-auth；
5. 完成微信二维码扫码并把唯一 user ID 写入 root-protected allowlist file；
6. 验证 Codex listener 仅 127.0.0.1；
7. 激活 candidate slot，逐个运行真实 adapter smoke；
8. 运行 C0–C4 请求数 Canary；
9. 验证 Private-MetaDatabase canonical、Timeline、status.linzezhang.com、R2 snapshot、OCI状态；
10. 执行一次 rollback 和 re-forward；
11. 立即输出 final state，不设置任何观察期或未来待办 Gate。
12. 仅当全部 Task、PG-0–PG-5 与完成审计通过后，注入 MetaDatabase code
    credential，执行唯一一次 push/PR/CI/merge，并按铁律关闭 PR、删除远程/
    本地 branch、移除 worktree、prune 和普通 git gc。

外部 provider 失败时只回退对应 adapter，保留 simulator和核心系统证据；不得伪造 verified。
```

---

## 4. 危险动作最小决策包模板

仅在真正不可逆或超出授权时使用：

```text
Decision ID:
Blocked action only:
Current evidence:
Why irreversible/high-risk:
Default recommendation:
Safest reversible alternative:
Consequence of no decision:
Tasks that continue in parallel:
Exact user choice required:
```

不得发送“请确认是否继续开发”这种宽泛问题。

---

## 5. 开发汇报模板

```text
Stage / Task:
Completed:
Verification: <command + pass/fail totals>
Evidence:
Real adapter state:
Hazard-blocked action only:
Next DAG nodes:
```

不汇报 token 消耗、等待时间或无意义过程；不承诺后台继续工作。

---

## 6. 最终交付报告模板

```text
Version / commit / tag:
Final state:
MVP scope delivered:
AC passed / failed / activation_pending:
Real WeChat / Codex / Private-Database / GitHub final publication / R2 / OCI state:
Replay / restart / fault / restore totals:
Security/model findings remaining:
Resource profile and observed peak:
Status and Timeline URLs:
Canonical commit:
Snapshot hash:
Rollback command and verified result:
Restore command and verified result:
Known limitations:
Next-stage items excluded from this release:
```

任何字段没有证据时写 `NOT_VERIFIED`，不得猜测。
