# eei-api 部署（公开数据接口，读 eei-db，不碰 Cloudflare）

`eei.linzezhang.com/v1/*` 的上游。入口 `apps.api.app.public_main:app`（公开只读面，不含写入实现）；完整本地 API（`apps/api/app/main.py`）不在这里部署。

- 只读：用 `eei_reader` 角色连库（`readonly_role.sql`），启动与每次建连都校验该角色对任何表没有写权限，否则 `/health` 回 503、拒绝服务。
- 发布门：只输出通过发布门的关系（与 `scripts/relationship_publication_gate.py` 同一套判定）。
- 写入 / 个人状态类路由（saved-views、watchlists、calibrations、scoring 写、snapshots、internal…）一律 403；`EEI_WRITE_ROUTE_MODE=hidden` 改成 404。
- 不对公网暴露端口：容器在 eei-db 所在网络启动，健康后接入宇宙容器所在网络，别名 `eei-api`，只有宇宙的 nginx 访问它。

## 文件

| 文件 | 作用 |
|---|---|
| `Dockerfile` | python:3.12-slim，`uv sync --frozen`，非 root（10001），只读根文件系统可跑 |
| `readonly_role.sql` | 幂等创建 `eei_reader`（只授 SELECT，白名单表） |
| `indexes.sql` | 幂等补 4 个排序索引 |
| `eei-api.env`、`eei-api-pull-deploy.sh`、`eei-api-pull.{service,timer}`、`install.sh` | 拉取式部署（10 分钟一轮，指纹没变就什么都不做） |
| `bench_explore.py` | 压测：造 15 万关系的一次性库，量 explore 延迟 |

## 首次上线（服务器上，root）

```bash
# 1) 只读角色 + 索引（幂等）
docker exec -i eei-db psql -U eei -d eei -v ON_ERROR_STOP=1 < EEI/apps/api/deploy/readonly_role.sql
docker exec -i eei-db psql -U eei -d eei -v ON_ERROR_STOP=1 < EEI/apps/api/deploy/indexes.sql
PW=$(openssl rand -hex 24)
docker exec -i eei-db psql -U eei -d eei -c "ALTER ROLE eei_reader PASSWORD '$PW'"
install -d -m 700 /etc/eei-api
printf 'DATABASE_URL=postgresql://eei_reader:%s@eei-db:5432/eei\n' "$PW" > /etc/eei-api/eei-api.secret.env
chmod 600 /etc/eei-api/eei-api.secret.env

# 2) 装拉取式部署并首次部署
bash EEI/apps/api/deploy/install.sh
/usr/local/bin/eei-api-pull-deploy.sh run eei-api --force
/usr/local/bin/eei-api-pull-deploy.sh status eei-api
```

## 切换与回滚（宇宙容器）

- 切换：宇宙的 `RUN_EXTRA_ARGS`（`/etc/linze-pull-deploy/eei-universe.env`）追加 `-e EEI_UPSTREAM=http://eei-api:8000 -e EEI_RESOLVER=127.0.0.11`，重跑 `install.sh`，再 `eei-pull-deploy.sh run eei-universe --force`。
  必须带 `EEI_RESOLVER=127.0.0.11`：容器接入自定义网络后，默认的 `1.1.1.1 8.8.8.8` 解析不了 `eei-api`。
- 回滚：去掉那两个 `-e`，重跑 `install.sh` 与 `run eei-universe --force`，即回到 Workers 上游。
