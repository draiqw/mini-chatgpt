"""Настройки из переменных окружения. Значения задаёт compose (infrastructure/docker-compose), секреты -- в .env."""

import os
import socket

LLM_URL = os.environ.get("LLM_URL", "http://llm:8001")   # имя сервиса из compose, не localhost
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen3-1.7B-Q8_0.gguf")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://chat:chat@db:5432/chat")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

SYSTEM_PROMPT = "Ты мини-ChatGPT с семинара по вебу. Отвечай по-русски, коротко и по делу."
MAX_TOKENS = 512        # длина ответа модели
LLM_TIMEOUT_S = 300     # сколько ждём весь ответ модели

HOST = socket.gethostname()   # id контейнера: уходит клиенту в заголовке X-Served-By
