# ABD v0.0.0.1 S18/P04 运行手册与值守自动化

本文件是 `AC-S18-P04` 的离线、确定性控制手册。它只描述
`OFFLINE_DETERMINISTIC_CONTRACT_ONLY` 的配置与重放，不安装真实排程，
不访问外部服务，也不改变生产状态。

## 正常周期

正常运行无需用户维护；异常仅按暂停合同升级。所有正常周期都必须产生
`CONTINUE_AUTONOMOUS_OFFLINE_CONTROL_PLANE` 和
`NO_OWNER_MAINTENANCE_REQUIRED`，并始终保持
`NO_RECOMMENDATION_NO_ORDER`。资金事实、实际账本、受限凯利和万分之一
不利扰动门保持不变。

`scheduled_jobs.json` 与 `maintenance_calendar.json` 是唯一排程真源。每个
窗口只重放本地已签名控制或派生状态，不执行外部网络、主机、边缘、邮件、
补丁、备份、恢复、流量切换或订单动作。

## 固定逻辑窗口

| 窗口 | 控制作业 | 正常动作 | 异常动作 |
| --- | --- | --- | --- |
| 每日 | `DAILY_SIGNED_CONTROL_REPLAY` | 重放 P01--P03 已签名控制 | 暂停合同 |
| 每日 | `DAILY_MAIL_EVIDENCE_CONTINUITY_AUDIT` | 审计本地邮件证据投影 | 暂停合同 |
| 每周 | `WEEKLY_PATCH_READINESS_GATE` | 评审补丁就绪投影 | 暂停合同 |
| 每周 | `WEEKLY_BACKUP_DERIVED_STATE_INTEGRITY_REPLAY` | 重放派生备份完整性 | 暂停合同 |
| 每月 | `MONTHLY_DISASTER_RECOVERY_PROJECTION` | 重放本地容灾投影 | 暂停合同 |
| 每月 | `MONTHLY_RETENTION_AND_EVIDENCE_REVIEW` | 评审本地保留与证据投影 | 暂停合同 |

## 异常、暂停与回滚

任何失败、未知作业、畸形输入、资金事实变更请求、风险门放宽请求、外部
执行请求或万分之一边界不稳定，均只能产生
`PAUSE_CONTRACT_AND_ESCALATE_OWNER_OUTBOX_ONLY`。升级是
`LOCAL_STRUCTURED_OUTBOX_PROJECTION_ONLY`，不会发送外部消息、重启进程、
恢复备份、安装补丁、切换来源/模型或提交订单。

回滚仅关闭本地 S18/P04 operations automation 控制，并保留 S18/P03 已签名
证据和派生状态的可重放性。正常持有人动作仍为 `FINAL_ORDER_ONLY`；本手册
不生成推荐或订单。

## 验收与边界

验收只运行 `tests/S18/P04_test.py`、离线静态包校验、零预算依赖扫描和
`python -m abd_acceptance --contract AC-S18-P04 --evidence machine/evidence`。
禁止全量测试、完整回归和真实时间 soak。通过仅证明本地控制合同，绝不证明
OVH、Cloudflare、Gmail、数据库、市场、账户、部署、上线或收益。
