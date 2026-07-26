#!/usr/bin/env bash
set -Eeuo pipefail

# The first argument is simulator-only state. Arguments after it mirror the
# repository-governed private_db_client.py subset used by CyberBoss.
usage() {
  cat >&2 <<'USAGE'
usage:
  private-db-simulator.sh <root> init
  private-db-simulator.sh <root> ingest Private-MetaDatabase <file> --domain CyberBoss [--batch <id>]
  private-db-simulator.sh <root> get Private-MetaDatabase <relative-path> <output>
  private-db-simulator.sh <root> list Private-MetaDatabase [prefix]
  private-db-simulator.sh <root> verify Private-MetaDatabase
USAGE
  exit 2
}

ROOT="${1:-}"
COMMAND="${2:-}"
[[ -n "$ROOT" && -n "$COMMAND" ]] || usage
shift 2

FAULT="${CB_SIM_PRIVATE_DB_FAULT:-}"
case "$FAULT" in
  "") ;;
  403|429)
    printf 'PRIVATE_DB_SIMULATOR=ERROR HTTP_STATUS=%s\n' "$FAULT"
    exit 1
    ;;
  outage)
    echo 'PRIVATE_DB_SIMULATOR=ERROR HTTP_STATUS=503'
    exit 1
    ;;
  409)
    [[ "$COMMAND" == "ingest" ]] || {
      echo 'PRIVATE_DB_SIMULATOR=ERROR fault_409_only_applies_to_ingest'
      exit 2
    }
    echo 'PRIVATE_DB_SIMULATOR=CONFLICT HTTP_STATUS=409'
    exit 1
    ;;
  *)
    echo "PRIVATE_DB_SIMULATOR=ERROR unknown_fault:$FAULT"
    exit 2
    ;;
esac

validate_area() {
  [[ "$1" == "Private-MetaDatabase" ]] || {
    echo "PRIVATE_DB_SIMULATOR=ERROR unsupported_area:$1"
    exit 2
  }
}

validate_relative_path() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9._/-]+$ ]] || {
    echo 'PRIVATE_DB_SIMULATOR=ERROR invalid_relative_path'
    exit 2
  }
  [[ "$value" != /* && "/$value/" != *"/../"* ]] || {
    echo 'PRIVATE_DB_SIMULATOR=ERROR unsafe_relative_path'
    exit 2
  }
}

case "$COMMAND" in
  init)
    (($# == 0)) || usage
    install -d -m 0750 "$ROOT/Private-MetaDatabase/objects"
    printf 'PRIVATE_DB_SIMULATOR=READY\nROOT=%s\nAREA=Private-MetaDatabase\n' "$ROOT"
    ;;
  ingest)
    AREA="${1:-}"
    SOURCE="${2:-}"
    shift 2 || usage
    validate_area "$AREA"
    [[ -r "$SOURCE" && -f "$SOURCE" ]] || {
      echo 'PRIVATE_DB_SIMULATOR=ERROR source_unreadable'
      exit 2
    }
    DOMAIN=""
    BATCH="$(date -u +%Y-%m-%d)"
    while (($#)); do
      case "$1" in
        --domain) DOMAIN="${2:-}"; shift 2 ;;
        --batch) BATCH="${2:-}"; shift 2 ;;
        *) usage ;;
      esac
    done
    [[ "$DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || {
      echo 'PRIVATE_DB_SIMULATOR=ERROR invalid_domain'
      exit 2
    }
    [[ "$BATCH" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || {
      echo 'PRIVATE_DB_SIMULATOR=ERROR invalid_batch'
      exit 2
    }
    NAME="$(basename "$SOURCE")"
    [[ "$NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || {
      echo 'PRIVATE_DB_SIMULATOR=ERROR unsafe_source_name'
      exit 2
    }
    AREA_ROOT="$ROOT/$AREA"
    MANIFEST="$AREA_ROOT/manifest.jsonl"
    SHA="$(sha256sum "$SOURCE" | awk '{print $1}')"
    RELATIVE_OBJECT="objects/${SHA:0:2}/${SHA}_${NAME}"
    TARGET="$AREA_ROOT/$RELATIVE_OBJECT"
    install -d -m 0750 "$(dirname "$TARGET")"
    if [[ -e "$TARGET" ]]; then
      [[ "$(sha256sum "$TARGET" | awk '{print $1}')" == "$SHA" ]] || {
        echo 'PRIVATE_DB_SIMULATOR=ERROR immutable_object_mismatch'
        exit 1
      }
      printf 'PRIVATE_DB_SIMULATOR=PASS OP=ingest HTTP_STATUS=409 RESULT=already_exists SHA256=%s OBJECT_PATH=%s\n' \
        "$SHA" "$RELATIVE_OBJECT"
      exit 0
    fi
    TEMP="$TARGET.tmp.$$"
    trap 'rm -f -- "$TEMP"' EXIT
    install -m 0640 "$SOURCE" "$TEMP"
    mv "$TEMP" "$TARGET"
    trap - EXIT
    BYTES="$(wc -c < "$TARGET" | tr -d '[:space:]')"
    INGESTED_AT="$(date -u +%Y-%m-%d)"
    printf '{"sha256":"%s","original_name":"%s","size_bytes":%s,"domain":"%s","batch":"%s","object_path":"%s","ingested_at":"%s"}\n' \
      "$SHA" "$NAME" "$BYTES" "$DOMAIN" "$BATCH" "$RELATIVE_OBJECT" "$INGESTED_AT" \
      >> "$MANIFEST"
    printf 'PRIVATE_DB_SIMULATOR=PASS OP=ingest HTTP_STATUS=201 SHA256=%s OBJECT_PATH=%s BYTES=%s\n' \
      "$SHA" "$RELATIVE_OBJECT" "$BYTES"
    ;;
  get)
    AREA="${1:-}"
    RELATIVE_OBJECT="${2:-}"
    DESTINATION="${3:-}"
    (($# == 3)) || usage
    validate_area "$AREA"
    validate_relative_path "$RELATIVE_OBJECT"
    [[ -n "$DESTINATION" ]] || usage
    SOURCE="$ROOT/$AREA/$RELATIVE_OBJECT"
    [[ -r "$SOURCE" ]] || {
      echo 'PRIVATE_DB_SIMULATOR=ERROR HTTP_STATUS=404'
      exit 1
    }
    install -m 0600 "$SOURCE" "$DESTINATION"
    printf 'PRIVATE_DB_SIMULATOR=PASS OP=get HTTP_STATUS=200 PATH=%s\n' "$RELATIVE_OBJECT"
    ;;
  list)
    AREA="${1:-}"
    PREFIX="${2:-}"
    (($# == 1 || $# == 2)) || usage
    validate_area "$AREA"
    if [[ -n "$PREFIX" ]]; then
      validate_relative_path "$PREFIX"
    fi
    TARGET="$ROOT/$AREA${PREFIX:+/$PREFIX}"
    if [[ ! -e "$TARGET" ]]; then
      echo 'PRIVATE_DB_SIMULATOR=PASS OP=list HTTP_STATUS=200 COUNT=0'
      exit 0
    fi
    find "$TARGET" -maxdepth 1 -mindepth 1 -print | sort
    COUNT="$(find "$TARGET" -maxdepth 1 -mindepth 1 -print | wc -l | tr -d '[:space:]')"
    printf 'PRIVATE_DB_SIMULATOR=PASS OP=list HTTP_STATUS=200 COUNT=%s\n' "$COUNT"
    ;;
  verify)
    AREA="${1:-}"
    (($# == 1)) || usage
    validate_area "$AREA"
    MANIFEST="$ROOT/$AREA/manifest.jsonl"
    if [[ ! -r "$MANIFEST" ]]; then
      printf 'PRIVATE_DB_SIMULATOR=PASS OP=verify HTTP_STATUS=200 RECORDS=0 MISSING=0\n'
      exit 0
    fi
    RECORDS=0
    MISSING=0
    while IFS= read -r record; do
      [[ -n "$record" ]] || continue
      SHA="$(printf '%s\n' "$record" | sed -n 's/.*"sha256":"\([0-9a-f]\{64\}\)".*/\1/p')"
      RELATIVE_OBJECT="$(printf '%s\n' "$record" | sed -n 's/.*"object_path":"\([^"]*\)".*/\1/p')"
      [[ "$SHA" =~ ^[0-9a-f]{64}$ && -n "$RELATIVE_OBJECT" ]] || {
        echo 'PRIVATE_DB_SIMULATOR=ERROR invalid_manifest_record'
        exit 1
      }
      validate_relative_path "$RELATIVE_OBJECT"
      RECORDS=$((RECORDS + 1))
      OBJECT="$ROOT/$AREA/$RELATIVE_OBJECT"
      if [[ ! -r "$OBJECT" || "$(sha256sum "$OBJECT" | awk '{print $1}')" != "$SHA" ]]; then
        MISSING=$((MISSING + 1))
      fi
    done < "$MANIFEST"
    [[ "$MISSING" -eq 0 ]] || {
      printf 'PRIVATE_DB_SIMULATOR=ERROR OP=verify RECORDS=%s MISSING=%s\n' "$RECORDS" "$MISSING"
      exit 1
    }
    printf 'PRIVATE_DB_SIMULATOR=PASS OP=verify HTTP_STATUS=200 RECORDS=%s MISSING=0\n' "$RECORDS"
    ;;
  *)
    usage
    ;;
esac
