# CB9-640 不可变 release、请求数 Canary 与精确回滚

**本地半边：PARTIAL · 线上半边：NOT_RUN**
验收：AC-034

## 本地半边

release/canary/rollback 的判定逻辑本地有测试；但「组装一个真 release 并回滚」本身就是环境动作

已闭环于：
- `app/src/services/release/（canonical-immutable-release / request-count-canary / canonical-dress-rehearsal）及其既有测试`

## 线上半边（NOT_RUN）

没验到的：

- 线上真的产出了一个不可变 release 且 manifest 摘要可核
- 按请求数的 canary 真的在生产流量上跑过
- 回滚是一次指针移动，且回滚后线上行为与上一版一致

实测缺失（不是推断）：

| 探针 | 结果 |
|---|---|
| ssh ubuntu@51.222.29.63 | connection timed out |
| env R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | unset |
| env CLOUDFLARE_API_TOKEN | unset |
| env OCI_CLI_CONFIG_FILE | unset |
| env GITHUB_TOKEN | unset |

## 凭据到位后跑什么

1. 组装 release → 记下 release_id 与 manifest 摘要 → 和 /source 页对上（这一条同时闭合 AC-029 的线上半边）
2. 按请求数放量 canary → 观察错误率 → 触发一次真实回滚 → 核对指针与行为

## 回滚

本节点未修改代码，只新增记录。回滚 = 删除 `docs/evidence/CB9-640/`。
