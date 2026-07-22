# ADP canonical HANDOFF — 2026-07-22

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
- 下一轮唯一任务是 `ADP-V12-S2-T001`。当前任务包尚无 S2 Run Contract 文件，必须先按
  `TASK_GRAPH.yaml` 与 `ACCEPTANCE_CONTRACT.yaml` 锁定独立合同再诊断；S2 仍是 `NOT_RUN`。
- S1 候选实现位于 [`google_news_candidate.mjs`](../deploy/cloudflare/google_news_candidate.mjs)：
  `gnews-us-tech-google-candidate`（Google News RSS）保持 `candidate_not_live`，live
  `gnews-us-tech` 仍是 Bing News RSS；机器登记见
  [`cloudflare_source_candidates_v1_2.json`](../config/cloudflare_source_candidates_v1_2.json)。
  当前单次 scheduled invocation 的 external 上界为 `32`，以后获授权替换时投影
  `34/50`；S1 没有接线或部署。
- S0 已以相对 source base、merge 双亲和 Worker 精确路径的零差异证明无 runtime/live 变化；
  后续仍不得用状态文字替代真实 diff 或 live 复查。
- Owner 的晚到决策已定案：3 个 dormant Cloudflare 资源均删除；继续救援剩余来源；
  不迁 OVH/Coolify；不修 V0.1 `TASK_INDEX.csv` 的死状态列。
- S0 通过后下一条开发线是来源救援；优先做 Google News 重试/退避的本地实现与负控，
  再诊断 stats-gov，最后实现 science-advances 的 PubMed 解析层。每条另开 Run Contract，
  前九个任务只做到对应合同边界；最终部署仅在 v1.2 全部门禁 PASS 后自动执行。

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
| 剩余来源救援 | 继续投入 | Google 候选 S1 已通过；stats-gov S2 尚未运行 |
| science-advances | 走 PubMed 解析层 | 待独立 Run Contract；先做本地 adapter/fixture/负控，不直接上线 |
| stats-gov | 继续诊断 | 下一轮先锁定独立 Run Contract；当前只有边缘超时事实，不能先写死结论 |
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

## 7. 永久提醒

- 主树只读，开发使用 `GithubProject/_scratch` worktree；谁开的谁收。
- 不使用 `git gc --prune=now`。
- Cloudflare 免费档边界不可越过；付费升级需 Owner 明确授权。
- 任何测试、live 状态、删除结果或独立复核结论都必须实跑后再写，不预签、不猜测。
- `TASK_INDEX.csv.status` 不是真实完成度；逐项开发前必须 `verify-not-live`。
