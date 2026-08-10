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
