# CB-530 运维命令实测摘要

本文件是 P5.4 的脱敏命令结果摘要，不保存主机地址、账户、OAuth refresh token、短期
access token、OCI PAR、客户邮箱、Prompt 或运行库内容。权威操作说明仍是
[`CB530_OPERATOR_HANDOVER.md`](../../operations/CB530_OPERATOR_HANDOVER.md)。

| 操作 | 实测结果 | 真值边界 |
| --- | --- | --- |
| immutable release 切换 | `current` 指向 `25670bf32c6d27e3668fcf59bc9ab754035e161d`，`previous` 保留有效 immutable release | 产品版本仍为 `v0.0.0.5` |
| `cyberboss-cloud.service` | active；`/healthz=200`、Timeline `=200` | `/readyz=503` 是缺少真实 WeChat credential 的故意 fail-closed 状态 |
| `cyberboss-backup.service` | 成功生成 `backup_5233145600b2b004151de2bb` | 同一在线 SQLite snapshot 通过 integrity 与 logical digest |
| R2 | 两个精确对象 PUT/GET、SHA-256 与 metadata 均通过 | 只使用冻结 bucket/prefix；无 list、delete 或 overwrite |
| OCI | 两个精确对象 PUT receipt、ETag 与本地 SHA-256 通过 | 日常 PAR 是 write-only，常规读回仍为 `activation_pending_write_only_par` |
| OCI 临时精确核验 | Owner 临时 ObjectRead PAR 只读取本次 `runtime.sqlite3`，SHA-256 匹配后立即撤销 | 该临时 credential 不进入日常 service、配置或事实库 |
| `cyberboss-restore@…` | R2 精确 key 的 isolated restore 成功 | network-disabled、`promoted=false`、SQLite integrity `ok` |
| `cyberboss-backup.timer` | enabled 且 active | Linux systemd 每日任务；不使用 macOS launchd |
| Cloudflare Access | Tunnel active；无 Cookie 的 Timeline 请求返回 `302` | 仅证明 Access challenge，未伪称已认证浏览器会话 |
| Status / Private-Database | Status collector 已刷新；daily 与 material sync 均成功 | 两条同步使用 `private_db_client.py`，无 clone |

## 可复跑命令

```bash
sudo systemctl start cyberboss-backup.service
sudo systemctl start cyberboss-restore@backup_5233145600b2b004151de2bb.service
sudo systemctl enable --now cyberboss-backup.timer
sudo systemctl status cyberboss-backup.service --no-pager
sudo journalctl -u cyberboss-backup.service -n 80 --no-pager
```

停止后续调度的命令是 `sudo systemctl disable --now cyberboss-backup.timer`；它不删除
任何 snapshot、remote object 或 retained release。应用回滚沿用既有 `previous` 指针
流程，先检查 release manifest、cloud service、Access 与 Status，再更新指针；本 Run
没有为了制造演练而停机，CB-520 已保留独立的真实 `current → previous → current` receipt。

## 不变约束

- 控制面与运维模型调用均为 `0`，没有已认证 turn。
- 没有新仓库、业务数据库、事实源或 Private-Database clone。
- 不存在 macOS `launchd` 依赖，也没有 simulator 冒充真实 provider。
- 真实 WeChat credential 未获授权，因此 channel/bridge 保持 pending，不能把
  `/readyz=503` 改写为成功。
