---
ck_schema: "context-kernel/kernel-v1"
skill_version: "0.0.0.1"
revision: 3
updated_at: "2026-07-26T13:49:19Z"
lifecycle: "ACTIVE"
---

# 文脉中枢｜Context Kernel

> 当前项目的唯一状态事实源。只保留仍影响后续执行的有效信息；不保存聊天记录、长推理或原始工具输出。

## 目标
- 项目：EEI (Economic Entity Intelligence)
- 北极星：把 SEC/GLEIF 第一手公开数据变成一个不用登录、不买商业数据、能自己看懂实体关系与资金链条的公开情报界面
- 当前目标：语料持续增长且增长可见；界面达到可交付观感；长期事实落权威数据层
- 当前任务：建权威仓定期同步（T-36）；把面包屑移出图谱核心（U-0002）
- 阶段 / Gate：数据脉搏 + UIUX 压叠归零均已上线；剩数据层排程与两处观感收尾

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
- C-0001 | 数据脉搏上线：/v1/meta/pulse（总量·今日/7日/30日增量·增长曲线·构成·来源新鲜度·心跳）+ 首屏 PulseStrip + 数据面板；曲线不建指标表 | E-0001 E-0002
- C-0002 | 采集「追平即静止」被打破：sec_daily_index 全量索引扫描 + 历史深挖游标；周日 SEC 零申报当天事件仍 0→9,929，总量 185,167→195,096 | E-0002
- C-0003 | 三处陈旧/缺失修复：as_of 改随语料刷新、补齐 /v1/sources/freshness、心跳改为每条退出路径都发 | E-0002 E-0003
- C-0004 | 长期事实首次进权威数据层：5 个日分片落 Private-MetaDatabase domain=EEI，manifest 恰好 5 行无重复，往返取回逐位相符 | E-0004 E-0005
- C-0005 | 数据层对齐三件套：private_db_client 照 PROTOCOL.md 自行实现（不跨仓）、--export-only 让盒子永不持凭据、WHERE_IS_THE_DATA.md 路牌 | E-0006
- C-0006 | 「无新增事实⇒不产生空提交」判据修正：账本去重改按事实身份，ingest 分报 uploaded_object/appended_manifest/created_commit | E-0008 E-0009
- C-0007 | 12 处文本压叠→0 并已上线（PR #128 squash=5192869d）：折叠面板真折叠、环节条单行且避开时间轴、图例让开 KPI 条与缩略图、浮层不透明度 97%、顶部带内不放 L0/L1 边标签；线上三档 1440/1280/768 实测叠字与横向溢出全为 0 | E-0011 E-0012 E-0014
- C-0008 | A110 真因修复：填表单前等页面自己的 hydrated 信号（此前初始加载会把受控输入清空）；linux 容器内 --repeat-each=3 全过 | E-0012
- C-0009 | 我的抽屉三处交互修复：未读基线、打开即清零、Escape 关闭 | E-0007
- C-0010 | 盒子磁盘 78%→50%（腾出 11.9G）：占用源是别的项目的 Docker 构建缓存 12.07GB（ACTIVE=0），9 个 alpha-* unit 全部照常 | E-0013
- C-0011 | 盒子占用实测收口：EEI 共约 790MB（库 334 / WAL 224 受 max_wal_size 约束 / 日志 244K / 镜像 228），原「深挖推到 2.5-3GB」风险不成立 | E-0013
- C-0012 | 文脉中枢落盘（EEI/.ramify/）：项目状态不再只活在聊天窗口 | E-0010

### 进行中
- P-0001 | T-36 建权威仓定期同步：新事实目前不会自动进 Private-Database（受 D-0002 约束，必须由持凭据侧发起）
- P-0002 | U-0002 面包屑浮在图谱核心区，需移出而不是靠标签保留带压掉

### 阻塞
- 无

### 未知与待验证
- U-0001 | 1280 宽度 43px 横向溢出的真实来源 | 现状：旧构建稳定复现、新构建（含 4s 静置+全页滚动）不复现，根因未定位 | 验证：若再现，查 .inspector（aside 248px）子元素为何实测 258px
- U-0002 | 面包屑（screen y 282-314）与焦点节点标签的关系 | 现状：三档探测器判为「正常遮挡」非叠字，但它确实浮在图谱核心 | 验证：把面包屑移出核心区后重量

### 风险
- R-0001 | 盒子磁盘会被别的项目的构建缓存再次撑满 | 现状：已 prune 到 50%、剩 20G | 缓解：非 EEI 可控，需要盒子级缓存上限或定期 prune
- R-0002 | 底部状态条「全库已核实关系」与脉搏计数不同源，会短暂不一致
- R-0003 | 首批事实是手工推的，尚无排程；新事实目前不会自动进权威仓（T-36）

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
1. A-0001 | 建定期同步排程，让新事实持续进权威仓（T-36）
2. A-0002 | 把面包屑移出图谱核心区（U-0002）
3. A-0003 | 若 1280 横向溢出再现，按 U-0001 的线索定位
4. A-0004 | 盒子构建缓存需要上限或定期 prune（非 EEI 可控，R-0001）

## 证据
- E-0001 | VERIFIED | PR #124 squash=c3acc31e；PR #125 | 数据脉搏后端与 as_of 自动刷新已合入 main
- E-0002 | VERIFIED | _protected/EEI_runtime_evidence/data_pulse_golive_20260726.md | 线上 pulse 实测、采集恢复决定性证据、盒子部署与共存核验、CI 结果
- E-0003 | VERIFIED | GET /v1/meta/pulse data_as_of=2026-07-26T10:53:39Z（原 2026-07-16T22:03:24）| as_of 已随语料刷新
- E-0004 | VERIFIED | Private-Database/Private-MetaDatabase/manifest.jsonl 恰好 5 条 domain=EEI，batch=EEI-20260726-initial | 首批事实落库无重复
- E-0005 | VERIFIED | eei_facts_2026-07-26.ndjson.gz 取回 1,227,266 字节 sha256=24ebd57e… 与本地逐位相符，9,938 行，首行 _meta 计数 2/9929/6 | 权威副本可恢复
- E-0006 | VERIFIED | EEI/scripts/private_db_client.py、EEI/scripts/sync_facts_to_private_db.py、EEI/WHERE_IS_THE_DATA.md | 数据层对齐实现与路牌
- E-0007 | VERIFIED | CI verify job 全绿 + 本地 27 passed（home/visual-regression/responsive）| e2e 与交互修复已验证
- E-0008 | VERIFIED | EEI/tests/unit/test_private_db_client.py 10 passed | 未变事实完全静默、真新增照样落账，两个方向都钉死
- E-0009 | VERIFIED | 对真实权威仓账本只读实测：5 条 EEI 记录重放全部判为不追加，2026-07-27 新分片判为追加 | 判据在真数据上成立
- E-0010 | VERIFIED | EEI/.ramify/ revision 1，resume 校验 PASS | 文脉中枢已落盘
- E-0011 | VERIFIED | 线上 eei.linzezhang.com 带裁剪判定与遮挡判定的实测：1440×900 12→0；768×1024 0→0 | 压叠已消除
- E-0012 | VERIFIED | e2e 30 passed（graph-label-overlap / home / visual-regression / responsive），视觉基线零变化 | 修复未回归
- E-0013 | VERIFIED | 盒子 df 78%→50%、docker system df 构建缓存 12.07GB→209MB、systemctl 9 个 alpha-* unit 全部 running/waiting | 清理未伤共租
- E-0014 | VERIFIED | 线上构建绑定 5192869d（/v1/meta/build 与 x-eei-build 头一致）、CSS 资产换为 20degs9ei54gw.css、计算样式 dockBody=none / stageRail 43px nowrap / legend bottom=172px、三档叠字与溢出全 0 | UI 修复确已上线生效

## 不要重复
- N-0001 | 测量与时序纪律：量压叠必须实机量、剔除被 overflow 裁掉的、并用 elementFromPoint 区分「叠字」与「正常遮挡」；不要看降尺寸截图或 0×0 视口；不要在 React 提交前同步读 DOM 断言；e2e 不要在页面 hydrated 之前填表单
- N-0002 | 不要把心跳/日志放在只覆盖部分退出路径的位置：曾漏掉「无新增」那条，恰是最需要的
- N-0003 | CI 自检会拦的两件事：改 EEI 内容后必须按顺序重生成两个清单；测试里不要写 PEM 头字面量（secret_scan 会正确拦下）
- N-0004 | 不要在主树里跑 next build/typecheck：会生成 next-env.d.ts 脏改动，锁死整仓并行
- N-0005 | 不要把画布控件的 z-index 提到图谱之上：图谱 svg 是 z-index:3 且 pointer-events 精心分配过，抬高条带会让条带截胡节点点击
- N-0006 | 不要用 overflow-x:hidden 让溢出计数归零：那是遮丑不是修
- N-0007 | 不要为了「OVH 降级为缓存」去删 postgres 里的事实：线上 D1 是从 postgres 发布的，删了等于把内容从产品里删掉
