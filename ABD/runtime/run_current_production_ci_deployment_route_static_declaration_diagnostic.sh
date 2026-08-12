#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_ci_deployment_route_static_declaration_diagnostic.sh --repo-root <directory>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--repo-root" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_ci_deployment_route_static_declaration_diagnostic.py" \
  --contract "$script_dir/current_production_ci_deployment_route_static_declaration_diagnostic_contract.json" \
  --repo-root "$2"
