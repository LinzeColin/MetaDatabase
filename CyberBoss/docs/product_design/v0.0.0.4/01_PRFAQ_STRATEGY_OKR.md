# 01 — PR/FAQ、战略、OKR、成本收益与反证

## A. Working Backwards Press Release

### 标题

**CyberBoss Cloud 上线：无需 Mac 常驻，直接通过微信 7×24 调用云端 Codex，并在同一状态平台查看任务、Timeline、备份与资源健康。**

### 日期

2026-07-26，Sydney / Singapore

### 客户问题

用户现有 AI 开发工作高度依赖本机：Mac 休眠、断网、客户端异常或不在电脑旁时，微信入口、Codex 执行和项目访问都会中断。即使桥接进程仍显示“在线”，消息也可能因微信长轮询失效、sync cursor 提交顺序、出站回复失败或重复进程而丢失、重复或没有真实反馈。与此同时，OVH VPS 的内存和存储余量有限；任务包以既有规划包络为起点，开工后由实时 preflight 自动选择资源档位，不能把工具、仓库和历史数据无限堆在 OVH。

### 新方案

CyberBoss Cloud 把微信桥、Codex CLI、受控项目工作副本、任务 spool、Timeline、状态输出和恢复机制统一部署到 OVH Singapore。微信消息先进入 durable inbox，再由单任务 Runtime 执行；最终事实同步到 `LinzeColin/Private-Database@main/Private-MetaDatabase (domain=CyberBoss)`，冷对象和快照分流到 Cloudflare R2，OCI 保存冷备份。用户可从 `cyberboss.linzezhang.com` 查看受保护的 Timeline 和运行状态，`status.linzezhang.com` 继续作为全局状态入口。

### 客户结果

- Mac 关机也不影响消息接收和 Codex 执行；
- 任务不会因为进程重启、微信游标推进或短暂网络失败而静默消失；
- 每个任务可追踪到真实 Git commit、测试结果和微信回复；
- OVH 只保留活跃工作副本与可重建 spool，历史数据自动分流；
- 自愈、状态与备份为确定性机制，不消耗 LLM token；
- 后续可在不推倒 MVP 的情况下增加附件、多 Runtime、更多通道和更严格的机制型 SLO。

### 客户引语（目标陈述，不作为已发生事实）

> “我不需要守在 Mac 前，也不用猜 CyberBoss 到底有没有工作。微信里能发任务，status 能看状态，Private-MetaDatabase 能重建，Timeline 能追溯，失败会明确告诉我。”

---

## B. FAQ

### Q1：这是不是把现有 CyberBoss 推倒重写？

不是。一次性导入固定 SHA 的微信 iLink adapter、Codex/Claude runtime
抽象、命令解析、diary/check-in 和 Timeline 工具后，只维护本地 source bundle。
新增或重构的重点是 durable inbox/outbox、cursor commit ordering、singleton、
Private-MetaDatabase no-clone canonical sync、资源护栏、状态输出和云端部署。

### Q2：为什么不直接部署 OpenHands、AstrBot 或 Wechaty？

它们各自更成熟于不同领域，但引入会扩大依赖、迁移微信协议、增加内存和运维。当前目标是 24 小时内上线单用户 MVP；在 CyberBoss 已具备微信 + Codex + Timeline 的条件下，原位强化的收益/成本比更高。项目借鉴其 runtime 边界、adapter/plugin、事件流、探针和评测方法，而不是复制整个栈。

### Q3：Private-MetaDatabase 为什么是唯一长期事实源，但还保留 SQLite？

Private-MetaDatabase 是长期权威事实源；SQLite 只负责进程必须具备的事务、
lease、重试和断电恢复。远端 API 无法可靠承担每条消息的实时锁。所有完成
状态和必要结构化事件必须快速通过 `private_db_client.py` 同步为内容寻址对象；
SQLite 可从 Private-MetaDatabase 与微信/对象索引重建，不拥有独立长期事实权。

### Q4：为何不用 PostgreSQL？

单用户、单并发、低消息量的 MVP 不需要数据库服务器。PostgreSQL 会增加
常驻内存、备份和升级负担。SQLite WAL + Private-MetaDatabase canonical
objects 能满足本阶段；当并发、多用户或数据量触发明确迁移阈值时再升级。

### Q5：为什么不把 Codex App Server 暴露到 Cloudflare？

没有必要且增加远程执行风险。CyberBoss 与 Codex 同机，使用 loopback WebSocket；Cloudflare 只面向人类访问的 Timeline、管理/status 页面。Runtime transport 不暴露公网。

### Q6：能否做到真正 7×24？

能做到“全云运行、自动恢复、消息不静默丢失、状态可见”的 MVP。单台 VPS 仍可能发生机房、宿主机或网络故障，因此不承诺生产级高可用。MVP 是单节点可恢复，不是多区域无中断。

### Q7：ChatGPT、Google、GitHub 登录怎么处理？

- Codex CLI 使用 ChatGPT device auth，凭据只在 OVH root-protected state 中；
- `cyberboss.linzezhang.com` 的人类 UI 使用 Cloudflare Access，首选 Google/GitHub IdP；
- “用 ChatGPT 账号登录 CyberBoss 网页”不是当前已核验的标准 OAuth 路径，本 MVP 不伪造该功能，保留 Feature Flag 和后续官方能力接入点。

### Q8：Timeline 是否已经存在？

存在。CyberBoss 已依赖并暴露 `timeline-for-agent` 的 write/read/build/serve/screenshot 能力。本任务不再开发第二个 Timeline，只完成云端数据路径、静态构建、Access 保护、搜索和 status 摘要。

### Q9：会不会把微信私人消息写入代码仓或长期数据库？

代码仓不保存业务数据。Private-MetaDatabase 的 canonical ledger 默认只保存脱敏摘要、
hash、状态、时间、workspace alias、结果证据索引。只有明确开启
`CB_STORE_FULL_CONTENT=true` 后，才允许加密保存必要正文，并需单独审查密钥和保留期。

### Q10：24 小时上线遇到外部激活未就绪时怎么办？

开发不得整体等待。Agent 继续完成代码、模拟器、确定性测试、staging slot、systemd、Status adapter、备份/恢复和 activation script；微信扫码、Codex device auth、DNS 与最小权限凭据集中到最终激活窗口。只有危险动作本身被阻止，其他无依赖 DAG 节点继续。最终明确区分 `verified`、`activation_pending` 和真实阻断，不伪造上线。

---

## C. 战略目标

### 北极星

**在最少常驻资源和最少治理复杂度下，把“微信发出一项受控任务”稳定转化为“云端 Runtime 真实执行、结果可靠返回、事实可追溯、系统可恢复”。**

### 战略原则

1. **真实链路优先于 UI。** 先确保微信→durable inbox→Runtime→outbox→微信，再做页面美化。
2. **恢复优先于不故障幻想。** 单节点必然会失败，必须可恢复、可重放、无静默丢失。
3. **Private-MetaDatabase 事实源，OVH 运行面。** 计算与短期事务在 OVH，
   长期结构化事实通过免 clone 客户端进入 Private-MetaDatabase，冷对象在 R2，备份在 OCI。
4. **复用优先于重写。** 保留 CyberBoss/Timeline 的有效内核，只替换薄弱边界。
5. **单并发优先于吞吐。** 4 GB VPS 的收益来自稳定，不来自并行 Agent。
6. **白箱优先于黑箱。** systemd、shell、SQLite、content-addressed objects 和明确状态机；不得用不可解释常驻 Agent 做运维。
7. **证据优先于完成声明。** 每个 Acceptance 都有真实 Oracle。
8. **安全默认拒绝。** 只允许明确用户、workspace alias、Runtime 和命令；未知路径/权限拒绝。
9. **可逆发布。** additive migration、Feature Flag、release symlink、快速 rollback。
10. **范围锁定。** 24h MVP 不吸收附件、多用户、重型编排和商业化需求。

---

## D. OKR

### O1 — 在 24 小时实施窗口内建立真正全云 Walking Skeleton

- KR1：真实微信文本经 OVH CyberBoss 调用 OVH Codex 并返回微信，连续成功 10 次；外部微信激活前以 iLink simulator 完成同样链路。
- KR2：Mac 关闭或完全离线不影响链路，系统没有任何本地连接器配置。
- KR3：Codex App Server 仅监听 loopback，端口扫描和配置审计均不可从公网访问。
- KR4：一个 correlation ID 串联 inbox、job、Codex turn、outbox、canonical event 和微信 delivery receipt。
- KR5：`cyberboss.linzezhang.com` 的 Timeline、搜索和详细状态经 Cloudflare Access 访问。

### O2 — 消除可预见的静默丢失和重复执行

- KR1：消息在 cursor commit 前 durable write；事务切点崩溃矩阵无丢失。
- KR2：同一 `source_message_id` 重放 1,000 次只执行一次。
- KR3：100 组 send failure/timeout/duplicate ack 场景中，最终用户可见结果最多一条。
- KR4：100 次快速重启和启动竞争后始终只有一个 bridge owner。
- KR5：所有未终态 job 在崩溃后恢复、重试或明确终止，不出现假成功。

### O3 — 在 OVH 资源边界内形成可持续数据生命周期

- KR1：资源 profile 由 live preflight 选择；压力达到 protect 阈值时停止新 mutation job，而非崩溃或挤压其他服务。
- KR2：日志、cache、release、workspace、state 均有大小配额和可立即执行的 GC。
- KR3：Canonical events 按条数/大小批量同步；Private-Database 的
  403/409/429、断网或部分成功进入 `sync_pending` 并可确定性补齐。
- KR4：R2 快照完成 hash 校验并执行 20 次隔离恢复循环；OCI adapter 在有凭据时立即执行同一验证，无凭据时仅标记 `activation_pending`。
- KR5：Private-MetaDatabase + R2 能重建 Timeline 与终态 job index，
  不依赖原 OVH SQLite 才能解释历史。

### O4 — 建立可观察、可诊断、可自愈的运行面

- KR1：`status.linzezhang.com` 展示服务、微信、Runtime、队列、同步、备份、Timeline、版本和资源状态。
- KR2：process health、poll freshness、send freshness、synthetic E2E 四种健康不混淆。
- KR3：自愈不调用 LLM；故障恢复由事件/探针触发并通过故障注入验证，不以真实等待时间验收。
- KR4：状态快照不含秘密、prompt、微信 ID、绝对路径或私人正文。
- KR5：启动、停止、诊断、备份、恢复和回滚都有单命令入口和真实执行证据。

### O5 — 形成软件正确性与模型能力安全双流水线

- KR1：lint/unit/integration/E2E/fault-injection/security pipeline 为发布必过。
- KR2：Codex 通过 golden tasks、false-success、prompt injection、secret exfiltration、workspace escape 和 approval tests。
- KR3：所有退避、TTL、提醒、check-in 和生命周期测试使用虚拟时钟，不等待真实时间。
- KR4：Alpha/Beta/GA 只按能力、风险和证据 Gate 划分，不按 7 天/30 天观察期划分。
- KR5：AGPL 对应源、依赖清单和修改说明可向网络用户提供。

---

## E. Baseline 与测量

| 指标 | 当前 Baseline | MVP 目标 | 立即可执行测量方式 | 发布门槛 |
|---|---|---|---|---|
| 全云可执行 | 尚未部署 | Mac 断开仍能 E2E | 断开/不配置任何 Mac 后运行真实或模拟微信任务 | 通过即 Gate |
| 消息持久化顺序 | 上游存在 cursor 先保存风险 | inbox durable 后才 commit cursor | 每个事务切点 kill/restart 矩阵 | 全部切点通过 |
| 重复执行 | 上游公开过重复桥/回复问题 | 同一 source id 恰好一次执行 | 1,000× replay + 100× restart race | execution_count=1 |
| 出站可靠性 | 主路径缺统一 durable retry | 生成与送达状态分离 | 100 组失败/超时/重复 ack | 用户可见最多一条 |
| Runtime 恢复 | 云端机制未建立 | crash 后状态真实且可恢复 | 100 组 process/app-server crash | 无假成功/无丢 job |
| Canonical sync | 目标架构未部署 | 可批量、补偿、冲突安全 | mock 403/429/冲突/断网 50 组 | 全量 reconcile |
| Timeline/search | 本地能力已存在 | Access 保护、可重建、可搜索 | 从空目录用 canonical data 重建 | 结果一致 |
| Status | 现有全局 status，尚无 CyberBoss contract | 安全 snapshot 与项目卡 | contract test + secret scan + adapter fixture | 全部通过 |
| RAM/CPU/disk | 由 live preflight 读取 | 自适应 profile + protect/recover | cgroup 压力注入与解除 | 不 OOM、不误杀他服 |
| 7×24 能力 | 尚未证明 | 常驻、自启、自愈、可恢复、无时间 Gate | restart/host-service/fault matrix + synthetic requests | 机制型 Oracle 全过 |
| 备份恢复 | 未部署 | Private-MetaDatabase/R2 可重建，OCI adapter 可激活 | 20 次 backup→restore→reconcile | hash/row/event 一致 |

不以“经过了多少天”作为开发、发布或升级门槛。上线后的真实运行指标用于持续改进，不反向阻塞本次交付。

---

## F. 用户、痛点、价值与非目标

### 主要用户

- 唯一授权用户：Linze Zhang；
- 技术操作主体：Codex / Claude Code 作为受控开发 Agent；
- 运维查看者：同一用户通过 status 与 Cloudflare Access；
- 暂不支持其他微信用户、团队成员或客户。

### 最高优先级痛点

1. 只有 Mac 在线时才能远程使用 Codex；
2. 消息是否被接收、执行、回复缺乏确定证据；
3. 重启、网络失败、重复进程可能造成静默丢失/重复；
4. 项目、Timeline、状态和备份彼此割裂；
5. OVH 资源小，不能按普通大平台架构堆服务；
6. 用户不希望在开发中持续提供小授权或处理技术选择；
7. 不希望形式化台账和自动 Agent 消耗超过实际收益。

### 核心价值

- 随时从微信发起真实开发/分析任务；
- 不依赖 Mac；
- 失败透明、可恢复、可追溯；
- 复用现有 GitHub/Cloudflare/OCI/status 体系；
- 将常驻资源和运维复杂度控制在个人系统可承受范围；
- 给后续生产化留下清晰演进边界。

### 非目标

详见 `00_README_FIRST.md §2.3`。任何新增需求必须先证明不影响 24h MVP Pass Gate，否则进入后续路线。

---

## G. 业务线与工作流

MVP 只有四条一级业务线，避免入口膨胀：

### BL1 — 微信任务执行

```text
用户发文本
→ 身份/命令/长度校验
→ durable inbox
→ 返回 accepted/job_id
→ 单任务调度
→ Codex 执行
→ 结果校验
→ durable outbox
→ 微信回复
→ canonical event sync
→ Timeline 写入
```

### BL2 — 状态与监督

```text
/status 或网页
→ 聚合 process/poll/send/runtime/queue/sync/backup/resource
→ 脱敏
→ status snapshot
→ status.linzezhang.com
```

### BL3 — Timeline 与历史追溯

```text
终态 job / diary / check-in
→ Timeline canonical source
→ debounce build
→ 静态只读页面
→ Cloudflare Access
→ 搜索/筛选
```

### BL4 — 恢复与发布

```text
local immutable release candidate
→ 双流水线
→ staging/synthetic
→ blue-green release
→ canary
→ health/ready/E2E
→ promote 或 rollback
→ R2 snapshot
→ evidence summary
```

---

## H. 竞品研究与模仿超越

### H1. 对比矩阵

| 对象 | 成熟优势 | 本项目直接借鉴 | 本项目要超越的单用户指标 | 当前不采用 |
|---|---|---|---|---|
| CyberBoss | 微信、Codex/Claude、主动监督、Timeline 已统一 | 原适配器、runtime、命令、工具 | durable inbox/outbox、云端可恢复、status/Private-MetaDatabase/R2/OCI 治理 | 重写核心 |
| timeline-for-agent | 轻量结构化 Timeline、CLI/build | 同一数据模型和工具 | 与任务 canonical ledger、Access/status 原生联动 | 第二套 Timeline |
| OpenHands | runtime abstraction、事件流、sandbox/backends | 明确 runtime boundary、事件驱动状态 | 在 4 GB、单用户场景显著更轻、更少运维 | 整套平台 |
| SWE-agent | 配置驱动、可复现实验、真实 repo eval | golden tasks、环境契约、可复现日志 | 微信链路和长期状态是第一公民 | 作为运行平台 |
| Wechaty | channel SDK、provider abstraction | 保留可替换 channel interface | 当前 iLink 不迁移即可上线 | Day-1 协议迁移 |
| AstrBot | 多平台、插件、MCP、上下文管理 | adapter/plugin feature flag | 更窄范围、更低常驻资源、更强恢复证据 | 多平台全栈 |
| Uptime Kuma | 多探针、状态页、通知 | health/ready/poll/send/E2E 分层 | 直接汇入用户既有 status，不再新增一套 | 再部署监控平台 |
| GitHub Actions | 代码 CI/CD、审计、并发控制 | 最终发布流水线、release evidence | 代码发布证据与 Private-MetaDatabase 对象证据可追溯关联 | 把实时队列或业务数据放 Actions |
| Cloudflare Access/R2 | Zero Trust 人类入口、对象存储 | UI 保护、冷对象、Web Analytics | 与 Runtime/status/Timeline 明确数据边界 | Runtime 公网代理 |

### H2. “超越”的可证伪定义

不能证明“比世界所有软件都好”。本任务把该目标转换为可测的场景优势：

- 在 **2 vCPU / 4 GB / 40 GB、单用户、微信入口、Private-MetaDatabase canonical** 的约束下，常驻组件更少；
- 上游已具备微信+Timeline，无需引入第二套平台；
- 对消息 cursor、出站重试、重复桥、Private-MetaDatabase/R2/OCI 分层提供显式 Oracle；
- status 与现有用户基础设施原生融合；
- 全部运维为白箱确定性机制；
- 任何竞品若在相同约束下以更低成本满足全部 Acceptance Contract，则本项目必须优先复用/替换，不为自研而自研。

---

## I. 收益、成本、敏感性与机会成本

### I1. 收益区间（不承诺伪精确）

| 收益项 | 低情景 | 中情景 | 高情景 | 置信度 |
|---|---|---|---|---|
| 减少因 Mac 不在线造成的等待 | 每周节省少量切换时间 | 每周恢复数次远程执行窗口 | 成为日常主要入口 | 中 |
| 减少消息丢失/重复返工 | 偶发避免一次返工 | 稳定减少排查与重复任务 | 对长期自动化显著 | 中高（机制可测） |
| 统一 Timeline/status/恢复 | 只改善可见性 | 降低故障定位时间 | 成为后续 Agent 控制面基础 | 中 |
| 复用既有 OVH/GitHub code/Cloudflare | 近零新增基础费用 | 少量对象/API费用 | 触发 VPS 升级 | 中高 |

### I2. 成本区间

- 基础设施增量：优先复用现有 OVH、GitHub code publication、Cloudflare 和
  OCI；任何付费升级必须由实时资源证据触发，不预先承诺。
- 开发：本任务包已经完成公开研究、架构取舍、协议边界、DAG、Acceptance、变更地图、配置与脚本起点，减少开发 Agent 的搜索与决策成本。
- 验证：采用虚拟时钟、模拟器、重放和故障注入，计算成本可控，不产生 7 天/30 天等待成本。
- 运维：单节点 systemd/SQLite/Git 较低；多用户、多 Runtime、多节点会非线性增加，后续必须重新做收益/成本评估。

### I3. 敏感性分析

| 变量 | 低 | 中 | 高 | 决策影响 |
|---|---:|---:|---:|---|
| 每日消息数 | <50 | 50–300 | >300 | 高时 canonical object batching、rate limit 需调整 |
| 项目工作副本 | <3 GB | 3–8 GB | >8 GB | 高时必须 sparse/partial 或升级存储 |
| 单任务 Runtime RAM | <1.5 GB | 1.5–2.5 GB | >2.5 GB | 高时 4 GB VPS 无法稳定共存 |
| 附件量 | 0 | 偶发 | 高频 | 高频附件不属于当前 MVP，R2 成为必需 |
| Private-Database API 不可用 | <5 min | 5–60 min | >60 min | 长期不可用时系统应降级，不继续无限积压 |
| 微信兼容性 | 正常 | 偶发断连 | 账号不支持 | 不支持即 Kill Gate / 换 channel |

### I4. 机会成本

- 投入自研可靠层，意味着短期不能同时做附件、多用户和复杂 UI；
- 引入 OpenHands/AstrBot 可获得更多功能，但会牺牲 24h 可交付性、资源和治理简洁度；
- 不修可靠性直接上线，表面快但会把每次丢消息变成不可预测返工，长期成本更高；
- 历史上游未来变化不自动进入项目。只有新的 Owner Change Event 批准后，
  才能固定新 SHA、重新审计许可证并以一次性 source import 更新。

---

## J. Kill Criteria / 证伪实验

Kill Criteria 只否决某项技术路线或危险动作，不得把可并行的开发工作整体挂起。

### J1. 路线 Kill Criteria

1. 微信 iLink 账号明确不支持或触发风控：保留 channel adapter，使用 simulator 完成其余开发；真实微信激活标记阻断，不重写整套系统。
2. Codex device auth 在服务器无法使用：完成 app-server simulator、所有非认证功能和部署；真实 Runtime 激活标记阻断，不公开端口或改用未授权 API。
3. live preflight 发现资源极低：自动选择 `tiny` profile、partial clone、暂停非必要 build；只有实测无法运行单一 Runtime 才否决“同机 Codex”路线。
4. 上游协议与当前 Codex 不兼容且无法在 adapter 层修复：保留 durable control plane，评估官方 SDK adapter，不重写微信与数据层。
5. AGPL 对应源义务无法满足：不得对网络用户提供服务，但本地/内部开发和合规准备继续。

### J2. 可靠性 Kill Criteria

下列任一失败都否决当前实现并要求修复，不要求等待：

- 事务切点测试可静默丢失；
- duplicate replay 触发第二次 mutation；
- outbox 无法区分生成成功与发送成功；
- singleton 无法保证唯一 owner；
- Private-Database 409/retry 可覆盖或丢失 canonical event；
- restore 后无法解释终态历史；
- status 暴露 secret/private content；
- rollback 或 migration 不可逆。

### J3. MVP 发布 Kill Criteria

- P0/P1 安全问题；
- secret scan 命中真实凭据；
- Runtime 公网可达；
- 必要 Oracle 无真实证据；
- 资源压力导致 OOM 或影响既有服务；
- 真实外部适配器未激活却被报告为已成功。

### J4. 价值证伪

MVP 上线后不设置真实时间观察 Gate。价值由使用事件累计评估：当累计 30 个真实任务后，若成功使用率、节省操作步骤、恢复价值和维护成本均未达到 `01` 与 `02` 中阈值，则冻结功能扩张，只保留可用核心和数据，不继续进入附件/多用户阶段。

---

## K. 十轮完善记录

1. **目标纠偏：** 彻底删除“云端控制 + Mac 执行”，锁定全云 OVH。
2. **交付结构：** 将“7 文件”纠正为最低控制骨架，增加研究、变更地图、预授权、Traceability 和可执行工程附件。
3. **上游复用：** 保留微信 adapter、Codex runtime、命令、diary/check-in 和内置 Timeline，不从零造轮子。
4. **消息一致性：** 将 durable inbox-before-cursor、唯一 source id、durable outbox 和 delivery receipt 设为最高优先级。
5. **事实源治理：** Private-MetaDatabase canonical、SQLite spool、R2 cold、OCI replica 角色彻底分离；禁止每 token 写入。
6. **资源自适应：** 删除静态 RAM/磁盘开工硬门槛，改为 live profile、partial clone、配额和 protect/recover。
7. **无等待开发：** 凭据和扫码集中最终激活；缺失时用 simulator 并行完成其余工作；危险动作只局部停止。
8. **无 Soak 验证：** 所有 24h/7d/30d观察 Gate 改为虚拟时钟、重启循环、崩溃矩阵、请求计数 Canary 和恢复循环。
9. **Status/Timeline：** 复用既有全局 status 和上游 Timeline，增加轻量搜索、Access、非敏感 contract，不再部署第二套监控。
10. **交付反形式化：** 每个新增文件必须可执行或直接降风险；删除空 Schema、重复 PRD、阶段台账和伪造世界第一声明。

---

## L. 两轮 × 六角色独立对抗复审

> 当前环境没有可核验的独立 SubAgent 调度接口，因此不伪造“12 个外部 Agent 已运行”。以下是按相互独立职责完成的两轮、六视角审查；每条反对意见均已转成设计变更、Oracle 或 Kill Criteria。

### 第一轮：交付可行性与工程正确性

| 视角 | 反对意见 | 已落实修正 |
|---|---|---|
| Product | 7 文件硬上限会删掉必要实现上下文；范围易被后续路线污染 | 7 核心文件仅最低骨架；增加 4 专项文件和 implementation-kit；后续路线独立 |
| Architecture | 远端 Private-Database API 不能做热事务/lease；全量重写风险高 | SQLite WAL spool + Private-MetaDatabase canonical；原位强化 adapter/runtime |
| SRE | 真时间 Soak 不能在 24h 内完成且会阻塞交付 | 全部改为确定性故障矩阵、虚拟时钟、重启和恢复循环 |
| Security | 公开 app-server、任意 `/bind`、secret 同步均危险 | loopback、alias allowlist、secret split、Access、abuse tests |
| Data/Privacy | 原始微信正文进代码仓/Private-MetaDatabase/R2会扩大泄露面 | 默认 hash/脱敏摘要；正文不入 canonical；冷对象加密与 retention |
| Developer Experience | 扫码/凭据/域名会反复打断 Agent | 一次性 activation sheet；simulator 先行；仅危险动作局部阻止 |

### 第二轮：长期运行、成本与反证

| 视角 | 反对意见 | 已落实修正 |
|---|---|---|
| Red Team | prompt 可诱导读 secret、越界 workspace、伪造完成 | deny paths、workspace guard、false-success/secret/workspace red-team |
| FinOps/Capacity | 固定 4GB 假设可能不符实时机器；重型组件会挤压既有服务 | live profile、单并发、systemd cgroup、按需 build、无 Redis/Postgres/K8s |
| Reliability | process alive 不等于微信和 E2E 可用 | process/poll/send/runtime/E2E 分层状态；synthetic 与 outbox receipt |
| Model Safety | 软件测试通过不代表 Agent 输出可信 | Golden Task Set、能力评分、模型安全流水线和证据绑定 |
| Operator | 多套 status、复杂 runbook 会提高维护成本 | 只扩展现有 status；单命令 deploy/rollback/backup/restore/diagnose |
| Independent Skeptic | “世界最好”“7×24已证明”不可验证 | 用约束场景中的可测优势替代；7×24定义为运行模式与恢复机制，不靠等待证明 |

### 结论

当前设计在“单用户、微信入口、OVH 小资源、Private-MetaDatabase 权威、
24 小时实施且无真实时间 Soak”的约束下，已经将必要研究、普通决策、测试设计和激活准备前置。
剩余不可替代的人类动作仅为扫码、device auth 和最小权限凭据注入；它们不再阻塞其余开发。
