# CyberBoss

CyberBoss 是 `LinzeColin/MetaDatabase` 内的全云微信驱动子项目：Owner 独占
Codex Workspace，普通用户通过同一个微信 Bot 以自带 Provider 密钥（BYOK）使用
相互隔离的个人服务。

## 当前状态

- 生命周期：Stage 0–5 与独立退出门 PG-0–PG-5 已通过（单用户全云底座）。
  Owner Change Event `owner-change-cyberboss-v0.0.0.8-multiuser-weixin` 已把产品
  推进到 `v0.0.0.8` 多用户范围，追加 Stage 6–8 与 PG-6–PG-8；Stage 0–5 不重做、
  不降级，其单用户 PASS 也不被继承为多用户 PASS。
- Owner 锁定的产品版本：`v0.0.0.8`；TaskPack 版本 `v0.0.0.8`（R7-FINAL）；
  设计基线保持 `v0.0.0.4`。开发 Agent 无版本决定权，本 Run 未改变版本或验收集。
- 已完成 Run：`PS0.1`；`P0.1 / CB-000`；`P0.2 / CB-010`；
  `P0.3 / CB-020`；`P0.4 / CB-030`；`P0.5 / CB-040`；
  `P1.1 / CB-100`；`P1.2 / CB-110`；`P1.3 / CB-120`；
  `P1.4 / CB-130`；`P1.5 / CB-140`；`PG-1`；`P2.1 / CB-200`；
  `P2.2 / CB-210`；`P2.3 / CB-220`；`P2.4 / CB-230`；`P2.5 / CB-240`；
  `P3.1 / CB-300`；`P3.2 / CB-310`；`P3.3 / CB-320`；`P3.4 / CB-330`；
  `P3.5 / CB-340`；`PG-3`；`P4.1 / CB-400`；`P4.2 / CB-410`；`P4.3 / CB-420`；
  `P4.4 / CB-430`；`P4.5 / CB-440`；`PG-4`；`P5.1 / CB-500`；`P5.2 / CB-510`；
  `P5.3 / CB-520`；`P5.4 / CB-530`；`P5.5 / CB-540`；`PG-5`；`P6.1 / CB-600`；
  `P6.2 / CB-610`；`P6.3 / CB-620`；
  `P6.4 / CB-630`；`P6.5 / CB-640`；`PG-6`；
  `P7.1 / CB-700`；`P7.2 / CB-710`；
  `P7.3 / CB-720`；`P7.4 / CB-730`；
  `P7.5 / CB-740`；`PG-7`；`P8.1 / CB-800`；`P8.2 / CB-810`；`P8.3 / CB-820`；
  `P8.4 / CB-830`
- 当前基线：不可变 release `fd3cd1e19d70caa148c3785288aaabfb909fed85` 已在
  Linux systemd、专用 Cloudflare Tunnel 与 Owner-only Access 后真实运行；已验证的
  immutable `previous` `25670bf32c6d27e3668fcf59bc9ab754035e161d` 已保留，
  并保留既有 `current → previous → current` 回滚收据。CB-600 未改变 release 指针。
- 最新 Run：`CB-830`。干净安装契约、请求数 Canary、回滚与 Owner 单命令生命周期。
  Canary 只看请求数不看时间：oracle 里没有任何计时调用，唯一一次取时间是决策做完之后
  盖收据；样本不够时给的是"还差几个请求"而不是"再等几分钟"，同一样本重算结果完全一致。
  错误率、p95、1 次隐私违规、1 次重复副作用、任一未测量字段、错误数大于请求数、阈值非法
  ——全部立即回滚；1 次隐私违规既压过一万请求的完美样本，也压过"请求数不够先等等"，
  不会被等过去。回滚点名精确的上一个 release，回滚两次也不会再往前走一格。
  运维面：9 个动作文档与实现完全一致（文档里有、配置里没有 → 直接失败），全部绝对路径
  可执行文件 + `shell:false` + 每动作独立超时；环境不继承（恶意 `PATH`/`LD_PRELOAD`/
  `NODE_OPTIONS`/`HOME` 全丢弃，放行的 3 个变量带控制字符也是丢弃而不是就地清洗）；
  超时的动作会被 SIGTERM 停掉并只给一条修复建议，不做重试循环。root 属主守卫用真实
  文件对象跑通：属主不符/组可写/软链接配置/相对路径/传目录各自拒绝，属主匹配时通过
  ——证明它在检查属主而不是一律失败。
  **`CB-830` = `CONDITIONAL_PASS`**：`AC-036` 无条件通过；`AC-040`/`AC-050` 除需要
  授权目标机的部分外全部通过；**`AC-039` 整项记为 `activation_pending`，不给任何部分
  分**——没有授权微信凭据，而"消息通路的结构性证明"不等于"两个真实用户真的注册了"。
  证据在 `docs/evidence/CB-830/`。
- 上一 Run：`CB-820`。安全、隐私、模型边界、供应链与故障注入闭环——不加任何新功能，
  只把安全性质端到端重证一遍。普通用户扫过全部 11 个 Owner-only 能力：授予 `0` 次、
  拒绝 11 次（含 Codex / Workspace / Shell / 工具面）；暂停用户在两套能力上都拿不到
  任何东西；客户端自称 owner 不作数。保险箱：每用户 32 字节随机 DEK（两次包装密文
  不同，证明是随机而非派生），AES-256-GCM + master KEK，AAD 绑定用户域（换用户或换
  master key 都解不开），Provider 子密钥按 provider 与 key version 派生（换任一个都
  读不了），明文只留后 4 位；写入凭据后直接读数据库文件与 WAL 原始字节，`0` 处明文。
  敏感属性：默认推断数 `0`，0.01–1 全区间推断一律拒绝，跨类目同意不解锁。
  冻结故障矩阵按 sha256 逐字节复放 7 个用例，全程假时钟、真实等待 `0`；畸形输出永远
  不算成功，导入文本始终是惰性数据（导入层没有任何通往 Provider 适配器的路径）。
  供应链：3 个来源全部钉死 40 位 commit、改动有记录、无残留 fetch remote、运行期
  拉取上游 `0` 处；凭据形态扫描覆盖整棵树，出货侧 `0`，测试侧全部是登记在册的合成
  向量。**已发现并如实记录一处真实许可证不一致**：`whereabouts-mcp` 的 package 元数据
  声明 AGPL-3.0-only，实际随附 LICENSE 是 GPL-3.0-only；本节点直接读了 vendored 文件
  确认 lock 记录准确，合规表达式按更严的 `GPL-3.0-only AND AGPL-3.0-only` 执行。
  **`CB-820` = `PASS`**（无条件）：`AC-006`/`AC-012`/`AC-026`/`AC-038` 全部通过，
  无 `activation_pending`。证据在 `docs/evidence/CB-820/`。
- 上一 Run：`CB-810`。Status 业务矩阵、资源闸门与 Zero-Agent 自愈。14 条冻结业务线
  ×14 个必填字段：少一条线、多一条线、少一个字段、多一个字段都整份拒绝，绝不"悄悄少
  一行照样发布"。字段名和字段值都按深度 8 递归扫描：冻结禁字段、嵌在值里的禁字段，
  以及以合法字段名承载的微信 id、用户 id、邮箱、Bearer、Provider key、私钥头、macOS
  路径，全部拒绝；拒绝信息只报字段路径不报值。用量摘要严格按冻结的 9 个聚合字段
  白名单输出，per-user 维度在聚合内部就被丢弃（不是事后过滤），未知 Provider/熔断
  状态/预算状态与自由文本 reason 一律拒绝。资源闸门、自愈策略与 Zero-Agent 台账三个
  模块零 import，任何路径 `modelCalls` 都是 `0`；未测量的下限按拒绝处理，硬下限先于
  压力信号上报，重启预算滑窗内耗尽即停并告警，冷却期内的重启是延后而不是放大，
  时钟前跳买不到额外重启，不可重启的故障隔离而非重启；11 个必须为 0 的计数器少报
  即失败（未上报 ≠ 0）。No-Mac 扫描覆盖整个运行时树：依赖点 `0`，禁令点 `24`。
  **`CB-810` = `PASS`**（无条件）：`AC-032`/`AC-033`/`AC-034`/`AC-048` 全部通过，
  无 `activation_pending`。证据在 `docs/evidence/CB-810/`。
- 上一 Run：`CB-800`。数据边界、备份与用户生命周期闭环，全部叠加在既有实现之上，
  没有第二个事实源、第二套备份运行时或第二个数据库：既有 canonical spool 仍是唯一
  长期事实权威，新 envelope 只做校验，自身不开表、不开文件、不开连接。六个冻结禁字段
  在任意深度、作为更长字段名的子串、以及仅凭字段值命中密钥模式时都被拒绝，拒绝信息
  只报字段路径不报字段值；普通事实走日频、五类重大事件即时、无新事实不空提交。
  备份必须两份都落盘才发收据，完整性在解密之前校验（损坏对象根本不进密码学路径），
  恢复只进隔离目录并校验关系；第一份不可读时第二份可独立完成恢复，降级状态如实上报。
  导出只含自己的行（查询里限定、装配后再验一次），钱包类材料（wrapped DEK、凭据密文）
  永不进导出；删除按冻结九步执行，先断访问再动数据，收据只增不改，中断后可续跑且
  crypto-shred 两次尝试合计只执行一次，Tombstone 不带原始用户 id。
  **`CB-800` = `CONDITIONAL_PASS`**：`AC-029`/`AC-030`/`AC-035` 全部通过，但真实 R2、
  真实 OCI 与真实 Private-Database 端点无授权凭据，记为 `activation_pending`，
  未按 PASS 折算。证据在 `docs/evidence/CB-800/`。
- 上一 Run：`CB-740` / `PG-7`。Timeline、日记、提醒全部经服务端 user scope 包装
  （不 fork 既有服务）：跨用户读为空、跨用户删除无效、暂停用户失去入口、无
  context 或伪造 context 一律拒绝；主动关心模块零依赖，任何路径模型调用都是 `0`，
  按小时扫一整周，关闭状态下主动消息数为 `0`。
  **`PG-7` = `CONDITIONAL_PASS`**：`AC-028`/`AC-031`/`AC-043` 通过，但仍带着三项
  `activation_pending`（真实双用户微信、真实 BYOK 凭据、冻结浏览器 harness），
  未按无条件 PASS 折算。证据在 `docs/evidence/CB-740/` 与 `docs/evidence/PG-7/`。
- 最新 Run：`CB-730` 已完成中文防呆入口与一次性设置页：自然中文意图靠冻结
  查表解析（模型调用 `0`），运维措辞一律不解析；页面在真实 Chromium 的
  375×812 与 1280×720 下实测：无横向溢出、可见控件全部 ≥44px、每屏一个主操作、
  正文 16px、对比度 8.02–17.76（要求 4.5）、Tab 顺序与视觉一致、inline style 为 `0`。
  一次性 token 走 URL fragment 并立刻从地址栏移除。冻结的 Playwright 浏览器
  harness 因本机没有 Playwright/Chromium 而 `not_run`，已如实记录，未冒充其结果。
  证据在 `docs/evidence/CB-730/`。
- 最新 Run：`CB-720` 已落地可解释画像与确定性行为分析：每条推断必须带来源、
  证据、置信度与反证（缺一即拒），9 类敏感属性在任何置信度下都不可推断且同意
  按类精确匹配，默认敏感推断数为 `0`；接受/修改/拒绝/冻结/删除与其效果在同一
  事务内生效，被拒绝的推断不会复活，冻结不会被隐式解除；日聚合模块零依赖、
  与输入顺序无关，且是可重建的投影而非第二事实源。证据在 `docs/evidence/CB-720/`。
- 最新 Run：`CB-710` 已完成上传安全与四源导入：路径穿越（4 种写法）、符号链接、
  加密条目、不支持算法、可执行/脚本/嵌套压缩包、超深路径、重复归一目标、
  超大与两种压缩炸弹全部在解压前被拒，解压后再校验 CRC 与长度；ChatGPT/Claude
  为 `stable`，Gemini/DeepSeek 只标 `beta`/`beta_low_confidence`，未知结构不冒充完整；
  同文件重复上传不产生重复事实，断点可续传，单条损坏记录被隔离而不影响其余。
  冻结攻击矩阵 7/7 重放通过。证据在 `docs/evidence/CB-710/`。
- 最新 Run：`CB-700` 已落地 BYOK 密钥保险箱（master KEK 包装每用户 DEK，再派生
  Provider 子密钥；跨用户/跨 Provider 解密与错误 master key 均被拒；crypto-shred
  只毁该用户）、四 Provider 固定官方 endpoint 与 allowlist、Token 预授权硬预算
  （BEGIN IMMEDIATE 单事务；超预算时 Provider 调用数为 `0`）、用量归一与崩溃保守
  记账、用户级/全局双作用域熔断与单个半开探针（有界 lease）。后台模型调用为 `0`。
  真实 BYOK 凭据不在授权范围内，保持 `activation_pending`，留待 `CB-830` 真实激活。
  证据在 `docs/evidence/CB-700/`。
- 最新 Run：`CB-640` / `PG-6` 已按冻结 blind set 逐条重放双用户隔离：8/8
  用例通过，跨用户读/搜索/改/删、setup token 复用、Owner 能力越权、暂停用户
  模型调用、回复目标掉包全部被拒；证据内无任何个人数据。
  **`PG-6` = `CONDITIONAL_PASS`**：`AC-003`/`AC-007` 通过，`AC-039`（两个真实
  微信发送者）因授权范围内没有真实微信凭据，保持 `activation_pending`，
  未按 PASS 折算，也未用 simulator 冒充真实通道，留待 `CB-830` 复测。
  证据在 `docs/evidence/CB-640/` 与 `docs/evidence/PG-6/`。
- 上一 Run：`CB-630` 已把服务端 UserContext 注入可信入口，11 项 Owner-only
  能力与普通用户能力互斥、scoped 仓库、公平队列、幂等与回复目标不可变绑定
  全部落地。证据在 `docs/evidence/CB-630/`。
- 更早 Run：`CB-620` 已完成邀请制注册、同意激活、10 分钟一次性设置链接与
  Secure/HttpOnly/SameSite=Strict Web Session，门户 fail-closed。
  证据在 `docs/evidence/CB-620/`。
- 更早 Run：`CB-610` 已按目标现有迁移约定物化 `006_multiuser_foundation.sql`
  （动态编号，非固定前缀），完成 Owner 回填与 valid-user 触发器，并新增服务端
  派生身份、用户仓与邀请码仓。证据在 `docs/evidence/CB-610/`。
- 更早 Run：`CB-600` 已完成 exact Subject 绑定（HEAD
  `bb716bd9cf2760aa9639ef85c626f0fd19c6ec94`、tree
  `a6426566cdba7dce4d1990eb888d308838b26ef1`、干净工作树）、只读 Current Truth
  对账（consensus=consistent）、v0.0.0.8 版本锁、单条 Owner Change Event，以及
  18 个必需域的目标兼容映射（唯一 ambiguous 域 `profile_analytics` 已解析）。
  证据在 `docs/evidence/CB-600/`。
- 真实 WeChat credential 不在已授权受保护范围内：channel/bridge 故意保持
  `pending_missing_real_wechat_credential` 和 `/readyz=503`，没有启动 simulator
  或把 pending 写成 ready。最小 Access service-token scope 同样保留 pending，
  不影响 Owner-only 登录或同机受保护 Status snapshot。
- 任务状态：`CB-000`–`CB-540` 与 `PG-0`–`PG-5` 已通过（单用户范围）；
  v0.0.0.8 追加的 `CB-600`–`CB-640`（Stage 6 全部 5 项）、`CB-700`–`CB-740`（Stage 7 全部 5 项）
  与 `CB-800`、`CB-810`、`CB-820`、`CB-830`（Stage 8 前 4 项）已通过；
  `PG-6` 与 `PG-7` 均为 `CONDITIONAL_PASS`。

- 尚未开始：`CB-840` 与 `PG-8` 为 `not_started`，
  权威清单见 [`machine/facts/task_state.json`](machine/facts/task_state.json)；
  每个节点必须作为独立 Run 按冻结 DAG 依赖顺序执行。
- R2 backup/readback 与 isolated restore 已 verified；OCI 日常 write-only PAR 的读回
  保持 `activation_pending_write_only_par`。`FORMAL_FINAL_ACCEPTANCE`
  仍为 `activation_pending`，不得因已验证子面提前封口。
- GitHub 发布：全部 TaskPack 与 PG-0–PG-8 完成前禁止 push/PR

## 唯一身份

- 代码仓：`LinzeColin/MetaDatabase`
- 项目路径：`CyberBoss/`
- MVP workspace alias：`cyberboss`
- MVP 写入范围：`CyberBoss/**`，以及 Run Contract 明确列出的根级治理集成文件
- 长期数据：`LinzeColin/Private-Database` 的 `Private-MetaDatabase` 区，
  `domain=CyberBoss`，通过 `private_db_client.py` 免 clone 存取

## 权威入口

1. [`AGENTS.md`](AGENTS.md)
2. [`HANDOFF.md`](HANDOFF.md)
3. [`machine/facts/owner_decisions.json`](machine/facts/owner_decisions.json)
4. [`machine/facts/task_state.json`](machine/facts/task_state.json)
5. [`docs/product_design/v0.0.0.4/00_README_FIRST.md`](docs/product_design/v0.0.0.4/00_README_FIRST.md)
6. [`docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`](docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml)

每个 Run 最多执行一个 TaskPack `phase`。Run 结束必须运行对应 Acceptance，
更新 `task_state.json` 与 `HANDOFF.md`；不得用意图、文档声明或窄测试代替真实证据。

CB-010 使用受保护本地部署记录解析同一授权 OVH 资产，严格 known-host、
key-only SSH 完成三次即时脱敏 preflight；选择 `constrained`，确认
8765/8780 和四个拟用路径无冲突，并在 128 MiB 有限容器中完成
16 MiB/8 MiB/100 有界 pressure，OOM-kill delta 为 0。地址、凭据、私钥、
原始进程/容器/Status 数据均未进入仓库。

P0.3 从受保护部署记录完成 Cloudflare/OCI 只读能力核验，没有输出真实值。
Access 专用 token 的跨服务读取被拒绝；现有 R2/D1 token 表现出跨
Access/R2/DNS 的读取能力且无法证明精确写 scope，因此所有真实 provider
mutation 保持 `activation_pending`/`hazard_blocked`。本地 adapters/mocks、
Access deny/allow、repo/data/bucket/prefix negative matrix 与 7 个受保护已知
秘密 equality scan 全部通过，P0/P1 findings=0。

P0.4 先原样运行 supplied simulator。WeChat baseline 收发成功；Codex
simulator 因无法从 implementation-kit 解析已锁定的 `ws` dependency 而实际
启动失败。最小扩展后，两份 simulator 覆盖 QR/login、cursor/replay、
duplicate/unknown outcome、401/403/429/500/503/timeout/reset，以及 Codex
initialize/thread/turn/progress/approval/error/overload/interrupt/crash/
false-success/late-event，4/4 contract tests 和 App 155/155 tests 均通过。
本机虽有锁定版本的 authenticated Codex，目标 OVH 仍无 CLI/auth/WeChat
state，真实 Codex/WeChat 与 AC-001/AC-010 均准确保持
`activation_pending`。安全复核同时修正既有 secret scanner 的字面
word-boundary 漏报，并用 7 类 hostile fixture 逐项验证；不阻塞下一 Run
`P0.5 / CB-040`。

P0.5 交叉核验 owner decisions、source lock、identity/credential policy、
OVH 实机边界和完整 TaskPack，消解旧 Feature Flag 别名后，将运行时名称唯一
对齐到 implementation-kit 已校验配置；没有改变功能默认值、Acceptance 或
Task DAG。`implementation-plan.json` 将 `CB-100`–`CB-540` 全部 25 个后续
任务映射到具体模块、测试、Acceptance、证据和 immutable release artifact。
确定性 SHA-256 抽取的 10 个 requirement 均能定位完整链，no-wait hits=0。
本地 baseline commit
`8a75b55e92071bb33f1cae5872feca55ade1c858` 未推送，远端 branch/PR/tag
核验均为空。真实 Codex、WeChat、Private-MetaDatabase 与 provider 写入继续
保持 `activation_pending`/`hazard_blocked`；该 Run 当时的唯一下一节点为
`PG-0`。

PG-0 在不读取或依赖真实 credential 的隔离环境中执行 22 项准备检查；
4/4 simulator tests、155/155 App tests、DAG/traceability/no-wait/TaskPack、
preflight/resource、activation clean fixture 与 secret scan 全部通过。
unresolved architecture conflicts、credential values、external writes 均为
0。原源码、许可证、Corresponding Source、129 项依赖清单和严格
`GPL-3.0-only AND AGPL-3.0-only` 冲突记录保持不变，且
`upstream_clarification_received=false`。远端 CyberBoss branch/PR/tag
仍为空；该 gate 当时未启动 `P1.1 / CB-100`。

P1.1 以本地 implementation commit
`b2a603e415a2045b441f31e07cf74ac451ba6240` 作为目标主机 immutable
release ID。fresh preflight 再次证明 target hash、strict known-host、
key-only SSH、constrained/recover profile、四个路径和 8765/8780 无冲突。
两次 apply（第二次不重测资源、不覆盖 rollback prestate）通过；主
`cyberboss-cloud.service` 固定非 root、`KillMode=control-group`、
strict filesystem allowlist、资源上限和独立 journal cap。最终验收完成
100/100 systemd kill/restart、100/100 singleton denial、5 个权限拒绝与
2 个 allowlisted write，规范化 route topology 不变，unit 回到
disabled/inactive 且端口为 0。首次验收 harness 的原始 route JSON
复合哈希冲突及后续纠正记录完整保留。未安装真实 Runtime、Node/Codex，
未执行 provider/Private-MetaDatabase 写入，也未 push/PR/tag。

P1.2 以本地 implementation commit
`3cd8eee4f6b7c0a78f7b6fde90dae0f4ff1392fc` 固定 Node.js `24.18.0`、
Codex CLI `0.146.0-alpha.3.1` 与三个官方 archive SHA-256，只安装到
`/opt/cyberboss-cloud/shared/toolchains`，不修改全局 Node/Codex。两次
apply 与独立 verify 通过，`node:sqlite` self-test 通过，受保护
`CODEX_HOME` 为 `cyberboss:cyberboss:0700`。瞬时 App Server 仅监听
`127.0.0.1:8765`，`/readyz=200`、initialize/initialized 通过，外部端口
不可达；清理后 listener/process/staging 均为 0，主 unit 仍
disabled/inactive，`current` 仍指向 CB-100 release。

目标没有 `auth.json`，因此真实 Codex adapter 准确保持
`activation_pending`，device auth 命令只准备未执行。Claude Code
binary/credential 均未安装；默认 feature/eval 双门为 false，三个负向组合
全部拒绝，true/true 只进入无副作用 fixture，没有启动 adapter。首次 hold
marker 编排超时和第二次 0700 staging 导出失败均保留在 CB-110 evidence，
最终完整重跑通过。没有真实 WeChat/Runtime、provider/
Private-MetaDatabase 写入或 GitHub publication。

P1.3 以本地 implementation commit
`10d988e908d72ea1a43bbed04a2130a338663363` 生成完整 Corresponding
Source、`blob:none` partial seed、exact canonical no-clone client 与官方
GitHub CLI `2.96.0` artifact。目标机 check、两次 apply、独立 verify 和
App 166/166 tests 通过；第二次 apply 幂等。唯一 workspace
`/srv/cyberboss-workspaces/cyberboss` 固定 exact head、`.github` /
`CyberBoss` sparse paths、本地 immutable seed remote 和 root-controlled
alias/realpath gate。

目标 9/9 workspace 专项测试证明 `/bind cyberboss` 通过，绝对路径、未知
alias、symlink escape 与未登记 Runtime root 全部 fail-closed。code identity
不能读/执行 data client，data identity 不能写 code workspace；wrapper
只执行 plan-only，credential 文件缺失，Private-Database clone 和真实数据
操作为 0。Live workspace 约 29.1 MB、预算状态 `recover`；有界 target
cgroup pressure 零 OOM。验收过程中 root Python 产生的两个 cache entry 已
作为精确 transient artifact 删除并保留纠正记录。最终 candidate 只读，
process/listener 为 0，`current` 仍指向 CB-100，service 仍
disabled/inactive；没有 push/PR/tag/release。

P1.4 / CB-130 以本地 implementation commit
`81dc1ee211e554dd8b84001bfca4b8aa73bb89dd` 固定一个非 shell、
无 detached child 的 cloud supervisor，在既有
`KillMode=control-group` unit 下管理 loopback Runtime、channel fixture
与 bridge。目标机 check、两次 apply、独立 verify 和 App 170/170 tests
通过；第二次 apply 幂等，candidate 只读且完整保留 Corresponding Source、
原许可证与冲突记录。

`/healthz`、`/readyz` 与 token-protected bounded snapshot 分离验证；
forced-unready 为 healthy 200 / ready 503，不能假绿。8765/8780/19080
仅监听 loopback，操作者主机扫描确认 8765/8780 外部不可达。100/100
concurrent start、100/100 singleton denial、100/100 SIGKILL/restart 与
runtime/channel/bridge/service 4/4 fault recovery 全部通过，每次恢复均证明
旧 cgroup 成员已全部替换。Node 24 TAP 前缀与 systemd 255
`kill-whom=all` 两个真实 harness 缺陷及所有失败/清理结果完整保留。

最终 service 为 disabled/inactive，MainPID、process、listener、transient
drop-in、token、incoming 均为 0；`current` 仍指向 CB-100，workspace 仍在
CB-120。真实 Codex/WeChat 仍准确保持 `activation_pending`，没有
Private-MetaDatabase/provider 写入或 GitHub publication。该 Run 当时只将
`P1.5 / CB-140` 留作下一任务。

P1.5 / CB-140 以本地 implementation commit
`571438751638a01c4648ff4fdf27403a97a971c3` 固定完整 Corresponding
Source、pre-Runtime sender/32768-byte 输入门和 opt-in 脱敏关联 trace。
目标机 check、两次 apply、独立 verify 与 App 175/175 tests 通过；第二次
apply 幂等，candidate 只读且未切换 `current`。

瞬时 simulator process family 完成 10/10 read-only E2E，194 条记录以 34
个 trace ID 关联 inbound、Runtime、outbox、confirmed delivery 和 canonical
event，原始消息/结果/身份字段为 0。未授权与 32769-byte 输入均在 Runtime
前拒绝且 Runtime 调用为 0；32768-byte 输入调用为 1。20/20 延迟样本为
P50 372 ms、P95 378 ms。运行源/config/process/connector 的 Mac 命中和
non-loopback 连接均为 0，操作者主机连续三次确认 8765/8780/19080 不可达。

浏览器安全策略禁止本地 `file://` 抓屏且禁止绕过，因此 PNG 证据使用已验收
fixture 固定字符串做确定性静态渲染，并在画面与说明中明确标注
`NOT REAL WECHAT`、`NOT A BROWSER CAPTURE`。真实 Codex/WeChat 和
AC-001/AC-010 real 仍为 `activation_pending`。证据取回后 staging/env/
incoming 均已删除，service disabled/inactive、process/listener 为 0，
`current` 仍在 CB-100、workspace 仍在 CB-120。`PG-1` 未在本 Run 执行；
下一独立 Run 是 `PG-1`，`CB-200` 仍为 `not_started`。

PG-1 以 P1.5 closure
`4020f07bc086ab9827ab97ddf295927075189a9f` 为冻结输入，核验
CB-100–CB-140 五个 evidence tree、implementation/closure topology 和
15 个唯一 Acceptance ID。隔离凭据环境下 simulator contract 5/5、
Walking Skeleton static 4/4、live process chain 1/1、两个 root contract
各 5/5、App 175/175、DAG/traceability/no-wait/TaskPack/Prestage 与 secret
scan 全部通过。

fresh strict-known-host/key-only 目标元数据探针确认 CB-140 candidate 保留但
inactive，service disabled/inactive，process/listener/staging/incoming/token
均为 0，`current`/workspace 未变化。真实 Codex/WeChat 继续准确标记为
`activation_pending`；GitHub branch/PR/tag/release 均为 0。该 Gate 不声称
Stage 2 SQLite WAL spool 已完成，也未启动 `P2.1 / CB-200`。

P2.1 / CB-200 以本地 implementation commit
`6c8d7a1092a1f4d10a7f512ebe9abd2380aa2287` 固定完整 Corresponding
Source、SQLite schema v2、WAL/FULL/foreign-key/busy-timeout 初始化和精确
21-edge job 状态机。10,000 个稳定 ID fixture、10,000 次 transition
property、32 个并发 inserter、五个真实子进程 crash cut point、clean/
existing-v1 migration、legacy-v1 reader、raw SQL guard、immutable event、
canonical reconcile 与 DB/WAL/SHM plaintext/key scan 全部通过；本地与目标
候选 App 均为 185/185。

active payload 仅以 caller-supplied key 做 AES-256-GCM 存储并经 TTL
redaction；scheduler、channel poll、outbox worker 与真实 canonical sync
明确未集成。目标机 check、两次 apply、独立 verify 与合成 acceptance 通过，
但未切换 `current`、未移动 workspace、未启动 service、未创建 canonical
runtime DB。证据取回后 staging/env/incoming/bootstrap/synthetic key/
acceptance DB-WAL-SHM 均删除；精确候选仅保留为 inactive。CB-210、PG-2 与
所有后续任务/退出门仍为 `not_started`，GitHub publication 仍为空。

P2.2 / CB-210 以本地 implementation commit
`5c7b48d8f618bc83a70ebbd63eaf94b6ce6627ea` 将 WeChat fetch 与 cursor
commit 分离。raw batch 的每条 user、policy-rejected 或 non-user update
都先进入 CB-200 AES-256-GCM spool；accepted update 只创建一个 job，
随后才以 compare-and-set 原子推进 cursor。numeric cursor 额外要求最高
连续序列；gap、duplicate sequence、regression、缺少稳定 provider identity、
symlink、oversize 和 stale writer 全部 fail closed。

本地及 immutable candidate App 195/195、十个专项测试、三种真实子进程
`SIGKILL` cut、1,000 次 replay、ordering/property、DB integrity、
canonical reconcile 与 DB/WAL/SHM plaintext/key scan 全部通过。每个 crash
case 最终均为一条 inbox、一个 job、一次 synthetic execution，message loss
和 duplicate execution 为 0；synthetic execution 不代表真实 Runtime。

目标机 check、两次 apply、独立 verify 和 synthetic acceptance 通过。
证据读取后 staging/env/incoming/bootstrap/synthetic runtime/key 均已删除；
精确候选只保留为 immutable/inactive，service disabled/inactive，
process/listener/incoming/canonical runtime DB 为 0 或不存在，`current` 与
workspace 保持原基线。CB-230、PG-2 与全部后续节点仍未开始，
GitHub publication 仍为空。

P2.3 / CB-220 以本地 implementation commit
`ac51cd2511a45def88068aef6d23fd10d7f507e4` 增加 schema v3 和 durable
Runtime scheduler。非 command job 严格按 `created_at,id` FIFO，由
transactional claim、partial unique index、owner token、heartbeat、
expiry 和 late-event fencing 保证全局 active Runtime lease 最大值为 1。
slash command 使用独立 control lease，因此 active turn 中 `/stop` 可立即
发出 cancel request；acknowledgement 不声明 terminal，最终状态由 Runtime
`completed`、`failed`、`interrupted` 事件决定。

每次 dispatch 重新解析 root-controlled workspace alias；absolute、unknown
和 symlink escape 均在 Runtime 前拒绝且不改变文件系统。resource/readiness
gate 对 unavailable measurement、poll stale、Runtime unhealthy、memory/
disk/inode/load/queue pressure 与 stuck lease 给出固定 reason/action。
只有明确 terminal retryable 的 read-only job 可在预算内重排；dispatch 后
ambiguous bounded mutation 永不自动 replay。

本地与 immutable candidate App 213/213、调度专项 9/9、目标 executable
acceptance 38/38 均通过。目标有限 128 MiB transient cgroup fixture 分配
16 MiB 内存、写入 8 MiB 临时文件并构造 100 项队列，OOM-kill delta=0。
check、两次 apply、独立 verify 全部通过；证据读取后 staging/env/incoming/
bootstrap/synthetic runtime 已删除。精确 candidate 保持 immutable/inactive，
service disabled/inactive，process/listener/incoming/canonical runtime DB
为 0 或不存在，`current` 与 workspace 保持冻结值。CB-230、PG-2 与全部
后续节点仍未开始，outbox worker/receipt 和 GitHub publication 均为空。

P2.4 / CB-230 以本地 implementation commit
`1b3e338847d8819869a5e12091f25b5463a8d3be` 增加 additive schema v4、
encrypted durable outbox、append-only attempt ledger 和 provider receipt
truth。accepted ack 在 cursor commit 前 staged；final result、terminal
error/cancelled 在 provider 调用前 staged。Unicode chunk、dedupe key、
logical-message hash 与 provider client ID 均稳定派生，旧 v1 pending
outbox 行升级时也会在 claim 前确定性补齐身份。

503→503→200 fixture 在 virtual clock 下仅尝试 3 次，retry delay 为
1000/2000 ms，真实等待为 0。相同 key staged 1,000 次只产生一个 durable
row 和一次 confirmed delivery。13,300 code points 被稳定分为 4 段并可
按 SHA-256 完整重建；401 进入 terminal，并只在 refreshed context 上发送
固定脱敏建议。pending、pre-dispatch claim、post-dispatch unknown 和
confirmation-commit 四个重启切点均由状态 predicate 恢复；unknown outcome
自动重发为 0，void receipt 不能确认，job 只在所有 final chunks confirmed
后进入 `replied`。

本地及 immutable candidate App 227/227、目标 synthetic acceptance 37/37
通过。exact artifact、write-free checks、两次 apply、独立 verify 和最终
cleanup 均通过；candidate 保持 immutable/inactive，service
disabled/inactive，process/listener/incoming/staging/runtime/canonical
runtime DB 为 0 或不存在，`current` 与 workspace 保持冻结值。真实
Codex/WeChat/Private-MetaDatabase/canonical sync 未调用，CB-240、PG-2
与 GitHub publication 均未开始。

## 许可证

`CyberBoss/` 子树适用 [`LICENSE`](LICENSE) 中的 GNU AGPL-3.0-only。
历史上游仅作为固定来源快照和依法必须的归属证明；项目不保留上游 remote、
submodule、Git URL 运行时依赖、自动同步或定期 rebase 关系。

`whereabouts-mcp` 的 package 声明与许可证文件冲突按
`AGPL-3.0-only AND GPL-3.0-only` 的严格双重义务处理；原许可证、源码和冲突
记录完整保留，且不得声称已获得上游澄清。
