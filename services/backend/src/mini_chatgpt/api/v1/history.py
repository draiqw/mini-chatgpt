"""GET /history -> последние сообщения из базы."""

from fastapi import APIRouter, Query

from mini_chatgpt.api.deps import Rid
from mini_chatgpt.schemas.history import HistoryItem
from mini_chatgpt.services import history_service

router = APIRouter(tags=["history"])


@router.get("/history")
async def history(rid: Rid, limit: int = Query(20, ge=1, le=100)) -> list[HistoryItem]:
    """Последние сообщения, старые сверху."""
    return [HistoryItem(**m) for m in await history_service.last_messages(rid, limit)]
