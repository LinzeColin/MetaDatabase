# CB9-660 发布后自动观察、状态投影与恢复演练入口

**本地半边：PASS · 线上半边：NOT_RUN**
验收：AC-035

## 本地半边

状态投影和「没测过 ≠ 坏的」已闭环

已闭环于：
- `app/test/cb9-500-parity-freshness.test.js`
- `app/test/cb9-510-status-vertical-matrix.test.js`

## 线上半边（NOT_RUN）

没验到的：

- 发布后自动观察真的在生产上跑起来并写回执
- 恢复演练入口在真机上能一键触发，且 backups.restore_drill_state 因此转绿

实测缺失（不是推断）：

| 探针 | 结果 |
|---|---|
| ssh ubuntu@51.222.29.63 | connection timed out |
| env R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | unset |
| env CLOUDFLARE_API_TOKEN | unset |
| env OCI_CLI_CONFIG_FILE | unset |
| env GITHUB_TOKEN | unset |

## 凭据到位后跑什么

1. 部署后确认观察任务落了第一条 live receipt（面板从 UNKNOWN 转 HEALTHY）
2. 触发一次恢复演练 → 确认 restore_drill_state 由 UNKNOWN 变 HEALTHY、建议动作从 run_restore_drill 回到 none

## 回滚

本节点未修改代码，只新增记录。回滚 = 删除 `docs/evidence/CB9-660/`。
