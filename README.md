# mini-chatgpt

Учебный сервис для семинара «Основы веба» (практикум по Python, ММП ВМК МГУ): чат с локальной LLM, стриминг ответа, дообучение в фоне, история в базе и логи, по которым виден путь каждого запроса.

Стенд: https://chat.myocto.ru (и по IP: http://147.45.146.134). Теория по этому коду: [`docs/theory.pdf`](docs/theory.pdf).

```
браузер → nginx ─ /      → frontend (статика)
                └ /api/  → api (FastAPI) ─→ llm (llama.cpp, Qwen3-1.7B, контекст 12k)
                                         ├→ redis → worker (Celery, дообучение)
                                         └→ db (Postgres: история и задачи)
```

## Ручки

| Метод и путь | Что делает | Ответ |
|---|---|---|
| `POST /api/chat` `{"message": "ты кто?"}` | спрашивает модель | `200`, поток SSE: `data: {"token": "Я"}` … `data: [DONE]` |
| `POST /api/finetune` `{"dataset": "...", "epochs": 3}` | ставит задачу в очередь | `202` `{"job_id": "..."}` |
| `GET /api/jobs/{id}` | статус задачи | `{"state": "PROGRESS", "epoch": 1, "loss": 2.3, ...}` |
| `GET /api/history?limit=20` | последние сообщения из базы | список `{role, content, tokens, latency_ms, at}` |
| `GET /api/health` | состояние api, модели и базы | `{"llm": "ok", "db": "ok", ...}` |

Все ручки с их схемами и кнопкой «попробовать» — на странице `/api/docs` (Swagger, его строит FastAPI).

Дообучение имитируется: воркер проходит эпохи и пишет падающий loss, но веса модели не меняет. Дообучение модели на CPU шло бы часами. Очередь, воркер, статусы и записи в базе настоящие.

## Устройство репозитория

```
services/
  backend/                     FastAPI + Celery, один пакет и один образ
    src/mini_chatgpt/
      main.py                  приложение: middleware, обработчики ошибок, ручки, база при старте
      api/v1/                  ручки: принять схему, вызвать сервис, вернуть ответ
        chat.py  finetune.py  history.py  health.py
      api/deps.py, errors.py   rid для ручек; ошибки -> HTTP-коды (422, 503, 400)
      schemas/                 что ручки принимают и возвращают (pydantic)
      services/                логика: chat_service, finetune_service, history_service, health_service, llm
      core/                    config, logs (hop), middleware (вход/выход запроса), db (пул, схема, SQL с rid)
      worker/                  celery_app, tasks (дообучение)
    tests/                     проверки без модели и базы: 422, 404, 405, схемы
    pyproject.toml
  frontend/index.html          страница чата: поток через fetch, polling статуса, история
infrastructure/
  docker-compose/              docker-compose.yml (все сервисы), docker-compose.https.yml (домен и сертификат)
  docker/backend/Dockerfile
  nginx/                       nginx.conf (http, лог), app.conf (маршруты), https.conf.template (TLS)
scripts/                       download-model, chat-logs, chat-trace, issue-cert
docs/theory.pdf
compose.yaml                   точка входа: `docker compose` из корня
```

Код удобно читать по пути запроса: `infrastructure/nginx` → `main.py` → `api/v1/chat.py` → `services/chat_service.py` → `services/llm.py` → `worker/tasks.py` → `services/frontend/index.html`.

## Запуск локально

Нужен Docker и около 4 ГБ на диске.

```bash
cp .env.example .env            # поменять пароль, PORT=8090
scripts/download-model          # Qwen3-1.7B, 1,8 ГБ
docker compose up -d --build
open http://localhost:8090
```

```bash
curl -N -X POST localhost:8090/api/chat -H 'Content-Type: application/json' -d '{"message": "ты кто?"}'
curl localhost:8090/api/health
```

Тесты и линт бэкенда: `cd services/backend && uv run --group dev pytest && uv run --group dev ruff check .`

## Выкладка на сервер

```bash
rsync -a --delete --exclude models --exclude .env --exclude .git ./ server:/opt/mini-chatgpt/
ssh server 'cd /opt/mini-chatgpt && cp -n .env.example .env && scripts/download-model \
            && install -m 755 scripts/chat-logs scripts/chat-trace /usr/local/bin/ && docker compose up -d --build'
```

HTTPS с доменом:

1. A-запись домена указывает на сервер (у стенда: `chat.myocto.ru` → `147.45.146.134`, DNS в Timeweb).
2. В `.env` на сервере: `DOMAIN=chat.myocto.ru`.
3. `scripts/issue-cert` — выдаёт сертификат Let's Encrypt, включает `docker-compose.https.yml` (порт 443, редирект с http) и ставит продление в cron.

Снаружи слушают только порты nginx: `ssh server ss -tlnp`.

## Логи

Каждая строка лога — один переход запроса между сервисами, с `rid` (это `X-Request-ID`, его выдаёт nginx). Все места в коде, где пишется лог, помечены `ЛОГ:` — `grep -rn "ЛОГ" .`, общая схема — в `services/backend/src/mini_chatgpt/core/logs.py`.

```
nginx  rid=… [195.170.198.93 → nginx → 172.18.0.7:8000] "POST /api/chat" 200 connect=0.001 header=0.035 total=0.9
api    rid=… [nginx → api] POST /chat клиент=195.170.198.93
api    rid=… [api → db] INSERT INTO messages (7 мс)
api    rid=… [api → llm] POST http://llm:8001/v1/chat/completions stream=true
api    rid=… [llm → api] первый токен через 294 мс
api    rid=… [api → nginx] стрим закрыт: 15 токенов за 0.88 с (25.7 ток/с)
db     … LOG: execute: /* rid=… */ INSERT INTO messages …
worker rid=… [redis → worker] взял задачу …
worker rid=… [worker → db] UPDATE jobs …: SUCCESS
```

| Где | Что пишет |
|---|---|
| `infrastructure/nginx/nginx.conf`, `log_format trace` | строку на запрос; придумывает `rid` и передаёт его в api заголовком `X-Request-ID` |
| `core/logs.py`, `hop()` | строку на каждый переход `[откуда → куда]` |
| `core/middleware.py` | вход и выход каждого запроса с кодом и временем |
| `core/db.py` | SQL с комментарием `/* rid=… */`: Postgres пишет его в свой лог (`log_statement=mod`) |
| `worker/tasks.py` | шаги задачи; `rid` приходит аргументом задачи |
| `scripts/chat-trace` | собирает строки с одним `rid` из всех контейнеров и сортирует по времени |

```bash
chat-logs                 # все сервисы в реальном времени (на сервере)
chat-logs api llm         # только выбранные
chat-trace <rid>          # путь одного запроса; rid показан в чате под ответом
docker compose logs -f    # то же локально
```

Ради наглядности в лог попадает начало текста вопроса и ответа, а `/api/history` отдаёт сообщения всех пользователей. Для учебного стенда это осознанно, в настоящем сервисе так не делают.
