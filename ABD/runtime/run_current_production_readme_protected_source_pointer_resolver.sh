#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_readme_protected_source_pointer_resolver.sh --readme <regular-file> --protected-root <directory>'
}

if [ "$#" -ne 4 ] || [ "$1" != "--readme" ] || [ "$3" != "--protected-root" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_readme_protected_source_pointer_resolver.py" \
  --contract "$script_dir/current_production_readme_protected_source_pointer_resolver_contract.json" \
  --readme "$2" \
  --protected-root "$4"
