# xhs-douyin-2notion

把用户明确选择的小红书、抖音、哔哩哔哩、快手、微博和淘宝当前内容或个人列表批次，治理为可恢复、可分类、带 ASR/OCR/关键帧证据的 Markdown 与 Notion 知识资产。

项目名是稳定品牌，不是平台范围上限。六平台均采用独立 Policy/Auth/Technical Gate；未知即禁用。这里的在线采集不是通用爬虫：无自动滚动、无账号状态改变、无代理/指纹规避、无凭据或平台媒体 URL/原始媒体持久化。

当前状态：`v0.0.0.1 / Stage 1` 的 `TSK.x2n.foundation.001–005` 与独立 `STG.X2N.1.REVIEW` 已完成，`G1=PASS`，Stage 1 整体上传与下一独立 Stage 2 Task 已获授权，但 Stage 2 尚未开始。Review 修复 8 个 finding；两轮 full lane 的 24 次阻塞执行、Task Pack 固定版本差分、PR merge-parent 隔离、逐提交历史扫描、风险覆盖率、OSV、SAST、隐私扫描、制品白名单和确定性复现均通过。远端 GitHub Actions 仍为 `PENDING_POST_G1_UPLOAD`，最后提交的远端 x2n CI 通过前不得 merge。模型侧只验证 versioned Dataset Contract，ASR/OCR/Fusion/Classify/Red Team 模型执行和自动分类全部关闭。真实采集、账号访问、平台动作、Markdown/Notion、模型和媒体仍未实现；六平台与所有上游候选保持关闭。Owner 保留的外部共享认证材料不由 x2n 读取、使用或修改；与 MetaDatabase 其他长期开发采用零重叠 worktree 隔离，外部文件不进入本项目证据或提交。

## 固定边界

- 母仓库：`LinzeColin/MetaDatabase`
- 子项目：`xhs-douyin-2notion/`
- 下载目的地逻辑名：`X2N_DOWNLOAD_DESTINATION`；原始 taskpack 未指定本机绝对路径
- 数据根逻辑名：`X2N_DATA_ROOT=${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`（Runtime 与全部下载共用隔离命名空间；真实解析值不进 Git；已有同级条目不触碰）
- 路径名边界：下载父目录名不授权安装、运行或接入同名 `MediaCrawler` 上游
- 真相源：本地 SQLite Canonical Store
- 交互/执行：Chrome Side Panel / Local Companion
- 发布边界：Public Code / Private Runtime，专有许可

## v0.0.0.1 DAG

唯一机器真源是 [`docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml`](docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml)，范围仅为 Stage 0–6。每个普通 Run 最多一个 DAG Task 及其 Acceptance；Stage Review 不执行新 Task。每个 Stage 只有在全阶段复核、修复和重验后才允许上传。

## Stage 1 Review / G1 验证

```bash
npm ci --ignore-scripts
uv sync --frozen --all-packages --group ci
PLAYWRIGHT_BROWSERS_PATH=build/playwright-browsers npx --no-install playwright install chromium
.venv/bin/python -B scripts/ci/run_lane.py \
  --lane full --repetitions 2 --reports-dir build/g1-review
.venv/bin/python -B scripts/verify_stage_1_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/g1-review/software-lane.json --require-evidence
```

G1 只证明 Foundation001–005 的本地公共安全合成范围。机器证据位于
`machine/evidence/stage_1/review/`；远端 Actions、Owner Chrome、真实账号、平台、
Notion、模型、媒体和 Sink 均不因 G1 自动变为已运行。下一独立产品 Run 只能执行
`TSK.x2n.skeleton.001`。

## Foundation 005 历史范围验证

```bash
npm ci --ignore-scripts
uv sync --frozen --all-packages --group ci
.venv/bin/python scripts/ci/run_lane.py \
  --lane fast --repetitions 1 --reports-dir build/ci-public
.venv/bin/python scripts/ci/run_lane.py \
  --lane full --repetitions 2 --reports-dir build/ci-public
python3.12 -B scripts/verify_foundation_005.py \
  --verify-worktree --allow-external-main-dirty --require-evidence
```

full lane 包含 format/lint/type/unit/contract/migration/integration/Extension E2E、风险覆盖率、
SAST/SARIF、Secret/Private/CDN/Fixture、OSV、33-component SBOM、License、CSP 与临时
source candidate allowlist。CI 使用完整 SHA 固定 Actions、最小 `contents: read` 权限，
不读取共享认证环境。Foundation005 的历史证据保持 `G1=NOT_RUN`；当前 G1 结论只来自
后续独立 Stage 1 Review 证据，远端运行仍待整阶段上传后完成。

## Foundation 004 验证

```bash
npm ci --ignore-scripts
python3 -B scripts/verify_foundation_004.py \
  --verify-worktree --allow-external-main-dirty --require-evidence
python3 -B -m unittest tests.test_foundation_004
```

门禁执行 20 个公共合成页面、五区 Side Panel、临时 Native Host 注册、24 个
Companion tests 与 100 次真实 Service Worker 终止/重启；SQLite 是唯一任务状态源。
截图和 trace 仅生成在临时目录，Git 证据只保存大小与 SHA-256。Owner Chrome、共享
Profile、真实账号与平台请求均不参与。Playwright 测试栈已进入独立 30-component
SBOM；可选 `fsevents` 的 install script 由 `.npmrc` 和验收命令共同禁止执行。

安装器默认只输出不含路径的计划；以下命令只是计划，不写入任何 Host：

```bash
X2N_DOWNLOAD_DESTINATION="$X2N_DOWNLOAD_DESTINATION" \
X2N_DATA_ROOT="$X2N_DATA_ROOT" \
PYTHONPATH="apps/companion/src:packages/contracts/src" \
python3.12 -B -m x2n_companion.native_host_installer plan --browser chrome
```

Owner 长期安装、卸载和 Canary 尚未授权，不应执行 `install`/`uninstall --confirm`。

## Foundation 003 历史范围验证

```bash
python3.12 -B scripts/verify_foundation_003.py --verify-worktree --allow-external-main-dirty
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

完整门禁使用 80 条合成输入连续两次、100 个并发重复消息和 10k 合成 DB，验证
SQLite WAL/FK/Unique/append-only、Outbox、Lease、迁移降级、备份 Hash、恢复后逻辑
摘要与 `integrity_check`。Markdown、Notion、Owner Alpha、Release 与异地灾备仍为
`DOWNSTREAM_NOT_RUN`。

Owner 私有空库初始化及复验必须显式提供逻辑环境变量，输出不得包含解析路径：

```bash
X2N_DOWNLOAD_DESTINATION="$X2N_DOWNLOAD_DESTINATION" \
X2N_DATA_ROOT="$X2N_DATA_ROOT" \
PYTHONPATH="apps/companion/src:packages/contracts/src" \
python3.12 -B -m x2n_companion.runtime_cli init

python3.12 -B scripts/verify_foundation_003.py \
  --verify-worktree --allow-external-main-dirty --validate-owner-runtime
```

## Foundation 002 历史范围验证

```bash
python3.12 -B scripts/verify_foundation_002.py --verify-worktree --allow-external-main-dirty
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

该门禁验证 14 类版本化 Contract、24 个错误码、144 个合成/模糊用例、精确依赖
SBOM 与 TypeScript strict compile；当前 DB 实现由 Foundation003 独立门禁证明，
不能倒推为 Foundation002 当时已经实现。

## Foundation 001 历史范围验证

```bash
python3.12 -B scripts/verify_foundation_001.py --verify-worktree --allow-external-main-dirty
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

`SKILL.md` 中的 install/Canary/upgrade/rollback 命令仍只验证纯合成 scaffold；它们不安装或操作真实产品，产品 lifecycle 仍是 `DOWNSTREAM_NOT_RUN`。

## Phase 0.1 验证

以下 Phase 0.1–Stage 0 Review 命令是历史 Runbook，`--verify-worktree` 严格绑定当时
的 Phase/Review branch 与 cutoff；不得直接把它们当作当前 Stage 1 worktree 门禁，
也不得为追求绿色而放宽历史证据。当前 Stage 1 使用 Foundation verifier、根回归与
未改写的历史 Evidence 共同复核。

```bash
python3 -B scripts/verify_phase_0_1.py --verify-worktree --allow-external-main-dirty --verify-local-root
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Owner 本机还须显式传入私有根目录执行本地边界验证；命令和真实路径仅保存在本地 Run 记录，不写入仓库。

## Phase 0.2 验证

```bash
python3 -B scripts/verify_phase_0_2.py --verify-worktree --allow-external-main-dirty --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

私有上游快照只在 Run 内用于复核 Git 对象与哈希，验收后必须清理；公开证据不包含真实本地路径、凭据或上游源码。

## Phase 0.5 验证

```bash
python3 -B scripts/verify_phase_0_5.py --verify-worktree --allow-external-main-dirty --validate-owner-input "$X2N_DATA_ROOT" --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

## Stage 0 Review Resume 验证

```bash
python3 -B scripts/verify_stage_0_review.py --verify-worktree --allow-external-main-dirty --verify-local-root --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK" --require-evidence
python3 -B scripts/verify_stage_0_review_resume.py --expect-g0 pass --verify-worktree --allow-external-main-dirty --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK" --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

首次 Review 的历史 Blocked 结论见 [`docs/governance/STAGE_0_REVIEW.md`](docs/governance/STAGE_0_REVIEW.md)，当前 Resume 结论见 [`docs/governance/STAGE_0_REVIEW_RESUME.md`](docs/governance/STAGE_0_REVIEW_RESUME.md)。历史证据未重写；当前 G0 PASS 来自独立 Resume 证据。

恢复动作使用闭合的私有 Owner Attestation 契约；验证命令如下：

```bash
python3 -B scripts/verify_owner_recovery_attestation.py
```

私有回执本身仍只授权 Review Resume，不直接授权 G0、Stage 1 或上传；最终授权以完整 Resume 机器门禁为准。共享外部材料的 Owner 保留决定不会覆盖 x2n 内 Secret/CDN 不可豁免规则。

以上 `--allow-external-main-dirty` 只用于 Owner 已明确要求的长期并行情形，并要求外部 dirty paths 与 x2n 零重叠；正常 clean-main 场景应省略此参数，默认严格门禁保持不变。
