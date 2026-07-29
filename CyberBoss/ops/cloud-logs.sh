#!/usr/bin/env bash
# 看云端后台在干什么。默认跟着实时刷，Control-C 退出。
#
# --namespace=cyberboss 不能省：unit 文件里写了 LogNamespace=cyberboss，
# 应用的输出全在那个独立的 journal 里，不带这个参数只能看到 systemd 自己
# 那几行"Started/Stopped"，会以为程序什么都没打印。
#   ops/cloud-logs.sh          实时跟
#   ops/cloud-logs.sh 100      看最近 100 行就退出
set -euo pipefail
HOST="${CB_DEPLOY_HOST:-139.99.61.6}"
USER_NAME="${CB_DEPLOY_USER:-ubuntu}"
KEY="${CB_DEPLOY_KEY:-$HOME/Documents/Codex/GithubProject/_protected/alpha_deploy_private/linze_ovh_production_ed25519}"
chmod 600 "$KEY" 2>/dev/null || true
if [ -n "${1:-}" ]; then
  exec ssh -i "$KEY" -o BatchMode=yes "$USER_NAME@$HOST" "sudo journalctl --namespace=cyberboss -u cyberboss-cloud.service -n $1 --no-pager"
fi
printf '实时日志（Control-C 退出）\n\n'
exec ssh -t -i "$KEY" "$USER_NAME@$HOST" "sudo journalctl --namespace=cyberboss -u cyberboss-cloud.service -f -n 40"
