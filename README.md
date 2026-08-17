# SaaS Niche Finder — личный инструмент

Приватная «машина» поиска B2B-ниш: парсинг VC.ru и Telegram, ML-скоринг
(RuBERT + pgvector), Яндекс.Вордстат и YandexGPT. Без публичного
DaaS-слоя: нет биллинга, тарифов, подписок, API-ключей и регистрации.

## Архитектура

- **Backend** (FastAPI, async) — `backend/app/`
  - API: `/v1/*` (поиск, топ, детали, similar, export) + `/internal/*` (feedback, entities)
  - Единый статический токен в заголовке `X-Api-Token` (или `Authorization: Bearer`)
  - ETL-пайплайн: парсеры VC.ru/Telegram → ML (RuBERT pain-классификатор) → агрегация ниш
  - Celery worker + beat (см. `backend/celery_app.py`)
- **PostgreSQL** + pgvector (эмбеддинги 768-d) + **Redis** (Celery broker)
- Фронтенд удалён — только API

## Быстрый старт

### 1. Переменные окружения

```bash
cp .env.example .env   # заполните API_TOKEN и секреты (Telegram, Яндекс)
```

### 2. База и Redis

```bash
docker compose up -d postgres redis
```

### 3. Миграция (только для существующей БД)

Если БД уже была создана в «DaaS»-режиме — удалить старые таблицы
users/api_keys и колонку feedback.user_id (эмбеддинги ниш сохраняются):

```bash
docker compose exec -T postgres psql -U postgres -d niche_finder \
  < backend/scripts/migrate_drop_users.sql
```

### 4. API

```bash
cd backend
uvicorn app.main:app --reload
# http://localhost:8000/docs  (Swagger)
```

Проверка:

```bash
curl -H "X-Api-Token: $API_TOKEN" http://localhost:8000/v1/niches/top?limit=5
# без токена → 401
curl http://localhost:8000/v1/niches/top
```

### 5. Celery (парсинг + ML-пайплайн)

```bash
cd backend
celery -A celery_app worker --loglevel=info
celery -A celery_app beat --loglevel=info
```

или всё сразу:

```bash
docker compose up --build
```

## API

Все эндпоинты требуют заголовок `X-Api-Token: <token>`.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/v1/niches/top` | Топ-ниши по скору (пагинация, фильтр по категории) |
| GET | `/v1/niches/search?q=...` | Полнотекстовый или семантический поиск (`query_embed=true`) |
| GET | `/v1/niches/{id}` | Детали ниши (pain points, конкуренты, метрики) |
| GET | `/v1/niches/{id}/similar` | Похожие ниши (pgvector cosine distance) |
| GET | `/v1/niches/export` | Экспорт CSV / JSONL |
| GET | `/internal/niches/top` | Топ (упрощённая схема) |
| GET | `/internal/niches/search` | Поиск (упрощённая схема) |
| GET | `/internal/niches/{id}` | Детали (упрощённая схема) |
| GET | `/internal/niches/{id}/similar` | Похожие (упрощённая схема) |
| POST | `/internal/feedback` | Отметить нишу (рейтинг/комментарий) |
| GET | `/internal/niches/{id}/entities` | Извлечение сущностей (Natasha) |
| GET | `/health` | Healthcheck |
| GET | `/ready` | Проверка готовности БД |

## Тесты и линтер

```bash
python -m pytest
python -m ruff check backend tests
```

## Ключевые каталоги

- `backend/app/api/` — роуты FastAPI
- `backend/app/services/` — парсеры, ML, wordstat, yandex_gpt, пайплайн ниш
- `backend/app/ml/` — RuBERT pain-классификатор, эмбеддинги
- `backend/app/models/` — SQLAlchemy-модели (niche_ideas, raw_posts, feedback, wordstat_cache)
- `backend/app/workers/tasks.py` — Celery-таски ETL
- `backend/scripts/migrate_drop_users.sql` — миграция из DaaS-режима
