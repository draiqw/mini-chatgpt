"""Приложение FastAPI. Запуск: uvicorn mini_chatgpt.main:app (см. infrastructure/docker/backend/Dockerfile).

nginx отрезает префикс /api/, поэтому здесь пути без него: /chat, /finetune, /jobs/{id}, /history, /health, /stats.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mini_chatgpt.api.errors import install_error_handlers
from mini_chatgpt.api.v1.chat import router as chat_router
from mini_chatgpt.api.v1.finetune import router as finetune_router
from mini_chatgpt.api.v1.health import router as health_router
from mini_chatgpt.api.v1.history import router as history_router
from mini_chatgpt.api.v1.stats import router as stats_router
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

app.include_router(chat_router)
app.include_router(finetune_router)
app.include_router(history_router)
app.include_router(health_router)
app.include_router(stats_router)
