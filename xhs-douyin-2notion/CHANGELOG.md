# Changelog

## v0.0.0.1 — Stage 5 / UX-Ops 003

- 完成 `TSK.x2n.uxops.003 / PH.X2N.5.3` 的 CI-synth Local WebUI：仅绑定 `127.0.0.1`，提供 Dashboard、Source、Taxonomy、低置信度 Review、Job、Sink、Model 与脱敏 Diagnostics；Host/Origin/仅内存 CSRF、CSP、no-CORS、静态 DOM `textContent` 与 Owner append-only review 均 Fail Closed。
- 活跃 CLI/Schema/证据迁移为 v2 `owner-mvp-plan`；已退休 v1 仅通过固定 `a67ba091239297b5c9c38a349e0a839680d1c411` 的 disposable Git replay 验证，不在当前运行面复活。21 个合成单测、三类 CSRF/Origin 拒绝、诊断脱敏与历史回放通过；平台、账号、Notion、外网和真实运行时写入均为 0/NOT_RUN。
- 下一独立 Run 仅为本地 `TSK.x2n.uxops.004`；G5、上传、部署与发布仍未授权。无预发布、固定观察或 soak。

## v0.0.0.1 — Stage 5 / UX-Ops 002

- 完成 `TSK.x2n.uxops.002 / PH.X2N.5.2` 的 CI-synth Markdown Library 加固：Renderer `1.1.0`、一次 SQLite 读快照、固定 `platform/content_id` Canonical 路径、生成分类 `INDEX.md` 链接、Hash Manifest、Link Checker 与逐文件原子恢复；重建不写 Canonical 或 Outbox。
- 10,000 条合成 SQLite 输入在删除派生目录后可完整重建，Canonical 内容数/Hash 与 Manifest 一致，分类重命名、合并和重分类不移动主文件，死链/重复内容副本为 0，第二次 rebuild 写入为 0。真实 Runtime、账号、平台、媒体、Notion、网络和下载目录写入均为 0/NOT_RUN。
- 下一独立 Run 仅为本地 `TSK.x2n.uxops.003`；G5、上传、部署、发布仍未授权。无 Alpha/Beta、固定观察或 soak。

## v0.0.0.1 — Stage 5 / UX-Ops 001

- 完成 `TSK.x2n.uxops.001 / PH.X2N.5.1` 的 CI-synth Mock 范围：Items/Categories 版本化加法 schema、精确长文本分块与首批创建/后续 append 均最多 100 block/request、2 req/s 闸门、429/529 Retry-After、Dead Letter、Outbox outage/kill 后 reconcile。
- 增加 14 个明确 x2n 自有 Items/Categories View 定义：Default Table、Category Gallery、Likes、Favorites、Review、Processing Failed、六个平台、Recent 与 Categories directory；同名但不同定义 Fail Closed，不覆盖 Owner View；View API 不可用时仅返回文档化 fallback，绝不伪称创建。真实 Notion、Owner Canary、网络、账号、平台调用均为 0/NOT_RUN。
- 下一独立 Run 仅为本地 `TSK.x2n.uxops.002`；G5、上传、部署、发布仍未授权。无 Alpha/Beta、固定观察或 soak。

## v0.0.0.1 — Stage 4 / G4 Review

- 独立复核 Stage 4 五个固定 Task receipt，并新增 G4 的 Run Contract、机器状态、schema、acceptance runner、fail-closed verifier 与脱敏证据入口。
- 重新运行 ASR、OCR/Vision、Fusion、taxonomy 合成验收；prompt-injection suite 通过，AI 一级 taxonomy mutation 为 0，自动分类仍为 DISABLED_PENDING_PRIVATE_GOLD。
- G4=PASS_CI_SYNTH 只授权下一单本地 TSK.x2n.uxops.001；Stage 4 上传、真实模型/私有 Gold、账号、平台、Notion、部署和发布未授权。无 Alpha/Beta、固定观察或 soak。

## v0.0.0.1 — Stage 4 / Multimodal 005

- 完成 `TSK.x2n.multimodal.005 / PH.X2N.4.5` 的 CI-synth 范围：Owner-only 一级 taxonomy registry、稳定 ID、保留 `unclassified`、全局歧义拒绝、disable/merge、SQLite append-only revision 与物理删除阻断。
- 增加无 Store/Registry mutator 的 deterministic local classifier、不可变 taxonomy snapshot、短生命周期不可序列化输入、cache/provenance ledger、私有 Gold 聚合评测与 calibration/coverage/precision 门；CI synthetic 不能开启自动分类。
- 22 个专项/Store 合成测试覆盖未知或 disabled 分类、分类 registry/revision、阈值/覆盖、私有 Gold 接口、Owner 确认/跨内容纠正拒绝和 CLI 聚合 receipt。Owner taxonomy/private Gold 未提供，`ACC.x2n.ai.006` 仍 pending，`auto_classify=false`，下一独立 Run 仅为 `G4` 复核。

## v0.0.0.1 — Stage 4 / Multimodal 004

- 完成 `TSK.x2n.multimodal.004 / PH.X2N.4.4`：增加仅内存 deterministic extractive fusion、来源归因事实/检索文本、缺失模态和非行动性分歧标记、固定 prompt 数据隔离、Unicode/Bidi/超长/恶意指令与 secret-shaped 输入拦截，以及只接受 grounded schema 的严格 parser。
- 12 个专项合成测试覆盖正常/冲突/缺失模态、恶意 caption/OCR/subtitle、Unicode/Bidi、超长输入、schema 篡改、缓存/版本 Artifact、零 side effect 和不可序列化边界；真实模型、工具、文件、网络、配置、密钥、云、平台、账号与 Notion 调用均为 0/NOT_RUN。
- `ACC.x2n.ai.004` 取得 CI-synth fusion schema/injection isolation 贡献；`ACC.x2n.ai.007` 仅取得 Task004 provenance/cache/budget/cloud-zero 贡献。未创建或修改分类；下一单仅为 `TSK.x2n.multimodal.005 / PH.X2N.4.5`。

## v0.0.0.1 — Stage 4 / Multimodal 003

- 完成 `TSK.x2n.multimodal.003 / PH.X2N.4.3`：增加 owner-managed 本地 JSON OCR/Vision Provider、不可序列化 OCR 文本/视觉描述、Provider/Model/Snapshot/Prompt/Input provenance、同版本缓存、图片/provider-call/超时预算、禁云路由与 `x2n eval ocr|vision --dataset` 私有聚合 Oracle。
- 9 个专项合成测试覆盖同输入缓存、版本化 Artifact、坏 JSON/超时清理、预算与云拒绝、OCR CER Gate、Vision rubric、敏感/不支持输入、私有 Gold schema 和零路径输出；真实模型、云上传、Owner Gold、平台、账号与 Notion 调用均为 0/NOT_RUN。
- `ACC.x2n.ai.002` 与 `ACC.x2n.ai.003` 均保持私有 Gold pending 且对应 Feature Flag 关闭；`ACC.x2n.ai.007` 仅取得 Task003 CI-synth provenance/cache/budget/cloud-zero 贡献。下一单仅为 `TSK.x2n.multimodal.004 / PH.X2N.4.4`。

## v0.0.0.1 — Stage 4 / Multimodal 002

- 完成 `TSK.x2n.multimodal.002 / PH.X2N.4.2`：增加本地 `whisper.cpp` CLI Provider、短生命周期音频/转录、Provider/Model/Snapshot/Prompt/Input provenance、同版本缓存、chunk/provider-call/音频/超时预算、禁云路由与 `x2n eval asr --dataset` 私有聚合 Oracle。
- 9 个专项合成测试覆盖无语音、JSON 损坏、超时、速率/预算、同输入缓存、新版本 Artifact、CER/WER、私有 Gold schema 与临时 FFmpeg 正规化；真实模型、云上传、Owner Gold、平台、账号与 Notion 调用均为 0/NOT_RUN。
- `ACC.x2n.ai.001` 保持 `PENDING_PRIVATE_GOLD_ASR_DISABLED_CI_CONTRACT_PASS`，ASR Feature Flag 关闭；`ACC.x2n.ai.007` 仅取得 CI-synth provenance/cache/budget/cloud-zero 贡献。下一单仅为 `TSK.x2n.multimodal.003 / PH.X2N.4.3`。

## v0.0.0.1 — Stage 4 / Multimodal 001

- 完成 `TSK.x2n.multimodal.001 / PH.X2N.4.1`：已有临时媒体 lease 内的 FFprobe、可选音频提取、代表帧采样、近重复过滤和派生文件清理均有硬上限；不新增持久化、平台、账号、Notion 或模型调用。
- 合成边界覆盖损坏/超限/假 MIME/image bomb/FFmpeg hang/120 分钟与 50 帧上限/清理竞态/24 小时孤儿派生物；32 个专项测试和临时合成本机 FFmpeg/FFprobe smoke 通过，平台调用为 0。
- 历史 G3/Task010 verifier 现可同时复验冻结事实与 Task001 已完成状态；仅授权下一单本地 `TSK.x2n.multimodal.002 / PH.X2N.4.2`，不引入 Alpha、Beta、固定观察或 soak。

## v0.0.0.1 — Stage 3 G3 Independent Recheck

- 独立复验签发 `G3=PASS_CI_SYNTH`：Task010 八 scope Extension→Native→Adapter、完整 capability snapshot/技术 veto、Task005 空响应不删除与 Extension 100 次 restart reconciliation 均重新运行；真实平台调用、自动 fallback、上传、部署和发布均为 0/NOT_RUN。
- 新增可复跑 G3 Run Contract、事实/schema、三份脱敏证据、独立 acceptance runner/negative verifier；首次 Review、Resume contract 和 Task010 final evidence 都以固定摘要/提交验证，不改写历史。
- 只授权下一单本地 `TSK.x2n.multimodal.001 / PH.X2N.4.1`。最终仍直接走正式 MVP deploy/run/online smoke，不引入 Alpha、Beta、固定观察或 soak。

## v0.0.0.1 — Stage 3 / Adapters 010

- 完成 `TSK.x2n.adapters.010 / PH.X2N.3.10` 的公开 CI synthetic 验收：严格八 scope Extension→Native→Adapter dispatch、versioned typed capability result、SQLite v3 derived snapshot、失败 `run_record`/脱敏 `run_failure` 与显式 Owner current-page fallback。
- 保持 legacy Native response compatibility，生成的 Pydantic/JSON Schema/TypeScript 与 Extension consumer 同步；8 个 scope dispatch、平台调用和自动 fallback 分别为 8、0、0。
- Task010 仅贡献 CI synthetic 证据；当前 `G3=REVIEW_PENDING`，Stage 3 上传、Stage 4、部署和真实平台/账号调用仍未授权，下一单为独立 G3 Resume 复验。

## v0.0.0.1 — Stage 3 Review Resume / Direct MVP Contract

- 版本化 `STG.X2N.3.REVIEW.RESUME`，不执行新 DAG Task；原 Stage 3 Review gate fact 与 final commit 字节一致。
- 将八个 relation/list scope 的合法技术终态固定为 `READY_FOR_MVP_ACTIVATION` / `DISABLED_EXTERNAL_GATE`；后者必须 Feature Flag 关闭、平台调用 0、live support claim 0。
- 拆分 Stage 3 `PASS_CI_SYNTH_CONTRIBUTION` 与 Stage 6 完整 `ACC.x2n.rel.006`；真实账号激活和私有 Manifest 移至 Stage 6，仍保持 `NOT_RUN`。
- 新增 `TSK.x2n.adapters.010 / ACC.x2n.batch.002`，DAG 更新为 44 Tasks / 62 Acceptances / 0 cycles；G3 当前只剩 Native dispatch 与 explicit fallback 两个技术 blocker。
- 明确无预发布阶段、固定 30 日健康观察或 soak；G0–G5、前置 Stage6 Tasks 与
  `assurance.005` 精确自有 18 项 Acceptance 之外的 Blocking Acceptance 通过后启动该任务，
  任务内完成激活、Owner MVP、安全门硬通过、模型通过或明确关闭/降级为仅建议模式、回滚、签字、
  部署与 online smoke 后才签发 G6 PASS；安全未知或失败不能降级结算，任务输出也不反向成为启动条件。
- 将 `X2N_DATA_ROOT` 定义为易失 working copy；耐久资产只经 `private_db_client.py ingest|get|list|verify` 写 `Private-MetaDatabase` area＋`domain=xhs-douyin-2notion`。根据客户端真实红线补充：不直接上传 `.sqlite/.db`，一致性快照封装为非运行时归档并按 ≤90 MiB 分片，以 restore manifest 验证重组；禁止 clone。
- 专用 verifier、严格 schema 与 fail-closed 负向突变测试已加入；Resume 20 tests＋旧 Review
  7 tests 共 27/27 PASS，Phase0.1/0.5 回归 PASS。source-freeze 后的 fresh fast lane 结果只以
  `machine/evidence/stage_3/review_resume_mvp/verification.json` 为准，禁止复用旧 lane 成功结论。
  Stage 3 upload、Stage 4、deployment 与真实平台调用保持 false/0。

## v0.0.0.1 — Stage 3 Review / G3 Blocked

- 独立复核 Stage 3 九个 Task、19 条 Acceptance、8 个 Canary 和 G3 四项条件；不执行新 DAG Task、不接触共享认证材料、不吸收其他长期开发线。
- 关闭六个 finding：Owner removed 终态保护、XHS envelope 严格绑定、Douyin 50 次真实子进程 Kill、private batch comparison/增量候选、80 条 Adapter→Canonical→Artifact→Markdown→Notion Mock/Outbox 真正跨层幂等、XHS resume policy `1.1.0` 对齐。
- 同一批 80 条 Adapter 输入生成 80 Canonical、80 Artifact、80 Markdown、80 Notion Mock Page 和 160 终态 Outbox/Receipt；第二轮 Artifact/Markdown/Notion 重复与 Notion replay request 均为 0，五个持久逻辑 scope 的 CDN/private-path finding 为 0。
- 九个 Task Acceptance 全部重新运行并保持 `PASS_CI_SYNTH_SCOPED`；8 个真实 Canary 全部 `NOT_RUN`，平台/真实 Notion/模型/媒体调用均为 0。
- 最终 263 个 root tests（260 PASS、3 个固定 Owner-private 可选 skip）、227 个 Companion tests 与 12 个 Contract tests 通过；full lane 两轮 24/24，0 failure/flaky/silent skip，coverage 79.66%，33 个依赖漏洞 0，78-member candidate 无 Runtime Data。
- 保持五个 Blocker：缺 relation/list Native dispatch、缺显式 fallback 状态机、8 Canary 合法 disabled terminal 未定义、`ACC.data.002`/`ACC.rel.006` 的 Stage 3/6 范围需版本化拆分、Owner 独立授权/私有 Manifest 未运行。
- 结论为 `G3_BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION`；Stage 3 上传与 Stage 4 禁止，下一独立 Run 只能是 `STG.X2N.3.REVIEW.RESUME`。

## v0.0.0.1 — Stage 3 / Adapters 005

- 基于固定 `Adapters009@8c6442a2…` 在独立 worktree 开发；A009 verifier 改为从 final commit blob 验收，旧 Task/Evidence 逐字节不改写，Stage 4/G3/上传均未进入。
- 新增 SQLite `run_record + checkpoint` 关系对账，不改 Schema。仅 `xhs_favorites`/`xhs_likes` 的 succeeded Run、complete/authoritative checkpoint、receipt、Relation 与 Observation 精确一致时可声明完整扫描；扫描必须 ID 不同且时间严格递增。
- 实现 `active -> unknown -> tombstone_candidate`；观察恢复为 active，既有 removed 原样保留。auth/HTTP/platform-change/empty/partial 清除连续缺失链且关系写入 0；代码没有 removed 写入或 Content/Relation DELETE 路径。
- 40 条关系中连续两次各缺失 10 条时，第一次生成 10 unknown、第二次生成 10 candidate；同一 source scan 换 event ID 重放、bounded/空/证据不完整、游标损坏和时间倒退均 Fail Closed。
- 80 条合成输入连续两轮、100 concurrent duplicate、40 个公开合同 cases、15 个专项单测与 50 次真实进程事务内 Kill 通过；重复实体、partial write、checkpoint premature advance、removed、物理删除、Content 自动删除均为 0。重放保持同一 source full-scan 哈希；成功 Run 若丢失 durable checkpoint 则 Fail Closed，不重建空游标。
- Owner Alpha 80 条只新增固定非执行 20+20+20+20 计划；Owner Profile、私有 Manifest、真实账号/平台、Notion、模型与媒体全部 `NOT_RUN`，平台调用 0，不声明 Alpha PASS。
- 最终 256 个 root tests（253 PASS、3 个固定可选 skip）、221 个 Companion tests 与 12 个 Contract tests 通过；full lane 两轮 24/24，coverage 79.61%，33 个依赖漏洞 0，78-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止；下一独立 Run 为 `STG.X2N.3.REVIEW`。

## v0.0.0.1 — Stage 3 / Adapters 009

- 基于固定 `Adapters008@a0f4a346…` 在独立 worktree 开发；A008 verifier 固定到 final commit blob，旧 Evidence 逐字节不改写，A005/G3/上传均未进入。
- 复核 Alibaba 一手 `taobao.item.get`、授权/增值 API、最小必要、可追溯授权、保留期/撤回/服务与合作终止删除及加密/去标识规则。当前审阅没有为本产品建立买家个人收藏列表能力，结论为 `UNKNOWN_DISABLED` 而非“不存在”。
- 新增 credential-free App/OAuth/Scope/cost/quota/retention receipt 与 `TaobaoSelectedIterator`：只接受 Owner 明确提供的最多 20 个 `num_iid` 及严格 `{num_iid,title}` 净化结果；无 network/OAuth/SDK/DOM/MTop/Cookie/signing/代理/自动重试或 raw API response。
- 新增 SQLite `TaobaoSelectedAdapter`：20 条合成条目原子映射为 20 Content、20 Owner-confirmed `saved_current` Relation 与 20 Observation；不伪造 `liked`/`favorited`、平台收藏夹或 full scan，分类、删除及多余字段写入为 0。
- App/OAuth/字段 Scope、增值计划、价格/配额、非零预算、官方 TOP＋净化 transport、local-only/canonical route、目的披露、保留期、撤回删除路径与删除回执均独立 Fail Closed。OAuth 撤回生成 cleanup-required receipt；本 Task 不执行历史 Canonical 删除。
- HTTP 429 必须携带 bounded `Retry-After`；120 秒保持窗内恢复拒绝，无 checkpoint/Canonical 写入、自动请求或代理轮换。70 个公共合成合同 cases、18 个专项单测和 50 次真实进程事务内 Kill 通过，lost/duplicate 均为 0；真实账号/API/Profile/Canary `NOT_RUN`。
- 最终 248 个 root tests（245 PASS、3 个固定可选 skip）、206 个 Companion tests 与 12 个 Contract tests 通过；full lane 两轮 24/24，coverage 79.59%，33 个依赖漏洞 0，77-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止；下一独立 Run 为 `TSK.x2n.adapters.005`。

## v0.0.0.1 — Stage 3 / Adapters 008

- 基于固定 `Adapters007@a088ea87…` 在独立 worktree 开发；A007 verifier 固定到 final commit blob，旧 Evidence 逐字节不改写，A009/A005/G3/上传均未进入。
- 复核 Weibo 一手 favorites/OAuth/Scope/限频/错误码/计划配额与存储规则，以及 RFC 429/`Retry-After`：官方存在当前登录用户 favorites API，但本应用权限、价格、配额和 canonical route 未获批准，Owner 预算为 0，因此真实请求继续关闭。
- 新增 credential-free App/OAuth/cost/quota receipt 与单页 `WeiboSelectedIterator`：仅接受 page 1、固定 20 条、Owner 明确动作的严格净化清单；无 network/OAuth/DOM/cursor transport、自动分页/滚动/重试、代理、购买或 raw API response。
- 新增 SQLite `WeiboSelectedAdapter`：20 条合成 favorites 原子映射为 20 Content、20 scan-confirmed `favorited` Relation 与 20 Observation；`source_collection_id`/`full_scan_id` 为空，fake `liked`/`saved_current`、删除和分类写入均为 0。
- HTTP 429 必须携带 canonical `Retry-After` 秒数或日期；120 秒保持窗内恢复拒绝，checkpoint/Canonical 写入、自动请求、代理轮换均为 0，保持窗后仍需新的显式 Owner batch。Auth/OAuth/Budget/Policy kill 只影响对应 scan，撤权后请求 0 并生成 1 个 cleanup-required receipt。
- 58 个公共合成合同 cases、18 个专项单测和 50 次真实进程事务内 Kill 通过；lost/duplicate/checkpoint premature advance 均为 0。固定 20 条 Canary 只生成非执行计划，真实 App/OAuth/API/CLI/DOM/Profile/账号/Canary `NOT_RUN`。
- 最终 240 个 root tests（237 PASS、3 个固定可选 skip）、188 个 Companion tests 与 12 个 Contract tests 通过；full lane 两轮 24/24，coverage 79.30%，33 个依赖漏洞 0，76-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止。

## v0.0.0.1 — Stage 3 / Adapters 007

- 基于固定 `Adapters006@5b6564d2…` 在独立 worktree 开发；A006 verifier 改为从 final commit blob 验收历史 Task/State/实现/Fixture/Evidence，旧证据逐字节不改写。
- 复核 Kuaishou 一手 OAuth、Open API、应用管理与平台协议：当前只证明经审批应用、动态最小同意和 `user_video_info` 覆盖的授权用户本人发布作品列表；任意个人点赞/收藏仍 `UNKNOWN_DISABLED`，公开详情路由仍为待独立证明的合成假设。
- 新增 credential-free capability receipt 与单次 `KuaishouSelectedIterator`：只接受 page 1、固定 page size 20、Owner 明确选择的严格净化清单；无 network/OAuth/DOM/cursor transport、自动滚动/分页/重试、Cookie/Profile、未知字段或 raw Open API response。
- 新增 SQLite `KuaishouSelectedAdapter`：20 条合成作品原子映射为 20 Content、20 Owner-confirmed `saved_current` Relation 与 20 `selected_collection` Observation；本地 selection ID 不冒充平台收藏夹，`liked`/`favorited` 写入与 full scan 均为 0。
- Scope 撤回立即使新请求为 0、使对应 scan invalidated 并生成待删除标记；本 Task 没有删除执行器，不自动删除历史 Canonical 关系。Partial/Empty/Platform Changed 写入 0；Auth/Scope Revoked/Policy/CAPTCHA 只影响对应 scan。
- 50 次真实进程在 item/checkpoint 事务点随机退出后 lost/duplicate/checkpoint premature advance 均为 0，随后恢复提交一次且 exact replay 无副作用。Canary 固定 20 条且只输出非执行计划；真实 App/OAuth/同意/API/DOM/删除/Profile/账号/Owner Canary 全部关闭或 `NOT_RUN`。
- 最终 233 个 root tests（230 PASS、3 个固定可选 skip）、170 个 Companion tests 与 12 个 Contract tests 通过；full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，coverage 78.99%，33 个依赖漏洞 0，75-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止。

## v0.0.0.1 — Stage 3 / Adapters 006

- 基于固定 `Adapters004@37ec58cb…` 在独立 worktree 开发；A004 verifier 改为从 final commit blob 验收历史 Task/State/实现/Fixture/Evidence，旧证据逐字节不改写。
- 复核 Bilibili 一手开发者协议、OAuth/Scope 与稿件接口：当前只证明经审批应用、关联 UP 主授权和 `ARC_BASE` 覆盖的授权用户自有视频稿件列表；任意个人点赞/收藏和文章列表仍 `UNKNOWN_DISABLED`。无书面自动化许可不得用 crawler/script，这是一项有界研究结论而非“不存在”断言。
- 新增 credential-free capability receipt 与单次 `BilibiliSelectedIterator`：只接受一页、最多 20 条、Owner 明确选择的严格净化稿件清单；无 network/DOM transport、自动滚动/分页/重试、Cookie/Profile、未知字段或 raw API response。
- 新增 SQLite `BilibiliSelectedAdapter`：20 条合成稿件原子映射为 20 Content、20 Owner-confirmed `saved_current` Relation 与 20 `selected_collection` Observation；本地 selection ID 不冒充平台收藏夹，`liked`/`favorited` 写入为 0，`full_scan_id` 始终为空。
- Partial/Empty/Platform Changed 只保留差集证据且 Canonical 写入 0；Auth/Policy/CAPTCHA 各自只使一个 Bilibili scan 失效，历史关系的 removed/tombstone/physical delete/Content delete 均为 0。50 次真实子进程事务内随机退出后 lost/duplicate/checkpoint premature advance 均为 0，随后一次提交与 exact replay 通过。
- Canary 固定 20 条且只输出非执行计划；生产 Feature Flag、真实 API/DOM transport、App/OAuth/书面许可/Profile/账号/Owner Canary 全部关闭或 `NOT_RUN`。现有 Bilibili current-page fallback、Chrome 权限、Native v1、Schema v2 和 A004 evidence 均未修改。
- 最终 224 个 root tests PASS（3 个固定可选 skip）、153 个 Companion tests 与 12 个 Contract tests PASS；full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，coverage 78.69%，33 个依赖漏洞 0，74-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止。

## v0.0.0.1 — Stage 3 / Adapters 004

- 基于固定 `Adapters003@0939d783…` 开发；A003 verifier 改为从其 final commit blob 验收历史 Task/State/实现/Fixture/Evidence，A004 不吸收 `main`、其他 worktree 或共享认证材料。
- 固定审计 `jiji262/douyin-downloader@ef3ad18c…`、tree `ff7774b6…`、version `2.0.0` 与 MIT identity；原始上游 CLI/REST 不满足 x2n 的 build/schema/persistence 合同，故不 vendor、不安装、不导入、不执行，也不成为 Runtime dependency 或真相源。
- 新增严格 `DouyinAdapter` sidecar protocol：每次 action 前核对 commit/tree/version/license、capability、persistence-off、integration lock、executable、resolved lock、transitive-license report 与 SBOM 摘要；递归拒绝未知/缺失字段和 URL/path/credential/raw/media/upstream primary key。
- 新增 `shell=False`、最小环境、bounded timeout/pipe 的 subprocess transport，以及仅数字 `127.0.0.1`、固定 POST path、bounded response 的 loopback REST transport；错误归一化为稳定安全合同，任一 mismatch 在 Canonical transaction 前 Fail Closed。
- 20 条合成收藏跨两个散列化收藏夹映射为 20 Content＋20 `favorited`；20 条合成点赞映射为 20 Content＋20 `liked`，共 40 Observation、两次 exact replay。upstream path/database primary key、full-scan completion、removed/tombstone/physical delete/Content delete 与分类写入均为 0。
- 新增 18 个负向合同用例、5 个非权威删除保护用例、固定 20＋20 非执行 Canary plan 与只能阻断不能晋级的 shadow comparator；JSON 布尔伪整数和损坏的 cursor/Run/Checkpoint 状态组合均 Fail Closed。approved pin 不变，观察到的当前 candidate 为 `BLOCKED_SHADOW`、promotion 0。
- 当前一手资料审阅未发现明确的个人点赞列表或收藏夹/列表 Scope；这是范围化研究结果而非不存在断言。抖音真实 upstream/private sidecar/Profile/账号/平台/Canary 均 `NOT_RUN`，两项生产 Feature Flag 关闭。
- 最终 216 个 root tests PASS（3 个固定可选 skip）、136 个 Companion tests 与 12 个 Contract tests PASS；full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，coverage 78.36%，33 个依赖漏洞 0，73-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止。

## v0.0.0.1 — Stage 3 / Adapters 003

- 基于固定 `Adapters002@050ec0c9…` 开发；A002 verifier 改为从其 final commit blob 验收 Task、状态、实现、Fixture、Receipt 与 Evidence，A003 新文件不会污染历史结论。
- 新增小红书点赞 clean-room visible-batch extractor：仅在 Owner gesture 后读取最多 20 条可见卡片，输出 stable ID、Canonical Page URL、净化标题/类型与固定 `unclassified` Inbox；无 Host Permission、静态 Content Script、网络、Cookie/Profile、自动滚动/分页、事件合成或 like/unlike/账号状态改变。
- 新增 SQLite `xhs_likes` Adapter：复用 platform＋stable ID Content key，原子写独立 `liked` Relation、Observation 与 versioned Checkpoint；既有 `favorited` Relation 和 Owner 分类不覆盖，自动归档、Classification/Taxonomy 写入均为 0。
- 严格 successor、精确最后批次 replay、partial/auth/verification/platform-change/empty-unverified 不推进或完成；bounded Canary 不冒充 full scan，只有权威可见结束可完成。20 条 Canary 仍是非执行计划，Owner/private-gold/真实页面均 `NOT_RUN`。
- 新增 7 个 DOM Fixture 与 100 条控制数据，其中 20 条预置收藏 Relation；5 个显式批次各执行 10 次真实子进程事务内退出，共 50 Kill。最终精确为 100 Content、100 `liked`、20 `favorited`、120 Observation；lost/duplicate/infinite loop/automatic scroll/removed/tombstone/physical delete/Content delete 为 0。
- 已审阅小红书一手材料只证明用户可见的笔记/收藏/赞过自主管理面；未在所审阅 Open/Mini Program 材料中发现个人点赞读取 API。这是范围化研究结果而非不存在断言，因此生产能力默认 deny。
- 最终 208 个 root tests PASS（3 个固定可选 skip）、119 个 Companion tests 与 12 个 Contract tests PASS；full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，coverage 77.79%，33 个依赖漏洞 0，71-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止。

## v0.0.0.1 — Stage 3 / Adapters 002

- 基于固定 `Adapters001@ea440535…` 开发且不吸收 `main`/其他 worktree；历史 Adapters001 verifier 改为固定提交回放，Skeleton009 Extension 源清单改从历史 tree 枚举，避免后代新增文件污染旧验收。
- 新增小红书收藏 clean-room visible-batch extractor：只在 Owner gesture 后读取最多 20 条稳定 ID、Canonical Page URL、净化标题/类型和可见收藏夹映射；无 Host Permission、静态 Content Script、网络、自动滚动/分页、事件合成、账号状态变化或 Cookie/Profile 读取。
- 新增 SQLite `xhs_favorites` Adapter：原子写 Content、`favorited` Relation、`selected_collection` Observation 和 versioned Checkpoint；严格 successor、精确最后批次 replay、部分批次保留证据但不推进、未知结束不完成。
- Canary 固定 20 条且只生成非执行计划；bounded scope 与 full scan 分离，只有权威可见结束可写 `full_scan_id`。真实页面/账号/Profile/Canary 继续关闭或 `NOT_RUN`。
- 新增 7 个 DOM Fixture 与 100 条两收藏夹控制数据；5 个显式批次每批 10 次真实子进程在事务内随机退出，共 50 Kill。恢复只读 Durable Checkpoint，最终 ID 集精确，lost/duplicate/infinite loop/automatic scroll/removed/tombstone/physical delete/Content delete 均为 0。
- 官方一手材料复核只确认用户可见自主管理与商家/分享开发面，未在已审阅来源中找到个人收藏读取 API；此为范围化研究结论而非“不存在”断言，因此生产能力默认 deny、当前页 fallback 保留。
- 最终 201 个 root tests PASS（3 个固定可选 skip）、105 个 Companion tests 与 12 个 Contract tests PASS；full lane 两轮 24/24 Blocking Gate PASS，coverage 77.73%，33 个依赖漏洞 0，69-member candidate 无 Runtime Data。`G3=NOT_RUN`，Stage 3 上传禁止。

## v0.0.0.1 — Stage 3 / Adapters 001

- 以 Stage 2 PR #78 合并提交为 Task base，核对 x2n/Dual-Plane 两条远端门禁成功后授权 Stage 3；新增 transition fact，不改写 G2 历史 Evidence。
- 新增专用 Profile launcher：只选择固定 OS Chrome candidate 和 `X2N_DATA_ROOT` 内的平台 Profile，显式确认后只开内部新标签；无任意 executable/path/URL、remote debugging、Cookie 导入导出、自动登录或验证码绕过。
- 新增五分钟 enum-only session checkpoint；只保存 platform/signal/time，缺失、未来、过期、login/verification required 与 platform drift 均给出最小 Blocked User Action，Profile path 和账号标识不输出。
- 新增八组件 `x2n doctor`：Native Host/Companion/DB 核心阻断，FFmpeg/Provider/Notion 与 Profile Adapter 缺失按能力降级或单项阻断；每项有稳定错误码和不含 Secret/path 的修复动作。
- 新增跨进程全局 Adapter `flock` 非等待互斥、30 秒 batch/3 秒 item 持久低频门、时钟回退/弱策略/状态损坏 Fail Closed；不 sleep、不自动重试。
- 新增 batch deletion guard：登录过期、HTTP、DOM、空数组、部分扫描均 removed 0；两次连续完整成功最多产生 `tombstone_candidate`，物理删除和 Content 自动删除为 0。
- 新增 7 session＋7 batch 公共合成 Fixture、16 个专项单测、独立 Acceptance runner/verifier 与 Public Code/Private Runtime 扫描；Owner Profile、真实账号/平台、Canary 与 G3 均 `NOT_RUN`，Stage 3 上传禁止。
- 最终 194 个 root tests PASS（3 个固定可选 skip）、92 个 Companion tests 与 12 个 Contract tests PASS；full lane 两轮 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，coverage 77.66%，33 个依赖漏洞 0，67-member candidate 无 Runtime Data。Stage 2 verifier 固定到已合并 Review final commit，旧 G2 Evidence 逐字节不变。

## v0.0.0.1 — Stage 2 Review / G2

- 独立复核 Skeleton001–009 的 Task、Acceptance、固定提交、九份历史 evidence 与 Stage 2 全提交；Review 不执行新 DAG Task，也没有 `apps/`/`packages/` 产品改动。
- 修复 8 个 finding：Skeleton005 后代分支历史回放、76 tests/76.93% 文档漂移、软件 lane 动态 G1 误报、实际工具链未绑定、G2 跨 Task Oracle、九证据冻结、逐版本隐私扫描、Task Pack/PR merge/历史 Review 后代重放/G2 事实负向闭合。
- 五项项目原生本地 G2 条件通过：六平台独立 current-page E2E、zero duplicate、zero CDN persistence、媒体清理、Notion outage 不阻断 canonical/Markdown；真实平台、真实 Notion、模型、媒体网络与 Owner Chrome 调用均为 0/NOT_RUN。
- 最终 186 root tests PASS（3 fixed optional skips）、76 Companion tests PASS；两份独立 full lane 各 24/24，coverage 76.93%、33 dependencies vulnerability 0、65-member candidate SHA 完全一致，实际工具链与政策一致。
- `G2=PASS` 只授权 Stage 2 整体上传；远端 CI/merge 保持 `PENDING_POST_G2_UPLOAD`，此前 Stage 3 禁止开始。正式 Verifier release-candidate 因原任务包缺少 canonical `MANIFEST` role 保持 `BLOCKED_REQUIREMENT_GAP`。

## v0.0.0.1 — Stage 2 / Skeleton 005

- 保持 SQLite Schema v2 与 Canonical 事务边界不变，新增一致性 snapshot、精确 Outbox event claim、retry/dead-letter state、私有 Notion Mapping 与 append-only Sink Receipt primitive；Notion 永不进入 Canonical 写事务。
- 新增固定 `runtime/library/content/<platform>/<content_id>.md` 的确定性 Markdown renderer；路径不依赖标题/分类，同目录 `0600` 临时文件经 file/directory `fsync` 后原子替换，symlink/path escape Fail Closed。`Unclassified` 只生成派生 Index，不创建 Taxonomy row。
- 新增 Notion `2026-03-11` Data Source/Page 语义合同、Items/Categories 加法式 Schema、Owner category 显式 Relation mapping、projection-hash no-op、用户字段保留与每 `content_key` 唯一 Page 约束；实现仅为进程内 deterministic Mock，不含真实 HTTP/SDK/凭据。
- 新增 2 req/s 串行限速、429/529 `Retry-After`、timeout/reset、一小时 outage、最大 4 次尝试、Dead Letter 与成功后本地 Receipt 前 kill-reconcile；重复 Page Fail Closed，Canonical/Markdown 在 Notion outage 时继续完成。
- 六平台 80 个 Canonical 输入两轮投影通过：80 Markdown、80 Notion Mock Pages、160 Outbox/Receipts；无半文件、无断链、Frontmatter invalid 0、CDN finding 0、duplicate Page 0、hash 相同 replay request 0、真实 Notion call 0。16 个 sink 单测覆盖长文本、特殊字符、分类 Relation、原子 kill、symlink、Schema conflict 与反向长队列。
- Skeleton004 历史 Task/State/Policy/Evidence 固定到 `36bd1213…`，旧 verifier 从最终 commit blob 验收，不再读取 S005 的当前状态或实现。
- 根回归 175 tests PASS、3 个显式可选 Owner-private input skip；76 个 Companion tests PASS。两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 76.93%，33 dependencies 的 OSV vulnerability 0，65-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.md.001` 与 `ACC.x2n.notion.001/.002/.003` 仅 CI-SYNTH/Mock scoped pass；真实 Notion 与 Owner Canary 均 `NOT_RUN`。`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 只能执行 `STG.X2N.2.REVIEW`。

## v0.0.0.1 — Stage 2 / Skeleton 004

- 新增 `CurrentPageOrchestrator`，把六平台已经净化并通过 Native v1 Contract 的 `capture_current` 输入接入 SQLite Canonical Store；不增加平台网络、媒体处理、分类、Markdown 或 Notion 行为。
- 保持 Schema v2 不变，以两事务状态机落地：事务 1 原子写 Request Ledger、running Run、Content、Owner-confirmed `saved_current` Relation、SourceObservation 与 `canonical_committed` Checkpoint；事务 2 追加/复用无私有 payload 的确定性 placeholder Artifact，并原子完成 Checkpoint 与 Run。
- Native Job UUID 与内部 Opaque Run 确定性映射；canonical commit 后即使进程退出，重复 `capture_current`、`GET_JOB` 或 bounded resume 都可只凭 SQLite 完成，不需要原请求 payload。请求冲突、Canonical URL/Content ID 不一致、非空分类 ID 均 Fail Closed。
- Receipt 只输出 Job、状态、计数和 entity hash refs，不输出页地址、内容 ID、标题、本机路径或匹配值；Classification、Renderer、Markdown、Notion 与媒体处理全部明确为 `DOWNSTREAM_NOT_RUN`。
- 合成验收通过六平台、80 个输入连续两轮、100 个并发重复、4 个 kill point 与完整 scoped provenance；重复实体、stuck Run、non-replayable state、broken trace、private placeholder payload 均为 0。
- Extension 当前页成功状态改为 Canonical Store 已提交；Service Worker restart 对账以 SQLite `completed` 为准，仍不触碰 Owner Chrome/Profile、真实账号或平台网络。
- Skeleton003 历史 Task/State/Policy/Evidence 固定到 `d5f61f30…`；历史验收读取最终 blob，当前树继续媒体安全回归且不重写历史 Evidence。
- 根回归 166 tests PASS、3 个显式可选 Owner-private input skip；59 个 Companion tests PASS。两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 74.61%，33 dependencies 的 OSV vulnerability 0，62-member source candidate 无 Runtime Data且可确定性重建。G2、Stage 2 上传、真实平台/媒体/模型/Notion/Markdown 仍未运行，下一独立 Run 为 `TSK.x2n.skeleton.005`。

## v0.0.0.1 — Stage 2 / Skeleton 003

- 实现进程内、不可序列化且 `repr` 脱敏的 `EphemeralMediaSource` 与 `ValidatedMediaTarget`；原始 CDN URL、Query/签名值不进入 SQLite、日志、Evidence、Markdown、Notion-export 或 Artifact。
- 实现六平台精确 suffix 的 HTTPS/443 URL firewall：拒绝 userinfo、IP literal、非标准端口、fragment、多重编码 traversal、控制字符和 lookalike；校验全部 DNS answer 为 global，拒绝 IPv4-mapped IPv6，并对每个 redirect 重新解析/解析 DNS。
- 定义绑定已校验 IP、保留 TLS hostname 的 transport 合同；本 Task 不提供生产 transport，也未执行真实媒体网络。安全下载使用调用方生成路径、`0600`、hard-link promotion、64 MiB stream limit、60 秒 Deadline、identity encoding、MIME sniff 与必需的隔离 Inspector。
- 扩展 Canonical Store media lease primitive，数据库继续没有 URL 列；acquisition 前先登记 URL-free cleanup identity，校验后再原位 finalize hash/MIME/size metadata，使下载/登记中途的删除失败也能写入 `cleanup_pending` 高优先级回执；实现共享 active-context/独占 cleaner 生命周期锁，成功/异常立即清理、crash orphan 最长 24h、活跃 lease 零误删。
- 新增固定 `db,markdown,logs,notion-export,artifacts` 逻辑 scope 的 chunk-boundary CDN scanner 与 `x2n verify cdn-zero`；拒绝任意路径、symlink 和 matched-value/private-path 输出。
- 合成验收通过 512 URL fuzz（64 allowlisted、448 forbidden、0 mismatch）、32 SSRF（0 forbidden success、0 local read）、8 cleanup chaos、8 acquisition resource block 和 23 个媒体安全单测；FFmpeg/image decode/repeated key frame/ASR/OCR 保持 `DOWNSTREAM_NOT_RUN`。
- Skeleton009 历史 Task/State/Policy/Evidence 固定到 `0af2d3b2…`；历史验收读取最终 blob，当前树继续六平台回归且不重写历史 Evidence。
- 根回归 158 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 73.67%，33 dependencies 的 OSV vulnerability 0，61-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.media.001–003` 与 `media.004` acquisition layer 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.004`。

## v0.0.0.1 — Stage 2 / Skeleton 009

- 复核淘宝一手 API/协议/隐私规则：`taobao.item.get` 是需授权的增值 API，以 `num_iid` 标识商品；私有商品/订单/收藏数据需要 OAuth，TOP 官方签名协议有文档，但本应用无 App/OAuth/API Permission/付费计划/字段范围/保留期/删除回执审批。
- 实现淘宝独立 CI-synthetic 当前页 detector/extractor：精确 `item.taobao.com/item.htm`、合成数字 `num_iid`、location/canonical/OG/detail `data-num-iid` 交叉校验、净化标题/null、既有 ContentType 与 provenance；不读取 media `src`、raw DOM、Cookie 或浏览器状态。
- 新增 8 个 DOM Fixture（4 ready、4 platform-changed）、14 个 Policy Fixture、2 个 Scope/Retention 未知拒绝、16 个未文档化 Cookie/MTop 签名输入拒绝及 7 个 schema-drift 拒绝；真实路由只登记为未验证合成假设。
- 页面观察 `id` 后只把值存为 `content_id`，Canonical 固定为无 Query/Fragment 的 Host/Path，继续满足 Native v1 合同；生产 TOP/OAuth transport、凭据/Cookie/Profile 输入、DOM fallback 与 Owner Canary 全部关闭或未运行。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；六平台真实按钮合成采集、Action 前各 2 个拒绝、各 100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton008 历史 Task/State/Policy/Evidence 固定到 `7e8a3dbf…`，旧验收只读取历史 blob；当前树继续此前五个平台安全与行为回归，历史 Evidence 不重写。
- 根回归 149 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，60-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.006` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.003`。

## v0.0.0.1 — Stage 2 / Skeleton 008

- 复核微博一手 API/CLI/协议：`statuses/show` 需要 OAuth 且只查询授权用户本人发布内容；应用/user/IP 有频率控制，额外容量可能涉及付费，但本应用价格、Scope、配额与付费层均未批准。
- 实现微博独立 CI-synthetic 当前页 detector/extractor：精确 `www.weibo.com`、合成 `/detail/<mid>`、location/canonical/OG/detail `data-mid` 交叉校验、净化标题/null、五类既有 ContentType 与 provenance；不读取 media `src`、raw DOM、Cookie 或浏览器状态。
- 新增 8 个 DOM Fixture（4 ready、4 platform-changed）、12 个 Policy Fixture、2 个真实形态预算拒绝、16 个任意 URL/Redirect-SSRF 拒绝及 7 个 schema-drift 拒绝；公开详情/用户状态路由只登记为未验证合成或预算拒绝假设。
- 预算默认 0；真实页、生产 API/CLI、OAuth/凭据输入、DOM fallback、任意 URL preview/proxy/redirect transport 与 Owner Canary 全部关闭或未运行。官方 CLI 只登记，未安装、未登录、未执行。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；五平台真实按钮合成采集、Action 前各 2 个拒绝、各 100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton007 历史 Task/State/Policy/Evidence 固定到 `17f1988b…`，旧验收只读取历史 blob；当前树继续 XHS/Douyin/Bilibili/Kuaishou 安全与行为回归，历史 Evidence 不重写。
- 根回归 140 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，59-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.005` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.009`。

## v0.0.0.1 — Stage 2 / Skeleton 007

- 复核快手一手 Open Platform/协议：OAuth 需应用登记、动态用户同意与最小 Scope；`user_video_info` 只证明授权用户已发布作品列表和 `photoId` 详情，不证明任意公开当前页、点赞/收藏读取或自动化 DOM 采集权限。
- 实现快手独立 CI-synthetic 当前页 detector/extractor：精确 `www.kuaishou.com`、合成 `/short-video/<id>`、location/canonical/OG/detail `photoId` 交叉校验、净化标题/null、`video/unknown` 与 provenance；不读取 media `src`、raw DOM、hydration、Cookie 或浏览器状态。
- 新增 8 个 DOM Fixture（4 ready、4 platform-changed）、10 个 Policy Fixture、2 个真实形态 `BLOCKED_AUTH` 与 5 个 schema-drift 拒绝；公开短视频路由只登记为未验证的合成假设。
- 真实页保持 `BLOCKED_AUTH`，生产 API transport、Access Token/Cookie/Profile 输入、DOM fallback 与 Owner Canary 全部关闭或未运行；无真实账号、OAuth、平台请求或自动滚动/分页。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；四平台真实按钮合成采集、Action 前各 2 个拒绝、各 100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton006 历史 Task/State/Policy/Evidence 固定到 `a314a1d…`，旧验收只读取历史 blob；当前树继续 XHS/Douyin/Bilibili 安全与行为回归，历史 Evidence 不重写。
- 根回归 131 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，58-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.004` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.008`。

## v0.0.0.1 — Stage 2 / Skeleton 006

- 复核 Bilibili 一手 Open Platform/协议：官方能力要求应用入驻、OAuth、具体 Scope 与关联 UP 主授权，只证明授权稿件管理，不证明任意当前页、点赞或收藏读取；真实页面/API 和 Owner Canary 保持 `UNKNOWN_DISABLED / NOT_RUN`。
- 实现 Bilibili 独立 CI-synthetic 当前页 detector/extractor：视频与文章稳定 ID、规范 Host/Path、净化标题/null、`video/text/image_gallery/mixed/unknown` 与 provenance；不读取 media `src`、hydration、raw DOM、Cookie 或浏览器状态。
- 新增 10 个 DOM Fixture（5 ready、5 platform-changed）、8 个 Policy Fixture 与 5 个 schema-drift 拒绝；文章 `/read/cv…` 明确登记为未验证现实路由，只是合成 Oracle。
- 对 `?p=<n>` 分 P 语义 Fail Closed；当前 v1 Canonical Contract 不保存 Query，禁止把所选分 P 错折叠成顶层视频。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；真实按钮采集、Action 前 2 个拒绝、100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton002 历史 Task/State/Policy/Evidence 固定到 `2a91efbc…`，旧验收只读取历史 blob，同时保留当前 XHS/Douyin 行为回归；历史 Evidence 不重写。
- 根回归 122 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，57-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.003` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.007`。

## v0.0.0.1 — Stage 2 / Skeleton 002

- 实现抖音当前详情页 clean-room 合成检测/提取：稳定字符串 ID、无 Query/Fragment 的 canonical 重建、净化标题/null、视频/图集/unknown 类型与 provenance；身份冲突、feed card、多详情根和非合成短链身份均 `X2N_PLATFORM_CHANGED`。
- 新增 8 个公共安全 DOM Fixture（4 ready、4 platform-changed）与 16 个短链安全用例（3 resolved、13 blocked）；覆盖五类 Redirect status、相对跳转、精确请求 URL、非允许 Host/Path、IP、lookalike、userinfo、port、loop、limit、额外响应字段、非 Redirect status 与 transport failure。
- 短链实现严格是 network-free、transport-injected 的 CI synthetic core；Extension/Service Worker/Companion 均无生产 requester，真实短链和真实页面保持 `UNKNOWN_DISABLED`，没有新增 Host Permission、Native Action 或 v1.0 Contract 字段。
- Service Worker 在注入前后复核 focused active tab 与完整 URL，阻止导航竞态；Side Panel 增加 stale refresh generation 与 in-flight guard，不再把迟到成功误报为“未执行”或允许重复提交。
- XHS/Douyin 两条 Playwright 链路均通过真实 Side Panel 按钮进入 Native Host/SQLite；所有平台形态请求被 catch-all route 拦截，实测平台调用 0；各 100 次 Worker restart 均 0 丢单/重单/错状态。
- Skeleton001 历史 Task/State/Policy/Evidence 固定到 `894553c6…`，当前树只做追加式 XHS 行为回归；历史 acceptance receipt 保持逐字节不变。
- 根回归 112 tests PASS、3 个显式可选私有输入 skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，56-member source candidate 无 Runtime Data。
- `ACC.x2n.capture.002` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；Owner Canary、真实账号/平台、生产网络、G2 与 Stage 2 上传均 `NOT_RUN/DISABLED`，下一独立 Run 为 `TSK.x2n.skeleton.006`。

## v0.0.0.1 — Stage 2 / Skeleton 001

- 实现小红书当前详情页 clean-room 检测与提取：稳定 ID、无 Query/Fragment 的规范 URL、净化标题或显式 null、图文/视频/unknown 类型及字段状态；身份冲突和 feed card 均返回 `X2N_PLATFORM_CHANGED`。
- 新增 5 个公共安全合成 DOM Fixture；3 个 ready 与 2 个 platform-changed Observation Diff 全部通过，媒体/raw DOM/Query/Fragment 返回或持久化为 0。
- Extension 增加最小 `scripting` 权限，但仍无 Host Permission、静态 Content Script、Storage/Cookie/Tabs/Downloads 或远程代码；默认 Action 前注入和采集均拒绝，Action 后仅凭临时 `activeTab` 执行隔离世界提取。
- Playwright 通过 Chromium 官方 CDP 默认 Action 触发测试真实权限语义；合成当前页进入 Native Host/SQLite skeleton Job 后，100 次 Service Worker 重启 0 丢单/重单/错状态。
- 两轮 full lane 共 24/24 Blocking Gate 通过，blocking failure/flaky/silent skip 为 0；新增的并发回归测试修复 SQLite `-wal/-shm` 在连接关闭期间消失引发的 chmod 竞态，Canonical DB 文件仍严格 Fail Closed。
- 历史 Foundation/Review verifier 改为固定提交取证并对 live tree 做追加式验证；历史测试数、权限与 Gate 事实不改写，当前新增测试不再被误判为历史漂移。
- 当前能力位为 `ci_synth_only`；小红书一手开放资料未提供可验证的个人内容读取能力，真实页面与 Owner Canary 保持 `UNKNOWN_DISABLED / NOT_RUN`。
- `ACC.x2n.capture.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`，Stage 2 禁止上传，下一独立 Run 为 `TSK.x2n.skeleton.002`。

## v0.0.0.1 — Stage 1 Review / G1

- 独立复核 Foundation001–005 的 Task、Acceptance、固定提交与历史证据；Review 不执行新 DAG Task，下一产品 Task 固定为 `TSK.x2n.skeleton.001`。
- 修复 8 个 Review finding：DAG/状态漂移、full lane 缺少逐执行身份、Stage 1 历史扫描缺口、重复 JSON 键、Runtime CLI 过期 Gate 输出、生成依赖/Build 树造成的零接触扫描误报、缺少 Task Pack 固定版本精确差分，以及 PR 合成 merge commit 误纳入 `main` 并行改动。
- 两轮 full lane 共 24/24 阻塞执行通过，silent skip/failure/flaky 为 0；整体风险覆盖率 70.88%，7 个关键模块均过阈值，33 个依赖的 OSV 漏洞为 0。
- Stage 1 逐提交变更 blob、提交消息、当前 Source 与 workflow 的 Secret/Private/CDN 扫描为 0；53-member 候选制品无 Runtime Data，确定性复现一致。
- 当前结论为 `REVIEW_COMPLETE / G1_PASS / STAGE_2_AUTHORIZED / STAGE_1_REMOTE_UPLOAD_AUTHORIZED`；远端 x2n CI 仍为 `PENDING_POST_G1_UPLOAD`，真实账号、平台、Notion、模型、媒体与 Sink 均 `NOT_RUN`。

## v0.0.0.1 — Stage 1 / Foundation 005

- 新增根级 `x2n-ci.yml`：changed-scope 快速门禁与 macOS full-release 候选门禁；Actions 全 SHA pin、`contents: read`、checkout 不持久化凭据，阻断项不可 `continue-on-error`。
- 软件门禁覆盖 format/lint/type/unit/contract/migration/integration/Extension E2E；full lane 两次重放，风险覆盖阈值登记到机器 policy，关键 Store/Host/Runtime/Contract 模块提供 branch evidence。
- 新增合成 seeded-failure 自测、Secret/Private/CDN/Fixture scan、SAST/SARIF、CSP、匿名 OSV、License、33-component Foundation005 SBOM 与确定性 source candidate allowlist；Runtime Data 和 Unknown License 阈值均为 0。
- 新增 `x2n-synthetic-model-contract-v1@1.0.0` 与模型 System Card；Dataset Contract 通过，但 ASR/OCR/Fusion/Classify/真实 Red Team 均未运行且 Feature Flag 关闭，自动分类等待 `ACC.x2n.ai.006`。
- 该 Foundation005 Run 当时只证明本地合成 CI baseline；远端 GitHub Actions、正式 Release、真实模型、账号、平台、Notion 和媒体均 `NOT_RUN`。其历史证据保持 `G1=NOT_RUN`，下一独立 Run 当时只能做 Stage 1 Review。

## v0.0.0.1 — Stage 1 / Foundation 004

- 新增固定开发 Extension ID 的 Chrome MV3 Side Panel，权限精确为 `activeTab`、`nativeMessaging`、`sidePanel`，无 `host_permissions`、Content Script、远程代码或 Extension Storage。
- Save/Sync/Review/Status/Settings 五区可访问；20 个公共合成 URL 覆盖六平台支持/非支持识别，所有平台动作仍 `executable=false`。
- 新增短进程 Native Messaging Host：精确 Origin、1 MiB 上限、未知动作/字段/版本与 Shell/Path/任意 URL 注入拒绝；重复 Request 只返回同一个 SQLite skeleton Job。
- 用户级 installer 默认 `plan`，写操作需要固定确认词；依赖从 frozen `uv.lock` 导出并强制 hash 校验，私有 Runtime 在 staging 中验证后原子替换；首次/升级失败均清理临时目录并保留旧 Runtime，安装/卸载用内容 hash 拒绝被篡改或非自有文件。
- Playwright 在临时 HOME/Profile/Runtime 中完成真实 Extension E2E：20/20 识别、五区导航、0 uncaught console error、100 次 Service Worker 终止/重启、任务丢失/重复/错状态均为 0；截图与 trace 只保留聚合 hash。
- 新增当前 30-component SBOM 与 Playwright/fsevents NOTICE；`.npmrc` 强制禁用 install scripts，验收执行数为 0。历史 Foundation002 的 26-component SBOM 保持原事实。
- Owner Chrome 安装/Canary、真实账号、平台调用、自动滚动、账号状态改变、Markdown/Notion、模型和媒体均未运行；该 Foundation004 Run 的历史状态为 `G1=NOT_RUN`，下一独立 Run 当时为 `TSK.x2n.foundation.005`。

## v0.0.0.1 — Stage 1 / Foundation 003

- 新增只接受显式 `X2N_DOWNLOAD_DESTINATION`/`X2N_DATA_ROOT` 的 Owner-only Private Runtime；无默认目录、任意路径参数或符号链接逃逸。
- 落地 SQLite Schema v2：17 tables、9 indexes、15 triggers，启用 WAL、FK、FULL synchronous、busy timeout 与启动完整性检查。
- Content/Relation/Artifact/Observation/Classification、Owner Taxonomy、Checkpoint、Request Ledger、Outbox/Receipt、Notion Mapping、Media Lease 和 Recovery Event 进入同一 Canonical Store；Artifact 等追加记录禁止更新/删除。
- 迁移支持前进与强制备份后降级；Backup/Restore 校验文件 Hash、Schema、完整性、表计数与逻辑摘要并原子替换。当前同盘副本不冒充异地灾备。
- 纯合成门禁覆盖 80 条连续两次、100 个并发重复消息和 10k DB；重复副作用、数据丢失、不可读记录和 orphan FK 均为 0，`integrity_check=ok`。
- Owner 私有根只初始化 Schema v2 空库，不含账号、平台内容、媒体或 Sink 数据。该 Foundation003 Run 的历史状态为 `G1=NOT_RUN`，下一独立 Run 当时为 `TSK.x2n.foundation.004`。

## v0.0.0.1 — Stage 1 / Foundation 002

- 冻结 `1.0` IPC、Canonical、Relation、Observation、Artifact、Taxonomy、Classification、Sink、Health、Error、Provenance 与 Compatibility Contract；Pydantic 是 JSON Schema、错误 Registry 和 TypeScript shared enums 的生成真源。
- 默认拒绝未知字段/版本/动作；固定 Native Origin 无通配符，消息有大小与动作边界，不存在 Shell、任意路径、任意 URL、Cookie/Header/Token 输入面。
- 用 opaque ephemeral media refs 表达临时媒体，Canonical Contract 无平台媒体 URL 字段；四类 key 确定性校验，Artifact append-only，一级分类仅 `created_by=owner`。
- Markdown/Notion 合成 Provenance 从最终节点连通 Canonical、Observation、Adapter、Artifact、Classification、Run 与 Renderer；真实 Sink/Canary 未运行。
- 新增 16 个有效 round-trip、22 个负向 fixture 和 106 个 Native fuzz；生成物 `--check` 与 TypeScript strict compile 通过。
- 精确锁定 5 个 Python Runtime registry packages 与 21 个 TypeScript build-only registry packages，生成 26-component CycloneDX SBOM；npm install script 为 0。
- 三项 Acceptance 仅在当时 Contract/合成范围 PASS；真实 Host/Job、SQLite/Migration/Integrity、Markdown/Notion 均为 `DOWNSTREAM_NOT_RUN`。该 Foundation002 Run 未运行 G1，下一独立 Run 当时为 `TSK.x2n.foundation.003`。

## v0.0.0.1 — Stage 1 / Foundation 001

- 新增受治理 Skill 入口、OpenAI agent metadata、npm/uv workspace 与冻结 lock；当前第三方 package 和 install script 均为 0。
- 建立无权限、无 Side Panel/Background/Host Permission 的 MV3 Extension scaffold，以及不含 Server、IPC、DB、Adapter、模型、媒体或 Sink 的 Python Companion scaffold。
- 增加纯合成 lifecycle rehearsal：install、self-test、synthetic Canary、upgrade/rollback dry-run、diagnose、uninstall dry-run，全部明确真实产品 lifecycle 为 `DOWNSTREAM_NOT_RUN`。
- 在隔离临时 HOME 的新副本验证 frozen locks、Extension 与正/负 lifecycle；证据不含私有路径、URL、凭据或内容。
- `TSK.x2n.foundation.001` 当时范围 PASS；该 Run 未运行 G1，下一独立 Run 当时为 `TSK.x2n.foundation.002`。

## v0.0.0.1 — Stage 0 Review Resume / G0 PASS

- 依据 `CE-X2N-20260720-S00-REVIEW-RESUME` 将共享认证材料限定为 x2n 外部、Owner 管理的并行基础设施；x2n 不读取、使用、改变或显示它，也不修改全局 Git 配置或 Credential Helper。
- 保留 Secret/CDN 不可 Owner waiver 的全局规则；新增匿名公开 GitHub Snapshot 工具与 11 项零接触控制。
- 用闭合 `0600` 私有回执记录 Owner 决策；公开证据不含回执 ID、时间、哈希、账号、URL、本机路径或材料值。
- 完整重跑当前树、项目历史、私有根、Local Remote、原始输入、Phase 0.1/0.2/0.5、历史证据与 G0；所有敏感形态扫描为 0，cutoff 后 x2n overlap 为 0。
- 首次 Review 的 `BLOCKED_OWNER_ACTION` 证据保持不变；新 `review_resume/` 证据签发 `G0 PASS`。
- Stage 0 整阶段上传与下一独立 Run 的 `TSK.x2n.foundation.001` 已授权；本 Resume Run 未执行产品代码、账号、平台、Notion、模型或媒体操作。

## v0.0.0.1 — Stage 0 Review

- 基于 `origin/main` 明确 cutoff 完成独立 Review/Fix/Re-acceptance；cutoff 后无关长期开发不吸收，触及 x2n 才阻断。
- 修复三个旧 Phase verifier 不接受独立 Review 分支的问题，并完整重跑 Phase 0.1/0.2/0.5。
- 将 Owner 执行约束从“每 Run 一个 Phase”收紧为“每普通 Run 一个 DAG Task 及其 Acceptance”；Stage Review 是不执行新 Task 的专用例外。
- 删除残留 `MediaCrawler` 产品 Adapter Feature Flag 和“外部安装”措辞；下载父目录名仍只代表存储路由，受限上游保持零安装、零执行、零输出接收。
- 复核原始 roadmap/ZIP 固定哈希；确认原输入没有指定 macOS 下载绝对路径。
- 重新核对 `ShilongLee/Crawler` 固定提交与 Chrome/Notion/六平台一手来源；竞品提交未漂移，六平台仍全部 `UNKNOWN_DISABLED`。
- 28 个单测通过（2 个私有可选输入测试按设计跳过），20 份历史 Phase receipt 保持未改，产品/账号/平台/Notion/模型/媒体均 `NOT_RUN`。
- 本地自动门禁通过，但 `INC-X2N-S00-P05-001` Owner Action 未完成；真实结论为 `G0_BLOCKED_OWNER_ACTION`，Stage 1 与远端上传继续禁止。
- Review Follow-up 修复了 Owner Recovery 仅有文字要求的盲点：新增闭合 Schema、合成 Fixture、不可覆盖的私有生成器和缺失/恶意/越权负向 verifier；没有生成真实回执，G0 状态不变。

## v0.0.0.1 — Stage 0 / Phase 0.5

- 通过 Owner Change Event 将终态范围扩为六平台，保留稳定项目名；DAG 从 35 增至 43 Task、需求从 28 增至 32、Acceptance 从 49 增至 61。
- 按 Owner 指令把子项目统一为 `xhs-douyin-2notion/`；记录原始 taskpack 未指定本机绝对下载路径，并将私有根固定为 Owner 下载目的地下同名隔离命名空间，既有同级条目触碰数为 0。
- 固化六平台 Capability/Policy/Auth 独立门禁、Feature Flag、Kill Switch 与所有下载统一 `X2N_DATA_ROOT` 契约。
- 完成 Chrome/CWS、Notion 和六平台一手政策快照、ADR-001–010、DFD/STRIDE、20 条 Stop/Kill 与 50 条合成治理用例。
- 深审 `ShilongLee/Crawler` 固定 Commit；因自定义非商业 License 与安全/隐私差距，限定为 clean-room ideas only，0 copy/vendor/runtime dependency。
- 收紧受限上游边界：ShilongLee/Crawler 与 MediaCrawler 仅为不可执行审计参考，不安装、不运行、不接收输出，也不是产品 Adapter。
- Owner 未提供值全部采用可逆保守默认；六平台、Notion、云模型、真实同步均保持关闭。
- 临时研究 remote 的凭据形态 URL 已按 `INC-X2N-S00-P05-001` 隔离：临时副本删除、项目/私有根文件扫描 0 命中；G0 前仍需轮换/重新认证或过期证明。
- 新增 Owner 指定的长期并行 worktree 隔离：默认仍要求 clean main，显式 override 仅在外部 dirty paths 与 x2n 零重叠时通过，公开证据只记录计数。
- 未进入产品代码、真实账号、平台/Notion/模型请求、Stage Gate 或远端上传。

## v0.0.0.1 — Stage 0 / Phase 0.2

- 精确登记 xiaohongshu-exporter、douyin-downloader 与 MediaCrawler 的 Commit/tree/关键文件哈希。
- 建立 Dependency Registry、Capability Matrix、License/NOTICE、SBOM dry run 与 Shadow-upgrade Plan。
- 将 xhs exporter 限定为 clean-room reference，将 MediaCrawler 限定为 external non-commercial research；douyin wrapper 保持关闭并等待 exact lock 与 Adapter contract。
- 平台个人点赞/收藏官方能力未确认时保持 `UNKNOWN / DISABLED`。
- 未运行上游或产品代码，未访问真实账号，未进入 Phase 0.5、Stage Gate 或远端上传。

## v0.0.0.1 — Stage 0 / Phase 0.1

- 注册唯一母仓库、子项目和 Stage 0–6 Task DAG。
- 将 Runtime 与全部 Adapter 下载统一到私有逻辑根 `X2N_DATA_ROOT`。
- 建立 Public Artifact / Private Runtime 路径契约、合成 Fixture 清单和机器验证入口。
- 保存原始输入 SHA-256，并以 Owner Change Event 记录路由与路径修正。
- 未进入产品代码、真实账号、浏览器、Notion、模型或媒体执行。
