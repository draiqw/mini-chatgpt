# mini-chatgpt

Учебный сервис для семинара «Основы веба» (практикум по Python, ММП ВМК МГУ): чат с локальной LLM, стриминг ответа, дообучение в фоне, история в базе и логи, по которым виден путь каждого запроса.

```
браузер → nginx ─ /      → frontend (статика)
                └ /api/  → api (FastAPI) ─→ llm (llama.cpp, Qwen3-1.7B, контекст 12k)
                                         ├→ redis → worker (Celery, дообучение)
                                         └→ db (Postgres: история и задачи)
```

Теория к семинару по этому коду: [`docs/theory.pdf`](docs/theory.pdf). Код удобно читать по пути запроса: `compose.yaml` → `nginx/nginx.conf` → `api/app.py` → `api/worker.py` → `frontend/index.html`.

## Ручки

| Метод и путь | Что делает | Ответ |
|---|---|---|
| `POST /api/chat` `{"message": "ты кто?"}` | спрашивает модель | `200`, поток SSE: `data: {"token": "Я"}` … `data: [DONE]` |
| `POST /api/finetune` `{"dataset": "...", "epochs": 3}` | ставит задачу в очередь | `202` `{"job_id": "..."}` |
| `GET /api/jobs/{id}` | статус задачи | `{"state": "PROGRESS", "epoch": 1, "loss": 2.3, ...}` |
| `GET /api/history?limit=20` | последние сообщения из базы | список `{role, content, tokens, latency_ms, at}` |
| `GET /api/health` | состояние api, модели и базы | `{"llm": "ok", "db": "ok", ...}` |

Дообучение имитируется: воркер проходит эпохи и пишет падающий loss, но веса модели не меняет. Дообучение модели на CPU шло бы часами. Очередь, воркер, статусы и записи в базе настоящие.

## Запуск локально

Нужен Docker и около 4 ГБ на диске.

```bash
cp .env.example .env            # поменять пароль, PORT=8090
bin/download-model              # Qwen3-1.7B, 1,8 ГБ
docker compose up -d --build
open http://localhost:8090
```

Проверка из терминала:

```bash
curl -N -X POST localhost:8090/api/chat -H 'Content-Type: application/json' -d '{"message": "ты кто?"}'
curl localhost:8090/api/health
```

## Выкладка на сервер

```bash
rsync -a --exclude models --exclude .env ./ server:/opt/mini-chatgpt/
ssh server 'cd /opt/mini-chatgpt && cp -n .env.example .env && bin/download-model \
            && install -m 755 bin/chat-logs bin/chat-trace /usr/local/bin/ && docker compose up -d --build'
```

Снаружи должен слушать только порт nginx: `ssh server ss -tlnp`.

## Логи

Каждая строка лога — один переход запроса между сервисами, с `rid` (это `X-Request-ID`, его выдаёт nginx):

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

Как это сделано (все места в коде помечены `ЛОГ:`, найти: `grep -rn "ЛОГ" .`):

| Где | Что пишет |
|---|---|
| `nginx/nginx.conf`, `log_format trace` | строку на запрос; придумывает `rid` и передаёт его в api заголовком `X-Request-ID` |
| `api/app.py`, `hop()` | строку на каждый переход `[откуда → куда]`; `trace()` — вход и выход запроса, `db_exec()` — запись в базу |
| `api/worker.py`, `hop()` | то же для задач Celery; `rid` приходит аргументом задачи |
| `compose.yaml`, db | Postgres пишет каждый INSERT/UPDATE с комментарием `/* rid=… */` (`log_statement=mod`) |
| `compose.yaml`, llm и redis | llama.cpp — скорость по каждому запросу, Redis — подключения |
| `bin/chat-trace` | собирает строки с одним `rid` из всех контейнеров и сортирует по времени |

Все сервисы пишут в stdout, Docker собирает его: `docker compose logs`. Ради наглядности в лог попадает начало текста вопроса и ответа. В настоящем сервисе так не делают: пишут только длины и id.

```bash
chat-logs                 # все сервисы в реальном времени (на сервере)
chat-logs api llm         # только выбранные
chat-trace <rid>          # путь одного запроса по времени; rid показан в чате под ответом
docker compose logs -f    # то же локально
```

Модель пишет свою статистику по каждому запросу: `chat-logs llm` → `prompt eval time`, `eval time … tokens per second`.

## Устройство

| Файл | Что внутри |
|---|---|
| `compose.yaml` | шесть сервисов, сеть, тома, проверки готовности |
| `nginx/nginx.conf` | маршруты, `X-Request-ID`, лимит запросов к чату, стрим без буфера, формат лога |
| `api/app.py` | FastAPI: ручки, проксирование потока из модели, запись в базу, логи переходов |
| `api/worker.py` | Celery-задача дообучения: прогресс в Redis, итог в Postgres |
| `frontend/index.html` | страница чата: чтение потока через `fetch`, опрос статуса задачи, история |
| `bin/` | `download-model`, `chat-logs`, `chat-trace` |
| `docs/theory.pdf` | теория семинара: путь запроса по шагам со схемами и кодом отсюда |
