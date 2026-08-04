# Third-party downloaders stay in this isolated process image. No GPL/AGPL code is copied or imported into the proprietary core.
FROM python:3.12-slim
# **给自己的镜像盖个戳。**
#
# 这台机器还跑着 memory-atlas / gatus / coolify 等别人的项目。部署那道磁盘门
# 需要回收空间时，只能回收**我们自己的**悬空镜像——按标签筛，不按「所有悬空」筛。
# 不盖这个戳的话，自动回收就只能是「全删」，那是在动别人的东西。
LABEL com.socialarchive.project="social-archive"
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
# **把 Dockerfile 自己也放进镜像。**
#
# 部署那道「cli-tools 跟上了没有」的门比的是 server.py 的哈希——
# 而只改 Dockerfile、不改 server.py 的那种改动，它一点都看不出来。
# 我把这个洞写进证据的当天就补上了：镜像里有这一份，门就能连 Dockerfile
# 一起比，不必靠构建参数或标签那一套。
#
# 不循环：COPY 复制的是**构建那一刻的 Dockerfile 本身**，包括这几行注释。
# 里面没有任何密钥（只有版本号和一段讲主组为什么必须是 socialarchive 的说明）。
COPY Dockerfile /worker/Dockerfile.built
# **cliworker 的主组必须是 socialarchive(10001)，不能是它自己的 cliworker(999)。**
#
# 这就是 C-T00-01 的根因。原来这里是 `useradd --uid 10002 --create-home cliworker`
# ——没有 --gid，于是 useradd 顺手建了个同名组 cliworker(999) 当主组。
# 生产实测：uid=10002(cliworker) gid=999(cliworker) groups=999,980。
#
# 而 /run/secrets/cli_worker_token 的属主是 10001:10001、模式 0640。
# 组位对不上 → **这个 sidecar 读不到自己的密钥** → /health 照样 200，
# 业务路由一律 401，job 层 attempt=4 失败，而 sync_run 仍是 scanning、
# last_error_code 为空 → 界面永远「同步中」。
# 这是 v0.0.0.6「点了同步是 0」的第一处断点。
#
# 主组设成 socialarchive(10001) 之后，容器**天然**读得到那些密钥，
# 不必靠 compose 的 group_add 去补。compose 那边的 group_add 仍然保留：
# 它管的是宿主机数据目录（vendor-output 属主 10001:980 模式 2770），
# 那是另一个组、另一件事。
RUN groupadd --system --gid 10001 socialarchive \
 && useradd --system --uid 10002 --gid socialarchive --create-home cliworker \
 && mkdir -p /work/output/cli \
 && chown -R cliworker:socialarchive /work /worker
USER cliworker
EXPOSE 5560
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5560/health', timeout=3)" || exit 1
ENTRYPOINT ["python", "/worker/server.py"]
