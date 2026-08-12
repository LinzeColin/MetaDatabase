#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_protected_provider_auth_route_resolver.sh --protected-root <directory>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--protected-root" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_protected_provider_auth_route_resolver.py" \
  --contract "$script_dir/current_production_protected_provider_auth_route_resolver_contract.json" \
  --protected-root "$2"
