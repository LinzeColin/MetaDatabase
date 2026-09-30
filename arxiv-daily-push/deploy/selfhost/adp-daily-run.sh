#!/usr/bin/env bash
# adp-daily-run.sh <daily|backfill> —— 由 systemd timer 调用：用「当前线上版本」的镜像起一个一次性容器跑 run_daily.mjs。
#
#   daily     抓取 → 选择 → 讲义 → 建卡（20:30 UTC = 悉尼 06:30），arXiv 失败带退避重试，见 app/run_daily.mjs
#   backfill  arXiv 历史回填一页（02:30 / 08:30 UTC）
#
# 退出码原样透传容器的：0 成功；1 运行失败；2 重试用尽 arXiv 仍没抓到；3 抓取成功但备份失败；
# 另：75 = 上一次同名任务还在跑（本次放弃，不叠加）；78 = 缺配置 / 找不到镜像。非 0 → systemd 判 unit 失败 → OnFailure。
#
# 资源限额落在容器上（docker 另起 cgroup，unit 里的 Memory/CPU 限制管不到它）：256m 内存（不允许 swap）、1 CPU、128 个进程。
set -uo pipefail
export LC_ALL=C

JOB=${1:-}
case "$JOB" in daily|backfill) ;; *) echo "用法: $0 <daily|backfill>" >&2; exit 64 ;; esac

APP=${ADP_APP:-adp}
CONF=${ADP_CONF:-/etc/linze-pull-deploy/$APP.env}
[ -r "$CONF" ] || { echo "缺配置 $CONF（先跑 install.sh）" >&2; exit 78; }
set -a; . "$CONF"; set +a
DATA=${ADP_DATA_HOST_DIR:-/var/lib/adp}
MEMORY=${MEMORY:-256m}
[ -d "$DATA" ] || { echo "缺数据目录 $DATA" >&2; exit 78; }

LOCK_DIR=${LINZE_PULL_LOCK_DIR:-/run/lock}
exec 9>"$LOCK_DIR/adp-job-$JOB.lock"
flock -n 9 || { echo "$(date -u +%FT%TZ) adp-$JOB 上一次还在跑，本次放弃" >&2; exit 75; }

# 用线上容器正在用的镜像；还没有线上容器（首次部署前）就退到本机最新的 $IMAGE 镜像
IMG=$(docker ps --filter "label=linze.pull.app=$APP" --filter status=running --format '{{.Image}}' | head -n1)
[ -n "$IMG" ] || IMG=$(docker images --format '{{.Repository}}:{{.Tag}}' "$IMAGE" 2>/dev/null | head -n1)
[ -n "$IMG" ] || { echo "找不到 $APP 的镜像：拉取式部署还没成功部署过（先看 adp-pull-deploy.sh status $APP）" >&2; exit 78; }

NAME="adp-job-$JOB"
docker rm -f "$NAME" >/dev/null 2>&1
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1; }
trap cleanup EXIT TERM INT

echo "$(date -u +%FT%TZ) adp-$JOB 开始，镜像 $IMG"
# --label 覆盖镜像里烘进去的 linze.pull.app：否则拉取式部署器会把这个一次性容器当成「线上容器」。
timeout --signal=TERM --kill-after=60 "${ADP_JOB_TIMEOUT_SECONDS:-9000}" \
  docker run --rm --name "$NAME" --init \
    --label "linze.pull.app=$APP-job" \
    --read-only --tmpfs /tmp:rw,noexec,nosuid,size=32m \
    --cap-drop ALL --security-opt no-new-privileges \
    --memory "$MEMORY" --memory-swap "$MEMORY" --cpus 1 --pids-limit 128 \
    --user 10001:10001 -v "$DATA:/data" \
    -e ADP_DATA_DIR=/data \
    -e "ADP_RETRY_BACKOFF_SECONDS=${ADP_RETRY_BACKOFF_SECONDS:-600,1200}" \
    --log-opt max-size=10m --log-opt max-file=3 \
    "$IMG" node /app/run_daily.mjs "$JOB"
rc=$?
echo "$(date -u +%FT%TZ) adp-$JOB 结束，退出码 $rc"
exit "$rc"
