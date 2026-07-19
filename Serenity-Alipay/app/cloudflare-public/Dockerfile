# 静态公开面 — Golden Path/Coolify 托管(构建脚本缺失,public/ 已自包含)
FROM nginx:1.27-alpine
# 安全: 基底镜像补丁 (Trivy 实测 35 HIGH/2 CRIT -> 0/0)
RUN apk upgrade --no-cache
COPY public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
