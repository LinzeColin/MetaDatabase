# HANDOFF

## 当前目标

按 v0.0.0.1 Task DAG Stage 0–6 构建 `LinzeColin/MetaDatabase` 下唯一子项目 `xhs-douyin-2notion/`。终态覆盖小红书、抖音、哔哩哔哩、快手、微博和淘宝，但始终是 Owner 明确选择内容的个人知识治理，不是通用爬虫。

## 当前状态

- `TSK.x2n.discovery.001–005` 与 Stage 0 Phase 0.1/0.2/0.5：完成。
- 首次 `STG.X2N.0.REVIEW`：历史结论 `BLOCKED_OWNER_ACTION`，原报告与 3 份机器证据保持不变。
- `STG.X2N.0.REVIEW.RESUME`：完整复验通过；当前 `G0=PASS`。
- Stage 0 整阶段已通过 PR #66 合并；G0 历史/Resume 证据保持不变。
- Stage 1：`TSK.x2n.foundation.001–003` 已分别完成 scaffold、`1.0` Contract 与 SQLite Canonical Store；`G1=NOT_RUN`，不得 push。
- 下一独立 Run：只执行 `TSK.x2n.foundation.004` / `PH.X2N.1.4`。
- 真实账号、Chrome 控制、六平台调用、Notion、模型、媒体与全部下游用户旅程 Acceptance：`NOT_RUN`。
- 六平台：全部 `UNKNOWN_DISABLED`；各平台实现开始时重新通过 Policy/Auth/Technical Gate。

## Resume 关键决策

1. Owner 要求保留供其他并行工作使用的外部共享 GitHub 认证材料，并接受其外部残余风险。
2. x2n 对该材料零读取、零请求、零显示、零持久化、零使用、零修改、零删除/轮换/撤销，也不修改全局 Git 配置或 Credential Helper。
3. 这不是 Secret Presence Waiver；认证材料、Cookie、认证 Remote 或平台媒体 CDN 值一旦进入 x2n Repo、History、Runtime、Evidence 或 Artifact，仍立即 Fail Closed。
4. 未来公开源码研究只允许 `scripts/public_source_snapshot.py`：匿名 HTTPS、隔离 HOME、最小环境、禁用 global/system Git config 与 Credential Helper，审计后删除。
5. 与其他长期开发线继续使用独立 worktree 和 Review cutoff；cutoff 后只检查 x2n overlap，不吸收无关提交。

## 证据与验证结果

- Owner 回执：私有 `0600` 闭合回执通过；公开证据不含 ID、时间、哈希、账号、URL、本机路径或材料值。
- G0 Resume 签发时的树、历史、私有根、x2n Local Remote 与产品/Runtime 引用快照：全部 0 命中；该历史证据未被 Stage 1 重写。
- 历史 Phase receipt：20 份，未重写；原 Review receipt：3 份，仍记录首次 Blocked 事实。
- 原始 roadmap/ZIP：固定 SHA-256 匹配；ZIP CRC/7 成员保持通过。
- cutoff 后 `origin/main` 漂移只做聚合复验；x2n overlap 0，不吸收外部提交。
- Resume 证据：`machine/evidence/stage_0/review_resume/{verification,G0,owner_decision}.json`。
- 人类报告：`docs/governance/STAGE_0_REVIEW_RESUME.md`。
- Foundation 001 证据：`evidence/foundation/TSK.x2n.foundation.001.json`；只证明当前 scaffold 范围。
- Foundation 002 证据：`evidence/contracts/TSK.x2n.foundation.002.json`；只证明当前 Contract/合成范围，真实 Host/SQLite/Sink 为下游未运行。
- Contract：14 类生成 JSON Schema、同源 Pydantic/TypeScript types、24 个稳定错误码；16 valid + 22 invalid + 106 fuzz，共 144 个合成用例。
- npm/uv locks：5 个 Python Runtime registry packages、21 个 TypeScript build-only registry packages；26-component SBOM，npm install script 为 0。
- Foundation 002 verifier：含 12 个 Pydantic Contract tests、TypeScript strict compile、Python↔TypeScript payload-hash vector、生成物/SBOM 漂移与 worktree 隔离，全部 PASS。
- Foundation 003：SQLite Schema v2 含 17 tables、9 indexes、15 triggers；WAL/FK/FULL synchronous/busy timeout、DB 层 Unique/append-only/delete protection、Request Ledger、Outbox/Receipt、Lease、Migration 与本地 Backup/Restore 已实现。
- Foundation 003 合成验收：13 Store tests；80 条连续两次、100 个并发重复、10k DB、Hash mismatch、2→1→Restore 2 全部通过；重复副作用、数据丢失、不可读记录、orphan FK 均为 0，`integrity_check=ok`。
- Owner Private Runtime：Schema v2 空库已初始化；Content/账号/下载/媒体/Sink 记录为 0；DB/marker 权限 Owner-only，解析路径未进入 Repo/Evidence。
- 当前根回归：67 tests 全部通过；显式 Owner root 后仅私有上游 snapshot 的 1 项测试按设计跳过。Foundation001/002 历史 Task verifier 与现有证据均重新通过。
- Fresh copy：隔离 HOME 中 frozen locks、Extension 与 7 个 lifecycle rehearsal 加 1 个负向 Canary 均通过。

```bash
python3.12 -B scripts/verify_foundation_001.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B scripts/verify_foundation_002.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B scripts/verify_foundation_003.py --verify-worktree --allow-external-main-dirty --validate-owner-runtime --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

历史 Stage 0 的完整 `--verify-worktree` 命令严格绑定原 Phase/Review branch 与 cutoff，
不应从当前 Stage 1 worktree 运行或为求绿色而放宽。当前 Run 通过根回归复核其核心规则，
并保留原始 Phase/G0 机器证据；需要重放历史完整命令时应在对应归档 worktree 按原
Run Contract 执行。

## 不变边界

- 母仓库/子项目：`LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`。
- `X2N_DATA_ROOT=${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`；Runtime 与全部下载共用该隔离根；真实解析路径不进 Git。
- 下载父目录名只代表存储位置，不授权 MediaCrawler 安装、运行、接入或输出导入。
- Public Code / Private Runtime；专有许可；SQLite Canonical Store 是唯一真相源；Markdown/Notion 为可重建 Sink。
- 当前 Owner Store 只含 Schema/Migration ledger 空库；同盘 Backup 只证明本地恢复能力，不是异地灾备。
- 不持久化平台媒体 CDN URL、凭据、Cookie、浏览器状态或原始媒体；AI 不创建一级分类；不自动滚动、不改变账号状态、不绕过平台控制。
- `ShilongLee/Crawler` 与 MediaCrawler 仅固定 Commit 的不可执行研究证据：不复制、不 Vendor、不安装、不运行、不接收输出、不作 Runtime Dependency。

## 下一步

1. 保留本地 foundation.001–003 commits，不 push；Stage 1 只有 G1 Review/Fix/Re-acceptance 通过后才整阶段上传。
2. 另开单 Task Run：`TSK.x2n.foundation.004` / `PH.X2N.1.4`，实现 MV3 Side Panel 与 Native Host skeleton；不得顺带实现 foundation.005。
3. 继续保持共享认证材料零接触、其他长期开发零重叠；任一 Secret/CDN/Runtime/越界写入命中立即 Fail Closed。
