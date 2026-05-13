# Образ для обучения RuBERT и эмбеддингов (CPU). API/worker остаются на slim-образе без torch.
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app ./app
COPY ml ./ml
COPY celery_app.py .

RUN pip install --no-cache-dir pip setuptools wheel \
    && pip install --no-cache-dir ".[ml]"

ENV PYTHONUNBUFFERED=1

# По умолчанию — обучение классификатора; переопределите command при необходимости.
CMD ["python", "-m", "ml.train_classifier"]
