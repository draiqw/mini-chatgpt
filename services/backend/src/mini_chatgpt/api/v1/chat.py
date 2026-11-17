"""POST /chat -> ответ модели потоком SSE."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from mini_chatgpt.api.deps import Rid
from mini_chatgpt.schemas.chat import ChatRequest
from mini_chatgpt.services import chat_service

router = APIRouter(tags=["chat"])

# Заголовки ответа-потока (SSE):
#   Cache-Control: no-cache -- браузер и прокси не берут ответ из кэша:
#       каждый вопрос идёт до сервера, а не отдаётся сохранённый старый ответ.
#   X-Accel-Buffering: no -- служебный заголовок для nginx: этот ответ не копить
#       в буфер, а отдавать браузеру кусками сразу, как токены приходят.
#       nginx его выполняет и до браузера не пропускает. То же делает
#       proxy_buffering off в infrastructure/nginx/app.conf; заголовок --
#       страховка на случай, если конфиг nginx поменяют.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


@router.post("/chat")
async def chat(body: ChatRequest, rid: Rid) -> StreamingResponse:
    """Задать вопрос. Ответ: `data: {"token": "Я"}` ... `data: [DONE]`."""
    tokens = await chat_service.start(rid, body.message)
    return StreamingResponse(
        tokens, media_type="text/event-stream", headers=SSE_HEADERS
    )
