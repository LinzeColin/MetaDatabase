# HANDOFF

更新：2026-09-30（线上数据均为当日 curl 实测，UTC 20:00 前后）。旧版交接（2026-07 时代）在 `文档/归档/HANDOFF_旧版.md`、`文档/归档/HANDOFF_EEI.md`，其中本机 docker 监测等内容已过时。

## 现在是什么状态

| 事实 | 出处 | 核实 |
|---|---|---|
| 主站 https://eei.linzezhang.com 在服务器 VPS-3 上，2026-09-30 由 Owner 批准从 Cloudflare Worker 切来；DNS 是 Cloudflare 里指向 VPS-3 的 A 记录，Traefik 自动签证书 | `apps/universe/deploy/README.md`「主站现状与回滚」 | 首页 200 |
| 线上页面版本 `c7aabdff…`（= 仓库里 #386 那次提交，EEI 目录最新一次改动） | `curl …/version.txt`、`git log -- EEI` | 已核实 |
| 代码更新靠服务器每 10 分钟从 GitHub `main` 拉取，仅 `EEI/apps/universe/` 变化才重建，健康检查过才切流量 | `apps/universe/deploy/README.md` | 部署器状态需登录服务器，未核实 |
| 数据接口路径：浏览器 → nginx 容器 → `/v1/*` 反代（读请求缓存 60 分钟，上游 5xx 时回旧结果）→ Cloudflare Worker `codex-eei`（workers.dev）→ D1 `eei-publication` | `apps/universe/deploy/site.conf.template`、`apps/cloudflare-public/wrangler.jsonc` | 缓存命中已核实（`x-eei-cache: HIT`） |
| 采集：容器 `eei-refresh`（每小时一轮）、`eei-watch`（每分钟看 SEC 最新申报）写 Postgres `eei-db`，再增量发布到 D1 | `docker-compose.ovh.yml`、`infra/ovh/RUNBOOK_OVH_EEI.md` | 容器是否在跑：未核实（无服务器权限）；间接证据：`/v1/meta/pulse` 显示最近发布 2026-09-30 18:56 UTC，当日新增事件 159 |
| 当前数据量：实体 14,819 / 关系 20,364 / 事件 990,050 | `curl …/v1/meta/pulse`（缓存结果，生成于 19:52 UTC） | 已核实 |
| 长期权威事实在私有仓 `Private-Database` 的 `Private-MetaDatabase/`（domain `EEI`）；`eei-db` 与 D1 都是可重建副本；同步命令 `python -m scripts.sync_facts_to_private_db --reason daily` | `文档/归档/WHERE_IS_THE_DATA.md`、`scripts/sync_facts_to_private_db.py` | 私有仓内容未核实 |
| Cloudflare D1 只是发布副本，Owner 计划淘汰 | 任务书（2026-09-30）；仓内没有淘汰方案文档 | 淘汰步骤未核实 |
| 产品版本 0.1.0（2026-07-16 发布，之后进入上线后监测） | `VERSION`、`docs/pursuing_goal/CURRENT.yaml` | 文件记载 |

## 已知问题

1. **D1 读额度耗尽，数据接口大面积 500。** 2026-09-30 D1 免费额度（每天 500 万行读取，全账户共用，ADP 同受影响）被读光，预计到 UTC 零点恢复（出处：提交 #386 说明；恢复时间未核实）。
   实测（UTC 20:00）：`/health`、`/v1/events`、`/v1/meta/build`、`/v1/policy/overview`、`/v1/cloud/runs` 返回 500，直连 Worker 也一样；`/v1/meta/pulse` 靠 nginx 缓存还能返回旧结果。`/health` 不走缓存。20:17 UTC 复测：`/health` 已回 200，其余四个仍 500，说明不是一刀切，恢复时间以实测为准。
2. **搜索返回空。** `/v1/entities?q=nvidia` 返回 200 但 `entities: []`（主站与直连 Worker 一致），原因未核实，可能与问题 1 有关。
3. **`apps/cloudflare-public/wrangler.jsonc` 仍声明 `routes: eei.linzezhang.com`（custom_domain）。** 而域名已切到 VPS-3、Worker 已解绑。从该目录 `wrangler deploy`（含 `scripts/deploy_cloud.sh`）很可能把主域名抢回 Worker。是推断，未试验。
4. 伯克希尔等大公司：一跳超过 60 节点或两跳，上游返回 500（已在宇宙页规避为一跳 60 节点起请求），出处：提交 #384。
5. **`文档/` 七份渲染文档是陈旧的：** `machine/facts/status.json` 渲染于 2026-07-15，`00_我在哪` 写「S7 已发布」，`01/04/05` 是空壳。账本 `docs/governance/development_events.jsonl` 最后一条是 2026-07-23，之后的 VPS-3 迁移、宇宙页、缓存均未入账。
6. 旧交接里「2026-07-23 双 7 天监测窗收口并发 Owner 最终稳定性报告」：是否完成，未核实（账本无记录）。
7. 旧交接记载「M&A、战略信号、供应链的关系边未建，实体侧栏未接 GLEIF 子公司关系」（2026-07-23）：现状未核实。

## 下一步

1. 等 D1 额度恢复（预计 UTC 零点）后复测问题 1、2。
2. 落实 D1 淘汰：接口改读 `eei-db` 或其它非 Cloudflare 来源。仓内无方案，需先定方案（Owner 要求：零花钱、不新增 Cloudflare 依赖）。
3. 处理问题 3（改 `wrangler.jsonc` 的 routes 或在文档里封死 deploy 路径）——属 `apps/` 代码，本次瘦身任务没动。
4. 把 `machine/facts/` 补全后重新渲染 `文档/`（`python3 machine/tools/render_human.py --root .`），并把 2026-08 以来的变更补进账本。

## 坑

- 集成/E2E 套件不能并发多实例（worker 抢队列、端口冲突）。出处：`文档/归档/HANDOFF_旧版.md`。
- `make verify` 是 40 个顺序目标，前面红了后面全不跑；报「修好了」前要跑完并看退出码。出处：`dev-notes/经验-202608.md`（仓根）。
- `docker-compose.ovh.yml` 的容器带硬内存上限、`oom_score_adj: 500`，与 Alpha 共用一台机器；资源红线见 `AGENTS.md`。
- 改 `apps/universe/deploy/` 后，服务器要重跑 `install.sh`，再 `eei-pull-deploy.sh run eei-universe --force`（部署器不会自我更新）。出处：同目录 README。

## 手动跑采集（排查用；需 `.env` 里有 `SEC_USER_AGENT`）

出处：`文档/归档/HANDOFF_EEI.md` §2.5，命令对应 `scripts/authoritative/` 下同名文件（均幂等）。

```bash
python -m scripts.authoritative.collect_universe            # SEC 公司登记表 → 实体
python -m scripts.authoritative.enrich_sec --limit N        # 每份重要申报 → 事件 + SIC 行业
python -m scripts.authoritative.collect_gleif --limit N     # GLEIF 母子/控股关系
python -m scripts.authoritative.refresh_cycle               # 以上合成一轮；--loop 供容器常驻
```

另：远端 D1 拒绝 6 张以上表的复合 SELECT（SQLITE_ERROR 7500），要逐表查。

## 接手第一步

```bash
curl -s https://eei.linzezhang.com/version.txt       # 线上是哪一版
curl -s https://eei.linzezhang.com/v1/meta/pulse      # 数据量与最近发布时间
sed -n 1,60p apps/universe/deploy/README.md           # 怎么部署、怎么回滚
ls 文档/归档                                           # 旧文档去向，README.md 有索引表
sed -n 1,30p docs/pursuing_goal/CURRENT.yaml          # 旧交接指定的第一份必读（2026-07-16 时点）
```
