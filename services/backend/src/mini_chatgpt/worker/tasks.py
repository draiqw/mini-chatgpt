"""Задача дообучения. Выполняется в отдельном процессе worker, не в api.

ДЕМО: настоящего обучения здесь нет. Дообучение 2B-модели на CPU шло бы часами, поэтому задача
имитирует эпохи и шаги (sleep + падающий loss). Всё остальное настоящее: очередь в Redis,
отдельный процесс, статус через update_state, том для весов и итоговая запись в Postgres.
"""

import json
import logging
import os
import time

import psycopg

from mini_chatgpt.core import config
from mini_chatgpt.worker.celery_app import celery

log = logging.getLogger("worker")
STEPS = 10  # шагов в эпохе


def hop(rid: str, src: str, dst: str, msg: str, *args) -> None:
    """ЛОГ: та же строка, что в api: rid=… [откуда → куда] что произошло. Пишем через логгер Celery."""
    log.info(f"rid=%s [%s → %s] {msg}", rid, src, dst, *args)


@celery.task(bind=True)
def finetune(self, dataset: str, epochs: int = 3, request_id: str = "-"):
    rid, job = request_id, self.request.id  # rid передал api в finetune.delay(...)
    hop(
        rid,
        "redis",
        "worker",
        "взял задачу %s: epochs=%d, датасет %r",
        job,
        epochs,
        dataset[:40],
    )
    loss = 2.5
    for epoch in range(1, epochs + 1):
        for step in range(1, STEPS + 1):
            time.sleep(0.5)  # «шаг обучения»
            loss *= 0.982
            # прогресс -> Redis; оттуда его читает GET /jobs/{id}
            self.update_state(
                state="PROGRESS",
                meta={
                    "epoch": epoch,
                    "epochs": epochs,
                    "step": step,
                    "steps": STEPS,
                    "loss": round(loss, 3),
                },
            )
            # ЛОГ: строка на каждый шаг -- видно, как идёт обучение
            hop(
                rid,
                "worker",
                "redis",
                "прогресс %s: epoch %d/%d step %d/%d loss=%.3f",
                job[:8],
                epoch,
                epochs,
                step,
                STEPS,
                loss,
            )

    adapter = f"lora-{job[:8]}"
    # том weights из compose: переживает перезапуск контейнера
    os.makedirs("/weights", exist_ok=True)
    with open(f"/weights/{adapter}.json", "w") as f:
        json.dump(
            {
                "base": config.LLM_MODEL,
                "dataset": dataset[:200],
                "loss": round(loss, 3),
            },
            f,
        )
    hop(rid, "worker", "volume", "веса /weights/%s.json", adapter)

    with psycopg.connect(config.DATABASE_URL) as conn:
        # ЛОГ: rid в комментарии SQL, как в api: запрос попадёт в лог Postgres с этим rid
        conn.execute(
            f"/* rid={rid} */ UPDATE jobs SET state = 'SUCCESS', loss = %s, adapter = %s, "
            "finished_at = now() WHERE id = %s",
            (round(loss, 3), adapter, job),
        )
    hop(rid, "worker", "db", "UPDATE jobs %s: SUCCESS", job[:8])
    hop(rid, "worker", "redis", "результат %s: SUCCESS, loss=%.3f", job[:8], loss)
    return {"epochs": epochs, "loss": round(loss, 3), "adapter": adapter}
