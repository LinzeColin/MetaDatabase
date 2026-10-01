# Alpha 规格（一页）

## 要解决什么问题

Owner 要一个 7×24 不靠人盯的交易研究与执行工作台：策略全白盒、能手工复算，先在影子盘里用真实行情模拟成交并如实记账，满足晋级门槛后才按 owner 预签授权考虑真实交易。

## 给谁用

Owner 一人，只服务 owner 本人账户；通过控制页看盘、停机，通过邮件收报告。

## 明确不做

- LLM/研究 Agent 不持有券商凭据、不调用下单接口；控制页、邮件指令只能查询/停机/授权确认，永远不能下单（`AGENTS.md` §4）。
- 不做 VPN/代理/地理伪装等规避；杠杆、保证金、做空、期权、期货、加密实盘一律禁止。
- 秘密永不进 Git；不编造测试结果、回报或收益。
- 当前不做真实下单：仓库默认 `DISABLED`，线上为 `SHADOW`。
- 第一阶段 0 付费组件。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 全量测试 | `cd Alpha && python -m pytest -q -p no:cacheprovider`（2026-09-30 实测 438 passed, 1 skipped） |
| 部署脚本语法与静态检查 | `bash -n Alpha/deploy/vps3/install.sh && shellcheck -S warning Alpha/deploy/vps3/install.sh` |
| 人类文档与机器事实一致 | `python3 Alpha/machine/tools/check_dual_plane_ci.py --root . --projects Alpha --require-projects` |
| 控制页活着且是影子盘 | `curl -s https://alpha.linzezhang.com/api/overview` 返回 200，`mode_code` 为 `SHADOW` |
| 净值快照在更新 | `systemctl list-timers alpha-equity-snapshot.timer` 有下一次触发（周期 15 分钟） |

## 已知坑

- `AGENTS.md` 与旧文档里的「Oracle 免费云主机」部署已过时，现行部署在 VPS-3（`deploy/vps3/`）；旧材料在 `deploy/` 其它文件。
- 影子盘净值未计分红（BIL、IEF 的派息占回报大头），比回测的复权总回报口径保守（控制页 `mode_explain`）。
- 在仓库根目录直接 `pytest Alpha/tests` 会因相对路径报错，必须先 `cd Alpha`（与 CI 一致）。
- 文档 `文档/00-06` 只能由 `machine/tools/render_human.py` 渲染，手改会让 dual-plane 变红。
