#!/bin/sh
# Limited S18/P03 runtime self-heal for the owned ABD observation container.
# It never starts a stopped container, changes routes, or accesses external systems.
set -eu

CONTAINER_NAME='abd-v0001-observation-runtime'
EXPECTED_RUNTIME_LABEL='observation-only'
EXPECTED_VERSION_LABEL='0.0.0.1'
EXPECTED_RESTART_POLICY='unless-stopped'
STATE_DIR='/run/abd-v0001-observation-watchdog'
RESTART_HISTORY="$STATE_DIR/restart-epochs"
MAX_RESTARTS_PER_HOUR=3

mkdir -p -m 0700 "$STATE_DIR"
chmod 0700 "$STATE_DIR"

inspection=$(
  /usr/bin/docker inspect --format '{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}unavailable{{end}}|{{index .Config.Labels "com.linze.abd.runtime"}}|{{index .Config.Labels "com.linze.abd.version"}}|{{.HostConfig.RestartPolicy.Name}}' "$CONTAINER_NAME" 2>/dev/null
) || {
  printf '%s\n' 'abd observation watchdog: owned container is unavailable; leaving it untouched' >&2
  exit 10
}

IFS='|' read -r running health_status runtime_label version_label restart_policy <<EOF
$inspection
EOF

if [ "$runtime_label" != "$EXPECTED_RUNTIME_LABEL" ] \
  || [ "$version_label" != "$EXPECTED_VERSION_LABEL" ] \
  || [ "$restart_policy" != "$EXPECTED_RESTART_POLICY" ]; then
  printf '%s\n' 'abd observation watchdog: ownership or restart-policy mismatch; leaving container untouched' >&2
  exit 11
fi

if [ "$running" != 'true' ]; then
  printf '%s\n' 'abd observation watchdog: container is stopped; respecting unless-stopped and leaving it untouched' >&2
  exit 12
fi

case "$health_status" in
  healthy|starting)
    exit 0
    ;;
  unhealthy)
    ;;
  *)
    printf '%s\n' 'abd observation watchdog: health state is not actionable; leaving container untouched' >&2
    exit 13
    ;;
esac

if [ -L "$RESTART_HISTORY" ] || { [ -e "$RESTART_HISTORY" ] && [ ! -f "$RESTART_HISTORY" ]; }; then
  printf '%s\n' 'abd observation watchdog: restart history is unsafe; leaving container untouched' >&2
  exit 14
fi

now_epoch=$(date +%s)
cutoff_epoch=$((now_epoch - 3600))
recent_epochs=''
if [ -f "$RESTART_HISTORY" ]; then
  recent_epochs=$(awk -v cutoff="$cutoff_epoch" '$1 ~ /^[0-9]+$/ && $1 >= cutoff { print $1 }' "$RESTART_HISTORY")
fi
recent_count=$(printf '%s\n' "$recent_epochs" | awk 'NF { count += 1 } END { print count + 0 }')

if [ "$recent_count" -ge "$MAX_RESTARTS_PER_HOUR" ]; then
  printf '%s\n' 'abd observation watchdog: restart budget exhausted; leaving container untouched' >&2
  exit 15
fi

history_tmp=$(mktemp "$STATE_DIR/restart-epochs.XXXXXX")
cleanup() {
  rm -f "$history_tmp"
}
trap cleanup EXIT HUP INT TERM

if [ -n "$recent_epochs" ]; then
  printf '%s\n' "$recent_epochs" > "$history_tmp"
else
  : > "$history_tmp"
fi
printf '%s\n' "$now_epoch" >> "$history_tmp"

printf '%s\n' 'abd observation watchdog: restarting unhealthy owned observation container' >&2
/usr/bin/docker restart --time 10 "$CONTAINER_NAME" >/dev/null
mv -f "$history_tmp" "$RESTART_HISTORY"
trap - EXIT HUP INT TERM

