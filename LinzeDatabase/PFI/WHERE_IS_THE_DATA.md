# 📍 支付宝流水数据已移出本公开仓

> **2026-07-25：`LinzeDatabase/PFI/alipay_daily/`（raw + processed，4 年 8,815 条支付宝个人流水）
> 已迁往私有仓 `LinzeColin/Private-Database` 的 `Private-MetaDatabase/` 区并从本公开仓删除。**
> 迁移前逐件核对 sha256 全部落库，移除安全。

## 为什么移

这批 CSV 含真实金额、日期、商户与理财对手方名称（个人财务 PII），不应存于公开仓。
`MetaDatabase` 是 PUBLIC 仓；数据权威落地处统一为私有仓（见根目录 `WHERE_IS_PROJECT_DATA.md`）。

## 怎么取（免 clone）

用 `KMOS/KMDatabase/machine/tools/private_db_client.py`（底层 GitHub API，零 clone）：

```bash
T=KMOS/KMDatabase/machine/tools/private_db_client.py
python3 $T list Private-MetaDatabase                        # 看有哪些对象（domain=LinzeDatabase-alipay）
python3 $T get  Private-MetaDatabase objects/2c/2c95…_alipay_transactions.csv ./out.csv
```

## 给 PFI 应用与后续 agent 的提示

- 顶层 `MetaDatabase/PFI/` 应用**运行时读本机缓存 `~/.pfi/runtime/`，不读本目录**；本目录原是"验收/备份/GitHub 检查"归档副本，移除不影响运行。
- 消费方对旧路径 `MetaDatabase/PFI/alipay_daily/...` 的引用在仓库拆分后**本就已悬空**（数据早改名到 `LinzeDatabase/PFI/`），本次移除不新造断裂。
- 只删当前版本；git 历史里的旧提交仍含这些 CSV，历史清除由 Owner 另行决策。
- 新数据一律用 SDK 写进 Private-MetaDatabase，不要再往本地落。
