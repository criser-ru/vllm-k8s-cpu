#!/usr/bin/env bash
# Пересобирает docker/vllm/requirements.txt.
# Ставит vLLM-CPU по официальной инструкции в чистом контейнере
# с тем же базовым образом, что и в Dockerfile, и снимает точные версии.
set -euo pipefail

VLLM_VERSION="${VLLM_VERSION:-0.32.0}"
# CPU-сборка vLLM требует triton-cpu прямой ссылкой на GitHub; uv ставит такие зависимости,
# только если ссылка указана явно. Ссылка взята из текста ошибки uv для vLLM 0.32.0
TRITON_WHEEL="https://github.com/triton-lang/triton-cpu/releases/download/v3.8.0/triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
BASE_IMAGE="python:3.12-slim-trixie"
OUT_DIR="$(cd "$(dirname "$0")/../docker/vllm" && pwd)"

docker run --rm --platform linux/amd64 -v "${OUT_DIR}:/out" "${BASE_IMAGE}" bash -euc "
  pip install --quiet uv
  uv venv /tmp/venv
  . /tmp/venv/bin/activate
  uv pip install 'vllm==${VLLM_VERSION}' 'triton @ ${TRITON_WHEEL}' \
      --extra-index-url https://wheels.vllm.ai/${VLLM_VERSION}/cpu \
      --index-strategy first-index \
      --torch-backend cpu
  {
    echo '# Сгенерировано scripts/lock_deps.sh - руками не править'
    echo '# vLLM ${VLLM_VERSION} (CPU), Python 3.12, linux/amd64'
    uv pip freeze
  } > /out/requirements.txt
"
echo "Готово: $(grep -c '==' "${OUT_DIR}/requirements.txt") пакетов в ${OUT_DIR}/requirements.txt"