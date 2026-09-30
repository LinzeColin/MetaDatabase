# Serenity-Alipay（Serenity 每日分析）

一句话：用公开数据对场外基金候选做确定性打分、排名和纪律标签，工作日自动出分析报告；**只做研究，不下单、不保证跑赢基准**。规格见 [SPEC.md](./SPEC.md)。

## 线上地址与是否真在跑

- 公开页：`https://serenity.linzezhang.com`。它只是一个静态的脱敏演示页（`app/cloudflare-public/`，`public-surface.json` 里邮件、券商、调度全部为 false），不是分析结果本身。2026-09-30 实测 `curl -sI` 返回 200。
- 真正的分析在 VPS-3 的 systemd 定时器 `serenity-tick.timer` 上跑：工作日（周一到周五）北京时间 08:30、09:30 … 17:30，共 10 个时段（`deploy/vps3/serenity-tick.timer`）。
- 怎么判断真在跑：服务器上 `systemctl list-timers serenity-tick.timer`、`journalctl -u serenity-tick -n 80`；每个时段会在私有仓 Release 里出一份报告（见下）。
- 数据最迟多久该更新一次：工作日 08:30–17:30 内最长 1 小时一次；周五 17:30 到下周一 08:30 没有运行是正常的。没有自动新鲜度告警端点：未核实。

## 数据放哪

- 运行状态：VPS-3 `/var/lib/serenity`（systemd `StateDirectory`）；代码只读检出在 `/opt/serenity/src`。
- 报告：作为 Release 资产发布到私有仓 `LinzeColin/Private-Database`（`app/headless/publish.py` 的 `DEFAULT_REPO`，可用 `SERENITY_RELEASE_REPO` 改）。
- 个人持仓与运行数据不进本公开仓，路牌见仓根 `WHERE_IS_PROJECT_DATA.md`。

## 怎么部署 / 回滚

- 分析服务：在 VPS-3 上 `sudo bash Serenity-Alipay/deploy/vps3/install.sh`（幂等：稀疏检出 `main`、装 unit、启用定时器）。
- 公开页：`Serenity-Alipay/app/cloudflare-public/**` 合入 `main` 后由 `.github/workflows/deploy-serenity.yml` 触发 Coolify 部署。
- 回滚：`main` 上 revert 出问题的提交，再在服务器上重跑 `install.sh`；`SERENITY_REF` 环境变量可指定其它分支或标签。

## 需登录 / 需凭据而停掉的功能

- 真实邮件通知：只生成草稿，不发送（公开页 `mail_enabled=false`），标「需凭据，已停」。
- moomoo / OpenD 平台检查：需本机 OpenD 登录，已停；失败不会被当成健康数据（`文档/归档/旧README_2026-09.md`）。
- 支付宝持仓导入：需 Owner 提供私有 CSV，已停。
- 发布 Release 需要服务器上的 GitHub 凭据（`serenity-tick.service` 的 `LoadCredential`，不入仓）。

## 本地测试

```bash
python3 -m venv /tmp/venv-serenity && /tmp/venv-serenity/bin/pip install pytest pypdf pillow
cd Serenity-Alipay && PYTHONDONTWRITEBYTECODE=1 /tmp/venv-serenity/bin/python -m pytest -q
```

2026-09-30 Linux 沙箱实测：仅 `tests/test_reporting_ui.py::test_application_bundle_has_custom_icon` 失败，原因是它调用 macOS 的 `iconutil`（在主干上同样失败）。长版说明、变更记录、回归日志、备份说明在 [文档/归档/](./文档/归档/)；运行规则见 `AGENTS.md`。
