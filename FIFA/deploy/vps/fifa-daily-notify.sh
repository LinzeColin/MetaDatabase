#!/usr/bin/env bash
# fifa-daily-notify.sh —— fifa-daily.service 结束时（ExecStopPost）调用：把成败写进 journal，并给 Gatus 推一次心跳。
# 成败取自 systemd 给的 $SERVICE_RESULT（success = 今天有新报告）。推送失败只记 journal，不影响 unit 结果。
# Gatus 端点是「外部端点」：30 小时内没有任何推送，Gatus 自己判红（覆盖「timer 整个没跑」这种没人能自报的故障）。
set -uo pipefail
CONF=${FIFA_CONF:-/etc/fifa-daily/fifa-daily.env}
[ -r "$CONF" ] && { set -a; . "$CONF"; set +a; }
res=${SERVICE_RESULT:-unknown}
if [ "$res" = success ]; then
  logger -t fifa-daily -p user.info "运行成功：今天有新报告（${PUBLIC_URL:-}）"
  ok=true; err=""
else
  logger -t fifa-daily -p user.err "运行失败：result=$res exit=${EXIT_STATUS:-?}；看 journalctl -u fifa-daily.service -n 80；线上保留旧页面"
  ok=false; err="fifa-daily failed: result=$res exit=${EXIT_STATUS:-?}"
fi
TOKEN_FILE=${GATUS_TOKEN_FILE:-/etc/fifa-daily/gatus.token}
if [ -n "${GATUS_URL:-}" ] && [ -r "$TOKEN_FILE" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -X POST \
    -H "Authorization: Bearer $(tr -d '[:space:]' < "$TOKEN_FILE")" \
    --get --data-urlencode "success=$ok" --data-urlencode "error=$err" \
    "$GATUS_URL/api/v1/endpoints/${GATUS_KEY}/external" 2>/dev/null) || code=000
  if [ "$code" = 200 ]; then logger -t fifa-daily -p user.info "已向 Gatus 推送心跳（success=$ok）"
  else logger -t fifa-daily -p user.warning "Gatus 心跳推送失败（HTTP $code）"; fi
fi
exit 0
