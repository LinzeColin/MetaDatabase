#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: install_current_production_blue_release_repair.sh --host <ssh-target> --apply'
}

if [ "$#" -ne 3 ] || [ "$1" != "--host" ] || [ "$3" != "--apply" ]; then
  usage >&2
  exit 64
fi

host=$2
case "$host" in
  ''|*[!A-Za-z0-9._:-]*)
    printf '%s\n' 'ssh target contains unsupported characters' >&2
    exit 65
    ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

for source in \
  infra/config.schema.json \
  infra/rebuild.sh \
  runtime/current_production_blue_release_acceptance_init.py \
  abd_acceptance/infrastructure_iac.py \
  abd_acceptance/canonical_facts.py \
  abd_acceptance/legacy_receipt_compatibility.py \
  abd_acceptance/stage3_delivery.py; do
  if [ ! -f "$PROJECT_ROOT/$source" ] || [ -L "$PROJECT_ROOT/$source" ]; then
    printf '%s\n' "required local source is unavailable: $source" >&2
    exit 66
  fi
done

if [ ! -x "$PROJECT_ROOT/infra/rebuild.sh" ]; then
  printf '%s\n' 'local rebuild script is not executable' >&2
  exit 67
fi

stage=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'sudo -n sh -s' <<'REMOTE'
set -eu
target=$(readlink -f /opt/abd/current 2>/dev/null || true)
[ "$target" = /opt/abd/releases/blue ]
[ -f "$target/infra/compose.yml" ]
[ ! -e "$target/infra/config.schema.json" ]
[ ! -e "$target/infra/rebuild.sh" ]
[ ! -e "$target/abd_acceptance" ]
[ "$(systemctl show abd.service -p LoadState --value 2>/dev/null || true)" = not-found ]
[ "$(systemctl show abd.service -p ActiveState --value 2>/dev/null || true)" = inactive ]
docker ps --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | grep -Fx 'abd-shadow-blue' >/dev/null
python3 -c 'import jsonschema, tomllib, sys; assert sys.version_info[:2] == (3, 12)'
umask 077
mktemp -d /opt/abd/releases/blue/.abd-core-release-repair.XXXXXX
REMOTE
)

case "$stage" in
  /opt/abd/releases/blue/.abd-core-release-repair.*) ;;
  *)
    printf '%s\n' 'remote staging path is invalid' >&2
    exit 70
    ;;
esac
case "$stage" in
  *[!A-Za-z0-9_./-]*)
    printf '%s\n' 'remote staging path contains unsupported characters' >&2
    exit 71
    ;;
esac

discard_stage() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "sudo -n sh -s -- '$stage'" <<'REMOTE'
set -eu
stage=$1
case "$stage" in /opt/abd/releases/blue/.abd-core-release-repair.*) ;; *) exit 1 ;; esac
[ "$(find "$stage" -type f -name '*.py' | wc -l | tr -d ' ')" = 5 ]
[ "$(find "$stage" -type f ! -name '*.py' | wc -l | tr -d ' ')" = 2 ]
[ -z "$(find "$stage" -type l -print -quit)" ]
rm -rf -- "$stage"
REMOTE
}

if ! COPYFILE_DISABLE=1 tar --format ustar -C "$PROJECT_ROOT" -cf - \
  infra/config.schema.json \
  infra/rebuild.sh \
  abd_acceptance/infrastructure_iac.py \
  abd_acceptance/canonical_facts.py \
  abd_acceptance/legacy_receipt_compatibility.py \
  abd_acceptance/stage3_delivery.py \
  | ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "sudo -n tar -xpf - -C '$stage'"; then
  discard_stage
  exit 72
fi

if ! COPYFILE_DISABLE=1 tar --format ustar -C "$PROJECT_ROOT/runtime" -cf - current_production_blue_release_acceptance_init.py \
  | ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "sudo -n tar -xpf - -C '$stage/abd_acceptance'"; then
  discard_stage
  exit 73
fi

ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "sudo -n sh -s -- '$stage'" <<'REMOTE'
set -eu
stage=$1
target=/opt/abd/releases/blue
package_moved=0
schema_installed=0
rebuild_installed=0
committed=0

cleanup() {
  result=$?
  trap - EXIT
  if [ "$committed" -ne 1 ]; then
    if [ "$rebuild_installed" -eq 1 ]; then rm -f -- "$target/infra/rebuild.sh"; fi
    if [ "$schema_installed" -eq 1 ]; then rm -f -- "$target/infra/config.schema.json"; fi
    if [ "$package_moved" -eq 1 ]; then
      if [ -d "$target/abd_acceptance" ] \
        && [ "$(find "$target/abd_acceptance" -type f -name '*.py' | wc -l | tr -d ' ')" = 5 ] \
        && [ "$(find "$target/abd_acceptance" -type f ! -name '*.py' | wc -l | tr -d ' ')" = 0 ] \
        && [ -z "$(find "$target/abd_acceptance" -type l -print -quit)" ]; then
        rm -rf -- "$target/abd_acceptance"
      fi
    fi
    if [ -d "$stage" ] \
      && [ "$(find "$stage" -type f -name '*.py' | wc -l | tr -d ' ')" = 5 ] \
      && [ "$(find "$stage" -type f ! -name '*.py' | wc -l | tr -d ' ')" = 2 ] \
      && [ -z "$(find "$stage" -type l -print -quit)" ]; then
      rm -rf -- "$stage"
    fi
  fi
  exit "$result"
}
trap cleanup EXIT

[ "$(readlink -f /opt/abd/current 2>/dev/null || true)" = "$target" ]
[ -f "$target/infra/compose.yml" ]
[ ! -e "$target/infra/config.schema.json" ]
[ ! -e "$target/infra/rebuild.sh" ]
[ ! -e "$target/abd_acceptance" ]
[ "$(systemctl show abd.service -p LoadState --value 2>/dev/null || true)" = not-found ]
[ "$(systemctl show abd.service -p ActiveState --value 2>/dev/null || true)" = inactive ]
docker ps --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | grep -Fx 'abd-shadow-blue' >/dev/null

for source in infra/config.schema.json infra/rebuild.sh; do
  [ -f "$stage/$source" ]
  [ ! -L "$stage/$source" ]
done
[ -f "$stage/abd_acceptance/current_production_blue_release_acceptance_init.py" ]
mv -- "$stage/abd_acceptance/current_production_blue_release_acceptance_init.py" "$stage/abd_acceptance/__init__.py"
[ "$(find "$stage" -type f -name '*.py' | wc -l | tr -d ' ')" = 5 ]
[ "$(find "$stage" -type f ! -name '*.py' | wc -l | tr -d ' ')" = 2 ]
[ -z "$(find "$stage" -type l -print -quit)" ]
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$stage" python3 -c 'import abd_acceptance.infrastructure_iac'

mv -- "$stage/abd_acceptance" "$target/abd_acceptance"
package_moved=1
install -m 0644 "$stage/infra/config.schema.json" "$target/infra/config.schema.json"
schema_installed=1
install -m 0755 "$stage/infra/rebuild.sh" "$target/infra/rebuild.sh"
rebuild_installed=1
rm -f -- "$stage/infra/config.schema.json" "$stage/infra/rebuild.sh"
rmdir -- "$stage/infra" "$stage"

[ "$(readlink -f /opt/abd/current 2>/dev/null || true)" = "$target" ]
[ -f "$target/infra/compose.yml" ]
[ -f "$target/infra/config.schema.json" ]
[ -x "$target/infra/rebuild.sh" ]
[ "$(find "$target/abd_acceptance" -type f -name '*.py' | wc -l | tr -d ' ')" = 5 ]
[ "$(find "$target/abd_acceptance" -type f ! -name '*.py' | wc -l | tr -d ' ')" = 0 ]
[ -z "$(find "$target/abd_acceptance" -type l -print -quit)" ]
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$target" python3 -c 'import abd_acceptance.infrastructure_iac'
[ "$(systemctl show abd.service -p LoadState --value 2>/dev/null || true)" = not-found ]
[ "$(systemctl show abd.service -p ActiveState --value 2>/dev/null || true)" = inactive ]
docker ps --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | grep -Fx 'abd-shadow-blue' >/dev/null
committed=1
printf '%s\n' 'ABD_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_PASS'
REMOTE
