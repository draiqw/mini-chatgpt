"""Чат. Если JSON не подходит под схему, FastAPI сразу отвечает 422, а ручка не вызывается."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    # ~10k токенов: контекст слота 12k
    message: str = Field(
        min_length=1,
        max_length=20_000,
    )
