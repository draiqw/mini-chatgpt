"""Мини-ChatGPT: три ручки и история в базе.

POST /chat          -> поток токенов (SSE) от llm; вопрос и ответ сохраняются в Postgres
POST /finetune      -> 202 + job_id, задача уходит в очередь Redis, запись о задаче -- в Postgres
GET  /jobs/{job_id} -> статус задачи (из Redis)
GET  /history       -> последние сообщения (из Postgres)

Как устроено логирование (все места в коде помечены «ЛОГ:», найти: grep -rn "ЛОГ" .)

1. rid -- номер запроса. Его придумывает nginx ($request_id) и кладёт в заголовок
   X-Request-ID (nginx/nginx.conf). Middleware trace() ниже достаёт его в request.state.rid.
2. Дальше rid едет вместе с запросом: в заголовке к llm, аргументом в задачу Celery
   (worker.py) и комментарием /* rid=… */ в каждом SQL-запросе (его видно в логе Postgres).
3. Каждый переход между сервисами -- одна строка через hop():
       rid=… [nginx → api]  POST /chat
       rid=… [api → db]     INSERT INTO messages (2 мс)
       rid=… [api → llm]    POST /v1/chat/completions
       rid=… [llm → api]    первый токен через 1863 мс
       rid=… [api → nginx]  стрим закрыт: 48 токенов за 3.84 с
4. Пишем в stdout процесса. Docker собирает stdout каждого контейнера:
   `docker compose logs -f api` (локально), `chat-logs api` (на сервере).
5. `chat-trace <rid>` берёт логи nginx, api, worker и db, оставляет строки с этим rid
   и сортирует по времени -- получается путь одного запроса через все сервисы.

Внимание: ради наглядности в лог попадает начало текста вопроса и ответа.
В настоящем сервисе так не делают: пишут только длины и id.
"""
import json
import logging
import os
import socket
import time
from contextlib import asynccontextmanager

import httpx
from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from worker import celery, finetune as finetune_task

LLM_URL = os.environ.get("LLM_URL", "http://llm:8001")   # имя сервиса из compose, не localhost
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen3-1.7B-Q8_0.gguf")
SYSTEM_PROMPT = "Ты мини-ChatGPT с семинара по вебу. Отвечай по-русски, коротко и по делу."
DB_URL = os.environ.get("DATABASE_URL", "postgresql://chat:chat@db:5432/chat")
HOST = socket.gethostname()

# ЛОГ: настройка. Формат строки: «12:39:03.310 INFO текст», вывод в stdout -> docker logs.
logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("chat")
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)   # стандартную строку uvicorn глушим: свою пишет trace()
logging.getLogger("httpx").setLevel(logging.WARNING)             # httpx пишет каждый запрос к llm; у нас это делает hop()


# ЛОГ: главная функция. Одна строка = один переход запроса: rid=… [откуда → куда] что произошло.
# Через неё пишут все ручки; worker.py использует такую же.
def hop(rid: str, src: str, dst: str, msg: str, *args, level: int = logging.INFO) -> None:
    """Одна строка лога = один переход запроса между сервисами."""
    log.log(level, f"rid=%s [%s → %s] {msg}", rid, src, dst, *args)


def short(text: str, n: int = 60) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         bigserial PRIMARY KEY,
    rid        text,
    role       text NOT NULL,          -- user | assistant
    content    text NOT NULL,
    tokens     int,
    latency_ms int,                    -- для ответа: время до первого токена
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
    id          text PRIMARY KEY,
    rid         text,
    dataset     text,
    epochs      int,
    state       text,
    loss        real,
    adapter     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # пул соединений с Postgres: открываем один раз при старте, а не на каждый запрос
    app.state.db = AsyncConnectionPool(DB_URL, min_size=1, max_size=5, open=False)
    await app.state.db.open(wait=True, timeout=30)
    async with app.state.db.connection() as conn:
        await conn.execute(SCHEMA)
    log.info("[api → db] схема готова: %s", DB_URL.rsplit("@", 1)[-1])   # ЛОГ: старт, адрес базы без пароля
    yield
    await app.state.db.close()


app = FastAPI(title="mini-chatgpt", lifespan=lifespan)


# ЛОГ: запись в базу. rid уходит комментарием в сам SQL: Postgres пишет запрос в свой лог
# (log_statement=mod в compose.yaml), и chat-trace находит его там по rid. Плюс строка [api → db] со временем.
async def db_exec(rid: str, sql: str, params: tuple) -> None:
    t0 = time.perf_counter()
    async with app.state.db.connection() as conn:
        await conn.execute(f"/* rid={rid} */ {sql}", params)
    hop(rid, "api", "db", "%s (%.0f мс)", sql.split("(")[0].strip(), (time.perf_counter() - t0) * 1000)


# ЛОГ: middleware -- обёртка вокруг каждого запроса. Пишет вход [nginx → api] и выход [api → nginx]
# с кодом и временем, кладёт rid в request.state и возвращает его клиенту в заголовке X-Request-ID.
@app.middleware("http")
async def trace(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", "-")
    request.state.rid = rid
    t0 = time.perf_counter()
    client = request.headers.get("X-Real-IP") or (request.client.host if request.client else "-")
    quiet = request.url.path == "/health"   # health дёргают часто, в лог не пишем
    if not quiet:
        hop(rid, "nginx", "api", "%s %s клиент=%s ua=%r", request.method, request.url.path, client,
            short(request.headers.get("user-agent", "-"), 40))
    try:
        response = await call_next(request)
    except Exception:
        log.exception("rid=%s [api] необработанное исключение", rid)   # ЛОГ: 500 с полным трейсбеком
        raise
    response.headers["X-Request-ID"] = rid
    response.headers["X-Served-By"] = HOST
    if not quiet:
        # для /chat это время до заголовков; конец потока пишет сама ручка
        hop(rid, "api", "nginx", "%s за %.0f мс", response.status_code, (time.perf_counter() - t0) * 1000)
    return response


# ЛОГ: 422. FastAPI отвечает на кривой JSON сам; здесь дописываем в лог, какое поле не прошло проверку.
@app.exception_handler(RequestValidationError)
async def on_422(request: Request, exc: RequestValidationError):
    errs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    hop(getattr(request.state, "rid", "-"), "api", "api", "422 pydantic: %s", errs, level=logging.WARNING)
    return await request_validation_exception_handler(request, exc)


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)   # ~10k токенов: контекст слота 12k


class FinetuneRequest(BaseModel):
    dataset: str = Field(min_length=1, max_length=10_000)
    epochs: int = Field(default=3, ge=1, le=5)


@app.get("/health")
async def health():
    # заодно проверяем соседей: модель грузится в память несколько секунд после старта
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            llm = (await c.get(f"{LLM_URL}/health")).json().get("status", "?")
    except (httpx.HTTPError, ValueError) as e:
        llm = f"недоступна: {type(e).__name__}"
    try:
        async with app.state.db.connection() as conn:
            await conn.execute("SELECT 1")
        db = "ok"
    except Exception as e:  # noqa: BLE001 -- для health любая ошибка базы = «не ok»
        db = f"недоступна: {type(e).__name__}"
    return {"ok": True, "host": HOST, "model": LLM_MODEL, "llm": llm, "db": db}


@app.post("/chat")
async def chat(msg: Message, request: Request):
    rid = request.state.rid
    hop(rid, "api", "api", "chat: сообщение %d симв. %r", len(msg.message), short(msg.message))   # ЛОГ: что спросили
    await db_exec(rid, "INSERT INTO messages (rid, role, content) VALUES (%s, 'user', %s)", (rid, msg.message))

    payload = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": msg.message}],
        "stream": True,
        "max_tokens": 512,
        "temperature": 0.7,
        "chat_template_kwargs": {"enable_thinking": False},   # Qwen3: без режима рассуждений, сразу ответ
    }

    # api сам становится клиентом: HTTP-запрос к соседнему контейнеру llm.
    # Если модель не готова, честно отвечаем 503, а не пустым потоком.
    client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5))
    t0 = time.perf_counter()
    hop(rid, "api", "llm", "POST %s/v1/chat/completions model=%s stream=true", LLM_URL, LLM_MODEL)   # ЛОГ: ушли в модель
    # rid едет и к модели в заголовке X-Request-ID
    try:
        r = await client.send(client.build_request("POST", f"{LLM_URL}/v1/chat/completions", json=payload,
                                                   headers={"X-Request-ID": rid}), stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        hop(rid, "api", "llm", "не достучались: %s %s", type(e).__name__, e, level=logging.ERROR)   # ЛОГ: -> 503
        raise HTTPException(503, f"llm недоступна: {type(e).__name__}")
    if r.status_code != 200:
        detail = (await r.aread()).decode(errors="replace")[:200]
        await r.aclose()
        await client.aclose()
        hop(rid, "llm", "api", "%s: %s", r.status_code, detail, level=logging.ERROR)   # ЛОГ: модель вернула ошибку
        # 400 от модели -- ошибка в запросе (например, не влез в контекст 12k): так и передаём клиенту
        raise HTTPException(400 if r.status_code == 400 else 503, f"llm ответила {r.status_code}: {detail}")
    hop(rid, "llm", "api", "200 за %.0f мс, заголовки получены, ждём токены", (time.perf_counter() - t0) * 1000)   # ЛОГ

    async def tokens():
        n, first, answer = 0, None, ""
        try:
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):].strip()
                if data == "[DONE]":
                    break
                choices = json.loads(data).get("choices") or []
                token = choices[0].get("delta", {}).get("content") if choices else None
                if token:
                    n += 1
                    answer += token
                    if first is None:   # ЛОГ: только первый токен, чтобы не писать строку на каждый
                        first = time.perf_counter()
                        hop(rid, "llm", "api", "первый токен через %.0f мс", (first - t0) * 1000)
                        hop(rid, "api", "nginx", "стрим SSE открыт, токены идут по одному")
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            total = time.perf_counter() - t0
            speed = n / (total - (first - t0)) if first and total > first - t0 else 0
            # ЛОГ: итог стрима: сколько токенов, за сколько, скорость, начало ответа
            hop(rid, "api", "nginx", "стрим закрыт: %d токенов за %.2f с (%.1f ток/с), ответ %r",
                n, total, speed, short(answer, 80))
            await db_exec(rid, "INSERT INTO messages (rid, role, content, tokens, latency_ms) "
                               "VALUES (%s, 'assistant', %s, %s, %s)",
                          (rid, answer, n, int((first - t0) * 1000) if first else None))
        except Exception:
            log.exception("rid=%s [llm → api] стрим оборвался после %d токенов", rid, n)   # ЛОГ: обрыв на середине
            raise
        finally:
            await r.aclose()
            await client.aclose()

    return StreamingResponse(tokens(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/finetune", status_code=202)
async def finetune(req: FinetuneRequest, request: Request):
    rid = request.state.rid
    job = finetune_task.delay(req.dataset, req.epochs, rid)   # rid уходит в задачу: worker пишет его в свои логи
    # ЛОГ: задача в очереди
    hop(rid, "api", "redis", "задача %s в очереди celery, epochs=%d, датасет %d симв.",
        job.id, req.epochs, len(req.dataset))
    await db_exec(rid, "INSERT INTO jobs (id, rid, dataset, epochs, state) VALUES (%s, %s, %s, %s, 'PENDING') "
                       "ON CONFLICT (id) DO NOTHING",
                  (job.id, rid, req.dataset[:2000], req.epochs))
    return {"job_id": job.id}


@app.get("/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    r = AsyncResult(job_id, app=celery)
    hop(request.state.rid, "redis", "api", "статус %s: %s %s", job_id[:8], r.state,   # ЛОГ: каждый опрос статуса
        r.info if r.state == "PROGRESS" else "")
    out = {"job_id": job_id, "state": r.state}
    if r.state == "PROGRESS":
        out.update(r.info)
    elif r.state == "SUCCESS":
        out.update(r.result)
    elif r.state == "FAILURE":
        out["error"] = str(r.result)
    return out


@app.get("/history")
async def history(request: Request, limit: int = 20):
    t0 = time.perf_counter()
    async with app.state.db.connection() as conn:
        cur = await conn.execute(
            "SELECT role, content, tokens, latency_ms, created_at FROM messages ORDER BY id DESC LIMIT %s",
            (min(limit, 100),))
        rows = await cur.fetchall()
    # ЛОГ: чтение истории
    hop(request.state.rid, "db", "api", "SELECT messages: %d строк (%.0f мс)", len(rows), (time.perf_counter() - t0) * 1000)
    return [{"role": r[0], "content": r[1], "tokens": r[2], "latency_ms": r[3], "at": r[4].isoformat()}
            for r in reversed(rows)]
