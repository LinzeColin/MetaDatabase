# CyberBoss CB-530 运维交接

本入口只适用于 OVH Linux 的 `systemd` 部署。产品版本固定为 `v0.0.0.5`；不要编辑
immutable release、不要复制 Private-Database、不要把 Codex/微信凭据写入 Runtime
snapshot，也不要使用 macOS `launchd`。

## 不可变发布清单

release staging 在冻结权限前，必须只运行一次仓库内的
`release/write-release-manifest.js`。它以 create-once 模式写入严格 JSON 的
`release-manifest.json`，固定产品版本 `v0.0.0.5`，并绑定 release commit、source tree、
source archive SHA-256 与非敏感运行时版本事实。禁止用 shell 拼接 JSON；已有清单、格式错误
或身份不匹配都必须 fail closed。随后才可移除 release 的写权限并原子更新
`current`/`previous`。

## 每日备份与诊断

```bash
sudo systemctl start cyberboss-backup.service
sudo systemctl status cyberboss-backup.service --no-pager
sudo journalctl -u cyberboss-backup.service -n 80 --no-pager
sudo systemctl enable --now cyberboss-backup.timer
sudo systemctl list-timers cyberboss-backup.timer --all --no-pager
```

该 service 仅生成一个新的 `backup_<24位十六进制>`。它固定写入 R2
`cyberboss-cold/ovh-singapore-vps-1/snapshots/` 与 OCI
`cyberboss-cold-backup/ovh-singapore-vps-1/snapshots/`，不会 list/delete/overwrite
remote object。凭据由 systemd credential slots 临时注入；日志和 receipt 不包含 token、
PAR、Prompt、微信内容或绝对路径。

R2 使用仅在 Linux backup service 内刷新的 OAuth access token：初始 refresh credential 由
systemd credential slot 提供，轮换后的 refresh state 与短期 access token 仅在受限
`/var/lib/cyberboss`/`/run` 路径保存。刷新失败会阻断本次 backup，绝不降级为 Mac 常驻进程、
手工复制 token 或模型调用。

## 隔离恢复

从上一条 backup journal 的 JSON 读取 `backup_id`，再运行：

```bash
sudo systemctl start cyberboss-restore@backup_<24位十六进制>.service
sudo systemctl status cyberboss-restore@backup_<24位十六进制>.service --no-pager
sudo journalctl -u cyberboss-restore@backup_<24位十六进制>.service -n 80 --no-pager
```

恢复只从同一 R2 精确 key 下载 `runtime.sqlite3` 与 `manifest.json`，校验 SHA-256、
SQLite integrity 和 logical digest；恢复目录使用 network-disabled 的临时隔离路径，
`promoted=false`，绝不覆盖运行中的 Runtime DB。OCI 现有 PAR 若为 write-only，日志会
明确为 `activation_pending_write_only_par`，但 R2 readback 仍是有效的恢复 Oracle。

## 回滚与安全边界

```bash
sudo systemctl disable --now cyberboss-backup.timer
sudo systemctl stop cyberboss-backup.service
```

这只停止后续 CB-530 backup job，不删除本地或远端 immutable backup。若必须回退应用
release，沿用已验收的 `previous` 指针流程；在回退前先停 timer，回退后重新检查
`cyberboss-cloud.service`、Cloudflare Access 和 Status。任何 hash mismatch、scope drift、
secret/PII 检测或非零模型计数均应 fail closed，不得重试覆盖对象。
