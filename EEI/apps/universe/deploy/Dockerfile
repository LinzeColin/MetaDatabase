# 商域宇宙 + 旧版「完整图谱」前端，同一个极小 nginx 容器。
# 构建上下文 = EEI/ 目录（拉取式部署配置里 SUBDIR=EEI，DOCKERFILE=apps/universe/deploy/Dockerfile）。
# 上下文里只有下面 COPY 到的文件会进构建：见同目录 Dockerfile.dockerignore（白名单）。
#
# 第 1 阶段（node）：用 pnpm-lock.yaml 锁定依赖，把 apps/web 静态导出（next build，output: "export"）。
#   接口基址写 same-origin：产物里没有任何域名，浏览器运行时取页面自己的 origin，请求 /v1/*。
# 第 2 阶段（nginx）：只拷静态产物；运行时没有 node、没有 pnpm、没有模型调用。
#
# 运行约束：只读根文件系统，可写只有 /tmp 与 /etc/nginx/conf.d 两块 tmpfs（见 eei-universe.env 的 RUN_EXTRA_ARGS）。

ARG NODE_IMAGE=node:24-alpine
ARG NGINX_IMAGE=nginx:1.27-alpine

# ---------- 第 1 阶段：构建旧版图谱前端 ----------
FROM ${NODE_IMAGE} AS web
ENV NEXT_TELEMETRY_DISABLED=1 \
    CI=true
WORKDIR /src
# 版本与 EEI/package.json 的 packageManager 保持一致
RUN npm install -g --no-audit --no-fund pnpm@11.8.0
# 先只拷依赖清单，源码没变时 pnpm install 这层走缓存
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @eei/web...
COPY apps/web apps/web
# development-status、objects-scope 两个页面在构建期读 ../../data/*.csv（仓里的目录台账，约 0.5MB）
COPY data data
# 线上版本戳：构建时传入提交号；放在最后一层，换提交号只重跑 next build
ARG SOURCE_COMMIT=unknown
ENV EEI_CLOUD_EXPORT=1 \
    NEXT_PUBLIC_EEI_API_BASE_URL=same-origin \
    NEXT_PUBLIC_EEI_SURFACE=cloud-publication \
    NEXT_PUBLIC_EEI_BUILD_SHA=${SOURCE_COMMIT}
RUN cd apps/web && rm -rf .next out && ./node_modules/.bin/next build \
 && printf '{"repo":"LinzeColin/MetaDatabase","commit":"%s","api_base":"same-origin"}\n' "$SOURCE_COMMIT" > out/build.json

# ---------- 第 2 阶段：nginx，只放静态产物 ----------
FROM ${NGINX_IMAGE}
# 安全：基底镜像补丁
RUN apk upgrade --no-cache && rm -f /etc/nginx/conf.d/default.conf
COPY apps/universe/deploy/nginx.conf /etc/nginx/nginx.conf
COPY apps/universe/deploy/headers.conf apps/universe/deploy/legacy-headers.conf /etc/nginx/snippets/
# envsubst 只在容器启动时替换环境变量（EEI_UPSTREAM / EEI_RESOLVER），别的 $ 变量原样保留
COPY apps/universe/deploy/site.conf.template /etc/nginx/templates/site.conf.template
# 宇宙页面（根目录）与旧版图谱前端（/usr/share/nginx/legacy，nginx 里单独一个 root）
COPY apps/universe/index.html apps/universe/app.js apps/universe/styles.css /usr/share/nginx/html/
COPY apps/universe/vendor/ /usr/share/nginx/html/vendor/
COPY --from=web /src/apps/web/out/ /usr/share/nginx/legacy/
# 线上版本戳：curl <域名>/version.txt 即可看到线上是哪一版
ARG SOURCE_COMMIT=unknown
RUN printf '%s\n' "$SOURCE_COMMIT" > /usr/share/nginx/html/version.txt
# 上游 = Cloudflare Workers 上的旧程序（workers.dev 地址），现在只承担 /v1/*、/health 与本地找不到的路径；
# 要换上游，在 eei-universe.env 的 RUN_EXTRA_ARGS 里加 -e EEI_UPSTREAM=... 即可，不用改镜像
ENV EEI_UPSTREAM=https://codex-eei.linzezhang35.workers.dev \
    EEI_RESOLVER="1.1.1.1 8.8.8.8" \
    NGINX_ENTRYPOINT_QUIET_LOGS=1
USER nginx
EXPOSE 8080
# -e：错误日志直接走 stderr，别去开只读盘上的默认日志文件
CMD ["nginx", "-e", "/dev/stderr", "-g", "daemon off;"]
