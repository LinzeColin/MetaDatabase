#!/bin/sh
set -eu

mount_point="${HARNESS_UI_MOUNT_POINT:-$HOME/mnt/share-full}"
share_url="${HARNESS_UI_SMB_URL:-//GUEST:@192.168.0.1/share}"

if /sbin/mount | /usr/bin/grep -F " on $mount_point (smbfs" >/dev/null 2>&1; then
  exit 0
fi
/bin/mkdir -p "$mount_point"
/sbin/mount_smbfs -o nobrowse "$share_url" "$mount_point"
