"""Общие зависимости ручек."""

from typing import Annotated

from fastapi import Depends, Request


def _rid(request: Request) -> str:
    # положил core/middleware.trace из заголовка X-Request-ID от nginx
    return request.state.rid


Rid = Annotated[str, Depends(_rid)]  # в ручке: `rid: Rid`
