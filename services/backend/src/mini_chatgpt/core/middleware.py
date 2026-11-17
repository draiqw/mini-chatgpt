"""ЛОГ: обёртка вокруг каждого запроса."""

import re
import time
import uuid

from fastapi import Request

from mini_chatgpt.core import config
from mini_chatgpt.core.logs import hop, log, short

RID_RE = re.compile(r"[A-Za-z0-9-]{1,64}")


async def trace(
    request: Request,
    call_next,
):
    """ЛОГ: пишет вход [nginx → api] и выход [api → nginx] с кодом и временем.

    rid (X-Request-ID от nginx) кладём в request.state -- ручки берут его оттуда --
    и возвращаем клиенту в заголовке ответа: браузер показывает его под ответом.
    """
    # rid попадает в логи и комментарием в SQL, поэтому берём только безопасные символы.
    # nginx и так ставит свой $request_id (32 hex), но api не должен доверять заголовку вслепую.
    header = request.headers.get("X-Request-ID", "")
    rid = header if RID_RE.fullmatch(header) else uuid.uuid4().hex
    request.state.rid = rid
    t0 = time.perf_counter()
    client = request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "-"
    )
    quiet = request.url.path.endswith("/health")  # health дёргают часто, в лог не пишем
    if not quiet:
        hop(
            rid,
            "nginx",
            "api",
            "%s %s клиент=%s ua=%r",
            request.method,
            request.url.path,
            client,
            short(request.headers.get("user-agent", "-"), 40),
        )
    try:
        response = await call_next(request)
    except Exception:
        # ЛОГ: 500 с полным трейсбеком
        log.exception("rid=%s [api] необработанное исключение", rid)
        raise
    response.headers["X-Request-ID"] = rid
    response.headers["X-Served-By"] = config.HOST
    if not quiet:
        # для /chat это время до заголовков; конец потока пишет сама ручка
        hop(
            rid,
            "api",
            "nginx",
            "%s за %.0f мс",
            response.status_code,
            (time.perf_counter() - t0) * 1000,
        )
    return response
