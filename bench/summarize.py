#!/usr/bin/env python3
"""Собирает JSON-результаты `vllm bench serve` в markdown-таблицу.
   python3 bench/summarize.py bench/results"""
import json
import sys
from pathlib import Path

ORDER = ["short-c1", "short-c8", "long-c1", "long-c4"]

rows = []
for path in sorted(Path(sys.argv[1]).glob("*.json"),
                   key=lambda p: ORDER.index(p.stem) if p.stem in ORDER else 99):
    r = json.loads(path.read_text())
    n = max(r["completed"], 1)
    rows.append([
        path.stem,
        f"{r['total_input_tokens'] / n:.0f}",
        f"{r['total_output_tokens'] / n:.0f}",
        str(r.get("max_concurrency") or "-"),
        f"{r['completed']}/{r['completed'] + r.get('failed', 0)}",
        f"{r['median_ttft_ms']:.0f}",
        f"{r['p99_ttft_ms']:.0f}",
        f"{r['median_tpot_ms']:.1f}",
        f"{r['median_e2el_ms'] / 1000:.2f}",
        f"{r['p99_e2el_ms'] / 1000:.2f}",
        f"{r['request_throughput']:.2f}",
        f"{r['output_throughput']:.1f}",
        f"{r['total_token_throughput']:.1f}",
    ])

header = ["Сценарий", "Вход, ток.", "Выход, ток.", "Параллельно", "Успешно",
          "TTFT p50, мс", "TTFT p99, мс", "TPOT p50, мс", "Latency p50, с", "Latency p99, с",
          "Запросов/с", "Выходных ток./с", "Всего ток./с"]
print("| " + " | ".join(header) + " |")
print("|" + "---|" * len(header))
for row in rows:
    print("| " + " | ".join(row) + " |")