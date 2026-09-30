#!/usr/bin/env bash
# fifa-daily-run.sh —— 生成一份日报并原子发布。由 fifa-daily.timer（每天两次）或代码更新后触发。
#
#   1. 把线上站点目录整份复制成新目录 releases/<时间戳>（状态 ledger/runs/缓存都在里面，所以能从上次继续）；
#   2. 用线上代码在新目录里跑 python -m fifa_daily run；
#   3. 校验新目录（首页/status.json/latest.json 都合格，且 status.json 是这次运行写的）；通过才把 current 原子切过去；
#      不合格就删掉新目录，线上保持旧页面，unit 记为 failed；
#   4. 生成器自己判定「今天没出新报告」（退出码 1）时，页面已如实写明原因并照样发布（旧报告标明「旧的」），
#      unit 同样记为 failed，好让 OnFailure/Gatus 看得见。
# 以无特权用户 fifa-daily 运行。
#
# 用法： fifa-daily-run.sh run | status
set -uo pipefail
export GIT_TERMINAL_PROMPT=0 LC_ALL=C
CONF=${FIFA_CONF:-/etc/fifa-daily/fifa-daily.env}
[ -r "$CONF" ] || { echo "缺配置 $CONF" >&2; exit 78; }
set -a; . "$CONF"; set +a
: "${BASE:?}" "${DATA:?}"
RUN_TIMEOUT=${RUN_TIMEOUT:-900}; KEEP_SITES=${KEEP_SITES:-4}
log() { printf '%s [fifa-run] %s\n' "$(date -u +%FT%TZ)" "$*"; }

do_status() {
  echo "== 线上站点 $DATA/current -> $(readlink "$DATA/current" 2>/dev/null || echo 无)"
  if [ -f "$DATA/current/status.json" ]; then
    python3 - "$DATA/current/status.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
for k in ("ok", "report_date", "today", "fresh_today", "last_attempt_at", "last_success_at", "error", "degraded", "missed_days"):
    print(f"  {k}: {s.get(k)}")
PY
  fi
  echo "== 站点发布"; ls -1dt "$DATA"/releases/*/ 2>/dev/null | head -n "$KEEP_SITES"
  echo "== 代码"; readlink -f "$BASE/current" 2>/dev/null || echo "(无)"
  echo "== 定时器"; systemctl list-timers 'fifa-daily*' --no-pager 2>/dev/null | sed -n '1,4p'
}

validate() { # site_dir started_iso -> 0 合格；不合格把原因打到 stderr
  python3 - "$1" "$2" <<'PY'
import json, sys
from pathlib import Path
site, started = Path(sys.argv[1]), sys.argv[2]
try:
    idx = (site / "index.html").read_text(encoding="utf-8")
    assert len(idx) > 1500 and "FIFA" in idx and "</html>" in idx, "index.html 不完整"
    st = json.loads((site / "status.json").read_text(encoding="utf-8"))
    assert isinstance(st.get("ok"), bool) and st.get("today"), "status.json 缺字段"
    assert st.get("last_attempt_at", "") >= started, f"status.json 不是本次运行写的（{st.get('last_attempt_at')} < {started}）"
    assert (site / "data" / "runs.json").exists(), "缺 data/runs.json"
    if st["ok"]:
        lj = json.loads((site / "latest.json").read_text(encoding="utf-8"))
        assert lj.get("report_date") == st.get("report_date"), "latest.json 与 status.json 日期不一致"
        assert (site / "archive" / f"{st['report_date']}.html").exists(), "缺当天存档"
        assert json.loads((site / "data" / "ledger.json").read_text(encoding="utf-8")).get("entries") is not None, "ledger.json 不合格"
except Exception as exc:
    print(f"校验不合格：{exc}", file=sys.stderr); sys.exit(1)
PY
}

do_run() {
  mkdir -p "$DATA/releases" || exit 73
  exec 9>"$DATA/.lock"; flock -n 9 || { log "上一轮还在跑，本轮跳过"; exit 0; }
  local code venv started new cur rc=0 v
  code=$(readlink -f "$BASE/current") && [ -d "$code/fifa_daily" ] || { log "还没有可用的代码发布（$BASE/current）：先跑 fifa-daily-pull.service"; exit 66; }
  venv=$(cat "$code/.venv" 2>/dev/null); [ -x "$venv/bin/python" ] || { log "虚拟环境缺失：$venv"; exit 66; }
  started=$(date -u +%FT%TZ)
  new="$DATA/releases/$(date -u +%Y%m%dT%H%M%SZ)"
  cur=$(readlink -f "$DATA/current" 2>/dev/null || true)
  if [ -n "$cur" ] && [ -d "$cur" ]; then cp -a "$cur" "$new" || { rm -rf "$new"; log "复制当前站点失败"; exit 73; }
  else mkdir -p "$new"; log "没有线上站点，从空目录开始（预测账本会从零起）"; fi

  log "生成日报：代码 $(basename "$code")，输出 $new"
  ( cd "$code" && timeout "$RUN_TIMEOUT" "$venv/bin/python" -m fifa_daily run --site "$new" ) || rc=$?
  log "生成器退出码 $rc"
  if ! validate "$new" "$started"; then
    rm -rf "$new"; log "新站点没通过校验，已丢弃；线上保持 $(basename "${cur:-无}")"; exit 2
  fi
  # current 放在 $DATA 根下，指向 releases/<ts>（相对链接，容器里同样解析得开）
  touch "$new"   # cp -a 会把旧站点目录的修改时间带过来；清理与 status 按修改时间排序，这里对齐成「发布时间」
  ln -sfn "releases/$(basename "$new")" "$DATA/current.tmp" && mv -Tf "$DATA/current.tmp" "$DATA/current" || { log "切换 current 失败"; exit 74; }
  log "已发布 $(basename "$new")（$([ "$rc" = 0 ] && echo 今天有新报告 || echo '今天没有新报告，页面已写明原因')）"
  # 只保留最近 KEEP_SITES 份（线上这份一定在其中）
  cur=$(readlink -f "$DATA/current"); local n=0 d
  for d in $(ls -1dt "$DATA"/releases/*/ 2>/dev/null); do
    d=${d%/}; n=$(( n + 1 )); [ "$n" -le "$KEEP_SITES" ] || [ "$d" = "$cur" ] && continue
    rm -rf "$d"
  done
  exit "$rc"
}

case "${1:-}" in
  run) do_run ;;
  status) do_status ;;
  *) echo "用法: $0 run | status" >&2; exit 64 ;;
esac
