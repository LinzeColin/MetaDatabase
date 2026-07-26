# CyberBoss Full-Cloud MVP Roadmap v0.0.0.4

- 日期：2026-07-26
- 当前交付范围：**产品 Stage 1 + 产品 Stage 2A**
- 目标：在单次 24 小时实施窗口内上线真正不依赖 Mac 的全云 MVP；7×24 是架构与恢复能力，不以真实时间 Soak 证明。
- 唯一实施合同：仓库内
  `CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`

---

## 1. 产品阶段边界

### 当前：Stage 1 — 全云 Walking Skeleton

```text
微信
→ OVH CyberBoss
→ OVH Codex CLI / App Server（loopback）
→ OVH 受控项目工作副本
→ 微信回复
```

必须同时具备：

- `cyberboss.linzezhang.com` 受 Cloudflare Access 保护；
- `status.linzezhang.com` 显示 CyberBoss 深度状态；
- Timeline 可写、可查、可从 canonical facts 重建；
- systemd 常驻、自启、单实例和非 LLM 自愈；
- Mac、家庭网络、本地 Connector 依赖为 0。

### 当前：Stage 2A — MVP 最低可靠性底座

- durable inbox → 再提交微信 cursor；
- job state machine、singleton lease、单 active job；
- durable outbox、幂等发送、真实失败状态；
- SQLite WAL 仅作可重建运行 spool；
- `LinzeColin/Private-Database@main/Private-MetaDatabase (domain=CyberBoss)` 为唯一长期 canonical hot fact source；
- R2 冷快照，OCI 异地冷备或明确 `activation_pending`；
- immutable release、request-count canary、rollback、restore；
- 软件正确性流水线 + 模型能力安全流水线；
- 所有重试、TTL、提醒、check-in 和生命周期可注入虚拟时钟；
- 不存在任何真实时间 Soak、观察期或等待凭据开发节点。

### 不属于当前任务包

- 产品 Stage 2B：附件、审批持久恢复、多 Workspace、Timeline 深化；
- 产品 Stage 3：生产强化、多 Runtime/Channel、容量扩展、商业化。

以上只在独立升级路线中，不得阻塞当前 MVP。

---

## 2. 机器执行图

当前任务包内部使用 6 个执行 Stage、30 个无环节点；每个 Stage 最多 5 个 Task：

| 内部 Stage | 目的 | DAG Nodes | Exit Gate |
|---|---|---|---|
| S0 | 上游基线、OVH测量、模拟器、威胁模型、预授权 | CB-000–CB-040 | PG-0 |
| S1 | 全云 Walking Skeleton | CB-100–CB-140 | PG-1 |
| S2 | durable messaging 与 canonical facts | CB-200–CB-240 | PG-2 |
| S3 | Timeline、Status、备份、资源治理 | CB-300–CB-340 | PG-3 |
| S4 | 软件/模型/安全双流水线与安全发布 | CB-400–CB-440 | PG-4 |
| S5 | 真实激活、请求数 Canary、回滚恢复、交接 | CB-500–CB-540 | PG-5 |

完整输入、输出、依赖、Oracle、证据、风险、回滚和 Stop Condition 以 `04_TASK_DAG_EXECUTION_PACK.yaml` 为准。

---

## 3. 并行实施路径

不按“等待多少小时”串行推进；按依赖和可逆性并行推进。

### Lane A — 上游与核心代码

1. pin CyberBoss/timeline-for-agent exact SHA，并形成固定本地 source bundle；
2. 复用现有 WeChat、Runtime、commands、diary、check-in、Timeline，但不保留
   upstream remote、`#main` 依赖或自动同步；
3. 修复 cursor 先提交的问题；
4. 增加 durable inbox/job/outbox/sync spool；
5. 增加 single-instance、workspace alias 和 loopback guard。

### Lane B — 云端 Runtime 与 Workspace

1. 建立 OVH `cyberboss` service user；
2. 安装 Node 22、Codex CLI 和 pinned dependencies；
3. 准备单一受控工作副本；
4. 先运行 Codex simulator，再集中执行一次 `codex login --device-auth`；
5. 验证 App Server 只有 `127.0.0.1:8765`。

### Lane C — Canonical Data / Timeline

1. fake Private-Database API 完成 ingest/idempotency/409/429/reconcile；
2. terminal event 按条数/大小阈值及终态立即 flush；
3. 私有库凭据启用后通过 `private_db_client.py` 补跑真实 ingest/list/verify；
4. 使用固定本地 timeline-for-agent source bundle 构建和轻量搜索；
5. 完成 canonical → Timeline 重建。

### Lane D — Status / UI / Cloudflare

1. 生成脱敏 `/status/snapshot.json`；
2. 本地文件适配现有 Status collector，避免公开反向抓取依赖；
3. 增加 `status.linzezhang.com` CyberBoss 一级条目；
4. `cyberboss.linzezhang.com` 配置 Access Google/GitHub IdP；
5. 启用只收 page view/unique visitor 的 Web Analytics。

### Lane E — Backup / Release / Resource

1. live preflight 选择 constrained/tiny/standard profile；
2. SQLite online backup + SHA-256；
3. 无 R2 凭据时先完成 local immutable/object-store simulator，不阻塞部署；
4. immutable releases + current/previous symlink；
5. predicate readiness、request-count canary、rollback/re-forward。

### Lane F — Assurance

1. DAG/config/no-wait/schema lint；
2. 1,000 message replay；
3. 100 restart/runtime crash；
4. 100 send fault；
5. 20 restore/reconcile；
6. SAST、secret、SBOM、license、workspace escape；
7. model golden/red-team/System Card；
8. 两轮六视角独立复审。

---

## 4. 一次性人工动作

这些动作集中到最终激活，不得让开发线程等待：

1. OVH SSH/sudo；
2. 微信二维码扫码；
3. `codex login --device-auth`；
4. GitHub 最终代码发布凭据与 Private-Database no-clone 客户端凭据分别注入；
5. Cloudflare DNS/Access/R2 最小权限 credential reference；
6. OCI prefix-scoped credential，或保留 `activation_pending:oci`。

缺少任何一项时：对应真实 adapter 标记 `activation_pending`，其余代码、模拟器、测试、部署槽位、文档和回滚继续完成。

---

## 5. 发布 Gate

### PG-0 — 可开发

- exact source、license、模块地图已核对；
- live resource collector、simulators、activation sheet 可运行；
- 无凭据也能开始所有非激活工作；
- DAG/no-wait validator 通过。

### PG-1 — Walking Skeleton

- simulator WeChat → durable inbox → simulator Codex → durable outbox → simulator WeChat 通过；
- real adapter 激活后只补跑真实 E2E；
- 无 Mac 路径/进程/网络依赖；
- Codex listener non-loopback count=`0`。

### PG-2 — 数据与消息可靠

- accepted-but-lost=`0`；
- duplicate execution=`0`；
- duplicate terminal reply=`0`；
- cursor 越过未持久消息=`0`；
- restart 后未完成 job 可恢复。

### PG-3 — 可见、可重建、资源受控

- Private-MetaDatabase no-clone canonical adapter verified 或真实 adapter `activation_pending`；
- Timeline 可从 canonical 重建；
- Status 维度完整且脱敏；
- R2/OCI adapter verified 或准确显示 activation state；
- resource protect/degraded/recover 通过压力阶梯。

### PG-4 — 双重 Assurance

- 软件正确性、模型能力安全、安全隐私、供应链、许可证全过；
- P0/P1 未处置项=`0`；
- fake clock 覆盖全部时间逻辑；
- 无真实时间 Soak/观察 Gate。

### PG-5 — 上线与交接

- immutable candidate、真实 adapter smoke、C0–C4 请求数 Canary；
- rollback 和 re-forward 均通过；
- isolated restore/reconcile 通过；
- final state 与 status snapshot 一致；
- 输出启动、停止、诊断、恢复和回滚命令。

---

## 6. Request-count Canary

| Step | 请求 | Pass Gate |
|---|---:|---|
| C0 | simulator 20 | 全部通过、重复/丢失=0 |
| C1 | OVH内部 10 | E2E、status、canonical正确 |
| C2 | 授权微信 10 | 成功率100%、双回复=0 |
| C3 | 故障注入 20 | degraded/recovery/rollback正确 |
| C4 | 正式槽位 20 | 无P0/P1、资源未越界 |

失败立即回滚或保持 candidate，不等待“再观察”。

---

## 7. 最终交付制品

- 可安装的固定本地 CyberBoss source bundle/patch；
- pinned lockfile；
- SQLite additive migrations；
- systemd/config/resource profile；
- Cloudflare Access/DNS/status integration；
- Private-MetaDatabase no-clone canonical adapter；
- Timeline/search；
- R2/OCI adapter；
- backup/restore/deploy/rollback；
- CI、加速可靠性、模型/安全 eval；
- SBOM、license/source-offer；
- immutable release/tag/checksum；
- `RELEASE_REPORT.md`；
- 唯一 final state。

---

## 8. Final State

- `MVP_LIVE`：所有 P0 和真实微信+Codex主链通过；
- `MVP_DEGRADED`：核心可用，非核心 P1 adapter 降级且状态明确；
- `ACTIVATION_PENDING`：软件与模拟验证完成，但至少一个真实关键适配器未激活；
- `STOPPED`：安全、数据、账户风控、许可证或不可逆风险；
- `NOT_VERIFIED`：证据不足。

不设置未来时间观察条件；完成 Gate 后立即作出当前真实结论。
