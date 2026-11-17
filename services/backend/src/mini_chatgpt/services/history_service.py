"""История сообщений.

Учебный стенд: отдаём сообщения всех пользователей, без авторизации. В настоящем сервисе история
привязывается к пользователю (сессия или токен) и чужая не отдаётся.
"""

from mini_chatgpt.core import db


async def last_messages(rid: str, limit: int) -> list[dict]:
    rows = await db.fetch(rid, "SELECT messages",   # ЛОГ: внутри db.fetch
                          "SELECT role, content, tokens, latency_ms, created_at FROM messages "
                          "ORDER BY id DESC LIMIT %s", (limit,))
    return [{"role": r[0], "content": r[1], "tokens": r[2], "latency_ms": r[3], "at": r[4]} for r in reversed(rows)]
