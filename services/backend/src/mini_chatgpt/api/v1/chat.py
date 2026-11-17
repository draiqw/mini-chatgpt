"""POST /chat -> ответ модели потоком SSE."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from mini_chatgpt.api.deps import Rid
from mini_chatgpt.schemas.chat import ChatRequest
from mini_chatgpt.services import chat_service

router = APIRouter(tags=["chat"])

# no-cache -- не кэшировать поток; X-Accel-Buffering: no -- просьба к nginx не копить ответ
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/chat")
async def chat(body: ChatRequest, rid: Rid) -> StreamingResponse:
    """Задать вопрос. Ответ: `data: {"token": "Я"}` ... `data: [DONE]`."""
    tokens = await chat_service.start(rid, body.message)
    return StreamingResponse(tokens, media_type="text/event-stream", headers=SSE_HEADERS)
