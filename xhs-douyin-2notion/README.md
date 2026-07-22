# xhs-douyin-2notion

把用户明确选择的小红书、抖音、哔哩哔哩、快手、微博和淘宝当前内容或个人列表批次，治理为可恢复、可分类、带 ASR/OCR/关键帧证据的 Markdown 与 Notion 知识资产。

项目名是稳定品牌，不是平台范围上限。六平台均采用独立 Policy/Auth/Technical Gate；未知即禁用。这里的在线采集不是通用爬虫：无自动滚动、无账号状态改变、无代理/指纹规避、无凭据或平台媒体 URL/原始媒体持久化。

当前状态：`v0.0.0.1 / Stage 2` 的九个 `TSK.x2n.skeleton.001–009` 与独立 `STG.X2N.2.REVIEW` 已完成项目原生本地验收；Stage 1 已通过 PR #73 合并且远端/合并后门禁通过。Skeleton005 在 SQLite Schema v2 之外新增可重建 Markdown 与进程内 Notion Mock Sink：六平台 80×2 投影使用固定 `platform/content_id` 路径、原子写、有效 Frontmatter、稳定 Unclassified Index；Notion 使用 `2026-03-11` Data Source 语义、加法式 Schema、Outbox、2 req/s、429/529/断网/kill 重试与对账。重复 Page、半文件、断链、CDN finding 与真实 Notion 调用均为 0。项目原生本地 `G2=PASS`，Stage 2 整体上传已授权；远端 CI/merge 仍为 `PENDING_POST_G2_UPLOAD`，此前不得进入 Stage 3。正式 Verifier release-candidate 因原任务包缺少 canonical `MANIFEST` role 保持 `BLOCKED_REQUIREMENT_GAP`。分类、列表 Adapter、真实平台/Notion、Owner Canary、真实媒体与模型处理仍未运行；共享认证材料和其他长期开发继续零接触、零重叠。

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

## Stage 2 / Review 与 G2 验证

```bash
.venv/bin/python -B scripts/ci/run_lane.py \
  --lane full --repetitions 2 --reports-dir build/g2-review
.venv/bin/python -B scripts/verify_stage_2_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/g2-review/software-lane.json --require-evidence
```

Review 冻结九个 Task final commit 与 evidence，逐版本扫描 Stage 2 历史，并聚合六平台独立
current-page E2E、zero duplicate、zero CDN persistence、媒体清理和 Notion outage 独立性。
软件 lane 只验证软件，不决定动态 Stage Gate；实际 Python/Node/npm/uv/ruff/coverage/PyYAML
必须与政策一致。项目原生 G2 只授权 Stage 2 上传；远端 CI/merge 前 `stage_3_task_start=false`。
Review 最终根回归为 186 tests PASS、3 个固定 Owner-private 可选输入 skip；76 个 Companion
tests PASS。两份独立 full lane 均为 24/24 Blocking Gate PASS，coverage 76.93%、33 个依赖
vulnerability 0；65-member 候选制品 SHA 一致且 Runtime Data 0。

## Stage 2 / Skeleton 005 历史验证

```bash
.venv/bin/python -B scripts/run_skeleton_005_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_005.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton005-final/software-lane.json --require-evidence
```

Markdown Canonical 路径固定为 `runtime/library/content/<platform>/<content_id>.md`，不使用标题或分类；
同目录 `0600` 临时文件经 `fsync` 后原子替换，kill 后只保留旧完整文件或新完整文件。Frontmatter、
正文与 Provenance 均由 SQLite snapshot 和私有 Artifact 文本确定性投影；`Unclassified` 只生成派生
Index，不创建一级分类。

Notion 实现只包含凭据无关的投影合同、限速客户端接口与进程内 deterministic Mock，不包含真实 HTTP
transport，也未读取 Notion 凭据。Items/Categories Schema 只加字段，Owner 自定义字段保留；同
`content_key` 只允许一个 Page，Projection Hash 一致不写，Owner category Relation 只接受显式 Page
映射。Outbox 在 429/529、timeout、reset、一小时 outage、成功后 Receipt 前 kill 与 Schema 冲突下，
最终进入 Receipt 或 bounded Dead Letter；Canonical/Markdown 不与 Notion 事务耦合。

最终根回归为 175 个测试 PASS、3 个固定 Owner-private 可选输入 skip；76 个 Companion tests PASS。
full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 76.93%，
33 个依赖 OSV 漏洞 0，65-member source candidate 确定性一致且 Runtime Data 0。真实 Notion、Owner
Chrome/Profile、真实账号、平台调用、真实媒体与模型均未运行；Skeleton005 完成当时 `G2=NOT_RUN`，当前 G2 状态以上述独立 Review 事实为准。

## Stage 2 / Skeleton 004 历史验证

```bash
.venv/bin/python -B scripts/run_skeleton_004_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_004.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton004-final/software-lane.json --require-evidence
```

`capture_current` 只接收 Native v1 已净化的六平台当前页事实。事务 1 原子提交 Request Ledger、
running Run、Content、`saved_current` Relation、SourceObservation 与 active Checkpoint；事务 2
追加或复用确定性的 URL-free/private-payload-free placeholder Artifact，并在同一提交中把 Checkpoint
与 Run 标为完成。事务内中断全回滚，canonical commit 后中断可由重复请求、`GET_JOB` 或 bounded
resume 只凭 SQLite 恢复；不需要原 payload，也没有新 Migration。

CI 合成范围覆盖 80 个输入连续两轮与 100 个并发重复：每类 scoped entity 分别保持 80/1，
duplicate entity 为 0；4 个 kill point 的 non-replayable state 为 0，完整 Run→Observation/Adapter→
Content/Relation→placeholder Artifact trace 的 broken 数为 0。Receipt 只输出状态、计数和 hash ref；
Classification、Renderer、Markdown、Notion 与媒体处理明确为 `DOWNSTREAM_NOT_RUN`。

最终根回归为 166 个测试 PASS、3 个固定 Owner-private 可选输入 skip；59 个 Companion 测试 PASS。
full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 74.61%，
33 个依赖 OSV 漏洞 0，62-member source candidate 确定性一致且 Runtime Data 0。Owner Chrome/Profile、
真实账号、平台调用、真实媒体、Markdown/Notion 与 G2 均未运行。

## Stage 2 / Skeleton 003 历史验证

```bash
.venv/bin/python -B scripts/run_skeleton_003_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_003.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton003-final/software-lane.json --require-evidence
```

`ACC.x2n.media.001–003` 在 `ENV-CI-SYNTH` 范围通过：五个固定逻辑 sink 的 CDN、签名/追踪参数与
Canonical Query/Fragment finding 均为 0；512 个 URL fuzz 中 64 个 allowlisted、448 个 forbidden，
Oracle mismatch 为 0；32 个 SSRF 目标成功数与本地文件读取均为 0。成功与异常处理后残留为 0，
过期 failure/kill 残留为 0，活跃 lease 误删为 0，注入的删除失败 100% 写入高优先级稳定错误并可重试。

下载核心不提供默认或生产网络 transport；调用方只能向 transport 交付已校验 hostname、已绑定的
global IP 和被隐藏的 request target。响应需通过逐跳重验、64 MiB stream limit、60 秒 Deadline、
identity encoding、MIME sniff 与隔离 Inspector；远端文件名不参与本地路径。`ACC.x2n.media.004`
只完成 8 个 acquisition-layer 结构化阻断，Companion crash 为 0；FFmpeg hang、image-bomb decode、
重复关键帧、ASR/OCR/关键帧处理明确为 `DOWNSTREAM_NOT_RUN`，未冒充完整媒体处理验收。

最终本地回归为 158 个根测试 PASS、3 个固定 Owner-private 可选输入 skip；full lane 两轮
24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 73.67%，
33 个依赖 OSV 漏洞 0，61-member source candidate 确定性一致且 Runtime Data 0。

## Stage 2 / Skeleton 009 历史验证

```bash
npm run self-test --workspace @x2n/extension
npm run test:taobao-fixtures --workspace @x2n/extension
npm run test:taobao-extension --workspace @x2n/extension
.venv/bin/python -B scripts/verify_skeleton_009.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton009-final3/software-lane.json --require-evidence
```

`ACC.x2n.capture.006` 当前只达到 `ENV-CI-SYNTH`：4 个 ready、4 个
`platform_changed`、14 个政策状态、2 个 Scope/Retention 未知拒绝、16/16 未文档化
Cookie/MTop 签名输入拒绝与 7 个 schema-drift 拒绝全部通过。页面先交叉验证一手资料证明的
`num_iid`，只把它写入 `content_id`；Canonical 只保留精确 `item.taobao.com/item.htm`
Host/Path，Query/Fragment、Cookie/签名材料、媒体/raw DOM 与平台调用为 0。

一手资料证明 `taobao.item.get` 是需授权的增值 API，私有商品/订单/收藏数据需要 OAuth，
TOP 官方签名协议已登记；同时要求最小目的/范围与撤回、服务结束、保留期届满时删除，并禁止
未授权爬取。本应用尚无 AppKey/OAuth/API Permission/付费计划/字段范围/保留期/删除撤销流程
及删除回执审批，故真实页面、TOP API 和 DOM fallback 为 `UNKNOWN_DISABLED`。官方 TOP
签名不是被禁止的未来路线，但本 Run 未实现；浏览器 Cookie/MTop 逆向签名输入永久拒绝。

最终本地回归为 149 个根测试 PASS、3 个固定 Owner-private 可选输入 skip；full lane
两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage
70.95%，33 个依赖 OSV 漏洞 0，60-member source candidate 确定性一致且 Runtime Data 0。

## Stage 2 / Skeleton 008 历史验证

```bash
npm run self-test --workspace @x2n/extension
npm run test:weibo-fixtures --workspace @x2n/extension
npm run test:weibo-extension --workspace @x2n/extension
.venv/bin/python -B scripts/verify_skeleton_008.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton008-final3/software-lane.json --require-evidence
```

`ACC.x2n.capture.005` 当前只达到 `ENV-CI-SYNTH`：4 个 ready、4 个
`platform_changed`、12 个政策状态、2 个真实形态预算拒绝、16/16 任意 URL/Redirect-SSRF
拒绝及 7 个 schema-drift 拒绝全部通过；Canonical Host/Path 正确，Query/Fragment、平台调用、
Cookie、媒体/raw DOM、preview/proxy/redirect transport 均为 0。微博一手资料只证明 OAuth 与
授权用户本人发布内容的 `statuses/show`，未证明任意公开当前页、点赞/收藏读取或自动化 DOM
豁免；本应用预算为 0，价格、Scope 与配额未知且未批准。因此真实页面为
`BLOCKED_BUDGET / UNKNOWN_DISABLED`，官方 CLI 仅登记未安装/未执行，生产 API/CLI、OAuth
材料输入、DOM fallback 与 Owner Canary 均为 `DISABLED / NOT_RUN`；公开路由只作为明确标注
的未验证合成假设。

最终本地回归为 140 个根测试 PASS、3 个固定 Owner-private 可选输入 skip；full lane
两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage
70.95%，33 个依赖 OSV 漏洞 0，59-member source candidate 确定性一致且 Runtime Data 0。

## Stage 2 / Skeleton 007 历史验证

```bash
npm run self-test --workspace @x2n/extension
npm run test:kuaishou-fixtures --workspace @x2n/extension
npm run test:kuaishou-extension --workspace @x2n/extension
python3.12 -B scripts/verify_skeleton_007.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton007-final/software-lane.json --require-evidence
```

`ACC.x2n.capture.004` 当前只达到 `ENV-CI-SYNTH`：4 个 ready、4 个
`platform_changed`、10 个政策状态、2 个真实形态 `BLOCKED_AUTH` 与 5 个 schema-drift
拒绝全部通过；Canonical Host/Path 正确，Query/Fragment、平台调用、Cookie、媒体/raw DOM
输出均为 0。快手一手资料证明 OAuth、应用登记、动态最小授权与 `user_video_info` 下授权
用户已发布作品的 `photoId`，未证明任意公开当前页或点赞/收藏读取能力，并明确限制未经
授权的自动化采集。因此真实页面为 `BLOCKED_AUTH`，生产 API transport、Access Token/
Cookie/Profile 输入、DOM fallback 与 Owner Canary 均为 `DISABLED / NOT_RUN`；
`/short-video/<id>` 仅是明确标注的未验证合成路由假设。

最终本地回归为 131 个根测试 PASS、3 个固定 Owner-private 可选输入 skip；full lane
两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage
70.95%，33 个依赖 OSV 漏洞 0，58-member source candidate 确定性一致且 Runtime Data 0。

## Stage 2 / Skeleton 006 历史验证

```bash
npm run self-test --workspace @x2n/extension
npm run test:bilibili-fixtures --workspace @x2n/extension
npm run test:bilibili-extension --workspace @x2n/extension
python3.12 -B scripts/verify_skeleton_006.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s02-skeleton006-final3/software-lane.json --require-evidence
```

`ACC.x2n.capture.003` 当前只达到 `ENV-CI-SYNTH`：5 个 ready、5 个
`platform_changed`、8 个政策状态与 5 个 schema-drift 拒绝全部通过；Canonical Host/Path
正确，Query/Fragment、平台调用、媒体/raw DOM 输出均为 0。开放平台的一手资料只证明
OAuth 及关联 UP 主授权后的稿件能力，未证明任意当前页、点赞或收藏读取能力；当前公开
Open Platform 文档也未证明文章 `/read/cv…` 路由。因此真实 Bilibili 页面/API 与 Owner
Canary 保持 `UNKNOWN_DISABLED / NOT_RUN`，文章路由只作为显式未验证的合成假设。
最终本地回归为 122 个根测试 PASS、3 个固定 Owner-private 可选输入 skip；full lane
两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage
70.95%，33 个依赖 OSV 漏洞 0，57-member source candidate 确定性一致且 Runtime Data 0。

## Stage 2 / Skeleton 002 历史验证

```bash
npm run self-test --workspace @x2n/extension
npm run test:xhs-fixtures --workspace @x2n/extension
npm run test:douyin-fixtures --workspace @x2n/extension
npm run test:e2e --workspace @x2n/extension
npm run test:douyin-extension --workspace @x2n/extension
python3.12 -B scripts/verify_skeleton_002.py \
  --verify-worktree --allow-external-main-dirty --require-evidence
```

`ACC.x2n.capture.002` 当前只达到 `ENV-CI-SYNTH`：4 个 ready、4 个
`platform_changed` 与 16 个重定向安全用例全部通过；3 个合成短链完成 canonical
重建，13 个非允许输入/跳转/响应/transport 故障全部拒绝。E2E 对所有平台形态网络请求
先拦截再本地 fulfill/abort，实测平台调用为 0。生产网络 transport、真实视频/图集/短链、
Owner Canary 和真实账号均为 `UNKNOWN_DISABLED / NOT_RUN`；`/note` 与短链形态仅是合成
Oracle，不是现实平台支持声明。

Skeleton002 的 Task State、Policy、Evidence 与 acceptance input receipt 固定在最终提交
`2a91efbc…`；当前树继续运行 XHS/Douyin 静态安全、Fixture 和 E2E 回归，历史 Evidence
不重写。

## Stage 2 / Skeleton 001 历史验证

```bash
npm ci --ignore-scripts
uv sync --frozen --all-packages --group ci
PLAYWRIGHT_BROWSERS_PATH=build/playwright-browsers \
  npx --no-install playwright install chromium
npm run self-test --workspace @x2n/extension
npm run test:xhs-fixtures --workspace @x2n/extension
npm run test:e2e --workspace @x2n/extension
python3.12 -B scripts/verify_skeleton_001.py \
  --verify-worktree --allow-external-main-dirty --require-evidence
```

`ACC.x2n.capture.001` 只达到 `ENV-CI-SYNTH`：3 个 ready 与 2 个
`platform_changed` Fixture 全部通过；Owner Canary 所需真实图文/视频各 1 为 `NOT_RUN`，
因此真实页面保持 `UNKNOWN_DISABLED`。Manifest 当前权限为 `activeTab`、
`nativeMessaging`、`scripting`、`sidePanel`；`scripting` 只能在 Extension Action 授予临时
`activeTab` 后执行，持久 Host Permission 仍为 0。

Skeleton001 的 Task State、Policy 与 acceptance input receipt 固定在最终提交
`894553c6…`；当前树继续运行 XHS 静态安全、Fixture 和 E2E 回归，历史 Evidence 不重写。

## Stage 1 Review / G1 历史验证

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

G1 只证明 Foundation001–005 的公共安全合成范围。机器证据位于
`machine/evidence/stage_1/review/`；Stage 1 后续已整体上传、远端通过并合并，但 Owner
Chrome、真实账号、平台、Notion、模型、媒体和 Sink 均不因 G1 自动变为已运行。

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

Foundation004 历史提交仍精确记录 3 权限；当前前向验证同时允许 Skeleton001 经独立
Acceptance 增加的 `scripting`，并继续拒绝 Host Permission。门禁执行 20 个公共合成页面、
五区 Side Panel、临时 Native Host 注册、当前 25 个 Companion tests（Foundation004 固定
提交历史为 24）与 100 次真实 Service
Worker 终止/重启；SQLite 是唯一任务状态源。Skeleton001 最终 full lane 两轮 24/24
Blocking Gate 通过，0 failure/flaky/silent skip；SQLite transient WAL/SHM 消失竞态已有
确定性回归，Canonical DB 权限加固仍 Fail Closed。
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
