"""Проверка соседей: модель после старта несколько секунд грузит веса, база может ещё подниматься."""

import httpx

from mini_chatgpt.core import config, db


async def check() -> dict:
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            llm = (await c.get(f"{config.LLM_URL}/health")).json().get("status", "?")
    except (httpx.HTTPError, ValueError) as e:
        llm = f"недоступна: {type(e).__name__}"
    try:
        await db.ping()
        db_state = "ok"
    except Exception as e:  # noqa: BLE001 -- для health любая ошибка базы = «не ok»
        db_state = f"недоступна: {type(e).__name__}"
    return {"ok": True, "host": config.HOST, "model": config.LLM_MODEL, "llm": llm, "db": db_state}
