"""Чат: сохранить вопрос, открыть поток у модели и ретранслировать токены клиенту строками SSE."""

import json
import time
from collections.abc import AsyncIterator

from mini_chatgpt.core import db
from mini_chatgpt.core.logs import hop, log, short
from mini_chatgpt.services import llm


async def start(rid: str, message: str) -> AsyncIterator[str]:
    """Вернуть поток `data: {"token": ...}`. Если модель недоступна -- llm.LLMError ещё до первого байта ответа."""
    # ЛОГ: что спросили
    hop(rid, "api", "api", "chat: сообщение %d симв. %r", len(message), short(message))
    await db.execute(
        rid,
        "INSERT INTO messages (rid, role, content) VALUES (%s, 'user', %s)",
        (rid, message),
    )
    stream = await llm.open_stream(rid, message)
    return _relay(rid, stream)


async def _relay(rid: str, stream: llm.Stream) -> AsyncIterator[str]:
    """Получили токен от модели -- сразу отдаём. yield не ждёт конца функции: так и получается поток."""
    n, first, answer = 0, None, ""
    try:
        async for token in stream.tokens():
            n += 1
            answer += token
            if (
                first is None
            ):  # ЛОГ: только первый токен, чтобы не писать строку на каждый
                first = time.perf_counter()
                hop(
                    rid,
                    "llm",
                    "api",
                    "первый токен через %.0f мс",
                    (first - stream.started) * 1000,
                )
                hop(rid, "api", "nginx", "стрим SSE открыт, токены идут по одному")
            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        total = time.perf_counter() - stream.started
        latency = first - stream.started if first else None
        speed = n / (total - latency) if latency is not None and total > latency else 0
        # ЛОГ: итог стрима: сколько токенов, за сколько, скорость, начало ответа
        hop(
            rid,
            "api",
            "nginx",
            "стрим закрыт: %d токенов за %.2f с (%.1f ток/с), ответ %r",
            n,
            total,
            speed,
            short(answer, 80),
        )
        await db.execute(
            rid,
            "INSERT INTO messages (rid, role, content, tokens, latency_ms) "
            "VALUES (%s, 'assistant', %s, %s, %s)",
            (rid, answer, n, int(latency * 1000) if latency is not None else None),
        )
    except Exception:
        # ЛОГ: обрыв на середине
        log.exception("rid=%s [llm → api] стрим оборвался после %d токенов", rid, n)
        raise
    finally:
        await stream.aclose()
