#!/usr/bin/env bash
# EEI-F07: the only sanctioned production deploy path. Builds the frontend
# with a commit stamp, deploys the Worker with the same stamp bound as vars,
# then verifies the LIVE surface reports exactly that stamp before declaring
# success, and records a deployment manifest as evidence.
#
# Never pipe this script through head/tail filters that close stdout early -
# SIGPIPE aborts the build midway and deploys a stale dist ("Uploaded 0 new
# assets" is the tell).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CF_DIR="$REPO_ROOT/apps/cloudflare-public"
BASE_URL="${EEI_CLOUD_API_BASE:-https://eei.linzezhang.com}"
EVIDENCE_DIR="${EEI_DEPLOY_EVIDENCE_DIR:-$HOME/Documents/Codex/GithubProject/_protected/EEI_runtime_evidence/deploys}"

# apps/web/next-env.d.ts 由 Next 自己生成，dev/typegen 写 ".next/dev/types/routes.d.ts"
# 而 next build 写 ".next/types/routes.d.ts" —— 文件头一行就写着 "should not be edited"。
# 本脚本自己的构建步骤会把它翻过去，于是**每个干净 checkout 只能跑一次部署**，
# 第二次必被自己的脏树门挡住（2026-08-11 实测）。只豁免这一个生成文件，
# 其余任何未提交改动照旧拒绝部署（EEI-F07 要保的是「别部署没提交的源码」）。
DIRTY="$(git -C "$REPO_ROOT" status --porcelain -- "$REPO_ROOT" 2>/dev/null | grep -v '/apps/web/next-env\.d\.ts$' || true)"
if [ -n "$DIRTY" ]; then
  echo "[deploy] refusing to deploy a dirty tree (EEI-F07 requires a clean commit)" >&2
  echo "$DIRTY" >&2
  exit 1
fi

BUILD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEPLOY_ID="deploy-$(date -u +%Y%m%dT%H%M%SZ)-${BUILD_SHA:0:8}"

bash "$REPO_ROOT/scripts/build_cloud_frontend.sh"

# 2026-08-12（WeReadPort 事故）：`wrangler deploy` 是**用配置替换线上 vars，不是合并**；
# secret 自动保留、plain_text 不保留。本脚本每次重传 EEI_BUILD_* 三个，所以那三个安全；
# 但线上若有人在 dashboard 上另加了 plain_text 变量，裸发就会把它清掉且不报错。
# 先取回来一并带上，缺什么都不猜。
PREV_VERSION_ID="$(python3 "$REPO_ROOT/scripts/cf_worker_vars.py" current-version)"
# 用 read 循环而不是 mapfile：mapfile 是 bash 4+ 的，而 macOS 自带 /bin/bash 是 3.2，
# 在本机跑会直接 "mapfile: command not found" 退出 127。构建已经跑完才炸，很浪费。
CARRY_ARGS=()
while IFS= read -r carry_line; do
  [ -n "$carry_line" ] && CARRY_ARGS+=("$carry_line")
done < <(python3 "$REPO_ROOT/scripts/cf_worker_vars.py" carry-args \
  --version "$PREV_VERSION_ID" --skip EEI_BUILD_SHA --skip EEI_BUILD_TIME --skip EEI_DEPLOY_ID)
if [ "${#CARRY_ARGS[@]}" -gt 0 ]; then
  echo "[deploy] 另带回 $(( ${#CARRY_ARGS[@]} / 2 )) 个仓外 plain_text 变量（名字见下）"
  printf '%s\n' "${CARRY_ARGS[@]}" | grep -v '^--var$' | cut -d: -f1 | sed 's/^/  · /'
fi

echo "[deploy] wrangler deploy with build binding $BUILD_SHA ($DEPLOY_ID)"
cd "$CF_DIR"
npx wrangler deploy \
  --var EEI_BUILD_SHA:"$BUILD_SHA" \
  --var EEI_BUILD_TIME:"$BUILD_TIME" \
  --var EEI_DEPLOY_ID:"$DEPLOY_ID" \
  "${CARRY_ARGS[@]+"${CARRY_ARGS[@]}"}"

echo "[deploy] verifying live build binding"
# 新版本推到边缘不是瞬时的。2026-08-11 实测：deploy 返回成功后立刻验，
# /v1/meta/build 已经是新 SHA 而 /health 的 X-EEI-Build 还是上一版，于是这道门
# 报了一次 FAIL —— 部署其实是成功的，几秒后两个戳就一致了。
# 有上限的重试，不是无上限等待（合同 §2.4：任何等待必须有次数上限，超时明确报超时）。
VERIFY_TRIES=10
VERIFY_SLEEP=3
for attempt in $(seq 1 "$VERIFY_TRIES"); do
  LIVE_BUILD="$(curl -fsS "$BASE_URL/v1/meta/build" | python3 -c 'import json,sys; print(json.load(sys.stdin)["commit"])')"
  # grep/cut, not awk field-matching: the first deploy's awk parse false-FAILed
  # on a correctly-bound header.
  LIVE_HEADER="$(curl -s -D - -o /dev/null "$BASE_URL/health" | tr -d '\r' | grep -i '^x-eei-build:' | cut -d' ' -f2)"
  if [ "$LIVE_BUILD" = "$BUILD_SHA" ] && [ "$LIVE_HEADER" = "$BUILD_SHA" ]; then
    echo "[deploy] live build binding confirmed on attempt $attempt/$VERIFY_TRIES"
    break
  fi
  if [ "$attempt" -eq "$VERIFY_TRIES" ]; then
    echo "[deploy] FAIL: 等了 $((VERIFY_TRIES * VERIFY_SLEEP))s 仍不一致 —— live build ($LIVE_BUILD / header $LIVE_HEADER) != $BUILD_SHA" >&2
    # 回读不过就自动回滚：把坏版本留在线上等人来救，是 2026-08-12 那次 3 分钟中断的形状。
    echo "[deploy] 自动回滚到 ${PREV_VERSION_ID:0:8}" >&2
    if npx wrangler rollback --version-id "$PREV_VERSION_ID" --message "自动回滚：部署后回读未通过" -y; then
      echo "[deploy] 已回滚。站点应已恢复，请查上面的失败原因。" >&2
    else
      echo "[deploy] 回滚也失败了，站点可能仍处于坏状态，立刻人工介入。" >&2
    fi
    exit 1
  fi
  echo "[deploy] attempt $attempt/$VERIFY_TRIES: 还没传播开（build=$LIVE_BUILD header=$LIVE_HEADER），${VERIFY_SLEEP}s 后重试"
  sleep "$VERIFY_SLEEP"
done

mkdir -p "$EVIDENCE_DIR"
MANIFEST="$EVIDENCE_DIR/$DEPLOY_ID.json"
cat > "$MANIFEST" <<RECORD
{
  "deploy_id": "$DEPLOY_ID",
  "repo": "LinzeColin/MetaDatabase",
  "commit": "$BUILD_SHA",
  "built_at": "$BUILD_TIME",
  "base_url": "$BASE_URL",
  "live_build_endpoint": "$LIVE_BUILD",
  "live_build_header": "$LIVE_HEADER",
  "verified": true
}
RECORD

echo "[deploy] OK: live surface bound to $BUILD_SHA; manifest $MANIFEST"
