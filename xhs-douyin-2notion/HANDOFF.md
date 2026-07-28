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
- Stage 2 九个独立单 Task `TSK.x2n.skeleton.001–009`（Phase 2.1–2.9）与独立 `STG.X2N.2.REVIEW` 已完成项目原生本地验收；8 个 finding 全部关闭。当前 Review 分支为 `codex/xhs-douyin-2notion-v0001-s02-review`，Review base 为 `c133e1d4…`、origin cutoff 为 `6777c8fc…`。
- Stage 2 已通过 PR #78 合并到 `main@ee5d251c…`；最终 x2n run `29922576589` 与 Dual-Plane run `29922576674` 均成功。新增 `stage_2_remote_merge_state.json` 只记录 Stage 3 授权前置事实，旧 G2 pre-upload Evidence 保持逐字节不变。
- Stage 3 九个历史 Adapter Task `PH.X2N.3.1–3.9 / TSK.x2n.adapters.001–009` 与首次 `STG.X2N.3.REVIEW` 已完成公开合成复核；六项 finding 关闭，九个 Task runner 均 `PASS_CI_SYNTH_SCOPED`。
- `STG.X2N.3.REVIEW.RESUME` 的合同版本化事实保持冻结：合法能力终态固定为 `READY_FOR_MVP_ACTIVATION` / `DISABLED_EXTERNAL_GATE`；Stage 3 只贡献 `PASS_CI_SYNTH_CONTRIBUTION`，真实激活与完整 `ACC.x2n.rel.006` 属于 Stage 6。它不是当前 G3 结论，旧 Evidence 不改写。
- `TSK.x2n.adapters.010 / PH.X2N.3.10` 已完成 CI synthetic 验收：8 scope Extension→Native→Adapter dispatch、`run_record.failed`＋脱敏 `run_failure`、由 `fallback_eligible` 派生的 `FALLBACK_AVAILABLE`、失败 `GET_JOB` 保留 `job_id` 与第二次 Owner 当前页动作的新 `request_id`＋`fallback_from_job_id` 均已验证。Pydantic/JSON Schema/generated TypeScript/Extension 与 versioned migration 同步；自动 fallback 和真实平台调用均为 0。
- 脱敏验收证据为 `evidence/adapters/TSK.x2n.adapters.010.json`：`PASS_CI_SYNTH_SCOPED_REVIEW_PENDING`，47 个 Python tests、8 个 scope dispatch、平台调用 0；它是固定 Task010 历史 receipt，不被后续 G3 状态回写。
- Review 关闭：Owner removed 终态、XHS envelope、Douyin 50 次真实子进程 Kill、private batch comparison/增量候选、A005 fixed-commit pin、同一批 80 Adapter 输入的 Canonical→Artifact→Markdown→Notion Mock/Outbox 真正跨层幂等。80 Artifact/Markdown/Notion Mock 与 160 Receipt 第二轮重复为 0，持久层 finding 0。
- 首次 Review 的五个 blocker 证据保持不可变；Resume 已关闭其中三个合同/归属 blocker，Task010 已在 CI synthetic 范围内闭合剩余两个实现 blocker。独立 `STG.X2N.3.REVIEW.RESUME.RECHECK` 已重新复跑六项 G3 条件并签发 `G3=PASS_CI_SYNTH`；8 个真实 Canary/private Manifest/平台授权仍 `NOT_RUN`，但归属 Stage 6。
- Stage 4 的 TSK.x2n.multimodal.001–005 已完成：有界媒体、local-first ASR、OCR/Vision、仅内存 Fusion/提示注入防护，以及 Owner 一级 taxonomy registry、append-only revision、immutable snapshot、受约束 suggestion、private Gold Oracle 和 Owner review correction 均有固定 receipt。Task005 的分类器没有 Store/registry mutation capability；未知、disabled 与跨内容 revision 都 Fail Closed。ASR/OCR/Vision/分类私有 Gold 仍 pending，自动分类固定关闭，只有 Unclassified/suggestion-only。
- 独立 STG.X2N.4.REVIEW 已签发 G4=PASS_CI_SYNTH：五份 Task receipt、ASR/OCR/Vision/Fusion 报告、prompt-injection suite、Owner-only taxonomy 与 auto_classify disabled 均复验；真实模型、私有 Gold、平台、账号、Notion、上传、部署和发布均为 0/NOT_RUN。仅授权下一单本地 TSK.x2n.uxops.001 / PH.X2N.5.1。
- Release：不设置预发布阶段、固定 30 日健康观察或 soak；`G0–G5`、`assurance.001–004/uxops.005` 与最终任务精确自有 Acceptance 集合之外的 Blocking Acceptance 通过后启动 `assurance.005`。该任务内完成 80 条 XHS/Douyin Owner MVP 基线、每个额外实际启用能力各自不超过 20 条的独立激活、安全门必须通过、模型能力通过或明确关闭/降级为仅建议模式、回滚、签字、部署、运行和 online smoke，成功后才签发 `G6 PASS` 并直接上线唯一 `v0.0.0.1`；合法外部门可关闭结算，技术阻断不能结算，安全未知或失败不能降级结算；上线后监控只触发修复、降级或回滚，不形成等待门。
- Data：`X2N_DATA_ROOT` 是下载/执行/活跃 SQLite working copy 的本机易失工作区；目标为整根排除 Time Machine，但当前仍是历史逐子目录状态，本 Resume 未执行系统修改，`uxops.005` 将在 Owner 明确授权后实施/复验。本地 backup 不能满足 durability；耐久资产只经 `KMOS/KMDatabase/machine/tools/private_db_client.py ingest|get|list|verify` 写入 `LinzeColin/Private-Database` 的 `Private-MetaDatabase` area，并以 manifest `domain=xhs-douyin-2notion` 归属，禁止 clone。客户端拒绝直接 `.sqlite/.db` 且单对象上限 95 MiB，因此一致性 SQLite 快照必须封装为非运行时归档、≤90 MiB 分片，凭精确 domain restore manifest 做 SHA-256 重组和 integrity 恢复；area-global verify 仅为无路径披露 advisory；验证前标记 `durability_pending`。
- Private DB client audit：当前源码 SHA-256 `8a26302c…c9ffa`；manifest SHA 幂等和 `verify` 都是全 area、`verify` 缺对象仍可能 exit 0 且会触及其他 domain 路径、`get` 会落临时文件、认证继承 `gh api` 环境。这里的后续 “Task005” 专指 `TSK.x2n.uxops.005`，不是已完成的 `TSK.x2n.multimodal.005`：它必须 domain-bound envelope、精确 x2n domain 逐对象 get/hash/restore、其他 domain 缺失不阻断且零路径披露、临时清理、opaque name、禁止 put/delete；显式授权后可让现有 authenticated session 仅经客户端使用，Token value contact 与 auth mutation 必须为 0，执行前重验 digest。删除只作用 active SQLite/派生 Sink，单调 deletion epoch/tombstone 防历史恢复复活；durable hard erase 需独立 Owner Private-Database 治理。本 Resume 仅只读源码/`--help`；“没有 authenticated session 或数据写入”是过程声明，不是离线 verifier 的独立观测。
- Resume 验证：严格 schema/history/DAG/release/data/client-audit/isolation 与 Phase0.1/0.5
  回归 PASS；Resume 20 tests＋旧 Review 7 tests 共 27/27 PASS。旧成功 lane 已因 source 更新失效；
  source-freeze 后的 fresh Python 3.12.13 fast lane 及其 failure/flaky/silent-skip 结果只以
  `machine/evidence/stage_3/review_resume_mvp/verification.json` 为准，禁止复用旧报告。
- 小红书收藏生产位保持关闭：Extension 只处理 Owner gesture 后最多 20 条可见净化 DOM，不滚动、不翻页、不联网；partial/auth/verification/platform-change/empty-unverified 不推进或完成。bounded Canary 不写 full scan，只有权威可见结束可完成 full scan；真实页面、Owner Profile/private gold/Canary 均 `NOT_RUN`。
- 小红书点赞生产位同样关闭：同一可见批次/Checkpoint 边界，不调用私有端点、不读取 Cookie/Profile、不执行 like/unlike。100 个合成点赞与 20 个预置收藏最终保持 100 Content、100 `liked`、20 `favorited`；自动归档、Classification/Taxonomy/Owner 分类覆盖均为 0。
- 小红书当前页代码、5 个 DOM Fixture、Action/临时 `activeTab`、Native Host/SQLite 闭环与 100 次 Worker restart 已通过；能力位仍为 `ci_synth_only`，真实页面禁用。
- 抖音当前页代码、8 个 DOM Fixture 与 16 个合成短链 redirect 用例通过；A004 另固定 `jiji262/douyin-downloader@ef3ad18c…`、tree `ff7774b6…`、version `2.0.0` 与 MIT identity，以严格 health/build attestation、递归封闭 Schema、`shell=False` subprocess 和数字 loopback REST 包装 owner-managed sidecar。20 收藏＋20 点赞合成映射、18 个负向合同用例和 shadow block 通过；原始上游未 vendor/安装/导入/执行，真实 Scope/private sidecar/Profile/账号/Canary 均 `UNKNOWN_DISABLED/NOT_RUN`。
- 哔哩哔哩当前页代码、10 个 DOM、8 个 Policy 与 5 个 schema-drift rejection 通过；文章公开路由未由当前 Open Platform 文档证明，`?p=` 分 P Fail Closed，真实页面/API 与 Owner Canary 均禁用。
- 哔哩哔哩所选列表只实现当前一手资料证明的 `authorized_uploader_video_manuscripts` 净化合同：真实启用要求 App 审批、关联 UP 主授权、`ARC_BASE`、书面自动化许可、受审净化 transport 和撤回/删除路径；当前均未满足/未运行，生产 Feature Flag 关闭。CI 合成清单一次最多 20 条，映射为 Owner-confirmed `saved_current`，不冒充平台点赞/收藏；无 network/DOM/next-page transport、自动滚动/分页或 raw API response。
- 快手当前页代码、8 个 DOM、10 个 Policy、2 个 `BLOCKED_AUTH` 与 5 个 schema-drift rejection 通过；A007 进一步只实现 `user_video_info` 下授权用户本人发布作品的严格净化选择合同。任意点赞/收藏仍 `UNKNOWN_DISABLED`，公开路由仍为未验证合成假设；真实 App/OAuth/动态同意/API/DOM transport、删除执行器与 Owner Canary 均关闭。Scope 撤回使新请求固定为 0，并生成待删除证据；本 Task 不自动删除历史 Canonical 数据。
- 微博当前页代码、8 个 DOM、12 个 Policy、2 个 `BLOCKED_BUDGET`、16 个任意 URL/Redirect-SSRF rejection 与 7 个 schema-drift rejection 通过。A008 进一步按官方 `GET /2/favorites.json` 只实现当前 OAuth 用户 favorites 的严格净化单页合同：20 条映射为 scan-confirmed `favorited`，不推断 like/本地收藏夹/full scan；预算 0、价格/配额/应用权限/canonical route 未批准，真实 API/OAuth/CLI/DOM/Profile/Canary 关闭。HTTP 429 只持久化 bounded `Retry-After` hold，不自动重试或代理轮换。
- 淘宝当前页代码、8 个 DOM、14 个 Policy、2 个 Scope/Retention 未知拒绝、16 个未文档化 Cookie/MTop 签名输入拒绝与 7 个 schema-drift rejection 通过。A009 当前只实现 Owner 明确提供最多 20 个 `num_iid`、未来独立获授权的 `taobao.item.get` 严格 `{num_iid,title}` 净化合同和 Owner-confirmed `saved_current`；当前一手导航未建立买家个人收藏列表能力，故不枚举、不冒充收藏。无 App/OAuth/Scope/增值计划/预算/当前价格配额/官方净化 transport/保留期/撤回删除流程与回执时真实 TOP API、Profile 与 Canary 均关闭。
- Media Safety 已实现不可序列化 URL 引用、六平台精确 suffix＋HTTPS/443＋DNS 全地址＋逐 redirect 防火墙、绑定已校验 IP 的 transport 合同、流式 byte/deadline/MIME/Inspector 限制、下载前 URL-free cleanup reservation＋校验后 metadata finalize 的 SQLite lease、共享/独占 lifecycle lock、24h cleaner 与五个固定 sink scanner。Task001 已在临时合成媒体上通过本机 FFmpeg/FFprobe、音频、关键帧、近重复及清理边界；Task002 只消费其 ephemeral M4A 并将 WAV/JSON/转录清理或留在内存；Task003 只消费验证过的 ephemeral JPEG 并在解析后清理 Provider JSON，OCR/视觉输出只留内存和脱敏哈希 receipt；Task004 只消费这些内存文本并把融合摘要/检索文本保持为不可序列化的会话对象。真实平台媒体、真实 ASR/OCR/Vision、真实融合模型与分类仍关闭或未运行。
- Canonical orchestration 保持 Schema v2 不变，以两个 SQLite 事务把六平台净化当前页落为 Request Ledger、Run、Content、Owner-confirmed `saved_current` Relation、SourceObservation、Checkpoint 与 URL-free/private-payload-free placeholder Artifact；canonical commit 后可由重复请求、`GET_JOB` 或 bounded resume 只凭 SQLite 恢复。
- Markdown Sink 使用固定 `platform/content_id` 路径、JSON-compatible YAML Frontmatter、同目录 `0600` atomic replace 与 Unclassified 派生 Index；Notion Sink 仅实现 `2026-03-11` 语义合同和进程内 Mock，以加法式 Schema、Owner category 显式映射、2 req/s、Outbox/Retry/Dead Letter/Mapping/Receipt 支持 kill-reconcile，真实 transport/凭据/Workspace/Page 为 0。
- Skeleton001 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；105 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，54-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton002 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；112 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，56-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton006 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；122 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，57-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton007 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；131 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，58-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton008 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；140 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，59-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton009 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；149 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 70.95%，33 个依赖 OSV 漏洞 0，60-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton003 最终全量回归：两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；158 个根测试 PASS、3 个 Owner-private 可选输入按 allowlist skip；overall combined coverage 73.67%，33 个依赖 OSV 漏洞 0，61-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton004 最终全量回归：80 个六平台输入两轮、100 个并发重复与 4 个 kill point 通过；duplicate entity、stuck Run、non-replayable state、broken provenance trace、private placeholder payload 均为 0；166 个根测试 PASS（3 skip）、59 个 Companion tests PASS；两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；overall combined coverage 74.61%，33 个依赖 OSV 漏洞 0，62-member source candidate 确定性一致且 Runtime Data 0。
- Skeleton005 最终全量回归：六平台 80×2 的 80 Markdown/80 Notion Mock Pages/160 Outbox+Receipt 通过；partial file、invalid Frontmatter、dead link、CDN finding、duplicate Page、hash-noop replay request 与真实 Notion call 均为 0；175 个根测试 PASS（3 skip）、76 个 Companion tests PASS；两轮 12×2=24/24 Blocking Gate PASS，0 failure/flaky/silent skip；overall combined coverage 76.93%，33 个依赖 OSV 漏洞 0，65-member source candidate 确定性一致且 Runtime Data 0。
- Stage 2 Review 最终回归：186 个根测试 PASS（3 个固定可选 skip）、76 个 Companion tests PASS；两份独立 full lane 各 24/24 Blocking Gate PASS，coverage 均 76.93%，33 个依赖漏洞 0，65-member source candidate SHA 一致；实际 Python 3.12.13 与全部工具链版本匹配政策。
- 回归捕获并修复 SQLite transient `-wal/-shm` 在并发连接关闭时消失的 chmod 竞态；只豁免已经消失的 sidecar，Canonical DB 或仍存在 sidecar 的加固失败继续 Fail Closed。
- 首次 Stage 3 Review 当时的 Gate 为 `G3=BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION`；九个历史 Task 与 Review 只证明 CI-SYNTH/Mock/Chaos 范围，A005 的 80 条 Owner 真实验收只完成非执行工具，Owner Profile/private Manifest/真实链路与正式 Release 均未运行。Resume 当时闭合三项合同/归属 blocker；当前 G3 只以本文件开头的新独立 recheck fact 为准。
- 真实账号、Owner Chrome/Profile、六平台调用、真实 Notion、模型、真实媒体处理与全部下游用户旅程 Acceptance：`NOT_RUN`；Markdown/Notion Mock 仅 CI-SYNTH scoped pass。
- 六平台真实执行：全部 `UNKNOWN_DISABLED`、`BLOCKED_AUTH` 或 `BLOCKED_BUDGET`；六平台均仅 `current_page=CI_SYNTH_ONLY`；各平台真实启用时重新通过 Policy/Auth/Technical/Canary Gate。

## Resume 关键决策

1. Owner 要求保留供其他并行工作使用的外部共享 GitHub 认证材料，并接受其外部残余风险。
2. 本 Resume 对 authenticated session、Token 值与 auth/config/Credential Helper 零接触；x2n 永不读取/显示 Token 值、修改认证或删除/轮换/撤销 Token。未来显式授权 Task 可让现有 session 仅经 `private_db_client.py` 执行 x2n in-scope 操作。
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
- Skeleton003：512 个 URL fuzz（64 allowlisted、448 forbidden）、32 个 SSRF、8 个 cleanup chaos、8 个 acquisition resource block 与 23 个媒体安全单测通过；forbidden target/local read/成功残留/过期残留/active misdelete/scanner finding/Companion crash 均为 0，删除失败稳定高优先级回执率 100%。
- Skeleton004：六平台 80×2 与 100 concurrent duplicate 通过；Request/Run/Content/Relation/Observation/Checkpoint/placeholder Artifact cardinality 精确，4 个 kill point 可重放，完整 scoped provenance broken trace 为 0；Classification/Renderer/Markdown/Notion/媒体处理 `DOWNSTREAM_NOT_RUN`。
- Skeleton005：六平台 80×2 固定路径 Markdown 与进程内 Notion Mock 通过；Schema v2 不迁移，Unclassified 不建 taxonomy row，Owner category Relation 只接受显式 mapping；7 类 retry/outage/kill/schema fault 最终 Receipt 或 bounded Dead Letter，真实 Notion/Owner Canary `NOT_RUN`。
- Adapters001：7 个 session＋7 个 batch 公共合成 Fixture 与 16 个专项单测通过；Profile symlink/权限/路径泄漏、过期/缺失/未来/验证码状态、Native Host 缺失、DB Busy、非核心依赖降级、互斥竞争、限速/时钟回退、异常/空/部分扫描删除均 Fail Closed。Cookie/Profile path/真实账号/平台调用/物理删除为 0/NOT_RUN。
- Adapters002：7 个 DOM cases 与 13 个专项单测通过；100 条两收藏夹数据经 5 个显式批次落为 Content/`favorited` Relation/`selected_collection` Observation/Checkpoint，每批 10 次真实子进程事务内退出、共 50 Kill 后均从 Durable Checkpoint 恢复。最终 ID 集精确，lost/duplicate/infinite loop/automatic scroll/removed/tombstone/physical delete/Content delete 为 0；20 条 Canary 仅工具、Owner 20 条真实验收 `NOT_RUN`。
- Adapters003：7 个 DOM cases 与 14 个专项单测通过；100 条点赞中 20 条预置收藏，经 5 个显式批次、每批 10 次真实子进程事务内退出、共 50 Kill 后从 Durable Checkpoint 精确恢复。最终 100 Content、100 `liked`、20 `favorited`、120 Observation；lost/duplicate/infinite loop/automatic scroll/removed/tombstone/physical delete/Content delete/分类写入为 0；20 条 Canary 仅工具、Owner 20 条真实验收 `NOT_RUN`。
- Adapters004：17 个 Companion 专项测试和 18 个负向合同用例通过；严格拒绝 JSON 布尔伪整数与损坏的 cursor/Run/Checkpoint 状态组合。20 收藏跨两个散列化收藏夹、20 点赞最终精确为 40 Content、20 `favorited`、20 `liked`、40 Observation，两次 replay 无副作用。upstream path/database primary key、full scan、removed/tombstone/physical delete/Content delete、Classification/Taxonomy 写入、外部 network/platform/upstream execution 均为 0；20＋20 Canary 仅工具，Owner private sidecar 未安装，Owner 40 条真实验收 `NOT_RUN`。
- Adapters006：17 个 Companion 专项测试、38 个公共合成合同 cases、六种非权威状态和 50 次真实子进程事务内 Kill 通过。20 条授权稿件形态清单精确映射为 20 Content、20 Owner-confirmed `saved_current`、20 Observation，识别率 100%、silent loss/fake liked-or-favorited/lost/duplicate/removed/tombstone/physical delete/Content delete/Classification/Taxonomy/network/platform call 均为 0；Owner Canary/真实 transport `NOT_RUN`。
- Adapters007：17 个 Companion 专项测试、43 个公共合成合同 cases、七种非权威状态和 50 次真实进程事务内 Kill 通过。20 条授权用户本人发布作品形态清单精确映射为 20 Content、20 Owner-confirmed `saved_current`、20 Observation；识别率 100%，silent loss/fake liked-or-favorited/lost/duplicate/removed/tombstone/physical delete/Content delete/Classification/Taxonomy/network/platform call 均为 0。Scope 撤回后请求 0、待删除回执 1、历史关系删除 0；Owner Canary/真实 OAuth/API/DOM transport/删除执行器 `NOT_RUN`。
- Adapters008：18 个 Companion 专项测试、58 个公共合成合同 cases、八种非权威状态和 50 次真实进程事务内 Kill 通过。20 条官方 favorites 形态清单精确映射为 20 Content、20 scan-confirmed `favorited`、20 Observation；识别率 100%，fake liked/saved-current、lost/duplicate/delete/classification/network/platform call 均为 0。预算 0、价格/配额未知、429 `Retry-After=120` 早恢复阻断、自动 retry/proxy 0；Owner Canary/真实 OAuth/API/DOM transport `NOT_RUN`。
- Adapters009：18 个 Companion 专项测试、70 个公共合成合同 cases、九种非权威状态和 50 次真实进程事务内 Kill 通过。20 条 Owner 明确 item ID＋最小净化结果精确映射为 20 Content、20 Owner-confirmed `saved_current`、20 Observation；fake liked/favorited、lost/duplicate/delete/classification/network/platform call 均为 0。预算 0、价格/配额/Retention 未批准、429 `Retry-After=120` 早恢复阻断、Cookie/MTop/signing/未文档化 endpoint/自动 retry/proxy 为 0；Owner Canary/真实 OAuth/TOP API/DOM transport `NOT_RUN`。
- Adapters005：40 个公共合成合同 cases、15 个 Companion 专项测试和 50 次真实进程 Kill 通过。两次独立 full scan 各缺失 10/40 时只生成 10 candidate；五类非权威 no-write、80×2、100 concurrent replay、source-scan relabel block、collection rename stable key、removed preservation 通过。duplicate entity、partial write、checkpoint premature advance、removed write、physical delete、Content auto-delete、network/platform call 均为 0；Owner 80 条真实验收 `NOT_RUN`。
- 历史重放：Adapters001 固定到 `ea440535…`，Adapters002 固定到 `050ec0c9…`，Adapters003 固定到 `0939d783…`，Adapters004 固定到 `37ec58cb…`，Adapters006 固定到 `5b6564d2…`，Adapters007 固定到 `a088ea87…`，Adapters008 固定到 `a0f4a346…`；七者都从 final commit blob 验收，Skeleton009 从固定提交 `git ls-tree` 枚举 Extension 源文件。旧 Task/Evidence 不重写。
- 当前 Extension 权限为 `activeTab`/`nativeMessaging`/`scripting`/`sidePanel`；历史 Foundation004 的 3 权限事实保持在固定提交与 Evidence 中。当前无 Host Permission、静态 Content Script、Storage/Cookie/Tabs/Downloads 或远程代码。
- Chromium E2E 在默认 Action 前验证注入与采集 2/2 拒绝；用官方 CDP Action 驱动后才取得临时 `activeTab`，并通过真实 Side Panel 按钮把 XHS/Douyin/Bilibili/Kuaishou/Weibo/Taobao 合成当前页分别送入 Native Host/SQLite；每平台 100 次 Worker 重启仍 0 丢单/重单/错状态。平台形态网络请求由 catch-all route 拦截，实测平台调用 0；Owner Canary 与真实页面均 `NOT_RUN/DISABLED`。
- 首次 Stage 3 Review 根回归：263 tests（260 PASS、3 个需要私有可选输入的测试按设计跳过且由机器 allowlist 核对）；227 个 Companion tests、12 个 Contract tests PASS；full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，coverage 79.66%，33 个依赖漏洞 0，78-member candidate 无 Runtime Data。九个 Task reacceptance、Foundation001–005、Skeleton001–009、Stage 2 Review 与固定 Adapters001–009 predecessor 均 PASS；Foundation003 只验证历史 Owner Runtime evidence，未重新读取 Owner 私有根。该软件 PASS 不改变首次 Review 的 `G3=BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION`；Resume 在其完成时的 Gate 为 `G3=BLOCKED_TECHNICAL`，当前状态以本文件开头的 Task010 后 `G3=REVIEW_PENDING` 为准。
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
.venv/bin/python -B scripts/verify_skeleton_003.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton003-final/software-lane.json --require-evidence
.venv/bin/python -B scripts/run_skeleton_004_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_004.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton004-final/software-lane.json --require-evidence
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s02-skeleton004-final
.venv/bin/python -B scripts/run_adapters_004_acceptance.py
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s03-adapters004-final
.venv/bin/python -B scripts/verify_adapters_004.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters004-final/software-lane.json --require-evidence
.venv/bin/python -B scripts/run_adapters_006_acceptance.py
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s03-adapters006-final2
.venv/bin/python -B scripts/verify_adapters_006.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters006-final2/software-lane.json --require-evidence
.venv/bin/python -B scripts/run_adapters_007_acceptance.py
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s03-adapters007-final
.venv/bin/python -B scripts/verify_adapters_007.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters007-final/software-lane.json --require-evidence
.venv/bin/python -B scripts/run_adapters_009_acceptance.py
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s03-adapters009-final
.venv/bin/python -B scripts/verify_adapters_009.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters009-final/software-lane.json --require-evidence
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

1. 下一独立 Run 只能执行本地 TSK.x2n.uxops.001；不得夹带后续 Stage 5 Task、Stage 4 上传、部署或发布。
2. 开始前重跑 scripts/verify_stage_4_review.py、五份 multimodal verifier 与历史 G3/Task010 verifier；私有 Gold 仍只能保持 disabled/suggestion-only，不能伪造质量通过。
3. 直接 MVP 部署、运行与 online smoke 仍严格位于最终 Stage 6 assurance.005 内；无 Alpha/Beta、固定观察或 soak。Owner Profile、真实账号和 Canary 仍属于该阶段的逐平台有界激活，私有 Manifest 永不进 Git。
4. 继续保持共享认证材料零接触、其他长期开发零重叠；任一 Secret/CDN/Profile/Runtime/越界写入命中立即 Fail Closed。
