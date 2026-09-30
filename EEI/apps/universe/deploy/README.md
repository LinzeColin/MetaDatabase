# 商域宇宙 · 部署件

服务器（VPS-3）自己每 10 分钟去公开仓看一眼 `main`；监视路径（`eei-universe.env` 的 `WATCH_PATHS`：宇宙页面、旧版图谱前端源码 `apps/web`、`data`、pnpm 锁文件）有变化才构建、起新容器、健康检查通过再切流量，失败保留旧版。
不需要 GitHub 往服务器推、不需要任何令牌。派生自 LinzeHomeHub `deploy/pull/`，扩展点写在 `eei-pull-deploy.sh` 头部。

| 文件 | 作用 |
|---|---|
| `Dockerfile`、`Dockerfile.dockerignore` | 多阶段：node 阶段把 `apps/web` 静态导出（接口基址 same-origin），nginx:1.27-alpine 阶段只拷产物；非 root（uid 101）监听 8080；只读根文件系统运行。构建上下文是 `EEI/`，白名单见 dockerignore |
| `nginx.conf` / `site.conf.template` / `headers.conf` / `legacy-headers.conf` | 静态服务、gzip、缓存、安全头（旧版图谱另有 CSP 等）、反代上游（`EEI_UPSTREAM`） |
| `eei-universe.env` | 拉取式部署配置（分支、构建上下文与监视路径、正式域名 eei.linzezhang.com、内存 112m、只读） |
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
| 线上是哪一版 | `curl https://eei.linzezhang.com/version.txt` |
| 部署器状态 | `sudo /usr/local/bin/eei-pull-deploy.sh status eei-universe` |
| 日志 | `journalctl -u eei-universe-pull.service` |
| 下次什么时候跑 | `systemctl list-timers eei-universe-pull.timer` |

## 路径去向

| 请求 | 去向 |
|---|---|
| `/`（无参数）、`/app.js`、`/styles.css`、`/vendor/*`、`/version.txt` | 本容器静态文件（宇宙页面） |
| `/?subject=…`、旧模块页（`/structure`、`/capital`、`/supply-chain`、`/industries`、`/objects-scope`、`/signals`、`/policy`、`/control`、`/ma`、`/development-status`）、`/_next/*`、图标等 | 本容器静态文件（旧版图谱前端，镜像构建时由 `apps/web` 导出，放在 `/usr/share/nginx/legacy`）；本地找不到才回退 `EEI_UPSTREAM` |
| `/v1/*`、`/health` | 反代到 `EEI_UPSTREAM`（Host 头与 SNI 用上游主机名，校验上游证书）；`/v1/` 只读查询走 1 小时缓存 |

`EEI_UPSTREAM` 默认 `https://codex-eei.linzezhang35.workers.dev`（Cloudflare Workers 上的旧程序，走 workers.dev 地址，不再绑自定义域名）。现在它只承担数据接口 `/v1/*`、`/health` 和本地找不到的路径；数据接口迁到服务器自己的 API 后，只改这个变量即可。换上游：在 `eei-universe.env` 的 `RUN_EXTRA_ARGS` 里加 `-e EEI_UPSTREAM=https://…`，重跑 `install.sh` 后 `eei-pull-deploy.sh run eei-universe --force`。

## 主站现状与回滚

**主站 `https://eei.linzezhang.com` 已在 VPS-3 上**（2026-09-30 从 Cloudflare Worker `codex-eei` 切来，Owner 批准）：

- DNS：Cloudflare 里 `eei` 是 A 记录 → VPS-3 IP（proxied）。
- 路由：本容器的 Traefik 路由是 `Host(eei.linzezhang.com)`（即 env 里的 `DOMAIN`），证书由 Traefik letsencrypt（HTTP-01）自动签。旧预览域名 `eei-preview.linzezhang.com` 已收掉（DNS 与路由都删了）。
- 上游：`/v1/*`、`/health` 与本地找不到的路径反代到 `https://codex-eei.linzezhang35.workers.dev`（Worker 已解绑自定义域名、开着 workers.dev）；`/` 是本容器的宇宙页面。
- `EXTRA_DOMAINS_CERT=yes`：额外域名机制保留，目前 `EXTRA_DOMAINS` 为空。

**回滚到 Cloudflare Worker**（宇宙页面下线、回到旧图谱）：
1. Cloudflare 后台：给 Worker `codex-eei` 重新添加自定义域名 `eei.linzezhang.com`。
2. 删除 `eei` 这条指向 VPS-3 的 A 记录（Worker 自定义域名会自己接管 DNS）。
3. 服务器容器可留着不动（没有流量进来）；要彻底停就 `sudo systemctl disable --now eei-universe-pull.timer`。

**改了本目录的 env 之后**：服务器跑 `install.sh` 同步，再 `sudo /usr/local/bin/eei-pull-deploy.sh run eei-universe --force`（路由标签只在新容器创建时生效，所以要 `--force` 重建一次）。
