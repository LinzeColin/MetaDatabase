# CB-510 Run Contract — 一次性真实激活、升级、DNS 与 Status

## 目标

将已关闭的 CB-500 候选以其精确 Git commit 封存为不可变 OVH release，
通过现有生产入口配置 Cloudflare Access、DNS 与全局 Status，并保留立即回滚至
`previous` 的能力。产品版本固定为 `v0.0.0.5`。

## 最小范围

- `CyberBoss/app/scripts/cloud-supervisor.js` 与其单测：Status 的阶段/任务元数据只能由
  受校验环境值覆写，默认保持历史兼容；从同一 loopback-only 进程暴露派生的
  Timeline 静态面和最小 Status 面，不新增 Web 服务或数据源。Linux `Type=notify`
  仅在该 loopback listener 已实际绑定后收到一次无阻塞 readiness 通知；非 systemd
  环境严格不调用该 Linux helper。
- OVH 的既有 `/opt/cyberboss-cloud` release/current/previous、
  `cyberboss-cloud.service` 及既有 Status collector。
- 现有 Cloudflare DNS 与 Access 账户资源。

不改动冻结的 `docs/product_design/v0.0.0.4/implementation-kit`，不创建仓库、
Private-Database clone、macOS launchd、控制面或运维模型调用。

## 前置与顺序

1. 本地单测与精确 commit 通过后才生成 release。
2. 先确认 OVH 主机密钥、当前指针和工具链；仅在 release 完整时切换指针。
3. Access 采用 Owner 邮箱 allow-only；Status 从同机受保护快照读取，不要求 Access
   service-token 管理权限。
4. DNS 只在公开 origin 与 Access 已可验证时写入；任何失败先停止 intake 并切回
   `previous`。
5. 若真实 WeChat account 凭据不存在，`CB_CHANNEL_ACTIVATION_MODE=pending` 只能保留
   channel/bridge 为 unready；真实 Codex、Timeline 和 Status 仍可启动，且不得启动
   simulator 或把 pending 写成 ready。

## 验收与证据

- `healthz`、`readyz`、受保护 `status/snapshot.json` 均来自 loopback；匿名访问被拒。
- `current`/`previous` 解析至不可变 release；release manifest 绑定精确 commit。
- Cloudflare Access/DNS、Status 注册和真实适配器探针均写入
  `docs/evidence/CB-510/summary.json` 与 `subject.json`，不可达项明确为 pending，
  不得标绿。
- 验证不使用真实时间等待；发生 P0 时只执行确定性停止/回滚。

## 回滚

停止 `cyberboss-cloud.service`、将 `current` 原子指向已验证 `previous`，重启服务，
并撤销本次新增 DNS route / Access application；不删除 spool、备份或证据。
