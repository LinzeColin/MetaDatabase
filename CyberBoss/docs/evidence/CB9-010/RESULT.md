# CB9-010 只读捕获线上 release、OVH 资源、systemd、Cloudflare 和数据端点现状

**本地半边：NOT_APPLICABLE · 线上半边：NOT_RUN**
验收：AC-031 / AC-032

## 本地半边

这个节点就是去读生产现状，本地无从读起

## 线上半边（NOT_RUN）

没验到的：

- 线上当前 release、systemd 单元状态、Cloudflare 隧道状态、数据端点可达性

实测缺失（不是推断）：

| 探针 | 结果 |
|---|---|
| ssh ubuntu@51.222.29.63 | connection timed out |
| env R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | unset |
| env CLOUDFLARE_API_TOKEN | unset |
| env OCI_CLI_CONFIG_FILE | unset |
| env GITHUB_TOKEN | unset |

## 凭据到位后跑什么

1. 能连上生产机后只读采集一次，写进本目录（只读，不改任何线上状态）

## 回滚

本节点未修改代码，只新增记录。回滚 = 删除 `docs/evidence/CB9-010/`。
