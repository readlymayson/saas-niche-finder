# Деплой SaaS Niche Finder (личный инструмент)

Ориентир: Ubuntu 22.04+, Docker 24+, 2 vCPU / 4 GB RAM.

## 1. Сервер

1. Создайте VPS (например Hetzner CX22).
2. Установите Docker и compose plugin.
3. Клонируйте репозиторий в `/opt/saas-niche-finder`.

## 2. Секреты

Скопируйте `.env.example` → `.env` на сервере и задайте:

- `DATABASE_URL`, `REDIS_URL`
- `API_TOKEN` — единственный токен доступа к API (сгенерируйте `openssl rand -hex 32`)
- `TELEGRAM_*` (если live-парсинг)
- `YANDEX_*` (Вордстат / YandexGPT)

> API не публикуется наружу: порт 8000 слушается внутри docker-сети
> (или пробрасывается только на localhost сервера).

## 3. ML-артефакт

На машине с GPU или локально:

```bash
docker compose --profile ml run --rm ml-train
python backend/ml/check_artifact_metrics.py --min-accuracy 0.85
```

Скопируйте `backend/ml/artifacts/rubert-pain-cls` на сервер (каталог в `.gitignore`).

## 4. Запуск стека

```bash
docker compose up -d postgres redis api worker beat
```

Миграция из старого DaaS-режима (только если БД уже существовала):

```bash
docker compose exec -T postgres psql -U postgres -d niche_finder \
  < backend/scripts/migrate_drop_users.sql
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
curl -s -H "X-Api-Token: $API_TOKEN" http://127.0.0.1:8000/v1/niches/top?limit=5
# без токена → 401
```

## 5. Нагрузочное тестирование

```bash
pip install locust
locust -f locustfile.py --host http://127.0.0.1:8000
```

## 6. Бэкапы

- Ежедневный `pg_dump` PostgreSQL (эмбеддинги pgvector входят в дамп)
