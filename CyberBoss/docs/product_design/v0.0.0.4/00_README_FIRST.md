# CyberBoss Full-Cloud MVP v0.0.0.4 — 唯一入口

> 状态：Implementation-ready Final Task Pack
> 日期：2026-07-26（Australia/Sydney）
> 目标域名：`cyberboss.linzezhang.com`
> 全局状态入口：`status.linzezhang.com`
> 运行位置：OVH Singapore
> 目标：24 小时实施窗口内上线可真实使用的全云 7×24 MVP
> 数据原则：`LinzeColin/Private-Database@main/Private-MetaDatabase (domain=CyberBoss)` 是唯一权威热事实源；Cloudflare R2 是冷对象层；OCI 是冷对象异地备份
> 来源边界：以固定 SHA 导入必要源码并保留 AGPL 归属；导入后不保留上游 remote、Git URL 依赖、自动同步或运行时拉取关系

---

## 0. 本版本纠正

v0.0.0.4 是 Owner 批准的 MetaDatabase 治理归一化版本。产品范围、6 个
Stage、30 个 Task 和 53 个 Acceptance Oracle 不变；仓库、许可证、数据和
workspace 身份以 `CyberBoss/machine/facts/owner_decisions.json` 为先决事实。

本项目唯一代码身份为 `LinzeColin/MetaDatabase` 的 `CyberBoss/` 子树，使用
AGPL-3.0-only。禁止创建独立代码仓；禁止 clone Private-Database；每个 Run
最多执行一个 TaskPack phase；PG-0–PG-5 全部通过前禁止 push/PR。

“Product-Design-Taskpack 的双平面 7 文件”只表示**至少包含七类核心控制文件**，从未构成 ZIP 文件数量上限。本版本不再把根目录或任务包限制为七个文件。

任务包采用：

```text
7 个核心控制文件（最低骨架）
+ 8 个直接降低开发风险的专项/交接文件
+ 可执行 implementation-kit
+ 外部独立 Roadmap、后续升级路线、Pursuing Goal
```

任何补充文件必须满足至少一个条件：能直接减少开发时间、消除歧义、提供可运行起点、提供可执行验收、支持部署/恢复；禁止为凑结构制造空 Schema、空台账或纸面证据。

本版本同时取消以下内容：

- 任何 24 小时、7 天、30 天或其他真实时间 Soak；
- 任何“等待观察后再开发/发布”的门槛；
- 任何按时间睡眠的 Canary；
- 任何为了证明稳定而人为挂机；
- 任何凭据、扫码或域名未就绪就让开发线程整体停住的规则；
- 任何与真实风险无关的人工审批、阶段签字或时间型 Gate。

稳定性改为**立即可执行、可重复、可加速的确定性验证**：虚拟时钟、崩溃切点矩阵、重复消息重放、网络故障注入、进程重启循环、备份恢复循环、资源压力和请求计数型 Canary。上线后继续监控，但监控不是开发完成或发布的等待门槛。

---

## 1. 唯一目标架构

```text
微信 iLink
   │
   ▼
OVH Singapore（唯一运行面，不依赖任何 Mac）
├── CyberBoss 微信桥与命令控制器
├── Durable Inbox / Job State Machine / Durable Outbox
├── Codex CLI + Codex App Server（loopback 主 Runtime）
├── Claude Code 适配边界（默认关闭，不阻塞 MVP）
├── 单活动任务 + allowlisted Git Worktree
├── SQLite WAL（可重建事务 Spool，不是权威热事实源）
├── Timeline 写入、构建、搜索与只读页面
├── Status Snapshot / Health / Self-heal
└── Canonical Sync / Backup / Restore
       │
       ├── LinzeColin/Private-Database/Private-MetaDatabase (domain=CyberBoss)：唯一权威热事实源
       ├── Cloudflare R2：冷快照、日志包、未来附件
       └── OCI Object Storage：R2 冷对象异地再备
```

硬性边界：

- Mac 运行依赖 = 0；
- 本地连接器 = 0；
- Codex App Server 只监听 `127.0.0.1`，不得经公网、Cloudflare Tunnel 或反向代理暴露；
- 只有 Web/Timeline/Status 人类入口通过 Cloudflare Access 暴露；
- 微信、Codex、队列、Timeline、恢复和状态都在 OVH 内完成；
- 单用户、单 Runtime、单活动任务，优先可靠和资源可控。

---

## 2. Pursuing Goal

> 在不依赖任何 Mac、不公开 Codex App Server、不把秘密或原始私聊写入
> 代码仓或 canonical object 的前提下，于 24 小时实施窗口内在现有 OVH
> Singapore 上交付微信驱动的 CyberBoss + Codex CLI + Timeline 全云 7×24
> MVP，以 `LinzeColin/Private-Database@main/Private-MetaDatabase
> (domain=CyberBoss)` 作为唯一权威热事实源、Cloudflare R2 作为冷对象层、
> OCI 作为异地冷备，并把运行状态接入 cyberboss.linzezhang.com 与
> status.linzezhang.com，做到可观察、可验证、可恢复、可回滚、资源受控且
> 没有任何真实时间 Soak Gate。

---

## 3. 当前 MVP 必须完成

### 3.1 Golden Path

1. 微信文本消息由云端长轮询接收；
2. 原始更新先进入 durable inbox，再提交微信 sync cursor；
3. `source_message_id` 唯一约束实现幂等；
4. job 进入明确状态机；
5. OVH Codex 真实执行 allowlisted workspace 中的任务；
6. 结果进入 durable outbox；
7. 微信成功发送后才标记 delivered；
8. 结构化摘要、状态转换和 Timeline 事件通过免 clone 客户端批量同步到
   `Private-MetaDatabase` 的 `domain=CyberBoss`；
9. `cyberboss.linzezhang.com` 展示受 Access 保护的 Timeline、搜索和详细状态；
10. `status.linzezhang.com` 展示 CyberBoss 项目行和深度状态。

### 3.2 必须具备的可靠性

- cursor commit 顺序修复；
- durable inbox/outbox；
- 消息幂等与单实例；
- 进程崩溃后确定性恢复；
- Private-Database API 不可用时本地 spool 继续、明确 `sync_pending`、恢复后补齐；
- 微信发送失败时重试但不重复可见回复；
- Codex App Server 崩溃时 supervisor 重启并保留真实 job 状态；
- 资源压力时停止接收新的 mutation job，但收消息、查状态、恢复和同步仍可工作；
- R2 快照与隔离恢复；
- OCI 备份适配器和立即可执行验证；若 OCI 凭据尚未提供，不阻塞其余开发与上线，只将 OCI 外部激活标记为 `activation_pending`，不得伪称已上传。

### 3.3 必须具备的产品能力

- `/status`、`/stop`、`/model`、`/bind <alias>`；
- allowlisted workspace alias，禁止微信输入任意绝对路径；
- Timeline 记录用户任务、关键状态、结果摘要和错误，不记录 secret；
- Timeline 搜索：MVP 使用 SQLite FTS5 或等价轻量索引，不引入 Elasticsearch/Meilisearch；
- Cloudflare Access 使用现有 Google/GitHub IdP，避免自建认证；
- 访问统计采用 Cloudflare Web Analytics 或现有匿名聚合统计，不记录私人消息；
- `healthz`、`readyz`、详细 status snapshot；
- status 项目卡包含 Runtime、微信 poll/send、队列、canonical sync、Timeline、R2/OCI、CPU/RAM/disk、版本和回滚点；
- systemd 常驻、自愈、日志限额、原子发布与回滚。

### 3.4 当前明确不做

- 微信图片、音频、视频、PDF、Word、Excel、ZIP 执行链路；
- 多用户、多租户、多微信账号、多节点；
- 多任务并发；
- 任意 shell、任意绝对路径、开放式 MCP 市场；
- Kubernetes、Redis、PostgreSQL、Temporal、消息总线；
- OpenHands/AstrBot/Wechaty 整套迁移；
- 复杂管理后台或原生 App；
- 对外商业 SLA；
- 以真实时间流逝为条件的 Alpha/Beta/GA Gate。

后续能力独立写入《Stage 2 / Stage 3 / 后续升级路线》，不得污染当前 24 小时 MVP。

---

## 4. 文件结构与权威顺序

### 4.1 七个核心控制文件

1. `00_README_FIRST.md`：唯一入口、Canonical Facts、范围与执行规则；
2. `01_PRFAQ_STRATEGY_OKR.md`：Working Backwards、战略、OKR、成本收益、证伪与竞品；
3. `02_PRD_ACCEPTANCE_CONTRACT.md`：需求、操作流、指标、Acceptance Oracle、Traceability；
4. `03_ARCHITECTURE_DATA_SECURITY.md`：架构、接口、数据、容量、安全、隐私、可靠性；
5. `04_TASK_DAG_EXECUTION_PACK.yaml`：机器可执行无环 Task Graph；
6. `05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md`：无真实时间 Soak 的双流水线、故障注入和发布；
7. `06_OPERATIONS_STATUS_HANDOVER.md`：安装、激活、运维、Status、恢复、回滚与交接。

### 4.2 直接减少开发时间的专项文件

8. `07_RESEARCH_COMPETITOR_UPSTREAM_FINDINGS.md`：GitHub/公开网络调研和可借鉴设计；
9. `08_UPSTREAM_CODE_CHANGE_MAP.md`：CyberBoss 现有代码到目标改造的文件/函数级变更地图；
10. `09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`：普通决策预授权、凭据槽位、一次性激活动作和默认值；
11. `10_TRACEABILITY_RELEASE_CHECKLIST.md`：需求→任务→测试→证据→发布制品一页式核对表；
12. `11_AGENT_EXECUTION_PROMPTS.md`：Codex 主开发、Claude Code 独立复审和最终激活的直接执行 Prompt；
13. `12_CURRENT_ROADMAP.md`：当前产品 Stage 1 + Stage 2A 路线镜像；
14. `13_STAGE2B_STAGE3_UPGRADES.md`：明确隔离的后续升级路线，不构成本次阻塞；
15. `14_PURSUING_GOAL.txt`：一句话北极星 Prompt。

`12–14` 是便于交接的镜像/路线文件，不得覆盖 `00/02/04` 的当前范围和验收合同。

### 4.3 可执行工程附件

`implementation-kit/` 提供配置模板、SQL、systemd、部署/回滚/备份/恢复/status 脚本、CI 和确定性测试起点。它不是空文档集合；每个文件必须能被开发 Agent 直接复用、运行或改造成目标仓库代码。

### 4.4 冲突优先级

```text
00 Canonical Facts
→ 02 Acceptance Contract
→ 04 Task DAG
→ 03 Architecture
→ 05 Accelerated Verification
→ 06 Operations
→ 09 Preauthorization
→ 10 Traceability
→ 11 Agent Prompts
→ 08 Change Map
→ 01 Strategy
→ 07 Research
→ implementation-kit
```

---

## 5. Canonical Facts

1. 目标是全云部署，Mac 依赖为零；
2. `cyberboss.linzezhang.com` 是 CyberBoss 人类入口；
3. `status.linzezhang.com` 是全局状态入口，不新建第二套全局 Status；
4. Codex CLI/App Server 与项目工作副本部署在 OVH；
5. Codex App Server 只允许 loopback；
6. `LinzeColin/Private-Database@main/Private-MetaDatabase (domain=CyberBoss)` 是唯一权威热事实源；
7. SQLite 是可重建事务 spool，不是长期权威库；
8. R2 是冷对象层；OCI 是冷对象异地再备；
9. Timeline 必须保留并云端化，优先沿用上游已集成能力；
10. MVP 仅文本、单用户、单活动任务；
11. 任何 secret、Codex auth、微信 bearer、原始私聊不得进入代码仓或
    Private-MetaDatabase；
12. 失败不得伪装成功，未激活外部服务不得标记已验证；
13. 资源治理优先于增加组件；
14. 7 个核心文件不是数量上限；
15. 不允许任何真实时间 Soak、等待观察期或按时间挂机的发布 Gate；
16. 可逆普通决策均预授权，开发线程不得因普通输入、实现选择或非关键凭据缺失而整体暂停；
17. 只有危险动作本身被阻止，其他无依赖 DAG 分支继续；
18. 7×24 是目标运行模式和恢复能力要求，不以实际等待 7×24 来验收。
19. 代码仓唯一为 `LinzeColin/MetaDatabase`，项目路径唯一为 `CyberBoss/`；
20. MVP workspace alias 唯一为 `cyberboss`，默认写入只允许 `CyberBoss/**`；
21. 上游只作为固定来源快照；依法保留归属但不保留持续技术关系；
22. 每个 Run 最多一个 phase；全部 TaskPack 完成前只允许本地 commit。

---

## 6. 数据边界

| 层 | 角色 | 保存内容 | 不得保存 |
|---|---|---|---|
| `LinzeColin/Private-Database/Private-MetaDatabase (domain=CyberBoss)` | 唯一权威热事实源 | 脱敏任务摘要、状态转换、Timeline 源、配置版本、对象索引、发布/恢复索引 | token、auth.json、微信 bearer、原始私聊、大型二进制、实时 lease |
| OVH SQLite WAL | 事务 Spool | inbox、job、event、outbox、sync queue、lease、retry | 作为唯一长期事实源、大文件长期堆积 |
| Cloudflare R2 | 冷对象层 | 加密/压缩快照、日志包、Timeline 构建包、未来附件 | 热队列、锁、实时事务 |
| OCI Object Storage | 异地冷备 | R2 清单和冷快照副本 | Runtime 依赖、热读写 |

Private-Database 不承担每个 token 或每次进度的写入。Canonical sync 把脱敏
事件批次或压缩快照通过 `private_db_client.py` 的 `ingest/get/list/verify`
协议写入内容寻址对象和 manifest；遇到 API 限流按响应头和退避策略重试。
高风险 mutation 在执行前确保相关授权/receipt 已进入权威事实源。禁止
clone、fetch、rebase 或 push Private-Database。

---

## 7. 无等待开发规则

### 7.1 已预授权

开发 Agent 无需询问即可：

- 读取目标公开仓库和官方文档；
- 建立分支/worktree、修改代码、增加测试和文档；
- 安装 Node、Codex CLI、SQLite 工具、systemd unit 和必要轻量依赖；
- 采用 TypeScript 或上游既有 JavaScript 风格；
- 创建 additive migration、feature flag、loopback service；
- 使用 Cloudflare Access 保护 UI；
- 使用 systemd 而不是 Kubernetes/Docker 多层编排；
- 清理可重建缓存和已完成冷备校验的临时文件；
- 运行全部单元、集成、E2E、故障注入、压力、恢复和安全测试；
- 失败后自动修复并重复测试；
- 部署到 staging slot、切换 release symlink、执行自动回滚；
- 对缺失的外部凭据使用 mock/local adapter 完成代码、测试和部署准备。

### 7.2 外部激活不阻塞开发

下列动作无法由 Agent 代替用户，但必须集中到最终激活窗口，不得在开发中零散打断：

- 微信扫码；
- Codex `device-auth`；
- GitHub 最终代码发布、Private-Database no-clone client、Cloudflare、R2、
  OCI 的最小权限凭据分别注入；
- DNS/Access 最终切换。

凭据未到时，Agent继续完成：接口、模拟器、测试、systemd、部署 slot、status adapter、secret slot 和 activation script。只在最终激活时输出一张最小输入表。

### 7.3 只阻止危险动作，不阻止整个 DAG

以下情况只停止对应危险动作，其他任务继续：

- 需要公开 Codex App Server、SSH 或任意 shell；
- 需要提交 secret；
- 需要不可恢复删除用户数据；
- 需要未经授权付费升级；
- 微信出现封禁/风控提示；
- 许可证义务无法满足。

报告格式仅包含：证据、被阻止的动作、默认安全方案、其余继续执行的 DAG 节点。禁止把“等待用户回复”写成全局 Stop Condition。

---

## 8. 24 小时实施规则

24 小时是交付截止目标，不是等待时钟。任务按依赖和并行泳道推进，不设置固定休眠或观察阶段：

```text
Lane A：固定来源基线与可靠消息补丁
Lane B：OVH/systemd/release/资源治理
Lane C：Private-MetaDatabase no-clone canonical + R2/OCI adapter
Lane D：Timeline/search/status/Cloudflare Access
Lane E：测试、故障注入、安全、回滚和交付证据
```

Lane 只描述依赖关系和当前 phase 内可并行的验证，不授权一个 Run 执行多个
phase。一旦当前 phase 需要外部激活，Agent 用模拟器完成该 phase 的其余
工作；下一个 phase 仍需新的 Run Contract。发布 Gate 只看可执行 Oracle，
不看经过了多少分钟、小时或天。

---

## 9. 立即可执行的发布证明

只有以下 Oracle 全部通过，才能标记 `MVP LIVE`：

- 真实微信→OVH Codex→微信端到端至少一条；
- 同一 source message 重放 1,000 次，仅产生一个 execution；
- inbox/cursor/outbox/job 的每个事务切点执行崩溃矩阵，重启后不丢且不重复 mutation；
- 100 次进程快速重启循环，singleton 始终为 1；
- 100 组微信 send 失败/超时/重复 ack 场景，最终用户可见回复最多一条；
- 100 组 Codex crash/overload/auth/network 场景，状态和重试分类正确；
- 50 组 Private-Database 403/409/429、断网、部分成功场景，canonical outbox 可补齐；
- 20 次 SQLite→R2 快照→隔离目录恢复→canonical reconcile 循环通过；
- 虚拟时钟覆盖所有提醒、退避、TTL、check-in、生命周期逻辑，不等待真实时间；
- 资源压力测试能触发 degraded/protect 并在压力解除后自动恢复；
- 请求计数型 Canary 完成只读、可逆 mutation、恢复三组场景，无时间等待；
- Timeline 可从 canonical data 重建和搜索；
- `status.linzezhang.com` 能读取最小安全 snapshot；
- secret scan、依赖扫描、静态分析、AGPL 对应源检查无未接受阻断项；
- deploy、health、rollback、restore 命令真实运行并留下普通日志/测试报告；
- 所有未具备真实外部凭据的适配器明确为 `activation_pending`，不伪称成功。

---

## 10. 直接执行指令

开发 Agent 必须：

1. 完整读取 11 个控制/专项文件和 `implementation-kit/README.md`；
2. 以 `04_TASK_DAG_EXECUTION_PACK.yaml` 为机器执行顺序；
3. 先运行仓库、环境和配置静态检查，但不得因普通凭据缺失停止开发；
4. 先完成 Walking Skeleton，再补齐可靠性、数据、Status 和恢复；
5. 所有验收使用确定性测试和故障注入，禁止真实时间 Soak；
6. 不创建重复 PRD、重复 Roadmap 或阶段性空台账；
7. 每条需求必须关联 Task、Oracle 和真实证据；
8. 可逆问题自行判断并修复，危险动作按 7.3 仅局部阻止；
9. 最终只报告：已完成、已验证、activation_pending、真实阻断、剩余风险、当前 commit、部署版本和一条回滚命令；
10. 不得伪造已部署、已登录、已备份或已恢复。
