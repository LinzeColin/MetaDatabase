# EEI 自托管数据接口 · 交接（本机停手，云端接手）

分支：`cloud/eei-selfhost-api-261001`（基于 main `2b754a61c`）。目标见任务书 A：让 `EEI/apps/api` 成为 `eei.linzezhang.com/v1/*` 的新上游，直接读 VPS 上的 Postgres `eei-db`，行为与 Worker（`apps/cloudflare-public/src/worker.mjs`）一致，运行时零 Cloudflare 依赖。PR：#392（Draft，未合并）。

## 设计（已定，照这个做完）

新开一个公开数据面入口，**不改** `main.py` / `domain.py` / `settings.py`（它们在 `CHECKSUMS.sha256`、`validate_v5_production_readiness_sync` 的清单里，动了要重生成清单）。本地完整版 API（带写入、给 Next 前端用）原样保留。

| 文件 | 作用 |
|---|---|
| `apps/api/app/public_main.py` | 容器入口 `uvicorn apps.api.app.public_main:app` |
| `apps/api/app/public/app.py` | 应用工厂；不挂 /docs；CORS `*`；no-store；500 只回 request_id；DB 不可用回 503 |
| `apps/api/app/public/settings.py` | 全部环境变量（`EEI_WRITE_ROUTE_MODE=forbidden\|hidden` 即「写入路由 403/404」开关；公开入口里根本没有写入实现） |
| `apps/api/app/public/db.py` | 只读连接池：会话 `default_transaction_read_only=on`、事务 READ ONLY、语句超时、建连时校验角色对任何 public 表无写权限（否则拒绝服务，`EEI_REQUIRE_READ_ONLY_ROLE=0` 仅供本地调试） |
| `apps/api/app/public/gate.py` | **发布门读端**：复用 `scripts/publish_to_cloud_channel.py` 的 `GATED_RELATIONSHIPS_SQL` + `gate_relationship`（即 `relationship_publication_gate.py` 的判定，不写第二份）；SQL 里只加「至少一条 supports 证据带 http(s) 链接」这个必要条件做预筛，过不过门始终由 Python 判定 |
| `apps/api/app/public/graph.py` | explore / expand / reroot，算法逐行对应 worker.mjs `exploreGraph`；被拒候选跳过并继续往后翻，预算只数已过门的边 |
| `apps/api/app/public/modules.py` | 实体检索（前缀优先，支持 `limit`）、证据、评分解释、control/ma/signals/policy/supply-chain 概览、changes、empire、scoring profiles |
| `apps/api/app/public/events.py` | events / amount-summary / evidence/event；复用 `amount_semantics.py`；Decimal 转 JSON 数字 |
| `apps/api/app/public/stats.py` | 缓存：`SurfaceStats`（全量过门扫描：已发布数、按天、家族构成，TTL 30 分钟，过期先回旧值后台刷）+ `LightStats`（事件曲线、来源新鲜度、快照、上下文，TTL 2 分钟）；pulse/production_context 形状同 worker |
| `apps/api/app/public/routes.py` | 全部路由；兜底路由：非 GET 或 saved-views/watchlists/exploration-log/cloud/calibrations/internal/audit-logs/data/export/scoring/profiles/* 一律 403（或 hidden 模式 404）；其余未知 `/v1/*` 404 |
| `apps/api/deploy/readonly_role.sql` | 幂等建 `eei_reader`：只授 SELECT，**白名单 14 张表**（个人状态/候选/复核/原文快照不在内），不设默认授权；密码不在 SQL 里 |
| `apps/api/deploy/indexes.sql` | 幂等补 4 个排序索引（changes / 家族概览 / 事件流 / 参与者） |
| `apps/api/deploy/Dockerfile` | python:3.12-slim，`uv sync --frozen --no-dev`，非 root uid 10001，只读根可运行，uvicorn 单进程 `--limit-concurrency 64`，HEALTHCHECK 打 `/health`（**还没 build 验证过**） |
| `apps/api/deploy/bench_explore.py` | 压测脚本：建一次性大库 → 幂律造数 → 量 explore 延迟分布 |
| `tests/integration/test_public_api_db.py` | 24 个测试，**本机全过**（见下） |

两个有意为之的判断：
- **实体可见性比 Worker 更窄**：研究目标，或至少挂着一条「真正过门」的关系（`has_published_edge` 逐条走发布门）。Worker 是「任何已发布规则关系的端点」。
- **pulse 的关系总数 = 过门后的数**（Worker 的 pulse 用的是未过门的规则内关系数，与 `published_relationship_count` 自相矛盾）；心跳用「最新一份原文入库时间」代替采集器心跳（PG 里没有心跳表），`heartbeat.detail.basis` 已注明；需要真心跳得让 eei-watch 写 PG，未做。

## 已完成且验证过

- 24 个集成测试通过（本机 Postgres 16，见下「跑测试」）。测试覆盖：explore（hops 1/2、预算截断、方向、expand/reroot、焦点不在发布面 404）、未过门关系在 explore/evidence/评分解释/变更流/概览/检索/事件中都不出现（8 类被拒情形：非官方单来源、官方无原文链接、无证据、仅 contradicts、来源停用、夹具规则、已取代、复核流水线但单来源）、公共 qualifiers 不带 `owner_actor`、事件与金额汇总、pulse 与 `published_relationship_count` 和发布端同一份判定数出来的一致、**worker.mjs 每条字面路由要么被服务要么被明确关掉**（自动从 worker.mjs 抽取路由，新增路由不分类会失败）、explore 响应字段集与 Worker 一致、`eei_reader` 只能 SELECT 白名单表、两份 SQL 幂等、属主角色连池也写不了、带写权限的角色启动即 503。
- 变异验证：把发布门判定绕过后 7 个测试变红，还原后 24 全绿（测试不是摆设）。
- `ruff check apps/api/app/public` 通过。
- 已实测：容器里 `docker network connect` 用户自定义网络后，原本在默认 bridge 上的容器 `resolv.conf` 会切到 `127.0.0.11`，容器名可解析——所以宇宙容器切换时必须 `-e EEI_RESOLVER=127.0.0.11`（现默认 `1.1.1.1 8.8.8.8` 解析不了 `eei-api`）。

## 状态（云端接手后，2026-09-30）

已完成并有外部证据（细节见 PR #392）：
- 集成测试 24 passed（本机 Postgres 16，apt 装的）；无库单元测试 `tests/unit/test_public_api_surface.py` 39 passed。
- ruff 全绿（`make lint` 的范围）。
- 压测：15 万关系、枢纽度数 1644 的库上，hops=2、max_nodes=160：进程内 hub p95 382ms / 随机目标 p95 144ms；真 uvicorn 回环 hub p95 366ms；真容器（`--memory 256m --cpus 0.5 --read-only --user 10001`）200 次 hub explore p95 369ms、内存峰值约 70MiB、未 OOM。
- 镜像 build 通过（355MB）；容器非 root、只读根、`/health` 通、连 `eei_reader`。
- 拉取式部署脚本在 Linux 上对真实 GitHub 分支实跑：首次部署、幂等（已是最新）、`--force` 切换（旧容器停）、DB 账号可写时候选被拒且旧容器保持，均按预期。
- 链路：真 nginx（`eei-universe` 镜像，`EEI_UPSTREAM=http://eei-api:8000 EEI_RESOLVER=127.0.0.11`）→ eei-api → 库，`/v1/meta/pulse|catalogs|scoring/profiles|entities|changes|publication/meta|sources/freshness|events|meta/build|explore` 200，`/v1/saved-views` 403。

没做 / 仍需主线处理：
1. `make verify` 里 `validate-clean-room-release` 与 `validate-release-artifacts` 会红：新增文件不在 `manifest.txt` / 清洁室清单里。按任务要求不手改也不重生成（与 #388 冲突）。#388 合并后在合并树上跑 `make generate-clean-room-release && make generate-release-artifacts` 并提交。因 `make verify` 在此处即停，CI 的 PG 集成步骤被跳过（本机已跑过）。
2. 沙箱 TLS 被代理中间人，本机 `docker build` 的 pip 步骤要临时注入 CA 才能过；Dockerfile 本身未改，服务器上不受影响。
3. eei-refresh 的发布环节（`EEI_PUBLISH_URL=https://eei.linzezhang.com/v1/internal/publish/exec`）切换后会打到 eei-api 的 403，无害（D1 本来就不再需要）；是否清掉 compose 里那两个变量由主线定。
4. pulse 的心跳仍是「最新一份原文入库时间」的代用，未让 eei-watch 写 PG。
5. 未在真实 eei-db（带真实数据）上测过 explore 延迟，数据规模是按幂律造的。

## 跑测试的命令

```bash
# 本机没有 Postgres：起一个一次性的（端口 55432，名字自取；用完 docker rm -f）
docker run -d --name eei-api-test-pg -e POSTGRES_DB=eei -e POSTGRES_USER=eei \
  -e POSTGRES_PASSWORD=change-me-local-only -p 127.0.0.1:55432:5432 postgres:16
cd EEI && uv sync --extra dev --python 3.12
export DATABASE_URL=postgresql://eei:change-me-local-only@127.0.0.1:55432/eei
.venv/bin/python scripts/migrate.py upgrade && .venv/bin/python scripts/load_seed_catalogs.py
.venv/bin/pytest tests/integration/test_public_api_db.py -q        # 24 passed
.venv/bin/ruff check apps tests                                      # 看 E501
# 压测（会自建/自删 eei_bench 库；admin-dsn 要能 CREATE DATABASE）
.venv/bin/python apps/api/deploy/bench_explore.py \
  --admin-dsn postgresql://eei:change-me-local-only@127.0.0.1:55432/postgres \
  --entities 20000 --relationships 150000 --requests 100
```

CI（`.github/workflows/eei-validation.yml`）：`make verify` 跑两遍（第二遍 DB 已起），`make test-integration` 跑 `tests/integration`；集成测试靠 `DATABASE_URL`/`.env` 存在才不跳过；迁移测试会把库留在「已降级」状态，所以我的测试模块有 `provisioned_database` 夹具（没表就升级+灌目录，用完还原）。

## 踩过的坑

- **ruff E501 把中文字符按 2 宽度算**：注释、docstring 里中文一长就超 100，要主动断行。
- psycopg3：带参数执行只能一条语句；SQL 里有 `%`（取模、LIKE）时必须转义 `%%` 或改成无参数执行；`INSERT` 不能放在子查询里（要 CTE 或先建临时表）。`CREATE TEMP TABLE ... AS SELECT` 可以。
- psycopg 的 `str` 参数按 unknown 类型绑定，`uuid = %s` 可直接比；但数组要写 `= ANY(%s::uuid[])`。
- 发布端 `GATED_RELATIONSHIPS_SQL` 用 `%(name)s` 命名参数，`fetch_page` 已按此拼接（`rules` 必带）；连接行工厂必须是默认的 tuple（`gate_relationship` 按位置取列），要 dict 行的地方单独开 `dict_row` 游标（`modules.scoring_profiles`）。
- PG 的 `ILIKE` 默认转义字符就是反斜杠，`escape_like` 已处理；`pg_trgm` 的 GIN 索引已在迁移里，检索不用新索引。
- 命名游标（全量过门扫描）要在事务里；池里连接是非 autocommit，刚好；扫描里 `SET LOCAL statement_timeout='120s'` 覆盖池默认的 8s。
- 公开面要 403 的不只是写：`saved_views` 等个人状态就在同一个 PG 里，GET 也必须关，否则会泄露（兜底路由已按前缀处理）。
- 改 `main.py`/`domain.py`/`settings.py` 会碰 `CHECKSUMS.sha256` 里的哈希（目前与文件一致），所以走独立入口。
- 本机 macOS 无 `flock`、`sha256sum`、GNU `date -d`，拉取式部署脚本只能在 Linux 容器里验。
- 宇宙 nginx 的 `proxy_ssl_*` 指令对 http 上游无效但无害；`Host` 头会变成 `eei-api:8000`，FastAPI 没开 TrustedHost，不受影响。

## 收尾状态（本机）

本机在提交后清理了自己起的测试 Postgres 容器（`eei-api-test-pg`）、`postgres:16` 与 `alpine` 镜像、一次性库 `eei_bench`、EEI 下的 `.venv`；重新开工从「跑测试的命令」起步即可。
