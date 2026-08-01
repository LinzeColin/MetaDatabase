# SA-507 Phase E｜最终收束、发布前复核与单一源码发布 Run Contract

## 目标

在不改变已经通过本开发周期唯一一次完整应用回归的功能候选前提下，收束
SA-507 的历史与环境证据，复验冻结任务包和结构合同，合入当前 `origin/main`
的无冲突上游更新；仅当全部 blocking assertion 均为 `PASS` 时，将完整源码
以 `v0.0.0.4` 发布到 `main`。随后验证远端引用并清理由本 run 创建的临时材料。

## 冻结边界

- 当前工作树：`/Users/linzezhang/.codex/worktrees/acc9/MetaDatabase`；本 run
  不创建第二个 worktree。
- 工作分支和起始 HEAD：`codex/sa-507-compat-tomllib-fix` /
  `9fdf6de319d9d20be22c298c44bbef6b0f4d8320`。
- 已拉取的最新整合基线：`origin/main` =
  `6b15ed6cdf96bcb24353b8b5c60f4b2193fb9d6e`。只读比较确认其 8 个新增提交
  不触及 `social-archive/`；`git merge-tree --write-tree HEAD origin/main` 已返回
  成功，未发现冲突。
- 唯一完整应用回归的当前候选证据在
  `PHASE_C_THREE_TARGET_OBJECT_RECOVERY_20260801.json`：`235 passed`，失败 0，
  仅有 1 条既有、非失败的 Starlette/httpx 弃用警告。本 Phase 绝不传入
  `final_verify.py --full`，也不再次运行 pytest。
- 冻结任务包原件的 SHA-256 必须保持
  `31c3af6c551e93bd32bec48c0f18a5e4084452175b85bac59bcd4759b60617c6`。
- 已有源码回滚标签：`social-archive-pre-v0.0.0.4-20260730t095749z`；生产上
  Phase D 的 root-only 精确脚本备份也保留，不删除。

## 最小范围

允许：

1. 新增本 Contract、更新 SA-507 的最终 `RESULT.json`、`COMMAND_LOG.json`、
   `RELEASE_REPORT.json`、`evidence/final-verification.json`、必要的 changelog/
   handoff 说明；只记录脱敏状态、摘要、哈希和 Git 引用。
2. 只读/临时运行兼容层 synthetic 验证、临时兼容任务包 `verify-fast`、最终
   结构验证与生产安全 smoke。临时目录必须位于新建的精确临时目录中，并在
   本 Phase 结束前清理。
3. 在下述候选指纹前后一致时，执行一次 `git merge --no-ff origin/main`。若 Git
   报告冲突，立即 `git merge --abort`，不发布。
4. 在所有最终门通过后，stage/commit、创建 annotated `v0.0.0.4` tag、将该提交
   推送为 `origin/main` 及该 tag，并用远端 ref readback 验证。不会创建 GitHub
   Source Release、镜像发布或额外数据副本。

禁止：

- 改动 `src/`、`apps/`、`sidecars/`、Compose/Docker 输入、connector/destination
  行为、事务/恢复核心，或写入 Runtime、用户内容、Provider 对象、Private-Database；
- 读取、打印、复制或提交 secret、cookie、token、身份、用户内容或生产绝对路径；
- 启用 replication/private-database sync timer，重新执行 Provider upload/delete，
  或将本地任务包检查伪称真实 Provider 验收；
- `git reset --hard`、强推、删除任何受保护目录、全局 Docker/Git 清理，或处理
  他人 worktree 的 GC 提示。

## 候选不变性证明

在合并前，从 `git ls-files --cached --others --exclude-standard social-archive`
得到当前可交付文件清单，排除仅为说明/证据的 `social-archive/evidence/**`、
`social-archive/docs/**`、`social-archive/HANDOFF.md` 和
`social-archive/CHANGELOG.md`；逐文件 SHA-256 后对路径与摘要的有序清单再
计算 SHA-256，得到 `functional_candidate_manifest_sha256`。

合入 `origin/main` 后使用同一算法重新计算。二者的文件数与摘要必须相同；若
不相同，说明唯一完整回归不再对应当前候选，立即停止本 Phase，不发布，也不以
第二次完整应用回归规避单一 suite 约束。另须确认以共同祖先为起点的
`git diff --name-only $(git merge-base HEAD origin/main)..origin/main -- social-archive`
为空；不能把“本分支新增整个产品目录”误判为远端删除。

## 验证门与顺序

1. 审计 32 个 Task 的 `RESULT.json`、任务 DAG、冻结 ZIP 与 Phase A–D 证据；
   更新 SA-507 历史 `DEGRADED` 汇总，绝不将旧 `NOT_RUN` 伪改为 `PASS`。
2. 运行兼容 synthetic 验证；用全新临时输出调用 `prepare_compat_taskpack.py`，
   再在兼容包根目录执行 `START_HERE.py verify-fast`。该检查必须显示 application
   tests skipped，不得运行应用 pytest。
3. 运行 `social-archive/scripts/final_verify.py`（无 `--full`），并检查报告为
   `PASS`、`suite_mode=structural`、`application_suite_rerun=false`。
4. 生产只读复核：服务/镜像状态、loopback health、公开边缘的无凭据安全边界、
   以及两个 timer 仍 disabled。没有 Owner 登录会话的正向 Access/Pairing 继续
   明确记为不在本 Phase 伪造；已有 Phase D/SA-505 真实收据仍为其相应事实的
   证据来源。
5. 仅在上述每一项和 Phase A（真实三副本完成态）、Phase B（Private-Database
   facts）、Phase C（三目标恢复）、Phase D（部署 smoke）都为 `PASS` 时，合并、
   commit、tag、push 和远端 ref readback。

## 发布与回滚

- 发布前先确认本地与 `origin` 均不存在 `v0.0.0.4`；tag 必须为 annotated，且仅
  指向本 Phase 的最终源码提交。
- 推送使用快进式 `HEAD:main`，禁止 force；远端 main 与 tag peeled commit 必须
  都解析到同一最终提交。任一拒绝或不一致都停止，并保留本地提交/标签供诊断，
  不尝试改写远端历史。
- 发布后的源码回滚只允许明确确认后以已有 pre-release tag 制定非破坏性 rollback
  plan；不会删除 ignored runtime 或生产数据。生产服务、Root-only Phase D 备份和
  已验证三副本对象均不是本 Phase 的清理目标。

## 停止条件

任何秘密泄露、候选指纹漂移、应用/镜像输入变化、兼容或结构检查失败、生产暴露
边界漂移、计时器启用、远端不是预期仓库、tag 已存在、merge 冲突、任何
`UNKNOWN`/`NOT_RUN` 被要求当作 blocking PASS，或需要超出本 Contract 的功能
修改时立即停止。此时 SA-507 维持未发布状态，并仅报告可验证的失败边界。
