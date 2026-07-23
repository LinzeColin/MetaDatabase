# MooMooAU 当前交接

## 当前目标与状态

- `RMD-06` 的 T0702/S7AC-002 protected Raw-only 入口与公开安全诊断已交付。共 5 个互异
  exact-main SHA 通过 PR #88、#92、#93、#94、#95 受控合并并各执行一次 workflow attempt 1；
  每次同树 Alpha 与 identity plaintext cleanup 均 PASS，Beta 均 FAILED，GitHub rerun 为 0。
  最新固定诊断已收敛为 `GITHUB_APP_TOKEN / INSTALLATION_ZERO`：现有最小权限 App 尚无任何
  installation。Raw commit、Gmail mutation、M3、Processed、Timeline 与 schedule 均为 0；
  T0702/S7AC-002 仍 `BLOCKED`，真实 PASS 前不得进入 M3。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-23-V1.0.6`。它原样继承 v1.0.1 的 34 RQ、34 AC、
  58-task DAG、Kill Criteria 与十条不变量，并将 v1.0.5 作为不可变直接前序。
- 唯一当前状态权威是 `machine/status/latest.json`：本地机制证据完整，受保护 Oracle
  2/43（PASS 1、FAILED 1），最终 Acceptance 0/34，protected Workflow 5、production Workflow 0，
  发布状态为 `CONTROLLED_BETA_DELIVERY_NOT_FINAL`。
- Governance 固定为私有 `LinzeColin/Governance` 的提交
  `ebc6c2e4884edc959118cfc56d0e18a86c49460f`。

## RMD-06 已完成的前置工作

1. 四个 Workflow 的 `runner.temp` 已从 job-level `env` 移至 runner 上的首个配置步骤，消除零 Job
   expression 解析失败。
2. 八个依赖 Governance 的 Workflow 只允许通过
   `MOOMOOAU_GOVERNANCE_DEPLOY_KEY` 注入 pinned `actions/checkout` 的 `with.ssh-key`；
   凭据不得进入 env、shell、项目 Python 或生产运行时。
3. fork pull request 在受保护依赖 checkout 前显式 fail closed；禁止 `pull_request_target`；
   `persist-credentials` 与 Deploy Key 写权限均为 false。
4. 单仓只读 Deploy Key 与 MetaDatabase Actions Secret 已配置；精确固定提交可由该凭据读取。
   本机一次性私钥、探测仓与临时 known_hosts 已删除。
5. 初始 v1.0.6 candidate 曾通过 package、delivery status、Governance、publication、Secret scan、
   production composition、Workflow matrix、Stage 1/2/7、本地 `257 passed`、Ruff 与 strict mypy；
   后续修复正在重跑全套门，不能沿用该旧快照结论。
6. 已从最新 `origin/main` 建立无旧开发谱系的 `codex/moomooau-rmd06-cloud-preflight` 快照分支；
   项目目录与全部十个 MooMooAU Workflow 已按 Git tree/blob 逐字节核对。
7. 34 个最终 Acceptance 记录已确定性重建到该干净主线父提交，仍保持 34/34 `BLOCKED`、0 `PASS`、
   0 invalid；未把谱系迁移解释为 protected 或生产成功。
8. commit `1936f5a321b896d8cdd91a103eb7300c70df9222` 的首轮 GitHub-hosted 预检已全部到终态：
   Stage 2/3/4/5/6 software、Stage 1、Stage 6 model、Stage 7 与 patch lifecycle 共 9 个 Workflow
   结论为 `failure`；Stage 2–6 的 5 个 CodeQL job 独立 `success`，push 上的 dependency-review
   按契约 `skipped`。Run IDs：
   `29981928812`、`29981928813`、`29981928814`、`29981928824`、`29981928830`、
   `29981928832`、`29981928848`、`29981928854`、`29981928885`。
9. 首轮失败没有扩大权限：私有 Governance checkout 成功，生产/Gmail/数据仓 Secret 未读取，
   外部写入、生产运行、部署与发布仍为 0。三个根因均可复现：
   Stage 1 缺少 `PyYAML`；clean clone 缺少旧 RMD-05 Git anchor object；Stage 3 累计锁缺少
   `pikepdf`/`Pillow`。
10. 三项修复已在本地完成：Stage 1 精确 pin `PyYAML==6.0.3`；关闭的 RMD-05 前序以不可变
    v1.0.5 Manifest 验证且不读取旧 Git object；Stage 2 累计锁更新为 80 packages / 15 direct
    pins，SBOM 为 80 components / 35 dependency nodes with edges。新锁通过零漏洞审计、全新
    Python 3.12 hash install、sdist/wheel/CLI smoke、Stage 2/3 digest-pinned container smoke、
    Stage 2 secret scan、SBOM reproducibility、Ruff 及 `54 passed` 目标测试。
11. 修复后的本地闭环已通过：全量 `257 passed`；strict mypy `80 source files`；34 Acceptance
    结构有效且全部 `BLOCKED`；package、Manifest、delivery status、Governance、publication、
    Secret scan、production composition 与 Stage 1/2 均 PASS；Workflow matrix 为 4 个
    cumulative PASS + 4 个 historical expected-BLOCKED，tree unchanged；Stage 7 preflight
    命令成功且准确保持 `BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES`。所有外部写入、生产运行、
    protected Oracle、final Acceptance PASS 与发布计数仍为 0。
12. commit `0855a745e6e85cd9a6579745c5cb517e917c984c` 的第二轮 GitHub-hosted 预检已全部到
    终态：Stage 6 Codex policy assurance 为唯一 `success`；Stage 1/2/3/4/5、Stage 6
    software、Stage 7 与 patch lifecycle 共 8 个 Workflow 为 `failure`；Stage 2–6 的
    5 个 CodeQL job 独立 `success`，push 上的 dependency-review 按契约 `skipped`。Run IDs：
    `29983372173`、`29983372175`、`29983372181`、`29983372188`、`29983372190`、
    `29983372197`、`29983372198`、`29983372202`、`29983372225`。
13. 第二轮证明首轮三个直接根因已解除：全部 Governance checkout 成功；Stage 1 lint/type
    成功；Stage 3 累计锁安装成功。8 个失败均汇聚到 `tests/tasks/test_t0101.py` 的 package
    gate；depth-1 clean clone 复现为 delivery-status transition 仍把 v1.0.6 的 Stage 6
    bundle 绑定到不可用的旧 Git anchor，报
    `closed delivery state lacks candidate-bound Stage 6 evidence`。未读取生产 Secret，
    未发生 Gmail、数据仓、部署、生产或发布写入。
14. 第三项闭环修复改为可移植双层验证：v1.0.6 的当前 Stage 6 bundle 只做候选结构绑定；
    关闭的 v1.0.5 前序则从其精确 Manifest 校验 82 个 Stage 6 evidence/review 权威文件的
    完整集合与 SHA-256，不依赖旧 Git object。Acceptance remediation base 在完整仓库仍要求
    Git ancestry；仅当仓库为 shallow checkout 且 v1.0.6 provenance 与代码同时精确固定
    `932dafae972ab00c3e2259ba3a06f6deaa8e108d` 时允许无对象验证，其他值全部 fail closed。
    目标 Ruff、strict mypy 与 `12 passed` RMD-06 回归已通过；独立 depth-1 clone 已确认
    `is-shallow=true`、仅 1 个 commit 且旧 base object 不存在，并通过 immutable predecessor、
    delivery status、package gate 及 T0101/RMD-06 合计 `13 passed`。
15. 最终本地静态树已通过：`316 passed`；strict mypy `80 source files`；scoped Ruff
    `131 files`；package `586 files`；34 个 Acceptance 全部结构有效且准确 `BLOCKED`；
    Stage 1/2/6 与 Stage 7 scoped preflight PASS，Stage 7 生产状态仍为
    `BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES`；Workflow matrix 为 4 个 cumulative PASS
    + 4 个 historical expected-BLOCKED 且 tree unchanged；依赖审计零已知漏洞、SBOM byte-equal、
    Secret/publication findings 均为 0。v1.0.5 Manifest、34 RQ/AC、traceability、58-task DAG、
    Kill Criteria 与 canonical facts 的冻结 SHA-256 全部未变。
16. commit `9d4b4f463d4fb9b42066f6409ddc455234fc31b7` 的第三轮 GitHub-hosted 预检已全部到终态：
    Stage 6 Codex policy assurance 为唯一 `success`；Stage 1/2/3/4/5、Stage 6 software、
    Stage 7 与 patch lifecycle 共 8 个 Workflow 为 `failure`；Stage 2–6 的 5 个 CodeQL job
    独立 `success`。Run IDs：`29985127083`、`29985127086`、`29985127092`、`29985127104`、
    `29985127105`、`29985127131`、`29985127142`、`29985127144`、`29985127168`。
17. 第三轮失败已在同构环境精确复现为三个非生产根因：Stage 1–4 的历史累计依赖不足以 import
    完整 production runtime，却被 v1.0.6 状态构建要求执行 contract-only CLI；Stage 5 Secret scan
    把校验器中的固定 production Workflow SHA-256 判为单个 entropy finding；Stage 6 当前 evidence
    再次读取 depth-1 checkout 不存在的旧 RMD-05 receipt anchor，产生 4 个 Git object 错误。
    Patch package gate 与 Stage 6 model assurance 已通过，证明 v1.0.6 package 与不可变前序本身未漂移。
18. 三项最窄修复已实现：v1.0.6 状态构建只做 hash-bound composition 静态层，完整 Stage 7 仍执行
    真实 CLI；Stage 6 在 sibling review check 验证精确 v1.0.5 Manifest 与 82 个不可变 authority
    后，只对当前 receipt bundle 做 portable 验证；Stage 5 固定 SHA 仅加单行 allowlist。初步验证为
    最小 Stage 2 环境状态构建 PASS、RMD-06 `15 passed`、完整 composition PASS、Stage 6 evidence
    errors 0、精确 Stage 5 scan findings 0。派生状态、13 份 facts、7 份文档与 v1.0.6 Manifest 已
    确定性重建；全新最小 Stage 1 环境的 13 个 task tests 与 validator、最小 Stage 2
    package/T0101、全量 `257 passed`、S1–S6 cumulative、S7 scoped preflight、Workflow matrix、
    Governance、package/status/facts/manifest、production composition、34 份结构有效且全部 BLOCKED
    的 Acceptance、publication/Secret 零 findings、Ruff、strict mypy 74 files、零已知漏洞 audit、
    SBOM byte-equal 与本地 package build 均 PASS。fresh depth-1 clone 已确认
    `is-shallow=true`、仅 1 个 commit；最小 Stage 1 package/13 tests、不可变前序 82 个文件、
    status/package、RMD-06 `15 passed` 与 Stage 6 cumulative 全部 PASS。
19. commit `5b05ff1a3e5f4b656427574dc9199e2c4366a4c4` 的第四轮 GitHub-hosted 预检已全部到终态：
    patch lifecycle `29987263305`、Stage 5 `29987263306`、Stage 3 `29987263312`、Stage 6 model
    assurance `29987263363`、Stage 1 `29987263366`、Stage 4 `29987263385` 与 Stage 2
    `29987263507` 共 7 个 Workflow `success`；Stage 6 software `29987263378` 与 Stage 7
    `29987263403` 为 `failure`。Stage 6 已通过功能、累计、依赖审计与 SBOM 门后，原始 entropy
    扫描才对不可变 RMD-05 receipt/review JSON 产生误报；Stage 7 仅命中一个只读依赖凭据名称和
    四个公开前序 Manifest SHA-256。未读取生产 Secret，未发生 Gmail、数据仓、protected Oracle、
    部署、生产或发布写入。最窄修复已改为 Stage 6 调用既有结构化 Secret gate，Stage 7 仅精确排除
    四个公开摘要，并为凭据名称加逐行 allowlist；目标 RMD-06 `17 passed`、Stage 6 structured gate
    findings 0、Stage 7 对齐扫描空结果。最终本地复核还通过全量 `257 passed`、strict mypy
    `60 source files`、S1–S6 cumulative、S7 scoped preflight、4 个 cumulative PASS + 4 个预期
    historical BLOCKED 且 tree unchanged 的 Workflow matrix、package/status/facts/Manifest/
    Governance/composition、34/34 结构有效且全部 BLOCKED 的 Acceptance、publication findings 0、
    零已知漏洞 audit 与 SBOM byte-equal；生产、protected Oracle 与 final Acceptance 仍未执行。
20. commit `2e1dda85a9bc85fb656eb6b6abb8f775bfef9292` 的第五轮 GitHub-hosted 非生产预检已精确
    生成 9 个 Workflow 且全部 `completed/success`：Stage 2 `29988365954`、patch lifecycle
    `29988365982`、Stage 3 `29988365983`、Stage 5 `29988365985`、Stage 7 `29988365987`、
    Stage 6 model assurance `29988365990`、Stage 6 software `29988365992`、Stage 1
    `29988366012`、Stage 4 `29988366020`。提交前 fresh depth-1 clone 已证明
    `is-shallow=true`、仅 1 个 commit、主线前序 Git object 不可达，并通过 package/status、
    RMD-06 `17 passed`、Stage 6 structured/cumulative、最小 Stage 1 `13 passed` 与 build、
    最小 Stage 2 T0101。远端候选分支已删除且没有 PR、merge 或发布；活跃 `/private/tmp` 中的
    MooMooAU 生成物和 worktree 缓存均已移入可恢复的系统 Trash。该结果只关闭云端非生产预检，
    不关闭任何 protected、真实数据或生产验收。
21. T0702 本地入口闭环新增 `.github/workflows/moomooau-beta.yml` 与
    `protected_beta_entrypoint.py`：只允许控制仓 owner 在 `main` 上手动首次 dispatch，精确绑定
    repo/owner/actor/run/SHA/Workflow ref、GitHub-hosted runner、`moomooau-beta` Environment 和
    同树 Alpha；两个 job 在 checkout 或 Secret 注入前拒绝非 GitHub-hosted runner，rerun 也 fail
    closed。执行步只接受六项精确 Beta Secret 名称，控制仓权限仅 `contents: read`。
22. 入口只装配 verified Raw age commit 与远端恢复；Gmail mutation、Parser、M3、Processed、
    Timeline、schedule、artifact/cache、控制仓写入均不可达。成功要求至少一个且不超过 owner
    配置预算的 Raw 完成 100% 远端恢复；公开输出不含精确预算或精确 verified/recovery 计数，失败
    只输出固定 reason code。T0702 本地 oracle 为 `24 passed`。
23. 只读 GitHub 核验确认控制仓仍为 public、main identity 已绑定、没有 GitHub Environment、没有
    六项 Beta Secret、没有可见的匹配私有数据仓；GitHub App installation 因 token 403 无法证实。
    verified sender registry 和正整数预算也未提供，因此未访问 Gmail、未读取真实 Secret、未调用
    私有仓、未 Dispatch Workflow。另有“中间不上传”与“必须在 GitHub-hosted runner 观察真实
    Beta”的顺序冲突，故七项 T0702 blocker 均保留。
24. 最终本地闭环通过全量 `265 passed`、strict mypy `60 source files`、Stage 7 scoped Ruff
    `107 files`、Stage 1/2、Stage 7 九项 preflight、4 个 cumulative PASS + 4 个预期 historical
    BLOCKED 且 tree unchanged 的 Workflow matrix、package/status/facts/Manifest/Governance/
    composition、34/34 结构有效且全部 BLOCKED 的 Acceptance、publication/Secret findings 0、
    零已知漏洞 audit 与 SBOM byte-equal。所有 Gmail、私有仓、外部写入、protected Oracle、生产
    Workflow、final Acceptance PASS 与远端发布计数均为 0。
25. Owner 授权后，候选提交序列已无冲突重放到最新 `origin/main`
    `9dce817b9d19d5515469df9c1ccccb16fed6a21b`；T0702 Run Contract 已改为一次性 protected
    执行合同，预算固定 1、Environment 无人工 reviewer、GitHub App 仅 `contents:write` +
    `metadata:read` 且只装一个私有仓。派生 34 Acceptance 仍为 0 PASS / 34 BLOCKED，
    protected Oracle 仍为 0/43；目标 `41 passed`、Package 587 files、Status、Governance pinned
    `ebc6c2e4884edc959118cfc56d0e18a86c49460f`、facts、Manifest 与 Stage 7 九项 scoped
    preflight 均 PASS。真实 Gmail、Secret、私有仓、Workflow dispatch 与 main delivery 尚未执行。
26. T0702 pre-dispatch bootstrap 已在不公开受保护标识或值的前提下完成：Environment 为
    no-reviewer/main-only，六项精确 Environment Secret 齐备；唯一私有数据仓为空白 64-byte
    bootstrap、Actions 关闭且无 LFS/release asset；GitHub App 仅有该仓的 contents write 与
    mandatory metadata read；age identity 在一次性 cloud tmpfs 内生成、绑定验证并销毁；预算为 1
    且容量证据为 fresh/GREEN。Gmail OAuth 仅授予 `gmail.modify`，sender registry 来自
    metadata-only 观察并已通过正负验证；未读取 RAW、未改变邮箱。
27. 真实 Gmail metadata 响应的只读核验暴露两个发布前兼容性事实：`format=metadata` 默认仍可能
    返回 content-derived `snippet`，而 Authentication-Results 可按 RFC 8601 使用 `header.i`。
    最窄修复要求 metadata get 使用 exact partial-response fields 排除 `snippet`，并让 DKIM 对
    `header.d`/`header.i` 中所有出现的 identity 全部按白名单域 fail closed。目标
    T0202/T0304/T0701/T0702 回归为 `39 passed`；受保护运行、PR/merge、Raw、数据仓写入与
    protected Oracle 仍为 0/NOT_RUN。
28. 已通过 PR #88 一次性合并精确候选到 `main`；merge tree 与本地全门候选 tree 一致。PR 合并前
    35 个 required/ordinary check success、5 个预期 skip、0 failure/pending；依赖图已启用，四个
    CodeQL clear-text logging 结果逐项核验为 false positive 后只关闭对应 alert。该受控 main 交付
    仅用于 T0702 Beta，不是最终发布。
29. 唯一 protected workflow run `29998793639` 在精确 merged SHA 上以 `workflow_dispatch`、
    attempt 1 执行且没有 rerun：Alpha job `success`；Beta job 的 protected execution step 运行
    88 秒后只输出固定 `PROTECTED_BETA_RUN_FAILED`；identity tmpfs cleanup `success`。运行后数据仓
    仍为 64-byte 单文件、单 commit、零 release 的 bootstrap 基线，故可证失败发生在首个远端 Raw
    commit 前；现有日志不足以判断 bootstrap、discovery、verification、Raw fetch、encryption 或
    first-commit 何处失败，也不能把 full Raw read 猜成 0。
30. Post-run Gmail 只使用 ID-only search 做聚合核验，未读取正文/附件、未输出 ID/发件人/主题且未
    mutation；受保护候选域仍有非 Trash 邮件。Beta 路径无 Gmail mutation/M3/Processed/Timeline/
    schedule authority，相关 effect 仍为 0。失败 receipt 已写入
    `machine/stages/S7/reviews/t0702/execution-receipt.json` 并把 Stage 7、唯一状态、Acceptance、
    Governance facts/七文档与 provenance 收敛为 fail-closed；所有这些 post-run 记录保持本地未推送。
31. 新一轮仅处理 Stage 7/T0702 diagnostic repair：新增 19 项封闭 public-safe failure phase、
    唯一固定 reason-code mapping 与拒绝额外字段/phase-reason 错配的 JSON Schema；entrypoint、
    bootstrap、Raw-only runner、remote recovery、aggregate gate 和 cleanup 均接入同一 enum-only
    tracker。renderer 不接收异常对象或动态 protected 值；合成 probe 已覆盖全部可达阶段，cleanup
    失败会在尝试全部清理动作后固定为 `RESOURCE_CLEANUP`。新的 repair Run Contract 将 main
    delivery、dispatch、Secret/Gmail/私有仓调用、M3 与发布预算全部固定为 0。该 repair 仍在本地、
    未上传，不能反推历史失败根因，T0702/S7AC-002 继续 `BLOCKED`。
32. Owner 最新指令取消 M3 七天与 Blue-Green 十四天固定等待。Stage 7 release gate 与共享 Parser
    comparator 已改为同日可完成的确定性证据门：M3/Blue-Green 各需一次有界受保护运行及完整恢复、
    Mutation/Parser、Reconcile、单 Timeline 证据；前序和安全门不变，GA 仍须真实观察一次 04:30
    Australia/Sydney 调度。本轮未因此调用任何远端服务或进入 M3。
33. 本轮收尾验证：全部 290 个 task tests PASS；RMD-04/RMD-06 remediation 24 tests PASS；strict
    mypy 67 source files PASS；Ruff format/lint PASS；58 份 task evidence 全部 schema-valid；
    34 份最终 Acceptance 全部结构有效并诚实保持 34 `BLOCKED`/0 `PASS`；Stage 7 cumulative
    preflight、package、delivery status、Governance render/budget/blocker、workflow matrix、
    production composition、publication scan 与 Secret scan 全部 PASS。未执行浏览器、远端调用、
    上传、dispatch、Secret/Gmail/私有仓访问、M3 或发布。
34. 2026-07-23T11:55:06Z 只读复核再次从 GitHub API 取得 run `29998793639` 的 attempt、job 与
    完整日志：六项 Environment Secret 名称仍齐备，Environment 仍无人工 reviewer，Alpha PASS、
    Beta execution FAILED、tmpfs cleanup PASS，日志仍只有 aggregate reason，不能新增历史根因
    结论。Google 官方 Gmail Discovery 文档当前明确列出 `gmail.modify` 覆盖本路径使用的
    messages.list、messages.get、filters.list 与 messages.trash；GitHub API 在固定
    `2026-03-10` version header 下返回 200，因此 OAuth scope 不足和 API version header 不能
    作为已证实根因。当前 `gh` user token 对 installation 枚举仍返回 403，不能独立核验受保护
    GitHub App installation；未浏览网页、未读取 Secret 值、未调用 Gmail/私有仓、未写远端、
    未 dispatch、未进入 M3。只读 fetch 还确认当前 `origin/main` 为
    `20f4e0806e275269df48171b4d93c27855400bc4`，相对本分支基点仅增加无 MooMooAU 路径重叠的
    EEI 提交；未来获准交付时仍须先把 repair 重放到该时点的最新 `main`。
35. Owner 明确要求解除重复授权阻塞并尽快完工；新增
    `machine/stages/S7/contracts/stage7_completion_run_contract.json`，授权受控 repair PR/merge、
    exact-main-SHA-bound serial new first-attempt protected dispatch，以及在真实前序 PASS 后继续
    M3、Blue-Green、GA 与 Recovery。当前工作树已无冲突 fast-forward 到
    `027e60bd1f3c2f195c60981337c007782544fbb8`；后续主线提交只增加 EEI 文件，与 MooMooAU delta
    无重叠。
36. Stage 7 诊断修复已通过 PR #92–#95 串行交付；对应 run `30008562905`、`30010198526`、
    `30011285627`、`30012211355` 均为新 exact-main SHA 的 attempt 1，Alpha/identity cleanup
    PASS、Beta FAILED、rerun 0。固定分类依次为 `GITHUB_APP_TOKEN`、
    `INSTALLATION_NOT_FOUND`、`INSTALLATION_DISCOVERY_REJECTED`、`INSTALLATION_ZERO`；
    最后一个类别证明 App JWT 有效且 App 的 installation 列表为空。五次完整序列收录于
    `machine/stages/S7/reviews/t0702/attempt-ledger.json`，不含 Secret、邮件字段、私有仓标识或
    动态异常文本。
37. 2026-07-23T14:15:57Z 已把五次 attempt 1 的 PR、精确 main SHA、run、固定分类、零副作用和
    rerun 0 收敛为 schema 约束的公开安全权威账本，并同步唯一状态、Acceptance、Governance facts、
    七份人类文档、来源链与包清单。最终本地复核通过 312 个累计测试、strict mypy 61 source files、
    Ruff 108 files、58 份任务证据、34 份 Acceptance、9/9 Stage 7 preflight、八入口 Workflow
    matrix、595 文件任务包、668 文件公开扫描、零已知漏洞 audit、字节级可复现 SBOM 与零 Secret
    findings；所有验证外部写入为 0，T0702、M3、生产和最终发布仍未被提升。

## 关键边界

- 依赖 Deploy Key 不等于生产 Secret；普通 CI 的 Gmail、数据仓和生产 Secret 读取仍为 0。
- GitHub-hosted 非生产预检不等于 protected Oracle、生产健康、部署、发布或最终 Acceptance。
- T0702 只允许 GitHub-hosted first attempt；rerun、自托管 runner、非 main、非 owner、错误 SHA/
  Workflow ref/Environment 必须在读取 Beta Secret 前 fail closed。
- public control logs 只能出现 bucket、零值计数和 gate 布尔值；不得输出精确 Beta 预算、精确邮箱/
  recovery 计数、message/thread/sender/subject/attachment 或私有仓标识。
- 历史一次受控 PR/merge 与 dispatch 已消费；新的 Stage 7 completion authority 允许受控交付和
  serial first-attempt dispatch。GitHub rerun 仍禁止，Beta PASS 前仍不得进入 M3。
- M3 与 Blue-Green 没有自然日等待；只有真实前序与确定性证据不满足时才阻塞。
- 预检任一 Workflow syntax、Governance checkout、Secret 边界、package、publication 或累计门失败，
  必须停止，不得扩大权限或读取生产 Secret。

## 下一步

1. 将现有最小权限 GitHub App 仅安装到唯一私有数据仓；不得改用 PAT、Deploy Key 或放宽权限。
2. 刷新仅有时效字段的 protected config，并执行一个新的 exact-SHA first-attempt T0702；失败只按
   固定 public-safe 类别修复并形成新提交，不使用 GitHub rerun。
3. 只有后续 Beta 真实 Oracle PASS 后才按 M3 → Blue-Green/Timeline → GA → Recovery 的既定顺序
   继续；M3 和 Blue-Green 各执行一次证据完整的受保护运行，不等待自然日；整体任务包完成后再做
   整体复审、修复与最终发布。
