# 商域宇宙：极小 nginx 静态容器。构建上下文 = EEI/apps/universe/（拉取式部署的 SUBDIR），Dockerfile 在 deploy/ 下。
# 只读根文件系统运行：可写的只有 /tmp 与 /etc/nginx/conf.d 两块 tmpfs（见 eei-universe.env 的 RUN_EXTRA_ARGS）。
FROM nginx:1.27-alpine
# 安全：基底镜像补丁
RUN apk upgrade --no-cache && rm -f /etc/nginx/conf.d/default.conf
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/headers.conf /etc/nginx/snippets/headers.conf
# envsubst 只在容器启动时替换环境变量（EEI_UPSTREAM / EEI_RESOLVER），别的 $ 变量原样保留
COPY deploy/site.conf.template /etc/nginx/templates/site.conf.template
COPY index.html app.js styles.css /usr/share/nginx/html/
COPY vendor/ /usr/share/nginx/html/vendor/
# 线上版本戳：拉取式部署构建时传入提交号，curl <域名>/version.txt 即可看到线上是哪一版
ARG SOURCE_COMMIT=unknown
RUN printf '%s\n' "$SOURCE_COMMIT" > /usr/share/nginx/html/version.txt
# 上游 = Cloudflare Workers 上的旧程序（workers.dev 地址）；要换上游，在 eei-universe.env 的 RUN_EXTRA_ARGS 里加 -e EEI_UPSTREAM=... 即可，不用改镜像
ENV EEI_UPSTREAM=https://codex-eei.linzezhang35.workers.dev \
    EEI_RESOLVER="1.1.1.1 8.8.8.8" \
    NGINX_ENTRYPOINT_QUIET_LOGS=1
USER nginx
EXPOSE 8080
# -e：错误日志直接走 stderr，别去开只读盘上的默认日志文件
CMD ["nginx", "-e", "/dev/stderr", "-g", "daemon off;"]
