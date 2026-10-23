# syntax=docker/dockerfile:1
# Образ vLLM для инференса на CPU (x86_64), запуск от непривилегированного пользователя.
# Сборка из корня репозитория:
#   docker build -f docker/vllm/Dockerfile -t vllm-cpu:0.32.0 .
FROM python:3.12-slim-trixie

ARG VLLM_VERSION=0.32.0
ARG APP_UID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Системные библиотеки:
#  libtcmalloc-minimal4 - быстрый аллокатор памяти (рекомендация vLLM для CPU)
#  libnuma1             - работа с NUMA, нужна CPU-бэкенду vLLM
#  g++                  - torch.compile на CPU компилирует ядра во время работы
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libnuma1 g++ ca-certificates \
 && (apt-get install -y --no-install-recommends libtcmalloc-minimal4t64 \
     || apt-get install -y --no-install-recommends libtcmalloc-minimal4) \
 && test -f /usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4 \
 && rm -rf /var/lib/apt/lists/*

# Python-зависимости строго из зафиксированного списка.
# --no-deps: pip не дотягивает ничего сверх requirements.txt;
# pip check: список полный и совместимый, иначе сборка падает.
COPY docker/vllm/requirements.txt /tmp/requirements.txt
RUN python -m venv "$VIRTUAL_ENV" \
 && pip install --no-deps -r /tmp/requirements.txt \
        --extra-index-url "https://wheels.vllm.ai/${VLLM_VERSION}/cpu" \
        --extra-index-url https://download.pytorch.org/whl/cpu \
 && pip check \
 && python -c "import vllm; print('vLLM', vllm.__version__)" \
 && test -f /opt/venv/lib/libiomp5.so \
 && rm /tmp/requirements.txt

# TCMalloc + Intel OpenMP из пакета intel-openmp (так же делает официальный CPU-образ)
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4:/opt/venv/lib/libiomp5.so

# Непривилегированный пользователь и папки, куда ему можно писать
RUN groupadd --gid "${APP_UID}" app \
 && useradd --uid "${APP_UID}" --gid "${APP_UID}" --create-home --home-dir /home/app \
        --shell /usr/sbin/nologin app \
 && mkdir -p /models \
 && mkdir -p /home/app/.cache \
 && chown -R "${APP_UID}:${APP_UID}" /models /home/app

# Наш код принадлежит root и доступен процессу только на чтение
COPY logging/privacy_filter.py logging/logging_config.json /app/logging/
COPY --chmod=0755 docker/vllm/entrypoint.sh /app/entrypoint.sh

ENV HOME=/home/app \
    PYTHONPATH=/app/logging \
    VLLM_LOGGING_CONFIG_PATH=/app/logging/logging_config.json \
    MODEL_DIR=/models/model

# Числовой UID, а не имя: иначе Kubernetes не сможет проверить runAsNonRoot
USER ${APP_UID}:${APP_UID}
WORKDIR /home/app
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]