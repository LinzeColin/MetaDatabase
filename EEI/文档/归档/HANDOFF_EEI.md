# EEI 交接文档（任意 agent 从 GitHub 接手）

> 最后更新：2026-07-20。本文件是 EEI 线程的**单一交接真源**。任何 agent（Codex/Claude）
> clone 本仓后读此文件即可接手。GitHub 是权威；本地机器只承载"在跑的监测"（见下方 §3）。

## 1. 当前状态（一句话）

EEI 在线：`https://eei.linzezhang.com`（Cloudflare Workers + D1，无服务器）。

**2026-07-23 重大转折**：Owner 自验判定「系统只有 1%、信息/逻辑/链条/交互全空」——**属实**。此前"交付验收 30/31 通过"验的是**管道正确性 + 诚实空状态 + 观感**，不是**有没有真数据**：线上当时只有 3 家真公司（ASML/NVIDIA/TSMC）、2 条关系、0 事件，其余全是被云端诚实模式挡掉的合成 fixture。根因：SEC 采集只到 source_document 事实层不建实体，实体/关系靠**手签金标侧链**（仅 2 条候选=3 家）。

**已重建为真数据管道（第一手权威、免费公开源、不加登录/不买数据）**，现状（本会话进行中）：
- 实体 **3 → ~8750 家真公司**（SEC 官方 registry：CIK+ticker 身份，`status='research_target'`）——搜索/图谱已真实。
- 关系 **2 → 数千条**（GLEIF 第一手母子/控股：`corporate_structure`/`ownership_control`）——控制/所有权/结构模块已填。
- 事件 **0 → 万级**（SEC 每份 material filing=真事件，证据锚 EDGAR URL）——资金模块/时间轴已填。
- 行业：SEC SIC 分类。管道 = worktree 分支 `eei-fulldata-authoritative`（本 PR）。
- **仍缺/下一步（诚实）**：M&A/战略信号/供应链的**关系**（GLEIF 只给结构/控股；需 8-K 文本解析等）；entity empire 侧栏结构section（现只认 segment/brand，未接 GLEIF subsidiary_of）；`/v1/evidence/event/{id}` 路由；GLEIF 对 SEC 全大写名召回率低；动态实时刷新未接；OVH 搬迁未做。详见记忆 `project-eei-fulldata-rebuild.md`。

## 2. 权威真源（都在 GitHub）

- **代码**：`LinzeColin/MetaDatabase` 仓 `EEI/` 子目录（main 分支）。本机规范工作间
  `~/Documents/Codex/GithubProject/MetaDatabase/`（稀疏克隆 + `sparse-checkout set EEI`，与 Alpha 线程共享，见 §7）。
- **DoD/验收**：`docs/pursuing_goal/v5_0/V5_0_ROOT_LOCK.yaml`（七条 DoD）+ `MVP_DONE_CHECKLIST.md`（READY）
  + `data/acceptance_matrix.csv`（已对账）+ `docs/governance/development_events.jsonl`（账本，全过程）。
- **验收/复刻规格**：外部独立验收由 `verifier` skill 产出；样例视频逆向规格由 `video-replica` skill 产出。
- **坑单（agent 记忆，非仓内）**：`~/.claude/.../memory/project-eei-takeover.md`（主线）+
  `project-eei-video-replica.md`（视频复刻）+ `project-eei-fulldata-rebuild.md`（真数据管道）+ `reference-*`。**新 agent 无此记忆时，本文件 + 账本 jsonl 是等价替代**。

## 2.5 真数据管道（如何续跑/扩量）

新包 `EEI/scripts/authoritative/`（幂等、可重跑、后台友好；证据全锚 source_documents）。跑法：python=主树 `MetaDatabase/EEI/.venv/bin/python`，cwd=worktree/EEI，`.env` 需含 `SEC_USER_AGENT`（带联系邮箱）：
- 全量实体：`python -m scripts.authoritative.collect_universe`（SEC company_tickers.json→~8k 真公司；按 CIK 幂等，只把有真 CIK 的 fixture 提升为真）。
- 事件+SIC 行业：`python -m scripts.authoritative.enrich_sec --limit N [--universe|--tickers T]`（每份 material filing=事件）。
- 关系（GLEIF 母子/控股）：`python -m scripts.authoritative.collect_gleif --limit N`（免费无 key；精确名匹配 0.90 门，全大写 SEC 名召回低）。
- **动态刷新（及时+增长，一体）**：`python -m scripts.authoritative.refresh_cycle`（滚动游标扫全宇宙，每轮 enrich+gleif+republish；`--loop --interval-seconds N` 供容器常驻）。enrich 事件按最近 N 份 material filing 封顶→幂等(重跑 delta=0)。**本地未起常驻；持续调度=OVH 限额容器职责**。
- 发布上云：`python scripts/publish_to_cloud_channel.py --report r.json --sql-out p.sql --apply`。**D1 是活库，发布即上线，数据改动无需 wrangler deploy**；`derivation_rule='authoritative_first_hand_ingestion'` 的实体/关系/事件全发；worker 按 family 查库自动填模块，仅 events 路由在本 PR 新接（D1 加 events/event_participants/event_evidence 表 + `/v1/events`、`/v1/events/amount-summary`）。worker.mjs 若改需 `scripts/deploy_cloud.sh`（洁净树+重刷 SHA）。

## 3. ⚠️ 机器绑定、不能交给 GitHub 的东西

**监测本质上跑在本机 docker，无法"交接到 GitHub"**——诚实告知：

- `docker` 两容器 **`eei-postgres` + `eei-worker`**：本地数据采集管线 + 每日 22:03Z 本地日采。
  **07-23 双 7 天窗未满前，绝不能停/删这两个容器**（停=断心跳链=作废窗口证据。曾有清理事故删过 runtime_evidence，见账本）。
- 云端 7×24 心跳/日 cron 在 **Cloudflare**，与本机无关，本机关了也照跑（但数据生产线在本机）。
- **`_protected/EEI_runtime_evidence/`**：监测证据/部署清单/重测基线/备份 dump。
  **铁律：永不删、永不上传**（README 铁律4）。这是本地专属，不入 GitHub。

若要彻底停本机：先确认 07-23 窗已收口 + Owner 拍板，否则本地监测中断（云站继续活，只是数据停在最后一次发布）。

## 4. 如何续监测（唯一在跑的义务）

```bash
cd ~/Documents/Codex/GithubProject/MetaDatabase/EEI
set -a; source .env; set +a   # .env: DATABASE_URL=postgresql://eei:change-me-local-only@localhost:5432/eei (chmod 600)
~/.local/bin/uv run python scripts/monitor_release_continuity.py \
  --evidence-dir ~/Documents/Codex/GithubProject/_protected/EEI_runtime_evidence
# 判 HEALTHY 续链；violation → 诊断 + worktree PR 修复流
```

- **硬节点**：每日 **18:00Z 云 cron**（SEC 增量，走 CF secret `SEC_USER_AGENT`）、**22:03Z 本地日采**。
  落点后核查 completed/succeeded + new_filings。静默期每小时跳一次。
- **07-23 收口**：双 7 天窗满（S7PDT02 本地日采 7 天全 succeeded + S10PBT02 云 cron 7 天 completed + ~168 小时心跳无缺口）
  → 汇总 JSON 落 `_protected` → 账本事件 PR（worktree 模式）→ **发 Owner 最终稳定性证据报告**。
- `uv` 用全局 `~/.local/bin/uv`（`make bootstrap-python` 的裸 `python` 会 127）。

## 5. 部署铁律（改代码后）

- **唯一发布路径**：`bash scripts/deploy_cloud.sh`（脏树拒发；打 git SHA 进 bundle+`x-eei-build` 头+`/v1/meta/build`；部署后自校验线上指纹=本次 commit；清单落 `_protected/deploys/`）。
- **`EEI_CLOUD_API_BASE` 默认 `https://eei.linzezhang.com`**（workers.dev 已禁，error 1042）；**绝不把 build_cloud_frontend.sh 管道给 head**（SIGPIPE 部署旧 dist，"Uploaded 0 new assets" 是信号）。
- 部署后 `git pull` 可能静默失败/边缘灰度传播秒级滞后：**必 curl 实测** `curl -s $B/ | grep data-build-sha` 等收敛。
- **视觉/模块改动用 headless Playwright 真渲染验证**（mcp 预览浏览器对生产子路由不稳）。
- **A167 视觉基线 CI 权威（ubuntu 字体栈）**：改布局 dispatch `eei-visual-baseline.yml` workflow 于分支→下载 artifact 覆盖 snapshots 提交。**注：纯 SVG 装饰改动 CI 基线常不变、verify 仍 pass**。
- 远端 D1 拒 6+ compound SELECT（SQLITE_ERROR 7500）→逐表查。
- 部署 SEC secret：`wrangler secret put SEC_USER_AGENT`（含邮箱，不入仓）。

## 6. 真实剩余（17 NOT STARTED，都非"闷头开发欠账"）

- **需时间/真实结果沉淀（14）**：模型预测有效性、长期双周校准、容量基准、浸泡测试、规模测试 —— 要跑真数据攒时间。
- **需商业数据（2）**：给全部 140 对象补真实关系等 —— **Owner 定：不买商业数据**，故搁置。
- **真未建/部分（~1-2）**：A196 触觉反馈（无实现，且视频规格本就 EEI silent/no haptics）、A194 全页视觉覆盖（仅首页自动化）。

**授权阻断的重测**（非开发，套件已就绪）：C-001 并发/P-003 负载/R-002 故障注入/S-003 主动安扫，
`scripts/acceptance_retest/` + `docs/37_ISOLATED_RETEST_SUITE.md`（Run Contract）。**生产级规模跑需 Owner 授权隔离克隆**。

## 7. Owner 决策 + 跨线协调（接手前必读）

- **Owner 决策**：①不加登录/多用户认证 ②不买商业数据。剩余战略开放项据此基本 settled。
- **Agent PR 自合并永久授权**：Owner 点名允许 agent CI 绿后自审合并自己的 PR（发布签核等其他门不受此授权覆盖）。
- **共享克隆协定（与 Alpha 线程）**：主树永驻 main；PR 一律在 `git worktree add ../_scratch/eei-pr-<名> -b <分支>` 内做，合并即收；
  **提交只用显式路径 `git add`（绝不 `-A`，会吞 Alpha 脏文件）**；提交前断言分支名。Alpha 若重写历史会提前知会→重新克隆（带 EEI/.env + .venv）。
- **OVH Singapore VPS**：新主部署节点（amd64）。**EEI 无需求**（CF 无服务器）；本地采集管线迁移属 Owner 决策 + 07-23 后 + 走容量 Gate。
- **视频复刻剩余**（批次3+，需 Owner 决策暂不擅自做）：开场 autoplay 分级 bloom/zoom 相机序列（与"交互工具"冲突）、紫罗兰 decree 焦点核（政策域特有，EEI 无对应态）。

## 8. 接手第一步

```bash
# 1) clone（按需稀疏）
cd ~/Documents/Codex/GithubProject
git clone --filter=blob:none --sparse git@github.com:LinzeColin/MetaDatabase.git   # 若无
cd MetaDatabase && git sparse-checkout set EEI && git pull --ff-only origin main
# 2) 读本文件 + 账本最近事件
tail -20 EEI/docs/governance/development_events.jsonl
# 3) 若续监测：见 §4（需本机 docker + .env + _protected，机器绑定）
# 4) 若改代码：worktree PR 流（§7）+ 部署铁律（§5）
```

**当前唯一活口**：盯监测到 07-23 → 发 Owner 最终稳定性报告。其余要么等时间、要么等 Owner 拍板（隔离环境授权、视频批次3、无商业数据前提下挑做哪些）。
