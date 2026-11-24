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
    r = client.post(
        "/chat",
        json={},
        headers={"X-Request-ID": "test-rid"},
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "message"]
    assert r.headers["X-Request-ID"] == "test-rid"  # middleware возвращает rid клиенту


def test_chat_empty_message_is_422():
    assert (
        client.post(
            "/chat",
            json={"message": ""},
        ).status_code
        == 422
    )


def test_unknown_path_is_404():
    assert client.get("/caht").status_code == 404


def test_wrong_method_is_405():
    assert client.get("/chat").status_code == 405


def test_stats():
    r = client.post("/stats", json={"message": "hello world"})
    assert r.status_code == 200
    assert r.json() == {"words": 2, "characters": 11}


@pytest.mark.parametrize("body", [{"text": "hello"}, {"message": ""}])
def test_stats_rejects_invalid_message(body):
    assert client.post("/stats", json=body).status_code == 422


def test_stats_query_changes_word_count():
    r = client.post("/stats?min_word_length=5", json={"message": "hi world"})
    assert r.status_code == 200
    assert r.json() == {"words": 1, "characters": 8}


@pytest.mark.parametrize(
    ("url", "body", "location", "error"),
    [
        ("/stats", {"message": "hi", "extra": 1}, "body", "extra_forbidden"),
        ("/stats?extra=1", {"message": "hi"}, "query", "extra_forbidden"),
        ("/stats?min_word_length=0", {"message": "hi"}, "query", "greater_than_equal"),
    ],
)
def test_stats_validates_body_and_query(url, body, location, error):
    r = client.post(url, json=body)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][0] == location
    assert r.json()["detail"][0]["type"] == error


def test_stats_openapi_shows_query_and_body_without_auth():
    operation = app.openapi()["paths"]["/stats"]["post"]
    assert [(item["name"], item["in"]) for item in operation["parameters"]] == [
        ("min_word_length", "query")
    ]
    assert operation["requestBody"]["required"]
    assert not operation.get("security")


def test_schemas_limits():
    assert ChatRequest(message="ты кто?").message == "ты кто?"
    assert FinetuneRequest(dataset="x").epochs == 3
    with pytest.raises(ValidationError):
        FinetuneRequest(
            dataset="x",
            epochs=10,
        )


def test_unsafe_rid_is_replaced():
    # rid уходит комментарием в SQL: '*/ ... /*' из заголовка не должен туда попасть
    r = client.post(
        "/chat",
        json={},
        headers={"X-Request-ID": "x */ DROP TABLE messages; /*"},
    )
    rid = r.headers["X-Request-ID"]
    assert rid != "x */ DROP TABLE messages; /*"
    assert rid.isalnum()
