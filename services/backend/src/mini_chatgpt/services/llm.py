"""Клиент к модели (контейнер llm, llama.cpp). api здесь сам становится клиентом: HTTP-запрос к соседнему контейнеру.

llm говорит на OpenAI-совместимом API: POST /v1/chat/completions со "stream": true отвечает потоком SSE,
по строке `data: {...}` на токен и `data: [DONE]` в конце.
"""

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from mini_chatgpt.core import config
from mini_chatgpt.core.logs import hop


class LLMError(Exception):
    """Модель недоступна или отказала. status -- что вернуть клиенту."""

    def __init__(
        self,
        status: int,
        detail: str,
    ):
        super().__init__(detail)
        self.status, self.detail = status, detail


class Stream:
    """Открытый поток ответа модели. Закрыть обязательно: aclose()."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
        started: float,
    ):
        self.client, self.response, self.started = client, response, started

    async def tokens(self) -> AsyncIterator[str]:
        """Разбираем SSE от модели и отдаём по одному токену."""
        async for line in self.response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[len("data: ") :].strip()
            if data == "[DONE]":
                return
            choices = json.loads(data).get("choices") or []
            token = choices[0].get("delta", {}).get("content") if choices else None
            if token:
                yield token

    async def aclose(self) -> None:
        await self.response.aclose()
        await self.client.aclose()


async def open_stream(
    rid: str,
    message: str,
) -> Stream:
    payload = {
        "messages": [
            {"role": "system", "content": config.SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "stream": True,
        "max_tokens": config.MAX_TOKENS,
        "temperature": 0.7,
        # Qwen3: без режима рассуждений, сразу ответ
        "chat_template_kwargs": {"enable_thinking": False},
    }
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            config.LLM_TIMEOUT_S,
            connect=5,
        )
    )
    t0 = time.perf_counter()
    # ЛОГ: ушли в модель; rid едет и к ней в заголовке X-Request-ID
    hop(
        rid,
        "api",
        "llm",
        "POST %s/v1/chat/completions model=%s stream=true",
        config.LLM_URL,
        config.LLM_MODEL,
    )
    try:
        r = await client.send(
            client.build_request(
                "POST",
                f"{config.LLM_URL}/v1/chat/completions",
                json=payload,
                headers={"X-Request-ID": rid},
            ),
            stream=True,
        )
    except httpx.HTTPError as e:
        await client.aclose()
        # ЛОГ: -> 503
        hop(
            rid,
            "api",
            "llm",
            "не достучались: %s %s",
            type(e).__name__,
            e,
            level=logging.ERROR,
        )
        raise LLMError(503, f"llm недоступна: {type(e).__name__}") from e
    if r.status_code != 200:
        detail = (await r.aread()).decode(errors="replace")[:200]
        await r.aclose()
        await client.aclose()
        # ЛОГ: модель отказала
        hop(
            rid,
            "llm",
            "api",
            "%s: %s",
            r.status_code,
            detail,
            level=logging.ERROR,
        )
        # 400 от модели -- ошибка в запросе (например, не влез в контекст 12k): так и передаём клиенту
        raise LLMError(
            400 if r.status_code == 400 else 503,
            f"llm ответила {r.status_code}: {detail}",
        )
    # ЛОГ: модель приняла запрос, заголовки пришли
    hop(
        rid,
        "llm",
        "api",
        "200 за %.0f мс, заголовки получены, ждём токены",
        (time.perf_counter() - t0) * 1000,
    )
    return Stream(
        client,
        r,
        t0,
    )
