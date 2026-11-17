"""Мини-ChatGPT: бэкенд семинара «Основы веба».

Устройство пакета (путь запроса сверху вниз):

    main.py           приложение FastAPI: подключает middleware и ручки, открывает базу при старте
    core/config.py    настройки из переменных окружения
    core/logs.py      ЛОГ: формат строк и hop() -- одна строка на переход «откуда → куда»
    core/middleware.py ЛОГ: вход и выход каждого запроса, rid
    core/db.py        пул соединений с Postgres, схема таблиц, запросы с rid
    api/v1/           ручки: только принять схему, вызвать сервис, вернуть ответ
    api/deps.py       rid для ручек; api/errors.py -- ошибки -> HTTP-коды (422, 503, 400)
    schemas/          что ручки принимают и возвращают (pydantic)
    services/         логика: chat_service, finetune_service, history_service, health_service;
                      llm.py -- клиент к модели: открыть поток и разобрать токены
    worker/           Celery: приложение и задача дообучения (отдельный процесс worker)
"""
