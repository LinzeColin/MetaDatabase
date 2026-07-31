FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SOCIAL_ARCHIVE_HOST=0.0.0.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git ffmpeg age \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md VERSION ./
COPY src ./src
COPY apps ./apps
COPY scripts ./scripts
RUN pip install .
RUN groupadd --system --gid 10001 socialarchive \
 && useradd --system --uid 10001 --gid socialarchive --create-home socialarchive \
 && mkdir -p /var/lib/social-archive \
 && chown -R socialarchive:socialarchive /var/lib/social-archive /app
USER socialarchive
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8765/health || exit 1
CMD ["social-archive-api"]
