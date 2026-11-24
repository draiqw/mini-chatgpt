"""POST /stats: статистика текста без вызова модели."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["stats"])


class StatsRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class StatsResponse(BaseModel):
    words: int
    characters: int


@router.post("/stats")
def stats(body: StatsRequest) -> StatsResponse:
    return StatsResponse(
        words=len(body.message.split()),
        characters=len(body.message),
    )
