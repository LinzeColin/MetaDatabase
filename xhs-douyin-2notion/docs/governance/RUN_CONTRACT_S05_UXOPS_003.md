# Stage 5 Task003 Run Contract — Local WebUI and Owner Review

## Identity

- Task: `TSK.x2n.uxops.003`
- Phase: `PH.X2N.5.3`
- Run: `RUN-X2N-S05-U003`
- Acceptance: `ACC.x2n.ext.001`, `ACC.x2n.ai.005`, `ACC.x2n.ai.006`, `ACC.x2n.ops.004`

## Scope

本 Run 提供一个仅由 Local Companion 托管的本地 WebUI。服务只能绑定
`127.0.0.1`；没有 LAN listener、CORS、Cookie、外部脚本、外部图片或网络请求。所有写操作均须同时通过
精确 Host、精确 loopback Origin 与仅内存 CSRF token 验证。

界面提供 Dashboard、六平台 Source Settings、Owner Taxonomy、低置信度 Review、Job Detail、Markdown /
Notion 状态、Model Budget、数据生命周期和脱敏 Diagnostics Export。页面使用静态 shell 与受限 JSON API；不可信
内容只作为 JSON 数据或 DOM `textContent` 处理，绝不作为 HTML 执行。

Review 只能由 Owner 选择已有且启用的一级分类。每次确认或更正只追加 `human` Classification，必须附带已有
Artifact ID，且过期 review token、未知/禁用 Category、无证据条目全部 Fail Closed。AI 没有 Registry 写能力，
自动分类仍保持 disabled / suggestion-only。

活跃 CLI、运行时 Schema 与新证据使用 `owner-mvp-plan` 和 runtime nomenclature v2。已退休的 v1 名称不再
出现在活跃 help、alias、输出 key 或本 Task 证据中；旧 Stage 3 Evidence 保持逐字节不变，并通过固定
`a67ba091239297b5c9c38a349e0a839680d1c411` 的 disposable alternate-object-store replay 验证。该 replay
不创建 MetaDatabase worktree、不改变当前 HEAD，也不检查 v2 tree。

## Non-goals

- 不执行真实平台采集、账号、Chrome Profile、媒体、模型、Notion、上传、部署或发布；
- 不读取、显示、修改认证材料，或持久化 CDN URL、原始媒体、Cookie、Profile、绝对路径、正文或诊断原文；
- 不改变 Owner taxonomy 的一级归属边界，不让 AI 创建、启用、禁用、删除或合并一级分类；
- 不执行 Task004、Task005、Stage 5 Review、Stage 6 或最终 MVP 部署/运行/online smoke。

## Acceptance and stop conditions

- loopback listener、Host / Origin / CSRF、`nosniff` / CSP / no-CORS 必须全部可验证；
- 所有主要 UI 区域可访问，低置信度 Review 能追加 Owner confirmation，重放旧 token 必须拒绝；
- Dashboard、Job、Sink、Model 和 diagnostics 均不得含 private content、secret、CDN URL 或 private path；
- 诊断导出只允许 aggregate health/count/status/recovery facts；
- 若 UI 需要任意 HTML 执行、无法限制 loopback/origin，或任一活跃运行面仍暴露已退休 v1 名称，立即停止；
- 回滚是停用 `x2n webui serve`；原有 CLI 和 Chrome Side Panel minimal flow 不受影响。

## Validation

```bash
.venv/bin/python -B scripts/replay_adapters_005_historical.py
.venv/bin/python -B scripts/run_uxops_003_acceptance.py
.venv/bin/python -B scripts/verify_uxops_003.py --verify-worktree --allow-external-main-dirty --run-acceptance --require-evidence
PYTHONPATH=apps/companion/src:packages/contracts/src .venv/bin/python -B -m unittest apps.companion.tests.test_webui
```

Task 完成只授权下一单本地 `TSK.x2n.uxops.004`；不授权 G5、真实 Runtime、上传、部署或发布。
