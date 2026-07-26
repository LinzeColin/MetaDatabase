# CyberBoss 产品 Stage 2B、Stage 3 与后续升级路线 v0.0.0.4

- 日期：2026-07-26
- 前置条件：当前 `Stage 1 + Stage 2A` 已按 Acceptance Contract 完成；本文件不得污染或阻塞当前 MVP。
- 验收原则：全部按能力、请求数、故障次数和恢复结果推进，不以 7 天/30 天或任何真实时间 Soak 为 Gate。

---

## Stage 2B — 单用户功能深化

### 2B.1 附件与文件工作流

- 微信图片、PDF、Word、Excel、ZIP 的受控接收；
- R2 临时对象、hash、MIME sniffing、大小/类型限制；
- malware scan 和 decompression bomb 防护；
- Codex workspace 临时挂载；
- TTL 使用虚拟时钟测试；
- 原始附件不进入代码仓；Private-MetaDatabase 仅存 hash、metadata 和 pointer。

Gate：每类 fixture、恶意文件、断点、重复上传和清理边界全部通过。

### 2B.2 审批持久化与中断恢复

- `/yes`、`/no`、`/always` durable approval state；
- Runtime/bridge restart 后恢复 waiting approval；
- approval request 与 job/correlation ID 一一对应；
- `/always` 限定 workspace + action class + expiry；
- 高风险动作始终不能被宽泛自动批准。

Gate：所有事务切点 crash 后无错批、漏批、重复执行。

### 2B.3 多 Workspace，仍单并发

- alias registry；
- sparse checkout/worktree；
- workspace quota；
- symlink/path traversal guard；
- 每 workspace 独立 thread/session/approval policy；
- 每个 workspace 的代码以其 canonical code repo 为准；长期运行事实唯一写入
  Private-MetaDatabase，OVH 工作副本可重建。

Gate：跨 workspace 写入、路径逃逸和状态串线均为 0。

### 2B.4 Timeline 2.0

- 任务、日记、check-in、release、incident、restore 统一视图；
- 日期、category、workspace、job、release 搜索；
- canonical rebuild；
- hash/pointer drill-down；
- 手机优先、结论优先、异常优先；
- 静态历史可分流到 Cloudflare，实时状态仍来自 OVH。

Gate：canonical → Timeline 重建 hash 一致，搜索 fixture recall=100%。

### 2B.5 操作体验

- 微信 `/jobs`、`/job <id>`、`/retry <id>`、`/timeline`；
- Dashboard 首页直接显示：当前结论、active job、queue、last failure、canonical lag、backup state；
- 用户不需要理解 SQLite、systemd、Git 或 Runtime 术语；
- 所有错误给出下一步动作，不输出机器堆栈。

Gate：Golden/Black/Degraded/Recovery flow 全部可完成且无死路。

---

## Stage 3 — 生产强化

### 3.1 数据与恢复强化

- Private-MetaDatabase canonical object/index/manifest；
- 并发 ingest 的 content-addressed conflict-safe append；
- R2 lifecycle、bucket lock 或等价不可变策略；
- OCI selected replication；
- encrypted secret-state backup 与独立恢复授权；
- disaster restore 到新 OVH host 的一键脚本。

Gate：空主机隔离恢复、故意损坏、对象缺失、Private-Database 409/429
冲突与重试矩阵全部通过。

### 3.2 Runtime 抽象与 Claude Code fallback

- Codex 继续为主 Runtime；
- Claude Code adapter 默认关闭；
- 使用同一 job/event/approval/outbox contract；
- 同一 golden/red-team/eval 达标后才能启用；
- 不在一次 job 内同时让两个 Runtime 修改同一 workspace。

Gate：等价任务结果、错误分类、取消、审批和资源预算全部达到基线。

### 3.3 Channel fallback

仅当微信 iLink 发生持续不可用、账户不兼容或风控不可接受时启用：

- 受 Cloudflare Access 保护的 Web Inbox 优先；
- 其次才评估 Telegram/其他正式 Channel；
- 核心 durable inbox/job/outbox 不重写；
- Channel adapter contract 保持一致。

Kill Criteria：fallback 开发成本高于微信失效造成的预期损失时不做。

### 3.4 容量扩展

按测量触发，而不是提前堆服务：

1. 优化 log、worktree、cache、canonical batching；
2. 静态 Timeline 和大对象分流 R2/Cloudflare；
3. OVH 存储扩容或附加卷；
4. 只有 SQLite 单写瓶颈被真实压测证明后才评估 PostgreSQL；
5. 不因“未来可能”引入 Redis/Kubernetes。

Kill Criteria：P95 queue、disk growth、restore time 和 Private-Database ingest
throughput 未达到触发阈值时不升级。

### 3.5 安全与合规

- AGPL 对应源代码交付流程；
- SBOM/VEX、依赖补丁策略；
- secret rotation；
- abuse-rate limits；
- incident response；
- privacy export/delete policy；
- model System Card 版本化；
- Alpha/Beta/GA 只按风险与证据 Gate。

---

## Stage 4+ — 条件式能力

仅在需求和收益被真实使用数据证明后讨论：

- 多用户/RBAC/租户隔离；
- 多 OVH worker；
- 多 Runtime 调度；
- MCP registry；
- 自动项目发现与一键开发；
- 语音/视频；
- 企业审计和 SLA；
- 商业化计费。

这些能力默认不开发。每一项必须先有：用户、频次、收益区间、成本区间、失败代价、证伪实验和 Kill Criteria。

---

## 升级优先级

| 优先级 | 能力 | 进入条件 | 不进入条件 |
|---|---|---|---|
| P0 | 审批恢复、附件安全、多Workspace | 当前MVP真实使用中形成明确阻塞 | 仅“可能以后需要” |
| P1 | Timeline 2.0、灾难恢复、容量优化 | 查询/恢复/磁盘指标触发 | 现有方案仍有余量 |
| P2 | Claude Code fallback、Channel fallback | 主Runtime/微信存在被证实的不可接受风险 | 只是追求技术多样性 |
| P3 | PostgreSQL/多节点/多用户 | 单机与SQLite经压测证伪 | 预防性过度架构 |
| P4 | 商业化平台 | 有真实第二用户/客户与付费意愿 | 个人自用阶段 |

---

## 无等待升级 Gate

每次升级均立即执行以下验证，不设置观察期：

```text
requirements review
→ isolated implementation
→ unit/integration/E2E
→ replay/restart/fault/restore matrix
→ security/model review
→ request-count canary
→ rollback/re-forward
→ current-state decision
```

上线后的真实指标用于下一轮优先级判断，但不是“必须等满多少天才能完成”的条件。
