#!/usr/bin/env bash
set -Eeuo pipefail

release_root="${1:-}"
case "$release_root" in
  /*) ;;
  *) printf '%s\n' 'CB530_RELEASE_ASSEMBLY=FAIL release_root_required' >&2; exit 2 ;;
esac

kit_target='docs/product_design/v0.0.0.4/implementation-kit'
kit_path="${release_root}/${kit_target}"
link_path="${release_root}/implementation-kit"

if [[ ! -d "$kit_path" ]]; then
  printf '%s\n' 'CB530_RELEASE_ASSEMBLY=FAIL frozen_kit_missing' >&2
  exit 2
fi

if [[ -e "$link_path" || -L "$link_path" ]]; then
  if [[ ! -L "$link_path" || "$(readlink "$link_path")" != "$kit_target" ]]; then
    printf '%s\n' 'CB530_RELEASE_ASSEMBLY=FAIL implementation_kit_conflict' >&2
    exit 2
  fi
else
  ln -s "$kit_target" "$link_path"
fi

if [[ ! -x "${link_path}/scripts/run-cyberboss.sh" ]]; then
  printf '%s\n' 'CB530_RELEASE_ASSEMBLY=FAIL cloud_runner_missing' >&2
  exit 2
fi

printf '%s\n' 'CB530_RELEASE_ASSEMBLY=PASS'
