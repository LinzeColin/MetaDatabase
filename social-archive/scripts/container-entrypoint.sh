#!/bin/sh
# The host data root is a setgid bind mount shared with constrained systemd
# maintenance jobs. Keep new SQLite/CAS paths group-writable without ever
# running Core as root.
set -eu
umask 0007
exec "$@"
