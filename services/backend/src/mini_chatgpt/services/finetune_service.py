"""Дообучение через очередь: api только ставит задачу, выполняет её отдельный процесс worker (worker/tasks.py).

Если учить прямо в ручке, запрос висел бы всё обучение, nginx вернул бы 504, а процесс api был бы занят.
"""

from celery.result import AsyncResult

from mini_chatgpt.core import db
from mini_chatgpt.core.logs import hop
from mini_chatgpt.worker.celery_app import celery
from mini_chatgpt.worker.tasks import finetune


async def enqueue(
    rid: str,
    dataset: str,
    epochs: int,
) -> str:
    # сообщение в Redis; rid уходит в задачу для логов worker
    job = finetune.delay(
        dataset,
        epochs,
        rid,
    )
    hop(
        rid,
        "api",
        "redis",
        "задача %s в очереди celery, epochs=%d, датасет %d симв.",  # ЛОГ: задача в очереди
        job.id,
        epochs,
        len(dataset),
    )
    await db.execute(
        rid=rid,
        sql="INSERT INTO jobs (id, rid, dataset, epochs, state) VALUES (%s, %s, %s, %s, 'PENDING') "
        "ON CONFLICT (id) DO NOTHING",
        params=(job.id, rid, dataset[:2000], epochs),
    )
    return job.id


def status(
    rid: str,
    job_id: str,
) -> dict:
    """Статус из Redis: туда его пишет worker через update_state."""
    r = AsyncResult(
        job_id,
        app=celery,
    )
    info = r.info if r.state == "PROGRESS" else ""
    # ЛОГ: каждый опрос (polling)
    hop(
        rid,
        "redis",
        "api",
        "статус %s: %s %s",
        job_id[:8],
        r.state,
        info,
    )
    out = {"job_id": job_id, "state": r.state}
    if r.state == "PROGRESS":
        out |= r.info
    elif r.state == "SUCCESS":
        out |= r.result
    elif r.state == "FAILURE":
        out["error"] = str(r.result)
    return out
