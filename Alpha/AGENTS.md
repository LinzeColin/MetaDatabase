# Alpha 执行契约（AGENTS.md）— Live MVP v1

本文件是 Alpha 项目的最高开发契约，2026-07-17 由 owner（Linze）授权全面替换旧契约。旧契约中「Committed code must not implement or enable unattended real-money order submission」等 paper-only 禁令自本版本起废止，替换为下述受控许可模型。

## 1. 使命

把 Alpha 建成账户所有者本人、自有资金的 7*24 自主实盘交易 Agent Workspace：多 Agent 并行研究，唯一执行网关经 Moomoo OpenD 在 owner 预签授权范围内自动真实下单、对账、通知。MVP 终点 = MICRO_LIVE 中完成首个真实订单生命周期。Paper/Shadow 是验证工具，不是产品终点。

## 2. 权威顺序

1. owner 当前指令；
2. 本文件 + `machine/facts/`（双平面唯一事实源）+ `Alpha_Live_TaskPack_v1` 的 `00_START_HERE.md`；
3. `configs/` 下各配置文件；
4. 仓库其余文档。旧 handoff（CodexProject 时代）仅作历史参考。

## 3. 受控许可模型（替代旧禁令）

允许实现并启用无人值守真实下单，但必须同时满足：

- 只有唯一的 Execution Gateway（单写者租约）可调用券商下单/改单/撤单接口；
- 仓库提交的默认配置永远 `DISABLED`（失败关闭）；
- 真实下单前置门禁十一项全过：环境开关、预签授权文件、policy hash 匹配、券商健康、辖区能力探针（接口实测）、对账一致、行情新鲜、风控通过、幂等键未用、kill switch 清位、执行租约在手；
- 资金授权：总敞口 ≤ 3000 AUD，单笔 ≤ 总授权 60%（胖手指保险丝），滚动 60 分钟 ≤ 5 笔，无持仓数量上限；
- 市场：MVP 仅美股/美国 ETF；港股第二阶段；沪深永不经 Moomoo AU 路由；
- 晋级：回测（≥3 年含费用）月均净收益 ≥0.6%（owner 2026-07-17 选乙保底线）且回撤 ≤15% + 3 日 Paper+Shadow 行为一致 + 工程零违规 → 按预签授权自动进入 MICRO_LIVE。

## 4. 永久红线

- LLM/研究 Agent 不得持有券商凭据、不得调用下单接口；自然语言不进执行边界。
- 外部/公开接口、控制页、邮件指令只能查询/停机/授权确认，永远不能下单。
- 不实现 VPN/代理/地理伪装等任何监管或券商条款规避；辖区探针不过即禁买。
- 秘密（券商密码、解锁密码、token、邮箱应用密码、会话缓存）永不进 Git。
- 不编造：测试结果、券商回报、回测数字、commit/push 状态、收益。跑不出来就如实说。
- 杠杆、保证金、做空、期权、期货、加密实盘：MVP 全部禁止。

## 5. 开发工作方式

- 任务队列：按 `Alpha_Live_TaskPack_v1/tasks/ISSUE_QUEUE.yaml` 依赖顺序执行；每任务先 PLAN_READ_ONLY（列出将读/写/测/回滚/风险）再实现；一次一个任务一个验收边界；非门禁任务自动连续推进。
- 双平面纪律：一切事实先写 `machine/facts/*.json|yaml`，再 `python3 machine/tools/render_human.py` 渲染 `文档/00-06`；文档层禁止手写；每次提交前必须过 `check_doc_budget.py`、`check_blocker_stop.py`、`check_dual_plane_ci.py`。
- 测试纪律：每任务运行其声明的测试命令并附原始输出；依赖缺失如实报阻塞。
- 白盒纪律：策略公式/阈值/参数只存在于 `configs/strategies/` 与口径字典；实盘运行中禁止手改参数——改动 = 新版本号 + 滚动前推验证证据 + Git 留痕 + 重新晋级判定。
- 月度评审：每月最后交易日收盘后自动运行（见 `configs/monthly_review.yaml`），改动下月首个交易日生效。
- 每任务结束报告：diff 摘要、测试命令与真实结果、验收状态、残余风险、下一任务。

## 6. 部署与运行

生产运行于 owner 已注册的 Oracle 免费云主机（runbook：`specs/DEPLOY_RUNBOOK_ORACLE.md`）；owner 本机为备援。掉线语义 = 停止新单，绝不失控。通知出口为邮件，遥控为网页控制页 + 邮件指令。凭据只存云主机本地环境文件。
