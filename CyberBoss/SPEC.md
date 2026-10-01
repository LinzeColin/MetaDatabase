# CyberBoss 规格与运行摘要（一页）

> 本目录的 `README.md`、`HANDOFF.md`、`CHANGELOG.md`、`UPSTREAM_PROVENANCE.md` 被验收校验脚本和 sha256 清单钉住（`docs/evidence/CB-840/MANIFEST.sha256.json`、`scripts/validate_current_truth.py` 等），本次没有改动它们；一屏版运行信息写在本页第二节。

## 要解决什么问题

让 Owner 通过微信 Bot 独占一个云端 Codex Workspace，同时让其他用户用同一个 Bot 自带 Provider 密钥（BYOK）使用相互隔离的个人服务，全程跑在云端，不依赖 Owner 的电脑。

## 给谁用

Owner 一人（Codex Workspace 独占）；其他用户走 BYOK 个人服务，数据相互隔离。

## 运行摘要（README 该有的一屏）

- 地址：`https://boss.linzezhang.com`（后台与设置页；2026-09-30 实测 `curl -sI` 返回 200，`/healthz` 返回 200）。`https://cyberboss.linzezhang.com` 前面挂 Cloudflare Access，实测 302 跳登录页，不能用来判活。
- 怎么知道真在跑：`curl -fsS https://boss.linzezhang.com/healthz`；服务器上看门狗 `cyberboss-watchdog.timer` 每 **2 分钟**问一次本机与公网 `/healthz`，连续失败才重启对应 unit（`ops/systemd/cyberboss-watchdog.timer`、`ops/watchdog/cyberboss-watchdog.sh`）。
- 备份最迟多久一次：每日 UTC 03:35（`cyberboss-backup.timer`）；2026-09-30 起 OCI 腿可选，现在只有 R2 一份冷备，R2 落地即判 passed。
- 数据放哪：服务器 `/var/lib/cyberboss`（运行 spool）；备份在 R2；可恢复快照经 `private_db_client.py` 进私有库 `Private-MetaDatabase`（`domain=CyberBoss`），禁止 clone 私有库。
- 部署：`CyberBoss/ops/deploy-to-cloud.sh`（需 SSH 私钥，从开发机执行，主线执行）。回滚：`ops/deploy-to-cloud.sh --rollback`，或服务器上 `cyberbossctl rollback`（回到上一个可用的不可变 release，`current → previous`）。
- 需凭据而停掉：真实微信通道、真实 Provider 密钥、授权目标机相关的 4 条验收项（`AC-035`、`AC-039`、`AC-040`、`AC-050`）标 `activation_pending`（README「当前状态」）。

## 明确不做

- 不创建、恢复或引用独立代码仓；只作为 `MetaDatabase/CyberBoss/` 子树存在。
- 不保留上游 remote、submodule、自动同步、运行时下载；上游更新需要新的 Owner Change Event。
- secret、Codex auth、微信 bearer、原始私聊、真实 PII 不进本仓、日志或公开证据。
- 外部凭据缺失只能标 `activation_pending`，不得伪称 verified。
- 未授权不写 `main`，开发走 `codex/cyberboss-*` 分支。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 合同测试 | `cd CyberBoss/app && npm run test:contract`（2026-09-30 沙箱实测 72 项，68 通过，4 项失败，未改动任何文件前即如此，原因未逐条核实） |
| 当前真相三处一致（README、HANDOFF、task_state） | `python3 -B CyberBoss/scripts/validate_current_truth.py` 输出 `"status": "consistent"`（2026-09-30 实测） |
| 服务活着 | `curl -fsS https://boss.linzezhang.com/healthz` 返回 200 |
| 双平面 | 本项目未列入 `dual-plane.yml` 的项目清单，不适用 |

## 已知坑

- PG-8 是 `CONDITIONAL_PASS`，不是完整产品验收；4 条验收项缺凭据或授权目标机。
- 看门狗端口必须从配置读取，写死 8787 曾导致误判重启（`ops/watchdog/cyberboss-watchdog.sh` 注释）。
- `cyberboss.*` 在 Access 之后，朋友打开设置链接会被拦，对外设置页用 `boss.*`（`ops/deploy-to-cloud.sh`）。
- 改 README 或 HANDOFF 前先看 `validate_current_truth.py`：只解析 README/HANDOFF 开头的有限行数，状态节必须排在窗口内。
