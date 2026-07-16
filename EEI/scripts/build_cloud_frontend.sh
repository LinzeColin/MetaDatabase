#!/usr/bin/env bash
# S10PAT02: build the static cloud frontend and stage it as the codex-eei
# Worker's asset directory. The export talks to the Worker API at
# EEI_CLOUD_API_BASE (workers.dev now; the custom domain lands in S10PCT01
# and just needs a rebuild with the new base).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${EEI_CLOUD_API_BASE:-https://codex-eei.linzezhang35.workers.dev}"
WEB_DIR="$REPO_ROOT/apps/web"
DIST_DIR="$REPO_ROOT/apps/cloudflare-public/dist"

echo "[cloud-frontend] exporting apps/web against $API_BASE"
cd "$WEB_DIR"
rm -rf .next out
EEI_CLOUD_EXPORT=1 NEXT_PUBLIC_EEI_API_BASE_URL="$API_BASE" npx next build

echo "[cloud-frontend] staging export into apps/cloudflare-public/dist"
rm -rf "$DIST_DIR"
cp -R "$WEB_DIR/out" "$DIST_DIR"

echo "[cloud-frontend] done: $(find "$DIST_DIR" -type f | wc -l | tr -d ' ') files"
