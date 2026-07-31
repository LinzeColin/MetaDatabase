# Signal Lattice｜股票信号格阵决策系统

Signal Lattice 是一个部署在 OVH 的全自动股票投资决策中枢。它每 60 秒执行一轮完整链路：先只读检查 GitHub 上投资 Skill 的新增、删除、修改、拆分和合并；再让全部 Active Skill 在同一份不可变市场快照上相互隔离、独立判断；最后由无投资立场的中枢去重证据、保留分歧、校准可靠性并只输出一个顶层建议。

## 用户实际看到什么

网站第一屏始终只显示一个结果：`BUY / ADD / HOLD / REDUCE / SELL / WATCH / AVOID / NO_ACTION / SYSTEM_BLOCKED`。

- `NO_ACTION`：所有 Active Skill 已真实完成本分钟独立判断，中枢已完成协调，但量化、证据、费用、流动性或风险硬门不允许行动。
- `SYSTEM_BLOCKED`：完整链路没有完成，例如市场数据不可用、Active Skill 不足或有 Skill 未返回。系统禁止把空数据伪装为投资建议。

用户可继续下钻查看每个 Skill 的原始独立判断、证据根、反证、冲突、量化硬门、可靠性权重和 GitHub 版本血缘。

## 不可变运行边界

- 每 60 秒一轮完整循环；
- 所有 Active Skill 必须参加当轮判断；
- 所有 Skill 平权，没有母 Skill；
- 中枢只协调，不产生自己的投资观点；
- 每轮只允许一个顶层建议；
- 自动交易永久关闭，仅供人执行；
- 运行期不依赖 ChatGPT、Codex、Claude、任何 Agent 线程、人工保活、用户 Mac 或 launchd；
- 当前版本模型模式为禁用，运行 Token 预算为 0；
- GitHub 上无法确定性兼容的新 Skill 进入隔离区，上一稳定版本继续运行。

## 运行入口

- 公网产品：`https://signal-lattice.linzezhang.com`
- 权威运行投影：`https://status.linzezhang.com`
- OVH 内部 API：`127.0.0.1:8787`

## 最后一公里

本项目目录是任务包中的完整可部署产品实现。Build Agent 不应重新研究或重新设计；它只执行状态预检、移动仓语义协调、目标仓落库、真实凭证绑定、OVH/systemd/Cloudflare 部署、即时故障注入、备份恢复回滚和 Status Closure。
