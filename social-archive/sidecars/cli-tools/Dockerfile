# Third-party downloaders stay in this isolated process image. No GPL/AGPL code is copied or imported into the proprietary core.
FROM python:3.12-slim
ARG GALLERY_DL_VERSION=1.32.8
ARG YT_DLP_VERSION=2026.7.4
ARG INSTALOADER_VERSION=4.15.3
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir \
      "gallery-dl==${GALLERY_DL_VERSION}" \
      "yt-dlp==${YT_DLP_VERSION}" \
      "instaloader==${INSTALOADER_VERSION}"
# The pinned Apache-2.0 Bilibili CLI is supplied only as a named Sidecar build
# context after `scripts/vendor_sync.py --source bilibili_cli --resolve-and-lock`.
# It never enters the first-party core image and needs no Bilibili secret.
COPY --from=bilibili_cli pyproject.toml README.md LICENSE /opt/bilibili-cli/
COPY --from=bilibili_cli bili_cli /opt/bilibili-cli/bili_cli
RUN pip install --no-cache-dir /opt/bilibili-cli
WORKDIR /worker
COPY server.py /worker/server.py
RUN useradd --system --uid 10002 --create-home cliworker \
 && mkdir -p /work/output/cli \
 && chown -R cliworker:cliworker /work /worker
USER cliworker
EXPOSE 5560
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5560/health', timeout=3)" || exit 1
ENTRYPOINT ["python", "/worker/server.py"]
