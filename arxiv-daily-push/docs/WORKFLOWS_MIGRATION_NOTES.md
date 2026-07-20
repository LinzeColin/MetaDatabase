# arxiv-daily-push 工作流迁移说明（2026-07-20）

本项目连同其 **10 个 GitHub Actions 工作流**已从 `LinzeColin/CodexProject` 迁入 `LinzeColin/MetaDatabase`。
代码迁移经 `git filter-repo` 保留完整历史（tree sha 位级一致、2132 文件、801 条提交可 `git log -- arxiv-daily-push` 追溯）。

## 迁移时的关键判定：**不需要配置任何 secrets 或 variables**

迁移前实测确认，当前**没有任何正在运行的作业消费 SMTP 凭据**：

- `arxiv-daily-push-scheduled.yml` 的发信作业被 gate 挡住：`if [ "${{ vars.ADP_PRODUCTION_ENABLED }}" = "true" ]`，
  而 **`ADP_PRODUCTION_ENABLED` 在源仓从未设置** → 近三次定时运行均为 `gate: success` / `scheduled: skipped`。
- 真正在自动运行且正常的三个工作流 —— `liveness`（每日巡夜）、`stage1-bootstrap`（push）、`visual-gate`（push）
  —— **不使用任何 `vars.*` 或 `secrets.*`**。

因此本次按「**不设变量、不配密钥**」原样搬迁，精确复制源仓当前「生产发信已关闭」的安全姿态。

## 若将来要启用生产发信，需要先做（Owner 操作）

1. 在本仓配置 4 个 secrets：`ADP_SMTP_HOST` / `ADP_SMTP_PORT` / `ADP_SMTP_USERNAME` / `ADP_SMTP_PASSWORD`。
   > GitHub secrets **只写不可读**，源仓的值无法导出；须从原始凭据来源重新取得。
2. 配置 `scheduled` 所需的 variables（源仓已设过的：`ADP_ALLOW_SMTP_SEND` / `ADP_ALLOW_RELEASE_UPLOAD` /
   `ADP_ARXIV_MAX_RESULTS` / `ADP_RELEASE_TARGET` / `ADP_TEXT_DEGRADATION_VERIFIED` / `ADP_VIDEO_DEGRADATION_VERIFIED`）。
3. 最后才设 `ADP_PRODUCTION_ENABLED=true` 这个总开关。
4. 此举等同启用 SMTP/scheduler，须走 ADP 自有的 Email V1 contract/readiness gate 与 owner 持久授权流程
   （见 `docs/HANDOFF.md`），不得绕过。

## 随迁的根级依赖

`liveness` 依赖两个原本在 CodexProject **根级**、不在 `arxiv-daily-push/` 内的文件（filter-repo 不会带走），已一并迁入：

- `scripts/adp_liveness_check.py`
- `tests/governance/test_adp_liveness_check.py`

## 既有悬空引用的迁移闭合状态

迁移前源仓已有两处悬空引用。本轮只闭合由仓位变化造成、可以无生产副作用修正的一处：

| 工作流 | 悬空引用 | 状态 |
|---|---|---|
| `production-trial` | `scripts/validate_project_governance.py` | 已改为当前 `machine/tools/check_dual_plane_ci.py`，并显式运行 supply-chain security regression；未启用或运行 production trial。 |
| `visual-gate` | `arxiv-daily-push/docs/design/visual_change_approvals.json` | **该文件在源仓 CodexProject 中同样不存在**，是 visual-gate 在源仓即持续 failing 的既有原因，非迁移引入。 |

## 生产运行时不受迁移影响

生产是 Cloudflare Worker `adp-cloud`（`adp.linzezhang.com`），已部署且不依赖仓库路径，迁仓不影响线上。
`deploy/cloudflare/worker_cloud.js` 在整个迁移过程中**零字节改动**，自哈希漂移守卫（BUILD 常量须与线上 `/build.json` 一致）未失效。
