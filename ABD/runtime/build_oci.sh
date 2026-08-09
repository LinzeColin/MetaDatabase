#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: ABD_BASE_IMAGE=docker.io/library/python:3.12-alpine@sha256:<64-lowercase-hex> runtime/build_oci.sh <oci-output.tar>'
}

if [ "$#" -ne 1 ]; then
  usage >&2
  exit 64
fi

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=$1
base_image=${ABD_BASE_IMAGE-}
platform=${ABD_TARGET_PLATFORM-linux/amd64}

if [ "$platform" != "linux/amd64" ]; then
  printf '%s\n' 'refusing non-OVH target platform; expected linux/amd64' >&2
  exit 65
fi

case "$base_image" in
  docker.io/library/python:3.12-alpine@sha256:????????????????????????????????????????????????????????????????) ;;
  *)
    printf '%s\n' 'ABD_BASE_IMAGE must be the pinned official python:3.12-alpine digest reference' >&2
    exit 66
    ;;
esac

digest=${base_image##*@sha256:}
case "$digest" in
  *[!0123456789abcdef]*)
    printf '%s\n' 'ABD_BASE_IMAGE digest must use lowercase hexadecimal' >&2
    exit 67
    ;;
esac

if [ -e "$output" ]; then
  printf '%s\n' 'refusing to overwrite OCI output' >&2
  exit 68
fi

if ! docker image inspect "$base_image" >/dev/null 2>&1; then
  printf '%s\n' 'pinned base image is not present locally; acquire it separately by exact digest before building' >&2
  exit 69
fi

umask 077
exec docker buildx build \
  --platform "$platform" \
  --pull=false \
  --network=none \
  --build-arg "BASE_IMAGE=$base_image" \
  --file "$project_root/runtime/Dockerfile" \
  --tag "local/abd-runtime:0.0.0.1" \
  --output "type=oci,dest=$output" \
  "$project_root"
