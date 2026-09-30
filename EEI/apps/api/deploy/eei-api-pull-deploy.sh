#!/usr/bin/env bash
# eei-api-pull-deploy.sh —— EEI 公开数据接口（eei-api）的拉取式部署。
#
# 派生自 apps/universe/deploy/eei-pull-deploy.sh（LinzeHomeHub 拉取式部署模板）。区别：eei-api 不对公网、没有域名、
# 没有 Traefik 与 TLS，只在 docker 网络里被「商域宇宙」的 nginx 容器按容器别名访问，所以：
#   1. 候选容器先放进 eei-db 所在的 docker 网络（STAGING_NETWORK，留空则从 DB_CONTAINER 自动取）；
#      健康检查（/health 会真连库并校验角色只读）+ 直连探活通过后，才接入 DOCKER_NETWORK（宇宙容器所在网络）并挂别名 NET_ALIAS；
#   2. 停旧容器后，用同一个镜像起一次性容器在 DOCKER_NETWORK 里按别名回测一次 /health（宇宙容器走的就是这条路）；
#   3. 变化检测看 TREE_PATHS 里每个路径的 git 哈希（合并成一个指纹）：monorepo 里无关目录的提交不会触发重建；
#      取源码时 sparse-checkout 只展开 SPARSE_PATHS；构建上下文是 SUBDIR（= EEI），Dockerfile 在 apps/api/deploy/。
# 任何一步失败都回滚：删新容器、拉起已停的旧容器、按退避重试（5 分钟起翻倍，封顶 6 小时），有新提交立刻重来。
#
# 不做：不碰任何令牌（仓库 URL 里带凭据会被拒绝；数据库密码只在服务器的 600 文件里，由 RUN_EXTRA_ARGS 的 --env-file 注入）；
# 不自我更新 —— 脚本和 unit 只由 install.sh 安装；仓库里的版本与已安装版本不一致时只在状态里标 script_drift。
#
# 用法：
#   eei-api-pull-deploy.sh run <app> [--branch <分支>] [--force]   # timer 调用；--branch 仅用于故障演练
#   eei-api-pull-deploy.sh status <app>
# 配置：/etc/linze-pull-deploy/<app>.env（即本目录 eei-api.env）。
set -uo pipefail
export GIT_TERMINAL_PROMPT=0 LC_ALL=C

CONF_DIR=${LINZE_PULL_CONF_DIR:-/etc/linze-pull-deploy}
STATE_ROOT=${LINZE_PULL_STATE_ROOT:-/var/lib/linze-pull-deploy}
LOCK_DIR=${LINZE_PULL_LOCK_DIR:-/run/lock}
SELF=$(readlink -f "$0")

usage() { echo "用法: $0 run <app> [--branch <分支>] [--force] | status <app>" >&2; exit 64; }
CMD=${1:-}; APP=${2:-}
[ -n "$CMD" ] && [ -n "$APP" ] || usage
shift 2
BRANCH_OVERRIDE=""; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --branch) BRANCH_OVERRIDE=${2:-}; [ -n "$BRANCH_OVERRIDE" ] || usage; shift 2 ;;
    *) usage ;;
  esac
done
[[ $APP =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "app 名只允许小写字母、数字和 -" >&2; exit 64; }

CONF="$CONF_DIR/$APP.env"
[ -r "$CONF" ] || { echo "缺配置文件 $CONF" >&2; exit 78; }
set -a; . "$CONF"; set +a
: "${REPO_URL:?配置缺 REPO_URL}" "${IMAGE:?配置缺 IMAGE}"
BRANCH=${BRANCH_OVERRIDE:-${BRANCH:-main}}
SUBDIR=${SUBDIR:-.}
DOCKERFILE=${DOCKERFILE:-Dockerfile}
CONTAINER_PORT=${CONTAINER_PORT:-8000}
HEALTH_PATH=${HEALTH_PATH:-/health}
HEALTH_CODE=${HEALTH_CODE:-200}
HEALTH_BODY_REGEX=${HEALTH_BODY_REGEX:-}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-90}
DOCKER_NETWORK=${DOCKER_NETWORK:-coolify}
STAGING_NETWORK=${STAGING_NETWORK:-}
DB_CONTAINER=${DB_CONTAINER:-eei-db}
NET_ALIAS=${NET_ALIAS:-eei-api}
SPARSE_PATHS=${SPARSE_PATHS:-$SUBDIR}
TREE_PATHS=${TREE_PATHS:-}
MEMORY=${MEMORY:-256m}
BUILD_TIMEOUT=${BUILD_TIMEOUT:-900}
KEEP_PREV=${KEEP_PREV:-1}
SELF_DIR_IN_REPO=${SELF_DIR_IN_REPO:-EEI/apps/api/deploy}
RUN_EXTRA_ARGS=${RUN_EXTRA_ARGS:-}
declare -a EXTRA_ARGS=(); read -r -a EXTRA_ARGS <<< "$RUN_EXTRA_ARGS"

[[ $REPO_URL =~ ^https://[^@[:space:]]+$ ]] || { echo "REPO_URL 必须是不带凭据的 https 公开地址" >&2; exit 78; }
[[ $IMAGE =~ ^[a-z0-9][a-z0-9._/-]*$ ]] || { echo "IMAGE 格式不对" >&2; exit 78; }
[[ $NET_ALIAS =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "NET_ALIAS 格式不对" >&2; exit 78; }
[[ $DB_CONTAINER =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { echo "DB_CONTAINER 格式不对" >&2; exit 78; }
[[ $SUBDIR =~ ^[A-Za-z0-9._/-]+$ && $SUBDIR != /* && $SUBDIR != *..* ]] || { echo "SUBDIR 格式不对" >&2; exit 78; }
for _p in $SPARSE_PATHS $TREE_PATHS; do
  [[ $_p =~ ^[A-Za-z0-9._/-]+$ && $_p != /* && $_p != *..* ]] || { echo "SPARSE_PATHS/TREE_PATHS 含非法路径 $_p" >&2; exit 78; }
done

STATE_DIR="$STATE_ROOT/$APP"
STATE_FILE="$STATE_DIR/state.env"
JSON_FILE="$STATE_DIR/status.json"
WORK="$STATE_DIR/repo"
STATE_KEYS=(S_state S_branch S_target_sha S_deployed_sha S_container S_last_check_at S_last_deploy_at \
            S_last_error S_fail_sha S_fail_count S_next_retry_epoch S_script_drift S_seen_sha S_seen_tree S_deployed_tree)
for _k in "${STATE_KEYS[@]}"; do printf -v "$_k" '%s' ""; done

log() { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$APP" "$*"; }
jesc() { local s=${1//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/ }; s=${s//$'\t'/ }; printf '%s' "$s"; }

load_state() { [ -f "$STATE_FILE" ] && . "$STATE_FILE"; return 0; }
save_state() {
  local k first=1
  : > "$STATE_FILE.tmp"
  for k in "${STATE_KEYS[@]}"; do printf '%s=%q\n' "$k" "${!k-}" >> "$STATE_FILE.tmp"; done
  mv -f "$STATE_FILE.tmp" "$STATE_FILE"
  {
    printf '{'
    for k in "${STATE_KEYS[@]}"; do
      [ "$first" = 1 ] || printf ','
      first=0
      printf '"%s":"%s"' "${k#S_}" "$(jesc "${!k-}")"
    done
    printf ',"app":"%s","repo":"%s","alias":"%s"}\n' "$APP" "$(jesc "$REPO_URL")" "$NET_ALIAS"
  } > "$JSON_FILE.tmp"
  mv -f "$JSON_FILE.tmp" "$JSON_FILE"
}

# ---------- 小工具 ----------
live_container() { docker ps -q --filter "label=linze.pull.app=$APP" --filter status=running | head -n1; }
label_of() { docker inspect -f "{{index .Config.Labels \"$2\"}}" "$1" 2>/dev/null; }
name_of() { docker inspect -f '{{.Name}}' "$1" 2>/dev/null | sed 's|^/||'; }
health_of() { docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$1" 2>/dev/null; }
http_probe() { # url outfile -> 回显 HTTP 状态码（连不上回显 000）
  local url=$1 out=$2 c
  c=$(curl -s --max-time 10 -o "$out" -w '%{http_code}' "$url" 2>/dev/null)
  echo "${c:-000}"
}
probe_ok() { # code bodyfile
  [ "$1" = "$HEALTH_CODE" ] || return 1
  [ -z "$HEALTH_BODY_REGEX" ] || grep -Eq -- "$HEALTH_BODY_REGEX" "$2"
}

# ---------- status ----------
do_status() {
  echo "== 状态文件 $JSON_FILE"
  if [ -f "$JSON_FILE" ]; then cat "$JSON_FILE"; else echo "(尚无状态：还没跑过)"; fi
  echo "== 容器（label linze.pull.app=$APP）"
  docker ps -a --filter "label=linze.pull.app=$APP" --format '{{.Names}}  {{.Status}}  commit={{.Label "linze.pull.commit"}}'
  echo "== 定时器"
  systemctl list-timers "eei-api-pull.timer" --no-pager 2>/dev/null | sed -n '1,3p'
}

# ---------- run ----------
CAND=""; RETIRED=(); LIVE_SHA=""; LIVE_TREE=""; TARGET=""; TREE=""

fail() { # 回滚：删新容器、拉起已停的旧容器、记退避，然后 exit 1
  local msg=$1 c n wait
  log "失败：$msg"
  [ -n "$CAND" ] && docker logs --tail 20 "$CAND" 2>&1 | sed 's/^/  candidate| /'
  # 先把旧容器拉起来，再删新容器，缩短空窗
  for c in ${RETIRED[@]+"${RETIRED[@]}"}; do
    if docker start "$c" >/dev/null 2>&1; then log "已拉起旧容器 $(name_of "$c")"; else log "警告：旧容器 $c 拉不起来"; fi
  done
  [ -n "$CAND" ] && docker rm -f "$CAND" >/dev/null 2>&1
  n=1; [ "$S_fail_sha" = "$TARGET" ] && n=$(( ${S_fail_count:-0} + 1 ))
  wait=$(( 300 * (1 << (n > 7 ? 6 : n - 1)) )); [ "$wait" -gt 21600 ] && wait=21600
  S_fail_sha=$TARGET; S_fail_count=$n; S_next_retry_epoch=$(( $(date +%s) + wait ))
  S_last_error=$msg; S_state=failing
  save_state
  log "线上保持 ${LIVE_SHA:0:12}；同一提交最早 ${wait}s 后重试（第 $n 次失败）"
  exit 1
}

fetch_source() {
  local sha=$1 p h=""
  if [ ! -d "$WORK/.git" ]; then
    rm -rf "$WORK"; git init -q "$WORK" || return 1
  fi
  git -C "$WORK" remote remove origin >/dev/null 2>&1
  git -C "$WORK" remote add origin "$REPO_URL" || return 1
  timeout 180 git -C "$WORK" -c credential.helper= fetch -q --depth 1 --filter=blob:none origin "$sha" || return 1
  # shellcheck disable=SC2086
  git -C "$WORK" sparse-checkout set --cone $SPARSE_PATHS || return 1
  git -C "$WORK" checkout -q -f --detach FETCH_HEAD || return 1
  git -C "$WORK" clean -ffdxq
  [ "$(git -C "$WORK" rev-parse HEAD)" = "$sha" ] || return 1
  [ -f "$WORK/$SUBDIR/$DOCKERFILE" ] || { log "仓库里找不到 $SUBDIR/$DOCKERFILE"; return 1; }
  # 变化指纹：TREE_PATHS 里每个路径的 tree/blob 哈希拼起来再哈希一次；没配 TREE_PATHS 就看整个 SUBDIR
  for p in ${TREE_PATHS:-$SUBDIR}; do
    h="$h$(git -C "$WORK" rev-parse "HEAD:$p" 2>/dev/null)"
    [[ $h =~ ^[0-9a-f]{40,}$ ]] || { log "取不到 $p 的 git 哈希"; return 1; }
  done
  TREE=$(printf '%s' "$h" | sha1sum | cut -d' ' -f1)
}

build_image() {
  local sha=$1 ctx="$WORK/$SUBDIR" logf="$STATE_DIR/last-build.log"
  if docker image inspect "$IMAGE:$sha" >/dev/null 2>&1; then log "镜像 $IMAGE:${sha:0:12} 已存在，跳过构建"; return 0; fi
  log "构建 $IMAGE:${sha:0:12}"
  timeout "$BUILD_TIMEOUT" docker build --progress=plain \
    --label "linze.pull.commit=$sha" --label "linze.pull.tree=$TREE" --label "linze.pull.app=$APP" \
    --build-arg "SOURCE_COMMIT=$sha" \
    -t "$IMAGE:$sha" -f "$ctx/$DOCKERFILE" "$ctx" >"$logf" 2>&1
  local rc=$?
  if [ "$rc" -ne 0 ]; then tail -n 40 "$logf" | sed 's/^/  build| /'; return 1; fi
  tail -n 2 "$logf" | sed 's/^/  build| /'
}

resolve_staging_network() { # STAGING_NETWORK 留空时，取 DB_CONTAINER 所在的第一个用户自定义网络
  [ -n "$STAGING_NETWORK" ] && return 0
  STAGING_NETWORK=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$DB_CONTAINER" 2>/dev/null \
    | grep -vx -e bridge -e host -e none -e '' | head -n1)
  [ -n "$STAGING_NETWORK" ]
}

start_candidate() {
  local sha=$1 name="$APP-${sha:0:12}-$(date +%H%M%S)"
  local hp="http://127.0.0.1:${CONTAINER_PORT}${HEALTH_PATH}"
  docker rm -f "$name" >/dev/null 2>&1
  # 先记名字：即使 run 半途失败，fail() 也会把它清掉
  CAND=$name
  # 先放进 eei-db 所在网络（宇宙容器不在这个网络上，看不见它）：直连探活通过后才接入 $DOCKER_NETWORK 并挂别名。
  # 切换成功前不设自动重启：崩溃的候选容器直接暴露为 exited。不发布任何端口（没有 -p）。
  docker run -d --name "$name" --network "$STAGING_NETWORK" --restart no \
    --memory "$MEMORY" --pids-limit 128 --security-opt no-new-privileges ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd "python -c \"import urllib.request as u; u.urlopen('$hp', timeout=3)\"" \
    --health-interval 5s --health-timeout 4s --health-retries 3 --health-start-period 5s \
    --label "linze.pull.app=$APP" --label "linze.pull.commit=$sha" --label "linze.pull.tree=$TREE" \
    "$IMAGE:$sha" >/dev/null
}

WH_STATE=""
wait_healthy() { # 0=健康；1=没起来/已退出/超时（最后状态在 WH_STATE）
  local c=$1 t=0
  while [ "$t" -lt "$HEALTH_TIMEOUT" ]; do
    WH_STATE=$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null)
    case "$WH_STATE" in
      "running healthy") return 0 ;;
      exited*|dead*|restarting*|"") return 1 ;;
    esac
    sleep 2; t=$(( t + 2 ))
  done
  return 1
}

postcheck() { # 切流量之后：用同一镜像起一次性容器，在 $DOCKER_NETWORK 里按别名访问 /health，必须 200 且报出新提交号
  local sha=$1 i=0 out
  while [ "$i" -lt 10 ]; do
    out=$(docker run --rm --network "$DOCKER_NETWORK" --entrypoint python --cap-drop ALL --user 10001 --memory 64m \
      "$IMAGE:$sha" -c "import urllib.request as u; r=u.urlopen('http://$NET_ALIAS:$CONTAINER_PORT$HEALTH_PATH', timeout=5); print(r.status); print(r.read().decode())" 2>/dev/null)
    if [ "$(printf '%s' "$out" | head -n1)" = "$HEALTH_CODE" ] \
       && { [ -z "$HEALTH_BODY_REGEX" ] || printf '%s' "$out" | grep -Eq -- "$HEALTH_BODY_REGEX"; } \
       && printf '%s' "$out" | grep -q "$sha"; then
      return 0
    fi
    sleep 3; i=$(( i + 1 ))
  done
  return 1
}

check_drift() { # 只报告，不自更新
  local d="" f
  [ -d "$WORK/$SELF_DIR_IN_REPO" ] || { S_script_drift="仓库里无 $SELF_DIR_IN_REPO，未比对"; return 0; }
  cmp -s "$SELF" "$WORK/$SELF_DIR_IN_REPO/eei-api-pull-deploy.sh" || d="$d eei-api-pull-deploy.sh"
  for f in eei-api-pull.service eei-api-pull.timer; do
    cmp -s "/etc/systemd/system/$f" "$WORK/$SELF_DIR_IN_REPO/$f" || d="$d $f"
  done
  cmp -s "$CONF" "$WORK/$SELF_DIR_IN_REPO/$APP.env" || d="$d $APP.env"
  if [ -z "$d" ]; then S_script_drift="ok"; else S_script_drift="与仓库不一致:$d（在服务器跑 deploy/install.sh 同步）"; log "$S_script_drift"; fi
}

prune_old() { # 尽力清理：只保留 KEEP_PREV 个已停的旧版本容器和当前镜像
  local sha=$1 c n=0 t
  for c in $(docker ps -aq --filter "label=linze.pull.app=$APP" --filter status=exited --filter status=created --filter status=dead); do
    n=$(( n + 1 )); [ "$n" -le "$KEEP_PREV" ] && continue
    docker rm "$c" >/dev/null 2>&1 && log "已删除更旧的容器 $c"
  done
  for t in $(docker images --format '{{.Tag}}' "$IMAGE"); do
    [ "$t" = "$sha" ] || docker image rm "$IMAGE:$t" >/dev/null 2>&1
  done
  return 0
}

do_run() {
  mkdir -p "$STATE_DIR" || exit 73
  exec 9>"$LOCK_DIR/eei-api-pull-deploy-$APP.lock"
  flock -n 9 || { log "上一轮还在跑，本轮跳过"; exit 0; }
  load_state
  local now live sha direct_ip direct_tmp="$STATE_DIR/direct.body" code c
  now=$(date +%s)
  S_last_check_at=$(date -u +%FT%TZ); S_branch=$BRANCH

  sha=$(timeout 30 git -c credential.helper= ls-remote "$REPO_URL" "refs/heads/$BRANCH" 2>/dev/null | awk 'NR==1{print $1}')
  if ! [[ $sha =~ ^[0-9a-f]{40}$ ]]; then
    S_last_error="ls-remote 失败（网络或仓不可达），线上不动"; log "$S_last_error"; save_state; exit 0
  fi
  TARGET=$sha; S_target_sha=$sha

  live=$(live_container)
  if [ -n "$live" ]; then LIVE_SHA=$(label_of "$live" linze.pull.commit); LIVE_TREE=$(label_of "$live" linze.pull.tree); fi
  local live_ok=0
  [ -n "$live" ] && [ "$(health_of "$live")" = healthy ] && live_ok=1
  if [ "$FORCE" = 0 ] && [ "$live_ok" = 1 ]; then
    if [ "$LIVE_SHA" = "$sha" ]; then
      S_state=up-to-date; S_deployed_sha=$sha; S_container=$(name_of "$live"); S_last_error=""
      log "已是最新 ${sha:0:12}"; save_state; exit 0
    fi
    # 整仓提交号变了但上次已经确认过相关路径内容与线上一致：不必再取源码
    if [ "$S_seen_sha" = "$sha" ] && [ -n "$LIVE_TREE" ] && [ "$S_seen_tree" = "$LIVE_TREE" ]; then
      S_state=up-to-date; S_container=$(name_of "$live"); S_last_error=""
      log "仓库提交 ${sha:0:12} 没改相关路径，线上内容不变（指纹 ${LIVE_TREE:0:12}）"; save_state; exit 0
    fi
  fi
  if [ "$FORCE" = 0 ] && [ "$S_fail_sha" = "$sha" ] && [ "${S_next_retry_epoch:-0}" -gt "$now" ]; then
    S_state=failing; log "提交 ${sha:0:12} 上次部署失败（$S_last_error），退避到 $(date -u -d "@$S_next_retry_epoch" +%T)Z 前不重试；线上仍是 ${LIVE_SHA:0:12}"
    save_state; exit 1
  fi
  [ -n "$live" ] && [ "$live_ok" = 0 ] && log "线上容器不健康（$(health_of "$live")），重新部署"

  # 取源码（只展开 SPARSE_PATHS，blob:none 部分克隆）后看指纹：内容没变就不重建
  fetch_source "$sha" || fail "取源码失败"
  if [ "$FORCE" = 0 ] && [ "$live_ok" = 1 ] && [ "$TREE" = "$LIVE_TREE" ]; then
    S_state=up-to-date; S_seen_sha=$sha; S_seen_tree=$TREE; S_container=$(name_of "$live"); S_last_error=""
    S_fail_sha=""; S_fail_count=0; S_next_retry_epoch=""
    log "仓库提交 ${sha:0:12} 没改相关路径，线上内容不变（指纹 ${TREE:0:12}）"; save_state; exit 0
  fi
  S_state=deploying; save_state
  log "开始部署 ${sha:0:12}（线上 ${LIVE_SHA:-无}）指纹 ${TREE:0:12} 分支 $BRANCH$([ "$FORCE" = 1 ] && echo " (force)")"
  check_drift
  resolve_staging_network || fail "找不到 $DB_CONTAINER 所在的 docker 网络（可在 env 里直接写 STAGING_NETWORK）"
  build_image "$sha" || fail "docker build 失败（日志尾部见上）"
  start_candidate "$sha" || fail "新容器启动失败"
  wait_healthy "$CAND" || fail "新容器没变健康（最后状态：${WH_STATE:-未知}，最多等 ${HEALTH_TIMEOUT}s；/health 连不上库或角色可写都会 503）"
  direct_ip=$(docker inspect -f "{{with index .NetworkSettings.Networks \"$STAGING_NETWORK\"}}{{.IPAddress}}{{end}}" "$CAND")
  [ -n "$direct_ip" ] || fail "拿不到新容器在网络 $STAGING_NETWORK 上的 IP"
  code=$(http_probe "http://$direct_ip:$CONTAINER_PORT$HEALTH_PATH" "$direct_tmp")
  probe_ok "$code" "$direct_tmp" || fail "新容器直连探活不合格（状态 $code，期望 $HEALTH_CODE${HEALTH_BODY_REGEX:+，内容需匹配 $HEALTH_BODY_REGEX}）"
  log "新容器 $CAND 健康、直连探活通过，接入 $DOCKER_NETWORK（别名 $NET_ALIAS）并切换"
  # 停旧：先收集旧容器（不含候选），接入新网络后再停，空窗只有一次 stop 的时间；新旧同别名共存期间 docker DNS 轮询，两边都是好的
  for c in $(docker ps -q --filter "label=linze.pull.app=$APP" --filter status=running); do
    [ "$(name_of "$c")" = "$CAND" ] && continue
    RETIRED+=("$c")
  done
  docker network connect --alias "$NET_ALIAS" "$DOCKER_NETWORK" "$CAND" || fail "新容器接入网络 $DOCKER_NETWORK 失败"
  docker update --restart unless-stopped "$CAND" >/dev/null 2>&1 || log "警告：没能给 $CAND 设 restart=unless-stopped"
  for c in ${RETIRED[@]+"${RETIRED[@]}"}; do
    log "停旧容器 $(name_of "$c")"
    docker stop -t 15 "$c" >/dev/null 2>&1
  done
  postcheck "$sha" || fail "切换后在 $DOCKER_NETWORK 里按别名 $NET_ALIAS 回测 /health 不合格"

  S_state=up-to-date; S_deployed_sha=$sha; S_deployed_tree=$TREE; S_seen_sha=$sha; S_seen_tree=$TREE
  S_container=$CAND; S_last_deploy_at=$(date -u +%FT%TZ)
  S_last_error=""; S_fail_sha=""; S_fail_count=0; S_next_retry_epoch=""
  save_state
  log "部署完成 ${sha:0:12}（线上此前 ${LIVE_SHA:0:12}）"
  prune_old "$sha"
  exit 0
}

case "$CMD" in
  run) do_run ;;
  status) do_status ;;
  *) usage ;;
esac
