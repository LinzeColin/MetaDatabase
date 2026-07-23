# MooMooAU 当前交接

## 当前目标与状态

- `RMD-06` 的 T0702/S7AC-002 protected Raw-only 入口已完成本地机制与证据闭环；Owner 已于
  2026-07-23 单独授权一次受控 PR/merge 到 `main` 和一次 budget-one protected dispatch，仅用于
  T0702。正式任务在真实 Oracle 完成前仍为 `BLOCKED`，Beta 仍为 `NOT_RUN`，不得进入 M3；该授权
  不等于最终发布，也不授权第二次交付、rerun、Gmail mutation、Processed、Timeline 或 schedule。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-23-V1.0.6`。它原样继承 v1.0.1 的 34 RQ、34 AC、
  58-task DAG、Kill Criteria 与十条不变量，并将 v1.0.5 作为不可变直接前序。
- 唯一当前状态权威是 `machine/status/latest.json`：本地机制证据完整，受保护 Oracle 0/43，
  最终 Acceptance 0/34，生产 Workflow 0，发布状态 `LOCAL_ONLY_NOT_PUBLISHED`。
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
25. Owner 授权后，候选 8 提交已无冲突重放到最新 `origin/main`
    `28605b86fdaa364346a7a491e074cc84320cd34c`；T0702 Run Contract 已改为一次性 protected
    执行合同，预算固定 1、Environment 无人工 reviewer、GitHub App 仅 `contents:write` +
    `metadata:read` 且只装一个私有仓。派生 34 Acceptance 仍为 0 PASS / 34 BLOCKED，
    protected Oracle 仍为 0/43；目标 `41 passed`、Package 587 files、Status、Governance pinned
    `ebc6c2e4884edc959118cfc56d0e18a86c49460f`、facts、Manifest 与 Stage 7 九项 scoped
    preflight 均 PASS。真实 Gmail、Secret、私有仓、Workflow dispatch 与 main delivery 尚未执行。

## 关键边界

- 依赖 Deploy Key 不等于生产 Secret；普通 CI 的 Gmail、数据仓和生产 Secret 读取仍为 0。
- GitHub-hosted 非生产预检不等于 protected Oracle、生产健康、部署、发布或最终 Acceptance。
- T0702 只允许 GitHub-hosted first attempt；rerun、自托管 runner、非 main、非 owner、错误 SHA/
  Workflow ref/Environment 必须在读取 Beta Secret 前 fail closed。
- public control logs 只能出现 bucket、零值计数和 gate 布尔值；不得输出精确 Beta 预算、精确邮箱/
  recovery 计数、message/thread/sender/subject/attachment 或私有仓标识。
- 当前候选已重放到最新 `origin/main`；只允许按 Owner 本次授权经一次 PR/merge 进入 `main`，不得
  直接向 `main` push，也不得进行第二次候选上传或 rerun。
- 预检任一 Workflow syntax、Governance checkout、Secret 边界、package、publication 或累计门失败，
  必须停止，不得扩大权限或读取生产 Secret。

## 下一步

1. 先独立核验 Owner 已创建的 `moomooau-beta` Environment，再配置 no-reviewer/main-only policy；
   建立或复用唯一私有数据仓与最小权限单仓 GitHub App；生成 age/opaque key、verified sender
   registry、Gmail OAuth 和 budget-one/fresh-capacity config，并只写入六项 Environment Secret。
2. 所有本地累计门与云端 pre-dispatch gate 通过后，经一次 PR/merge 进入 `main`，确认精确 merged
   SHA，再 dispatch 一次。任何 sender、权限、容量、私有性、Secret、Gmail 或恢复结果未知即停止；
   不审批、不 rerun、不读取未验证 RAW、不进行 Gmail mutation。
3. protected run 后只在本地更新 T0702 证据，不进行第二次 main 交付，不进入 M3。整体任务包完成后
   才做整体复审、修复与最终发布。
