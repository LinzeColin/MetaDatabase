FROM python:3.12-slim
# **给自己的镜像盖个戳。**
#
# 这台机器还跑着 memory-atlas / gatus / coolify 等别人的项目。部署那道磁盘门
# 需要回收空间时，只能回收**我们自己的**悬空镜像——按标签筛，不按「所有悬空」筛。
# 不盖这个戳的话，自动回收就只能是「全删」，那是在动别人的东西。
LABEL com.socialarchive.project="social-archive"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SOCIAL_ARCHIVE_HOST=0.0.0.0 SOCIAL_ARCHIVE_EXTENSION_PACKAGE=/app/dist/social-archive-extension.zip
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git ffmpeg age \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md VERSION ./
COPY src ./src
COPY apps ./apps
COPY scripts ./scripts
# Build the extension inside the image from the checked-in v0.0.0.6 source.
# `dist/` is intentionally ignored by Git, so copying a host-built ZIP here
# could otherwise make a clean checkout fail or ship a stale extension.
RUN python3 scripts/build_extension_package.py
RUN pip install .
RUN groupadd --system --gid 10001 socialarchive \
 && useradd --system --uid 10001 --gid socialarchive --create-home socialarchive \
 && mkdir -p /var/lib/social-archive \
 && chown -R socialarchive:socialarchive /var/lib/social-archive /app
USER socialarchive
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8765/health || exit 1
ENTRYPOINT ["/bin/sh", "/app/scripts/container-entrypoint.sh"]
CMD ["social-archive-api"]
