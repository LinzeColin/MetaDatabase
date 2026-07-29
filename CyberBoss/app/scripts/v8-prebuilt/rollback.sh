#!/usr/bin/env bash
set -euo pipefail
root="${CYBERBOSS_RELEASE_ROOT:-/opt/cyberboss-cloud}"
[[ -L "$root/current" && -L "$root/previous" ]] || { echo '缺少 current/previous 不可变 release。' >&2; exit 1; }
current="$(readlink -f "$root/current")"; previous="$(readlink -f "$root/previous")"
ln -sfn "$previous" "$root/current.next" && mv -Tf "$root/current.next" "$root/current"
ln -sfn "$current" "$root/previous.next" && mv -Tf "$root/previous.next" "$root/previous"
systemctl restart cyberboss.service
/opt/cyberboss-cloud/current/starter_kit/scripts/doctor.sh
printf '%s\n' 'CyberBoss 已回滚到上一不可变版本。'
