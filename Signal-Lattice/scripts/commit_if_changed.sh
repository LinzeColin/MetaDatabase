#!/usr/bin/env bash
set -euo pipefail
REPO="${1:?repository path required}"
MESSAGE="${2:?commit message required}"
cd "$REPO"
git diff --check
if git diff --quiet && git diff --cached --quiet; then echo '{"state":"NO_CHANGE","commit_created":false}'; exit 0; fi
git add --all
if git diff --cached --quiet; then echo '{"state":"NO_CHANGE","commit_created":false}'; exit 0; fi
git commit -m "$MESSAGE"
printf '{"state":"PASS","commit_created":true,"commit":"%s"}\n' "$(git rev-parse HEAD)"
