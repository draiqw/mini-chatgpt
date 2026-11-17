# Образ бэкенда: из него запускаются и api (uvicorn), и worker (celery) -- см. docker-compose.yml.
# Контекст сборки -- корень репозитория (context: ../.. в compose), поэтому пути ниже от корня.
FROM python:3.12-slim
WORKDIR /app
# PYTHONUNBUFFERED=1 -- ЛОГ: печатать сразу, без буфера, иначе строки появятся в docker logs с задержкой
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# сначала зависимости, потом код: при правке кода слой с библиотеками берётся из кэша
COPY services/backend/pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
      > requirements.txt && pip install --no-cache-dir -r requirements.txt
COPY services/backend/src ./src
RUN pip install --no-cache-dir --no-deps .

# --root-path /api: снаружи api живёт под /api/ (nginx отрезает префикс), документация -- /api/docs
CMD ["uvicorn", "mini_chatgpt.main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/api"]
