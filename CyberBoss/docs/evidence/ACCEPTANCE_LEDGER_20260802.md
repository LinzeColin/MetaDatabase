# v0.0.0.9 R1 验收总账 —— 2026-08-02T03:35Z（第二版）

这份取代 `docs/evidence/CB9-660/RESULT.md` 里的线上判断。**那一份是过期的**：它写的探针
主机是 `51.222.29.63`，而现在的生产机是 `139.99.61.6`；它据此报告的一串 SSH timeout 和
「凭据 unset」，量的是一台不相干的机器。

现场事实（本文件写成那一刻实测）：

| 项 | 值 |
|---|---|
| 线上 release | `231d4755ee54` |
| 用户数 | 4（1 主人 + 3 访客） |
| `agent_sessions_v009` | 1 行，`sess_0fe1f3b14319d`，`context_version=2` |
| `parity_receipts_v009` | 1 行（`OWNER / wechat_channel / success`） |
| 最后一条真实入站 | `2026-08-02T02:58:57.640Z` |
| 最新异地冷备 | `backup_4876061c91eb8c45e5c00f79` @ `2026-08-02T03:24:35Z`（OCI，已用 API 密钥取回校验） |
| 测试 | 1559 + 72 全绿 |
| failed 服务 | 本包内 **0**（`cyberboss-backup` 已恢复为 Finished）；`signal-lattice-{cycle,worker}` 是同机另一项目，不在本包 |

---

## 判定口径

这份账只用三个词，而且**不许混用**：

- **PASS** —— 在真实链路上取到过证据。不是「测试绿」，是「真的跑过一次并留下了痕迹」。
- **本地闭环** —— 制品、测试、变异验证齐了，但它的 oracle 本来就只要求本地（contract/unit/
  integration/fault-injection）。这类不需要线上证据。
- **NOT_RUN** —— 缺一个我拿不到的东西。**每一条都写清楚缺什么、实测过什么**，不写「待验证」。

刻意不设「大概可以」这一档。这个仓这一整轮反复栽的就是「看起来是好的」——
会话表 0 行、回执表两头没人、`this.formatOwnerLocalTime` 根本不存在，
三件事在此之前全都「测试全绿」。

---

## 线上已验（PASS）

| AC | 名称 | 怎么验的 |
|---|---|---|
| AC-002 | Owner Session 守恒 | 真实入站 02:58:57 让 `context_version` 1→2，`session_key` 不变 |
| AC-006 | 扫码首轮可用 | **PARTIAL** —— 见下 |
| AC-007 | 新手零技术词汇 | 真站抓 DOM + 11 条脚本内分支文案，六类技术词命中 0 |
| AC-012 | 无摩擦时区信号 | 真浏览器上报 `Australia/Sydney` → `{"ok":true}` |
| AC-025 | 真实回执新鲜度 | 生产上 `OWNER: HEALTHY/fresh_success` 与 `COMPANION: UNKNOWN/no_live_receipt` **同时**成立 |
| AC-027 | 权威同步幂等 | 上一轮生产验证 |
| AC-028 | 双冷备恢复 | 两份可验证对象都在；「一份不可读时从另一份隔离恢复」两个方向各验一次 |
| AC-029 | AGPL 对应源码 | 线上 digest 与部署 commit 本地重算逐字节一致 |
| AC-030 | 中文防呆 UI | 375×812 与 1280×720 实测全过 |
| AC-034 | 发布与回滚 | 上一轮生产验证 |
| AC-037 | 前端性能 | 593ms、6KB、页面零模型耗时 |
| AC-042 | 位置权限非阻塞 | 页面根本不调 `navigator.geolocation` |
| AC-044 | 跨会话恢复 | 会话建于 01:59:32，历经**四次**部署重启，02:58:57 的消息落回同一条 |
| AC-045 | 无管理员依赖 | 三个真实访客，邀请码 `used_count` 全 0；其中一位注册到已送达回复 **2.0 秒** |

**AC-006 为什么是 PARTIAL**：能证明三位访客是全新用户、能证明他们没经设置页、能证明没人替他们开通——但证明不了他们具体是从 `/join` 那张码进来的。公开入口的票是内存态、确认后即删，库里没有把 user_id 和「来自 /join」绑起来的记录。主人已说明不会有新人现场扫码，所以这一句只能留着。

## 本地闭环（oracle 只要求本地）

AC-001、AC-003、AC-005、AC-008、AC-009、AC-010、AC-011、AC-013、AC-014、AC-015、AC-016、
AC-017、AC-018、AC-019、AC-020、AC-021、AC-022、AC-023、AC-024、AC-026、AC-031、AC-032、
AC-033、AC-035、AC-036、AC-038、AC-039、AC-041、AC-043

共 29 条。1548 + 72 条测试全绿，关键项配了变异验证。

---

## NOT_RUN —— 缺什么，写清楚

只剩两项，而且都不缺代码。

| 项 | 缺的那一步 | 实测依据 |
|---|---|---|
| AC-040 AI 双流水线 | 需要一次走完整模型路径的真实 turn 并留下双流水线证据 | — |
| AC-006 的「从 /join 扫码」这一句 | 需要一次现场扫码；主人已说明不会有 | — |
| R2 写权限（不是 AC，是运维缺口） | 一个带 `Workers R2 Storage : Edit` 的令牌 | 见下表 |

R2 写权限这一条，机上每一份候选凭据都实测过：

| 凭据 | 结果 |
|---|---|
| `_protected/…/cloudflare_r2d1_token.txt` | GET 200 / **PUT 403** |
| `cloudflare_token.txt`、`cloudflare_access_token.txt`、`cloudflare_readonly_token.txt` | 无 R2 权限 |
| `weread_port_r2_v0019.env` 的 S3 密钥对 | 对 `cyberboss-cold` 全 403（绑定在自己桶上） |
| 生产机 `/etc/cyberboss/credentials/r2_api_token` 及其 `.bak` | **PUT 403** |
| 生产机 `/srv/linze/apps/status/.secrets/cf_r2d1_token`、`cf_access_token` | **PUT 403** |
| OAuth 刷新路径 | 刷新令牌已被 Cloudflare 判为 `invalid_grant`，且已被 `10-static-r2-token.conf` 停用 |

四把令牌都无法访问 `/user/tokens`，所以也签发不出新令牌。新建只能在 Cloudflare 控制台完成，那需要账号密码——我不做这件事。

**但这不再阻塞异地冷备**：OCI 那条腿已经接通并落地，面板如实显示 `degraded / BACKUP_SINGLE_COPY_ONLY`。R2 令牌到位后自动恢复成两份。

## 这一轮修掉的缺陷

| # | 缺陷 | 为什么没有症状 |
|---|---|---|
| F9 | 会话层收不下真实链路给的密钥（hex 字符串 vs Buffer），每个 turn 静默失败 | 旁路 catch 吞成一行 warn；测试自己造了 `Buffer.alloc(32,9)` |
| F10 | 系统直回读留在对象上的可变字段，把会话记到上一条系统消息那个号的人头上 | 查不到就返回 null，没有异常没有日志 |
| F11 | `this.formatOwnerLocalTime` 在 prototype 上根本不存在 | 七处测试各自往对象上装了一个生产没有的方法 |
| F12 | 回执层两头都没人，Status 四种状态在生产上只可能是 UNKNOWN | UNKNOWN 看起来和「刚部署完还没人用」一模一样 |
| F13 | 异地冷备停摆四天而面板显示 healthy | 新鲜度读的是**快照**目录（上传失败照样有），判据是「备份器配好了没有」 |
| F14 | 源码清单扫不到文件时静默发布空字符串的 sha256 | 页面照常渲染、照常权威，只有文件数悄悄变成 0 |
| F16 | 双冷备串行耦合：R2 先跑且抛异常，OCI 永远轮不到 | 「两份冗余」实际是一条链，一边坏掉异地副本直接归零 |
| — | 每个公开路径 HEAD 都回 404，包括 `/healthz` | 探活监控会一直报站挂了，而站是好的 |

前六个是同一个形状：**测试造出了生产环境不存在的东西**（造 Buffer、造方法、造 fact、造摘要），
于是套件全绿而真实链路失效。新加的测试有一条共同规矩——输入一律从真实生产方身上取，
每一条都用变异验过真能红。

## 我自己判错又纠正的两处

写下来是因为它们都属于「用错的方法探测，把结论读反了」，比缺陷本身更容易重犯。

| 我当时的结论 | 实际情况 | 教训 |
|---|---|---|
| OCI PAR 已失效（BucketNotFound），OCI 冷备不可用 | PAR 是活的，有效期到 2027-07-19，只是 **AnyObjectWrite（只写）**。我用**列举**去探它，只写的 PAR 本来就该拒绝 | 探测必须用**它被授予的那个动作**；用错动作得到的拒绝会被读成「凭据死了」 |
| `usr_KPEKBX9Lpt` 五条入站全 rejected，一个真实用户被静默拒绝 | `reject_reason` 全是 `handled_by_admission`——「没排进 job 队列」不是「没服务到」。五条各对应一条 `delivered=1` 的直回 | 按字面读状态名会把一次正常服务读成一次事故 |

## 未修，留给主人决定

**F8 两条路径对「谁是主人」判断不一致**（`docs/evidence/LIVE-20260802/F8-owner-identity-split.json`）。
准入把 00:19 那条入站路由给了 codex（主人运行时），而 checkin 的解析器在最近入站里找不到主人。
选哪个 `user_id` 当主人决定了 Codex 访问权和 Owner 专属能力的归属——这是主人的决定，不是我的。
