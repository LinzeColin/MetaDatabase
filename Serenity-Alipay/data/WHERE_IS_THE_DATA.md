# 📍 Serenity 数据说明（哪些留、哪些移出）

> **2026-07-25 清理：运行时派生产物已移出本公开仓并加入 `.gitignore`，公开参考数据保留。**

## 保留在仓内（App 有意公开、且被测试断言）

- `data/manual/`：候选基金主数据 `candidates.csv`、净值/基准历史 `price_history.csv` / `benchmark_price_history.csv`、申赎规则 `fund_rules.csv` —— **公开基金参考数据**（含官网来源 URL），App 首页公开链接、`test_reporting_ui.py` 断言其 URL。
- `data/imports/alipay_positions.csv`：**样例**持仓（source_note 标注 manual sample），非真实持仓。
- `data/moomoo/`：公开行情 OHLCV 快照。

## 已移出（迁往私有仓 `Private-MetaDatabase`，domain=Serenity）

- `data/notifications/`（79 个邮件草稿，含本人邮箱）、`data/reports/`（53 个生成的投顾报告）
  → 打包为 `serenity_notifications_20260725.tar.gz` / `serenity_reports_20260725.tar.gz` 归档进私有仓后删除。

## 已删除且不再入库（运行时自动再生，无需备份）

- `data/serenity_daily.sqlite`：App `CREATE TABLE IF NOT EXISTS` 自动重建（下次运行即生成）。
- `data/serenity_launchd.*.log`：本机调度日志。

取私有仓归档：`python3 KMOS/KMDatabase/machine/tools/private_db_client.py get Private-MetaDatabase objects/3a/…serenity_notifications_20260725.tar.gz ./out.tar.gz`。
只删当前版本；git 历史清除由 Owner 另行决策。
