#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root=$(pwd)
if [[ ! -f .env ]]; then
  echo ".env is missing." >&2
  exit 2
fi
set -a
source .env
set +a
run_user="${SUDO_USER:-$(id -un)}"
run_group="$(id -gn "$run_user")"
run_home="$(getent passwd "$run_user" | cut -d: -f6)"
if [[ -z "$run_home" ]]; then
  echo "Could not determine the runtime user's home directory." >&2
  exit 2
fi
if ! id -nG "$run_user" | tr ' ' '\n' | grep -qx docker && [[ "$run_user" != root ]]; then
  echo "Runtime user $run_user is not in the docker group." >&2
  exit 2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for source in deploy/systemd/*.service deploy/systemd/*.timer; do
  target="$tmp/$(basename "$source")"
  sed \
    -e "s|__PROJECT_DIR__|$root|g" \
    -e "s|__RUN_USER__|$run_user|g" \
    -e "s|__RUN_GROUP__|$run_group|g" \
    -e "s|__RUN_HOME__|$run_home|g" \
    "$source" > "$target"
done
sudo cp "$tmp"/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobhuntos-private-sync.timer
sudo systemctl start jobhuntos-private-sync.service
if [[ "${R2_SYNC_ENABLED:-false}" == "true" && -n "${RCLONE_R2_REMOTE:-}" ]]; then
  sudo systemctl enable --now jobhuntos-r2-sync.timer
  sudo systemctl start jobhuntos-r2-sync.service
else
  sudo systemctl disable --now jobhuntos-r2-sync.timer >/dev/null 2>&1 || true
fi
systemctl list-timers 'jobhuntos-*' --no-pager
