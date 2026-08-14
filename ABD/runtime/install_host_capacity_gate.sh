#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: sudo runtime/install_host_capacity_gate.sh <release-root>'
}

if [ "$#" -ne 1 ]; then
  usage >&2
  exit 64
fi

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'must run as root; this installer never starts or enables a service' >&2
  exit 65
fi

release_root=$1
gate_source=$release_root/runtime/host_capacity_gate.py
dropin_source=$release_root/runtime/systemd/10-host-capacity-gate.conf

for source in "$gate_source" "$dropin_source"; do
  if [ ! -f "$source" ]; then
    printf '%s\n' "required guard artifact is missing: $source" >&2
    exit 66
  fi
done

install -d -m 0755 /usr/local/lib/abd /etc/systemd/system/abd.service.d
install -m 0755 "$gate_source" /usr/local/lib/abd/host_capacity_gate.py
install -m 0644 "$dropin_source" /etc/systemd/system/abd.service.d/10-host-capacity-gate.conf
systemctl daemon-reload

printf '%s\n' 'ABD_HOST_CAPACITY_GUARD_INSTALLED_NO_SERVICE_STARTED'
