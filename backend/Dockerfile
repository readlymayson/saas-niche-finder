FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим зависимости (кэшируется: повторная сборка не качает torch/CUDA)
COPY pyproject.toml .
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir pip setuptools wheel \
    && pip install --no-cache-dir .

# Теперь код — перезаписывает минимальный пакет из шага выше
COPY app ./app
COPY ml ./ml
COPY celery_app.py .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
