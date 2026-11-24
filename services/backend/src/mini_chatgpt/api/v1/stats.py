"""POST /stats: статистика текста без вызова модели."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["stats"])


class StatsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20_000)


class StatsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_word_length: int = Field(default=1, ge=1, le=100)


class StatsResponse(BaseModel):
    words: int
    characters: int


@router.post("/stats")
def stats(
    body: StatsRequest,
    options: Annotated[StatsQuery, Query()],
) -> StatsResponse:
    """Посчитать слова не короче min_word_length и все символы строки."""
    words = sum(len(word) >= options.min_word_length for word in body.message.split())
    return StatsResponse(
        words=words,
        characters=len(body.message),
    )
