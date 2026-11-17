"""История сообщений из Postgres."""

from datetime import datetime

from pydantic import BaseModel


class HistoryItem(BaseModel):
    role: str                      # user | assistant
    content: str
    tokens: int | None = None
    latency_ms: int | None = None  # для ответа: время до первого токена
    at: datetime
