# Signal Lattice｜股票信号格阵决策系统

Signal Lattice 是确定性、零 Agent、零模型 Token 的股票研究与决策支持系统。它动态接入平权 Skill，将研究结果规范化为 Claim、Evidence、Conflict、Quant Validation 和 Action Packet；任何关键门失败时输出 `NO_ACTION`。

当前交付物是 `SEALED_TASKPACK`：可交给 Build Agent 完成目标仓、真实凭证、OVH 和供应商环境的最后一公里。它不声称真实市场优势或正式生产发布已经 PASS。

股票 Skill 的唯一 Git 真源是仓库根相对路径 `Signal-Lattice/Stock_Skill/`；根目录 `Stock_Skill/` 不得重建。最终开发任务包会携带该可恢复源码树，并用独立的嵌入式源码哈希绑定；正式应用 ZIP 仍不重复打包历史 Skill ZIP。两种交付均要求在 Git 源码仓验证 registry 与公开安全扫描。

## 快速入口

```bash
bash scripts/codex_last_mile.sh plan
bash scripts/codex_last_mile.sh task T-002
python3 scripts/verify_taskpack_seal.py --root .
```

## 运行边界

- 仅部署到 OVH Linux；
- API 默认只绑定 `127.0.0.1`，由批准的 Cloudflare 入口代理；
- 无 Agent Runtime、模型 SDK 或模型 API；
- 无自动交易；
- 无 macOS launchd 或本地常驻资源；
- Status Tier-0 是第一步和最后一步；
- 缺少正式来源、数据或发布证据时强制 `RESEARCH_AND_NO_ACTION`。

Build Agent P80 约 250k Token／15h 墙钟，P95 约 495k Token／32h 墙钟；详见 `machine/facts/build_agent_cost_estimate.json`。
