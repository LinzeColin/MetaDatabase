#!/usr/bin/env bash
# fifa-daily-pull.sh —— 拉取式更新 FIFA 日报的代码（免令牌，只读公开仓）。
#
# 每次被 timer 唤醒：
#   1. git ls-remote 看公开仓 BRANCH 的最新提交（一次极小的 HTTPS 请求）；没变就退出；
#   2. 变了：只取目录树（--filter=blob:none），比较 SUBDIR 的子树哈希；和线上代码一样就退出（别的目录的提交不打扰它）；
#   3. 不一样：取出 SUBDIR -> 必要时建新的 Python 虚拟环境 -> 跑离线单元测试 -> 通过才把 current 切过去，
#      并请求 fifa-daily.service 立刻按新代码重新出一份报告；
#   4. 任何一步失败：删掉半成品，线上代码不动，unit 记为 failed（journal 有原因）；同一提交按 1h、2h…封顶 6h 退避重试。
# 本脚本以无特权用户 fifa-daily 运行（下载来的代码只在这个用户下执行，不是 root）；脚本本身不自我更新，只由 install.sh 安装。
#
# 用法： fifa-daily-pull.sh run | status
set -uo pipefail
export GIT_TERMINAL_PROMPT=0 LC_ALL=C
CONF=${FIFA_CONF:-/etc/fifa-daily/fifa-daily.env}
[ -r "$CONF" ] || { echo "缺配置 $CONF" >&2; exit 78; }
set -a; . "$CONF"; set +a
: "${REPO_URL:?}" "${SUBDIR:?}" "${BASE:?}"
BRANCH=${BRANCH:-main}; KEEP_CODE=${KEEP_CODE:-2}
TEST_TIMEOUT=${TEST_TIMEOUT:-600}; PIP_TIMEOUT=${PIP_TIMEOUT:-900}
[[ $REPO_URL =~ ^https://[^@[:space:]]+$ ]] || { echo "REPO_URL 必须是不带凭据的 https 公开地址" >&2; exit 78; }
[[ $SUBDIR =~ ^[A-Za-z0-9._/-]+$ && $SUBDIR != /* && $SUBDIR != *..* ]] || { echo "SUBDIR 格式不对" >&2; exit 78; }

PULL="$BASE/pull"; WORK="$PULL/repo"; STATE_FILE="$PULL/state.env"; JSON_FILE="$PULL/status.json"
STATE_KEYS=(S_state S_seen_sha S_deployed_sha S_deployed_tree S_last_check_at S_last_deploy_at S_last_error S_fail_tree S_fail_count S_next_retry_epoch)
for _k in "${STATE_KEYS[@]}"; do printf -v "$_k" '%s' ""; done
log() { printf '%s [fifa-pull] %s\n' "$(date -u +%FT%TZ)" "$*"; }
jesc() { local s=${1//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/ }; s=${s//$'\t'/ }; printf '%s' "$s"; }
load_state() { [ -f "$STATE_FILE" ] && . "$STATE_FILE"; return 0; }
save_state() {
  local k first=1
  : > "$STATE_FILE.tmp"
  for k in "${STATE_KEYS[@]}"; do printf '%s=%q\n' "$k" "${!k-}" >> "$STATE_FILE.tmp"; done
  mv -f "$STATE_FILE.tmp" "$STATE_FILE"
  { printf '{'
    for k in "${STATE_KEYS[@]}"; do [ "$first" = 1 ] || printf ','; first=0; printf '"%s":"%s"' "${k#S_}" "$(jesc "${!k-}")"; done
    printf ',"repo":"%s","subdir":"%s"}\n' "$(jesc "$REPO_URL")" "$SUBDIR"; } > "$JSON_FILE.tmp"
  mv -f "$JSON_FILE.tmp" "$JSON_FILE"
}

do_status() {
  echo "== 拉取状态 $JSON_FILE"; [ -f "$JSON_FILE" ] && cat "$JSON_FILE" || echo "(尚无：还没跑过)"
  echo "== 线上代码"; readlink -f "$BASE/current" 2>/dev/null || echo "(无)"
}

TMP_REL=""
fail() {
  local msg=$1 n wait
  log "失败：$msg"
  [ -n "$TMP_REL" ] && [ -d "$TMP_REL" ] && rm -rf "$TMP_REL"
  n=1; [ "$S_fail_tree" = "$TREE" ] && n=$(( ${S_fail_count:-0} + 1 ))
  wait=$(( 3600 * (1 << (n > 3 ? 3 : n - 1)) )); [ "$wait" -gt 21600 ] && wait=21600
  S_fail_tree=$TREE; S_fail_count=$n; S_next_retry_epoch=$(( $(date +%s) + wait ))
  S_last_error=$msg; S_state=failing; save_state
  log "线上代码保持 ${S_deployed_tree:0:12}；同一版本最早 ${wait}s 后重试（第 $n 次失败）"
  exit 1
}

TREE=""
do_run() {
  mkdir -p "$PULL" "$BASE/releases" "$BASE/venvs" || exit 73
  exec 9>"$PULL/lock"; flock -n 9 || { log "上一轮还在跑，本轮跳过"; exit 0; }
  load_state
  local now sha rel venv rh
  now=$(date +%s); S_last_check_at=$(date -u +%FT%TZ)

  sha=$(timeout 30 git -c credential.helper= ls-remote "$REPO_URL" "refs/heads/$BRANCH" 2>/dev/null | awk 'NR==1{print $1}')
  if ! [[ $sha =~ ^[0-9a-f]{40}$ ]]; then
    S_last_error="ls-remote 失败（网络或仓不可达），线上代码不动"; log "$S_last_error"; save_state; exit 0
  fi
  if [ "$sha" = "$S_seen_sha" ] && [ -e "$BASE/current" ]; then
    if [ "$S_state" = failing ] && [ "${S_next_retry_epoch:-0}" -le "$now" ]; then log "退避期满，重试提交 ${sha:0:12}"
    else [ "$S_state" = failing ] || S_state=up-to-date; save_state; log "仓库 $BRANCH 没有新提交（${sha:0:12}）"; exit 0; fi
  fi

  # 初始化本地空仓并声明为部分克隆（只取树，按需取 SUBDIR 的文件）
  if [ ! -d "$WORK/.git" ]; then
    rm -rf "$WORK"; git init -q "$WORK" || fail "git init 失败"
  fi
  git -C "$WORK" remote remove origin >/dev/null 2>&1
  git -C "$WORK" remote add origin "$REPO_URL" || fail "git remote 失败"
  git -C "$WORK" config extensions.partialClone origin
  git -C "$WORK" config remote.origin.promisor true
  git -C "$WORK" config remote.origin.partialclonefilter blob:none
  timeout 180 git -C "$WORK" -c credential.helper= fetch -q --depth 1 --filter=blob:none origin "$sha" || fail "git fetch 失败"
  TREE=$(git -C "$WORK" rev-parse "FETCH_HEAD:$SUBDIR" 2>/dev/null) || fail "仓库里找不到 $SUBDIR"
  if [ "$TREE" = "$S_deployed_tree" ] && [ -e "$BASE/current" ]; then
    S_seen_sha=$sha; S_deployed_sha=$sha; S_state=up-to-date; S_last_error=""; S_fail_tree=""; S_fail_count=0; S_next_retry_epoch=""
    save_state; log "提交 ${sha:0:12} 没有改动 $SUBDIR（子树 ${TREE:0:12}），线上代码不变"; exit 0
  fi

  S_state=deploying; log "$SUBDIR 有变化：线上 ${S_deployed_tree:0:12} -> ${TREE:0:12}（提交 ${sha:0:12}）"
  git -C "$WORK" sparse-checkout set --cone "$SUBDIR" || fail "sparse-checkout 失败"
  timeout 180 git -C "$WORK" -c credential.helper= checkout -q -f --detach FETCH_HEAD || fail "checkout 失败"
  [ "$(git -C "$WORK" rev-parse "HEAD:$SUBDIR")" = "$TREE" ] || fail "取出的子树与预期不一致"
  [ -f "$WORK/$SUBDIR/requirements.txt" ] && [ -d "$WORK/$SUBDIR/fifa_daily" ] || fail "$SUBDIR 里缺 requirements.txt 或 fifa_daily/"

  rel="$BASE/releases/${TREE:0:12}"; TMP_REL="$rel.new"
  rm -rf "$TMP_REL"; mkdir -p "$TMP_REL" && cp -a "$WORK/$SUBDIR/." "$TMP_REL/" || fail "复制代码失败"
  rh=$(sha256sum "$TMP_REL/requirements.txt" | cut -c1-12); venv="$BASE/venvs/$rh"
  if [ ! -x "$venv/bin/python" ]; then
    log "建虚拟环境 $venv"
    { timeout "$PIP_TIMEOUT" python3 -m venv "$venv" \
      && timeout "$PIP_TIMEOUT" "$venv/bin/python" -m pip install -q --no-cache-dir --disable-pip-version-check -r "$TMP_REL/requirements.txt"; } \
      || { rm -rf "$venv"; fail "建虚拟环境/装依赖失败"; }
  fi
  printf '%s\n' "$venv" > "$TMP_REL/.venv"
  log "跑离线单元测试（合成数据，不联网）"
  ( cd "$TMP_REL" && timeout "$TEST_TIMEOUT" nice "$venv/bin/python" -m unittest discover -s tests -t . ) > "$PULL/last-test.log" 2>&1 \
    || { tail -n 30 "$PULL/last-test.log" | sed 's/^/  test| /'; fail "离线单元测试没过（日志 $PULL/last-test.log）"; }
  grep -E '^(Ran|OK|FAILED)' "$PULL/last-test.log" | sed 's/^/  test| /'

  touch "$TMP_REL"; rm -rf "$rel"; mv -T "$TMP_REL" "$rel" || fail "发布目录就位失败"; TMP_REL=""
  ln -sfn "releases/${TREE:0:12}" "$BASE/current.tmp" && mv -Tf "$BASE/current.tmp" "$BASE/current" || fail "切换 current 失败"
  S_state=up-to-date; S_seen_sha=$sha; S_deployed_sha=$sha; S_deployed_tree=$TREE; S_last_deploy_at=$(date -u +%FT%TZ)
  S_last_error=""; S_fail_tree=""; S_fail_count=0; S_next_retry_epoch=""
  save_state
  : > "$PULL/run-requested"   # ExecStartPost 见到它就请求 fifa-daily.service 立刻出一份新报告
  log "代码已更新到 ${TREE:0:12}"
  prune_old
  exit 0
}

prune_old() { # 只保留最近 KEEP_CODE 份代码发布（含线上）和它们引用的虚拟环境
  local cur d n=0 keep_venvs="" v
  cur=$(readlink -f "$BASE/current")
  for d in $(ls -1dt "$BASE"/releases/*/ 2>/dev/null); do
    d=${d%/}; n=$(( n + 1 ))
    if [ "$d" = "$cur" ] || [ "$n" -le "$KEEP_CODE" ]; then keep_venvs="$keep_venvs $(cat "$d/.venv" 2>/dev/null)"; continue; fi
    rm -rf "$d" && log "已删除更旧的代码发布 $(basename "$d")"
  done
  for v in "$BASE"/venvs/*/; do
    v=${v%/}; case " $keep_venvs " in *" $v "*) ;; *) rm -rf "$v" && log "已删除不用的虚拟环境 $(basename "$v")";; esac
  done
  return 0
}

case "${1:-}" in
  run) do_run ;;
  status) do_status ;;
  *) echo "用法: $0 run | status" >&2; exit 64 ;;
esac
