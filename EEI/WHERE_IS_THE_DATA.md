# 📍 EEI 的数据在哪、谁是权威

> 判断某处是「权威」还是「快照」，以本文件为准（Private-Database README 的口径）。

## 一句话

**长期结构化事实的权威在 GitHub `LinzeColin/Private-Database` 的 `Private-MetaDatabase/` 区（domain=`EEI`）。
OVH 上那份 postgres 是可重建的工作缓存，不是权威；Cloudflare D1 是可重建的冷索引，也不是权威。**

## 分层（Owner 2026-07-26 定）

| 位置 | 角色 | 装什么 | 权威? |
|---|---|---|---|
| `Private-Database/Private-MetaDatabase/`（domain `EEI`） | **权威长期事实层** | 实体 / 关系 / 事件 + 各自的证据锚点（source_document id、locator、官方 URL、publisher）；发布记录、故障结论、恢复事实 | ✅ **是** |
| OVH `eei-db`（postgres，139.99.61.6） | 计算节点的**可重建事务缓存** | 采集中间态、幂等去重、游标、Runtime Journal、Outbox | ❌ 否 |
| OVH 容器磁盘（`.eei_*_state.json` / `.eei_*_runs.jsonl`） | Runtime Journal | 轮询日志、seen-accession 环、刷新游标 | ❌ 否（高频，且定义上可重建） |
| Cloudflare D1 `eei-publication` | **可重建冷索引** | 公开站点查询用的投影（含 pulse 聚合） | ❌ 否 |
| Cloudflare R2 | 冷备 / 大文件冷存 | 原始申报正文、二进制、含隐私的对象 | ❌ 否（权威层只存引用+hash） |
| OCI | R2 冷备的异地备份 | 同上 | ❌ 否 |

## 怎么同步（免 clone）

```bash
# 日频批量（无新增事实 => 零上传、零 manifest 行、零空提交）
python -m scripts.sync_facts_to_private_db --reason daily

# 重大发布 / 故障 / 恢复时即时同步
python -m scripts.sync_facts_to_private_db --reason release
```

实现：`scripts/private_db_client.py`（照 `Private-Database/PROTOCOL.md` 自行实现，**不跨仓取代码**）
+ `scripts/sync_facts_to_private_db.py`（按入库日分片 gzip NDJSON，内容寻址，天然幂等）。

## 刻意**不**同步的东西

- Runtime Journal（轮询日志、游标、seen-accession 环）——高频，且定义上可由运行状态重建；
- 原始申报正文与任何 blob——归 R2，权威层只留引用、hash、版本；
- 任何触碰红线的文件——凭据（文件名 + 内容双重拒绝）、`*.sqlite`/`*.db`、>95MB。

## 恢复口径

权威层的每个日分片自带 `_meta.counts`（当日 entities/relationships/events 条数）与 sha256。
从零恢复 = 拉全部日分片 → 重建 postgres → 跑一次 `publish_to_cloud_channel.py --apply` 重建 D1。
D1 与 postgres 都可丢，权威层不可丢。

## 规模与天花板

2026-07-26 实测：5 个日分片，14,677 实体 / 13,312 关系 / 195,096 事件，**gzip 后共 27MB**，
最大单片 22MB（< 95MB 硬限）。逼近 5GB / 出现 >95MB 单片 / 高频撞车时，按 Private-Database
README 的「逃生口」整体平移到对象存储，上层零感知。
