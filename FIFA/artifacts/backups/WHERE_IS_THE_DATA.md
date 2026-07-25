# 📍 含 SQLite 的私有备份已移出本公开仓

> **2026-07-25：以下含真实博彩数据库/台账的备份已迁往私有仓
> `LinzeColin/Private-Database` 的 `Private-MetaDatabase/`（domain=FIFA）并从本公开仓删除：**
>
> - `tab_fifa_reports_20260613.sqlite3.gz`（报表 SQLite 库本体）
> - `legacy_fifa_analysis_db_20260613.sqlite3.gz`（旧分析库）
> - `20260615/runtime_outputs_snapshot_20260615.tar.gz`（含 `tab_fifa_reports.sqlite3` + bankroll + bets 的运行时快照）
> - `20260615/2026_FIFA_ledger_20260615.xlsx`（资金台账）

## 为什么

本项目**自有 public-safe 纪律**：SQLite 库属私有、公开件只展示聚合状态（见 `artifacts/latest/position_monitor_latest.md`）。
但上述 sqlite 备份被误提交进了 PUBLIC 仓，与项目自身边界冲突，故移除。

## 保留的 public-safe 件（未动）

- `public_outputs_without_sqlite_20260613.tar.gz`（有意剔除 sqlite 的公开输出集）
- `20260615/fifa_world_cup_team_tables_1930_2022.xlsx`（公开世界杯赛事参考）
- `artifacts/latest/`（有意公开、余额/下注均 `account-update-pending` 脱敏）

## 取回（免 clone）

```bash
python3 KMOS/KMDatabase/machine/tools/private_db_client.py list Private-MetaDatabase
python3 KMOS/KMDatabase/machine/tools/private_db_client.py get Private-MetaDatabase objects/e8/e8601a0c09ed…_tab_fifa_reports_20260613.sqlite3.gz ./out.gz
```

活运行时写仓外 `work/private/tab_fifa`，本次移除不影响运行。只删当前版本；git 历史清除由 Owner 另行决策。
