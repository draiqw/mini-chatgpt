"""Postgres: пул соединений, схема таблиц и запросы с rid в логах."""

import time

from psycopg_pool import AsyncConnectionPool

from mini_chatgpt.core import config
from mini_chatgpt.core.logs import hop, log

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

# Пул открывается один раз при старте api (main.py), а не на каждый запрос: подключение к базе дорогое.
pool = AsyncConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,
)


async def open_pool() -> None:
    await pool.open(
        wait=True,
        timeout=30,
    )
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)
    # ЛОГ: адрес базы без пароля
    log.info("[api → db] схема готова: %s", config.DATABASE_URL.rsplit("@", 1)[-1])


async def close_pool() -> None:
    await pool.close()


async def execute(
    rid: str,
    sql: str,
    params: tuple,
) -> None:
    """INSERT/UPDATE. Значения -- параметрами %s, а не вклеиваются в строку: так не будет SQL-инъекции.

    ЛОГ: rid уходит комментарием в сам SQL. Postgres пишет запрос в свой лог (log_statement=mod в compose),
    и chat-trace находит его там по rid. Плюс строка [api → db] со временем.
    """
    t0 = time.perf_counter()
    async with pool.connection() as conn:
        await conn.execute(f"/* rid={rid} */ {sql}", params)
    hop(
        rid,
        "api",
        "db",
        "%s (%.0f мс)",
        sql.split("(")[0].strip(),
        (time.perf_counter() - t0) * 1000,
    )


async def fetch(
    rid: str,
    what: str,
    sql: str,
    params: tuple,
) -> list[tuple]:
    """SELECT. what -- короткое имя запроса для лога. ЛОГ: сколько строк и за сколько."""
    t0 = time.perf_counter()
    async with pool.connection() as conn:
        rows = await (await conn.execute(f"/* rid={rid} */ {sql}", params)).fetchall()
    hop(
        rid,
        "db",
        "api",
        "%s: %d строк (%.0f мс)",
        what,
        len(rows),
        (time.perf_counter() - t0) * 1000,
    )
    return rows


async def ping() -> None:
    async with pool.connection() as conn:
        await conn.execute("SELECT 1")
