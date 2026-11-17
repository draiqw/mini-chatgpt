"""Ошибки -> HTTP-ответы. Ручки не ловят исключения сами: этим занимаются обработчики ниже."""

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mini_chatgpt.core.logs import hop
from mini_chatgpt.services.llm import LLMError


async def _on_422(
    request: Request,
    exc: RequestValidationError,
):
    """ЛОГ: FastAPI отвечает 422 на кривой JSON сам; дописываем в лог, какое поле не прошло проверку."""
    errs = "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
    )
    hop(
        getattr(
            request.state,
            "rid",
            "-",
        ),
        "api",
        "api",
        "422 pydantic: %s",
        errs,
        level=logging.WARNING,
    )
    return await request_validation_exception_handler(request, exc)


async def _on_llm_error(
    request: Request,
    exc: LLMError,
):
    """Модель недоступна -> 503, запрос не влез в контекст -> 400. Честная ошибка вместо пустого потока."""
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status,
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _on_422)
    app.add_exception_handler(LLMError, _on_llm_error)
