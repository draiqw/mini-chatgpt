"""GET /health -> живы ли api, модель и база."""

from fastapi import APIRouter

from mini_chatgpt.schemas.health import Health
from mini_chatgpt.services import health_service

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> Health:
    return Health(**await health_service.check())
