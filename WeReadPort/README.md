# 阅迁（WeRead Port）

一句话：微信读书笔记迁移与个人阅读资产账户平台——注册登录后，把微信读书笔记一键导入并长期保存，支持跨设备同步、导出和永久删除账户；运行期不调用模型，Agent 与 Token 依赖均为零。规格见 [SPEC.md](./SPEC.md)；旧版长 README（能力清单、Cloudflare 部署细节、运维命令）在 [文档/归档/](./文档/归档/)。

## 线上地址与是否真在跑

- 地址：`https://weread.linzezhang.com`（Cloudflare Worker 薄代理 + OVH 账户服务 `https://weread-api.linzezhang.com`）。
- 健康检查：`/healthz`（只证明公开入口存活）、`/readyz`（主动验证 SQLite、R2 写读删、worker 心跳、OAuth 配置，失败返回 503）、`/api/status`（脱敏状态）。
- 2026-09-30 实测：`weread.linzezhang.com/healthz`、`/readyz`、`/api/status` 与 `weread-api.linzezhang.com/readyz` 的 `curl -sI` 都返回 200；版本 `v0.0.0.1.9`。
- 数据最迟多久该更新一次：服务健康每 **60 秒**采集一次（`weread-port-platform-health.timer`）；事实同步每日 UTC 03:47；平台快照每日 UTC 03:31；Private-Database 冷备每日 UTC 04:01（`service/systemd/`）。站点烟雾检查每日 UTC 02:23（`.github/workflows/weread-port-postlaunch.yml`）。

## 数据放哪

账户索引、会话、队列在 OVH SQLite；笔记正文以账户级 AES-256-GCM 加密对象存 Cloudflare R2（每条笔记只保留最新 3 个版本）；脱敏结构化事实进私有仓 `Private-Database`（路牌见仓根 `WHERE_IS_PROJECT_DATA.md`）。本仓只放代码，密钥在 `/etc/weread-port/platform.env`，不入仓。

## 怎么部署 / 回滚

- 网站（Worker）：只用 `npm run deploy:cloudflare`，不要裸跑 `npx wrangler deploy`（会清空线上变量）。脚本部署前取回线上变量、部署后回读 `/api/version`，任一条不过自动回滚；手动回滚用 `wrangler rollback`。
- 账户服务（OVH）：`sudo python3 service/scripts/platform_preflight.py --env-file /etc/weread-port/platform.env --require-paths --strict`，再 `sudo python3 service/install_platform.py --apply`；安装器用版本化 release 目录加 `/opt/weread-port/current` 软链接，激活失败自动指回上一版（`service/install_platform.py`）。
- 运维包回滚：`ops/bin/rollback <已安装版本>`。

## 需登录 / 需凭据而停掉的功能

- Google、GitHub、Notion 登录与导入：需各平台 OAuth 凭据，配在服务器环境文件；当前是否已配置：未核实。
- 真实账户端到端验收（`tests/browser/production_account_e2e.py`）：需 Owner 的微信读书密钥（仓库 Secret `WRP_E2E_WEREAD_KEY`），只由 Owner 手动触发，不进定时任务。
- 部署 Worker：需 `CLOUDFLARE_API_TOKEN`，在 Owner 的保管库里。

## 本地测试

要求 Node.js 22.13+、Python 3.11+：

```bash
cd WeReadPort
npm ci --ignore-scripts --no-audit --no-fund
npm run verify:integration     # 2026-09-30 实测全绿（node 140+64+6 项，Python 19+13 项）
```

全量验证 `npm run verify:all`（多跑两个基准）。CI：`.github/workflows/weread-port-ci.yml`；上线后持续检查：`weread-port-postlaunch.yml`。运行规则见 `AGENTS.md`。
