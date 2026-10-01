# Social Archive v0.0.0.109

免费、私有、跨平台的收藏、点赞与网页归档系统：把你在各平台（B站、抖音、小红书、Reddit、Instagram、Chrome 书签）收藏的内容，聚到一个自己的资料库里，一键保存、可搜索、多处备份。规格见 [SPEC.md](SPEC.md)；接手或运维先读 [HANDOFF.md](HANDOFF.md)；日常使用见 [docs/使用说明.md](docs/使用说明.md)。

## 线上地址与是否真在跑

- 资料库：`https://social-archive-api.linzezhang.com/`（VPS-3 上的 Docker 容器，经 Cloudflare Tunnel 对外；`deploy/cloudflare/tunnel-config.example.yml`）。2026-09-30 实测 `curl -sI` 返回 405（该路径只接受 GET），GET 返回 200。
- 健康检查：`curl -s https://social-archive-api.linzezhang.com/health`，看 `version`、`worker.alive`、`backup.stale`、`replication.stale`（后两个要是 `false`）。2026-09-30 实测 200，`version` 为 0.0.0.109，`worker.alive` 为 true，两个 `stale` 均为 false。
- 数据最迟多久该更新一次：对象复制与运行库快照每 **15 分钟**，私有库事实同步每 **10 分钟**，状态投影每 **5 分钟**，完整备份每天一次（服务器本地时间 03:20）；`/health` 在复制超过 **2 小时**、备份超过 **30 小时**没新的就报 `stale`（`src/social_archive/api.py`、`deploy/systemd/*.timer`）。

## 数据放哪

- 运行库：服务器 `/var/lib/social-archive/runtime/`（SQLite）。
- 制品与备份：Cloudflare R2 与 GitHub Release 两份密文（`SOCIAL_ARCHIVE_REPLICA_STORES=r2,github`，OCI 已于 2026-09-30 退役）。
- 结构化事实：私有仓 `Private-Database` 的 `Private-MetaDatabase`（`domain=SocialArchive`）。本仓只放代码，路牌见仓根 `WHERE_IS_PROJECT_DATA.md`。

## 怎么部署 / 回滚

- 部署：在开发机上 `bash scripts/deploy_to_production.sh`（rsync 源码、重建镜像、重建容器、逐道门检查并从公开域名回读）。不要用 `systemctl restart` 代替，它不会重建镜像。需要 SSH，由主线执行。
- 回滚：先确认回滚点还在 `docker image inspect social-archive/core:rollback`，再按 `docs/06_运维手册.md`回滚一节那一行命令执行；没有回滚点时看同一节末尾。

## 需登录 / 需凭据而停掉的功能

- B站、抖音、小红书自动同步：需要 Owner 在浏览器里授权连接账号（最后一下必须真实用户手势，Cookie 不出浏览器），目前三者均为断开，已停（`HANDOFF.md` 第四节）。
- 服务器上不得有国内平台的 Cookie；部署第 0.9 步专门查这件事。

## 本地测试

```bash
cd social-archive
python3.12 -m venv /tmp/venv-sa && /tmp/venv-sa/bin/pip install -e ".[test]"
python -m pytest -q tests                # 需要 Python 3.12
```

2026-09-30 沙箱实测：2151 passed，18 failed，8 skipped（18 项失败在没有改动时就存在，见 SPEC 的已知坑一节）。规则见 `AGENTS.md`；旧版 README、PURSUING_GOAL 在 [文档/归档/](文档/归档/)。
