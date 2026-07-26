# 07 — 公开研究、竞品反向研究与可复用结论

> 研究快照：2026-07-26。开发开始时必须记录精确 commit SHA；本文件给出
> 历史来源结论，不用模糊记忆替代 pinned source。Owner 已决定只做一次性
> 固定 source import；研究链接不构成持续 upstream remote、自动同步或支持关系。

## 1. 结论先行

最短、风险最低的路线不是换框架，而是：

```text
保留 CyberBoss：微信 iLink + Runtime adapter + command surface + Timeline
补齐：durable inbox/outbox、cursor ordering、idempotency、singleton、canonical sync、status、backup/recovery
云端化：OVH + loopback Codex + systemd + Cloudflare Access
分层：Private-MetaDatabase canonical / SQLite spool / R2 cold / OCI replica
```

原因：CyberBoss 已经把微信、Codex/Claude、提醒、日记、随机 check-in 和 `timeline-for-agent` 组合在一起。迁移到成熟大框架会重新承担微信登录、命令兼容、Timeline、隐私和资源成本，却不能自动解决当前最关键的 crash consistency 和出站幂等。

## 2. 上游 CyberBoss 核验

### 2.1 可直接复用

公开 README 与源码显示：

- Node.js `>=22`；
- 微信 HTTP 长轮询、出站回复、文件与状态转换；
- Codex 和 Claude Code 可插拔 Runtime；
- `CYBERBOSS_CODEX_ENDPOINT=ws://127.0.0.1:8765` 可复用已有 App Server；
- `/status`、`/stop`、`/bind`、`/model`、`/checkin` 等命令；
- `timeline-for-agent` 已集成，工具包括 timeline write/build/serve/dev/screenshot；
- 当前默认状态在 `${HOME}/.cyberboss`；
- AGPL-3.0-only，网络提供修改版时必须提供对应源。

直接复用：

- `src/adapters/channel/weixin/`；
- `src/adapters/runtime/codex/`；
- `src/core/app.js` 的命令/线程/审批框架；
- `src/integrations/timeline/`；
- `scripts/shared-start.js` 的共享Runtime概念；
- 现有 test 中 Codex reconnect/RPC/approval、stream delivery、system inbound、Timeline tests。

### 2.2 必须修复

源码 `src/adapters/channel/weixin/index.js` 的当前 poll 流程会在上层 durable 处理前保存新的 sync buffer。若进程在“sync buffer 已持久化、消息尚未可靠进入 job”之间崩溃，存在静默丢失窗口。

目标修复：

```text
provider getupdates
→ normalize messages + candidate cursor（不提交）
→ SQLite transaction: inbox/job/event
→ commit transaction
→ commit candidate cursor
→ durable accepted outbox
```

其他缺口：

- 当前本地/in-memory queue 不能承担重启恢复；
- sendmessage 需要统一 durable outbox 和 unknown-outcome语义；
- `/bind /absolute/path` 需要改成 alias allowlist；
- shared-start需要systemd/cgroup/singleton强化；
- local state需要明确Private-MetaDatabase canonical、R2/OCI和隐私边界；
- process alive不能代表poll/send/Runtime/E2E健康。

### 2.3 Timeline事实

CyberBoss README明确说明它构建于 `timeline-for-agent` 之上，并已暴露Timeline工具；源码树包含 `src/integrations/timeline`，test目录包含Timeline integration/service tests。因此：

- 不新造Timeline内核；
- 只改数据来源、云端build、静态发布、搜索、Access和Status摘要；
- Runtime cache可删除重建；canonical source通过免 clone client 进入
  Private-MetaDatabase。

## 3. OpenAI Codex官方边界

### 3.1 App Server

官方App Server面向自定义客户端；本项目保留现有JSON-RPC adapter。WebSocket只在同机loopback使用：

```text
ws://127.0.0.1:8765
```

不得：

- `0.0.0.0:8765`；
- Cloudflare Tunnel转发；
- 公网裸WebSocket；
- 无TLS/鉴权远程连接。

官方文档对非本地连接要求TLS和鉴权；当前项目没有任何远程Runtime需求，公开端口只增加风险。

### 3.2 Headless Auth

无浏览器服务器使用：

```bash
codex login --device-auth
```

`~/.codex/auth.json` 视同密码：0600、不打印、不进Git、不进普通R2备份。若auth未激活，开发使用App Server simulator继续，最终真实Codex E2E保持`activation_pending`。

### 3.3 Overload/Retry

App Server可出现有界队列/overloaded错误。Runtime adapter必须分类：

- retryable overload/network；
- auth invalid；
- cancelled；
- terminal tool/model error；
- unknown outcome。

重试必须有上限并用fake clock验证，不能在测试中真实等待。

## 4. 竞品与相邻系统矩阵

| 项目 | 成熟优势 | 本项目借鉴 | 不直接采用 | 约束场景中的超越目标 |
|---|---|---|---|---|
| CyberBoss | 微信+Codex/Claude+Timeline+主动监督已整合 | 原channel/runtime/command/timeline | 原本地可靠性和部署方式 | 全云、幂等、可恢复、status/canonical |
| timeline-for-agent | 轻量结构化Timeline、静态build | 数据模型、工具、站点 | 第二套Timeline | 与job/canonical/Status同源 |
| Wechaty | channel/puppet抽象、多平台生命周期 | adapter contract、provider可替换 | 迁移现有iLink、增加登录风险 | 保持现有微信兼容同时允许未来fallback |
| AstrBot | 多IM、插件、Agent/MCP生态 | feature-flag、plugin边界 | 多平台全栈和额外常驻组件 | 更窄、更低资源、更强一致性证据 |
| OpenHands | runtime抽象、事件流、sandbox/backends | runtime supervisor、事件状态 | 重型平台、超出小VPS | 单用户微信场景更轻、更易恢复 |
| SWE-agent | 配置驱动、真实repo eval、可复现 | Golden Task Set、artifact oracle | 作为长期控制面 | 微信/Timeline/7×24运维是一等公民 |
| n8n | 工作流DAG、凭据隔离、重试 | 节点式DAG和credential boundary | 常驻workflow平台、重复控制面 | 专用链路更少组件、低内存 |
| ActivityWatch | 本地优先、事件Timeline、隐私 | event bucket/retention思想 | 第二套行为采集系统 | 只记录必要任务事件，隐私面更窄 |
| Uptime Kuma | 多探针、状态页、通知 | probe分类 | 用户已有status系统 | 不新增监控栈，直接融入全局status |
| Gatus | 轻量声明式健康条件 | assertion-style health/ready | 单独部署 | 内置contract test和status adapter |
| GitHub Actions | 代码 CI、并发控制、审计 | 最终发布流水线、release gate | 实时Runtime/queue/业务数据 | code release 与 canonical object evidence 可追溯关联 |
| Cloudflare Access | Zero Trust人类入口 | Google/GitHub IdP、service token | 自建登录 | 最少认证代码和攻击面 |
| Cloudflare R2 | 对象存储、lifecycle、低egress复杂度 | 冷快照/日志/未来附件 | 热事务/锁 | 与Private-MetaDatabase canonical边界明确 |
| OCI Object Storage | retention/replication/lifecycle | 异地冷备和恢复清单 | 热路径 | 不增加执行依赖，仅做灾备 |

## 5. Private-MetaDatabase 作为权威长期事实源的工程约束

`private_db_client.py` 与底层 provider 限制意味着不能每个 token/进度都写入：

- 禁止 clone Private-Database；
- 单 client object 必须小于 95 MiB，大对象应压缩/分片或进入 R2；
- authenticated API和content-generating requests有速率约束；
- 403/429必须尊重provider提示和退避。

设计结果：

- canonical event按记录数/字节批量；
- 终态/高风险receipt可显式flush；
- deterministic NDJSON/Markdown 压缩批次；
- event ID稳定且 manifest 409 后 refetch/retry/set verify；
- prompt原文、日志、未压缩活库、附件不进 Private-MetaDatabase；
- R2对象只在 Private-MetaDatabase 保存manifest/hash/index；
- code workspace 可用 sparse checkout；Private-Database 本身禁止 clone；
- Private-Database client 与 code repo 使用不同最小权限身份。

## 6. Cloudflare/OCI可复用能力

### R2

- lifecycle rules用于对象过期/分层；
- multipart未完成对象应有清理策略；
- hash/manifest先校验再删除OVH本地副本；
- 真实R2凭据缺失时用S3-compatible simulator/local object fixture，不阻塞开发。

### OCI

- retention/lifecycle/replication是冷备能力，不进入执行关键路径；
- versioning、retention和replication组合需按当前官方约束验证；
- MVP允许`activation_pending`，但adapter、manifest、mock和恢复路径必须完成。

## 7. Node/SQLite选择

Node 22+已具备内建`node:sqlite`能力，但不同Node版本的稳定级别和API状态需在pinned版本核验。因此：

- 通过`DatabaseAdapter`隔离driver；
- 目标环境支持时优先`node:sqlite`，减少native addon；
- 不满足时使用锁定版本的轻量SQLite binding；
- SQL schema、WAL、事务、backup和test不绑定driver；
- 不因driver选择询问用户。

## 8. 模仿但不复制的设计模式

1. **Adapter boundary：** channel/runtime/storage/status均可替换；
2. **Event envelope：**稳定ID、correlation、schema version、hash；
3. **Durable outbox：**执行成功≠用户已收到；
4. **Provider simulator：**外部凭据不阻塞开发；
5. **Predicate health：**不靠固定sleep；
6. **Request-count Canary：**按风险和请求推进；
7. **Append-only canonical：**冲突合并、不覆盖历史；
8. **Least privilege：**code/data/R2/OCI身份分离；
9. **Cold offload：**OVH只保留活跃工作集；
10. **Artifact Oracle：**模型文字不构成完成证据。

## 9. 反证：何时应放弃当前路线

- 上游微信iLink真实账号明确不可用且无合规替代；
- App Server协议无法在adapter层兼容；
- tiny profile仍不能让单一Codex Runtime与既有关键服务共存；
- 用户不能履行AGPL对应源义务却要对网络用户提供；
- 同一约束下成熟项目能以更少组件满足全部P0 Acceptance。

此时只否决相应channel/runtime/部署路线，保留durable queue、canonical、Timeline、Status和恢复层，不推倒全部成果。

## 10. 研究来源

### 上游与竞品

- https://github.com/WenXiaoWendy/cyberboss
- https://github.com/WenXiaoWendy/timeline-for-agent
- https://github.com/wechaty/wechaty
- https://github.com/AstrBotDevs/AstrBot
- https://github.com/All-Hands-AI/OpenHands
- https://github.com/SWE-agent/SWE-agent
- https://github.com/n8n-io/n8n
- https://github.com/ActivityWatch/activitywatch
- https://github.com/louislam/uptime-kuma
- https://github.com/TwiN/gatus

### 官方工程文档

- https://developers.openai.com/codex/app-server
- https://developers.openai.com/codex/auth
- https://developers.openai.com/codex/cli
- https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm
- https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm
- https://nodejs.org/api/sqlite.html
