---
ck_schema: "context-kernel/kernel-v1"
skill_version: "0.0.0.1"
revision: 1
updated_at: "2026-07-26T12:52:18Z"
lifecycle: "ACTIVE"
---

# 文脉中枢｜Context Kernel

> 当前项目的唯一状态事实源。只保留仍影响后续执行的有效信息；不保存聊天记录、长推理或原始工具输出。

## 目标
- 项目：EEI (Economic Entity Intelligence)
- 北极星：把 SEC/GLEIF 第一手公开数据变成一个不用登录、不买商业数据、能自己看懂实体关系与资金链条的公开情报界面
- 当前目标：语料持续增长且增长可见；界面达到可交付观感；长期事实落权威数据层
- 当前任务：修可见文本压叠（T-32）、修 skipped_upload 误报（T-33）、盒子 postgres 定期裁剪（T-34）
- 阶段 / Gate：MVP 数据脉搏已上线，进入 UIUX 收敛与数据层运维收口

## 范围与约束
### 范围内
- SEC EDGAR + GLEIF 第一手公开数据采集、入库、发布
- Cloudflare Worker 公开只读 API + Next.js 前端（CLOUD_MODE）
- OVH 计算节点上的采集/发布容器
- 长期事实同步至 Private-Database

### 范围外
- 任何登录/鉴权功能（Owner 明令「不加登录」）
- 任何付费商业数据源（Owner 明令「不买商业数据」）
- 触碰 OVH 上 Alpha 共租系统的任何资源
- 为长期数据治理另建第二个权威数据仓

### 硬约束
- 所有完成声明必须绑定 VERIFIED 证据；未核验内容必须明确标记 UNVERIFIED
- 不保存密钥、完整聊天、隐藏推理或原始工具输出
- 活跃 Markdown 文件最多三个
- 主树只读停 main，开发一律在 worktree；谁开的谁收（合并+关 PR+收 worktree+删分支+清缓存）
- git gc 禁止 --prune=now
- _protected/ 永不删永不上传
- OVH 共租红线：不碰 5 个 alpha-* unit、系统 postgresql、cloudflared、/opt/alpha/、11111 端口、127.0.0.1:8443；不重启 docker daemon；EEI 容器带 oom_score_adj 500
- 部署冻结窗口：美股交易时段 周一至周五 13:30-20:00 UTC，每日 20:10-20:20，周二 14:00-15:00
- CI 清单顺序不可颠倒：git add 显式路径 → manage_clean_room_release.py generate → manage_release_artifacts.py generate

### 软偏好
- 汇报用人话，结论先行，不堆治理 ID 与提交号（Owner 说过「我看不懂」）
- 优先使用最少上下文恢复任务

## 当前状态
### 已完成
- C-0001 | 数据脉搏后端+前端上线：/v1/meta/pulse 总量·今日/7日/30日增量·增长曲线·构成·来源新鲜度·采集器心跳；曲线不建指标表，直接由原始 observed_at/created_at 推导 | E-0001 E-0002
- C-0002 | 采集「追平即静止」被打破：新增 sec_daily_index 全量索引扫描 + 历史深挖游标；周日 SEC 零申报当天事件仍从 0 涨到 9,929，总量 185,167→195,096 | E-0002
- C-0003 | snapshot_meta.as_of 陈旧修复：由固定治理时间戳改为语料中最新事实时间，每轮 pulse 刷新 | E-0003
- C-0004 | 补齐 GET /v1/sources/freshness（前端一直在调、云上一直 404） | E-0002
- C-0005 | 采集器心跳每条退出路径都发（第一版漏了「无新增」那条，恰是最需要的那条） | E-0002
- C-0006 | 长期事实首次进入权威数据层：5 个日分片 gzip NDJSON 落 Private-MetaDatabase domain=EEI，manifest 恰好 5 行无重复，往返取回逐位相符 | E-0004 E-0005
- C-0007 | 盒子永不持有 GitHub 凭据的分离式同步：盒子只 --export-only 造分片，入库在有 gh 认证处执行，两侧临时文件用后即抹 | E-0006
- C-0008 | EEI/WHERE_IS_THE_DATA.md 路牌：权威=Private-Database，OVH postgres 与 D1 都只是可重建层 | E-0006
- C-0009 | private_db_client.py 照 PROTOCOL.md 自行实现（不跨仓取代码），凭据/*.sqlite 红线五条单测全过 | E-0006
- C-0010 | e2e A110 抖动根因修复：apply 点击前加输入值提交门，本地 --repeat-each=4 8/8 过，CI 两个 verify job 全绿 | E-0007
- C-0011 | 我的抽屉三处交互修复：未读基线、打开即清零、Escape 关闭 | E-0007

### 进行中
- P-0001 | T-32 修 11 处可见文本压叠（1440×900 实测有坐标清单），三类根因：边标签在 L0/L1 从不进防压叠竞争、浮层压时间轴年份、底部状态条内部互挤
- P-0002 | T-33 修 private_db_client.ingest 的 skipped_upload 误报
- P-0003 | T-34 盒子 postgres 按权威副本裁剪历史分区

### 阻塞
- 无

### 未知与待验证
- U-0001 | skipped_upload 为何在首次上传时也报 true | 重要性：它正是「无新增事实⇒不产生空提交」的判据，恒为 true 会让真新增被误跳过 | 验证：读 ingest 的 blob_sha 比对分支，构造「已存在」与「全新」两个用例断言
- U-0002 | 修完压叠后 1440/1280/768 三档是否仍无新压叠 | 验证：三档重测 + 重录视觉基线

### 风险
- R-0001 | OVH 盒子磁盘 40 分钟内 21G→28G（54%→75%，余 9.8G）| 归因：非 EEI，Docker Build Cache 2.28G→10.56G（9.25G 可回收）+ containerd 17G，EEI pg 卷 577M 未动 | 缓解：docker builder prune 可回收 9.25G，但属共享基建需 Owner 点头
- R-0002 | 深挖游标持续回扫历史会把 pg 推向 2.5-3GB | 缓解：权威副本已就位，按 T-34 定期裁剪
- R-0003 | 底部状态条「全库已核实关系」与脉搏计数不同源，会短暂不一致

## 责任
- 最终责任人：Linze (Owner)
- 当前执行主体：Claude Code session db976b0c
- 移交状态：NONE
- 移交编号：无
- 移交来源主体：无
- 目标执行主体：无
- 移交原因：无

## 决策引用
- D-0001 | 数据分层：GitHub Private-Database 唯一权威，OVH 只跑计算
- D-0002 | 计算节点永不持有 GitHub 凭据
- D-0003 | 增长曲线不建指标表，直接由原始时间戳推导
- D-0004 | 不跨仓取代码，照协议自行实现客户端

## 下一步
1. A-0001 | 提交 --export-only 与 .ramify/，按 CI 清单顺序重生成清单，开 PR 走 CI 合入
2. A-0002 | 修 T-33 skipped_upload 误报并补两个方向的单测
3. A-0003 | 修 T-32 十一处压叠，三档重测并重录视觉基线
4. A-0004 | 实施 T-34 盒子 postgres 裁剪
5. A-0005 | 收尾：合 PR、删分支、收 worktree、git gc（禁 --prune=now）

## 证据
- E-0001 | VERIFIED | PR #124 squash=c3acc31e；PR #125 | 数据脉搏后端与 as_of 自动刷新已合入 main
- E-0002 | VERIFIED | _protected/EEI_runtime_evidence/data_pulse_golive_20260726.md | 线上 pulse 实测、采集恢复决定性证据、盒子部署与共存核验、CI 结果
- E-0003 | VERIFIED | GET /v1/meta/pulse data_as_of=2026-07-26T10:53:39Z（原 2026-07-16T22:03:24）| as_of 已随语料刷新
- E-0004 | VERIFIED | Private-Database/Private-MetaDatabase/manifest.jsonl 恰好 5 条 domain=EEI，batch=EEI-20260726-initial | 首批事实落库无重复
- E-0005 | VERIFIED | eei_facts_2026-07-26.ndjson.gz 取回 1,227,266 字节 sha256=24ebd57e… 与本地逐位相符，9,938 行，首行 _meta 计数 2/9929/6 | 权威副本可恢复
- E-0006 | VERIFIED | EEI/scripts/private_db_client.py、EEI/scripts/sync_facts_to_private_db.py、EEI/WHERE_IS_THE_DATA.md | 数据层对齐实现与路牌
- E-0007 | VERIFIED | CI verify job 全绿 + 本地 27 passed（home/visual-regression/responsive）| e2e 与交互修复已验证

## 不要重复
- N-0001 | 不要再用降尺寸截图或 0×0 视口测量压叠：两次都得出过错误结论，必须 1440×900 实机量并带可见性过滤
- N-0002 | 不要在 React 提交前同步读 DOM 判断「点了没反应」：曾据此误报指标卡失效
- N-0003 | 不要把心跳放在只覆盖部分退出路径的位置：曾漏掉「无新增」那条
- N-0004 | 不要改 EEI 内容后忘记按顺序重生成两个清单：CI 会以 missing/stale 直接失败
- N-0005 | 不要在主树里跑 next build/typecheck：会生成 next-env.d.ts 脏改动，锁死并行
