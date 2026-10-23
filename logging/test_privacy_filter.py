"""Проверка фильтра без vLLM: python3 logging/test_privacy_filter.py"""
import io
import json
import logging
import logging.config
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

config = json.load(open(os.path.join(HERE, "logging_config.json")))
config["handlers"]["console"]["stream"] = "ext://sys.stdout"
buf = io.StringIO()
sys.stdout, real_stdout = buf, sys.stdout
logging.config.dictConfig(config)

req_log = logging.getLogger("vllm.entrypoints.serve.utils.request_logger")
req_log.setLevel(logging.DEBUG)
params = types.SimpleNamespace(max_tokens=64, temperature=0.7)

# Ровно те вызовы, которые делает vLLM 0.32.0 (request_logger.py)
req_log.debug("Request %s details: prompt: %r, prompt_token_ids: %s, prompt_embeds shape: %s.",
              "req-1", "SECRET_PROMPT", [1, 2, 3], None)
req_log.debug("Request %s JSON body: %s", "req-1", '{"messages":"SECRET_PROMPT"}')
req_log.info("Received request %s: params: %s, lora_request: %s.", "req-1", params, None)
req_log.info("Generated response %s%s: output: %r, finish_reason: %s",
             "req-1", "", "SECRET_ANSWER", "stop")
logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d',
                                         "10.0.0.5:5555", "POST", "/v1/chat/completions", "1.1", 200)
logging.getLogger("vllm.some.module").info("unexpected prompt: %s", "SECRET_PROMPT")

sys.stdout = real_stdout
out = buf.getvalue()
print(out)
assert "SECRET" not in out, "в логи утёк пользовательский текст!"
assert "Request received: id=req-1" in out, "факт обращения не залогирован"
assert "Response generated: id=req-1 finish_reason=stop" in out
assert "POST /v1/chat/completions" in out
print("OK: промпты и ответы скрыты, факт обращения записан")