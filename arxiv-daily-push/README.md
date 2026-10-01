# ADP（arXiv 日报推送）

一句话：每天把高价值论文和公开来源整理成中文讲解、复习卡片与收益判断的网页（证据优先，不是论文新闻摘要）。规格见 [SPEC.md](./SPEC.md)；owner 每日阅读面见 [用户中心](./用户中心/README.md)。

## 线上地址与是否真在跑

- 目标地址：`https://adp.linzezhang.com/`。2026-10-01 起自托管于 VPS-3（systemd + Docker，出处 `deploy/selfhost/`）。
- **域名还没切到服务器**。2026-09-30 实测 `curl -sI https://adp.linzezhang.com/healthz` 返回 404、`/` 返回 500（仍是旧 Cloudflare）。切换后以下面两项为准，切换前不要当成已上线。
- 健康检查：`/healthz`（进程 + 库能读，固定响应体）；`/healthz?strict=1`（数据不新鲜返回 503）；`/api/selfhost/status`（只读 JSON，看 `fresh` 与 `fresh_reason`）。出处 `deploy/selfhost/app/server.mjs`、`status.mjs`。
- 数据最迟多久该更新一次：**30 小时**（`ADP_FRESH_LIMIT_HOURS` 默认值，`status.mjs`）。每日任务 `adp-daily.timer` 在 UTC 20:30 跑（北京时间 04:30）；arXiv 历史回填 `adp-backfill.timer` 在 UTC 02:30 与 08:30。

## 数据放哪

服务器 `/var/lib/adp`（SQLite 库、备份、任务日志；容器内 `/data`）。本仓只放代码，不放运行数据（见仓根 `WHERE_IS_PROJECT_DATA.md`）。

## 怎么部署 / 回滚

- 部署：合入 `main` 后，服务器上 `adp-web-pull.timer` 每 10 分钟拉一次，只有 `arxiv-daily-push/deploy/` 变了才重建；新容器健康检查不过就自动拉起旧容器（`deploy/selfhost/adp-pull-deploy.sh` 的 `fail()`）。
- 首次安装 / 比对：`sudo bash arxiv-daily-push/deploy/selfhost/install.sh [--enable-jobs|--check]`。
- 回滚：在 `main` 上 revert 出问题的提交，下一轮拉取会自动部署；立刻生效用 `sudo /usr/local/bin/adp-pull-deploy.sh run adp`。

## 需凭据而停掉的功能

- 真实邮件发送：需 SMTP 凭据，已停（`ADP_ALLOW_SMTP_SEND` 保持 `UNSET`）。自托管运行时本身不需要任何凭据（`deploy/selfhost/adp.env`）。
- 持久日常运行（S3/DAILY_OPERATION）：需 owner 持久授权文件，已停。

## 合同边界与本地验证（被 tests 钉住，勿随意删改）

| 事项 | 状态 |
|---|---|
| Stage 2 integrated acceptance 已记录 | 已记录并保持；不等于 S3/DAILY_OPERATION |
| S3/DAILY_OPERATION | 未进入；`daily_operation_enabled=false` |
| 持久运行授权 | 缺 `FINAL_ACCEPTANCE_BUNDLE/daily_operation_persistent_enablement_authorization.json`，不得启用 |
| 运行策略 | 本机/launchd 只作为历史与受控运行证据来源 |
| SMTP 发送开关 | `ADP_ALLOW_SMTP_SEND` 原始值只接受 `UNSET` 或 false-like；truthy 必须停止 |

当前 MVP 准备只做复审修补、证据同步和防回归补强，不进入 S3/DAILY_OPERATION。新增、删除、重命名、启用或停用板块或数据源，必须同步 [数据源与板块健康](./用户中心/数据源与板块健康.md)。

以下命令必须从 MetaDatabase 仓库根目录运行；`tools/` 与 `FINAL_ACCEPTANCE_BUNDLE/` 均为仓根 ADP 兼容路径。
不要给这些 root tools 追加 `--json`；它们默认输出 JSON。
以下 `python3` 必须指向已安装 `arxiv-daily-push/requirements.txt` 的 Python 3.12 环境；macOS 系统 Python 3.9 无法运行当前 ADP 验收入口。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=arxiv-daily-push/src python3 -m unittest discover -s arxiv-daily-push/tests -q
PYTHONDONTWRITEBYTECODE=1 python3 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects
python3 -B tools/verify_acceptance_bundle.py --root . --require-zero P0 P1; ec=$?; echo "EXPECTED_BUNDLE_EXIT=$ec"; test "$ec" -eq 2
python3 -B tools/verify_daily_operation_readiness.py --root .; ec=$?; echo "EXPECTED_READINESS_EXIT=$ec"; test "$ec" -eq 2
python3 -B tools/verify_daily_operation_enablement_preflight.py --root .; ec=$?; echo "EXPECTED_PREFLIGHT_EXIT=$ec"; test "$ec" -eq 2
```

预期：后三个历史 final-bundle / S3 兼容命令均退出码 `2`。`verify_acceptance_bundle.py` 因迁移后刻意不恢复旧根级 `HANDOFF/00_下一Agent先读.md` 而 fail closed；readiness 与 preflight 因缺持久授权文件而 fail closed。不得为了返回 0 而恢复旧 HANDOFF，或启用 SMTP、scheduler、Release、restore、DAILY_OPERATION。

历史长版 README（V5/V6 任务连续性、Stage 1 证据清单）在 [文档/归档/](./文档/归档/)；当前增量开发合同在 [docs/pursuing_goal/v1_2/](./docs/pursuing_goal/v1_2/README.md)；交接入口 `docs/HANDOFF.md`。
