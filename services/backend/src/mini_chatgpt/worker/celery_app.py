"""Приложение Celery. Redis здесь и очередь (broker), и хранилище статусов задач (backend).

Запуск воркера (compose, сервис worker): celery -A mini_chatgpt.worker.celery_app worker --loglevel=info
ЛОГ: Celery сам пишет в stdout время, уровень и процесс; --loglevel=info -- видно каждую задачу.
"""

from celery import Celery

from mini_chatgpt.core import config

celery = Celery("chat", broker=config.REDIS_URL, backend=config.REDIS_URL, include=["mini_chatgpt.worker.tasks"])
