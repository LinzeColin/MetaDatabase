# 交付流水线第 8 关执行器镜像：只含执行器代码与旅程文件，不含任何密钥。
# 基础镜像与 requirements.txt 里的 playwright 版本必须一致（浏览器版本随镜像走）。
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

# axe-core 版本固定并校验 sha256，打包进镜像，运行时不再访问 CDN
ADD --chmod=0644 --checksum=sha256:fb83a4378d978ecb7d2dae48a3a3778a84c971ac692f3afd45d714fba89c0f0d \
    https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.11.4/axe.min.js /opt/axe/axe.min.js

RUN chmod -R a+rX /opt/axe   # 容器以 uid 1000 运行，必须可读

ENV E2E_AXE_JS=/opt/axe/axe.min.js \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt
COPY run.py ./
COPY 旅程 ./旅程

ENTRYPOINT ["python", "/app/run.py"]
CMD ["--out", "/out"]
