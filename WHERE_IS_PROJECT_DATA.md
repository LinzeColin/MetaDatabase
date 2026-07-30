# 📍 项目数据往哪存：Private-Database

> **给 MetaDatabase 各项目（Alpha / EEI / FIFA / LinzeDatabase / PFI / QBVS / Serenity-Alipay / ABD / CyberBoss）
> 及后续新 agent 的路牌。**

本仓**只放代码与治理**。任何项目产生的**原始/业务数据**（需要跨设备、跨 agent 统一落地、
或体量超出代码仓合理范围的），一律存到私有仓 **`LinzeColin/Private-Database` 的 `Private-MetaDatabase/` 区**。

## 现状

**2026-07-25 核查更正**：上一版（2026-07-19）误判"无数据可迁"——它只盘点了顶层项目工作区，漏看了藏在项目里的真实数据。本次已把真实个人财务/业务数据迁入 `Private-MetaDatabase/` 并从本公开仓删除：

| 来源（本公开仓） | 迁入 domain | 内容 |
|---|---|---|
| `LinzeDatabase/PFI/alipay_daily/` | `LinzeDatabase-alipay` | 支付宝 4 年 8,815 条个人流水（raw+processed，6 件） |
| `FIFA/artifacts/backups/`（含 sqlite 的备份） | `FIFA` | 博彩报表/分析 SQLite 库、运行时快照、资金台账（4 件） |
| `Serenity-Alipay/data/{notifications,reports}` | `Serenity` | 含本人邮箱的邮件草稿与生成的投顾报告（打包 2 件） |

各来源目录已留 `WHERE_IS_THE_DATA.md` 路牌。**保留在公开仓的是**：各项目代码/治理、FIFA public-safe 件、Serenity 公开基金参考 CSV 与样例。
仅删当前版本；git 历史里的旧提交仍含这些数据，历史清除由 Owner 另行决策。

## 项目路由

| 项目 | 耐久路由 | 当前状态 |
|---|---|---|
| xhs-douyin-2notion | `Private-MetaDatabase` / `domain=xhs-douyin-2notion` / `private_db_client.py ingest|get|list|verify`；禁止 clone | Task005 仅完成 CI-synth 验证；未执行真实传输、认证会话、系统备份设置或物理删除 |

## 将来怎么用（免 clone）

```bash
# 参考实现（可从 KMOS/KMDatabase/machine/tools/private_db_client.py 取一份）
python3 private_db_client.py ingest Private-MetaDatabase ./某项目原始数据.xlsx --domain Alpha
python3 private_db_client.py get    Private-MetaDatabase objects/xx/....xlsx ./out.xlsx
```

规则：Private-Database 是 **PRIVATE**，**禁止 `git clone`**（预计 500GB+）；只按需下载单文件；协议见 `Private-Database/PROTOCOL.md`。

## 新项目路由登记

| 项目 | Private-MetaDatabase domain | 当前状态 | 存取方式 |
|---|---|---|---|
| `CyberBoss/` | `CyberBoss` | Prestage 0；尚无业务/运行时数据入库 | `private_db_client.py` 的 `ingest/get/list/verify`；禁止 clone |
