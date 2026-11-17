"""Состояние сервиса и соседей."""

from pydantic import BaseModel


class Health(BaseModel):
    ok: bool
    host: str     # id контейнера api
    model: str
    llm: str      # ok | loading model | недоступна: …
    db: str       # ok | недоступна: …
