#!/usr/bin/env bash
# Нагрузочный тест развёрнутого vLLM: короткие и длинные промпты, разная параллельность.
# Запускает встроенный `vllm bench serve` внутри пода (там уже есть vLLM и токенизатор),
# забирает JSON с результатами и печатает сводную таблицу.
#   ./bench/run_bench.sh                  # полный прогон
#   NUM_PROMPTS=16 ./bench/run_bench.sh   # быстрее
set -euo pipefail

NS="${NS:-llm-inference}"
MODEL="${MODEL:-qwen2.5-0.5b-instruct}"     # = served-model-name из ConfigMap
NUM_PROMPTS="${NUM_PROMPTS:-32}"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)/results"
mkdir -p "${OUT_DIR}"

# сценарий: имя  длина_промпта  длина_ответа  одновременных_запросов
SCENARIOS=(
  "short-c1   128  128  1"
  "short-c8   128  128  8"
  "long-c1   3072  128  1"
  "long-c4   3072  128  4"
)

POD="$(kubectl -n "${NS}" get pod -l app=vllm -o jsonpath='{.items[0].metadata.name}')"
echo "Под: ${POD}, промптов на сценарий: ${NUM_PROMPTS}"

# Прогрев: первые запросы после старта медленнее из-за компиляции, в замеры их не берём
echo "=== прогрев (в результаты не входит)"
kubectl -n "${NS}" exec "${POD}" -c vllm -- sh -c "
  OPENAI_API_KEY=\"\$VLLM_API_KEY\" vllm bench serve \
    --backend openai --base-url http://localhost:8000 --endpoint /v1/completions \
    --model ${MODEL} --tokenizer \"\$MODEL_DIR\" \
    --dataset-name random --random-input-len 128 --random-output-len 16 \
    --num-prompts 4 --max-concurrency 2 --seed 1000" >/dev/null

seed=0
for s in "${SCENARIOS[@]}"; do
  read -r name in_len out_len conc <<<"${s}"
  # У каждого сценария свой seed: иначе сценарии с одинаковой длиной промпта
  # получат те же самые случайные промпты, и кэш префиксов исказит TTFT
  seed=$((seed + 1))
  echo "=== ${name}: вход ${in_len} ток., выход ${out_len} ток., параллельно ${conc}"
  # \$VLLM_API_KEY и \$MODEL_DIR раскрываются ВНУТРИ пода, токен не проходит через этот терминал
  kubectl -n "${NS}" exec "${POD}" -c vllm -- sh -c "
    OPENAI_API_KEY=\"\$VLLM_API_KEY\" vllm bench serve \
      --backend openai --base-url http://localhost:8000 --endpoint /v1/completions \
      --model ${MODEL} --tokenizer \"\$MODEL_DIR\" \
      --dataset-name random --random-input-len ${in_len} --random-output-len ${out_len} \
      --ignore-eos --num-prompts ${NUM_PROMPTS} --max-concurrency ${conc} --seed ${seed} \
      --percentile-metrics ttft,tpot,e2el --metric-percentiles 50,99 \
      --save-result --result-dir /tmp/bench --result-filename ${name}.json" \
    | grep -E 'Successful|Benchmark duration|throughput|TTFT|E2EL' || true
  kubectl -n "${NS}" cp -c vllm "${POD}:/tmp/bench/${name}.json" "${OUT_DIR}/${name}.json" >/dev/null
done

python3 "$(dirname "$0")/summarize.py" "${OUT_DIR}" | tee "$(dirname "$0")/results.md"