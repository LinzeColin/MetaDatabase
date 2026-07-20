# Run Contract — Stage 1 Foundation 005

- Run ID：`RUN-X2N-S01-F005`
- 唯一 Task：`TSK.x2n.foundation.005`
- 唯一 Phase：`PH.X2N.1.5`
- Task base：`09d5cdf1993080401f99e023feb03be479baca27`
- `origin/main` cutoff：`7fd0768002081f27c070561fa855a08713d1bc00`
- Run kind：`single_dag_task`
- Stage gate：`G1=NOT_RUN`；本 Run 禁止远端上传

## 1. 目标

仅用公共安全合成数据，建立 x2n 的 changed-scope 快速门禁、full-release 候选流水线、
软件供应链与制品隐私门禁，以及模型评测 runner 骨架。所有 Blocking Gate 必须显式
执行或由可验证路径分类标记为不适用，不能静默跳过。

## 2. 最小相关范围

- 母仓库根唯一新增 `.github/workflows/x2n-ci.yml`；不修改其他项目工作流。
- 子项目新增 CI policy、runner、seeded-failure fixtures、coverage gate、SAST/SARIF、
  Secret/Private/CDN/Fixture/Artifact 扫描、OSV、License 与 SBOM。
- 建立只验证 Dataset Contract 的模型骨架；ASR/OCR/Fusion/Classify 和模型 Red Team
  执行均保持禁用或 `NOT_RUN`。
- 为后续 Task 向前兼容历史 Foundation verifier 的“追加 fixture/CI-only dependency”
  识别，但不改写历史 Acceptance 或证据。

## 3. 明确非目标

- 不实现或调用六平台 Adapter、Notion、模型、ASR、OCR、关键帧或分类功能。
- 不访问真实账号、Owner Chrome/Profile、Private Runtime、下载目录或真实媒体。
- 不启用 AI 自动分类；`ACC.x2n.ai.006` 未通过前固定关闭。
- 不执行 G1 Review，不进入 Stage 2，不 push、merge、rebase 或发布。
- 不读取、显示、使用、修改、删除或轮换任何共享认证材料。

## 4. Acceptance 解释

- `ACC.x2n.rel.001`：本地合成软件流水线需覆盖 format/lint/type/unit/contract/
  migration/integration/E2E；full lane 重放两次，Blocking failure、silent skip 和 flaky
  blocker 均为 0；每轮 3 个依赖 Owner 私有输入的非阻断 skip 必须逐 reason/count 命中
  机器 allowlist，任何新增或缺失均 Fail Closed；coverage 使用已登记的整体与关键模块风险阈值。
- `ACC.x2n.rel.002`：Versioned Dataset Contract 为 PASS；ASR/OCR/Fusion/Classify 为
  `NOT_RUN_FEATURE_DISABLED`，Red Team 为 `CONTRACT_PASS_MODEL_NOT_RUN`；失败降级为关闭
  对应能力并要求 Review，不能冒充模型质量验收。
- `ACC.x2n.rel.003`：当前 frozen locks 和临时 source candidate 的 SAST、Secret、OSV、
  SBOM、License、CSP、Artifact Allowlist 全部达到阈值。远端 Actions 和正式 Release
  仍为 `NOT_RUN`。

## 5. 验证命令

```text
npm ci --ignore-scripts
uv sync --frozen --all-packages --group ci
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/python scripts/ci/run_lane.py --lane fast --repetitions 1 --reports-dir build/ci-public
.venv/bin/python scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/ci-public
python3.12 -B scripts/verify_foundation_005.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B -m unittest discover -s tests -p 'test_*.py'
```

依赖安装、OSV 和浏览器下载只允许匿名公开网络；执行环境采用变量 allowlist，不继承
Token、Credential Helper、Keyring 或用户级包配置。CI 报告和 candidate 必须先通过
同一 Secret/Private/CDN/Artifact 扫描再允许上传为私有仓库 CI artifact。

## 6. 风险、回滚与停止条件

- 风险：本地绿但远端未知、路径分类漏跑、Actions 未固定、网络 OSV 未知、报告/ZIP
  泄露本机路径或 Runtime、阻断测试抖动。
- 回滚：删除候选 `x2n-ci.yml`，revert 本 Task 本地 commit；`build/` 和临时 HOME 可直接
  丢弃。没有产品 Runtime、数据迁移或账号状态需要回滚。
- 出现真实 Secret/账号/媒体依赖、Blocking Gate 可静默跳过、Critical/High 漏洞、
  Unknown License、Artifact Runtime Data、Secret/Private/CDN 命中或 worktree overlap，
  立即 `FAIL_CLOSED`。
