# ADP 自托管：网页服务 + 每日任务共用同一个镜像（命令不同）。
# 构建上下文 = arxiv-daily-push/deploy/（拉取式部署的 SUBDIR），本文件在 selfhost/ 下，所以 COPY 路径从 deploy/ 起算。
#
# 运行约束（由 adp.env 的 RUN_EXTRA_ARGS 与 adp-daily-run.sh 落实）：
#   · 非 root：uid/gid 10001；只读根文件系统，可写的只有 /tmp（内存盘）与 /data（宿主机 /var/lib/adp 挂进来）；
#   · 内存上限 256m、丢掉全部 capability、no-new-privileges；
#   · 只监听容器内 8080，对外只经 Traefik，不发布端口；
#   · 零第三方依赖：用 Node 内置 node:sqlite（需要 Node >= 22.13，基底镜像 node:22-alpine 满足；启动时若缺会直接报错退出）。
FROM node:22-alpine

# 基底镜像补丁默认要打；仅当构建环境的 apk 源不可达（例如沙箱里被代理改了证书）时才 --build-arg APK_UPGRADE=no
ARG APK_UPGRADE=yes
RUN if [ "$APK_UPGRADE" = yes ]; then apk upgrade --no-cache; fi \
 && addgroup -g 10001 -S adp \
 && adduser -u 10001 -S -G adp -H -h /app adp \
 && mkdir -p /data && chown adp:adp /data

WORKDIR /app
COPY selfhost/app/ /app/
# 页面/选择/讲义/FSRS/抓取的唯一实现仍是 worker_cloud.js，自托管直接加载它（见 app/load_worker.mjs），不复制改写
COPY cloudflare/worker_cloud.js /app/vendor/worker_cloud.js
COPY cloudflare/schema_cloud.sql /app/schema_cloud.sql
COPY cloudflare/assets/media/ /app/media/

# 线上版本戳：拉取式部署构建时传入提交号，curl <域名>/version.txt 即可看到线上是哪一版
ARG SOURCE_COMMIT=unknown
RUN printf '%s\n' "$SOURCE_COMMIT" > /app/version.txt

ENV NODE_ENV=production \
    PORT=8080 \
    ADP_DATA_DIR=/data \
    NODE_OPTIONS="--disable-warning=ExperimentalWarning --max-old-space-size=160"

USER 10001:10001
EXPOSE 8080
CMD ["node", "/app/server.mjs"]
