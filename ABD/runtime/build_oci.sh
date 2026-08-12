#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: runtime/build_oci.sh <oci-output.tar>'
}

if [ "$#" -ne 1 ]; then
  usage >&2
  exit 64
fi

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=$1
platform=${ABD_TARGET_PLATFORM-linux/amd64}
expected_base_image='docker.io/library/python:3.12-alpine@sha256:aa679aa4eed6eb56c1dc6ad3f1b98b7d2d788fd961596779d188fdedad97fb38'
base_image=$expected_base_image

if [ "$platform" != "linux/amd64" ]; then
  printf '%s\n' 'refusing non-OVH target platform; expected linux/amd64' >&2
  exit 65
fi

if [ -n "${ABD_BASE_IMAGE-}" ] && [ "$ABD_BASE_IMAGE" != "$expected_base_image" ]; then
  printf '%s\n' 'ABD_BASE_IMAGE cannot override the reviewed base image digest' >&2
  exit 66
fi

if [ -e "$output" ]; then
  printf '%s\n' 'refusing to overwrite OCI output' >&2
  exit 67
fi

if ! docker image inspect "$base_image" >/dev/null 2>&1; then
  printf '%s\n' 'pinned base image is not present locally; acquire it separately by exact digest before building' >&2
  exit 68
fi

umask 077
exec docker buildx build \
  --platform "$platform" \
  --pull=false \
  --network=none \
  --file "$project_root/runtime/Dockerfile" \
  --tag "local/abd-runtime:0.0.0.1" \
  --output "type=oci,dest=$output" \
  "$project_root"
