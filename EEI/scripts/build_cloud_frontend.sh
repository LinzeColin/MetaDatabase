#!/usr/bin/env bash
# S10PAT02: build the static cloud frontend and stage it as the codex-eei
# Worker's asset directory. The export talks to the Worker API at
# EEI_CLOUD_API_BASE. Default is the production custom domain: workers.dev
# serving is DISABLED for this worker (error 1042) - a bare rebuild against
# the old default silently points every production-data panel at a dead
# origin (the S12 timeline-empty incident).
#
# EEI-F07: the build is stamped with the git commit (clean tree required) so
# production can be provably mapped to a revision. The same SHA goes into the
# frontend bundle (NEXT_PUBLIC_EEI_BUILD_SHA), a dist/build.json manifest, and
# scripts/deploy_cloud.sh passes it to the Worker as EEI_BUILD_SHA.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${EEI_CLOUD_API_BASE:-https://eei.linzezhang.com}"
WEB_DIR="$REPO_ROOT/apps/web"
DIST_DIR="$REPO_ROOT/apps/cloudflare-public/dist"

BUILD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if [ -n "$(git -C "$REPO_ROOT" status --porcelain -- "$REPO_ROOT" 2>/dev/null)" ]; then
  BUILD_SHA="${BUILD_SHA}-dirty"
fi
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "[cloud-frontend] exporting apps/web against $API_BASE (build $BUILD_SHA)"
cd "$WEB_DIR"
rm -rf .next out
EEI_CLOUD_EXPORT=1 \
  NEXT_PUBLIC_EEI_API_BASE_URL="$API_BASE" \
  NEXT_PUBLIC_EEI_BUILD_SHA="$BUILD_SHA" \
  NEXT_PUBLIC_EEI_SURFACE="cloud-publication" \
  npx next build

echo "[cloud-frontend] staging export into apps/cloudflare-public/dist"
rm -rf "$DIST_DIR"
cp -R "$WEB_DIR/out" "$DIST_DIR"

cat > "$DIST_DIR/build.json" <<MANIFEST
{
  "repo": "LinzeColin/MetaDatabase",
  "commit": "$BUILD_SHA",
  "built_at": "$BUILD_TIME",
  "api_base": "$API_BASE"
}
MANIFEST

# EEI-F08: static assets bypass the Worker (run_worker_first covers /v1/* and
# /health only), so the security baseline for HTML/chunks rides the Workers
# Assets _headers file. Keep in lockstep with SECURITY_HEADERS in worker.mjs.
cat > "$DIST_DIR/_headers" <<HEADERS
/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self' https://cloudflareinsights.com https://static.cloudflareinsights.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
  X-EEI-Build: $BUILD_SHA
HEADERS

echo "[cloud-frontend] done: $(find "$DIST_DIR" -type f | wc -l | tr -d ' ') files, build $BUILD_SHA"
