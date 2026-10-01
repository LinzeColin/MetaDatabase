# Serenity 规格（一页）

## 要解决什么问题

Owner 想对一批场外基金候选做有纪律的筛选：导入持仓和候选、用固定规则打分、对比基准、给出目标权重与行动标签，并在工作日固定时段自动出报告，不依赖本机。

## 给谁用

Owner 一人；报告是私有的，公开页只有脱敏演示。

## 明确不做

- 不自动买卖；不提交支付宝动作、券商订单、转账或实盘指令（`AGENTS.md`「边界」）。
- 不绕过支付宝、基金公司、moomoo、券商的平台控制。
- 不承诺未来跑赢上证指数或标普 500。
- 不把 moomoo/OpenD 失败当成健康数据。
- 个人财务数据、凭据、运行数据库不进公开仓。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 应用测试 | `cd Serenity-Alipay && PYTHONDONTWRITEBYTECODE=1 python -m pytest -q`（需 `pytest`、`pypdf`、`pillow`；Linux 上图标测试因缺 macOS `iconutil` 必失败） |
| 无人值守调度与发布逻辑 | `python -m pytest -q tests/test_headless_service.py tests/test_headless_publish.py tests/test_headless_sources.py` |
| 公开页可达且是演示页 | `curl -sI https://serenity.linzezhang.com` 返回 200（2026-09-30 实测 200）；`app/cloudflare-public/public/public-surface.json` 中 `mail_enabled`、`broker_enabled`、`scheduler_enabled` 均为 false |
| 定时器已装好 | 服务器上 `systemctl list-timers serenity-tick.timer` 有下一次触发时间 |
| 双平面文档未漂移 | `python3 Serenity-Alipay/machine/tools/check_dual_plane_ci.py --root . --projects Serenity-Alipay --require-projects` |

## 已知坑

- 运行时需要服务器上的 GitHub 凭据才能发布 Release；没有凭据时 `service-tick` 会失败（`journalctl -u serenity-tick`）。
- 机器事实与治理 YAML 里仍有指向原 `CHANGELOG.md`、`BACKUP_SYNC_NOTE.md`、`DEVELOPMENT_BUG_REGRESSION_LOG.md` 的证据路径；这些文件现在在 `文档/归档/`。
- `AGENTS.md` 里提到的 `scripts/lean_governance.py` 在本仓已不存在，以 `machine/tools/check_dual_plane_ci.py` 为准。
- `test_application_bundle_has_custom_icon` 需要 macOS `iconutil`，Linux 上失败，与本次改动无关。
- 没有自动新鲜度告警：未核实。
