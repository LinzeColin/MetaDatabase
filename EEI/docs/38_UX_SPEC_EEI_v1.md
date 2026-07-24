# EEI「商域图谱」UX 重构规格 v1.0

- 日期:2026-07-23 | 作者:UX 研究员(admin 委托) | 性质:纯规格,未改任何代码
- 产品:https://eei.linzezhang.com | 代码基线:`/Users/linzezhang/Documents/Codex/GithubProject/MetaDatabase/EEI`(主树只读参考;实施须走 worktree)
- 前端:`apps/web/src/app/`(Next.js 16 静态导出 + Tailwind 4 + 自有 globals.css 设计系统)
- API:`apps/cloudflare-public/src/worker.mjs`(Cloudflare Worker + D1,`/v1/*`,共 21 个端点,见附录)
- 数据现实(2026-07-23 线上实测 `/v1/publication/meta`、`/v1/supply-chain/overview`):9,635 实体、3,044 关系(集团结构/控制/董监高为主)、13,103 事件(SEC filing);供应链覆盖 2/16 阶段;并购/信号/政策数据极少(采集器在建)
- 技术约束:栈不换;深空 + 金核/粒子/发光连接视觉语言保留并精炼(视频复刻批次 1+2 已上线,PR #62/#63)

---

## 0. 执行摘要 & Owner 原话逐条回应

Owner 原话:「目前一级入口都不能用,uiux太幼儿园了,对现有开源项目成熟系统做反向开源分析和调研,重构uiux反馈操作逻辑操作流程,确保动效质感,参考 http://motionsites.ai/」

| Owner 诉求 | 本规格回应 | 章节 |
|---|---|---|
| 一级入口都不能用 | 已定位代码级根因:左栏 18 项里 5 个「section 滚动按钮」在生产必死(目标元素在云模式根本不渲染,或滚动无任何视觉反馈,或从子页点击丢失目标只回首页),另有 2 对重复入口。方案:18 → 6 个一级入口 + 顶栏搜索 + 「我的」抽屉,每个入口点击必有可见响应 | §A、§G-P0-1 |
| uiux 太幼儿园 | 根因不是「简陋」而是「把内部治理调试台当了产品界面」:快照哈希、刷新代数、Budget、GAPS%、评分模型版本、状态机字符串全部直出给用户。方案:治理术语全量替换为用户语言,机器状态收进〈诊断详情〉;统一五态反馈规范 | §B、§E、§G-P0-2 |
| 反向分析成熟开源系统 | 已实读 OpenBB Workspace、Grafana(Saga 设计系统+grafana-ui 源码)、Neo4j Bloom(5 个子页)、Cytoscape.js、Linear(实测 CSS 变量拆解)、shadcn/Radix、Material 3,全部结论带 URL | §2 |
| 重构反馈/操作逻辑/操作流程 | 五态(加载/成功/失败/空/陈旧)统一规范 + 100ms 反馈规则;搜索优先进入流、图谱探索流、证据下钻流三条主流程 | §B、§C |
| 确保动效质感 | 动效 token 表(时长档位 + cubic-bezier 具体值,可直接落 CSS);太阳系 ambient 动画(金核 rays/粒子/光行进)保留,交互层遵守 Linear 纪律 | §D |
| 参考 motionsites.ai | 已实抓。定性:它是营销 landing page 的 hero 动效风格库("designed to convert, impress, amaze"),无 token 数值。其戏剧性语汇只用于首屏入场(600ms 预算内)与空态,图谱操作界面遵守工作软件纪律——两者不冲突,分层使用 | §2.5、§D |

一句话战略:**数据强区(实体/关系/事件)做深做爽,数据弱区(供应链/并购/信号)诚实收敛为「采集中」引导态;把已经很好的深空视觉资产从治理调试台里解放出来。**

---

## 1. 现状盘点(代码基线,全部实读)

### 1.1 路由与页面清单

| 路由 | 文件(相对 `apps/web/src/app/`) | 行数 | 现状 |
|---|---|---|---|
| `/` | `page.tsx` | 5,143 | 主工作台:4 列 grid(导航 210px + 左栏 220-260px + 画布 680px+ + 右栏 250-300px,`globals.css:111`,最小宽约 1450px,移动端不可用)。含太阳系 SVG 图谱、Ask 栏、语义缩放 L0-L3、年轴、证据栏 |
| `/structure` | `structure/page.tsx` | 279 | 集团结构五层(法律集团/板块/品牌/产品/设施),多层「无断言」空行 |
| `/supply-chain` | `supply-chain/page.tsx` | 246 | 16 阶段全量渲染,14 行空(线上实测 2/16 有数据) |
| `/capital` | `capital/page.tsx` | 593 | 事件河流 + 筛选 + 金额汇总 + 证据下钻——**全站数据最厚、最接近可用的模块**(13,103 事件) |
| `/ma` `/control` `/signals` | 各自 `page.tsx`(47/40/51)| 薄壳 | 共用 `family-module-page.tsx`(189 行):关系断言列表 + 「诚实边界」 |
| `/policy` | `policy/page.tsx` | 309 | 同族薄页 |
| `/industries` | `industries/page.tsx` | 344 | 硬编码三行业 taxonomy(英文数据),无 API |
| `/objects-scope` | `objects-scope/page.tsx` | 371 | 数据目录(10 catalogs)+ coverage + 导出;副标题英文直出(L266) |
| `/development-status` | `development-status/page.tsx` | 338 | 开发状态(验收 ID 等治理内容) |

共享件:`workspace-context.tsx`(325 行,16 个 `WORKSPACE_MODULES` 定义于 L74-248)、`workspace-navigation.tsx`(197 行,左栏)、`analysis-context-badge.tsx`(47 行,跨页快照徽章)、`globals.css`(3,619 行,双主题 token L14-63 + reduced-motion 总闸 L66-80)。

### 1.2 六个已复现缺陷的代码级根因

**缺陷 1|首页图谱节点标签压叠成一团字**(root cause 链,`page.tsx`):
- L1191-1205 `serverNodeZone()`:person(董监高)等实体类型无专属扇区,全部 fallback 到 `"upstream"` 一个扇区;
- L1220-1251 `layoutEmpireOrbits()`:同扇区 n 个节点按 `spreadDeg = min(30, max(16, 110/(n-1)))` 摊开——n≥8 时固定 16°/个,20 个节点摊满 320° 环绕整圈,侵入其他扇区;交错 +34px 半径(L1242)杯水车薪;
- L1281-1285 `serverNodeStage()` 返回 `"person / board governance"` 这类英文枚举拼接,L4585-4587 **给每个节点无条件渲染**在 y=52 处 → 十几个 person 节点 = 十几行重复的「person / governance people」;
- L4582-4592 每节点最多 3 层文本(shortLabel + stage + L3 时 role),**零碰撞检测、零分级显示**;viewBox 仅 760×480(L4355)。

**缺陷 2|治理/调试信息漏给最终用户**:
- `page.tsx` L3198-3231 左栏 `subjectStats`:「数据快照 global:live:job:5d75a0e7」「评分模型 balanced-v2@2」「Budget 12/11」(= `graphViewNodes.length/graphViewEdges.length`,L3209-3211)「上下文刷新代 第 24 代」(线上实测 refresh_generation=24);
- L4194-4200 图例上的「GAPS 88% · 14/16 阶段无断言」徽章;
- L4150-4177 `context-kpi-bar` 显示「候选/来源/评审/发布」——治理流水线 KPI,不是业务 KPI;
- `analysis-context-badge.tsx` L34-44:「快照 global:live:job:5d75a0e7」「server · gen 24」「fixture 回退」,**每个子页都渲染**;
- L4667/L4672/L4676 右栏节点卡直出 zone/stage/role 原始值:「upstream」「server focus entity」。

**缺陷 3|左栏 5 个死按钮 + 2 对重复**(`workspace-context.tsx` + `workspace-navigation.tsx`):
- 5 个 `controlKind:"section"` 模块(时间演变/证据中心/模型中心/我的关注/探索记录)点击走 `applyWorkspaceNavigationSection()`(`page.tsx` L2907-2912):`querySelector` + `scrollIntoView({block:"nearest"})`,**无高亮、无过渡、目标常在视口内 → 视觉零反应**;
- 「时间演变」的目标 `timeline-controls` 仅在非云模式渲染(L4109-4131 `!CLOUD_MODE ?`),**生产上 querySelector 返回 null,点击字面上什么都不发生**;
- 从子页点击这 5 项:`supply-chain/page.tsx` L53-57、`family-module-page.tsx` L67-71 的 `handleNavigation` 丢弃 section 目标,只 `window.location.href = "/"`;
- 重复:「数据中心」→ `/objects-scope` 与系统区「对象与范围」→ `/objects-scope`(`workspace-context.tsx` L204-215 vs `workspace-navigation.tsx` L85-93);「系统状态」→ `/development-status` 与「开发状态」→ 同页(L239-247 vs L94-102)。左栏实际 18 项。

**缺陷 4|供应链页 16 行 14 空 + 治理黑话**:`supply-chain/page.tsx` L151-210 全量渲染 16 阶段,空行只写「无断言(≠真实为空)」(L169-171);副标题「十六阶段全链轨道 — Owner 签核事实与演示数据分层呈现,绝不混同」(L75)。线上实测 `summary: 2/16 阶段有数据、published_fact_count=2`。

**缺陷 5|中英文混排随意**:枚举值用 `replaceAll("_"," ")` 直出(`page.tsx` L1281-1289):「person / board governance」「commercial dependency」;role 硬编码英文「server focus entity / server returned entity」(L1152);zone 原文「upstream」上屏(L4667);`objects-scope/page.tsx` L266 副标题英文;`industries/page.tsx` 整页数据英文;Ask 按钮「Ask」、GAPS、Budget 等混在中文界面。

**缺陷 6|空状态无引导**:`family-module-page.tsx` L133-137「图谱当前没有该族的已断言关系。缺席=无断言而非无关系——候选经双源核验与 Owner 签核后自动出现」——解释了内部流程,没告诉用户**已覆盖什么、可以去哪**;首页 `honestEmpty`(L3825/3864/3914/3959)同病;图谱空态 L4243-4247 同病。

### 1.3 已有资产(保留并复用,不推倒)

- **太阳系视觉语言**(Owner 已验收方向):金核 + 光芒 rays(`empireSunPulse/sunRaysSpin/sunRayShimmer`,`globals.css:801-837`)、travelling 粒子(`ambientDrift:1214`)、弯曲发光连接线(`curvedEdgePath`,`page.tsx:1271-1279`)、光沿路径行进(`edgeLightTravel:1200`)、节点扇出 stagger(`empireNodeFanOut:853`)、reroot 飞行(`empireRerootFly:863`)。
- 双主题 token 体系 + `data-theme` 防闪烁 + `prefers-reduced-motion` 总闸(`globals.css:14-80`)——正是 ADP 模式⑩的做法,别动。
- 语义缩放 L0-L3、年轴 `empire-history-scrubber`(目标观感 V3)、Ask 栏(V6)、reroot 面包屑(V8)、图例(V4)、KPI 条(V5)结构都在——**问题是往里灌的内容是治理数据,不是结构不行**。
- 证据三步链已通:`production-evidence-detail`(L4789-4845,snippet + locator + 官方源链接)、`capital/page.tsx` 的 `loadEvidenceDetail` 下钻。
- 图表替代视图 `graph-table-alternative`(L4883+,可访问性)、保存视图/冲突解决、e2e testid 契约(48 用例,重构须同步 `tests/`)。

---

## 2. 研究基线(全部实读,URL 为证)

### 2.1 OpenBB Workspace(金融工作站 IA)
读自 https://docs.openbb.co/workspace 及 analysts/apps、analysts/dashboards、widgets/overview、widgets/interacting-with-data、developers/json-specs/widgets-json-reference:
- IA 按「使用者角色 + 对象层级」组织,分析师侧核心对象只有 4 个:Widgets → Dashboards → Apps → AI。**一级对象种类 ≤4**。
- 首屏不给空白画布,给 Apps Gallery(预配置模板,"structured starting points")——**首屏回答「我能直接看什么」**。
- 每个 widget 自带刷新元数据:`refetchInterval`(默认 15 分钟)、`staleTime`(默认 5 分钟)、`dataUpdateDisplay`(刷新按钮 tooltip 显示上次/下次更新)。**刷新策略是数据卡片的元数据,且「数据何时更新」必须暴露**。
- 搜索(Cmd+K)= 添加内容的唯一路径;每个数据组件强制标注 Source(数据来源)。

### 2.2 Grafana(空态/骨架/错误分层)
读自 https://grafana.com/developers/saga/patterns/empty-state/、grafana/grafana 仓库源码 `utils/skeleton.tsx`、`LoadingBar.tsx`、`PanelStatus.tsx`、saga/components/alert/、https://grafana.com/docs/grafana/latest/dashboards/use-dashboards/:
- **空态三变体**:`call-to-action`(未创建:一句话 message + 主按钮,空态显示期间隐藏页头重复 CTA)、`not-found`(搜索无结果:message + 清筛选,动态出现时 `role="alert"`)、`completed`(已清空:"You're all caught up")。先判定空因再选变体。
- **加载指示延迟出现防闪烁**:skeleton 淡入 `delay 100ms + duration 100ms ease-in backwards`(100ms 内返回则用户看不到);LoadingBar 默认延迟 300ms 才动,1px 高、时长 500-4000ms;骨架与真组件一一同构(`<Component.Skeleton/>`)。
- **错误三层**:面板角标(红色小三角,tooltip 出错文,点开检查器,不打断全局)→ 区块内联 Alert(「标题永远必填、简洁、面向人、无术语」)→ 全局 toast(右上、自动消失)。
- **刷新不清屏**:旧数据保留可见,只在面板顶部走 LoadingBar;加载中可点击取消;默认不自动刷新,刷新间隔是用户可选项。

### 2.3 Neo4j Bloom + Cytoscape.js(图探索交互)
读自 https://neo4j.com/docs/bloom-user-guide/current/ 下 search-bar、bloom-scene-interactions、settings-drawer、legend-panel、card-list 五个子页;https://js.cytoscape.org/#style/labels;https://cambridge-intelligence.com/visualize-large-networks/;碰撞检测:UW IDL "FastLabels"(VIS 2021, https://idl.cs.washington.edu/files/2021-FastLabels-VIS.pdf,检索摘要):
- Bloom 自称 **"search-first environment"**:搜索栏是主入口(近自然语言 pattern + UI 命令 Actions:Fit to selection / Expand selection / Dismiss others / Undo / Redo)。空场景只给两个起点:样例片段或去搜索——**不一上来倒全图**。
- **展开防爆炸**:每次展开受 Node query limit 硬限;右键可按「关系类型+方向」选择性展开;入口两处(节点右键、详情面板邻居卡)。
- **聚焦=灰显不删除**;单击=选中,**双击才开 Inspector 详情面板**;回退靠全局 Undo/Redo;minimap 管大图定位。
- **标签策略**:节点文字随节点尺寸缩放;hover 才显完整标签;重要度(rule-based styling)决定节点大小、大小决定文字可见度。Cytoscape 的 `min-zoomed-font-size`:有效字号低于阈值整个标签不渲染。KeyLines adaptiveStyling:缩小时节点退化为色点,只有「足够大」的节点保留标签。
- **碰撞检测权威做法**:按优先级降序贪心占位 + 占用检测,O(n),放不下就不放(IDL);聚类折叠用 compound 父节点收合(cytoscape.js-expand-collapse)。

### 2.4 Linear + shadcn/Radix + Material 3(反馈时序与动效参数)
读自 https://performance.dev/how-is-linear-so-fast-a-technical-breakdown(含 Linear 线上 CSS 一手变量)、https://ui.shadcn.com/docs/components/skeleton、https://sonner.emilkowal.ski/toast、https://emilkowal.ski/ui/great-animations、https://www.radix-ui.com/primitives/docs/guides/animation、M3 token 表(m3.material.io JS 渲染直抓失败,数值取自引用文档并交叉验证):
- Linear 一手值:`--speed-highlightFadeIn: 0s`、`highlightFadeOut .15s`、`quickTransition .1s`、`regularTransition .25s`、`slowTransition .35s`。为什么快:乐观更新(本地先改、网络后台)、hover 即现慢出、列表行刻意不加 transition、键盘操作零动画。
- shadcn skeleton = `animate-pulse` 循环;sonner toast 默认停留 4000ms;Radix 范式:`data-state` 驱动 CSS 动画,入场 ease-out / 出场 ease-in,出场动画期间挂起卸载。
- M3 easing:standard `cubic-bezier(0.2,0,0,1)`、standard-decelerate `(0,0,0,1)`、standard-accelerate `(0.3,0,1,1)`、emphasized-decelerate `(0.05,0.7,0.1,1)`;时长分层 short 50-200 / medium 250-400 / long 450-600,长档只给全屏级。

### 2.5 motionsites.ai(Owner 指定参考)
实读 http://motionsites.ai/:定位是「AI 设计提示词库」,收录 300+ 带动效的营销 landing page(3D Portfolio、Web3 Hero、Fintech 等分类),口号 "Animated backgrounds designed to convert, impress, and amaze",**无 token 数值**。结论:它提供的是**首屏入场的视觉词汇**(戏剧性 hero、动态背景),不是工作界面节奏基准。EEI 用法:hero 级词汇只花在图谱首次入场编排(≤600ms 预算)与空态插画,操作层遵守 Linear 纪律。这与 Owner 已认可的太阳系入场(金核绽放+节点波次扇出)完全同族——**EEI 首屏本身就是一个 motionsites 级的 hero,已经有了,别再叠**。

### 2.6 本机基准(实读三文件)
- `~/.claude/projects/-Users-linzezhang-Documents-Codex/memory/project-adp-benchmark.md`:ADP 十模式为验收对照——①首屏即答案 ②决策透明 ③敢于弃权 ④证据三步可溯源 ⑤唯一有效行为闭环 ⑥回执文化 ⑦诚实降级 ⑧结论先行 ⑨来源全透明 ⑩轻前端极速(六主题 CSS 令牌/防闪烁/44px 触控/中文优先)。EEI 现状④⑦⑨已达,①⑧被治理信息污染,⑩桌面 ok 移动为零。
- `.../reference-eei-target-experience.md`:目标观感十要素 V1-V10(深空画布/徽章/时间轴刷/图例即库存/上下文 KPI/Ask 栏/洞察卡/问答即 reroot/聚焦展开卡/右侧详情卡)。V1/V3/V4/V5/V6/V8 结构已在,V2(百分比徽章)/V7(洞察卡)/V9(分类展开卡)/V10(状态 pill 详情卡)未达或内容错灌。
- `.../project-eei-video-replica.md`:视频复刻批次 1+2 已上线(弯曲发光连接/光行进/travelling 粒子/金核 rays),**视觉语言核心元素已齐**;剩余(autoplay 相机序列、紫罗兰焦点核)被 Owner 决策门挡住,本规格不越权安排。

---

## A. 信息架构重构:18 项 → 6 个一级入口 + 搜索 + 「我的」

### A.1 收敛原则
1. OpenBB:一级对象 ≤4 类(EEI 取 6 个入口,因图谱/结构/事件三类数据形态确实不同);
2. 按数据厚度排序:强区(实体/关系/事件)占前排,弱区(供应链/信号/政策)合并降级为「采集中」态;
3. Bloom:搜索是入口不是功能;证据/关注/历史是**随身面板**不是页面;
4. 每个入口首屏必须回答一个用户问题(ADP 模式①⑧)。

### A.2 新一级结构

| # | 入口(全中文) | 路由 | 首屏回答的问题 | 首屏内容(结论先行) | 数据支撑 |
|---|---|---|---|---|---|
| 1 | 商业版图 | `/` | 「这家公司的生态长什么样?」 | 太阳系图谱(中心实体 + 分区关系)+ 右栏实体卡;**未选实体时 = 搜索起始页**(大搜索框 + 3 个行业入口卡 + 热门实体),不是空图 | 9,635 实体 / 3,044 关系 |
| 2 | 集团与控制 | `/structure` | 「谁控制谁?董监高是谁?」 | 焦点公司控制树 + 董监高名单 + 控制路径;吸收现「业务板块」(锚点)与「控制关系」(同一问题域,数据同为 corporate_structure/ownership_control/board_governance 三族) | 关系数据主体 |
| 3 | 资本与事件 | `/capital` | 「最近发生了什么?涉及多少钱?」 | 事件河流(时间倒序)+ 金额汇总 + 类型筛选;「并购交易」并入为事件类型筛选片(M&A 本质是 event_type 子集) | 13,103 事件,全站最厚 |
| 4 | 供应链 | `/supply-chain` | 「上下游依赖是什么?」 | 覆盖横幅(2/16)+ 仅已覆盖阶段的关系卡 + 「采集中」折叠区(见 §E.2 模板) | 2/16,诚实引导态 |
| 5 | 外部信号 | `/signals` | 「政策与战略动向有什么?」 | 政策环境 + 战略信号两 tab 合并(都是「外部环境对公司的作用力」,现都是薄数据) | 少,引导态 |
| 6 | 数据与来源 | `/data`(新)或沿用 `/objects-scope` | 「数据从哪来、多新、覆盖多少?」 | 来源清单(SEC/GLEIF)+ 每目录覆盖数 + 最近刷新时间;吸收「对象与范围」「开发状态」「系统状态」「模型中心」(诊断向内容全部归这) | catalogs + freshness API 已有 |

**顶栏(所有页共享,新增)**:全局搜索(`Cmd+K`,见 §C.1)| 「我的」抽屉按钮(关注 + 保存视图 + 探索记录,API `/v1/watchlists` `/v1/saved-views` `/v1/exploration-log` 已有)| 主题切换。

### A.3 旧 16+2 项去向逐条裁定

| 现模块(`workspace-context.tsx` L74-248) | 裁定 | 去向 |
|---|---|---|
| 商业版图 | 保留 | 入口 1 |
| 集团结构 | 保留 | 入口 2 |
| 业务板块(`/structure#segments`) | 合并 | 入口 2 内锚点/卡片,不占一级 |
| 供应链 | 保留改造 | 入口 4 |
| 资本网络 | 保留 | 入口 3 |
| 并购交易(`/ma`) | 合并 | 入口 3 的事件类型筛选片;旧 URL 重定向 `/capital?event_type=ma` |
| 控制关系(`/control`) | 合并 | 入口 2 的「控制路径」区块;旧 URL 重定向 |
| 政策环境(`/policy`) | 合并 | 入口 5 tab;旧 URL 重定向 |
| 战略信号 | 保留改造 | 入口 5 |
| 时间演变(死按钮) | **砍一级入口,做成画布控件** | 年轴 `empire-history-scrubber` 已在画布右缘;时间是图谱的维度,不是页面 |
| 证据中心(死按钮) | **砍一级入口,做成全局右栏** | 右栏 inspector 已存在(`page.tsx` L4649+);任何数字点开即达(§C.3),不需要「去一个页面」 |
| 模型中心(死按钮) | 砍一级入口 | 归入口 6 的「评分与模型」区块(治理工具,非日常) |
| 数据中心(与「对象与范围」重复) | 合并 | 入口 6 |
| 我的关注(死按钮) | **移出导航,做成顶栏抽屉** | 关注是随身面板;铃铛角标显未读(`/v1/changes` 未读计数逻辑已有,`workspace-context.tsx` L217-227 注释) |
| 探索记录(死按钮) | 移出导航 | 面包屑(已有)+「我的」抽屉历史 tab |
| 系统状态(与「开发状态」重复) | 合并 | 入口 6 的「系统健康」区块 |
| 系统区「对象与范围」「开发状态」 | 删除 | 与上重复项一并消失 |

死按钮处理总原则:**5 个 section 按钮全部消灭——不是修好滚动,而是承认「滚动到首页某段落」根本不配做一级导航**。P0 先从导航移除并保住功能可达(右栏/抽屉/入口 6),P2 做旧 URL 重定向。

### A.4 导航渲染规则(替代现 `controlKind` 四态)
- 只允许两种项:route(点击 = URL 变化)和 drawer(点击 = 抽屉滑出)。**禁止再出现点击无视觉变化的导航项。**
- 数据弱的入口不禁用、不隐藏:正常可点,进去是「采集中」引导态(§B 空态-a)。灰色死按钮是最差解(现 `workspace-navigation.tsx` L182-195 的 `disabled` 渲染分支删除)。
- 当前页高亮:左缘 2px 金色指示条 + 图标着色(现仅 className `active`,视觉太弱)。

---

## B. 反馈与操作逻辑:五态统一规范 + 100ms 规则

### B.1 五态规范(全站唯一标准,落成共享组件,见 §G-P1-6)

| 态 | 规范 | 参数(出处) |
|---|---|---|
| **加载 loading** | 首次加载:与真实内容**同构**的骨架屏(卡片位出卡片骨架、表格位出行骨架),禁全屏 spinner。**延迟 100ms 出现**(快速返回则完全不见);刷新(已有旧数据):**不清屏**,区块顶部 1px 进度条,延迟 300ms 出现;>10s 提供「取消」 | Grafana skeleton `delay 100ms/duration 100ms ease-in backwards`;LoadingBar delay 300ms、高 1px、时长 500-4000ms;「旧数据保留可见」 |
| **成功 success** | 界面直接呈现结果即是反馈(乐观更新:本地状态先变、网络后台);**只有用户看不见的后台完成**(保存视图同步、导出完成)才用 toast,4s 自动消失、可手关;禁「操作成功」弹层打断 | Linear 乐观更新;sonner 默认 duration 4000ms |
| **失败 error** | 三层分级:①卡片级 = 角标(琥珀/红点 + tooltip),不打断其他区块;②区块级 = 内联 Alert:**标题必填、人话、无术语**,正文 = 出了什么 + 你能做什么,右侧「重试」按钮;③全局级(网络断)= toast。**错误码/reason 字符串一律收进〈诊断详情〉折叠**,现 `family-module-page.tsx` L120「加载失败(unknown)」这种直出禁止 | Grafana PanelStatus 三层;Saga Alert「简洁、面向人、无术语」 |
| **空 empty** | 四变体,先判空因再选型(§E.2 有文案模板):a)**采集中**(EEI 特有主力态:数据管道未覆盖)= 覆盖事实 + 管道说明 + 可做动作;b)无结果(搜索/筛选)= 说明 + 「清除筛选」;c)未创建(关注列表)= 一句话 + 主 CTA;d)无新变化 = 「已看完」。空态显示期间隐藏页头重复的同名 CTA | Grafana empty-state 三变体 + EEI 数据现实加第四种 |
| **陈旧 stale** | 每个数据卡右上角常显「更新于 MM-DD HH:mm」(现有 `as_of`/`activated_at` 字段直接用);超过模块级 `staleTime` 显示琥珀点 + 「数据可能滞后」;刷新按钮 tooltip 显示上次/下次刷新时间。模块级元数据建议:图谱/结构 24h、事件 6h、目录 7d | OpenBB `staleTime` 默认 5min、`dataUpdateDisplay`;EEI 数据节奏放宽 |

### B.2 100ms 反馈规则(每个用户操作)

| 时刻 | 必须发生什么 |
|---|---|
| 0ms(按下) | 可点元素即时进入 pressed 态(`:active` scale 0.97 或亮度变化,CSS 原生,无 JS 延迟);键盘触发的操作**零动画直接生效** |
| ≤100ms | 状态可见变化:按钮进入 busy(禁二次点击)、选中行高亮、导航项高亮切换、面包屑追加。**做不到 100ms 内给真结果的,先给乐观状态** |
| 100-300ms | 若还没结果:骨架屏此刻淡入(=Grafana 延迟策略,快请求全程无闪烁) |
| ≥300ms | 区块顶部进度条出现;Ask/搜索类显示「正在查询…」行内文本 |
| 失败任何时刻 | pressed/busy 态回滚 + 对应层级错误反馈(§B.1) |

现状违规点举例:section 导航点击零反馈(缺陷 3);`serverReroot` 固定 `setTimeout 360ms`(`page.tsx` L2863-2880)假装加载——改为真实请求状态驱动 + 立即面包屑追加(乐观)。

---

## C. 操作流程(三条主流程,精确到屏)

### C.1 搜索优先进入流(Bloom "search-first" + OpenBB Cmd+K)
```
任意页 Cmd+K / 点顶栏搜索 / 首页中央大框
→ 输入 ≥2 字符,防抖 150ms → GET /v1/entities?q=(worker.mjs L1258-1264 已有,q 必填)
→ 下拉即时结果:按类型分组(公司/人/设施),每组前 5,高亮匹配段;↑↓ 选择,Enter 确认
→ 无结果:『没找到「X」。试试英文注册名或股票代码(如 NVIDIA、TSM)。』+「查看数据覆盖范围」链接(入口 6)
→ 选中实体 → 跳 / 并 POST /v1/explore/reroot(L1284)→ 画布以其为中心绽放入场
→ 落地首屏 = 图谱 + 右栏实体卡:名称/类型/「本图 N 家实体 · M 条关系」/最近 3 条事件
→ 右栏三个下一步按钮:展开关系(→C.2)| 查看结构(→/structure?entity=)| 查看事件(→/capital?entity=)
```
现状差距:搜索埋在左栏第 8 区块(`home-global-search`,L3742),Ask 栏只匹配**图内**节点、否则跳 ChatGPT(L4026-4058)——保留 Ask 的 ChatGPT 逃生舱,但实体查找主路径必须走全局搜索;`/industries` 静态页改造为首页未聚焦态的三张行业入口卡。

### C.2 图谱探索流(聚焦/展开/回退,Bloom 骨架)
- **单击节点** = 选中:右栏详情卡即时更新(0ms,数据已在内存),节点 selected 光环 + 邻域高亮(`hoverNeighborhood` 已有);**不移动相机**。
- **双击 / 右栏「以此为中心」** = reroot:面包屑立即追加(乐观)→ `/v1/explore/reroot` → `empireRerootFly` 相机过渡(已有)→ 新图节点波次扇出(`empireNodeFanOut` 已有)。URL `?subject=` 同步(已有 `WORKSPACE_QUERY_KEYS`)。
- **展开** = 右栏「展开上游/下游」(`node-action-upstream/downstream` 已有,走 `/v1/explore/expand`,预算 `expand_nodes:12`,L566):新增节点带 stagger 入场并**短暂金边呼吸 2 次**标识新来者;超预算返回时渲染聚合节点「+N 家」(aggregateCount 机制已有),点击开成员列表(`group-list` 已有)。**每次展开 ≤12 个是防爆炸特性,UI 要说明**:「已展开 12/37,点击查看其余」。
- **聚焦** = 「只看相关」:非邻域节点灰显 40% 不可点(faded 机制已有),Esc 或空白处单击恢复。**灰显不删除**(Bloom)。
- **回退**三通道:面包屑点任意层(已有)| 「返回」按钮(`app-back` 已有)| 浏览器 Back(URL 持久化已有)。P2 补 Undo/Redo 栈与 minimap(Bloom 完整骨架)。

### C.3 证据下钻流(任何数字 → 官方来源,ADP 模式④)
```
规则:凡呈现「事实」的元素(关系边/事件行/金额/结构行)hover 出现「查证」图标,点击 →
右栏证据卡三段式:
  ① 结论:「NVIDIA —[供应商]→ TSMC」(人话关系句)
  ② 摘录:evidence snippet + 定位(「10-K 第 42 页 / Exhibit 21」,evidence-locator 已有 L4831)
  ③ 官方源:「查看 SEC 原文 ↗」新窗口(evidence-source-link 已有 L4838)
超时/无证据:该数字不渲染为可点(禁裸下钻死链)
```
现状:链路已在首页与 `/capital` 打通,**推广到 structure/supply-chain/signals 每一行**;右栏证据卡从「治理契约展示」(status/count 字段直出,L4794-4818)改为上述三段式,契约字段进〈诊断详情〉。

---

## D. 动效体系

### D.1 动效 token 表(落 `globals.css` `:root`,全部可直接用)

| Token | 值 | Easing | 用途 | 出处 |
|---|---|---|---|---|
| `--motion-instant` | 0ms | — | hover 高亮出现、键盘操作、乐观更新数据变化 | Linear `highlightFadeIn: 0s` |
| `--motion-fast` | 100ms | `--ease-standard: cubic-bezier(0.2,0,0,1)` | 按下反馈、开关/pill 变色、tab 切换 | Linear `quickTransition .1s`;M3 standard |
| `--motion-base` | 180ms | 入场 `--ease-out: cubic-bezier(0,0,0,1)`;出场 `--ease-in: cubic-bezier(0.3,0,1,1)` | hover 退出淡出、tooltip/popover/toast 出入场 | Linear `.15s` 档;M3 decelerate/accelerate 配对(现 css 已多用 180ms,顺势标准化) |
| `--motion-slow` | 280ms | `--ease-emphatic: cubic-bezier(0.05,0.7,0.1,1)` | 抽屉/dialog、右栏卡切换、图谱局部重排 | Linear `regularTransition .25s`-`slowTransition .35s` 区间;M3 emphasized-decelerate |
| `--motion-entrance` | 480ms | `--ease-emphatic` | 仅:图谱首次入场、reroot 相机、空态插画入场 | M3 long 档给全屏级;现 reroot 360ms 可上调对齐 |
| `--motion-ambient` | ≥2s 无限循环 | linear / ease-in-out | 金核 rays(90s)、粒子(14-18s)、skeleton 脉冲(2s)——**现有值保留** | shadcn `animate-pulse`;M3「linear 只准给不定态」;`globals.css` 现值 |

### D.2 各组件动效参数

| 组件 | 参数 |
|---|---|
| hover(卡/行/节点) | 进入 0ms 即现;离开 150ms `--ease-out`;只动 opacity/box-shadow/亮度,**列表行与表格行不动 transform、不加 transition**(Linear 纪律) |
| 按下 | 100ms `scale(0.97)`,松手即回;仅按钮/节点,不给行 |
| tooltip/popover | 入 180ms `--ease-out`(opacity + translateY 4px);出 150ms `--ease-in`;Radix `data-state` 范式 |
| 抽屉(「我的」/诊断) | 入 280ms `--ease-emphatic` translateX;出 200ms `--ease-in`;背景遮罩同步 opacity |
| toast | 入 180ms、停 4000ms、出 150ms(sonner 默认) |
| 骨架屏 | 出现延迟 100ms,淡入 100ms ease-in backwards;脉冲 2s 循环 |
| 页面/视图切换 | 180ms opacity(+ ≤8px 位移),入 decelerate 出 accelerate;内容先渲染,动画不阻塞交互 |
| 图谱入场 stagger | 单节点 220ms `--ease-emphatic`(opacity + scale 0.85→1),项间 delay 40ms,**总编排封顶 600ms**(`empireNodeFanOut` 已有,校参数);金核 rays/粒子照旧 ambient |
| reroot | 面包屑即时 → 相机 `empireRerootFly` 480ms → 新节点 stagger(≤600ms)→ 右栏信息卡最后入 200ms(「面板在图建立上下文后进入」,视频复刻 DESIGN_SPEC 分层运动第 6 条) |
| 展开新增节点 | stagger 入场 + 金边呼吸 2 次(2×600ms)后归常态 |

### D.3 不做什么(禁华而不实清单)
1. 键盘触发的一切操作零动画(Emil Kowalski/Linear);
2. 列表/表格行不加 transition,虚拟滚动区零动画(Linear);
3. 数据刷新**不重放**入场 stagger(入场只属于首次与 reroot);
4. 能乐观更新就不出 spinner;spinner 仅作 >300ms 的兜底且延迟出现;
5. 高频小交互禁用 emphasized 慢曲线(100ms 尺度会感知为卡,M3);
6. 工作区一切交互动画 >300ms 一律砍,400ms+ 只属于 entrance 档;
7. 纯装饰淡入删除——动画必须做「空间工作」(说明元素从哪来);
8. motionsites 式动态背景不进操作区(只许首屏/空态);视差滚动、3D 翻转、元素跨屏飞行、全屏转场,全禁;
9. SVG 滤镜只给焦点束、不给全图(A168 性能纪律,已有,继续守);
10. `prefers-reduced-motion` 总闸已有(`globals.css` L66-80),新增动效必须挂在 token 上自动受控。

---

## E. 文案体系

### E.1 治理术语 → 用户语言对照表(渲染层替换;API 字段与 e2e data-* 契约不动)

| 现状(位置) | 改为 | 备注 |
|---|---|---|
| `Budget 12/11`(`page.tsx` L3208-3211) | 本图 12 家实体 · 11 条关系 | Budget 概念不出现 |
| `数据快照 global:live:job:5d75a0e7`(L3200) | 数据版本 2026-07-16 | 完整 key 收进〈诊断详情〉 |
| `评分模型 balanced-v2@2`(L3204) | (从首屏删除) | 收进〈诊断详情〉 |
| `上下文刷新代 第 24 代`(L3215) | 更新于 07-17 05:50 | 用 `activated_at`,代数收诊断 |
| `GAPS 88% · 14/16 阶段无断言`(L4194) | 供应链覆盖 2/16 环节 | 正着说覆盖,不说 GAP 黑话 |
| KPI 条「候选/来源/评审/发布」(L4150-4177) | 实体 · 关系 · 事件 · 来源(业务量) | 治理流水线 KPI 收入口 6 |
| `无断言(≠真实为空)`(supply-chain L170) | 采集中 — 暂无已核实数据 | |
| `Owner 签核事实与演示数据分层呈现,绝不混同`(L75) | 只展示经官方文件核实的事实 | |
| `已发布 · Owner 签核`(family L157) | 已核实 · 官方来源 | |
| `fixture 演示`(family L161) | 示例数据 | |
| `需要连接 EEI API — 本模块不用合成数据充数`(family L110) | 暂时连不上数据服务,请稍后重试 + [重试] | |
| `server · gen 24` / `fixture 回退`(badge L38-43) | 实时数据 / 示例模式 | 徽章整体缩为一枚小 pill |
| `server focus entity` / `server returned entity`(L1152) | 当前中心 / 关联实体 | |
| `person / board governance` 等枚举直出(L1281-1289) | 董事/高管、公司、设施…(映射表) | **废除 `replaceAll("_"," ")` 直出** |
| zone 原文 `upstream` 上屏(L4667) | 上游 / 下游 / 资本 / 政策 / 业务 / 设施 | |
| `候选经双源核验与 Owner 签核后自动出现`(family L135) | 新数据核实后会自动出现在这里 | |
| `本站仅呈现经双源核验与 Owner 签核发布的事实…`(L3627) | 本站只展示有官方文件依据的事实(每条可点开查来源) | |

落地方式:新建 `apps/web/src/app/labels.ts`——`ENTITY_TYPE_LABELS` / `RELATIONSHIP_FAMILY_LABELS` / `RELATIONSHIP_TYPE_LABELS` / `ZONE_LABELS` / `STATUS_LABELS` 五张映射表 + `zhLabel(kind, value)` 兜底(未知值显示原文并上报 console.warn,不 throw)。现 `zhStatus()`(page.tsx 已有)并入。

### E.2 空状态文案模板(诚实但有引导)
结构强制三段:**[什么没有] + [为什么/事实覆盖] + [你可以做什么]**。禁止:无依据的上线日期承诺、内部流程解释(双源/签核/候选队列)、「≠真实为空」这类逻辑学措辞。

- 采集中(a 型,供应链/信号/政策):
  > **供应链数据采集中**
  > 已核实 2/16 个环节(设计、制造)。数据来自 SEC 年报供应商披露,采集器扩展中。
  > [查看已覆盖环节] [关注这家公司,有新数据时提醒我]
- 无结果(b 型,搜索/筛选):
  > 没有符合「2024 年 + 并购」的事件。 [清除筛选] [查看全部 13,103 条事件]
- 未创建(c 型,关注列表):
  > 还没有关注任何公司。在图谱中选中实体后点「关注」,变化会在这里汇总。 [去图谱看看]
- 无新变化(d 型):
  > 自上次查看以来没有新发布。上次数据更新:07-17。
- 图谱空态(现 L4243「该主体暂无已发布关系」):
  > **NVIDIA 目前没有已核实的关系数据**
  > 数据库覆盖 9,635 家实体、3,044 条关系,持续扩充中。
  > [换一家公司] [查看数据覆盖范围]

### E.3 中英文使用规则
1. 界面 chrome(导航/按钮/状态/提示)一律中文;
2. 专名保留原文:公司法定名(NVIDIA Corporation)、人名、SEC 表格号(10-K、8-K、DEF 14A)、GLEIF/LEI;法律术语首次出现「中文(原文)」;
3. 一切枚举值必须过 `labels.ts` 映射后上屏,**禁止任何 `replaceAll("_"," ")` 直出**;
4. 日期 `YYYY-MM-DD`,时间 24 制;金额千分位 + 币种前缀(USD 1.2 亿另起规则:≥1 亿用「亿」,≥1 万用「万」);
5. 按钮动词化中文:「Ask」→「提问」、「Fit」→「回正视图」;
6. data-testid / data-* 契约属性是机器接口,保持英文不受本节约束。

---

## F. 图谱标签防压叠(四层策略,按优先级实施)

### F.1 聚合优先(治本,消灭 90% 压叠源)
- 规则:同 zone 同 entity_type 节点数 >5 → 折叠为一个聚合节点「董事/高管 ×14」(**机制已有**:`aggregateCount` L4545/4583、`systemMakersGroup`、`group-list` L5101,只差把 server 图的 person 群接进来);
- 点击聚合节点 → 右栏成员列表(可逐个「上图」或「以此为中心」),或 L3 缩放下就地扇出;
- 出处:Bloom Group nodes / cytoscape.js-expand-collapse(compound 收合 + meta-edge)。
- 同时修 `serverNodeZone()`(L1191-1205):person + board_governance 给专属「治理」扇区(不再挤 upstream);`layoutEmpireOrbits()`(L1220-1251)删除 16° 下限环绕逻辑——**任何扇区超 5 个必聚合,布局函数永远只摆 ≤5 个**;三条轨道半径 118/182/246 按节点 priority 分环。

### F.2 分级显示(semantic zoom,机制已有 L0-L3,补标签语义)
- priority = evidenceCount(已有字段)优先,次选 degree;
- L0:只显示 focus + 聚合节点标签;L1:+ priority top 10;L2:top 50 经碰撞裁剪;L3:全量经碰撞裁剪;
- hover / 选中 / focus 节点的标签**任何级别必显**;
- 出处:Cytoscape `min-zoomed-font-size`(有效字号低于阈值整标签不渲染)、KeyLines adaptiveStyling(小节点退化为色点)、Bloom(hover 才给全名)。

### F.3 贪心碰撞裁剪(兜底)
- 时机:布局变更 / 缩放级切换后 debounce 100ms 跑一次(纯计算,不进渲染热路径);
- 算法:按 priority 降序遍历,标签 AABB 估算(宽 ≈ 字符数 × 7.2px @ 12px 字号,CJK ×13px;高 16px),与已放置矩形数组求交,相交则该标签 `display:none`(节点本体照常);≤200 节点线性扫足够,超千节点换占用位图;
- 出处:UW IDL FastLabels(VIS 2021):优先级贪心 + 占用检测,O(n),「放不下就不放」。

### F.4 渲染修正(直接删压叠来源)
- stage 文本(L4585-4587,「person / board governance」重复十几次的直接元凶)**从常显改为 hover tooltip**;role 文本(L4588-4592)删除,内容归右栏详情卡;
- shortLabel 截断从 22 字符收紧到 14 字符 + `…`(L1291-1295);
- 所有 SVG 文本加 `paint-order: stroke` + 2px 深空底色描边(或半透明垫片),禁裸文字叠星空(Cytoscape `text-outline-*` 惯例);
- 边标签(L4513-4526)同样纳入 F.3 裁剪,L0/L1 只显 focus 相邻边标签。

### F.5 验收
- Playwright:NVIDIA 默认图 + 任一 reroot 图,程序化断言任意两个可见 `<text>` 的 bbox 相交面积 = 0;
- 主观口径:L1 缩放下可读标签 ≤12 个;任何视图下不存在重复的类型说明文字;
- 视觉基线走 A167 CI 重录。

---

## G. 实施计划(P0 本周 = 能不能用;P1 = 好用;P2 = 精)

> 实施纪律:每项一个 worktree 小 PR(铁律 2/3);e2e testid 契约变更须同步 `tests/`;A167 视觉基线重录;A168 性能纪律(滤镜只给焦点束);reduced-motion 回退必测。

### P0(本周,四项,直接决定「能不能用」)

**P0-1 导航收敛:18 项 → 6 入口 + 顶栏搜索位 + 「我的」占位**
- 动:`apps/web/src/app/workspace-context.tsx`(重写 `WORKSPACE_MODULES` 为 6 项 route 型;删 `section`/`planned` controlKind)、`workspace-navigation.tsx`(删 L83-103 systemNav 重复区、删 L166-195 section/disabled 渲染分支;当前页金色指示条)、`page.tsx` L2901-2912(删 section 处理器)、各子页 rail 调用点、`tests/` 中 `main-nav-*` 相关用例。
- 验收:左栏无任何点击后无可见变化的项(Playwright 遍历每个 nav 项断言 URL 变化或抽屉出现);旧路由 `/ma` `/control` `/policy` 暂保留可直达(P2 才做跳转);`workspace-context-contract` data-* 同步更新。

**P0-2 治理术语清场(§E.1 全表)**
- 动:`page.tsx`(L3198-3231 subjectStats 重写、L4150-4177 KPI 条换业务量、L4194-4200 GAPS 徽章改覆盖、L4667-4682 节点卡走映射、L3260-3350 模型面板整体默认折叠为〈诊断详情〉——该模式 L3260 注释已开头做了,推广到底)、`analysis-context-badge.tsx`(重写为一枚小 pill:「实时数据 · 更新于 07-17」)、`family-module-page.tsx`、`supply-chain/page.tsx`、`structure/page.tsx` 文案位;新建 `apps/web/src/app/labels.ts`。
- 验收:构建产物可见文本 grep 断言不出现:`Budget|GAPS|快照 global|gen |签核|断言|fixture|candidate|balanced-v2|刷新代`;〈诊断详情〉展开后旧信息仍在(e2e 契约保留);全站可见枚举 0 个下划线英文。

**P0-3 标签防压叠(§F.1 聚合 + F.2 分级 + F.4 渲染修正;F.3 裁剪可延到 P1)**
- 动:`page.tsx` L1123-1295(节点管线:serverNodeZone 加治理扇区、layoutEmpireOrbits 超 5 聚合、priority 字段)、L4530-4595(渲染:stage 改 tooltip、role 删、标签描边、分级显隐)、`globals.css`(标签描边样式、聚合节点样式)。
- 验收:§F.5 三条(bbox 零相交断言 + L1 标签 ≤12 + A167 重录)。

**P0-4 空状态与供应链页改造(§B 空态 + §E.2 模板)**
- 动:`supply-chain/page.tsx`(16 行全量 → 覆盖横幅「已核实 2/16 环节」+ 仅有数据阶段的关系卡 + 「其余 14 个环节采集中」单条折叠区)、`family-module-page.tsx` L133-137(a 型模板)、`page.tsx` L4238-4252(图谱空态)、首页 4 个 `honestEmpty`(L3825/3864/3914/3959)。
- 验收:每个空态含三段(事实覆盖 + 原因 + 可点的下一步);供应链页首屏不再出现 14 行空行;文案对照 §E.2 逐条 diff。

### P1(下周,四项)

**P1-5 全局搜索 Cmd+K + 首页搜索优先首屏(§C.1)**
- 动:新建 `apps/web/src/app/components/command-search.tsx`(Portal + 键盘导航,`/v1/entities?q=` 已够用);`page.tsx` 首页未聚焦态改为大搜索框 + 三张行业入口卡(素材取自 `industries/page.tsx`,该页随后由入口卡替代);顶栏挂载到所有子页。
- 验收:任意页 Cmd+K 唤起;输入→结果 ≤400ms(含防抖);Enter 落地图谱且面包屑正确;无结果态含 b 型文案。

**P1-6 五态统一组件库(§B.1)**
- 动:新建 `apps/web/src/app/components/feedback.tsx`(`Skeleton`(同构变体)/`EmptyState`(四变体)/`ErrorState`(三层)/`StaleBadge`/`TopLoadingBar`);替换 `family-module-page.tsx`、`supply-chain`、`capital`、`structure`、`policy` 的手写状态块;骨架延迟 100ms/进度条延迟 300ms 按 Grafana 参数落。
- 验收:五个模块的加载/空/错渲染出自同一组件(截图对比一致);快速响应(<100ms)下无骨架闪烁(网络节流测试);刷新不清屏。

**P1-7 动效 token 落地(§D)**
- 动:`globals.css` `:root` 增 `--motion-*`/`--ease-*` 六 token;全文件手写 `180ms/260ms/300ms` 替换为 token 引用;交互层参数对齐 §D.2;`empireRerootFly` 时长对齐 480ms。
- 验收:`globals.css` grep 交互类 transition 全走 var();reduced-motion 下全灭(已有总闸回归测试);录屏主观验收 hover 即现慢出、无 >300ms 交互动画。

**P1-8 证据下钻全覆盖(§C.3)**
- 动:`page.tsx` 证据卡三段式重写(L4789-4850);`structure/page.tsx`、`supply-chain/page.tsx` 关系行接 `loadEvidenceDetail`(`capital/page.tsx` 已有样板,`production-data-client.ts` 复用)。
- 验收:图谱边/结构行/供应链关系/事件行四处均可 2 步内(点击→右栏)见到 摘录+官方链接;链接可打开 SEC/GLEIF 真 URL。

### P2(两周后,四项)

**P2-9 「我的」抽屉**:watchlist + saved views + 探索历史合并,顶栏铃铛未读角标(`/v1/watchlists` `/v1/saved-views` `/v1/exploration-log` `/v1/changes` 全部已有);验收:关注/取消关注乐观更新,断网回滚 + 错误反馈。
**P2-10 旧路由收编**:`/ma`→`/capital?event_type=ma`、`/control`→`/structure#control`、`/policy`→`/signals?tab=policy` 静态 meta-refresh 跳转页;`/industries` 退役为入口卡;验收:旧链接 0 死链。
**P2-11 响应式**:`globals.css:111` 4 列 grid 增 `<1280px` 断点(右栏变抽屉)与 `<768px` 断点(左栏变底部 dock,ADP 三导航之 dock;触控目标 ≥44px);验收:iPhone 视口核心流程(搜索→图谱→证据)可完成。
**P2-12 图谱骨架补全**:minimap、Undo/Redo 栈、「按关系类型展开」子菜单(Bloom 完整骨架);F.3 贪心裁剪若 P0 未做完在此收尾。

### 验收总对照(ADP 十模式 + 观感十要素)
- P0 完成 → ADP ①⑧(首屏即答案/结论先行,治理信息退场)恢复,⑦(诚实降级)从黑话变人话;观感 V4/V5 内容纠正。
- P1 完成 → ADP ⑤(唯一有效行为闭环:搜索→图→证据)、④③ 全链可演示;V9/V10(展开卡/详情卡)达标。
- P2 完成 → ADP ⑩(移动/触控)补齐;Bloom 骨架(Undo/minimap)补齐。

---

## 附录:Worker API 清单(`apps/cloudflare-public/src/worker.mjs` L1121-1448,规格所引用端点均已核实存在)

`GET /health` · `GET /v1/publication/meta` · `GET /v1/policy/overview` · `GET /v1/control/overview` · `GET /v1/ma/overview` · `GET /v1/signals/overview` · `GET /v1/entities?q=`(L1258,q 必填) · `POST /v1/explore`(L1266,budget/hops 有硬限 L25-26) · `POST /v1/explore/reroot`(L1284) · `POST /v1/explore/expand`(L1302) · `POST/GET /v1/saved-views` · `GET/POST /v1/watchlists` · `GET/POST /v1/exploration-log` · `GET /v1/cloud/runs`(+`/trigger`) · `GET /v1/scoring/active-context` · `GET /v1/supply-chain/overview`(L1403) · `GET /v1/changes?since=` · `GET /v1/events`(entity/theme/from/to/event_type/currency/amount_kind/limit 筛选,L932-983) · `GET /v1/events/amount-summary` · `GET /v1/meta/build`

事件筛选参数足以支撑 §A.2 入口 3 的「并购=筛选片”方案与 §C.1 的「查看事件」跳转,无需新端点;唯一建议的后端增量:`/v1/entities` 支持空 q 返回热门实体(P1-5 首屏热门位,可选,当前可用硬编码顶流实体代替)。

## 研究来源汇总(实读)
- OpenBB:docs.openbb.co/workspace(+analysts/apps、analysts/dashboards、widgets/*、developers/json-specs/widgets-json-reference)
- Grafana:grafana.com/developers/saga/patterns/empty-state/、saga/components/alert/、grafana/grafana 源码 skeleton.tsx/LoadingBar.tsx/PanelStatus.tsx、grafana.com/docs/grafana/latest/dashboards/use-dashboards/
- Neo4j Bloom:neo4j.com/docs/bloom-user-guide/current/(search-bar、bloom-scene-interactions、settings-drawer、legend-panel、card-list)
- Cytoscape.js:js.cytoscape.org(#style/labels、init 选项);cytoscape.js-expand-collapse(iVis-at-Bilkent);Cambridge Intelligence visualize-large-networks;UW IDL FastLabels(VIS 2021)
- Linear:performance.dev/how-is-linear-so-fast-a-technical-breakdown(一手 CSS 变量)
- shadcn/Radix/sonner:ui.shadcn.com/docs/components/skeleton、sonner.emilkowal.ski/toast、radix-ui.com/primitives/docs/guides/animation、emilkowal.ski/ui/great-animations
- Material 3:m3.material.io token 表(JS 渲染,数值经引用文档交叉验证)
- motionsites.ai:直抓成功(定位与分类见 §2.5)
- 本机:project-adp-benchmark.md、reference-eei-target-experience.md、project-eei-video-replica.md;EEI 代码与线上 API 实测(文中逐处标注文件:行号)
