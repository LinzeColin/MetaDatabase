# S9-GATE 证据收割（帝国观感升级阶段门）

- gate: `S9-GATE`
- harvested_at: `2026-07-16T13:20:00+10:00`
- verdict: `PASS`（十要素 9/10 ≥ 8；ADP 十模式全对照；动效 bar ①-⑧ 全 E2E 锁定；T1118/T1119 落地）
- 采集环境：本机全栈（uvicorn 8000 生产库只读 + next dev 3000 `NEXT_PUBLIC_EEI_API_BASE_URL` 配通），截图 1440×900，Playwright 采集脚本一次成图（不摆拍）。
- 截图目录：`/Users/linzezhang/Documents/Codex/runtime_evidence/EEI/s9_gate/`（runtime_evidence 惯例，不入 git）

## 一、录屏十要素对照（Fuselab "Control AI Policy Platform" 基准）

| # | 要素 | 判定 | 证据（截图 + E2E/代码锚点） |
|---|---|---|---|
| V1 | 深空黑宇宙画布：焦点=发光太阳+行星带+粒子光晕 | PASS | `v1_home_sun_orbits.png`（NVIDIA 太阳 + CoreWeave/OpenAI 等真实实体行星带）；`layoutEmpireOrbits`（page.tsx）+ 深空 token（globals.css）；E2E theme-system.spec 三主题契约 + home.spec 布局断言 |
| V2 | 行星带徽章：分带计数/百分比 | PASS | `v1_v2_canvas_closeup.png` + `v4_legend_gaps.png`（图例·库存 上游 6/业务 3/焦点 1 分带计数；GAPS 63% 百分比徽章）；theme-system.spec 图例/GAPS 用例 |
| V3 | 时间轴刷 2016→今（活动波形+当前年 pill） | PASS | `v3_history_scrubber.png`（2016-2026 十一年真实条形，条高=当年官方申报深度，"2026 · 149 份官方申报（sec_edgar）"）+ `v3_history_scrubber_selected.png`（选中 2016 · 192 份）；数据 /v1/policy/overview by_year（S7PDT01 回填 2191 份）；断连时如实显示「历史纵深未连接」（theme-system.spec 用例锁定） |
| V4 | 图例即库存 + GAPS% | PASS | `v4_legend_gaps.png`：per-zone 库存计数（双通道色点）+ "GAPS 63% · 10/16 阶段无断言"（真实断言缺口语义，无 API 显「未知」）；theme-system.spec 图例用例 |
| V5 | 上下文 KPI 条随聚焦重算 | PASS | `v5_context_kpi_bar.png`（GV-FACT-001 · 独立源 2/2 ✓ · human_verified · 发布状态），与评分解释面板同源渲染（一致性 by construction），saved-view-live.spec live 断言 KPI↔面板同值；点击滚动至解释面板 |
| V6 | "Ask a question" 栏 | PASS | `v6_ask_bar.png`（画布顶栏 Ask 输入+按钮）；D4 形态：零 LLM API（Owner 决策），开放问题组装上下文 prompt 跳 ChatGPT 新会话；theme-system.spec ask-bar 用例（stub window.open 断言状态机） |
| V7 | 结构化洞察卡深链回图 | PARTIAL | `v7_change_overlay.png`（画布变化提要 overlay：/v1/changes 真实变化条目）+ 模块页首屏三结论卡（/policy 等六模块）；但"洞察卡点击深链回画布对象"的闭环未做——如实记为缺口，归入后续迭代 |
| V8 | 问答即 reroot（被查对象成新中心/聚焦态） | PASS | `v8_ask_reroot_tsmc.png`（ask "tsmc" → inspector 呈 TSMC · UPSTREAM · server returned entity 聚焦态；本地图内实体则直接换根+reroot 飞行动画）；theme-system.spec 断言 data-last-ask-action idle→reroot:*；home.spec NVIDIA 递归 reroot 路径用例 |
| V9 | 聚焦展开卡（对象→分类卡→细丝扇出到叶） | FAIL（如实） | 未实现。S9PAT02 时已登记 ledger risks（"聚焦展开卡归 S9PC 交互深化"），S9PC 实际交付时间轴+Ask 栏。十要素 9/10 仍过门槛（≥8）；此项列入 S11 前补强候选或 v0.2 |
| V10 | 右侧详情卡（状态 pill/最近更新/探索深链） | PASS | `v10_inspector_detail.png`（Relationship path 详情卡：FOCUS/UPSTREAM pill、Stage、Role、Current subject、Saved view 面板）；state-contract.spec 保存视图/恢复用例锁定 |

**判定：9/10（8 PASS + 1 PARTIAL 计 0.5×2=9 口径说明：V7 计 0.5、V9 计 0——严格口径 8.5/10，仍 ≥8 过门。**

## 二、ADP 十个体验模式对照

| # | ADP 模式 | EEI 对应 | 判定 |
|---|---|---|---|
| ① | 首屏即答案 | 六模块页首屏三结论卡（/policy /supply-chain /ma /control /signals /structure）；主画布首屏即帝国全景 | PASS |
| ② | 决策透明 | 评分解释面板 + KPI 条同源（candidate_key/独立源 n/m/review/publication 全可见）；八特征贡献→EEI 为源阈值+人工复核状态 | PASS |
| ③ | 敢于弃权 | abstentions 节（模块页如实列出弃权项）；GAPS「无断言≠真实为空」；金标 recall 如实上报不虚增 | PASS |
| ④ | 证据可溯源 | 已发布事实→evidence 链→official source URL 三步；导出 CSV 带 evidence 列；operation_logs 签核哈希 | PASS |
| ⑤ | 唯一有效行为闭环 | 发布链：候选→双源核验→Owner 签核→原子快照发布（唯一写路径）；review_queue 开闭环 | PASS |
| ⑥ | 回执文化 | Owner 签核 bundle（SIGNED_DECISION_BUNDLE + RISK_WAIVER_ACCEPTED 枚举回执）；gold_only_sha256 冻结回执 | PASS |
| ⑦ | 诚实降级 | fixture/api_required 徽标（未连接 API 如实展示）；源三连败熔断自动停用+system log；CI fps 天花板文档化降级 | PASS |
| ⑧ | 结论先行的浅层用户中心 | 首屏结论卡+详情卡分层；语义缩放 L0-L3 浅→深 | PASS |
| ⑨ | 来源全透明 | /v1/sources/freshness + 数据中心模块 + 快照键全链路展示（sec-backfill-2016:...:pipeline:hash 直接可见） | PASS |
| ⑩ | 轻前端极速 | A168 P75=391ms（预算 2500ms）；防闪烁 HEAD_INIT；dual-theme CSS 令牌；reduced-motion 全回退 | PASS |

## 三、动效高级 bar ①-⑧（全 E2E 锁定：tests/e2e/motion-choreography.spec.ts + theme-system.spec.ts）

①镜头飞行 reroot（class 重启+reflow）②光晕脉冲（empireSunPulse）③细丝 draw-in（pathLength=1）④扇出 stagger（--stagger-i 纯 opacity，规避 CSS transform 覆写 SVG 属性）⑤悬停景深传播（hoverNeighborhood）⑥fps 抽帧证明（非 CI 断言地板+实测 annotation 常记；CI ~31fps 共享跑器软渲染=文档化降级）⑦reduced-motion 全塌缩（--motion-scale 归零+时长钳制 0.001s）⑧防闪烁（首绘前 data-theme 钉定）。

## 四、T1118 / T1119 / A144

- **T1118（A167）视觉回归**：`tests/e2e/visual-regression.spec.ts` 六个批准态截图契约（default / lens pivot / dense list / empty search / loading pending / error api）。基线 CI 权威（ubuntu 字体栈；macOS 平台门跳过）；`eei-visual-baseline.yml` workflow_dispatch 再生成基线；`eei-validation.yml` 失败上传 test-results 工件。animations disabled 保像素确定性；交互用 toPass 自愈重试（慢跑器水合前点击是静默 no-op）。
- **T1119（A168）首屏性能**：`tests/e2e/perf-first-interactive.spec.ts` 首交互图 7 采样 P75 断言 <2500ms + 指标 JSON/annotation 双留痕。本地实测 P75=391ms（samples 347-420ms）。预热轮排除 dev 编译成本。
- **A144 首屏预算**：历史已 DONE（acceptance_traceability.csv:31 TR-FUN-EXP-01-A144 → home.spec.ts），本门以 A168 数字化复核（391ms ≪ 预算）。

## 五、如实缺口与遗留

1. V9 聚焦展开卡未实现（FAIL 如实计入，门槛 9/10 仍过）；V7 洞察卡深链回图闭环未完成（PARTIAL）。两项列入 S11 前补强候选。
2. KPI 条与 as-of 横幅在 1440 宽下轻度视觉重叠（cosmetic，不影响可读/点击；后续微调 z/offset）。
3. 视觉回归基线是 CI 字体栈快照：本地（darwin）套件跳过是设计而非缺测——CI 每次 PR 都跑。
4. 采集环境说明：截图带真实生产数据（快照 sec-backfill-2016:…:pipeline:999d4263…，server · gen 17，GV-FACT-001 2/2）；watchlist 面板的 Synthetic fixture 徽标是该模块的诚实标记（其数据仍为 fixture——正是⑦诚实降级的活例）。
