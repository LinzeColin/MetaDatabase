# ADP canonical HANDOFF — 2026-07-23

本文件是 ADP 迁入 MetaDatabase 后的**唯一当前交接入口**。先读本文件，再按任务路由到
被点名的最小文件集；不要把 V0.1、V0.3、V7.2 或旧 CodexProject 根级文档各自解释成
全项目“当前合同”。

## 0. 三十秒版

- canonical 仓库是 `LinzeColin/MetaDatabase`，项目路径是 `arxiv-daily-push/`。
  CodexProject 中已删除的旧源目录不得恢复。
- live 面仍是 Cloudflare Worker `adp-cloud` / `https://adp.linzezhang.com`；当前产品版本
  `0.41.0`，封存 live/git build 为 `c2ccc1fd01ec`。
- 迁移闭合已由 `e1af471c` 和 PR #68 完成并通过独立 developer_check；当前开发合同是
  `docs/pursuing_goal/v1_2/`，目标产品版本 `1.2.0`。
- `ADP-V12-S0-T001` 已在 merge `46dae697b81843b26fe5f4b97ccaa75a38622307`
  上完成独立 post-merge clean-room 验收，`ACC-V12-S0-001..006 = 6/6 PASS`；公开安全的
  收尾 receipt 位于
  [`PHASE_ADP_V12_S0_POSTMERGE_CLOSEOUT.md`](phase_records/PHASE_ADP_V12_S0_POSTMERGE_CLOSEOUT.md)。
- `ADP-V12-S1-T001` 已完成整阶段独立复审，`ACC-V12-S1-001..005 = 5/5 PASS`，
  `P0/P1/UNKNOWN/BLOCKED = 0`；公开 receipt 位于
  [`PHASE_ADP_V12_S1_GOOGLE_NEWS_RETRY.md`](phase_records/PHASE_ADP_V12_S1_GOOGLE_NEWS_RETRY.md)。
- `ADP-V12-S2-T001` 已在首轮 P1 修复后通过 fresh-context 整阶段复审，
  `ACC-V12-S2-001..003 = 3/3 PASS`，`P0/P1/UNKNOWN/BLOCKED = 0`；公开 receipt 位于
  [`PHASE_ADP_V12_S2_STATS_GOV_DIAGNOSIS.md`](phase_records/PHASE_ADP_V12_S2_STATS_GOV_DIAGNOSIS.md)。
- 公开安全的[事实型诊断 receipt](../machine/runs/ADP-V12-S2-T001-diagnosis.json)已区分两类事实：
  `2026-07-22T10:07:12Z` 的历史 edge `EDGE_TIMEOUT/0` 未保留 raw，标为 stale；最新已绑定
  raw hash 的本地与 edge 点样分别在 `2026-07-22T10:36:12.687Z`、
  `2026-07-22T10:36:47.591Z` 得到 `SUCCESS/15`。
  edge 在零 adapter 变更下自行恢复，因此决定仍是 `degraded_preserved` / `NO_ADAPTER_FIX`；
  前者只表示保留失败时降级行为，不是当前瞬时健康断言。Worker、cron、来源启停和部署均未改。
- `ADP-V12-S3-T001` 已在首轮 XML/实体边界修复后通过 fresh-context 整阶段复审，
  `ACC-V12-S3-001..003 = 3/3 PASS`，`P0/P1/UNKNOWN/BLOCKED/waiver = 0`；公开 receipt 位于
  [`PHASE_ADP_V12_S3_SCIENCE_ADVANCES_PUBMED.md`](phase_records/PHASE_ADP_V12_S3_SCIENCE_ADVANCES_PUBMED.md)。
- 当前唯一下一任务是 `ADP-V12-S4-T001`（中文人话版 fail-closed 闭合）；它仍为 `NOT_RUN`，
  Run Contract 尚未创建。必须先锁定独立合同，不得把 S3 验收外推为 S4、部署或 live 授权。
- S1 候选实现位于 [`google_news_candidate.mjs`](../deploy/cloudflare/google_news_candidate.mjs)：
  `gnews-us-tech-google-candidate`（Google News RSS）保持 `candidate_not_live`，live
  `gnews-us-tech` 仍是 Bing News RSS；机器登记见
  [`cloudflare_source_candidates_v1_2.json`](../config/cloudflare_source_candidates_v1_2.json)。
  当前单次 scheduled invocation 的 external 上界为 `32`，以后获授权替换时投影
  `34/50`；S3 PubMed 候选未来若也另获授权替换现有 Science.org RSS，合并投影 `35/50`；
  当前两者均没有接线或部署。
- S0 已以相对 source base、merge 双亲和 Worker 精确路径的零差异证明无 runtime/live 变化；
  后续仍不得用状态文字替代真实 diff 或 live 复查。
- Owner 的晚到决策已定案：3 个 dormant Cloudflare 资源均删除；继续救援剩余来源；
  不迁 OVH/Coolify；不修 V0.1 `TASK_INDEX.csv` 的死状态列。
- S1–S3 来源救援开发线已按独立 Run Contract 完成 candidate-only 验收；下一条开发线是
  S4.1 中文人话内容。前九个任务仍只做到对应合同边界；最终部署仅在 v1.2 全部门禁 PASS 后自动执行。

## 1. 合同路由与优先级

| 范围 | 当前用途 | 是否可覆盖 live/仓位事实 |
|---|---|---|
| `docs/HANDOFF.md` | 仓位、Owner 决策、当前开发线、下一步 | 是，唯一当前入口 |
| `docs/pursuing_goal/v1_2/` | 当前增量产品合同、Roadmap、Task Graph、Acceptance | 约束 v1.2；不能预签 live 状态 |
| `machine/facts/` + `文档/` | MetaDatabase 双平面治理；由机器事实渲染 | 只覆盖其已登记事实 |
| `CHANGELOG.md` + `docs/pursuing_goal/v0_2/evidence/` | Cloudflare V0.2 生产开发证据 | 可证明对应阶段，不自动授权下一次部署 |
| `docs/pursuing_goal/v0_1/` | V0.1 需求谱系与历史任务包 | 否；`TASK_INDEX.csv.status` 是已裁定不修的死配置 |
| `docs/v03/` | 被显式点名时才启用的本地重构任务包 | 否，不是默认活动合同 |
| `docs/pursuing_goal/v7_2/` + 根级 compatibility artifacts | 旧本机 runner/SMTP 的 fail-closed 合同与回归面 | 否；不覆盖 V0.2，也不授权 live 运行 |

发生冲突时按“当前 HANDOFF → 当前任务 Run Contract → 对应开发线证据 → 历史合同”的顺序
解释；任何证据不足的状态保持 `UNKNOWN`/`BLOCKED`，不得自行拼接出授权。

## 2. 生产面封存事实与边界

| 项 | 2026-07-20 封存事实 |
|---|---|
| Worker | `adp-cloud`，Cloudflare 免费档 |
| 域名 | `adp.linzezhang.com` |
| build | `c2ccc1fd01ec` |
| 存储 | D1 `adp-mirror` + R2 `adp-raw-artifacts` |
| cron | 3/5 槽位已用；不得越过免费档上限 |
| liveness | `.github/workflows/arxiv-daily-push-liveness.yml` |

S0 已按停止条件封存。任何 S0 状态同步若需要改 Worker、部署、增加 cron/资源、读取
secret、恢复旧源目录、弱化 fail-closed 测试，或把历史 artifact 当作新授权，仍须立即停止。

## 3. Owner 晚到决策（已定案，不再询问）

| 事项 | Owner 决策 | 当前执行状态 |
|---|---|---|
| dormant Cloudflare 资源 | 删除 | `adp-mirror` legacy Worker、`adp-origin` DNS、`adp` Tunnel 均已删除并复核；不得重建 |
| 剩余来源救援 | 继续投入 | Google 候选 S1、stats-gov 诊断 S2、Science Advances/PubMed S3 均已完成 candidate-only 独立验收；未切 live |
| science-advances | 走 PubMed 解析层 | S3 已 3/3 PASS；候选仍未接 Worker、现有来源、cron、存储或部署 |
| stats-gov | 继续诊断 | S2 已 3/3 PASS；历史 edge timeout 点样无 raw，最新本地/edge 均为 `SUCCESS/15` 且由事实 receipt 绑定 hash；保持失败时降级语义与 `NO_ADAPTER_FIX`，未来满足最小重开条件才另立合同 |
| Google News | 加重试/退避后评估回切 | S1 5/5 PASS；仍为 candidate_not_live，历史采样是间歇 503，不是“被墙” |
| OVH VPS / Coolify | 不迁 | Cloudflare 免费档保持 canonical live 面 |
| `TASK_INDEX.csv.status` | 不修 | 90 行 `NOT_STARTED` 不代表代码未完成；只把它当历史字段 |
| v1.2 部署 | 全部门禁通过即部署 | P0/P1/UNKNOWN 为零、独立验收和回滚门均 PASS 后才生效 |
| 费用 | Cloudflare Free 优先 | 容量不足时生成升级提案；不得自动付费 |
| 本地任务包 | GitHub 恢复证明后删除 | 任一远端 hash/unzip/ingest 失败则删除零文件 |

来源与板块变更必须满足根 `AGENTS.md` 与项目 `AGENTS.md` 的 user-center sync gate；
config/code-only change 不算完成。

## 4. 迁移闭合资产

为保持历史引用与内容哈希，以下 ADP 专属兼容面保留在 MetaDatabase 仓根：

- `FINAL_ACCEPTANCE_BUNDLE/`：30 个历史 final-bundle 文件；
- `governance/run_manifests/ADP-*`：424 个历史 run manifests；
- `tools/validate_task_pack.py`、`verify_acceptance_bundle.py`、
  `verify_daily_operation_readiness.py`、`verify_daily_operation_enablement_preflight.py`：
  只读、fail-closed 兼容入口。

它们不是 MetaDatabase 治理框架。治理框架继续从 `LinzeColin/Governance` 消费；禁止恢复
CodexProject 的 `repository_hygiene_policy.json`、`generate_governance_dashboard.py`、
`validate_project_governance.py` 或 `project-governance.yml`。根级 `HANDOFF/` 也保持缺席，
不得为了唤醒 29 个冻结的旧 final-bundle 测试而重建。

## 5. 验收合同

从 MetaDatabase 仓根、使用已安装 `arxiv-daily-push/requirements.txt` 的 Python 3.12 运行；
macOS 系统 Python 3.9 无法运行当前 ADP 验收入口：

```bash
# 当前双平面项目门
python3 arxiv-daily-push/machine/tools/check_dual_plane_ci.py \
  --root . --projects arxiv-daily-push --require-projects

# 历史 V7.2 + 当前双平面兼容入口（只读；需先安装 requirements.txt）
PYTHONPATH=arxiv-daily-push/src python3 -B tools/validate_task_pack.py --root .

# 迁移治理回归：必须 65/65
PYTHONPATH=arxiv-daily-push/src python3 -B -m unittest discover \
  -s tests/governance -p 'test_adp_*.py' -q

# ADP full suite：按测试名称集合比较，不得相对两条基线新增 failure/error
PYTHONPATH=arxiv-daily-push/src python3 -B -m unittest discover \
  -s arxiv-daily-push/tests -q
```

验收时必须区分两条不可混用的比较面：

1. **迁移线程封存的历史旧控制口径**：923 tests、`3 failures + 11 errors + 62 skips`。
   它用于核对剩余 failure/error 是否仍在历史允许集合内，不是对 MetaDatabase
   `7fd0768002081f27c070561fa855a08713d1bc00` 的重放结果。
2. **可重放的 MetaDatabase 迁移前 base**：在精确 `7fd0768` detached checkout、Python 3.12
   环境重跑同一命令，结果为 923 tests、`54 failures + 50 errors + 49 skips`；大量失败来自当时
   尚未迁入的根级 ADP compatibility dependencies。迁移判定必须比较 failure/error 的完整测试
   名称集合，不能只看总数；本轮候选相对该 base 的新增集合为 0。

历史旧控制口径中的 11 errors 来自仓拆分前已缺失的 `功能清单.md` / `开发记录.md` /
`模型参数文件.md`，另有 development-ledger 与 video gate 历史债；本轮不伪装为已修复。

S0 pre-commit 实测是 923 tests、`2 failures + 11 errors + 49 skips`：根来源同步契约的
旧 failure 已修复，skip 比历史旧控制口径少 13 个；相对上述两条比较面的迁移新增
failure/error 均为 0。剩余 2 failures
分别是 development-ledger/current matrix drift 与 video media gate，11 errors 仍全部来自
上述三基文件缺失。不得以修改/跳过测试来伪造全绿。

S1 收尾在隔离 Python 3.12 环境实测 939 tests、`2 failures + 11 errors + 29 skips`；新增
16 项候选专项测试，failure/error 完整测试名集合仍与 sealed 基线精确一致，
`candidate_only=[]`、`baseline_only=[]`。S1 没有恢复上述三份缺失旧文件。

S2 收尾在 requirements-locked Python 3.12 环境实测 949 tests、
`2 failures + 11 errors + 29 skips`；原始 suite 状态仍为 FAIL。相对 sealed baseline 的
failure/error 完整测试名集合差分为 `PASS`，`candidate_only=[]`、`baseline_only=[]`。
独立复审没有把历史失败包装成绿色，也没有恢复上述三份缺失旧文件。

`arxiv-daily-push-real-backfill.yml` 查询的是会随论文修订而变化的外部历史元数据，因此重型
30 日 replay 只在 `src/config/schemas/packaging` 运行面变化时执行；tests/docs/governance-only
变更必须通过 scope classifier，但不得靠降低“每日额外排队候选”质量门来消除真实 runtime
失败。replay 失败时必须保留并上传 JSON artifact、在日志打印 `blocking_reasons`。

本轮还必须证明：

1. `git diff origin/main -- arxiv-daily-push/deploy/cloudflare/worker_cloud.js` 为空；
2. 30 个 bundle、424 个 manifests 与前端原始存档内容哈希不漂移；
3. CodexProject 主线不重新出现 `arxiv-daily-push/`；
4. PR CI 通过后，才可把迁移闭合写成完成；
5. 合并提交必须由独立 `verifier` 在新上下文复验，实施者不能自签。

## 6. v1.2 第一个产品 Run Contract（S1 已关闭）

**目标**：在不部署、不改 cron、不引入付费 API 的前提下，为 Google News adapter 增加
有上限的 retry/backoff，并用确定性夹具和负控证明“间歇 503 可恢复、确定性拒绝仍失败关闭”。

**最小范围**：Google News adapter、相关 source registry/fixtures、来源与用户中心同步文件、
目标测试；不顺带做 stats-gov 或 PubMed adapter。

**验收**：真实实现路径测试 + 负控 + source/board sync gate + full suite 与迁移基线对比；
S1 不切换 live、不改 cron；最终部署权仍由 v1.2 S6 的全部阻断门控制。

S1 终局边界：`gnews-us-tech`（Bing News RSS）保持 live，
`gnews-us-tech-google-candidate`（Google News RSS）保持 `candidate_not_live`。可执行验证器从真实
Worker registry/常量核算 daily external 最坏 `32` 次，候选将来替换单次 Bing 路径时最多
`34/50`；当前没有发生该替换。独立 verifier 已在修复自动重定向计数与 canonical 文档渲染
两个 P1 后裁定 `5/5 PASS`。下一阶段仍须另建、另验 S2 Run Contract，不复用 S1 授权。

## 7. v1.2 第二个产品 Run Contract（S2 已关闭）

**目标**：只读区分 stats-gov 的 `EDGE_TIMEOUT`、`HTTP_STATUS`、`PARSE_ZERO` 与 `SUCCESS`，
仅在免费、边缘安全、可复跑的证据支持时修改 adapter；否则保持 degraded 并给出最小下一条件。

**诊断事实**：专项测试与可执行 verifier 已让四类互斥通过；候选 parser 与当前 Worker
`parseA0` 在正/负夹具上逐项一致。历史 edge `EDGE_TIMEOUT/0` 点样没有保留 raw receipt，现已
标记 `STALE_UNVERIFIED_RAW_UNAVAILABLE`；前序 A7 验证运行在 `2026-07-22T10:36:12.687Z`
直连官方入口得到 `SUCCESS` / HTTP 200 / 15 项，又在 `10:36:47.591Z` 从既有只读 edge canary
得到 `SUCCESS/15`。r2 没有重新请求外部来源，只对前序 sealed A7 包内的 raw bytes/hash 与
事实链做复验，因此不外推当前健康；公开 receipt 登记 SHA-256 与推断边界。

**当前决定**：`degraded_preserved` / `NO_ADAPTER_FIX`。edge control 已在零 adapter 变更下
自行恢复，故没有因果证据支持 timeout/retry/header 等猜测性修复；`degraded_preserved` 只保留
既有失败时降级行为与来源启停状态。诊断模块不接入 Worker、单次只读 1 subrequest、零写入、
零新增服务、零付费；本轮不部署、不改 cron、不改变来源启停。只有未来再次出现带 raw hash 的
重复 `EDGE_TIMEOUT`，且获授权的隔离 matched control/candidate 证明候选至少两次
`HTTP 2xx + parsed_count>0` 而 control 同时仍超时，才另开 Run Contract 评估最小变更。

**整阶段复审**：首轮独立 verifier 发现 Owner 页面把无 raw 的旧 timeout 写成无时间戳当前事实，
且链接到尚不存在的 developer-check receipt，定级 P1。现已新增非自签的事实型 receipt、registry
hash 绑定、canonical renderer fail-closed 校验与 Owner 同步。fresh verifier 对新 Subject
`c4174a1712d6b102a543f900cbf4d44447115e5cdeabe6a78a86ff5438d55c13` 独立复跑后关闭 finding，
裁定 `3/3 PASS`；evidence root 为
`711d324114d5fa0659954abe5ce31909eed7aa55596d656f948afabb91e2b36d`。这只关闭 S2，不签署
S3–S6，也不授权部署。

## 8. v1.2 第三个产品 Run Contract（S3 已关闭）

**活动任务**：`ADP-V12-S3-T001`，通过 PubMed E-utilities 为 Science Advances 建立本地、
可注入、失败关闭的 ESearch→EFetch 解析层，保留 PMID/DOI provenance，并证明期刊/日期过滤、
去重、坏 XML、空搜索、限流与 HTTP error 边界。

**已锁合同**：[`RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md`](pursuing_goal/v1_2/RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md)
固定 NLM ID `101653440`、电子 ISSN `2375-2548`、最多 20 PMID/2 请求、请求起始间隔至少
1000ms、无 API key/bulk、零写入。候选 `science-advances-pubmed-candidate` 保持
`candidate_not_live`；现有 `science-advances` RSS、Worker、cron 和 live `0.41.0` 不变。

**整阶段复审**：首轮 fresh verifier 对旧 Subject `3cd2138c` 裁定 `FAIL / ACTION ACT`：
XML 1.0 非法 literal 字符未失败关闭，未声明命名实体边界为 `UNKNOWN`。实现随后增加严格
XML 1.0 code point 校验，仅按大小写精确接受五个预定义实体，并补对应正负控。fresh r2 对
冻结 commit `7e5ab5ae3152844e8d073bc2e0074d8bf0f5a8f7` / tree
`dab9106886077a549b5b424a098943430e6e8b91` 独立复跑后裁定 `3/3 PASS`；
P0/P1/UNKNOWN/BLOCKED/waiver 均为零，evidence root 为
`08fb4185df9c9c7a497673ca0c1299cb313c9aa0672c824202d616acf5bf6fbb`。

**诚实回归边界**：full suite 原始结果为 `962 tests / 2 failures / 11 errors / 29 skips`；
与 sealed baseline 的失败/错误测试名集合精确一致，`candidate_only=[]`、
`baseline_only=[]`。这只关闭 S3 candidate 开发验收，不签署接入、部署、S4–S6 或生产验收。

## 9. v1.2 下一任务（S4.1 NOT_RUN）

**下一任务**：`ADP-V12-S4-T001`，关闭真实英文论文的中文人话结构与无可靠翻译时的诚实
fail-closed 回退，对应 `ACC-V12-S4-001..002`。

**当前状态**：`NOT_RUN`，Run Contract 尚未创建。下一线程必须先从 Task Graph 与 Acceptance
Contract 锁定唯一 S4.1 合同，再收集真实用户旅程与破坏负控；不得复用 S3 receipt 预签内容、
UI、模型、版本、运维或部署。

## 10. 永久提醒

- 主树只读，开发使用 `GithubProject/_scratch` worktree；谁开的谁收。
- 不使用 `git gc --prune=now`。
- Cloudflare 免费档边界不可越过；付费升级需 Owner 明确授权。
- 任何测试、live 状态、删除结果或独立复核结论都必须实跑后再写，不预签、不猜测。
- `TASK_INDEX.csv.status` 不是真实完成度；逐项开发前必须 `verify-not-live`。
