#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
printf '%s\n' '=== compose services ==='
docker compose ps
printf '%s\n' '=== HTTPS health ==='
curl -fsS "${BASE_URL%/}/healthz" || true
printf '\n%s\n' '=== HTTPS ready ==='
curl -fsS "${BASE_URL%/}/readyz" || true
printf '\n%s\n' '=== Alembic ==='
docker compose exec -T web alembic current || true
printf '%s\n' '=== Web logs ==='
docker compose logs --tail=80 web || true
printf '%s\n' '=== Scheduler logs ==='
docker compose logs --tail=80 scheduler || true
printf '%s\n' '=== Worker logs ==='
docker compose logs --tail=80 worker || true
