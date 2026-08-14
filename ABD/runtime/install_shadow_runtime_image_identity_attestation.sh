#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: sudo runtime/install_shadow_runtime_image_identity_attestation.sh <non-secret-source-directory>'
}

if [ "$#" -ne 1 ]; then
  usage >&2
  exit 64
fi

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'must run as root; this installer does not start or reload a service' >&2
  exit 65
fi

source_dir=$1
case "$source_dir" in
  /*) ;;
  *)
    printf '%s\n' 'source directory must be absolute' >&2
    exit 66
    ;;
esac

script=$source_dir/shadow_runtime_image_identity_attestation.py
contract=$source_dir/shadow_runtime_image_identity_attestation_contract.json
for file in "$script" "$contract"; do
  if [ ! -f "$file" ] || [ -L "$file" ]; then
    printf '%s\n' "required regular source file is missing: $file" >&2
    exit 67
  fi
done

install -d -m 0755 /usr/local/lib/abd
install -m 0755 "$script" /usr/local/lib/abd/shadow_runtime_image_identity_attestation.py
install -m 0644 "$contract" /usr/local/lib/abd/shadow_runtime_image_identity_attestation_contract.json
printf '%s\n' 'ABD_SHADOW_IMAGE_IDENTITY_ATTESTER_INSTALLED_NO_RUNTIME_STATE_CHANGE'
