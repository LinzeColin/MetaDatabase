# EEI 自托管数据接口 · 交接（本机停手，云端接手）

分支：`cloud/eei-selfhost-api-261001`（基于 main `2b754a61c`）。目标见任务书 A：让 `EEI/apps/api` 成为 `eei.linzezhang.com/v1/*` 的新上游，直接读 VPS 上的 Postgres `eei-db`，行为与 Worker（`apps/cloudflare-public/src/worker.mjs`）一致，运行时零 Cloudflare 依赖。**未开 PR、未合并。**

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

## 没完成（按优先级）

1. **拉取式部署件**（任务书第 5 条，整块没做）：`apps/api/deploy/` 下需要 `eei-api.env`、`eei-api-pull-deploy.sh`、`install.sh`、`eei-api-pull.service`、`eei-api-pull.timer`、`README.md`。做法：从 `apps/universe/deploy/` 派生，但去掉 Traefik/域名/TLS 回测——eei-api 不对公网，只在 docker 网络里被宇宙容器访问。要点：
   - 候选容器放进 **eei-db 所在网络**（`STAGING_NETWORK=<eei-db 网络>`，服务器上 `docker inspect eei-db -f '{{json .NetworkSettings.Networks}}'` 取名），健康检查通过后 `docker network connect --alias eei-api coolify <候选>`（宇宙容器在 `coolify` 网络），再停旧容器；回测用 `docker exec <宇宙容器> wget -qO- http://eei-api:8000/health`。
   - 变化检测：`SPARSE_PATHS="EEI/apps/api EEI/scripts EEI/data"`，`TREE_PATHS="EEI/apps/api EEI/scripts/relationship_publication_gate.py EEI/scripts/publish_to_cloud_channel.py EEI/scripts/db_tools.py EEI/data EEI/pyproject.toml EEI/uv.lock"`，对它们各取 `git rev-parse HEAD:<path>` 合并哈希当 tree；构建上下文 `EEI/`，`DOCKERFILE=apps/api/deploy/Dockerfile`（Dockerfile 要 `pyproject.toml`/`uv.lock`，它们在 EEI 根）。
   - 独立命名不撞宇宙的：`/usr/local/bin/eei-api-pull-deploy.sh`、`/etc/linze-pull-deploy/eei-api.env`、`eei-api-pull.{service,timer}`、状态目录 `/var/lib/linze-pull-deploy/eei-api`、`IMAGE=linze-pull/eei-api`。
   - `RUN_EXTRA_ARGS` 建议：`--read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --user 10001 --memory-swap 256m --cpus 0.5 --env-file /etc/eei-api/eei-api.secret.env`（`DATABASE_URL=postgresql://eei_reader:<密码>@eei-db:5432/eei` 只放服务器这个 600 文件里，不进仓库），`MEMORY=256m`，`HEALTH_PATH=/health`，`--health-cmd` 用 `python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=3)"`（slim 镜像没有 wget/curl）。
   - 本机没法直接跑该脚本（macOS 无 `flock`/`sha256sum`/GNU `date -d`）；验证办法：在 `docker:cli` 之类镜像里装 bash/git/curl/util-linux/coreutils，挂 docker.sock，对推到 GitHub 的分支跑 `run eei-api --branch cloud/eei-selfhost-api-261001`。
2. **压测数字**：`bench_explore.py` 已写、数据生成 SQL 已跑通（15 万关系 25 秒造完），但最后一次因 `ModuleNotFoundError: apps` 中断（已在 commit 里补了 `sys.path.insert`），**还没拿到 p50/p95/p99**。要在 15 万关系、枢纽度数几千的库上证明 hops=2、max_nodes=160 时 p95 < 1.5s；加 `--http` 再测一遍真 uvicorn；最好再用 `docker run --memory 256m` 的真容器测一遍并记内存峰值（`docker stats`）。如果 p95 不达标，先看枢纽节点一跳内被拒候选翻页次数（`fetch_published` 的 `page`/`scan_cap`）与 `ENTITY_VISIBLE_SQL` 的 EXISTS 成本，再看是否需要给 `relationships(derivation_rule, ...)` 加索引。
3. **DB 无关的单元测试**（`make verify` 的第一轮在没库时只跑 `tests/unit`）：未写。建议 `tests/unit/test_public_api_surface.py`：写入路由 403/hidden 模式 404、未知路由 404、`/docs`、`/openapi.json` 404、`/health` 无库时 503、CORS/no-store 头、`PublicSettings` 解析；另加一个测试断言 Dockerfile 用 `--frozen`（依赖版本以 uv.lock 为准）。用 `TestClient(create_public_app(PublicSettings(database_url=None), warm_up=False))`。
4. **lint**：`tests/integration/test_public_api_db.py` 还有 6 处 E501（ruff 把中文按 2 宽度算，行要更短）。`ruff check apps tests` 是 `make lint` 的一部分，CI 会拦。
5. **`make verify` 整套没跑**（含 `validate-release-artifacts`、`validate-clean-room-release`、`secret-scan`、`copy-lint`、`validate-governance*`）。新增文件可能被其中某个清单/扫描卡住，本机没验证。Dockerfile/脚本里不要出现看起来像密钥的字符串（测试里用了 `READER_PASSWORD = "reader-test-only"`，若 `secret-scan` 报警就改成运行时 `secrets.token_hex` 生成）。
6. **Docker 镜像 build 与容器实跑**：没 build 过。要验证：非 root、`--read-only` 下起得来、`--memory 256m` 不 OOM、`/health` 通、连 `eei_reader`。
7. **PR 描述**：未写。需含任务书要求的：改了什么、测试命令与结果、没做到的、主线在服务器上的逐条部署步骤（见下）、回滚步骤。

## 主线部署步骤（草稿，供写进 PR；部署件做完后再定稿）

1. 服务器：`docker exec -i eei-db psql -U eei -d eei -v ON_ERROR_STOP=1 < EEI/apps/api/deploy/readonly_role.sql`，再 `... < EEI/apps/api/deploy/indexes.sql`；设密码：`docker exec -i eei-db psql -U eei -d eei -c "ALTER ROLE eei_reader PASSWORD '<生成的随机串>'"`，写进 `/etc/eei-api/eei-api.secret.env`（`chmod 600`，内容 `DATABASE_URL=postgresql://eei_reader:<串>@eei-db:5432/eei`）。
2. 装 eei-api 拉取式部署（部署件待写）；首次 `run eei-api --force`，`journalctl` 看健康检查通过。
3. 切换：宇宙容器的 `eei-universe.env` 里 `RUN_EXTRA_ARGS` 追加 `-e EEI_UPSTREAM=http://eei-api:8000 -e EEI_RESOLVER=127.0.0.11`，服务器重跑宇宙的 `install.sh`，再 `eei-pull-deploy.sh run eei-universe --force`（新容器缓存为空，旧 Worker 的 404/500 缓存一并清掉）。
4. 验：`curl https://eei.linzezhang.com/v1/meta/pulse`、`POST /v1/explore`、`/v1/catalogs`、`/v1/scoring/profiles` 不再 404；`/v1/saved-views` 回 403。
5. 回滚：宇宙的 `eei-universe.env` 去掉那两个 `-e`，重跑 install + `run --force` 即回到 Worker 上游（Worker 只要没被删就还在）；eei-api 容器可留着不接流量，或 `systemctl disable --now eei-api-pull.timer && docker stop <容器>`。
6. 已知提示：宇宙 nginx 对 `/v1/*` 有 60 分钟缓存（老行为），所以脉搏数字最多晚 1 小时；这不是 eei-api 的问题。

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
