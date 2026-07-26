# 09 — 预授权决策、一次性激活输入与开发不中断规则

## 1. 目的

本文件把普通、可逆、低风险选择一次性授权给开发 Agent，避免开发中反复询问。任何未列出的普通实现细节由 Agent 按：

```text
安全 > 数据不丢 > 可回滚 > 复用固定本地源码 > 低资源 > 低复杂度 > 速度 > 美化
```

自行决定。

## 2. 技术默认值（已预授权）

| 领域 | 默认决策 | 允许的自动调整 | 禁止 |
|---|---|---|---|
| 架构 | 单OVH、全云、单用户、单active job | tiny/standard profile | Mac connector、多节点MVP |
| Runtime | Codex App Server loopback | 官方SDK adapter仅在现有RPC不可兼容时 | 公开8765、未鉴权远程Runtime |
| Node | 选择与固定 source bundle 兼容的最新官方LTS并锁定；最低满足Node 22+ | 若依赖不兼容，回退到验证通过的LTS/22.13+ | 无版本pin、随机升级 |
| SQLite | WAL + adapter；优先`node:sqlite`，不兼容则锁定轻量binding | driver可替换，SQL contract不变 | PostgreSQL/Redis用于MVP |
| Service | systemd + dedicated user + cgroup | 使用现有反向代理 | K8s、复杂Compose栈 |
| Web | 轻量只读Timeline/status/search | 固定本地静态站或最小server | 重型SPA重写 |
| Auth | Cloudflare Access Google/GitHub IdP | 复用现有Access policy | 自建密码/OAuth、伪造ChatGPT网页登录 |
| Channel | 现有WeChat iLink adapter | simulator、未来adapter fallback | 从零实现微信协议、非官方绕过风控 |
| Timeline | 复用固定本地 `timeline-for-agent` source bundle | 增加canonical source/search/status | 第二套Timeline内核、`#main`依赖 |
| Search | SQLite FTS5/静态index/过滤 | driver不支持FTS时使用倒排JSON小索引 | Elasticsearch/Meilisearch |
| Code Git | 本地branch/worktree/local CI；全部PG通过后一次性push/PR | 紧急修复仍不得绕过最终全量Gate | 中间phase push/PR/tag、force push历史 |
| Canonical Data | `private_db_client.py` 内容寻址 batch ingest | 压缩/分批/manifest reconcile | clone Private-Database、每token写入、覆盖旧event |
| Cold | R2 snapshot/object | S3-compatible simulator | R2热事务/锁 |
| Cold backup | OCI selected replica | activation_pending | 让OCI成为执行依赖 |
| Logs | journald + size cap + selected bundles | 调整cap适配host | 无限日志、原始prompt默认入日志 |
| Release | immutable release + current/previous symlink | 现有部署器可包裹该模型 | 原地覆盖、破坏性migration |
| Verification | fake clock + fault matrix + request-countCanary | 增加更多次数 | 真实时间Soak/观察Gate |
| Analytics | Cloudflare Web Analytics/匿名聚合 | 现有统计系统 | 记录私人消息/微信标识 |

## 3. 产品默认值（已预授权）

- 产品名：CyberBoss Cloud；
- 域名：`cyberboss.linzezhang.com`；
- 全局Status：`status.linzezhang.com`；
- 默认Runtime：Codex；
- Claude Code：安装/adapter可准备，flag=false；
- 用户：唯一授权微信ID；
- channel：文本；
- input上限：32 KiB，可配置；
- active job：1；
- queue：FIFO；
- `/bind`：alias only；
- mutation：受控worktree/branch/checkpoint；
- 默认不保存完整prompt/result到canonical；
- Timeline：任务/结果摘要/diary/check-in；
- status不显示微信ID、thread ID、绝对路径、私人文件名；
- 高风险不可逆操作仍需运行时明确批准；
- 普通开发操作不需要用户逐项批准。

## 4. 资源默认值（动态生成而非硬编码）

Preflight输出：

```text
RESOURCE_PROFILE=tiny | standard
MEMORY_HIGH_BYTES=
MEMORY_MAX_BYTES=
DISK_WARN_BYTES=
DISK_PROTECT_BYTES=
DISK_RECOVER_BYTES=
MAX_WORKSPACE_BYTES=
MAX_LOG_BYTES=
MAX_SNAPSHOT_BYTES=
```

### tiny

- 只运行一个bridge/runtime process family；
- Timeline按需build；
- Git/backup串行；
-只保留current+previous release；
- partial/sparse clone；
- mutation在保护阈值时拒绝；
-不安装Claude runtime依赖若会增加常驻资源。

### standard

- 同样单并发；
-允许更大cache/工作副本；
- Timeline可事件触发debounce；
-仍不增加Redis/Postgres/第二Runtime并发。

资源不足时Agent先缩小active working set，不询问用户。只有需要付费升级或拆Runtime时输出证据和默认建议。

## 5. 已锁定的仓库与数据边界

```text
代码/开发/部署仓：LinzeColin/MetaDatabase
代码子路径：CyberBoss/
历史来源输入：固定 SHA 的 CyberBoss + timeline-for-agent；导入后无持续关系
MVP workspace：alias=cyberboss，repo=LinzeColin/MetaDatabase，write=CyberBoss/**
唯一权威热数据仓：LinzeColin/Private-Database
权威数据根：Private-MetaDatabase (domain=CyberBoss)
数据协议：private_db_client.py ingest/get/list/verify；clone forbidden
Cloudflare R2 冷备前缀：cyberboss-cold/ovh-singapore-vps-1/
OCI 再备前缀：cyberboss-cold-backup/ovh-singapore-vps-1/
```

`Private-MetaDatabase` 只保存数据，不保存 CyberBoss 代码、systemd、部署脚本或运行程序。代码与数据不得互相污染。

## 6. 一次性激活变量

真实值不得写入任务包。开发准备以下secret slots：

```text
/etc/cyberboss/credentials/
├── github-code.token
├── cloudflare-access-api.token
├── cloudflare-dns-api.token
├── cloudflare-r2-api.token
├── cloudflare-account-id
├── cloudflare-zone-id
├── cloudflare-origin-hostname
├── cloudflare-access-owner-identity
├── cloudflare-access-status-service-token
├── r2-access-key-id
├── r2-secret-access-key
├── oci-config
├── oci-private-key
├── oci-bucket-name
├── cloudflare-access-scope.json
├── cloudflare-dns-scope.json
├── cloudflare-r2-scope.json
└── oci-object-scope.json
```

Private-Database 认证复用 dedicated service user 的 `gh` 登录态，不另造
`private-db.token`。三个 Cloudflare control-plane token 必须彼此分离；
scope attestation 只记录资源与权限声明，不含 token value。真实写前 adapter
要求 exact permission set、目标 account/zone/bucket/prefix，以及
`broad_account_write=false`、`unrelated_write_permissions=[]`。

Codex和WeChat凭据由各自官方/上游登录流程生成，不复制到env：

```text
/var/lib/cyberboss/.codex/auth.json
/var/lib/cyberboss/accounts/
```

建议activation env只含非secret引用：

```dotenv
CB_DOMAIN=cyberboss.linzezhang.com
CB_CODE_REPO=LinzeColin/MetaDatabase
CB_CODE_SUBPATH=CyberBoss
CB_DATA_REPO=LinzeColin/Private-Database
CB_DATA_AREA=Private-MetaDatabase
CB_DATA_DOMAIN=CyberBoss
CB_PRIVATE_DB_CLIENT=/opt/cyberboss-cloud/shared/private_db_client.py
CB_GITHUB_CODE_TOKEN_FILE=/etc/cyberboss/credentials/github-code.token
CB_PRIVATE_DB_AUTH_MODE=gh-login
CB_R2_ACCESS_KEY_FILE=/etc/cyberboss/credentials/r2-access-key-id
CB_R2_SECRET_KEY_FILE=/etc/cyberboss/credentials/r2-secret-access-key
CB_OCI_CONFIG_FILE=/etc/cyberboss/credentials/oci-config
CB_OCI_BUCKET_FILE=/etc/cyberboss/credentials/oci-bucket-name
CB_R2_BUCKET=cyberboss-cold
CB_R2_PREFIX=ovh-singapore-vps-1/
CB_OCI_PREFIX=cyberboss-cold-backup/ovh-singapore-vps-1/
CB_CHANNEL_PROVIDER=simulator
CB_RUNTIME_PROVIDER=simulator
```

### 6.1 P0.3 local capability observation

2026-07-26 的只读审计确认：

- designated Access token 可读 Access applications，不能读 R2/DNS；
- designated DNS tokens 可读目标 zone DNS，不能读 Access/R2；
- 现有 R2/D1 token 可同时读取 Access、R2、DNS，故其真实 mutation 被
  `hazard_blocked`，不能当作最小权限写凭据；
- OCI SDK 可读取 namespace 并列出一个现有 private bucket，但 task-pack 的
  `cyberboss-cold-backup/ovh-singapore-vps-1/` 是 object prefix，不得猜成
  bucket 名；
- provider token detail/IAM write scope 未能由只读 API 证明，所有真实写
  继续为 `activation_pending`，adapter/mocks 和下游无关任务继续。

以上记录不包含任何 token、account/zone/bucket 原名、OCID、PAR URL 或私钥。

### 6.2 P0.4 auth-state observation

2026-07-26 的 metadata-only probe 读取本机和同一获授权 OVH staging：

- 本机 `codex-cli 0.146.0-alpha.3.1` login status 为 authenticated，
  `auth.json` 是 owner-only `0600`；这不替代 OVH runtime；
- OVH key-only/strict-known-host 连接成功，但目标上 Codex CLI、
  `/var/lib/cyberboss/.codex/auth.json`、CyberBoss state directory 与 WeChat
  account state 均不存在；
- probe 没有读取 credential/session content、没有持久远端写入、没有真实
  QR/login/API call；
- OVH Codex/WeChat、AC-001 real 与 AC-010 real 均保持
  `activation_pending`，simulator 非激活验证已经完成，不阻塞 P0.5。

合并 activation/re-login 真源：
`docs/evidence/CB-030/auth-gates.md`。

真实激活后只切：

```dotenv
CB_CHANNEL_PROVIDER=weixin
CB_RUNTIME_PROVIDER=codex
```

## 7. 最终激活窗口只需用户完成的动作

1. 提供/打开OVH SSH；
2. 在OVH执行Codex device auth并浏览器确认；
3. 扫微信二维码一次；
4. 允许最小权限Private-Database/Cloudflare/R2/OCI凭据注入；
5. 允许DNS/Access最终切换。
6. PG-0–PG-5 全部通过后，允许 MetaDatabase 代码凭据执行唯一一次
   push/PR/CI/merge。

开发Agent必须把这些动作合并成一张可复制清单，不得分多轮打断。

## 8. 缺失输入的默认行为

| 缺失 | Agent行为 | 最终状态 |
|---|---|---|
| OVH | 完成repo-local实现、CI、systemd/deploy模板和host simulator | activation_pending:ovh |
| WeChat扫码 | 运行iLink simulator全部channel/fault测试 | activation_pending:wechat |
| Codex auth | 运行App Server simulator全部runtime测试 | activation_pending:codex |
| Private-Database dedicated service-user `gh` login | fake API object/manifest conflict/rate-limit/reconcile | activation_pending:private_db |
| GitHub code token | 保留已全量验证本地branch；禁止上传不完整phase | activation_pending:github_publish |
| Cloudflare token | local origin/Access policy tests + declarative activation commands | activation_pending:cloudflare |
| R2 token | object simulator、manifest/hash/restore | activation_pending:r2 |
| OCI token | OCI mock/replica contract | activation_pending:oci |
| 实际status私有实现 | 依公开页面/现有contract制作adapter fixture，部署时只读确认 | activation_pending:status_adapter |

任何一项缺失都不得产生`waiting_for_user`全局节点。

## 9. 仅需最小决策包的情况

只有以下不可逆/付费/法律情形可以询问用户：

- 必须升级或购买额外OVH/R2/OCI/GitHub资源；
- 必须删除无法恢复的数据；
- 必须公开新的网络端口/服务；
- 必须改变Private-MetaDatabase唯一权威热事实源原则；
- 必须改变AGPL网络提供方式；
- 微信账号出现封禁/风控；
- 必须使用第三方付费API而用户未授权。

格式固定：

```text
决策：<一句话>
证据：<最多3条>
默认建议：<一个>
不决策后果：<局部功能状态>
继续执行：<不受影响DAG节点>
```

禁止长篇泛问，禁止把整个开发线程挂起。

## 10. 安全预授权边界

Agent可以自动：

- 创建/additive migration；
- 本地 branch/worktree/local commit；
- 安装锁定依赖；
- systemd unit/drop-in；
-启动simulator/staging；
- fault injection；
-清理已验证可重建cache；
- rollback；
-生成R2/OCI mock；
-更新Status adapter；
-修改feature flag默认值（out-of-scope flag不得true）。

Agent不可以自动：

- 中间phase push/PR/tag；
- force push/改写代码历史或 canonical object/manifest；
- clone Private-Database；
-公开Codex/SSH/shell；
-输出/提交secret；
-删除唯一数据副本；
-开启多用户/多Runtime并发；
-购买资源；
-绕过微信风控；
-启用`CB_AUTONOMOUS_IRREVERSIBLE`；
-把simulator结果称为真实外部成功。

## 11. 开发完成状态

```text
verified            真实或不需要外部的Oracle通过
activation_pending  代码/模拟/部署准备完成，真实外部激活未完成
failed              真实或模拟contract失败
hazard_blocked       具体危险动作被安全阻止
out_of_scope         明确不属于MVP
```

不使用：

```text
waiting
waiting_for_credentials
waiting_for_soak
observe_for_7_days
observe_for_30_days
```
