# xhs-douyin-2notion

把用户明确选择的小红书、抖音、哔哩哔哩、快手、微博和淘宝当前内容或个人列表批次，治理为可恢复、可分类、带 ASR/OCR/关键帧证据的 Markdown 与 Notion 知识资产。

项目名是稳定品牌，不是平台范围上限。六平台均采用独立 Policy/Auth/Technical Gate；未知即禁用。这里的在线采集不是通用爬虫：无自动滚动、无账号状态改变、无代理/指纹规避、无凭据或平台媒体 URL/原始媒体持久化。

当前状态：`v0.0.0.1 / Stage 1` 的 `TSK.x2n.foundation.001–003` 已分别完成 scaffold、`1.0` Contract 与 SQLite Canonical Store；Stage 0 已合并且 `G0=PASS`，但 `G1=NOT_RUN`，Stage 1 不得上传。当前具备严格 Contract、Schema v2、FK/Unique/append-only、Request Ledger、Outbox/Lease、Migration 和本地 Backup/Restore；Owner 私有根仅初始化空库，没有真实内容。真实采集、账号访问、浏览器行为、Native Host/Worker、Markdown/Notion、模型和媒体仍未实现。六平台与所有上游候选保持关闭。Owner 保留的外部共享认证材料不由 x2n 读取、使用或修改；与 MetaDatabase 其他长期开发采用零重叠 worktree 隔离，外部文件不进入本项目证据或提交。

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

## Foundation 003 验证

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
