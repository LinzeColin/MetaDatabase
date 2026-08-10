#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: sudo runtime/provision_host_bundle.sh <stage-root> <release-id>'
}

if [ "$#" -ne 2 ]; then
  usage >&2
  exit 64
fi

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'must run as root; do not use this script to start a service' >&2
  exit 65
fi

stage_root=$1
release_id=$2
case "$release_id" in
  ???????*) ;;
  *)
    printf '%s\n' 'release id must be at least seven characters' >&2
    exit 66
    ;;
esac

case "$release_id" in
  *[!0123456789abcdefghijklmnopqrstuvwxyz._-]*)
    printf '%s\n' 'release id contains unsupported characters' >&2
    exit 67
    ;;
esac

config=$stage_root/config.json
runtime_env=$stage_root/runtime.env
compose=$stage_root/infra/compose.yml

for file in "$config" "$runtime_env" "$compose"; do
  if [ ! -f "$file" ]; then
    printf '%s\n' "required staged file is missing: $file" >&2
    exit 68
  fi
done

image=$(awk -F= '/^ABD_IMAGE=/{print $2; found=1} END{if (!found) exit 1}' "$runtime_env") || {
  printf '%s\n' 'runtime.env does not declare ABD_IMAGE' >&2
  exit 69
}
case "$image" in
  *@sha256:????????????????????????????????????????????????????????????????) ;;
  *)
    printf '%s\n' 'ABD_IMAGE must be a sha256 digest reference' >&2
    exit 70
    ;;
esac

if ! docker image inspect "$image" >/dev/null 2>&1; then
  printf '%s\n' 'referenced OCI image is not loaded' >&2
  exit 71
fi

release_dir=/opt/abd/releases/$release_id
if [ -e "$release_dir" ]; then
  printf '%s\n' 'refusing to overwrite an existing release directory' >&2
  exit 72
fi

install -d -o root -g 10001 -m 0750 /etc/abd
install -d -m 0750 /etc/abd/secrets /opt/abd/releases "$release_dir" "$release_dir/infra"
install -d -o 10001 -g 10001 -m 0750 /var/lib/abd /var/log/abd
install -m 0640 -o root -g 10001 "$config" /etc/abd/config.json
install -m 0600 "$runtime_env" /etc/abd/runtime.env
install -m 0644 "$compose" "$release_dir/infra/compose.yml"

printf '%s\n' 'ABD_HOST_BUNDLE_STAGED_NO_SERVICE_OR_TUNNEL_ACTIVATION'
