#!/bin/sh
# S18/P04 local-only operations sentinel for the owned ABD observation runtime.
# It reports a pause condition on failure and never patches, backs up, sends mail,
# changes routes, accesses external systems, or restarts the runtime.
set -eu

window=${1:-}
case "$window" in
  daily|weekly|monthly)
    ;;
  *)
    printf '%s\n' 'abd observation operations: unknown maintenance window; pause required' >&2
    exit 20
    ;;
esac

CONTAINER_NAME='abd-v0001-observation-runtime'
EXPECTED_RUNTIME_LABEL='observation-only'
EXPECTED_VERSION_LABEL='0.0.0.1'
EXPECTED_RESTART_POLICY='unless-stopped'
WATCHDOG_TIMER='abd-v0001-observation-watchdog.timer'
PRIOR_IMAGE='abd-v0001-observation:0.0.0.1'
RESTART_HISTORY='/run/abd-v0001-observation-watchdog/restart-epochs'

pause() {
  printf '%s\n' "abd observation operations: $1; pause required" >&2
  exit 21
}

inspection=$(
  /usr/bin/docker inspect --format '{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}unavailable{{end}}|{{index .Config.Labels "com.linze.abd.runtime"}}|{{index .Config.Labels "com.linze.abd.version"}}|{{.HostConfig.RestartPolicy.Name}}' "$CONTAINER_NAME" 2>/dev/null
) || pause 'owned container unavailable'

IFS='|' read -r running health_status runtime_label version_label restart_policy <<EOF
$inspection
EOF

[ "$runtime_label" = "$EXPECTED_RUNTIME_LABEL" ] || pause 'ownership label mismatch'
[ "$version_label" = "$EXPECTED_VERSION_LABEL" ] || pause 'version label mismatch'
[ "$restart_policy" = "$EXPECTED_RESTART_POLICY" ] || pause 'restart-policy mismatch'
[ "$running" = 'true' ] || pause 'container stopped'
[ "$health_status" = 'healthy' ] || pause 'container health is not healthy'
[ "$(/usr/bin/systemctl is-active "$WATCHDOG_TIMER")" = 'active' ] || pause 'watchdog timer inactive'
[ "$(/usr/bin/systemctl is-enabled "$WATCHDOG_TIMER")" = 'enabled' ] || pause 'watchdog timer not enabled'

case "$window" in
  weekly)
    /usr/bin/docker image inspect "$PRIOR_IMAGE" >/dev/null 2>&1 || pause 'rollback image unavailable'
    ;;
  monthly)
    if [ -L "$RESTART_HISTORY" ] || { [ -e "$RESTART_HISTORY" ] && [ ! -f "$RESTART_HISTORY" ]; }; then
      pause 'watchdog restart history unsafe'
    fi
    ;;
esac

printf '%s\n' "abd observation operations: $window local maintenance window ready; no owner action required" >&2

