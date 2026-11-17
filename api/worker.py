"""Celery-воркер: дообучение в фоне.

ДЕМО: настоящего обучения здесь нет. Дообучение 2B-модели на CPU шло бы часами,
поэтому задача имитирует эпохи и шаги (sleep + падающий loss). Всё остальное
настоящее: очередь в Redis, отдельный процесс, статус через update_state,
том для весов и итоговая запись в Postgres.

Логи в том же формате, что у api: rid=… [откуда → куда] что произошло.
"""
import json
import logging
import os
import time

import psycopg
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://chat:chat@db:5432/chat")
celery = Celery("chat", broker=REDIS_URL, backend=REDIS_URL)
log = logging.getLogger("worker")   # формат задаёт celery: время, уровень, процесс


def hop(rid: str, src: str, dst: str, msg: str, *args) -> None:
    log.info(f"rid=%s [%s → %s] {msg}", rid, src, dst, *args)


@celery.task(bind=True)
def finetune(self, dataset: str, epochs: int = 3, request_id: str = "-"):
    rid, job = request_id, self.request.id
    hop(rid, "redis", "worker", "взял задачу %s: epochs=%d, датасет %r", job, epochs, dataset[:40])
    steps, loss = 10, 2.5
    for epoch in range(1, epochs + 1):
        for step in range(1, steps + 1):
            time.sleep(0.5)
            loss *= 0.982
            self.update_state(state="PROGRESS", meta={
                "epoch": epoch, "epochs": epochs, "step": step, "steps": steps, "loss": round(loss, 3)})
            hop(rid, "worker", "redis", "прогресс %s: epoch %d/%d step %d/%d loss=%.3f",
                job[:8], epoch, epochs, step, steps, loss)
    adapter = f"lora-{job[:8]}"
    os.makedirs("/weights", exist_ok=True)
    with open(f"/weights/{adapter}.json", "w") as f:
        json.dump({"base": os.environ.get("LLM_MODEL", "?"), "dataset": dataset[:200], "loss": round(loss, 3)}, f)
    hop(rid, "worker", "volume", "веса /weights/%s.json", adapter)
    with psycopg.connect(DB_URL) as conn:
        conn.execute(f"/* rid={rid} */ UPDATE jobs SET state = 'SUCCESS', loss = %s, adapter = %s, "
                     "finished_at = now() WHERE id = %s", (round(loss, 3), adapter, job))
    hop(rid, "worker", "db", "UPDATE jobs %s: SUCCESS", job[:8])
    hop(rid, "worker", "redis", "результат %s: SUCCESS, loss=%.3f", job[:8], loss)
    return {"epochs": epochs, "loss": round(loss, 3), "adapter": adapter}
