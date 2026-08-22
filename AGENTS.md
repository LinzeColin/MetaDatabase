# MetaDatabase Agent Contract

母仓库，中文优先；代码、API、库名、模型名和错误可保留英文。

## 永久规则

- 治理框架来自共享仓库 LinzeColin/Governance。
  禁止在本仓库内复制、分叉或重建治理框架。
  禁止用 git submodule 引入它 —— 通过 CI checkout 或 pip 安装消费。
- **数据落地铁律（长期有效 · 自运行分仓治理）**：长期/业务/运行时数据（原始数据、导出件、
  数据库、内容寻址对象、运行时快照、含 PII 记录等）一律写私有仓 `LinzeColin/Private-Database` 的
  `Private-MetaDatabase/`，用 `KMOS/KMDatabase/machine/tools/private_db_client.py` 免 clone 读写
  （`ingest/get/list/verify`）；**禁止把数据提交进本代码仓**，派生/临时物走 `.gitignore`。
  Private-Database 禁止 `git clone`。各项目数据现状见根目录 `WHERE_IS_PROJECT_DATA.md`。
  目的：分仓治理长期自运行，不需 Owner 反复人工迁移。

## 三款桌面 App 一致性规则（强制）

- Kimi Code Desktop、Harness UI、DSH Desktop 的唯一共享源码真源是本仓 `main`。每个 agent 在开始三端相关开发前先读取
  [`desktop-suite/COMPATIBILITY_CONTRACT.json`](desktop-suite/COMPATIBILITY_CONTRACT.json)，并在独立 worktree 的分支中完成改动。
- 修改 Kimi、Harness UI、DSH 桥接、共享皮肤协议、版本、bundle identifier、发布标签或发布流程时，同一 PR 必须同步更新
  该契约与相关说明，并通过 `node scripts/validate-desktop-suite-contract.mjs`。
- `Harness UI` 是 `~/.harness-ui/catalog.json`、`state.json` 与 `POST /api/next` 的唯一状态 owner。Kimi 与 DSH 只消费这一份
  协议，三端不创建第二套持久皮肤状态。
- 正式三端发布只由 `.github/workflows/desktop-app-suite-release.yml` 从同一个 `GITHUB_SHA` 执行；该 workflow 同时生成
  Kimi、Harness UI、DSH 三组资产并更新各自正式标签。agent 本机生成的应用只用于开发，不能成为另一台电脑的发布真源。
- 仓库 Actions 的 `default_workflow_permissions` 保持 `write`，发布 job 保持最小 `contents: write`。该组合允许统一 workflow 更新既有 Release 的 tag 与资产，并让守卫与构建 job 继续使用读取权限。
- API key、账号、会话、SMB 凭据、素材库、运行时 catalog/state、个人图标原件、已安装 App 与回滚目录均属于本机私有状态；
  它们保持在 App Bundle 外，按本仓的数据落地铁律处理，禁止进入公开源码或 Release 资产。
- 跨电脑协作以 GitHub PR 合入的 commit 为交接边界。两台电脑都从同一 `main` 拉取、在各自分支提交、由统一 workflow 发布，
  因此三款 App 始终回到同一组源码与同一发布提交。

## 命名陷阱（务必记住）

- `LinzeDatabase/` 是原 CodexProject 的 `MetaDatabase/` 目录改名而来。
- `LinzeDatabase/PFI` 与将来迁入的顶层 `PFI` 项目**不是同一个东西**，不要合并或互相引用。
- `ADP` 已从 CodexProject 迁入本仓，canonical 路径是 `arxiv-daily-push/`；
  其 CI secrets 名为 `ADP_SMTP_*`。按顶层目录名 `ADP` 去找会一无所获。
- CodexProject 中已删除的 `arxiv-daily-push/` 是迁移后的预期状态，禁止从历史、
  备份或任务包恢复；后续开发只在本仓的 `arxiv-daily-push/` 进行。

## 股票 Skill 路由（强制）

- 股票类 Skill 的唯一 Git 真源统一位于 `Signal-Lattice/Stock_Skill/`；仓库根目录 `Stock_Skill/` 是禁止存在的 legacy 路径，所有未来股票 Skill 也只能落在该目录。
- `Signal-Lattice/Stock_Skill/REGISTRY.json` 的 active schema 必须精确为 `1.1`。每个 entry 必须显式声明大小写敏感的
  `version_scheme`；唯一允许值是 canonical 三段数字 `semver` 或 canonical 四段数字
  `numeric-quad`，两者都禁止 `v`、前导零和额外 suffix，且只能在同一 scheme 内比较。
- `latest_major` 必须是与版本首段相等的 JSON integer（boolean 不合法）；`superseded_archives` 必须存在
  且为数组，但首版允许 `[]`。archive 继承父 entry 的 scheme、不得自声明 scheme，版本必须唯一且严格
  早于 current version。
- 任何 agent 在声称“最新版本”前，必须先读 `Signal-Lattice/Stock_Skill/REGISTRY.json`，并运行
  `python3 Signal-Lattice/Stock_Skill/scripts/validate_registry.py`。校验失败、未运行或字段冲突时，版本状态只能是 `UNKNOWN`，不得猜测。
- `stock-commercial-opportunities`（股票商业机会拆解）当前唯一最新版本是 `3.0.0`（v3）；
  v1/v2 只在 `archives/` 中作为不可变历史谱系，不是当前版本、安装源或回退默认值。
- `bottleneck-serenity-skill=0.0.0.1` 已按 `numeric-quad` 登记为 active/current source entry，展示与
  release label 是完整 `v0.0.0.1`；该状态必须由 canonical source、真实 release SHA、manifest、registry
  entry 与 validator 共同证明，且不代表已安装到本机运行时。
- `equity-foresight-signal=0.0.0.1`、`global-equity-lead-lag-atlas=0.0.0.1` 与
  `equity-event-atlas=0.0.0.1` 均为 `numeric-quad`、`SOURCE_ONLY`、禁止本机安装的 current entries；
  三者均只提供研究/决策支持，不连接账户、不执行交易。
- Validator 的 current 输出保留 semver major shorthand（例如 `3.0.0` 显示 `v3`），但
  `numeric-quad` 必须显示完整版本（`0.0.0.1` 显示 `v0.0.0.1`，不得缩写为 `v0`）；release 文件名使用
  完整的 `v<latest_version>`。
- 本仓只保存源码和可恢复备份；不得据此写入 `~/.agents/skills` 或 `~/.codex/skills`。

## 迁移状态

本仓库正从 LinzeColin/CodexProject 分批迁入项目。
EEI 已于 2026-07-15 迁入（wave 3，含完整历史与自带 CI `eei-validation`）。
ADP（`arxiv-daily-push/`）已于 2026-07-20 迁入并纳入 `dual-plane.yml`；
canonical 交接入口是 `arxiv-daily-push/docs/HANDOFF.md`。
ADP 当前增量开发合同是 `arxiv-daily-push/docs/pursuing_goal/v1_2/`；它按
单任务 Run Contract 推进，不覆盖 V7.2 的旧本机运行时兼容边界。
PFI 仍在 CodexProject 中；迁入前不要在本仓库创建顶层 `PFI` 占位目录或桩代码。

ADP 历史合同仍以仓根相对路径引用 `FINAL_ACCEPTANCE_BUNDLE/`、
`governance/run_manifests/ADP-*` 和 4 个 `tools/` 只读校验入口；这些是迁入的
ADP 证据/兼容面，不是本仓治理框架。禁止据此复制 CodexProject 的旧
`repository_hygiene_policy.json`、`generate_governance_dashboard.py`、
`validate_project_governance.py` 或 `project-governance.yml`。

## ADP 来源与板块变更门（强制）

Any ADP source or board add/delete/rename/enable/disable change must pass the
user-center sync gate in `arxiv-daily-push/AGENTS.md`. config/code-only changes are not complete
until every required owner-facing page and both named tests are
synchronized in the same change.

---

## 云成本红线：对象存储必须零付费（Owner 硬指令 · 长期有效）

**云端账单必须恒为 $0.00。不允许任何 agent 触发收费行为。**

1. **禁止 `InfrequentAccess` 存储类** —— 建桶、写对象、生命周期转换，一律不许。
   R2 的免费额度（10GB 存储 / 100 万 Class A / 1000 万 Class B）**只覆盖 Standard**；
   IA 从第 1 次操作起计费，且**按整计费单位向上取整**。
   2026-08-07 实账单：**51 次 IA 操作 = $9.00**，同期 **301 万次 Standard 操作 = $0.00**。
   根因是建桶时默认存储类选了 IA，写入端不指定存储类就全部继承 —— 一次手滑，之后静默自动计费。
2. **禁止"整包下载来判断存在 / 做校验"的高频轮询。** 判断对象存在用 `HeadObject`
   （写入时把 sha256 放进对象 `Metadata`，Head 就读得到）；真要逐字节复核，
   **按天或按周跑，不许按分钟跑**。
   反例：memory-atlas reconcile 每 15 分钟把 2466 个对象整包拉一遍核 sha256，
   折合 71 万次 Class B/天、21.3M/月，直接打穿 10M/月免费额度。
3. **新增或改动任何周期性任务，先算月操作量**：
   `每轮操作数 × 每天轮数 × 31 < 免费额度 × 50%`。**算不出来就不上线。**
4. **存储优先级**：**GitHub Release 资产 > R2 > OVH 本地**。
   Release 资产不计仓库体积、没有操作计费，永远优先。

完整事故记录、账单逐行归因、免费额度速查表 → **`Private-Database` 仓 `OPS/AGENT_ONBOARDING.md` §9.7**。
机器守卫 → OVH `/usr/local/bin/linze-r2-free-tier-guard.py`（每 6 小时，非 Standard 桶自动熔断改回；
判定 `/srv/linze/apps/status/data/r2_free_tier_guard.json`）。

### R2 周期任务清单与预算（改动前必读）

云端账单恒为 $0.00，靠的是下面这份预算不被打破。**改这些任务的频率、范围或参数之前，先算月操作量。**
数字为 2026-08-07 实测（Cloudflare GraphQL `r2OperationsAdaptiveGroups`，7 个完整日日均外推）。

| 任务 | 频率 | 桶 | 作用 | 月 Class A | 月 Class B | **一碰就变收费的地方** |
|---|---|---|---|---|---|---|
| `weread-port-r2-oci-backup` | 每日 04:23 | weread-port-private | 加密用户对象镜像到 OCI 异地冷备 | 465 | 0 | **`rclone sync` 必须带 `--fast-list`**。删掉它 → 按前缀逐个列举，实测 15 次 → **9,300 次**（Class A 额度的 28.8%），且随对象数线性增长 |
| `memory-atlas-reconcile` | **每日** | weread-port-private | 核对 R2 是否仍持有 manifest 里的字节 | 434 | **229,338 (2.3%)** | **频率**。原为每 15 分钟 = 21.3M/月，直接打穿 10M 额度。因为 `exists_with_hash()` 对每个对象**整包下载**（2 Head + 1 Get × 2466 对象 = 7,398/轮） |
| `linze-status-r2-mirror.sh` | 每 5 分钟 | primary-objects | status 站数据镜像 | 31,872 (3.2%) | ~200 | **镜像的文件个数**。每多镜像 1 个文件 = +8,928 次/月 |
| weread-port 平台写入（常驻） | 持续 ~56 次/小时 | weread-port-private | 加密笔记 / 跨设备同步的对象写入 | 41,664 (4.2%) | 0 | 随用户活跃度增长。**写入方未逐一归因**，但已确认不是 reconcile（降频后仍在） |
| `social-archive-replication` | 每 15 分钟 | social-archive-e2n-v0004 | 对象复制到多存储 | 3,224 | 19,468 | **`--limit 200` 这个上限**，别放大 |
| `weread-port-private-database-backup` | 每日 04:01 | backups | Private-Database git bundle 冷备 | 190 | ~30 | 有 `UNCHANGED` 短路，**别去掉** |
| `linze-offsite-backup.sh` | 每日 03:40 | backups | 全量加密备份（单对象） | ~60 | ~30 | 别改成分片小块上传 |
| `cyberboss-backup` | 每日 03:35 | cyberboss-cold | CyberBoss 冷备 | 35 | ~150 | — |
| `memory-atlas-action-worker` | 每分钟 | weread-port-private | 有界 owner 动作队列 | ~0 | ~0 | 队列空时不发任何 R2 请求；**队列一旦长期非空，就会变成每分钟打 R2** |
| 其余（adp / sl-* / kmfa / status-evidence） | 每日 | 各自 | 各项目产物 | <900 | <100 | — |
| **合计** | | | | **≈ 8.0% 的 100 万/月** | **≈ 2.5% 的 1000 万/月** | |

**余量**：Class B 有 **40 倍**余量；Class A 有 **12 倍**余量。两者都健康，但 **Class A 历来是先见底的那个**
（修 `--fast-list` 之前它已经到 37%，而 Class B 只有 2.5%）—— 盯额度先盯 Class A。

**改动这些任务时的三条硬规则**

1. **别删这三类参数** —— 它们是额度的直接开关，不是性能调优：
   `--fast-list`（rclone 列举方式）、`--limit`（单轮上限）、`UNCHANGED` / `--skip-if-unchanged`（无变化短路）。
2. **别把日级任务改成分钟级。** 先算：`每轮操作数 × 每天轮数 × 31 < 免费额度 × 50%`。**算不出来就不上线。**
3. **别用"整包下载"判断对象存在或做校验。** 判断存在用 `HeadObject` 读 `Metadata.sha256`；
   逐字节复核按天/周跑，不许按分钟跑。（`exists_with_hash()` 就是反例，它是这次事故的第二个根因。）

**改完自己核**（不要交给 owner 去发现）：

```bash
ssh ovh 'sudo /usr/local/bin/linze-r2-free-tier-guard.py'
```

它会打印本计费周期 Class A / Class B / 存储对免费额度的投影占比，≥70% 报 WARN、≥90% 报 CRIT，
并把判定写进每日复审清单。完整事故记录见 `Private-Database` 仓 `OPS/AGENT_ONBOARDING.md` §9.7。

**存储维度（唯一跨月累积的）**：操作次数每计费周期清零，**存储不清零**。2026-08-10 实测 **4.55 GB / 10 GB = 44.4%**。

| 桶 | 当前 | 状态 |
|---|---|---|
| `weread-port-private` | 3.22 GB | 冻结（memory-atlas 迁出后不再增长） |
| `backups` | 0.96 GB | 冻结（`linze-offsite-backup.sh` 的 R2 写入已停用：`R2_CODE=disabled_zero_charge_policy`） |
| `social-archive-e2n-v0004` | 0.31 GB | **3 天保留封顶**（见下） |
| 其余 7 个桶 | 合计 <0.06 GB | 冻结 |

**social-archive 的 3 天保留（Owner 2026-08-10 定）**

`backups/runtime-db/` 每 15 分钟写一份 1.03 MB 加密快照，而 `prune_runtime_db_snapshots.py`
**只清本地**——它的文件头明确写着「不碰远端副本(R2/OCI/GitHub)，保留期是另一个决定」，
那个决定一直没给，于是 R2 上累积了 **512 份 / 521 MB、+99 MB/天**，是当时账号里唯一还在长的东西。

现由 `social-archive/scripts/prune_r2_backup_replicas.py --apply` 承接（挂在
`social-archive-backup.service`，每日 03:20），保留 **72 小时**，稳态约 290 MB。首次执行删了 258 个 / 234 MB。

> **改动禁区**：① 别删那条 `ExecStart`，② 别把 `--apply` 拿掉，③ 别放宽 `--hours`。
> 脚本的安全底线也别削：**删 R2 对象前先 `HeadObject` 核对 OCI 上同 key 同大小，核不上就跳过不删**；
> 最新一批永远保留；只碰 `backups/<组>/<时间戳>/`，**不碰 `primary-objects/`（那是制品字节，删了就是毁档）**。
> 每份快照有 `r2`/`oci`/`github` 三个 verified 副本，删掉 R2 那份仍剩两份 —— 这是「卸载」不是「删除」。

---

## Cloudflare 部署：三个 worker 是三种契约，**裸跑 `wrangler deploy` 会清空线上变量**

**结论**：`wrangler deploy` 对 vars 是**替换**不是合并。**secret 会自动保留，plain_text 不会** —— 这个不对称最容易漏。
2026-08-12 照仓里 `wrangler.jsonc` 裸跑一次 `npx wrangler deploy`，`weread-port` 线上 **8 个仓外 plain_text 变量当场全没**，
站点报「账户服务尚未完成安全连接」，**断 3 分钟**，靠 `wrangler rollback --version-id` 才救回来。

**为什么会犯**：同账号下另两个 worker 能裸跑，我据此类推。但三个 worker 的部署契约**完全不同**：

| worker | vars | 裸跑后果 |
|---|---|---|
| `adp-cloud` | 0 个 | 无害 |
| `codex-eei` | 3 vars + 3 secrets | secret 留、vars 没 |
| `weread-port` | **8 个仓外 plain_text** | **全部清空 → 断站** |

**代价**：真实生产中断 3 分钟；根因是**生产配置活在版本控制之外**，仓里那份 `wrangler.jsonc` 不是事实。

**改动禁区**：三个仓各自的部署脚本已经把「先拉线上 vars 比对、缺谁报谁、失败自动 rollback」做进去了 ——
`WeReadPort/scripts/deploy-cloudflare.mjs`、`arxiv-daily-push/deploy/cloudflare/deploy.py`、`EEI/scripts/deploy_cloud.sh`。
**用脚本，不要裸跑 `wrangler deploy`**；也不要把某个 worker 的做法套到另一个上。

> 踩过的次生坑：`wrangler.jsonc` 里加注释会让 `check:release` 挂（它用严格 `JSON.parse`，不管扩展名是 .jsonc）；
> `mapfile` 是 bash 4+ 而 macOS 自带 3.2；urllib 默认 UA 会被 Cloudflare 403，**把一个完全正常的部署自动回滚了**。

## `make verify` 是 40 个**顺序**目标：第 27 个红着，后面 13 个在 CI 里一次没跑过

**结论**：EEI 的 `validate-clean-room-release` 排第 27，长期红。它后面 13 个目标 ——
其中有 **`secret-scan` / `copy-lint` / `lint` / `typecheck` / `test`** 和整串 soak ——
**在 CI 里从来没有执行过**，而面板上只显示一行 `clean-room stale`。
修好第 27 个之后，第 28 个（`validate-release-artifacts`）**当场也红了**，它被挡了同样久。

**为什么**：一道长期红的门不是一个孤立事实，它是个**开关** —— 它红着，它后面所有门等于关掉。红的时长越长，被掩护的东西越多。

**两处漂移都不是回归**，是产物没跟着源码重新生成：clean-room ZIP 缺 `scripts/cf_worker_vars.py`（PR #182 加的文件），
`manifest.txt` 差异**恰好同一行**；另有 #175 改的 `WHERE_IS_THE_DATA.md` 一行 IP（VPS-1 退役）。
修法是跑 `manage_clean_room_release.py generate` 和 `manage_release_artifacts.py generate`（PR #193）。

**代价**：查根因时我从 git log 找到 #175 就以为是唯一漂移，一跑复现报的却是**我自己在 #182 加的文件** ——
**先跑复现拿当前失败文本，再回历史里找它，顺序不能反**；长期红里可能有自己的一份。

**改动禁区**：报「已修复」之前必须把后面全部跑完并贴退出码。
核对某个目标跑没跑，要按它的**实际 recipe 命令** grep（`make` 只回显命令不回显目标名，按目标名 grep 会得到假阴，我第一次就这么错了）。
本机 bootstrap 用 `make bootstrap PYTHON=python3`（macOS 无 `python`，Makefile 顶上 `PYTHON ?= python` 就是留的口子，别改文件）。

## 长期红的门：先分「判据考的是逻辑还是数据」

**结论**：两道在 main 上长期红的 ADP 门，查下来**都不是回归**。

- **30 天回填门**（PR #191）：要求 `content_ledger_queued_row_count >= 30`，而队列只收 ROI 达标的落选候选，
  「当天没有够格的亚军」是正常态（实测 19/30 天为空）。**它考的是语料碰巧有多少高分亚军，不是重放对不对。**
  换成数据无关的不变量（`mismatch_day_count == 0`）后 CI 真跑重放：`status=pass`，而 `47/30/17` 三个数**与被判 blocked 时一模一样**。
- **六主题视觉门**（PR #192）：基线冻在 24 天前。用门自己的 `run_ci` 比对，18 项里只有 2 项不一致；
  逐提交追踪，`page_shell` 只在一次「标题面 deMath」变过，unified diff **恰好 2 行、只有 `<title>` 那行**。
  重冻工具 `ABORT: unexplained drift` **拒绝盖橡皮图章是对的** —— 缺的不是权限，是归因证据，补齐逐提交+逐行证据后它自己放行。

**代价**：那 24 天里这道门对任何改动都报红，**真回归和背景红分不开**。

**改动禁区**：重冻/换判据之后必须验**三个方向** —— 正例过、真回归拦、相邻类别也拦。只验「现在绿了」等于把门关掉。

> `arXiv Daily Push real 30-day backfill` 只在 `pull_request` / `workflow_dispatch` 上触发，
> **从不在 push to main 上跑**，所以 main 永远显示最后一次 PR 的结果 —— 看到它在 main 上红，先确认那次运行的 sha 是不是 84 个提交之前的。

## ABD 发布：凭据已解封，但**ABD 根本没注册进 Coolify**

**结论**：2026-08-13 `ABD Coolify controlled release` 连failure 3 次，报
`inventory_transport=authorization_rejected` / `Coolify rejected the deployment credential.`
**根因是 MetaDatabase 仓的 GitHub secret `COOLIFY_API_TOKEN` 死了，而 KMOS 仓的是活的**（同日 `deploy` success）——
两个仓的 secret 各自独立。死因不是过期：查 `coolify-db` 的 `personal_access_tokens`，
**老的 id 7/8 已被删除，id 被 08-11/08-12 新建的 token 复用了**，明文对不上新哈希。

Owner 授权后由 agent 在服务器侧签发 id `12` / `abd-deploy-20260813`（权限 `read`/`deploy`/`write`，team_id `0`），
三个端点实测全 200，写进 MetaDatabase secret，重跑 → **success**。

**但部署仍做不成，原因换了**：那次 success 的输出是 `abd_candidate_count=0` / `release_action=no_deployment_requested`。
直接查 `coolify-db`（绕开 API 的 team 作用域）确认：**`applications` 表 4 条、`services` 表 0 条，没有任何名字含 `abd` 的资源**
（只有 `linze-home-hub` / `pfi-public` / `serenity-public` / `kmfa-kmos-p1`）。
而服务器上确实跑着容器 `abd-shadow-blue-abd-shadow-1` —— **ABD 是在 Coolify 之外部署的**。

**代价**：在此之前任何「已上线」的说法都不成立。下一步不是找凭据，是**决定 ABD 要不要以 Coolify application 的形式存在**（产品决定）。

**重签 token 会再撞上的两个坑**：
① `$u->createToken(...)` **会失败** —— Coolify 给 `personal_access_tokens` 加了 NOT NULL 的 `team_id` 列，Sanctum 不填它；
必须 `$u->tokens()->create([... 'team_id'=>0])` 自己拼。
② 别把输出接 `| grep MINTED` —— 第一次就是这样**把报错过滤掉了**，我据此以为「没签成」，查库发现表里没新行才知道真失败。

> 凭据与基础设施现状在 `_protected/ABD云服务解封_TaskPack_v1_20260813/`（本机 `_protected/`，永不上传）。
> **KMOS 仓的 `COOLIFY_API_TOKEN` 一直是活的，别动它。**

## Kimi Code Desktop / Harness UI：候选安装包不等于 A 级 Release

**结论**：跨平台桌面项目必须在干净 runner 实际生成 macOS arm64 的 DMG/ZIP 与 Windows x64/arm64 的安装器/ZIP；只编译 `.app`、`.exe` 或 unpacked 目录不能报“可安装”。A 级公开发布还必须同时通过 Apple Developer ID 签名与公证、Windows Authenticode 签名，缺凭据时保持 `WAITING_SIGNING_CREDENTIAL`，不发布未签名 Release。

**为什么**：本次目录构建先后漏出了 Windows 路径分隔符、PowerShell 对 electron-builder 短参数的解析差异；提升到完整安装包后才证明 DMG、Inno、NSIS 与双架构 ZIP 都能真实生成。Harness 图片继续只留在 `smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/`，Git 只保存代码、标签与 SMB 地址；目录支持手动同步与 15 分钟轻量刷新。

**代价**：完整 Windows 候选门约 10 分钟；签名 secrets 缺失时源码和候选构建可以合并，但正式 Release 仍未签发，且不得为验证而重启 owner 正在运行的 Kimi、DSH 或 Harness。

## Kimi 皮肤：空会话可见不代表已有线程页可见

**结论**：皮肤验收必须同时打开空白新会话和有长消息/表格的既有线程。人物场景只放在根背景；普通根层、侧栏、阅读列使用分层半透明玻璃，输入框保持约 98%，模型、工作区和创建工作区弹层保持 99%；系统“降低透明度”单独切为实体背景。不要为了可读性把所有 `surface/panel/content-wrap` 一起提高到 90% 以上。

**为什么**：空白页没有阅读列，看起来皮肤正常；既有线程叠加 `color-bg`、`surface`、`panel` 与 `.content-wrap` 后，单层 90% 看似合理，最终合成却接近纯白。Node 回归和空白页截图都不会暴露这个错误。

**代价**：一次“透明度修复”把皮肤本身洗掉，Owner 在实际线程页才发现。以后视觉门固定检查“背景确实可见、正文确实可读、弹层确实不透”三个互相独立的条件；运行中修正可用临时本机 inspector 注入 CSS 验收，但必须关闭 inspector，并把持久修复进入正式安装包。

**结论**：签名 Release 不能只检查 secret 非空或数安装包文件；Electron 项目要强制 `forceCodeSigning`，Mac App/DMG 要验证签名、stapled 公证票据与 Gatekeeper，Windows 主程序/安装器要验证 Authenticode 信任链和时间戳，全部通过后 publish job 才能创建 Release。

**为什么**：无效证书可能让构建工具回退为未签名输出，文件数量仍然完全正确；签名存在也不证明 Apple 公证票据已附带或 Windows 时间戳已写入。先在轻量 guard job 一次性列出缺失 secret，可避免明知无法发布仍分配 macOS/Windows runner。

**代价**：正式发布多一次 DMG 公证和若干本地验签，但换来离线 Gatekeeper、Windows 证书过期后的时间戳有效性和“不可能误发 unsigned Release”的硬证据。

## 零付费桌面发行：社区版与受信任签名版必须双轨

**结论**：Owner 将预算锁为 `$0` 后，Apple Developer ID/公证不再是可执行交付；必须保留原 signed workflow，同时另发名称、tag、资产名和 Release 文案都明确标注安全状态的 community prerelease。macOS 用 `NOT-NOTARIZED`，Windows 用 `UNSIGNED`，任何一方都不得简称“A 级”或“已签名”。

**为什么**：免费 Apple Account 只能开发和个人测试，Developer ID 与 Mac 公证属于付费 Apple Developer Program；代码、自签名证书或 GitHub Actions 都不能替代 Apple 的发行身份。把未公证 DMG 做得能下载，不等于 Gatekeeper 会信任它。Agent clone 后通过系统自带 `curl` 安装固定 GitHub Release ZIP，可以降低工具链门槛，但仍不能改变签名事实。

**代价**：零成本路线可以交付 macOS arm64、Windows x64/arm64 安装资产和一键迁移脚本，但下载件可能触发 Gatekeeper/SmartScreen；Release 必须保持 prerelease 且不设为 Latest。未来取得真实证书时，另走 signed workflow，不能覆盖或改名洗白既有 community 资产。

**结论**：桌面壳、CLI 后台与 macOS TCC 是三层身份；更新必须保持 App 路径、bundle id 与签名身份稳定，`Cmd+W` 只释放窗口，`Cmd+Q` 才结束由该 App 管理或安全接管的后台。更新器要先验签/验 Gatekeeper，再做旧版回滚点与原子替换；图标、皮肤、配置、会话和素材一律放在 App Bundle 外，并在失败后自动重新打开旧版、留下回执。

**为什么**：只重启 GUI 不会清掉长寿命 CLI 的旧权限上下文；覆盖 App Bundle 会丢个性化资源，更新后再改已签名 Bundle 又会破坏 Developer ID 身份。HarnessUI 的 LaunchAgent 还可能能列 SMB 目录却被 TCC 拒绝读图片，因此 catalog/state 必须带 generation 热同步，并采用“完整本地镜像优先、SMB 补充、缺分区不覆盖上一版”的完整性门。

**代价**：DSH 2.0.2 上游运行时代码变化使首次本地补丁安全停止，且失败阶段曾残留在 `/Applications`；补齐双版本补丁契约、失败清理、本地镜像降级和真实应用内更新验收后，后续更新不再依赖 Agent 手工救场。Kimi 正式安装仍必须等待 Developer ID/公证凭据，未签名候选件只能静态验收，状态保持 `WAITING_SIGNING_CREDENTIAL`。

## 桌面 App 版本与无资质更新：一个产品只能有一条版本线

**结论**：Kimi Code Desktop 的 App 版本必须直接等于所内置的 `MoonshotAI/kimi-code` 官方版本；DSH Desktop 必须直接等于 `anywhere-labs` 官方版本。不得再用 `1.0.1`、`community-v*` 等桌面壳私有版本覆盖上游版本。Harness UI 没有外部官方上游，沿用 AgentDatabase 已存在的 `1.0.0` 产品线。无 Apple/Windows 资质时仍发布同一正式 tag；未来获得受信任签名后只替换同一 Release 的资产，不另开版本。

**为什么**：私有包装版本会让 `1.0.0 > 0.38.0`，导致真正的新官方版本被更新器判成降级；前台、后台和 GitHub 三套数字也让 Owner 无法判断实际运行版本。唯一版本线让 App 菜单、内置 CLI、Release tag 和另一台电脑安装包保持一致。

**代价**：旧包装版迁移到 `0.38.0` 需要在现有 Kimi 任务结束后做一次人工替换；之后 GitHub 每日自动读取官方最新 Release，缺同版本资产时自行构建/镜像，不再需要 Agent 每次改版本。

**结论**：无 Developer ID 的 macOS 构建不能继续接受默认的临时 ad-hoc designated requirement。必须用稳定 bundle id 显式签出本地 requirement：Kimi 为 `com.electron.kimi-code`、Harness UI 为 `com.linzecolin.harnessui`、DSH 为 `ai.deepseek.dsh.desktop`；用户配置、图标、皮肤、素材和会话继续全部外置。

**为什么**：现场 Kimi 的实际代码标识是 `Electron`，designated requirement 直接绑定单次二进制；本地个性化后的 DSH 也绑定单次构建。每次更新代码身份漂移，会让 TCC 中不同前台/后台进程出现权限不一致。固定本地 requirement 可在不阻塞公开发布的前提下保持后续同一 App 身份；首次从旧身份迁移仍可能需要 Owner 重新确认一次完整磁盘访问。

**代价**：这种本地 identity 不等同于 Apple 公证，首次启动仍可能有系统确认；但它消除了“每次构建都换身份”的确定性缺陷。未来 Developer ID 流程不得被本地 after-sign hook覆盖。

**结论**：看到 DSH 日志中多次启动，先把时间点与 Agent 的 `open`、诊断启动和受控更新一一对齐，再判断自动重启。本轮没有 DSH launchd/登录启动项，正常退出后连续 90 秒没有自动拉起；此前“总是自动重启”来自诊断操作本身。

**为什么**：把观测动作造成的进程变化误报成产品行为，会诱发继续重启、继续观测的自证循环。真正的 DSH 自动重启只允许出现在用户明确确认更新后的退出安装路径。

**代价**：本轮停止了不必要的重启；DSH 保持退出，Kimi 全程未重启。

**结论**：Electron 桌面壳升级时除了 App Bundle、CLI home 和 TCC 身份，还必须固定或兼容 `app.getPath("userData")`。Kimi 旧包装版使用 `Application Support/kimi-shell`，新 `productName` 默认会切到 `Application Support/Kimi Code`；检测到旧目录时必须继续使用旧 profile，fresh install 才使用新目录。

**为什么**：只保护 `~/.kimi-code` 仍会遗漏 Electron Cookies、Preferences、Session Storage 和窗口状态。首次 `0.38.0` 迁移现场就出现了新目录，表现会像账号或界面配置丢失，虽然原数据仍在。

**代价**：同一上游版本内的包装兼容修复需要重建并覆盖同 tag Release 资产，不能另造私有版本号；当前机器须重新安装一次修复后的 `0.38.0`，早期误建的新 profile 只归档、不覆盖旧数据。

**结论**：macOS 的 ad-hoc App 即使显式写了稳定 bundle id / designated requirement，TCC 仍可能把完整磁盘权限绑定到本次构建的 cdhash；不能据此宣称跨更新权限稳定。Kimi Desktop 必须保留 Moonshot 官方 CLI 的 Developer ID 签名，并始终从 `~/.kimi-code/bin/kimi` 这一稳定路径启动后台。

**为什么**：现场 TCC 行显示 `com.electron.kimi-code` 已允许，但其 requirement 实际绑定旧构建；更新后 GUI 直接派生的后台访问 `/Volumes/share` 一直挂起。同一 `0.38.0` 官方签名 CLI 由 launchd 作为父进程启动后可立即列出和读取 SMB。根因一是 electron-builder 与 after-sign 的 deep signing 覆盖了 Moonshot 的签名，二是 GUI 直接 spawn 会让子进程继承 ad-hoc Electron 壳的 TCC responsibility；after-sign 需恢复官方二进制后只重签外层 App，后台则交给当前用户域的临时 launchd job。

**代价**：桌面启动时只允许替换稳定路径中的 CLI 本体，并把旧版本留进 `desktop-updates/cli-rollback/`；`~/.kimi-code` 的配置、会话、登录、个性化目录和 `~/.harness-ui` 必须原位不动。临时 launchd job 必须由 App 管理：关窗保留，正常退出移除，App 崩溃后下次启动可安全接管；提交 job 时只传 HOME/PATH/TMPDIR/locale 等必要环境，禁止把 GUI 继承的 API token 或其他 secret 扩散到后台。外层 App 在取得真实 Developer ID 前仍不是受信任发行身份，但文件访问后台不再随每次桌面构建换身份。

**结论**：诊断本机 bearer 服务时，不能把 `Authorization` 值直接放进可被 `ps` 读到的 curl 参数；读取 token 的探针应在进程内部组装请求，若任何诊断输出暴露了 token，立即旋转并确认旧值失效。

**为什么**：排查 Kimi SMB 卡顿时，一次进程列表把 localhost bearer token 连同 curl 参数输出到了诊断记录。虽然服务只监听 loopback，记录本身仍扩大了凭据暴露面；现场已用 `kimi web rotate-token` 在线轮换，无需重启 GUI。

**代价**：后续 API 探针统一由短生命周期 Node 进程读取 `server.token` 并发送，日志只保留状态码、耗时与结果形状，不输出 header 或 token。

**结论**：Kimi、DSH、Harness UI 的“下一张”必须是共享服务端的原子动作，不得再把 `mode=rotate` 同时当成模式更新与单次推进。三端统一调用 `POST /api/next`、统一 `Cmd/Ctrl+Shift+N`，客户端只轮询同一 catalog/state。

**为什么**：旧实现里 Electron、Swift、Windows 各自把 `mode=rotate` 解释成推进，而 Python 服务只保存 mode；结果是按钮看似成功但 selected/cursor 不动，且三个宿主可能各自显示不同状态。服务端原子推进后，旧客户端兼容入口也能在线恢复。

**代价**：每次共享状态协议变化必须同时跑 Node、macOS、Windows 候选；活动中的旧 Kimi 可通过服务兼容层恢复按钮，但代码级快捷键仍要等自然退出后加载新包。

**结论**：macOS 回滚副本绝不能继续以 `.app` 结尾；更新器必须持久化正式安装位置，回滚目录使用 `.app.rollback`，并在备份未运行时隔离历史 `.app`。从 rollback 副本误启动时，更新目标仍必须回到正式 App。

**为什么**：隐藏目录中的完整 `.app` 仍会被 LaunchServices、Siri 或界面自动化注册成同 bundle id 的另一个应用；按名称启动时可能命中备份，造成前台路径、TCC 责任和后续更新目标漂移。

**代价**：旧回滚副本不能在活动进程期间改名；先保护当前线程，等新包从正式路径启动后再自动隔离。回滚仍可通过目录改名原子恢复，不牺牲恢复能力。

**结论**：对用户明确要求“不重启”的活动桌面 App，Computer Use 的 `get_app_state(app=...)` 也不算只读安全操作；它可能通过 `coreservices.uiagent` 发起 LaunchServices 启动或重试。此时只允许用 `ps`、`lsof`、loopback 状态与系统日志取证。

**为什么**：本轮用界面读取做皮肤目视验收时，系统日志明确记录 uiagent 连续发起 Kimi 启动请求；由于同 bundle id 的 rollback `.app` 已注册，最终切到了备份路径。没有崩溃报告，异常由观测动作和重复 App 身份共同造成。

**代价**：活动 Kimi 的本轮验收降级为服务状态与跨端状态证据；完整快捷键目视验收留到 Owner 自然退出后的正式包激活，不能为了“验收完成”再次触碰进程。

**结论**：Electron renderer reload 会销毁皮肤 DOM/CSS，但 main process 中的 `lastAppliedKey` 仍会存活；`did-finish-load` 必须先重新插入 CSS，再清空应用键并强制重放当前 catalog/state。只给菜单项或轮询加快捷键不能修复 `Cmd+R` 后皮肤消失。

**为什么**：现场共享状态、选中素材和缓存键都没有变化，旧 bridge 因此把重载后的空 DOM 误判为“已经应用”。在不重启活动 Kimi 的条件下，通过既有 main process 对 renderer 做一次等价 reload，确认重载后当前工作线程、CSS URL 与真实合成画面同时保留。

**代价**：Kimi Node 回归新增 reload 行为契约；活动旧壳需要一次进程内恢复，新正式包自然启动后由永久 `did-finish-load` 路径接管，不保留调试端口或第二套后台。

**结论**：菜单栏 accessory App 的 `NSMenuItem.keyEquivalent` 不是全局快捷键。三端统一的 `Cmd/Ctrl+Shift+N` 在 macOS 由 Harness UI 使用 Carbon `RegisterEventHotKey` 注册为唯一全局 owner，Kimi/DSH 只保留宿主前台回退；每次改动必须验证一次按键只推进一个 cursor。

**为什么**：Kimi 或 DSH 在前台时，旧 Harness UI 收不到菜单快捷键。全局注册后若事件继续传给 DSH renderer，又可能一次推进两张；现场以 DSH 前台按一次，服务 cursor 精确从 34 到 35，排除了重复消费。

**代价**：Carbon 注册必须在 App 退出时释放，Harness UI 无窗口启动时用进程与共享状态验收；本机 Command Line Tools 失配时，以干净 macOS runner 的 Swift build/test 为编译证据。

**结论**：共享皮肤客户端必须同时防两类画面倒退：异步图片预加载用单调 revision 只允许最新请求落地；`immutable` 素材 URL 额外加入稳定 `skin=<entry.id>` 身份键，避免正确的 selected/CSS URL 继续命中历史错误位图。

**为什么**：DSH 快捷键已经把 cursor 从 32 推到 33，DOM active label 与 computed style 也都是桂乃芬，但真实合成画面仍停在伊芙琳；为同一素材追加新的身份 query 后，合成画面立即变为桂乃芬。单看 state、DOM 或截图中的任一项都不足以定位这类故障。

**代价**：DSH 与 Kimi 必须共享同一缓存键规则，并用真实合成画面做最终验收；稳定 skin key 可复用正确缓存，不需要每次切换都下载一份新的 7MB 素材。

**结论**：用户级 SMB LaunchAgent 不能把 AppleScript `mount volume` 作为唯一重连路径；Harness UI 的 macOS 包必须携带一个使用 NetFS `NoUI` 的小型 mounter，服务安装时复制到 `~/.harness-ui`，锁屏重连优先调用它，旧包才回退 AppleScript。

**为什么**：现场 `/Volumes/share` 被正常卸载后，锁屏状态下 AppleScript 一直等待 GUI 会话；同一用户、同一 guest URL 的 `NetFSMountURLSync` 在不到 1 秒内恢复规范挂载，随后 GUI-owned helper 重新得到 SMB 408、本地 408、目录 408、缺失 0。

**代价**：macOS 包增加一个很小的原生 sidecar，并在服务更新时只替换该 helper；账号、凭据、catalog、state、master、皮肤和图标都不进入 helper。若 App 尚未包含 sidecar，兼容回退仍可在解锁状态挂载。

**结论**：Harness UI 的“同步 SMB 素材”不能把 `SMB + 本地 fallback` 的并集数量当成 SMB 同步成功。刷新必须先把 SMB 中完整的 `light.png` / `dark.png` 对原子部署到 App Bundle 外的 durable master，再分别报告 `smbCount`、`localCount`、`catalogCount`、`deployedCount`、缺失素材和缺失分区；SMB 不完整时状态必须是 `partial`，且不得删除本地既有素材。

**为什么**：现场 SMB 只有 326 个可消费变体，本地完整库有 408 个；旧实现只合并两边目录、不复制素材，却用并集 408 个显示“已同步”，同时掩盖了 SMB 缺少 82 个既有素材和异环完整分区。刷新按钮因此看似成功，另一台电脑却拿不到本机 fallback 中的缺口。

**代价**：首次同步会把可用 SMB 素材复制到 `~/.harness-ui/master`，后续按文件大小和修改时间增量部署；本地独有素材继续保留，直到 SMB 真正补齐时状态才从 `partial` 变为 `ready`。loopback HTTP 只是进程间实现细节，“打开完整素材库”在 macOS 必须通过原生 WebKit 窗口和 `harnessui://library` 唤起，不能再把用户送到 Chrome 标签页。

**结论**：macOS SMB 同步的读取 owner 必须是 Harness UI GUI App，不能是裸 Python LaunchAgent。3099 后台服务保留共享状态与本地供图，但刷新时必须通过相邻 loopback helper 请求 GUI App 读取 SMB、原子部署到 durable master，再用实际落盘素材核验 helper 回执。

**为什么**：TCC 日志把 launchd Python 归因为 `com.apple.dt.xcode_select.tool-shim` / `/usr/bin/git`，同一挂载在终端可读、后台却扫描为 0；旧实现又把本地 408 并集误报为 SMB 已同步。仅增加复制代码无法跨越 Network Volumes 的责任身份，必须让有稳定 bundle id 和权限说明的 Harness UI App 执行读取。

**代价**：Harness UI 运行时额外监听仅限 loopback 的同步 helper（默认主端口 + 1）；Kimi/DSH 仍只访问 3099。App 未运行或权限未授予时服务继续保留本地完整库并返回 `partial`，不会回退到伪成功，也不会删除本地素材。

**结论**：SMB 挂载 LaunchAgent 不能把“Network Volumes TCC 禁止读取 volume ID 内容”直接等同于错误挂载。先用 `smbutil` 精确确认服务器与共享名并确认 marker 路径存在；marker 可读时必须匹配固定 ID，不可读时才使用前述 SMB 身份作为受限降级判据。

**为什么**：现场 `/Volumes/share` 在终端可读且素材为 408/408，但后台 job 能完成 `smbutil statshares` 和文件存在性判断、读取首行却返回 `Operation not permitted`。旧脚本因此每 60 秒退出 70 并追加错误日志，制造重复挂载假象和无效资源消耗。

**代价**：TCC 拒绝内容读取时不再验证 marker 文本本身，但仍同时约束固定服务器、固定共享名、真实 smbfs 状态和 marker 存在；内容一旦可读仍执行严格匹配。代码回归与真实 LaunchAgent 都必须通过后才能安装。

**结论**：完整素材库页面必须独立轮询 `refresh-status.json`，不能只在皮肤 state 或 catalog generation 变化时顺带更新同步状态。

**为什么**：首次由 GUI App 完成 326 套 SMB 部署后，服务端已正确写出 `partial` 回执，但皮肤选中状态没有变化，网页的提前返回分支让标题仍停在“正在读取 SMB 素材目录”。素材已经部署成功，用户界面却像永久卡住。

**代价**：原生素材库每秒把轻量 refresh 状态与共享 state 一起读取；只有状态、目录或选择实际变化时才重绘。这样后台自动刷新与人工按钮刷新都能在同一 GUI 内显示最终回执，不需要重新载入窗口或打开浏览器。

**结论**：安装或更新 Harness UI 时，3099 共享服务与 GUI App 不能无序并发启动。服务安装器返回成功前必须确认 `state.json` 已可读；检测到共享服务 LaunchAgent 的 App 也必须给它一个有上限的就绪窗口，再决定是否启动 standalone 服务。

**为什么**：现场服务和 GUI 在同一秒启动，App 的第一次探针早于 Python 监听完成，于是没有建立 3100 helper，后台只能再次报告 SMB 0；手动重开 App 后立即恢复 `sourceOwner=harness-app`。素材未丢，但这会把正常更新变成人工重启流程。

**代价**：服务安装最多等待约 10 秒，App 只在已配置共享 LaunchAgent 时短暂重试；没有共享服务的独立安装仍直接走 standalone，不增加日常启动等待。

**结论**：Kimi 的人物背景只能留在最底层，信息表层不得用 `transparent` 冒充皮肤效果。主画布至少使用独立可读遮罩，侧栏与编辑器使用更高不透明度，模型菜单、工作区选择器和添加工作区对话框必须接近实体表面；浅色、暗色及 macOS“降低透明度”三种路径必须同步维护。

**为什么**：旧 `harness.css` 把 `.app-shell`、侧栏和主要 surface 设为 0%–30% 不透明度，文字直接叠在高亮人物图上；工作区和模型弹层又被旧的 light/dark 高优先级规则压回 84%–86%，导致同一功能随背景与色彩模式随机失去可读性。只改一个弹窗或只验浅色会留下夜间回归。

**代价**：皮肤仍可辨认，但信息层优先保证阅读；每次调整主题变量都要同时验证主界面、模型菜单、工作区选择器、添加工作区对话框和暗色覆盖，并保留无重启 `insertCSS` 作为活动 Kimi 的临时恢复手段，正式修复仍须进入同上游版本安装包。

**结论**：DSH 的共享皮肤入口必须由 Harness 插件通过官方 `desktopRuntime.registerTrayItem` 注册，再由受控运行时补丁提升为独立 macOS“皮肤”菜单；菜单项直接读取 `~/.harness-ui/catalog.json/state.json` 并调用 3099 原子接口，不能让 renderer 按钮、原生菜单和 Kimi 各自保存状态。

**为什么**：仅在窗口右下角注入“皮肤”按钮不属于普通桌面软件菜单，且官方 runtime 原先只允许一层 tray submenu，无法表达与 Kimi 一致的游戏/角色/变体目录。补丁必须递归保留多级菜单、checkbox 与禁用状态，同时把 harness 分组从 App 菜单正文提升到顶层；状态文件变化只刷新菜单，不复制素材或凭据。

**代价**：DSH 上游 runtime 的菜单模板或命令转换器变化时安装必须 fail-closed；浅色主题原生 `label-dimmed=#e1e5ee` 在人物背景上几乎不可见，因此桥接 CSS 要同时覆盖 light/dark 的 caption、dimmed、secondary、tertiary、placeholder 与实体输入表层，并保留“降低透明度”路径。

**结论**：桌面壳可见版本必须跟随上游时，同一版本内覆盖 Release 资产还需要独立的内部发行修订协议；更新按钮先比较官方版本，再比较包内修订与 Release 清单，不能把 `0.38.0 == 0.38.0` 直接判成无需更新。

**为什么**：Kimi 的皮肤可见性修复必须继续发布为官方 `0.38.0`，旧更新器只做 SemVer 比较，导致正式资产已经覆盖而用户仍看到“当前没有可用更新”。workflow 在包和同 tag 清单中写入同一 GitHub run 修订后，新安装不重复提示，旧安装可发现同版本维护更新。

**代价**：每次正式 workflow 多发布一个很小的 JSON 清单，安装回执多记录一个内部修订；可见版本、内置 CLI、tag、账号、会话、配置、皮肤、素材和图标边界全部保持不变，换来同版本修复也能通过普通更新按钮完成。
