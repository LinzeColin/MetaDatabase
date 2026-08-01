# CB9-630 资源闸门、成本预算与自愈

**本地半边：PASS · 线上半边：NOT_RUN**
验收：AC-031 / AC-035

## 本地半边

闸门和自愈都是纯函数，本地已逐条钉过

已闭环于：
- `app/test/cb810-status-resource-selfheal.test.js（资源闸门：量不到的读数拒绝而不是放行；自愈零模型调用）`
- `app/test/cb9-500-parity-freshness.test.js / cb9-510-status-vertical-matrix.test.js（AC-035 的结构化状态、建议动作、上次成功/失败、恢复）`

## 线上半边（NOT_RUN）

没验到的：

- 真实 OVH 主机负载/磁盘/inode 压力下闸门确实拦住新活
- 真实成本预算耗尽时熔断真的合上
- 自愈在真机上重启服务并恢复，且全程零模型调用

实测缺失（不是推断）：

| 探针 | 结果 |
|---|---|
| ssh ubuntu@51.222.29.63 | connection timed out |
| env R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | unset |
| env CLOUDFLARE_API_TOKEN | unset |
| env OCI_CLI_CONFIG_FILE | unset |
| env GITHUB_TOKEN | unset |

## 凭据到位后跑什么

1. 在生产机上人为占满磁盘 → 确认闸门拒收新活且面板说得出原因
2. 把预算调到已用量以下 → 确认下一次调用被熔断而不是照发
3. kill 掉服务 → 确认看门狗拉起来，并检查这期间的模型调用计数为 0

## 回滚

本节点未修改代码，只新增记录。回滚 = 删除 `docs/evidence/CB9-630/`。
