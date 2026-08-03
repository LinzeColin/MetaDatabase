#!/usr/bin/env bash
# 回滚 v0.0.0.7 / T01 的多租户迁移。
#
# 迁移本身是**加法**（新表 + ADD COLUMN + 回填），SQLite 无法 DROP COLUMN，
# 所以唯一诚实的回滚是**恢复迁移前的快照**，而不是试图逐条撤销。
#
# 用法：
#   rollback_0007.sh --verify   <db> <snapshot>   # 只检查，不写（先跑这个）
#   rollback_0007.sh --restore  <db> <snapshot>   # 真的恢复
#
# 设计取舍：
#   · 恢复前先把当前库另存一份 .pre-rollback，**回滚本身也要可回滚**。
#     否则一次误判的回滚会把迁移后产生的新数据一起抹掉，且没有后悔药。
#   · 恢复用 `sqlite3 .restore` 而不是 `cp`：它走 SQLite 自己的备份 API，
#     能正确处理 WAL；直接 cp 主库文件会丢掉还在 -wal 里的事务。
#   · 任何一步失败立刻退出，绝不"尽力而为"地留下半个库。

set -euo pipefail

MODE="${1:-}"
DB="${2:-}"
SNAP="${3:-}"

usage() { echo "用法: $0 --verify|--restore <db> <snapshot>" >&2; exit 2; }
[ "$MODE" = "--verify" ] || [ "$MODE" = "--restore" ] || usage
[ -n "$DB" ] && [ -n "$SNAP" ] || usage

fail() { echo "✗ $*" >&2; exit 1; }

[ -f "$SNAP" ] || fail "快照不存在: $SNAP"
[ -f "$DB" ]   || fail "目标库不存在: $DB"

# ── 快照必须是一个完整可用的 SQLite 库 ────────────────────────────
sqlite3 "$SNAP" "PRAGMA integrity_check;" | grep -qx "ok" \
  || fail "快照未通过 integrity_check，拒绝用它覆盖任何东西"

TENANT_TABLES="source_account user_relation platform_collection sync_run"
BUSINESS_TABLES="content user_relation source_account artifact platform_collection sync_run scan_receipt"

# v0.0.0.7 之后才有的表。回滚到 v0.0.0.7 之前的快照会**整表消失**：
# 登录身份、会话、扩展令牌、以及托管的平台凭据全部没有。
# 那意味着回滚之后 Owner 会发现自己"没登录过、插件没连过、平台没连过"，
# 而上面那套行数比对一个字都不会提——它只数它认识的那 7 张表。
# 这里单独列出来，回滚前必须明确告知会丢什么。
V0007_TABLES="users oauth_identity session extension_token platform_credential"

echo "== 快照（迁移前）=="
for t in $BUSINESS_TABLES; do
  n=$(sqlite3 "$SNAP" "SELECT COUNT(*) FROM $t;" 2>/dev/null || echo "-")
  printf "  %-22s %s\n" "$t" "$n"
done

echo ""
echo "== 当前库（迁移后）=="
for t in $BUSINESS_TABLES; do
  n=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $t;" 2>/dev/null || echo "-")
  printf "  %-22s %s\n" "$t" "$n"
done

# ── 行数守卫 ──────────────────────────────────────────────────────
# 迁移是加法，行数必须一模一样。对不上说明这个快照根本不是这个库的迁移前状态，
# 拿它去恢复会造成静默数据丢失——宁可拒绝，也不要"看起来成功"。
echo ""
echo "== 行数比对 =="
MISMATCH=0
for t in $BUSINESS_TABLES; do
  a=$(sqlite3 "$SNAP" "SELECT COUNT(*) FROM $t;" 2>/dev/null || echo "-")
  b=$(sqlite3 "$DB"   "SELECT COUNT(*) FROM $t;" 2>/dev/null || echo "-")
  if [ "$a" = "$b" ]; then
    printf "  ✓ %-22s %s\n" "$t" "$a"
  else
    printf "  ✗ %-22s 快照 %s ≠ 当前 %s\n" "$t" "$a" "$b"
    MISMATCH=1
  fi
done

# ── 会被回滚抹掉的 v0.0.0.7 新表 ──────────────────────────────────
# 全库 .restore 是整文件替换：快照里没有的表，恢复之后就不存在了。
# 这不是"数据没变"，是"整张表连同结构一起没了"，必须说出来。
echo ""
echo "== 回滚会抹掉的 v0.0.0.7 新增表 =="
WILL_DROP=0
for t in $V0007_TABLES; do
  in_db=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$t';" 2>/dev/null || echo 0)
  in_snap=$(sqlite3 "$SNAP" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$t';" 2>/dev/null || echo 0)
  if [ "$in_db" = "1" ] && [ "$in_snap" = "0" ]; then
    rows=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $t;" 2>/dev/null || echo "?")
    printf "  ✗ %-22s 当前有 %s 行，快照里没有这张表 —— 回滚后会整表消失\n" "$t" "$rows"
    WILL_DROP=1
  else
    printf "  · %-22s 当前 %s / 快照 %s\n" "$t" "$in_db" "$in_snap"
  fi
done
if [ "$WILL_DROP" = "1" ]; then
  echo ""
  echo "注意：上面标 ✗ 的表在回滚后不复存在。对 Owner 的实际表现是："
  echo "  · 需要重新用 Google/GitHub 登录一次"
  echo "  · 浏览器插件需要重新连接"
  echo "  · 已托管的平台登录信息全部消失，需要重新连接各平台"
  echo "这不是故障，是回滚的正常代价 —— 但必须先知道再决定。"
fi

if [ "$MISMATCH" = "1" ]; then
  echo ""
  echo "行数不一致。这个快照与当前库不是同一条时间线，或迁移后已经产生了新数据。"
  echo "恢复会丢掉这些差异。请人工确认后再决定，本脚本不替你做这个判断。"
  [ "$MODE" = "--restore" ] && fail "拒绝在行数不一致时恢复"
fi

if [ "$MODE" = "--verify" ]; then
  echo ""
  echo "✓ 校验通过（未写入任何东西）。确认无误后用 --restore 执行。"
  exit 0
fi

# ── 真的恢复 ──────────────────────────────────────────────────────
PRE="${DB}.pre-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
echo ""
echo "== 恢复 =="
echo "  先把当前库存一份: $PRE"
sqlite3 "$DB" ".backup '$PRE'"
sqlite3 "$PRE" "PRAGMA integrity_check;" | grep -qx "ok" \
  || fail "回滚前备份自身损坏，中止（当前库未被修改）"

echo "  从快照恢复到: $DB"
sqlite3 "$DB" ".restore '$SNAP'"

echo ""
echo "== 恢复后自检 =="
sqlite3 "$DB" "PRAGMA integrity_check;" | grep -qx "ok" || fail "恢复后 integrity_check 失败"

# 租户列应当已经不在了（快照是迁移前的）
for t in $TENANT_TABLES; do
  if sqlite3 "$DB" "PRAGMA table_info($t);" | grep -q "|user_id|"; then
    printf "  ! %-22s 仍有 user_id —— 快照可能本来就是迁移后的\n" "$t"
  else
    printf "  ✓ %-22s user_id 已消失\n" "$t"
  fi
done

echo ""
echo "✓ 回滚完成。回滚前的库保留在: $PRE"
echo "  要撤销这次回滚：$0 --restore '$DB' '$PRE'"
