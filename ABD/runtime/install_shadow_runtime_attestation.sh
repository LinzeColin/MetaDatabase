#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: sudo runtime/install_shadow_runtime_attestation.sh <release-root>'
}

if [ "$#" -ne 1 ]; then
  usage >&2
  exit 64
fi

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'must run as root; this installer only installs a one-shot attestation script' >&2
  exit 65
fi

release_root=$1
source=$release_root/runtime/shadow_runtime_attestation.py

if [ ! -f "$source" ]; then
  printf '%s\n' "required attestation artifact is missing: $source" >&2
  exit 66
fi

install -d -m 0755 /usr/local/lib/abd
install -m 0755 "$source" /usr/local/lib/abd/shadow_runtime_attestation.py

printf '%s\n' 'ABD_SHADOW_RUNTIME_ATTESTATION_INSTALLED_NO_RUNTIME_STATE_CHANGED'
