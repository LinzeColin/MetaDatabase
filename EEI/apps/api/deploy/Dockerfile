# 公开数据接口（eei-api）：FastAPI 直接读 Postgres eei-db，对外行为与 Cloudflare Worker 一致。
# 构建上下文 = EEI/（拉取式部署的 SUBDIR），Dockerfile 在 apps/api/deploy/ 下。
# 非 root（uid 10001）运行；根文件系统只读也能跑（不写 .pyc，临时文件走 /tmp 内存盘）。
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 依赖按 uv.lock 锁版本安装（含哈希校验）；只装运行时依赖，不装 dev。
RUN python -m pip install --disable-pip-version-check --no-cache-dir uv==0.11.22
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm -rf /root/.cache

# 运行时代码：API、发布门（与发布端共用的判定）、目录文件。其余脚本不进镜像。
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY scripts/relationship_publication_gate.py scripts/publish_to_cloud_channel.py \
     scripts/db_tools.py ./scripts/
COPY data ./data

# 线上版本戳：拉取式部署构建时传入提交号，/health 与 /v1/meta/build 会报出来。
ARG SOURCE_COMMIT=unknown
ENV EEI_BUILD_SHA=${SOURCE_COMMIT}

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin eei
USER 10001

EXPOSE 8000
# 只读库角色、库连接、版本：/health 一并检查；库连不上返回 503，部署器据此不切流量。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# 单进程：256m 内存上限下足够；并发上限让过载时快速 503，而不是排长队拖垮共用的数据库。
CMD ["uvicorn", "apps.api.app.public_main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--limit-concurrency", "64", "--no-access-log", "--no-server-header"]
