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

if [ -n "$(git -C "$REPO_ROOT" status --porcelain -- "$REPO_ROOT" 2>/dev/null)" ]; then
  echo "[deploy] refusing to deploy a dirty tree (EEI-F07 requires a clean commit)" >&2
  exit 1
fi

BUILD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEPLOY_ID="deploy-$(date -u +%Y%m%dT%H%M%SZ)-${BUILD_SHA:0:8}"

bash "$REPO_ROOT/scripts/build_cloud_frontend.sh"

echo "[deploy] wrangler deploy with build binding $BUILD_SHA ($DEPLOY_ID)"
cd "$CF_DIR"
npx wrangler deploy \
  --var EEI_BUILD_SHA:"$BUILD_SHA" \
  --var EEI_BUILD_TIME:"$BUILD_TIME" \
  --var EEI_DEPLOY_ID:"$DEPLOY_ID"

echo "[deploy] verifying live build binding"
LIVE_BUILD="$(curl -fsS "$BASE_URL/v1/meta/build" | python3 -c 'import json,sys; print(json.load(sys.stdin)["commit"])')"
LIVE_HEADER="$(curl -fsSI "$BASE_URL/health" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-eei-build" {print $2}')"
if [ "$LIVE_BUILD" != "$BUILD_SHA" ] || [ "$LIVE_HEADER" != "$BUILD_SHA" ]; then
  echo "[deploy] FAIL: live build ($LIVE_BUILD / header $LIVE_HEADER) != $BUILD_SHA" >&2
  exit 1
fi

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
