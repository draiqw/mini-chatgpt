"""ЛОГ: как пишутся логи. Все места в коде, где пишется лог, помечены «ЛОГ:» -- найти: grep -rn "ЛОГ" .

1. rid -- номер запроса. Его придумывает nginx ($request_id) и кладёт в заголовок X-Request-ID
   (infrastructure/nginx/nginx.conf). core/middleware.py достаёт его в request.state.rid.
2. Дальше rid едет вместе с запросом: в заголовке к llm (services/llm.py), аргументом в задачу Celery
   (worker/tasks.py) и комментарием /* rid=… */ в каждом SQL-запросе (core/db.py) -- его видно в логе Postgres.
3. Каждый переход между сервисами -- одна строка через hop():
       rid=… [nginx → api]  POST /chat
       rid=… [api → db]     INSERT INTO messages (2 мс)
       rid=… [api → llm]    POST /v1/chat/completions
       rid=… [llm → api]    первый токен через 1863 мс
       rid=… [api → nginx]  стрим закрыт: 48 токенов за 3.84 с
4. Пишем в stdout процесса. Docker собирает stdout каждого контейнера: `docker compose logs -f api`.
5. scripts/chat-trace <rid> берёт логи nginx, api, worker и db, оставляет строки с этим rid
   и сортирует по времени -- получается путь одного запроса через все сервисы.

Ради наглядности в лог попадает начало текста вопроса и ответа. В настоящем сервисе так не делают:
пишут только длины и id.
"""

import logging

log = logging.getLogger("chat")


def setup_logging() -> None:
    """ЛОГ: формат строки «12:39:03.310 INFO текст», вывод в stdout -> docker logs."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # свою строку доступа пишет middleware
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # запрос к llm пишет hop()


def hop(
    rid: str, src: str, dst: str, msg: str, *args, level: int = logging.INFO
) -> None:
    """ЛОГ: одна строка = один переход запроса между сервисами: rid=… [откуда → куда] что произошло."""
    log.log(level, f"rid=%s [%s → %s] {msg}", rid, src, dst, *args)


def short(text: str, n: int = 60) -> str:
    """Начало текста в одну строку -- чтобы длинное сообщение не растягивало лог."""
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"
