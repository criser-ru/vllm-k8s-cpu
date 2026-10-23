#!/usr/bin/env python3
"""Скачивает веса модели с Hugging Face на примонтированный том (PVC).

Первый запуск пода: модели на томе нет -> скачиваем и ставим маркер.
Следующие запуски: маркер есть -> выходим сразу, в сеть не идём.

Настройки через переменные окружения:
  MODEL_ID        - репозиторий на HF, например Qwen/Qwen2.5-0.5B-Instruct (обязательно)
  MODEL_REVISION  - ветка, тег или хеш коммита (по умолчанию main)
  MODEL_DIR       - куда класть файлы (по умолчанию /models/model)
  HF_TOKEN        - токен HF; нужен только для закрытых (gated) моделей
"""
import os
import sys
import time
from pathlib import Path

MARKER_NAME = ".download-complete"
# Берём только то, что нужно vLLM: конфиги, токенизатор, веса в safetensors.
# Дубли весов в других форматах (*.bin, *.pth, *.gguf) не качаем.
ALLOW_PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.model", "*.tiktoken", "*.jinja"]
ATTEMPTS = 3


def log(message: str) -> None:
    print(f"[download_model] {message}", flush=True)


def main() -> int:
    model_id = os.environ.get("MODEL_ID")
    if not model_id:
        log("ОШИБКА: не задана переменная MODEL_ID")
        return 2
    revision = os.environ.get("MODEL_REVISION", "main")
    model_dir = Path(os.environ.get("MODEL_DIR", "/models/model"))
    marker = model_dir / MARKER_NAME
    wanted = f"{model_id}@{revision}"

    # 1. Модель уже скачана - ничего не делаем
    if marker.exists():
        on_disk = marker.read_text().strip()
        if on_disk == wanted:
            log(f"{wanted} уже есть в {model_dir}, скачивание пропущено")
            return 0
        log(f"ОШИБКА: в {model_dir} лежит другая модель ({on_disk}). "
            f"Укажи для {wanted} другой MODEL_DIR или очисти том.")
        return 3

    # 2. Скачиваем (импорт здесь, чтобы ветка 'уже скачано' не зависела от библиотеки)
    from huggingface_hub import snapshot_download

    token = os.environ.get("HF_TOKEN") or None  # пустая строка из Secret -> None
    model_dir.mkdir(parents=True, exist_ok=True)
    log(f"скачиваю {wanted} в {model_dir} (токен HF: {'есть' if token else 'нет'})")

    for attempt in range(1, ATTEMPTS + 1):
        try:
            started = time.monotonic()
            snapshot_download(
                repo_id=model_id,
                revision=revision,
                local_dir=model_dir,
                token=token,
                allow_patterns=ALLOW_PATTERNS,
            )
            break
        except Exception as exc:  # сеть, 401/403 для gated-модели, 404 и т.п.
            log(f"попытка {attempt}/{ATTEMPTS} не удалась: {type(exc).__name__}: {exc}")
            if attempt == ATTEMPTS:
                return 1
            time.sleep(5 * attempt)

    # 3. Проверяем, что веса действительно на месте, и только потом ставим маркер
    weights = list(model_dir.glob("*.safetensors"))
    if not weights or not (model_dir / "config.json").exists():
        log("ОШИБКА: после скачивания нет config.json или *.safetensors")
        return 1
    size_gb = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) / 1024**3
    marker.write_text(wanted + "\n")
    log(f"готово за {time.monotonic() - started:.0f} с: {len(weights)} файл(ов) весов, {size_gb:.2f} ГБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())