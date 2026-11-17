"""Общие зависимости ручек."""

from typing import Annotated

from fastapi import Depends, Request


def _rid(request: Request) -> str:
    return request.state.rid   # положил core/middleware.trace из заголовка X-Request-ID от nginx


Rid = Annotated[str, Depends(_rid)]   # в ручке: `rid: Rid`
