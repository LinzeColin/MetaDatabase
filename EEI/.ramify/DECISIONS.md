---
ck_schema: "context-kernel/decisions-v1"
skill_version: "0.0.0.1"
updated_at: "2026-07-26T13:29:17Z"
---

# 文脉中枢｜决策账本

> 只记录会持续影响后续任务、架构、边界、责任或高返工成本的重要决策。普通讨论、临时想法和重复确认不进入本文件。

## 有效决策索引
- D-0001 | 数据分层：GitHub Private-Database 唯一权威，OVH 只跑计算
- D-0002 | 计算节点永不持有 GitHub 凭据
- D-0003 | 增长曲线不建指标表，直接由原始时间戳推导
- D-0004 | 不跨仓取代码，照协议自行实现客户端

## 决策记录

> 新决策使用 `D-0001` 起的四位编号。已接受决策不得静默改写；替代时新增决策并维护 Supersession 关系。

### D-0001 — 数据分层：GitHub Private-Database 唯一权威，OVH 只跑计算
- 状态：ACCEPTED
- 日期：2026-07-26
- 决策责任人：Owner
- 决策：长期结构化事实、发布记录、故障结论、恢复事实只以 GitHub LinzeColin/Private-Database 为唯一权威；OVH 只跑计算，其存储降级为可重建的事务缓存/队列/游标/Runtime Journal；Cloudflare D1 仅在确有查询价值时作可重建冷索引；R2 冷备与大文件（含用户/隐私信息对象）；OCI 是 R2 的异地备份。无新增事实不得空提交，不上传高频日志或可由运行状态重建的数据。不许为长期数据治理另建第二个或平行权威仓。
- 理由：Owner 原话「你不要保存在ovh」。EEI 此前把全部长期事实只存在 OVH postgres 一处，盒子损毁即全损。
- 证据：VERIFIED | EEI/WHERE_IS_THE_DATA.md + Private-MetaDatabase manifest 5 条 domain=EEI + 往返取回逐位相符
- 影响：所有采集结果必须批量、幂等、可验证地流入 Private-Database；EEI postgres 与 D1 从此可被裁剪与重建
- 替代：无
- 复审触发：Owner 变更数据分层，或权威仓协议 PROTOCOL.md 变更

### D-0002 — 计算节点永不持有 GitHub 凭据
- 状态：ACCEPTED
- 日期：2026-07-26
- 决策责任人：Claude Code session db976b0c
- 决策：同步分两段——盒子只执行 --export-only 造分片（不需任何凭据），入库在已有 gh 认证的环境执行，两侧临时文件用后即抹。
- 理由：与「账号级 Cloudflare 密钥不下盒子」同一条原则。盒子是共租主机，一旦被读取，凭据即等同权威仓写权限。
- 证据：VERIFIED | EEI/scripts/sync_facts_to_private_db.py --export-only 分支 + 首批 5 分片实测流程
- 影响：同步不能做成盒子上的全自动 cron，必须由持凭据侧发起或拉取
- 替代：无
- 复审触发：出现可安全下放到盒子的短时效、仅可写单一路径的凭据机制

### D-0003 — 增长曲线不建指标表，直接由原始时间戳推导
- 状态：ACCEPTED
- 日期：2026-07-26
- 决策责任人：Claude Code session db976b0c
- 决策：/v1/meta/pulse 的每日累计与新增曲线由 events.observed_at、relationships.created_at、entities.created_at 现场推导，不落任何 metrics/统计中间表。
- 理由：中间表会引入第二事实源与回填/漂移问题；曾出现 snapshot_meta.as_of 停在十天前正是固化时间戳的后果。
- 证据：VERIFIED | EEI/scripts/publish_to_cloud_channel.py 的 PULSE_*_SQL + 线上 data_as_of 随语料刷新
- 影响：曲线永远与语料一致，代价是发布时多跑几条聚合查询
- 替代：无
- 复审触发：聚合查询成为发布瓶颈，或需要跨天回溯已删除数据

### D-0004 — 不跨仓取代码，照协议自行实现客户端
- 状态：ACCEPTED
- 日期：2026-07-26
- 决策责任人：Claude Code session db976b0c
- 决策：Private-Database 客户端按该仓 PROTOCOL.md 在 EEI 内自行实现，不从 KMOS 等其他仓复制既有实现。
- 理由：工作间铁律「不跨仓」。复制会造成两份互不同步的实现与隐性依赖。
- 证据：VERIFIED | EEI/scripts/private_db_client.py + 凭据/*.sqlite 红线五条单测全过
- 影响：协议变更时每个仓各自跟进，代价是重复实现
- 替代：无
- 复审触发：协议方发布官方客户端包
