# EEI dynamic-refresh worker image (OVH / hard-capped Coolify app).
#
# Runs the authoritative data pipeline steady-state loop:
#   python -m scripts.authoritative.refresh_cycle --loop --interval-seconds N
# Each cycle: enrich_sec (SEC filings -> events) + collect_gleif (ownership)
# -> publish_to_cloud_channel --apply. The publish leg streams chunked SQL
# batches to the public worker's authenticated internal channel
# (/v1/internal/publish/exec) over plain HTTPS, so this image ships NO
# Node/wrangler and the box holds no account-level Cloudflare credential.
#
# Deliberately MINIMAL: the pipeline imports psycopg + httpx only (no
# fastapi/uvicorn/pydantic). Pure-Python image keeps both the image size and
# the resident-memory floor small for a box with almost no free RAM.

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal OS deps: tini for correct signal handling (long-running loop),
# ca-certificates for HTTPS to SEC / GLEIF / the publish channel, curl for
# ad-hoc debugging inside the capped container.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only the two runtime Python deps the pipeline actually uses (versions pinned
# to match EEI/pyproject.toml). psycopg[binary] ships its own libpq wheel, so we
# need no system postgres client libs.
RUN pip install "psycopg[binary]==3.3.4" "httpx==0.28.1"

# Source needed by the pipeline:
#  scripts/           -> refresh_cycle, authoritative collectors, publish, migrate, db_tools
#  infra/db/          -> migrations (entrypoint runs migrate upgrade)
#  infra/cloudflare/  -> d1_publication_schema.sql (publish --apply applies it)
#  specs/             -> domain_schema_v0001.sql (pulled in by migration `-- include:`)
COPY scripts ./scripts
COPY infra ./infra
COPY specs ./specs

COPY infra/docker/refresh-entrypoint.sh /usr/local/bin/refresh-entrypoint.sh
RUN chmod +x /usr/local/bin/refresh-entrypoint.sh

# Writable state dir for the rolling cursor + run log (mount a volume here).
ENV EEI_REFRESH_STATE=/state/.eei_refresh_state.json \
    EEI_REFRESH_RUN_LOG=/state/.eei_refresh_runs.jsonl
RUN mkdir -p /state && useradd -u 10001 -m eei && chown -R eei:eei /app /state
USER eei

# Liveness: the run log must exist once the first cycle completes. The
# healthcheck is intentionally cheap (no DB / network) so it never adds load.
HEALTHCHECK --interval=5m --timeout=10s --start-period=10m --retries=3 \
  CMD test -f /state/.eei_refresh_runs.jsonl || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/refresh-entrypoint.sh"]
# Overridable; the compose file sets the steady-state loop command.
CMD ["python", "-m", "scripts.authoritative.refresh_cycle", "--loop", "--interval-seconds", "86400"]
