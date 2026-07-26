#!/usr/bin/env bash
set -Eeuo pipefail

FAIL=()
for path in /opt/cyberboss-cloud/releases /var/lib/cyberboss /srv/cyberboss-workspaces /etc/cyberboss; do
  [[ -d "$path" ]] || FAIL+=("missing_dir:$path")
done
for path in /etc/cyberboss/cyberboss.env /etc/cyberboss/workspaces.json; do
  [[ -r "$path" ]] || FAIL+=("missing_or_unreadable:$path")
done
for unit in cyberboss-cloud.service cyberboss-status.timer cyberboss-backup.timer cyberboss-selfheal.timer; do
  systemctl cat "$unit" >/dev/null 2>&1 || FAIL+=("unit_missing:$unit")
done
if [[ -r /etc/cyberboss/cyberboss.env ]] && grep -Eq 'REPLACE_' /etc/cyberboss/cyberboss.env; then
  echo 'ACTIVATION_STATE=activation_pending:environment_placeholders'
fi
if ((${#FAIL[@]})); then
  for item in "${FAIL[@]}"; do echo "FAIL_REASON=$item"; done
  echo 'INSTALL_VERIFY=FAIL'
  exit 1
fi
echo 'INSTALL_VERIFY=PASS'
