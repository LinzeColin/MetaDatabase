# 商域图谱 EEI（Enterprise Ecosystem Intelligence）

用 SEC、GLEIF 等官方公开数据，把美国上市公司的子公司、董事、股东和申报事件画成可点击的关系图（「商域宇宙」）。
不登录、不买商业数据；评分只用于研究排序，不是投资建议。出处：`文档/归档/AGENTS_旧版.md`（产品定位）、`.ramify/KERNEL.md`（范围外）。

## 线上

| 看什么 | 地址 | 2026-09-30 实测 |
|---|---|---|
| 商域宇宙（主站） | https://eei.linzezhang.com/ | 200，标题「商域宇宙 · EEI」 |
| 线上是哪一版 | https://eei.linzezhang.com/version.txt | 返回一个 git commit（页面来源 `apps/universe/`） |
| 数据总量与增长 | https://eei.linzezhang.com/v1/meta/pulse | 200；实体 14,819 / 关系 20,364 / 事件 990,050 |
| 数据接口健康 | https://eei.linzezhang.com/health | 时好时坏：20:00 UTC 500，20:17 UTC 200；`/v1/events` 等仍 500（疑为 D1 读额度耗尽，见 `HANDOFF.md`） |

主站在服务器 VPS-3 上：静态页面由 nginx 容器直接给，`/v1/*` 等数据接口经 nginx 反代（带缓存）到上游。
出处：`apps/universe/deploy/README.md`、`apps/universe/deploy/site.conf.template`。

## 怎么跑

```bash
make bootstrap
cp .env.example .env
make doctor
make db-up
make migrate-up
make seed-catalogs
make load-fixtures
make check-db-schema
make health
make verify-g2-db
make validate-clean-room-release
make validate-release-artifacts
make db-down
```

以上是本机从干净 checkout 复现的完整顺序（需要 Docker 与 Python 3.12；本机没有 `python` 命令时用 `make bootstrap PYTHON=python3`）。
它只用于开发验证；线上数据不是这样跑出来的。出处：`Makefile`、`docker-compose.yml`、`pyproject.toml`、`dev-notes/经验-202608.md`（仓根）。

- 宇宙页面单独看：它是纯静态页（`apps/universe/`），默认读 `https://eei.linzezhang.com` 的接口，可用 `?api=` 换接口。
- 线上代码更新：服务器每 10 分钟从 GitHub `main` 拉取，`EEI/apps/universe/` 有变化才重建，健康检查过才切流量。
  不需要任何人登录服务器或推送。出处：`apps/universe/deploy/README.md`。
- 线上数据采集：服务器上的容器 `eei-refresh`（每小时一轮补全）与 `eei-watch`（每分钟看 SEC 最新申报）写 Postgres `eei-db`，
  再增量发布到 Cloudflare D1（公开接口的查询副本，计划淘汰）。出处：`docker-compose.ovh.yml`、`infra/ovh/RUNBOOK_OVH_EEI.md`。

## 怎么验证

```bash
make verify                      # 静态校验 + 合同 + lint + typecheck + 单测（CI 同款）
make test-integration            # 需要 make db-up
make test-e2e && make test-e2e-live
```

CI：仓根 `.github/workflows/eei-validation.yml`（`EEI/**` 有改动就跑）与 `.github/workflows/dual-plane.yml`（`文档/` 七份文件必须与 `machine/facts/` 渲染一致）。
改了 `EEI/` 下被 git 跟踪的文件（`apps/universe/` 除外），要重新生成清洁室 ZIP 与校验清单，顺序见 `AGENTS.md`。

## 目录

| 目录 / 文件 | 是什么 |
|---|---|
| `apps/universe/` | 线上主页「商域宇宙」（静态页 + 服务器部署件 `deploy/`） |
| `apps/cloudflare-public/` | 公开接口的 Cloudflare Worker（读 D1） |
| `apps/api/`、`apps/worker/`、`apps/web/` | FastAPI 接口、后台任务、Next.js 前端（本机验证链路用） |
| `scripts/authoritative/` | SEC/GLEIF 采集、刷新、发布（`refresh_cycle`、`watch_recent_filings`） |
| `docker-compose.ovh.yml`、`infra/` | 服务器采集容器（`eei-db`/`eei-refresh`/`eei-watch`）与迁移、部署手册 |
| `data/`、`config/`、`models/` | 目录、模型与参数的机器可读源 |
| `reviews/`、`brand/`、`specs/`、`prototype/` | v5 审查记录、品牌调研、接口与库表规格、离线高保真原型（治理校验会读取） |
| `docs/` | 规格、ADR、治理账本（`docs/governance/development_events.jsonl` 只追加） |
| `文档/` | 七份由 `machine/facts/` 渲染的文档，不要手改；`文档/归档/` 是 2026-10 瘦身时搬走的旧根目录文档，带索引表 |
| `HANDOFF.md` | 现在的真实状态、已知问题、下一步 |
