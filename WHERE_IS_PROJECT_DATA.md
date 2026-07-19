# 📍 项目数据往哪存：Private-Database

> **给 MetaDatabase 各项目（Alpha / EEI / FIFA / LinzeDatabase / PFI / QBVS / Serenity-Alipay / ABD）
> 及后续新 agent 的路牌。**

本仓**只放代码与治理**。任何项目产生的**原始/业务数据**（需要跨设备、跨 agent 统一落地、
或体量超出代码仓合理范围的），一律存到私有仓 **`LinzeColin/Private-Database` 的 `Private-MetaDatabase/` 区**。

## 现状

2026-07-19 核查：MetaDatabase 各项目**尚无独立的内容寻址数据层**（大目录多为 `node_modules`/工作区，属代码依赖，不属数据），故 `Private-MetaDatabase/` 当前为**占位区**，未实迁任何文件。

## 将来怎么用（免 clone）

```bash
# 参考实现（可从 KMOS/KMDatabase/machine/tools/private_db_client.py 取一份）
python3 private_db_client.py ingest Private-MetaDatabase ./某项目原始数据.xlsx --domain Alpha
python3 private_db_client.py get    Private-MetaDatabase objects/xx/....xlsx ./out.xlsx
```

规则：Private-Database 是 **PRIVATE**，**禁止 `git clone`**（预计 500GB+）；只按需下载单文件；协议见 `Private-Database/PROTOCOL.md`。
