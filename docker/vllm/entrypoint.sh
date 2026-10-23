#!/usr/bin/env bash
# Точка входа контейнера vLLM.
# Модель уже лежит на PVC (её скачал initContainer), здесь только запуск.
set -euo pipefail

MODEL_DIR="${MODEL_DIR:?переменная MODEL_DIR не задана}"
CONFIG_FILE="${VLLM_CONFIG_FILE:-/etc/vllm/config.yaml}"
PORT="${PORT:-8000}"

# Маркер, который download_model.py создаёт только после полного скачивания
if [[ ! -f "${MODEL_DIR}/.download-complete" ]]; then
  echo "ОШИБКА: модель не найдена в ${MODEL_DIR} (нет маркера .download-complete)." >&2
  echo "Её должен скачать initContainer (scripts/download_model.py)." >&2
  exit 1
fi

# Гарантия, что vLLM и transformers не пойдут в сеть за моделью
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

if [[ -z "${VLLM_API_KEY:-}" ]]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: VLLM_API_KEY не задан, API будет открыт без токена." >&2
fi

args=(serve "${MODEL_DIR}" --host 0.0.0.0 --port "${PORT}")
if [[ -f "${CONFIG_FILE}" ]]; then
  args+=(--config "${CONFIG_FILE}")
fi

# Токен API не попадает в командную строку: vLLM сам читает VLLM_API_KEY из окружения
echo "Запуск: vllm ${args[*]} $*"
exec vllm "${args[@]}" "$@"