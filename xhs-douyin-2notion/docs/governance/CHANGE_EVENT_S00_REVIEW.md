# Change Event — CE-X2N-20260720-S00-REVIEW

## 触发与授权来源

Owner 的 Pursuing Goal 明确要求“每次只执行一个 Task 及其 Acceptance”，并要求 x2n 与 MetaDatabase 内长期开发互不污染、持续并行。Stage 0 Review 还发现旧产品文件残留可能把下载父目录误解为 MediaCrawler 上游授权。

本 Change Event 只纠正 Stage 0 治理与未来执行边界，不授权 Stage 1、产品代码、真实账号、平台/Notion/模型调用、媒体下载或远端上传。

## 变更

1. 普通 Run 从“最多一个 Phase”收紧为“最多一个 DAG Task 及其 Acceptance”；Stage Review 是不执行新 Task 的专用 Run。
2. Phase 0.1 历史 Run 曾一次完成 discovery.001–003，属于流程粒度不符合项。历史提交和 receipt 不重写；本 Review 逐 Task 复核输出/证据并增加未来机器门禁。
3. 删除 `MediaCrawler` 产品 Adapter Feature Flag 与“外部安装”残留措辞；其固定 Commit 仅保留不可执行历史审计证据。
4. Stage Review 使用显式 `origin/main` cutoff；cutoff 后无关长期提交不吸收，只有 x2n 或其父级索引语义发生重叠才阻断。
5. 增加独立 Review verifier、G0 状态 schema 和 fail-closed receipt；未关闭的 `before_g0_pass` Owner Action 必须阻断 G0。

## 不变事实

- 母仓库/子项目仍为 `LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`。
- 原始 roadmap/ZIP 哈希与 7 个成员保持不变；原始输入没有指定本机绝对下载路径。
- 六平台终态范围不变，当前仍全部 `UNKNOWN_DISABLED`。
- Public Code / Private Runtime、SQLite Canonical Truth、无 CDN/凭据/原始媒体持久化、AI 不创建一级分类等永久边界不变。

## 验收与回滚

- 验收：Review/三个 Phase verifier、全量单测、原始输入、私有根、changed-scope、历史 receipt 和负向 G0 测试全部通过。
- 回滚：仅回滚本 Change Event 之后的 review 治理文件；不得恢复“一 Run 一个 Phase”或 MediaCrawler 产品语义。
- 当前结论：`REVIEW_COMPLETE / G0_BLOCKED_OWNER_ACTION`；不得 push 或进入 Stage 1。
