# Alpha｜7*24 自主实盘交易 Agent Workspace

Alpha 是一个由 AI coding agents 在开发阶段协助构建、但在生产阶段独立运行的 7×24 autonomous live trading agent workspace。ChatGPT 或其他 LLM 与 Codex 或其他 Agent 仅负责需求、架构、任务分解、代码、测试和部署制品，不接收实时市场数据、不持有券商凭据、不参与任何生产交易决策。部署并经 owner 预授权后，Alpha 软件自行收集市场信息、识别交易机会、形成策略与组合决策、通过风险门禁，并直接连接券商或交易所完成真实下单、改单、撤单、成交处理与对账；不要求 owner 逐笔审批。
Alpha 是 Linze 本人自有资金的全自动实盘交易工作台：多 Agent 并行研究，唯一执行网关经 Moomoo OpenD 在预签授权内自动真实下单、对账、通知。产品目的是直接真实交易（real trading）；Paper/Shadow 只是上线前的验证工具。

**30 秒了解现状**：读 `文档/00_我在哪.md`（状态/卡点/路线图）。全部七份文档由机器平面自动渲染，禁止手写。

| 想知道 | 看哪里 |
|---|---|
| 为谁做、做什么、不做什么 | `文档/01_产品需求.md` |
| 功能、数据流、参数为什么这么定 | `文档/02_系统架构.md` |
| 每个数字的唯一裁定 | `文档/03_口径字典.md` |
| 这一轮做什么、怎么算完成 | `文档/05_执行与验收.md` |
| 策略公式与人话解读 | 任务包 `PRD/策略白盒规范.md` |

## 核心口径（详见口径字典）

- 资金授权：总敞口 ≤ **3000 AUD**；单笔 ≤ 60%（1800 AUD 胖手指保险丝）；滚动 60 分钟 ≤ 5 笔；无持仓数上限
- 市场：MVP 仅美股/美国 ETF（港股第二阶段；沪深不经 Moomoo AU）
- 晋级门槛：回测月均净收益 ≥0.6%（含真实费用；owner 2026-07-17 选乙保底线，主力=黄金叠加动量）+ 3 日 Paper+Shadow 行为一致 + 工程零违规 → 按 owner 预签授权自动进 MICRO_LIVE；不达标零成本调参循环
- 断路器：单日 -2% 停新仓；3 日 -4% 退防现金；月内 -8% 自动降回 Paper
- 默认失败关闭：仓库默认 `DISABLED`；十一项门禁全过才可真实下单
- 第一阶段 0 付费组件；策略全白盒可手工复算

## 本地开发

```bash
python -m pip install -e .[dev]
python -m pytest tests -q                                   # 全量测试
python3 machine/tools/render_human.py                        # 渲染人类平面
python3 machine/tools/check_doc_budget.py                    # 三道门
python3 machine/tools/check_blocker_stop.py
```

## 生产运行

Oracle 免费云主机常驻（见任务包 `specs/DEPLOY_RUNBOOK_ORACLE.md`）；owner 通过邮件收报告、网页控制页一键停机。凭据永不进 Git。

## 安全声明

本仓库公开。策略参数公开是 owner 知情决定；账户凭据、授权文件、运行时秘密全部在 Git 之外。本项目只服务 owner 本人账户，不构成任何投资建议。
