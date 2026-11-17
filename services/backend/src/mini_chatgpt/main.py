"""Приложение FastAPI. Запуск: uvicorn mini_chatgpt.main:app (см. infrastructure/docker/backend/Dockerfile).

nginx отрезает префикс /api/, поэтому здесь пути без него: /chat, /finetune, /jobs/{id}, /history, /health.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mini_chatgpt.api.errors import install_error_handlers
from mini_chatgpt.api.v1 import chat, finetune, health, history
from mini_chatgpt.core import db
from mini_chatgpt.core.logs import setup_logging
from mini_chatgpt.core.middleware import trace

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await db.open_pool()  # один раз при старте; база ещё поднимается -- ждём до 30 с
    yield
    await db.close_pool()


app = FastAPI(
    title="mini-chatgpt",
    lifespan=lifespan,
)
app.middleware("http")(trace)  # ЛОГ: вход и выход каждого запроса, rid
install_error_handlers(app)  # 422 с логом, ошибки модели -> 503/400

for module in (chat, finetune, history, health):
    app.include_router(module.router)
