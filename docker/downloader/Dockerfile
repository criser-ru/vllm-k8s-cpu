# syntax=docker/dockerfile:1
# Лёгкий образ для initContainer: только Python + huggingface_hub.
# Сборка из корня репозитория:
#   docker build -f docker/downloader/Dockerfile -t model-downloader:1.0 .
FROM python:3.12-slim-trixie

ARG APP_UID=1000
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME=/tmp/hf-home

# --require-hashes: pip откажется ставить пакет, если файл на сервере подменён
COPY docker/downloader/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements.txt \
 && pip check \
 && rm /tmp/requirements.txt

RUN groupadd --gid "${APP_UID}" app \
 && useradd --uid "${APP_UID}" --gid "${APP_UID}" --no-create-home --shell /usr/sbin/nologin app

COPY --chmod=0755 scripts/download_model.py /app/download_model.py

USER ${APP_UID}:${APP_UID}
ENTRYPOINT ["python", "/app/download_model.py"]