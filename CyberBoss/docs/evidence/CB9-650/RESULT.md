# CB9-650 真实 Owner 与 Companion 微信端到端验收并生成 release receipt

**本地半边：NOT_APPLICABLE · 线上半边：NOT_RUN**
验收：AC-002 / AC-004 / AC-006 / AC-025 / AC-040 / AC-044 / AC-045

## 本地半边

这个节点的全部意义就是真人真号真消息。用模拟器跑一遍再标 PASS，正是任务包明令禁止的伪造回执

## 线上半边（NOT_RUN）

没验到的：

- 主人从真实微信发一句话，走完整条链路并收到回复
- 一个真实访客扫码进来、同意、拿到属于自己的回复，且看不到主人的任何数据
- AC-025 的 live receipt 由这次真实往返产生（而不是由配置推出来）

实测缺失（不是推断）：

| 探针 | 结果 |
|---|---|
| ssh ubuntu@51.222.29.63 | connection timed out |
| env R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | unset |
| env CLOUDFLARE_API_TOKEN | unset |
| env OCI_CLI_CONFIG_FILE | unset |
| env GITHUB_TOKEN | unset |

## 凭据到位后跑什么

1. 凭据到位后按 scripts/live_acceptance.sh 走，逐条把真实回执写进本目录

## 回滚

本节点未修改代码，只新增记录。回滚 = 删除 `docs/evidence/CB9-650/`。
