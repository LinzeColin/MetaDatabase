# Alpha Decision Log

## 2026-06-13: GitHub Is Authoritative

Decision: Superseded on 2026-06-27. Use `https://github.com/LinzeColin/CodexProject`, project path `Alpha/`, as the authoritative project backup and continuity surface.

Reason: Future agents need a stable, inspectable state source for code, docs, tests, rules, and handoff.

Consequence: Every meaningful run must commit and push code/docs/test evidence through `LinzeColin/CodexProject/Alpha` unless blocked. Standalone `LinzeColin/Alpha` and old local shadow folders are not authoritative delivery roots.

## 2026-06-27: Phase 6 Owner Gate Evidence Must Be Canonical

Decision: Alpha G6 Phase 6 evidence must be generated from the canonical `CodexProject/Alpha` root and must not be inferred from older shadow folders.

Reason: The current canonical dashboard is in research/paper order-intent review mode with live trading disabled. Older local shadow outputs are not a safe source for owner-gate claims.

Consequence: Phase 6 remains blocked until canonical evidence proves 48-hour Paper/Shadow soak, a qualified trading-day report, Shadow live constraints, limit-order contract, and closeout readiness. `runtime/LIVE_AUTHORIZATION.json` must remain absent.

## 2026-06-13: Execution Boundary

Decision: Alpha will automate paper trading, risk checks, approval queues, and broker-ready order tickets. It will not autonomously submit real-money broker orders.

Reason: Trading systems must preserve owner control at the real-money execution boundary.

Consequence: Committed defaults keep `live_trading.enabled: false`; live candidates enter an approval queue as tickets.

## 2026-06-13: Five-Minute Candidate Refresh

Decision: The order-intent loop has a default refresh cadence of 300 seconds.

Reason: The user requires timely candidate updates while still keeping risk checks and review gates explicit.

Consequence: `paper_trading_loop.run_forever()` remains available for CLI use, and the FastAPI dashboard lifecycle starts an app-managed automatic paper loop that runs immediately and then sleeps for the configured interval.

## 2026-06-13: Ticket Freshness Is Actionability

Decision: Only unexpired `pending_owner_approval` tickets count as owner-actionable live candidates.

Reason: Broker-ready tickets can become stale; a candidate older than its TTL should remain auditable but should not be treated as executable.

Consequence: `ApprovalQueue.summary()` separates fresh pending, expired pending, blocked, and total tickets. The dashboard shows actionability, freshness, and seconds until expiry.

## 2026-06-13: App Bundle Entrypoints

Decision: Alpha should ship a macOS `.app` entrypoint in Downloads and Applications, backed by the same dashboard start script.

Reason: The user needs a stable local webpage workspace entry that behaves like a normal app instead of requiring terminal commands.

Consequence: `outputs/applications/Alpha.applescript` generates `Alpha.app`, and copies were installed to Downloads, user Applications, and system `/Applications`.

## 2026-06-13: Strategy Iteration Requires Walk-Forward Evidence

Decision: Strategy tournament candidates must expose simple out-of-sample evidence: walk-forward return, hit rate, and validation window count.

Reason: Last-window momentum ranking is too weak for strategy promotion. Even fixture-level MVP strategy iteration should show whether a signal had repeated one-step-ahead confirmation.

Consequence: `run_strategy_tournament()` now returns `validation_summary`, and each candidate includes `oos_return`, `hit_rate`, and `validation_windows`. The dashboard tournament table displays these fields.

## 2026-06-24: Persisted Paper State Requires Locked Atomic Writes

Decision: ApprovalQueue and PaperBroker persisted JSON updates must run through a shared lock and atomic temp-file replace rather than direct read-modify-write.

Reason: Concurrent manual and automatic paper-loop actions can otherwise overwrite queue tickets or paper portfolio state.

Consequence: S3PBT01 adds `atomic_json_store`, `ApprovalQueue.enqueue` transactions, `PaperBroker.submit_order_to_path`, and paper-loop persisted-state integration. Shutdown, cancellation, PID cleanup, and live broker readiness remain out of scope.

## 2026-06-24: Runtime Stop Must Preserve Lifecycle Truth

Decision: `AutoPaperAgentRuntime.stop()` must wait for the current paper cycle to drain before reporting `stopped`, and must report `stop_timeout` with `task_running=true` if a cycle remains active after the timeout.

Reason: Cancelling an `asyncio.to_thread()` wait cannot stop the underlying Python worker thread, so claiming `stopped` on timeout can hide writes that are still in progress.

Consequence: S3PBT02 records stopping state, last stopped time, and timeout count in the runtime snapshot. Dashboard start/stop scripts keep PID files until process exit is confirmed, escalating TERM to KILL only after a bounded wait.

## 2026-06-24: Shutdown Faults Must Preserve Local State And PID Truth

Decision: Atomic JSON writes must preserve the previous committed target on replace failure or forced writer termination, `AutoPaperAgentRuntime.stop()` must produce no further writes after it reports stopped, and dashboard lifecycle scripts must verify that a PID belongs to the Alpha uvicorn process before trusting or terminating it.

Reason: S3PB must preserve governance truth during failures: a stale PID that points to an unrelated process is not dashboard evidence, and a failed local write must not corrupt paper queue or broker state.

Consequence: S3PBT03 adds shutdown fault-injection tests for disk-error preservation, forced termination before replace, no write after stopped, reused PID archiving, and start script dashboard identity checks. This closes the S3PB technical fault-injection gate without enabling live broker execution or production readiness.

## 2026-07-17 — Live MVP 契约重置（Alpha_Live_TaskPack_v1）
- owner 授权废止 paper-only 禁令，采用受控许可模型（唯一执行网关+十一门禁+预签授权）。
- 资金授权 3000 AUD / 单笔 ≤60% / 每小时 ≤5 笔 / 无持仓数上限；美股首发；月末策略评审；邮件遥控；免费云常驻。
- 事实源与全部口径见 Alpha/machine/facts/ 与 文档/03_口径字典.md。

## 2026-07-17 — owner 裁定:维持 5%/月门槛,选择「改造策略结构」持续推进(BLK-006 处置)
- owner 判断:市面高回报策略普遍存在,5%/月不算高;要求系统持续寻找高胜率策略、改造结构直到满足最低要求。
- 执行纪律不变:所有候选策略走 研究配置登记 -> 网格约束 -> 滚动前推(含费用、整股、双源数据)-> 样本外如实报告;不达标就继续迭代并如实说;绝不用过拟合数字冒充达标;红线(无杠杆/无做空/无期权期货/不绕监管)不动。
- 同批澄清:「烤机」= 72 小时不间断受控运行的工程可靠性验收(心跳/重连/内存/通知延迟),与策略无关。

## 2026-07-17 — owner 裁定:晋级月均门槛 5% 校准为 1.8%(BLK-006 解除)
- owner 经会话明示:最低要求回报率改为月均 1.8%(≈年化 23.9%)。
- 同步修改四个契约面:configs/strategy_promotion.yaml(v2)、trading_governor_policy.yaml、AGENTS.md 第 3 节、README.md 核心口径;判定代码改为从权威配置读门槛,不再写死。
- 影响披露:现有全部候选样本外最好成绩 0.811%/月(且回撤 18.35% 破 15% 门),在新门槛下仍不达标;结构改造循环(R2 起)继续。
- owner 同时提供 Oracle Always Free 用户标识(仅为账号编号、无鉴权能力),已存本机 _protected 私密文件,不进 Git;部署日仍需租户标识+区域+API 密钥或 owner 控制台操作+moomoo/Gmail 凭据。

## 2026-07-17 — owner 裁定「选乙」:黄金叠加为保底线主力,门槛校准 0.6%/月;搜索循环不停
- 主力策略 = S1_GOLD_BLEND(52 周新高过滤动量 8 成 + 恒持黄金 2 成),样本外 10.58 年 0.662%/月 @ 回撤 13.07%(唯一门内胜基线结构)。
- 晋级门槛按保底线证据下缘校准为 0.6%/月(回撤 15% 不变);持续寻优条款:更优结构经同口径证据+月度评审可替换主力,门槛只升不降。
- 超卖抄底(两版)停用:样本外均负期望;旧动量基线让位为影子对照。均可经证据复活。
- owner 同时要求:继续调整策略结构寻找更高回报(自研/市场反向研究/量化回测),循环如实汇报。
