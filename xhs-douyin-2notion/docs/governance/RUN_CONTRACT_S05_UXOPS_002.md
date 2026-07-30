# Stage 5 Task002 Run Contract — Markdown Library Hardening

## Identity

- Task: `TSK.x2n.uxops.002`
- Phase: `PH.X2N.5.2`
- Run: `RUN-X2N-S05-U002`
- Acceptance: `ACC.x2n.md.001`–`.002`

## Scope

本 Run 只加固可删除重建的本地 Markdown Library。Canonical Content 永远固定在
`runtime/library/content/<platform>/<content_id>.md`；分类只生成
`runtime/library/categories/<category_slug>/INDEX.md` 的相对链接，不产生内容副本。

实现从一次 SQLite 只读事务取得完整 Canonical/Relation/Observation/Artifact/Classification
快照。调用方显式提供私有文本投影，重建本身不写 Canonical、不写 Outbox、不创建分类，也不接触
真实运行时数据。每个内容和 Index 都以 `0600` 原子替换；目录为 `0700`；symlink、非受管路径、
竞争投影、死链、重复链接、非确定性 Manifest 或不一致 Renderer Version 一律 Fail Closed。

Renderer 与 Sink Schema 升至 `1.1.0`，Content 与 Index frontmatter 都显式记录
`renderer_version`。重建完成后必须以内容/Index 哈希 Manifest 比较、全量 Link Checker、零重复
Canonical 内容副本和第二次零写入证明幂等。

## Non-goals

- 不执行真实平台采集、账号、Chrome、媒体、模型、Notion、上传、部署或发布；
- 不读取、显示、修改认证材料；
- 不持久化媒体 CDN URL、原始媒体、Cookie、Profile、绝对路径或真实内容；
- 不创建、改名或合并 Owner 一级分类；分类变化只消费现有 Canonical/Owner 投影；
- 不执行 Task003、Task004、Task005、Stage 5 Review 或 Stage 6。最终唯一 MVP 的部署、运行和
  online smoke 仍由 `TSK.x2n.assurance.005` 执行，不设置 Alpha、Beta、固定观察或 soak 阶段。

## Acceptance and stop conditions

- 六平台固定 `platform/content_id` 路径，标题、类别、类别重命名/合并/重分类均不得移动 Canonical 文件；
- Content/Index Frontmatter 必须可解析，Renderer Version 一致，长 Transcript/OCR 和特殊字符保持确定性；
- 10,000 条合成 SQLite Canonical 输入的删除派生目录后全量重建 Manifest 必须完全一致；
- Index 仅能有相对 Canonical 链接，死链和重复链接为 `0`，内容副本为 `0`；
- kill 位于原子替换前后时，文件只能保持旧完整版本或新完整版本，重放后恢复 Index；
- 任一路径依赖标题/类别、需要 CDN、修改 Canonical/Outbox、出现非受管文件或证据不完整时立即停止；
  回滚仅删除 `runtime/library/` 派生目录并从 Canonical 重建。

## Validation

```bash
.venv/bin/python -B scripts/verify_uxops_001.py --verify-worktree --allow-external-main-dirty --require-evidence
.venv/bin/python -B scripts/run_uxops_002_acceptance.py
.venv/bin/python -B scripts/verify_uxops_002.py --verify-worktree --allow-external-main-dirty --run-acceptance --require-evidence
PYTHONPATH=apps/companion/src:packages/contracts/src .venv/bin/python -B -m unittest apps.companion.tests.test_sinks
```

Task 完成只授权下一单本地 `TSK.x2n.uxops.003`；不授权 G5、真实 Runtime、上传、部署或发布。
