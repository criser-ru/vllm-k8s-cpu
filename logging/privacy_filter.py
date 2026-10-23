"""Фильтр логов: убирает из логов vLLM промпты и ответы модели,
но оставляет сам факт обращения (id запроса, параметры генерации)."""
import logging
import re

# Логгер vLLM, который пишет о запросах. Сравниваем по окончанию имени:
# путь к модулю меняется между версиями vLLM, а имя файла - нет.
REQUEST_LOGGER_SUFFIX = ".request_logger"

# Страховка для любых других логгеров: признаки пользовательского текста
SENSITIVE = re.compile(r"\b(prompt|prompt_token_ids|output|messages|content)\b\s*[:=]",
                       re.IGNORECASE)


class PrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.endswith(REQUEST_LOGGER_SUFFIX):
            return self._rewrite_request_log(record)

        # Любой другой логгер: если в сообщении похоже на текст пользователя,
        # заменяем сообщение целиком, но саму запись не теряем.
        try:
            text = record.getMessage()
        except Exception:
            return True
        if SENSITIVE.search(text):
            record.msg = "[REDACTED] сообщение логгера %s скрыто: могло содержать данные пользователя"
            record.args = (record.name,)
        return True

    @staticmethod
    def _rewrite_request_log(record: logging.LogRecord) -> bool:
        msg = str(record.msg)
        args = record.args if isinstance(record.args, tuple) else ()
        request_id = args[0] if args else "unknown"

        if msg.startswith("Received request"):
            params = args[1] if len(args) > 1 else None
            record.msg = "Request received: id=%s max_tokens=%s temperature=%s"
            record.args = (request_id,
                           getattr(params, "max_tokens", None),
                           getattr(params, "temperature", None))
            return True

        if msg.startswith("Generated response"):
            finish_reason = args[-1] if len(args) >= 4 else None
            record.msg = "Response generated: id=%s finish_reason=%s"
            record.args = (request_id, finish_reason)
            return True

        # Всё остальное от request_logger (DEBUG-детали с промптом,
        # токенами, телом запроса) не пропускаем вообще.
        return False