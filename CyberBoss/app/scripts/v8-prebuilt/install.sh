#!/usr/bin/env bash
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo '请使用管理员安装入口执行，不要手工复制文件。' >&2; exit 1; }
release_root="${CYBERBOSS_RELEASE_ROOT:-/opt/cyberboss-cloud}"
[[ -d "$release_root/current" ]] || { echo '当前 release 链接不存在。' >&2; exit 1; }
install -d -m 0700 -o cyberboss -g cyberboss /var/lib/cyberboss /var/lib/cyberboss/backups
install -d -m 0750 -o cyberboss -g cyberboss /var/log/cyberboss /run/cyberboss
install -d -m 0700 -o root -g root /etc/cyberboss /etc/cyberboss/credentials
install -m 0644 "$release_root/current/starter_kit/deploy/systemd/cyberboss.service" /etc/systemd/system/cyberboss.service
install -m 0644 "$release_root/current/starter_kit/deploy/systemd/cyberboss-health.service" /etc/systemd/system/cyberboss-health.service
install -m 0644 "$release_root/current/starter_kit/deploy/systemd/cyberboss-health.timer" /etc/systemd/system/cyberboss-health.timer
install -m 0644 "$release_root/current/starter_kit/deploy/systemd/cyberboss-backup.service" /etc/systemd/system/cyberboss-backup.service
install -m 0644 "$release_root/current/starter_kit/deploy/systemd/cyberboss-backup.timer" /etc/systemd/system/cyberboss-backup.timer
systemctl daemon-reload
printf '%s\n' '安装资产已就位；凭据和真实迁移仍由授权部署步骤提供。'
