# Signal Lattice｜最终开发任务包入口

本任务包版本锁定为 `v0.0.0.1.39`，目标路径为 `LinzeColin/MetaDatabase/Signal-Lattice/`，目标域名为 `signal-lattice.linzezhang.com`，运行节点为 OVH Linux。股票 Skill 的唯一 Git 路径是 `Signal-Lattice/Stock_Skill/`；根目录 `Stock_Skill/` 是禁止重建的 legacy 路径。

当前状态：`SEALED_TASKPACK`。Owner 已明确批准把该任务包交给 Build Agent 执行最后一公里。该状态不等于生产发布 PASS；Live Action 仍关闭，正式发布验收不得伪造。

## 唯一执行顺序

1. 读取 `CANONICAL_STATE.json`、`evidence/owner_gate/taskpack_seal.json`、`PURSUING_GOAL.txt` 和 `ROADMAP.md`；
2. 运行 `bash scripts/codex_last_mile.sh plan`；
3. 运行 `bash scripts/codex_last_mile.sh task T-002`，第一步必须读取 Status；
4. 获取最新 `integration_base`，按 `satisfied / apply / adapt / equivalent / conflict / blocked / obsolete` 分类，不覆盖上游更优实现；
5. 将 `Signal-Lattice/` 落入目标仓，只完成 `machine/facts/residual_environment_tasks.json` 中的环境绑定工作；
6. 运行 `python3 scripts/verify_taskpack_seal.py --root .`；
7. 绑定 OVH、Cloudflare、Private-Database、R2、OCI 与 Status 的真实凭证，凭证不得进入 Git 或任务包；
8. 安装、即时故障注入、备份、恢复和回滚；
9. 自动生成 13×9 业务线证据并运行 `bash scripts/codex_last_mile.sh close`；
10. 仅在有真实新事实时 commit、push、merge 和备份，不得空提交。

## 强制边界

- 不得修改版本号、Scope、Acceptance、Oracle、Test Catalog 或发布边界；`Signal-Lattice/Stock_Skill/` 是唯一 Git 真源。v0.0.0.1.39 的最终任务包会携带该源码树并由外层清单及封存收据绑定；正式应用 ZIP 仍不得复制其历史 release/archives；
- 不得重新进行市场研究、产品定义、架构设计或独立复审；
- 不得启用运行期 Agent、LLM、模型 API、自动交易、上游 Skill 写回、macOS launchd 或用户本机常驻；
- 缺少环境输入时写入 `BLOCKED_ENVIRONMENT` 收据并停止对应任务；不得猜测、跳过或转成 PASS；
- 正式 Upstream Seal、目标环境和独立发布验收完成前，只允许 `RESEARCH_AND_NO_ACTION`。
