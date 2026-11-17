"""Проверки, которым не нужны модель, Redis и Postgres: валидация входа, маршруты, rid в ответе.

Запуск: cd services/backend && uv run --group dev pytest
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mini_chatgpt.main import app
from mini_chatgpt.schemas.chat import ChatRequest
from mini_chatgpt.schemas.finetune import FinetuneRequest

client = TestClient(app)  # без `with`: lifespan (подключение к базе) не запускается


def test_chat_without_message_is_422():
    r = client.post("/chat", json={}, headers={"X-Request-ID": "test-rid"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "message"]
    assert r.headers["X-Request-ID"] == "test-rid"  # middleware возвращает rid клиенту


def test_chat_empty_message_is_422():
    assert client.post("/chat", json={"message": ""}).status_code == 422


def test_unknown_path_is_404():
    assert client.get("/caht").status_code == 404


def test_wrong_method_is_405():
    assert client.get("/chat").status_code == 405


def test_schemas_limits():
    assert ChatRequest(message="ты кто?").message == "ты кто?"
    assert FinetuneRequest(dataset="x").epochs == 3
    with pytest.raises(ValidationError):
        FinetuneRequest(dataset="x", epochs=10)
