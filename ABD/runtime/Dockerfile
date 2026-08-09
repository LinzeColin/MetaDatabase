ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="ABD observation runtime"
LABEL org.opencontainers.image.version="0.0.0.1"
LABEL org.opencontainers.image.description="Non-trading, non-recommendation ABD runtime control plane"

WORKDIR /app

RUN addgroup -S -g 10001 abd && adduser -S -D -H -u 10001 -G abd abd

COPY --chown=abd:abd runtime/abd_runtime /app/abd_runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ABD_RUNTIME_MODE=OBSERVATION_ONLY

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["python3", "-m", "abd_runtime.server"]
