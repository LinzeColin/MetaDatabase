# 商域宇宙 · 部署件

服务器（VPS-3）自己每 10 分钟去公开仓看一眼 `main`；`EEI/apps/universe/` 的内容有变化才构建、起新容器、健康检查通过再切流量，失败保留旧版。
不需要 GitHub 往服务器推、不需要任何令牌。派生自 LinzeHomeHub `deploy/pull/`，扩展点写在 `eei-pull-deploy.sh` 头部。

| 文件 | 作用 |
|---|---|
| `Dockerfile` | nginx:1.27-alpine，非 root（uid 101）监听 8080；只读根文件系统运行 |
| `nginx.conf` / `site.conf.template` / `headers.conf` | 静态服务、gzip、缓存、安全头、反代上游（`EEI_UPSTREAM`） |
| `eei-universe.env` | 拉取式部署配置（分支、域名、内存 64m、只读、额外域名） |
| `eei-pull-deploy.sh`、`eei-universe-pull.{service,timer}`、`install.sh` | 服务器上的部署器与定时器 |

## 装 / 更新（服务器上，root）

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/LinzeColin/MetaDatabase.git /tmp/mdb \
  && git -C /tmp/mdb sparse-checkout set EEI/apps/universe/deploy \
  && sudo bash /tmp/mdb/EEI/apps/universe/deploy/install.sh
```

`install.sh --check` 比对服务器与仓库是否一致。部署器不会自我更新；改了本目录后在服务器重跑 `install.sh`，状态里的 `script_drift` 会提醒。

## 怎么看它活着

| 想知道 | 命令 |
|---|---|
| 线上是哪一版 | `curl https://eei-preview.linzezhang.com/version.txt` |
| 部署器状态 | `sudo /usr/local/bin/eei-pull-deploy.sh status eei-universe` |
| 日志 | `journalctl -u eei-universe-pull.service` |
| 下次什么时候跑 | `systemctl list-timers eei-universe-pull.timer` |

## 路径去向

| 请求 | 去向 |
|---|---|
| `/`（无参数）、`/app.js`、`/styles.css`、`/vendor/*`、`/version.txt` | 本容器静态文件 |
| `/v1/*`、`/health`、`/_next/*`、`/?subject=…` | 反代到 `EEI_UPSTREAM`（Host 头与 SNI 用上游主机名，校验上游证书） |

`EEI_UPSTREAM` 默认 `https://codex-eei.linzezhang35.workers.dev`（Cloudflare Workers 上的旧程序）。换上游：在 `eei-universe.env` 的 `RUN_EXTRA_ARGS` 里加 `-e EEI_UPSTREAM=https://…`，重跑 `install.sh` 后 `eei-pull-deploy.sh run eei-universe --force`。

## 切主站 eei.linzezhang.com（预留）

容器的 Traefik 路由已同时接受 `Host(eei.linzezhang.com)`，但默认**不**为它申请证书（域名指向本机之前 Let's Encrypt 验证必失败）。
1. Cloudflare 后台解绑旧程序上的 `eei.linzezhang.com`；用服务器 `/etc/linze/cf-dns.env` 建 A 记录 → 服务器 IP、proxied。
2. 服务器：把 `/etc/linze-pull-deploy/eei-universe.env` 里 `EXTRA_DOMAINS_CERT=no` 改 `yes`，运行 `sudo /usr/local/bin/eei-pull-deploy.sh run eei-universe --force`（蓝绿切换，先健康检查）。证书由 Traefik 的 letsencrypt（HTTP-01）自动签。
3. 切换后：`/` 是宇宙页面；`/?subject=…` 反代到旧程序的完整图谱；`/v1/*`、`/health`、`/_next/*` 反代到旧程序。
