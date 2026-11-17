FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# PYTHONUNBUFFERED=1 -- ЛОГ: печатать сразу, без буфера, иначе строки появятся в docker logs с задержкой
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
