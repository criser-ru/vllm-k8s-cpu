# vLLM на CPU в Kubernetes

Инференс модели [Qwen/Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) через vLLM 0.32.0 на CPU в Minikube.

- OpenAI-совместимый API, доступ только с Bearer-токеном.
- Собственные образы без root: vLLM и лёгкий образ загрузчика модели для initContainer.
- Все зависимости, включая вторичные, зафиксированы в `requirements.txt`.
- Логи без текстов промптов и ответов, но с фактом каждого обращения.
- Модель скачивается один раз на постоянный диск (PVC), дальше берётся локально.
- Токены в Secret, настройки vLLM в ConfigMap.

Выполнены все основные требования и все три бонуса: Kustomize, initContainer на отдельном лёгком образе, нагрузочное тестирование с аналитикой.

## Архитектура
Клиент ──> Service vllm:8000 ──> Pod vllm
                                  ├─ initContainer model-downloader (образ 54 МБ)
                                  │    качает модель с Hugging Face на PVC,
                                  │    если её там ещё нет (маркер .download-complete)
                                  └─ контейнер vllm (UID 1000)
                                       читает модель с PVC без доступа к сети
                                       (HF_HUB_OFFLINE=1) и обслуживает запросы

Secret vllm-secrets:      HF_TOKEN -> только загрузчику, VLLM_API_KEY -> только vLLM
ConfigMap vllm-env:       модель, ревизия, путь на PVC, настройки CPU-бэкенда
ConfigMap vllm-serve-config: файл /etc/vllm/config.yaml для vllm serve --config
PVC vllm-models:          10Gi, веса модели

## Структура репозитория
.
├── README.md
├── client_example.py            # пример запроса через официальный клиент openai
├── docker/
│   ├── vllm/
│   │   ├── Dockerfile           # образ vLLM: python:3.12-slim-trixie, USER 1000
│   │   ├── entrypoint.sh        # проверка модели на PVC, offline-режим, запуск vllm serve
│   │   ├── requirements.in      # прямые зависимости (vllm, triton-cpu)
│   │   └── requirements.txt     # все 151 пакет с точными версиями (генерируется)
│   └── downloader/
│       ├── Dockerfile           # лёгкий образ загрузчика, USER 1000
│       ├── requirements.in      # huggingface_hub
│       └── requirements.txt     # 15 пакетов с версиями и хешами sha256 (генерируется)
├── scripts/
│   ├── lock_deps.sh             # пересборка docker/vllm/requirements.txt
│   └── download_model.py        # скачивание модели на PVC (работает в initContainer)
├── logging/
│   ├── privacy_filter.py        # фильтр, убирающий промпты и ответы из логов
│   ├── logging_config.json      # конфиг логирования для vLLM и uvicorn
│   └── test_privacy_filter.py   # тест фильтра без запуска vLLM
├── k8s/
│   ├── kustomization.yaml       # kubectl apply -k k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml           # vllm-env и vllm-serve-config
│   ├── pvc.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── secret.example.yaml      # только шаблон, настоящий Secret создаётся командой
└── bench/
    ├── run_bench.sh             # нагрузочный тест (vllm bench serve внутри пода)
    ├── summarize.py             # сводная таблица из JSON-результатов
    └── results.md               # итоговая таблица

## Что нужно

- Linux x86_64 или Windows 11 + WSL2. Проверено на Windows 11 + WSL2 (Ubuntu) + Docker Desktop.
- Docker, Minikube, kubectl, `openssl`, `jq`; для генерации списков зависимостей `uv`.
- Свободно хотя бы 8 CPU и 20 ГБ RAM для Minikube.
- Токен Hugging Face с правами Read. Модель открытая, токен нужен для повышенных лимитов скачивания и для закрытых моделей.

## Быстрый старт

```bash
# 1. Кластер
minikube start --driver=docker --cpus=8 --memory=20g --disk-size=40g

# 2. Образы (из корня репозитория) и загрузка их в Minikube
docker build -f docker/vllm/Dockerfile -t vllm-cpu:0.32.0 .
docker build -f docker/downloader/Dockerfile -t model-downloader:1.0 .
minikube image load vllm-cpu:0.32.0
minikube image load model-downloader:1.0

# 3. Namespace и Secret (токены вводятся в терминал и не попадают в файлы и историю)
kubectl apply -f k8s/namespace.yaml
read -rs -p 'HF token: ' HF_TOKEN; echo
VLLM_API_KEY="$(openssl rand -hex 32)"
kubectl -n llm-inference create secret generic vllm-secrets \
  --from-literal=HF_TOKEN="$HF_TOKEN" --from-literal=VLLM_API_KEY="$VLLM_API_KEY"

# 4. Всё остальное одной командой
kubectl apply -k k8s/
kubectl -n llm-inference get pods -w      # ждать READY 1/1 (первый раз 5-7 минут)

# 5. Доступ (в отдельном терминале)
kubectl -n llm-inference port-forward svc/vllm 8000:8000

# 6. Запрос
export VLLM_API_KEY=$(kubectl -n llm-inference get secret vllm-secrets \
  -o jsonpath='{.data.VLLM_API_KEY}' | base64 -d)
curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $VLLM_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-0.5b-instruct","messages":[{"role":"user","content":"Привет! Кто ты?"}],"max_tokens":50}' \
  | jq -r '.choices[0].message.content'

# То же через официальный клиент OpenAI
uv run --with openai python client_example.py
```

Остановить с сохранением всего (модель остаётся на PVC): `minikube stop`, запустить снова: `minikube start`.
Удалить всё, включая модель: `kubectl delete -k k8s/`.

## Проверка требований

Все выводы ниже получены на моей машине. Для краткости `K="kubectl -n llm-inference"`.

| Требование | Команда | Результат |
|---|---|---|
| Инференс на CPU | `$K logs deploy/vllm -c vllm \| grep -o 'device_config=cpu'` | `device_config=cpu` |
| vLLM ≥ 0.27.0, CPU-сборка | `$K exec deploy/vllm -c vllm -- python -c "import importlib.metadata as m; print(m.version('vllm'))"` | `0.32.0+cpu` |
| Запуск не от root | `$K exec deploy/vllm -c vllm -- id` | `uid=1000(app) gid=1000(app) groups=1000(app)` |
| Без токена доступа нет | `curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/v1/models` | `401` |
| С токеном доступ есть | то же с `-H "Authorization: Bearer $VLLM_API_KEY"` | `200` |
| Промпты и ответы не в логах | запрос с текстом "МАРКЕР-777 скажи привет", затем `$K logs deploy/vllm -c vllm \| grep -ci маркер` | `0` |
| Факт обращения в логах | `$K logs deploy/vllm -c vllm \| grep -E 'Request received\|POST /v1'` | по две строки на запрос, пример ниже |
| Первый запуск скачивает модель | `$K logs deploy/vllm -c model-downloader` | `готово за 133 с: 1 файл(ов) весов, 0.93 ГБ` |
| Повторный запуск без скачивания | `$K delete pod -l app=vllm`, затем логи загрузчика | `уже есть в /models/qwen2.5-0.5b-instruct, скачивание пропущено` |
| Модель на PVC | `$K get pvc vllm-models` | `Bound`, `10Gi`, `RWO` |
| Токен HF не виден vLLM | `$K exec deploy/vllm -c vllm -- printenv HF_TOKEN` | `command terminated with exit code 1` |
| Настройки через ConfigMap | `max-model-len` 4096 -> 2048, `apply -k`, `rollout restart`, затем `curl .../v1/models \| jq '.data[0].max_model_len'` | `2048`, образ не пересобирался |
| Kustomize | `kubectl apply -k k8s/` | все 6 объектов `unchanged` |
| Загрузчик на лёгком образе | `minikube image ls --format table` | `model-downloader:1.0` 53.6 МБ против `vllm-cpu:0.32.0` 1.16 ГБ |

Пример логов: на каждый запрос две строки, без текста промпта и ответа.

INFO 2026-10-23 16:32:45 [vllm.entrypoints.serve.utils.request_logger] Request received: id=chatcmpl-822c311981b0187a max_tokens=20 temperature=0.7
INFO 2026-10-23 16:32:46 [uvicorn.access] 127.0.0.1:48176 - "POST /v1/chat/completions HTTP/1.1" 200

Первое скачивание модели:

[download_model] скачиваю Qwen/Qwen2.5-0.5B-Instruct@main в /models/qwen2.5-0.5b-instruct (токен HF: есть)
Fetching 7 files: 100%|██████████| 7/7 [02:12<00:00, 18.88s/it]
[download_model] готово за 133 с: 1 файл(ов) весов, 0.93 ГБ

## Как поменять настройки

Все параметры инференса лежат в `k8s/configmap.yaml`:

- `vllm-env`: какая модель, её ревизия и папка на PVC; размер KV-кэша (`VLLM_CPU_KVCACHE_SPACE`); сколько ядер оставить под HTTP-сервер.
- `vllm-serve-config`: флаги `vllm serve` в виде YAML (`max-model-len`, `max-num-seqs`, `max-num-batched-tokens`, кэш префиксов и т.д.).

Порядок: отредактировать файл, затем `kubectl apply -k k8s/` и `kubectl -n llm-inference rollout restart deployment/vllm`. Перезапуск нужен, потому что переменные окружения и флаги читаются один раз при старте.

Пример смены модели на Qwen2.5-1.5B-Instruct: поменять `MODEL_ID` и `MODEL_DIR` (новая папка), поднять лимит памяти пода до 10Gi. Загрузчик скачает новую модель в новую папку, старая останется на диске.

## Приватность логов

vLLM пишет данные запроса в логгер `vllm.entrypoints.serve.utils.request_logger`: на уровне INFO параметры генерации, на уровне DEBUG полный промпт и тело запроса, с флагом `--enable-log-outputs` ещё и ответ модели. Задача: чтобы текст пользователя не попал в stdout/stderr ни при каких флагах, но факт обращения оставался.

Решение:

- `VLLM_LOGGING_CONFIG_PATH` подменяет конфиг логирования vLLM нашим `logging/logging_config.json`. vLLM применяет его во всех своих процессах и передаёт в uvicorn.
- `PrivacyFilter` из `logging/privacy_filter.py` переписывает записи `request_logger` по белому списку: от запроса остаются id, `max_tokens` и `temperature`, от ответа — id и причина завершения. Все остальные записи этого логгера, включая DEBUG с промптом, выбрасываются. В записях других логгеров фильтр ищет признаки пользовательского текста (`prompt:`, `messages=` и т.п.) и заменяет такое сообщение на `[REDACTED]`, саму запись не теряя.
- Фильтр стоит на обработчике (handler), а не на логгере. Фильтр логгера не видит записей дочерних логгеров, которые приходят к нему через propagation, а фильтр обработчика видит всё, что печатается.
- `--enable-log-requests` включён (факт обращения), `--enable-log-outputs` не включён.

Тест без запуска vLLM имитирует вызовы логгера, которые делает vLLM 0.32.0:

```
$ python3 logging/test_privacy_filter.py
OK: промпты и ответы скрыты, факт обращения записан
```

## Безопасность

- Оба образа запускаются от пользователя с числовым UID 1000. Числовой, чтобы Kubernetes мог проверить `runAsNonRoot` без чтения `/etc/passwd`. Код приложения принадлежит root и доступен процессу только на чтение.
- Pod: `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, `capabilities: drop: [ALL]`, `seccompProfile: RuntimeDefault`, `automountServiceAccountToken: false`. Запись разрешена только в смонтированные тома: PVC (только загрузчику), `/tmp`, `/home/app`, `/dev/shm`.
- Токены лежат только в Secret, и каждый контейнер получает только свой: Secret подключается по одному ключу через `secretKeyRef`, а не целиком через `envFrom`. В репозитории есть только шаблон `secret.example.yaml`, сам Secret создаётся командой. Токен API передаётся в vLLM переменной `VLLM_API_KEY`, а не флагом `--api-key`: флаги видны в `ps` и печатаются vLLM при старте.
- Проверки здоровья (`/health`) не требуют токена, все пути `/v1/...` требуют.
- Зависимости: основной образ ставит пакеты строго из `requirements.txt` с `--no-deps` и проверяет `pip check`; образ загрузчика — с `--require-hashes`.

## Нагрузочное тестирование

**Железо:** Intel Core i5-12400F (6 ядер / 12 потоков), Windows 11 + WSL2 (10 CPU, 28 ГБ). Minikube запущен с `--cpus=8 --memory=20g`, поду vLLM выделено `cpu request 4`, `memory 8Gi`; по логам vLLM привязал вычисления к 4 ядрам и ещё одно оставил под HTTP-сервер.

**Методика:** `vllm bench serve` внутри пода (без сетевых потерь port-forward), датасет `random` (случайные токены заданной длины), `--ignore-eos`: каждый ответ ровно 128 токенов. 32 запроса на сценарий. Перед замерами идёт прогрев на 4 запросах, у каждого сценария свой `--seed`. Запуск: `./bench/run_bench.sh`.

| Сценарий | Вход, ток. | Выход, ток. | Параллельно | Успешно | TTFT p50, мс | TTFT p99, мс | TPOT p50, мс | Latency p50, с | Latency p99, с | Запросов/с | Выходных ток./с | Всего ток./с |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| short-c1 | 128 | 128 | 1 | 32/32 | 1723 | 2023 | 57.2 | 9.09 | 11.56 | 0.11 | 14.3 | 28.5 |
| short-c8 | 128 | 128 | 8 | 32/32 | 12991 | 13758 | 190.5 | 37.27 | 41.62 | 0.21 | 27.0 | 54.0 |
| long-c1 | 3072 | 128 | 1 | 32/32 | 50364 | 54061 | 55.5 | 57.42 | 62.44 | 0.02 | 2.2 | 55.3 |
| long-c4 | 3072 | 128 | 4 | 32/32 | 100682 | 214972 | 916.2 | 216.08 | 327.91 | 0.02 | 2.3 | 56.9 |

TTFT — время до первого токена, TPOT — время на каждый следующий токен, Latency — полное время запроса.

### Что видно в цифрах

1. **Длина промпта определяет TTFT.** Промпт long-c1 длиннее, чем у short-c1, в 24 раза, а TTFT больше в 29 раз (50.4 с против 1.7 с). Prefill (обработка промпта) на этой машине идёт со скоростью около 60 токенов/с.
2. **Длина контекста почти не влияет на TPOT:** 55.5 мс у long-c1 против 57.2 мс у short-c1. На каждом шаге генерации модель один раз читает все веса, а длинный KV-кэш добавляет только вычисления внимания.
3. **Батчинг на коротких запросах:** при 8 параллельных запросах выходная скорость сервера выросла в 1.9 раза (27.0 против 14.3 ток./с), но TPOT каждого запроса вырос в 3.3 раза. Это и есть компромисс между пропускной способностью и задержкой. TTFT у short-c8 13 с: восемь запросов приходят разом, и их prefill (8 × 128 = 1024 токена) при ~60 ток./с занимает примерно столько же.
4. **Длинные запросы мешают друг другу.** У long-c4 TTFT p99 вдвое больше p50 (215 с против 101 с): запросы ждут в очереди за prefill друг друга. Пропускная способность при этом не выросла (2.3 против 2.2 ток./с), а TPOT вырос до 916 мс: процессор полностью занят prefill, и шаги генерации остальных запросов ждут, пока посчитается очередной промпт на 3072 токена.

Вывод: на этом железе узкое место — вычисления prefill. Вероятная причина в процессоре: у i5-12400F нет AVX-512 и AMX, которыми vLLM на CPU ускоряет матричные операции в BF16. С этим согласуется предупреждение в логах `Failed to create oneDNN linear, fallback to torch linear`. Это гипотеза, отдельно я её не проверял.

### Ошибка методики, найденная по ходу

В первом прогоне у long-c4 получился TTFT 7.9 с — в 6 раз меньше, чем у long-c1, хотя четыре параллельных длинных запроса не могут обрабатываться быстрее одного. Причина: `vllm bench serve` генерирует "случайные" промпты из одного и того же seed, поэтому long-c4 получил ровно те же промпты, что long-c1, и сервер брал готовый prefill из кэша префиксов (`Prefix cache hit rate` в логах дошёл до 48%). Исправлено: у каждого сценария свой `--seed`, плюс прогрев перед замерами (в первом прогоне p99 TTFT у short-c1 был 11.4 с из-за компиляции на первом запросе, после прогрева — 2.0 с). В таблице выше результаты второго прогона.

### Как поднять пропускную способность

Два параметра документация vLLM для CPU называет ключевыми: `max-num-batched-tokens` сильнее влияет на prefill (первый токен), `max-num-seqs` — на генерацию остальных токенов. В ConfigMap стоят консервативные значения под ноутбук: 4096 и 16.

**А) Много запросов с маленьким числом токенов.** Нагрузка упирается в генерацию (decode): prefill дешёвый, а на каждом шаге дороже всего прочитать веса из памяти. Цель — обслужить за одно чтение весов как можно больше запросов.

- Поднять `max-num-seqs` (16 -> 64–128): больше запросов в одном шаге — выше токенов/с на сервер. Цена — рост TPOT каждого запроса, что видно уже на short-c8.
- Поднять `VLLM_CPU_KVCACHE_SPACE`, чтобы эти запросы поместились. Каждому короткому запросу нужно мало кэша, но их много. Если кэша не хватит, vLLM начнёт вытеснять запросы (preemption) и пересчитывать их.
- Держать включённым кэш префиксов: в реальных чатах у всех запросов общий системный промпт, и его prefill делается один раз.
- Масштабироваться горизонтально: маленькие независимые запросы хорошо делятся между репликами за тем же Service, а на многосокетном сервере — между NUMA-узлами (data parallel).
- `max-num-batched-tokens` здесь вторичен: достаточно, чтобы он был не меньше `max-num-seqs`.

**Б) Мало запросов, но с огромным контекстом.** Нагрузка упирается в prefill и в память под KV-кэш. Оценка для Qwen2.5-0.5B (24 слоя, 2 KV-головы по 64): 2 (K и V) × 24 × 2 × 64 × 2 байта = 12 КБ на токен, то есть ~384 МБ на один запрос в 32 768 токенов.

- Поднять `max-model-len` до нужной длины (иначе сервер ответит 400), а под него `VLLM_CPU_KVCACHE_SPACE` с запасом на несколько таких запросов и лимит памяти пода.
- Поднять `max-num-batched-tokens` (4096 -> 8192–16384). Длинный промпт обрабатывается кусками (chunked prefill), и этот параметр задаёт размер куска: крупнее куски — меньше шагов и лучше загрузка матричных инструкций. Цена — пока считается большой кусок, остальные запросы ждут свой следующий токен; это ровно эффект TPOT 916 мс у long-c4.
- Понизить `max-num-seqs` до 2–4: запросов всё равно мало, а низкий лимит защищает начатые длинные запросы от вытеснения, после которого их prefill пришлось бы считать заново.
- Кэш префиксов даёт огромный выигрыш, если один и тот же документ спрашивают повторно: повторный prefill почти бесплатен. Это наглядно показал неудачный первый прогон.
- Квантизация весов (vLLM на x86 CPU поддерживает AWQ, GPTQ и INT8 W8A8) освобождает память под KV-кэш, а на многосокетном сервере — tensor parallel по NUMA-узлам.

Коротко: в случае А увеличиваем ширину батча (больше запросов за шаг генерации), в случае Б — глубину (больше токенов за шаг prefill) и следим, чтобы хватило KV-кэша.

## С чем столкнулся при разработке

| Проблема | Причина | Решение |
|---|---|---|
| uv: у `vllm==0.32.0+cpu` нет подходящего wheel | CPU-сборке нужна glibc 2.39+, в `python:3.12-slim-bookworm` 2.36 | базовый образ `python:3.12-slim-trixie` (glibc 2.41) |
| uv: `triton` was included as a URL dependency | CPU-сборка vLLM ссылается на triton-cpu прямой ссылкой на GitHub | ссылка указана явно в `requirements.in` |
| `Permission denied: '/home/app/.cache/vllm'` при запуске в Docker | Docker создал недостающую папку для тома от root | `/home/app/.cache` создаётся в Dockerfile и отдаётся пользователю app |
| Под в CrashLoopBackOff: `VLLM_PORT 'tcp://...' appears to be a URI` | Kubernetes добавляет в под переменные `<ИМЯ_SERVICE>_PORT`; для Service `vllm` это `VLLM_PORT`, а vLLM считает её своей настройкой | `enableServiceLinks: false` в Deployment |
| vLLM падает после прогрева: не хватает памяти под KV-кэш | после загрузки весов и компиляции из лимита 6Gi оставалось 1.3 ГиБ при запрошенных 2 ГиБ | лимит памяти пода поднят до 8Gi |
| Аномально низкий TTFT у long-c4 | одинаковые промпты из-за общего seed + кэш префиксов | разные `--seed` и прогрев |

## Ограничения

- Тест на ноутбуке под Windows + WSL2, а клиент бенчмарка работает в том же поде и отнимает немного CPU у сервера.
- Модель на 0.5B параметров выбрана из-за ограничений CPU и памяти. Качество ответов не было целью: на фактических вопросах она ошибается, особенно на русском.
- Хеши есть только у зависимостей загрузчика. У основного образа версии зафиксированы, но без хешей: пакеты лежат в трёх разных индексах (wheels.vllm.ai, download.pytorch.org, PyPI) плюс triton-cpu на GitHub.
- `MODEL_REVISION` стоит `main`, а не хеш коммита модели.