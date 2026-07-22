# HANDOFF

## 当前目标

按 v0.0.0.1 Task DAG Stage 0–6 构建 `LinzeColin/MetaDatabase` 下唯一子项目 `xhs-douyin-2notion/`。终态覆盖小红书、抖音、哔哩哔哩、快手、微博和淘宝，但始终是 Owner 明确选择内容的个人知识治理，不是通用爬虫。

## 当前状态

- `TSK.x2n.discovery.001–005` 与 Stage 0 Phase 0.1/0.2/0.5：完成。
- 首次 `STG.X2N.0.REVIEW`：历史结论 `BLOCKED_OWNER_ACTION`，原报告与 3 份机器证据保持不变。
- `STG.X2N.0.REVIEW.RESUME`：完整复验通过；当前 `G0=PASS`。
- Stage 0 整阶段已通过 PR #66 合并；G0 历史/Resume 证据保持不变。
- Stage 1：`TSK.x2n.foundation.001–005` 与独立 `STG.X2N.1.REVIEW` 已完成；8 个 finding 全部关闭，当前 `G1=PASS`，Stage 1 整体上传与 Stage 2 下一 Task 已授权。
- Stage 1 已通过 PR #73 合并到 `main`，远端 PR 与合并后 x2n CI 均通过；历史 G1 Evidence 不改写。
- Stage 2 已完成六个独立单 Task：`TSK.x2n.skeleton.001/.002/.006/.007/.008/.009`（Phase 2.1–2.6），均仅为 CI 合成 scoped pass；当前 Skeleton009 分支为 `codex/xhs-douyin-2notion-v0001-s02-skeleton009`，Task base 为 `7e8a3dbf…`、origin cutoff 为 `6777c8fc…`。
- 小红书当前页代码、5 个 DOM Fixture、Action/临时 `activeTab`、Native Host/SQLite 闭环与 100 次 Worker restart 已通过；能力位仍为 `ci_synth_only`，真实页面禁用。
- 抖音当前页代码、8 个 DOM Fixture 与 16 个合成短链 redirect 用例通过；短链核心无生产 transport，Extension/Companion 不联网解析，真实页面、真实短链和 Owner Canary 均禁用。
- 哔哩哔哩当前页代码、10 个 DOM、8 个 Policy 与 5 个 schema-drift rejection 通过；文章公开路由未由当前 Open Platform 文档证明，`?p=` 分 P Fail Closed，真实页面/API 与 Owner Canary 均禁用。
- 快手当前页代码、8 个 DOM、10 个 Policy、2 个 `BLOCKED_AUTH` 与 5 个 schema-drift rejection 通过；官方只证明 `user_video_info` 下授权用户已发布作品和 `photoId`，公开路由仍为未验证合成假设，真实页/API transport/DOM fallback 与 Owner Canary 均关闭。
- 微博当前页代码、8 个 DOM、12 个 Policy、2 个 `BLOCKED_BUDGET`、16 个任意 URL/Redirect-SSRF rejection 与 7 个 schema-drift rejection 通过；官方 `statuses/show` 只证明 OAuth 授权用户本人发布内容读取，本应用预算为 0，价格、Scope 与配额未获批准，公开路由仍为未验证合成假设，真实页/API/CLI transport、OAuth 输入、DOM fallback 与 Owner Canary 均关闭。
- 淘宝当前页代码、8 个 DOM、14 个 Policy、2 个 Scope/Retention 未知拒绝、16 个未文档化 Cookie/MTop 签名输入拒绝与 7 个 schema-drift rejection 通过；官方只证明需授权的增值 `taobao.item.get`、OAuth/TOP 协议及删除义务，本应用无 App/OAuth/API/付费/字段范围/保留期/删除回执审批，真实页/TOP API/DOM fallback 与 Owner Canary 均关闭。
- Skeleton001 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；105 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，54-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton002 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；112 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，56-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton006 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；122 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，57-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton007 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；131 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，58-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton008 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；140 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，59-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton009 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；149 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，60-member source candidate 确定性一致且 Runtime Data 0。
- 回归捕获并修复 SQLite transient `-wal/-shm` 在并发连接关闭时消失的 chmod 竞态；只豁免已经消失的 sidecar，Canonical DB 或仍存在 sidecar 的加固失败继续 Fail Closed。
- 当前 `G2=NOT_RUN`、Stage 2 上传禁止；下一独立产品 Run 只能执行 `TSK.x2n.skeleton.003`（`PH.X2N.2.7`）。
- 真实账号、Owner Chrome/Profile、六平台调用、Notion、模型、媒体与全部下游用户旅程 Acceptance：`NOT_RUN`。
- 六平台真实执行：全部 `UNKNOWN_DISABLED`、`BLOCKED_AUTH` 或 `BLOCKED_BUDGET`；六平台均仅 `current_page=CI_SYNTH_ONLY`；各平台真实启用时重新通过 Policy/Auth/Technical/Canary Gate。

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
- Foundation 003 合成验收：固定提交历史为 13 Store tests；当前为 14（新增 transient SQLite sidecar 竞态回归）；80 条连续两次、100 个并发重复、10k DB、Hash mismatch、2→1→Restore 2 全部通过；重复副作用、数据丢失、不可读记录、orphan FK 均为 0，`integrity_check=ok`。
- Owner Private Runtime：Schema v2 空库已初始化；Content/账号/下载/媒体/Sink 记录为 0；DB/marker 权限 Owner-only，解析路径未进入 Repo/Evidence。
- Foundation 004：固定开发 Extension ID，权限只含 `activeTab`/`nativeMessaging`/`sidePanel`，Host Permission 为 0；五区 Side Panel 与 20/20 六平台合成 URL 识别通过，所有平台动作保持禁用。
- Native Host：精确单 Origin、短进程 stdio、1 MiB 上限、严格 Contract；固定 Foundation004 历史为 24 个 Companion tests，当前 25 个覆盖 Origin/Schema/Action/Size/Injection、100 个并发重复、transient SQLite sidecar 竞态、payload-free SQLite Job、unowned 文件拒绝与 installer 首次/升级失败回滚。
- 隔离 Chromium E2E：临时 HOME/Profile/Runtime/Host 注册；100 次真实 Service Worker 终止/重启，任务丢失/重复/错状态和 uncaught console error 均为 0；Owner Chrome/Profile/Canary 未运行。
- Foundation 004 供应链：当前 SBOM 30 components；Playwright `1.61.1` 精确锁定；可选 `fsevents` install script 由 `.npmrc` 和验收命令禁用，执行数 0。历史 Foundation002 SBOM 保持 26-component 原事实。
- Foundation 005：changed-scope/full-release candidate CI 已建立；Actions 全 SHA pin、最小权限且 checkout 不持久化凭据。full lane 本地两次重放，format/lint/type/unit/contract/migration/integration/E2E、风险覆盖率和 seeded-failure 均通过；silent Blocking skip/failure/flaky 为 0，3 个公开 CI 无私有输入的显式非阻断 skip 每轮按固定 reason/count allowlist 验证（full 共 6）；远端 Actions 未运行。
- Foundation 005 Assurance：当前 33-component SBOM、Unknown License 0、匿名 OSV vulnerability 0、SAST Critical/High 0、Secret/Private/CDN/Fixture/Artifact Runtime Data 0；确定性 source candidate 只在 ignored build/临时目录生成并扫描。
- Stage 1 Review：关闭 8 个 finding；DAG/Task State/G1 Fact 一致，Task Pack 只允许精确 Review 状态差分，PR 合成 merge 只选择唯一继承 Foundation005 的父提交，duplicate JSON key 被拒绝，full lane 记录精确 24 项 gate/repetition/status，Runtime CLI 不再硬编码动态 Gate。
- G1 独立复验：全新 frozen npm/uv 环境与隔离 Chromium；12 门禁×2 共 24/24 PASS，blocking failure/flaky/silent skip 均 0；overall combined coverage 70.88%，7 个关键模块过阈值；OSV 查询 33 个依赖、漏洞 0。
- Review 证据：5 份 Foundation 历史 receipt 与固定提交逐字节一致；Stage 1 提交消息、逐提交变更 blob、当前 Source 与根 workflow 的 Secret/Private/CDN 扫描 0 命中；53-member candidate 无 Runtime Data 且两次 Hash 一致。
- Review 机器证据：`machine/evidence/stage_1/review/{findings,verification,G1}.json`；人类报告：`docs/governance/STAGE_1_REVIEW.md`。本地 `G1=PASS`，远端 x2n CI 尚待上传后运行。
- Model baseline：`x2n-synthetic-model-contract-v1@1.0.0` Dataset Contract PASS；ASR/OCR/Fusion/Classify 为禁用且 NOT_RUN，Red Team 只过合同，自动分类等待 `ACC.x2n.ai.006`，模型调用 0。
- Skeleton001：5/5 公共合成 DOM 通过；3 个 ready 的稳定 ID/Host/Path/标题/null/类型完全匹配，2 个改版或 feed-card Fixture 返回 `platform_changed`；Query/Fragment、媒体/raw DOM 持久化为 0。
- Skeleton002：8/8 公共合成 DOM 通过；4 个 ready、4 个 `platform_changed`；16 个短链 redirect 用例中 3 个 canonical resolved、13 个 fail-closed。短链、Query/Fragment、媒体/raw DOM 持久化为 0，生产网络 transport 与平台调用为 0。
- Skeleton006：10/10 公共合成 DOM、8/8 Policy 与 5/5 schema-drift rejection 通过；5 个 ready、5 个 `platform_changed`；稳定 ID/Canonical Host/Path 100%，Query/Fragment、媒体/raw DOM 与平台调用为 0。
- Skeleton007：8/8 公共合成 DOM、10/10 Policy、2/2 `BLOCKED_AUTH` 与 5/5 schema-drift rejection 通过；4 个 ready、4 个 `platform_changed`；稳定 `photoId`/Canonical Host/Path 100%，Query/Fragment、Cookie、媒体/raw DOM 与平台调用为 0。
- Skeleton008：8/8 公共合成 DOM、12/12 Policy、2/2 `BLOCKED_BUDGET`、16/16 任意 URL/Redirect-SSRF 与 7/7 schema-drift rejection 通过；4 个 ready、4 个 `platform_changed`；稳定 `mid`/Canonical Host/Path 100%，Query/Fragment、Cookie、OAuth 材料、媒体/raw DOM、任意 URL transport 与平台调用为 0。
- Skeleton009：8/8 公共合成 DOM、14/14 Policy、2/2 Scope/Retention 未知拒绝、16/16 未文档化 Cookie/MTop 签名输入拒绝与 7/7 schema-drift rejection 通过；4 个 ready、4 个 `platform_changed`；稳定 `num_iid`/Canonical Host/Path 100%，Query/Fragment、Cookie/签名材料、媒体/raw DOM 与平台调用为 0。
- 当前 Extension 权限为 `activeTab`/`nativeMessaging`/`scripting`/`sidePanel`；历史 Foundation004 的 3 权限事实保持在固定提交与 Evidence 中。当前无 Host Permission、静态 Content Script、Storage/Cookie/Tabs/Downloads 或远程代码。
- Chromium E2E 在默认 Action 前验证注入与采集 2/2 拒绝；用官方 CDP Action 驱动后才取得临时 `activeTab`，并通过真实 Side Panel 按钮把 XHS/Douyin/Bilibili/Kuaishou/Weibo/Taobao 合成当前页分别送入 Native Host/SQLite；每平台 100 次 Worker 重启仍 0 丢单/重单/错状态。平台形态网络请求由 catch-all route 拦截，实测平台调用 0；Owner Canary 与真实页面均 `NOT_RUN/DISABLED`。
- 当前根回归：149 tests PASS，3 个需要私有可选输入的测试按设计跳过且由机器 allowlist 核对；Foundation001 固定提交 fresh replay、Foundation002 Contract、Foundation003 Store、Foundation004、Foundation005、Skeleton001/002/006/007/008 历史固定＋当前六平台回归与 Skeleton009 完整 verifier 均 PASS。Foundation003 本轮只验证历史 Owner Runtime evidence，未重新读取 Owner 私有根。
- Fresh copy：隔离 HOME 中 frozen locks、Extension 与 7 个 lifecycle rehearsal 加 1 个负向 Canary 均通过。

```bash
python3.12 -B scripts/verify_foundation_001.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B scripts/verify_foundation_002.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B scripts/verify_foundation_003.py --verify-worktree --allow-external-main-dirty --validate-owner-runtime --require-evidence
python3 -B scripts/verify_foundation_004.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B scripts/verify_foundation_005.py --verify-worktree --allow-external-main-dirty --require-evidence
python3 -B scripts/verify_skeleton_002.py --verify-worktree --allow-external-main-dirty --require-evidence
python3 -B scripts/verify_skeleton_006.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton006-final3/software-lane.json --require-evidence
python3 -B scripts/verify_skeleton_007.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton007-final/software-lane.json --require-evidence
python3 -B scripts/verify_skeleton_008.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton008-final3/software-lane.json --require-evidence
python3 -B scripts/verify_skeleton_009.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton009-final3/software-lane.json --require-evidence
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s02-skeleton009-final3
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

1. 保留 Skeleton001、Skeleton002、Skeleton006、Skeleton007、Skeleton008 与 Skeleton009 本地提交，不上传；Stage 2 必须等全部 9 个 Skeleton Task、独立 Review/Fix/Re-acceptance 与 `G2=PASS` 后整体上传。
2. 下一独立 Run 只执行 `TSK.x2n.skeleton.003`（临时媒体与 URL scrubber）；不得顺带进入列表/Adapter、下载、媒体分析、Notion、分类或真实 Canary。
3. 六平台真实页面、API/CLI/TOP 与抖音生产短链解析继续关闭，直到当时的一手政策证据、Owner 明确授权、对应 Canary、隐私披露与网络安全门禁独立通过。
4. 继续保持共享认证材料零接触、其他长期开发零重叠；任一 Secret/CDN/Runtime/越界写入命中立即 Fail Closed。
