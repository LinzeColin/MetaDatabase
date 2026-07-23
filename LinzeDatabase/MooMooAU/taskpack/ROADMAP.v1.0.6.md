# MooMooAU Archive Roadmap v1.0.6

本版本是 v1.0.5 的基线保真控制继任。v1.0.1 冻结的 Pursuing Goal、S0–S7、34 RQ、34 AC、
58-task DAG、Kill Criteria 与十条不变量全部继续有效。

## 不变的产品契约

| 契约 | 数量或身份 | SHA-256 |
|---|---:|---|
| Requirements | 34 | `ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27` |
| Acceptance Contracts | 34 | `3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb` |
| Traceability Matrix | 34 RQ ↔ 34 AC ↔ 58 tasks | `263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2` |
| Task DAG | 58 tasks | `72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9` |
| Kill Criteria | 原样继承 | `2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc` |
| Canonical Facts | 十条不变量 | `27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2` |
| v1.0.5 Manifest | 不可变直接前序 | `f99413b9c1fb67369ba3039a7acfeb437004d1aad8cb54dc3697f87f38e35cb3` |

## RMD-06 云执行前置闭包

目标仅为建立可运行的 GitHub-hosted 验证前置：

- 修复 GitHub expression context；
- 为私有 Governance 使用单仓只读 Deploy Key；
- 凭据仅供 pinned `actions/checkout` 使用；
- fork PR 在凭据 checkout 前 fail closed；
- clean checkout 对已关闭 RMD-05 前序只依赖不可变 Manifest，不依赖候选分支不可达的旧 Git object；
- 普通 CI 的 parser 与 Stage 3 PDF runtime 依赖必须完整进入精确 pin、hash lock、SBOM 和审计面；
- 历史累计 Job 对 v1.0.6 使用 hash-bound composition 静态验证，Stage 7 完整依赖 Job 继续执行
  contract-only CLI，二者不得互相冒充；
- Stage 6 先验证 v1.0.5 Manifest 与完整不可变 authority set，再验证当前 receipt bundle；depth-1
  checkout 不得因缺少已关闭前序的旧 Git object 而改变证据结论；
- Stage 6 的不可变结构化 receipt/provenance JSON 使用 JSON 解析与显式高风险凭据模式验证，其余
  代码/契约范围继续执行 `detect-secrets`；固定非 Secret SHA-256 只允许精确值 allowlist，不允许
  宽泛凭据值排除；
- 普通 CI 的生产/Gmail/数据仓 Secret 读取保持零；
- 不执行生产、Gmail mutation、私有数据仓写入、部署或最终发布。

本版本不把依赖凭据读取解释为生产 Secret 读取，也不把 GitHub-hosted CI 解释为 protected Oracle。
任何 Workflow syntax、Governance pin、Secret 边界、fork policy、package、publication 或 cumulative gate
失败都停止 RMD-06。

第五轮受控候选提交 `2e1dda85a9bc85fb656eb6b6abb8f775bfef9292` 已让精确生成的 9 个
GitHub-hosted 非生产 Workflow 全部 `completed/success`；候选远端分支随后删除，没有 PR、merge、
部署或发布。该结果只关闭云执行前置，不满足任何 protected Oracle。

## T0702 Beta Run Contract 与实际结果

本轮只允许 T0702/S7AC-002 的一次受保护 Raw-only 交付与 dispatch：

- 唯一入口为 `.github/workflows/moomooau-beta.yml`，只接受 owner 在 `main` 上手动
  `workflow_dispatch`；
- 先绑定控制仓/owner/actor 数字 ID、expected commit、Workflow ref、GitHub-hosted runner、
  首次 run attempt、受保护 `moomooau-beta` Environment 与同树 Alpha gate，再读取任何 Beta Secret；
- 执行步只接受六个精确名称：Beta config、sender registry、GitHub App private key、age identity、
  opaque ID key 与 Gmail OAuth；
- 只允许 Raw archive 与远端恢复；Gmail mutation、Parser、M3、Processed 与 Timeline 均为零；
- 成功必须观测 1..显式正整数预算个真实已验证消息且远端恢复 100%；公开输出仅为 bucket、零值计数
  与 gate 布尔值，不公开精确预算或精确邮箱/恢复计数；
- 代码就绪不等于真实 Beta。Environment、六个值、消息预算、verified registry、唯一私有数据仓和
  GitHub App installation 未配置或未证实时，Oracle 必须保持 `NOT_RUN`。

Owner 已于 2026-07-23 仅为 T0702 解除一次上述顺序冲突：允许一次受控 PR/merge 到 `main` 和一次
budget-one protected Raw-only dispatch，且 `moomooau-beta` 不设人工 reviewer。该例外不授权第二次
交付、rerun、Gmail mutation、M3、Processed、Timeline、schedule 或最终发布；任一前置无法独立核验
即停止。

该历史一次性授权消费并失败后，Owner 又明确授权受控完成 Stage 7，不允许以自然时间或人工审批制造
阻塞。新授权允许交付已验证 repair，并对每个 exact main SHA 串行执行新的 first-attempt protected
dispatch；仍禁止 GitHub rerun。Beta 每次预算固定 1、Gmail mutation 固定 0；只有真实 T0702 PASS
后才按现有门进入 M3、Blue-Green、GA 与 Recovery。

Pre-dispatch bootstrap 已完成独立核验：Environment 为 no-reviewer/main-only，只有六项允许的
Secret；唯一私有数据仓、单仓最小权限 GitHub App、cloud-only age identity、opaque key、预算 1、
fresh-capacity config、`gmail.modify` OAuth 与 metadata-derived verified sender registry 均已就绪。
真实 metadata-only 观察还确认 Gmail 默认 metadata 响应可能携带 `snippet`，且 RFC 8601 DKIM
identity 可能位于 `header.i`；运行时因此强制 exact partial-response fields，并要求出现的全部
`header.d`/`header.i` identity 对齐 allowlist。

一次受控 PR/merge 与一次 first-attempt dispatch 已实际完成。同树 Alpha job PASS；protected Beta
执行步返回 `PROTECTED_BETA_RUN_FAILED`，identity tmpfs cleanup PASS。运行后唯一私有数据仓仍为
64-byte 单文件、单 commit、零 release 的 bootstrap 基线，因此失败边界可确定为“首个远端 Raw
commit 之前”；现有 aggregate-only 日志无法区分 bootstrap、discovery、verification、Raw fetch、
encryption 或 first-commit 内部失败，verified full Raw read 只能记为
`UNDETERMINED_WITHIN_BUDGET_ONE`。Gmail mutation、M3、Processed、Timeline、schedule 与最终发布
均为 0；T0702/S7AC-002 未通过。

## T0702 本地诊断修复

唯一失败尝试仍是不可变历史，不能从后续代码反推其精确根因。新的纯本地 repair 只改善下一次
独立授权 attempt 的可观测性：

- 新增 19 项封闭 failure phase 与唯一固定 reason code；
- phase/reason 通过 exact JSON Schema 配对，拒绝额外字段与错配；
- public renderer 不接收异常对象或动态文本，不输出 Secret、邮件字段、私有仓标识或精确计数；
- 合成 probes 覆盖 context、Alpha binding、config/capacity、registry、GitHub App、age identity、
  Gmail OAuth、repository resolution、discovery、metadata verification、Raw fetch/encryption/
  commit、remote recovery、aggregate gate 与 cleanup；
- repair Run Contract 的远端写入、dispatch、protected Secret、Gmail、私有仓、M3 与发布预算均为 0。

该 repair 已通过 PR #92–#95 受控交付，并分别在互异 exact-main SHA 上执行新的 workflow
attempt 1，未使用 GitHub rerun。四次公开安全结果依次收敛为 `GITHUB_APP_TOKEN`、
`INSTALLATION_NOT_FOUND`、`INSTALLATION_DISCOVERY_REJECTED` 与 `INSTALLATION_ZERO`。
加上历史首次运行，共 5 次 Alpha/identity cleanup PASS、Beta FAILED；最新事实是现有 App 的
installation 列表为空。精确公开安全序列由
`machine/stages/S7/reviews/t0702/attempt-ledger.json` 绑定。在 App 仅安装到唯一私有数据仓且新的
protected attempt 实际 PASS 前，T0702/S7AC-002 继续诚实保持 `BLOCKED`。

## Stage 7 确定性证据替代日历等待

Owner 最新指令明确取消 M3 七天与 Blue-Green 十四天的固定观察期，开发和验收不得因自然时间暂停。
该调整不改变 34 条最终 Acceptance、不放宽零误伤、远端恢复、Budget 1、单一 Timeline 或前序门：

- M3 在 Beta PASS 后执行一次有界受保护运行，必须产生至少一个 complete/safe-deferred Processed、
  恢复率 100%、Mutation Budget=1、至少一个精确 source Trash、零 collateral mutation，Timeline 关闭；
- Blue-Green 在 M3 PASS 后执行一次有界受保护运行，必须对同一恢复 Raw 完成 Processed 恢复、
  incumbent/candidate 比较、Timeline publish、Full Reconcile，差异为 0 且 live Timeline 恒为 1；
- GA 仍必须实际观察一次 04:30 Australia/Sydney 调度，这是核心产品行为，不是等待期。

## 后续顺序

1. 只读 Governance Deploy Key 与 GitHub-hosted 非生产预检已完成并关闭临时远端候选；
2. T0702 protected Raw-only 入口、pre-dispatch bootstrap、受控 main 交付与唯一 dispatch 已执行；
3. 历史 Beta FAILED 与一次性 Run Contract 消费记录保持不可变；
4. Stage 7 public-safe diagnostic repair 已通过 PR #92–#95 交付并完成四个 serial new
   first-attempt dispatch；最新固定结果为 `INSTALLATION_ZERO`，继续禁止 GitHub rerun；
5. 只有 Beta 真实 Oracle 全绿后，才可按 M3 → Timeline Blue-Green → GA → Recovery → 最终 AC
   的既定顺序继续；M3 与 Blue-Green 各只需一次证据完整的受保护运行，不等待自然日；
6. RMD-06 完成后再进入 RMD-07 整体复审与最终一次性发布。
